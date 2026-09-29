"""The EChem panel (Windows_STMBJ.ipf:436-473).

    Electrochemical Gating     [Counter Electrode ON]
                               Counter Electrode Bias (mV)   (enabled after ON)
    Cyclic Voltammetry         Gain ( log(V/A) )
                               CV Acquisition Rate (samps/s)
                               Number of Cycles
                               Scan Rate (mV/s)
                               Voltage Peak 1 (V)   Voltage Peak 2 (V)
                               [CV HighRes]  [CV LowRes]

Igor enabled the two CV buttons only after SetGain had run (so the gain
the conductance divides by is known); the same rule applies here.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..state import PARAMS
from ..widgets import FONT, MAGENTA, RED, SetVariable, button, groupbox, \
    set_enabled


class EChemPanel(tk.Toplevel):
    def __init__(self, master, app, position=(847, 62)):
        super().__init__(master)
        self.app = app
        self.state = app.state
        self.ctl = app.ctl
        self.title("Electrochemistry")
        self.geometry(f"+{position[0]}+{position[1]}")
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

        gate = groupbox(self, "Electrochemical Gating")
        gate.pack(fill="x", padx=8, pady=(8, 4))
        self.b_on = button(gate, "Counter\nElectrode\nON",
                           self.ctl.counter_electrode_on, fg="#006633",
                           font=("Arial", 14, "bold"), width=10,
                           tip=self.ctl.counter_electrode_on)
        self.b_on.pack(pady=4)
        self.gate_mv = SetVariable(gate, PARAMS["G_CounterElectrodeBias"],
                                   self.state,
                                   on_commit=self.ctl.set_counter_electrode,
                                   tip=self.ctl.set_counter_electrode,
                                   width=8, font=("Arial", 13))
        self.gate_mv.pack(pady=4)
        set_enabled(self.gate_mv, False)

        cv = groupbox(self, "Cyclic Voltammetry")
        cv.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self.gain = SetVariable(cv, PARAMS["G_CurrentVoltGain"], self.state,
                                on_commit=self.ctl.set_gain, width=4,
                                tip=self.ctl.set_gain,
                                font=("Arial", 13))
        self.gain.pack(anchor="w", pady=2)
        self.setvars = [self.gain]
        for igor in ("G_CVAcquisitionRate", "G_NumCVCycles", "G_ScanRate",
                     "G_VoltagePeakOne", "G_VoltagePeakTwo"):
            w = SetVariable(cv, PARAMS[igor], self.state, width=7,
                            font=("Arial", 13))
            w.pack(anchor="w", pady=2)
            self.setvars.append(w)
        row = ttk.Frame(cv)
        row.pack(pady=(8, 2))
        self.b_high = button(row, "CV HighRes",
                             lambda: self.ctl.start_cv("highres"), fg=RED,
                             font=("Arial", 14, "bold"), width=10,
                             tip=self.ctl.start_cv)
        self.b_high.pack(side="left", padx=4)
        self.b_low = button(row, "CV LowRes",
                            lambda: self.ctl.start_cv("lowres"), fg=MAGENTA,
                            font=("Arial", 14, "bold"), width=10,
                            tip=self.ctl.start_cv)
        self.b_low.pack(side="left", padx=4)
        self.set_cv_enabled(False)                     # until SetGain

    def set_cv_enabled(self, on: bool) -> None:
        set_enabled(self.b_high, on)
        set_enabled(self.b_low, on)

    def refresh_all(self) -> None:
        for w in self.setvars:
            w.refresh()
        self.gate_mv.refresh()

    def on_event(self, kind: str, payload) -> None:
        if kind == "gate":
            on = payload is not None
            set_enabled(self.b_on, not on)
            set_enabled(self.gate_mv, on)
            self.gate_mv.refresh()
        elif kind == "gain":
            self.gain.refresh()
            self.set_cv_enabled(True)
        elif kind == "writing" and not payload:
            # StopWritingTasks: gate button back on, bias entry off, CV off
            set_enabled(self.b_on, True)
            set_enabled(self.gate_mv, False)
            self.set_cv_enabled(False)
        elif kind == "config":
            self.refresh_all()
