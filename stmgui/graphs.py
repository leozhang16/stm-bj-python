"""The nine Igor graph windows (Windows_STMBJ.ipf), as matplotlib-in-Tk.

    HighRes                 last background read: junction V (mV) and I (uA)
    PullOutGvsE             last trace, conductance (G0) vs displacement, linear
    PullOutLow ("PullOutLowG")  same on a log axis 1e-6..5.6, plus measured bias
    AuAuConductanceLevel    same, linear, 1e-5..5 (the gold-plateau view)
    SenseInDisplay          piezo (nm) vs points for the last trace
    LogHistOfBlock          counts/trace vs log10(G/G0) for the last block
    Izero                   I(applied bias) points and fit -- the Find Offset result
    Izero_Time              Izero against saved trace number
    CyclicVoltammogram      tip current vs applied potential, x reversed

Each is a Toplevel that starts withdrawn; ``show()`` raises it, closing it
only hides it (Igor's DoWindow/F re-opens the same window). ``on_event``
routes the controller's events to whichever graphs they feed.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import numpy as np

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg   # noqa: E402
from matplotlib.figure import Figure                              # noqa: E402

from .widgets import FONT                                         # noqa: E402

# Igor's rgb= triples, converted.
IGOR_BLUE = "#0000ff"
IGOR_ORANGE = "#ffaa00"
IGOR_PINK = "#ff00cc"
IGOR_GREEN = "#009900"
IGOR_LIGHTBLUE = "#6060ff"


class GraphWindow(tk.Toplevel):
    """One Igor Graph window. Subclasses draw into ``self.ax``."""

    title_text = "Graph"
    igor_geometry = (400, 300)          # px, from Igor's Display /W=

    def __init__(self, master, position: tuple[int, int] = (0, 0)):
        super().__init__(master)
        self.title(self.title_text)
        w, h = self.igor_geometry
        self.geometry(f"{max(w, 360)}x{max(h, 260)}+{position[0]}+{position[1]}")
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self.fig = Figure(figsize=(max(w, 360) / 100, max(h, 260) / 100),
                          dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.tick_params(labelsize=9)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self._toolbar_frame = ttk.Frame(self)
        self._toolbar_frame.pack(fill="x")
        self.decorate()
        self.fig.tight_layout()
        self.withdraw()

    def decorate(self) -> None:
        """Axis labels and ranges. Called once."""

    def show(self) -> None:
        self.deiconify()
        self.lift()

    def redraw(self) -> None:
        try:
            self.fig.tight_layout()
        except Exception:                                 # noqa: BLE001
            pass
        self.canvas.draw_idle()


class HighRes(GraphWindow):
    title_text = "HighRes"
    igor_geometry = (400, 280)

    def decorate(self) -> None:
        self.ax2 = self.ax.twinx()
        self.ax.set_ylabel("Voltage (mV)", fontsize=9)
        self.ax2.set_ylabel("Current (uA)", fontsize=9)
        self.ax.set_xlabel("sample", fontsize=9)
        self.ax2.tick_params(labelsize=9)
        self.ax.ticklabel_format(useOffset=False, axis="y")
        self.ax2.ticklabel_format(useOffset=False, axis="y")
        (self.l_v,) = self.ax.plot([], [], color=IGOR_BLUE, lw=0.8,
                                   label="VoltageIn")
        (self.l_i,) = self.ax2.plot([], [], color=IGOR_GREEN, lw=0.8,
                                    label="CurrentIn")

    def update(self, payload: dict) -> None:
        v = np.asarray(payload["voltage_mv"])
        i = np.asarray(payload["current_ua"])
        x = np.arange(v.size)
        self.l_v.set_data(x, v)
        self.l_i.set_data(x, i)
        for ax, y in ((self.ax, v), (self.ax2, i)):
            ax.set_xlim(0, max(1, v.size - 1))
            lo, hi = float(np.min(y)), float(np.max(y))
            pad = 0.1 * (hi - lo) if hi > lo else 1e-3
            ax.set_ylim(lo - pad, hi + pad)
        self.redraw()


class _TraceGraph(GraphWindow):
    """Shared by the three PullOut graphs."""
    ylabel = "Conductance (G$_0$)"

    def decorate(self) -> None:
        self.ax.set_xlabel("Displacement (nm)", fontsize=9)
        self.ax.set_ylabel(self.ylabel, fontsize=9)
        self.ax.grid(True, axis="y", lw=0.4)
        (self.l_g,) = self.ax.plot([], [], color="#000000", lw=0.8)
        self.text = self.ax.text(0.98, 0.95, "", transform=self.ax.transAxes,
                                 fontsize=8, va="top", ha="right")

    def update(self, payload: dict) -> None:
        g = np.asarray(payload["g0"])
        x = np.asarray(payload["disp_nm"])
        self.l_g.set_data(x, g)
        self.ax.set_xlim(float(np.min(x)), float(max(np.max(x), np.min(x) + 1e-3)))
        self.text.set_text(f"trace {payload['number']} "
                           f"{'saved' if payload['accepted'] else 'rejected'}"
                           f" ({payload['mode']})")
        self.scale(g)
        self.redraw()

    def scale(self, g: np.ndarray) -> None:
        self.ax.set_ylim(0, max(1.0, float(np.nanmax(g)) * 1.05))


class PullOutGvsE(_TraceGraph):
    title_text = "PullOutGvsE"
    igor_geometry = (420, 300)


class PullOutLow(_TraceGraph):
    title_text = "PullOutLowG"
    igor_geometry = (560, 330)

    def decorate(self) -> None:
        super().decorate()
        self.ax.set_yscale("log")
        self.ax.set_ylim(1e-6, 5.58676)                   # Igor SetAxis left
        self.ax2 = self.ax.twinx()
        self.ax2.set_ylabel("Measured Bias (mV)", fontsize=9)
        self.ax2.tick_params(labelsize=9)
        (self.l_bias,) = self.ax2.plot([], [], color=IGOR_LIGHTBLUE, lw=0.6)
        self.l_bias.set_visible(False)                    # hideTrace=1
        self.show_bias = tk.BooleanVar(value=False)
        ttk.Checkbutton(self._toolbar_frame, text="show PullOutVoltage",
                        variable=self.show_bias,
                        command=self._toggle_bias).pack(side="left")

    def _toggle_bias(self) -> None:
        self.l_bias.set_visible(self.show_bias.get())
        self.redraw()

    def update(self, payload: dict) -> None:
        x = np.asarray(payload["disp_nm"])
        b = np.asarray(payload["bias_mv"])
        self.l_bias.set_data(x, b)
        lo, hi = float(np.min(b)), float(np.max(b))
        pad = 0.1 * (hi - lo) if hi > lo else 1.0
        self.ax2.set_ylim(lo - pad, hi + pad)
        super().update(payload)

    def scale(self, g: np.ndarray) -> None:
        self.ax.set_ylim(1e-6, 5.58676)


class AuAuConductanceLevel(_TraceGraph):
    title_text = "AuAuConductanceLevel"
    igor_geometry = (420, 300)

    def scale(self, g: np.ndarray) -> None:
        self.ax.set_ylim(1e-5, 5)                         # Igor SetAxis left


class SenseInDisplay(GraphWindow):
    title_text = "SenseInDisplay"
    igor_geometry = (360, 280)

    def decorate(self) -> None:
        self.ax.set_xlabel("Points", fontsize=9)
        self.ax.set_ylabel("Piezo (nm)", fontsize=9)
        (self.l,) = self.ax.plot([], [], color="#000000", lw=0.8)

    def update(self, payload: dict) -> None:
        y = np.asarray(payload["piezo_nm"])
        self.l.set_data(np.arange(y.size), y)
        self.ax.set_xlim(0, max(1, y.size - 1))
        lo, hi = float(np.min(y)), float(np.max(y))
        pad = 0.05 * (hi - lo) if hi > lo else 1.0
        self.ax.set_ylim(lo - pad, hi + pad)
        self.redraw()


class LogHistOfBlock(GraphWindow):
    title_text = "LogHistOfBlock"
    igor_geometry = (520, 420)

    def decorate(self) -> None:
        self.ax.set_xlabel("Conductance [Log]", fontsize=11)
        self.ax.set_ylabel("Counts/Trace", fontsize=11)
        self.ax.set_xlim(-6, 1)
        self.ax.set_ylim(0, 40)
        self.bars = None
        self.text = self.ax.text(0.02, 0.95, "", transform=self.ax.transAxes,
                                 fontsize=9, va="top")

    def update(self, payload: dict) -> None:
        centres = np.asarray(payload["centres"])
        counts = np.asarray(payload["counts"])
        if self.bars is not None:
            self.bars.remove()
        width = float(centres[1] - centres[0]) if centres.size > 1 else 0.01
        self.bars = self.ax.bar(centres, counts, width=width, color=IGOR_BLUE,
                                align="center", linewidth=0)
        top = float(np.max(counts)) if counts.size else 0.0
        self.ax.set_ylim(0, max(40.0, top * 1.1))
        self.text.set_text(f"{payload['n']} traces"
                           f"{' (partial block)' if payload.get('partial') else ''}")
        self.redraw()


class Izero(GraphWindow):
    title_text = "I(Applied Bias) fit - Izero estimate"
    igor_geometry = (440, 300)

    def decorate(self) -> None:
        self.ax.set_xlabel("Tip Applied Bias (mV)", fontsize=9)
        self.ax.set_ylabel("Current (uA)", fontsize=9)
        self.ax.axhline(0, color="#888888", lw=0.5)
        (self.pts,) = self.ax.plot([], [], "o", color=IGOR_PINK, ms=4,
                                   label="CurrentWave")
        (self.fit,) = self.ax.plot([], [], color=IGOR_BLUE, lw=1.0,
                                   label="fit_CurrentWave")
        self.text = self.ax.text(0.98, 0.05, "", transform=self.ax.transAxes,
                                 fontsize=9, ha="right", va="bottom",
                                 bbox=dict(boxstyle="round", fc="white",
                                           ec="#888888"))

    def update(self, result) -> None:
        x = np.asarray(result.bias_mv)
        y = np.asarray(result.current_a) * 1e6
        self.pts.set_data(x, y)
        if x.size >= 2:
            slope, intercept = np.polyfit(x, y, 1)
            xf = np.array([x.min(), x.max()])
            self.fit.set_data(xf, slope * xf + intercept)
            pad = 0.1 * (x.max() - x.min())
            self.ax.set_xlim(x.min() - pad, x.max() + pad)
            lo, hi = float(min(y.min(), 0)), float(max(y.max(), 0))
            padv = 0.1 * (hi - lo) if hi > lo else 1e-3
            self.ax.set_ylim(lo - padv, hi + padv)
        self.text.set_text(f"V$_0$ = {result.vzero_mv:.4f} mV\n"
                           f"I$_0$ = {result.izero_a * 1e6:.6f} uA")
        self.redraw()


class IzeroTime(GraphWindow):
    title_text = "Izero change over time"
    igor_geometry = (440, 300)

    def decorate(self) -> None:
        self.ax.set_xlabel("Saved Trace Number", fontsize=9)
        self.ax.set_ylabel("I$_0$ (uA x 1e-3)", fontsize=9)
        (self.l,) = self.ax.plot([], [], "-o", color=IGOR_GREEN, ms=4, lw=0.8)

    def update(self, payload) -> None:
        n, i = payload
        n = np.asarray(n)
        i = np.asarray(i) * 1e3
        self.l.set_data(n, i)
        if n.size:
            self.ax.set_xlim(float(n.min()) - 1, float(n.max()) + 1)
            lo, hi = float(i.min()), float(i.max())
            pad = 0.1 * (hi - lo) if hi > lo else 1.0
            self.ax.set_ylim(lo - pad, hi + pad)
        self.redraw()


class CyclicVoltammogram(GraphWindow):
    title_text = "Cyclic Voltammogram"
    igor_geometry = (560, 380)

    def __init__(self, master, cfg, position=(0, 0)):
        self.cfg = cfg
        super().__init__(master, position)

    def decorate(self) -> None:
        self.ax.set_xlabel("Applied Voltage (mV)", fontsize=10)
        self.ax.set_ylabel("Current (uA)", fontsize=10)
        self.ax.grid(True, axis="x", lw=0.4)
        self.lines: list = []
        self.text = self.ax.text(0.05, 0.93, "", transform=self.ax.transAxes,
                                 fontsize=10)

    def update(self, cycles: list) -> None:
        for line in self.lines:
            line.remove()
        self.lines = []
        gain = self.cfg.cal.preamp_gain_v_per_a
        for k, cyc in enumerate(cycles):
            x = np.asarray(cyc.applied_v) * 1e3
            y = np.asarray(cyc.tip_current_v) / gain * 1e6
            keep = np.asarray(cyc.keep, dtype=bool)
            y = np.where(keep, y, np.nan)
            last = k == len(cycles) - 1
            (line,) = self.ax.plot(x, y, color=IGOR_BLUE if last else "#9999ff",
                                   lw=1.0 if last else 0.6)
            self.lines.append(line)
        if cycles:
            self.ax.relim()
            self.ax.autoscale_view()
            self.ax.invert_xaxis() if not self.ax.xaxis_inverted() else None
            self.text.set_text(f"CV cycle {cycles[-1].cycle}")
        self.redraw()


class GraphSet:
    """All nine windows, created lazily, positioned like Igor's /W= boxes."""

    ORDER = [
        ("HighRes", HighRes, (620, 440)),
        ("PullOutGvsE", PullOutGvsE, (6, 44)),
        ("PullOutLowG", PullOutLow, (6, 385)),
        ("AuAuConductanceLevel", AuAuConductanceLevel, (6, 214)),
        ("SenseInDisplay", SenseInDisplay, (447, 403)),
        ("LogHistOfBlock", LogHistOfBlock, (296, 43)),
        ("Izero", Izero, (354, 46)),
        ("Izero_Time", IzeroTime, (341, 244)),
        ("CyclicVoltammogram", CyclicVoltammogram, (128, 47)),
    ]

    # Which event feeds which windows; the first-listed opens on first data.
    FEEDS = {
        "highres": ["HighRes"],
        "trace": ["PullOutLowG", "PullOutGvsE", "AuAuConductanceLevel",
                  "SenseInDisplay"],
        "hist": ["LogHistOfBlock"],
        "izero": ["Izero"],
        "izero_time": ["Izero_Time"],
        "cv": ["CyclicVoltammogram"],
    }

    def __init__(self, master, cfg):
        self.master = master
        self.cfg = cfg
        self._windows: dict[str, GraphWindow] = {}

    def names(self) -> list[str]:
        return [name for name, _, _ in self.ORDER]

    def get(self, name: str) -> GraphWindow:
        if name not in self._windows:
            for n, klass, pos in self.ORDER:
                if n == name:
                    if klass is CyclicVoltammogram:
                        self._windows[name] = klass(self.master, self.cfg, pos)
                    else:
                        self._windows[name] = klass(self.master, pos)
                    break
        return self._windows[name]

    def show(self, name: str) -> None:
        self.get(name).show()

    def on_event(self, kind: str, payload) -> None:
        names = self.FEEDS.get(kind)
        if not names:
            return
        for k, name in enumerate(names):
            first_time = name not in self._windows
            win = self.get(name)
            if name == "SenseInDisplay":
                win.update({"piezo_nm": payload["piezo_nm"]})
            else:
                win.update(payload)
            # Igor: DoWindow/F ...; if (V_flag==0) Execute "Window()"
            if first_time and (k == 0 or kind in ("izero", "cv", "hist")):
                win.show()
