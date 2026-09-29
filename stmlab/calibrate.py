"""Measuring the constants, rather than assuming them.

Every one of these writes into ``cfg.cal``, and ``cfg`` is written into every
data file, so a calibration always travels with the data it applies to.

    measure_zero          the preamp's resting offset -- every session
    measure_group_delay   AI/AO lag in samples        -- after a rate change
    measure_gain_offset   AI transfer function        -- loopback cable
    expected_resistor_v   what a known resistor should read

The one constant not measurable from here is the piezo's nm/V. That needs a
length standard, and on this rig it is inherited from Igor's K_ZPiezoScale = 62
as an end-to-end number for the whole chain including the driver box.
"""

from __future__ import annotations

import logging

import numpy as np

from . import analysis
from .config import G0_SIEMENS

log = logging.getLogger(__name__)


def measure_zero(rig, n_samples: int = 20_000) -> float:
    """The preamp's output with no bias applied.

    Hundreds of microvolts, drifts with temperature, and sets the floor of the
    tunnelling tail. Re-measure every session; an uncorrected zero puts a
    false plateau at the bottom of every histogram.

    The tip should be out of contact. Bias is set to zero for the measurement
    and restored afterwards.
    """
    cfg = rig.cfg
    was = rig.bias_v
    try:
        record = rig.hold(bias_v=0.0, n_samples=n_samples)
    finally:
        rig.hold(bias_v=was)

    current = record[cfg.channels.ROW_CURRENT]
    keep = current[current.size // 4:]          # discard the settling head
    zero = float(np.mean(keep))
    noise = float(np.std(keep))

    log.info("preamp zero %.3f uV, noise %.3f uV rms (= %.2e G0 at %.0f mV)",
             zero * 1e6, noise * 1e6,
             abs(cfg.cal.volts_to_amps(noise)) / (cfg.ramp.bias_v * G0_SIEMENS),
             cfg.ramp.bias_v * 1e3)
    return zero


def measure_group_delay(rig, repeats: int = 20) -> tuple[float, float]:
    """AI/AO lag in samples, from a bias spike. Returns (mean, stdev).

    The mean will be tens of samples on a delta-sigma card. What matters is
    the scatter: it should be well under one sample. If it is not, AI is not
    actually triggered off AO and something in the timing setup is wrong.

    The probe is a *spike*, not a step, so this exercises exactly the edge
    that every trace uses to align itself -- same waveform shape, same
    detector. A step would need only one crossing and would therefore test a
    code path nothing else uses.

    Traces recover their own delay from their own spike, so this is a
    cross-check and a fallback rather than a dependency.
    """
    cfg = rig.cfg
    n = max(2000, cfg.ramp.settle_samples * 2)
    baseline = cfg.cal.bias_output_sign * cfg.ramp.bias_v

    spike_start = n // 2
    spike_stop = spike_start + max(20, n // 8)   # trailing baseline is needed
    if spike_stop >= n:                          # for the second crossing
        raise ValueError("probe waveform too short for a spike")

    waveform = np.repeat([[rig.piezo_v], [baseline]], n, axis=1)
    waveform[cfg.channels.ROW_BIAS, spike_start:spike_stop] = -baseline

    delays = []
    for _ in range(repeats):
        record = rig.play(waveform)
        edge = analysis.find_alignment_edge(
            record[cfg.channels.ROW_VOLTAGE], search_from=spike_start // 2)
        if edge is not None:
            delays.append(edge - (spike_start - 0.5))

    if not delays:
        raise RuntimeError("no edges found; is the bias channel connected to "
                           "the voltage input?")

    mean, sd = float(np.mean(delays)), float(np.std(delays))
    log.info("group delay %.2f +/- %.2f samples over %d repeats",
             mean, sd, len(delays))
    if sd > 1.0:
        log.warning("group delay scatter is %.2f samples, above one sample. "
                    "AI is probably not triggered off ao/StartTrigger.", sd)
    return mean, sd


def measure_gain_offset(rig, lo: float = -2.0, hi: float = 2.0,
                        points: int = 17) -> tuple[float, float]:
    """DC transfer function of the AI path. Needs a loopback cable.

    Wire the bias output to the voltage input, sweep, and fit a line: the
    slope is the gain error and the intercept the offset. Requires DC
    coupling, which must be set explicitly on a 4461 -- its default is AC, and
    an AC-coupled sweep returns a slope of zero and a very confusing afternoon.
    """
    cfg = rig.cfg
    commanded = np.linspace(lo, hi, points)
    measured = []

    for volts in commanded:
        record = rig.hold(bias_v=cfg.cal.bias_output_sign * volts,
                          n_samples=cfg.ramp.settle_samples * 2)
        tail = record[cfg.channels.ROW_VOLTAGE]
        measured.append(float(np.mean(tail[tail.size // 2:])))

    slope, intercept = np.polyfit(commanded, np.asarray(measured), 1)
    log.info("AI transfer: slope %.6f, offset %.3f uV", slope, intercept * 1e6)
    return float(slope), float(intercept)


def expected_resistor_v(cfg, resistance_ohm: float) -> float:
    """What the preamp should read with a known resistor for a junction.

    The check from the setup document: 100 mV across 1 MOhm is 100 nA, which
    at 1e6 V/A gives exactly 0.1 V at the ADC. If it does not, the preamp gain
    in the config is wrong and every conductance is scaled by the same factor.
    """
    return cfg.ramp.bias_v / resistance_ohm * cfg.cal.preamp_gain_v_per_a


def session_calibration(rig, do_group_delay: bool = True) -> dict:
    """The routine to run at the start of every session."""
    cfg = rig.cfg
    results: dict[str, float] = {}

    cfg.cal.current_zero_v = measure_zero(rig)
    results["current_zero_v"] = cfg.cal.current_zero_v

    if do_group_delay:
        try:
            mean, sd = measure_group_delay(rig)
            cfg.cal.group_delay_samples = int(round(mean))
            results["group_delay_samples"] = mean
            results["group_delay_stdev"] = sd
        except Exception:
            log.exception("group delay measurement failed; traces will still "
                          "align themselves from the spike")

    cfg.cal.granted_sample_rate_hz = rig.sample_rate_hz
    results["granted_sample_rate_hz"] = rig.sample_rate_hz
    return results
