"""Volts to physics. No hardware; runs anywhere.

Everything here is a pure function of arrays, so it can be exercised against
archived Igor data on a laptop. That is phase 2 of the build order and the
thing that decides whether the rest of the pipeline is trustworthy: if this
module reproduces Igor's 1 G0 peak position from Igor's own files, the
analysis path is validated and any later disagreement is an acquisition
problem, not an arithmetic one.

Igor equivalents:

    to_conductance      GenerateTrace's final lines   Functions_STMBJ.ipf:380-393
    select_trace        TestTrace                     Functions_STMBJ.ipf:1180
    log_histogram       LogHistFromBlocks             Functions_STMBJ.ipf:785
    find_alignment_edge FindLevels on the pulse       Functions_STMBJ.ipf:371-377
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import G0_SIEMENS, Calibration, RampConfig


# --------------------------------------------------------------------------
# Igor primitives that numpy spells differently
# --------------------------------------------------------------------------

def average_deviation(x: np.ndarray) -> float:
    """Igor's ``V_adev``: mean absolute deviation, *not* the standard one.

    Worth being explicit about. Substituting np.std here inflates the number
    by about 25% for gaussian noise, which quietly tightens TestTrace's
    ``Dev_Conductance < 0.01`` cut and throws away good traces.
    """
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return float("nan")
    return float(np.mean(np.abs(x - x.mean())))


def boxcar(x: np.ndarray, width: int = 11) -> np.ndarray:
    """Igor's ``Smooth/B width``: a sliding box average.

    Igor pads by holding the end values, which is what ``mode="nearest"``
    reproduces; a zero-padded convolution would drag the ends of every trace
    toward zero and bias the low-conductance tail.
    """
    x = np.asarray(x, dtype=float)
    if width <= 1 or x.size == 0:
        return x.copy()
    if width % 2 == 0:
        width += 1                       # Igor rounds even widths up
    pad = width // 2
    padded = np.pad(x, pad, mode="edge")
    kernel = np.ones(width) / width
    return np.convolve(padded, kernel, mode="valid")


# --------------------------------------------------------------------------
# Conductance
# --------------------------------------------------------------------------

def to_conductance(current_v: np.ndarray,
                   cal: Calibration,
                   voltage_v: np.ndarray | None = None,
                   bias_v: float | None = None) -> np.ndarray:
    """Preamp output volts -> conductance in units of G0.

        G/G0 = (V_out - V_zero) / (Rf * V_bias * G0)

    Pass ``voltage_v`` to divide by the *measured* junction voltage sample by
    sample, which is what Igor did (Functions_STMBJ.ipf:388-389) and what the
    bias monitor exists for. Pass ``bias_v`` instead to divide by the
    commanded value -- quieter at very low conductance, where the measured
    voltage carries the preamp's noise into the denominator, but it trusts a
    number nobody checked.

    Exactly one of the two must be given.
    """
    if (voltage_v is None) == (bias_v is None):
        raise ValueError("pass exactly one of voltage_v or bias_v")

    amps = cal.volts_to_amps(np.asarray(current_v, dtype=float))
    if bias_v is not None:
        denominator = float(bias_v)
    else:
        denominator = cal.voltage_input_sign * np.asarray(voltage_v,
                                                          dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return amps / (denominator * G0_SIEMENS)


def displacement_nm(n_samples: int, ramp: RampConfig,
                    sample_rate_hz: float | None = None) -> np.ndarray:
    """Tip displacement axis for a pull, in nm, starting at 0.

    Commanded, not measured. Igor read the piezo back on the low-res card's
    sense channel and stored that as POExtension; here that readback, when
    the rig has a second card, travels as ``TraceRecord.piezo_sense_v`` for
    checking the piezo, and this axis stays the commanded trajectory. The
    piezo is open-loop either way -- the sense channel measures the driver's
    output voltage, not the actual displacement -- so the difference is
    smaller than it sounds, but hysteresis and creep are absent from this
    axis entirely.
    """
    fs = sample_rate_hz or ramp.sample_rate_hz
    return np.arange(n_samples, dtype=float) * ramp.pull_rate_nm_per_s / fs


# --------------------------------------------------------------------------
# Alignment
# --------------------------------------------------------------------------

def find_alignment_edge(voltage_raw: np.ndarray,
                        search_from: int = 0,
                        level: float = 0.0) -> float | None:
    """Locate the rising edge of the bias alignment spike, sub-sample.

    A short spike is written on the bias channel near the end of every ramp
    and read straight back on ai0. The lag between where it was written and
    where it appears is the card's AI/AO group delay plus trigger skew, and
    measuring it per trace means the delay never has to be assumed.

    On the 4461 this is tens of samples, and constant -- but it changes with
    sample rate, so per-trace recovery survives a rate change that a
    hardcoded constant would not.

    Igor did the same thing across two cards, taking the second of two
    crossings found scanning backwards (Functions_STMBJ.ipf:371-376). With one
    card the spike appears directly on ai0 and the crossing search is over the
    same signal that was written.

    Returns the fractional index of the last rising-to-spike transition, or
    None if the spike could not be found.
    """
    v = np.asarray(voltage_raw, dtype=float)[search_from:]
    if v.size < 3:
        return None

    signs = np.sign(v - level)
    signs[signs == 0] = 1.0
    crossings = np.nonzero(np.diff(signs) != 0)[0]
    if crossings.size < 2:
        return None

    # The spike produces two crossings: into it, then back out. Take the pair
    # closest to the end of the record and use the earlier one.
    front = int(crossings[-2])

    # Linear interpolation between the bracketing samples.
    y0, y1 = v[front] - level, v[front + 1] - level
    frac = 0.0 if y1 == y0 else -y0 / (y1 - y0)
    return search_from + front + float(np.clip(frac, 0.0, 1.0))


def spike_indices(ramp: RampConfig,
                  sample_rate_hz: float | None = None) -> tuple[int, int]:
    """(front, back) indices of the spike within the pull, Igor's convention.

    Igor put the front edge 7.5 ms and the back edge 2.5 ms before the end of
    the ramp, writing the spike into ``[front+1, back-1]`` inclusive
    (Functions_STMBJ.ipf:1618-1631).
    """
    fs = sample_rate_hz or ramp.sample_rate_hz
    n = ramp.n_pull_samples
    front = n - int(round(ramp.spike_front_ms * 1e-3 * fs)) - 1
    back = n - int(round(ramp.spike_back_ms * 1e-3 * fs)) + 1
    return front, back


# --------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------

@dataclass
class Selection:
    accepted: bool
    reason: str
    end_conductance: float = float("nan")
    end_deviation: float = float("nan")
    start_conductance: float = float("nan")
    plateau_counts: float = float("nan")


def select_trace(g0: np.ndarray, ramp: RampConfig,
                 require_engaged: bool = False,
                 plateau_min_counts: float = 10.0,
                 end_deviation_max: float = 0.01) -> Selection:
    """Accept or reject one trace. Igor's ``TestTrace``.

    Two crude criteria, plus one that Igor left switched off:

    * **ended in tunnelling** -- the conductance around 90% of the way through
      the pull is below ``ramp.break_g0``, and quiet
    * **has a gold plateau** -- at least ``plateau_min_counts`` points sit
      between 0.5 and 2.5 G0
    * **started in metallic contact** -- the first 0.5% of the trace is above
      ``ramp.engage_g0``

    That third test is present in Igor's source but its ``else`` branch is
    commented out (Functions_STMBJ.ipf:1212-1215), so a trace that fails it
    falls through to ``return 1`` and is accepted anyway. ``require_engaged``
    defaults to False to reproduce that behaviour, because matching archived
    Igor histograms is the validation milestone. Set it True for new data if
    you want the criterion your architecture document describes -- but then
    say so in the paper, and apply it identically to controls.

    Selection is the step where this measurement becomes unfalsifiable if you
    are careless, which is why all of it lives in this one function rather
    than being scattered through the acquisition code.
    """
    g0 = np.asarray(g0, dtype=float)
    n = g0.size
    if n < 200:
        return Selection(False, "trace too short")

    # End of trace: Igor sampled the 90%-91% window.
    tail = g0[int(n * 0.90):int(n * 0.91) + 1]
    end_mean = float(np.mean(tail))
    end_adev = average_deviation(tail)

    if not abs(end_mean) < ramp.break_g0:
        return Selection(False,
                         f"end G = {end_mean:.3e} >= break threshold "
                         f"{ramp.break_g0:.3e}",
                         end_mean, end_adev)

    # Start of trace: Igor sampled the first n/200 points.
    head = g0[0:int(round(n / 200)) + 1]
    start_mean = float(np.mean(head))

    if not abs(start_mean) > ramp.engage_g0:
        if require_engaged:
            return Selection(False,
                             f"start G = {start_mean:.3e} <= engage "
                             f"threshold {ramp.engage_g0:.3g}",
                             end_mean, end_adev, start_mean)
        return Selection(True, "accepted (engage check disabled, as in Igor)",
                         end_mean, end_adev, start_mean)

    if end_adev >= end_deviation_max:
        return Selection(False,
                         f"end of trace is noisy: adev {end_adev:.3e} >= "
                         f"{end_deviation_max:.3e}",
                         end_mean, end_adev, start_mean)

    # Igor: Histogram/B={0.1, 0.1, 40}, then sum over x in [0.5, 2.5].
    counts, _ = np.histogram(g0, bins=40, range=(0.1, 4.1))
    plateau = float(counts[4:25].sum())      # bins whose left edge is 0.5..2.5

    if plateau <= plateau_min_counts:
        return Selection(False,
                         f"only {plateau:.0f} points between 0.5 and 2.5 G0 "
                         f"(need > {plateau_min_counts:.0f})",
                         end_mean, end_adev, start_mean, plateau)

    return Selection(True, "accepted", end_mean, end_adev, start_mean, plateau)


# --------------------------------------------------------------------------
# Histogram
# --------------------------------------------------------------------------

def log_histogram(traces,
                  lo: float = -8.0,
                  hi: float = 2.0,
                  n_bins: int = 1000,
                  keep_fraction: float = 0.95,
                  smooth_width: int = 11,
                  zero_cutoff: float | None = None,
                  subtract_floor: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Accumulate log10(G/G0) over many traces. Igor's ``LogHistFromBlocks``.

    This is the measurement. Individual traces prove nothing; configurations
    that recur produce peaks and noise does not.

    Per trace, following Igor:

    1. keep the first ``keep_fraction`` of the points, dropping the tail that
       contains the alignment spike
    2. box-smooth
    3. estimate the residual current floor from the 95%-96% window
    4. if that floor is below ``zero_cutoff``, subtract it, smooth again,
       take log10, and accumulate

    Step 4's condition is a quality gate, not just an offset correction: a
    trace whose floor sits *above* the cutoff never entered a clean tunnelling
    regime and is dropped from the histogram entirely.

    Returns ``(bin_centres, counts_per_trace)``.

    One deliberate difference from Igor: Igor's ``SetScale/I x -8,2`` over
    1000 points gives a bin width of 10/999, half a percent wider than 10/1000
    and with the last bin hanging past 2.0. This uses even bins across
    [lo, hi]. The resulting peak shift is under 0.005 decade, an order of
    magnitude below the 0.05 decade agreement target.
    """
    edges = np.linspace(lo, hi, n_bins + 1)
    centres = 0.5 * (edges[:-1] + edges[1:])
    counts = np.zeros(n_bins, dtype=float)

    n_used = 0
    for trace in traces:
        g0 = np.asarray(trace, dtype=float)
        if g0.size == 0:
            continue

        keep = max(1, int(g0.size * keep_fraction))
        g0 = boxcar(g0[:keep], smooth_width)

        window = g0[int(g0.size * 0.95):int(g0.size * 0.96) + 1]
        floor = float(np.mean(window)) if window.size else 0.0

        if zero_cutoff is not None and not floor < zero_cutoff:
            continue

        if subtract_floor:
            g0 = boxcar(g0 - floor, smooth_width)

        with np.errstate(divide="ignore", invalid="ignore"):
            logs = np.log10(g0)
        logs = logs[np.isfinite(logs)]
        if logs.size == 0:
            continue

        counts += np.histogram(logs, bins=edges)[0]
        n_used += 1

    if n_used:
        counts /= n_used              # counts per trace, as Igor reported
    return centres, counts


def peak_position(centres: np.ndarray, counts: np.ndarray,
                  around: float = 0.0, window: float = 0.5,
                  refine: float = 0.15) -> float:
    """Position of the histogram peak near ``around``, in decades.

    Locates the maximum within ``window`` of ``around``, then takes a centroid
    within ``refine`` of it. The two-step matters: a plain centroid over the
    whole window is dragged by the shoulder of counts from the metallic
    contact region on one side and the tunnelling descent on the other, and
    reports a peak position that no bin actually occupies.

    Used to compare against Igor's 1 G0 peak. A disagreement diagnoses itself:
    an offset of exactly +/-1.000 decade is a 10x gain error, and +/-0.301 is a
    factor of two in bias -- or someone defining G0 as e^2/h instead of 2e^2/h.
    """
    centres = np.asarray(centres, dtype=float)
    counts = np.asarray(counts, dtype=float)

    sel = np.abs(centres - around) <= window
    if not sel.any() or counts[sel].sum() == 0:
        return float("nan")

    local = np.where(sel, counts, -np.inf)
    apex = centres[int(np.argmax(local))]

    near = np.abs(centres - apex) <= refine
    if counts[near].sum() == 0:
        return float(apex)
    return float(np.average(centres[near], weights=counts[near]))
