"""The plots the approach-and-pull test draws, as functions on matplotlib axes.

One function per picture, each taking an ``Axes`` and plain arrays, so the
same code draws the live window of ``02_approach_pull.py`` and the figures
for a saved session. Run it on a file to get the figures as PNGs:

    python rigtests/plots.py data/rigtest02_20261006_1530.h5            # trace 0
    python rigtests/plots.py data/rigtest02_20261006_1530.h5 --trace 7  # trace 7
    python rigtests/plots.py data/rigtest02_20261006_1530.h5 --out figs # PNGs there

Igor's windows, for orientation: ``HighRes`` is :func:`plot_record`,
``PullOutLowG`` is :func:`plot_trace` on a log axis, ``AuAuConductanceLevel``
is :func:`plot_gold_level`, ``SenseInDisplay`` is :func:`plot_piezo`,
``LogHistOfBlock`` is :func:`plot_histogram`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from stmlab import analysis, storage                          # noqa: E402
from stmlab.config import RigConfig                          # noqa: E402

C_CMD, C_SENSE = "#1f77b4", "#d62728"       # piezo command, piezo readback
C_V, C_I = "#ff7f0e", "#2ca02c"             # junction voltage, current
C_G, C_REJ = "#000000", "#999999"           # conductance, rejected trace


# --------------------------------------------------------------------------
# One record: what the inputs saw during a play
# --------------------------------------------------------------------------

def plot_record(ax, cfg: RigConfig, record: np.ndarray, fs: float,
                spike_front: int | None = None, title: str = "record") -> None:
    """Junction voltage (mV) and preamp current (uA) against time (ms).

    ``record`` is the (2, n) array a play returned, raw volts; the voltage
    sign and the preamp gain from the config turn it into mV and uA. The
    alignment spike, if ``spike_front`` is given, is marked where it was
    *written*; it appears in the data a group delay later.
    """
    M, C = cfg.channels, cfg.cal
    n = record.shape[1]
    t_ms = np.arange(n) / fs * 1e3
    v_mv = C.voltage_input_sign * record[M.ROW_VOLTAGE] * 1e3
    i_ua = C.volts_to_amps(record[M.ROW_CURRENT]) * 1e6

    ax.clear()
    ax.plot(t_ms, v_mv, color=C_V, lw=0.8, label="junction V (mV)")
    ax.set_ylabel("junction (mV)", color=C_V, fontsize=8)
    ax.tick_params(axis="y", colors=C_V, labelsize=8)
    ax.tick_params(axis="x", labelsize=8)
    ax.set_xlabel("time (ms)", fontsize=8)
    ax2 = _twin(ax)
    ax2.plot(t_ms, i_ua, color=C_I, lw=0.8, label="current (uA)")
    ax2.set_ylabel("current (uA)", color=C_I, fontsize=8)
    ax2.tick_params(axis="y", colors=C_I, labelsize=8)
    if spike_front is not None and 0 <= spike_front < n:
        ax.axvline(spike_front / fs * 1e3, color="k", lw=0.5, ls="--", alpha=0.5)
    ax.set_title(title, fontsize=9)
    ax.grid(True, alpha=0.3)


# --------------------------------------------------------------------------
# One trace: conductance against displacement
# --------------------------------------------------------------------------

def plot_trace(ax, cfg: RigConfig, g0: np.ndarray, disp_nm: np.ndarray,
               verdict=None, title: str = "trace") -> None:
    """log10(G/G0) against displacement, Igor's PullOutLowG.

    Horizontal lines at 1 G0 and at the break threshold; the title carries
    the selection verdict when one is given.
    """
    R = cfg.ramp
    ax.clear()
    ok = verdict is None or getattr(verdict, "accepted", True)
    with np.errstate(divide="ignore", invalid="ignore"):
        y = np.log10(np.clip(g0, 1e-12, None))
    ax.plot(disp_nm, y, color=C_G if ok else C_REJ, lw=0.8)
    ax.axhline(0.0, color=C_CMD, lw=0.6, ls="--", alpha=0.7)
    ax.axhline(np.log10(R.break_g0), color=C_SENSE, lw=0.6, ls=":", alpha=0.7)
    ax.set_xlim(float(disp_nm[0]), float(disp_nm[-1]))
    ax.set_ylim(-7.5, 1.0)
    ax.set_xlabel("displacement (nm)", fontsize=8)
    ax.set_ylabel("log10 (G / G0)", fontsize=8)
    ax.tick_params(labelsize=8)
    if verdict is not None:
        title = f"{title}: {verdict.reason}" if verdict.accepted \
            else f"{title}: REJECTED, {verdict.reason}"
    ax.set_title(title, fontsize=9)
    ax.grid(True, alpha=0.3)


def plot_gold_level(ax, cfg: RigConfig, g0: np.ndarray, disp_nm: np.ndarray,
                    title: str = "gold level") -> None:
    """G/G0 on a linear axis, 0 to 5, Igor's AuAuConductanceLevel: the
    single-atom plateau is the flat step at 1."""
    ax.clear()
    ax.plot(disp_nm, g0, color=C_G, lw=0.8)
    ax.axhline(1.0, color=C_CMD, lw=0.6, ls="--", alpha=0.7)
    ax.set_xlim(float(disp_nm[0]), float(disp_nm[-1]))
    ax.set_ylim(-0.1, 5.0)
    ax.set_xlabel("displacement (nm)", fontsize=8)
    ax.set_ylabel("G / G0", fontsize=8)
    ax.tick_params(labelsize=8)
    ax.set_title(title, fontsize=9)
    ax.grid(True, alpha=0.3)


# --------------------------------------------------------------------------
# The piezo: in and out
# --------------------------------------------------------------------------

def plot_piezo(ax, cfg: RigConfig, t_s: np.ndarray, cmd_v: np.ndarray,
               sense_v: np.ndarray | None = None, marks: dict | None = None,
               title: str = "piezo") -> None:
    """Commanded piezo position (nm) against time, with the readback on top
    when there is one. ``marks`` is {label: time_s} for the phases of a
    cycle (approach start, contact, pull start, pull end)."""
    C = cfg.cal
    ax.clear()
    ax.plot(t_s, C.piezo_volts_to_nm(cmd_v), color=C_CMD, lw=1.0,
            label="command")
    if sense_v is not None and np.isfinite(sense_v).any():
        ax.plot(t_s, C.sense_volts_to_nm(sense_v), color=C_SENSE, lw=0.8,
                label="readback")
    for label, when in (marks or {}).items():
        ax.axvline(when, color="k", lw=0.5, ls=":", alpha=0.6)
        ax.text(when, ax.get_ylim()[1] if ax.lines else 0, label, fontsize=7,
                rotation=90, va="top", ha="right", alpha=0.7)
    ax.set_xlabel("time (s)", fontsize=8)
    ax.set_ylabel("piezo (nm)", fontsize=8)
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=7, loc="upper right", frameon=False)
    ax.set_title(title, fontsize=9)
    ax.grid(True, alpha=0.3)


def plot_approach(ax, cfg: RigConfig, piezo_v: np.ndarray, g0: np.ndarray,
                  railed: np.ndarray | None = None,
                  title: str = "approach") -> None:
    """Conductance read at each approach step against the piezo position:
    where the junction closed. Railed probes are drawn at the top of the
    axis, since their conductance is a floor, not a value."""
    C, R = cfg.cal, cfg.ramp
    ax.clear()
    x = C.piezo_volts_to_nm(np.asarray(piezo_v, dtype=float))
    g = np.asarray(g0, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        y = np.log10(np.clip(g, 1e-12, 1e3))
    if railed is not None:
        railed = np.asarray(railed, dtype=bool)
        y = np.where(railed, 1.5, y)
        ax.plot(x[railed], y[railed], "^", color=C_SENSE, ms=4, label="railed")
        ax.plot(x[~railed], y[~railed], "o-", color=C_G, ms=3, lw=0.6)
    else:
        ax.plot(x, y, "o-", color=C_G, ms=3, lw=0.6)
    ax.axhline(np.log10(R.engage_g0), color=C_CMD, lw=0.6, ls="--", alpha=0.7)
    ax.axhline(np.log10(R.break_g0), color=C_SENSE, lw=0.6, ls=":", alpha=0.7)
    ax.set_ylim(-7.5, 2.0)
    ax.set_xlabel("piezo (nm)", fontsize=8)
    ax.set_ylabel("log10 (G / G0)", fontsize=8)
    ax.tick_params(labelsize=8)
    ax.set_title(title, fontsize=9)
    ax.grid(True, alpha=0.3)


# --------------------------------------------------------------------------
# Many traces: the histogram
# --------------------------------------------------------------------------

def plot_histogram(ax, cfg: RigConfig, centres: np.ndarray, counts: np.ndarray,
                   n_traces: int, title: str = "histogram") -> None:
    """Counts per trace against log10(G/G0), Igor's LogHistOfBlock."""
    ax.clear()
    ax.plot(centres, counts, color=C_G, lw=0.8)
    ax.axvline(0.0, color=C_CMD, lw=0.6, ls="--", alpha=0.7)
    ax.set_xlim(-7.0, 1.0)
    ax.set_ylim(0, max(1e-9, float(np.max(counts)) * 1.1) if counts.size else 1)
    ax.set_xlabel("log10 (G / G0)", fontsize=8)
    ax.set_ylabel("counts / trace", fontsize=8)
    ax.tick_params(labelsize=8)
    ax.set_title(f"{title}: {n_traces} traces", fontsize=9)
    ax.grid(True, alpha=0.3)


# --------------------------------------------------------------------------
# Junction I against V
# --------------------------------------------------------------------------

def plot_iv(ax, cfg: RigConfig, voltage_v: np.ndarray, current_v: np.ndarray,
            title: str = "junction I-V") -> None:
    """Current against junction voltage, sample by sample, for one pull.

    At constant bias this is a vertical line at the bias (and a second one
    at minus the bias during the alignment spike); its spread in current is
    the trace. A real I-V sweep is experiment 03.
    """
    M, C = cfg.channels, cfg.cal
    del M
    ax.clear()
    v_mv = C.voltage_input_sign * np.asarray(voltage_v) * 1e3
    i_ua = C.volts_to_amps(np.asarray(current_v)) * 1e6
    ax.plot(v_mv, i_ua, ".", color=C_G, ms=1.5, alpha=0.5)
    ax.set_xlabel("junction voltage (mV)", fontsize=8)
    ax.set_ylabel("current (uA)", fontsize=8)
    ax.tick_params(labelsize=8)
    ax.set_title(title, fontsize=9)
    ax.grid(True, alpha=0.3)


# --------------------------------------------------------------------------
# A whole figure for a saved session
# --------------------------------------------------------------------------

def _twin(ax):
    """A right-hand axis for ``ax``, reused across redraws."""
    twin = getattr(ax, "_stm_twin", None)
    if twin is None:
        twin = ax.twinx()
        ax._stm_twin = twin
    else:
        twin.clear()
    return twin


def figure_for_session(path: str | Path, trace_index: int = 0):
    """Six panels for one trace of a saved session plus its histogram.

    Returns (figure, info dict). The record panel shows the cut trace, since
    the file keeps the trace and not the pads around it.
    """
    from matplotlib.figure import Figure

    with storage.Session(path) as session:
        cfg = session.cfg
        n = len(session)
        if n == 0:
            raise ValueError(f"{path} holds no traces")
        i = max(0, min(trace_index, n - 1))
        voltage, current = session.raw(i)
        g0 = session.conductance(i)
        fs = float(session.scalar("sample_rate_hz")[i])
        start_v = float(session.scalar("start_piezo_v")[i])
        disp = analysis.displacement_nm(voltage.size, cfg.ramp, fs)
        sense = session.piezo_sense(i, in_nm=False)
        centres, counts = analysis.log_histogram(session.conductances())
        verdict = analysis.select_trace(g0, cfg.ramp)

    fig = Figure(figsize=(13, 7.5), dpi=100)
    axes = fig.subplots(2, 3)
    record = np.stack([voltage, current])
    plot_record(axes[0, 0], cfg, record, fs, title=f"trace {i} of {n}: record")
    plot_trace(axes[0, 1], cfg, g0, disp, verdict, title=f"trace {i}")
    plot_gold_level(axes[0, 2], cfg, g0, disp)
    t = np.arange(voltage.size) / fs
    cmd = start_v - cfg.cal.nm_to_piezo_volts(disp)
    plot_piezo(axes[1, 0], cfg, t, cmd, sense, title="piezo during the pull")
    plot_histogram(axes[1, 1], cfg, centres, counts, n)
    plot_iv(axes[1, 2], cfg, voltage, current)
    fig.suptitle(str(Path(path).name), fontsize=10)
    fig.tight_layout()
    return fig, {"n": n, "index": i, "verdict": verdict}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("path", type=Path, help="a session .h5 file")
    p.add_argument("--trace", type=int, default=0, help="trace index (default 0)")
    p.add_argument("--out", type=Path, default=None,
                   help="folder for the PNG (default: beside the .h5)")
    args = p.parse_args(argv)

    import matplotlib
    matplotlib.use("Agg")
    fig, info = figure_for_session(args.path, args.trace)
    out_dir = args.out or args.path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{args.path.stem}_trace{info['index']:04d}.png"
    fig.savefig(out, dpi=110)
    print(f"{args.path.name}: {info['n']} traces; trace {info['index']} "
          f"{'accepted' if info['verdict'].accepted else 'rejected'} "
          f"({info['verdict'].reason})")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
