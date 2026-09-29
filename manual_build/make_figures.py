#!/usr/bin/env python3
"""Regenerate the GUI manual's figures from a simulated session.

Drives the real panels and graphs (root window withdrawn) through the lab
flow -- Start Writing, background read, approach, Find Offset, Find
Suppress, a 100-trace constant-bias run with V0 tracking, a CV -- and saves
every graph window's figure to manual/figures/gui/. Nothing here is drawn by
hand: every PNG is what the corresponding window showed.

    ./.venv/bin/python manual_build/make_figures.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "manual" / "figures" / "gui"


def main() -> int:
    import tkinter as tk

    from stmgui.app import App
    from stmgui.state import simulated_state

    OUT.mkdir(parents=True, exist_ok=True)
    state = simulated_state()
    state.opts.data_dir = tempfile.mkdtemp(prefix="stmgui_figs_")
    state.cfg.vzero.settle_s = 0.0
    root = tk.Tk()
    root.withdraw()
    app = App(state=state, simulate=True, root=root)
    ctl = app.ctl
    ctl.wait_idle()

    ctl.start_writing(wait=True)
    ctl._run("bkgd", ctl._background_read, wait=True)      # one HighRes read
    ctl.approach(wait=True)
    ctl.find_offset(wait=True)
    ctl.find_suppress(wait=True)

    state.opts.vzero_check = True
    state.cfg.vzero.every_n_traces = 25
    state.opts.stop_number = state.opts.pull_out_number + 100
    ctl.start_measurement(wait=True)

    ctl.set_gain(6, wait=True)
    ctl.start_cv("highres", wait=True)
    app.pump_once()
    root.update()

    for name in app.graphs.names():
        win = app.graphs.get(name)
        path = OUT / f"{name}.png"
        win.fig.savefig(path, dpi=150)
        print("wrote", path.relative_to(ROOT))

    print("saved traces:", state.opts.pull_out_number - 1,
          "attempts:", state.opts.pull_out_attempt,
          "V0 measurements:", len(ctl.vzero_tracker.history))
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
