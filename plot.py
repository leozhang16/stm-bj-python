"""Plots of saved STM-BJ traces: the histograms, and single traces.

    python plot.py <session>.h5 1D         the conductance histogram (counts per
                                           trace against log10 G/G0)
    python plot.py <session>.h5 2D         the 2D histogram (log G against
                                           displacement)
    python plot.py <session>.h5 -1         trace 1, the first; -2 the second ...
    python plot.py <session>.h5            1D and 2D side by side
    python plot.py a.h5 b.h5 1D            several files, one histogram
    python plot.py <session>.h5 1D --save  a PNG beside the file, no window

    python plot.py NAS/07_16_26 1D                 a whole Igor day folder (300
                                                   blocks; NAS: the folder that
                                                   holds the day folders)
    python plot.py NAS/07_16_26 2D                 log G against displacement
    python plot.py NAS/07_16_26                    both side by side
    python plot.py NAS/07_16_26 1D --blocks 1-5,9  only those blocks of it
                                                   (traces 1-500, 801-900)
    python plot.py NAS/07_16_26 --traces 1-500 1D  only those trace numbers; the
                                                   options may stand anywhere
    python plot.py NAS/07_16_26/PullOutConductanceBlock_7.ibw 1D
                                                   one block (traces 601-700)
    python plot.py NAS/07_16_26 -250               trace 250 of the day (block 3,
                                                   column 49), with its voltage,
                                                   current and extension
    python plot.py "Saved Histograms/Loghist1_1000_07_10_25.ibw" 1D
                                                   a saved histogram wave, drawn
                                                   as the curve it is
    python plot.py data/10_22_26Merge --blocks 1 data/10_22_26Merge/PullOutConductanceBlockHist_1.ibw 1D
                                                   a block's own Hist file over the
                                                   histogram recomputed from its
                                                   block (a Python day writes one;
                                                   the July 2026 days have none)
    python plot.py data/10_22_26Merge NAS/07_16_26 1D
                                                   today's Python day and an Igor
                                                   day in one histogram
    python plot.py NAS/07_16_26 1D --save          a PNG in the day folder (or in
                                                   --out <folder>), no window

The kinds of input, which can be mixed in one histogram:

    folder  an Igor day folder (Igor's ``10_22_26Merge`` or a renamed copy
            such as ``07_16_26``): every ``PullOutConductanceBlock_k.ibw`` in
            it, 100 traces to a block, in the order 1, 2, ..., 10, 11
    .ibw    one Igor binary wave: a ConductanceBlock (one column per trace
            in G/G0, then the 20 parameters), a companion block
            (PullOutVoltage/Current/ExtensionBlock_k: its ConductanceBlock
            is used), a 1000-point histogram wave (PullOutConductanceBlock-
            Hist_k, or a Loghist* saved by the analysis macro), or a bare
            trace. Needs the igor2 package: pip install igor2
    .h5     this program's raw session (volts + config; the conductance is
            computed on loading, so a re-measured gain reprocesses the file)
    .txt    this program's table (displacement, then one G/G0 column per trace)

Igor's traces have the displacement axis Igor gave them, ``SetScale/I x 0,
Size``: ``linspace(0, Size, N)`` from the pull length in each column's own
parameter slot 0. The 1D histogram is the block histogram's recipe
(``igor_scheme.block_histogram``, Igor's ``LogHistFromBlocks``): per trace
the first 95 % of the points, smoothed, the noise floor from the 95-96 %
window, and the trace counts only when that floor is below the
end-of-trace threshold (``cfg.ramp.break_g0``; ``--no-floor-gate`` keeps
every trace). It uses Igor's bins by default (1000 points scaled -8 to 2,
so bin i starts at -8 + i*10/999), to compare peak positions bin for bin
with Igor's; ``--even-bins`` gives even bins over the range instead.

Knobs, all optional (the defaults are Igor's):

    1D   --bins 1000  --smooth 11  --xlim -7 1  --logy  --fill  --color k  --lw 1.2
         --even-bins  --no-floor-gate
    2D   --xbins 200  --ybins 300  --xlim -0.5 2  --ylim -7 1  --align 0.5
         --cmap viridis  --vmax 50  --no-colorbar
    any  --save  --out <folder>  --dpi 110  --blocks 1-5,9  --traces 1-500

The options may come before or after the inputs and the 1D/2D/-N word.

The window (pullout.py) draws its histogram windows with the functions in
this file, so a picture is the same from the command line and from the
window. The analysis itself -- which points of a trace count, the
smoothing, the floor, the alignment -- is stmlab/analysis.py; the file
layout Igor used is stmlab/igor_scheme.py; this file only loads, calls
them, and draws.
"""
from __future__ import annotations

import argparse
import inspect
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from stmlab import analysis, igor_scheme, plots, storage   # noqa: E402
from stmlab.config import RigConfig                        # noqa: E402

GOLD_LINES = (0.0, np.log10(2), np.log10(3), np.log10(4))   # 1, 2, 3, 4 G0

# Igor's block files, by their stem: PullOutConductanceBlock_3 is block 3's
# conductance; the others are its companions (same k, same columns).
_BLOCK_FILE_RE = re.compile(
    r"^PullOut(Conductance|Voltage|Current|Extension|VoltageLowRes)Block_(\d+)$")
_HIST_NAME_RE = re.compile(r"^(PullOutConductanceBlockHist_\d+|Loghist.*)$", re.IGNORECASE)

# Colours of a saved histogram wave drawn over the recomputed histogram.
_WAVE_COLOURS = ("#d62728", "#1f77b4", "#2ca02c", "#9467bd", "#8c564b")


# --------------------------------------------------------------------------
# The data of one or more inputs, loaded once
# --------------------------------------------------------------------------

@dataclass
class HistWave:
    """A histogram that Igor (or this program) saved as a 1-D wave.

    ``x`` is the wave's own x scaling, ``x0 + i*dx``: for these waves the
    *start* of bin i (Igor's ``SetScale/I x -8, 2`` over 1000 points), so a
    curve drawn at ``x`` sits where Igor itself would draw it, half a bin
    (0.005 decade) left of the bin centres the recomputed histogram uses.
    ``per_trace`` is True for a ``PullOutConductanceBlockHist_k`` (counts
    per trace, like the recomputed histogram) and False for a ``Loghist*``
    of the analysis macro (a raw sum over many traces), which is therefore
    drawn on its own right-hand axis.
    """
    x: np.ndarray
    values: np.ndarray
    name: str
    path: Path
    per_trace: bool = True


@dataclass
class Data:
    """The traces of one or more inputs, in G0, with what the plots need.

    ``traces`` are the conductance traces (G/G0 along each pull); ``disps``
    one displacement axis per trace (nm); ``numbers`` the number of each
    trace -- Igor's day number for a block or folder, the position in the
    file otherwise; ``hist_waves`` the saved histogram waves given as
    inputs, drawn over the 1D histogram; ``report`` the last drawing's
    info dicts, under "1d" and "2d"; ``tail_rows`` the rows an Igor block
    column has beyond the trace (``igor_scheme.TAIL_ROWS`` = 22 for traces
    read from Igor's blocks, 0 for a .h5 or .txt), which the 1D histogram's
    95 % cut counts as Igor's did.
    """
    traces: list                   # conductance (G/G0) along each pull
    disp_nm: np.ndarray            # displacement along a pull, in nm (the first trace's)
    cfg: RigConfig                 # the first file's config (or Igor's parameters)
    name: str                      # for titles
    paths: list = field(default_factory=list)
    disps: list = field(default_factory=list)   # one displacement axis per trace
    cache: dict = field(default_factory=dict)   # histograms already computed
    numbers: list = field(default_factory=list)   # each trace's number
    hist_waves: list = field(default_factory=list)
    report: dict = field(default_factory=dict)
    tail_rows: int = 0             # 22 for Igor block columns (the 95 % cut counts them)

    def __post_init__(self):
        if not self.disps:
            self.disps = [self.disp_nm] * len(self.traces)
        if not self.numbers:
            self.numbers = list(range(1, len(self.traces) + 1))

    @property
    def n(self) -> int:
        return len(self.traces)


def from_session(session, name: str | None = None) -> Data:
    """The data of an open ``storage.Session``."""
    cfg = session.cfg
    traces = list(session.conductances())
    n_samples = max((t.size for t in traces), default=0)
    fs = (float(session.scalar("sample_rate_hz")[0]) if len(session)
          else cfg.ramp.sample_rate_hz)
    disp = analysis.displacement_nm(n_samples, cfg.ramp, fs)
    return Data(traces, disp, cfg, name or Path(session.path).stem,
                paths=[Path(session.path)])


# -- Igor's files ----------------------------------------------------------

def block_file_kind(path) -> tuple[str, int] | None:
    """What an Igor block file is, from its name: ``("Conductance", 3)`` for
    ``PullOutConductanceBlock_3.ibw``, ``("Current", 3)`` for its current
    companion, ...; None for any other name (a legacy export, a bare wave,
    a histogram wave)."""
    m = _BLOCK_FILE_RE.match(Path(path).stem)
    return (m.group(1), int(m.group(2))) if m else None


def is_hist_wave(wave: igor_scheme.IgorWave) -> bool:
    """True for a saved histogram wave: 1-D, Igor's 1000 points scaled from
    -8 (a ``PullOutConductanceBlockHist_k`` or a ``Loghist*``), or any 1-D
    wave with one of those names."""
    data = np.asarray(wave.data)
    if data.ndim != 1:
        return False
    if data.size == igor_scheme.HIST_POINTS and abs(wave.x0 - igor_scheme.HIST_X0) < 1e-6:
        return True
    return bool(_HIST_NAME_RE.match(wave.name) or _HIST_NAME_RE.match(Path(wave.path).stem))


def cfg_from_igor_parameters(p: np.ndarray, n_points: int = 0) -> RigConfig:
    """A RigConfig carrying what one Igor parameter row says about the pull:
    the pull length (slot 0, nm), rate (slot 1, nm/s), bias (slot 10, mV)
    and engage threshold (slot 13, G0); the sample rate follows from the
    number of points, ``N = Size / Rate * fs``. Slots that are missing (NaN
    in the legacy export) or 0 leave the defaults."""
    cfg = RigConfig()
    p = np.asarray(p, dtype=float)
    if p.size > 0 and np.isfinite(p[0]) and p[0] > 0:
        cfg.ramp.pull_length_nm = float(p[0])
    if p.size > 1 and np.isfinite(p[1]) and p[1] > 0:
        cfg.ramp.pull_rate_nm_per_s = float(p[1])
    if p.size > 10 and np.isfinite(p[10]) and p[10] != 0:
        cfg.ramp.bias_v = float(p[10]) * 1e-3
    if p.size > 13 and np.isfinite(p[13]) and p[13] > 0:
        cfg.ramp.engage_g0 = float(p[13])
    if n_points > 1:
        cfg.ramp.sample_rate_hz = (n_points * cfg.ramp.pull_rate_nm_per_s
                                   / cfg.ramp.pull_length_nm)
    return cfg


def _igor_axes(params: np.ndarray, n_points: int) -> list:
    """One displacement axis per column, Igor's ``SetScale/I x 0, Size``:
    ``linspace(0, Size, N)`` with Size from the column's own slot 0 (the
    end point included). Columns with the same Size share one array, so a
    day of 30 000 traces does not hold 30 000 copies of the axis."""
    shared: dict = {}
    axes = []
    for p in params:
        size = float(p[0]) if p.size and np.isfinite(p[0]) and p[0] > 0 else float("nan")
        if size not in shared:
            shared[size] = (np.linspace(0.0, size, n_points) if np.isfinite(size)
                            else np.arange(n_points, dtype=float))
        axes.append(shared[size])
    return axes


class _BlockTraces:
    """The traces of Igor blocks, collected one block at a time: each block
    is converted to single-precision traces (as Igor stored them; half the
    memory of the float64 ``IgorBlock``) and can then be dropped, so a whole
    day is never held as float64 blocks."""

    def __init__(self):
        self.traces, self.disps, self.numbers = [], [], []
        self.cfg = None

    def add(self, b: igor_scheme.IgorBlock, keep: np.ndarray | None = None) -> int:
        """The columns of ``b`` where ``keep`` (a boolean mask over its
        filled columns; None: all) is True. Returns how many were added."""
        g0, params, numbers = b.g0, b.params, b.numbers
        if keep is not None:
            keep = np.asarray(keep, dtype=bool)
            g0, params, numbers = g0[:, keep], params[keep], numbers[keep]
        if numbers.size == 0:
            return 0
        g0 = np.asarray(g0, dtype=np.float32, order="F")   # each column contiguous
        self.traces.extend(g0[:, j] for j in range(g0.shape[1]))
        self.disps.extend(_igor_axes(params, b.n_points))
        self.numbers.extend(int(x) for x in numbers)
        if self.cfg is None:
            self.cfg = cfg_from_igor_parameters(params[0], b.n_points)
        return int(numbers.size)

    def data(self, name: str, paths: list) -> Data:
        """One Data of everything added: Igor's axes, the day numbers, the
        config of the first row, and the block column's 22 tail rows for
        the 1D histogram's 95 % cut."""
        disp = self.disps[0] if self.disps else np.zeros(0)
        return Data(self.traces, disp, self.cfg or RigConfig(), name, paths=list(paths),
                    disps=self.disps, numbers=self.numbers, tail_rows=igor_scheme.TAIL_ROWS)


def _data_from_blocks(blocks: list, name: str, paths: list) -> Data:
    """One Data from a list of ``igor_scheme.IgorBlock`` already in memory
    (one block, in practice): see :class:`_BlockTraces`."""
    acc = _BlockTraces()
    for b in blocks:
        acc.add(b)
    return acc.data(name, paths)


def from_igor(path) -> Data:
    """One Igor binary wave (.ibw), whatever it holds:

    * a ConductanceBlock (Igor's ``PullOutConductanceBlock_k``, or this
      program's legacy ``_bNNN`` export): its filled columns, each with the
      axis of its own slot 0, numbered ``(k-1)*100 + column + 1`` when the
      name carries ``k``, else 1, 2, ... in file order
    * a companion block (``PullOutVoltageBlock_k`` etc.): the matching
      ConductanceBlock beside it is loaded instead (a note says so); when
      that is missing the columns are taken as they are, which are then
      volts, amps or nm and not G/G0
    * a histogram wave (:func:`is_hist_wave`): no traces, one
      :class:`HistWave` to draw
    * anything else, a bare 1-D trace or a 2-D block without the parameter
      tail: taken whole, with the wave's own x scaling when it has one
    """
    path = Path(path)
    try:
        wave = igor_scheme.read_wave(path)
    except ImportError as exc:
        raise SystemExit(f"reading {path.name} needs the igor2 package: "
                         f"pip install igor2   ({exc})") from None
    kind = block_file_kind(path)
    k = kind[1] if kind else None

    if is_hist_wave(wave):
        x, values = igor_scheme.read_hist_wave(path)
        per_trace = not Path(path).stem.lower().startswith("loghist")
        return Data([], np.zeros(0), RigConfig(), path.stem, paths=[path],
                    hist_waves=[HistWave(x, values, wave.name or path.stem, path, per_trace)])

    if kind is not None and kind[0] != "Conductance":
        sibling = igor_scheme.block_file(path.parent, "conductance", k)
        if sibling.exists():
            print(f"{path.name} is the {kind[0].lower()} companion of block {k}; "
                  f"plotting {sibling.name}")
            block = igor_scheme.read_block(path.parent, k, companions=False)
            return _data_from_blocks([block], path.stem, [path])
        print(f"{path.name} is a companion block and {sibling.name} is not beside "
              f"it: its columns are drawn as they are (not G/G0)")

    data = np.asarray(wave.data, dtype=float)
    if data.ndim == 1:
        data = data[:, None]
    if data.ndim != 2:
        raise ValueError(f"{path.name}: a {data.ndim}-D wave is not a block of traces")

    if igor_scheme.has_parameter_tail(data):
        g0_all, params_all, filled = igor_scheme.split_block(data)
        idx = np.flatnonzero(filled)
        numbers = (k - 1) * igor_scheme.BLOCK + idx + 1 if k else idx + 1
        block = igor_scheme.IgorBlock(k or 0, path.parent, g0_all[:, idx],
                                      params_all[idx], idx, numbers)
        return _data_from_blocks([block], path.stem, [path])

    # No parameter tail: a bare trace, or a block cut by hand. Taken whole.
    traces = [np.asarray(col, dtype=np.float32) for col in data.T]
    n = data.shape[0]
    cfg = RigConfig()
    if wave.dx != 1.0 or wave.x0 != 0.0:            # the wave's own scaling
        disp = wave.x0 + wave.dx * np.arange(n, dtype=float)
    else:                                            # none: the pull over its length
        disp = np.linspace(0.0, cfg.ramp.pull_length_nm, n, endpoint=False)
    return Data(traces, disp, cfg, path.stem, paths=[path])


def from_folder(folder, blocks=None, traces=None) -> Data:
    """Every ConductanceBlock of an Igor day folder, in block order, or a
    subset: ``blocks`` an iterable of block numbers, ``traces`` a list of
    ``(first, last)`` day-number ranges (inclusive); both may be given.
    Each block is read once and converted to single-precision traces
    before the next is read, so a whole day (300 blocks of 100 traces x
    10000 points, 1.2 GB as float32) is never held as float64 blocks. A
    trace in several of the ranges is loaded once."""
    folder = Path(folder)
    ks = igor_scheme.list_blocks(folder)
    if not ks:
        raise ValueError(f"{folder}: no PullOutConductanceBlock_k.ibw in it")
    if blocks is not None:
        want = {int(b) for b in blocks}
        ks = [k for k in ks if k in want]
    ranges = None
    if traces is not None:
        ranges = [(int(a), int(b)) for a, b in traces]
        ks = [k for k in ks
              if any((k - 1) * igor_scheme.BLOCK + 1 <= b and k * igor_scheme.BLOCK >= a
                     for a, b in ranges)]
    if len(ks) > 20:
        print(f"reading {len(ks)} blocks from {folder.name} ...", flush=True)
    acc = _BlockTraces()
    for k in ks:
        b = igor_scheme.read_block(folder, k, companions=False)   # the one float64 block alive
        keep = None
        if ranges is not None:
            keep = np.zeros(b.n_traces, dtype=bool)
            for a, z in ranges:
                keep |= (b.numbers >= a) & (b.numbers <= z)
        acc.add(b, keep)
        del b
    name = folder.name
    if blocks is not None:
        name += " blocks " + _ranges_text(sorted({int(b) for b in blocks}))
    if ranges is not None:
        name += " traces " + ",".join(f"{a}-{b}" if a != b else f"{a}" for a, b in ranges)
    if not acc.traces:
        raise ValueError(f"{folder.name}: no trace matches"
                         + (f" blocks {blocks}" if blocks is not None else "")
                         + (f" traces {ranges}" if ranges is not None else ""))
    return acc.data(name, [folder])


def _ranges_text(values: list) -> str:
    """``[1, 2, 3, 4, 5, 9]`` as ``"1-5,9"``."""
    parts, start, prev = [], None, None
    for v in values:
        if start is None:
            start = prev = v
        elif v == prev + 1:
            prev = v
        else:
            parts.append(f"{start}-{prev}" if start != prev else f"{start}")
            start = prev = v
    if start is not None:
        parts.append(f"{start}-{prev}" if start != prev else f"{start}")
    return ",".join(parts)


def from_txt(path) -> Data:
    """The traces of this program's .txt table: displacement, then one
    G/G0 column per trace (NaN-padded when the traces differ in length)."""
    path = Path(path)
    table = np.loadtxt(path)
    if table.ndim == 1:
        table = table[:, None]
    disp = table[:, 0]
    traces = [col[np.isfinite(col)] for col in table[:, 1:].T]
    cfg = RigConfig()
    cfg.ramp.pull_length_nm = float(disp[-1]) if disp.size else cfg.ramp.pull_length_nm
    return Data(traces, disp, cfg, path.stem, paths=[path])


def load_one(path, blocks=None, traces=None) -> Data:
    """One input of any kind: a day folder (``blocks``/``traces`` pick a
    subset of it), or a file by its suffix."""
    path = Path(path)
    if path.is_dir():
        return from_folder(path, blocks=blocks, traces=traces)
    suffix = path.suffix.lower()
    if suffix == ".h5":
        with storage.Session(path) as session:
            return from_session(session)
    if suffix == ".ibw":
        return from_igor(path)
    if suffix == ".txt":
        return from_txt(path)
    raise ValueError(f"{path.name}: not a day folder or a .h5, .ibw or .txt file")


def load(paths, blocks=None, traces=None) -> Data:
    """The data of one or more inputs (folders, .h5, .ibw, .txt, mixed),
    all their traces together, each trace keeping its own displacement
    axis and number; the saved histogram waves among them are collected
    for the 1D plot. ``blocks`` and ``traces`` apply to the folders. The
    tail rows of the 1D histogram's 95 % cut are kept when every input
    with traces has the same (all Igor blocks, or none); Igor blocks mixed
    with .h5/.txt traces are cut without them."""
    paths = [Path(p) for p in paths]
    if not paths:
        raise ValueError("no file given")
    parts = [load_one(p, blocks=blocks, traces=traces) for p in paths]
    first = parts[0]
    traces_ = [t for part in parts for t in part.traces]
    disps = [d for part in parts for d in part.disps]
    numbers = [n for part in parts for n in part.numbers]
    waves = [w for part in parts for w in part.hist_waves]
    cfg = next((part.cfg for part in parts if part.n), first.cfg)
    disp = next((part.disp_nm for part in parts if part.n), first.disp_nm)
    lead = next((part for part in parts if part.n), first)
    name = first.name if len(parts) == 1 else f"{len(parts)} files, {lead.name} ..."
    tails = {part.tail_rows for part in parts if part.n}
    tail_rows = tails.pop() if len(tails) == 1 else 0
    return Data(traces_, disp, cfg, name, paths=paths, disps=disps,
                numbers=numbers, hist_waves=waves, tail_rows=tail_rows)


# --------------------------------------------------------------------------
# The two histograms, each drawn on an axes you hand over
# --------------------------------------------------------------------------

def hist_1d(ax, data: Data, bins: int = 1000, smooth: int = 11,
            xlim=(-7.0, 1.0), lw: float = 1.2, color: str = "k",
            logy: bool = False, fill: bool = False,
            title: str | None = None, igor_bins: bool = True,
            floor_gate: bool = True) -> dict:
    """Igor's LogHistFromBlocks: counts per trace against log10(G/G0).

    The recipe is the block histogram's (``igor_scheme.block_histogram``,
    the ``PullOutConductanceBlockHist_k`` files), per trace: keep the first
    95 % of the points, box-smooth over ``smooth`` points, take the mean
    over the 95-96 % window as the noise floor and, only if that floor is
    below the end-of-trace threshold ``data.cfg.ramp.break_g0`` (Igor's
    ``G_EndOfTraceNoiseThreshold``, a quality gate: a trace that never
    reached a clean floor is left out), subtract it, smooth again, take
    log10 and bin. ``floor_gate=False`` (``--no-floor-gate``) keeps every
    trace, floor subtracted. For traces from Igor's blocks the 95 % cut
    counts the block column's 22 tail rows (``data.tail_rows``), as Igor
    cut the whole column; a .h5 or .txt trace is cut over its own points.
    The threshold is ``data.cfg``'s: the session's own for a .h5, the
    config default for Igor data (Igor's panel value is not among the 20
    parameters). The sum over the traces is divided by the traces that
    passed the gate; Igor divided a block's by 100, passed or not.

    ``igor_bins`` (the default) bins as Igor's ``Histogram/A`` into a
    1000-point wave scaled -8 to 2 did: bin i starts at -8 + i*10/999.
    False gives even bins across the range. The saved histogram waves in
    ``data.hist_waves`` are drawn too, each at its own x scaling: a
    ``PullOutConductanceBlockHist_k`` (counts per trace) on the same axis,
    a ``Loghist*`` (a raw sum) on a right-hand axis of its own.

    Returns {"peak": the 1 G0 peak position in decades (NaN with no
    traces), "note": a line for a status bar, "centres", "counts",
    "wave_peaks": {wave name: its 1 G0 peak}}.
    """
    bins = max(10, int(bins))
    smooth = max(1, int(smooth))
    cutoff = float(data.cfg.ramp.break_g0) if floor_gate else None
    key = ("1d", bins, smooth, "igor" if igor_bins else "even", int(data.tail_rows), cutoff)
    note = ""
    peak = float("nan")
    centres = counts = np.zeros(0)
    if data.n:
        if key not in data.cache:
            data.cache[key] = analysis.log_histogram(data.traces, lo=-8.0, hi=2.0,
                                                     n_bins=bins, smooth_width=smooth,
                                                     zero_cutoff=cutoff,
                                                     igor_bins=igor_bins,
                                                     tail_rows=int(data.tail_rows))
        centres, counts = data.cache[key]
        try:
            ax.plot(centres, counts, color=color, lw=lw, label="recomputed" if data.hist_waves else None)
            if fill:
                ax.fill_between(centres, 0, counts, color=color, alpha=0.25)
        except ValueError:
            ax.plot(centres, counts, color="k", lw=lw)
            note = f"'{color}' is not a colour name; drew black. "
        peak = analysis.peak_position(centres, counts, around=0.0, window=0.4)
        note += (f"1 G0 peak at {peak:+.4f} decades; {bins} "
                 f"{'Igor' if igor_bins else 'even'} bins, smooth {smooth} points, "
                 + (f"floor gate {cutoff:g} G0" if cutoff is not None else "no floor gate"))
    else:
        note += "no traces"

    wave_peaks: dict = {}
    ax_sum = None
    for i, w in enumerate(data.hist_waves):
        target = ax
        if not w.per_trace:
            if ax_sum is None:
                ax_sum = ax.twinx()
                ax_sum.set_ylabel("saved sum (counts, as stored)", fontsize=9)
                if logy:
                    ax_sum.set_yscale("log")
            target = ax_sum
        c = _WAVE_COLOURS[i % len(_WAVE_COLOURS)]
        target.plot(w.x, w.values, color=c, lw=lw, alpha=0.85, label=w.name)
        wave_peaks[w.name] = analysis.peak_position(w.x, w.values, around=0.0, window=0.4)
        note += f"; {w.name}: 1 G0 peak at {wave_peaks[w.name]:+.4f} decades"
    if data.hist_waves and data.n:
        note += ("; the saved wave is drawn at Igor's bin starts, "
                 f"{igor_scheme.HIST_DX / 2:.3f} decade left of the recomputed centres")
        if any(w.per_trace for w in data.hist_waves):
            note += (", and is per column of its block where the recomputed one is "
                     "per trace that passed the floor gate")
    if data.hist_waves:
        handles, labels = ax.get_legend_handles_labels()
        if ax_sum is not None:
            h2, l2 = ax_sum.get_legend_handles_labels()
            handles, labels = handles + h2, labels + l2
        ax.legend(handles, labels, fontsize=8, loc="upper left")

    if logy:
        ax.set_yscale("log")
    ax.set_xlim(*xlim)
    ax.set_xlabel("log10 (G / G0)")
    ax.set_ylabel("counts per trace")
    if title is None:
        title = (f"{data.name}: {data.n} traces" if data.n
                 else f"{data.name}: saved histogram")
    ax.set_title(title, fontsize=10)
    for g in GOLD_LINES:
        ax.axvline(g, color="#999", lw=0.5, ls=":")
    ax.grid(True, alpha=0.3)
    info = {"peak": peak, "note": note, "centres": centres, "counts": counts,
            "wave_peaks": wave_peaks}
    data.report["1d"] = info
    return info


def hist_2d(ax, data: Data, xbins: int = 200, ybins: int = 300,
            xlim=(-0.5, 2.0), ylim=(-7.0, 1.0), align: float | None = 0.5,
            cmap: str = "viridis", vmax: float | None = None,
            colorbar: bool = True, title: str | None = None) -> dict:
    """The 2D histogram: log10(G/G0) against displacement, counts per trace,
    every trace's 0 nm put where its conductance first drops below
    ``align`` G0 (None: where the pull started).

    Returns {"max": the largest bin, "note": a line for a status bar,
    "counts", "x_edges", "y_edges"}.
    """
    if not data.n:
        raise ValueError(f"{data.name}: no traces for a 2D histogram "
                         "(a saved histogram wave holds none)")
    xbins, ybins = max(10, int(xbins)), max(10, int(ybins))
    key = ("2d", xbins, ybins, tuple(xlim), tuple(ylim), align)
    if key not in data.cache:
        data.cache[key] = analysis.histogram_2d(
            data.traces, data.disps, align_at_g0=align, x_range=tuple(xlim),
            n_x=xbins, y_range=tuple(ylim), n_y=ybins)
    counts, xe, ye = data.cache[key]
    note = ""
    try:
        im = ax.pcolormesh(xe, ye, counts.T, cmap=cmap, vmin=0, vmax=vmax,
                           shading="flat")
    except ValueError:
        im = ax.pcolormesh(xe, ye, counts.T, cmap="viridis", vmin=0, vmax=vmax,
                           shading="flat")
        note = f"'{cmap}' is not a colormap; used viridis. "
    if colorbar:
        ax.figure.colorbar(im, ax=ax, label="counts per trace")
    ax.set_xlabel("displacement (nm)"
                  + ("" if align is None else f", 0 where G first < {align:g} G0"))
    ax.set_ylabel("log10 (G / G0)")
    ax.set_title(title or f"{data.name}: {data.n} traces", fontsize=10)
    top = float(counts.max()) if counts.size else 0.0
    note += (f"{xbins} x {ybins} bins; colour max {top:.3g} counts per trace"
             + (f" (shown up to {vmax:g})" if vmax else ""))
    info = {"max": top, "note": note, "counts": counts, "x_edges": xe,
            "y_edges": ye}
    data.report["2d"] = info
    return info


def figure(data: Data, kind: str, fig=None, **knobs):
    """A whole figure: ``kind`` "1D", "2D" or "both" (side by side). ``knobs``
    are hist_1d's and hist_2d's keyword arguments, each handed to the one
    that takes it. Draws on ``fig`` when given, else makes one. With no
    traces (only saved histogram waves) "both" draws the 1D alone."""
    from matplotlib.figure import Figure
    kind = kind.lower()
    if kind == "both" and not data.n:
        kind = "1d"
    if fig is None:
        fig = Figure(figsize=(13, 5.4) if kind == "both" else (7.5, 5.4), dpi=100)
    fig.clear()
    k1 = {k: v for k, v in knobs.items() if k in inspect.signature(hist_1d).parameters}
    k2 = {k: v for k, v in knobs.items() if k in inspect.signature(hist_2d).parameters}
    if kind == "1d":
        hist_1d(fig.add_subplot(111), data, **k1)
    elif kind == "2d":
        hist_2d(fig.add_subplot(111), data, **k2)
    else:
        ax1, ax2 = fig.subplots(1, 2)
        hist_1d(ax1, data, **k1)
        hist_2d(ax2, data, **{k: v for k, v in k2.items() if k != "xlim"})
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------
# One trace
# --------------------------------------------------------------------------

def is_igor_day_input(path) -> bool:
    """True for a day folder or an Igor block file (conductance or
    companion) named with its block number: inputs where a trace is
    addressed by its day number."""
    path = Path(path)
    return path.is_dir() or (path.suffix.lower() == ".ibw"
                             and block_file_kind(path) is not None)


def igor_trace_figure(path, number: int, fig=None):
    """Trace ``number`` -- Igor's day number -- of a day folder or of one
    of its block files, with the block's histogram beside it.

    The left column holds the conductance against displacement (Igor's
    ``SetScale/I x 0, Size`` axis) and, under it, whatever companion blocks
    the folder has for that block: the junction voltage (mV), the current
    (nA) and the piezo readback (nm), all against the same displacement.
    The right-hand panel is the histogram of the block's 100 traces,
    recomputed with Igor's bins; when the block's own saved histogram
    (``PullOutConductanceBlockHist_k``) exists it is drawn over it.

    On a block file, ``number`` outside the block's range but between 1 and
    100 is taken as the position in the block (``-2`` on block 3 is trace
    202; a note is printed). Returns ``(figure, info)`` with ``info["n"]``
    (traces in the folder, or in the block when a block file was given),
    ``"number"``, ``"block"``, ``"column"`` (0-based), ``"index"`` (0-based
    position in the block), ``"verdict"`` and ``"numbers"`` (the day numbers
    the block holds)."""
    from matplotlib.figure import Figure
    path = Path(path)
    number = int(number)
    B = igor_scheme.BLOCK
    if path.is_dir():
        folder = path
        k = (number - 1) // B + 1
        k_last, filled = igor_scheme.IgorDayWriter.scan(folder)
        total = B * (k_last - 1) + filled if k_last else 0
        if k_last == 0:
            raise ValueError(f"{folder}: no PullOutConductanceBlock_k.ibw in it")
    else:
        kind = block_file_kind(path)
        if kind is None:
            raise ValueError(f"{path.name} is not an Igor block file")
        folder, k = path.parent, kind[1]
        first, last = (k - 1) * B + 1, k * B
        if not first <= number <= last and 1 <= number <= B:
            print(f"block {k} holds traces {first}-{last}; taking -{number} as the "
                  f"{number}{'st' if number == 1 else 'nd' if number == 2 else 'rd' if number == 3 else 'th'} "
                  f"trace of the block, trace {first + number - 1} of the day")
            number = first + number - 1
        total = None
    conductance = igor_scheme.block_file(folder, "conductance", k)
    if not conductance.exists():
        raise ValueError(f"trace {number} would be in block {k}, and {conductance.name} "
                         f"is not in {folder}")
    b = igor_scheme.read_block(folder, k, companions=True)
    if total is None:
        total = b.n_traces
    sel = np.flatnonzero(b.numbers == number)
    if sel.size == 0:
        held = (f"{int(b.numbers[0])}-{int(b.numbers[-1])}" if b.n_traces else "nothing")
        raise ValueError(f"trace {number} is not in block {k} of {folder.name} "
                         f"(it holds {held}, {b.n_traces} traces)")
    j = int(sel[0])
    g0 = np.asarray(b.g0[:, j], dtype=float)
    disp = _igor_axes(b.params[j:j + 1], b.n_points)[0]
    cfg = cfg_from_igor_parameters(b.params[j], b.n_points)
    verdict = analysis.select_trace(g0, cfg.ramp)

    panels = []
    if b.voltage_v is not None:
        panels.append(("junction voltage (mV)", b.voltage_v[:, j] * 1e3, plots.C_V))
    if b.current_a is not None:
        panels.append(("current (nA)", b.current_a[:, j] * 1e9, plots.C_I))
    if b.extension_nm is not None:
        panels.append(("piezo readback (nm)", b.extension_nm[:, j], plots.C_SENSE))

    if fig is None:
        fig = Figure(figsize=(13, 7.5 if panels else 5.4), dpi=100)
    fig.clear()
    rows = 1 + len(panels)
    gs = fig.add_gridspec(rows, 2, width_ratios=[1.15, 1],
                          height_ratios=[2.2] + [1] * len(panels))
    ax0 = fig.add_subplot(gs[0, 0])
    plots.plot_trace(ax0, cfg, g0, disp, verdict,
                     title=f"{folder.name}: trace {number} (block {k}, column {j + 1})")
    prev = ax0
    for r, (label, values, colour) in enumerate(panels, start=1):
        ax = fig.add_subplot(gs[r, 0], sharex=ax0)
        ax.plot(disp, values, color=colour, lw=0.8)
        ax.set_ylabel(label, fontsize=8)
        ax.tick_params(labelsize=8)
        ax.grid(True, alpha=0.3)
        prev.set_xlabel("")
        prev.tick_params(labelbottom=False)
        prev = ax
    prev.set_xlabel("displacement (nm)", fontsize=8)

    block_data = _data_from_blocks([b], f"{folder.name} block {k}", [conductance])
    hist_path = igor_scheme.block_file(folder, "hist", k)
    if b.hist is not None and hist_path.exists():
        x = igor_scheme.HIST_X0 + np.arange(b.hist.size) * igor_scheme.HIST_DX
        block_data.hist_waves.append(HistWave(x, b.hist, hist_path.stem, hist_path, True))
    ax_h = fig.add_subplot(gs[:, 1])
    hist_1d(ax_h, block_data)
    fig.tight_layout(w_pad=3.0)
    info = {"n": total, "index": j, "number": number, "verdict": verdict,
            "block": k, "column": j, "numbers": b.numbers}
    return fig, info


def trace_figure(path, number: int, fig=None):
    """Trace ``number`` of one input. A .h5 session has the raw record, so it
    gets the six panels of stmlab.plots.figure_for_session; a day folder or
    an Igor block file gets :func:`igor_trace_figure` (``number`` is the day
    number there); any other .ibw or a .txt block holds conductance only,
    so it gets the trace (``number`` = its position, 1 = the first) against
    displacement beside the block's histogram. Returns (figure, info) with
    info["n"], info["number"], info["verdict"]."""
    path = Path(path)
    if path.suffix.lower() == ".h5" and not path.is_dir():
        return plots.figure_for_session(path, max(0, int(number) - 1), fig=fig)
    if is_igor_day_input(path):
        return igor_trace_figure(path, number, fig=fig)
    from matplotlib.figure import Figure
    data = load_one(path)
    if data.n == 0:
        raise ValueError(f"{path.name} holds no traces")
    i = max(0, min(int(number) - 1, data.n - 1))
    g0, disp = data.traces[i], data.disps[i][:data.traces[i].size]
    verdict = analysis.select_trace(g0, data.cfg.ramp)
    if fig is None:
        fig = Figure(figsize=(13, 5.4), dpi=100)
    fig.clear()
    ax1, ax2 = fig.subplots(1, 2)
    plots.plot_trace(ax1, data.cfg, g0, disp, verdict,
                     title=f"{data.name}: trace {i + 1} of {data.n}")
    hist_1d(ax2, data)
    fig.tight_layout(w_pad=3.0)
    return fig, {"n": data.n, "index": i, "number": i + 1, "verdict": verdict}


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def parse_ranges(text: str) -> list[tuple[int, int]]:
    """``"1-5,9"`` as ``[(1, 5), (9, 9)]``: comma-separated numbers or
    ``first-last`` ranges, counted from 1. ValueError for anything else."""
    out = []
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        a, dash, b = part.partition("-")
        try:
            if dash and not b:
                raise ValueError
            first = int(a)
            last = int(b) if b else first
        except ValueError:
            raise ValueError(f"'{part}' is not a number or a first-last range") from None
        if first < 1 or last < first:
            raise ValueError(f"'{part}': ranges count from 1, first <= last")
        out.append((first, last))
    if not out:
        raise ValueError(f"'{text}': no range in it")
    return out


def parse(argv) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Plots of saved STM-BJ traces: this program's sessions and "
                    "Igor's day folders.",
        epilog="python plot.py <session>.h5 | <day folder> | <block>.ibw  "
               "1D | 2D | -<trace number> | (nothing: both)",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("items", nargs="+",
                   help="input(s): a day folder, .h5 (this program), .ibw (Igor), "
                        ".txt; then 1D, 2D or -N (trace N; the day number for a "
                        "folder or block, else 1 = the first); nothing after the "
                        "inputs: 1D and 2D")
    p.add_argument("--blocks", default=None, metavar="LIST",
                   help='blocks of a day folder, e.g. "1-5,9" (default: all)')
    p.add_argument("--traces", default=None, metavar="RANGE",
                   help='trace numbers of a day folder, e.g. "1-500" (default: all)')
    g1 = p.add_argument_group("1D")
    g1.add_argument("--bins", type=int, default=1000)
    g1.add_argument("--smooth", type=int, default=11, help="box smoothing, points")
    g1.add_argument("--even-bins", action="store_true",
                    help="even bins over the range instead of Igor's (bin i "
                         "starting at -8 + i*10/999)")
    g1.add_argument("--no-floor-gate", action="store_true",
                    help="count every trace; by default (Igor's recipe) a trace "
                         "whose noise floor is not below the end-of-trace "
                         "threshold (config break_g0) is left out")
    g1.add_argument("--logy", action="store_true")
    g1.add_argument("--fill", action="store_true")
    g1.add_argument("--color", default="k")
    g1.add_argument("--lw", type=float, default=1.2, help="line width")
    g2 = p.add_argument_group("2D")
    g2.add_argument("--xbins", type=int, default=200)
    g2.add_argument("--ybins", type=int, default=300)
    g2.add_argument("--ylim", type=float, nargs=2, default=(-7.0, 1.0),
                    metavar=("LO", "HI"), help="log G range")
    g2.add_argument("--align", type=float, default=0.5,
                    help="0 nm where G first drops below this (G0); "
                         "a negative value: 0 nm at the start of the pull")
    g2.add_argument("--cmap", default="viridis")
    g2.add_argument("--vmax", type=float, default=None, help="colour scale top")
    g2.add_argument("--no-colorbar", action="store_true")
    p.add_argument("--xlim", type=float, nargs=2, default=None, metavar=("LO", "HI"),
                   help="x range: log G for 1D (default -7 1), nm for 2D "
                        "(default -0.5 2)")
    p.add_argument("--save", action="store_true", help="write a PNG, no window")
    p.add_argument("--out", type=Path, default=None,
                   help="folder for the PNG (default: beside the file, or inside "
                        "the day folder)")
    p.add_argument("--dpi", type=int, default=110)
    # intermixed: the options may stand between the inputs and the 1D/2D/-N
    # word ("07_16_26 --blocks 1-5,9 1D"); -205 is still read as a trace
    # number, since no option looks like a negative number
    args = p.parse_intermixed_args(argv)

    args.files, args.mode, args.trace = [], "both", None
    for item in args.items:
        low = item.lower()
        if low.endswith((".h5", ".ibw", ".txt")) and not Path(item).is_dir():
            if not Path(item).exists():
                p.error(f"{item}: no such file")
            args.files.append(Path(item))
        elif Path(item).is_dir():
            args.files.append(Path(item))
        elif low in ("1d", "2d", "both"):
            args.mode = low
        elif low.lstrip("-").isdigit():
            args.trace = int(low.lstrip("-"))
            args.mode = "trace"
            if args.trace < 1:
                p.error("traces are counted from 1: -1 is the first")
        else:
            p.error(f"'{item}' is not a day folder, a .h5/.ibw/.txt file, 1D, 2D "
                    f"or a trace number")
    if not args.files:
        p.error("give a day folder or a .h5, .ibw or .txt file")
    for name in ("blocks", "traces"):
        text = getattr(args, name)
        if text is None:
            continue
        try:
            ranges = parse_ranges(text)
        except ValueError as exc:
            p.error(f"--{name}: {exc}")
        if name == "blocks":
            args.blocks = sorted({k for a, b in ranges for k in range(a, b + 1)})
        else:
            args.traces = ranges
    return args


def _fail(exc: Exception) -> int:
    """A load error as one line on stderr, not a traceback; the exit code."""
    print(f"plot.py: {exc}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    args = parse(sys.argv[1:] if argv is None else argv)
    import matplotlib
    matplotlib.use("Agg" if args.save else "TkAgg")
    import matplotlib.pyplot as plt

    first = args.files[0]
    if args.mode == "trace":
        if len(args.files) > 1:
            print("one file at a time for a trace")
            return 2
        path = first
        fig = plt.figure(figsize=(13, 7.5), dpi=100)
        try:
            _, info = trace_figure(path, args.trace, fig=fig)
        except (ValueError, FileNotFoundError) as exc:
            return _fail(exc)
        v = info["verdict"]
        where = (f"block {info['block']}, column {info['column'] + 1}; "
                 if "block" in info else "")
        status = "accepted" if v.accepted else f"rejected: {v.reason}"
        print(f"{path.name}: {info['n']} traces; trace {info['number']} ({where}{status})")
        out_name = f"{path.stem}_trace{info['number']:04d}.png"
        title = f"trace {info['number']}: {path.name}"
    else:
        try:
            data = load(args.files, blocks=args.blocks, traces=args.traces)
        except (ValueError, FileNotFoundError) as exc:
            return _fail(exc)
        print(f"{data.name}: {data.n} traces"
              + (f", {len(data.hist_waves)} saved histogram wave(s)" if data.hist_waves else ""))
        knobs = dict(bins=args.bins, smooth=args.smooth, logy=args.logy,
                     fill=args.fill, color=args.color, lw=args.lw,
                     igor_bins=not args.even_bins, floor_gate=not args.no_floor_gate,
                     xbins=args.xbins, ybins=args.ybins, ylim=tuple(args.ylim),
                     align=None if args.align < 0 else args.align,
                     cmap=args.cmap, vmax=args.vmax,
                     colorbar=not args.no_colorbar)
        if args.xlim is not None:
            knobs["xlim"] = tuple(args.xlim)
        fig = plt.figure(figsize=(13, 5.4) if args.mode == "both" else (7.5, 5.4),
                         dpi=100)
        try:
            figure(data, args.mode, fig=fig, **knobs)
        except ValueError as exc:                 # e.g. 2D of a saved wave alone
            return _fail(exc)
        for kind in ("1d", "2d"):
            if kind in data.report:
                print(f"{kind.upper()}: {data.report[kind]['note']}")
        out_name = (f"{first.stem}_"
                    f"{'hist' if args.mode == 'both' else args.mode.upper()}.png")
        title = f"{args.mode.upper()}: {data.name}"

    if args.save:
        out_dir = args.out or (first if first.is_dir() else first.parent)
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / out_name
        fig.savefig(out, dpi=args.dpi)
        plt.close(fig)
        print(f"wrote {out}")
    else:
        if fig.canvas.manager is not None:
            fig.canvas.manager.set_window_title(title)
        plt.show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
