"""One pull, and many pulls.

Igor equivalents:

    build_ramp    CreateInputs, constant-bias branch  Functions_STMBJ.ipf:1601
    single_trace  GenerateTrace                       Functions_STMBJ.ipf:284
    trace_loop    MeasureBreakJunctions               Functions_STMBJ.ipf:1664

Only the constant-bias ramp is implemented. Igor's CreateInputs also builds
push-pull, IV, AC-hold and high-bias-hold trajectories; those are separate
experiments and are deliberately out of scope here.

Traces carry **raw volts**, never conductance. The conversion depends on three
measured constants that can be revised -- a mis-measured preamp gain, a zero
taken before the amplifier warmed up -- and baking them into stored data turns
a calibration error into a lost dataset instead of a re-analysis.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from . import analysis, safety
from .config import RigConfig
from .safety import RigState, SafetyViolation

log = logging.getLogger(__name__)


@dataclass
class Ramp:
    """A waveform ready for the card, plus where the interesting part is."""
    waveform: np.ndarray          # (2, n_record) volts at the DAQ
    pre_pad: int
    n_pull: int
    spike_front: int              # index of the spike's rising edge, in the
                                  # written waveform (fractional edge sits at
                                  # spike_front + 0.5)
    start_piezo_v: float
    end_piezo_v: float


@dataclass
class TraceRecord:
    """One pull, as raw volts."""
    index: int
    voltage_v: np.ndarray
    current_v: np.ndarray
    delay_samples: int
    start_piezo_v: float
    bias_v: float
    sample_rate_hz: float
    timestamp: float = field(default_factory=time.time)
    attempt: int = 0
    # Piezo sense readback over the same samples, raw volts from the low-res
    # card; None on a one-card rig. Igor's POExtension. Informational: the
    # displacement axis is still the commanded one (``displacement_nm``).
    piezo_sense_v: np.ndarray | None = None

    def conductance_g0(self, cfg: RigConfig,
                       use_measured_voltage: bool = True) -> np.ndarray:
        if use_measured_voltage:
            return analysis.to_conductance(self.current_v, cfg.cal,
                                           voltage_v=self.voltage_v)
        return analysis.to_conductance(self.current_v, cfg.cal,
                                       bias_v=self.bias_v)

    def displacement_nm(self, cfg: RigConfig) -> np.ndarray:
        return analysis.displacement_nm(self.voltage_v.size, cfg.ramp,
                                        self.sample_rate_hz)

    def piezo_sense_nm(self, cfg: RigConfig) -> np.ndarray | None:
        """Measured piezo position along the trace, in nm (Igor's SenseIn),
        or None when the rig has no sense line."""
        if self.piezo_sense_v is None:
            return None
        return cfg.cal.sense_volts_to_nm(self.piezo_sense_v)


# --------------------------------------------------------------------------
# Building the ramp
# --------------------------------------------------------------------------

def build_ramp(cfg: RigConfig, start_piezo_v: float,
               sample_rate_hz: float | None = None,
               bias_offset_v: float = 0.0) -> Ramp:
    """Construct the piezo and bias waveforms for one pull.

    Layout, in samples::

        [ pre_pad ][ ------------ pull ------------ ][ post_pad ]
          hold DC     descending ramp, spike near end   hold final

    The leading pad gives the 4461's decimation filter somewhere to settle
    that is not the metallic-contact region, where the 1 G0 reference sits.
    The trailing pad keeps the whole spike inside the captured record even
    after the AI/AO group delay shifts it later.

    Raises SafetyViolation if the descending ramp would reach the piezo floor;
    on a unipolar piezo that would clip and silently shorten the trace, which
    is indistinguishable from a junction that broke early.
    """
    R, C, M = cfg.ramp, cfg.cal, cfg.channels
    fs = sample_rate_hz or R.sample_rate_hz

    safety.check_bias(cfg, R.bias_v)
    safety.check_pull_headroom(cfg, start_piezo_v)

    n = R.n_pull_samples
    # Volts per sample. Igor: DeltaEx, Functions_STMBJ.ipf:1458.
    dv = R.pull_rate_nm_per_s / C.piezo_nm_per_volt / fs

    piezo_pull = start_piezo_v - np.arange(n, dtype=float) * dv

    # bias_offset_v is the Vzero correction: Igor wrote -(TipBias+Vzero)/1000
    # when the Voltage_Offset panel was active (Functions_STMBJ.ipf:1609-1614)
    # but kept the spike at +TipBias/1000 (line 1631), so the offset is added
    # to the baseline only.
    baseline = C.bias_output_sign * (R.bias_v + bias_offset_v)
    bias_pull = np.full(n, baseline, dtype=float)

    front, back = analysis.spike_indices(R, fs)
    if 0 <= front < back <= n:
        # Igor writes the spike into [front+1, back-1] inclusive.
        bias_pull[front + 1:back] = -C.bias_output_sign * R.bias_v
    else:
        log.warning("alignment spike does not fit in a %d-point pull; "
                    "trace alignment will fall back to the configured "
                    "group delay", n)

    pre = np.repeat([[start_piezo_v], [baseline]], R.pre_pad_samples, axis=1) \
        if R.pre_pad_samples else np.zeros((2, 0))
    post = np.repeat([[piezo_pull[-1]], [baseline]], R.post_pad_samples,
                     axis=1) if R.post_pad_samples else np.zeros((2, 0))

    waveform = np.concatenate(
        [pre, np.stack([piezo_pull, bias_pull]), post], axis=1)

    # Clamp is a backstop, not the plan: check_pull_headroom above should
    # already have made it impossible for this to fire.
    lo, hi = cfg.limits.piezo_ao_min_v, cfg.limits.piezo_ao_max_v
    if waveform[M.ROW_PIEZO].min() < lo or waveform[M.ROW_PIEZO].max() > hi:
        log.warning("clamping piezo ramp into [%.3f, %.3f] V", lo, hi)
        waveform[M.ROW_PIEZO] = np.clip(waveform[M.ROW_PIEZO], lo, hi)

    return Ramp(waveform=waveform,
                pre_pad=R.pre_pad_samples,
                n_pull=n,
                spike_front=R.pre_pad_samples + front,
                start_piezo_v=start_piezo_v,
                end_piezo_v=float(piezo_pull[-1]))


# --------------------------------------------------------------------------
# One pull
# --------------------------------------------------------------------------

def single_trace(rig, index: int = 0,
                 bias_offset_v: float = 0.0) -> TraceRecord | None:
    """Play one constant-bias pull and cut the trace out of the record.

    Returns None if the alignment spike could not be located, which means the
    record cannot be trusted to line up with the commanded displacement.
    ``bias_offset_v`` is the Vzero correction (see ``build_ramp``).
    """
    cfg = rig.cfg
    ramp = build_ramp(cfg, rig.piezo_v, rig.sample_rate_hz,
                      bias_offset_v=bias_offset_v)
    return capture(rig, ramp, index=index,
                   bias_v=cfg.ramp.bias_v + bias_offset_v)


def capture(rig, ramp, index: int = 0,
            bias_v: float | None = None) -> TraceRecord | None:
    """Play any prebuilt ramp and cut the trace out of the captured record.

    ``ramp`` is a ``Ramp`` from :func:`build_ramp` or a ``ramps.ModeRamp`` --
    anything with ``waveform``, ``pre_pad``, ``n_pull``, ``spike_front`` and
    ``start_piezo_v``. This is the single capture path for every experiment:
    the alignment-spike recovery and the plausibility cut are identical for a
    constant-bias pull, a push-pull cycle, an IV sweep, or a hold.

    For mode ramps, ``TraceRecord.displacement_nm`` does NOT apply -- it
    assumes a constant pull rate. Use the ramp's ``segments`` instead.
    """
    cfg = rig.cfg
    rig.state = RigState.PULLING
    record = rig.play(ramp.waveform)      # play() updates the position tracker

    delay = _measure_delay(cfg, record, ramp, rig.sample_rate_hz)
    if delay is None:
        return None

    start = ramp.pre_pad + delay
    stop = start + ramp.n_pull
    if stop > record.shape[1]:
        log.warning("trace runs past the end of the record (delay %d "
                    "samples); increase post_pad_samples", delay)
        return None

    # The sense line, when there is one, is cut with the same indices as the
    # two record rows: one rule for everything in a TraceRecord. It comes
    # from the other card, which has no decimation filter, so the readback
    # actually leads the record by part of the group delay -- a fraction of a
    # millisecond, far below anything the readback is used to judge.
    sense = getattr(rig, "last_sense_v", None)
    sense_cut = None
    if sense is not None:
        if sense.size >= stop:
            sense_cut = np.asarray(sense[start:stop], dtype=float).copy()
        else:
            log.warning("piezo sense readback has %d samples, record needs "
                        "%d; dropping it for this trace", sense.size, stop)

    M = cfg.channels
    return TraceRecord(
        index=index,
        voltage_v=record[M.ROW_VOLTAGE, start:stop].copy(),
        current_v=record[M.ROW_CURRENT, start:stop].copy(),
        delay_samples=delay,
        start_piezo_v=ramp.start_piezo_v,
        bias_v=cfg.ramp.bias_v if bias_v is None else bias_v,
        sample_rate_hz=rig.sample_rate_hz,
        attempt=rig.attempts,
        piezo_sense_v=sense_cut)


def _measure_delay(cfg: RigConfig, record: np.ndarray, ramp: Ramp,
                   fs: float) -> int | None:
    """AI/AO lag in samples, from the alignment spike."""
    edge = analysis.find_alignment_edge(
        record[cfg.channels.ROW_VOLTAGE],
        search_from=max(0, ramp.spike_front - int(0.05 * fs)))

    if edge is None:
        if cfg.cal.group_delay_samples is not None:
            return int(cfg.cal.group_delay_samples)
        log.warning("alignment spike not found and no measured group delay "
                    "in the calibration; discarding trace")
        return None

    delay = int(round(edge - (ramp.spike_front + 0.5)))

    # A delay of the wrong order means the spike search locked onto something
    # else -- a noise crossing, or a junction so noisy the bias readback
    # changes sign. Better to drop the trace than to shift it by 1000 samples.
    if not -0.02 * fs <= delay <= 0.05 * fs:
        log.warning("implausible alignment delay of %d samples; discarding "
                    "trace", delay)
        return None
    return delay


# --------------------------------------------------------------------------
# Many pulls
# --------------------------------------------------------------------------

def trace_loop(rig, n: int | None = None, on_trace=None, stop_flag=None,
               require_engaged: bool = False) -> dict:
    """Acquire until ``n`` traces are accepted, or the budget runs out.

    ``on_trace(index, trace, selection)`` is called for every *accepted*
    trace. ``stop_flag`` is anything with ``is_set()``, checked between
    attempts -- Igor polled the Alt key for this (Functions_STMBJ.ipf:1697).

    Both parameters exist so the loop is callable from a script, a test, or a
    GUI worker thread without modification.
    """
    from . import approach

    cfg = rig.cfg
    target = n if n is not None else cfg.ramp.traces_target

    accepted = 0
    attempts = 0
    rejections: dict[str, int] = {}

    while accepted < target and attempts < cfg.ramp.max_attempts:
        if stop_flag is not None and stop_flag.is_set():
            log.info("stopping: stop flag set")
            break

        attempts += 1
        rig.attempts = attempts

        if cfg.ramp.smash_every and attempts % cfg.ramp.smash_every == 0:
            approach.smash(rig)

        try:
            if approach.engage(rig) is not RigState.ENGAGED:
                continue
            trace = single_trace(rig, index=accepted)
        except SafetyViolation:
            raise
        except Exception:
            log.exception("attempt %d failed", attempts)
            continue

        if trace is None:
            rejections["alignment"] = rejections.get("alignment", 0) + 1
            continue

        verdict = analysis.select_trace(
            trace.conductance_g0(cfg), cfg.ramp,
            require_engaged=require_engaged)

        if not verdict.accepted:
            key = verdict.reason.split(":")[0].split("(")[0].strip()
            rejections[key] = rejections.get(key, 0) + 1
            continue

        accepted += 1
        if on_trace is not None:
            on_trace(accepted - 1, trace, verdict)

        if accepted % 25 == 0:
            log.info("%d/%d accepted, %d attempts (%.0f%%)",
                     accepted, target, attempts, 100 * accepted / attempts)

    return {"accepted": accepted,
            "attempts": attempts,
            "acceptance_rate": accepted / attempts if attempts else 0.0,
            "rejections": rejections}
