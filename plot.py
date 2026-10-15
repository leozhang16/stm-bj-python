"""Plots of saved STM-BJ traces: the histograms, and single traces.

    python plot.py <session>.h5 1D         the conductance histogram (counts per
                                           trace against log10 G/G0)
    python plot.py <session>.h5 2D         the 2D histogram (log G against
                                           displacement)
    python plot.py <session>.h5 -1         trace 1, the first; -2 the second ...
    python plot.py <session>.h5            1D and 2D side by side
    python plot.py a.h5 b.h5 1D            several files, one histogram
    python plot.py <session>.h5 1D --save  a PNG beside the file, no window

Three kinds of file, which can be mixed in one histogram:

    .h5    this program's session (raw volts + config; the conductance is
           computed on loading, so a re-measured gain reprocesses the file)
    .ibw   an Igor binary wave: Igor's own PullOut blocks (one column per
           trace in G/G0, then the parameters), or the blocks this program
           exports for Igor. Needs the igor2 package: pip install igor2
    .txt   this program's table (displacement, then one G/G0 column per trace)

Knobs, all optional (the defaults are Igor's):

    1D   --bins 1000  --smooth 11  --xlim -7 1  --logy  --fill  --color k  --lw 1.2
    2D   --xbins 200  --ybins 300  --xlim -0.5 2  --ylim -7 1  --align 0.5
         --cmap viridis  --vmax 50  --no-colorbar
    any  --save  --out <folder>  --dpi 110

The window (pullout.py) draws its histogram windows with the functions in
this file, so a picture is the same from the command line and from the
window. The analysis itself -- which points of a trace count, the
smoothing, the floor, the alignment -- is stmlab/analysis.py; this file
only loads a session, calls it, and draws.
"""
from __future__ import annotations

import argparse
import inspect
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from stmlab import analysis, plots, storage       # noqa: E402
from stmlab.config import RigConfig               # noqa: E402

GOLD_LINES = (0.0, np.log10(2), np.log10(3), np.log10(4))   # 1, 2, 3, 4 G0


# --------------------------------------------------------------------------
# The data of one or more session files, loaded once
# --------------------------------------------------------------------------

@dataclass
class Data:
    """The traces of one or more files, in G0, with what the plots need."""
    traces: list                   # conductance (G/G0) along each pull
    disp_nm: np.ndarray            # displacement along a pull, in nm
    cfg: RigConfig                 # the first file's config (or Igor's parameters)
    name: str                      # for titles
    paths: list = field(default_factory=list)
    disps: list = field(default_factory=list)   # one displacement axis per trace
    cache: dict = field(default_factory=dict)   # histograms already computed

    def __post_init__(self):
        if not self.disps:
            self.disps = [self.disp_nm] * len(self.traces)

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


def from_igor(path) -> Data:
    """The traces of an Igor binary wave (.ibw): Igor's own PullOut block
    or one this program exported. The pull length, rate and bias come
    from the block's parameter rows when it has them."""
    path = Path(path)
    try:
        block = storage.load_igor_block(path)
    except ImportError as exc:
        raise SystemExit(f"reading {path.name} needs the igor2 package: "
                         f"pip install igor2   ({exc})") from None
    traces = block["traces"]
    cfg = RigConfig()
    params = block["parameters"]
    if params is not None and len(params):
        p = params[0]
        if np.isfinite(p[0]) and p[0] > 0:
            cfg.ramp.pull_length_nm = float(p[0])
        if np.isfinite(p[1]) and p[1] > 0:
            cfg.ramp.pull_rate_nm_per_s = float(p[1])
        if np.isfinite(p[10]):
            cfg.ramp.bias_v = float(p[10]) * 1e-3
        if np.isfinite(p[13]) and p[13] > 0:
            cfg.ramp.engage_g0 = float(p[13])
    n = max((t.size for t in traces), default=0)
    if block["dx_nm"]:
        disp = block["x0_nm"] + block["dx_nm"] * np.arange(n)
    else:                                   # no x scaling: the pull over its length
        disp = np.linspace(0.0, cfg.ramp.pull_length_nm, n, endpoint=False)
    return Data(traces, disp, cfg, path.stem, paths=[path])


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


def load_one(path) -> Data:
    """One file of any of the three kinds, by its suffix."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".h5":
        with storage.Session(path) as session:
            return from_session(session)
    if suffix == ".ibw":
        return from_igor(path)
    if suffix == ".txt":
        return from_txt(path)
    raise ValueError(f"{path.name}: not a .h5, .ibw or .txt file")


def load(paths) -> Data:
    """The data of one or more files (.h5, .ibw, .txt, mixed), all their
    traces together, each trace keeping its own displacement axis."""
    paths = [Path(p) for p in paths]
    if not paths:
        raise ValueError("no file given")
    parts = [load_one(p) for p in paths]
    first = parts[0]
    traces = [t for part in parts for t in part.traces]
    disps = [d for part in parts for d in part.disps]
    name = first.name if len(parts) == 1 else f"{len(parts)} files, {first.name} ..."
    return Data(traces, first.disp_nm, first.cfg, name, paths=paths, disps=disps)


# --------------------------------------------------------------------------
# The two histograms, each drawn on an axes you hand over
# --------------------------------------------------------------------------

def hist_1d(ax, data: Data, bins: int = 1000, smooth: int = 11,
            xlim=(-7.0, 1.0), lw: float = 1.2, color: str = "k",
            logy: bool = False, fill: bool = False,
            title: str | None = None) -> dict:
    """Igor's LogHistOfBlock: counts per trace against log10(G/G0).

    Returns {"peak": the 1 G0 peak position in decades, "note": a line for
    a status bar, "centres", "counts"}.
    """
    bins = max(10, int(bins))
    smooth = max(1, int(smooth))
    key = ("1d", bins, smooth)
    if key not in data.cache:
        data.cache[key] = analysis.log_histogram(data.traces, lo=-8.0, hi=2.0,
                                                 n_bins=bins, smooth_width=smooth)
    centres, counts = data.cache[key]
    note = ""
    try:
        ax.plot(centres, counts, color=color, lw=lw)
        if fill:
            ax.fill_between(centres, 0, counts, color=color, alpha=0.25)
    except ValueError:
        ax.plot(centres, counts, color="k", lw=lw)
        note = f"'{color}' is not a colour name; drew black. "
    if logy:
        ax.set_yscale("log")
    ax.set_xlim(*xlim)
    ax.set_xlabel("log10 (G / G0)")
    ax.set_ylabel("counts per trace")
    ax.set_title(title or f"{data.name}: {data.n} traces", fontsize=10)
    for g in GOLD_LINES:
        ax.axvline(g, color="#999", lw=0.5, ls=":")
    ax.grid(True, alpha=0.3)
    peak = analysis.peak_position(centres, counts, around=0.0, window=0.4)
    note += f"1 G0 peak at {peak:+.4f} decades; {bins} bins, smooth {smooth} points"
    return {"peak": peak, "note": note, "centres": centres, "counts": counts}


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
    return {"max": top, "note": note, "counts": counts, "x_edges": xe,
            "y_edges": ye}


def figure(data: Data, kind: str, fig=None, **knobs):
    """A whole figure: ``kind`` "1D", "2D" or "both" (side by side). ``knobs``
    are hist_1d's and hist_2d's keyword arguments, each handed to the one
    that takes it. Draws on ``fig`` when given, else makes one."""
    from matplotlib.figure import Figure
    kind = kind.lower()
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


def trace_figure(path, number: int, fig=None):
    """Trace ``number`` (1 = the first) of one file. A .h5 session has the
    raw record, so it gets the six panels of stmlab.plots.figure_for_session;
    an .ibw or .txt block holds conductance only, so it gets the trace
    against displacement beside the block's histogram. Returns
    (figure, info) with info["n"], info["number"], info["verdict"]."""
    path = Path(path)
    if path.suffix.lower() == ".h5":
        return plots.figure_for_session(path, max(0, int(number) - 1), fig=fig)
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

def parse(argv) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Plots of a saved STM-BJ session.",
        epilog="python plot.py <session>.h5 1D | 2D | -<trace number> | (nothing: both)",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("items", nargs="+",
                   help="file(s): .h5 (this program), .ibw (Igor), .txt; then "
                        "1D, 2D or -N (trace N, 1 = the first); nothing after "
                        "the files: 1D and 2D")
    g1 = p.add_argument_group("1D")
    g1.add_argument("--bins", type=int, default=1000)
    g1.add_argument("--smooth", type=int, default=11, help="box smoothing, points")
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
                   help="folder for the PNG (default: beside the file)")
    p.add_argument("--dpi", type=int, default=110)
    args = p.parse_args(argv)

    args.files, args.mode, args.trace = [], "both", None
    for item in args.items:
        low = item.lower()
        if low.endswith((".h5", ".ibw", ".txt")):
            args.files.append(Path(item))
        elif low in ("1d", "2d", "both"):
            args.mode = low
        elif low.lstrip("-").isdigit():
            args.trace = int(low.lstrip("-"))
            args.mode = "trace"
            if args.trace < 1:
                p.error("traces are counted from 1: -1 is the first")
        else:
            p.error(f"'{item}' is not a .h5/.ibw/.txt file, 1D, 2D or a trace number")
    if not args.files:
        p.error("give a .h5, .ibw or .txt file")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse(sys.argv[1:] if argv is None else argv)
    import matplotlib
    matplotlib.use("Agg" if args.save else "TkAgg")
    import matplotlib.pyplot as plt

    if args.mode == "trace":
        if len(args.files) > 1:
            print("one file at a time for a trace")
            return 2
        path = args.files[0]
        fig = plt.figure(figsize=(13, 7.5), dpi=100)
        _, info = trace_figure(path, args.trace, fig=fig)
        v = info["verdict"]
        print(f"{path.name}: {info['n']} traces; trace {args.trace} "
              f"{'accepted' if v.accepted else 'rejected'} ({v.reason})")
        out_name = f"{path.stem}_trace{args.trace:04d}.png"
        title = f"trace {args.trace}: {path.name}"
    else:
        data = load(args.files)
        print(f"{data.name}: {data.n} traces")
        knobs = dict(bins=args.bins, smooth=args.smooth, logy=args.logy,
                     fill=args.fill, color=args.color, lw=args.lw,
                     xbins=args.xbins, ybins=args.ybins, ylim=tuple(args.ylim),
                     align=None if args.align < 0 else args.align,
                     cmap=args.cmap, vmax=args.vmax,
                     colorbar=not args.no_colorbar)
        if args.xlim is not None:
            knobs["xlim"] = tuple(args.xlim)
        fig = plt.figure(figsize=(13, 5.4) if args.mode == "both" else (7.5, 5.4),
                         dpi=100)
        figure(data, args.mode, fig=fig, **knobs)
        out_name = (f"{args.files[0].stem}_"
                    f"{'hist' if args.mode == 'both' else args.mode.upper()}.png")
        title = f"{args.mode.upper()}: {data.name}"

    if args.save:
        out_dir = args.out or args.files[0].parent
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / out_name
        fig.savefig(out, dpi=args.dpi)
        print(f"wrote {out}")
    else:
        if fig.canvas.manager is not None:
            fig.canvas.manager.set_window_title(title)
        plt.show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
