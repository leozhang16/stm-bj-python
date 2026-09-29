"""Electrochemistry: the counter-electrode gate, and cyclic voltammetry.

Igor equivalents (EChem_Module.ipf):

    CounterElectrode        StartEChemWriting / WriteToCounterElectrode  :63, :88
    build_cv_ramp_highres   CVcurveHighRes's ramp construction           :106
    build_cv_ramp_lowres    CVcurveLowRes's ramp construction            :234
    run_cv                  the acquisition loop of both                 :178, :306

Two distinct things share this module because Igor kept them together:

**The gate.** In electrochemical gating a DC potential on the counter
electrode shifts the molecular levels relative to the tip and substrate.
Igor wrote it to the low-res card's ao1 in a +/-5 V channel, value entered
in millivolts (WriteToCounterElectrode divides by 1000). This voltage was
saved with every trace as ParameterWave[18] ("GateVoltage"); here it travels
inside the config (``echem.gate_mv``) in every data file.

**CV.** A cyclic voltammogram sweeps the electrode potential in a triangle
at fixed scan rate and records the current: capacitive charging plus
faradaic peaks where redox happens. Igor built the triangle from the two
peak potentials -- 0 to V1, back to 0, 0 to V2, back to 0 -- then repeated
the beginning of the sweep and NaN-ed the first quarter and the repeat, so
each saved cycle is a *steady-state* loop with the initial transient cut
off. That masking is reproduced here as a boolean ``keep`` array instead of
NaNs, so the raw record survives.

The high-res variant drives the *junction bias* channel (dev1/ao1) -- the
tip is the working electrode. The low-res variant drives the counter
electrode on the second card and prepends 5000 samples of 0 V. Both read
tip current on ai1 (and the high-res one reads the electrode voltage on
ai0).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from .config import EChemConfig, RigConfig

log = logging.getLogger(__name__)


class EChemError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------

class CounterElectrode:
    """DC gate on the low-res card's counter-electrode output."""

    def __init__(self, cfg: RigConfig):
        self.cfg = cfg
        self.gate_mv = 0.0
        self._task = None

    def on(self) -> "CounterElectrode":
        device = self.cfg.channels.low_res_device
        if device is None:
            raise EChemError(
                "no low-res device configured (channels.low_res_device is "
                "None); the counter electrode lives on the second card")
        import nidaqmx
        self._task = nidaqmx.Task("stmlab_gate")
        self._task.ao_channels.add_ao_voltage_chan(
            f"{device}/{self.cfg.echem.counter_electrode_channel}",
            min_val=-5.0, max_val=5.0)          # Igor: MXCreateAOVoltageChan(-5,5)
        self._write(0.0)
        return self

    def off(self, zero: bool = True) -> None:
        """Release the channel. ``zero=False`` leaves the last value standing
        (the card's AO holds after the task closes), which is how a one-shot
        CLI call can set a gate that outlives the process -- Igor's task
        simply stayed open inside the running experiment instead."""
        if self._task is not None:
            try:
                if zero:
                    self._write(0.0)
            finally:
                self._task.close()
                self._task = None
        if zero:
            self.gate_mv = 0.0
            # The config is written into every data file, so it must not go
            # on claiming a gate that is no longer applied.
            self.cfg.echem.gate_mv = 0.0

    def __enter__(self) -> "CounterElectrode":
        return self.on()

    def __exit__(self, *exc) -> bool:
        self.off()
        return False

    def _write(self, volts: float) -> None:
        self._task.write(volts, auto_start=True)

    def set_mv(self, mv: float) -> None:
        """Igor: WriteToCounterElectrode(Voltage) -- entered in mV."""
        self._write(mv / 1000.0)
        self.gate_mv = float(mv)
        self.cfg.echem.gate_mv = float(mv)      # travels in every data file
        log.info("counter electrode at %+.1f mV", mv)


class SimulatedCounterElectrode(CounterElectrode):
    def on(self) -> "SimulatedCounterElectrode":
        return self

    def off(self, zero: bool = True) -> None:
        # Signature must match the base class: callers pass zero=False to
        # leave the gate standing after the process exits, and a simulated
        # run has to accept the same call the real one does or the
        # simulation stops being a rehearsal.
        if zero:
            self.gate_mv = 0.0
            self.cfg.echem.gate_mv = 0.0

    def _write(self, volts: float) -> None:
        log.debug("simulated counter electrode <- %.4f V", volts)


def make_counter_electrode(cfg: RigConfig) -> CounterElectrode:
    return SimulatedCounterElectrode(cfg) if cfg.simulate \
        else CounterElectrode(cfg)


# --------------------------------------------------------------------------
# CV ramp construction
# --------------------------------------------------------------------------

def build_cv_ramp_highres(ec: EChemConfig) -> tuple[np.ndarray, np.ndarray]:
    """Igor CVcurveHighRes lines 127-158. Returns ``(applied_v, keep)``.

    Full sweep 0 -> V1 -> 0 -> V2 -> 0, then the first half repeated;
    ``keep`` is False over the first quarter and the repeat -- Igor NaN-ed
    exactly those, so a kept cycle starts and ends at the same potential
    with the switch-on transient discarded.
    """
    sweep = ec.scan_rate_mv_per_s / 1000.0                     # V/s
    r1 = int(round(2 * abs(ec.peak_one_v) / sweep * ec.cv_rate_hz))
    r2 = int(round(2 * abs(ec.peak_two_v) / sweep * ec.cv_rate_hz))
    if min(r1, r2) < 4:
        raise ValueError("CV ramp too short; slow the scan rate or raise "
                         "cv_rate_hz")
    s1, s2 = ec.peak_one_v / (r1 / 2), ec.peak_two_v / (r2 / 2)
    f1, q2, q3, q4 = r1 // 2, r1, r1 + r2 // 2, r1 + r2
    n = 2 * r1 + r2

    p = np.arange(n, dtype=float)
    applied = np.empty(n)
    applied[:f1] = s1 * p[:f1]
    applied[f1:q2] = ec.peak_one_v - s1 * (p[f1:q2] - f1)
    applied[q2:q3] = s2 * (p[q2:q3] - q2)
    applied[q3:q4] = ec.peak_two_v - s2 * (p[q3:q4] - q3)
    applied[q4:q4 + f1] = s1 * (p[q4:q4 + f1] - q4)
    applied[q4 + f1:q4 + q2] = ec.peak_one_v - s1 * \
        (p[q4 + f1:q4 + q2] - (q4 + f1))

    keep = np.ones(n, dtype=bool)
    keep[:f1] = False                       # switch-on quarter
    keep[q4 + f1:q4 + q2] = False           # the repeated half
    return applied, keep


def build_cv_ramp_lowres(ec: EChemConfig,
                         set_zero: int = 5000) -> tuple[np.ndarray,
                                                        np.ndarray]:
    """Igor CVcurveLowRes lines 251-286: 5000 samples of 0 V first, then the
    same triangle, with a longer repeated tail. Returns ``(applied, keep)``."""
    sweep = ec.scan_rate_mv_per_s / 1000.0
    r1 = int(round(2 * abs(ec.peak_one_v) / sweep * ec.cv_rate_hz))
    r2 = int(round(2 * abs(ec.peak_two_v) / sweep * ec.cv_rate_hz))
    if min(r1, r2) < 4:
        raise ValueError("CV ramp too short; slow the scan rate or raise "
                         "cv_rate_hz")
    s1, s2 = ec.peak_one_v / (r1 / 2), ec.peak_two_v / (r2 / 2)
    z = set_zero
    f1, q2, q3, q4 = r1 // 2 + z, r1 + z, r1 + r2 // 2 + z, r1 + r2 + z
    n = q4 + r1 + r2 // 2                   # Igor: 2*R1 + 3*R2/2 + SetZero

    p = np.arange(n, dtype=float)
    applied = np.zeros(n)
    applied[z:f1] = s1 * (p[z:f1] - z)
    applied[f1:q2] = ec.peak_one_v - s1 * (p[f1:q2] - f1)
    applied[q2:q3] = s2 * (p[q2:q3] - q2)
    applied[q3:q4] = ec.peak_two_v - s2 * (p[q3:q4] - q3)
    applied[q4:q4 + f1 - z] = s1 * (p[q4:q4 + f1 - z] - q4)
    applied[q4 + f1 - z:q4 + q2 - z] = ec.peak_one_v - s1 * \
        (p[q4 + f1 - z:q4 + q2 - z] - (q4 + f1 - z))
    applied[q4 + q2 - z:] = s2 * (p[q4 + q2 - z:] - (q4 + q2 - z))

    keep = np.ones(n, dtype=bool)
    keep[:f1] = False
    keep[q4 + f1 - z:] = False
    return applied, keep


# --------------------------------------------------------------------------
# Acquisition
# --------------------------------------------------------------------------

@dataclass
class CVCycle:
    cycle: int                        # 1-based, Igor's CVCycle counter
    applied_v: np.ndarray             # commanded electrode potential
    tip_current_v: np.ndarray         # raw preamp output, volts
    we_voltage_mv: np.ndarray | None  # measured electrode V (high-res only)
    keep: np.ndarray                  # False where Igor NaN-ed
    rate_hz: float


def run_cv(cfg: RigConfig, kind: str = "highres",
           cycles: int | None = None, seed: int = 0) -> list[CVCycle]:
    """Play the CV ramp and record the tip current, ``cycles`` times.

    ``kind`` is "highres" (drive dev1/ao1, the junction-bias channel; the
    tip is the working electrode; also records ai0) or "lowres" (drive the
    counter electrode on the second card; tip current only).

    With ``cfg.simulate`` the current comes from a simple cell model: a
    double-layer capacitance plus one reversible redox couple, enough to
    produce the classic hysteresis loop and test every line of the analysis.

    Hardware note: unplug nothing -- the high-res variant repurposes the
    junction-bias output, which is why Igor reset the card afterwards. Run
    ``rig.withdraw()`` first and expect the bias to be whatever the ramp
    left; this function parks the channel at 0 V when it finishes.
    """
    ec = cfg.echem
    n_cycles = cycles if cycles is not None else ec.cycles
    if kind == "highres":
        applied, keep = build_cv_ramp_highres(ec)
    elif kind == "lowres":
        applied, keep = build_cv_ramp_lowres(ec)
    else:
        raise ValueError(f"kind must be 'highres' or 'lowres', not {kind!r}")

    if cfg.simulate:
        return _run_cv_simulated(cfg, kind, applied, keep, n_cycles, seed)
    return _run_cv_hardware(cfg, kind, applied, keep, n_cycles)


def _simulated_cell_current_a(applied: np.ndarray, rate_hz: float,
                              rng: np.random.Generator) -> np.ndarray:
    """A double-layer capacitance and one reversible couple at ~+0.2 V.

    Not chemistry -- shape. Capacitive current flips sign with scan
    direction (the rectangular part of the loop); the faradaic peaks sit
    60 mV apart, anodic on the up-sweep, cathodic on the down-sweep.
    """
    dvdt = np.gradient(applied) * rate_hz
    i_cap = 1.0e-6 * dvdt                              # 1 uF double layer
    up = dvdt >= 0
    i_far = 2.0e-7 * (np.exp(-((applied - 0.23) / 0.05) ** 2) * up
                      - np.exp(-((applied - 0.17) / 0.05) ** 2) * ~up)
    noise = rng.normal(0.0, 2e-9, applied.size)
    return i_cap + i_far + noise


def _run_cv_simulated(cfg, kind, applied, keep, n_cycles, seed):
    rng = np.random.default_rng(seed)
    out = []
    for c in range(1, n_cycles + 1):
        current_a = _simulated_cell_current_a(applied, cfg.echem.cv_rate_hz,
                                              rng)
        tip_v = current_a * cfg.cal.preamp_gain_v_per_a
        we_mv = applied * 1000.0 + rng.normal(0, 0.05, applied.size) \
            if kind == "highres" else None
        out.append(CVCycle(c, applied.copy(), tip_v, we_mv, keep.copy(),
                           cfg.echem.cv_rate_hz))
        log.info("simulated CV cycle %d/%d", c, n_cycles)
    return out


def _run_cv_hardware(cfg, kind, applied, keep, n_cycles):
    import nidaqmx
    from nidaqmx.constants import AcquisitionType

    M, ec = cfg.channels, cfg.echem
    n = applied.size
    rate = ec.cv_rate_hz

    if kind == "highres":
        ao_chan = M.path(M.ao_bias)                       # dev1/ao1
        ao_range = max(M.bias_ao_range_v,
                       abs(ec.peak_one_v), abs(ec.peak_two_v))
    else:
        if M.low_res_device is None:
            raise EChemError("lowres CV needs channels.low_res_device")
        ao_chan = f"{M.low_res_device}/{ec.counter_electrode_channel}"
        ao_range = 10.0                                   # Igor used +/-10

    out = []
    with nidaqmx.Task("stmlab_cv_ao") as ao, nidaqmx.Task("stmlab_cv_ai") as ai:
        ao.ao_channels.add_ao_voltage_chan(ao_chan, min_val=-ao_range,
                                           max_val=ao_range)
        for chan in M.ai_channels:
            ai.ai_channels.add_ai_voltage_chan(chan, min_val=-M.ai_range_v,
                                               max_val=M.ai_range_v)
        ao.timing.cfg_samp_clk_timing(rate, sample_mode=AcquisitionType.FINITE,
                                      samps_per_chan=n)
        ai.timing.cfg_samp_clk_timing(rate, sample_mode=AcquisitionType.FINITE,
                                      samps_per_chan=n)
        # Igor started the two tasks back to back and lived with the skew;
        # a hardware trigger costs nothing and removes it.
        ai.triggers.start_trigger.cfg_dig_edge_start_trig(M.ao_start_trigger)

        timeout = float(np.ceil(n / rate)) + 5.0
        for c in range(1, n_cycles + 1):
            ao.write(applied, auto_start=False, timeout=timeout)
            ai.start()
            ao.start()
            ao.wait_until_done(timeout=timeout)
            data = np.asarray(ai.read(number_of_samples_per_channel=n,
                                      timeout=timeout))
            ai.stop()
            ao.stop()
            we_mv = data[M.ROW_VOLTAGE] * 1000.0 if kind == "highres" else None
            out.append(CVCycle(c, applied.copy(), data[M.ROW_CURRENT].copy(),
                               we_mv, keep.copy(), rate))
            log.info("CV cycle %d/%d", c, n_cycles)

        ao.write(np.zeros(2), auto_start=True)            # park at 0 V
    return out
