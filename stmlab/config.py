"""Rig constants, split by lifecycle.

Four dataclasses, because the numbers in them have completely different
lifetimes:

    ChannelMap    which channel carries what -- changes when the rig changes
    SafetyLimits  hardware breaking points  -- set once, rarely touched
    RampConfig    trajectory and sampling   -- tuned per experiment
    Calibration   measured constants        -- re-measured every session

The whole ``RigConfig`` is written into every data file. A file whose gain you
cannot reconstruct six months later is not data.

Defaults are taken from the Igor procedures this package replaces, so that a
Python run and an archived Igor run are directly comparable:

    Setup1_STMBJ.ipf:25-34    K_G0, K_ZPiezoScale, channel names
    Functions_STMBJ.ipf:5-198 Declare_STMBJ_Variables

Rig note (differs from project-architecture.pdf): this rig runs a *single*
PXI-4461. The junction bias therefore comes from ``ao1`` on the same card
rather than from a second card, and there is no current-suppression output.
That matches the Igor code exactly.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, ClassVar

# 2e^2/h, the conductance quantum. Igor: K_G0 in Setup1_STMBJ.ipf:25.
G0_SIEMENS = 7.7480917346e-5


class ConfigError(Exception):
    """Raised by :func:`validate` for a configuration that must not be run."""


# --------------------------------------------------------------------------
# Channels
# --------------------------------------------------------------------------

# Accepted spellings of ChannelMap.sense_terminal, mapped to DAQmx's
# TerminalConfiguration names in daq.py.
SENSE_TERMINALS = {"default", "rse", "nrse", "diff"}


@dataclass
class ChannelMap:
    """Which physical channel carries what.

    The AI channels are added to the DAQmx task in the order given by
    :attr:`ai_channels`, and the returned array's rows follow that order.
    Voltage first, current second -- the same order as Igor's
    ``SetUpHRTaskID1`` (Functions_STMBJ.ipf:243).
    """

    device: str = "Dev1"

    ao_piezo: str = "ao0"    # Z-piezo command, via the piezo driver box
    ao_bias: str = "ao1"     # junction bias
    ai_voltage: str = "ai0"  # junction voltage
    ai_current: str = "ai1"  # current preamp output

    ai_range_v: float = 10.0
    # The bias AO channel's range. The piezo AO channel's range is taken from
    # SafetyLimits instead, so the channel the card enforces and the limit the
    # software enforces can never disagree. Igor did the same, passing
    # G_PiezoChanLow/High into MXCreateAOVoltageChan (Controls_STMBJ.ipf:152).
    bias_ao_range_v: float = 2.5   # Igor: G_HighResOutputRange

    # Set to None to skip the product-type check in verify_devices().
    expected_product_type: str | None = "PXI-4461"

    # Igor's second card ("dev2", the low-res card): piezo sense readback,
    # X piezo on ao0, EChem counter electrode on ao1 (Setup1_STMBJ.ipf:36-41).
    # None means "this rig has one card" and every feature needing it refuses
    # cleanly instead of guessing.
    low_res_device: str | None = None
    # Checked by verify_devices() when low_res_device is set; None skips it.
    low_res_expected_product_type: str | None = "PXIe-6361"

    # Piezo sense readback: the piezo driver box's monitor output, read on the
    # low-res card. Igor's SenseIn / POExtension. It is read in its own task
    # during every play, N samples at the same rate, started by the same
    # trigger as the other inputs, and travels beside the record as
    # ``Rig.last_sense_v``; it never enters the (2, n) record itself. None
    # means "no sense line" even on a two-card rig.
    ai_piezo_sense: str | None = "ai2"
    sense_ai_range_v: float = 10.0
    # How the sense input is wired: "default" (the card's default, DIFF on an
    # X-series card), "rse" (single-ended, shield to AI GND -- a BNC from a
    # box is usually this), "nrse" or "diff". A floating minus input reads a
    # slow drift that follows nothing; if the readback ignores the command,
    # try "rse" before suspecting the cable.
    sense_terminal: str = "default"

    # Row indices into the (2, n) arrays that cross the DAQ boundary. ClassVar
    # so they stay out of asdict() and therefore out of the data files: they
    # describe this code's array layout, not the rig.
    ROW_VOLTAGE: ClassVar[int] = 0
    ROW_CURRENT: ClassVar[int] = 1
    ROW_PIEZO: ClassVar[int] = 0
    ROW_BIAS: ClassVar[int] = 1

    def path(self, channel: str) -> str:
        return f"{self.device}/{channel}"

    @property
    def has_piezo_sense(self) -> bool:
        """True only on a two-card rig with a sense channel named."""
        return bool(self.low_res_device) and bool(self.ai_piezo_sense)

    @property
    def piezo_sense_path(self) -> str | None:
        """``dev2/ai2``, or None when this rig has no sense line."""
        if not self.has_piezo_sense:
            return None
        return f"{self.low_res_device}/{self.ai_piezo_sense}"

    @property
    def ai_channels(self) -> tuple[str, str]:
        return (self.path(self.ai_voltage), self.path(self.ai_current))

    @property
    def ao_channels(self) -> tuple[str, str]:
        return (self.path(self.ao_piezo), self.path(self.ao_bias))

    @property
    def ao_start_trigger(self) -> str:
        """Terminal the AI task triggers off. Derived, never hardcoded."""
        return f"/{self.device}/ao/StartTrigger"


# --------------------------------------------------------------------------
# Safety
# --------------------------------------------------------------------------

@dataclass
class SafetyLimits:
    """Values beyond which something breaks -- not values you intend to use.

    All piezo limits are expressed **at the DAQ output**, before the piezo
    driver box. That is deliberate: this rig's displacement calibration
    (``Calibration.piezo_nm_per_volt``) is also DAQ-side and already folds in
    whatever gain the box applies, so the two agree without anyone needing to
    know the box's gain. See ``Calibration.hv_amp_gain``.

    This piezo is **unipolar, 0 to 10 V**. Igor's own defaults
    (G_PiezoChanLow/High = -10/+10, Functions_STMBJ.ipf:1294) were written for
    a bipolar piezo and would drive this one 10 V the wrong way; Igor flagged
    the distinction at Functions_STMBJ.ipf:44, where G_PiezoOffset_nm "MUST BE
    LARGER THAN EXCURSION SIZE when used with unipolar piezos".

    Two consequences follow from unipolar, and both are load-bearing:

    * 0 V is fully retracted, so parking every output at zero -- which is what
      the card does by itself whenever a task is not running -- is the safe
      state rather than a mid-range one.
    * A pull ramp descends. It can only start from a piezo position at least
      ``pull_length_nm`` above the floor, or the ramp clips and the trace is
      silently truncated. :func:`validate` and ``trace.build_ramp`` both check.
    """

    piezo_ao_min_v: float = 0.0
    piezo_ao_max_v: float = 10.0

    # Hard refusal, not a clamp. Igor's tip bias is 100 mV; its rungo() sweep
    # reaches 1.1 V, so raise this deliberately if you need that.
    bias_max_v: float = 0.5

    # Above this the preamp output is railed and the reading is meaningless.
    preamp_saturation_v: float = 9.5

    # Approach runaway protection.
    max_coarse_steps: int = 2000

    # THE interlock. A coarse step advances further than the piezo's whole
    # range; taking one while the piezo is extended drives the tip into the
    # sample. Extension is the +ve direction here (approach steps are +0.5 nm,
    # the pull ramp descends), so "retracted" means at or below this value.
    # 0.1 V is 6.2 nm of residual extension.
    coarse_step_max_piezo_v: float = 0.1


# --------------------------------------------------------------------------
# Ramp
# --------------------------------------------------------------------------

@dataclass
class RampConfig:
    """Trajectory and sampling. Igor's Declare_STMBJ_Variables defaults."""

    sample_rate_hz: float = 40_000.0        # G_AcquisitionRate

    pull_length_nm: float = 5.0             # G_PseudoTotalLength_nm
    pull_rate_nm_per_s: float = 20.0        # G_PullOutRate
    bias_v: float = 0.100                   # G_TipBias, 100 mV

    # Igor used 5 G0 (G_ConductanceThreshold). Through the 106 kohm series
    # resistor that is reachable: 0.92 V at the amplifier with 2.4 mV left
    # across the junction (see amplifier_volts / junction_volts below).
    # Without the resistor it would need 38.7 V and could never be seen.
    # 0.5 G0 is a shallower contact, 0.76 V and 20 mV across the junction;
    # whether to go back to Igor's 5 is a physics choice (how deep a
    # contact each pull starts from), not a range problem. A railed
    # amplifier counts as contact as well, where the amplifier can rail.
    engage_g0: float = 0.5                  # G_ConductanceThreshold
    break_g0: float = 5e-4                  # G_EndOfTraceNoiseThreshold
    approach_step_nm: float = 0.5           # G_MakeContactApproachStepSize
    retract_step_nm: float = 5.0            # magnitude; applied negative

    # Samples played (and captured) for one DC move during approach. Igor
    # wrote 1000 samples per WriteToHighRes call (G_WriteBufferSize) and
    # averaged 200 (G_FastReadWaveSize).
    settle_samples: int = 1000
    settle_discard: int = 800               # average only the tail

    # Constant-value padding either side of the pull. The leading pad lets the
    # 4461's decimation filter settle before the region of interest, and the
    # trailing pad keeps the alignment spike inside the captured record.
    pre_pad_samples: int = 400
    post_pad_samples: int = 400

    # Alignment spike, written on the bias channel and read back on ai0. Igor
    # placed it 7.5 ms to 2.5 ms before the end of the ramp
    # (Functions_STMBJ.ipf:1618-1631).
    spike_front_ms: float = 7.5
    spike_back_ms: float = 2.5

    # Tip conditioning. Igor's SmashFun, Functions_STMBJ.ipf:1375.
    smash_every: int = 50                   # 0 disables
    smash_in_nm: float = 30.0
    smash_out_nm: float = -40.0

    traces_target: int = 1000               # G_StopNumber - G_PullOutNumber
    max_attempts: int = 100_000

    # Where the fine piezo sits when idle between attempts, in volts at the
    # DAQ. 0 V is fully retracted on this unipolar piezo, which is also where
    # the card parks itself, so the idle state needs no maintenance.
    piezo_park_v: float = 0.0

    # A pull that would descend below this many volts above the floor is
    # refused rather than clipped. Igor's equivalent was the instruction to
    # keep G_PiezoOffset_nm larger than the excursion (Functions_STMBJ.ipf:44).
    piezo_headroom_v: float = 0.02

    @property
    def n_pull_samples(self) -> int:
        """Points in the pull proper. Igor: G_NumPtsInAppliedWaves."""
        return int(round(self.pull_length_nm / self.pull_rate_nm_per_s
                         * self.sample_rate_hz))

    @property
    def n_record_samples(self) -> int:
        return (self.pre_pad_samples + self.n_pull_samples
                + self.post_pad_samples)

    @property
    def seconds_per_pull(self) -> float:
        return self.pull_length_nm / self.pull_rate_nm_per_s


# --------------------------------------------------------------------------
# Calibration
# --------------------------------------------------------------------------

@dataclass
class Calibration:
    """Measured constants. Produced by ``calibrate.py``, saved per session."""

    # Transimpedance of the current preamp. Igor stored this as an exponent,
    # G_CurrentVoltGain = 6, and multiplied readings by 10**-6.
    preamp_gain_v_per_a: float = 1e6

    # Resting offset of the preamp. Hundreds of microvolts, drifts with
    # temperature, must be re-measured every session.
    current_zero_v: float = 0.0

    # Displacement per volt **at the DAQ output**. Igor: K_ZPiezoScale = 62.
    # This is an end-to-end number: it already includes the gain of the piezo
    # driver box, so hv_amp_gain below is documentation, not arithmetic.
    piezo_nm_per_volt: float = 62.0

    # Gain of the piezo driver box, if you ever measure it (piezo
    # disconnected). None means "unknown, folded into piezo_nm_per_volt".
    # Nothing in this package multiplies by it.
    hv_amp_gain: float | None = None

    # Displacement per volt on the piezo *sense* line (the driver box's
    # monitor output, read on the low-res card). Igor: K_SenseScale = 314.
    # Only used to turn the readback into nm for display and storage; the
    # displacement axis of every trace stays the commanded one.
    # nm = (sense_v - sense_zero_v) * sense_nm_per_volt. Both numbers come
    # from rigtests/01_piezo_sweep.py: the readback against the command is a
    # straight line, and the line need not pass through 0 V.
    sense_nm_per_volt: float = 314.0
    sense_zero_v: float = 0.0           # what the sense line reads at 0 V command

    # Igor writes -(TipBias/1000) to ao1 and negates ai0 to recover the
    # junction voltage (Functions_STMBJ.ipf:347, 358).
    bias_output_sign: float = -1.0
    voltage_input_sign: float = -1.0

    # From the DC loopback sweep. Identity until measured.
    ai_gain_error: float = 1.0
    ai_offset_v: float = 0.0

    # Filled in at run time by the driver; the granted rate is not always the
    # requested one on a delta-sigma card, and every time axis must use it.
    granted_sample_rate_hz: float | None = None

    # Fixed AI/AO group delay in samples, if you have measured it. Left None,
    # each trace recovers its own delay from the alignment spike.
    group_delay_samples: int | None = None

    def volts_to_amps(self, v: float | Any) -> Any:
        """Preamp output volts -> junction current in amps."""
        return (v - self.current_zero_v) / self.preamp_gain_v_per_a

    def volts_to_g0(self, v: float | Any, bias_v: float | Any) -> Any:
        """Preamp output volts -> conductance in units of G0."""
        return self.volts_to_amps(v) / (bias_v * G0_SIEMENS)

    def g0_to_volts(self, g0: float, bias_v: float) -> float:
        """Inverse. Used by the validator to catch clipping before acquiring."""
        return g0 * G0_SIEMENS * bias_v * self.preamp_gain_v_per_a

    def nm_to_piezo_volts(self, nm: float | Any) -> Any:
        return nm / self.piezo_nm_per_volt

    def piezo_volts_to_nm(self, v: float | Any) -> Any:
        return v * self.piezo_nm_per_volt

    def sense_volts_to_nm(self, v: float | Any) -> Any:
        """Piezo sense readback volts -> nm (Igor: SenseIn * K_SenseScale),
        after removing what the line reads with the piezo parked."""
        return (v - self.sense_zero_v) * self.sense_nm_per_volt


# --------------------------------------------------------------------------
# Coarse approach
# --------------------------------------------------------------------------

@dataclass
class ActuatorConfig:
    """Coarse approach actuator.

    Igor drove a Newport NanoPZ over a serial port with ``0MO`` (motor on)
    then ``0PR<n>`` (relative move) -- NanoPZ_Actuator_Functions_STM.ipf:6-23.
    ``project-architecture.pdf`` put coarse approach on the 6361's digital
    port, which this single-card rig does not have, so serial is the only
    route available.

    kind: "none" (approach by hand), "nanopz" (serial), or "simulated".
    """

    kind: str = "none"
    port: str = "COM1"
    baud: int = 19200
    step_size: int = 5           # G_ActuatorStepSize
    settle_s: float = 0.10
    # Current above which the coarse approach stops, in microamps. Igor used
    # 0.1 uA on G_CurrentSamplingReadoutVal (Functions_STMBJ.ipf:1780).
    stop_current_ua: float = 0.1


# --------------------------------------------------------------------------
# Ramp modes beyond constant bias. Igor: CreateInputs' four GUI-selected
# branches (Functions_STMBJ.ipf:1461-1599) and their G_* globals (:91-123).
# Lengths are nanometres *at the pull rate*, Igor's parameterisation: a
# 3 nm "hold" lasts as long as pulling 3 nm would.
# --------------------------------------------------------------------------

@dataclass
class PushPullConfig:
    """Igor's PushPull branch. Igor declared these globals with no defaults
    (set from the GUI, Functions_STMBJ.ipf:91-96); these are working values,
    not Igor's."""
    # THE CONSTRAINT: push_pull_nm must EXCEED initial_pull_nm, or the push
    # never gets back to the contact point and the junction is never
    # re-formed -- every cycle sits in tunnelling and the experiment
    # measures nothing. The trajectory pulls initial_pull_nm away, then each
    # cycle pushes push_pull_nm back toward the surface; the net position at
    # hold_in is (push_pull_nm - initial_pull_nm) relative to contact.
    # validate() warns when this is violated.
    initial_pull_nm: float = 1.0    # G_InitialPullLength
    push_pull_nm: float = 1.5       # G_PushPullLength -> hold_in at +0.5 nm
    hold_nm: float = 1.0            # G_HoldLength
    final_pull_nm: float = 4.0      # G_FinalPullLength
    cycles: int = 2                 # G_NumPushPullCycles


@dataclass
class IVConfig:
    """Igor's IV branch defaults, Functions_STMBJ.ipf:99-105."""
    init_pull_nm: float = 3.0       # G_IVInitPull
    final_pull_nm: float = 4.0      # G_IVFinPull
    cap_nm: float = 0.5             # G_IVCapLength, either side of the sweep
    ramp_nm: float = 2.0            # G_IVRampLength, the sweep window
    max_bias_v: float = 1.0         # G_IVMaxBias
    # G_IVSignFlag, Igor line 1535. NAMED FOR WHAT IT DOES, not for the
    # flag's Igor name: because Igor negates the whole bias wave first
    # (line 1533), leaving this False sweeps to the NEGATIVE apex first.
    # Setting it True negates the ramp segment a second time, so the
    # sweep goes positive first.
    positive_first: bool = False    # G_IVSignFlag


@dataclass
class ACHoldConfig:
    """Igor's AC-hold branch defaults, Functions_STMBJ.ipf:108-114."""
    init_pull_nm: float = 3.0       # G_ACInitPullLength
    final_pull_nm: float = 4.0      # G_ACFinPullLength
    hold_nm: float = 3.0            # G_ACHoldLength
    cap_nm: float = 0.5             # G_ACCapLength
    amp_v: float = 0.8              # G_ACAmp
    freq_khz: float = 10.0          # G_ACFreq, in kHz as Igor's was


@dataclass
class HBHoldConfig:
    """Igor's high-bias-hold branch defaults, Functions_STMBJ.ipf:117-123."""
    init_pull_nm: float = 3.0       # G_HBInitPullLength
    final_pull_nm: float = 4.0      # G_HBFinPullLength
    hold_nm: float = 3.0            # G_HBHoldLength
    cap_in_nm: float = 0.1          # G_HBCapLengthIN
    cap_fin_nm: float = 0.1         # G_HBCapLengthFIN
    hold_bias_v: float = 0.8        # G_HBBias, in volts


@dataclass
class VzeroConfig:
    """The Voltage_Offset workflow: find the applied bias that nulls the
    current. Igor: OffsetVoltage/SaveOffset, Functions_STMBJ.ipf:920-1041."""
    interval_mv: float = 5.0        # G_VoltageInterval, sweep is +/- this
    n_points: int = 5               # G_NumPoints, per polarity (2N total)
    every_n_traces: int = 50        # G_VzeroFrequency
    settle_s: float = 0.05          # Igor: Sleep/T 3 (3 ticks = 50 ms)


@dataclass
class KeithleyConfig:
    """Keithley 428 current amplifier over GPIB.
    Igor: SetUpGPIB_Keithley.ipf (address 22) and SetGain/SetCurrentSuppress
    in Controls_STMBJ.ipf:290-311, 460-477."""
    resource: str = "GPIB0::22::INSTR"
    gain_exponent: int = 6              # G_CurrentVoltGain, log10(V/A)
    suppress_const: float = 0.0         # G_CurrentSuppressConst
    series_resistance_ohm: float = 106130.0   # G_SeriesResistance
    enabled: bool = False               # G_KeithleyBiasEnabled started 0


@dataclass
class EChemConfig:
    """Electrochemistry: counter-electrode gate and cyclic voltammetry.
    Igor: EChem_Module.ipf. The counter electrode lived on the low-res
    card's ao1 (Setup1_STMBJ.ipf:11); the high-res CV drove the junction
    bias channel (dev1/ao1) instead."""
    counter_electrode_channel: str = "ao1"   # on channels.low_res_device
    gate_mv: float = 0.0                     # G_CounterElectrodeBias
    cv_rate_hz: float = 1000.0               # G_CVAcquisitionRate
    scan_rate_mv_per_s: float = 100.0        # G_ScanRate
    peak_one_v: float = -1.0                 # G_VoltagePeakOne
    peak_two_v: float = 1.0                  # G_VoltagePeakTwo
    cycles: int = 1                          # G_NumCVCycles


@dataclass
class XPiezoConfig:
    """Lateral X piezo on the low-res card's ao0, for monolayer experiments.
    Igor: SetupXPiezo/MoveXPiezo, NanoPZ_Actuator_Functions_STM.ipf:25-100."""
    channel: str = "ao0"                     # on channels.low_res_device
    nm_per_volt: float = 522.0               # K_XPiezoScale
    min_v: float = 0.0
    max_v: float = 10.0


# --------------------------------------------------------------------------
# Top level
# --------------------------------------------------------------------------

@dataclass
class RigConfig:
    channels: ChannelMap = field(default_factory=ChannelMap)
    limits: SafetyLimits = field(default_factory=SafetyLimits)
    ramp: RampConfig = field(default_factory=RampConfig)
    cal: Calibration = field(default_factory=Calibration)
    actuator: ActuatorConfig = field(default_factory=ActuatorConfig)

    # Mode and support configs. Present on every RigConfig so they travel in
    # every data file, but only the experiment that uses one reads it.
    push_pull: PushPullConfig = field(default_factory=PushPullConfig)
    iv: IVConfig = field(default_factory=IVConfig)
    ac_hold: ACHoldConfig = field(default_factory=ACHoldConfig)
    hb_hold: HBHoldConfig = field(default_factory=HBHoldConfig)
    vzero: VzeroConfig = field(default_factory=VzeroConfig)
    keithley: KeithleyConfig = field(default_factory=KeithleyConfig)
    echem: EChemConfig = field(default_factory=EChemConfig)
    xpiezo: XPiezoConfig = field(default_factory=XPiezoConfig)

    simulate: bool = False
    notes: str = ""

    # -- serialisation ----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RigConfig":
        """Rebuild from ``to_dict`` output, ignoring keys we no longer know.

        Tolerating unknown keys matters: files written by an older version of
        this package must still open, because re-analysis with a corrected
        calibration is the whole reason raw volts are stored.
        """
        def build(klass, blob):
            init_names = {f.name for f in fields(klass) if f.init}
            unknown = set(blob) - init_names
            if unknown:
                _log_unknown(klass.__name__, unknown)
            return klass(**{k: v for k, v in blob.items() if k in init_names})

        kwargs: dict[str, Any] = {}
        for name, klass in (("channels", ChannelMap), ("limits", SafetyLimits),
                            ("ramp", RampConfig), ("cal", Calibration),
                            ("actuator", ActuatorConfig),
                            ("push_pull", PushPullConfig), ("iv", IVConfig),
                            ("ac_hold", ACHoldConfig), ("hb_hold", HBHoldConfig),
                            ("vzero", VzeroConfig), ("keithley", KeithleyConfig),
                            ("echem", EChemConfig), ("xpiezo", XPiezoConfig)):
            if name in data:
                kwargs[name] = build(klass, data[name])
        for scalar in ("simulate", "notes"):
            if scalar in data:
                kwargs[scalar] = data[scalar]
        return cls(**kwargs)

    @classmethod
    def from_json(cls, path: str | Path) -> "RigConfig":
        return cls.from_dict(json.loads(Path(path).read_text()))


def _log_unknown(klass_name: str, keys: set[str]) -> None:
    import logging
    logging.getLogger(__name__).warning(
        "ignoring unknown %s keys in config: %s",
        klass_name, ", ".join(sorted(keys)))


# --------------------------------------------------------------------------
# The current path: bias source, series resistor, junction, amplifier
# --------------------------------------------------------------------------
#
# The bias is applied through ``keithley.series_resistance_ohm`` (Igor's
# G_SeriesResistance, 106 kohm on this rig), so the current a junction of
# conductance G draws is
#
#     I = V_bias / (R_series + 1/G)
#
# and the voltage left across the junction is V_bias / (1 + G R_series). The
# conductance arithmetic never needs this: it divides the current by the
# junction voltage *measured* on ai0, so the drop is in the data. But every
# estimate of "what will the amplifier read at X G0" does, and without it the
# validator believes 1 G0 is 7.75 V at the amplifier when it is 0.84 V, and
# refuses biases and thresholds that are perfectly usable. Set the resistance
# to 0 for a rig without the resistor.

def amplifier_volts(cfg: RigConfig, g0: float) -> float:
    """Amplifier output, in volts, for a junction of ``g0`` at the config's
    bias, series resistor included (the zero not added)."""
    g = g0 * G0_SIEMENS
    rs = max(0.0, cfg.keithley.series_resistance_ohm)
    current = cfg.ramp.bias_v * g / (1.0 + g * rs)
    return cfg.cal.preamp_gain_v_per_a * current


def junction_volts(cfg: RigConfig, g0: float) -> float:
    """Voltage left across a junction of ``g0`` once the series resistor has
    taken its share of the bias."""
    g = g0 * G0_SIEMENS
    rs = max(0.0, cfg.keithley.series_resistance_ohm)
    return cfg.ramp.bias_v / (1.0 + g * rs)


def conductance_at_amplifier_volts(cfg: RigConfig, v: float) -> float:
    """The junction conductance, in G0, that puts ``v`` volts out of the
    amplifier; inf when no junction can, because the series resistor caps the
    current at bias / R_series."""
    current = v / cfg.cal.preamp_gain_v_per_a
    rs = max(0.0, cfg.keithley.series_resistance_ohm)
    left = cfg.ramp.bias_v - current * rs
    if left <= 0:
        return float("inf")
    return current / left / G0_SIEMENS


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def validate(cfg: RigConfig) -> list[str]:
    """Check a config. Returns warnings; raises ConfigError on the fatal ones.

    The point of this function is to catch, before any hardware is touched,
    the class of mistake that otherwise survives to become a histogram with a
    missing gold peak that gets blamed on chemistry.
    """
    problems: list[str] = []
    warnings: list[str] = []

    C, R, L, M = cfg.cal, cfg.ramp, cfg.limits, cfg.channels

    # THE range check: does 1 G0 fit in the AI range? With a series resistor
    # the current is capped at bias / R_series whatever the junction does, so
    # on this rig (106 kohm) 1 G0 is 0.84 V at the amplifier, not 7.75 V, and
    # nothing clips at 100 mV; the check matters again at high gain or bias,
    # or on a rig with no resistor.
    v_at_1g0 = amplifier_volts(cfg, 1.0)
    g_at_range = conductance_at_amplifier_volts(cfg, M.ai_range_v)
    if v_at_1g0 > M.ai_range_v:
        problems.append(
            f"1 G0 produces {v_at_1g0:.3f} V but the AI range is "
            f"+/-{M.ai_range_v} V -- everything above "
            f"{g_at_range:.3g} G0 will CLIP. "
            f"Reduce preamp gain, reduce bias, or widen the range.")
    elif v_at_1g0 > L.preamp_saturation_v:
        warnings.append(
            f"1 G0 produces {v_at_1g0:.3f} V, above the preamp saturation "
            f"limit of {L.preamp_saturation_v} V: the metallic-contact region "
            f"of every trace will read railed. Usually acceptable -- the "
            f"science is in the retraction below 1 G0 -- but the engage "
            f"threshold cannot be trusted above that point.")

    # Is the engage threshold reachable before the preamp rails? Without a
    # series resistor an engage threshold above the saturation point makes
    # the approach loop run the piezo to its ceiling and give up, with no
    # indication of why. With the resistor the amplifier may never rail at
    # all; then the question is whether enough voltage is left across the
    # junction at the threshold for ai0 to judge it.
    v_at_engage = amplifier_volts(cfg, R.engage_g0)
    v_saturation = min(L.preamp_saturation_v, M.ai_range_v)
    g_saturation = conductance_at_amplifier_volts(cfg, v_saturation)
    if v_at_engage > v_saturation:
        warnings.append(
            f"engage threshold {R.engage_g0:g} G0 needs {v_at_engage:.1f} V "
            f"at the ADC but the input saturates at {v_saturation:.1f} V "
            f"({g_saturation:.2f} G0). Contact will "
            f"only ever be detected by saturation, never by the threshold. "
            f"Lower engage_g0 below {g_saturation:.2f}"
            f" or reduce the preamp gain.")
    vj_engage = junction_volts(cfg, R.engage_g0)
    if vj_engage < 1e-3:
        warnings.append(
            f"at the engage threshold of {R.engage_g0:g} G0 the series "
            f"resistor ({cfg.keithley.series_resistance_ohm:.0f} ohm) leaves "
            f"only {vj_engage * 1e3:.2f} mV across the junction; contact is "
            f"judged on that voltage, so ai0's noise matters. Lower "
            f"engage_g0, or raise the bias.")

    # Can the break threshold be told apart from the noise floor?
    v_at_break = amplifier_volts(cfg, R.break_g0)
    if v_at_break < 5e-6:
        warnings.append(
            f"break threshold {R.break_g0:g} G0 is only {v_at_break * 1e6:.2f}"
            f" uV at the ADC, comparable to the card's noise floor. Traces "
            f"may be judged 'broken' by noise alone.")

    # Bias against its own limit.
    if abs(R.bias_v) > L.bias_max_v:
        problems.append(
            f"bias {R.bias_v:+.3f} V exceeds the limit "
            f"+/-{L.bias_max_v} V")
    if R.bias_v == 0:
        problems.append("bias is 0 V: conductance would divide by zero")

    # Engage threshold must be reachable and above the break threshold.
    if R.engage_g0 <= R.break_g0:
        problems.append(
            f"engage_g0 ({R.engage_g0:g}) must be above break_g0 "
            f"({R.break_g0:g})")

    # Piezo range vs. the pull it is being asked to make.
    pull_v = C.nm_to_piezo_volts(R.pull_length_nm)
    span_v = L.piezo_ao_max_v - L.piezo_ao_min_v
    if pull_v > span_v:
        problems.append(
            f"a {R.pull_length_nm} nm pull needs {pull_v:.3f} V but the piezo "
            f"range is only {span_v:.3f} V wide")

    if L.piezo_ao_min_v >= L.piezo_ao_max_v:
        problems.append("piezo_ao_min_v must be below piezo_ao_max_v")

    if not (L.piezo_ao_min_v <= R.piezo_park_v <= L.piezo_ao_max_v):
        problems.append(
            f"piezo_park_v ({R.piezo_park_v} V) is outside the piezo range "
            f"[{L.piezo_ao_min_v}, {L.piezo_ao_max_v}] V")

    # Unipolar-specific: a descending ramp needs room beneath the contact
    # point. Contact is found wherever it is found, so this is only a sanity
    # check on the geometry; trace.build_ramp enforces it per attempt.
    usable = L.piezo_ao_max_v - (L.piezo_ao_min_v + R.piezo_headroom_v)
    if pull_v > usable:
        problems.append(
            f"a {R.pull_length_nm} nm pull ({pull_v:.3f} V) leaves no room "
            f"above the {L.piezo_ao_min_v} V floor once "
            f"{R.piezo_headroom_v} V of headroom is reserved")
    elif pull_v > 0.5 * usable:
        warnings.append(
            f"a {R.pull_length_nm} nm pull uses {pull_v / usable:.0%} of the "
            f"usable piezo range, so contact must be made in the upper part "
            f"of the range or attempts will be refused for lack of headroom")

    # The amplifier's programmed gain and the gain the arithmetic uses are
    # two separate numbers that must describe the same box. Nothing else
    # connects them: keithley.set_gain() programs the 428, while every
    # conductance divides by cal.preamp_gain_v_per_a.
    K = cfg.keithley
    programmed = 10.0 ** K.gain_exponent
    if abs(programmed - C.preamp_gain_v_per_a) > 1e-6 * programmed:
        warnings.append(
            f"keithley.gain_exponent = {K.gain_exponent} programs the "
            f"amplifier for {programmed:.3g} V/A, but "
            f"cal.preamp_gain_v_per_a is {C.preamp_gain_v_per_a:.3g} V/A. "
            f"Every conductance would be scaled by "
            f"{programmed / C.preamp_gain_v_per_a:.3g} -- "
            f"{abs(math.log10(programmed / C.preamp_gain_v_per_a)):.3f} decades "
            f"of error in the histogram.")

    # Push-pull only means anything if the push reaches back into contact.
    P = cfg.push_pull
    if P.push_pull_nm <= P.initial_pull_nm:
        warnings.append(
            f"push-pull: push_pull_nm ({P.push_pull_nm} nm) does not exceed "
            f"initial_pull_nm ({P.initial_pull_nm} nm), so every cycle holds "
            f"{P.initial_pull_nm - P.push_pull_nm:.2f} nm BELOW the contact "
            f"point and the junction is never re-formed. Experiment 02 would "
            f"record tunnelling for every cycle.")

    if not (L.piezo_ao_min_v <= L.coarse_step_max_piezo_v <= L.piezo_ao_max_v):
        problems.append(
            "coarse_step_max_piezo_v is outside the piezo range, so the "
            "coarse-step interlock can never be satisfied (or never fires)")

    # Piezo sense readback: only checked on a two-card rig that reads it.
    if M.has_piezo_sense:
        if C.sense_nm_per_volt <= 0:
            problems.append("cal.sense_nm_per_volt must be positive")
        if M.sense_ai_range_v <= 0:
            problems.append("channels.sense_ai_range_v must be positive")
        if M.sense_terminal.lower() not in SENSE_TERMINALS:
            problems.append(
                f"channels.sense_terminal must be one of "
                f"{sorted(SENSE_TERMINALS)}, not {M.sense_terminal!r}")

    # Sampling.
    if R.sample_rate_hz <= 0:
        problems.append("sample_rate_hz must be positive")
    if R.n_pull_samples < 100:
        problems.append(
            f"a {R.pull_length_nm} nm pull at {R.pull_rate_nm_per_s} nm/s "
            f"sampled at {R.sample_rate_hz:g} Hz is only {R.n_pull_samples} "
            f"points")

    spike_pts = int(round(R.spike_front_ms * 1e-3 * R.sample_rate_hz))
    if spike_pts >= R.n_pull_samples:
        problems.append(
            f"the {R.spike_front_ms} ms alignment spike does not fit inside a "
            f"{R.n_pull_samples}-point pull")

    if C.granted_sample_rate_hz is not None and \
            abs(C.granted_sample_rate_hz - R.sample_rate_hz) > 1e-6:
        warnings.append(
            f"requested {R.sample_rate_hz:g} Hz but the card granted "
            f"{C.granted_sample_rate_hz:g} Hz; every time axis uses the "
            f"granted value")

    if C.current_zero_v == 0.0:
        warnings.append(
            "current_zero_v is 0: the preamp zero has not been measured this "
            "session, so the tunnelling tail will sit on an uncorrected "
            "offset")

    if C.hv_amp_gain is None:
        warnings.append(
            "hv_amp_gain is unknown; piezo limits are enforced at the DAQ "
            "output only. That is correct as long as piezo_nm_per_volt "
            f"({C.piezo_nm_per_volt} nm/V) is an end-to-end measurement on "
            "this exact chain")

    if problems:
        raise ConfigError(
            "configuration is unsafe:\n  " + "\n  ".join(problems))

    return warnings
