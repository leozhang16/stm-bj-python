"""STM-BJ noise check: at which frequencies does the junction shake?

    python noisecheck.py --simulate
    python noisecheck.py --config configs/labpc_rig.json

Close pullout (and Igor) first: only one program can have the card.

The tunnelling current is the most sensitive vibration meter on the rig. With
the tip a fraction of a nanometre off the surface it changes by about a
factor of ten for every tenth of a nanometre of gap. So this program brings
the tip to the edge of contact, holds the piezo still, records the current
and takes its Fourier transform. Lines in the spectrum are the frequencies
at which the gap moves, or at which the amplifier picks something up.

The window, top to bottom:

    Junction     OPEN / TUNNELLING / CONTACT, the current, G, the piezo
    Piezo driver standard or bypass and the total displacement, as in
                 pullout's Piezo box (every distance here hangs on it)
    1. Get to the edge of contact
                 Approach (the piezo comes up to the surface and stops at
                 contact), Find the edge (retracts from the contact in
                 0.1 nm steps until the junction lets go), Step apart and
                 Step closer by hand, Calibrate zero, Stop
    2. Record    which signal, for how long; Record takes it in pieces of
                 4 s and averages their spectra; Save, Keep as reference,
                 Load a reference, Clear
    plots        the signal against time (live while idle), and the
                 spectrum with its biggest lines labelled in Hz; the
                 reference in grey behind it
    the list     the biggest lines: frequency, size, about how many
                 picometres of gap, and what each may be

The reference is how a line is told apart. Record once with the tip far
away (the junction open) and keep it as the reference. A line that is in
both is electrical: the gap cannot shake a current that is not flowing.
Mains (60 Hz, or 50, and its multiples) is the usual one and is marked. A
line that is only there at the edge of contact is the gap moving.

A saved spectrum can be loaded as the reference later: record, Save, change
the suspension, record again with the old one loaded, and the two are on
one plot.

With a two-channel amplifier the signal is channel 2, its high-gain output:
a tunnelling current is a few nanoamps to a few hundred, which is nothing on
channel 1. Whether the junction is open, tunnelling or closed is read from
channel 2 as well, while it is below its rail, and from channel 1 above.

Moves are pullout's own (its Worker: the guarded move toward the surface,
the three signs of contact, the piezo's limits), so nothing here moves the
piezo in a way pullout would not. With --simulate the pretend tip is shaken
and the pretend amplifier hums, so that there is something to find; the
simulator's two boxes set how much.
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import queue
import sys
import time
from pathlib import Path
from typing import NamedTuple

import numpy as np

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pullout                                                      # noqa: E402
from stmlab import noise                                            # noqa: E402
from stmlab.config import ConfigError, G0_SIEMENS, RigConfig        # noqa: E402
from stmlab.safety import SafetyViolation                           # noqa: E402
from stmlab.tklook import windows_look                              # noqa: E402

log = logging.getLogger("noisecheck")

# The repo's version: the same number as pullout and rigcheck.
__version__ = pullout.__version__

# The signals a record holds, in the units they are shown in.
SIGNALS = {"i1": "current ch 1 (nA)",
           "i2": "current ch 2 (nA)",
           "gap": "gap (pm)",
           "v": "junction voltage (mV)",
           "z": "piezo sense (nm)"}
UNITS = {"i1": "nA", "i2": "nA", "gap": "pm", "v": "mV", "z": "nm"}

# Above this conductance the junction counts as closed, below the config's
# break threshold as open, and in between as tunnelling.
CLOSED_G0 = 0.5
# Find the edge retracts until the conductance is at or under this. Much
# above a tenth of G0 two gold surfaces tend to jump back together, and a
# tip that is being shaken needs room on both sides.
EDGE_G0 = 0.1
# The tunnelling current falls by a factor of ten over this much gap. 0.1 nm
# is the vacuum value; in air it is more like 0.2 to 0.3 nm, so the
# picometres here are a low estimate there.
NM_PER_DECADE = 0.1
# The spectrum is drawn, and its lines looked for, up to this frequency.
TOP_HZ = 5000.0


# --------------------------------------------------------------------------
# The simulator: something to find
# --------------------------------------------------------------------------

class SimShake:
    """Simulation only. Shakes the pretend tip against the pretend surface
    and adds mains hum to the pretend amplifier's output, so that the
    program has lines to find on a MacBook: one that is the gap moving, one
    that is electrical.

    It stands between the rig and the simulated card (``session.play``).
    The shake is added to the piezo's position, in nanometres; the hum to
    the current input, in nanoamps, whatever the junction does. Time runs
    on a clock of its own (the samples played, plus the 15 ms a real card
    takes between two plays), because a simulated play takes none."""

    def __init__(self, session, cfg: RigConfig):
        self.session, self.cfg = session, cfg
        self.shake_nm, self.shake_hz = 0.02, 7.5
        self.hum_na, self.mains_hz = 1.0, 60.0
        self.samples = 0
        self._play = session.play
        session.play = self.play
        # Clean gold: a molecule's plateau does not change with the gap,
        # and a junction sitting on one would show no shake at all.
        if hasattr(session, "p_molecule"):
            session.p_molecule = 0.0

    def play(self, waveform, *args, **kwargs):
        wave = np.array(waveform, dtype=float, copy=True)
        n = wave.shape[1]
        rate = float(getattr(self.session, "effective_rate_hz",
                             self.cfg.ramp.sample_rate_hz))
        t = (self.samples + np.arange(n)) / rate
        self.samples += n + int(0.015 * rate)
        C, M = self.cfg.cal, self.cfg.channels
        if self.shake_nm > 0 and self.shake_hz > 0:
            wave[M.ROW_PIEZO] += (self.shake_nm / C.piezo_nm_per_volt
                                  * np.sin(2 * np.pi * self.shake_hz * t))
        record = self._play(wave, *args, **kwargs)
        # What the tracker believes is the command, not the shaken position.
        self.session.piezo_nm = float(np.asarray(waveform)[M.ROW_PIEZO, -1]
                                      * C.piezo_nm_per_volt)
        if self.hum_na > 0:
            hum_a = self.hum_na * 1e-9 * np.sin(2 * np.pi * self.mains_hz * t)
            limit = M.ai_range_v
            record[M.ROW_CURRENT] = np.clip(
                record[M.ROW_CURRENT] + C.sign_of(1) * hum_a * C.gain_of(1),
                -limit, limit)
            second = getattr(self.session, "last_current2_v", None)
            if second is not None and np.size(second) == n:
                self.session.last_current2_v = np.clip(
                    second + C.sign_of(2) * hum_a * C.gain_of(2), -limit, limit)
        return record


# --------------------------------------------------------------------------
# The worker: pullout's, with a few commands of its own
# --------------------------------------------------------------------------

class Watch(NamedTuple):
    """What a few looks at the junction in a row saw (``NoiseWorker._watch``)."""
    words: list          # contact, tunnelling or open, for each look
    middle: float        # the middle one of the conductances, in G0
    high: float          # the highest of channel 1's conductances, in G0
    # Closed in some looks and open in others: the tip is shaken open and
    # shut, by more than a tunnelling current reaches. The sentence for the
    # status line, else "". (Closed in some and tunnelling in the others is
    # not that: it is the very edge of the contact, which a step apart mends.)
    chopping: str

    @property
    def word(self) -> str:
        """One word for all the looks together: contact when any look was
        closed, open when all were open."""
        if "contact" in self.words:
            return "contact"
        if "open" not in self.words:
            return "tunnelling"
        return "open" if "tunnelling" not in self.words else "in and out of tunnelling"

    @property
    def clear(self) -> bool:
        """Is there nothing to retract from? The junction is at or under
        ``EDGE_G0`` in every look; or it is open in some, where a step
        apart only opens it more."""
        return bool(self.chopping) or self.high <= EDGE_G0 or "open" in self.words


class NoiseWorker(pullout.Worker):
    """pullout's worker (Approach, the steps, the driver's mode, the
    simulator's screw, all as they are there) with what this program adds:
    a live look at the inputs, the way from contact to its edge, and the
    record."""

    # A record is taken as plays of this length, one after the other: the
    # card does not play for longer than ten seconds at a time, and the
    # spectra of the pieces are averaged anyway (``noise.amplitude_spectrum``).
    # The resolution of the spectrum is 1 / PIECE_S: a quarter of a hertz,
    # which a suspension's bounce at one hertz or two needs.
    PIECE_S = 4.0
    # The longest record: every signal of it is kept in memory (2 MB a second).
    LONGEST_S = 120.0
    LIVE_S = 0.25
    # Find the edge: one step, and how far apart it goes before giving up.
    # The card rounds a step to its own (0.33 nm on a 16-bit output at a
    # micrometre to the volt), so some of these steps move nothing.
    EDGE_STEP_NM = 0.1
    EDGE_REACH_NM = 30.0
    # A tunnelling current worth recording: at least this, which is ten
    # times the break threshold. It is well under a tenth of ``EDGE_G0``,
    # so that a junction that lets go a step at a time (a decade a step)
    # is not sent back and forth between the two.
    AIM_G0 = 0.005
    # Before Find the edge moves anything, and when it has ended, it looks
    # at the junction this many times in a row (``_watch``).
    EDGE_LOOKS = 6

    def _grab(self, n: int) -> dict:
        """One quiet hold of ``n`` samples where the piezo is: every signal
        in the units it is shown in (``SIGNALS``). Nothing moves, and the
        hold is kept out of pullout's cycle log."""
        self.mon.quiet = True
        try:
            rec = self.rig.hold(n_samples=n)
        finally:
            self.mon.quiet = False
        M, C = self.cfg.channels, self.cfg.cal
        out = {"i1": np.asarray(C.volts_to_amps(rec[M.ROW_CURRENT])) * 1e9,
               "v": C.voltage_input_sign * rec[M.ROW_VOLTAGE] * 1e3}
        second = self.rig.last_current2_v
        if second is not None and np.size(second) == n:
            # Channel 2 of a two-channel amplifier, and where it was at its
            # rail (there the current is beyond it, and channel 1 has it).
            second = np.asarray(second, dtype=float)
            out["i2"] = np.asarray(C.volts_to_amps(second, channel=2)) * 1e9
            out["railed2"] = np.abs(second) >= self.cfg.limits.preamp_saturation_v
        sense = self.rig.last_sense_v
        if sense is not None and np.size(sense) == n:
            out["z"] = np.asarray(C.sense_volts_to_nm(np.asarray(sense, dtype=float)))
        return out

    def status(self, text: str, level: str | None = None) -> None:
        """pullout's status lines, except where they speak of pullout's own
        window (its fine slider, Start N): here the next thing to do after a
        contact is Find the edge."""
        for theirs, ours in (
                ("The piezo stays there and the fine slider is around it. Now "
                 "Start N", "The piezo stays there. Now Find the edge"),
                ("Step apart first, or Start N", "Now Find the edge"),
                ("That is too low in the range to pull from: turn",
                 "That is at the bottom of the piezo's range, with no room to "
                 "retract: turn")):
            text = text.replace(theirs, ours)
        super().status(text, level)

    def word_for(self, g0: float, best: float | None = None) -> str:
        """contact, tunnelling or open. ``g0`` is channel 1's conductance,
        which is the one that is good in contact; ``best`` the reading of
        the junction-open test (``Rig.open_side``: channel 2 of a
        two-channel amplifier while it is below its rail), which is the one
        that is good at a few nanoamps. Contact is above 0.5 G0, open below
        the config's break threshold, tunnelling in between."""
        if not g0 <= CLOSED_G0:                   # above it, or not a number
            return "contact"
        return ("open" if (g0 if best is None else best) < self.cfg.ramp.break_g0
                else "tunnelling")

    def _settle_by_hand(self) -> tuple[float, str, str]:
        """pullout's, with this program's word for the junction. pullout
        calls a junction closed above its contact current (0.15 uA), which
        at 0.1 V is a few hundredths of a G0: for a move made by hand that
        is the right place to stop, and here it is a tunnelling current,
        the thing being looked for."""
        g0, _word, second = super()._settle_by_hand()
        return g0, self.word_for(g0, self.rig.open_side()[0]), second

    def _look(self, piezo_v: float | None = None) -> tuple[float, float]:
        """One hold, after a step to ``piezo_v`` when that is given:
        (channel 1's conductance, the junction-open test's reading). Kept
        out of pullout's cycle log, which this window does not show."""
        self.mon.quiet = True
        try:
            record = self.rig.hold(piezo_v=piezo_v)
        finally:
            self.mon.quiet = False
        return self.rig.conductance_of(record), self.rig.open_side_of(record)[0]

    def _watch(self) -> "Watch":
        """A few looks one after the other, where the piezo is (``Watch``).

        One look is 5 ms of the junction. A tip that is shaken is closer in
        one look than in the next, and a single look would call the junction
        whatever it happened to catch."""
        looks = [self._look() for _ in range(self.EDGE_LOOKS)]
        words = [self.word_for(g1, best) for g1, best in looks]
        closed = words.count("contact")
        chopping = ""
        if closed and "open" in words:
            low = min(best for _g1, best in looks)
            high = max(g1 for g1, _best in looks)
            chopping = (f"opens and closes by itself at {self.rig.piezo_v:.4f} V: "
                        f"closed in {closed} of {len(words)} looks (G {low:.1e} to "
                        f"{high:.1e} G0). The tip shakes by more than the "
                        "tunnelling range. Record as it is: the frequencies will "
                        "be right")
        return Watch(words, float(np.median([best for _g1, best in looks])),
                     max(g1 for g1, _best in looks), chopping)

    def cmd_begin(self) -> None:
        """What the window asks for first: the amplifier's zero, as
        Calibrate zero measures it, unless the junction is closed (a contact
        passes the amplifier's own offset current even at 0 V bias, and the
        zero would have that in it)."""
        if self.bias_dirty:
            self.cmd_bias()
        self.mon.quiet = True
        try:
            why = self._closed(self.rig.hold())
        finally:
            self.mon.quiet = False
        if why:
            self.status(f"the junction is closed at the start ({why}): the "
                        "amplifier's zero was NOT measured. Step apart, or turn "
                        "the screw back, then Calibrate zero", "warn")
            return
        self.cmd_zero()

    def cmd_scope(self) -> None:
        """A quarter of a second of every input, for the live picture."""
        if self.bias_dirty:
            self.cmd_bias()
        rate = self.rig.sample_rate_hz
        self.post("scope", rate=rate, piece=None, of=None,
                  signals=self._grab(int(round(self.LIVE_S * rate))))

    def cmd_edge(self) -> None:
        """Find the edge: "make contact, then retract a little".

        From contact the piezo goes apart in steps of 0.1 nm until the
        conductance is at or below 0.1 G0 (``EDGE_G0``) in every one of a
        few looks in a row (``_watch``): a tip that is being shaken a
        little is then clear of the contact over its whole swing.

        A gold contact often lets go all at once and is then open by more
        than a tunnelling current reaches. So from there the piezo comes
        back toward the surface, in the same steps, until there is one (G
        of 0.005 G0 or more, ``AIM_G0``), and never further than where the
        contact was. If the junction closes again on the way, it goes back
        out and says that there is no place in between.

        A junction that is closed in some looks and open in others is being
        shaken open and shut, which no step of the piezo mends. Find the
        edge then stays where it is and says so.

        It gives up 30 nm from the contact, and at the bottom of the
        piezo's range. Stop ends it between two steps."""
        C, L = self.cfg.cal, self.cfg.limits
        self._begin_by_hand()

        def here() -> str:
            return f"{self.rig.piezo_v:.4f} V = {self.rig.piezo_nm:.1f} nm"
        seen = self._watch()
        if seen.clear:
            # Nothing to retract from: shaken open and shut, or clear of the
            # contact already, or open (for part of the swing, or all of it).
            self._settle_by_hand()
            if seen.chopping:
                self.status(seen.chopping, "warn")
            elif seen.word == "open":
                self.status(f"Find the edge: the junction is open (G = "
                            f"{seen.middle:.2e} G0). Press Approach first; Find "
                            "the edge then retracts from the contact", "warn")
            else:
                self.status(f"already at the edge of contact: G = {seen.middle:.2e} "
                            f"G0 ({seen.word}) at {here()}. Now Record", "ok")
            return
        start = self.rig.piezo_v
        step_v = C.nm_to_piezo_volts(self.EDGE_STEP_NM)
        self.status(f"retracting from the contact in steps of {self.EDGE_STEP_NM:g} "
                    "nm ... (Stop ends it)", "busy")

        def apart() -> str:
            """Step apart until the junction is clear of the contact
            (``Watch.clear``): at or under ``EDGE_G0`` in every look of a
            watch, or open in some."""
            nonlocal seen
            while True:
                if self.stop_flag.is_set():
                    return "stop"
                if (start - self.rig.piezo_v) * C.piezo_nm_per_volt \
                        >= self.EDGE_REACH_NM - 1e-6:
                    return "far"
                if self.rig.piezo_v - step_v < L.piezo_ao_min_v:
                    return "bottom"
                g1, _best = self._look(self.rig.piezo_v - step_v)
                if g1 <= EDGE_G0:
                    seen = self._watch()
                    if seen.clear:
                        return "edge"

        ended = apart()
        came_back = False
        if ended == "edge" and not seen.chopping and seen.middle < self.AIM_G0:
            # It let go all at once. Back toward the surface, a step at a
            # time, for a tunnelling current; not past where the contact was.
            self.status(f"it let go all at once (G = {seen.middle:.2e} G0): coming "
                        f"back in steps of {self.EDGE_STEP_NM:g} nm for a "
                        "tunnelling current ... (Stop ends it)", "busy")
            g1, best = 0.0, seen.middle
            while best < self.AIM_G0 and g1 <= CLOSED_G0 \
                    and self.rig.piezo_v + step_v <= start + 1e-12:
                if self.stop_flag.is_set():
                    ended = "stop"
                    break
                g1, best = self._look(self.rig.piezo_v + step_v)
            if ended == "edge":
                seen = self._watch()
                if seen.word == "contact" and not seen.chopping:
                    came_back = True              # closed again: out once more
                    ended = apart()
        self._settle_by_hand()
        if ended != "edge":
            seen = self._watch()                  # where it gave up, as it is now
        word = seen.word
        went = (start - self.rig.piezo_v) * C.piezo_nm_per_volt
        where = (f"retracted {went:.1f} nm to {here()}, G = {seen.middle:.2e} G0 "
                 f"({word})")
        if ended == "stop":
            self.status(f"Find the edge stopped by Stop: {where}", "warn")
        elif ended == "bottom":
            self.status(f"still closed with the piezo at the bottom of its range: "
                        f"{where}. Turn the screw back a little, then Approach "
                        "again", "warn")
        elif ended == "far":
            self.status(f"still closed: {where}. Press Find the edge again, or "
                        "Step apart by hand", "warn")
        elif seen.chopping:
            self.status(seen.chopping, "warn")
        elif word == "contact":
            self.status(f"it closed again: {where}. Press Find the edge once more",
                        "warn")
        elif word != "open":
            self.status(f"at the edge of contact: {where}. Now Record", "ok")
        elif came_back:
            self.status(f"no place in between here: {where}, and one step closer "
                        "it is closed. Record as it is, or try Step closer", "warn")
        else:
            self.status(f"open again where the contact was: {where}. The tip has "
                        "changed: press Approach again", "warn")

    def cmd_record(self, seconds: float = 16.0) -> None:
        """Record: hold the piezo where it is and take ``seconds`` of every
        input, as pieces of ``PIECE_S``. Nothing moves. Stop ends it after
        the piece in hand, and what was taken is still shown."""
        if self.bias_dirty:
            self.cmd_bias()
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            seconds = float("nan")
        if not self.PIECE_S <= seconds <= self.LONGEST_S:
            self.status(f"Record: the time is a number of seconds, {self.PIECE_S:g} "
                        f"to {self.LONGEST_S:g} (it is taken in pieces of "
                        f"{self.PIECE_S:g} s)", "bad")
            return
        rate = self.rig.sample_rate_hz
        count = max(1, int(round(seconds / self.PIECE_S)))
        n = int(round(self.PIECE_S * rate))
        here = f"{self.rig.piezo_v:.4f} V = {self.rig.piezo_nm:.1f} nm"
        self.status(f"recording {count} piece{'' if count == 1 else 's'} of "
                    f"{self.PIECE_S:g} s with the piezo at {here} ... do not "
                    "touch the rig (Stop ends it)", "busy")
        pieces = []
        for k in range(count):
            if self.stop_flag.is_set():
                break
            pieces.append(self._grab(n))
            self.post("scope", rate=rate, piece=k + 1, of=count, signals=pieces[-1])
        if not pieces:
            self.status("Record: stopped before the first piece", "warn")
            return
        self.post("noise", pieces=pieces, rate=rate, piece_s=self.PIECE_S,
                  piezo_v=self.rig.piezo_v, piezo_nm=self.rig.piezo_nm,
                  bias_mv=self.rig.bias_v * 1e3, when=time.time(),
                  break_g0=self.cfg.ramp.break_g0)
        self.status(f"recorded {len(pieces)} x {self.PIECE_S:g} s at {here}"
                    + (" (stopped early)" if len(pieces) < count else ""), "ok")


# --------------------------------------------------------------------------
# From a record to its lines
# --------------------------------------------------------------------------

def _smooth(x: np.ndarray, rate_hz: float) -> np.ndarray:
    """A millisecond's running mean (the same length as ``x``)."""
    box = max(1, int(round(0.001 * rate_hz)))
    if box <= 1 or x.size < box:
        return x
    return np.convolve(x, np.ones(box) / box, mode="same")


def best_current(piece: dict) -> np.ndarray:
    """The junction current of a piece, in nA, sample by sample from the
    channel that reads it best: channel 2 of a two-channel amplifier (its
    high-gain output) where that is below its rail, channel 1 where it is
    not, and channel 1 throughout on a one-channel rig. It is what the
    junction-open test does (``Rig.open_side_of``)."""
    current = np.asarray(piece["i1"], dtype=float)
    if "i2" in piece and "railed2" in piece:
        current = np.where(piece["railed2"], current, piece["i2"])
    return current


def with_gap(pieces: list[dict], rate_hz: float, break_g0: float) -> list[dict]:
    """Add the gap to every piece of a record: the tunnelling current read
    as a distance, in picometres, ``-NM_PER_DECADE * log10(G)``. G is the
    current (``best_current``) over the junction voltage, both averaged over
    a millisecond (so that the card's noise on an open junction is not read
    as a current), and is kept between the break threshold and 1 G0:
    outside that the junction is open or closed and the current says
    nothing about the gap."""
    for p in pieces:
        if "gap" in p:
            continue
        amps = np.abs(_smooth(best_current(p) * 1e-9, rate_hz))
        volts = np.maximum(np.abs(_smooth(np.asarray(p["v"], dtype=float) * 1e-3,
                                          rate_hz)), 1e-6)
        g0 = amps / volts / G0_SIEMENS
        p["g0"] = g0
        p["gap"] = -1000.0 * NM_PER_DECADE * np.log10(np.clip(g0, break_g0, 1.0))
    return pieces


def analyse(pieces: list[dict], rate_hz: float, key: str = "i1",
            break_g0: float = 5e-4, reference: dict | None = None,
            count: int = 8) -> dict:
    """The spectrum of one signal of a record and what there is to say
    about it. ``pieces`` is what Record took (``NoiseWorker.cmd_record``);
    ``reference`` an earlier result of this function, or a loaded spectrum
    (``freqs``, ``amp``), to tell electrical lines from the gap moving.

    Returns a dict: ``freqs``, ``amp`` (the spectrum), ``peaks`` (a list of
    dicts: ``hz``, ``amp``, ``over``, ``what``, ``share`` of the mean,
    ``pm`` of gap or None, ``in_reference``), ``mains``, ``mean``,
    ``shares`` (open, tunnelling, closed), ``railed`` (the share of the
    record channel 2 spent at its rail, when the signal is channel 2),
    ``step_hz``, ``pieces``, ``piece_s``, ``key``, ``unit``."""
    with_gap(pieces, rate_hz, break_g0)
    freqs, amp = noise.amplitude_spectrum([p[key] for p in pieces], rate_hz)
    step = float(freqs[1] - freqs[0])
    top = min(TOP_HZ, float(freqs[-1]))
    mains = noise.guess_mains(freqs, amp)
    found = noise.find_peaks(freqs, amp, count=count, hi_hz=top)
    words = noise.describe(found, mains, step)
    mean = float(np.mean([np.mean(p[key]) for p in pieces]))
    g0 = np.concatenate([p["g0"] for p in pieces])
    is_open = float(np.mean(g0 < break_g0))
    is_closed = float(np.mean(g0 > CLOSED_G0))
    shares = (is_open, max(0.0, 1.0 - is_open - is_closed), is_closed)
    railed = 0.0
    if key == "i2" and all("railed2" in p for p in pieces):
        railed = float(np.mean(np.concatenate([p["railed2"] for p in pieces])))
    # The gap's own spectrum, for the picometres of a line: only while the
    # junction was in tunnelling for most of the record.
    gap_f = gap_a = None
    if key in ("i1", "i2") and shares[1] >= 0.8:
        gap_f, gap_a = noise.amplitude_spectrum([p["gap"] for p in pieces], rate_hz)
    peaks = []
    biggest = max((p.amp for p in found), default=0.0)
    for p, what in zip(found, words):
        if p.amp < biggest / 1000.0:
            continue                    # a thousandth of the biggest line: not news
        in_ref = False
        if reference is not None and reference.get("unit") == UNITS[key]:
            ref = float(np.interp(p.hz, reference["freqs"], reference["amp"]))
            in_ref = ref >= 0.5 * p.amp
        pm = None
        if gap_a is not None and not what.startswith("mains") and not in_ref:
            j = int(round(p.hz / step))
            if 1 <= j < gap_a.size - 1:
                pm = float(np.sqrt(np.sum(gap_a[j - 1:j + 2] ** 2) / 1.5))
        peaks.append({"hz": p.hz, "amp": p.amp, "over": p.over, "what": what,
                      # of the mean, where the mean is a level and not a place
                      "share": (abs(p.amp / mean) if mean and key in ("i1", "i2", "v")
                                else float("nan")),
                      "pm": pm, "in_reference": in_ref})
    return {"freqs": freqs, "amp": amp, "peaks": peaks, "mains": mains,
            "mean": mean, "shares": shares, "railed": railed, "step_hz": step,
            "pieces": len(pieces), "piece_s": pieces[0][key].size / rate_hz,
            "key": key, "unit": UNITS[key]}


def pieces_words(result: dict) -> str:
    """"4 pieces of 4 s averaged", or "1 piece of 4 s"."""
    n = result["pieces"]
    return (f"1 piece of {result['piece_s']:g} s" if n == 1 else
            f"{n} pieces of {result['piece_s']:g} s averaged")


LEGEND = ("in ref: the line is in the reference too. With a reference taken "
          "far away, that",
          "makes it electrical. gap: with a tenfold change of the current "
          f"taken as {NM_PER_DECADE:g} nm.")


def report(result: dict, legend: bool = True) -> list[str]:
    """What a result says, as lines for the list under the plots (which has
    the legend beside it) and for the saved .txt (which has it at its end)."""
    unit = result["unit"]
    o, t, c = result["shares"]
    lines = [f"{SIGNALS[result['key']]}: {pieces_words(result)}, lines "
             f"{result['step_hz']:g} Hz apart",
             f"the junction was open {o:.0%}, tunnelling {t:.0%}, closed {c:.0%} "
             f"of the time; mean {result['mean']:.4g} {unit}"]
    if result["key"] in ("i1", "i2", "gap"):
        if o > 0.8:
            lines.append("OPEN nearly all the time: this is the amplifier alone "
                         "(a good reference). For the shaking, go closer.")
        elif c > 0.8:
            lines.append("CLOSED nearly all the time: a contact does not show "
                         "the gap. Find the edge, or Step apart.")
        elif t < 0.8:
            lines.append("In and out of tunnelling: the frequencies are right, "
                         "the sizes are not (no picometres).")
    if result.get("railed", 0.0) > 0.01:
        lines.append(f"Channel 2 was at its rail {result['railed']:.0%} of the "
                     "time: its spectrum is cut off there. Look at channel 1.")
    lines.append("")
    if not result["peaks"]:
        lines.append("no line stands out of the noise")
        return lines
    lines.append(f"{'Hz':>9}  {unit:>10}  {'of mean':>7}  {'gap':>8}  {'in ref':>6}   "
                 "what it may be")
    for p in result["peaks"]:
        share = ""
        if np.isfinite(p["share"]) and p["share"] < 10:
            share = (f"{p['share']:.0%}" if p["share"] >= 0.1 else
                     f"{p['share']:.1%}" if p["share"] >= 0.0005 else "<0.1%")
        # Under a tenth of a picometre the gap is not moving at this
        # frequency: the line is a by-product (a multiple of a real one).
        pm = "" if p["pm"] is None else \
            f"{p['pm']:.3g} pm" if p["pm"] >= 0.1 else "<0.1 pm"
        also = "also" if p["in_reference"] else ""
        lines.append(f"{p['hz']:9.2f}  {p['amp']:10.4g}  {share:>7}  {pm:>8}  {also:>6}   "
                     f"{p['what']}")
    if legend:
        lines.extend(["", *LEGEND])
    return lines


def save_spectrum(folder: Path, name: str, result: dict, meta: dict) -> Path:
    """Write a spectrum as a .csv (Excel opens it; Load a reference reads
    it back): lines of ``# key: value`` first, then ``frequency_hz`` and the
    amplitude, up to ``TOP_HZ``. Returns the file."""
    folder.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name.strip())
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(meta.get("when")))
    path = folder / f"noise_{stamp}{'_' + safe if safe else ''}_{result['key']}.csv"
    keep = result["freqs"] <= TOP_HZ
    head = {"name": name.strip(), "signal": SIGNALS[result["key"]],
            "unit": result["unit"], "pieces": result["pieces"],
            "piece_s": f"{result['piece_s']:g}",
            "mean": f"{result['mean']:.6g}",
            "open_tunnelling_closed": " ".join(f"{s:.3f}" for s in result["shares"]),
            **{k: v for k, v in meta.items() if k != "when"},
            "recorded": time.strftime("%Y-%m-%d %H:%M:%S",
                                      time.localtime(meta.get("when")))}
    part = path.with_suffix(".part")
    with open(part, "w", newline="", encoding="utf-8") as fh:
        for k, v in head.items():
            fh.write(f"# {k}: {v}\n")
        fh.write(f"frequency_hz,amplitude_{result['unit']}\n")
        for f, a in zip(result["freqs"][keep], result["amp"][keep]):
            fh.write(f"{f:.4f},{a:.6g}\n")
    os.replace(part, path)
    return path


def load_spectrum(path: Path) -> dict:
    """Read a spectrum ``save_spectrum`` wrote: a dict with ``name``,
    ``unit``, ``signal``, ``freqs``, ``amp``."""
    head, rows = {}, []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("#"):
                k, _, v = line[1:].partition(":")
                head[k.strip()] = v.strip()
            elif line and line[0].isdigit():
                f, _, a = line.partition(",")
                rows.append((float(f), float(a)))
    if len(rows) < 8:
        raise ValueError(f"{path.name} holds no spectrum")
    data = np.array(rows)
    return {"name": head.get("name") or path.stem, "unit": head.get("unit", ""),
            "signal": head.get("signal", ""), "freqs": data[:, 0], "amp": data[:, 1]}


# --------------------------------------------------------------------------
# The window
# --------------------------------------------------------------------------

def run(cfg: RigConfig, config_name: str, out_dir: Path,
        autoclose: float | None = None, zoom: float | None = None) -> int:
    """Open the card, show the window, and when the window is gone, however
    it went, end the worker and park the outputs."""
    # What the window needs, before the card is touched: a Python without
    # Tk fails here, with nothing opened.
    import importlib

    import matplotlib
    importlib.import_module("tkinter")
    matplotlib.use("TkAgg")
    importlib.import_module("matplotlib.backends.backend_tkagg")

    try:
        guard, rig = pullout.open_rig(cfg)
    except (ConfigError, SafetyViolation):
        raise
    except Exception as exc:                       # noqa: BLE001
        # A card another program holds says so in its own words, at length.
        first = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
        log.error("could not open the card: %s: %s", type(exc).__name__, first)
        log.error("Is pullout, rigcheck or Igor still open? Only one program "
                  "can have the card. Close it and start noisecheck again.")
        return 1
    shake = SimShake(rig._session, cfg) if cfg.simulate else None
    mon = pullout.Monitor(rig)
    worker = NoiseWorker(cfg, rig, mon, save=False, out_dir=out_dir,
                         igor_export=False)
    worker.config_name = config_name
    worker.start()
    closed = {"done": False}

    def shutdown() -> None:
        if closed["done"]:
            return
        closed["done"] = True
        worker.stop_flag.set()
        worker.quit()
        worker.join(timeout=60)
        if worker.is_alive():
            log.error("the rig worker has not finished in 60 s; closing the "
                      "cards under it")
        pullout.close_rig(guard, rig)

    try:
        return _window(cfg, config_name, out_dir, rig, shake, worker, shutdown,
                       closed, autoclose, zoom)
    finally:
        shutdown()


def _window(cfg: RigConfig, config_name: str, out_dir: Path, rig, shake,
            worker: NoiseWorker, shutdown, closed: dict,
            autoclose: float | None, zoom: float | None) -> int:
    """The window, around a rig that is open and a worker that is running.
    ``shutdown`` ends both (``run`` calls it again when this returns or
    fails, and it does its work once); ``closed["done"]`` says it has."""
    import tkinter as tk
    from tkinter import filedialog, ttk

    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    root = tk.Tk()
    root.title(f"STM-BJ noise check  {__version__}"
               + ("  [simulate]" if cfg.simulate else f"  [{cfg.channels.device}]")
               + f"  {config_name}")
    style = ttk.Style(root)
    want_clam = sys.platform == "darwin" or os.environ.get("PULLOUT_THEME") == "clam"
    if zoom is None:
        zoom = 1.2 if sys.platform == "darwin" else 1.0
    if want_clam and "clam" in style.theme_names():
        windows_look(root, style, zoom)
    elif zoom != 1.0:
        root.tk.call("tk", "scaling", float(root.tk.call("tk", "scaling")) * zoom)

    def px(n: int) -> int:
        return int(round(n * zoom))

    C, R = cfg.cal, cfg.ramp
    outer = ttk.Frame(root)
    outer.pack(fill="both", expand=True, padx=6, pady=6)
    left = ttk.Frame(outer)
    left.pack(side="left", fill="y", padx=(0, 8))
    right = ttk.Frame(outer)
    right.pack(side="right", fill="both", expand=True)
    WIDE = px(470)

    # What the window holds between two ticks of its clock.
    live = {"record": None,        # the last record (the "noise" event)
            "result": None,        # its analysis for the signal on show
            "reference": None,     # a kept or loaded spectrum
            "scope": None,         # the last look at the inputs
            "last_scope": 0.0,
            # The top plot: the live picture, or, after Record, the record,
            # which stays on show until something is asked of the rig again.
            "show": "live",
            "selftest": 0}
    QUIET = ("scope", "monitor", "noop")

    def rig_is_free() -> bool:
        return ((not worker.busy or worker.current in QUIET)
                and all(c[0] in QUIET for c in list(worker.commands.queue)))

    def do(*command) -> bool:
        """Send a command, unless one is already running."""
        if not rig_is_free():
            set_status("busy: wait for the current command to finish, or press "
                       "Stop", "bad")
            return False
        live["show"] = "live"
        worker.send(*command)
        return True

    # -- status ---------------------------------------------------------------
    stb = ttk.LabelFrame(left, text="Status")
    stb.pack(fill="x", pady=(0, 3))
    status = tk.Label(stb, text="ready", font=("Arial", 10, "bold"),
                      wraplength=WIDE, justify="left", anchor="nw", height=4,
                      fg="#1b5e20")
    status.pack(fill="x", padx=6, pady=2)
    COLOURS = {"ok": "#1b5e20", "bad": "#b00000", "warn": "#b06000",
               "busy": "#0d47a1", "info": "#202020"}

    def set_status(text: str, level: str | None = None) -> None:
        status.config(text=text, fg=COLOURS.get(level or "info", COLOURS["info"]))

    # -- the junction ---------------------------------------------------------
    jb = ttk.LabelFrame(left, text="Junction")
    jb.pack(fill="x", pady=(0, 3))
    light = tk.Label(jb, text="  --  ", font=("Arial", 12, "bold"), fg="white",
                     bg="#6a6a6a", width=12)
    light.grid(row=0, column=0, rowspan=2, padx=6, pady=4)
    read1 = tk.Label(jb, text="", font=("Courier", 10), anchor="w", justify="left")
    read1.grid(row=0, column=1, sticky="w")
    read2 = tk.Label(jb, text="", font=("Courier", 10), anchor="w", justify="left")
    read2.grid(row=1, column=1, sticky="w")
    LIGHTS = {"open": ("  OPEN  ", "#6a6a6a"), "tunnelling": ("TUNNELLING", "#1b7a1b"),
              "contact": (" CONTACT ", "#b00000"), "": ("  --  ", "#6a6a6a")}

    def show_readout(p: dict) -> None:
        """The light and the numbers. With a two-channel amplifier they are
        channel 2's while it is below its rail (a tunnelling current is
        nothing on channel 1), and channel 1's above."""
        g1, ch2 = p["g0"], p.get("ch2")
        if ch2 is not None and not ch2["railed"]:
            best, amps, which = ch2["g0"], ch2["amps"], "  (ch 2)"
        else:
            best, amps = g1, p["current_ua"] * 1e-6
            which = "" if ch2 is None else "  (ch 1: ch 2 is at its rail)"
        word = "" if math.isnan(g1) else worker.word_for(g1, best)
        text, colour = LIGHTS[word]
        light.config(text=text, bg=colour)
        read1.config(text=f"I {amps * 1e9:10.2f} nA    G {best:.2e} G0{which}")
        read2.config(text=f"piezo {p['piezo_v']:.4f} V = {p['piezo_nm']:.1f} nm    "
                          f"bias {p['bias_mv']:.0f} mV")

    # -- the piezo driver: pullout's Driver row -------------------------------------
    db = ttk.LabelFrame(left, text="Piezo driver (as in pullout)")
    db.pack(fill="x", pady=(0, 3))
    df = ttk.Frame(db)
    df.pack(anchor="w", padx=2)
    pmode_var = tk.StringVar(value=str(C.piezo_mode).lower())
    ptotal_var = tk.StringVar(
        value="" if C.piezo_total_um is None else f"{C.piezo_total_um:g}")
    for word in ("standard", "bypass"):
        ttk.Radiobutton(df, text=word, value=word, variable=pmode_var).pack(
            side="left", padx=(4, 0))
    ttk.Label(df, text="total displacement").pack(side="left", padx=(10, 2))
    pt_entry = ttk.Entry(df, textvariable=ptotal_var, width=8)
    pt_entry.pack(side="left")
    ttk.Label(df, text="um").pack(side="left", padx=(2, 6))
    drive_lbl = tk.Label(db, text="", font=("Arial", 9, "bold"), anchor="w",
                         justify="left", wraplength=WIDE)
    drive_lbl.pack(anchor="w", padx=4)

    def show_driver(_p: dict | None = None) -> None:
        mode, total = str(C.piezo_mode).lower(), C.piezo_total_um
        lo, hi = cfg.limits.piezo_ao_min_v, cfg.limits.piezo_ao_max_v
        if total is None:
            drive_lbl.config(fg="#b06000", text=(
                f"no total displacement set: the config's own "
                f"{C.piezo_nm_per_volt:g} nm per volt is used. If that is not "
                "this rig's, every move here is wrong: type the total, pick "
                "the mode, press Set"))
        else:
            pmode_var.set(mode)
            ptotal_var.set(f"{total:g}")
            drive_lbl.config(fg="#006000", text=(
                f"{mode.upper()}: 1 V at the card = {C.piezo_nm_per_volt:.2f} nm; "
                f"the whole {lo:g} to {hi:g} V = "
                f"{(hi - lo) * C.piezo_nm_per_volt:.0f} nm"))

    def set_driver() -> None:
        try:
            total = float(ptotal_var.get())
        except ValueError:
            set_status(f"total displacement: '{ptotal_var.get()}' is not a number "
                       "of micrometres", "bad")
            return
        do("piezo_mode", pmode_var.get(), total)
    ttk.Button(df, text="Set", width=5, command=set_driver).pack(side="left")
    pt_entry.bind("<Return>", lambda _e: set_driver())
    show_driver()

    # -- 1. to the edge of contact ----------------------------------------------------
    eb = ttk.LabelFrame(left, text="1. Get to the edge of contact")
    eb.pack(fill="x", pady=(0, 3))
    speed_var = tk.StringVar(value=f"{worker.hand_speed_nm_s:g}")
    r1 = ttk.Frame(eb)
    r1.pack(anchor="w", padx=2, pady=1)
    ttk.Button(r1, text="Approach", width=12,
               command=lambda: do("piezo_approach")).pack(side="left")
    ttk.Label(r1, text="toward the surface at").pack(side="left", padx=(6, 2))
    ttk.Entry(r1, textvariable=speed_var, width=6).pack(side="left")
    ttk.Label(r1, text="nm/s, stopping at contact").pack(side="left", padx=(2, 0))

    def set_speed(*_a):
        try:
            speed = float(speed_var.get())
        except ValueError:
            return
        if 1.0 <= speed <= 5000.0:
            worker.hand_speed_nm_s = speed
    speed_var.trace_add("write", set_speed)
    r2 = ttk.Frame(eb)
    r2.pack(anchor="w", padx=2, pady=1)
    ttk.Button(r2, text="Find the edge", width=12,
               command=lambda: do("edge")).pack(side="left")
    ttk.Label(r2, text="retract from the contact in 0.1 nm steps until it lets go"
              ).pack(side="left", padx=(6, 0))
    r3 = ttk.Frame(eb)
    r3.pack(anchor="w", padx=2, pady=1)
    z_var = tk.StringVar(value="0.3")

    def on_step(sign: int) -> None:
        try:
            nm = abs(float(z_var.get()))
        except ValueError:
            nm = float("nan")
        if not math.isfinite(nm):
            set_status(f"Z: '{z_var.get()}' is not a number", "bad")
            return
        do("step", sign * nm)
    ttk.Button(r3, text="Step apart", width=12,
               command=lambda: on_step(-1)).pack(side="left")
    ttk.Label(r3, text="Z (nm)").pack(side="left", padx=(8, 2))
    ttk.Entry(r3, textvariable=z_var, width=6).pack(side="left")
    ttk.Button(r3, text="Step closer", width=12,
               command=lambda: on_step(+1)).pack(side="left", padx=(8, 0))
    r4 = ttk.Frame(eb)
    r4.pack(anchor="w", padx=2, pady=1)
    ttk.Button(r4, text="Calibrate zero", width=12,
               command=lambda: do("zero")).pack(side="left")
    ttk.Label(r4, text="(with the junction open)").pack(side="left", padx=(6, 0))
    # Red, as in pullout: a themed button where the theme takes colours (the
    # Mac's window is drawn in "clam"), a classic one elsewhere.
    if style.theme_use() == "clam":
        style.configure("Stop.TButton", font=("Arial", 10, "bold"),
                        foreground="white", background="#c62828",
                        bordercolor="#8e0000", lightcolor="#c62828",
                        darkcolor="#c62828", padding=(4, 2))
        style.map("Stop.TButton", background=[("active", "#8e0000")],
                  lightcolor=[("active", "#8e0000")], darkcolor=[("active", "#8e0000")])
        stop_btn = ttk.Button(r4, text="\u25a0  Stop", width=10, style="Stop.TButton",
                              command=worker.stop_flag.set)
    else:
        stop_btn = tk.Button(r4, text="\u25a0  Stop", font=("Arial", 10, "bold"),
                             fg="white", bg="#c62828", activebackground="#8e0000",
                             activeforeground="white", width=10,
                             command=worker.stop_flag.set)
    stop_btn.pack(side="left", padx=(30, 0))
    if shake is not None:
        # The simulator has no screw and nothing shakes it. These two rows
        # are the screw (pullout's own) and the shake.
        s1 = ttk.Frame(eb)
        s1.pack(anchor="w", padx=2, pady=(4, 1))
        ttk.Label(s1, text="simulator's screw: surface at").pack(side="left")
        surface_var = tk.StringVar(
            value=f"{getattr(rig._session, 'surface_nm', 300.0):g}")
        ttk.Entry(s1, textvariable=surface_var, width=7).pack(side="left", padx=2)
        ttk.Label(s1, text="nm up the piezo's travel").pack(side="left")

        def turn_screw():
            try:
                nm = float(surface_var.get())
            except ValueError:
                set_status(f"simulator's screw: '{surface_var.get()}' is not a "
                           "number of nm", "bad")
                return
            do("sim_surface", nm)
        ttk.Button(s1, text="Turn", width=5, command=turn_screw).pack(
            side="left", padx=4)
        s2 = ttk.Frame(eb)
        s2.pack(anchor="w", padx=2, pady=1)
        shake_nm_var = tk.StringVar(value=f"{shake.shake_nm:g}")
        shake_hz_var = tk.StringVar(value=f"{shake.shake_hz:g}")
        hum_var = tk.StringVar(value=f"{shake.hum_na:g}")
        ttk.Label(s2, text="simulator: shake the tip by").pack(side="left")
        ttk.Entry(s2, textvariable=shake_nm_var, width=5).pack(side="left", padx=2)
        ttk.Label(s2, text="nm at").pack(side="left")
        ttk.Entry(s2, textvariable=shake_hz_var, width=5).pack(side="left", padx=2)
        ttk.Label(s2, text="Hz; mains hum").pack(side="left")
        ttk.Entry(s2, textvariable=hum_var, width=5).pack(side="left", padx=2)
        ttk.Label(s2, text="nA").pack(side="left")

        def set_shake(*_a):
            for var, name, top in ((shake_nm_var, "shake_nm", 5.0),
                                   (shake_hz_var, "shake_hz", 5000.0),
                                   (hum_var, "hum_na", 1e6)):
                try:
                    value = float(var.get())
                except ValueError:
                    continue
                if 0.0 <= value <= top:
                    setattr(shake, name, value)
        for var in (shake_nm_var, shake_hz_var, hum_var):
            var.trace_add("write", set_shake)

    # -- 2. record ---------------------------------------------------------------------
    rb = ttk.LabelFrame(left, text="2. Record")
    rb.pack(fill="x", pady=(0, 3))
    q1 = ttk.Frame(rb)
    q1.pack(anchor="w", padx=2, pady=1)
    have = ["i1"] + (["i2"] if cfg.channels.two_current_channels else []) + ["gap", "v"] \
        + (["z"] if cfg.channels.has_piezo_sense else [])
    # A tunnelling current is read on the amplifier's high-gain output.
    signal_var = tk.StringVar(value=SIGNALS["i2" if "i2" in have else "i1"])
    ttk.Label(q1, text="signal").pack(side="left")
    signal_box = ttk.Combobox(q1, textvariable=signal_var, state="readonly", width=21,
                              values=[SIGNALS[k] for k in have])
    signal_box.pack(side="left", padx=(4, 8))
    seconds_var = tk.StringVar(value="16")
    ttk.Label(q1, text="for").pack(side="left")
    ttk.Entry(q1, textvariable=seconds_var, width=5).pack(side="left", padx=2)
    ttk.Label(q1, text="s").pack(side="left")

    def key_now() -> str:
        return next(k for k, v in SIGNALS.items() if v == signal_var.get())

    def on_record() -> None:
        try:
            seconds = float(seconds_var.get())
        except ValueError:
            set_status(f"Record: '{seconds_var.get()}' is not a number of seconds",
                       "bad")
            return
        do("record", seconds)
    ttk.Button(q1, text="Record", width=9, command=on_record).pack(
        side="left", padx=(10, 0))
    q2 = ttk.Frame(rb)
    q2.pack(anchor="w", padx=2, pady=1)
    name_var = tk.StringVar(value="")
    ttk.Label(q2, text="name").pack(side="left")
    ttk.Entry(q2, textvariable=name_var, width=22).pack(side="left", padx=(4, 6))
    ttk.Button(q2, text="Save", width=6, command=lambda: on_save()).pack(side="left")
    live_var = tk.BooleanVar(value=True)

    def on_live() -> None:
        if live_var.get():
            live["show"] = "live"
    ttk.Checkbutton(q2, text="live picture while idle", variable=live_var,
                    command=on_live).pack(side="left", padx=(10, 0))
    q3 = ttk.Frame(rb)
    q3.pack(anchor="w", padx=2, pady=1)
    ttk.Button(q3, text="Keep as reference", width=17,
               command=lambda: keep_reference()).pack(side="left")
    ttk.Button(q3, text="Load a reference...", width=17,
               command=lambda: load_reference()).pack(side="left", padx=4)
    ttk.Button(q3, text="Clear", width=6,
               command=lambda: clear_reference()).pack(side="left")
    ref_lbl = ttk.Label(rb, text="no reference", wraplength=WIDE)
    ref_lbl.pack(anchor="w", padx=4)

    # -- the list, under the plots ------------------------------------------------------
    lb = ttk.LabelFrame(right, text="The biggest lines")
    lb.pack(side="bottom", fill="x", pady=(4, 0))
    listing = tk.Text(lb, height=13, width=90, font=("Courier", 9), wrap="none",
                      relief="flat", state="disabled",
                      background=root.cget("background"))
    listing.pack(fill="x", padx=2, pady=(2, 0))
    ttk.Label(lb, text=" ".join(LEGEND), wraplength=px(640), justify="left",
              foreground="#505050").pack(anchor="w", padx=4, pady=(0, 2))

    def set_listing(lines: list[str]) -> None:
        listing.config(state="normal")
        listing.delete("1.0", "end")
        listing.insert("1.0", "\n".join(lines))
        listing.config(state="disabled")
    set_listing(["First, with the tip far away (the light says OPEN): Record, then",
                 "Keep as reference. That is what the amplifier picks up by itself.",
                 "",
                 "1. Approach, then Find the edge (the light should say TUNNELLING).",
                 "2. Record. The lines of the spectrum come up here."])

    # -- the plots ---------------------------------------------------------------------
    # Small enough for a 13 inch laptop; the plots take what room a bigger
    # window gives them.
    fig = Figure(figsize=(6.6, 4.5), dpi=100)
    ax_t = fig.add_subplot(2, 1, 1)
    ax_f = fig.add_subplot(2, 1, 2)
    canvas = FigureCanvasTkAgg(fig, master=right)
    canvas.get_tk_widget().pack(fill="both", expand=True)

    def relayout(_event=None) -> None:
        """The margins of the plots in inches, whatever size the window has
        been given: room for the labels, and the rest for the two plots."""
        w, h = fig.get_size_inches()
        between = 0.86                 # the top plot's time axis, the lower one's title
        each = max(0.4, (h - 0.50 - 0.30 - between) / 2.0)
        fig.subplots_adjust(left=0.80 / w, right=1.0 - 0.20 / w,
                            bottom=0.50 / h, top=1.0 - 0.30 / h,
                            hspace=between / each)
    fig.canvas.mpl_connect("resize_event", relayout)
    relayout()
    resized = {"job": None}

    def on_resize(_event=None) -> None:
        """The labels of the lines are placed by pixel: once the window has
        a new size, place them again."""
        if resized["job"] is not None:
            root.after_cancel(resized["job"])
        resized["job"] = root.after(250, redraw_after_resize)

    def redraw_after_resize() -> None:
        resized["job"] = None
        if not closed["done"]:
            draw_spectrum()
    fig.canvas.mpl_connect("resize_event", on_resize)
    C_SIG, C_REF = "#1f4e9a", "#9a9a9a"

    def draw_time(signals: dict, rate: float, title: str) -> None:
        key = key_now()
        if key == "gap" and key not in signals:
            with_gap([signals], rate, R.break_g0)
        ax_t.clear()
        if key not in signals:                    # not read in this play
            ax_t.set_title(f"{SIGNALS[key]}: not read", fontsize=10)
            return
        y = np.asarray(signals[key], dtype=float)
        t, y = noise.thin(np.arange(y.size) / rate, y)
        ax_t.plot(t, y, color=C_SIG, lw=0.7)
        ax_t.set_xlabel("time (s)", fontsize=9)
        ax_t.set_ylabel(SIGNALS[key], fontsize=9)
        ax_t.set_title(title, fontsize=10)
        ax_t.set_xlim(0.0, max(float(t[-1]), 1e-3))
        ax_t.grid(True, alpha=0.3)
        ax_t.tick_params(labelsize=8)

    def label_lines(result: dict) -> None:
        """The frequency over each line of the spectrum: red for the gap's
        own lines, grey for mains and for what the reference has too. The
        biggest line is labelled first; a label that would lie on one
        already there is lifted, and left out if that does not help (the
        list has every line)."""
        per_pt = fig.dpi / 72.0
        top = ax_f.bbox.y1
        there: list[tuple[float, float, float, float]] = []
        for p in sorted(result["peaks"], key=lambda q: -q["amp"]):
            mains = p["what"].startswith("mains")
            text = f"{p['hz']:.4g} Hz" + (" mains" if mains else "")
            x, y = ax_f.transData.transform((p["hz"], p["amp"]))
            half = (0.56 * 8.0 * len(text) + 4.0) * per_pt / 2.0
            high = 8.0 * 1.3 * per_pt
            for lift in (4.0, 15.0, 26.0):
                box = (x - half, x + half, y + lift * per_pt, y + lift * per_pt + high)
                if box[3] > top:
                    break
                if all(box[1] < o[0] or box[0] > o[1] or box[3] < o[2] or box[2] > o[3]
                       for o in there):
                    there.append(box)
                    ax_f.annotate(text, xy=(p["hz"], p["amp"]), xytext=(0, lift),
                                  textcoords="offset points", ha="center",
                                  va="bottom", fontsize=8,
                                  color="#b00000" if not (mains or p["in_reference"])
                                  else "#555555")
                    break

    def draw_spectrum() -> None:
        result, ref = live["result"], live["reference"]
        ax_f.clear()
        ax_f.set_xscale("log")
        ax_f.set_yscale("log")
        ax_f.grid(True, which="both", alpha=0.25)
        ax_f.tick_params(labelsize=8)
        ax_f.set_xlabel("frequency (Hz)", fontsize=9)
        lows = []
        if ref is not None and (result is None or ref.get("unit") == result["unit"]):
            keep = (ref["freqs"] > 0) & (ref["freqs"] <= TOP_HZ)
            ax_f.plot(ref["freqs"][keep], ref["amp"][keep], color=C_REF, lw=0.8,
                      label=f"reference: {ref['name']}")
            lows.append(ref["amp"][keep])
        if result is not None:
            keep = (result["freqs"] > 0) & (result["freqs"] <= TOP_HZ)
            f, a = result["freqs"][keep], result["amp"][keep]
            ax_f.plot(f, a, color=C_SIG, lw=0.8, label=SIGNALS[result["key"]])
            lows.append(a)
            ax_f.set_ylabel(f"amplitude ({result['unit']})", fontsize=9)
            ax_f.set_title("spectrum: " + pieces_words(result), fontsize=10)
            ax_f.set_xlim(max(result["step_hz"], 0.1), TOP_HZ)
        else:
            ax_f.set_title("spectrum (press Record)", fontsize=10)
            ax_f.set_xlim(0.5, TOP_HZ)
        if lows:
            every = np.concatenate(lows)
            every = every[every > 0]
            if every.size:
                # A quarter of the height above the highest line, for the
                # labels.
                low, high = float(every.min()) * 0.5, float(every.max())
                ax_f.set_ylim(low, high * (high / low) ** 0.28 if high > low
                              else high * 10.0)
            ax_f.legend(fontsize=8, loc="upper right", frameon=False)
        if result is not None:
            label_lines(result)                 # after the limits: it places by pixel
        canvas.draw_idle()

    def show_record() -> None:
        """The record on show again: for a new record, or another signal."""
        rec = live["record"]
        if rec is None:
            draw_spectrum()
            return
        key = key_now()
        if key != "gap" and key not in rec["pieces"][0]:
            set_status(f"{SIGNALS[key]} is not in this record", "bad")
            return
        live["result"] = analyse(rec["pieces"], rec["rate"], key,
                                 break_g0=rec["break_g0"],
                                 reference=live["reference"])
        whole = {key: np.concatenate([p[key] for p in rec["pieces"]])}
        draw_time(whole, rec["rate"],
                  f"the record: {len(rec['pieces'])} x {rec['piece_s']:g} s with the "
                  f"piezo at {rec['piezo_v']:.4f} V (the pieces end to end)")
        draw_spectrum()
        # Without its empty lines here: the window is as low as it can be.
        set_listing([line for line in report(live["result"], legend=False) if line])

    def on_signal(_e=None) -> None:
        reference_text()
        if live["record"] is not None:
            show_record()                 # the spectrum and the list, for this signal
        else:
            draw_spectrum()
        if live["show"] == "live" and live["scope"] is not None:
            draw_time(live["scope"]["signals"], live["scope"]["rate"],
                      "live: the last quarter of a second")
            canvas.draw_idle()
    signal_box.bind("<<ComboboxSelected>>", on_signal)

    def reference_text() -> None:
        """Which reference there is, and when it is not on the plot: a
        spectrum in nanoamps says nothing beside one in picometres."""
        ref = live["reference"]
        if ref is None:
            ref_lbl.config(text="no reference")
            return
        text = f"reference (grey): {ref['name']}  [{ref.get('signal') or ref['unit']}]"
        if ref.get("unit") != UNITS[key_now()]:
            text += (f". NOT SHOWN: it is in {ref.get('unit') or '?'}, the signal "
                     f"on show in {UNITS[key_now()]}")
        ref_lbl.config(text=text)

    def keep_reference() -> None:
        result = live["result"]
        if result is None:
            set_status("Keep as reference: there is no record yet", "bad")
            return
        live["reference"] = {"name": name_var.get().strip() or "the record before",
                             "unit": result["unit"], "signal": SIGNALS[result["key"]],
                             "freqs": result["freqs"], "amp": result["amp"]}
        reference_text()
        show_record()
        set_status("kept as the reference (grey). Lines that the next record "
                   'shares with it get "also" in the list', "ok")

    def load_reference() -> None:
        path = filedialog.askopenfilename(
            parent=root, title="A spectrum saved by noisecheck",
            initialdir=str(out_dir if out_dir.is_dir() else _ROOT),
            filetypes=[("noisecheck spectrum", "*.csv"), ("all files", "*")])
        if not path:
            return
        try:
            live["reference"] = load_spectrum(Path(path))
        except (OSError, ValueError) as exc:
            set_status(f"Load a reference: {exc}", "bad")
            return
        reference_text()
        show_record()
        set_status(f"reference loaded: {Path(path).name}", "ok")

    def clear_reference() -> None:
        live["reference"] = None
        reference_text()
        show_record()

    def on_save() -> None:
        rec, result = live["record"], live["result"]
        if rec is None or result is None:
            set_status("Save: there is no record yet", "bad")
            return
        try:
            path = save_spectrum(out_dir, name_var.get(), result, {
                "piezo_v": f"{rec['piezo_v']:.4f}", "piezo_nm": f"{rec['piezo_nm']:.1f}",
                "bias_mv": f"{rec['bias_mv']:.1f}", "config": config_name,
                "version": __version__, "when": rec["when"]})
            fig.savefig(path.with_suffix(".png"), dpi=110)
            path.with_suffix(".txt").write_text("\n".join(report(result)) + "\n",
                                                encoding="utf-8")
        except OSError as exc:
            set_status(f"Save: {exc}", "bad")
            return
        set_status(f"saved {path.name} (with a .png of the plots and a .txt of "
                   f"the list) in {path.parent}", "ok")

    # -- the clock ---------------------------------------------------------------------
    def poll_body() -> None:
        while True:
            try:
                kind, p = worker.events.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                set_status(p["text"], p.get("level"))
            elif kind == "error":
                set_status(p["text"], "bad")
            elif kind == "readout":
                show_readout(p)
            elif kind == "piezo":
                show_driver(p)
            elif kind == "scope":
                live["scope"] = p
                if p["piece"] is None:
                    if live["show"] == "live":
                        draw_time(p["signals"], p["rate"],
                                  "live: the last quarter of a second")
                        canvas.draw_idle()
                else:
                    draw_time(p["signals"], p["rate"],
                              f"recording: piece {p['piece']} of {p['of']}")
                    canvas.draw_idle()
            elif kind == "noise":
                live["record"], live["show"] = p, "record"
                show_record()
                if live["selftest"] == 1:
                    live["selftest"] = 2
                    name_var.set("self test")
                    on_save()
                    keep_reference()
                    worker.send("record", 4.0)
        if rig_is_free() and not worker.busy \
                and time.monotonic() - live["last_scope"] > 0.4:
            # While idle: a look for the live picture, or, without it, the
            # short one that keeps the light and the numbers going.
            live["last_scope"] = time.monotonic()
            worker.send("scope" if live_var.get() else "monitor")

    def poll() -> None:
        try:
            poll_body()
        except Exception:                       # noqa: BLE001
            log.exception("window update failed")
        root.after(150, poll)

    def on_close() -> None:
        try:
            shutdown()
        finally:
            root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)

    # On a small screen the plots give way, so that the buttons and the list
    # stay whole.
    root.update_idletasks()
    over_w = root.winfo_reqwidth() - (root.winfo_screenwidth() - 20)
    over_h = root.winfo_reqheight() - (root.winfo_screenheight() - 80)
    if over_w > 0 or over_h > 0:
        plots = canvas.get_tk_widget()
        plots.config(width=max(px(420), plots.winfo_reqwidth() - max(0, over_w)),
                     height=max(px(330), plots.winfo_reqheight() - max(0, over_h)))

    draw_spectrum()
    worker.send("piezo")
    worker.send("begin")                          # the amplifier's zero, junction open
    root.after(150, poll)
    if autoclose is not None:
        # The self-test: the whole path once, on whatever card this is (the
        # tests run it on the simulated one). Approach, the edge, a short
        # record that is saved and kept as the reference, a second record.
        live["selftest"] = 1
        root.after(300, lambda: worker.send("piezo_approach"))
        root.after(400, lambda: worker.send("edge"))
        root.after(500, lambda: worker.send("record", 8.0))
        root.after(int(autoclose * 1000), on_close)
    try:
        root.mainloop()
    finally:
        shutdown()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="At which frequencies does the junction shake? The "
                    "tunnelling current, Fourier transformed.")
    p.add_argument("--config", type=Path, help="rig config JSON")
    p.add_argument("--simulate", action="store_true", help="fake card, no hardware")
    p.add_argument("--out", type=Path, default=None,
                   help="where Save puts its files (default: data/noisecheck)")
    p.add_argument("--zoom", type=float, default=None,
                   help="make the window bigger or smaller (1.2 is a fifth bigger)")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--autoclose", type=float, help=argparse.SUPPRESS)
    p.add_argument("--version", action="version", version=f"noisecheck {__version__}")
    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    cfg = RigConfig.from_json(args.config) if args.config else RigConfig()
    if args.simulate:
        cfg.simulate = True
    try:
        return run(cfg, args.config.name if args.config else "defaults",
                   args.out or _ROOT / "data" / "noisecheck",
                   autoclose=args.autoclose, zoom=args.zoom)
    except (ConfigError, SafetyViolation) as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.info("interrupted; outputs parked")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
