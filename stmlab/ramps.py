"""Every trajectory Igor's CreateInputs could build, as pure functions.

Igor equivalent: CreateInputs, Functions_STMBJ.ipf:1398-1633. That function
had five branches selected by GUI checkboxes; the constant-bias branch lives
in ``trace.build_ramp`` (translated first, validated first), and the other
four live here:

    build_push_pull   PushPull branch    Functions_STMBJ.ipf:1461-1495
    build_iv          IV branch          Functions_STMBJ.ipf:1497-1537
    build_ac_hold     AC-hold branch     Functions_STMBJ.ipf:1539-1564
    build_hb_hold     HB-hold branch     Functions_STMBJ.ipf:1566-1599

All four share Igor's conventions exactly:

* Lengths are expressed in nanometres and converted to sample counts at the
  pull rate: ``n = round(length_nm / pull_rate * sample_rate)``. A "hold" of
  3 nm therefore means "as long as pulling 3 nm would take" -- Igor's
  parameterisation, kept so archived settings translate one to one.
* The piezo trajectory is built relative to the contact point (0 at start,
  negative = retracted) and shifted to ``start_piezo_v``. On this unipolar
  piezo, descending = retracting, the same sign convention as Igor's.
* The bias row is in **write volts at ao1**, Igor's sign convention included:
  the constant baseline is ``-(TipBias/1000)`` and the IV branch builds its
  ramp positive then negates the whole wave (``*= -1``, Igor line 1533).
* The alignment spike is written into ``[front+1, back-1]`` at
  ``+(TipBias/1000)`` in *every* mode (Igor line 1631), 7.5 to 2.5 ms before
  the end of the mode wave, so ``trace.capture`` can recover the AI/AO delay
  for mode traces exactly as it does for constant-bias pulls.

What this module adds that Igor did not have: the pre/post pads from
``RampConfig`` (the 4461's decimation filter needs somewhere to settle), and
refusals when the trajectory would leave the piezo range in either
direction -- Igor only guarded the retracted side, but push-pull moves the
tip *above* the contact point, where the hazard is the ceiling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from . import safety
from .config import (ACHoldConfig, HBHoldConfig, IVConfig, PushPullConfig,
                     RigConfig)
from .safety import SafetyViolation

log = logging.getLogger(__name__)


@dataclass
class ModeRamp:
    """A mode trajectory ready for the card.

    Field-compatible with ``trace.Ramp`` (waveform, pre_pad, n_pull,
    spike_front, start/end_piezo_v) so ``trace.capture`` accepts either.
    ``segments`` maps segment names to ``(start, stop)`` sample indices
    *within the pull* (add ``pre_pad`` + the measured delay to index into a
    captured record -- ``trace.TraceRecord`` is already cut, so its arrays
    line up with these indices directly).
    """
    mode: str
    waveform: np.ndarray          # (2, n_record) volts at the DAQ
    pre_pad: int
    n_pull: int
    spike_front: int
    start_piezo_v: float
    end_piezo_v: float
    segments: dict[str, tuple[int, int]] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# Shared pieces
# --------------------------------------------------------------------------

def _n_points(length_nm: float, cfg: RigConfig, fs: float) -> int:
    """Igor: round(Length/ExcursionRate*AcquisitionRate)."""
    return int(round(length_nm / cfg.ramp.pull_rate_nm_per_s * fs))


def _spike_edges(n: int, cfg: RigConfig, fs: float) -> tuple[int, int]:
    """Igor lines 1619-1622, on a mode wave of ``n`` points."""
    front = n - int(round(cfg.ramp.spike_front_ms * 1e-3 * fs)) - 1
    back = n - int(round(cfg.ramp.spike_back_ms * 1e-3 * fs)) + 1
    return front, back


def _assemble(cfg: RigConfig, mode: str, rel: np.ndarray, bias: np.ndarray,
              start_piezo_v: float, fs: float,
              segments: dict[str, tuple[int, int]],
              meta: dict | None = None) -> ModeRamp:
    """Spike, bounds checks, pads: the part common to all four builders."""
    R, L, M = cfg.ramp, cfg.limits, cfg.channels
    n = rel.size

    # The alignment spike, Igor line 1631: +(TipBias/1000) in every mode.
    front, back = _spike_edges(n, cfg, fs)
    if 0 <= front < back <= n:
        bias[front + 1:back] = R.bias_v
    else:
        log.warning("%s: alignment spike does not fit in a %d-point wave",
                    mode, n)

    safety.check_bias(cfg, float(np.max(np.abs(bias))))

    piezo = start_piezo_v + rel
    floor = L.piezo_ao_min_v + R.piezo_headroom_v
    if piezo.min() < floor:
        raise SafetyViolation(
            f"refusing {mode} trajectory: it would reach {piezo.min():.4f} V, "
            f"below the {floor:.4f} V working floor. Contact was made too low "
            f"in the piezo range for this excursion.")
    if piezo.max() > L.piezo_ao_max_v:
        raise SafetyViolation(
            f"refusing {mode} trajectory: it would reach {piezo.max():.4f} V, "
            f"above the {L.piezo_ao_max_v} V ceiling. A push segment from "
            f"this contact point would over-extend the piezo.")

    pre = np.repeat([[start_piezo_v], [bias[0]]], R.pre_pad_samples, axis=1) \
        if R.pre_pad_samples else np.zeros((2, 0))
    post = np.repeat([[piezo[-1]], [bias[-1]]], R.post_pad_samples, axis=1) \
        if R.post_pad_samples else np.zeros((2, 0))
    waveform = np.concatenate([pre, np.stack([piezo, bias]), post], axis=1)

    lo, hi = L.piezo_ao_min_v, L.piezo_ao_max_v
    if waveform[M.ROW_PIEZO].min() < lo or waveform[M.ROW_PIEZO].max() > hi:
        log.warning("clamping %s piezo trajectory into [%.3f, %.3f] V",
                    mode, lo, hi)
        waveform[M.ROW_PIEZO] = np.clip(waveform[M.ROW_PIEZO], lo, hi)

    return ModeRamp(mode=mode, waveform=waveform,
                    pre_pad=R.pre_pad_samples, n_pull=n,
                    spike_front=R.pre_pad_samples + front,
                    start_piezo_v=start_piezo_v,
                    end_piezo_v=float(piezo[-1]),
                    segments=segments, meta=meta or {})


def _dv(cfg: RigConfig, fs: float) -> float:
    """Piezo volts per sample. Igor: DeltaEx, line 1458."""
    return cfg.ramp.pull_rate_nm_per_s / cfg.cal.piezo_nm_per_volt / fs


# --------------------------------------------------------------------------
# Push-pull  (Igor 1461-1495)
# --------------------------------------------------------------------------

def build_push_pull(cfg: RigConfig, start_piezo_v: float,
                    pp: PushPullConfig | None = None,
                    sample_rate_hz: float | None = None) -> ModeRamp:
    """Initial pull, then per cycle {hold, push back in, hold, pull out},
    then a final pull. Bias constant throughout.

    Igor left the segment lengths at 0 until the GUI set them
    (Functions_STMBJ.ipf:91-96); the defaults here are working values, not
    Igor's.
    """
    pp = pp or cfg.push_pull
    fs = sample_rate_hz or cfg.ramp.sample_rate_hz
    dv = _dv(cfg, fs)

    n_init = _n_points(pp.initial_pull_nm, cfg, fs)
    n_pp = _n_points(pp.push_pull_nm, cfg, fs)
    n_hold = _n_points(pp.hold_nm, cfg, fs)
    n_final = _n_points(pp.final_pull_nm, cfg, fs)
    if min(n_init, n_pp, n_hold, n_final) < 1 or pp.cycles < 1:
        raise ValueError("push-pull: every segment needs at least one point "
                         "and cycles >= 1")

    n = n_init + pp.cycles * 2 * (n_pp + n_hold) + n_final
    rel = np.empty(n, dtype=float)
    segments: dict[str, tuple[int, int]] = {}

    rel[:n_init] = -np.arange(n_init) * dv
    segments["initial_pull"] = (0, n_init)

    i0 = n_init
    for k in range(pp.cycles):
        i1, i2 = i0 + n_hold, i0 + n_hold + n_pp
        i3, i4 = i2 + n_hold, i2 + n_hold + n_pp
        held_low = rel[i0 - 1]
        rel[i0:i1] = held_low                                   # hold (out)
        rel[i1:i2] = held_low + (np.arange(i1, i2) - i1) * dv   # push in
        held_high = rel[i2 - 1]
        rel[i2:i3] = held_high                                  # hold (in)
        rel[i3:i4] = held_high - (np.arange(i3, i4) - i3) * dv  # pull out
        segments[f"cycle{k}_hold_out"] = (i0, i1)
        segments[f"cycle{k}_push"] = (i1, i2)
        segments[f"cycle{k}_hold_in"] = (i2, i3)
        segments[f"cycle{k}_pull"] = (i3, i4)
        i0 = i4

    rel[i0:] = rel[i0 - 1] - (np.arange(i0, n) - i0) * dv
    segments["final_pull"] = (i0, n)

    bias = np.full(n, cfg.cal.bias_output_sign * cfg.ramp.bias_v)

    return _assemble(cfg, "push_pull", rel, bias, start_piezo_v, fs, segments,
                     meta={"cycles": pp.cycles})


# --------------------------------------------------------------------------
# IV sweep  (Igor 1497-1537)
# --------------------------------------------------------------------------

def build_iv(cfg: RigConfig, start_piezo_v: float,
             iv: IVConfig | None = None,
             sample_rate_hz: float | None = None) -> ModeRamp:
    """Pull, hold, sweep the bias in a triangle, hold, final pull.

    The bias ramp is Igor's, quarter by quarter: 0 -> +max over the first
    quarter of the ramp window, +max -> -max over the middle half,
    -max -> 0 over the last quarter -- then the *whole* bias wave is negated
    ("to have normal convention", Igor line 1533), which is what makes the
    default sweep run to the NEGATIVE apex first; ``positive_first``
    negates the ramp segment a second time (G_IVSignFlag). The caps either side
    of the sweep let the junction settle at DC before and after.

    Igor forced BiasSave and CurrentSave on for this mode; here the raw
    measured voltage and current are always stored, so nothing needs forcing.
    """
    iv = iv or cfg.iv
    fs = sample_rate_hz or cfg.ramp.sample_rate_hz
    dv = _dv(cfg, fs)

    n_init = _n_points(iv.init_pull_nm, cfg, fs)
    n_cap = _n_points(iv.cap_nm, cfg, fs)
    n_ramp = _n_points(iv.ramp_nm, cfg, fs)
    n_final = _n_points(iv.final_pull_nm, cfg, fs)
    if min(n_init, n_cap, n_final) < 1 or n_ramp < 8:
        raise ValueError("iv: init/cap/final need >= 1 point and the ramp "
                         "window >= 8 points")

    i1 = n_init
    i2 = i1 + n_cap
    i3 = i2 + n_ramp
    i4 = i3 + n_cap
    n = i4 + n_final

    rel = np.empty(n, dtype=float)
    rel[:i1] = -np.arange(i1) * dv
    rel[i1:i4] = rel[i1 - 1]
    # Igor line 1518: -(p - 2*NumIVCapPoints - NumIVRampPoints)*DeltaEx
    rel[i4:] = -(np.arange(i4, n) - 2 * n_cap - n_ramp) * dv

    # Bias, Igor lines 1526-1537. Built positive, then negated wholesale.
    bias = np.full(n, cfg.ramp.bias_v)
    q = n_ramp // 4                       # Igor indexed with NumIVRampPoints/4
    del_bias = 4.0 * iv.max_bias_v / n_ramp
    b1, b2, b3, b4 = i2, i2 + q, i3 - q, i3
    p = np.arange(n)
    bias[b1:b2] = (p[b1:b2] - i2) * del_bias
    bias[b2:b3] = iv.max_bias_v - (p[b2:b3] - i2 - n_ramp / 4) * del_bias
    bias[b3:b4 + 1] = -iv.max_bias_v + \
        (p[b3:b4 + 1] - i2 - 3 * n_ramp / 4) * del_bias

    bias *= -1.0                           # Igor line 1533
    if iv.positive_first:                  # G_IVSignFlag, line 1535
        bias[b1:b4 + 1] *= -1.0

    segments = {"init_pull": (0, i1), "cap_in": (i1, i2),
                "iv_ramp": (i2, i3), "cap_out": (i3, i4),
                "final_pull": (i4, n)}
    return _assemble(cfg, "iv", rel, bias, start_piezo_v, fs, segments,
                     meta={"max_bias_v": iv.max_bias_v,
                           "positive_first": iv.positive_first,
                           "quarters": (b1, b2, b3, b4)})


# --------------------------------------------------------------------------
# AC hold  (Igor 1539-1564)
# --------------------------------------------------------------------------

def build_ac_hold(cfg: RigConfig, start_piezo_v: float,
                  ac: ACHoldConfig | None = None,
                  sample_rate_hz: float | None = None) -> ModeRamp:
    """Pull, hold while the bias is a pure sine, final pull.

    During the hold the sine *replaces* the DC baseline entirely
    (Igor line 1564) -- there is no DC offset under the modulation.
    ``freq_khz`` is in kHz, as Igor's G_ACFreq was.
    """
    ac = ac or cfg.ac_hold
    fs = sample_rate_hz or cfg.ramp.sample_rate_hz
    dv = _dv(cfg, fs)

    n_init = _n_points(ac.init_pull_nm, cfg, fs)
    n_cap = _n_points(ac.cap_nm, cfg, fs)
    n_hold = _n_points(ac.hold_nm, cfg, fs)
    n_final = _n_points(ac.final_pull_nm, cfg, fs)
    if min(n_init, n_cap, n_hold, n_final) < 1:
        raise ValueError("ac_hold: every segment needs at least one point")

    i1 = n_init
    i2 = i1 + n_cap
    i3 = i2 + n_hold
    i4 = i3 + n_cap
    n = i4 + n_final

    rel = np.empty(n, dtype=float)
    rel[:i1] = -np.arange(i1) * dv
    rel[i1:i4] = rel[i1 - 1]
    rel[i4:] = -(np.arange(i4, n) - 2 * n_cap - n_hold) * dv

    bias = np.full(n, cfg.cal.bias_output_sign * cfg.ramp.bias_v)
    t = np.arange(n_hold)
    bias[i2:i3] = ac.amp_v * np.sin(
        2 * np.pi * ac.freq_khz * 1000.0 * t / fs)   # Igor line 1564

    segments = {"init_pull": (0, i1), "cap_in": (i1, i2),
                "ac_hold": (i2, i3), "cap_out": (i3, i4),
                "final_pull": (i4, n)}
    return _assemble(cfg, "ac_hold", rel, bias, start_piezo_v, fs, segments,
                     meta={"amp_v": ac.amp_v, "freq_hz": ac.freq_khz * 1e3})


# --------------------------------------------------------------------------
# High-bias hold  (Igor 1566-1599)
# --------------------------------------------------------------------------

def build_hb_hold(cfg: RigConfig, start_piezo_v: float,
                  hb: HBHoldConfig | None = None,
                  sample_rate_hz: float | None = None,
                  vzero_mv: float | None = None) -> ModeRamp:
    """Pull, hold at an elevated DC bias, final pull.

    ``hold_bias_v`` is in volts (Igor's G_HBBias) and is written as
    ``-hold_bias_v``, the same sign convention as the baseline. If Igor's
    Voltage_Offset panel had VzeroCheckBox ticked, the hold bias became the
    measured Vzero (lines 1595-1599); pass ``vzero_mv`` (from
    ``vzero.measure_offset``) to reproduce that.
    """
    hb = hb or cfg.hb_hold
    fs = sample_rate_hz or cfg.ramp.sample_rate_hz
    dv = _dv(cfg, fs)

    n_init = _n_points(hb.init_pull_nm, cfg, fs)
    n_cap_in = _n_points(hb.cap_in_nm, cfg, fs)
    n_cap_fin = _n_points(hb.cap_fin_nm, cfg, fs)
    n_hold = _n_points(hb.hold_nm, cfg, fs)
    n_final = _n_points(hb.final_pull_nm, cfg, fs)
    if min(n_init, n_cap_in, n_cap_fin, n_hold, n_final) < 1:
        raise ValueError("hb_hold: every segment needs at least one point")

    i1 = n_init
    i2 = i1 + n_cap_in
    i3 = i2 + n_hold
    i4 = i3 + n_cap_fin
    n = i4 + n_final

    rel = np.empty(n, dtype=float)
    rel[:i1] = -np.arange(i1) * dv
    rel[i1:i4] = rel[i1 - 1]
    rel[i4:] = -(np.arange(i4, n) - (n_cap_in + n_cap_fin) - n_hold) * dv

    hold_bias_v = hb.hold_bias_v
    if vzero_mv is not None:               # Igor lines 1595-1599
        hold_bias_v = vzero_mv / 1000.0

    bias = np.full(n, cfg.cal.bias_output_sign * cfg.ramp.bias_v)
    bias[i2:i3] = -hold_bias_v             # Igor line 1592

    segments = {"init_pull": (0, i1), "cap_in": (i1, i2),
                "hb_hold": (i2, i3), "cap_out": (i3, i4),
                "final_pull": (i4, n)}
    return _assemble(cfg, "hb_hold", rel, bias, start_piezo_v, fs, segments,
                     meta={"hold_bias_v": hold_bias_v,
                           "from_vzero": vzero_mv is not None})
