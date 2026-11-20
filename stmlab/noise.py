"""The frequencies in a record: an averaged spectrum and its biggest peaks.

For noisecheck.py. Numpy only, no card, no window: everything here is a plain
function of arrays, so it can be tested without either.

Why the tunnelling current. With the tip a fraction of a nanometre off the
surface the current falls by about a factor of ten for every tenth of a
nanometre of gap. So anything that shakes the tip against the sample shows
in the current long before it shows anywhere else, and the Fourier transform
of the current says at which frequencies it shakes. What the transform
cannot say by itself is whether a line is the gap moving or the amplifier
picking something up: for that the same record is taken with the tip far
away (the reference). A line that is there with the junction open is
electrical. Mains (60 Hz, or 50, and its multiples) is the usual one.
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np


class Peak(NamedTuple):
    """One line of a spectrum."""
    hz: float          # its frequency, read between the bins
    amp: float         # its amplitude, in the units of the record
    over: float        # how many times it stands above the floor around it


def amplitude_spectrum(pieces, rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """(frequencies in Hz, amplitude) of a record given as pieces: a list
    of 1-D arrays of the same length (or a 2-D array, one piece a row),
    each sampled at ``rate_hz`` without a gap inside it. Gaps BETWEEN the
    pieces do not matter, which is why a record is taken as several plays.

    Each piece has its straight-line trend taken off (a drifting tunnelling
    current would otherwise smear over the low frequencies), is weighted
    with a Hann window and Fourier transformed. The POWERS of the pieces
    are averaged: a steady line stays, the noise around it gets smoother
    with every piece. The resolution is 1 / (the length of a piece).

    Scaled so that a steady sine of amplitude A reads A at its frequency
    when it falls on a bin, and 15 % less at worst between two bins
    (``find_peaks`` makes up for that).
    """
    rows = [np.asarray(p, dtype=float).ravel() for p in pieces]
    if not rows:
        raise ValueError("no pieces")
    n = min(r.size for r in rows)
    if n < 16:
        raise ValueError(f"a piece of {n} samples is too short for a spectrum")
    window = np.hanning(n)
    ramp = np.arange(n) - (n - 1) / 2.0
    power = np.zeros(n // 2 + 1)
    for r in rows:
        r = r[:n]
        r = np.where(np.isfinite(r), r, np.nanmean(r) if np.isfinite(r).any() else 0.0)
        r = r - r.mean()
        r = r - ramp * (ramp @ r) / (ramp @ ramp)
        power += np.abs(np.fft.rfft(r * window)) ** 2
    amp = 2.0 / window.sum() * np.sqrt(power / len(rows))
    amp[0] = 0.0
    return np.fft.rfftfreq(n, 1.0 / rate_hz), amp


def _floor(amp: np.ndarray, half: int = 20) -> np.ndarray:
    """The level of the noise around each bin: the median of its
    neighbours, 20 bins either side (fewer near 0 Hz, where a spectrum
    climbs steeply and far-off bins would say nothing about this one)."""
    n = amp.size
    floor = np.empty(n)
    if n > 2 * half + 1:
        view = np.lib.stride_tricks.sliding_window_view(amp, 2 * half + 1)
        floor[half:n - half] = np.median(view, axis=1)
        floor[n - half:] = floor[n - half - 1]
    for i in range(min(n, 2 * half)):
        h = max(4, i // 2)
        near = amp[max(1, i - h):i + h + 1]
        floor[i] = np.median(near) if near.size else 0.0
    return floor


def find_peaks(freqs: np.ndarray, amp: np.ndarray, count: int = 8,
               lo_hz: float | None = None, hi_hz: float | None = None,
               stand_out: float = 5.0) -> list[Peak]:
    """The ``count`` biggest lines of a spectrum, biggest first.

    A line is a bin higher than both its neighbours that stands at least
    ``stand_out`` times above the floor around it (``_floor``). Its
    frequency is read between the bins (the Hann window's own
    interpolation), and its amplitude is taken from the bin and its two
    neighbours together, which gives a sine's amplitude to a per cent
    wherever between two bins it falls. ``lo_hz`` defaults to one and a
    half bins: the two lowest bins are what is left of the drift.
    """
    freqs, amp = np.asarray(freqs, dtype=float), np.asarray(amp, dtype=float)
    n = amp.size
    if n < 8:
        return []
    step = float(freqs[1] - freqs[0])
    lo = 1.5 * step if lo_hz is None else float(lo_hz)
    hi = float(freqs[-1]) if hi_hz is None else float(hi_hz)
    floor = _floor(amp)
    i = np.arange(1, n - 1)
    is_top = (amp[i] >= amp[i - 1]) & (amp[i] > amp[i + 1])
    in_band = (freqs[i] >= lo) & (freqs[i] <= hi)
    stands = (floor[i] > 0) & (amp[i] >= stand_out * floor[i])
    found = i[is_top & in_band & stands]
    taken: list[int] = []
    for k in found[np.argsort(amp[found])[::-1]]:
        if all(abs(int(k) - j) > 3 for j in taken):
            taken.append(int(k))
        if len(taken) >= count:
            break
    peaks = []
    for k in taken:
        left, mid, right = amp[k - 1], amp[k], amp[k + 1]
        if right >= left:
            shift = (2.0 * right - mid) / (right + mid) if right + mid > 0 else 0.0
        else:
            shift = -(2.0 * left - mid) / (left + mid) if left + mid > 0 else 0.0
        shift = float(np.clip(shift, -0.5, 0.5))
        size = float(np.sqrt((left ** 2 + mid ** 2 + right ** 2) / 1.5))
        peaks.append(Peak(hz=float(freqs[k] + shift * step), amp=size,
                          over=float(mid / floor[k])))
    return peaks


def guess_mains(freqs: np.ndarray, amp: np.ndarray) -> float:
    """60 or 50: which mains this record has in it, by how far the first
    three multiples of each stand above the floor. 60 when neither shows."""
    freqs, amp = np.asarray(freqs, dtype=float), np.asarray(amp, dtype=float)
    if amp.size < 8:
        return 60.0
    step = float(freqs[1] - freqs[0])
    floor = _floor(amp)

    def score(mains: float) -> float:
        best = 0.0
        for k in (1, 2, 3):
            j = int(round(k * mains / step))
            if 1 <= j < amp.size - 1:
                near = slice(j - 1, j + 2)
                top = float(np.max(amp[near]))
                level = float(np.median(floor[near]))
                if level > 0:
                    best = max(best, top / level)
        return best
    s60, s50 = score(60.0), score(50.0)
    return 50.0 if s50 > max(s60, 5.0) else 60.0


def multiple_of(hz: float, base_hz: float, tol_hz: float, up_to: int = 12) -> int:
    """k when ``hz`` is k times ``base_hz`` to within ``tol_hz`` (k from 1
    to ``up_to``), else 0."""
    if base_hz <= 0:
        return 0
    k = int(round(hz / base_hz))
    return k if 1 <= k <= up_to and abs(hz - k * base_hz) <= tol_hz else 0


def band_hint(hz: float) -> str:
    """What a line at ``hz`` usually is on an STM, in a few words. A hint
    for where to look, not a finding."""
    if hz < 2.0:
        return "slow swing of the rig, or drift"
    if hz < 20.0:
        return "bounce on the suspension, the floor"
    if hz < 200.0:
        return "machines, or a part of the rig ringing"
    return "sound, or a stiff part ringing"


def describe(peaks: list[Peak], mains_hz: float, step_hz: float) -> list[str]:
    """One word or two for each of ``peaks`` (in the same order): "mains"
    for a multiple of the mains frequency, "2 x 7.50 Hz" for a multiple of
    a bigger line in the list (a gap that shakes at one frequency gives the
    current its multiples too, because the current is not a straight line
    in the gap), else where such a line usually comes from."""
    tol = max(0.75 * step_hz, 0.3)
    words = []
    for n, p in enumerate(peaks):
        k = multiple_of(p.hz, mains_hz, tol)
        if k:
            words.append("mains" if k == 1 else f"mains x {k}")
            continue
        of = ""
        for q in peaks[:n]:
            if multiple_of(q.hz, mains_hz, tol):
                continue
            m = multiple_of(p.hz, q.hz, tol, up_to=8)
            if m >= 2:
                of = f"{m} x {q.hz:.2f} Hz"
                break
        words.append(of or band_hint(p.hz))
    return words


def thin(t, y, points: int = 4000) -> tuple[np.ndarray, np.ndarray]:
    """A long record cut down for a plot without losing its spikes: the
    lowest and the highest sample of each stretch, in the order they came."""
    t, y = np.asarray(t, dtype=float), np.asarray(y, dtype=float)
    n = y.size
    if n <= points:
        return t, y
    chunk = int(np.ceil(n / (points // 2)))
    whole = (n // chunk) * chunk
    yy = y[:whole].reshape(-1, chunk)
    tt = t[:whole].reshape(-1, chunk)
    rows = np.arange(yy.shape[0])
    lo, hi = np.nanargmin(yy, axis=1), np.nanargmax(yy, axis=1)
    first, second = np.minimum(lo, hi), np.maximum(lo, hi)
    out_t = np.column_stack([tt[rows, first], tt[rows, second]]).ravel()
    out_y = np.column_stack([yy[rows, first], yy[rows, second]]).ravel()
    return out_t, out_y
