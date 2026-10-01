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
