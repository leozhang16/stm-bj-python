"""The BreakJunctionMeasurement panel (Windows_STMBJ.ipf:133-375).

Same groups, same controls, same names, top to bottom:

    TabControl TAB: DAQ | Inputs | Options (sub-tabs Push-Pull, IV, AC,
                    High bias hold)
    Background Sampling (Beep is ON)
    Keithley Controls   Bias, Zero Check, Zero Correct, Suppress I,
                        Find Suppress, Gain, Suppress I value
    Actuator Controls   Step Size, counter, Start Approach, Step closer/apart
    Piezo Controls      Step closer, Z (nm), Step apart, slider
    Readouts            I (uA), V (mV), Piezo
    Saved, Tip Bias (mV), Stop #, Start Measurement, Attempts, +1

Two additions Igor did not have: a Stop button (Igor polled the Alt key),
and a "Piezo offset (nm)" entry on the DAQ tab (Igor's G_PiezoOffset_nm
was only settable from the command line, and on a unipolar piezo it is the
number that gives the pull somewhere to go).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..state import PARAMS
from ..widgets import (Tooltip, tip_text, BLUE, FONT, FONT_BIG, FONT_BOLD, GREEN, LIME, ORANGE,
                       RED, SKY, CheckBox, SetVariable, ValDisplay, button,
                       groupbox, set_enabled)


class MainPanel(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=6)
        self.app = app
        self.state = app.state
        self.ctl = app.ctl
        self.refreshable: list = []
        self._slider_programmatic = False
        self._build()
        self.set_writing(False)

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def _sv(self, parent, igor: str, on_commit=None, **kw) -> SetVariable:
        w = SetVariable(parent, PARAMS[igor], self.state, on_commit, **kw)
        self.refreshable.append(w)
        return w

    def _cb(self, parent, igor: str, on_toggle=None, **kw) -> CheckBox:
        w = CheckBox(parent, PARAMS[igor], self.state, on_toggle, **kw)
        self.refreshable.append(w)
        return w

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        row = 0

        # -- TabControl TAB -------------------------------------------
        self.tabs = ttk.Notebook(self)
        self.tabs.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        row += 1
        self._build_daq_tab()
        self._build_inputs_tab()
        self._build_options_tab()

        # -- Background sampling ---------------------------------------
        self.bkgd = self._cb(self, "OnCheck",
                             on_toggle=self.ctl.set_background_sampling,
                             tip=self.ctl.set_background_sampling)
        self.bkgd.configure(style="Big.TCheckbutton")
        self.bkgd.grid(row=row, column=0, sticky="w", pady=4)
        row += 1

        # -- Keithley Controls -----------------------------------------
        kb = groupbox(self, "Keithley Controls")
        kb.grid(row=row, column=0, sticky="ew", pady=3)
        row += 1
        self.k_bias = self._cb(kb, "G_KeithleyBiasEnabled",
                               on_toggle=self.ctl.keithley_bias,
                               tip=self.ctl.keithley_bias)
        self.k_bias.grid(row=0, column=0, sticky="w")
        self.k_zero = self._cb(kb, "ZeroCheckBox", on_toggle=self.ctl.zero_check,
                              tip=self.ctl.zero_check)
        self.k_zero.grid(row=0, column=1, sticky="w", padx=8)
        self.b_zero_correct = button(kb, "Zero Correct", self.ctl.zero_correct,
                                     fg=ORANGE, tip=self.ctl.zero_correct)
        self.b_zero_correct.grid(row=0, column=2, sticky="e", padx=4)
        self.k_sup = self._cb(kb, "SuppressCheckBox",
                              on_toggle=self.ctl.suppress_enable,
                              tip=self.ctl.suppress_enable)
        self.k_sup.grid(row=1, column=1, sticky="w", padx=8)
        self.b_find_sup = button(kb, "Find Suppress", self.ctl.find_suppress,
                                 fg=LIME if not _dark_text_needed() else "#008800",
                                 tip=self.ctl.find_suppress)
        self.b_find_sup.grid(row=1, column=2, sticky="e", padx=4)
        self.gain = self._sv(kb, "G_CurrentVoltGain", on_commit=self.ctl.set_gain,
                             tip=self.ctl.set_gain,
                             width=4)
        self.gain.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.suppress = self._sv(kb, "G_CurrentSuppressConst",
                                 on_commit=self.ctl.set_suppress_const, width=8,
                                 tip=self.ctl.set_suppress_const)
        self.suppress.grid(row=2, column=2, sticky="e", pady=(6, 0))
        kb.columnconfigure(2, weight=1)

        # -- Actuator Controls -----------------------------------------
        ab = groupbox(self, "Actuator Controls")
        ab.grid(row=row, column=0, sticky="ew", pady=3)
        row += 1
        self.step_size = self._sv(ab, "G_ActuatorStepSize", width=5)
        self.step_size.grid(row=0, column=0, sticky="w")
        self.counter = ValDisplay(ab, "", fmt="%d", width=6,
                                  tip="Igor: G_ActuatorCounter -- actuator steps "
                                      "taken by the last Start Approach")
        self.counter.set(self.state.opts.actuator_counter)
        self.counter.grid(row=0, column=1, sticky="w", padx=8)
        self.b_approach = button(ab, "Start\nApproach", self.ctl.approach,
                                 fg=SKY, width=9, tip=self.ctl.approach)
        self.b_approach.grid(row=0, column=2, rowspan=2, sticky="e", padx=4)
        self.b_act_closer = button(ab, "Step closer",
                                   lambda: self.ctl.step_actuator(True),
                                   font=FONT, tip=self.ctl.step_actuator)
        self.b_act_closer.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.b_act_apart = button(ab, "Step apart",
                                  lambda: self.ctl.step_actuator(False),
                                  font=FONT, tip=self.ctl.step_actuator)
        self.b_act_apart.grid(row=1, column=1, sticky="w", padx=8, pady=(6, 0))
        ab.columnconfigure(2, weight=1)

        # -- Piezo Controls --------------------------------------------
        pb = groupbox(self, "Piezo Controls")
        pb.grid(row=row, column=0, sticky="ew", pady=3)
        row += 1
        self.b_pz_closer = button(
            pb, "Step closer",
            lambda: self.ctl.piezo_step(+self.state.opts.piezo_step_nm),
            font=FONT, tip=self.ctl.piezo_step)
        self.b_pz_closer.grid(row=0, column=0, sticky="w")
        self.z_step = self._sv(pb, "G_PiezoDeltaZ_nm", width=5)
        self.z_step.grid(row=0, column=1, padx=8)
        self.b_pz_apart = button(
            pb, "Step apart",
            lambda: self.ctl.piezo_step(-self.state.opts.piezo_step_nm),
            font=FONT, tip=self.ctl.piezo_step)
        self.b_pz_apart.grid(row=0, column=2, sticky="e")
        L = self.state.cfg.limits
        self.slider = tk.Scale(pb, from_=L.piezo_ao_min_v, to=L.piezo_ao_max_v,
                               resolution=0.01, orient="horizontal",
                               length=320, tickinterval=(L.piezo_ao_max_v
                                                         - L.piezo_ao_min_v) / 5,
                               label="SliderPos_Z (piezo volts at the DAQ)",
                               font=("Arial", 9))
        self.slider.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self.slider.bind("<ButtonRelease-1>", self._slider_release)
        Tooltip(self.slider, tip_text(self.ctl.piezo_goto))
        pb.columnconfigure(2, weight=1)

        # -- Readouts --------------------------------------------------
        rb = ttk.Frame(self)
        rb.grid(row=row, column=0, sticky="ew", pady=(6, 3))
        row += 1
        self.ro_i = ValDisplay(rb, "I (uA)", fmt="%3.5f", width=9, bold=True)
        self.ro_i.pack(side="left")
        self.ro_v = ValDisplay(rb, "V (mV)", fmt="%3.2f", width=8, bold=True)
        self.ro_v.pack(side="left", padx=10)
        self.ro_pz = ValDisplay(rb, "Piezo", fmt="%3.2f", width=6, bold=True)
        self.ro_pz.pack(side="left")
        for w, v in ((self.ro_i, 0.0), (self.ro_v, 0.0), (self.ro_pz, 0.0)):
            w.set(v)

        # -- Saved / Tip Bias / Stop # / Start / Attempts / +1 ----------
        bb = ttk.Frame(self)
        bb.grid(row=row, column=0, sticky="ew", pady=3)
        row += 1
        self.saved = self._sv(bb, "G_PullOutNumber", width=7, font=FONT_BOLD)
        self.saved.grid(row=0, column=0, sticky="w")
        self.tip_bias = self._sv(bb, "G_TipBias", on_commit=self.ctl.set_tip_bias,
                                 tip=self.ctl.set_tip_bias,
                                 width=8, font=FONT_BOLD)
        self.tip_bias.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.stop_no = self._sv(bb, "G_StopNumber", width=7, font=FONT_BOLD)
        self.stop_no.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.b_start = button(bb, "Start\nMeasurement",
                              lambda: self.ctl.start_measurement(False),
                              fg=GREEN, font=FONT_BIG, width=12,
                              tip=self.ctl.start_measurement)
        self.b_start.grid(row=1, column=1, rowspan=2, sticky="e", pady=(6, 0))
        self.attempts = self._sv(bb, "G_PullOutAttempt", width=7,
                                 font=FONT_BOLD)
        self.attempts.grid(row=2, column=0, sticky="w", pady=(6, 0))
        side = ttk.Frame(bb)
        side.grid(row=1, column=2, rowspan=2, sticky="e", padx=(6, 0))
        self.b_stop = button(side, "Stop\n(Alt)", self.ctl.request_stop,
                             fg=RED, width=5, tip=self.ctl.request_stop)
        self.b_stop.pack(side="top")
        self.b_plus1 = button(side, "+1",
                              lambda: self.ctl.start_measurement(True),
                              fg=SKY, width=4, tip=self.ctl.start_measurement)
        self.b_plus1.pack(side="top", pady=(4, 0))
        bb.columnconfigure(1, weight=1)

        # -- status line, and the way to the code ------------------------
        sb = ttk.Frame(self)
        sb.grid(row=row, column=0, sticky="ew", pady=(4, 0))
        self.status = ttk.Label(sb, text="idle", font=("Arial", 10),
                                foreground="#444444", anchor="w")
        self.status.pack(side="left", fill="x", expand=True)
        self.b_code = button(sb, "Which code runs this?",
                             self.app.show_button_map, font=("Arial", 10),
                             tip="Opens the Button map: every control on the "
                                 "panels, the RigController method and the "
                                 "worker-thread _impl it runs (file:line), "
                                 "the Igor procedure it mirrors, and the "
                                 "stmlab functions it calls.\n\nAlso: hover "
                                 "any control for the same text, or "
                                 "right-click it to open the Inspector.")
        self.b_code.pack(side="right")
        row += 1
        self.hint = ttk.Label(
            self, text="Hover a control for its Python; right-click it "
                       "(macOS: Control-click) for the Inspector.",
            font=("Arial", 9), foreground="#8c3a10", anchor="w")
        self.hint.grid(row=row, column=0, sticky="ew")

    def _build_daq_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(tab, text="DAQ")
        left = ttk.Frame(tab)
        left.grid(row=0, column=0, sticky="nw")
        right = ttk.Frame(tab)
        right.grid(row=0, column=1, sticky="ne", padx=(12, 0))
        tab.columnconfigure(1, weight=1)

        self.zscale = ValDisplay(left, "Z piezo scale (nm/V)", fmt="%g", width=6)
        self.zscale.set(self.state.cfg.cal.piezo_nm_per_volt)
        self.zscale.pack(anchor="w", pady=1)
        self.sscale = ValDisplay(left, "Z Sense scale (nm/V)", fmt="%g", width=6)
        self.sscale.set(self.state.opts.sense_scale_nm_per_v)
        self.sscale.pack(anchor="w", pady=1)
        self.daq_setvars = [
            self._sv(left, "G_AcquisitionRate", width=8),
            self._sv(left, "G_WriteBufferSize", width=6),
            self._sv(left, "G_FastReadWaveSize", width=6),
            self._sv(left, "G_HighResOutputRange", width=5),
            self._sv(left, "G_PiezoOffset_nm", width=6),
        ]
        for w in self.daq_setvars:
            w.pack(anchor="w", pady=1)

        self.b_start_daq = button(right, "Start\nWriting", self.ctl.start_writing,
                                  fg=BLUE, width=10, tip=self.ctl.start_writing)
        self.b_start_daq.pack(pady=2)
        self.b_kill = button(right, "Kill\nTasks", self.ctl.kill_tasks,
                             fg=RED, width=10, tip=self.ctl.kill_tasks)
        self.b_kill.pack(pady=2)
        self.b_reset = button(right, "Reset DAQ\nDevices", self.ctl.reset_daq,
                              fg="#666666", width=10, tip=self.ctl.reset_daq)
        self.b_reset.pack(pady=2)

    def _build_inputs_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(tab, text="Inputs")
        left = ttk.Frame(tab)
        left.grid(row=0, column=0, sticky="nw")
        right = ttk.Frame(tab)
        right.grid(row=0, column=1, sticky="ne", padx=(12, 0))
        for igor in ("G_PullOutRate", "G_PseudoTotalLength_nm",
                     "G_ConductanceThreshold", "G_MakeContactApproachStepSize",
                     "G_SeriesResistance", "G_EndOfTraceNoiseThreshold"):
            self._sv(left, igor, width=8).pack(anchor="w", pady=1)
        for igor in ("G_BiasSaveCheck", "G_CurrentSaveCheck",
                     "G_PiezoWaveSaveCheck", "G_SenseSaveCheck",
                     "G_HistSaveCheck", "G_VoltageRead"):
            self._cb(right, igor).pack(anchor="w")
        for igor in ("G_SmashFrequency", "G_SmashInSteps", "G_SmashOutSteps"):
            self._sv(right, igor, width=6).pack(anchor="w", pady=1)

    def _build_options_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=4)
        self.tabs.add(tab, text="Options")
        sub = ttk.Notebook(tab)
        sub.pack(fill="both", expand=True)
        self.mode_boxes: dict[str, CheckBox] = {}

        def mode_toggle(name):
            def handler(on):
                self.state.opts.select_mode(name, on)
                for box in self.mode_boxes.values():
                    box.refresh()
            return handler

        # Push-Pull
        pp = ttk.Frame(sub, padding=6)
        sub.add(pp, text="Push-Pull")
        self.mode_boxes["push_pull"] = self._cb(pp, "G_PushPullCheck",
                                                mode_toggle("push_pull"))
        self.mode_boxes["push_pull"].grid(row=0, column=0, sticky="w")
        self._sv(pp, "G_NumPushPullCycles", width=4).grid(row=0, column=1,
                                                          sticky="w", padx=8)
        self._sv(pp, "G_InitialPullLength", width=6).grid(row=1, column=0,
                                                          sticky="w", pady=2)
        self._sv(pp, "G_FinalPullLength", width=6).grid(row=1, column=1,
                                                        sticky="w", padx=8)
        self._sv(pp, "G_PushPullLength", width=6).grid(row=2, column=0,
                                                       sticky="w", pady=2)
        self._sv(pp, "G_HoldLength", width=6).grid(row=2, column=1, sticky="w",
                                                   padx=8)

        # IV
        iv = ttk.Frame(sub, padding=6)
        sub.add(iv, text="IV")
        self.mode_boxes["iv"] = self._cb(iv, "G_IVCheck", mode_toggle("iv"))
        self.mode_boxes["iv"].grid(row=0, column=0, sticky="w")
        sign = ttk.Frame(iv)
        sign.grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(sign, text="Sign:", font=FONT).pack(side="left")
        self.iv_sign = ttk.Combobox(sign, values=["+ / -", "- / +"], width=5,
                                    state="readonly", font=FONT)
        self.iv_sign.pack(side="left")
        self.iv_sign.bind("<<ComboboxSelected>>", self._iv_sign_changed)
        self._refresh_iv_sign()
        self._sv(iv, "G_IVMaxBias", width=6).grid(row=0, column=2, sticky="w")
        self._sv(iv, "G_IVInitPull", width=6).grid(row=1, column=0, sticky="w",
                                                   pady=2)
        self._sv(iv, "G_IVFinPull", width=6).grid(row=1, column=1, columnspan=2,
                                                  sticky="w", padx=8)
        self._sv(iv, "G_IVCapLength", width=6).grid(row=2, column=0, sticky="w",
                                                    pady=2)
        self._sv(iv, "G_IVRampLength", width=6).grid(row=2, column=1,
                                                     columnspan=2, sticky="w",
                                                     padx=8)

        # AC
        ac = ttk.Frame(sub, padding=6)
        sub.add(ac, text="AC")
        self.mode_boxes["ac_hold"] = self._cb(ac, "G_ACHoldCheck",
                                              mode_toggle("ac_hold"))
        self.mode_boxes["ac_hold"].grid(row=0, column=0, sticky="w")
        self._sv(ac, "G_ACAmp", width=6).grid(row=1, column=0, sticky="w", pady=2)
        self._sv(ac, "G_ACFreq", width=6).grid(row=1, column=1, sticky="w",
                                               padx=8)
        self._sv(ac, "G_ACInitPullLength", width=6).grid(row=2, column=0,
                                                         sticky="w", pady=2)
        self._sv(ac, "G_ACHoldLength", width=6).grid(row=2, column=1, sticky="w",
                                                     padx=8)
        self._sv(ac, "G_ACFinPullLength", width=6).grid(row=3, column=0,
                                                        sticky="w", pady=2)

        # High bias hold
        hb = ttk.Frame(sub, padding=6)
        sub.add(hb, text="High bias hold")
        self.mode_boxes["hb_hold"] = self._cb(hb, "G_HBHoldCheck",
                                              mode_toggle("hb_hold"))
        self.mode_boxes["hb_hold"].grid(row=0, column=0, sticky="w")
        self._sv(hb, "G_HBBias", width=8).grid(row=1, column=0, sticky="w",
                                               pady=2)
        self._sv(hb, "G_HBInitPullLength", width=6).grid(row=2, column=0,
                                                         sticky="w", pady=2)
        self._sv(hb, "G_HBFinPullLength", width=6).grid(row=2, column=1,
                                                        sticky="w", padx=8)
        self._sv(hb, "G_HBHoldLength", width=6).grid(row=3, column=0,
                                                     sticky="w", pady=2)
        self._sv(hb, "G_HBCapLengthIN", width=8).grid(row=4, column=0,
                                                      sticky="w", pady=2)
        self._sv(hb, "G_HBCapLengthFIN", width=8).grid(row=4, column=1,
                                                       sticky="w", padx=8)

    # ------------------------------------------------------------------
    # Small handlers
    # ------------------------------------------------------------------

    def _iv_sign_changed(self, _event=None) -> None:
        # Igor IVSignPopup: item 1 -> G_IVSignFlag=0, item 2 -> 1
        self.state.cfg.iv.positive_first = self.iv_sign.current() == 1

    def _refresh_iv_sign(self) -> None:
        self.iv_sign.current(1 if self.state.cfg.iv.positive_first else 0)

    def _slider_release(self, _event=None) -> None:
        if self._slider_programmatic:
            return
        self.ctl.piezo_goto(float(self.slider.get()))

    def set_slider(self, volts: float) -> None:
        self._slider_programmatic = True
        try:
            self.slider.set(volts)
        finally:
            self._slider_programmatic = False

    def set_writing(self, on: bool) -> None:
        """StartHighResWritingTask / StopWritingTasks enable/disable lists."""
        set_enabled(self.b_start_daq, not on)
        set_enabled(self.b_reset, not on)
        set_enabled(self.b_kill, True)
        set_enabled(self.slider, on)
        for w in self.daq_setvars:
            set_enabled(w, not on)
        set_enabled(self.bkgd, on)
        if not on:
            self.bkgd.refresh()
            self.k_zero.refresh()

    def set_busy(self, name: str | None) -> None:
        busy = bool(name)
        self.status.configure(text=f"running: {name}" if busy else "idle")
        for w in (self.b_start, self.b_plus1, self.b_approach, self.b_find_sup,
                  self.b_start_daq, self.b_reset):
            set_enabled(w, not busy)
        if not busy:
            self.set_writing(self.ctl.rig is not None)

    def refresh_all(self) -> None:
        for w in self.refreshable:
            w.refresh()
        self._refresh_iv_sign()
        self.zscale.set(self.state.cfg.cal.piezo_nm_per_volt)
        self.counter.set(self.state.opts.actuator_counter)

    # ------------------------------------------------------------------
    # Events from the controller
    # ------------------------------------------------------------------

    def on_event(self, kind: str, payload) -> None:
        o = self.state.opts
        if kind == "readout":
            self.ro_i.set(payload["current_ua"])
            self.ro_v.set(payload["junction_mv"])
            self.ro_pz.set(payload["piezo_v"])
            if payload.get("beep") and o.bkgd_sampling:
                self.bell()
        elif kind == "piezo":
            self.ro_pz.set(payload["volts"])
            self.set_slider(payload["volts"])
        elif kind == "writing":
            self.set_writing(bool(payload))
        elif kind == "saved":
            self.saved.refresh()
        elif kind == "attempts":
            self.attempts.refresh()
        elif kind == "stop_number":
            self.stop_no.refresh()
        elif kind == "counter":
            self.counter.set(payload)
        elif kind == "gain":
            self.gain.refresh()
            self.suppress.refresh()
        elif kind == "bias":
            self.tip_bias.refresh()
        elif kind == "suppress":
            self.suppress.refresh()
        elif kind == "bkgd":
            self.bkgd.refresh()
        elif kind == "busy":
            self.set_busy(payload)
        elif kind == "idle":
            self.set_busy(None)
            self.saved.refresh()
            self.attempts.refresh()
            self.stop_no.refresh()
        elif kind == "config":
            self.refresh_all()


def _dark_text_needed() -> bool:
    """Pure lime on a light button is unreadable on most platforms."""
    return True
