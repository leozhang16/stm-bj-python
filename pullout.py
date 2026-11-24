"""STM-BJ pull-out: approach, pull, decide, histogram, save -- the experiment.

    python pullout.py --simulate
    python pullout.py --config configs/labpc_rig.json
    python pullout.py --config configs/labpc_rig.json --headless 20

The fine-piezo approach and the constant-bias pull, exactly as the experiment
does them (``approach.engage`` and ``trace.single_trace``), driven by buttons
instead of a loop, with the settings Igor's Inputs tab had, each change
checked against the safety rules before it is accepted, and four live plots:

    record          junction V and current during the last play (Igor HighRes)
    trace           log G vs displacement with the accept/reject verdict, and
                    over it, in grey on a right-hand axis, how far the piezo
                    readback says the piezo retracted during that same pull
                    (dotted diagonal = the command; a lag sits below it)
    piezo in/out    commanded position (and the readback) over the whole cycle
    histogram       counts per trace over the accepted traces so far

Saving is Igor's scheme (``stmlab.igor_scheme``, the layout of Igor's
``SavePullOut``), so the lab's Igor analysis macro and plot.py read a
Python day exactly as they read an Igor day. Every accepted trace goes into
the day folder <data folder>/MM_DD<SetupID>YYMerge (``10_22_26Merge`` on
22 Oct 2026 with the default Setup ID ``_``), numbered through the day
from 1 -- Igor's ``Saved`` -- 100 traces to a block: block k is
``PullOutConductanceBlock_k.ibw`` (G/G0, then the 20 Igor parameters per
column) with ``PullOutVoltageBlock_k``, ``PullOutCurrentBlock_k``,
``PullOutExtensionBlock_k`` (the sense readback, when the rig has one),
``PullOutConductanceBlockHist_k`` and ``PullOutPiezoBiasWave_k`` as the
Save boxes say. A block is written when its 100th trace is taken and, as
Igor could not, at the end of every run (Stop, pause, quit) with its
empty columns NaN; the next run continues the numbering from the folder
and refills that block. Beside the Igor files, in the same day folder:
the raw .h5 session of each Start N (raw volts, the config, per-trace
scalars: ``storage.SessionWriter``; <experiment>_<HHMMSS>_<N>traces.h5),
``experiment_log.csv`` (one row per run, every day) and the .txt table
(displacement, then one G/G0 column per trace) when ticked. Folder,
Setup ID, name, experiment, notes and the boxes are remembered between
launches in data/pullout_saving.json. The Run box is Start N (every trace
is its own approach + pull, from an open junction), Continue, Stop and
Calibrate zero; the single-cycle commands (engage, pull, cycle, withdraw,
smash) are still there for --headless and the tests, and the smash-every
line runs the smash inside Start N. Saved data -- an .h5 session, an Igor
day folder (this program's or Igor's own) or one PullOutConductanceBlock
-- can be browsed in the same plots, and its histograms opened in windows
of their own, drawn by plot.py -- the same file that works alone:
``python plot.py <session>.h5 1D | 2D | -1`` (trace 1), or
``python plot.py <day folder> 1D``. Under Run, the Status box: the rig's
numbers (state, piezo, junction, current, zero, traces saved today, file,
Keithley) and the last message, in colour.

A current amplifier with two outputs is read as two channels (the Current
amplifier box: one channel or two, and the gain of each. On a rig whose
config names channel 2's input it stands in the left column where the
Keithley box otherwise is, in view when the window opens, and the Keithley
box is not shown: a two-output amplifier is not the 428. On a one-channel
rig it is the first box of the Settings tab). Channel 1 is the lower-gain output, the one that follows the
junction through contact, and contact is judged on it, as with one
channel. Channel 2 is the higher-gain output for the low conductances,
and the junction-open test (the Break threshold: the approach's separate
step and the end of every trace) is read from it, because down there
channel 1 is in its own noise; where channel 2 is at its rail channel 1
is read instead. Channel 2 is read in the same task during every play,
saved with every trace, and drawn beside channel 1 -- the trace panel and the
histogram show both on one plot, channel 1 in blue and channel 2 in red,
so the histogram has two noise floors. Channel 2 is drawn and counted
only as far as it measured (v75): where its output is saturated
(``limits.preamp_saturation_v``) it has no line and no counts. Before, the
saturated part was drawn too, and since a saturated current divided by
the junction voltage still has steps where the gold steps are, channel 2
showed "G0 peaks" at conductances that were wrong (at 300 mV, about
0.38 G0 for the 1 G0 plateau).
Which card input channel 2 is on is the config's ``channels.ai_current_2``
(``configs/newrig_2ch.json`` is such a rig); its raw volts go into the .h5
(``current2_v``), and its Igor files into the day folder's ``ch2``
subfolder under Igor's own names, same blocks and trace numbers, while
channel 1's files stay exactly as they are. In the ``ch2`` files and the
``_ch2.txt`` table the saturated part of channel 2 holds channel 1's
conductance (Igor's analysis needs the contact part of a trace); read
back here, those points are blank again.

Three things for bringing a rig up (v69, manual chapter 23). The Current
amplifier box has a "flip the sign" box for each channel: an amplifier
whose output is the other way round from the Keithley's gives a negative
current at a positive bias, so a negative conductance, no logarithm and an
empty trace panel; ticked, that channel's current is -(V - zero) / gain
(``cal.current_sign``, ``cal.current_sign_2``). A pull that reads negative
where the junction conducts says so in red, and three in a row stop the
run. Above the plots, "plot 1: log I and V" draws the record panel's |V|
and |I| on logarithmic axes and "plot 2: linear G" draws the trace panel
as G/G0 itself, sign and all. The Monitor window's Sample-rate check
holds the outputs where they are for one second, again and again, records
every input in use, counts the numbers through a scratch file (written,
read back, deleted) and times the card against this PC's clock
(``stmlab.ratecheck``).

The Piezo box is Igor's PiezoGroupbox, with two things Igor's had not.
Its first row is the piezo DRIVER: the mode its switch is in (standard or
bypass) and the stage's total displacement in micrometres; Set makes them
the program's, and every distance follows (standard: total / 10 V per card
volt; bypass: total / 150 V). A change of mode takes the piezo to 0 V first.
Then Step closer / Step apart by Z nm, and TWO sliders on the one piezo
output: a coarse one over the piezo's whole voltage range, for coming up
to the surface after the screws, and a fine one over a window of it (half
a volt either side of where the piezo is, on round numbers; the window
walks along with the piezo). THE PIEZO FOLLOWS THE SLIDERS (v75): one
click anywhere on a bar and the knob goes there, and the piezo after it;
a knob that is dragged is followed while the mouse holds it (the worker's
``cmd_follow``). Nothing waits for the mouse to let go, and a knob pressed
and let go where it stood moves nothing. (Up to v74 they applied on mouse
release, as Igor's did, and a click beside the knob was one step of 1 mV.)
Because a move toward the surface is slow and may stop at contact, the
knob can be ahead of the piezo: its label is then orange and a red mark
over the bar shows where the piezo is; when the piezo is there, or was
stopped, the knobs are on the piezo again. A slider never pushes into a
junction that is closed already (Step closer does, by Z nm), so clicking
past a contact again and again costs nothing. In a simulation such a move
takes the time it takes on the rig (distance over speed), so that a
slider tried on a laptop is as slow or as fast as it will be there.
Under them Igor's readouts -- I (uA), V (mV), Piezo (V) and the
sense line -- refreshed every 0.3 s while the rig is idle by the same quiet
10 ms hold the Monitor window uses (Igor's Background Sampling), with
Igor's beep above 0.15 uA. A move made by hand AWAY from the surface is
ramped over 50 ms. One TOWARD it goes at a set speed (200 nm/s to begin
with) in pieces of 25 ms and stops where the junction closes: the
conductance above the Engage threshold, the amplifier at its rail, or the
current above the contact current (the CONTACT light's level). Then the
junction is probed: in contact, the state becomes ENGAGED (Step apart, or
a slider, opens it again); Start N starts from wherever the sliders left
the tip, separating first. Nothing checks where the switch on the driver
box stands: the Driver row has to say what the box is in.

APPROACH (v73; the big blue button since v75) is for a rig whose coarse
approach is a screw: the screw
brings the surface within the piezo's reach, and the button takes the piezo
toward it from where it is, at that same speed, until contact. The fine
slider is then around the contact. With no contact up to the top of the
range the piezo is taken back and the status line says to approach with
the screw again. Each slider's knob carries its volts and its nanometres,
and the fine slider's two ends are written in both.

The Keithley 428 tab is Igor's Keithley Controls over GPIB: zero check on
or off, Zero correct, Suppress I on or off, Find suppress (Igor's
TestVirtualGround sweep at 0 V bias) and the gain. The amplifier is
connected only when you press Connect, its state is left exactly as it is
(Igor's Kill Tasks leaves zero check ON, which makes the amplifier read
nothing -- the banner says so once the program knows), and on exit the
connection is closed without touching the amplifier.

The Coarse approach box is Igor's Actuator Controls: a Newport controller,
chosen with the port -- a NanoPZ PZC200 (19200 baud, read/write) or an
Agilis AG-UC2/AG-UC8 (NI-VISA, 921600 baud, this lab's) -- Connect, then
Step closer / Step apart, or Start approach, which puts the fine piezo
at its approach position (mid range, as Igor's), steps the sample in
until the current passes the stop level, and then retracts the piezo
until the junction is open, leaving it a few nanometres from the surface
with room both ways (one coarse step on this stage is wider than the
piezo's range, so the actuator is backed off only if the piezo cannot
open the junction); or, with a screw by hand, a contact light and beep
at the contact current. The Agilis
answers, so Connect asks it for its firmware and step counter, every
command is checked against its error code, and a move waits for "ready";
toward the sample is +PR (closer_sign = +1). The port is opened by
Connect, not at start-up, so a wrong port costs a message and nothing
else; rigtests/actuator_check.py finds the port and the controller and
moves an Agilis once with the counter read before and after. Every coarse
step passes the interlock: the piezo must be at or below its approach
position first (the slider, or Step apart).

When this program starts it parks the piezo at 0 V, so whatever extension
Igor left is undone; the approach (or the slider) then extends the piezo
until contact. Close Igor (its DAQ tasks and its serial port) before
starting, or the card and the port will be busy.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import logging
import math
import os
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass, field, fields as dataclass_fields
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import plot as session_plots                     # noqa: E402  (plot.py, beside this file)
from stmlab import analysis, approach, calibrate, igor_scheme, plots, ratecheck, storage, trace   # noqa: E402,E501
from stmlab.actuator import ActuatorError                           # noqa: E402
from stmlab.approach import ApproachError                           # noqa: E402
from stmlab.config import ConfigError, G0_SIEMENS, RigConfig, validate   # noqa: E402
from stmlab.instrument import Rig                                   # noqa: E402
from stmlab.safety import RigState, SafeSession, SafetyViolation    # noqa: E402
from stmlab.tklook import WIN_BG, _light_window, windows_look       # noqa: E402,F401

log = logging.getLogger("pullout")

# Shown in the window title and by --version, so a patch can say which
# version it applies to and you can see which one you have. (v74 was
# noisecheck.py, a separate program. v75: channel 2 of a two-channel
# amplifier is drawn and counted only where its output is not saturated,
# and the piezo follows the sliders -- a click on the bar, or a drag.)
__version__ = "v75"

# What the Saving tab holds when nothing is remembered yet. ``folder`` is
# the data folder (the day folder is made under it); ``setup_id`` is Igor's
# SetupID, the letters between the day and the year of the folder name;
# the five flags are Igor's save check boxes (igor_scheme.SaveFlags: which
# companion files a block gets); ``h5`` keeps the raw session file beside
# the Igor files; ``txt`` adds the plain-text table.
DEFAULT_SAVING = {"folder": "", "setup_id": "_", "name": "", "experiment": "",
                  "notes": "", "h5": True, "txt": False,
                  "bias": True, "current": True, "sense": True, "hist": True,
                  "piezo_wave": False}
IGOR_FLAG_KEYS = ("bias", "current", "sense", "hist", "piezo_wave")


def next_trace_number(folder) -> int:
    """The number the next trace saved into this day folder gets -- Igor's
    ``Saved`` -- read from the block files already there: 1 for a missing
    or empty folder, else 100 * (last block - 1) + its filled columns + 1."""
    k_last, filled = igor_scheme.IgorDayWriter.scan(folder)
    return 1 if k_last == 0 else igor_scheme.BLOCK * (k_last - 1) + filled + 1


# --------------------------------------------------------------------------
# Settings: Igor's Inputs tab, each change validated before it is accepted
# --------------------------------------------------------------------------

# (config path, label, Igor name, unit, kind, display scale)
SETTINGS = [
    ("ramp.pull_length_nm", "Excursion", "G_PseudoTotalLength_nm", "nm", float, 1),
    ("ramp.pull_rate_nm_per_s", "Pull rate", "G_PullOutRate", "nm/s", float, 1),
    ("ramp.bias_v", "Tip bias", "G_TipBias", "mV", float, 1e3),
    ("ramp.engage_g0", "Engage threshold", "G_ConductanceThreshold", "G0", float, 1),
    ("ramp.break_g0", "Break threshold", "", "G0", float, 1),
    ("ramp.approach_step_nm", "Approach step", "G_MakeContactApproachStepSize", "nm", float, 1),
    ("ramp.retract_step_nm", "Retract step", "", "nm", float, 1),
    ("ramp.settle_samples", "Settle samples", "G_WriteBufferSize", "", int, 1),
    ("ramp.pre_pad_samples", "Pre-pad", "", "samples", int, 1),
    ("ramp.post_pad_samples", "Post-pad", "", "samples", int, 1),
    ("ramp.smash_in_nm", "Smash in", "", "nm", float, 1),
    ("ramp.smash_out_nm", "Smash out", "", "nm", float, 1),
    ("ramp.smash_every", "Smash every", "", "attempts (0 = never)", int, 1),
    # Not a trajectory setting but a description of the wiring: the resistor
    # between the bias output and the junction. The validator's amplifier
    # estimates use it; the conductance itself does not (it divides by the
    # measured junction voltage). 0 means there is no resistor.
    ("keithley.series_resistance_ohm", "Series resistor", "G_SeriesResistance", "ohm", float, 1),
    # The gains of the current amplifier: what the amplifier is set to,
    # typed in because the program cannot read them off the box (they tell
    # the arithmetic, they program nothing). Channel 1 is the output
    # contact is judged on; channel 2 is the second, higher-gain output of
    # a two-channel amplifier, which the junction-open test is read from,
    # and only matters while two channels are read.
    # Both live in the Current amplifier box.
    ("cal.preamp_gain_v_per_a", "Gain ch 1", "", "V/A", float, 1),
    ("cal.preamp_gain_2_v_per_a", "Gain ch 2", "", "V/A", float, 1),
]
AMPLIFIER_SETTINGS = ("cal.preamp_gain_v_per_a", "cal.preamp_gain_2_v_per_a")


def follow_gain(cfg: RigConfig) -> None:
    """Keep ``keithley.gain_exponent`` in step with a channel-1 gain typed
    in the window, when that gain is a whole decade (1e5, 1e6, ...): the
    exponent is what the Keithley box shows, and the validator compares
    the two. A gain that is not a whole decade has no exponent to follow
    and is left alone (the validator then compares nothing)."""
    gain = cfg.cal.preamp_gain_v_per_a
    if gain > 0:
        decades = math.log10(gain)
        if abs(decades - round(decades)) < 1e-9:
            cfg.keithley.gain_exponent = int(round(decades))


def fine_window(volts: float, half_v: float, lo_v: float, hi_v: float
                ) -> tuple[float, float]:
    """The range of the Piezo box's FINE slider: ``half_v`` volts either
    side of where the piezo is, on round numbers (a piezo at 7.9868 V with
    half a volt either side gives 7.5 to 8.5 V), cut off where the piezo's
    own range ``lo_v``..``hi_v`` ends: around 0.29 V it is 0 to 0.8 V. A
    range narrower than twice ``half_v`` gets the whole range, and so does
    a ``half_v`` under a millivolt or a voltage that is not a number."""
    half_v, volts = abs(float(half_v)), float(volts)
    if not half_v >= 0.001 or not math.isfinite(volts) \
            or 2 * half_v >= hi_v - lo_v:
        return float(lo_v), float(hi_v)
    grid = half_v / 5.0                          # 0.1 V for half a volt
    centre = round(volts / grid) * grid
    return (round(float(max(centre - half_v, lo_v)), 6),
            round(float(min(centre + half_v, hi_v)), 6))


def _get(cfg, path: str):
    obj = cfg
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def _set(cfg, path: str, value) -> None:
    parts = path.split(".")
    obj = cfg
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], value)


def check_settings(cfg: RigConfig, changes: dict) -> tuple[list[str], list[str]]:
    """Try ``changes`` ({config path: value}) on a copy of ``cfg``.

    Returns (problems, warnings). Problems mean the change is refused:
    ``validate`` raised, or a value is of the wrong kind. Only when the list
    of problems is empty may the caller apply the changes to the live config.
    """
    trial = copy.deepcopy(cfg)
    problems: list[str] = []
    for path, value in changes.items():
        _set(trial, path, value)
    R = trial.ramp
    if not trial.cal.preamp_gain_v_per_a > 0 or \
            not trial.cal.preamp_gain_2_v_per_a > 0:
        return ["an amplifier gain must be a positive number of V/A "
                "(1e6, say)"], []
    if "cal.preamp_gain_v_per_a" in changes:
        follow_gain(trial)
    if R.pull_length_nm <= 0 or R.pull_rate_nm_per_s <= 0:
        problems.append("excursion and pull rate must be positive")
    if R.approach_step_nm <= 0 or R.retract_step_nm <= 0:
        problems.append("approach and retract steps must be positive")
    if R.settle_samples < 50:
        problems.append("settle samples must be at least 50")
    if R.pre_pad_samples < 0 or R.post_pad_samples < 0:
        problems.append("pads cannot be negative")
    if R.smash_every < 0:
        problems.append("smash every must be 0 or more")
    if trial.keithley.series_resistance_ohm < 0:
        problems.append("the series resistor cannot be negative (0 = none)")
    if problems:
        return problems, []
    try:
        warnings = validate(trial)
    except ConfigError as exc:
        return [str(exc)], []
    # Only warnings the change *caused*: the validator also repeats its
    # standing remarks about the config as a whole (the granted sample rate,
    # the unmeasured driver gain), which are not news.
    try:
        standing = set(validate(cfg))
    except ConfigError:
        standing = set()
    return [], [w for w in warnings if w not in standing]


# --------------------------------------------------------------------------
# Watching the rig: every play and every probe, for the plots
# --------------------------------------------------------------------------

@dataclass
class CycleLog:
    """What one approach-and-pull cycle looked like, for the pictures."""
    t: list = field(default_factory=list)          # seconds since cycle start
    piezo_v: list = field(default_factory=list)
    sense_v: list = field(default_factory=list)
    marks: dict = field(default_factory=dict)      # phase -> seconds
    app_piezo_v: list = field(default_factory=list)   # at each probe
    app_g0: list = field(default_factory=list)
    app_railed: list = field(default_factory=list)
    # What the inputs saw, play after play, on the same clock as ``t``: the
    # whole cycle's junction voltage and amplifier output, raw volts, with a
    # NaN between plays so the line breaks where nothing was recorded. A
    # pull is kept whole; a hold is thinned to 100 points.
    rec_t: list = field(default_factory=list)
    rec_v: list = field(default_factory=list)
    rec_i: list = field(default_factory=list)
    last_record: np.ndarray | None = None
    last_waveform: np.ndarray | None = None
    # Channel 2 of a two-channel amplifier over the same play as
    # ``last_record`` (raw volts), or None while it is not read.
    last_current2: np.ndarray | None = None


class Monitor:
    """Wraps ``rig.play`` and ``rig.probe`` so the window can see every move.

    The wrappers only observe; the rig's own clamp, tracker and interlock
    run exactly as before, because the wrapped methods are still the rig's.
    """

    def __init__(self, rig: Rig):
        self.rig = rig
        self.lock = threading.Lock()
        self.cycle = CycleLog()
        self.t0 = time.monotonic()
        # While True, plays update last_record (so the readout follows)
        # but are kept out of the cycle log: the idle monitor's holds.
        self.quiet = False
        self._play = rig.play
        self._probe = rig.probe
        rig.play = self.play            # instance attribute shadows the method
        rig.probe = self.probe

    def begin_cycle(self) -> None:
        with self.lock:
            self.cycle = CycleLog()
            self.t0 = time.monotonic()

    def mark(self, label: str) -> None:
        when = self._now()
        with self.lock:
            self.cycle.marks[label] = when

    def play(self, waveform):
        t_real = time.monotonic() - self.t0
        record = self._play(waveform)
        waveform = np.asarray(waveform, dtype=float)
        n = waveform.shape[1]
        fs = self.rig.sample_rate_hz
        sense = self.rig.last_sense_v
        if sense is not None and sense.size != n:
            sense = None
        second = self.rig.last_current2_v      # channel 2 of this same play
        with self.lock:
            c = self.cycle
            c.last_current2 = second
            if self.quiet:
                c.last_record = record
                c.last_waveform = waveform
                return record
            # The cycle clock: real time, but never running backwards and
            # never shorter than the plays themselves, so the picture is the
            # same on the rig (where a play takes n/fs seconds of wall time)
            # and on the simulator (where it takes none).
            t_begin = max(t_real, c.t[-1] if c.t else 0.0)
            t_finish = t_begin + n / fs
            if n > 2000:
                # A pull: keep its trajectory, thinned to ~500 points, so
                # the in-and-out picture shows the ramp itself.
                idx = np.arange(0, n, max(1, n // 500))
                c.t.extend((t_begin + idx / fs).tolist())
                c.piezo_v.extend(waveform[0, idx].tolist())
                c.sense_v.extend(sense[idx].tolist() if sense is not None
                                 else [float("nan")] * idx.size)
            else:
                # A hold: one point, where it ended up.
                c.t.append(t_finish)
                c.piezo_v.append(float(waveform[0, -1]))
                c.sense_v.append(float(np.mean(sense[-50:])) if sense is not None
                                 else float("nan"))
            # The inputs, for the record panel: everything the card read
            # this cycle, against the same clock.
            M = self.rig.cfg.channels
            ridx = np.arange(0, n, 1 if n > 2000 else max(1, n // 100))
            if c.rec_t:
                c.rec_t.append(float("nan"))
                c.rec_v.append(float("nan"))
                c.rec_i.append(float("nan"))
            c.rec_t.extend((t_begin + ridx / fs).tolist())
            c.rec_v.extend(record[M.ROW_VOLTAGE, ridx].tolist())
            c.rec_i.extend(record[M.ROW_CURRENT, ridx].tolist())
            c.last_record = record
            c.last_waveform = waveform
        return record

    def _now(self) -> float:
        with self.lock:
            return max(time.monotonic() - self.t0,
                       self.cycle.t[-1] if self.cycle.t else 0.0)

    def probe(self, n_samples=None):
        g0, railed = self._probe(n_samples)
        with self.lock:
            c = self.cycle
            c.app_piezo_v.append(self.rig.piezo_v)
            c.app_g0.append(g0)
            c.app_railed.append(railed)
        return g0, railed

    # A series of moves by hand is one cycle, and it grows with every play.
    # Past this many recorded points the next move starts a fresh one
    # (``spent``), so the pictures, and the copies made for them, stay quick.
    MAX_POINTS = 200_000

    def snapshot(self) -> CycleLog:
        """The cycle so far, as a copy of its own: its lists and its marks
        are copied too, under the lock. The worker goes on adding to the
        cycle (a series of moves by hand is one cycle), and whoever draws
        from a snapshot must not meet a play that is half added."""
        with self.lock:
            c = copy.copy(self.cycle)
            for f in dataclass_fields(c):
                value = getattr(c, f.name)
                if isinstance(value, list):
                    setattr(c, f.name, list(value))
                elif isinstance(value, dict):
                    setattr(c, f.name, dict(value))
            return c

    def last(self) -> CycleLog:
        """Only the last play (``last_record``, ``last_waveform``,
        ``last_current2``), without the cycle's series: what the readouts
        need, many times a second."""
        with self.lock:
            c = self.cycle
            return CycleLog(last_record=c.last_record,
                            last_waveform=c.last_waveform,
                            last_current2=c.last_current2)

    def spent(self) -> bool:
        """Is this cycle no longer one to add a move by hand to? It is
        empty, or finished (it has pulled), or has grown past
        ``MAX_POINTS``."""
        with self.lock:
            c = self.cycle
            return (not c.t or "end" in c.marks
                    or len(c.rec_t) > self.MAX_POINTS)


# --------------------------------------------------------------------------
# The worker: owns the rig, runs one command at a time
# --------------------------------------------------------------------------

class Worker(threading.Thread):
    """Executes commands from the window in order, on the rig, in its own
    thread, and posts events back. Commands: zero, bias, engage, pull,
    cycle, run (n), withdraw, smash, testpull (V), goto (V), step (nm),
    monitor. The stop flag interrupts a run between cycles and an approach
    between two steps; every command clears it as it starts, so a Stop
    pressed earlier does not kill the next command."""

    def __init__(self, cfg: RigConfig, rig: Rig, monitor: Monitor,
                 save: bool, out_dir: Path, igor_export: bool):
        super().__init__(daemon=True, name="rig-worker")
        self.cfg, self.rig, self.mon = cfg, rig, monitor
        self.commands: queue.Queue = queue.Queue()
        self.events: queue.Queue = queue.Queue()
        self.stop_flag = threading.Event()
        self._quit = threading.Event()

        self.save = save
        # Write the Igor files (the day folder's PullOut*Block_k.ibw). Off
        # only with --no-igor, for bench tests; the raw .h5 still goes.
        self.igor_export = igor_export
        self.out_dir = out_dir
        # The Saving tab: the data folder, Igor's Setup ID, who, what, the
        # notes and the save boxes (DEFAULT_SAVING has the keys); the run's
        # file stem (day folder / <experiment>_<HHMMSS>) while a run is
        # going, else None.
        self.saving: dict = dict(DEFAULT_SAVING, folder=Path(out_dir))
        self.run_saving: dict = dict(self.saving)  # the copy a run keeps (_sv)
        self.config_name = ""                  # for the session log
        self.run_stem: Path | None = None
        self.run_started: float | None = None
        # The day's Igor writer (igor_scheme.IgorDayWriter): numbers the
        # traces through the day, keeps the block in progress and writes
        # its files. Made when first needed, remade when the folder, the
        # Setup ID or the date changes; None with --no-igor.
        self.igor: igor_scheme.IgorDayWriter | None = None
        self.run_numbers: list[int] = []       # the day numbers this run's traces got
        # Measured junction voltage per saved trace, sign-corrected, in mV:
        # at the start of the pull (in contact) and at its end (open).
        self.run_v_contact: list[float] = []
        self.run_v_open: list[float] = []
        # Every Stop within the run: after which accepted trace, when, and
        # when Continue carried on. Written into the note and the file.
        self.run_pauses: list[dict] = []
        # A run that Stop interrupted: how many traces it still owes. Its
        # file stays open so Continue can carry on into it.
        self.paused: dict | None = None
        self.writer: storage.SessionWriter | None = None
        self.file_traces: list = []            # this run's (g0, start_v, ts), for the .txt
        self.n_saved = 0                       # traces written to .h5 since launch
        self.save_test_pulls = False           # into a TESTPULLS file, never data
        self.writer_is_test = False
        self.accepted = 0
        self.attempts = 0
        self.rejections: dict[str, int] = {}
        self.hist_sum = None
        self.hist_centres = None
        self.hist_n = 0
        # The same histogram of channel 2 of a two-channel amplifier, on
        # the same bins, summed over the run's accepted traces that have
        # one. Its own sum and its own count: nothing is merged.
        self.hist2_sum = None
        self.hist2_n = 0
        # The noise floor of each accepted trace of the run: the rms of its
        # open end on channel 1 and, when it has one, on channel 2 (None
        # otherwise). For the report; nothing is decided on it.
        self.floors: list = []
        # Pulls in a row whose channel-1 current read negative where the
        # junction conducts (analysis.reads_negative): a current channel
        # whose sign is the wrong way round. Three of them end a run, since
        # nothing can be accepted like that (SIGN_STOP).
        self.negative_in_a_row = 0
        self.sign_cure = ""                    # what to do about it, in words
        # How fast a move TOWARD the surface made by hand goes (Approach,
        # the sliders, Step closer): nm a second. It goes in short pieces
        # and stops at contact (``_approach_by_hand``). The Piezo box sets it.
        self.hand_speed_nm_s = 200.0
        # The sliders (``cmd_follow``). The window writes here from its own
        # thread, through ``follow_begin`` / ``follow_to`` / ``follow_end``:
        # where the knob is, in volts; whether the mouse still holds it; and
        # whether a slider move is under way at all (from the mouse going
        # down until the piezo has got there, or was stopped). One lock for
        # the three, so that a press is never lost between two moves.
        self.follow_lock = threading.Lock()
        self.follow_v: float | None = None
        self.follow_held = False
        self.following = False
        # A simulated card plays a move in no time at all. With this set
        # (the window sets it in a simulation) each piece of a move toward
        # the surface made by hand takes the 25 ms it takes on the rig, so
        # that a slider or Approach tried on a laptop is as slow or as fast
        # as it will be there: distance over speed.
        self.sim_real_time = False
        # The current, in uA, that counts as contact for such a move: the
        # Coarse approach box's contact current, the level of its CONTACT
        # light (``_closed``). The window keeps it in step; 0 switches this
        # sign of contact off. ``contact_why`` is the sign the last such
        # move stopped at, in words.
        self.contact_ua = 0.15
        self.contact_why = ""
        self.bias_dirty = True                 # set_bias before the next cycle
        self.busy = False                      # a command is running
        self.current: str | None = None        # its name
        # The Keithley 428, opened on the first Keithley command. What the
        # program knows of its state: None = unknown until a button sets it.
        self.keithley = None
        self.k_state: dict = {"connected": False, "zero_check": None,
                              "suppress": None, "suppress_ua": None,
                              "gain": cfg.keithley.gain_exponent}
        # The NanoPZ: its port is opened by Connect in the Coarse approach
        # box, never at start-up (a wrong port must not cost the session).
        act = getattr(rig, "actuator", None)
        self.a_state: dict = {"connected": bool(getattr(act, "connected", False)),
                              "port": cfg.actuator.port, "position": None,
                              "steps": 0, "ports": None,
                              "controller": cfg.actuator.kind}

    # -- posting ------------------------------------------------------------

    def post(self, kind: str, **payload) -> None:
        self.events.put((kind, payload))

    def status(self, text: str, level: str | None = None) -> None:
        """A line for the Status box. ``level``: "ok" (green), "bad" (red),
        "busy" (something automatic is running), "warn" (orange), or None
        for the window to judge from the words."""
        self.post("status", text=text, level=level)

    # -- commands from the window --------------------------------------------

    def send(self, *command) -> None:
        self.commands.put(command)

    def quit(self) -> None:
        self.stop_flag.set()
        self._quit.set()
        self.commands.put(("noop",))

    # -- the loop ------------------------------------------------------------

    def run(self) -> None:
        while not self._quit.is_set():
            try:
                command = self.commands.get(timeout=0.2)
            except queue.Empty:
                continue
            if self._quit.is_set():
                break
            name, args = command[0], command[1:]
            if name not in ("monitor", "ratecheck", "noop"):
                self.stop_flag.clear()         # Stop applies to what is running
            self.busy = True
            self.current = name
            try:
                getattr(self, "cmd_" + name, self.cmd_noop)(*args)
            except SafetyViolation as exc:
                # Every SafetyViolation is a refusal made *before* the move,
                # never a report of damage: show it, stop any run, carry on.
                self.post("error", text=f"REFUSED: {exc}", fatal=False)
                self.stop_flag.set()
            except ApproachError as exc:
                self.post("error", text=f"approach: {exc}", fatal=False)
            except Exception as exc:                # noqa: BLE001
                log.exception("command %s failed", name)
                self.post("error", text=f"{name}: {type(exc).__name__}: {exc}",
                          fatal=False)
            finally:
                self.busy = False
                self.current = None
                self.readout()
        if self.run_stem is not None:
            self.end_experiment()
        else:
            self.close_file()
        self.close_keithley()

    def cmd_noop(self) -> None:
        return

    def cmd_ai_modes(self) -> None:
        """Tell the window which input wiring modes this card offers and
        which one is in use (the Settings tab's Input mode box)."""
        self.post("ai_modes", modes=self.rig.ai_terminal_modes(),
                  current=self.cfg.channels.ai_terminal.lower())

    def cmd_ai_terminal(self, name: str) -> None:
        """Switch the record inputs' wiring mode live: the input task is
        rebuilt, the piezo and bias stay where they are, the next file
        carries the new mode in its header."""
        if self.rig.state is RigState.ENGAGED:
            self.status("input mode refused: the tip is in contact; step apart "
                        "first (the inputs are rebuilt, and a reading is lost)")
            return
        self.rig.set_ai_terminal(name)
        self.cmd_newfile()                     # the next file carries the mode
        m = self.cfg.channels
        inputs = list(m.record_inputs)         # channel 2 and the sense line too
        keep = f'"ai_terminal": "{name}"' + (f', "sense_terminal": "{name}"'
                                             if m.sense_in_record else "")
        self.status(f"inputs {', '.join(inputs)} now in {name} mode. To keep it, "
                    f"put {keep} in the config's channels", level="ok")

    def amplifier_state(self) -> dict:
        """The current amplifier as the config has it now, for the window's
        Current amplifier box: how many outputs are read, whether the
        config names an input for channel 2 at all, the inputs, the gains."""
        m, C = self.cfg.channels, self.cfg.cal
        return {"channels": 2 if m.two_current_channels else 1,
                "available": bool(m.ai_current_2),
                "ch1": m.path(m.ai_current),
                "ch2": m.path(m.ai_current_2) if m.ai_current_2 else None,
                "gain1": C.preamp_gain_v_per_a, "gain2": C.preamp_gain_2_v_per_a,
                "sign1": C.sign_of(1), "sign2": C.sign_of(2)}

    def cmd_amplifier(self) -> None:
        """Tell the window how the current amplifier is read."""
        self.post("amplifier", **self.amplifier_state())

    def piezo_state(self) -> dict:
        """The piezo driver as the config has it now, for the Piezo box:
        the mode, the total displacement (None: not set, the scale is the
        config's own number), nm per card volt, and the reach of the
        card's whole output range in nm."""
        C, L = self.cfg.cal, self.cfg.limits
        return {"mode": str(C.piezo_mode).lower(), "total_um": C.piezo_total_um,
                "nm_per_volt": C.piezo_nm_per_volt,
                "reach_nm": (L.piezo_ao_max_v - L.piezo_ao_min_v) * C.piezo_nm_per_volt,
                "full_v": C.piezo_drive_full_v, "gain": C.piezo_drive_gain}

    def cmd_piezo(self) -> None:
        """Tell the window how the piezo driver is set."""
        self.post("piezo", **self.piezo_state())

    def cmd_piezo_mode(self, mode: str, total_um: float) -> None:
        """The Piezo box's Set: the driver's mode ("standard" or "bypass")
        and the stage's total displacement in micrometres. The two scales
        (nm per card volt, nm per sense volt) follow from them
        (``Calibration.apply_piezo_mode``); the next file carries them.

        When the MODE changes, the piezo is first taken to 0 V and stays
        there. The switch on the box is about to be flipped, and at any
        other voltage that would move the tip by micrometres: from bypass
        to standard, 8 V at the card goes from 8 V to 120 V at the piezo.
        At 0 V, and only there, the two modes agree. So a change of mode is
        refused when the piezo cannot be taken to 0 V (this rig's limits do
        not include it) or stands below it (going up to 0 V would be a move
        toward the surface). A change of the total displacement alone moves
        nothing.

        Nothing here can tell where the switch really stands. The mode is
        what the person at the rig says it is."""
        mode = str(mode).lower()
        C, L = self.cfg.cal, self.cfg.limits
        try:
            total_um = float(total_um)
        except (TypeError, ValueError):
            total_um = float("nan")
        # Tried on a copy first: nothing is changed, and nothing moves, for
        # numbers the scales cannot be worked out from.
        trial = copy.copy(C)
        trial.piezo_total_um, trial.piezo_mode = total_um, mode
        if mode not in ("standard", "bypass") or not 0 < total_um <= 1000 \
                or not trial.apply_piezo_mode():
            self.status("piezo driver: refused. The mode is standard or bypass and "
                        "the total displacement a number of micrometres "
                        "(10.776, say)", "bad")
            self.post("piezo", **self.piezo_state())
            return
        if self.run_stem is not None and self.paused is None:
            self.status("a run is in progress: press Stop before changing the "
                        "piezo driver's mode")
            self.post("piezo", **self.piezo_state())
            return
        switching = mode != str(C.piezo_mode).lower()
        was_v = self.rig.piezo_v
        if switching:
            why = ""
            if not L.piezo_ao_min_v <= 0.0 <= L.piezo_ao_max_v:
                why = (f"this rig's piezo range ({L.piezo_ao_min_v:g} to "
                       f"{L.piezo_ao_max_v:g} V) does not include 0 V")
            elif was_v < -1e-9:
                why = (f"the piezo is at {was_v:.3f} V, below it. Take it to "
                       "0 V with the slider first")
            if why:
                self.status("piezo driver: the mode was NOT changed. The switch "
                            "on the driver may only be flipped with the piezo "
                            f"at 0 V, and {why}", "bad")
                self.post("piezo", **self.piezo_state())
                return
            if was_v > 1e-9:
                self.rig.piezo_ramp_to(0.0)
            self.rig.state = RigState.RETRACTED
        C.piezo_total_um, C.piezo_mode = total_um, mode
        C.apply_piezo_mode()
        self.cmd_newfile()                     # the config travels with the data
        state = self.piezo_state()
        self.post("piezo", **state)
        self.post("moved", cycle=self.mon.snapshot())
        # The status box shows three lines and no more: what has to be done
        # comes first, and the numbers stand in the Driver row's own line.
        keep = (f'To keep it: "piezo_total_um": {total_um:g}, "piezo_mode": '
                f'"{mode}" in the config\'s cal')
        if switching:
            came = f" (it was at {was_v:.3f} V)" if was_v > 1e-9 else ""
            self.status(f"NOW PUT THE SWITCH ON THE DRIVER TO {mode.upper()}. The "
                        f"piezo is at 0 V{came}. {keep}", "warn")
        else:
            self.status(f"Piezo driver {mode.upper()}, {total_um:g} um in all: 1 V "
                        f"at the card = {state['nm_per_volt']:.2f} nm. {keep}", "ok")

    def cmd_current_sign(self, channel: int, sign: float) -> None:
        """Turn one current channel the other way round: the Current
        amplifier box's "flip the sign". ``cal.current_sign`` for channel
        1, ``cal.current_sign_2`` for channel 2, +1 or -1. It is arithmetic
        only: nothing on the rig changes and the bias on the junction stays
        as it is. The next file carries the new sign."""
        channel = 2 if int(channel) == 2 else 1
        sign = -1.0 if float(sign) < 0 else 1.0
        name = "current_sign_2" if channel == 2 else "current_sign"
        C = self.cfg.cal
        if C.sign_of(channel) == sign:
            self.post("amplifier", **self.amplifier_state())
            return
        setattr(C, name, sign)
        self.cmd_newfile()                     # the config travels with the data
        self.post("amplifier", **self.amplifier_state())
        # (The Status box shows three lines: these fit.)
        if sign < 0:
            self.status(f"ch {channel}: sign flipped (current = -(V - zero) / "
                        "gain). The next trace shows it. To keep it, put "
                        f'"{name}": -1 in the "cal" part of the config file',
                        level="ok")
        else:
            self.status(f"ch {channel}: sign as the amplifier gives it (current "
                        "= (V - zero) / gain). The next trace shows it. To keep "
                        f'it, put "{name}": 1 in the "cal" part of the config '
                        "file", level="ok")

    def cmd_current_channels(self, n: int) -> None:
        """Read one output of the current amplifier or both, live: the
        input task is rebuilt with or without channel 2, the piezo and
        the bias stay where they are, and the next file carries it.
        Contact is channel 1's either way; the junction-open test moves to
        channel 2 with two channels and back to channel 1 with one."""
        n = int(n)
        m = self.cfg.channels
        if n == (2 if m.two_current_channels else 1):
            self.post("amplifier", **self.amplifier_state())
            return
        if n == 2 and not m.ai_current_2:
            self.status('two channels refused: the config names no input for '
                        'channel 2. Put "ai_current_2": "ai4" (the card input '
                        'channel 2 is wired to) in the config\'s channels',
                        level="bad")
            self.post("amplifier", **self.amplifier_state())
            return
        if self.rig.state is RigState.ENGAGED:
            self.status("current channels refused: the tip is in contact; step "
                        "apart first (the inputs are rebuilt, and a reading is lost)")
            self.post("amplifier", **self.amplifier_state())
            return
        try:
            self.rig.set_current_channels(n)
        except Exception as exc:                   # noqa: BLE001
            self.post("amplifier", **self.amplifier_state())
            self.status(f"current channels: the card refused {m.path(m.ai_current_2)} "
                        f"({type(exc).__name__}: {str(exc).splitlines()[0]}); still "
                        "reading one channel", level="bad")
            return
        self.cmd_newfile()                     # the next file carries the count
        self.hist2_sum, self.hist2_n = None, 0
        if self.histogram() is not None:
            # The run's histogram so far stays; channel 2's starts again.
            self.post("hist", centres=self.hist_centres, counts=self.histogram(),
                      n=self.hist_n, counts2=None)
        self.post("amplifier", **self.amplifier_state())
        C = self.cfg.cal
        if n == 2:
            self.status(f"two current channels: ch 1 on {m.path(m.ai_current)} "
                        f"({C.preamp_gain_v_per_a:g} V/A), which contact is judged "
                        f"on, and ch 2 on {m.current2_path} "
                        f"({C.preamp_gain_2_v_per_a:g} V/A), drawn in red, which the "
                        'Break threshold is judged on. Calibrate zero now takes '
                        'both. To keep it, put "current_channels": 2 in the '
                        'config\'s channels', level="ok")
        else:
            self.status(f"one current channel: {m.path(m.ai_current)} "
                        f"({C.preamp_gain_v_per_a:g} V/A); channel 2 is not read. "
                        'To keep it, put "current_channels": 1 in the config\'s '
                        "channels", level="ok")

    def cmd_monitor(self) -> None:
        """One quiet 10 ms hold at the present position and bias, for the
        monitor window and the Piezo box's readouts: nothing moves, the
        inputs are simply read (Igor's background sampling)."""
        self.mon.quiet = True
        try:
            rec = self.rig.hold(n_samples=400)
        finally:
            self.mon.quiet = False
        sense = self.rig.last_sense_v
        sense_v = (float(np.mean(sense[sense.size // 2:]))
                   if sense is not None and sense.size else None)
        self.post("monitor", t=time.monotonic(), record=rec,
                  piezo_v=self.rig.piezo_v, sense_v=sense_v,
                  ch2=self.rig.channel2_of(rec))

    def cmd_ratecheck(self, seconds: float = 1.0) -> None:
        """The Monitor window's sample-rate check (``stmlab.ratecheck``).
        Nothing moves: the piezo and the bias are held where they are for
        ``seconds`` while every input in use records, as in a pull. The
        numbers the card returned go into a scratch file, the file is read
        back and counted, and the file is deleted. The same record is kept
        in the data folder as ``sampling_rate_test.csv``, one row per
        sample, written afresh by every check, to be opened in Excel. The
        time the card took comes from this PC's clock, as a rough
        cross-check. The end of the record also feeds the readouts, as a
        monitor sample would."""
        self.mon.quiet = True
        try:
            result = ratecheck.measure(
                self.rig, seconds, keep=self.saving.get("folder") or self.out_dir)
        except Exception as exc:                   # noqa: BLE001
            log.exception("sample-rate check failed")
            self.post("ratecheck", error=f"{type(exc).__name__}: "
                                         f"{str(exc).splitlines()[0] if str(exc) else ''}")
            return
        finally:
            self.mon.quiet = False
        rec = result.pop("record")
        self.post("ratecheck", **result)
        keep = min(400, rec.shape[1])
        tail = rec[:, -keep:]
        sense = self.rig.last_sense_v
        sense_v = (float(np.mean(sense[-keep // 2:]))
                   if sense is not None and sense.size else None)
        second = self.rig.last_current2_v
        self.post("monitor", t=time.monotonic(), record=tail,
                  piezo_v=self.rig.piezo_v, sense_v=sense_v,
                  ch2=self.rig.channel2_of(
                      tail, None if second is None else second[-keep:]))

    # -- the Keithley 428 ----------------------------------------------------------

    def _keithley(self):
        if self.keithley is None:
            from stmlab import keithley as kmod
            k = kmod.make_keithley(self.cfg)
            k.open(init=False)             # join the session; change nothing
            self.keithley = k
            self.k_state["connected"] = True
            if self.cfg.simulate:          # the simulated card sees its suppress
                setattr(self.rig._session, "keithley", k)
        return self.keithley

    def close_keithley(self) -> None:
        if self.keithley is not None:
            try:
                self.keithley.close(inert=False)   # leave it as it is
            except Exception:
                pass
            self.keithley = None

    def cmd_keithley(self, action: str, *args) -> None:
        """Igor's Keithley Controls. Every action reports the state it left
        the amplifier in, and the window shows it."""
        K = self.cfg.keithley
        try:
            k = self._keithley()
        except Exception as exc:                 # noqa: BLE001
            self.status(f"Keithley: could not open {K.resource}: {exc}. "
                        "pyvisa and a VISA backend are needed (see the "
                        "Keithley tab); the front-panel buttons do the same."
                        + (" The gain the program computes with needs no "
                           "Keithley: type it in the Current amplifier box "
                           "(Settings tab)." if action == "gain" else ""))
            return
        sim = " (simulated)" if self.cfg.simulate else ""
        if action == "connect":
            self.status(f"Keithley 428 at {K.resource} connected{sim}; its "
                        "state is unknown until a button sets it")
        elif action == "zero_check":
            on = bool(args[0])
            k.zero_check(on)
            self.k_state["zero_check"] = on
            self.status("zero check ON: the amplifier's input is shorted and it "
                        "reads nothing until you turn it off" if on else
                        "zero check OFF: the amplifier is live")
        elif action == "zero_correct":
            k.zero_check(True)
            k.zero_correct()
            time.sleep(0.5)
            k.zero_check(False)
            self.k_state["zero_check"] = False
            self.status("zero corrected (zero check on, correct, off): the "
                        "amplifier is live. Press Calibrate zero next so the "
                        "software zero matches the new hardware zero.")
        elif action == "suppress":
            on = bool(args[0])
            k.suppress_enable(on)
            self.k_state["suppress"] = on
            self.status(f"current suppress {'ON' if on else 'OFF'}"
                        + (f" ({k.suppress_ua:+.4f} uA)" if on else ""))
        elif action == "find_suppress":
            if self.k_state["zero_check"]:
                self.status("find suppress refused: zero check is ON, the "
                            "amplifier would read nothing. Turn it off first.")
                return
            if self.rig.state is RigState.ENGAGED:
                self.status("find suppress refused: the tip is in contact; it "
                            "must be out of contact (Step apart, or the slider down)")
                return
            from stmlab import keithley as kmod
            self.status("finding the suppress: 21 points from -1 to +1 uA at "
                        "0 V bias, about 3 s ...")
            was = self.rig.bias_v
            self.mon.quiet = True
            # The sweep only does anything with the suppress switched ON:
            # swept with it off, the output stays flat, the fit through the
            # noise puts the zero crossing anywhere, and switching that value
            # on afterwards rails the amplifier (seen on the rig).
            k.suppress_enable(True)
            try:
                value, sweep, readings = kmod.find_suppress(self.rig, k)
                self.rig.hold(bias_v=was)
            finally:
                self.mon.quiet = False
            # Sanity: the output must have followed the sweep at the gain's
            # slope (1 V per uA at 1e6 V/A), and an offset current of more
            # than half a microamp is not an offset but a wrong fit.
            slope = float(np.polyfit(sweep[1:-1], readings[1:-1], 1)[0])  # V per uA
            expected = self.cfg.cal.preamp_gain_v_per_a * 1e-6
            if abs(slope) < 0.2 * abs(expected) or abs(value) > 0.5:
                k.set_suppress_ua(0.0)
                k.suppress_enable(False)
                self.k_state.update(suppress=False, suppress_ua=0.0)
                self.bias_dirty = True
                self.status(f"find suppress: the sweep did not behave (slope "
                            f"{slope:+.2f} V/uA, expected about {expected:+.2f}; "
                            f"fit {value:+.3f} uA), so the suppress is set to 0 "
                            "and OFF. At 1e6 V/A it is not needed anyway: press "
                            "Calibrate zero.")
                return
            self.k_state.update(suppress=True, suppress_ua=float(value))
            self.bias_dirty = True
            self.status(f"current suppress set to {value:+.4f} uA and ON "
                        f"(output {readings.min() * 1e3:+.2f} to "
                        f"{readings.max() * 1e3:+.2f} mV across the sweep). "
                        "Press Calibrate zero next.")
        elif action == "gain":
            n = int(args[0])
            k.set_gain(n)
            K.gain_exponent = n
            self.cfg.cal.preamp_gain_v_per_a = 10.0 ** n
            self.k_state["gain"] = n
            self.close_file()                  # the config travels with the data
            self.status(f"gain set to 1e{n} V/A on the amplifier and in cal "
                        "(preamp_gain_v_per_a); the session file was closed so "
                        "the next one carries the new gain")
        self.post("keithley", **self.k_state)

    # -- the coarse actuator: Igor's Actuator Controls ------------------------------

    def _actuator_ready(self) -> bool:
        """True when a step can be sent; otherwise the status says what to do."""
        act = self.rig.actuator
        if getattr(act, "connected", False):
            return True
        if self.cfg.actuator.kind == "none":
            self.status("no actuator configured or connected: choose the "
                        "controller and its COM port and press Connect in the "
                        "Coarse approach box (or use the screw by hand, "
                        "watching I (uA) and the contact light)")
        else:
            self.status("the actuator is not connected: choose the controller "
                        "and its COM port and press Connect in the Coarse "
                        "approach box")
        return False

    def _post_actuator(self) -> None:
        act = self.rig.actuator
        on = bool(getattr(act, "connected", False))
        self.a_state.update(connected=on, steps=self.rig.coarse_steps,
                            position=act.position() if on else None)
        self.post("actuator", **self.a_state)

    def cmd_actuator(self, action: str, *args) -> None:
        """The NanoPZ link. Igor opened Com1 when it started; here the port
        is chosen in the window and opened on Connect, and the controller
        has to answer a status query before the program believes it."""
        from stmlab import actuator as amod
        if action == "ports":
            try:
                ports = amod.list_serial_ports()
            except amod.ActuatorError as exc:
                self.status(f"{exc}. On the lab PC: pip install pyserial")
                return
            self.a_state["ports"] = ports
            agilis = [d for d, desc in ports if "AG-UC" in desc.upper()]
            self.status("serial ports on this PC: "
                        + (", ".join(f"{d} ({desc})" for d, desc in ports)
                           or "none found (Device Manager -> Ports (COM & LPT))")
                        + (f". {', '.join(agilis)} is a Newport Agilis AG-UC2/UC8: "
                           "if that is the coarse actuator, choose Agilis and "
                           "that port" if agilis else ""))
            self.post("actuator", **self.a_state)
            return
        if action == "connect":
            port = (args[0] if args and args[0] else self.cfg.actuator.port).strip()
            kind = (args[1] if len(args) > 1 and args[1] else self.cfg.actuator.kind)
            kind = kind.lower() if kind.lower() in amod.KINDS else "nanopz"
            name = {"nanopz": "NanoPZ", "agilis": "Agilis"}[kind]
            if self.cfg.simulate:
                act = amod.SimulatedActuator(self.cfg, getattr(self.rig, "_session", None))
                reply = {"status": "simulated", "position": act.position(), "port": port}
            else:
                act = None
                try:
                    act = amod.KINDS[kind](self.cfg, port=port)
                    reply = act.identify()
                except Exception as exc:          # noqa: BLE001
                    if act is not None:
                        act.close()               # free the port for the next try
                    self.status(f"{name}: {exc}")
                    self.a_state.update(connected=False)
                    self.post("actuator", **self.a_state)
                    return
            self.rig.attach_actuator(act)
            self.cfg.actuator.port = port
            self.cfg.actuator.kind = kind              # the config travels with the data
            self.a_state.update(port=port, controller=kind)
            where = reply.get("resource") or port
            self.status(f"{name} connected at {where}"
                        + (f": {reply['version']}" if reply.get("version") else "")
                        + f", status {reply['status']!r}, step counter "
                          f"{reply['position']}. Step apart first and watch the "
                          "counter fall; Start approach puts the piezo at "
                          f"{self.cfg.actuator.approach_piezo_v:g} V and steps "
                          "the sample in")
            self._post_actuator()
            return
        self.status(f"actuator: unknown action {action!r}")

    def cmd_coarse_step(self, closer: bool) -> None:
        """One actuator step, through the interlock: refused unless the
        piezo is at or below its approach position, and, closer, unless the
        junction is open -- a coarse step into a closed junction is a crash."""
        if not self._actuator_ready():
            return
        if closer and self.rig.state is RigState.ENGAGED:
            self.status("Step closer refused: the junction is closed (engaged). "
                        "Step apart on the piezo (or the slider down) first")
            return
        try:
            self.rig.coarse_step(closer=closer)
        except (NotImplementedError, ActuatorError) as exc:
            self.status(f"actuator: {exc}")
            return
        self._post_actuator()
        pos = self.a_state["position"]
        self.status(f"actuator stepped {'closer' if closer else 'apart'} "
                    f"({self.rig.coarse_steps} steps this session"
                    + (f", position {pos}" if pos is not None else "") + ")")

    def cmd_coarse_approach(self) -> None:
        """Igor's Start Approach (HighResCardApproach): the fine piezo at its
        approach position (mid range), the actuator stepping the sample in
        until the current passes ``actuator.stop_current_ua``, then the
        fine piezo retracting until the junction is open -- so it is left a
        few nanometres from the surface with room both ways. Stop ends it
        between steps."""
        if not self._actuator_ready():
            return
        if self.bias_dirty:
            self.cmd_bias()
        A, C = self.cfg.actuator, self.cfg.cal
        self.rig.hold(bias_v=self.cfg.ramp.bias_v)
        self.mon.begin_cycle()
        self.mon.mark("approach")
        self.status(f"coarse approach: piezo at {A.approach_piezo_v:g} V, the "
                    f"sample stepping in until {A.stop_current_ua:g} uA, then "
                    f"aiming the contact between {A.band_lo_v:g} and "
                    f"{A.band_hi_v:g} V ... (automatic: do not touch)", level="busy")
        try:
            r = approach.coarse_approach(self.rig, self.stop_flag)
        except ApproachError as exc:
            self._post_actuator()
            self.post("moved", cycle=self.mon.snapshot())
            self.status(f"coarse approach: {exc}", level="bad")
            return
        except ActuatorError as exc:
            self.status(f"actuator: {exc}", level="bad")
            self._post_actuator()
            return
        self._post_actuator()
        self.post("moved", cycle=self.mon.snapshot())
        room_out = C.piezo_volts_to_nm(r["open_v"] - self.cfg.limits.piezo_ao_min_v)
        room_in = C.piezo_volts_to_nm(self.cfg.limits.piezo_ao_max_v - r["open_v"])
        self.status(f"coarse approach done: {r['steps_in']} steps in, then "
                    f"{r['rounds']} round(s) of aiming; contact at "
                    f"{r['contact_v']:.2f} V, junction opened at {r['open_v']:.3f} V "
                    f"({room_out:.0f} nm of room to retract, {room_in:.0f} nm to "
                    "extend)"
                    + (f"; one single actuator step = {r['step_v']:.2f} V of "
                       "contact" if r.get("step_v") else "")
                    + ". Now Start N", level="ok")

    # -- moves made by hand: the slider and the step buttons ----------------------

    def cmd_goto(self, volts: float) -> None:
        """Igor's SetPiezoBiasFromSlider: put the piezo at ``volts``.

        Away from the surface the move is made at once, along a 50 ms ramp.
        Toward the surface it goes at ``hand_speed_nm_s`` and stops where
        the junction closes (``_approach_by_hand``). Then the junction is
        probed and the state follows what it reads, so a contact made by
        hand can be pulled from with the pull command (headless), as Igor's
        slider-then-measure could. Start N needs no state: it separates first.
        """
        volts = float(volts)
        if not math.isfinite(volts):
            self.status("the piezo was not moved: that voltage is not a number",
                        "bad")
            return
        self._begin_by_hand()
        was = self.rig.piezo_v
        L = self.cfg.limits
        target = min(max(volts, L.piezo_ao_min_v), L.piezo_ao_max_v)
        if target > was + 1e-9:
            ended = self._approach_by_hand(target)     # toward the surface
        else:
            self.rig.piezo_ramp_to(target)             # away from it: at once
            ended = "there"
        g0, word, second = self._settle_by_hand()
        short = target - self.rig.piezo_v
        ending = ""
        if short > 1e-9:                       # it ended before it got there
            ending = {"contact": f"STOPPED AT CONTACT ({self.contact_why})",
                      "stop": "stopped by Stop"
                      }[ended] + (f", {short:.4f} V short of the {target:.4f} V "
                                  "asked for. ")
        self.status(f"{ending}piezo {was:.4f} -> {self.rig.piezo_v:.4f} V "
                    f"({self.rig.piezo_nm:.1f} nm): G = {g0:.3e} G0{second}, {word}",
                    "warn" if ending else None)

    # -- the sliders: the piezo follows the knob ------------------------------

    def follow_begin(self, volts: float) -> None:
        """From the window: the mouse has gone down on a slider and its knob
        is at ``volts``. A ``follow`` command is queued unless one is waiting
        already; if one is running it simply takes the new place."""
        with self.follow_lock:
            self.follow_v = float(volts)
            self.follow_held = True
            self.following = True
        if not any(c[0] == "follow" for c in list(self.commands.queue)):
            self.send("follow")

    def follow_to(self, volts: float) -> bool:
        """From the window: the knob has been dragged to ``volts``. False
        when no slider move is under way any more (Stop ended it, or an
        error): the drag is over, and the knob goes back on the piezo."""
        with self.follow_lock:
            if not self.following:
                return False
            self.follow_v = float(volts)
            return True

    def follow_end(self) -> None:
        """From the window: the mouse has let go. The piezo finishes its
        way to where the knob was left, and ``cmd_follow`` then ends."""
        with self.follow_lock:
            self.follow_held = False

    # While the mouse rests on a knob the piezo has already reached, the
    # junction is looked at this often (seconds between two looks).
    FOLLOW_REST_S = 0.03

    def cmd_follow(self) -> None:
        """The sliders: take the piezo to where the knob is, and go on
        following the knob for as long as the mouse holds it.

        One click on the bar and the piezo goes there; a drag and it follows
        the knob. The rules of every move made by hand hold (``cmd_goto``):
        away from the surface at once, along a 50 ms ramp; toward the
        surface at ``hand_speed_nm_s`` in pieces of 25 ms, the junction read
        at the end of each, stopping where it closes (``_closed``). So the
        knob can be ahead of the piezo, and the window shows both.

        A slider never pushes into a junction that is closed. Before the
        first piece of every stretch toward the surface the junction is
        looked at where the piezo stands, and if it is closed already the
        piezo stays (Step closer is the way to press further in, by Z nm).
        After a contact the piezo goes no further toward the surface
        wherever the knob is taken; it follows the knob again once the knob
        has come back below it, and comes up again only if the junction has
        opened. So clicking past a contact again and again costs nothing
        (with ``cmd_goto``'s rule, one more piece each time, ten clicks at
        2000 nm/s would be half a micrometre into the surface).

        The move ends when the mouse has let go and the piezo is at the
        knob (or held back by the contact), or when Stop is pressed. A
        press on a knob that takes it nowhere moves nothing and says
        nothing.
        """
        with self.follow_lock:
            if not self.following:
                return                         # nothing asked since the last one ended
        C, L = self.cfg.cal, self.cfg.limits
        look = max(8, int(round(self.HAND_LOOK_S * self.rig.sample_rate_hz)))
        was = asked = self.rig.piezo_v
        wall = None                # a contact was found here: no further up
        rising = already = False   # on a stretch toward the surface; closed before it
        ended, begun, pieces = "there", False, 0
        said_at, slow_s, clean = 0.0, 0.0, False
        try:
            while True:
                with self.follow_lock:
                    target, held = self.follow_v, self.follow_held
                    here = self.rig.piezo_v
                    if target is None or not math.isfinite(target):
                        target = here
                    target = min(max(target, L.piezo_ao_min_v), L.piezo_ao_max_v)
                    blocked = wall is not None and target > here + 1e-9
                    resting = abs(target - here) <= 1e-9 or blocked
                    stopped = self.stop_flag.is_set()
                    if stopped or (resting and not held):
                        self.following = False
                        ended = ("stop" if stopped else
                                 "contact" if blocked else "there")
                        asked, clean = target, True
                        break
                if not resting and not begun:
                    self._begin_by_hand()
                    begun = True
                if target < here - 1e-9:                   # away from the surface: at once
                    self.rig.piezo_ramp_to(target)
                    wall, rising = None, False
                    if self.rig.piezo_v > here - 1e-12:    # it did not move: never a loop
                        with self.follow_lock:
                            self.follow_v = self.rig.piezo_v
                elif not resting:                          # toward it: piece by piece
                    if not rising:
                        # a new stretch toward the surface: a look at the
                        # junction where the piezo stands, before any move
                        rising = True
                        why = self._closed(self.rig.piezo_glide_to(here, self.HAND_PIECE_S),
                                           tail=look)
                        if why:
                            self.contact_why, wall, already = why, here, True
                            continue
                    already = False
                    speed = max(float(self.hand_speed_nm_s), 1.0)
                    step_v = speed / C.piezo_nm_per_volt * self.HAND_PIECE_S
                    left_s = (target - here) * C.piezo_nm_per_volt / speed
                    now = time.monotonic()
                    if left_s > 1.5 and now - said_at > 1.0:
                        said_at = now
                        self.status(f"going toward the surface to {target:.3f} V at "
                                    f"{speed:g} nm/s: about {left_s:.0f} s more (the "
                                    "box beside Approach is the speed; Stop ends it)",
                                    "busy")
                    started = time.monotonic()
                    record = self.rig.piezo_glide_to(min(target, here + step_v),
                                                     self.HAND_PIECE_S)
                    if self.sim_real_time:
                        time.sleep(self.HAND_PIECE_S)  # as long as the rig takes
                    slow_s += time.monotonic() - started
                    why = self._closed(record, tail=look)
                    if not why and self.rig.piezo_v <= here + 1e-12:
                        why = "the piezo does not go further"     # never a loop
                    if why:
                        self.contact_why = why
                        wall = self.rig.piezo_v
                else:
                    # at the knob (or held back by the contact) with the
                    # mouse still down: a look at the junction now and then,
                    # so that the readouts stay live under a resting hand
                    rising = False
                    if begun:
                        self.rig.piezo_glide_to(here, self.HAND_PIECE_S)
                    time.sleep(self.FOLLOW_REST_S)
                pieces += 1
                if begun and pieces % 4 == 0:
                    self.readout()                 # the readouts and the mark follow
                    if self.mon.spent():           # a long way: a fresh picture
                        self.mon.begin_cycle()
                        self.mon.mark("by hand")
        finally:
            if not clean:                          # an error ends the move too
                with self.follow_lock:
                    self.following = False
        if not begun:
            return                                 # the knob was taken nowhere
        g0, word, second = self._settle_by_hand()
        short = asked - self.rig.piezo_v
        ending = ""
        if ended == "contact" and short > 1e-9 and already:
            ending = (f"ALREADY IN CONTACT ({self.contact_why}): a slider does not "
                      "push further in (Step closer does, by Z nm). ")
        elif ended == "contact" and short > 1e-9:
            ending = (f"STOPPED AT CONTACT ({self.contact_why}), {short:.4f} V short "
                      f"of the {asked:.4f} V asked for. ")
        elif ended == "stop" and abs(short) > 1e-9:
            ending = (f"stopped by Stop, {abs(short):.4f} V short of the "
                      f"{asked:.4f} V asked for. ")
        took = f" in {slow_s:.0f} s" if slow_s >= 2.0 else ""
        self.status(f"{ending}piezo {was:.4f} -> {self.rig.piezo_v:.4f} V "
                    f"({self.rig.piezo_nm:.1f} nm){took}: G = {g0:.3e} G0{second}, "
                    f"{word}", "warn" if ending else None)

    def cmd_piezo_approach(self) -> None:
        """The Piezo box's Approach: the piezo itself comes up to the
        surface, after the screws have brought the surface within its
        reach. From where the piezo is, toward the surface at
        ``hand_speed_nm_s``, until the junction closes
        (``_approach_by_hand``, ``_closed``).

        Contact: the piezo stays there, and the window puts its fine slider
        around that place. No contact all the way to the top of the range:
        the piezo is taken back to where it started (over half a second),
        and the status line says to approach with the screw again. Stop
        ends it where it is."""
        C, L = self.cfg.cal, self.cfg.limits
        self._begin_by_hand()
        start, top = self.rig.piezo_v, L.piezo_ao_max_v

        def here() -> str:
            return f"{self.rig.piezo_v:.4f} V = {self.rig.piezo_nm:.1f} nm"
        why = self._closed(self.rig.hold())
        if why:
            self._settle_by_hand()
            self.status(f"already in contact at {here()} ({why}): nothing to "
                        "approach. Step apart first, or Start N", "warn")
            return
        if start >= top - 1e-9:
            self._settle_by_hand()
            self.status(f"NO CONTACT, and the piezo is at the top of its range "
                        f"({top:g} V): take it down with the coarse slider, then "
                        "approach with the screw again", "warn")
            return
        self.status(f"approaching with the piezo from {start:.3f} V, at "
                    f"{self.hand_speed_nm_s:g} nm/s ... (Stop ends it)", "busy")
        ended = self._approach_by_hand(top)
        if ended == "contact":
            why = self.contact_why
            self._settle_by_hand()
            # A pull goes down from here: is there room for one?
            R = self.cfg.ramp
            room = (self.rig.piezo_v - C.nm_to_piezo_volts(R.pull_length_nm)
                    >= L.piezo_ao_min_v + R.piezo_headroom_v)
            self.status(f"CONTACT at {here()} ({why}). "
                        + ("The piezo stays there and the fine slider is around "
                           "it. Now Start N" if room else
                           "That is too low in the range to pull from: turn the "
                           "screw back a little, then Approach again"),
                        "ok" if room else "warn")
        elif ended == "stop":
            g0, word, second = self._settle_by_hand()
            self.status(f"Approach stopped by Stop at {here()}: G = {g0:.3e} G0"
                        f"{second}, {word}", "warn")
        else:
            self.rig.piezo_ramp_to(start, ramp_s=0.5)
            self._settle_by_hand()
            self.status(f"NO CONTACT for the whole range (up to {top:g} V = "
                        f"{C.piezo_volts_to_nm(top):.0f} nm): approach with the "
                        f"screw again. The piezo is back at {start:.3f} V", "warn")

    def cmd_sim_surface(self, nm: float) -> None:
        """The simulator's screw: put the pretend surface ``nm`` up the
        piezo's travel. On a rig whose coarse approach is a screw turned by
        hand the simulator has nothing to turn, and its surface stays at
        300 nm: 0.28 V on a stage with a micrometre to the volt. With this
        it can be put where a real one ends up (near 8 V, say), or out of
        the piezo's reach. Simulation only."""
        session = getattr(self.rig, "_session", None)
        if not self.cfg.simulate or not hasattr(session, "move_surface"):
            self.status("the simulator's screw: this is not a simulation", "bad")
            return
        try:
            nm = float(nm)
        except (TypeError, ValueError):
            nm = float("nan")
        if not math.isfinite(nm):
            self.status("the simulator's screw: that is not a number of nm", "bad")
            return
        if nm < self.rig.piezo_nm + 1.0:
            self.status(f"the simulator's screw: {nm:g} nm would push the surface "
                        f"into the tip (the piezo is at {self.rig.piezo_nm:.1f} nm). "
                        "Take the piezo down first", "bad")
            return
        session.move_surface(nm - session.surface_nm)
        C, L = self.cfg.cal, self.cfg.limits
        reach = C.piezo_volts_to_nm(L.piezo_ao_max_v)
        self.status(f"simulator's screw: the surface is now {nm:g} nm up the "
                    f"piezo's travel, "
                    + (f"which is {C.nm_to_piezo_volts(nm):.3f} V"
                       if nm <= reach else
                       f"out of the piezo's reach ({reach:.0f} nm)"), "ok")

    def _begin_by_hand(self) -> None:
        """Before a move made by hand: the bias on, and a fresh picture for
        a fresh series of moves (a cycle that has pulled is finished; one
        that has not keeps accumulating, until it has grown long)."""
        if self.bias_dirty:
            self.cmd_bias()
        if self.mon.spent():
            self.mon.begin_cycle()
            self.mon.mark("by hand")

    def _settle_by_hand(self) -> tuple[float, str, str]:
        """After a move made by hand: probe the junction, let the state
        follow what it reads, and tell the window. Returns (G in G0, a word
        for the junction, channel 2's reading in words)."""
        g0, railed = self.rig.probe()
        # The same probe on the open side: channel 2 of a two-channel
        # amplifier while it is in range, else this same pair.
        g_open, railed_open, ch_open = self.rig.open_side()
        R = self.cfg.ramp
        record = self.mon.last().last_record       # that probe's own record
        if railed or g0 > R.engage_g0 or (record is not None
                                          and self._closed(record)):
            self.rig.state = RigState.ENGAGED
            word = "in contact"
        else:
            # Not parked, not engaged: the tip is wherever the hand left it.
            self.rig.state = RigState.UNKNOWN
            word = ("open" if not railed_open and g_open < R.break_g0
                    else "tunnelling")
        self.post("moved", cycle=self.mon.snapshot())
        second = f" (ch 2: {g_open:.3e} G0)" if ch_open == 2 else ""
        return g0, word, second

    def _closed(self, record: np.ndarray, tail: int | None = None) -> str:
        """Has the junction closed, going by the end of ``record``? "" for
        no; else why, in a few words for the status line. Any one of three
        signs says yes:

        * the amplifier is at its rail;
        * the conductance is above the Engage threshold;
        * the current is above the contact current (``contact_ua``, the
          level of the Coarse approach box's CONTACT light).

        The third does not use the junction voltage. On a rig whose
        conductance reading has a ceiling (an offset of a few millivolts on
        the junction voltage caps G near 4 G0 on the new rig) the second
        never comes with Engage above that ceiling, and through a series
        resistor the first never comes at all."""
        R = self.cfg.ramp
        if self.rig.is_saturated(record, tail=tail):
            return "the amplifier is at its rail"
        g0 = self.rig.conductance_of(record, tail=tail)
        if g0 > R.engage_g0:
            return f"G = {g0:.3g} G0"
        ua = abs(self.rig.current_ua_of(record, tail=tail))
        if self.contact_ua > 0 and ua > self.contact_ua:
            return f"{ua:.3g} uA, above the contact current"
        return ""

    # A move toward the surface made by hand goes in pieces this long, and
    # the junction is read from this much of the end of each.
    HAND_PIECE_S = 0.025
    HAND_LOOK_S = 0.001

    def _approach_by_hand(self, target_v: float) -> str:
        """Take the piezo toward the surface to ``target_v`` at
        ``hand_speed_nm_s``, in pieces of 25 ms, reading the junction at
        the end of each: "contact" when it has closed (``_closed``: the
        move ends there, short of the target, and ``contact_why`` says by
        which sign), "stop" when Stop was pressed, "there" when the target
        was reached.

        A slider is a coarse thing: with a micrometre to the volt, one
        finger's width of it is hundreds of nm, and a move made in one go
        would be through the surface before anything could look. In pieces,
        the tip ends a little more than one piece (speed x 25 ms: 5 nm at
        200 nm/s) past the place where the junction closed: the piece in
        which it closed is played to its end, and the junction is read from
        that piece's last millisecond."""
        C = self.cfg.cal
        look = max(8, int(round(self.HAND_LOOK_S * self.rig.sample_rate_hz)))
        step_v = (max(float(self.hand_speed_nm_s), 1.0) / C.piezo_nm_per_volt
                  * self.HAND_PIECE_S)
        pieces = 0
        while self.rig.piezo_v < target_v - 1e-9:
            if self.stop_flag.is_set():
                return "stop"
            record = self.rig.piezo_glide_to(
                min(target_v, self.rig.piezo_v + step_v), self.HAND_PIECE_S)
            if self.sim_real_time:
                time.sleep(self.HAND_PIECE_S)      # as long as the rig takes
            why = self._closed(record, tail=look)
            if why:
                self.contact_why = why
                return "contact"
            pieces += 1
            if pieces % 8 == 0:
                self.readout()                     # the sliders and readouts follow
                if self.mon.spent():               # a long way: a fresh picture
                    self.mon.begin_cycle()
                    self.mon.mark("by hand")
        return "there"

    def cmd_step(self, delta_nm: float) -> None:
        """Igor's PiezoStepCloser / PiezoStepApart: closer is +nm."""
        self.cmd_goto(self.rig.piezo_v + self.cfg.cal.nm_to_piezo_volts(delta_nm))

    # -- the pieces of a cycle ---------------------------------------------------

    def cmd_zero(self) -> None:
        self.status("measuring the preamp zero at 0 V bias ...")
        zero, zero2 = calibrate.measure_zeros(self.rig)
        self.cfg.cal.current_zero_v = zero
        self.bias_dirty = True
        text = f"preamp zero {zero * 1e6:+.2f} uV, written into cal"
        if zero2 is not None:
            # Channel 2 of a two-channel amplifier, from the same hold. A
            # reading at the rail is not an offset: the junction is closed
            # (a contact passes the amplifier's own offset current even at
            # 0 V bias), and the old zero is kept.
            if abs(zero2) >= self.cfg.limits.preamp_saturation_v:
                text += (f"; channel 2 reads {zero2:+.2f} V at 0 V bias, which is "
                         "its rail, not a zero: NOT taken. Open the junction "
                         "(Step apart) and calibrate again")
            else:
                self.cfg.cal.current_zero_2_v = zero2
                text += f"; channel 2 zero {zero2 * 1e6:+.2f} uV"
        # The sense line's zero drifts from day to day like any offset; the
        # slope is the stable property. Re-measure the zero here, at whatever
        # command the piezo sits at, assuming the config's slope.
        sense = self.rig.last_sense_v
        if sense is not None and sense.size:
            C = self.cfg.cal
            sense_v = float(np.mean(sense[sense.size // 2:]))
            slope = C.piezo_nm_per_volt / C.sense_nm_per_volt   # sense V per command V
            today = sense_v - slope * self.rig.piezo_v
            was = C.sense_zero_v
            C.sense_zero_v = today
            text += (f"; sense zero today {today:.4f} V (config {was:.4f} V, "
                     f"{(today - was) * C.sense_nm_per_volt:+.0f} nm of offset "
                     f"removed for this session)")
        self.status(text)
        self.post("zero", zero_v=zero, zero2_v=zero2)

    def cmd_bias(self) -> None:
        self.rig.set_bias(self.cfg.ramp.bias_v)
        self.bias_dirty = False
        self.status(f"bias set to {self.cfg.ramp.bias_v * 1e3:.1f} mV")

    def cmd_engage(self) -> None:
        self._engage()

    def _engage(self) -> RigState:
        if self.bias_dirty:
            self.cmd_bias()
        self.mon.begin_cycle()
        self.mon.mark("approach")
        self.status("approaching ... (Stop ends it between two steps)")
        state = approach.engage(self.rig, stop_flag=self.stop_flag)
        self.mon.mark("contact")
        self.post("approach", cycle=self.mon.snapshot())
        self.status(f"engaged at {self.rig.piezo_v:.4f} V = "
                    f"{self.rig.piezo_nm:.1f} nm")
        return state

    def cmd_pull(self) -> None:
        """One pull from wherever the piezo is (after an engage)."""
        if self.rig.state is not RigState.ENGAGED:
            self.status("not engaged: an engage comes first")
            return
        self._pull()

    def _pull(self, test: bool = False):
        """One pull. ``test`` pulls are shown but never saved or counted."""
        if not test:
            self.attempts += 1
        self.rig.attempts = self.attempts
        self.mon.mark("pull")
        tr = trace.single_trace(self.rig, index=self.accepted)
        self.mon.mark("end")
        cycle = self.mon.snapshot()
        if tr is None:
            if not test:
                self.rejections["alignment"] = self.rejections.get("alignment", 0) + 1
            self.status("pull done, but the alignment spike was not found: "
                        "trace discarded")
            self.post("cycle", cycle=cycle, record=None, verdict=None)
            return None
        g0 = tr.conductance_g0(self.cfg)
        # Channel 2 of a two-channel amplifier, as far as it measured (no
        # value where its output is saturated): shown beside channel 1.
        # The verdict reads the end of the trace from it (the open side:
        # channel 2 where it is in range, channel 1 where it is railed);
        # the start of the trace and the gold plateau are channel 1's.
        # The sign of the channel is read with the saturated part left
        # in: a channel the wrong way round sits at its negative rail
        # through contact.
        g0_2 = g0_open = g0_2_sign = None
        if tr.current2_v is not None:
            g0_2 = tr.conductance_g0(self.cfg, channel=2)
            g0_2_sign = tr.conductance_g0(self.cfg, channel=2, as_measured=True)
            g0_open = tr.open_side_g0(self.cfg)
        verdict = analysis.select_trace(g0, self.cfg.ramp,
                                        require_engaged=self.require_engaged,
                                        g0_open=g0_open)
        disp = tr.displacement_nm(self.cfg)
        # A current channel whose sign is the wrong way round reads negative
        # wherever the junction conducts. Nothing is accepted then and the
        # trace panel shows no line, so the status line says what it is.
        # A pull whose conductance is negative where the junction conducts
        # says so, in front of its status line so the box never cuts it off.
        sign_note, sign_level, negative = self.sign_words(g0, g0_2_sign, tr.voltage_v)
        # for the trace panel, which is given channel 2 without its
        # saturated part and could not tell
        negative2 = g0_2_sign is not None and analysis.reads_negative(g0_2_sign)
        if not test:
            self.negative_in_a_row = self.negative_in_a_row + 1 if negative else 0
        if test:
            self.post("cycle", cycle=cycle, record=tr, g0=g0, disp=disp,
                      verdict=verdict, g0_2=g0_2, negative2=negative2)
            saved = ""
            if self.save and self.save_test_pulls:
                self._save(tr, verdict, test=True)
                saved = f", saved to the TESTPULLS file ({self.n_saved})"
            self.status(f"{sign_note}test pull done (not counted{saved}); the "
                        f"selector would say: {verdict.reason}; alignment delay "
                        f"{tr.delay_samples} samples", sign_level)
            return verdict
        if verdict.accepted:
            self.accepted += 1
            self._accumulate(g0, g0_2)
            if self.save:
                self._save(tr, verdict)
        else:
            key = verdict.reason.split(":")[0].split("(")[0].strip()
            self.rejections[key] = self.rejections.get(key, 0) + 1
        self.post("cycle", cycle=cycle, record=tr, g0=g0, disp=disp,
                  verdict=verdict, g0_2=g0_2, negative2=negative2)
        self.post("hist", centres=self.hist_centres,
                  counts=self.histogram(), n=self.hist_n,
                  counts2=self.histogram2())
        word = "accepted" if verdict.accepted else "rejected"
        self.status(f"{sign_note}trace {word}: {verdict.reason}; {self.accepted} "
                    f"accepted in {self.attempts} attempts", sign_level)
        return verdict

    def sign_words(self, g0, g0_2, voltage_v) -> tuple[str, str | None, bool]:
        """What to say about the signs of one pull: (a note for the front
        of the status line, its colour, whether channel 1 read negative).

        A negative conductance means the current and the junction voltage
        have opposite signs. Which of the two is the odd one out is read
        off the junction voltage (``voltage_v``, raw volts): with its sign
        right it has the sign of the bias that was set. Channel 1 reading
        negative is the red case, and three of them in a row end a run
        (``SIGN_STOP``); ``sign_cure`` is then what to do about it.
        Channel 2 alone reading negative is said in orange and ends
        nothing: it is its sign, or an output at its negative rail
        (``g0_2`` is channel 2 with its saturated part left in,
        ``conductance_g0(..., as_measured=True)``). A pull that never
        touched says nothing about the sign and gets no note
        (``analysis.reads_negative``)."""
        if analysis.reads_negative(g0):
            v_seen = self.cfg.cal.voltage_input_sign * float(np.nanmean(voltage_v))
            if v_seen * self.cfg.ramp.bias_v < 0:
                self.sign_cure = ('Put the other sign in "voltage_input_sign" '
                                  "(the config's cal) and start again")
                return ("THE JUNCTION VOLTAGE HAS THE WRONG SIGN (opposite to the "
                        'bias), so G is negative: "voltage_input_sign" in the '
                        "config's cal is the wrong way round.  ", "bad", True)
            # The box as it stands is the wrong way: tick it, or untick it.
            verb = "Untick" if self.cfg.cal.sign_of(1) < 0 else "Tick"
            self.sign_cure = (f'{verb} "flip the sign of ch 1" in the Current '
                              "amplifier box, then Start N again")
            return ("CH 1 CURRENT HAS THE WRONG SIGN (opposite to the bias), so G "
                    f'is negative: {verb.lower()} "flip the sign of ch 1" (Current '
                    "amplifier box).  ", "bad", True)
        if g0_2 is not None and analysis.reads_negative(g0_2):
            return ('ch 2 reads a NEGATIVE conductance (its sign, or an output at '
                    'its negative rail): "flip the sign of ch 2" turns it.  ',
                    "warn", False)
        return "", None, False

    require_engaged = False

    def cmd_cycle(self) -> None:
        self._engage()
        self._pull()

    def cmd_testpull(self, start_v: float) -> None:
        """A pull from ``start_v`` with no approach and no contact.

        For a rig with no tip, or a dry run: the ramp, the alignment spike on
        ai0 and the record plot are all exercised on the real cards. The
        result is shown but never saved or counted: it is a hardware test,
        not data. (Igor's selector, reproduced here, would in fact *accept*
        a never-engaged trace unless --require-engaged is given.)
        """
        if self.bias_dirty:
            self.cmd_bias()
        self.mon.begin_cycle()
        self.mon.mark("go to start")
        self.rig.piezo_goto(start_v)
        self.rig.state = RigState.ENGAGED          # so the pull is allowed
        self.status(f"test pull from {self.rig.piezo_v:.3f} V, no contact")
        self._pull(test=True)

    def cmd_run(self, n: int, saving: dict | None = None,
                resume: bool = False) -> None:
        """One experiment: N accepted traces, one set of files.

        Stop ends the loop between cycles and leaves the experiment open
        ("paused"): Continue (``resume``) carries on into the same file for
        the traces still owed. A new Start N, a settings change or closing
        the window finishes the paused experiment first.
        """
        if resume:
            if self.paused is None:
                self.status("nothing to continue: press Start N to start an "
                            "experiment")
                return
            n = self.paused["remaining"]
            self.paused = None
            if self.run_pauses and self.run_pauses[-1]["continued"] is None:
                self.run_pauses[-1]["continued"] = time.time()
            self.status(f"continuing after trace {self.accepted}: {n} more "
                        f"traces into {self.run_stem.name}")
        else:
            if saving:
                self.saving.update(saving)
            self.begin_experiment()
        done = 0
        R = self.cfg.ramp
        failed = False
        sign_stop = False
        self.negative_in_a_row = 0
        while done < n and not self.stop_flag.is_set():
            if R.smash_every and self.attempts and \
                    self.attempts % R.smash_every == 0:
                self.status("smashing the tip")
                approach.smash(self.rig)
            try:
                self._engage()
            except ApproachError as exc:
                self.post("error", text=f"approach: {exc}", fatal=False)
                failed = True
                break
            verdict = self._pull()
            if verdict is not None and verdict.accepted:
                done += 1
            self.readout()
            if self.negative_in_a_row >= self.SIGN_STOP:
                # Every pull reads negative: the sign of the current is the
                # wrong way round and no trace will ever be accepted. Stop
                # here rather than crash the tip a thousand times for nothing.
                sign_stop = True
                break
        if done < n and (self.stop_flag.is_set() or failed or sign_stop):
            why = ("approach failed" if failed else
                   "the current reads negative" if sign_stop else "Stop")
            self.paused = {"remaining": n - done}
            self.run_pauses.append({"after_trace": self.accepted, "why": why,
                                    "stopped": time.time(), "continued": None})
            # The block in progress goes to disk now (a partial block), so
            # the traces taken so far are in the Igor files while the run
            # waits; the .h5 stays open for Continue.
            self.flush_igor(why)
            self.post("paused", remaining=n - done)
            if sign_stop:
                self.status(f"RUN STOPPED: {self.SIGN_STOP} pulls in a row gave a "
                            "NEGATIVE conductance on ch 1, so no trace can be "
                            f"accepted. {self.sign_cure}", "bad")
                return
            self.status(f"run paused with {n - done} of {n} traces still to "
                        f"take ({self.accepted} accepted so far). Continue "
                        "carries on into the same file; Start N starts a new "
                        "experiment")
            return
        files = self.end_experiment()
        self.status(f"run finished: {self.accepted} accepted in "
                    f"{self.attempts} attempts; rejected {self.rejections}"
                    + (f"; saved {files}" if files else "; nothing saved"))

    # Pulls in a row with a negative channel-1 current that end a run.
    SIGN_STOP = 3

    def cmd_continue(self) -> None:
        self.cmd_run(0, resume=True)

    # -- experiments: one per Start N -------------------------------------------------

    @staticmethod
    def _safe(text: str, fallback: str) -> str:
        """A folder or file name from what was typed: letters, digits, '-'
        and '_' kept, spaces made '_', anything else dropped."""
        cleaned = "".join(ch if ch.isalnum() or ch in "-_" else
                          ("_" if ch.isspace() else "")
                          for ch in text.strip())
        return cleaned or fallback

    def _sv(self) -> dict:
        """The saving settings that apply: while a run is going, the copy
        taken at its Start N (``run_saving``), so a folder or a box changed
        in the window during the run waits for the next one; otherwise the
        Saving tab as it is now."""
        return self.run_saving if self.run_stem is not None else self.saving

    def setup_id(self) -> str:
        """Igor's SetupID from the Saving tab: the letters between the day
        and the year of the folder name (``_`` by default)."""
        return str(self._sv().get("setup_id") or "_")

    def day_folder(self, when: float | None = None) -> Path:
        """Igor's day folder for a run started at ``when`` (now if None):
        the data folder, then ``MM_DD<SetupID>YYMerge``
        (``igor_scheme.day_folder_name``, Igor's ``MakePath``)."""
        return (Path(self._sv()["folder"])
                / igor_scheme.day_folder_name(when, self.setup_id()))

    def experiment_paths(self, when: float | None = None) -> tuple[Path, str]:
        """(folder, stem) a run started at ``when`` would use: the day
        folder, and <experiment>_<HHMMSS> for the run's own files (.h5,
        .txt). The Igor files have Igor's names and need no stem."""
        t = time.localtime(when)
        stem = (f"{self._safe(self._sv()['experiment'], 'experiment')}_"
                f"{time.strftime('%H%M%S', t)}")
        return self.day_folder(when), stem

    def flags(self) -> igor_scheme.SaveFlags:
        """Igor's save check boxes, from the Saving tab."""
        s, d = self._sv(), DEFAULT_SAVING
        return igor_scheme.SaveFlags(**{key: bool(s.get(key, d[key]))
                                        for key in IGOR_FLAG_KEYS})

    def offsets(self) -> tuple[float, float]:
        """Igor's ``Vzero`` (mV) and ``Izero`` (uA) for ParameterWave slots
        15 and 16. Igor's Find Offset fitted the junction's I-V at zero
        bias: Izero was the current it read with no bias applied and Vzero
        the bias that would null it. This program applies no bias
        correction, so Vzero is 0; Izero is what Calibrate zero measured
        (``cal.current_zero_v``, the preamp's output at 0 V bias) as a
        current, in uA -- the same quantity, measured the simpler way."""
        C = self.cfg.cal
        return 0.0, C.sign_of(1) * C.current_zero_v / C.preamp_gain_v_per_a * 1e6

    def izero2(self) -> float:
        """Slot 16 of channel 2's parameters in the ch2 subfolder: what
        Calibrate zero measured on the amplifier's second output, as a
        current in uA (``offsets`` gives channel 1's)."""
        C = self.cfg.cal
        return C.sign_of(2) * C.current_zero_2_v / C.preamp_gain_2_v_per_a * 1e6

    def _note_fields(self) -> dict:
        """What goes into the ConductanceBlock's wave note besides the
        trace range: the program version, the experiment and who ran it
        (semicolons separate the fields, so none may be inside one)."""
        fields = {"version": __version__}
        for key, word in (("experiment", "experiment"), ("name", "operator")):
            value = str(self._sv().get(key, "")).replace(";", ",").strip()
            if value:
                fields[word] = value
        return fields

    def igor_writer(self, when: float | None = None):
        """The day's Igor writer, or None when the Igor files are off.

        Made the first time it is needed -- which scans the day folder so
        the numbering continues where the last run (today, with this Setup
        ID) stopped, and reads a partial block back to refill it -- and
        remade when the folder, the Setup ID or the date has changed. The
        save flags and the note follow the Saving tab every time.
        """
        if not self.igor_export:
            return None
        folder = self.day_folder(when)
        if self.igor is not None and self.igor.folder != folder:
            self.flush_igor("folder changed")
            self.igor = None
        if self.igor is None:
            try:
                self.igor = igor_scheme.IgorDayWriter(
                    self._sv()["folder"], self.cfg, setup_id=self.setup_id(),
                    flags=self.flags(), when=when, note_fields=self._note_fields())
            except Exception as exc:               # noqa: BLE001
                # The folder holds blocks and reading them back (to continue
                # the numbering) needs igor2; or the folder cannot be looked
                # at or its last block read (the NAS gone, a file that will
                # not parse). Writing might still work, but it would start
                # again at 1 over what is there: refuse, for the session,
                # rather than fail every Start N.
                self.igor_export = False
                if isinstance(exc, ImportError):
                    why = (f"continuing the numbering in {folder} needs the igor2 "
                           f"package (pip install igor2): {exc}")
                else:
                    log.exception("Igor day folder %s could not be opened", folder)
                    why = (f"the Igor day folder {folder} could not be opened: "
                           f"{type(exc).__name__}: {exc}")
                self.post("error", fatal=False,
                          text=f"Igor files OFF for this session: {why}. The .h5 is "
                               "still written")
                return None
            self.status(f"Igor folder {self.igor.folder}: next trace (Saved) "
                        f"{self.igor.saved}", level="ok")
        else:
            self.igor.flags = self.flags()
            self.igor.note_fields = self._note_fields()
        return self.igor

    def flush_igor(self, why: str = "") -> list[Path]:
        """Put the Igor block in progress on disk now (``IgorDayWriter.flush``:
        a partial block, NaN in the columns not yet taken), guarded: a write
        that fails -- the NAS gone, the folder read-only -- is logged and
        reported as a non-fatal error, never raised, so the run, the .h5 and
        the window carry on. The traces stay in the writer and go out with
        the next write that succeeds. Returns the files written ([] when
        nothing changed or the write failed)."""
        if self.igor is None:
            return []
        try:
            return list(self.igor.flush())
        except Exception as exc:                   # noqa: BLE001
            log.exception("Igor block not written")
            self.post("error", fatal=False,
                      text=f"Igor block {self.igor.current_block} not written to "
                           f"{self.igor.folder}{f' ({why})' if why else ''}: "
                           f"{type(exc).__name__}: {exc}. Its traces are not in the "
                           "Igor files; the .h5 is written separately")
            return []

    def igor_today(self) -> igor_scheme.IgorDayWriter | None:
        """The day's Igor writer when it is the one for the day folder the
        Saving tab names now (this folder, this Setup ID, today), else None:
        after the folder, the Setup ID or the day has changed, the writer's
        count is the old folder's, not the one the window shows."""
        if self.igor is None or self.igor.folder != self.day_folder():
            return None
        return self.igor

    def saved_today(self) -> int | None:
        """Traces in today's Igor folder so far (Igor's ``Saved`` - 1), or
        None before the folder has been looked at, or after the folder, the
        Setup ID or the day changed (the window then shows its own count
        from the files)."""
        writer = self.igor_today()
        return None if writer is None else writer.saved - 1

    def begin_experiment(self) -> None:
        """A fresh set of files, histogram and counters for this run; the
        Igor writer for the day (the numbering carries on)."""
        if self.run_stem is not None:
            self.end_experiment()              # a paused run: its files are done
        elif self.writer is not None:
            self.close_file()
        self.paused = None
        self.run_started = time.time()
        # The Saving tab as it is at this Start N, for the whole run.
        self.run_saving = dict(self.saving)
        folder, stem = self.experiment_paths(self.run_started)
        self.run_stem = folder / stem
        self.run_numbers = []
        self.file_traces = []
        self.accepted = 0
        self.attempts = 0
        self.rejections = {}
        self.run_v_contact = []
        self.run_v_open = []
        self.run_pauses = []
        self.hist_sum = None
        self.hist_n = 0
        self.hist2_sum = None
        self.hist2_n = 0
        self.floors = []
        self.post("hist", centres=None, counts=None, n=0, counts2=None)
        self.post("experiment", stem=str(self.run_stem))
        writer = self.igor_writer(self.run_started)
        self.status(f"experiment {stem}: files go to {folder}"
                    + (f"; Igor trace numbers from {writer.saved}" if writer else ""))

    def end_experiment(self) -> list[str]:
        """Finish the run: the Igor block in progress goes to disk (a
        partial block, refilled by the next run), the .h5 is closed and
        named after its trace count, the .txt table is written when ticked,
        and the run gets its row in experiment_log.csv. Returns the names
        of the files written.

        Whatever fails on the way -- the Igor block, the .txt, the log row --
        is reported as a non-fatal error and the rest still happens: the .h5
        is closed and renamed even when the Igor block could not be
        written, and the run is closed in the window (not paused, no
        experiment, no file) in every case, so it never stays half-closed.
        """
        stem = self.run_stem
        if stem is None:
            self.paused = None
            self.post("paused", remaining=0)
            self.post("experiment", stem=None)
            return []
        written: list[str] = []
        try:
            sv = self._sv()                        # the run's own settings
            traces = list(self.file_traces)
            if not traces:
                # Nothing was taken: no files, no log row (a block an
                # earlier run left in memory still goes to disk).
                self.flush_igor()
                return []
            auto = self.auto_notes(len(traces))
            written += [self._igor_file_name(p) for p in self.flush_igor()]
            h5: Path | None = None
            if self.writer is not None and not self.writer_is_test:
                try:
                    self.writer.describe(auto_notes=auto)
                except Exception:                  # noqa: BLE001
                    log.exception("could not write the automatic note into the file")
                h5 = self.writer.path
            self._close_h5()
            final = stem.with_name(f"{stem.name}_{len(traces)}traces")
            if h5 is not None:
                try:
                    h5 = h5.rename(final.with_suffix(".h5"))
                except OSError as exc:
                    log.warning("could not rename %s: %s", h5.name, exc)
                written.insert(0, h5.name)
            if sv.get("txt"):
                try:
                    data, info = storage.save_txt_block(
                        final.with_suffix(".txt"), self.cfg, [t[0] for t in traces],
                        start_piezo_v=[t[1] for t in traces],
                        timestamps=[t[2] for t in traces],
                        header_lines=[f"name={sv['name']} experiment={sv['experiment']} "
                                      f"file={h5.name if h5 else final.parent.name}",
                                      f"notes={sv.get('notes', '')}",
                                      f"auto_notes={auto}"])
                    written += [data.name, info.name]
                    # Channel 2 of a two-channel amplifier: its own table,
                    # the same layout, from the traces that have one (the
                    # others are a column of NaN, so the columns of the
                    # two tables are the same traces).
                    if any(t[3] is not None for t in traces):
                        n_pts = max(t[0].size for t in traces)
                        second = [t[3] if t[3] is not None
                                  else np.full(n_pts, np.nan, dtype=np.float32)
                                  for t in traces]
                        data2, info2 = storage.save_txt_block(
                            final.with_name(final.name + "_ch2.txt"), self.cfg, second,
                            start_piezo_v=[t[1] for t in traces],
                            timestamps=[t[2] for t in traces],
                            header_lines=[f"name={sv['name']} experiment={sv['experiment']} "
                                          f"file={h5.name if h5 else final.parent.name}",
                                          "current channel 2 of a two-channel amplifier "
                                          f"(channel 1: {data.name}); where its output "
                                          "was saturated the conductance is channel 1's",
                                          f"notes={sv.get('notes', '')}",
                                          f"auto_notes={auto}"],
                            channel=2)
                        written += [data2.name, info2.name]
                except Exception as exc:           # noqa: BLE001
                    log.exception("txt export failed")
                    self.post("error", text=f"txt export failed: {exc}", fatal=False)
            try:
                self.log_session(h5 if h5 is not None else final.parent, traces, written)
            except Exception as exc:               # noqa: BLE001
                log.exception("session log failed")
                self.post("error", text=f"session log not written: {exc}", fatal=False)
        finally:
            self.run_stem = None
            self.paused = None
            self.post("paused", remaining=0)
            self.post("experiment", stem=None)
            self.post("file", path=None)
        return written

    SESSION_LOG = "experiment_log.csv"

    @staticmethod
    def _igor_file_name(path: Path) -> str:
        """A written Igor file as the messages name it: its name, with
        ``ch2/`` in front for a file of channel 2's subfolder (which has
        the same file names as the day folder)."""
        path = Path(path)
        if path.parent.name == igor_scheme.CH2_FOLDER:
            return f"{igor_scheme.CH2_FOLDER}/{path.name}"
        return path.name

    def auto_notes(self, n_traces: int) -> str:
        """The sentence a lab notebook would want written for every run,
        made from the settings and from what the junction actually read:
        the bias set, the junction voltage measured with the junction open
        (what the tunnelling tail sees through the series resistor) and at
        the start of the pull (in contact), the resistor, the gain, the
        preamp zero, the pull, and which Igor trace numbers the run got."""
        R, C, K = self.cfg.ramp, self.cfg.cal, self.cfg.keithley
        v_open = float(np.median(self.run_v_open)) if self.run_v_open else float("nan")
        v_con = float(np.median(self.run_v_contact)) if self.run_v_contact else float("nan")
        # ":g", not ".0e": a gain typed in the Current amplifier box need
        # not be a whole decade, and 4.7e5 must not be noted as 5e+05.
        gain = f"gain {C.preamp_gain_v_per_a:g} V/A"
        zero = f"preamp zero {C.current_zero_v * 1e6:+.1f} uV"
        if self.cfg.channels.two_current_channels:
            # Both outputs of the amplifier, each with its own numbers.
            gain = (f"two current channels: ch 1 gain {C.preamp_gain_v_per_a:g} "
                    f"V/A, ch 2 gain {C.preamp_gain_2_v_per_a:g} V/A")
            zero = (f"zero ch 1 {C.current_zero_v * 1e6:+.1f} uV, ch 2 "
                    f"{C.current_zero_2_v * 1e6:+.1f} uV")
        note = (f"bias set {R.bias_v * 1e3:g} mV; junction measured "
                f"{v_open:.1f} mV open, {v_con:.1f} mV at pull start "
                f"(medians over {n_traces} traces); series resistor "
                f"{K.series_resistance_ohm:g} ohm; {gain}; "
                f"{zero}; pull "
                f"{R.pull_length_nm:g} nm at {R.pull_rate_nm_per_s:g} nm/s, "
                f"engage {R.engage_g0:g} G0, break {R.break_g0:g} G0, "
                f"{C.piezo_nm_per_volt:g} nm/V")
        if self.run_numbers:
            note += (f"; Igor traces {min(self.run_numbers)}-{max(self.run_numbers)}"
                     + (f" in {self.igor.folder.name}" if self.igor is not None else ""))
        for pz in self.run_pauses:
            clock = lambda t: time.strftime("%H:%M:%S", time.localtime(t))  # noqa: E731
            note += (f"; {pz['why']} after trace {pz['after_trace']} at "
                     f"{clock(pz['stopped'])}"
                     + (f", continued {clock(pz['continued'])}"
                        if pz["continued"] else ", not continued"))
        return note

    def log_session(self, data_path: Path, traces: list, written: list) -> Path:
        """Two lines per experiment in <day folder>/experiment_log.csv, one
        file per day folder for everyone, readable as a notebook:

            date, start time, name, experiment, traces, your notes, the
                automatic note (bias set, junction measured, resistor,
                gain, zero, the pull, the Igor trace numbers)
            the full path of the data file (the .h5; the day folder when
                the .h5 is off), alone on the next line

        The header is written once; lines are appended."""
        started = self.run_started or time.time()
        sv = self._sv()
        path = self.day_folder(started) / self.SESSION_LOG
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["date", "start_time", "name", "experiment", "traces",
                            "notes", "auto_notes"])
            w.writerow([time.strftime("%Y-%m-%d", time.localtime(started)),
                        time.strftime("%H:%M:%S", time.localtime(started)),
                        sv.get("name", ""),
                        sv.get("experiment", ""),
                        len(traces),
                        sv.get("notes", ""),
                        self.auto_notes(len(traces))])
            w.writerow([str(Path(data_path).resolve())])
        log.info("experiment log: %s (+1 row)", path)
        self.post("session_log", path=str(path))
        return path

    def cmd_withdraw(self) -> None:
        self.rig.withdraw()
        self.bias_dirty = True
        self.status("withdrawn: piezo parked, bias 0 V")

    def cmd_smash(self) -> None:
        approach.smash(self.rig)
        self.status("smashed")

    # -- bookkeeping ---------------------------------------------------------

    def _accumulate(self, g0: np.ndarray, g0_2: np.ndarray | None = None) -> None:
        """Add an accepted trace to the run's histogram, and its channel 2
        (when it has one) to channel 2's: the same recipe and bins, a
        histogram of its own. ``g0_2`` is channel 2 as far as it measured
        (NaN where its output was saturated): those points are not
        counted, so channel 2's histogram ends where channel 2 ends."""
        centres, counts = analysis.log_histogram([g0])
        if self.hist_sum is None:
            self.hist_centres, self.hist_sum = centres, np.zeros_like(counts)
        if counts.any():
            self.hist_sum += counts
            self.hist_n += 1
        if g0_2 is not None:
            _, counts2 = analysis.log_histogram([g0_2])
            if self.hist2_sum is None:
                self.hist2_sum = np.zeros_like(counts2)
            if counts2.any():
                self.hist2_sum += counts2
                self.hist2_n += 1
        # Each channel's noise floor on this trace: the rms over 85 to 95 %
        # of the pull, where the junction is open (the last 5 % holds the
        # alignment spike).
        a, b = int(g0.size * 0.85), int(g0.size * 0.95)
        if b - a >= 10:
            floor2 = None
            if g0_2 is not None:
                # only where channel 2 measured (an accepted trace is open
                # there, so that is all of it, bar a stray sample)
                tail2 = g0_2[a:b]
                tail2 = tail2[np.isfinite(tail2)]
                floor2 = float(np.std(tail2)) if tail2.size >= 10 else None
            self.floors.append((float(np.std(g0[a:b])), floor2))

    def noise_floors(self) -> tuple[float | None, float | None]:
        """(channel 1's noise floor, channel 2's) over the run's accepted
        traces, in G0: the median of each trace's rms at its open end.
        None for a channel with no traces."""
        first = [f[0] for f in self.floors]
        second = [f[1] for f in self.floors if f[1] is not None]
        return (float(np.median(first)) if first else None,
                float(np.median(second)) if second else None)

    def histogram(self) -> np.ndarray | None:
        if self.hist_sum is None or self.hist_n == 0:
            return None
        return self.hist_sum / self.hist_n

    def histogram2(self) -> np.ndarray | None:
        """Channel 2's histogram of the run so far, counts per trace, or
        None while there is none (one channel read, or no trace yet)."""
        if self.hist2_sum is None or self.hist2_n == 0:
            return None
        return self.hist2_sum / self.hist2_n

    def _save(self, tr, verdict, test: bool = False) -> None:
        """Save one accepted trace: into the day's Igor block (the files
        Igor's macro reads, through ``igor_scheme.IgorDayWriter``) and,
        when the raw .h5 is ticked, into the run's session file.

        Test pulls go to a .h5 whose name says TESTPULLS, never into the
        Igor files nor into a file holding real traces (nor the other way
        round): a file is either data or a format test.
        """
        if not test and (self.run_stem is None or self.paused is not None):
            return                                 # a single cycle: shown only
        if test:
            self._save_h5(tr, verdict, test=True)
            self.post("saved", n=self.n_saved, number=None, block=None,
                      saved=self.saved_today(), path=str(self.writer.path),
                      folder=None, run=0)
            return
        number = block = None
        writer = self.igor_writer(self.run_started)
        if writer is not None:
            vzero_mv, izero_ua = self.offsets()
            t = igor_scheme.IgorTrace.from_record(tr, self.cfg, vzero_mv=vzero_mv,
                                                  izero=izero_ua,
                                                  bias_save=writer.flags.bias,
                                                  izero2=self.izero2())
            before = writer.current_block
            try:
                number = writer.append(t)
            except Exception as exc:               # noqa: BLE001
                # The NAS dropped, the folder went read-only: the trace is
                # not in the Igor files. Say so and go on -- the .h5 (when
                # ticked) still gets it below, and the run is not lost.
                log.exception("Igor trace not written")
                self.post("error", fatal=False,
                          text=f"Igor block {before} in {writer.folder} not written: "
                               f"{type(exc).__name__}: {exc}. This trace is "
                               + ("still in the .h5" if self._sv().get("h5", True)
                                  else "NOT saved (the .h5 is off)")
                               + "; the run goes on")
            else:
                # Igor's numbering says which block the trace went into and
                # whether it completed one (the 100th trace writes the files).
                block = (number - 1) // igor_scheme.BLOCK + 1
                self.run_numbers.append(number)
                if number % igor_scheme.BLOCK == 0:
                    self.status(f"Igor block {block} complete: traces "
                                f"{(block - 1) * igor_scheme.BLOCK + 1}-{number} in "
                                f"{writer.folder.name}", level="ok")
                elif block != before:
                    # A trace of another length than the block's: the writer
                    # put the partial block on disk and started a new one
                    # with this trace (igor_scheme.IgorDayWriter.append).
                    self.status(f"trace length changed: partial block {before} "
                                f"written, continuing in block {block} (trace "
                                f"{number}) in {writer.folder.name}", level="warn")
        if self._sv().get("h5", True):
            self._save_h5(tr, verdict)
        self.file_traces.append((
            tr.conductance_g0(self.cfg).astype(np.float32),
            tr.start_piezo_v, tr.timestamp,
            # channel 2, for the second .txt table (None with one channel):
            # as in the ch2 Igor block, channel 1's conductance where
            # channel 2's output was saturated
            tr.open_side_g0(self.cfg).astype(np.float32)
            if tr.current2_v is not None else None))
        v = self.cfg.cal.voltage_input_sign * np.asarray(tr.voltage_v, float) * 1e3
        n = v.size
        # The first half-millisecond: the junction as it was when the
        # pull began, before a shallow contact has had time to break.
        self.run_v_contact.append(float(np.mean(v[:max(5, n // 500)])))
        self.run_v_open.append(float(np.mean(v[int(n * 0.90):int(n * 0.94) + 1])))
        self.post("saved", n=self.n_saved, number=number, block=block,
                  saved=self.saved_today(), run=len(self.file_traces),
                  path=str(self.writer.path) if self.writer is not None else None,
                  folder=str(writer.folder) if writer is not None else None)

    def _save_h5(self, tr, verdict, test: bool = False) -> None:
        """Append a trace to the raw session file, opening one if needed
        (in the day folder, or TESTPULLS in the data folder for a test)."""
        if self.writer is not None and self.writer_is_test != test:
            self.close_file()
        if self.writer is None:
            sv = self._sv()
            if test:
                path = (Path(sv["folder"]) /
                        f"pullout_TESTPULLS_{time.strftime('%Y%m%d_%H%M%S')}.h5")
            else:
                path = self.run_stem.with_suffix(".h5")
            self.writer = storage.SessionWriter(path, self.cfg).open()
            self.writer.describe(operator=sv.get("name", ""),
                                 experiment=sv.get("experiment", ""),
                                 notes=sv.get("notes", ""),
                                 program=f"pullout {__version__}",
                                 setup_id=self.setup_id(),
                                 config=self.config_name)
            self.writer_is_test = test
            self.post("file", path=str(path))
        self.writer.append(self.n_saved, tr, verdict)
        self.n_saved += 1

    def _close_h5(self) -> None:
        """Close the session file, if one is open, with its summary."""
        if self.writer is not None:
            try:
                self.writer.write_summary({"accepted": self.accepted,
                                           "attempts": self.attempts,
                                           "rejections": self.rejections})
                self.writer.close()
            finally:
                self.writer = None
            self.post("file", path=None)

    def close_file(self) -> None:
        """Close the session file, if one is open, and put the Igor block
        in progress on disk (a partial block, NaN in the columns not yet
        taken; the next run refills it). Called at the end of a run, on
        pause, Stop, a settings change and quit. A block that cannot be
        written is reported, not raised (``flush_igor``)."""
        self._close_h5()
        files = self.flush_igor()
        if files:
            log.info("Igor partial block written: %s",
                     ", ".join(p.name for p in files))

    def cmd_newfile(self) -> None:
        """Something changed (a setting, the gain): the open experiment, if
        any, is finished so its files describe what they hold."""
        if self.run_stem is not None and self.paused is None:
            self.status("a run is in progress and its traces belong in one "
                        "file; press Stop to end it")
            return
        if self.run_stem is not None:
            files = self.end_experiment()
            self.status(f"paused experiment finished: {files}; the next Start N "
                        "starts a new one")
        else:
            self.close_file()

    def readout(self) -> None:
        rig = self.rig
        c = self.mon.last()
        rec = c.last_record
        M, C = self.cfg.channels, self.cfg.cal
        if rec is not None and rec.shape[1] >= 4:
            tail = rec[:, rec.shape[1] // 2:]
            v_mv = float(C.voltage_input_sign * np.mean(tail[M.ROW_VOLTAGE]) * 1e3)
            i_ua = float(C.volts_to_amps(np.mean(tail[M.ROW_CURRENT])) * 1e6)
            g0 = rig.conductance_of(rec)
            railed = rig.is_saturated(rec)
        else:
            v_mv = i_ua = g0 = float("nan")
            railed = False
        sense = rig.last_sense_v
        sense_v = (float(np.mean(sense[sense.size // 2:]))
                   if sense is not None and sense.size else None)
        # Channel 2 of a two-channel amplifier over that same play: its
        # output volts, current, conductance and whether it is railed; None
        # while it is not read.
        ch2 = (rig.channel2_of(rec, c.last_current2)
               if rec is not None and c.last_current2 is not None else None)
        # "saved" is the day counter (traces in today's Igor folder, Igor's
        # Saved - 1), None until the folder has been looked at or when the
        # Saving tab now names another folder, Setup ID or day than the
        # writer's (the window then counts the folder's files itself).
        writer = self.igor_today()
        self.post("readout", state=rig.state.name, piezo_v=rig.piezo_v,
                  piezo_nm=rig.piezo_nm, bias_mv=rig.bias_v * 1e3,
                  junction_mv=v_mv, current_ua=i_ua, g0=g0, railed=railed,
                  sense_nm=rig.sense_nm, sense_v=sense_v,
                  accepted=self.accepted, attempts=self.attempts,
                  saved=None if writer is None else writer.saved - 1,
                  igor_folder=str(writer.folder) if writer is not None else None,
                  zero_uv=C.current_zero_v * 1e6,
                  two_channels=M.two_current_channels, ch2=ch2,
                  zero2_uv=C.current_zero_2_v * 1e6)


# --------------------------------------------------------------------------
# Opening and closing the rig
# --------------------------------------------------------------------------

def open_rig(cfg: RigConfig) -> tuple[SafeSession, Rig]:
    for w in validate(cfg):
        log.warning("config: %s", w)
    guard = SafeSession(cfg)
    guard.__enter__()
    try:
        actuator = None
        if cfg.actuator.kind.lower() in ("nanopz", "agilis") and not cfg.simulate:
            from stmlab.actuator import UnconnectedActuator
            actuator = UnconnectedActuator()        # Connect opens the port
        rig = Rig(cfg, actuator=actuator).open()
    except Exception:
        guard.__exit__(*sys.exc_info())
        raise
    return guard, rig


def close_rig(guard: SafeSession, rig: Rig) -> None:
    try:
        rig.close()
    finally:
        guard.__exit__(None, None, None)


# --------------------------------------------------------------------------
# Headless: N cycles into the day folder, report
# --------------------------------------------------------------------------

def run_headless(cfg: RigConfig, n: int, out_dir: Path, igor_export: bool,
                 require_engaged: bool, test_pull_v: float | None = None,
                 save_test_pulls: bool = False, setup_id: str = "_",
                 saving: dict | None = None) -> int:
    """No window: zero, then N cycles saved exactly as Start N saves them
    -- the Igor block files in <out_dir>/MM_DD<setup_id>YYMerge (the
    numbering carried on from what is there) and the raw .h5 beside them
    -- then a report. ``saving`` is the Saving tab's entries that apply
    (name, experiment, notes, the save boxes; ``main`` passes what the tab
    remembered, with ``--name`` and ``--experiment`` over it)."""
    guard, rig = open_rig(cfg)
    mon = Monitor(rig)
    worker = Worker(cfg, rig, mon, save=True, out_dir=out_dir,
                    igor_export=igor_export)
    worker.require_engaged = require_engaged
    worker.save_test_pulls = save_test_pulls
    worker.saving["setup_id"] = setup_id or "_"
    if saving:
        worker.saving.update(saving)
    try:
        worker.cmd_zero()
        if test_pull_v is not None:
            for _ in range(n):
                worker.cmd_testpull(test_pull_v)
                cyc = mon.snapshot()
                rec = cyc.last_record
                print(f"  test pull from {test_pull_v:.3f} V: record "
                      f"{rec.shape if rec is not None else None}, "
                      f"{len(cyc.t)} points in the piezo log")
        else:
            worker.cmd_run(n)
    finally:
        worker.close_file()
        close_rig(guard, rig)
    # drain the events for the printout
    last_status = ""
    while True:
        try:
            kind, payload = worker.events.get_nowait()
        except queue.Empty:
            break
        if kind == "status":
            last_status = payload["text"]
        elif kind == "error":
            print("error:", payload["text"])
    print(last_status)
    hist = worker.histogram()
    if hist is not None:
        peak = analysis.peak_position(worker.hist_centres, hist, around=0.0,
                                      window=0.4)
        print(f"1 G0 peak at {peak:+.4f} decades over {worker.hist_n} traces")
    floor1, floor2 = worker.noise_floors()
    if floor1 is not None and floor2 is not None:
        # A two-channel amplifier: each channel's noise floor, as the rms
        # of the open end of the traces.
        print(f"two current channels: noise floor {floor1:.1e} G0 on ch 1 and "
              f"{floor2:.1e} G0 on ch 2 (rms at the open end of the traces, "
              f"{worker.hist2_n} traces)")
    if worker.igor is not None:
        folder = worker.igor.folder
        files = sorted(p.name for p in folder.glob("PullOut*.ibw")) if folder.is_dir() else []
        sub = igor_scheme.channel2_folder(folder)
        files += sorted(f"{sub.name}/{p.name}" for p in sub.glob("PullOut*.ibw")) \
            if sub.is_dir() else []
        print(f"Igor folder {folder}: {worker.igor.saved - 1} traces today, next "
              f"trace (Saved) {worker.igor.saved}"
              + (f"; files: {', '.join(files)}" if files else ""))
    return 0


# --------------------------------------------------------------------------
# Igor data opened for browsing: a day folder, or one block file
# --------------------------------------------------------------------------

class IgorDay:
    """An Igor day folder -- Igor's own or this program's -- or one
    ``PullOutConductanceBlock_k.ibw``, opened for the window's browser.

    The traces keep Igor's numbering through the day (block k, column c
    is trace (k-1)*100 + c + 1). ``trace(i)`` is the i-th trace present
    (0-based, as the browser counts) with its displacement axis from the
    block's parameters (``linspace(0, Size, N)``, Igor's ``SetScale/I``)
    and, when the companion files exist, its junction voltage (V), current
    (A) and sense readback (nm). Only the block being looked at is held in
    memory with its companions; the histogram over everything is made once
    when the folder is opened, block by block, so a whole day of 10,000
    traces can be browsed without loading it all.

    Any other ``.ibw`` holding traces in columns with the 22-row parameter
    tail (this program's old ``_bNNN`` export) opens too, as one block
    numbered 0 without companions.

    A day taken with a two-channel amplifier has channel 2 in its ``ch2``
    subfolder (``igor_scheme.CH2_FOLDER``): ``trace(i)`` then carries
    ``g0_2``, the same trace as channel 2 read it, ``hist2`` is channel
    2's histogram over the day and ``data()`` holds both. Channel 2 is
    read as it measured: the points of the ``ch2`` block that are channel
    1's conductance, filled in where channel 2's output was saturated,
    are blank here (``igor_scheme.read_block_channel2``). (The ``ch2``
    subfolder opened by itself is simply a day folder: the two channels
    as one trace.)
    """

    _BLOCK_FILE = re.compile(r"^PullOutConductanceBlock_(\d+)\.ibw$")

    def __init__(self, path):
        path = Path(path)
        self.path = path
        self.name = path.name if path.is_dir() else path.stem
        self.folder = path if path.is_dir() else path.parent
        self._single: igor_scheme.IgorBlock | None = None
        if path.is_dir():
            self.ks = igor_scheme.list_blocks(path)
            if not self.ks:
                raise ValueError(f"{path.name}: no PullOutConductanceBlock_k.ibw in it")
        else:
            m = self._BLOCK_FILE.match(path.name)
            if m:
                self.ks = [int(m.group(1))]
            else:
                g0, params, filled = igor_scheme.split_block(igor_scheme.read_wave(path).data)
                idx = np.flatnonzero(filled)
                self._single = igor_scheme.IgorBlock(0, path.parent, g0[:, idx],
                                                     params[idx], idx, idx + 1)
                self.ks = [0]
        self._cache: tuple[int, igor_scheme.IgorBlock] | None = None
        self._cache2: tuple[int, igor_scheme.IgorBlock | None] | None = None
        # (block k, position j in the block's filled columns, Igor's number)
        self.entries: list[tuple[int, int, int]] = []
        self.cfg = RigConfig()
        centres = total = total2 = None
        n2 = 0
        for k in self.ks:
            b = self._read(k, companions=False)
            if b.n_traces == 0:
                continue
            if not self.entries:
                self._settings_from(b.params[0])
            self.entries += [(k, j, int(b.numbers[j])) for j in range(b.n_traces)]
            c, counts = analysis.log_histogram(list(b.g0.T), igor_bins=True)
            centres = c
            total = counts * b.n_traces if total is None else total + counts * b.n_traces
            # Channel 2 of the same block, when the day has a ch2 subfolder.
            b2 = self._read2(k, companions=False, first=b)
            if b2 is not None and b2.n_traces:
                if n2 == 0:
                    slot9 = float(b2.params[0][9])
                    if np.isfinite(slot9) and slot9 > 0:
                        self.cfg.cal.preamp_gain_2_v_per_a = 1e6 / slot9
                _, counts2 = analysis.log_histogram(list(b2.g0.T), igor_bins=True)
                total2 = (counts2 * b2.n_traces if total2 is None
                          else total2 + counts2 * b2.n_traces)
                n2 += b2.n_traces
        # (centres, counts per trace) over every trace present, Igor's bins;
        # each block's counts-per-trace weighted by its trace count (exact
        # when every trace passes the noise-floor gate). The overview panel
        # only; the histogram windows recompute from every trace.
        self.hist = None if total is None else (centres, total / max(len(self.entries), 1))
        # Channel 2's histogram over the traces that have one (counts per
        # trace, the same bins), or None for a day taken with one channel.
        self.hist2 = None if total2 is None or n2 == 0 else total2 / n2
        self.n2 = n2

    def _settings_from(self, p: np.ndarray) -> None:
        """The pull as the block's parameters record it, into the config the
        plots and the selector use (as plot.py does for an Igor file)."""
        R = self.cfg.ramp
        if np.isfinite(p[0]) and p[0] > 0:
            R.pull_length_nm = float(p[0])
        if np.isfinite(p[1]) and p[1] > 0:
            R.pull_rate_nm_per_s = float(p[1])
        if np.isfinite(p[10]) and p[10] != 0:
            R.bias_v = float(p[10]) * 1e-3
        if np.isfinite(p[13]) and p[13] > 0:
            R.engage_g0 = float(p[13])
        if np.isfinite(p[9]) and p[9] > 0:
            self.cfg.cal.preamp_gain_v_per_a = 1e6 / float(p[9])   # slot 9: uA per V

    def _read(self, k: int, companions: bool) -> igor_scheme.IgorBlock:
        if self._single is not None:
            return self._single
        return igor_scheme.read_block(self.folder, k, companions=companions)

    def _read2(self, k: int, companions: bool,
               first: igor_scheme.IgorBlock | None = None
               ) -> igor_scheme.IgorBlock | None:
        """Block ``k`` of channel 2 (the ``ch2`` subfolder), or None when
        the day has none, or it cannot be read: channel 1 is still shown.
        ``first`` is block ``k`` of the day folder itself when the caller
        has it (it tells which points of channel 2 are filled in)."""
        if self._single is not None:
            return None
        try:
            return igor_scheme.read_block_channel2(self.folder, k, companions=companions,
                                                   first=first)
        except Exception as exc:                   # noqa: BLE001
            log.warning("channel 2 of block %d in %s cannot be read (%s: %s)",
                        k, self.folder.name, type(exc).__name__, exc)
            return None

    def block(self, k: int) -> igor_scheme.IgorBlock:
        """Block ``k`` with its companions, the last one looked at kept."""
        if self._cache is None or self._cache[0] != k:
            self._cache = (k, self._read(k, companions=True))
        return self._cache[1]

    def block2(self, k: int) -> igor_scheme.IgorBlock | None:
        """Block ``k`` of channel 2, the last one looked at kept; None when
        the day has none."""
        if self._cache2 is None or self._cache2[0] != k:
            self._cache2 = (k, self._read2(k, companions=True, first=self.block(k)))
        return self._cache2[1]

    def __len__(self) -> int:
        return len(self.entries)

    def close(self) -> None:
        self._cache = None
        self._cache2 = None

    def describe(self) -> str:
        if not self.entries:
            return "no traces"
        first, last = self.entries[0][2], self.entries[-1][2]
        blocks = (f"block {self.ks[0]}" if len(self.ks) == 1
                  else f"blocks {self.ks[0]}-{self.ks[-1]}")
        return (f"{blocks}, Igor traces {first}-{last}"
                + (f", two current channels ({self.n2} traces have channel 2)"
                   if self.hist2 is not None else ""))

    def trace(self, i: int) -> dict:
        """The i-th trace present: Igor's number and block, the conductance
        (G/G0), the displacement axis (nm), the sample rate the parameters
        imply (N points over Size/Rate seconds), the companions (None when
        their file is missing), the 20 parameters and the block's
        histogram when its file exists."""
        k, j, number = self.entries[i]
        b = self.block(k)
        p = np.asarray(b.params[j], dtype=float)
        n = b.n_points
        R = self.cfg.ramp
        size = float(p[0]) if np.isfinite(p[0]) and p[0] > 0 else R.pull_length_nm
        rate = float(p[1]) if np.isfinite(p[1]) and p[1] > 0 else R.pull_rate_nm_per_s
        fs = n * rate / size if size > 0 else R.sample_rate_hz

        def column(arr):
            return None if arr is None else np.asarray(arr[:, j], dtype=float)

        # The same trace as channel 2 read it, from the ch2 subfolder.
        g0_2 = None
        b2 = self.block2(k)
        if b2 is not None and b2.n_points == n:
            hit = np.flatnonzero(b2.numbers == number)
            if hit.size:
                g0_2 = np.asarray(b2.g0[:, int(hit[0])], dtype=float)

        return {"number": number, "block": k, "g0": np.asarray(b.g0[:, j], dtype=float),
                "disp": np.linspace(0.0, size, n), "fs": fs,
                "voltage_v": column(b.voltage_v), "current_a": column(b.current_a),
                "extension_nm": column(b.extension_nm), "params": p,
                "block_hist": b.hist, "g0_2": g0_2}

    def conductances(self):
        """Every trace's conductance in turn, block by block."""
        for k in self.ks:
            b = self._read(k, companions=False)
            for j in range(b.n_traces):
                yield np.asarray(b.g0[:, j], dtype=float)

    def data(self) -> "session_plots.Data":
        """plot.py's ``Data`` over every trace, for the histogram windows:
        each trace with its own displacement axis from its block's
        parameters. Reads every block (a full day of 10,000 traces is a few
        hundred MB), so it is made only when a histogram window asks."""
        traces, disps, traces2 = [], [], []
        for k in self.ks:
            b = self._read(k, companions=False)
            d = b.displacement_nm
            b2 = (self._read2(k, companions=False, first=b)
                  if self.hist2 is not None else None)
            where = ({int(num): j2 for j2, num in enumerate(b2.numbers)}
                     if b2 is not None and b2.n_points == b.n_points else {})
            for j in range(b.n_traces):
                traces.append(np.asarray(b.g0[:, j], dtype=np.float32))
                disps.append(d)
                j2 = where.get(int(b.numbers[j]))
                traces2.append(None if j2 is None
                               else np.asarray(b2.g0[:, j2], dtype=np.float32))
        disp0 = disps[0] if disps else np.zeros(0)
        return session_plots.Data(traces, disp0, self.cfg, self.name,
                                  paths=[self.path], disps=disps,
                                  traces2=traces2)


# --------------------------------------------------------------------------
# Histogram windows for a saved session: 1D and 2D, with their own controls
# --------------------------------------------------------------------------

def hist_window(win, session, stem: str, kind: str, tk, ttk, FigureCanvasTkAgg,
                Figure, status) -> dict:
    """A window with one plot and the knobs that matter for it, applied on
    Redraw or Return; the matplotlib toolbar underneath gives zoom, pan and
    Save. The picture itself is plot.py's (hist_1d, hist_2d), the same one
    ``python plot.py <file>.h5 1D`` draws. ``session`` is an open
    ``storage.Session`` or, for Igor data, plot.py's ``Data`` already
    loaded (``IgorDay.data()``). Returns the window's controls (for tests)."""
    from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk

    bar = ttk.Frame(win)
    bar.pack(fill="x", padx=6, pady=(6, 0))
    bar2 = ttk.Frame(win)
    bar2.pack(fill="x", padx=6, pady=(2, 0))
    fig = Figure(figsize=(7.5, 5.4), dpi=100)
    ax = fig.add_subplot(111)
    canvas = FigureCanvasTkAgg(fig, master=win)
    canvas.get_tk_widget().pack(fill="both", expand=True)
    NavigationToolbar2Tk(canvas, win)
    note = ttk.Label(win, text="", font=("Arial", 9))
    note.pack(fill="x", padx=6, pady=(0, 4))
    ctl: dict = {}

    def entry(parent, label, key, value, width=6):
        ttk.Label(parent, text=label).pack(side="left", padx=(6, 1))
        var = tk.StringVar(value=str(value))
        e = ttk.Entry(parent, textvariable=var, width=width)
        e.pack(side="left")
        e.bind("<Return>", lambda _e: redraw())
        ctl[key] = var
        return var

    def flag(parent, label, key, value):
        var = tk.BooleanVar(value=value)
        ttk.Checkbutton(parent, text=label, variable=var,
                        command=lambda: redraw()).pack(side="left", padx=6)
        ctl[key] = var
        return var

    def num(key, default, kind_=float):
        raw = ctl[key].get().strip()
        if raw == "":
            return None
        try:
            return kind_(raw)
        except ValueError:
            return default

    data = (session if isinstance(session, session_plots.Data)
            else session_plots.from_session(session, stem))
    # Data of a two-channel amplifier: the 1D window draws both channels
    # (blue and red) unless "channel" says 1 or 2, and starts a decade
    # further down, where channel 2's floor is; the 2D window draws one
    # channel, 1 unless "channel" says 2.
    two = data.two_channels
    x_low = -8 if two else -7

    if kind == "1d":
        entry(bar, "bins", "bins", 1000)
        entry(bar, "x from", "x0", x_low)
        entry(bar, "x to", "x1", 1)
        entry(bar, "line width", "lw", 1.2)
        entry(bar, "color", "color", "k", width=8)
        entry(bar2, "smooth (points)", "smooth", 11)
        flag(bar2, "log y", "logy", False)
        flag(bar2, "fill", "fill", False)
        if two:
            entry(bar2, "channel (both, 1, 2)", "channel", "both", width=5)
    else:
        entry(bar, "x bins", "nx", 200)
        entry(bar, "y bins", "ny", 300)
        entry(bar, "x from (nm)", "x0", -0.5)
        entry(bar, "x to", "x1", 2.0)
        entry(bar, "log G from", "y0", -7)
        entry(bar, "to", "y1", 1)
        entry(bar2, "zero at G/G0 = (blank: pull start)", "align", 0.5)
        entry(bar2, "colormap", "cmap", "viridis", width=9)
        entry(bar2, "color max (blank: auto)", "vmax", "")
        flag(bar2, "colorbar", "cbar", True)
        if two:
            entry(bar2, "channel (1, 2)", "channel", "1", width=3)
    ttk.Button(bar2, text="Redraw", command=lambda: redraw()).pack(side="right", padx=4)

    def which_channel(default: str) -> str:
        """What the "channel" box says (it is only there for two-channel
        data): "both", "1" or "2"; anything else is the default."""
        if "channel" not in ctl:
            return default
        word = ctl["channel"].get().strip().lower()
        return word if word in ("both", "1", "2") else default

    def redraw():
        fig.clear()
        ax = fig.add_subplot(111)
        if kind == "1d":
            x0, x1 = num("x0", float(x_low)), num("x1", 1.0)
            info = session_plots.hist_1d(
                ax, data,
                bins=num("bins", 1000, int) or 1000,
                smooth=num("smooth", 11, int) or 11,
                xlim=(float(x_low) if x0 is None else x0, 1.0 if x1 is None else x1),
                lw=num("lw", 1.2) or 1.2,
                color=ctl["color"].get().strip() or "k",
                logy=ctl["logy"].get(), fill=ctl["fill"].get(),
                channel=which_channel("both"))
        else:
            x0, x1 = num("x0", -0.5), num("x1", 2.0)
            y0, y1 = num("y0", -7.0), num("y1", 1.0)
            info = session_plots.hist_2d(
                ax, data,
                xbins=num("nx", 200, int) or 200,
                ybins=num("ny", 300, int) or 300,
                xlim=(-0.5 if x0 is None else x0, 2.0 if x1 is None else x1),
                ylim=(-7.0 if y0 is None else y0, 1.0 if y1 is None else y1),
                align=num("align", 0.5),
                cmap=ctl["cmap"].get().strip() or "viridis",
                vmax=num("vmax", None), colorbar=ctl["cbar"].get(),
                channel=which_channel("1"))
        note.config(text=info["note"])
        fig.tight_layout()
        canvas.draw_idle()

    ctl["redraw"] = redraw
    redraw()
    return ctl


# --------------------------------------------------------------------------
# The window
# --------------------------------------------------------------------------

def load_saving(path: Path) -> dict:
    """What the Saving tab showed last time, or {}."""
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_saving(path: Path, saving: dict) -> None:
    data = dict(saving)
    data["folder"] = str(data["folder"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=1)


def run_gui(cfg: RigConfig, out_dir: Path, igor_export: bool,
            config_name: str, autoclose: float | None = None,
            readback: bool = False,
            saving_file: Path | None = None, zoom: float | None = None,
            setup_id: str | None = None) -> int:
    saving_file = saving_file or (_ROOT / "data" / "pullout_saving.json")
    import tkinter as tk
    from tkinter import filedialog, ttk

    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    guard, rig = open_rig(cfg)
    mon = Monitor(rig)
    worker = Worker(cfg, rig, mon, save=True, out_dir=out_dir,
                    igor_export=igor_export)
    worker.config_name = config_name
    # In a simulation a move toward the surface made by hand (Approach, the
    # sliders, Step closer) takes the time it takes on the rig, so that what
    # is tried here is what the rig will do. Not in the self-test: that one
    # is timed.
    worker.sim_real_time = bool(cfg.simulate and autoclose is None)
    worker.start()

    root = tk.Tk()
    root.title(f"STM-BJ pull-out  {__version__}" +
               ("  [simulate]" if cfg.simulate else f"  [{cfg.channels.device}]")
               + f"  {config_name}")
    # The same window everywhere. Windows draws the themed widgets in its
    # own "vista" style, the look this program was laid out for. The Mac
    # would draw them in "aqua" -- classic buttons ignoring their colours,
    # fonts a third smaller, and in dark mode the classic widgets black --
    # so there the window is rebuilt in Windows' colours and sizes
    # (windows_look). PULLOUT_THEME=clam forces the same on any platform
    # (used to test it on Linux); --zoom scales it.
    style = ttk.Style(root)
    want_clam = sys.platform == "darwin" or os.environ.get("PULLOUT_THEME") == "clam"
    if zoom is None:
        # A MacBook's screen packs a fifth more pixels into an inch than the
        # lab's monitor, so Windows' sizes come out small there; 1.2 puts
        # the text at the size the Mac's own windows use.
        zoom = 1.2 if sys.platform == "darwin" else 1.0
    if want_clam and "clam" in style.theme_names():
        windows_look(root, style, zoom)
    elif zoom != 1.0:
        root.tk.call("tk", "scaling", float(root.tk.call("tk", "scaling")) * zoom)
    themed_buttons = style.theme_use() == "clam"

    def px(n: int) -> int:
        """A pixel size laid out at zoom 1 (a wrap width, the slider's
        length), scaled with the text."""
        return int(round(n * zoom))

    outer = ttk.Frame(root)
    outer.pack(fill="both", expand=True, padx=6, pady=6)
    # The left column scrolls: on a 1080-pixel screen it just fits, on a
    # laptop it does not, so it lives on a canvas with a scrollbar and the
    # mouse wheel works wherever the pointer is over it. The column keeps
    # its natural width; only its height is cut to what the screen allows.
    left_outer = ttk.Frame(outer)
    left_outer.pack(side="left", fill="y", padx=(0, 8))
    left_canvas = tk.Canvas(left_outer, highlightthickness=0, borderwidth=0,
                            yscrollincrement=24)
    left_bar = ttk.Scrollbar(left_outer, orient="vertical", command=left_canvas.yview)
    left_canvas.configure(yscrollcommand=left_bar.set)
    left_bar.pack(side="right", fill="y")
    left_canvas.pack(side="left", fill="y")
    left = ttk.Frame(left_canvas)
    left_canvas.create_window((0, 0), window=left, anchor="nw")

    def left_resized(_e=None):
        left_canvas.configure(scrollregion=left_canvas.bbox("all"),
                              width=left.winfo_reqwidth())
    left.bind("<Configure>", left_resized)

    def over_left(widget) -> bool:
        while widget is not None:
            if widget is left_canvas:
                return True
            widget = getattr(widget, "master", None)
        return False

    def on_wheel(e):
        # Windows and macOS send <MouseWheel> with delta (120 per notch on
        # Windows, small integers on macOS); X11 sends Button-4 / Button-5.
        if not over_left(root.winfo_containing(e.x_root, e.y_root)):
            return
        num = getattr(e, "num", None)
        delta = getattr(e, "delta", 0)
        if num == 4 or delta > 0:
            left_canvas.yview_scroll(-1, "units")
        elif num == 5 or delta < 0:
            left_canvas.yview_scroll(1, "units")
    root.bind_all("<MouseWheel>", on_wheel, add="+")
    root.bind_all("<Button-4>", on_wheel, add="+")
    root.bind_all("<Button-5>", on_wheel, add="+")
    right = ttk.Frame(outer)
    right.pack(side="right", fill="both", expand=True)

    # -- run ---------------------------------------------------------------------
    rb = ttk.LabelFrame(left, text="Run")
    rb.pack(fill="x", pady=(0, 3))
    n_var = tk.StringVar(value="3" if autoclose is not None else "10")
    svars: dict[str, tk.StringVar] = {}        # settings entries, by config path
    for c in range(3):
        rb.columnconfigure(c, weight=1, uniform="run")

    def on_run():
        try:
            n = max(1, int(n_var.get()))
        except ValueError:
            return
        sv = saving_now()
        if not sv["name"].strip() or not sv["experiment"].strip():
            set_status("type your name and an experiment name in the "
                               "Saving tab first; every Start N is one experiment")
            nb.select(fb)
            return
        save_saving(saving_file, sv)
        worker.send("run", n, sv)
    # The experiment's start button, and the two that pause and resume it,
    # are the big coloured ones. On Windows classic tk.Buttons (the vista
    # theme ignores colours on themed buttons); under the clam theme (the
    # Mac) themed buttons with coloured styles, which there do show.
    BIG = ("Arial", 11, "bold")
    GREEN, GREEN_DOWN, RED, RED_DOWN = "#2e7d32", "#1b5e20", "#c62828", "#8e0000"
    BLUE, BLUE_DOWN = "#1565c0", "#0d47a1"         # the Piezo box's Approach
    if themed_buttons:
        for name, bg, down in (("Go", GREEN, GREEN_DOWN), ("Stop", RED, RED_DOWN),
                               ("Move", BLUE, BLUE_DOWN),
                               ("Off", root.cget("background"), root.cget("background"))):
            style.configure(f"{name}.TButton", font=BIG, foreground="white",
                            background=bg, bordercolor=down, lightcolor=bg,
                            darkcolor=bg, padding=(4, 3))
            style.map(f"{name}.TButton", background=[("active", down),
                                                     ("disabled", bg)],
                      lightcolor=[("active", down)], darkcolor=[("active", down)],
                      bordercolor=[("disabled", "#adadad")],
                      foreground=[("disabled", "#9e9e9e")])

    def big_button(parent, text, command, bg, down):
        if themed_buttons:
            name = {RED: "Stop", BLUE: "Move"}.get(bg, "Go")
            return ttk.Button(parent, text=text, command=command,
                              style=f"{name}.TButton")
        return tk.Button(parent, text=text, font=BIG, command=command, bg=bg,
                         fg="white", activebackground=down,
                         activeforeground="white", pady=2)

    start_btn = big_button(rb, "\u25b6  Start N", on_run, GREEN, GREEN_DOWN)
    start_btn.grid(row=0, column=0, columnspan=2, padx=2, pady=(2, 1), sticky="ew")
    nf = ttk.Frame(rb)
    nf.grid(row=0, column=2, padx=2, pady=(2, 1), sticky="w")
    ttk.Label(nf, text="N =", font=BIG).pack(side="left", padx=(2, 4))
    ttk.Entry(nf, textvariable=n_var, width=6, font=("Arial", 11)).pack(side="left")
    ttk.Label(nf, text="traces").pack(side="left", padx=(4, 0))
    cont_btn = big_button(rb, "Continue", lambda: worker.send("continue"),
                          GREEN, GREEN_DOWN)

    def set_continue(enabled: bool):
        """Green and live while a stopped run is waiting; grey otherwise."""
        if themed_buttons:
            cont_btn.config(state="normal" if enabled else "disabled",
                            style="Go.TButton" if enabled else "Off.TButton")
        else:
            cont_btn.config(state="normal" if enabled else "disabled",
                            bg=GREEN if enabled else root.cget("background"))
    set_continue(False)
    cont_btn.grid(row=1, column=0, padx=2, pady=1, sticky="ew")
    big_button(rb, "\u25a0  Stop", worker.stop_flag.set, RED, RED_DOWN).grid(
        row=1, column=1, padx=2, pady=1, sticky="ew")
    ttk.Button(rb, text="Calibrate zero", command=lambda: worker.send("zero")).grid(
        row=1, column=2, padx=2, pady=1, sticky="ew")
    smf = ttk.Frame(rb)
    smf.grid(row=2, column=0, columnspan=3, sticky="w", padx=2)
    ttk.Label(smf, text="smash the tip every").pack(side="left", padx=(2, 2))
    smash_var = svars.setdefault("ramp.smash_every",
                                 tk.StringVar(value=f"{cfg.ramp.smash_every:g}"))
    sm_ent = ttk.Entry(smf, textvariable=smash_var, width=5)
    sm_ent.pack(side="left")
    ttk.Label(smf, text="attempts (0 = never)").pack(side="left", padx=2)
    sm_ent.bind("<Return>", lambda _e: apply_settings())
    sm_ent.bind("<FocusOut>", lambda _e: apply_settings())

    # -- status: the rig's numbers and what the program is doing, in colour ---------
    # Right under Run, where the eye lands: the readout (state, piezo,
    # junction, current, file, Keithley) and the last message. Green when
    # a thing went right, red when something is wrong or refused, orange
    # for a warning or a Stop, blue while something automatic is running
    # -- and then the whole box turns yellow with a "do not touch" line.
    stb = tk.LabelFrame(left, text="Status", font=("Arial", 9, "bold"))
    stb.pack(fill="x", pady=(0, 3))
    # A rig whose config names a second amplifier output gets one more
    # readout line (and one more cell under the slider) for channel 2.
    has_ch2 = bool(cfg.channels.ai_current_2)
    ro = tk.Text(stb, width=62, height=8 if has_ch2 else 7, font=("Courier", 9),
                 relief="flat", state="disabled", background=root.cget("background"))
    ro.pack(fill="x", padx=2, pady=(1, 0))
    status = tk.Label(stb, text="ready", font=("Arial", 10, "bold"), wraplength=px(548),
                      justify="left", anchor="nw", height=3, fg="#1b5e20")
    status.pack(fill="x", padx=6, pady=(1, 0))
    status2 = tk.Label(stb, text="", font=("Arial", 9, "bold"), fg="#8e0000",
                       wraplength=px(548), justify="left", anchor="w", height=1)
    status2.pack(fill="x", padx=6, pady=(0, 2))
    COLOURS = {"ok": "#1b5e20", "bad": "#b00000", "warn": "#b06000",
               "busy": "#0d47a1", "info": "#202020"}
    BAD_WORDS = ("refused", "could not", "cannot", "failed", "not connected",
                 "error", "asleep", "switched off", "no reply", "nothing at",
                 "safety", "zero check on", "still closed", "crashed", "busy:",
                 "not a number", "unknown", "did not")
    WARN_WORDS = ("stopped", "paused", "warning", "stop ")
    OK_WORDS = ("connected", "applied", "engaged at", "finished", "done", "saved",
                "opened the junction", "junction opened", "preamp zero", "set to",
                "logged", "written", "ok,", "ready", "stepped")
    BUSY_WORDS = ("...", "running", "approaching", "finding", "measuring",
                  "stepping", "smashing", "pulling")

    def judge(text: str) -> str:
        t = text.lower()
        if any(w in t for w in BAD_WORDS):
            return "bad"
        if any(w in t for w in WARN_WORDS):
            return "warn"
        if any(w in t for w in BUSY_WORDS):
            return "busy"
        if any(w in t for w in OK_WORDS):
            return "ok"
        return "info"

    def set_status(text: str, level: str | None = None) -> None:
        level = level or judge(text)
        status.config(text=text, fg=COLOURS.get(level, COLOURS["info"]))

    def working(on: bool, line: str = "") -> None:
        """The yellow box and the "do not touch" line while a command runs."""
        bg = "#fff3b0" if on else root.cget("background")
        for w in (stb, status, status2, ro):
            w.config(bg=bg)
        status2.config(text=line)

    def set_text(widget, text):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.config(state="disabled")

    # -- the Keithley 428: Igor's Keithley Controls -------------------------------------
    # Not shown on a rig whose config names a second amplifier output
    # (channels.ai_current_2): an amplifier with two outputs is not the
    # 428, and the Current amplifier box stands here instead. The box and
    # everything in it are still made, so nothing that talks to them has
    # to know.
    kb = ttk.LabelFrame(left, text="Keithley 428 (GPIB)")
    if not has_ch2:
        kb.pack(fill="x", pady=(0, 3))
    k_lbl = tk.Label(kb, text="not connected (the front panel rules)",
                     font=("Arial", 9), anchor="w")
    ttk.Button(kb, text="Connect",
               command=lambda: worker.send("keithley", "connect")).grid(
        row=0, column=0, padx=2, pady=1, sticky="ew")
    k_lbl.grid(row=0, column=1, columnspan=3, sticky="w", padx=4)
    zc_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(kb, text="Zero check", variable=zc_var,
                    command=lambda: worker.send("keithley", "zero_check",
                                                zc_var.get())).grid(
        row=1, column=0, sticky="w", padx=2)
    ttk.Button(kb, text="Zero correct",
               command=lambda: worker.send("keithley", "zero_correct")).grid(
        row=1, column=1, padx=2, pady=1, sticky="ew")
    sup_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(kb, text="Suppress I", variable=sup_var,
                    command=lambda: worker.send("keithley", "suppress",
                                                sup_var.get())).grid(
        row=1, column=2, sticky="w", padx=2)
    ttk.Button(kb, text="Find suppress",
               command=lambda: worker.send("keithley", "find_suppress")).grid(
        row=1, column=3, padx=2, pady=1, sticky="ew")
    gf = ttk.Frame(kb)
    gf.grid(row=2, column=0, columnspan=2, sticky="w", padx=2, pady=(2, 2))
    ttk.Label(gf, text="Gain 10^").pack(side="left")
    gain_var = tk.StringVar(value=str(cfg.keithley.gain_exponent))
    ttk.Entry(gf, textvariable=gain_var, width=3).pack(side="left", padx=2)
    ttk.Label(gf, text="V/A").pack(side="left")

    def on_gain():
        try:
            n = int(gain_var.get())
        except ValueError:
            set_status(f"gain: '{gain_var.get()}' is not a whole number")
            return
        if not 3 <= n <= 11:
            set_status("gain exponent must be 3 to 11")
            return
        worker.send("keithley", "gain", n)
    ttk.Button(gf, text="Set", command=on_gain).pack(side="left", padx=4)
    sup_lbl = tk.Label(kb, text="suppress: unknown", font=("Arial", 9), anchor="w")
    sup_lbl.grid(row=2, column=2, columnspan=2, sticky="w", padx=4)

    def keithley_line() -> str:
        k = live.get("keithley")
        if not k or not k["connected"]:
            return "not connected (front panel rules)"
        word = {None: "?", True: "ON", False: "off"}
        return (f"zero check {word[k['zero_check']]}, suppress "
                f"{word[k['suppress']]}, gain 1e{k['gain']}")

    def show_keithley(k: dict):
        live["keithley"] = k
        sim = " (simulated)" if cfg.simulate else ""
        k_lbl.config(text=(f"connected{sim}: {cfg.keithley.resource}; Igor's Kill "
                           "Tasks leaves zero check ON" if k["connected"]
                           else "not connected (the front panel rules)"))
        if k["zero_check"] is not None:
            zc_var.set(k["zero_check"])
        if k["suppress"] is not None:
            sup_var.set(k["suppress"])
        sup_lbl.config(text=("suppress: unknown" if k["suppress_ua"] is None
                             else f"suppress: {k['suppress_ua']:+.4f} uA")
                            + f"   gain 1e{k['gain']} V/A")
        gain_var.set(str(k["gain"]))
        sync_gain_boxes()          # Set here is channel 1's gain there

    # -- the coarse approach: Igor's Actuator Controls, or a screw by hand ------------
    ab = ttk.LabelFrame(left, text="Coarse approach")
    ab.pack(fill="x", pady=(0, 3))
    A = cfg.actuator
    mode_var = tk.StringVar(value="screw" if A.kind == "none" else "actuator")
    mf = ttk.Frame(ab)
    mf.grid(row=0, column=0, sticky="w")
    ttk.Radiobutton(mf, text="Actuator", value="actuator",
                    variable=mode_var, command=lambda: show_mode()).pack(
        side="left", padx=2)
    ttk.Radiobutton(mf, text="screw by hand", value="screw",
                    variable=mode_var, command=lambda: show_mode()).pack(
        side="left", padx=8)
    contact_var = tk.StringVar(value="0.15")            # the beep / light level
    contact = {"ua": 0.15}

    # Actuator mode: Igor's Step Size, Step closer / apart, Start Approach,
    # the stop current and the step counter.
    af = ttk.Frame(ab)
    step_var = tk.StringVar(value=str(A.step_size))
    amp_var = tk.StringVar(value=str(A.step_amplitude))
    stop_var = tk.StringVar(value=f"{A.stop_current_ua:g}")

    def apply_actuator():
        try:
            A.step_size = max(1, int(step_var.get()))
            A.step_amplitude = max(1, min(50, int(amp_var.get())))
            A.stop_current_ua = abs(float(stop_var.get()))
            v = float(appr_var.get())
            lo, hi = cfg.limits.piezo_ao_min_v, cfg.limits.piezo_ao_max_v - 0.5
            if not lo <= v <= hi:
                set_status(f"coarse approach piezo: {v:g} V must be "
                                   f"between {lo:g} and {hi:g} V")
                appr_var.set(f"{A.approach_piezo_v:g}")
            else:
                A.approach_piezo_v = v
        except ValueError:
            set_status("actuator: step size and amplitude must be "
                               "whole numbers, stop current and piezo numbers")
    # The link first: which controller (two Newport ones speak different
    # languages), the COM port (Igor hard-wired Com1), and Connect, which
    # opens the port and asks the controller for its status and position.
    KIND_NAMES = {"nanopz": "NanoPZ PZC200 (19200 baud)",
                  "agilis": "Agilis AG-UC2/UC8 (921600 baud)"}
    kind_var = tk.StringVar(value=KIND_NAMES.get(A.kind.lower(), KIND_NAMES["nanopz"]))

    def kind_now() -> str:
        return next((k for k, v in KIND_NAMES.items() if v == kind_var.get()),
                    "nanopz")
    ttk.Label(af, text="Controller").grid(row=0, column=0, sticky="w", padx=2)
    ttk.Combobox(af, textvariable=kind_var, width=28, state="readonly",
                 values=tuple(KIND_NAMES.values())).grid(
        row=0, column=1, columnspan=3, padx=2, pady=2, sticky="w")
    port_var = tk.StringVar(value=A.port)
    ttk.Label(af, text="Port").grid(row=1, column=0, sticky="w", padx=2)
    port_box = ttk.Combobox(af, textvariable=port_var, width=8, values=(A.port,))
    port_box.grid(row=1, column=1, padx=2, sticky="w")
    ttk.Button(af, text="Connect",
               command=lambda: hand_move("actuator", "connect", port_var.get(),
                                         kind_now())).grid(
        row=1, column=2, padx=2, pady=1, sticky="ew")
    ttk.Button(af, text="Find ports",
               command=lambda: worker.send("actuator", "ports")).grid(
        row=1, column=3, padx=2, pady=1, sticky="ew")
    szf = ttk.Frame(af)
    szf.grid(row=2, column=0, columnspan=2, sticky="w", padx=2)
    ttk.Label(szf, text="Steps").pack(side="left")
    e1 = ttk.Entry(szf, textvariable=step_var, width=4)
    e1.pack(side="left", padx=(2, 8))
    ttk.Label(szf, text="Amplitude").pack(side="left")
    e1b = ttk.Entry(szf, textvariable=amp_var, width=4)
    e1b.pack(side="left", padx=2)
    ttk.Button(af, text="Step closer",
               command=lambda: (apply_actuator(), hand_move("coarse_step", True))).grid(
        row=2, column=2, padx=2, pady=1, sticky="ew")
    ttk.Button(af, text="Step apart",
               command=lambda: (apply_actuator(), hand_move("coarse_step", False))).grid(
        row=2, column=3, padx=2, pady=1, sticky="ew")
    saf = ttk.Frame(af)
    saf.grid(row=3, column=0, columnspan=3, sticky="w", padx=2)
    ttk.Label(saf, text="Start approach: piezo at").pack(side="left")
    appr_var = tk.StringVar(value=f"{A.approach_piezo_v:g}")
    e4 = ttk.Entry(saf, textvariable=appr_var, width=4)
    e4.pack(side="left", padx=2)
    ttk.Label(saf, text="V, stops at").pack(side="left")
    e2 = ttk.Entry(saf, textvariable=stop_var, width=5)
    e2.pack(side="left", padx=2)
    ttk.Label(saf, text="uA").pack(side="left")
    ttk.Button(af, text="Start approach",
               command=lambda: (apply_actuator(), hand_move("coarse_approach"))).grid(
        row=3, column=3, padx=2, pady=1, sticky="ew")
    for e in (e1, e1b, e2, e4):
        e.bind("<Return>", lambda _e: apply_actuator())
        e.bind("<FocusOut>", lambda _e: apply_actuator())
    NOT_CONNECTED = "not connected: choose the controller and the port, press Connect"
    STEP_RULE = (f"a step needs the piezo at or below {A.approach_piezo_v:g} V "
                 "(its approach position)")
    act_lbl = tk.Label(af, text=NOT_CONNECTED, font=("Arial", 9), anchor="w",
                       fg="#b06000", wraplength=px(560), justify="left")
    act_lbl.grid(row=4, column=0, columnspan=4, sticky="w", padx=2)

    def show_actuator(p: dict):
        if p.get("ports"):
            port_box.config(values=tuple(d for d, _desc in p["ports"]))
        if p["connected"]:
            kind_var.set(KIND_NAMES.get(p.get("controller", ""), kind_var.get()))
            act_lbl.config(fg="#006000",
                           text=f"connected on {p['port']}"
                                + (f", position {p['position']}"
                                   if p["position"] is not None else "")
                                + f"; {p['steps']} steps this session; {STEP_RULE}")
        else:
            act_lbl.config(fg="#b06000", text=NOT_CONNECTED)

    # Screw mode: nothing to drive; the program is the eyes. The contact
    # current sets the beep and the light.
    sf = ttk.Frame(ab)
    ttk.Label(sf, text="contact current (uA)").grid(row=0, column=0, sticky="w", padx=2)
    e3 = ttk.Entry(sf, textvariable=contact_var, width=6)
    e3.grid(row=0, column=1, padx=2)
    contact_lbl = tk.Label(sf, text="  OPEN  ", font=("Arial", 11, "bold"),
                           fg="white", bg="#6a6a6a", width=10)
    contact_lbl.grid(row=0, column=2, padx=8)
    ttk.Label(sf, text="turn the screw in slowly; the light and the beep say "
                       "contact; then Start N",
              font=("Arial", 9)).grid(row=1, column=0, columnspan=3, sticky="w", padx=2)
    if cfg.simulate:
        # The simulator has no screw to turn: this box is one. It puts the
        # pretend surface where a real one ends up (near 8 V, say), or out
        # of the piezo's reach (the worker's cmd_sim_surface).
        ssf = ttk.Frame(sf)
        ssf.grid(row=2, column=0, columnspan=3, sticky="w", padx=2, pady=(2, 0))
        ttk.Label(ssf, text="simulator's screw: surface at",
                  font=("Arial", 9)).pack(side="left")
        surface_var = tk.StringVar(
            value=f"{getattr(rig._session, 'surface_nm', 300.0):g}")
        ttk.Entry(ssf, textvariable=surface_var, width=7).pack(side="left", padx=2)
        ttk.Label(ssf, text="nm up the piezo's travel",
                  font=("Arial", 9)).pack(side="left")

        def turn_screw():
            try:
                nm = float(surface_var.get())
            except ValueError:
                set_status(f"simulator's screw: '{surface_var.get()}' is not a "
                           "number of nm", "bad")
                return
            hand_move("sim_surface", nm)
        ttk.Button(ssf, text="Turn", width=5, command=turn_screw).pack(
            side="left", padx=4)

    def apply_contact(*_a):
        try:
            contact["ua"] = abs(float(contact_var.get()))
        except ValueError:
            return
        # The same current is a sign of contact for a move toward the
        # surface made by hand (Approach, the sliders, Step closer).
        worker.contact_ua = contact["ua"]
    contact_var.trace_add("write", apply_contact)

    def show_mode():
        af.grid_forget()
        sf.grid_forget()
        (af if mode_var.get() == "actuator" else sf).grid(row=1, column=0, sticky="w")
    show_mode()

    # -- piezo: Igor's PiezoGroupbox, with Igor's readouts under it -----------------
    # Step apart / Z (nm) / Step closer, two sliders over the piezo's range
    # that the piezo follows (a click on the bar, or a drag: v75; Igor's
    # SetPiezoBiasFromSlider applied on mouse release, as these did up to
    # v74), and the readouts Igor kept at the bottom of its panel:
    # I (uA), V (mV), Piezo, plus the sense line this rig has. They are
    # refreshed by every command and, while idle, every 0.3 s by a quiet
    # hold (Igor's Background Sampling) with Igor's beep above the contact
    # current.
    C = cfg.cal
    pb = ttk.LabelFrame(left, text="Piezo (Igor's piezo controls)")
    pb.pack(fill="x", pady=(0, 3))
    lo_v, hi_v = cfg.limits.piezo_ao_min_v, cfg.limits.piezo_ao_max_v
    z_var = tk.StringVar(value="5")

    # Commands that do not count as busy: they only read (the idle
    # sampling, the Monitor window's sample-rate check).
    QUIET = ("monitor", "ratecheck", "noop")

    def rig_is_free() -> bool:
        """Nothing but idle sampling is running or queued."""
        return ((not worker.busy or worker.current in QUIET)
                and all(c[0] in QUIET for c in list(worker.commands.queue)))

    def hand_move(*command) -> bool:
        """Send a move made by hand, unless a command is already running:
        a slider release in the middle of Start N must not queue up behind it."""
        if not rig_is_free():
            set_status("busy: wait for the current command to finish, "
                               "or press Stop")
            return False
        worker.send(*command)
        return True

    def on_step(sign: int):
        try:
            nm = abs(float(z_var.get()))
        except ValueError:
            nm = float("nan")
        if not math.isfinite(nm):
            set_status(f"Z: '{z_var.get()}' is not a number")
            return
        hand_move("step", sign * nm)

    # The driver box: where its switch stands and how far the stage moves in
    # all. Every distance in this window hangs on these two (the worker's
    # cmd_piezo_mode has the arithmetic, and the reason a change of mode
    # takes the piezo to 0 V first). Pick, type, Set: nothing changes
    # before Set, and the line under the row says what Set would do.
    df = ttk.Frame(pb)
    df.grid(row=0, column=0, columnspan=3, sticky="w", padx=2, pady=(1, 0))
    ttk.Label(df, text="Driver", font=("Arial", 9, "bold")).pack(side="left")
    pmode_var = tk.StringVar(value=str(C.piezo_mode).lower())
    ptotal_var = tk.StringVar(
        value="" if C.piezo_total_um is None else f"{C.piezo_total_um:g}")
    for word in ("standard", "bypass"):
        ttk.Radiobutton(df, text=word, value=word, variable=pmode_var).pack(
            side="left", padx=(6, 0))
    ttk.Label(df, text="total displacement", font=("Arial", 9)).pack(
        side="left", padx=(12, 2))
    pt_entry = ttk.Entry(df, textvariable=ptotal_var, width=8)
    pt_entry.pack(side="left")
    ttk.Label(df, text="um", font=("Arial", 9)).pack(side="left", padx=(2, 6))
    ttk.Button(df, text="Set", width=5, command=lambda: set_piezo()).pack(side="left")
    drive_lbl = tk.Label(pb, text="", font=("Arial", 9, "bold"), anchor="w",
                         justify="left", wraplength=px(540), fg="#006000")
    drive_lbl.grid(row=1, column=0, columnspan=3, sticky="w", padx=4)
    piezo_ui = {"showing": False}

    def piezo_numbers(mode: str, total_um: float) -> str:
        """What a mode and a total displacement come to, in words."""
        per_volt = total_um * 1e3 / C.piezo_drive_full_v * (
            C.piezo_drive_gain if mode == "standard" else 1.0)
        return (f"1 V at the card = {per_volt:.2f} nm; the whole {lo_v:g} to "
                f"{hi_v:g} V = {(hi_v - lo_v) * per_volt:.0f} nm")

    def piezo_label():
        """The driver as the program has it now."""
        mode, total = str(C.piezo_mode).lower(), C.piezo_total_um
        if total is None:
            drive_lbl.config(fg="#b06000", text=(
                "no total displacement set: the config's own "
                f"{C.piezo_nm_per_volt:g} nm per volt is used. Type the stage's "
                "total displacement (10.776, say), pick the mode, press Set"))
        else:
            drive_lbl.config(fg="#006000",
                             text=f"{mode.upper()}: " + piezo_numbers(mode, total))

    def show_piezo(_p: dict | None = None):
        """After Set, and at start-up: the row and the sliders follow the
        program's mode and total displacement."""
        piezo_ui["showing"] = True
        try:
            pmode_var.set(str(C.piezo_mode).lower())
            if C.piezo_total_um is not None:
                ptotal_var.set(f"{C.piezo_total_um:g}")
        finally:
            piezo_ui["showing"] = False
        piezo_label()
        set_fine_window()
        on_slide(slider_var.get())

    def preview_piezo(*_a):
        """What Set would do, while the row differs from what is applied."""
        if piezo_ui["showing"]:
            return
        mode = pmode_var.get()
        try:
            total = float(ptotal_var.get())
        except ValueError:
            return
        if not total > 0:
            return
        same_mode = mode == str(C.piezo_mode).lower()
        if same_mode and C.piezo_total_um is not None and \
                abs(total - C.piezo_total_um) < 1e-12:
            piezo_label()
            return
        drive_lbl.config(fg="#b06000", text=(
            f"press Set for {mode.upper()}, {total:g} um: "
            + piezo_numbers(mode, total)
            + ("" if same_mode else ". The piezo goes to 0 V first; then put "
               f"the driver's switch on {mode.upper()}")))

    def set_piezo():
        try:
            total = float(ptotal_var.get())
        except ValueError:
            set_status(f"total displacement: '{ptotal_var.get()}' is not a "
                       "number of micrometres", "bad")
            return
        if not hand_move("piezo_mode", pmode_var.get(), total):
            show_piezo()                           # busy: back to what is applied
    pmode_var.trace_add("write", preview_piezo)
    ptotal_var.trace_add("write", preview_piezo)
    pt_entry.bind("<Return>", lambda _e: set_piezo())

    ttk.Button(pb, text="Step apart", command=lambda: on_step(-1)).grid(
        row=2, column=0, padx=2, pady=1, sticky="ew")
    zf = ttk.Frame(pb)
    zf.grid(row=2, column=1, padx=2)
    ttk.Label(zf, text="Z (nm)", font=("Arial", 9)).pack(side="left")
    ttk.Entry(zf, textvariable=z_var, width=6).pack(side="left", padx=2)
    ttk.Button(pb, text="Step closer", command=lambda: on_step(+1)).grid(
        row=2, column=2, padx=2, pady=1, sticky="ew")

    slider_var = tk.DoubleVar(value=rig.piezo_v)       # coarse: the whole range
    fine_var = tk.DoubleVar(value=rig.piezo_v)         # fine: a window of it
    fine_half_var = tk.StringVar(value="0.5")
    speed_var = tk.StringVar(value=f"{worker.hand_speed_nm_s:g}")
    # dragging: the mouse is down on a slider (which: that slider). grab:
    # how far from the knob's middle the mouse took hold of it, in volts.
    # target: where a slider has asked the piezo to go, from the mouse going
    # down until the piezo is there or was stopped (None otherwise: the
    # knobs are then on the piezo). window: the fine slider's range. half:
    # the last usable "fine: +/-" width.
    slide = {"dragging": False, "which": None, "grab": 0.0, "target": None,
             "window": None, "half": 0.5}

    # Approach: the piezo itself comes up to the surface, after the screws
    # have brought it within reach (the worker's cmd_piezo_approach), at the
    # speed in the box. The sliders and Step closer go toward the surface at
    # that speed too, and stop at contact in the same way. A big button: it
    # is the one pressed with an eye on the rig.
    apf = ttk.Frame(pb)
    apf.grid(row=3, column=0, columnspan=3, sticky="ew", padx=2, pady=(3, 0))
    approach_btn = big_button(apf, "Approach", lambda: hand_move("piezo_approach"),
                              BLUE, BLUE_DOWN)
    approach_btn.config(width=12)
    approach_btn.pack(side="left", ipady=px(3))
    ttk.Label(apf, text="speed toward\nthe surface", font=("Arial", 9),
              justify="right").pack(side="left", padx=(8, 3))
    ttk.Entry(apf, textvariable=speed_var, width=6).pack(side="left")
    ttk.Label(apf, text="nm/s. It stops at contact.\nThe sliders and Step closer too.",
              font=("Arial", 9), justify="left").pack(side="left", padx=(3, 0))

    def knob_strip(row: int):
        """A thin strip over a slider, for the label that rides on its knob
        (the volts and the nanometres; Tk's own number over a knob can only
        be the slider's value, the volts) and for the small red mark that
        shows where the piezo is while the knob is ahead of it."""
        strip = tk.Frame(pb, height=px(17))
        strip.grid(row=row, column=0, columnspan=3, sticky="ew", padx=4)
        return (strip, tk.Label(strip, text="", font=("Arial", 9, "bold")),
                tk.Frame(strip, width=px(5), height=px(9), bg="#c62828"))

    def show_knobs(*_a):
        """The label on each slider's knob: where the knob is, in volts and
        in nanometres. While a slider has asked for a place the piezo has
        not reached (the mouse holds a knob, or the piezo is on its way)
        the labels are orange and a red mark on each strip shows where the
        piezo is."""
        ahead = slide["target"] is not None
        for sc, var, strip, lbl, mark, digits in knobs:
            # The variable, not the slider's own rounded value: with the
            # piezo at 8.0271 V both labels say 8650.0 nm, though the coarse
            # slider can only stand on 8.027 V.
            v = float(var.get())
            lbl.config(text=f"{v:.{digits}f} V = {C.piezo_volts_to_nm(v):.1f} nm",
                       fg="#b06000" if ahead else "#202020")
            try:
                x = float(sc.coords()[0])           # the knob, in pixels
            except (tk.TclError, IndexError, ValueError):
                x = 0.0
            half = lbl.winfo_reqwidth() / 2.0       # kept inside the strip
            x = min(max(x, half), max(half, strip.winfo_width() - half))
            lbl.place(x=x, y=0, anchor="n")
            at = rig.piezo_v
            if ahead and float(sc.cget("from")) - 1e-9 <= at <= float(sc.cget("to")) + 1e-9:
                try:
                    mx = float(sc.coords(at)[0])
                except (tk.TclError, IndexError, ValueError):
                    mx = 0.0
                mark.place(x=mx, rely=1.0, anchor="s")
                mark.lift()
            else:
                mark.place_forget()

    def on_slide(_value=None):
        show_knobs()
        if slide["dragging"]:
            # Igor's readouts kept ticking under a held mouse. Tk's timers
            # should too, but a drag floods the event queue with motion
            # events, so drive the refresh from the drag itself: every
            # 150 ms of dragging, one pass of the window's heartbeat and a
            # repaint, same as the timer would have done.
            if time.monotonic() - live.get("last_poll", 0.0) > 0.15:
                poll_body()
                root.update_idletasks()

    # Two sliders on the one piezo output. The classic Tk scale, not the
    # themed one: it has a knob you can see and ticks, which is what Igor's
    # looked like. Over each knob rides a label with its volts and its
    # nanometres (knob_strip, show_knobs).
    # COARSE: the piezo's whole range, on steps of 1 mV. With a micrometre
    # to the volt this is the one for coming up to the surface after the
    # screws.
    # FINE: a window of the range, half a volt either side of where the
    # piezo is (the box beside it), on steps of 0.1 mV. The window is put
    # on round numbers (7.5 to 8.5 V around 7.99 V), is cut off where the
    # piezo's range ends, and walks along whenever the piezo nears one of
    # its ends (fine_window). After Approach the piezo is at the contact,
    # so the window is around the contact. Its two ends are written under
    # it, in volts and in nanometres.
    # On either (v75): CLICK anywhere on the bar and the knob goes there,
    # and the piezo after it; DRAG the knob, or the bar from where you
    # clicked, and the piezo follows it as it moves. Nothing waits for the
    # mouse to let go. The piezo keeps the rules of every move made by hand
    # (the worker's cmd_follow): away from the surface at once, toward it at
    # the speed in the box beside Approach, stopping at contact. So the knob
    # can be ahead of the piezo: its label is then orange and a red mark on
    # the strip above the bar shows where the piezo is. When the piezo is
    # there, or was stopped, the knobs are on the piezo again.
    ttk.Label(pb, text="coarse: the whole range (V).  Click on a bar or drag: "
                       "the piezo goes there",
              font=("Arial", 9)).grid(
        row=4, column=0, columnspan=3, sticky="w", padx=4, pady=(4, 0))
    coarse_strip, coarse_knob, coarse_mark = knob_strip(5)
    scale = tk.Scale(pb, from_=lo_v, to=hi_v, orient="horizontal",
                     variable=slider_var, command=on_slide, length=px(360),
                     resolution=0.001, bigincrement=0.1, tickinterval=1.0,
                     showvalue=False, sliderlength=px(26), width=px(18),
                     font=("Arial", 9))
    scale.grid(row=6, column=0, columnspan=3, sticky="ew", padx=4)
    ff = ttk.Frame(pb)
    ff.grid(row=7, column=0, columnspan=3, sticky="w", padx=4, pady=(3, 0))
    ttk.Label(ff, text="fine: +/-", font=("Arial", 9)).pack(side="left")
    ttk.Entry(ff, textvariable=fine_half_var, width=5).pack(side="left", padx=2)
    ttk.Label(ff, text="V around the piezo (after Approach: around the contact)",
              font=("Arial", 9)).pack(side="left")
    fine_strip, fine_knob, fine_mark = knob_strip(8)
    fine = tk.Scale(pb, from_=lo_v, to=hi_v, orient="horizontal",
                    variable=fine_var, command=on_slide, length=px(360),
                    resolution=0.0001, bigincrement=0.01, showvalue=False,
                    sliderlength=px(26), width=px(18), font=("Arial", 9))
    fine.grid(row=9, column=0, columnspan=3, sticky="ew", padx=4)
    knobs = ((scale, slider_var, coarse_strip, coarse_knob, coarse_mark, 3),
             (fine, fine_var, fine_strip, fine_knob, fine_mark, 4))
    # The two ends of the fine window, written out in volts and nanometres
    # (Tk's own tick labels round 7.45 to "7.5", and know no nanometres).
    fl = ttk.Frame(pb)
    fl.grid(row=10, column=0, columnspan=3, sticky="ew", padx=6)
    fine_lo_lbl = ttk.Label(fl, text="", font=("Arial", 9))
    fine_lo_lbl.pack(side="left")
    fine_hi_lbl = ttk.Label(fl, text="", font=("Arial", 9))
    fine_hi_lbl.pack(side="right")

    def slide_over() -> bool:
        """Has a slider's move ended (the piezo got there, or was stopped)?
        Then the knobs belong to the piezo again, whatever the mouse does
        until it next goes down."""
        if slide["target"] is not None and not worker.following:
            slide.update(dragging=False, which=None, target=None)
            return True
        return False

    def set_fine_window(volts: float | None = None):
        """Put the fine slider's window around ``volts`` (default: where
        the piezo is, or where a slider has asked it to go) and its knob on
        it. Always: while the "fine: +/-" box holds nothing usable (it is
        being typed in), the last usable width stays, so the knob is never
        left where the piezo is not."""
        try:
            half = abs(float(fine_half_var.get()))
        except ValueError:
            half = float("nan")
        if 0.001 <= half <= hi_v - lo_v:
            slide["half"] = half
        if volts is None:
            slide_over()
            v = rig.piezo_v if slide["target"] is None else slide["target"]
        else:
            v = float(volts)
        window = fine_window(v, slide["half"], lo_v, hi_v)
        if slide["window"] != window:
            slide["window"] = window
            fine.config(from_=window[0], to=window[1])
        fine_var.set(min(max(v, window[0]), window[1]))
        # The ends in nanometres change with the driver's mode, not only
        # with the window: written afresh every time.
        fine_lo_lbl.config(
            text=f"{window[0]:g} V = {C.piezo_volts_to_nm(window[0]):.0f} nm")
        fine_hi_lbl.config(
            text=f"{window[1]:g} V = {C.piezo_volts_to_nm(window[1]):.0f} nm")
        show_knobs()

    def on_fine_half(*_a):
        if slide["which"] is not fine:             # never under a held mouse
            set_fine_window()
    fine_half_var.trace_add("write", on_fine_half)

    def put_knobs(volts: float, held=None):
        """Both knobs on ``volts``: where the piezo is or, during a slider's
        move, where the slider has asked it to go. The fine window walks
        along when ``volts`` nears one of its ends. ``held`` is the slider
        under the mouse: its knob and its window are the hand's."""
        if held is not scale:
            slider_var.set(volts)
        if held is not fine:
            low, high = slide["window"] or (lo_v, hi_v)
            edge = 0.1 * (high - low)
            if low + edge <= volts <= high - edge:
                fine_var.set(volts)
            else:
                set_fine_window(volts)
        on_slide(volts)

    def set_speed(*_a):
        """How fast a move toward the surface made by hand goes."""
        try:
            speed = float(speed_var.get())
        except ValueError:
            return
        if 1.0 <= speed <= 5000.0:
            worker.hand_speed_nm_s = speed
    speed_var.trace_add("write", set_speed)

    def sliders_free() -> bool:
        """May a slider take the piezo? Yes while nothing but the idle
        sampling, or the sliders' own move, is running or waiting."""
        mine = QUIET + ("follow",)
        return ((not worker.busy or worker.current in mine)
                and all(c[0] in mine for c in list(worker.commands.queue)))

    def volts_under(widget, e) -> float:
        """The volts a slider would stand on with its knob's middle under
        the mouse: on the slider's own steps, inside its range."""
        return float(widget.tk.call(widget._w, "get", int(e.x), int(e.y)))

    def pressed(widget, var):
        def on_press(e):
            # The mouse goes down. On the knob: the knob stays where it is
            # and is held where it was taken. Anywhere else on the bar: the
            # knob goes under the mouse, and the piezo after it.
            if not sliders_free():
                set_status("busy: wait for the current command to finish, "
                           "or press Stop")
                return "break"
            # With no slider move under way the knobs ARE the piezo: put
            # them exactly on it before this press is read (they are
            # refreshed a few times a second, and a press on a knob that is
            # a moment behind must not send the piezo back to where it was).
            if slide_over():
                put_knobs(rig.piezo_v)
                set_fine_window()
            elif slide["target"] is None:
                put_knobs(rig.piezo_v)
            part = str(widget.identify(e.x, e.y))
            if part not in ("slider", "trough1", "trough2"):
                return "break"                     # beside the bar: nothing
            under = volts_under(widget, e)
            if part == "slider":
                # the knob's own place, not the piezo's: the two differ
                # while an earlier move is still on its way
                target = float(var.get())
                slide["grab"] = under - target
            else:
                target, slide["grab"] = under, 0.0
                var.set(target)
            slide["dragging"], slide["which"] = True, widget
            worker.follow_begin(target)
            slide["target"] = target
            put_knobs(target, held=widget)
            return "break"
        return on_press

    def dragged(widget, var):
        def on_drag(e):
            if not slide["dragging"] or slide["which"] is not widget:
                return "break"
            low, high = float(widget.cget("from")), float(widget.cget("to"))
            target = min(max(volts_under(widget, e) - slide["grab"], low), high)
            if not worker.follow_to(target):
                slide_over()                       # Stop ended it: the drag is over
                put_knobs(rig.piezo_v)
                set_fine_window()
                return "break"
            var.set(target)
            slide["target"] = target
            put_knobs(target, held=widget)
            return "break"
        return on_drag

    def released(widget):
        def on_release(_e):
            if slide["dragging"] and slide["which"] is widget:
                slide["dragging"], slide["which"] = False, None
                worker.follow_end()
                # the knob stays where it was left until the piezo is there
                on_slide()
            return "break"
        return on_release
    for widget, var in ((scale, slider_var), (fine, fine_var)):
        widget.bind("<ButtonPress-1>", pressed(widget, var))
        widget.bind("<B1-Motion>", dragged(widget, var))
        widget.bind("<ButtonRelease-1>", released(widget))
        # Tk's own Control-click sends a scale's knob to the END of its
        # range, and its middle button moves the knob without us: not here.
        for event in ("<Control-ButtonPress-1>", "<ButtonPress-2>", "<B2-Motion>",
                      "<ButtonRelease-2>"):
            widget.bind(event, lambda _e: "break")
        # The knob's label is placed by the knob's pixels: again whenever
        # the slider is laid out anew.
        widget.bind("<Configure>", show_knobs, add="+")
    set_fine_window()
    piezo_label()

    rof = ttk.Frame(pb)
    rof.grid(row=11, column=0, columnspan=3, sticky="ew", padx=2, pady=(3, 1))
    big: dict[str, tk.Label] = {}
    cells = [("i", "I (uA)"), ("v", "V (mV)"), ("p", "Piezo (V)"), ("s", "Sense (V)")]
    if has_ch2:
        # Channel 2 of the amplifier, in nA; the word RAILED, in red, while
        # its output is saturated (where it sits whenever the junction is
        # closed, at a bias and gain that rail it).
        cells.insert(1, ("i2", "I ch 2 (nA)"))
    for col, (key, title) in enumerate(cells):
        cell = ttk.Frame(rof, relief="groove", borderwidth=1)
        cell.grid(row=0, column=col, padx=2, sticky="ew")
        rof.columnconfigure(col, weight=1)
        ttk.Label(cell, text=title, font=("Arial", 9)).pack()
        big[key] = tk.Label(cell, text="--", font=("Courier", 12, "bold"), width=9)
        big[key].pack()
    bkgd_var = tk.BooleanVar(value=True)
    beep_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(pb, text="background sampling while idle (Igor: Beep is ON)",
                    variable=bkgd_var).grid(row=12, column=0, columnspan=2,
                                            sticky="w", padx=2)
    ttk.Checkbutton(pb, text="beep at the contact current",
                    variable=beep_var).grid(row=12, column=2, sticky="w", padx=2)

    def show_big(i_ua, v_mv, piezo_v, sense_v, beep_ok: bool = False, ch2=None):
        big["i"].config(text=f"{i_ua:9.4f}" if np.isfinite(i_ua) else "--")
        if has_ch2:
            if not cfg.channels.two_current_channels:
                big["i2"].config(text="off", fg="#6a6a6a")
            elif ch2 is None:
                big["i2"].config(text="--", fg="#202020")
            elif ch2["railed"]:
                big["i2"].config(text="RAILED", fg="#b00000")   # saturated: no number
            else:
                big["i2"].config(text=f"{ch2['amps'] * 1e9:9.3f}", fg="#202020")
        big["v"].config(text=f"{v_mv:8.2f}" if np.isfinite(v_mv) else "--")
        big["p"].config(text=f"{piezo_v:7.4f}")
        big["s"].config(text=f"{sense_v:7.4f}" if sense_v is not None else "none")
        slide_over()
        if slide["target"] is None:
            put_knobs(piezo_v)                  # both sliders follow every move
        else:
            show_knobs()                        # a slider is ahead: the mark follows
        touching = np.isfinite(i_ua) and abs(i_ua) > contact["ua"]
        contact_lbl.config(text=" CONTACT " if touching else "  OPEN  ",
                           bg="#b00000" if touching else "#6a6a6a")
        if beep_ok and beep_var.get() and touching:
            root.bell()

    # The rest of the column is tabbed, as Igor's panel was, so that the
    # boxes above stay in view on a 900-pixel screen: Settings and Saving.
    style.configure("Big.TNotebook.Tab", font=("Arial", 11, "bold"), padding=(14, 4))
    nb = ttk.Notebook(left, style="Big.TNotebook")
    nb.pack(fill="both", expand=True)

    # -- settings --------------------------------------------------------------------
    # Two columns of (label, entry); "smash every" lives in the Run box.
    sb = ttk.Frame(nb)
    nb.add(sb, text="Settings")

    # The current amplifier: how many of its outputs are read, and the gain
    # of each. On a rig with a two-output amplifier (the config names
    # channel 2's input) the box stands in the left column in the Keithley
    # box's place, above Coarse approach: there it is in view when the
    # window opens, which the tabs are not on a laptop screen. On a
    # one-channel rig it is the first box of this tab, as it was.
    # One channel is the amplifier as it
    # always was. Two: channel 1 (the config's ai_current) is the
    # lower-gain output that follows the junction through contact, and
    # contact is judged on it; channel 2 (ai_current_2) is the higher-gain
    # output, recorded with every trace, drawn in red beside channel 1's
    # blue, and the one the Break threshold is judged on (the junction
    # open). The gains are typed in: they tell the arithmetic
    # what the amplifier is set to and program nothing. They are settings
    # like the others: checked as typed, applied on Enter or Apply.
    amp = ttk.LabelFrame(left if has_ch2 else sb, text="Current amplifier")
    if has_ch2:
        amp.pack(fill="x", pady=(0, 3), before=ab)
    else:
        amp.grid(row=0, column=0, columnspan=4, sticky="ew", padx=4, pady=(4, 2))
    ch_var = tk.IntVar(value=2 if cfg.channels.two_current_channels else 1)

    def on_channels():
        want = ch_var.get()
        if not hand_move("current_channels", want):
            ch_var.set(2 if cfg.channels.two_current_channels else 1)
    one_rb = ttk.Radiobutton(amp, text="one channel", value=1, variable=ch_var,
                             command=on_channels)
    one_rb.grid(row=0, column=0, sticky="w", padx=(6, 2), pady=1)
    two_rb = ttk.Radiobutton(amp, text="two channels", value=2, variable=ch_var,
                             command=on_channels)
    two_rb.grid(row=0, column=1, sticky="w", padx=(6, 2), pady=1)
    amp_lbl = tk.Label(amp, text="", font=("Arial", 9), anchor="w", fg="#444")
    amp_lbl.grid(row=0, column=2, columnspan=3, sticky="w", padx=6)
    gain_entries = {}
    for col, path in enumerate(AMPLIFIER_SETTINGS):
        ttk.Label(amp, text=f"Gain ch {col + 1} (V/A)", font=("Arial", 9)).grid(
            row=1, column=col * 2, sticky="w", padx=(6, 2), pady=1)
        var = svars.setdefault(path, tk.StringVar(value=f"{_get(cfg, path):g}"))
        ent = ttk.Entry(amp, textvariable=var, width=9)
        ent.grid(row=1, column=col * 2 + 1, padx=2, pady=1, sticky="w")
        ent.bind("<Return>", lambda _e: apply_settings())
        ent.bind("<FocusOut>", lambda _e: apply_settings())
        gain_entries[path] = ent
    # Which way round each output is (cal.current_sign, cal.current_sign_2).
    # Ticked: the current of that channel is -(V - zero) / gain. For an
    # amplifier whose output goes negative at a positive bias, which gives
    # a negative conductance, no logarithm, and an empty trace panel.
    flip_vars = {ch: tk.BooleanVar(value=cfg.cal.sign_of(ch) < 0) for ch in (1, 2)}
    flip_boxes = {}

    def on_flip(channel: int):
        want = -1.0 if flip_vars[channel].get() else 1.0
        if not hand_move("current_sign", channel, want):
            flip_vars[channel].set(cfg.cal.sign_of(channel) < 0)
    for col, channel in enumerate((1, 2)):
        box = ttk.Checkbutton(amp, text=f"flip the sign of ch {channel}",
                              variable=flip_vars[channel],
                              command=lambda c=channel: on_flip(c))
        box.grid(row=2, column=col * 2, columnspan=2, sticky="w", padx=(6, 2),
                 pady=(0, 1))
        flip_boxes[channel] = box
    ttk.Label(amp, text="ch 1: the lower-gain output; contact is judged on it. "
                        "ch 2: the higher-gain output; the Break threshold (junction "
                        "open) is judged on it. Both are drawn, ch 1 blue and ch 2 "
                        "red; ch 2 only where its output is not saturated. A gain "
                        "says what the amplifier is "
                        "set to (1e4, 1e7 ...); it programs nothing. Flip the sign "
                        "of a channel whose current reads NEGATIVE at a positive "
                        "bias: an amplifier whose output is the other way round "
                        "from the Keithley's.",
              font=("Arial", 9), foreground="#444", wraplength=px(540),
              justify="left").grid(row=3, column=0, columnspan=5, sticky="w",
                                   padx=6, pady=(0, 2))

    def show_amplifier(p: dict):
        """The box as the rig is: which count is selected, whether two can
        be (the config must name channel 2's input), the inputs, and
        channel 2's gain greyed while it is not read."""
        ch_var.set(p["channels"])
        two_rb.config(state="normal" if p["available"] else "disabled")
        gain_entries[AMPLIFIER_SETTINGS[1]].config(
            state="normal" if p["channels"] == 2 else "disabled")
        flip_vars[1].set(p["sign1"] < 0)
        flip_vars[2].set(p["sign2"] < 0)
        flip_boxes[2].config(state="normal" if p["channels"] == 2 else "disabled")
        if not p["available"]:
            amp_lbl.config(text=f'ch 1 on {p["ch1"]}; for two, name "ai_current_2" '
                                "in the config's channels")
        elif p["channels"] == 2:
            amp_lbl.config(text=f"ch 1 on {p['ch1']}, ch 2 on {p['ch2']}")
        else:
            amp_lbl.config(text=f"ch 1 on {p['ch1']} (ch 2 on {p['ch2']}: not read)")
        sync_gain_boxes()

    def sync_gain_boxes():
        """The two gain entries follow the config, which the Keithley box's
        Set changes too (it programs the 428 and is channel 1's gain)."""
        for path in AMPLIFIER_SETTINGS:
            value = _get(cfg, path)
            if applied["values"].get(path) != value:
                applied["values"][path] = value
                svars[path].set(f"{value:g}")

    shown = [row for row in SETTINGS if row[0] != "ramp.smash_every"
             and row[0] not in AMPLIFIER_SETTINGS]
    per_col = (len(shown) + 1) // 2
    for i, (path, label, igor, unit, kind, scale_) in enumerate(shown):
        r, c = 1 + i % per_col, (i // per_col) * 2
        ttk.Label(sb, text=f"{label} ({unit})" if unit else label,
                  font=("Arial", 9)).grid(row=r, column=c, sticky="w", padx=(6, 2),
                                          pady=1)
        value = _get(cfg, path) * scale_
        var = svars.setdefault(path, tk.StringVar(value=f"{value:g}"))
        ent = ttk.Entry(sb, textvariable=var, width=9)
        ent.grid(row=r, column=c + 1, padx=2, pady=1, sticky="w")
        ent.bind("<Return>", lambda _e: apply_settings())
        ent.bind("<FocusOut>", lambda _e: apply_settings())
    ttk.Button(sb, text="Apply", command=lambda: apply_settings()).grid(
        row=per_col + 1, column=0, sticky="w", padx=6, pady=(6, 0))
    # How the two record inputs are wired, switched live: the card says
    # which modes it has (the worker asks it at start-up). RSE for a BNC
    # whose centre goes to the AI+ terminal and whose shield goes to AI GND
    # or nowhere; differential for centre to AI+ and shield to AI-.
    MODE_WORDS = {"default": "card default", "rse": "RSE (single-ended)",
                  "nrse": "NRSE", "diff": "differential"}
    mode_frame = ttk.Frame(sb)
    mode_frame.grid(row=per_col + 2, column=0, columnspan=4, sticky="w", padx=6,
                    pady=(4, 0))
    ttk.Label(mode_frame, text="Input mode (how the inputs on this card are wired)").pack(
        side="left")
    ai_mode_var = tk.StringVar(value=MODE_WORDS.get(cfg.channels.ai_terminal.lower(),
                                                    cfg.channels.ai_terminal))
    ai_mode_box = ttk.Combobox(mode_frame, textvariable=ai_mode_var, width=18,
                               state="readonly", values=tuple(MODE_WORDS.values()))
    ai_mode_box.pack(side="left", padx=4)

    def on_ai_mode(_e=None):
        name = next((k for k, v in MODE_WORDS.items() if v == ai_mode_var.get()),
                    "default")
        worker.send("ai_terminal", name)
    ai_mode_box.bind("<<ComboboxSelected>>", on_ai_mode)

    def show_ai_modes(p: dict):
        ai_mode_box.config(values=tuple(MODE_WORDS[m] for m in p["modes"]
                                        if m in MODE_WORDS))
        ai_mode_var.set(MODE_WORDS.get(p["current"], p["current"]))
    # The safety check, in its own box and large. Every value is tried on a
    # copy of the config as it is typed -- green when it would be accepted,
    # red with the reason when not -- and applied on Enter, Apply or
    # leaving the box.
    cb = ttk.LabelFrame(sb, text="Safety check")
    cb.grid(row=per_col + 3, column=0, columnspan=4, sticky="ew", padx=4,
            pady=(8, 2))
    smsg = tk.Label(cb, text="all settings as loaded", font=("Arial", 11, "bold"),
                    wraplength=px(540), justify="left", anchor="w", fg="#006000")
    smsg.pack(fill="x", padx=6, pady=(2, 0))
    ttk.Label(cb, text="Every change is checked against the safety rules before "
                       "it applies (Enter, Apply, or leaving the box). An "
                       "accepted change starts a new file.",
              font=("Arial", 9), foreground="#444", wraplength=px(540),
              justify="left").pack(fill="x", padx=6, pady=(0, 4))
    applied = {"values": {path: _get(cfg, path) for path, *_ in SETTINGS}}

    scales = {path: scale_ for path, *_rest, scale_ in SETTINGS}
    labels = {path: label for path, label, *_rest in SETTINGS}
    sb.columnconfigure(3, weight=1)            # the check box spans the tab

    def pending_changes():
        """The typed values that differ from what is applied, as
        {config path: value}, or (None, message) when a box is not a number."""
        changes = {}
        for path, label, igor, unit, kind, scale_ in SETTINGS:
            raw = svars[path].get().strip()
            try:
                number = float(raw) / scale_
            except ValueError:
                return None, f"{label}: '{raw}' is not a number"
            value = int(round(number)) if kind is int else number
            if value != applied["values"][path]:
                changes[path] = value
        return changes, ""

    def verdict(text: str, fg: str) -> None:
        """The Safety check box and the Status box say the same thing."""
        smsg.config(text=text, fg=fg)
        set_status("Safety check: " + text,
                   {"#b00000": "bad", "#b06000": "warn"}.get(fg, "ok"))

    def preview_settings(*_args):
        """The verdict as you type, without applying anything."""
        changes, bad = pending_changes()
        if bad:
            verdict(bad, "#b00000")
            return
        if not changes:
            return                     # nothing pending: keep the last verdict
        problems, warnings = check_settings(cfg, changes)
        names = ", ".join(labels[p] for p in changes)
        if problems:
            verdict("REFUSED: " + "; ".join(problems), "#b00000")
        elif warnings:
            verdict(f"{names}: allowed, with a warning: " + " | ".join(warnings)
                    + "  (Enter or Apply to use it)", "#b06000")
        else:
            verdict(f"{names}: OK, within the safety rules (Enter or Apply to "
                    "use it)", "#006000")

    def apply_settings() -> bool:
        changes, bad = pending_changes()
        if bad:
            verdict(bad, "#b00000")
            return False
        if not changes:
            return True
        problems, warnings = check_settings(cfg, changes)
        if problems:
            for path in changes:                   # put the boxes back
                svars[path].set(f"{applied['values'][path] * scales[path]:g}")
            verdict("REFUSED: " + "; ".join(problems), "#b00000")
            return False
        for path, value in changes.items():
            _set(cfg, path, value)
            applied["values"][path] = value
        if "cal.preamp_gain_v_per_a" in changes:
            # Channel 1's gain is the gain the Keithley box shows as an
            # exponent: keep the two in step (a whole decade only).
            follow_gain(cfg)
            worker.k_state["gain"] = cfg.keithley.gain_exponent
            gain_var.set(str(cfg.keithley.gain_exponent))
        worker.send("newfile")                     # the config travels with the data
        if "ramp.bias_v" in changes:
            # Put the new bias on the output now, so the readout and the
            # junction show it at once rather than at the next move.
            worker.bias_dirty = True
            worker.send("bias")
        names = ", ".join(labels[p] for p in changes)
        if warnings:
            verdict(f"applied {names}; warning: " + " | ".join(warnings), "#b06000")
        else:
            verdict(f"applied {names}", "#006000")
        return True

    for var in svars.values():
        var.trace_add("write", preview_settings)

    # -- saving: Igor's scheme, one experiment per Start N ---------------------------
    # <data folder>/MM_DD<SetupID>YYMerge/PullOut*Block_k.ibw, 100 traces to a
    # block, numbered through the day (igor_scheme); the raw .h5, the .txt
    # and experiment_log.csv beside them. Everything typed here is
    # remembered between launches.
    fb = ttk.Frame(nb)
    nb.add(fb, text="Saving")
    remembered = dict(DEFAULT_SAVING, **load_saving(saving_file))
    if setup_id is not None:
        remembered["setup_id"] = setup_id
    folder_var = tk.StringVar(value=str(remembered.get("folder") or out_dir))
    setup_var = tk.StringVar(value=str(remembered.get("setup_id") or "_"))
    name_var = tk.StringVar(value=remembered.get("name", ""))
    exp_var = tk.StringVar(value=remembered.get("experiment", ""))
    notes_var = tk.StringVar(value=remembered.get("notes", ""))
    h5_var = tk.BooleanVar(value=bool(remembered.get("h5", True)))
    txt_var = tk.BooleanVar(value=bool(remembered.get("txt", False)))
    flag_vars = {key: tk.BooleanVar(value=bool(remembered.get(key, DEFAULT_SAVING[key])))
                 for key in IGOR_FLAG_KEYS}

    ttk.Label(fb, text="Data folder").grid(row=0, column=0, sticky="w", padx=2, pady=(4, 1))
    ttk.Entry(fb, textvariable=folder_var, width=36).grid(
        row=0, column=1, sticky="ew", padx=2, pady=(4, 1))

    def browse_folder():
        chosen = filedialog.askdirectory(initialdir=folder_var.get() or str(out_dir),
                                         title="data folder (Igor's day folder "
                                               "MM_DD_YYMerge is made under it)")
        if chosen:
            folder_var.set(chosen)
    ttk.Button(fb, text="Browse...", command=browse_folder).grid(
        row=0, column=2, padx=2, pady=(4, 1), sticky="ew")
    ttk.Label(fb, text="Setup ID").grid(row=1, column=0, sticky="w", padx=2, pady=1)
    sf = ttk.Frame(fb)
    sf.grid(row=1, column=1, columnspan=2, sticky="ew", padx=2)
    ttk.Entry(sf, textvariable=setup_var, width=6).pack(side="left")
    ttk.Label(sf, text="Igor's SetupID: the letters between the day and the year of "
                       "the folder name ('_' gives 10_22_26Merge)",
              font=("Arial", 9), foreground="#444").pack(side="left", padx=6)
    ttk.Label(fb, text="Your name").grid(row=2, column=0, sticky="w", padx=2, pady=1)
    ttk.Entry(fb, textvariable=name_var, width=36).grid(row=2, column=1, sticky="ew", padx=2)
    ttk.Label(fb, text="Experiment").grid(row=3, column=0, sticky="w", padx=2, pady=1)
    ttk.Entry(fb, textvariable=exp_var, width=36).grid(row=3, column=1, sticky="ew", padx=2)
    ttk.Label(fb, text="Notes").grid(row=4, column=0, sticky="w", padx=2, pady=1)
    ttk.Entry(fb, textvariable=notes_var, width=36).grid(
        row=4, column=1, columnspan=2, sticky="ew", padx=2)
    ttk.Label(fb, text="experiment: e.g. clean_gold, OPE3_1mM, changed any time, the "
                       "next Start N uses it (it names the .h5 and goes into the Igor "
                       "block's note). Notes: molecule, solvent, tip, sample; they go "
                       "into the .h5 header and into experiment_log.csv in the day "
                       "folder, one row per run",
              font=("Arial", 9), foreground="#444", wraplength=px(560), justify="left").grid(
        row=5, column=0, columnspan=3, sticky="w", padx=2)

    ff = ttk.LabelFrame(fb, text="Igor files per block of 100 traces "
                                 "(PullOutConductanceBlock_k always; these as ticked)")
    ff.grid(row=6, column=0, columnspan=3, sticky="ew", padx=2, pady=(6, 0))
    for col, (key, text) in enumerate((("bias", "Save Bias (Voltage block, V)"),
                                       ("current", "Save Current (A)"),
                                       ("sense", "Save Sense (Extension block, nm)"),
                                       ("hist", "Save Hist (block histogram)"),
                                       ("piezo_wave", "Save Piezo wave (the ramp, V)"))):
        ttk.Checkbutton(ff, text=text, variable=flag_vars[key]).grid(
            row=col // 3, column=col % 3, sticky="w", padx=4, pady=1)
    ttk.Checkbutton(fb, text="also keep the raw .h5 session (recommended: raw volts + "
                             "config, so a re-measured gain reprocesses the file)",
                    variable=h5_var).grid(row=7, column=0, columnspan=3,
                                          sticky="w", padx=2, pady=(4, 0))
    ttk.Checkbutton(fb, text="also write a .txt table when the run ends "
                             "(nm, then one G/G0 column per trace)",
                    variable=txt_var).grid(row=8, column=0, columnspan=3,
                                           sticky="w", padx=2)
    next_lbl = tk.Label(fb, text="", font=("Arial", 9), anchor="w", justify="left",
                        wraplength=px(560))
    next_lbl.grid(row=9, column=0, columnspan=3, sticky="w", padx=2, pady=(4, 0))
    file_lbl = tk.Label(fb, text="no run in progress", font=("Arial", 9), anchor="w",
                        wraplength=px(560), justify="left")
    file_lbl.grid(row=10, column=0, columnspan=3, sticky="w", padx=2)
    igor_next = {"n": None}                    # Igor's Saved, as read from the folder

    def saving_now() -> dict:
        sv = {"folder": Path(folder_var.get().strip() or str(out_dir)),
              "setup_id": setup_var.get().strip() or "_",
              "name": name_var.get(), "experiment": exp_var.get(),
              "notes": notes_var.get(), "h5": h5_var.get(), "txt": txt_var.get()}
        sv.update({key: var.get() for key, var in flag_vars.items()})
        return sv

    def show_next():
        """The line under the boxes: the day folder the next trace goes to
        and the number it gets, read from the block files already there
        (igor_scheme's scan); while a run is going the worker's own count
        takes over (the readout event)."""
        worker.saving.update(saving_now())
        folder = worker.day_folder()
        try:
            igor_next["n"] = next_trace_number(folder)
            word = str(igor_next["n"])
        except Exception as exc:                 # noqa: BLE001  (igor2 missing, a half-written file)
            igor_next["n"] = None
            word = f"? ({exc})"
        extras = [k for k, on in (("h5", h5_var.get()), ("txt", txt_var.get())) if on]
        next_lbl.config(text=f"Igor folder: {folder}   next trace (Saved): {word}"
                             + (f"   (+ .{' + .'.join(extras)} beside the Igor files)"
                                if extras else ""))

    pending_scan = {"id": None}

    def schedule_show_next(*_a):
        """A keystroke in the folder box must not read a 4 MB block each
        time: the scan runs 300 ms after the last change."""
        if pending_scan["id"] is not None:
            root.after_cancel(pending_scan["id"])
        pending_scan["id"] = root.after(300, lambda: (pending_scan.update(id=None),
                                                      show_next()))
    for var in (folder_var, setup_var, name_var, exp_var, notes_var, h5_var, txt_var,
                *flag_vars.values()):
        var.trace_add("write", schedule_show_next)
    show_next()

    # -- saved data, at the bottom of the Saving tab -----------------------------------
    bb = ttk.LabelFrame(fb, text="Saved data: browse traces, plot histograms (.h5 session, "
                                 "Igor day folder, or one PullOutConductanceBlock_k.ibw)")
    bb.grid(row=11, column=0, columnspan=3, sticky="ew", padx=2, pady=(6, 2))
    browse = {"session": None, "path": None, "n": 0, "hist": None}
    idx_var = tk.StringVar(value="1")          # traces count from 1, as plot.py's -1

    def open_saved(path: str):
        """Open saved data for browsing: a .h5 session of this program, an
        Igor day folder (Igor's own or this program's), or one block file
        (IgorDay)."""
        p = Path(path)
        writer = worker.writer
        if (writer is not None and p.suffix.lower() == ".h5"
                and p.resolve() == Path(writer.path).resolve()):
            set_status("that file is still being written (a run is in "
                       "progress or paused); open it when the run has ended")
            return
        if browse["session"] is not None:
            browse["session"].close()
            browse.update(session=None, path=None, n=0, hist=None)
        try:
            if p.is_dir() or p.suffix.lower() == ".ibw":
                set_status(f"reading {p.name} ...", level="busy")
                root.update_idletasks()
                s = IgorDay(p)
            else:
                s = storage.Session(p)
        except Exception as exc:                 # noqa: BLE001
            set_status(f"could not open {p.name}: {exc}")
            return
        if len(s) == 0:
            s.close()
            set_status(f"{p.name} holds no traces")
            blbl.config(text=f"{p.name}: 0 traces")
            return
        browse.update(session=s, path=str(p), n=len(s), hist=None)
        idx_var.set("1")
        blbl.config(text=f"{p.name}: {len(s)} traces"
                         + (f" ({s.describe()})" if isinstance(s, IgorDay) else ""))
        if (isinstance(s, IgorDay) and worker.igor is not None
                and s.folder.resolve() == worker.igor.folder.resolve()):
            set_status("this is today's folder: traces saved from now on are not "
                       "shown until you open it again", level="warn")
        else:
            set_status(f"opened {p.name}: {len(s)} traces", level="ok")
        show_saved()

    def open_file():
        path = filedialog.askopenfilename(
            initialdir=folder_var.get() or str(out_dir),
            filetypes=[("session or Igor block", "*.h5 *.ibw"), ("session", "*.h5"),
                       ("Igor block", "*.ibw")])
        if path:
            open_saved(path)

    def open_folder():
        path = filedialog.askdirectory(initialdir=folder_var.get() or str(out_dir),
                                       title="an Igor day folder, e.g. 10_22_26Merge")
        if path:
            open_saved(path)

    def show_saved(delta: int = 0):
        s = browse["session"]
        if s is None or browse["n"] == 0:
            return
        try:
            i = int(idx_var.get()) + delta
        except ValueError:
            i = 1
        i = max(1, min(i, browse["n"]))
        idx_var.set(str(i))
        live["paused"] = True
        draw_saved(s, i - 1)

    ttk.Button(bb, text="Open .h5 / .ibw ...", command=open_file).grid(
        row=0, column=0, padx=2, pady=1, sticky="ew")
    ttk.Button(bb, text="<", width=3, command=lambda: show_saved(-1)).grid(
        row=0, column=1, padx=1)
    ttk.Entry(bb, textvariable=idx_var, width=6).grid(row=0, column=2, padx=1)
    ttk.Button(bb, text=">", width=3, command=lambda: show_saved(+1)).grid(
        row=0, column=3, padx=1)
    ttk.Button(bb, text="Show", command=lambda: show_saved(0)).grid(
        row=0, column=4, padx=2)
    ttk.Button(bb, text="Back to live",
               command=lambda: live.update(paused=False)).grid(
        row=0, column=5, padx=2, pady=1, sticky="ew")

    def save_png():
        s = browse["session"]
        if s is None:
            set_status("open saved data first")
            return
        try:
            number = int(idx_var.get())
            if isinstance(s, IgorDay):
                # The window's four panels as drawn for this trace, into
                # the folder, named by Igor's trace number.
                t = s.trace(max(1, min(number, len(s))) - 1)
                out = s.folder / f"{s.name}_trace{t['number']:04d}.png"
                fig.savefig(out, dpi=110)
            else:
                fig2, info = session_plots.trace_figure(browse["path"], number)
                out = Path(browse["path"]).with_name(
                    f"{Path(browse['path']).stem}_trace{info['number']:04d}.png")
                fig2.savefig(out, dpi=110)
        except Exception as exc:                 # noqa: BLE001
            set_status(f"PNG not written: {exc}")
            return
        set_status(f"wrote {out}")
    ttk.Button(bb, text="Open Igor day folder ...", command=open_folder).grid(
        row=1, column=0, padx=2, pady=1, sticky="ew")
    ttk.Button(bb, text="Save PNG of trace", command=save_png).grid(
        row=1, column=1, columnspan=3, padx=2, pady=1, sticky="ew")
    ttk.Button(bb, text="Plot 1D histogram",
               command=lambda: open_hist_window("1d")).grid(
        row=1, column=4, padx=2, pady=1, sticky="ew")
    ttk.Button(bb, text="Plot 2D histogram",
               command=lambda: open_hist_window("2d")).grid(
        row=1, column=5, padx=2, pady=1, sticky="ew")
    blbl = tk.Label(bb, text="", font=("Arial", 9), anchor="w", wraplength=px(560),
                    justify="left")
    blbl.grid(row=2, column=0, columnspan=6, sticky="w", padx=2)

    def open_hist_window(kind: str):
        s = browse["session"]
        if s is None:
            set_status("open saved data first (Open .h5 / .ibw ... or Open Igor "
                       "day folder ...)")
            return
        source = s
        if isinstance(s, IgorDay):
            set_status(f"reading every trace of {s.name} for the histogram ...",
                       level="busy")
            root.update_idletasks()
            try:
                source = s.data()
            except Exception as exc:             # noqa: BLE001
                set_status(f"could not read {s.name}: {exc}")
                return
        win = tk.Toplevel(root)
        _light_window(win)
        win.title(f"{Path(browse['path']).name}: "
                  + ("1D histogram" if kind == "1d" else "2D histogram"))
        hist_window(win, source, Path(browse["path"]).stem, kind, tk, ttk,
                    FigureCanvasTkAgg, Figure, status)

    # -- the plots --------------------------------------------------------------------
    # Four panels: the record, the trace with the readback over it, the
    # piezo in and out, the histogram.
    top = ttk.Frame(right)
    top.pack(fill="x")
    # Off by default, every panel redraws together once per trace, when the
    # pull is in; on, the record and piezo panels also redraw while a move
    # is running (the staircase grows as you watch).
    live_moving = tk.BooleanVar(value=False)
    ttk.Checkbutton(top, text="redraw while moving", variable=live_moving).pack(
        side="left", padx=(0, 3))
    # How the first two panels are drawn. Plot 1 (the record): |V| and |I|
    # on logarithmic axes, so a small current beside a large one is still a
    # line. Plot 2 (the trace): G/G0 itself on a linear axis, sign and all,
    # where the default is its logarithm. Both redraw what is on screen.
    log_iv = tk.BooleanVar(value=False)
    lin_g = tk.BooleanVar(value=False)
    def replot():
        """A check box changed what the panels carry: draw again, and fit
        the panels around their new labels."""
        live["layout_stale"] = True
        redraw_now()
    ttk.Checkbutton(top, text="plot 1: log I and V", variable=log_iv,
                    command=replot).pack(side="left", padx=(10, 3))
    ttk.Checkbutton(top, text="plot 2: linear G", variable=lin_g,
                    command=replot).pack(side="left", padx=(4, 3))
    banner = tk.Label(top, text="", font=("Arial", 9, "bold"), fg="#b06000")
    banner.pack(side="right")
    ttk.Button(top, text="Readback window",
               command=lambda: open_readback()).pack(side="right", padx=8)
    ttk.Button(top, text="Axis limits",
               command=lambda: open_limits()).pack(side="right", padx=4)
    ttk.Button(top, text="Monitor",
               command=lambda: open_monitor()).pack(side="right", padx=4)

    # -- the monitor window: the junction while nothing is commanded ------------
    # While it is open and the worker is idle, a quiet 10 ms hold is played
    # every 0.3 s at wherever the piezo and bias are, and the junction
    # voltage, the current and the conductance it read are added to three
    # strip charts. Nothing moves; it is the same read the readout box uses.
    from collections import deque
    mon_state: dict = {"win": None, "on": None, "last": 0.0,
                       "t": deque(maxlen=3000), "v": deque(maxlen=3000),
                       "i": deque(maxlen=3000), "g": deque(maxlen=3000),
                       # the sample-rate check: its tick box, when the last
                       # one was sent, how many came back, how to show one
                       "rate_on": None, "rate_last": 0.0, "rate_n": 0,
                       "rate_show": None}

    def monitor_wants_sample() -> bool:
        """Idle sampling runs for the Piezo box's readouts (its checkbox) or
        for an open Monitor window with its own box ticked."""
        if bkgd_var.get():
            return True
        win = mon_state["win"]
        return (win is not None and win.winfo_exists()
                and mon_state["on"] is not None and mon_state["on"].get())

    def rate_check_wanted() -> bool:
        """The Monitor window is open and its sample-rate box is ticked."""
        win = mon_state["win"]
        return (win is not None and win.winfo_exists()
                and mon_state["rate_on"] is not None and mon_state["rate_on"].get())

    def open_monitor():
        if mon_state["win"] is not None and mon_state["win"].winfo_exists():
            mon_state["win"].lift()
            return
        win = tk.Toplevel(root)
        _light_window(win)
        win.title("monitor: the junction while idle")
        mon_state["win"] = win
        mon_state["on"] = tk.BooleanVar(value=True)
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=8, pady=(6, 0))
        ttk.Checkbutton(bar, text="sample while idle (a 10 ms hold every 0.3 s; "
                                  "nothing moves)", variable=mon_state["on"]).pack(
            side="left")
        secs_var = tk.StringVar(value="30")
        ttk.Label(bar, text="seconds shown").pack(side="left", padx=(12, 2))
        ttk.Entry(bar, textvariable=secs_var, width=5).pack(side="left")

        # The sample-rate check (stmlab.ratecheck): is the card really
        # handing over the configured number of samples a second on every
        # input in use? While the box is ticked and the rig is idle the
        # worker holds the outputs where they are for one second, records,
        # counts the numbers through a scratch file (written, read back,
        # deleted), keeps that second as sampling_rate_test.csv in the
        # data folder and times the card against this PC's clock (a rough
        # cross-check); the result is shown here, and the line flashes,
        # once a second. The big line is the rate as counted.
        rate_box = ttk.LabelFrame(win, text="Sample-rate check")
        rate_box.pack(fill="x", padx=8, pady=(6, 0))
        mon_state["rate_on"] = tk.BooleanVar(value=False)
        ttk.Checkbutton(rate_box,
                        text="check the sample rate: record 1 s on every input in "
                             "use, again and again (nothing moves).\nThe last "
                             "second stays in the data folder as "
                             "sampling_rate_test.csv, to open in Excel",
                        variable=mon_state["rate_on"]).pack(anchor="w", padx=6,
                                                            pady=(2, 0))
        rate_big = tk.Label(rate_box, text="not checked yet: tick the box",
                            font=("Arial", 18, "bold"), anchor="w", fg="#444444")
        rate_big.pack(fill="x", padx=6, pady=(2, 0))
        rate_note = tk.Label(rate_box, text="", font=("Courier", 9), justify="left",
                             anchor="w")
        rate_note.pack(fill="x", padx=6, pady=(0, 4))
        rate_plain = rate_big.cget("bg")           # the colour between flashes

        def show_rate(p: dict):
            """One finished check: the headline, the lines, and a flash."""
            if not win.winfo_exists():
                return
            mon_state["rate_n"] += 1
            head, text = ratecheck.lines(p)
            good = bool(p.get("ok")) and not p.get("error")
            if p.get("error"):
                # The card refused: do not ask it again every second.
                mon_state["rate_on"].set(False)
                text = text + ["the box was unticked; tick it to try again"]
            rate_big.config(text=head, fg="#006000" if good else "#b00000")
            rate_note.config(text="\n".join(text + [f"check number {mon_state['rate_n']}"]))
            rate_big.config(bg="#ffe066")           # the flash: a new number is in
            win.after(250, lambda: rate_big.winfo_exists()
                      and rate_big.config(bg=rate_plain))
        mon_state["rate_show"] = show_rate

        fig3 = Figure(figsize=(7.0, 5.2), dpi=100)
        ax_v, ax_i, ax_g = fig3.subplots(3, 1, sharex=True)
        canvas3 = FigureCanvasTkAgg(fig3, master=win)
        canvas3.get_tk_widget().pack(fill="both", expand=True)
        note = ttk.Label(win, text="", font=("Courier", 9), justify="left")
        note.pack(fill="x", padx=8, pady=(0, 6))

        def refresh_monitor():
            if not win.winfo_exists():
                mon_state["win"] = None
                return
            try:
                secs = max(1.0, float(secs_var.get()))
            except ValueError:
                secs = 30.0
            if mon_state["t"]:
                t = np.array(mon_state["t"]); t = t - t[-1]
                keep = t >= -secs
                series = (("junction (mV)", ax_v, np.array(mon_state["v"])[keep], plots.C_V),
                          ("current (uA)", ax_i, np.array(mon_state["i"])[keep], plots.C_I),
                          ("log10 (G / G0)", ax_g, np.array(mon_state["g"])[keep], plots.C_G))
                for label, a_, y, colour in series:
                    a_.clear()
                    a_.plot(t[keep], y, color=colour, lw=0.9)
                    a_.set_ylabel(label, fontsize=8)
                    a_.tick_params(labelsize=8)
                    a_.grid(True, alpha=0.3)
                ax_g.set_xlabel("seconds ago", fontsize=8)
                ax_v.set_title("the junction while idle: every point is one 10 ms hold",
                               fontsize=9)
                fig3.tight_layout(pad=1.5)
                canvas3.draw_idle()
                v, i, g = (np.array(mon_state["v"])[keep], np.array(mon_state["i"])[keep],
                           np.array(mon_state["g"])[keep])
                note.config(text=f"last {secs:g} s: junction {v.mean():8.3f} mV "
                                 f"(rms {v.std():.3f}), current {i.mean():9.5f} uA "
                                 f"(rms {i.std():.5f}), G {10 ** np.nanmean(g):.3e} G0")
            win.after(300, refresh_monitor)

        refresh_monitor()

    # -- the readback-only window ----------------------------------------------------
    rb_state: dict = {"win": None}

    def open_readback():
        if rb_state["win"] is not None and rb_state["win"].winfo_exists():
            rb_state["win"].lift()
            return
        win = tk.Toplevel(root)
        _light_window(win)
        win.title("piezo readback: " + (cfg.channels.piezo_sense_path or "no sense line"))
        rb_state["win"] = win
        fig2 = Figure(figsize=(7.0, 3.8), dpi=100)
        ax_rb = fig2.add_subplot(111)
        fig2.tight_layout(pad=2.0)
        canvas2 = FigureCanvasTkAgg(fig2, master=win)
        canvas2.get_tk_widget().pack(fill="both", expand=True)
        note = ttk.Label(win, text="the sense line alone, this cycle, y axis "
                                   "fitted to the data; redraws while a move runs",
                         font=("Arial", 9))
        note.pack(fill="x", padx=8, pady=(0, 6))

        def refresh_rb():
            if not win.winfo_exists():
                rb_state["win"] = None
                return
            cyc = mon.snapshot()
            if cyc.t:
                plots.plot_readback(ax_rb, cfg, np.array(cyc.t), np.array(cyc.sense_v),
                                    marks=cyc.marks)
                fig2.tight_layout(pad=2.0)
                canvas2.draw_idle()
            win.after(300, refresh_rb)

        refresh_rb()

    fig = Figure(figsize=(10.5, 6.6), dpi=100)
    canvas = FigureCanvasTkAgg(fig, master=right)
    canvas.get_tk_widget().pack(fill="both", expand=True)

    live = {"paused": False, "cycle": None, "trace": None, "hist": None,
            "dirty": False}
    C = cfg.cal
    ax: dict = {}                      # panel name -> Axes, rebuilt on demand

    # -- axis limits, per panel ---------------------------------------------------
    # Each plot function picks its own limits; what is typed in the "Axis
    # limits" window overrides them after every redraw. Blank means "leave
    # the plot's own". y2 is the right-hand axis where a panel has one.
    PANELS = [  # key, label, x unit, y unit, right-y unit (None = no right axis)
        ("record", "record", "s", "junction mV", "current uA"),
        ("trace", "trace", "nm", "log10 G/G0", "readback nm"),   # both channels share y
        ("piezo", "piezo in/out", "s", "piezo nm", None),
        ("hist", "histogram", "log10 G/G0", "counts/trace", None),
    ]
    limits: dict = {}                  # key -> {"x": (lo, hi), "y": ..., "y2": ...}

    def apply_limits():
        for key, a_ in ax.items():
            lim = limits.get(key)
            if not lim:
                continue
            if lim.get("x"):
                a_.set_xlim(*lim["x"])
            if lim.get("y"):
                a_.set_ylim(*lim["y"])
            twin = getattr(a_, "_stm_twin", None)
            if lim.get("y2") and twin is not None:
                twin.set_ylim(*lim["y2"])

    lim_state: dict = {"win": None, "vars": {}}

    def open_limits():
        if lim_state["win"] is not None and lim_state["win"].winfo_exists():
            lim_state["win"].lift()
            return
        win = tk.Toplevel(root)
        _light_window(win)
        win.title("axis limits (blank = the plot's own)")
        lim_state["win"] = win
        grid_ = ttk.Frame(win)
        grid_.pack(padx=8, pady=8)
        for col, text in enumerate(("panel", "x from", "x to", "y from", "y to",
                                    "right y from", "right y to")):
            ttk.Label(grid_, text=text, font=("Arial", 9, "bold")).grid(
                row=0, column=col, padx=4, pady=(0, 4))
        vars_: dict = lim_state["vars"]
        for row, (key, label, xu, yu, y2u) in enumerate(PANELS, start=1):
            ttk.Label(grid_, text=f"{label}  (x: {xu}; y: {yu}"
                                  + (f"; right: {y2u})" if y2u else ")"),
                      font=("Arial", 9)).grid(row=row, column=0, sticky="w", padx=4)
            vars_.setdefault(key, {})
            for col, name in enumerate(("x0", "x1", "y0", "y1", "z0", "z1"), start=1):
                if name.startswith("z") and not y2u:
                    continue
                var = vars_[key].setdefault(name, tk.StringVar(value=""))
                ent = ttk.Entry(grid_, textvariable=var, width=8)
                ent.grid(row=row, column=col, padx=2, pady=1)
                ent.bind("<Return>", lambda _e: apply_from_window())
        msg = ttk.Label(win, text="", font=("Arial", 9))
        msg.pack(fill="x", padx=8)
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=8, pady=(4, 8))

        def pair(key, lo, hi):
            a, b = vars_[key][lo].get().strip(), vars_[key][hi].get().strip()
            if not a and not b:
                return None
            if not a or not b:
                raise ValueError(f"{key}: give both ends of the range or neither")
            lo_v, hi_v = float(a), float(b)
            if hi_v <= lo_v:
                raise ValueError(f"{key}: 'to' must be above 'from'")
            return (lo_v, hi_v)

        def apply_from_window():
            new: dict = {}
            try:
                for key, label, xu, yu, y2u in PANELS:
                    entry = {"x": pair(key, "x0", "x1"), "y": pair(key, "y0", "y1")}
                    if y2u:
                        entry["y2"] = pair(key, "z0", "z1")
                    if any(entry.values()):
                        new[key] = entry
            except ValueError as exc:
                msg.config(text=str(exc), foreground="#b00000")
                return
            limits.clear()
            limits.update(new)
            msg.config(text=f"applied to {len(new)} panel(s)" if new
                       else "all limits cleared", foreground="#006000")
            redraw_now()

        def clear_all():
            for d in vars_.values():
                for v in d.values():
                    v.set("")
            apply_from_window()

        ttk.Button(bar, text="Apply", command=apply_from_window).pack(side="left", padx=2)
        ttk.Button(bar, text="Clear all", command=clear_all).pack(side="left", padx=2)
        ttk.Label(bar, text="Return in any box applies too",
                  font=("Arial", 9)).pack(side="left", padx=8)

    def redraw_now():
        if live["paused"] and browse["session"] is not None:
            draw_saved(browse["session"], int(idx_var.get()) - 1)
        else:
            draw_live()

    def rebuild():
        """Lay the figure out: the four panels in two columns. Everything is
        redrawn into the new axes on the next poll (or at once while
        browsing)."""
        fig.clear()
        grid = fig.subplots(2, 2, squeeze=False)
        ax.clear()
        ax.update(record=grid[0, 0], trace=grid[0, 1],
                  piezo=grid[1, 0], hist=grid[1, 1])
        fig.tight_layout(pad=2.0, w_pad=3.0)   # room for the right-hand axes
        live["layout_stale"] = True            # and once more when there are labels
        if live["paused"] and browse["session"] is not None:
            draw_saved(browse["session"], int(idx_var.get()) - 1)
        else:
            live["dirty"] = True
            canvas.draw_idle()

    def relayout():
        """Fit the panels around their labels once more, after the first
        drawing of a layout and after a check box has changed the labels.
        The right-hand axes get their labels only when there is something
        to draw, which is after rebuild() laid the empty figure out; without
        this the current's label sits on the next panel's. Once per layout,
        so the panels do not shift from trace to trace."""
        if live.get("layout_stale") and ax["record"].lines and ax["trace"].lines:
            live["layout_stale"] = False
            # Tick labels and axis labels decide the layout. Titles and notes
            # written on a panel do not: they can be wider than the panel, and
            # the layout would shrink the panels to make room for them.
            for a_ in fig.axes:
                a_.title.set_in_layout(False)
                for words in a_.texts:
                    words.set_in_layout(False)
            try:
                fig.tight_layout(pad=2.0, w_pad=3.0)
            except Exception:                   # noqa: BLE001
                log.debug("tight_layout failed", exc_info=True)

    def cycle_frame(cyc, least: float = 1.2):
        """The default x range of the two panels that run against time, the
        record (plot 1) and the piezo (plot 3): the SAME for both, so the
        two line up. It is 0 to 1.2 s, and reaches to the end of the cycle
        when the cycle lasted longer, so that the pull, which comes last,
        is never cut off. The Axis limits window still overrides it."""
        last = 0.0
        for series in (cyc.t, cyc.rec_t, list(cyc.marks.values())):
            arr = np.asarray(series, dtype=float)
            if arr.size and np.isfinite(arr).any():
                last = max(last, float(np.nanmax(arr)))
        return (0.0, least if last <= least else 1.02 * last)

    def draw_live():
        cyc, tr, hist = live["cycle"], live["trace"], live["hist"]
        if cyc is not None and cyc.rec_t:
            plots.plot_record_series(ax["record"], cfg, np.array(cyc.rec_t),
                                     np.array(cyc.rec_v), np.array(cyc.rec_i),
                                     marks=cyc.marks, frame=cycle_frame(cyc),
                                     title="this cycle: junction V and current",
                                     log=log_iv.get())
        if tr is not None and tr.get("record") is not None:
            rec = tr["record"]
            # g0_2: the same pull on channel 2 of a two-channel amplifier
            # (None with one channel) -- blue and red on the one axis,
            # the red only where channel 2's output was not saturated.
            plots.plot_trace(ax["trace"], cfg, tr["g0"], tr["disp"], tr["verdict"],
                             title=f"trace {worker.attempts}",
                             sense_v=rec.piezo_sense_v, g0_2=tr.get("g0_2"),
                             linear=lin_g.get(), negative2=tr.get("negative2"))
        if cyc is not None and cyc.t:
            plots.plot_piezo(ax["piezo"], cfg, np.array(cyc.t), np.array(cyc.piezo_v),
                             np.array(cyc.sense_v), marks=cyc.marks,
                             title="piezo in and out, this cycle",
                             frame=cycle_frame(cyc))
        if hist is not None and hist["counts"] is not None:
            plots.plot_histogram(ax["hist"], cfg, hist["centres"], hist["counts"],
                                 hist["n"], counts2=hist.get("counts2"))
        elif hist is not None:
            ax["hist"].clear()
            ax["hist"].set_title("histogram: 0 traces (new experiment)", fontsize=9)
        apply_limits()
        relayout()
        canvas.draw_idle()

    def draw_igor(s: IgorDay, i: int):
        """The four panels for a trace of an Igor day folder or block: the
        junction voltage and current from the Voltage and Current blocks
        when they were saved, the conductance against its own displacement
        axis with the sense readback (Extension block) over it, the piezo
        command the parameters imply, and the histogram over everything
        opened."""
        t = s.trace(i)
        scfg = s.cfg
        C = scfg.cal
        g0, disp, fs = t["g0"], t["disp"], t["fs"]
        # The end of the trace on channel 2 when the day has one, as the
        # pull judged it.
        verdict = analysis.select_trace(
            g0, scfg.ramp, g0_open=analysis.open_side(g0, t.get("g0_2")))
        who = f"Igor trace {t['number']} (block {t['block']})"
        if t["voltage_v"] is not None and t["current_a"] is not None:
            # Back to raw volts with this config's calibration, which the
            # record panel undoes again: an exact round trip.
            rec = np.stack([t["voltage_v"] * C.voltage_input_sign,
                            C.amps_to_volts(t["current_a"])])
            plots.plot_record(ax["record"], scfg, rec, fs,
                              title=f"{who}: junction V and current (Voltage and "
                                    "Current blocks)", log=log_iv.get())
        else:
            ax["record"].clear()
            ax["record"].set_title(f"{who}: no Voltage/Current block saved", fontsize=9)
        sense_v = None
        if t["extension_nm"] is not None:
            sense_v = t["extension_nm"] / C.sense_nm_per_volt + C.sense_zero_v
        plots.plot_trace(ax["trace"], scfg, g0, disp, verdict, title=who, sense_v=sense_v,
                         g0_2=t.get("g0_2"),        # channel 2, from the ch2 subfolder
                         linear=lin_g.get(), saved=True)
        tt = np.arange(g0.size) / fs
        p = t["params"]
        # Slot 3 is the piezo position after the pull, slot 0 the pull.
        start_nm = (p[3] + p[0]) if np.isfinite(p[3]) and np.isfinite(p[0]) else disp[-1]
        plots.plot_piezo(ax["piezo"], scfg, tt, C.nm_to_piezo_volts(start_nm - disp),
                         sense_v, title="piezo during the pull (from the parameters, "
                                        "this config's nm/V)")
        if browse["hist"] is None:
            browse["hist"] = s.hist if s.hist is not None else \
                analysis.log_histogram(list(s.conductances()), igor_bins=True)
        plots.plot_histogram(ax["hist"], scfg, *browse["hist"], browse["n"],
                             title=f"histogram of {s.name}", counts2=s.hist2)
        banner.config(text=f"BROWSING {s.name}: {who}, Igor's numbering; "
                           f"live plots paused")
        apply_limits()
        relayout()
        canvas.draw_idle()

    def draw_saved(s, i: int):
        if isinstance(s, IgorDay):
            draw_igor(s, i)
            return
        scfg = s.cfg
        voltage, current = s.raw(i)
        g0 = s.conductance(i)
        fs = float(s.scalar("sample_rate_hz")[i])
        start_v = float(s.scalar("start_piezo_v")[i])
        disp = analysis.displacement_nm(voltage.size, scfg.ramp, fs)
        verdict = analysis.select_trace(
            g0, scfg.ramp, g0_open=s.open_side(i) if s.has_current2 else None)
        sense = s.piezo_sense(i, in_nm=False)
        # A session taken with a two-channel amplifier: channel 2 as well,
        # as far as it measured; its sign is read with the saturated part in.
        g0_2 = s.conductance(i, channel=2) if s.has_current2 else None
        negative2 = (analysis.reads_negative(
            s.conductance(i, channel=2, as_measured=True))
            if s.has_current2 else None)
        plots.plot_record(ax["record"], scfg, np.stack([voltage, current]), fs,
                          title=f"saved trace {i + 1}: junction V and current "
                                f"(the file keeps the trace only)", log=log_iv.get())
        plots.plot_trace(ax["trace"], scfg, g0, disp, verdict,
                         title=f"saved trace {i + 1}", sense_v=sense, g0_2=g0_2,
                         linear=lin_g.get(), saved=True, negative2=negative2)
        t = np.arange(voltage.size) / fs
        cmd = start_v - scfg.cal.nm_to_piezo_volts(disp)
        plots.plot_piezo(ax["piezo"], scfg, t, cmd, sense,
                         title="piezo during the saved pull")
        if browse["hist"] is None:
            browse["hist"] = analysis.log_histogram(s.conductances())
            browse["hist2"] = (analysis.log_histogram(s.conductances(channel=2))[1]
                               if s.has_current2 else None)
        plots.plot_histogram(ax["hist"], scfg, *browse["hist"], browse["n"],
                             title="histogram of the file", counts2=browse.get("hist2"))
        banner.config(text=f"BROWSING {Path(browse['path']).name} trace {i + 1}; "
                           f"live plots paused")
        apply_limits()
        relayout()
        canvas.draw_idle()

    rebuild()

    def poll():
        """The window's heartbeat, every 150 ms. An error in one tick is
        logged and the next tick still comes: the loop must not die while
        the rig is in use."""
        try:
            poll_body()
        except Exception:                       # noqa: BLE001
            log.exception("window update failed")
        root.after(150, poll)

    def poll_body():
        M, C = cfg.channels, cfg.cal
        live["last_poll"] = time.monotonic()
        while True:
            try:
                kind, p = worker.events.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                live["status"] = p["text"]
                set_status(p["text"], p.get("level"))
            elif kind == "error":
                set_status(p["text"], "bad")
                if p.get("fatal"):
                    banner.config(text="SAFETY STOP: see the status line; close "
                                       "and restart", fg="#b00000")
            elif kind == "readout":
                # "saved" is the day counter: the worker's once it has the
                # day's Igor writer, else what the Saving tab read from the
                # folder's files.
                saved = p["saved"]
                if saved is None:
                    saved = igor_next["n"] - 1 if igor_next["n"] is not None else "?"
                elif p.get("igor_folder") and live.get("experiment") is not None:
                    next_lbl.config(text=f"Igor folder: {p['igor_folder']}   "
                                         f"next trace (Saved): {saved + 1}")
                left_col = [
                    f"state     {p['state']}",
                    f"piezo     {p['piezo_v']:7.4f} V",
                    f"          {p['piezo_nm']:7.1f} nm",
                    (f"readback  {p['sense_nm']:7.1f} nm" if p["sense_nm"] is not None
                     else "readback  none"),
                    f"bias      {p['bias_mv']:7.1f} mV",
                ]
                right_col = [
                    f"junction  {p['junction_mv']:7.1f} mV",
                    f"current   {p['current_ua']:9.4f} uA" + (" RAILED" if p["railed"] else ""),
                    f"G         {p['g0']:.3e} G0",
                    f"zero      {p['zero_uv']:+.1f} uV",
                    f"accepted  {p['accepted']} / {p['attempts']}, {saved} saved today",
                ]
                lines = [f"{a:<27}{b}" for a, b in zip(left_col, right_col)]
                if has_ch2:
                    # Channel 2 of the amplifier: what it puts out, as a
                    # current and as a conductance. At its rail (its normal
                    # state while the junction is closed, at a bias and
                    # gain that saturate it) the volts are all there is to
                    # say: a saturated output is not a current, and no
                    # conductance is made of it (v75).
                    c2 = p.get("ch2")
                    if not p.get("two_channels"):
                        lines.append("ch 2      not read (one channel selected)")
                    elif c2 is None:
                        lines.append("ch 2      --")
                    elif c2["railed"]:
                        lines.append(f"ch 2      {c2['volts']:+8.4f} V  RAILED: its output "
                                     "is saturated, no reading")
                    else:
                        lines.append(f"ch 2      {c2['volts']:+8.4f} V {c2['amps'] * 1e9:10.3f} nA"
                                     f"  G {c2['g0']:.2e} G0")
                lines.append(f"file      {live.get('file') or 'none open'}")
                lines.append(f"keithley  {keithley_line()}")
                set_text(ro, "\n".join(lines))
                show_big(p["current_ua"], p["junction_mv"], p["piezo_v"],
                         p["sense_v"], ch2=p.get("ch2"))
            elif kind == "approach":
                live["cycle"] = p["cycle"]
                if live_moving.get():
                    live["dirty"] = True       # else: wait for the pull
            elif kind == "moved":
                # A move made by hand is its own event: the piezo and record
                # panels show it at once, whatever "redraw while moving" says.
                live["cycle"] = p["cycle"]
                live["dirty"] = True
                set_fine_window()               # the fine window, around where it ended
            elif kind == "keithley":
                show_keithley(p)
            elif kind == "ai_modes":
                show_ai_modes(p)
            elif kind == "amplifier":
                show_amplifier(p)
            elif kind == "piezo":
                show_piezo(p)
            elif kind == "paused":
                set_continue(bool(p["remaining"]))
            elif kind == "actuator":
                show_actuator(p)
            elif kind == "session_log":
                set_status(f"{status.cget('text')}   |   logged in "
                           f"{Path(p['path']).name}", level="ok")
            elif kind == "experiment":
                live["experiment"] = p["stem"]
                file_lbl.config(text=(f"experiment {Path(p['stem']).name}: waiting "
                                      "for the first accepted trace" if p["stem"]
                                      else "no run in progress"))
                if not p["stem"]:
                    schedule_show_next()       # the run's blocks are on disk: re-read
            elif kind == "cycle":
                live["cycle"] = p["cycle"]
                live["trace"] = p if p.get("record") is not None else None
                live["dirty"] = True
            elif kind == "hist":
                live["hist"] = p
                live["dirty"] = True
            elif kind == "file":
                live["file"] = Path(p["path"]).name if p["path"] else None
                if p["path"]:
                    file_lbl.config(text=f"writing {live['file']}")
                elif live.get("experiment") is None:
                    file_lbl.config(text="no file open")
            elif kind == "saved":
                live["file"] = Path(p["path"]).name if p["path"] else None
                words = []
                if p.get("number") is not None:
                    words.append(f"Igor trace {p['number']} -> "
                                 f"{Path(p['folder']).name}{os.sep}"
                                 f"PullOutConductanceBlock_{p['block']}")
                if p["path"]:
                    words.append(f"{live['file']}: {p['run']} traces" if p["run"]
                                 else f"{live['file']}: {p['n']} test pulls")
                file_lbl.config(text="writing " + "; ".join(words) if words
                                else "nothing is being written")
            elif kind == "ratecheck":
                if mon_state["rate_show"] is not None:
                    mon_state["rate_show"](p)
            elif kind == "monitor":
                rec = p["record"]
                tail = rec[:, rec.shape[1] // 2:]
                v = float(C.voltage_input_sign * np.mean(tail[M.ROW_VOLTAGE]))
                i = float(C.volts_to_amps(np.mean(tail[M.ROW_CURRENT])))
                with np.errstate(divide="ignore", invalid="ignore"):
                    g = abs(i) / abs(v) / G0_SIEMENS if abs(v) > 1e-9 else float("inf")
                mon_state["t"].append(p["t"])
                mon_state["v"].append(v * 1e3)
                mon_state["i"].append(i * 1e6)
                mon_state["g"].append(float(np.log10(max(g, 1e-12))) if np.isfinite(g) else 3.0)
                show_big(i * 1e6, v * 1e3, p["piezo_v"], p["sense_v"], beep_ok=True,
                         ch2=p.get("ch2"))
        if worker.busy and worker.current not in QUIET:
            # Igor's slider and readouts followed every write. While a
            # command runs, follow the tracker and the last play's record,
            # so the slider walks up the staircase and down the pull and
            # the readouts show the junction closing, as Igor's did.
            cyc = mon.last()
            rec = cyc.last_record
            if rec is not None and rec.shape[1] >= 4:
                tail = rec[:, rec.shape[1] // 2:]
                v_mv = float(C.voltage_input_sign * np.mean(tail[M.ROW_VOLTAGE])) * 1e3
                i_ua = float(C.volts_to_amps(np.mean(tail[M.ROW_CURRENT]))) * 1e6
            else:
                v_mv = i_ua = float("nan")
            sense = rig.last_sense_v
            sense_v = (float(np.mean(sense[sense.size // 2:]))
                       if sense is not None and sense.size else None)
            ch2 = (rig.channel2_of(rec, cyc.last_current2)
                   if rec is not None and cyc.last_current2 is not None else None)
            show_big(i_ua, v_mv, rig.piezo_v, sense_v, ch2=ch2)
            # A heartbeat on the status line, so a two-minute approach with
            # the plots standing still does not look like a frozen window.
            if live.get("busy_since") is None:
                live["busy_since"] = time.monotonic()
            elapsed = time.monotonic() - live["busy_since"]
            if worker.current == "follow":
                # the sliders' own move: the hand is on the rig, by the mouse
                working(True, f"SLIDER: the piezo follows the knob ({elapsed:.0f} s). "
                              f"Stop ends it. piezo {rig.piezo_v:.3f} V, junction "
                              f"{v_mv:.1f} mV, {i_ua:.3f} uA")
            else:
                working(True, f"WORKING: {worker.current} running {elapsed:.0f} s -- "
                              f"do not touch the rig; Stop ends it between steps. "
                              f"piezo {rig.piezo_v:.3f} V, junction {v_mv:.1f} mV, "
                              f"{i_ua:.3f} uA")
        else:
            live["busy_since"] = None
            if status2.cget("text"):
                working(False)
        if (rate_check_wanted() and not worker.busy and worker.commands.empty()
                and time.monotonic() - mon_state["rate_last"] > 1.0):
            # One second on every input, counted and timed; its last
            # samples feed the readouts as a monitor sample would.
            mon_state["rate_last"] = mon_state["last"] = time.monotonic()
            worker.send("ratecheck")
        elif (monitor_wants_sample() and not worker.busy and worker.commands.empty()
                and time.monotonic() - mon_state["last"] > 0.3):
            mon_state["last"] = time.monotonic()
            worker.send("monitor")
        if live["dirty"] and not live["paused"]:
            draw_live()
            live["dirty"] = False
            banner.config(text="", fg="#b06000")
        elif (worker.busy and worker.current not in QUIET and not live["paused"]
              and live_moving.get()):
            # A move in progress: redraw the record, piezo and approach
            # panels from the monitor every few polls, so the staircase
            # grows as you watch. Only when asked: by default the panels
            # change together, once per trace.
            live["tick"] = live.get("tick", 0) + 1
            if live["tick"] % 3 == 0:
                cyc = mon.snapshot()
                if cyc.t:
                    plots.plot_piezo(ax["piezo"], cfg, np.array(cyc.t),
                                     np.array(cyc.piezo_v), np.array(cyc.sense_v),
                                     marks=cyc.marks,
                                     title="piezo in and out, this cycle (live)",
                                     frame=cycle_frame(cyc))
                    if cyc.rec_t:
                        plots.plot_record_series(
                            ax["record"], cfg, np.array(cyc.rec_t),
                            np.array(cyc.rec_v), np.array(cyc.rec_i),
                            marks=cyc.marks, frame=cycle_frame(cyc),
                            title="this cycle: junction V and current (live)",
                            log=log_iv.get())
                    apply_limits()
                    canvas.draw_idle()
        if not live["paused"] and banner.cget("text").startswith("BROWSING"):
            banner.config(text="")
        # The one amplifier state that silently ruins a session: say so in
        # red for as long as the program knows it is on.
        k = live.get("keithley")
        zc_text = "ZERO CHECK ON: the amplifier reads nothing"
        if k is not None and k["zero_check"] and not banner.cget("text"):
            banner.config(text=zc_text, fg="#b00000")
        elif banner.cget("text") == zc_text and not (k is not None and k["zero_check"]):
            banner.config(text="")

    closed = {"done": False}

    def shutdown():
        """Stop whatever is running, wait for the worker to let go of the
        cards, and only then close them. Closing the tasks under a running
        approach made the worker's next write fail and left the outputs to
        the emergency park; the stop flag ends the approach between two
        steps instead, within a tenth of a second."""
        if closed["done"]:
            return
        closed["done"] = True
        worker.stop_flag.set()
        worker.quit()
        worker.join(timeout=60)
        if worker.is_alive():
            log.error("the rig worker has not finished in 60 s; closing the "
                      "cards under it")
        if browse["session"] is not None:
            browse["session"].close()
        try:
            save_saving(saving_file, saving_now())
        except Exception:                        # noqa: BLE001
            log.exception("could not remember the saving settings")
        close_rig(guard, rig)

    def on_close():
        try:
            shutdown()
        finally:
            root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)

    # The column's height: all of it when the screen has room, else what
    # fits, and the scrollbar takes care of the rest.
    root.update_idletasks()
    left_canvas.configure(height=min(left.winfo_reqheight(),
                                     root.winfo_screenheight() - 170))

    worker.send("noop")                              # first readout
    worker.send("ai_modes")                          # the card's input modes
    worker.send("amplifier")                         # one current channel or two
    worker.send("piezo")                             # the driver's mode and total
    root.after(150, poll)
    if readback:
        root.after(400, open_readback)
    if autoclose is not None:
        # v72: the driver row and the two sliders. Bypass with 9.3 um in all
        # is this simulated rig's 62 nm per volt, so nothing else changes;
        # then the fine window narrowed, the speed of a move made by hand
        # raised, and one such move toward the surface, before the run.
        root.after(150, lambda: (pmode_var.set("bypass"), ptotal_var.set("9.3"),
                                 worker.send("piezo_mode", "bypass", 9.3)))
        root.after(200, lambda: (fine_half_var.set("0.2"), speed_var.set("400")))
        root.after(250, lambda: worker.send("goto", 0.15))
        root.after(300, lambda: worker.send("zero"))
        # v73: Approach, the piezo coming up to the surface by itself, so
        # that the run starts from a contact the piezo found.
        root.after(350, lambda: worker.send("piezo_approach"))
        root.after(400, lambda: (name_var.set("smoke"), exp_var.set("clean gold"),
                                 txt_var.set(True)))
        root.after(600, on_run)
        root.after(900, open_limits)                 # smoke test: it must open
        root.after(950, open_monitor)
        # v69: the sample-rate check of the Monitor window (it runs whenever
        # the worker is idle), and the two plot check boxes on and off again.
        root.after(1000, lambda: mon_state["rate_on"].set(True))
        root.after(1300, lambda: (log_iv.set(True), lin_g.set(True), redraw_now()))
        root.after(2700, lambda: (log_iv.set(False), lin_g.set(False), redraw_now()))
        root.after(1200, lambda: (limits.update(
            trace={"x": (-0.5, 3.0), "y": (-7.0, 1.0), "y2": None}), redraw_now()))
        root.after(3000, lambda: (lim_state["win"].destroy(),   # and close again
                                  mon_state["win"].destroy()))

        def smoke_browse_igor():
            # The run of 3 is over by now: its block is on disk. Open the
            # day folder in the browser, show a trace, draw its histogram.
            if worker.igor is not None and worker.run_stem is None:
                open_saved(str(worker.igor.folder))
                if isinstance(browse["session"], IgorDay):
                    show_saved(+1)
                    open_hist_window("1d")
        root.after(3300, smoke_browse_igor)
        # The Settings tab: a refused value and an accepted one, previewed.
        root.after(4500, lambda: (nb.select(sb), left_canvas.yview_moveto(1.0),
                                  svars["ramp.bias_v"].set("900")))
        root.after(6500, lambda: svars["ramp.bias_v"].set("150"))
        root.after(6700, lambda: (ai_mode_var.set(MODE_WORDS["rse"]), on_ai_mode()))
        # v69: flip the sign of channel 1 and put it back, as the box does.
        root.after(6710, lambda: worker.send("current_sign", 1, -1.0))
        root.after(6730, lambda: worker.send("current_sign", 1, 1.0))
        if has_ch2:
            # A rig with a two-channel amplifier. Its gains must be where
            # they are seen without looking for them: the Current amplifier
            # box in the column, above Coarse approach, in the place of the
            # Keithley box, which is not shown.
            def smoke_amplifier_box():
                assert amp.winfo_ismapped() and not kb.winfo_ismapped(), \
                    "the Current amplifier box must stand in for the Keithley box"
                assert stb.winfo_rooty() < amp.winfo_rooty() < ab.winfo_rooty(), \
                    "the Current amplifier box must be between Status and Coarse approach"
                assert all(ent.winfo_ismapped() for ent in gain_entries.values()), \
                    "both gain boxes must be showing"
            root.after(2000, smoke_amplifier_box)
            # Read one channel, then both again, and change channel 2's
            # gain the way a person would.
            other = 1 if cfg.channels.two_current_channels else 2
            root.after(6750, lambda: worker.send("current_channels", other))
            root.after(6800, lambda: worker.send("current_channels", 3 - other))
            root.after(6850, lambda: svars[AMPLIFIER_SETTINGS[1]].set("1e8"))
            root.after(6900, lambda: apply_settings())
        # The coarse approach on the simulated actuator: Connect, then
        # Start approach (lands, backs off one step), then a piezo Approach.
        root.after(6900, lambda: (mode_var.set("actuator"), show_mode(),
                                  kind_var.set(KIND_NAMES["agilis"]),
                                  left_canvas.yview_moveto(0.0)))
        root.after(7000, lambda: worker.send("actuator", "ports"))
        root.after(7100, lambda: worker.send("actuator", "connect", "COM4", "agilis"))
        root.after(7200, lambda: worker.send("coarse_approach"))
        # The Piezo box: a slider move and a step by hand, after the run.
        root.after(9000, lambda: worker.send("goto", 2.0))
        root.after(9500, lambda: worker.send("step", 0.5))
        # The Keithley tab, on the simulated amplifier.
        root.after(9600, lambda: worker.send("keithley", "connect"))
        root.after(9700, lambda: worker.send("keithley", "zero_check", True))
        root.after(9800, lambda: worker.send("keithley", "zero_correct"))
        root.after(10400, lambda: worker.send("keithley", "find_suppress"))
        root.after(10500, lambda: worker.send("keithley", "gain", 7))
        root.after(9200, lambda: nb.select(fb))
        root.after(9300, lambda: left_canvas.yview_moveto(1.0))   # scrolled down

        def smoke_hist():
            files = sorted(Path(worker.saving["folder"]).rglob("*traces.h5"))
            if files:
                sess = storage.Session(files[-1])
                browse.update(session=sess, path=str(files[-1]), n=len(sess))
                open_hist_window("1d")
                open_hist_window("2d")
        root.after(12000, smoke_hist)
        root.after(int(autoclose * 1000), on_close)
    try:
        root.mainloop()
    finally:
        shutdown()
    return 0


# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Approach and pull by hand, with the pictures that matter.")
    p.add_argument("--config", type=Path, help="rig config JSON")
    p.add_argument("--simulate", action="store_true", help="fake card, no hardware")
    p.add_argument("--out", type=Path, default=None,
                   help="data folder (default: the one the Saving tab last "
                        "used, else data/); Igor's day folder "
                        "MM_DD<setup id>YYMerge is made under it")
    p.add_argument("--setup-id", default=None, metavar="ID",
                   help="Igor's SetupID in the day folder name (default: the "
                        "one the Saving tab last used, else '_', which gives "
                        "e.g. 10_22_26Merge)")
    p.add_argument("--no-igor", action="store_true",
                   help="do not write the Igor files (PullOut*Block_k.ibw); "
                        "for bench tests, the raw .h5 is still written")
    p.add_argument("--require-engaged", action="store_true",
                   help="also require each trace to start in contact")
    p.add_argument("--headless", type=int, metavar="N",
                   help="no window: zero, then N cycles saved into the day "
                        "folder as Start N saves them, then a report")
    p.add_argument("--test-pull", type=float, metavar="VOLTS",
                   help="headless: instead of cycles, N pulls from this piezo "
                        "voltage with no approach and no contact (a rig with "
                        "no tip)")
    p.add_argument("--name", default=None, metavar="WHO",
                   help="headless: your name, for the .h5 and the log (default: "
                        "the one the Saving tab last used)")
    p.add_argument("--experiment", default=None, metavar="WHAT",
                   help="headless: the experiment, which names the .h5 and goes "
                        "into the Igor block's note (default: the one the Saving "
                        "tab last used)")
    p.add_argument("--readback", action="store_true",
                   help="GUI: open the readback-only window at start")
    p.add_argument("--save-test-pulls", action="store_true",
                   help="headless with --test-pull: also save them to a "
                        "TESTPULLS .h5 (a format test, never Igor data)")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--zoom", type=float, default=None,
                   help="make the window bigger or smaller: 1.2 is a fifth "
                        "bigger (text, buttons, boxes; the plots take what "
                        "is left). Default 1.0, on a Mac 1.2")
    p.add_argument("--autoclose", type=float, help=argparse.SUPPRESS)
    p.add_argument("--version", action="version",
                   version=f"pullout {__version__}")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S")

    cfg = RigConfig.from_json(args.config) if args.config else RigConfig()
    if args.simulate:
        cfg.simulate = True
    try:
        # The smoke run keeps its remembered settings in its own folder so
        # it never pre-fills a real session's Saving tab.
        saving_file = (args.out / "pullout_saving.json"
                       if args.autoclose is not None and args.out is not None
                       else _ROOT / "data" / "pullout_saving.json")
        remembered = load_saving(saving_file)
        if args.headless is not None:
            # Saved exactly as Start N saves: the name, experiment, notes
            # and save boxes the Saving tab remembered apply; the folder
            # and the Setup ID come from the flags (the Setup ID is
            # remembered too).
            saving = {key: remembered[key] for key in DEFAULT_SAVING
                      if key in remembered and key not in ("folder", "setup_id")}
            if args.name is not None:
                saving["name"] = args.name
            if args.experiment is not None:
                saving["experiment"] = args.experiment
            return run_headless(cfg, args.headless, args.out or _ROOT / "data",
                                not args.no_igor,
                                args.require_engaged, test_pull_v=args.test_pull,
                                save_test_pulls=args.save_test_pulls,
                                setup_id=args.setup_id or remembered.get("setup_id") or "_",
                                saving=saving)
        out = args.out or Path(remembered.get("folder") or _ROOT / "data")
        return run_gui(cfg, out, not args.no_igor,
                       args.config.name if args.config else "defaults",
                       autoclose=args.autoclose, readback=args.readback,
                       saving_file=saving_file, zoom=args.zoom,
                       setup_id=args.setup_id)
    except (ConfigError, SafetyViolation) as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.info("interrupted; outputs parked")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
