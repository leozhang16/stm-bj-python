"""The Voltage_Offset panel (Windows_STMBJ.ipf:378-405).

    Tip Bias interval (mV)     Frequency (traces)
    Number of points
    [ ] V0 check ON            V0 (fit, mV)
    [Find Offset]              I0 (fit, uA)

"Find Offset" is the button the lab calls "Find Zero": it runs Igor's
OffsetVoltage, fills V0 / I0, and opens the Izero graph. With "V0 check ON"
ticked, every constant-bias trace is applied at TipBias + V0 and V0 is
re-measured every "Frequency" saved traces (SaveOffset), which is what the
Izero_Time graph plots.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..state import PARAMS
from ..widgets import FONT, FONT_BOLD, CheckBox, SetVariable, ValDisplay, \
    button, groupbox


class VoltageOffsetPanel(tk.Toplevel):
    def __init__(self, master, app, position=(790, 655)):
        super().__init__(master)
        self.app = app
        self.state = app.state
        self.ctl = app.ctl
        self.title("Voltage Offset")
        self.geometry(f"+{position[0]}+{position[1]}")
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self.refreshable: list = []

        box = groupbox(self, "Voltage Offset")
        box.pack(fill="both", expand=True, padx=8, pady=8)

        self.interval = SetVariable(box, PARAMS["G_VoltageInterval"], self.state,
                                    width=6)
        self.interval.grid(row=0, column=0, sticky="w", pady=2)
        self.freq = SetVariable(box, PARAMS["G_Vzerofrequency"], self.state,
                                width=6)
        self.freq.grid(row=0, column=1, sticky="w", padx=(12, 0), pady=2)
        self.npts = SetVariable(box, PARAMS["G_NumPoints"], self.state, width=6)
        self.npts.grid(row=1, column=0, sticky="w", pady=2)

        self.check = CheckBox(box, PARAMS["VzeroCheckBox"], self.state,
                              on_toggle=self._toggled,
                              tip="Igor: VzeroCheckBox. ON: constant-bias traces are "
                                  "applied at TipBias + V0, V0 is re-measured every "
                                  "Frequency saved traces (SaveOffset), and a high-bias "
                                  "hold uses V0 as its hold bias.")
        self.check.configure(style="Big.TCheckbutton")
        self.check.grid(row=2, column=0, sticky="w", pady=(8, 2))
        self.vzero = ValDisplay(box, "V0 (fit, mV)", fmt="%3.4f", width=10,
                                bold=True)
        self.vzero.grid(row=2, column=1, sticky="w", padx=(12, 0), pady=(8, 2))

        self.b_find = button(box, "Find Offset", self.ctl.find_offset,
                             fg="#00aa00", font=("Arial", 14),
                             tip=self.ctl.find_offset)
        self.b_find.grid(row=3, column=0, sticky="w", pady=(6, 2))
        self.izero = ValDisplay(box, "I0 (fit, uA)", fmt="%3.6f", width=10,
                                bold=True)
        self.izero.grid(row=3, column=1, sticky="w", padx=(12, 0), pady=(6, 2))

        self.refreshable = [self.interval, self.freq, self.npts, self.check]
        self.refresh_all()

    def _toggled(self, on: bool) -> None:
        self.app.log(f"V0 check {'ON' if on else 'OFF'}: constant-bias traces "
                     f"{'carry' if on else 'ignore'} the measured offset")

    def refresh_all(self) -> None:
        for w in self.refreshable:
            w.refresh()
        self.vzero.set(self.state.opts.vzero_mv)
        self.izero.set(self.state.opts.izero_ua)

    def on_event(self, kind: str, payload) -> None:
        if kind == "vzero":
            vz, iz = payload
            self.vzero.set(vz)
            self.izero.set(iz)
        elif kind == "config":
            self.refresh_all()
        elif kind in ("busy", "idle"):
            self.b_find.configure(state="disabled" if kind == "busy"
                                  else "normal")
