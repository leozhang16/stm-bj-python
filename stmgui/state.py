"""Igor's globals, and where each one lives now.

Igor kept the whole experiment in ``root:`` globals (``Declare_STMBJ_Variables``,
Functions_STMBJ.ipf:5-198) and every panel control was bound to one of them
by name. Most of those globals already have a home in ``stmlab.config``; the
rest -- counters, checkbox states, display-only values -- have none, because
the command-line package never needed them. They live in :class:`GuiOptions`.

:data:`PARAMS` is the binding table: one row per panel control, naming the
Igor global, the attribute it maps to, its units and limits. The panels build
their Tk variables from this table, so adding a control is one line here and
one widget call in the panel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from stmlab.config import RigConfig

MODES = ("constant", "push_pull", "iv", "ac_hold", "hb_hold")


@dataclass
class GuiOptions:
    """Igor globals with no ``RigConfig`` home. Names follow the Igor ones."""

    # DAQ tab
    fast_read_wave_size: int = 200        # G_FastReadWaveSize
    piezo_offset_nm: float = 0.0          # G_PiezoOffset_nm (position after Start Writing)
    sense_scale_nm_per_v: float = 314.0   # K_SenseScale, display only

    # Piezo controls
    piezo_step_nm: float = 5.0            # G_PiezoDeltaZ_nm

    # Counters on the panel
    pull_out_number: int = 1              # G_PullOutNumber, "Saved"
    stop_number: int = 1001               # G_StopNumber, "Stop #"
    pull_out_attempt: int = 0             # G_PullOutAttempt, "Attempts"
    actuator_counter: int = 0             # G_ActuatorCounter

    # Inputs tab save flags. Raw volts are always stored; these are recorded
    # in the file header so an archived run says what Igor would have kept.
    save_bias: bool = False               # G_BiasSaveCheck
    save_current: bool = False            # G_CurrentSaveCheck
    save_hist: bool = True                # G_HistSaveCheck
    save_sense: bool = False              # G_SenseSaveCheck
    save_piezo_wave: bool = False         # G_PiezoWaveSaveCheck
    voltage_read: bool = False            # G_VoltageRead

    # Keithley checkboxes
    zero_check: bool = True               # ZeroCheckBox, C1X on start
    suppress_on: bool = False             # SuppressCheckBox, N0X on start

    # Ramp-mode checkboxes (mutually exclusive, RampOptionsCheckProc)
    push_pull_check: bool = False         # G_PushPullCheck
    iv_check: bool = False                # G_IVCheck
    ac_hold_check: bool = False           # G_ACHoldCheck
    hb_hold_check: bool = False           # G_HBHoldCheck

    # Voltage_Offset panel
    vzero_check: bool = False             # VzeroCheckBox
    vzero_mv: float = 0.0                 # G_Vzero (display)
    izero_ua: float = 0.0                 # G_Izero (display)

    # Background sampling
    bkgd_sampling: bool = False           # OnCheck
    beep_current_ua: float = 0.15         # BackgroundRead: beep above this

    # Live readouts (Igor's ValDisplays)
    current_readout_ua: float = 0.0       # G_CurrentSamplingReadoutVal
    junction_voltage_mv: float = 0.0      # G_JunctionVoltage
    piezo_readout_v: float = 0.0          # G_PiezoBiasSamplingReadoutVal

    # Where the session files go. Igor: DataDir + G_PathDate (MakePath).
    data_dir: str = "data"

    # stmlab addition: measure the preamp zero and the AI/AO group delay
    # once, right after Start Writing, while the tip is still retracted.
    # Igor had no equivalent; validate() warns when it has not been done.
    calibrate_on_start_writing: bool = True

    def mode(self) -> str:
        """Which CreateInputs branch the next Start Measurement takes."""
        if self.push_pull_check:
            return "push_pull"
        if self.iv_check:
            return "iv"
        if self.ac_hold_check:
            return "ac_hold"
        if self.hb_hold_check:
            return "hb_hold"
        return "constant"

    def select_mode(self, name: str, on: bool) -> None:
        """Igor's RampOptionsCheckProc: ticking one box clears the others."""
        for key in ("push_pull_check", "iv_check", "ac_hold_check",
                    "hb_hold_check"):
            setattr(self, key, False)
        if on and name != "constant":
            setattr(self, f"{name}_check", True)


@dataclass
class GuiState:
    """Everything the panels read and write: the config plus the options."""
    cfg: RigConfig = field(default_factory=RigConfig)
    opts: GuiOptions = field(default_factory=GuiOptions)


# --------------------------------------------------------------------------
# The binding table
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Param:
    """One panel control's binding.

    ``path`` is dotted from a :class:`GuiState` ("cfg.ramp.bias_v",
    "opts.stop_number"). ``scale`` converts internal -> displayed
    (``bias_v`` in volts is shown as mV, so scale is 1000).
    ``limits`` is Igor's ``limits={lo, hi, increment}``; increment 0 means a
    plain entry, otherwise a spinbox.
    """
    igor: str
    path: str
    kind: type
    title: str
    limits: tuple[float, float, float] = (float("-inf"), float("inf"), 0)
    fmt: str = "%g"
    scale: float = 1.0

    def get(self, state: GuiState) -> Any:
        obj: Any = state
        for part in self.path.split("."):
            obj = getattr(obj, part)
        if self.kind is bool:
            return bool(obj)
        if self.kind is int:
            return int(round(obj * self.scale))
        if self.kind is float:
            return float(obj) * self.scale
        return obj

    def set(self, state: GuiState, value: Any) -> Any:
        """Coerce, clamp to the Igor limits, store. Returns what was stored
        (in display units) so a widget can show the clamped value."""
        if self.kind is bool:
            stored: Any = bool(value)
        else:
            lo, hi, _ = self.limits
            v = self.kind(value)
            v = min(max(v, lo), hi)
            stored = v
            value = v
            v = v / self.scale
            if self.kind is int and self.scale == 1.0:
                v = int(v)
        parts = self.path.split(".")
        obj: Any = state
        for part in parts[:-1]:
            obj = getattr(obj, part)
        setattr(obj, parts[-1], stored if self.kind is bool else v)
        return stored


INF = float("inf")

PARAMS: dict[str, Param] = {p.igor: p for p in (
    # -- DAQ tab -------------------------------------------------------
    Param("G_AcquisitionRate", "cfg.ramp.sample_rate_hz", float,
          "Acquisition Rate", (100, 200000, 0), "%g"),
    Param("G_WriteBufferSize", "cfg.ramp.settle_samples", int,
          "Write Buffer Size", (25, 2000, 0), "%d"),
    Param("G_FastReadWaveSize", "opts.fast_read_wave_size", int,
          "Fast Read Wave Size", (25, 2000, 0), "%d"),
    Param("G_HighResOutputRange", "cfg.channels.bias_ao_range_v", float,
          "HighRes Output Range (V)", (0, 10, 0), "%g"),
    Param("K_ZPiezoScale", "cfg.cal.piezo_nm_per_volt", float,
          "Z piezo scale (nm/V)", fmt="%g"),
    Param("K_SenseScale", "opts.sense_scale_nm_per_v", float,
          "Z Sense scale (nm/V)", fmt="%g"),

    # -- Inputs tab ----------------------------------------------------
    Param("G_PullOutRate", "cfg.ramp.pull_rate_nm_per_s", float,
          "Pull Rate (nm/s)", (0, 1000, 0)),
    Param("G_PseudoTotalLength_nm", "cfg.ramp.pull_length_nm", float,
          "Excursion (nm)", (0.1, 500, 0)),
    Param("G_ConductanceThreshold", "cfg.ramp.engage_g0", float,
          "Contact Threshold (G0)", (0, 10000, 0)),
    Param("G_MakeContactApproachStepSize", "cfg.ramp.approach_step_nm", float,
          "Contact step size (nm)", (0, 50, 0)),
    Param("G_SeriesResistance", "cfg.keithley.series_resistance_ohm", float,
          "Series R (Ohm)"),
    Param("G_EndOfTraceNoiseThreshold", "cfg.ramp.break_g0", float,
          "Zero Cutoff (G0)", (0, 0.5, 0), "%g"),
    Param("G_SmashFrequency", "cfg.ramp.smash_every", int,
          "Smash Freq.", (0, INF, 0), "%d"),
    Param("G_SmashInSteps", "cfg.ramp.smash_in_nm", float, "Smash In"),
    Param("G_SmashOutSteps", "cfg.ramp.smash_out_nm", float, "Smash Out"),
    Param("G_BiasSaveCheck", "opts.save_bias", bool, "Save Bias"),
    Param("G_CurrentSaveCheck", "opts.save_current", bool, "Save Current"),
    Param("G_PiezoWaveSaveCheck", "opts.save_piezo_wave", bool,
          "Save Piezo Wave"),
    Param("G_SenseSaveCheck", "opts.save_sense", bool, "Save Sense"),
    Param("G_HistSaveCheck", "opts.save_hist", bool, "Save Hist"),
    Param("G_VoltageRead", "opts.voltage_read", bool, "VoltageRead"),

    # -- Options tab: Push-Pull ----------------------------------------
    Param("G_PushPullCheck", "opts.push_pull_check", bool, "Push-Pull"),
    Param("G_NumPushPullCycles", "cfg.push_pull.cycles", int,
          "Number of cycles", (1, INF, 1), "%d"),
    Param("G_InitialPullLength", "cfg.push_pull.initial_pull_nm", float,
          "Initial Pull (nm)"),
    Param("G_FinalPullLength", "cfg.push_pull.final_pull_nm", float,
          "Final Pull (nm)"),
    Param("G_PushPullLength", "cfg.push_pull.push_pull_nm", float,
          "Push-Pull length (nm)"),
    Param("G_HoldLength", "cfg.push_pull.hold_nm", float, "Hold length (nm)"),

    # -- Options tab: IV -----------------------------------------------
    Param("G_IVCheck", "opts.iv_check", bool, "IV"),
    Param("G_IVMaxBias", "cfg.iv.max_bias_v", float, "MaxBias (V)",
          fmt="%1.2f"),
    Param("G_IVSignFlag", "cfg.iv.positive_first", bool, "Sign:"),
    Param("G_IVInitPull", "cfg.iv.init_pull_nm", float, "Initial Pull (nm)",
          fmt="%3.1f"),
    Param("G_IVFinPull", "cfg.iv.final_pull_nm", float, "Final Pull (nm)",
          fmt="%3.1f"),
    Param("G_IVCapLength", "cfg.iv.cap_nm", float, "Cap length (nm)",
          fmt="%3.1f"),
    Param("G_IVRampLength", "cfg.iv.ramp_nm", float, "Ramp length (nm)",
          fmt="%3.1f"),

    # -- Options tab: AC -----------------------------------------------
    Param("G_ACHoldCheck", "opts.ac_hold_check", bool, "AC Hold"),
    Param("G_ACAmp", "cfg.ac_hold.amp_v", float, "Amp (V)", fmt="%1.2f"),
    Param("G_ACFreq", "cfg.ac_hold.freq_khz", float, "Freq (kHz)",
          fmt="%3.1f"),
    Param("G_ACInitPullLength", "cfg.ac_hold.init_pull_nm", float,
          "Initial Pull (nm)", fmt="%3.1f"),
    Param("G_ACHoldLength", "cfg.ac_hold.hold_nm", float, "Hold length (nm)",
          fmt="%3.1f"),
    Param("G_ACFinPullLength", "cfg.ac_hold.final_pull_nm", float,
          "Final Pull (nm)", fmt="%3.1f"),

    # -- Options tab: High bias hold -----------------------------------
    Param("G_HBHoldCheck", "opts.hb_hold_check", bool, "High Bias Hold"),
    Param("G_HBBias", "cfg.hb_hold.hold_bias_v", float, "Hold bias (V)",
          fmt="%1.5f"),
    Param("G_HBInitPullLength", "cfg.hb_hold.init_pull_nm", float,
          "Initial Pull (nm)", fmt="%3.2f"),
    Param("G_HBFinPullLength", "cfg.hb_hold.final_pull_nm", float,
          "Final Pull (nm)", fmt="%3.2f"),
    Param("G_HBHoldLength", "cfg.hb_hold.hold_nm", float, "Hold length (nm)",
          fmt="%3.2f"),
    Param("G_HBCapLengthIN", "cfg.hb_hold.cap_in_nm", float,
          "Cap Length IN (nm)", fmt="%3.5f"),
    Param("G_HBCapLengthFIN", "cfg.hb_hold.cap_fin_nm", float,
          "Cap Length FIN (nm)", fmt="%3.5f"),

    # -- Keithley controls ---------------------------------------------
    Param("G_CurrentVoltGain", "cfg.keithley.gain_exponent", int,
          "Gain ( log(V/A) )", (3, 10, 1), "%d"),
    Param("G_CurrentSuppressConst", "cfg.keithley.suppress_const", float,
          "Suppress I value", (-1000, 1000, 0), "%3.2f"),
    Param("G_KeithleyBiasEnabled", "cfg.keithley.enabled", bool, "Bias"),
    Param("ZeroCheckBox", "opts.zero_check", bool, "Zero Check"),
    Param("SuppressCheckBox", "opts.suppress_on", bool, "Suppress I"),

    # -- Actuator / piezo ----------------------------------------------
    Param("G_ActuatorStepSize", "cfg.actuator.step_size", int, "Step Size",
          (1, INF, 1), "%d"),
    Param("G_ActuatorCounter", "opts.actuator_counter", int, "", fmt="%d"),
    Param("G_PiezoDeltaZ_nm", "opts.piezo_step_nm", float, "Z (nm)",
          (0, 100, 1)),
    Param("G_PiezoOffset_nm", "opts.piezo_offset_nm", float,
          "Piezo offset (nm)", (0, 620, 0)),

    # -- Bottom of the panel -------------------------------------------
    Param("G_TipBias", "cfg.ramp.bias_v", float, "Tip Bias (mV)",
          (-5000, 5000, 0), "%3.1f", scale=1000.0),
    Param("G_PullOutNumber", "opts.pull_out_number", int, "Saved",
          (0, INF, 0), "%d"),
    Param("G_StopNumber", "opts.stop_number", int, "Stop #", (0, INF, 0),
          "%d"),
    Param("G_PullOutAttempt", "opts.pull_out_attempt", int, "Attempts",
          (0, INF, 0), "%d"),
    Param("OnCheck", "opts.bkgd_sampling", bool,
          "Background Sampling (Beep is ON)"),

    # -- Voltage_Offset panel ------------------------------------------
    Param("G_VoltageInterval", "cfg.vzero.interval_mv", float,
          "Tip Bias interval (mV)", (0.1, 1000, 0), "%3.1f"),
    Param("G_NumPoints", "cfg.vzero.n_points", int, "Number of points",
          (3, 1000, 1), "%d"),
    Param("G_Vzerofrequency", "cfg.vzero.every_n_traces", int,
          "Frequency (traces)", (1, 5000, 10), "%d"),
    Param("VzeroCheckBox", "opts.vzero_check", bool, "V0 check ON"),
    Param("G_Vzero", "opts.vzero_mv", float, "V0 (fit, mV)", fmt="%3.4f"),
    Param("G_Izero", "opts.izero_ua", float, "I0 (fit, uA)", fmt="%3.6f"),

    # -- EChem panel ---------------------------------------------------
    Param("G_CounterElectrodeBias", "cfg.echem.gate_mv", float,
          "Counter Electrode Bias (mV)"),
    Param("G_CVAcquisitionRate", "cfg.echem.cv_rate_hz", float,
          "CV Acquisition Rate (samps/s)", (50, 40000, 0), "%g"),
    Param("G_NumCVCycles", "cfg.echem.cycles", int, "Number of Cycles",
          (0, 1000, 1), "%d"),
    Param("G_ScanRate", "cfg.echem.scan_rate_mv_per_s", float,
          "Scan Rate (mV/s)", (0, 2000, 25)),
    Param("G_VoltagePeakOne", "cfg.echem.peak_one_v", float,
          "Voltage Peak 1 (V)", (-2.5, 0, 0.25)),
    Param("G_VoltagePeakTwo", "cfg.echem.peak_two_v", float,
          "Voltage Peak 2 (V)", (0, 2.5, 0.25)),

    # -- Readouts ------------------------------------------------------
    Param("G_CurrentSamplingReadoutVal", "opts.current_readout_ua", float,
          "I (uA)", fmt="%3.5f"),
    Param("G_JunctionVoltage", "opts.junction_voltage_mv", float, "V (mV)",
          fmt="%3.2f"),
    Param("G_PiezoBiasSamplingReadoutVal", "opts.piezo_readout_v", float,
          "Piezo", fmt="%3.2f"),
)}


def simulated_state() -> GuiState:
    """A GuiState wired for the simulator, like the snippets' sim_config."""
    state = GuiState()
    state.cfg.simulate = True
    state.cfg.channels.low_res_device = "Dev2"
    state.cfg.actuator.kind = "simulated"
    return state


Listener = Callable[[str, Any], None]
