"""Igor's saving scheme, written and read from Python.

The lab's Igor code (``SavePullOut`` in Functions_STMBJ.ipf) stored every
day's traces in one folder, 100 traces to a block, one ``.ibw`` file per
block and per kind of signal. This module writes exactly those files, so
Igor's analysis macro (STMBJ_HistogramAnalysis.ipf: ``LoadCond``,
``LoadCurrent``, ``LoadVoltage``, ``LoadHist``) opens a Python day as if
Igor had taken it -- and it reads them, so ``plot.py`` draws the old Igor
days as well. Every number below was checked against the July 2026 data on
the NAS with ``igor2``; see IGOR_SCHEME_SPEC.md for the full account.

**The folder.** ``MakePath`` named it ``MM_DD<SetupID>YYMerge``, e.g.
``10_22_26Merge`` on 22 Oct 2026 with the default SetupID ``_``. Igor took
the day as the two characters before the comma of ``Date()``, which not
every system zero-pads, so a folder can read ``05_ 2_05Merge``;
:func:`parse_day_folder_name` accepts that (and a bare ``5_2_05``), while
:func:`day_folder_name` always writes ``MM_DD``. Copies on the NAS were
renamed by hand to ``07_16_26``; the readers here accept any folder and
only care about the file names inside it.

**The numbering.** Igor's ``G_PullOutNumber`` -- called ``Saved`` here --
starts at 1 and counts through the whole day. Block ``k`` holds traces
``(k-1)*100+1 .. k*100``; column ``c`` (0-based) of the block is trace
``(k-1)*100 + c + 1``.

**The files of block k** (all float32, wave name = file stem, version-5 IBW):

    PullOutConductanceBlock_k.ibw      (N+22, 100)  G/G0; always written
    PullOutVoltageBlock_k.ibw          (N, 100)     junction voltage, V
    PullOutCurrentBlock_k.ibw          (N, 100)     current, A
    PullOutExtensionBlock_k.ibw        (N, 100)     piezo readback, nm
    PullOutVoltageLowResBlock_k.ibw    (N, 100)     (other Igor variant; read only)
    PullOutPiezoBiasWave_k.ibw         (N,) float64 the applied piezo ramp, V
    PullOutConductanceBlockHist_k.ibw  (1000,)      log10(G/G0) histogram

Each ConductanceBlock column is the N-point trace, then two rows that are
exactly 0, then the 20 ``ParameterWave`` slots (:data:`PARAM_NAMES`).
Columns of traces not yet taken are NaN. The companions carry Igor's
``SetScale/I x 0, Size``: x = Size * i / (N-1), i.e. dx = Size/(N-1).

**Three deliberate differences from Igor**, none of which changes a complete
block: (1) a partial block is written at the end of every run instead of
being lost, with its empty columns NaN; (2) the next run continues the
numbering from the folder and refills that partial block in place;
(3) the ConductanceBlock carries a one-line wave note with the program
version, experiment, operator and trace range (Igor left it empty and
``LoadWave`` ignores notes).

Reading from this file
----------------------
:func:`read_block`, :func:`read_day_folder`, :func:`list_blocks`,
:func:`read_hist_wave`, :func:`read_wave`, :func:`split_block`.

Writing from this file
----------------------
:class:`IgorDayWriter` (one per day; handles the numbering and the resume),
:func:`write_block_files` (one block), :func:`block_histogram`,
:class:`IgorTrace` (what one trace must carry), :func:`igor_parameters`.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import analysis
from .config import RigConfig
from .storage import IGOR_EPOCH_OFFSET, igor_datetime, unix_from_igor_datetime, write_ibw  # noqa: F401

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# The constants of the layout
# --------------------------------------------------------------------------

BLOCK = 100               # traces per block
PARAM_SLOTS = 20          # Igor's ParameterWave
TAIL_ROWS = 2 + PARAM_SLOTS   # two zero rows + the parameters = 22

# Igor's DateTime is *local* seconds since 1904-01-01. ``IGOR_EPOCH_OFFSET``,
# ``igor_datetime`` and ``unix_from_igor_datetime`` live in storage.py (the
# IBW header dates use them too) and are re-exported from here.

# The block histogram: Igor's ``SetScale/I x -8, 2`` over 1000 points.
HIST_POINTS = 1000
HIST_X0 = -8.0
HIST_X1 = 2.0
HIST_DX = (HIST_X1 - HIST_X0) / (HIST_POINTS - 1)     # 10/999

# What each ParameterWave slot holds (Igor name, unit). Unused slots are 0.
PARAM_NAMES = (
    "Size: pull length, nm",                               # 0
    "Rate: pull rate, nm/s",                               # 1
    "approach step, nm",                                   # 2
    "PiezoOffset_nm after the pull, nm",                   # 3
    "BiasSave flag (1 = Voltage block written)",           # 4
    "StartX - StopX: sense readback start minus end, nm",  # 5
    "tip thermocouple average (0 on this rig)",            # 6
    "substrate thermocouple average (0 on this rig)",      # 7
    "unused (0)",                                          # 8
    "CurrentVoltConversion, uA per V = 10^(6 - gain)",     # 9
    "TipBias, mV",                                         # 10
    "unused (0)",                                          # 11
    "SeriesResistance, ohm",                               # 12
    "ConductanceThreshold, G0 (engage)",                   # 13
    "unused (0)",                                          # 14
    "Vzero, mV (last Find-Offset result)",                 # 15
    "Izero (last Find-Offset result)",                     # 16
    "PullOutTime: Igor DateTime, local-time s since 1904-01-01",  # 17
    "gate voltage, mV",                                    # 18
    "CurrentSuppress, uA = const * 10^(3 - gain)",         # 19
)

# File name of each kind of block file; ``{k}`` is the block number.
FILE_PATTERNS = {
    "conductance": "PullOutConductanceBlock_{k}.ibw",
    "voltage": "PullOutVoltageBlock_{k}.ibw",
    "current": "PullOutCurrentBlock_{k}.ibw",
    "extension": "PullOutExtensionBlock_{k}.ibw",
    "voltage_lowres": "PullOutVoltageLowResBlock_{k}.ibw",
    "piezo_wave": "PullOutPiezoBiasWave_{k}.ibw",
    "hist": "PullOutConductanceBlockHist_{k}.ibw",
}

_CONDUCTANCE_RE = re.compile(r"^PullOutConductanceBlock_(\d+)\.ibw$")
# MM_DD<SetupID>YY[Merge]. The day may be space-padded or a single digit:
# MakePath took the two characters before the comma of Igor's Date(), and
# not every system zero-pads it ("05_ 2_05Merge"). Writing is always MM_DD.
_DAY_FOLDER_RE = re.compile(r"^(\d{1,2})_(\s?\d{1,2})(\D*?)(\d{2})(?:Merge)?$")


def block_file(folder: str | Path, kind: str, k: int) -> Path:
    """The path of block ``k``'s file of one ``kind`` (a key of
    :data:`FILE_PATTERNS`) inside ``folder``."""
    return Path(folder) / FILE_PATTERNS[kind].format(k=int(k))


# --------------------------------------------------------------------------
# The day folder
# --------------------------------------------------------------------------

def day_folder_name(when: float | None = None, setup_id: str = "_") -> str:
    """Igor's ``MakePath`` folder name for a moment in time: ``MM_DD`` +
    SetupID + ``YY`` + ``Merge``, e.g. ``"10_22_26Merge"`` for 22 Oct 2026
    with the default SetupID ``"_"``. ``when`` is Unix time (now if None);
    the local date is used, as Igor's ``Date()`` did."""
    t = time.localtime(time.time() if when is None else when)
    return f"{t.tm_mon:02d}_{t.tm_mday:02d}{setup_id}{t.tm_year % 100:02d}Merge"


def parse_day_folder_name(name: str) -> tuple[int, int, int, str] | None:
    """Take a day folder name apart: ``(yy, mm, dd, setup_id)``, or None
    when the name is not one. Accepts Igor's own ``10_22_26Merge``, the
    hand-renamed ``07_16_26`` (no ``Merge``) and a space-padded or
    single-digit day (``05_ 2_05Merge``, ``5_2_05``: Igor's ``Date()`` is
    not zero-padded on every system) alike; the setup id is whatever sits
    between the day and the year (``"_"`` by default)."""
    m = _DAY_FOLDER_RE.match(Path(name).name)
    if m is None:
        return None
    mm, dd, setup_id, yy = int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4))
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return None
    return yy, mm, dd, setup_id


# --------------------------------------------------------------------------
# What gets saved per trace
# --------------------------------------------------------------------------

@dataclass
class SaveFlags:
    """Igor's save check boxes. Igor's own defaults were Bias 0, Current 0,
    Sense 0, Hist 1, PiezoWave 0; the lab's July 2026 practice was Bias,
    Current and Sense on, which is the default here."""
    bias: bool = True          # G_BiasSaveCheck: PullOutVoltageBlock_k
    current: bool = True       # G_CurrentSaveCheck: PullOutCurrentBlock_k
    sense: bool = True         # G_SenseSaveCheck: PullOutExtensionBlock_k (if the rig has a sense line)
    hist: bool = True          # G_HistSaveCheck: PullOutConductanceBlockHist_k
    piezo_wave: bool = False   # G_PiezoWaveSaveCheck: PullOutPiezoBiasWave_k


def igor_parameters(cfg: RigConfig, start_piezo_v: float, timestamp: float, *,
                    extension_nm: np.ndarray | None = None,
                    vzero_mv: float = 0.0, izero: float = 0.0,
                    bias_save: bool = True) -> np.ndarray:
    """The 20 ``ParameterWave`` slots of one trace (float64; stored as
    float32). Slot by slot in :data:`PARAM_NAMES`; unused slots are 0, as
    Igor's were.

    ``start_piezo_v`` is the piezo voltage at contact, where the pull began;
    Igor recorded ``PiezoOffset_nm`` *after* the pull had moved the piezo by
    the pull length, so slot 3 is the start position minus the pull length.
    Slot 5 is Igor's ``StartX - StopX``: the sense readback averaged over the
    first 1000 points minus the average over the last 1000, when there is a
    readback (``extension_nm``), else the pull length. Slot 17 is Igor's
    DateTime, :func:`igor_datetime` of ``timestamp``: *local* seconds
    since 1904-01-01, as Igor's clock counts (verified on the July 2026
    headers; UTC + 2082844800 would be 4 h off in EDT).
    """
    R, C, K = cfg.ramp, cfg.cal, cfg.keithley
    p = np.zeros(PARAM_SLOTS, dtype=float)
    p[0] = R.pull_length_nm
    p[1] = R.pull_rate_nm_per_s
    p[2] = R.approach_step_nm
    p[3] = C.piezo_volts_to_nm(start_piezo_v) - R.pull_length_nm
    p[4] = 1.0 if bias_save else 0.0
    if extension_nm is not None and np.asarray(extension_nm).size:
        ext = np.asarray(extension_nm, dtype=float)
        p[5] = float(np.nanmean(ext[:1000]) - np.nanmean(ext[-1000:]))
    else:
        p[5] = R.pull_length_nm
    p[9] = 10.0 ** (6 - K.gain_exponent)
    p[10] = R.bias_v * 1e3
    p[12] = K.series_resistance_ohm
    p[13] = R.engage_g0
    p[15] = vzero_mv
    p[16] = izero
    p[17] = igor_datetime(timestamp)
    p[18] = cfg.echem.gate_mv
    p[19] = K.suppress_const * 10.0 ** (3 - K.gain_exponent)
    return p


@dataclass
class IgorTrace:
    """One accepted trace, converted to the physical units Igor saved.

    ``g0`` is the conductance in G/G0 (N points), ``voltage_v`` the measured
    junction voltage in volts (sign-corrected), ``current_a`` the current in
    amps, ``extension_nm`` the piezo sense readback in nm (None on a rig
    without a sense line), ``piezo_wave_v`` the piezo ramp that was applied,
    in volts, starting at 0 and going negative over the pull (Igor's
    ``PiezoBiasWave``), and ``params`` the 20 slots of
    :func:`igor_parameters`. Build one with :meth:`from_record`.
    """
    g0: np.ndarray
    voltage_v: np.ndarray
    current_a: np.ndarray
    extension_nm: np.ndarray | None
    piezo_wave_v: np.ndarray | None
    params: np.ndarray

    @classmethod
    def from_record(cls, tr, cfg: RigConfig, *, vzero_mv: float = 0.0,
                    izero: float = 0.0, bias_save: bool = True) -> "IgorTrace":
        """From a ``trace.TraceRecord`` (raw volts) with the rig's
        calibration: conductance from the *measured* junction voltage, as
        Igor computed it; ``vzero_mv``/``izero`` are the last Find-Offset
        results for slots 15 and 16; ``bias_save`` is slot 4."""
        cal = cfg.cal
        g0 = np.asarray(tr.conductance_g0(cfg), dtype=float)
        voltage_v = cal.voltage_input_sign * np.asarray(tr.voltage_v, dtype=float)
        current_a = np.asarray(cal.volts_to_amps(np.asarray(tr.current_v, dtype=float)))
        extension_nm = tr.piezo_sense_nm(cfg)
        if extension_nm is not None:
            extension_nm = np.asarray(extension_nm, dtype=float)
        disp_nm = analysis.displacement_nm(g0.size, cfg.ramp, tr.sample_rate_hz)
        piezo_wave_v = -disp_nm / cal.piezo_nm_per_volt
        params = igor_parameters(cfg, tr.start_piezo_v, tr.timestamp,
                                 extension_nm=extension_nm, vzero_mv=vzero_mv,
                                 izero=izero, bias_save=bias_save)
        return cls(g0, voltage_v, current_a, extension_nm, piezo_wave_v, params)

    @property
    def n(self) -> int:
        return int(self.g0.size)


# --------------------------------------------------------------------------
# Writing one block
# --------------------------------------------------------------------------

def _write(folder: Path, kind: str, k: int, data: np.ndarray, note: str = "",
           dx: float = 1.0, x0: float = 0.0) -> Path | None:
    """Write one block file; the wave name is the file stem, as Igor's
    ``Save/C`` made it. Returns None (with a warning) when the name is too
    long for an Igor wave, which only the Hist file can reach (k >= 1000)."""
    path = block_file(folder, kind, k)
    try:
        return write_ibw(path, path.stem, data, note=note, dx=dx, x0=x0)
    except ValueError as exc:
        log.warning("not writing %s: %s", path.name, exc)
        return None


def write_block_files(folder: str | Path, k: int, traces, cfg: RigConfig,
                      flags: SaveFlags, note: str = "") -> list[Path]:
    """Write every file of block ``k`` from up to 100 :class:`IgorTrace`
    (``traces[c]`` is column ``c``; None marks a column not yet taken, which
    is written as NaN). Returns the files written.

    Always the ConductanceBlock; the Voltage, Current, Extension, PiezoBias
    and Hist files per ``flags`` (the Extension file only when at least one
    trace has a readback). The histogram is divided by 100 for a complete
    block, exactly as Igor's ``LogHistFromBlocks``, and by the number of
    filled columns for a partial one, so it stays "counts per trace". When
    the block is complete, the per-trace files Igor wrote for the block's
    last trace when a flag was *off* (``PullOutExtension_<k*100>``,
    ``PullOutVoltage_<k*100>``, ``PullOutCurrent_<k*100>``; float64) are
    written too.
    """
    folder = Path(folder)
    traces = list(traces)
    if len(traces) > BLOCK:
        raise ValueError(f"a block holds at most {BLOCK} traces, got {len(traces)}")
    filled = [c for c, t in enumerate(traces) if t is not None]
    if not filled:
        return []
    n = traces[filled[0]].n
    for c in filled:
        if traces[c].n != n:
            raise ValueError(f"column {c} has {traces[c].n} points, the block "
                             f"has {n}; one block holds traces of one length")
    size_nm = float(traces[filled[0]].params[0])
    if not (np.isfinite(size_nm) and size_nm > 0):
        size_nm = float(cfg.ramp.pull_length_nm)
    dx = size_nm / (n - 1) if n > 1 else 1.0            # SetScale/I x 0, Size
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # The ConductanceBlock: trace, two zero rows, 20 parameters.
    block = np.full((n + TAIL_ROWS, BLOCK), np.nan, dtype=np.float32)
    for c in filled:
        t = traces[c]
        block[:n, c] = t.g0
        block[n:n + 2, c] = 0.0
        block[n + 2:, c] = t.params
    p = _write(folder, "conductance", k, block, note=note, dx=1.0, x0=0.0)
    written.append(p)

    def companion(kind: str, pick) -> None:
        arr = np.full((n, BLOCK), np.nan, dtype=np.float32)
        any_data = False
        for c in filled:
            v = pick(traces[c])
            if v is not None:
                arr[:, c] = v
                any_data = True
        if any_data:
            p = _write(folder, kind, k, arr, dx=dx, x0=0.0)
            if p is not None:
                written.append(p)

    if flags.bias:
        companion("voltage", lambda t: t.voltage_v)
    if flags.current:
        companion("current", lambda t: t.current_a)
    if flags.sense:
        companion("extension", lambda t: t.extension_nm)

    if flags.piezo_wave:
        # One ramp per block (the same for every trace): Igor's PiezoBiasWave,
        # a float64 wave with no x scaling.
        wave = next((traces[c].piezo_wave_v for c in reversed(filled)
                     if traces[c].piezo_wave_v is not None), None)
        if wave is not None:
            p = _write(folder, "piezo_wave", k, np.asarray(wave, dtype=np.float64))
            if p is not None:
                written.append(p)

    complete = len(filled) == BLOCK
    if flags.hist:
        hist = block_histogram([traces[c].g0 for c in filled], cfg,
                               BLOCK if complete else len(filled))
        p = _write(folder, "hist", k, hist.astype(np.float32), dx=HIST_DX, x0=HIST_X0)
        if p is not None:
            written.append(p)

    if complete:
        last = traces[BLOCK - 1]
        number = k * BLOCK
        if not flags.sense and last.extension_nm is not None:
            name = f"PullOutExtension_{number}"
            written.append(write_ibw(folder / f"{name}.ibw", name,
                                     np.asarray(last.extension_nm, dtype=np.float64),
                                     dx=dx, x0=0.0))
        if not flags.bias:
            for name, values in ((f"PullOutVoltage_{number}", last.voltage_v),
                                 (f"PullOutCurrent_{number}", last.current_a)):
                if values is not None:
                    written.append(write_ibw(folder / f"{name}.ibw", name,
                                             np.asarray(values, dtype=np.float64),
                                             dx=dx, x0=0.0))
    return [p for p in written if p is not None]


def block_histogram(g0_columns, cfg: RigConfig, n_divide: int) -> np.ndarray:
    """Igor's ``LogHistWave`` for one block: the 1000-point histogram of
    log10(G/G0) with Igor's bins (bin i starts at -8 + i*10/999), summed
    over the given conductance columns and divided by ``n_divide`` (100 for
    a complete block, as Igor did; the number of filled columns for a
    partial one).

    Per column, as ``LogHistFromBlocks``: keep the first 95 %, box-smooth
    over 11 points, take the mean over the 95-96 % window as the noise
    floor, and only if that floor is below ``cfg.ramp.break_g0`` subtract
    it, smooth again, take log10 and bin. Igor ran this on the whole block
    column -- the N points *plus* the 22 tail rows -- so its 95 % cut kept
    floor(0.95 * (N+22)) points; ``tail_rows=TAIL_ROWS`` of
    :func:`analysis.log_histogram` makes that same cut (capped at N, which
    only matters below 418 points), and plot.py takes the same path for
    Igor-block data, so the two agree bin for bin. (Constant-bias pulls
    only: the hold/push deletions of Igor's ramp modes are not reproduced.)
    """
    total = np.zeros(HIST_POINTS, dtype=float)
    for g0 in g0_columns:
        _, counts = analysis.log_histogram(
            [np.asarray(g0, dtype=float)], lo=HIST_X0, hi=HIST_X1, n_bins=HIST_POINTS,
            keep_fraction=0.95, smooth_width=11, zero_cutoff=cfg.ramp.break_g0,
            subtract_floor=True, igor_bins=True, tail_rows=TAIL_ROWS)
        total += counts                    # one trace: counts/1 or all zeros
    return total / n_divide if n_divide else total


# --------------------------------------------------------------------------
# A day of writing
# --------------------------------------------------------------------------

class IgorDayWriter:
    """Igor's ``SavePullOut`` for one day: numbers the traces, keeps the
    current block in memory and writes its files when it completes.

    ``root`` is the data folder; the day folder ``root / day_folder_name(
    when, setup_id)`` is created on the first write. On creation the folder
    is scanned (:meth:`scan`) and the numbering continues where it stopped:
    ``saved`` is the number the next trace will get. A partial block found
    in the folder is read back and refilled in place, so a complete block
    is byte-for-byte what Igor would have written.

    Call :meth:`append` for every accepted trace, and :meth:`flush` (or
    :meth:`close`) when a run stops, so the partial block is on disk.

    ``note_fields`` go into the ConductanceBlock's wave note, e.g.
    ``{"version": "v65", "experiment": "clean gold", "operator": "MK"}``;
    ``version`` is written as ``pullout <version>``.
    """

    def __init__(self, root: str | Path, cfg: RigConfig, *, setup_id: str = "_",
                 flags: SaveFlags | None = None, when: float | None = None,
                 note_fields: dict | None = None):
        self.root = Path(root)
        self.cfg = cfg
        self.setup_id = setup_id
        self.flags = flags if flags is not None else SaveFlags()
        self.note_fields = dict(note_fields or {})
        self.folder = self.root / day_folder_name(when, setup_id)
        self._pending: list[IgorTrace | None] = []
        self._pending_k: int | None = None     # the block the pending traces belong to
        self._dirty = False
        k_last, filled = self.scan(self.folder)
        if k_last == 0:
            self.saved = 1
        else:
            self.saved = BLOCK * (k_last - 1) + filled + 1
            if 0 < filled < BLOCK:
                try:
                    self._pending = self._reload(k_last, filled)
                    self._pending_k = k_last
                except Exception as exc:              # noqa: BLE001
                    log.warning("block %d cannot be reloaded (%s: %s); continuing after it",
                                k_last, type(exc).__name__, exc)
                    self._pending = []
                    self.saved = BLOCK * k_last + 1
        log.info("Igor day folder %s: next trace (Saved) = %d", self.folder, self.saved)

    # -- the folder --------------------------------------------------------

    @staticmethod
    def scan(folder: str | Path) -> tuple[int, int]:
        """``(k_last, filled)``: the highest block number in the folder and
        how many of its columns are filled (the last filled column + 1);
        ``(0, 0)`` for an empty or missing folder. A last block that cannot
        be read is reported full, so nothing is ever written over it."""
        folder = Path(folder)
        ks = list_blocks(folder)
        if not ks:
            return 0, 0
        k_last = ks[-1]
        try:
            _, _, filled = split_block(read_wave(block_file(folder, "conductance", k_last)).data)
        except Exception as exc:                      # noqa: BLE001
            # igor2 raises ValueError on a file that is no IBW, TypeError on
            # a truncated one and AssertionError on a text wave; whatever
            # it is, the block is not ours to refill.
            log.warning("%s is not readable as a block (%s: %s); continuing after it",
                        block_file(folder, "conductance", k_last).name,
                        type(exc).__name__, exc)
            return k_last, BLOCK
        idx = np.flatnonzero(filled)
        return k_last, (int(idx[-1]) + 1 if idx.size else 0)

    def _reload(self, k: int, filled: int) -> list[IgorTrace | None]:
        """The traces of a partial block on disk, back in memory so the
        block can be refilled in place. A companion that is missing, or
        that cannot be read, gives NaN rows (the data was not saved then,
        or is lost; the ConductanceBlock is what counts)."""
        b = read_block(self.folder, k, companions=True)
        n = b.g0.shape[0]
        piezo_wave = None
        piezo_path = block_file(self.folder, "piezo_wave", k)
        if piezo_path.exists():
            try:
                piezo_wave = np.asarray(read_wave(piezo_path).data, dtype=float)
                if piezo_wave.ndim != 1 or piezo_wave.size != n:
                    raise ValueError(f"shape {piezo_wave.shape} is not one {n}-point ramp")
            except Exception as exc:                  # noqa: BLE001
                log.warning("%s cannot be used (%s: %s); the refilled block takes its "
                            "piezo wave from the next trace", piezo_path.name,
                            type(exc).__name__, exc)
                piezo_wave = None
        pending: list[IgorTrace | None] = [None] * filled

        def column(arr, j):
            return np.full(n, np.nan) if arr is None else np.asarray(arr[:, j], dtype=float)

        for j, c in enumerate(b.columns):
            if c >= filled:
                continue
            pending[c] = IgorTrace(
                g0=np.asarray(b.g0[:, j], dtype=float),
                voltage_v=column(b.voltage_v, j),
                current_a=column(b.current_a, j),
                extension_nm=None if b.extension_nm is None
                else np.asarray(b.extension_nm[:, j], dtype=float),
                piezo_wave_v=piezo_wave,
                params=np.asarray(b.params[j], dtype=float))
        return pending

    # -- state ---------------------------------------------------------------

    @property
    def current_block(self) -> int:
        """The block number the next trace goes into."""
        return (self.saved - 1) // BLOCK + 1

    @property
    def n_pending(self) -> int:
        """Traces of the current block held in memory (filled columns)."""
        return sum(t is not None for t in self._pending)

    def _note(self, k: int) -> str:
        idx = [c for c, t in enumerate(self._pending) if t is not None]
        first = (k - 1) * BLOCK + 1
        last = first + (idx[-1] if idx else 0)
        fields = dict(self.note_fields)
        head = "pullout" + (f" {fields.pop('version')}" if "version" in fields else "")
        parts = [head] + [f"{key}={value}" for key, value in fields.items()]
        parts.append(f"traces {first}-{last}")
        parts.append("written " + time.strftime("%Y-%m-%dT%H:%M:%S"))
        return "; ".join(parts)

    # -- writing -------------------------------------------------------------

    def append(self, t: IgorTrace) -> int:
        """Store one trace under the next number and return that number.
        When it is the 100th of its block, the block's files are written.

        A trace of a different length than the block in progress cannot go
        into the same files: the partial block is written as it is and the
        numbering jumps to the next block, which starts with this trace
        (a warning says so). Igor could not represent this either.

        The write of a completed block is transactional: the trace is
        placed, the files are written, and only then does the numbering
        move on. When the write fails (the NAS is gone, the disk is full)
        the slot is put back as it was and the exception is re-raised:
        nothing is renumbered, the traces already in the block stay pending
        for the next :meth:`flush` or the next 100th trace, and the caller
        decides what to do with the trace that was not saved.
        """
        filled = [x for x in self._pending if x is not None]
        if filled and t.n != filled[0].n:
            log.warning("trace has %d points, block %d holds %d-point traces; "
                        "writing the partial block and starting block %d",
                        t.n, self.current_block, filled[0].n, self.current_block + 1)
            self.flush()
            self.saved = self.current_block * BLOCK + 1
            self._pending = []
            self._pending_k = None
        number = self.saved
        k = (number - 1) // BLOCK + 1
        c = (number - 1) % BLOCK
        previous_k = self._pending_k
        if previous_k is None:
            self._pending_k = k                       # the first trace of a block
        previous_len = len(self._pending)
        while len(self._pending) <= c:
            self._pending.append(None)
        previous = self._pending[c]
        self._pending[c] = t
        if c == BLOCK - 1:
            try:
                write_block_files(self.folder, k, self._pending, self.cfg, self.flags,
                                  note=self._note(k))
            except BaseException:
                # Not written: put the slot back, so the numbering, the
                # pending block and what is on disk still agree.
                if previous_len <= c:
                    del self._pending[previous_len:]
                else:
                    self._pending[c] = previous
                self._pending_k = previous_k
                raise
            self._pending = []
            self._pending_k = None
            self._dirty = False
        else:
            self._dirty = True
        self.saved = number + 1
        return number

    def flush(self) -> list[Path]:
        """Write the block in progress now, as a partial block (NaN in the
        columns not yet taken). Returns the files written; nothing is
        written when nothing changed since the last write."""
        if not self._dirty or not any(t is not None for t in self._pending):
            return []
        # The block the pending traces belong to, kept explicitly rather
        # than derived from ``saved``, so a failed write can never make the
        # flush file them under the next block's number.
        k = self._pending_k if self._pending_k is not None else self.current_block
        files = write_block_files(self.folder, k, self._pending, self.cfg, self.flags,
                                  note=self._note(k))
        self._dirty = False
        return files

    def close(self) -> list[Path]:
        """Same as :meth:`flush`."""
        return self.flush()

    def __enter__(self) -> "IgorDayWriter":
        return self

    def __exit__(self, *exc) -> bool:
        self.flush()
        return False


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

@dataclass
class IgorWave:
    """One Igor binary wave as read from disk: the data, its x scaling
    (x = x0 + i*dx), the wave name and the note."""
    data: np.ndarray
    dx: float
    x0: float
    name: str
    note: str
    path: Path


def read_wave(path: str | Path) -> IgorWave:
    """Read any ``.ibw`` with its header. Needs ``igor2``."""
    from igor2 import binarywave
    path = Path(path)
    w = binarywave.load(str(path))["wave"]
    header = w["wave_header"]
    data = np.asarray(w["wData"])
    # Version-5 waves scale by sfA/sfB per dimension; version-2 and -3
    # waves (Igor 3 and older, as the lab's oldest saved histograms may
    # be) by the scalars hsA/hsB.
    sfa = header.get("sfA", header.get("hsA", 1.0))
    sfb = header.get("sfB", header.get("hsB", 0.0))
    dx = float(np.asarray(sfa).ravel()[0]) if np.size(sfa) else 1.0
    x0 = float(np.asarray(sfb).ravel()[0]) if np.size(sfb) else 0.0
    name = header.get("bname", b"")
    if isinstance(name, bytes):
        name = name.split(b"\0", 1)[0].decode("ascii", "ignore")
    note = w.get("note", b"")
    if isinstance(note, bytes):
        note = note.decode("utf-8", "ignore")
    return IgorWave(data, dx, x0, str(name), str(note), path)


def split_block(block_2d: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Take a ConductanceBlock apart: ``(g0, params, filled)`` with ``g0`` of
    shape (N, cols) -- all columns, NaN where empty --, ``params`` of shape
    (cols, 20) and ``filled`` a boolean mask over the columns.

    The 22-row tail is recognised by: more than 22 rows; rows N and N+1
    both exactly 0 (Igor) or both NaN (this package's legacy ``_bNNN``
    export) in every filled column; and slots 0 (pull length) and 1 (pull
    rate) positive in every filled column. Anything else -- a bare trace, a
    companion block, a histogram -- raises ValueError.
    """
    block = np.asarray(block_2d, dtype=float)
    if block.ndim == 1:
        block = block[:, None]
    if block.ndim != 2:
        raise ValueError(f"a {block.ndim}-D wave is not a block of traces")
    rows = block.shape[0]
    if rows <= TAIL_ROWS:
        raise ValueError(f"{rows} rows: no room for a trace and the {TAIL_ROWS}-row tail")
    n = rows - TAIL_ROWS
    g0 = block[:n, :]
    filled = np.isfinite(g0).any(axis=0)
    if not filled.any():
        raise ValueError("no column holds a trace (all NaN)")
    blanks = block[n:n + 2, :][:, filled]
    if not ((blanks == 0.0).all() or np.isnan(blanks).all()):
        raise ValueError("rows N and N+1 are neither both 0 (Igor) nor both "
                         "NaN (legacy export): not a conductance block")
    params = block[n + 2:, :].T
    p = params[filled]
    if not ((p[:, 0] > 0) & (p[:, 1] > 0)).all():
        raise ValueError("the parameter rows have no positive pull length and "
                         "rate: not a conductance block")
    return g0, params, filled


def has_parameter_tail(block_2d: np.ndarray) -> bool:
    """True when :func:`split_block` accepts the array as a ConductanceBlock."""
    try:
        split_block(block_2d)
    except ValueError:
        return False
    return True


@dataclass
class IgorBlock:
    """Block ``k`` of a day folder, filled columns only.

    ``g0`` is (N, n_cols) in G/G0, ``params`` (n_cols, 20), ``columns`` the
    0-based column indices, ``numbers`` the day numbers of those traces.
    The companions are (N, n_cols) when their file exists, else None;
    ``hist`` is the block's 1000-point histogram when its file exists.
    ``displacement_nm`` is Igor's ``SetScale/I x 0, Size``: ``linspace(0,
    Size, N)`` with Size from slot 0.
    """
    k: int
    folder: Path
    g0: np.ndarray
    params: np.ndarray
    columns: np.ndarray
    numbers: np.ndarray
    voltage_v: np.ndarray | None = None
    current_a: np.ndarray | None = None
    extension_nm: np.ndarray | None = None
    voltage_lowres_v: np.ndarray | None = None
    hist: np.ndarray | None = None

    @property
    def n_traces(self) -> int:
        return int(self.numbers.size)

    @property
    def n_points(self) -> int:
        return int(self.g0.shape[0])

    @property
    def displacement_nm(self) -> np.ndarray:
        n = self.n_points
        if self.params.size == 0 or not np.isfinite(self.params[0, 0]):
            return np.arange(n, dtype=float)
        return np.linspace(0.0, float(self.params[0, 0]), n)

    def select(self, keep: np.ndarray) -> "IgorBlock":
        """A copy with only the columns where ``keep`` (a boolean mask over
        the filled columns) is True."""
        keep = np.asarray(keep, dtype=bool)

        def cut(arr):
            return None if arr is None else arr[:, keep]

        return IgorBlock(self.k, self.folder, self.g0[:, keep], self.params[keep],
                         self.columns[keep], self.numbers[keep],
                         cut(self.voltage_v), cut(self.current_a),
                         cut(self.extension_nm), cut(self.voltage_lowres_v), self.hist)


def list_blocks(folder: str | Path) -> list[int]:
    """The block numbers ``k`` whose ``PullOutConductanceBlock_k.ibw`` is in
    the folder, in numerical order (1, 2, ..., 10, 11, not 1, 10, 11, 2)."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    ks = []
    for p in folder.iterdir():
        m = _CONDUCTANCE_RE.match(p.name)
        if m:
            ks.append(int(m.group(1)))
    return sorted(ks)


def read_block(folder: str | Path, k: int, companions: bool = True) -> IgorBlock:
    """Block ``k`` of a day folder (Igor's own, the other Igor variant's,
    or this module's). With ``companions`` the Voltage, Current, Extension
    and VoltageLowRes blocks and the Hist wave are read when their files
    exist. Needs ``igor2``."""
    folder = Path(folder)
    wave = read_wave(block_file(folder, "conductance", k))
    g0_all, params_all, filled = split_block(wave.data)
    idx = np.flatnonzero(filled)
    block = IgorBlock(int(k), folder, g0_all[:, idx], params_all[idx], idx,
                      (int(k) - 1) * BLOCK + idx + 1)
    if companions:
        for kind, attr in (("voltage", "voltage_v"), ("current", "current_a"),
                           ("extension", "extension_nm"),
                           ("voltage_lowres", "voltage_lowres_v")):
            path = block_file(folder, kind, k)
            if not path.exists():
                continue
            try:
                data = read_wave(path).data
            except Exception as exc:                  # noqa: BLE001
                # A torn or foreign companion loses only itself: the
                # ConductanceBlock is what the traces are read from.
                log.warning("%s cannot be read (%s: %s); skipped",
                            path.name, type(exc).__name__, exc)
                continue
            if data.ndim == 1:
                data = data[:, None]
            if data.ndim != 2 or data.shape[0] != g0_all.shape[0] \
                    or data.shape[1] <= idx.max():
                log.warning("%s has shape %s, not a companion of block %d; skipped",
                            path.name, data.shape, k)
                continue
            setattr(block, attr, np.asarray(data[:, idx], dtype=float))
        hist_path = block_file(folder, "hist", k)
        if hist_path.exists():
            try:
                block.hist = read_hist_wave(hist_path)[1]
            except Exception as exc:                  # noqa: BLE001
                log.warning("%s cannot be read (%s: %s); skipped",
                            hist_path.name, type(exc).__name__, exc)
    return block


def read_day_folder(folder: str | Path, blocks=None, traces=None,
                    companions: bool = False) -> list[IgorBlock]:
    """All blocks of a day folder in order, or a subset: ``blocks`` is an
    iterable of block numbers, ``traces`` a ``(first, last)`` pair of day
    numbers (inclusive); both may be given. Blocks left with no trace are
    dropped."""
    folder = Path(folder)
    ks = list_blocks(folder)
    if blocks is not None:
        want = {int(b) for b in blocks}
        ks = [k for k in ks if k in want]
    if traces is not None:
        first, last = int(traces[0]), int(traces[1])
        ks = [k for k in ks if (k - 1) * BLOCK + 1 <= last and k * BLOCK >= first]
    out = []
    for k in ks:
        b = read_block(folder, k, companions=companions)
        if traces is not None:
            b = b.select((b.numbers >= first) & (b.numbers <= last))
        if b.n_traces:
            out.append(b)
    return out


def read_hist_wave(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """A 1-D histogram wave -- a ``PullOutConductanceBlockHist_k`` (counts
    per trace) or one of the lab's saved ``Loghist<a>_<b>_<date>`` waves
    (raw sums) -- as ``(x, values)``. ``x`` is the wave's own scaling, ``x0
    + i*dx``, which for these is the *start* of bin i (-8 + i*10/999);
    add dx/2 for bin centres."""
    wave = read_wave(path)
    if wave.data.ndim != 1:
        raise ValueError(f"{Path(path).name}: a {wave.data.ndim}-D wave is not a histogram")
    n = wave.data.size
    x = wave.x0 + np.arange(n, dtype=float) * wave.dx
    return x, np.asarray(wave.data, dtype=float)
