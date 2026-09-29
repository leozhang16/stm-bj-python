"""The application: Igor's InitializeExperiment, plus the menus.

    InitializeExperiment()  (Setup1_STMBJ.ipf:55)
        Declare_STMBJ_Variables  -> GuiState()
        BreakJunctionMeasurement -> MainPanel in the root window
        SetUpGPIB_Keithley       -> ctl.connect_instruments()
        InitializeEChem          -> EChemPanel
        Voltage_Offset           -> VoltageOffsetPanel

Menus:
    File     load / save a RigConfig JSON, quit
    Macros   Igor's "Macros" menu: the panels, rungo, LateralEXPT, X piezo
    Windows  the nine graphs and the History window
    Help     where the manual is

The event pump (``_pump``) drains the controller's queue every 50 ms on
the Tk thread and fans each event out to the panels and graphs.
"""

from __future__ import annotations

import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .controller import IGOR_RUNGO_BIAS_MV, IGOR_RUNGO_TRACES_PER_BIAS, \
    RigController
from .graphs import GraphSet
from . import widgets
from .panels import ButtonMapWindow, EChemPanel, HistoryWindow, \
    InspectorWindow, MainPanel, VoltageOffsetPanel
from .state import GuiState, simulated_state

PKG_ROOT = Path(__file__).resolve().parents[1]


class App:
    PUMP_MS = 50

    def __init__(self, state: GuiState | None = None, simulate: bool = False,
                 root: tk.Tk | None = None):
        self.state = state or (simulated_state() if simulate else GuiState())
        if simulate:
            self.state.cfg.simulate = True
        self.root = root or tk.Tk()
        title = "Molecular Break Junction Measurement"
        if self.state.cfg.simulate:
            title += "  [SIMULATED]"
        self.root.title(title)
        self.root.geometry("+1265+60" if self.root.winfo_screenwidth() > 1700
                           else "+900+40")
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        style = ttk.Style(self.root)
        style.configure("Big.TCheckbutton", font=("Arial", 14, "bold"))
        style.configure("TLabel", font=("Arial", 12))
        style.configure("TLabelframe.Label", font=("Arial", 11))
        style.configure("TNotebook.Tab", font=("Arial", 12))

        self.ctl = RigController(self.state)

        self.main = MainPanel(self.root, self)
        self.main.pack(fill="both", expand=True)
        self.history = HistoryWindow(self.root)
        self.offset = VoltageOffsetPanel(self.root, self)
        self.echem = EChemPanel(self.root, self)
        self.graphs = GraphSet(self.root, self.state.cfg)
        self._build_menus()

        # The Alt key was Igor's abort; Escape works as well.
        for key in ("<Alt_L>", "<Alt_R>", "<Escape>"):
            self.root.bind_all(key, lambda _e: self.ctl.request_stop())

        # Right-click on any control -> the Inspector window.
        self.inspector = None
        self.button_map = None
        widgets.INSPECT_HOOK = self.inspect

        self.log("Molecular Break Junction Measurement -- "
                 f"{'SIMULATED rig' if self.state.cfg.simulate else 'hardware'}")
        self.log("Igor flow: Start Writing -> (Background Sampling) -> "
                 "Start Approach -> Find Offset -> Find Suppress -> "
                 "Start Measurement. Stop = Alt / Escape / the Stop button.")
        self.log("WHICH CODE RUNS A BUTTON? Hover it (tooltip), right-click "
                 "it (Inspector window), press 'Which code runs this?' at "
                 "the bottom of the panel (Button map), or watch the "
                 "'-> name: file:line function' line printed here on every "
                 "click.")
        self.ctl.connect_instruments()
        self.root.after(self.PUMP_MS, self._pump)

    # ------------------------------------------------------------------

    def log(self, text: str) -> None:
        self.history.append(text)

    def _build_menus(self) -> None:
        bar = tk.Menu(self.root)

        m_file = tk.Menu(bar, tearoff=0)
        m_file.add_command(label="Load config JSON...", command=self._load_cfg)
        m_file.add_command(label="Save config JSON...", command=self._save_cfg)
        m_file.add_separator()
        m_file.add_command(label="Open data folder", command=self._open_data)
        m_file.add_separator()
        m_file.add_command(label="Quit", command=self.quit)
        bar.add_cascade(label="File", menu=m_file)

        m_macros = tk.Menu(bar, tearoff=0)
        m_macros.add_command(label="STM Break Junction Measurement",
                             command=lambda: (self.root.deiconify(),
                                              self.root.lift()))
        m_macros.add_command(label="Voltage Offset panel",
                             command=lambda: (self.offset.deiconify(),
                                              self.offset.lift()))
        m_macros.add_command(label="Electrochemistry panel",
                             command=lambda: (self.echem.deiconify(),
                                              self.echem.lift()))
        m_macros.add_separator()
        m_macros.add_command(label="rungo()  bias series...", command=self._rungo)
        m_macros.add_command(label="LateralEXPT(Z, X, XFreq)...",
                             command=self._lateral)
        m_macros.add_separator()
        m_macros.add_command(label="MoveXPiezo(nm)...", command=self._move_x)
        m_macros.add_command(label="MoveXPiezoToZero()",
                             command=self.ctl.zero_xpiezo)
        m_macros.add_separator()
        m_macros.add_command(label="Stop (Alt)", command=self.ctl.request_stop)
        bar.add_cascade(label="Macros", menu=m_macros)

        m_win = tk.Menu(bar, tearoff=0)
        for name in self.graphs.names():
            m_win.add_command(label=name,
                              command=lambda n=name: self.graphs.show(n))
        m_win.add_separator()
        m_win.add_command(label="History",
                          command=lambda: (self.history.deiconify(),
                                           self.history.lift()))
        m_win.add_command(label="Button map (control -> Python -> Igor)",
                          command=self.show_button_map)
        bar.add_cascade(label="Windows", menu=m_win)

        m_help = tk.Menu(bar, tearoff=0)
        m_help.add_command(label="Button map: which Python does each button run?",
                           command=self.show_button_map)
        m_help.add_command(label="About / where the manual is",
                           command=self._about)
        bar.add_cascade(label="Help", menu=m_help)
        self.root.config(menu=bar)

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------

    def _load_cfg(self) -> None:
        path = filedialog.askopenfilename(
            title="Load RigConfig JSON", filetypes=[("JSON", "*.json")])
        if path:
            try:
                self.ctl.load_config(path)
            except Exception as exc:                     # noqa: BLE001
                messagebox.showerror("Load config", str(exc))
            self._fanout("config", None)

    def _save_cfg(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save RigConfig JSON", defaultextension=".json",
            filetypes=[("JSON", "*.json")])
        if path:
            self.ctl.save_config(path)

    def _open_data(self) -> None:
        import subprocess
        import sys
        path = self.ctl.data_dir()
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _rungo(self) -> None:
        text = simpledialog.askstring(
            "rungo", "Bias list in mV, comma-separated\n(Igor's list is "
            "pre-filled; Saved decides where it resumes):",
            initialvalue=", ".join(f"{b:.0f}" for b in IGOR_RUNGO_BIAS_MV),
            parent=self.root)
        if not text:
            return
        try:
            biases = [float(t) for t in text.replace(";", ",").split(",")
                      if t.strip()]
        except ValueError:
            messagebox.showerror("rungo", "could not parse the bias list")
            return
        n = simpledialog.askinteger("rungo", "Traces per bias:",
                                    initialvalue=IGOR_RUNGO_TRACES_PER_BIAS,
                                    minvalue=1, parent=self.root)
        if n:
            self.ctl.rungo(biases, n)

    def _lateral(self) -> None:
        z = simpledialog.askinteger("LateralEXPT", "ZDistance (actuator "
                                    "steps apart per site):", initialvalue=10,
                                    minvalue=1, parent=self.root)
        if z is None:
            return
        x = simpledialog.askfloat("LateralEXPT", "XDistance (nm per site):",
                                  initialvalue=200.0, parent=self.root)
        if x is None:
            return
        f = simpledialog.askinteger("LateralEXPT", "XFreq (traces per site):",
                                    initialvalue=250, minvalue=1,
                                    parent=self.root)
        if f is None:
            return
        self.ctl.lateral_expt(z, x, f)

    def _move_x(self) -> None:
        nm = simpledialog.askfloat("MoveXPiezo", "Relative move (nm):",
                                   initialvalue=200.0, parent=self.root)
        if nm is not None:
            self.ctl.move_xpiezo(nm)

    def show_button_map(self) -> None:
        """Windows / Help -> Button map: every control, the RigController
        method and _impl it runs (file:line), the Igor procedure, and the
        stmlab functions reached. Generated from controller.COMMAND_MAP."""
        if self.button_map is None:
            self.button_map = ButtonMapWindow(self.root)
        else:
            self.button_map.refresh()
        self.button_map.show()

    def inspect(self, text: str) -> None:
        """Right-click on any control: show its Python in the Inspector."""
        if self.inspector is None:
            self.inspector = InspectorWindow(self.root,
                                             on_open_map=self.show_button_map)
        self.inspector.show_text(text)
        self.history.append("inspect: " + text.splitlines()[0])

    def _about(self) -> None:
        messagebox.showinfo(
            "STM-BJ GUI",
            "The Igor STM break-junction panels on top of stmlab.\n\n"
            f"Package: {PKG_ROOT}\n"
            "Manual: STMLAB_GUI_Manual.pdf in this folder (Part I is the\n"
            "        GUI, chapters 40-51; source manual/4x_gui_*.md)\n"
            "Data:   data/<date>/ (HDF5 sessions, CSV histograms)")

    # ------------------------------------------------------------------
    # Event pump
    # ------------------------------------------------------------------

    def _fanout(self, kind: str, payload) -> None:
        for target in (self.main, self.offset, self.echem, self.history,
                       self.graphs):
            try:
                target.on_event(kind, payload)
            except tk.TclError:
                pass
            except Exception as exc:                         # noqa: BLE001
                self.history.append(f"GUI error on {kind}: {exc!r}", "error")

    def _pump(self) -> None:
        for _ in range(200):
            try:
                kind, payload = self.ctl.events.get_nowait()
            except queue.Empty:
                break
            self._fanout(kind, payload)
        if self.root.winfo_exists():
            self.root.after(self.PUMP_MS, self._pump)

    def pump_once(self) -> None:
        """Drain the queue synchronously (tests)."""
        while True:
            try:
                kind, payload = self.ctl.events.get_nowait()
            except queue.Empty:
                return
            self._fanout(kind, payload)

    def quit(self) -> None:
        try:
            self.ctl.shutdown()
        finally:
            if widgets.INSPECT_HOOK == self.inspect:
                widgets.INSPECT_HOOK = None      # do not keep this App alive
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main(argv: list[str] | None = None) -> int:
    import argparse
    import logging

    p = argparse.ArgumentParser(
        description="The Igor STM-BJ panels, on top of stmlab.")
    p.add_argument("--simulate", action="store_true",
                   help="use the simulated junction, card, Keithley and "
                        "actuator (no hardware, no drivers)")
    p.add_argument("--config", type=Path, default=None,
                   help="RigConfig JSON to start from")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname).1s %(name)s: %(message)s")

    state = simulated_state() if args.simulate else GuiState()
    if args.config:
        from stmlab.config import RigConfig
        state.cfg = RigConfig.from_json(args.config)
        if args.simulate:
            state.cfg.simulate = True
    app = App(state=state, simulate=args.simulate)
    app.run()
    return 0
