"""The open file.

``SessionWriter`` appends traces as they arrive rather than accumulating them
in RAM. 50,000 traces x 10,000 samples x float64 is 4 GB, and a crash at trace
49,000 should not cost the session.

**Raw volts only.** The stored arrays are what the ADC saw. Conductance is a
derived quantity that depends on three measured constants, any of which may be
revised later; storing it would turn a re-analysis into a lost dataset. The
corollary is that the config must travel with the data, which is why it is
written into the file's attributes on creation.

Igor wrote 100-trace blocks as separate ``.ibw`` files with 20 parameters
appended to each column (SavePullOut, Functions_STMBJ.ipf:438). One HDF5 file
per session replaces that: self-describing, appendable, crash-safe, and
readable by numpy, MATLAB and Igor alike.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np

from .config import RigConfig

log = logging.getLogger(__name__)

FORMAT_VERSION = 1


class SessionWriter:
    """Append traces to an HDF5 file, flushing as it goes."""

    def __init__(self, path: str | Path, cfg: RigConfig,
                 chunk_traces: int = 32, compression: str | None = "gzip"):
        self.path = Path(path)
        self.cfg = cfg
        self.chunk_traces = chunk_traces
        self.compression = compression
        self._h5 = None
        self._n = 0
        self._n_samples: int | None = None
        self._with_sense = False
        self._warned_sense = False

    # -- lifecycle --------------------------------------------------------

    def open(self) -> "SessionWriter":
        import h5py

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._h5 = h5py.File(self.path, "w")

        self._h5.attrs["format_version"] = FORMAT_VERSION
        self._h5.attrs["created_unix"] = time.time()
        self._h5.attrs["created_iso"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._h5.attrs["config_json"] = json.dumps(self.cfg.to_dict(),
                                                   indent=2)
        self._h5.attrs["units"] = (
            "voltage_v and current_v are raw volts at the ADC. "
            "piezo_sense_v, when present, is the piezo sense readback in raw "
            "volts (nm = volts * cal.sense_nm_per_volt). "
            "Conductance is derived, not stored.")
        log.info("writing to %s", self.path)
        return self

    def close(self) -> None:
        if self._h5 is None:
            return
        self._h5.attrs["n_traces"] = self._n
        self._h5.attrs["closed_unix"] = time.time()
        self._h5.close()
        self._h5 = None
        log.info("closed %s with %d traces", self.path, self._n)

    def __enter__(self) -> "SessionWriter":
        return self.open()

    def __exit__(self, *exc) -> bool:
        self.close()
        return False

    # -- writing ----------------------------------------------------------

    def _create(self, n_samples: int, with_sense: bool) -> None:
        h5 = self._h5
        self._n_samples = n_samples
        self._with_sense = with_sense
        chunks = (self.chunk_traces, n_samples)
        names = ["voltage_v", "current_v"]
        if with_sense:
            # Piezo sense readback, raw volts from the low-res card. Only
            # present in files from a two-card rig; readers must not assume it.
            names.append("piezo_sense_v")
        for name in names:
            h5.create_dataset(
                name, shape=(0, n_samples), maxshape=(None, n_samples),
                dtype="float64", chunks=chunks, compression=self.compression)
        for name, dtype in (("delay_samples", "int32"),
                            ("start_piezo_v", "float64"),
                            ("bias_v", "float64"),
                            ("sample_rate_hz", "float64"),
                            ("timestamp", "float64"),
                            ("attempt", "int64"),
                            ("end_conductance_g0", "float64"),
                            ("start_conductance_g0", "float64")):
            h5.create_dataset(name, shape=(0,), maxshape=(None,), dtype=dtype,
                              chunks=(max(64, self.chunk_traces),))

    def append(self, index: int, trace, selection=None) -> None:
        """Append one accepted trace. Signature matches ``on_trace``."""
        del index
        if self._h5 is None:
            raise RuntimeError("SessionWriter is not open")

        n_samples = trace.voltage_v.size
        sense = getattr(trace, "piezo_sense_v", None)
        if self._n_samples is None:
            self._create(n_samples, with_sense=sense is not None)
        elif n_samples != self._n_samples:
            raise ValueError(
                f"trace has {n_samples} samples but this file holds "
                f"{self._n_samples}; a ramp parameter changed mid-session")

        h5 = self._h5
        i = self._n
        rows = [("voltage_v", trace.voltage_v), ("current_v", trace.current_v)]
        if self._with_sense:
            if sense is None:
                # The readback went missing mid-session (a dropped read);
                # keep the file rectangular and make the gap visible.
                sense = np.full(n_samples, np.nan)
            rows.append(("piezo_sense_v", sense))
        elif sense is not None and not self._warned_sense:
            log.warning("first trace had no piezo sense readback, so this "
                        "file has no piezo_sense_v dataset; later readbacks "
                        "are not stored")
            self._warned_sense = True
        for name, value in rows:
            ds = h5[name]
            ds.resize(i + 1, axis=0)
            ds[i, :] = value

        scalars = {
            "delay_samples": trace.delay_samples,
            "start_piezo_v": trace.start_piezo_v,
            "bias_v": trace.bias_v,
            "sample_rate_hz": trace.sample_rate_hz,
            "timestamp": trace.timestamp,
            "attempt": trace.attempt,
            "end_conductance_g0":
                getattr(selection, "end_conductance", np.nan),
            "start_conductance_g0":
                getattr(selection, "start_conductance", np.nan),
        }
        for name, value in scalars.items():
            ds = h5[name]
            ds.resize(i + 1, axis=0)
            ds[i] = value

        self._n += 1
        if self._n % self.chunk_traces == 0:
            h5.attrs["n_traces"] = self._n       # so a killed session still counts
            h5.flush()

    def write_summary(self, stats: dict) -> None:
        if self._h5 is not None:
            self._h5.attrs["run_stats_json"] = json.dumps(stats, indent=2,
                                                          default=str)


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

class Session:
    """Read back a session file. Conductance is computed, never loaded."""

    def __init__(self, path: str | Path):
        import h5py
        self.path = Path(path)
        self._h5 = h5py.File(self.path, "r")
        self.cfg = RigConfig.from_dict(
            json.loads(self._h5.attrs["config_json"]))

    def __len__(self) -> int:
        # The dataset is the truth. The n_traces attribute is only final
        # when the writer closed cleanly, so a file from a session that was
        # killed, or one still being written, would otherwise read as empty.
        if "current_v" in self._h5:
            return int(self._h5["current_v"].shape[0])
        return int(self._h5.attrs.get("n_traces", 0))

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *exc) -> bool:
        self._h5.close()
        return False

    def close(self) -> None:
        self._h5.close()

    def raw(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        return (self._h5["voltage_v"][i], self._h5["current_v"][i])

    @property
    def has_piezo_sense(self) -> bool:
        """Was this session recorded with the piezo sense line?"""
        return "piezo_sense_v" in self._h5

    def piezo_sense(self, i: int, in_nm: bool = True) -> np.ndarray | None:
        """Piezo sense readback of trace ``i``, in nm (or raw volts), or None
        for a file from a one-card rig."""
        if not self.has_piezo_sense:
            return None
        v = self._h5["piezo_sense_v"][i]
        return self.cfg.cal.sense_volts_to_nm(v) if in_nm else v

    def conductance(self, i: int, cal=None,
                    use_measured_voltage: bool = True) -> np.ndarray:
        """Conductance in G0, using a calibration you may override.

        Passing a corrected ``cal`` is the whole reason raw volts are stored:
        a preamp gain re-measured next month reprocesses this file rather than
        invalidating it.
        """
        from . import analysis
        cal = cal or self.cfg.cal
        voltage, current = self.raw(i)
        if use_measured_voltage:
            return analysis.to_conductance(current, cal, voltage_v=voltage)
        return analysis.to_conductance(current, cal,
                                       bias_v=float(self._h5["bias_v"][i]))

    def conductances(self, cal=None, use_measured_voltage: bool = True):
        for i in range(len(self)):
            yield self.conductance(i, cal, use_measured_voltage)

    def scalar(self, name: str) -> np.ndarray:
        return self._h5[name][:]


# --------------------------------------------------------------------------
# Igor interoperability
# --------------------------------------------------------------------------

def load_ibw(path: str | Path) -> np.ndarray:
    """Load an Igor binary wave. Needs ``igor2``.

    Igor's conductance blocks are 2D: one column per trace, with the trace
    followed by two blank points and then 20 parameters
    (Functions_STMBJ.ipf:501, 526-530). Use :func:`split_igor_block` to
    separate them.
    """
    from igor2 import binarywave
    return np.asarray(binarywave.load(str(path))["wave"]["wData"])


def write_ibw(path: str | Path, name: str, data: np.ndarray,
              note: str = "", dx: float = 1.0, x0: float = 0.0,
              data_units: str = "", x_units: str = "") -> Path:
    """Write a numeric array as an Igor Binary Wave, format version 5.

    Igor's own loader reads this (File -> Load Waves -> Load Igor Binary),
    and so does ``igor2`` (see :func:`load_ibw`). Layout, from Igor's
    Technical Note 003: a 64-byte BinHeader5, a 320-byte WaveHeader5, the
    data, then the note. A 2-D array is written column-major, which is how
    Igor stores a 2-D wave, so ``data[r, c]`` is Igor's ``w[r][c]``.

    ``name`` must be a legal Igor wave name: letters, digits and underscores,
    starting with a letter, at most 31 characters. ``dx``/``x0`` set the
    row (x) scaling, ``data_units`` and ``x_units`` the units (3 chars max
    in the header; longer units are dropped rather than truncated).
    """
    import struct

    data = np.asarray(data)
    if data.ndim not in (1, 2):
        raise ValueError(f"an Igor wave of {data.ndim} dimensions is not "
                         f"supported here (1 or 2)")
    if not name or len(name) > 31 or not name[0].isalpha() or \
            not all(ch.isalnum() or ch == "_" for ch in name):
        raise ValueError(f"{name!r} is not a legal Igor wave name (letters, "
                         f"digits, underscores; starts with a letter; <= 31)")

    if data.dtype == np.float32:
        igor_type, fmt_dtype = 2, "<f4"            # NT_FP32
    elif data.dtype == np.float64:
        igor_type, fmt_dtype = 4, "<f8"            # NT_FP64
    elif np.issubdtype(data.dtype, np.integer):
        igor_type, fmt_dtype = 0x20, "<i4"         # NT_I32
        data = data.astype(np.int32)
    else:
        igor_type, fmt_dtype = 4, "<f8"
        data = data.astype(np.float64)
    payload = np.ascontiguousarray(data.ravel(order="F")).astype(fmt_dtype).tobytes()

    n_dim = [0, 0, 0, 0]
    n_dim[0] = int(data.shape[0])
    if data.ndim == 2:
        n_dim[1] = int(data.shape[1])
    npnts = int(data.size)
    note_bytes = note.encode("utf-8")
    igor_epoch = 2082844800                       # 1904-01-01 -> 1970-01-01
    now = int(time.time()) + igor_epoch

    def units(s: str) -> bytes:
        s = s.encode("ascii", "ignore")
        return (s if len(s) <= 3 else b"").ljust(4, b"\0")

    # WaveHeader5 (320 bytes before wData), little-endian, standard sizes.
    wave_header = struct.pack(
        "<L L L l h h 6s h 32s l L 4l 4d 4d 4s 16s h h d d L 4L 4L L 16l "
        "h h h c c L l h h L L",
        0,                      # next
        now, now,               # creationDate, modDate
        npnts,
        igor_type,
        0,                      # dLock
        b"\0" * 6,              # whpad1
        1,                      # whVersion
        name.encode("ascii").ljust(32, b"\0"),
        0,                      # whpad2
        0,                      # dFolder
        *n_dim,
        float(dx), 1.0, 1.0, 1.0,         # sfA
        float(x0), 0.0, 0.0, 0.0,         # sfB
        units(data_units),
        units(x_units) + b"\0" * 12,      # dimUnits[4][4]
        0, 0,                             # fsValid, whpad3
        0.0, 0.0,                         # top/botFullScale
        0,                                # dataEUnits
        0, 0, 0, 0,                       # dimEUnits
        0, 0, 0, 0,                       # dimLabels
        0,                                # waveNoteH
        *([0] * 16),                      # whUnused
        0, 0, 0,                          # aModified, wModified, swModified
        b"\0", b"\0",                     # useBits, kindBits
        0, 0, 0, 0, 0, 0)                 # formula, depID, whpad4, srcFldr,
                                          # fileName, sIndices
    assert len(wave_header) == 320, len(wave_header)

    def bin_header(checksum: int) -> bytes:
        return struct.pack(
            "<h h l l l l 4l 4l l l l",
            5,                            # version
            checksum,
            320 + len(payload),           # wfmSize
            0,                            # formulaSize
            len(note_bytes),              # noteSize
            0,                            # dataEUnitsSize
            0, 0, 0, 0,                   # dimEUnitsSize
            0, 0, 0, 0,                   # dimLabelsSize
            0, 0, 0)                      # sIndicesSize, optionsSize1/2

    # Igor's checksum: the 16-bit words of the two headers (wData excluded)
    # must sum to zero, modulo 2^16.
    head = bin_header(0) + wave_header
    total = sum(struct.unpack("<192h", head)) & 0xFFFF
    checksum = (-total) & 0xFFFF
    if checksum >= 0x8000:
        checksum -= 0x10000
    head = bin_header(checksum) + wave_header
    assert sum(struct.unpack("<192h", head)) & 0xFFFF == 0

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(head)
        fh.write(payload)
        fh.write(note_bytes)
    return path


IGOR_PARAMETER_SLOTS = 20


def igor_parameters(cfg: RigConfig, start_piezo_v: float = 0.0,
                    timestamp: float | None = None) -> np.ndarray:
    """The 20-entry parameter column Igor appended to every saved trace.

    Slot layout from SavePullOut (Functions_STMBJ.ipf:501, 526-530), the
    same one :func:`split_igor_block` reads back. Slots Igor used for things
    this package does not have (6-8, 11, 14) are NaN.
    """
    R, C, K = cfg.ramp, cfg.cal, cfg.keithley
    p = np.full(IGOR_PARAMETER_SLOTS, np.nan)
    p[0] = R.pull_length_nm                        # pull length nm
    p[1] = R.pull_rate_nm_per_s                    # pull rate nm/s
    p[2] = R.approach_step_nm                      # approach step nm
    p[3] = C.piezo_volts_to_nm(start_piezo_v)      # piezo offset nm (start)
    p[4] = 0.0                                     # bias-save flag
    p[5] = R.pull_length_nm                        # piezo travel nm
    p[9] = 10.0 ** (6 - K.gain_exponent)           # current/volt, uA per V
    p[10] = R.bias_v * 1e3                         # tip bias mV
    p[12] = K.series_resistance_ohm                # series resistance
    p[13] = R.engage_g0                            # conductance threshold
    p[15] = 0.0                                    # Vzero
    p[16] = 0.0                                    # Izero (Find Offset result)
    t = time.time() if timestamp is None else timestamp
    p[17] = t + 2082844800                         # Igor datetime (from 1904)
    p[18] = cfg.echem.gate_mv                      # gate voltage
    p[19] = K.suppress_const                       # current suppress
    return p


def save_igor_block(path: str | Path, cfg: RigConfig, traces_g0,
                    start_piezo_v=None, timestamps=None,
                    name: str | None = None) -> Path:
    """Write conductance traces as one Igor block, Igor's SavePullOut layout.

    One column per trace: the conductance in G0, two blank points (NaN),
    then the 20 parameters. Loads straight into Igor and into the analysis
    procedures that expect ``PullOut`` blocks; :func:`load_ibw` +
    :func:`split_igor_block` read it back here. Single precision, as Igor's
    waves were. ``name`` defaults to the file's stem.
    """
    traces = [np.asarray(t, dtype=float) for t in traces_g0]
    if not traces:
        raise ValueError("no traces to write")
    n = traces[0].size
    if any(t.size != n for t in traces):
        raise ValueError("all traces in one block must have the same length")
    n_traces = len(traces)
    start_piezo_v = [0.0] * n_traces if start_piezo_v is None \
        else list(start_piezo_v)
    timestamps = [None] * n_traces if timestamps is None else list(timestamps)

    block = np.full((n + 2 + IGOR_PARAMETER_SLOTS, n_traces), np.nan,
                    dtype=np.float32)
    for k, tr in enumerate(traces):
        block[:n, k] = tr
        block[n + 2:, k] = igor_parameters(cfg, start_piezo_v[k], timestamps[k])

    path = Path(path)
    wave_name = name or _igor_name(path.stem)
    note = (f"stmlab conductance block, {n_traces} traces x {n} samples; "
            f"rows: trace (G/G0), 2 blank, 20 parameters (SavePullOut layout); "
            f"x = {cfg.ramp.pull_rate_nm_per_s / cfg.ramp.sample_rate_hz:.6g} "
            f"nm per point")
    return write_ibw(path, wave_name, block, note=note,
                     dx=cfg.ramp.pull_rate_nm_per_s / cfg.ramp.sample_rate_hz,
                     data_units="", x_units="nm")


def _igor_name(stem: str) -> str:
    """A legal Igor wave name made from a file stem."""
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in stem)
    if not cleaned or not cleaned[0].isalpha():
        cleaned = "w_" + cleaned
    return cleaned[:31]


def split_igor_block(block: np.ndarray, n_parameters: int = 20
                     ) -> tuple[np.ndarray, np.ndarray]:
    """Split an Igor conductance block into (traces, parameters).

    Returns traces as (n_traces, n_samples) and parameters as
    (n_traces, n_parameters), matching the ParameterWave layout Igor appended:

        0 pull length nm      9 current/volt conversion   15 Vzero
        1 pull rate nm/s     10 tip bias mV               16 Izero
        2 approach step nm   11 -                         17 Igor datetime
        3 piezo offset nm    12 series resistance         18 gate voltage
        4 bias-save flag     13 conductance threshold     19 current suppress
        5 piezo travel nm    14 -
    """
    block = np.asarray(block)
    if block.ndim != 2:
        raise ValueError(f"expected a 2D block, got shape {block.shape}")
    n_samples = block.shape[0] - 2 - n_parameters
    traces = block[:n_samples, :].T
    parameters = block[n_samples + 2:, :].T
    return traces, parameters


# --------------------------------------------------------------------------
# Cyclic voltammetry
# --------------------------------------------------------------------------
#
# A CV cycle is not a trace: it has no piezo axis, no alignment spike, and no
# accept/reject verdict. It gets its own schema rather than being bent into
# the trace one, but obeys the same rule -- raw volts plus the config, never
# derived current.

def save_cv_cycles(path: str | Path, cfg: RigConfig, cycles: list,
                   kind: str = "highres") -> Path:
    """Write CV cycles from :func:`echem.run_cv` to HDF5.

    All cycles of one run share a ramp, so ``applied_v`` and ``keep`` are
    stored once rather than per cycle. ``keep`` is Igor's masking as a
    boolean: False over the switch-on quarter and the repeated tail, which
    Igor NaN-ed outright. Keeping the mask beside the full record instead of
    destroying the samples means a later reader can second-guess the choice.
    """
    import h5py

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cycles:
        raise ValueError("no CV cycles to save")

    first = cycles[0]
    with h5py.File(path, "w") as h5:
        h5.attrs["format_version"] = FORMAT_VERSION
        h5.attrs["record_kind"] = "cv"
        h5.attrs["cv_variant"] = kind
        h5.attrs["created_unix"] = time.time()
        h5.attrs["created_iso"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        h5.attrs["config_json"] = json.dumps(cfg.to_dict(), indent=2)
        h5.attrs["n_cycles"] = len(cycles)
        h5.attrs["rate_hz"] = first.rate_hz
        h5.attrs["gate_mv"] = cfg.echem.gate_mv
        h5.attrs["units"] = (
            "applied_v is the commanded electrode potential in volts. "
            "tip_current_v is raw preamp output in volts; divide by "
            "cal.preamp_gain_v_per_a for amps. Current is derived, not stored.")

        h5.create_dataset("applied_v", data=first.applied_v, dtype="float64")
        h5.create_dataset("keep", data=first.keep, dtype="bool")
        h5.create_dataset(
            "tip_current_v",
            data=np.stack([c.tip_current_v for c in cycles]), dtype="float64")
        if first.we_voltage_mv is not None:
            h5.create_dataset(
                "we_voltage_mv",
                data=np.stack([c.we_voltage_mv for c in cycles]),
                dtype="float64")
    log.info("wrote %d CV cycle(s) to %s", len(cycles), path)
    return path


class CVSession:
    """Read back a CV file written by :func:`save_cv_cycles`."""

    def __init__(self, path: str | Path):
        import h5py
        self.path = Path(path)
        self._h5 = h5py.File(self.path, "r")
        if self._h5.attrs.get("record_kind") != "cv":
            self._h5.close()
            raise ValueError(f"{path} is not a CV file")
        self.cfg = RigConfig.from_dict(
            json.loads(self._h5.attrs["config_json"]))
        self.kind = str(self._h5.attrs.get("cv_variant", "highres"))
        self.rate_hz = float(self._h5.attrs["rate_hz"])

    def __len__(self) -> int:
        return int(self._h5.attrs.get("n_cycles", 0))

    def __enter__(self) -> "CVSession":
        return self

    def __exit__(self, *exc) -> bool:
        self._h5.close()
        return False

    def close(self) -> None:
        self._h5.close()

    @property
    def applied_v(self) -> np.ndarray:
        return self._h5["applied_v"][:]

    @property
    def keep(self) -> np.ndarray:
        return self._h5["keep"][:]

    def current_a(self, i: int, cal=None) -> np.ndarray:
        """Cell current in amps, using a calibration you may override."""
        cal = cal or self.cfg.cal
        return cal.volts_to_amps(self._h5["tip_current_v"][i])

    def we_voltage_mv(self, i: int) -> np.ndarray | None:
        if "we_voltage_mv" not in self._h5:
            return None
        return self._h5["we_voltage_mv"][i]
