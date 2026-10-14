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

Saving is per experiment: every Start N is one experiment, filed under
<data folder>/<date>/<your name>/<experiment>_<HHMMSS of the click>, and
when the run ends the files are renamed with the number of traces they hold
(``..._<N>traces``). The .h5 always (raw volts, the config, per-trace
scalars: ``storage.SessionWriter``); Igor .ibw blocks in SavePullOut's
layout and a .txt table (displacement, then one G/G0 column per trace) as
ticked. Name, experiment, folder and the boxes are remembered between
launches in data/pullout_saving.json. The Run box is Start N (every trace
is its own approach + pull, from an open junction), Continue, Stop and
Calibrate zero; the single-cycle commands (engage, pull, cycle, withdraw,
smash) are still there for --headless and the tests, and the smash-every
line runs the smash inside Start N. A saved session can be browsed in the
same plots. Under Run, the Status box: the rig's numbers (state, piezo,
junction, current, zero, file, Keithley) and the last message, in colour.

The Piezo box is Igor's PiezoGroupbox: a slider over the piezo's whole
voltage range (applies when the mouse is released, as Igor's did), Step
closer / Step apart by Z nm, and under them Igor's readouts -- I (uA),
V (mV), Piezo (V) and the sense line -- refreshed every 0.3 s while the rig
is idle by the same quiet 10 ms hold the Monitor window uses (Igor's
Background Sampling), with Igor's beep above 0.15 uA. A move made by hand
is ramped over 50 ms, then the junction is probed: in contact, the state
becomes ENGAGED (Step apart, or the slider, opens it again); Start N starts
from wherever the slider left the tip, separating first.

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
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from stmlab import analysis, approach, calibrate, plots, storage, trace   # noqa: E402
from stmlab.actuator import ActuatorError                           # noqa: E402
from stmlab.approach import ApproachError                           # noqa: E402
from stmlab.config import ConfigError, G0_SIEMENS, RigConfig, validate   # noqa: E402
from stmlab.instrument import Rig                                   # noqa: E402
from stmlab.safety import RigState, SafeSession, SafetyViolation    # noqa: E402

log = logging.getLogger("pullout")

# Shown in the window title and by --version, so a patch can say which
# version it applies to and you can see which one you have.
__version__ = "v52"


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
]


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
        with self.lock:
            c = self.cycle
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

    def snapshot(self) -> CycleLog:
        with self.lock:
            return copy.copy(self.cycle)


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
        self.igor_export = igor_export
        self.out_dir = out_dir
        # Where and under what name the next run's files go (the Saving
        # tab); the run's file stem while a run is going, else None.
        self.saving: dict = {"folder": Path(out_dir), "name": "",
                             "experiment": "", "notes": "", "txt": False}
        self.config_name = ""                  # for the session log
        self.run_stem: Path | None = None
        self.run_started: float | None = None
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
        self.file_traces: list = []            # (g0, start_v, ts) for Igor export
        self.n_saved = 0
        self.save_test_pulls = False           # into a TESTPULLS file, never data
        self.writer_is_test = False
        self.accepted = 0
        self.attempts = 0
        self.rejections: dict[str, int] = {}
        self.hist_sum = None
        self.hist_centres = None
        self.hist_n = 0
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
            if name not in ("monitor", "noop"):
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
                  piezo_v=self.rig.piezo_v, sense_v=sense_v)

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
                        "Keithley tab); the front-panel buttons do the same.")
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

        Ramped over 50 ms rather than jumped, then the junction is probed and
        the state follows what it reads, so a contact made by hand can be
        pulled from with the pull command (headless), as Igor's
        slider-then-measure could. Start N needs no state: it separates first.
        """
        if self.bias_dirty:
            self.cmd_bias()
        c = self.mon.snapshot()
        if not c.t or "end" in c.marks:
            # A fresh picture for a fresh series of moves; a cycle that has
            # pulled is finished, one that has not keeps accumulating.
            self.mon.begin_cycle()
            self.mon.mark("by hand")
        was = self.rig.piezo_v
        self.rig.piezo_ramp_to(volts)
        g0, railed = self.rig.probe()
        R = self.cfg.ramp
        if railed or g0 > R.engage_g0:
            self.rig.state = RigState.ENGAGED
            word = "in contact"
        else:
            # Not parked, not engaged: the tip is wherever the hand left it.
            self.rig.state = RigState.UNKNOWN
            word = "open" if g0 < R.break_g0 else "tunnelling"
        self.post("moved", cycle=self.mon.snapshot())
        self.status(f"piezo {was:.4f} -> {self.rig.piezo_v:.4f} V "
                    f"({self.rig.piezo_nm:.1f} nm): G = {g0:.3e} G0, {word}")

    def cmd_step(self, delta_nm: float) -> None:
        """Igor's PiezoStepCloser / PiezoStepApart: closer is +nm."""
        self.cmd_goto(self.rig.piezo_v + self.cfg.cal.nm_to_piezo_volts(delta_nm))

    # -- the pieces of a cycle ---------------------------------------------------

    def cmd_zero(self) -> None:
        self.status("measuring the preamp zero at 0 V bias ...")
        zero = calibrate.measure_zero(self.rig)
        self.cfg.cal.current_zero_v = zero
        self.bias_dirty = True
        text = f"preamp zero {zero * 1e6:+.2f} uV, written into cal"
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
        self.post("zero", zero_v=zero)

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
        verdict = analysis.select_trace(g0, self.cfg.ramp,
                                        require_engaged=self.require_engaged)
        disp = tr.displacement_nm(self.cfg)
        if test:
            self.post("cycle", cycle=cycle, record=tr, g0=g0, disp=disp,
                      verdict=verdict)
            saved = ""
            if self.save and self.save_test_pulls:
                self._save(tr, verdict, test=True)
                saved = f", saved to the TESTPULLS file ({self.n_saved})"
            self.status(f"test pull done (not counted{saved}); the selector "
                        f"would say: {verdict.reason}; alignment delay "
                        f"{tr.delay_samples} samples")
            return verdict
        if verdict.accepted:
            self.accepted += 1
            self._accumulate(g0)
            if self.save:
                self._save(tr, verdict)
        else:
            key = verdict.reason.split(":")[0].split("(")[0].strip()
            self.rejections[key] = self.rejections.get(key, 0) + 1
        self.post("cycle", cycle=cycle, record=tr, g0=g0, disp=disp,
                  verdict=verdict)
        self.post("hist", centres=self.hist_centres,
                  counts=self.histogram(), n=self.hist_n)
        word = "accepted" if verdict.accepted else "rejected"
        self.status(f"trace {word}: {verdict.reason}; {self.accepted} accepted "
                    f"in {self.attempts} attempts")
        return verdict

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
        a never-engaged trace unless "require engaged start" is on.)
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
        if done < n and (self.stop_flag.is_set() or failed):
            self.paused = {"remaining": n - done}
            self.run_pauses.append({"after_trace": self.accepted,
                                    "why": "approach failed" if failed else "Stop",
                                    "stopped": time.time(), "continued": None})
            self.post("paused", remaining=n - done)
            self.status(f"run paused with {n - done} of {n} traces still to "
                        f"take ({self.accepted} accepted so far). Continue "
                        "carries on into the same file; Start N starts a new "
                        "experiment")
            return
        files = self.end_experiment()
        self.status(f"run finished: {self.accepted} accepted in "
                    f"{self.attempts} attempts; rejected {self.rejections}"
                    + (f"; saved {files}" if files else "; nothing saved"))

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

    def experiment_paths(self, when: float | None = None) -> tuple[Path, str]:
        """(folder, stem) a run started at ``when`` would use: the data
        folder, the date, the person's name, then <experiment>_<HHMMSS>."""
        t = time.localtime(when)
        folder = (Path(self.saving["folder"])
                  / time.strftime("%Y-%m-%d", t)
                  / self._safe(self.saving["name"], "unknown"))
        stem = (f"{self._safe(self.saving['experiment'], 'experiment')}_"
                f"{time.strftime('%H%M%S', t)}")
        return folder, stem

    def begin_experiment(self) -> None:
        """A fresh set of files, histogram and counters for this run."""
        if self.run_stem is not None:
            self.end_experiment()              # a paused run: its files are done
        elif self.writer is not None:
            self.close_file(export=False)
        self.paused = None
        self.run_started = time.time()
        folder, stem = self.experiment_paths(self.run_started)
        self.run_stem = folder / stem
        self.accepted = 0
        self.attempts = 0
        self.rejections = {}
        self.run_v_contact = []
        self.run_v_open = []
        self.run_pauses = []
        self.hist_sum = None
        self.hist_n = 0
        self.post("hist", centres=None, counts=None, n=0)
        self.post("experiment", stem=str(self.run_stem))
        self.status(f"experiment {stem}: files go to {folder}")

    def end_experiment(self) -> list[str]:
        """Close the run's file, name it after its trace count, and write
        the Igor blocks and the .txt table beside it as ticked."""
        stem = self.run_stem
        self.run_stem = None
        self.paused = None
        self.post("paused", remaining=0)
        if stem is None or self.writer is None:
            self.post("experiment", stem=None)
            return []
        traces = list(self.file_traces)
        auto = self.auto_notes(len(traces))
        try:
            self.writer.describe(auto_notes=auto)
        except Exception:                          # noqa: BLE001
            log.exception("could not write the automatic note into the file")
        self.close_file(export=False)
        h5 = stem.with_suffix(".h5")
        final = stem.with_name(f"{stem.name}_{len(traces)}traces")
        try:
            h5 = h5.rename(final.with_suffix(".h5"))
        except OSError as exc:
            log.warning("could not rename %s: %s", h5.name, exc)
        written = [h5.name]
        if self.igor_export and traces:
            self.file_traces = traces
            self.export_igor(h5)
            written += [f"{h5.stem}_b*.ibw"]
        if self.saving.get("txt") and traces:
            try:
                data, info = storage.save_txt_block(
                    h5.with_suffix(".txt"), self.cfg, [t[0] for t in traces],
                    start_piezo_v=[t[1] for t in traces],
                    timestamps=[t[2] for t in traces],
                    header_lines=[f"name={self.saving['name']} "
                                  f"experiment={self.saving['experiment']} "
                                  f"file={h5.name}",
                                  f"notes={self.saving.get('notes', '')}",
                                  f"auto_notes={auto}"])
                written += [data.name, info.name]
            except Exception as exc:               # noqa: BLE001
                log.exception("txt export failed")
                self.post("error", text=f"txt export failed: {exc}", fatal=False)
        try:
            self.log_session(h5, traces, written)
        except Exception as exc:                   # noqa: BLE001
            log.exception("session log failed")
            self.post("error", text=f"session log not written: {exc}", fatal=False)
        self.post("experiment", stem=None)
        self.post("file", path=None)
        return written

    SESSION_LOG = "experiment_log.csv"

    def auto_notes(self, n_traces: int) -> str:
        """The sentence a lab notebook would want written for every run,
        made from the settings and from what the junction actually read:
        the bias set, the junction voltage measured with the junction open
        (what the tunnelling tail sees through the series resistor) and at
        the start of the pull (in contact), the resistor, the gain, the
        preamp zero, and the pull."""
        R, C, K = self.cfg.ramp, self.cfg.cal, self.cfg.keithley
        v_open = float(np.median(self.run_v_open)) if self.run_v_open else float("nan")
        v_con = float(np.median(self.run_v_contact)) if self.run_v_contact else float("nan")
        note = (f"bias set {R.bias_v * 1e3:g} mV; junction measured "
                f"{v_open:.1f} mV open, {v_con:.1f} mV at pull start "
                f"(medians over {n_traces} traces); series resistor "
                f"{K.series_resistance_ohm:g} ohm; gain {C.preamp_gain_v_per_a:.0e} V/A; "
                f"preamp zero {C.current_zero_v * 1e6:+.1f} uV; pull "
                f"{R.pull_length_nm:g} nm at {R.pull_rate_nm_per_s:g} nm/s, "
                f"engage {R.engage_g0:g} G0, break {R.break_g0:g} G0, "
                f"{C.piezo_nm_per_volt:g} nm/V")
        for pz in self.run_pauses:
            clock = lambda t: time.strftime("%H:%M:%S", time.localtime(t))  # noqa: E731
            note += (f"; {pz['why']} after trace {pz['after_trace']} at "
                     f"{clock(pz['stopped'])}"
                     + (f", continued {clock(pz['continued'])}"
                        if pz["continued"] else ", not continued"))
        return note

    def log_session(self, h5: Path, traces: list, written: list) -> Path:
        """Two lines per experiment in <data folder>/experiment_log.csv, one
        file for every day and everyone, readable as a notebook:

            date, start time, name, experiment, traces, your notes, the
                automatic note (bias set, junction measured, resistor,
                gain, zero, the pull)
            the full path of the data file, alone on the next line

        The header is written once; lines are appended."""
        started = self.run_started or time.time()
        path = Path(self.saving["folder"]) / self.SESSION_LOG
        new = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["date", "start_time", "name", "experiment", "traces",
                            "notes", "auto_notes"])
            w.writerow([time.strftime("%Y-%m-%d", time.localtime(started)),
                        time.strftime("%H:%M:%S", time.localtime(started)),
                        self.saving.get("name", ""),
                        self.saving.get("experiment", ""),
                        len(traces),
                        self.saving.get("notes", ""),
                        self.auto_notes(len(traces))])
            w.writerow([str(h5.resolve())])
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

    def _accumulate(self, g0: np.ndarray) -> None:
        centres, counts = analysis.log_histogram([g0])
        if self.hist_sum is None:
            self.hist_centres, self.hist_sum = centres, np.zeros_like(counts)
        if counts.any():
            self.hist_sum += counts
            self.hist_n += 1

    def histogram(self) -> np.ndarray | None:
        if self.hist_sum is None or self.hist_n == 0:
            return None
        return self.hist_sum / self.hist_n

    def _save(self, tr, verdict, test: bool = False) -> None:
        """Append a trace to the session file, opening one if needed.

        Test pulls go to a file whose name says TESTPULLS, and never into a
        file holding real traces (nor the other way round): a file is either
        data or a format test.
        """
        if not test and (self.run_stem is None or self.paused is not None):
            return                                 # a single cycle: shown only
        if self.writer is not None and self.writer_is_test != test:
            self.close_file()
        if self.writer is None:
            if test:
                path = (Path(self.saving["folder"]) /
                        f"pullout_TESTPULLS_{time.strftime('%Y%m%d_%H%M%S')}.h5")
            else:
                path = self.run_stem.with_suffix(".h5")
            self.writer = storage.SessionWriter(path, self.cfg).open()
            self.writer.describe(operator=self.saving.get("name", ""),
                                 experiment=self.saving.get("experiment", ""),
                                 notes=self.saving.get("notes", ""),
                                 program=f"pullout {__version__}",
                                 config=self.config_name)
            self.writer_is_test = test
            self.file_traces = []
            self.post("file", path=str(path))
        self.writer.append(self.n_saved, tr, verdict)
        self.n_saved += 1
        self.file_traces.append((tr.conductance_g0(self.cfg).astype(np.float32),
                                 tr.start_piezo_v, tr.timestamp))
        if not test:
            v = self.cfg.cal.voltage_input_sign * np.asarray(tr.voltage_v, float) * 1e3
            n = v.size
            # The first half-millisecond: the junction as it was when the
            # pull began, before a shallow contact has had time to break.
            self.run_v_contact.append(float(np.mean(v[:max(5, n // 500)])))
            self.run_v_open.append(float(np.mean(v[int(n * 0.90):int(n * 0.94) + 1])))
        self.post("saved", n=self.n_saved, path=str(self.writer.path))

    def close_file(self, export: bool | None = None) -> None:
        """Close the session file; export it for Igor if asked."""
        if self.writer is None:
            return
        path = self.writer.path
        try:
            self.writer.write_summary({"accepted": self.accepted,
                                       "attempts": self.attempts,
                                       "rejections": self.rejections})
            self.writer.close()
        finally:
            self.writer = None
        do_export = self.igor_export if export is None else export
        if do_export and self.file_traces:
            self.export_igor(path)
        self.post("file", path=None)

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

    def cmd_export(self) -> None:
        if self.writer is None or not self.file_traces:
            self.status("nothing to export yet")
            return
        self.export_igor(self.writer.path)

    def export_igor(self, h5_path: Path) -> None:
        """Igor blocks of up to 100 traces, as SavePullOut wrote them."""
        traces = self.file_traces
        written = []
        for b in range(0, len(traces), 100):
            chunk = traces[b:b + 100]
            name = f"{h5_path.stem}_b{b // 100:03d}"
            out = h5_path.with_name(name + ".ibw")
            storage.save_igor_block(out, self.cfg, [t[0] for t in chunk],
                                    start_piezo_v=[t[1] for t in chunk],
                                    timestamps=[t[2] for t in chunk],
                                    name=storage._igor_name(name))
            written.append(out.name)
        self.status(f"Igor export: {', '.join(written)} ({len(traces)} traces)")
        self.post("exported", files=written)

    def readout(self) -> None:
        rig = self.rig
        c = self.mon.snapshot()
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
        self.post("readout", state=rig.state.name, piezo_v=rig.piezo_v,
                  piezo_nm=rig.piezo_nm, bias_mv=rig.bias_v * 1e3,
                  junction_mv=v_mv, current_ua=i_ua, g0=g0, railed=railed,
                  sense_nm=rig.sense_nm, sense_v=sense_v,
                  accepted=self.accepted, attempts=self.attempts,
                  saved=self.n_saved, zero_uv=C.current_zero_v * 1e6)


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
# Headless: N cycles, save, export, report
# --------------------------------------------------------------------------

def run_headless(cfg: RigConfig, n: int, out_dir: Path, igor_export: bool,
                 require_engaged: bool, test_pull_v: float | None = None,
                 save_test_pulls: bool = False) -> int:
    guard, rig = open_rig(cfg)
    mon = Monitor(rig)
    worker = Worker(cfg, rig, mon, save=True, out_dir=out_dir,
                    igor_export=igor_export)
    worker.require_engaged = require_engaged
    worker.save_test_pulls = save_test_pulls
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
    files = []
    while True:
        try:
            kind, payload = worker.events.get_nowait()
        except queue.Empty:
            break
        if kind == "status":
            last_status = payload["text"]
        elif kind == "exported":
            files = payload["files"]
        elif kind == "error":
            print("error:", payload["text"])
    print(last_status)
    hist = worker.histogram()
    if hist is not None:
        peak = analysis.peak_position(worker.hist_centres, hist, around=0.0,
                                      window=0.4)
        print(f"1 G0 peak at {peak:+.4f} decades over {worker.hist_n} traces")
    if files:
        print("Igor files:", ", ".join(files))
    return 0


# --------------------------------------------------------------------------
# Histogram windows for a saved session: 1D and 2D, with their own controls
# --------------------------------------------------------------------------

def hist_window(win, session, stem: str, kind: str, tk, ttk, FigureCanvasTkAgg,
                Figure, status) -> dict:
    """A window with one plot and the knobs that matter for it, applied on
    Redraw or Return; the matplotlib toolbar underneath gives zoom, pan and
    Save. Returns the window's controls (for tests)."""
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

    cfg = session.cfg
    traces = list(session.conductances())
    n_samples = max((t.size for t in traces), default=0)
    fs = float(session.scalar("sample_rate_hz")[0]) if len(session) else \
        cfg.ramp.sample_rate_hz
    disp = analysis.displacement_nm(n_samples, cfg.ramp, fs)
    cache: dict = {}

    if kind == "1d":
        entry(bar, "bins", "bins", 1000)
        entry(bar, "x from", "x0", -7)
        entry(bar, "x to", "x1", 1)
        entry(bar, "line width", "lw", 1.2)
        entry(bar, "color", "color", "k", width=8)
        entry(bar2, "smooth (points)", "smooth", 11)
        flag(bar2, "log y", "logy", False)
        flag(bar2, "fill", "fill", False)
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
    ttk.Button(bar2, text="Redraw", command=lambda: redraw()).pack(side="right", padx=4)

    def redraw():
        fig.clear()
        ax = fig.add_subplot(111)
        if kind == "1d":
            bins = max(10, num("bins", 1000, int) or 1000)
            x0, x1 = num("x0", -7.0) or -7.0, num("x1", 1.0) or 1.0
            smooth = max(1, num("smooth", 11, int) or 11)
            key = (bins, smooth)
            if key not in cache:
                cache[key] = analysis.log_histogram(traces, lo=-8.0, hi=2.0,
                                                    n_bins=bins,
                                                    smooth_width=smooth)
            centres, counts = cache[key]
            lw = num("lw", 1.2) or 1.2
            color = ctl["color"].get().strip() or "k"
            try:
                ax.plot(centres, counts, color=color, lw=lw)
                if ctl["fill"].get():
                    ax.fill_between(centres, 0, counts, color=color, alpha=0.25)
            except ValueError:
                ax.plot(centres, counts, color="k", lw=lw)
                note.config(text=f"'{color}' is not a colour name; drew black")
            if ctl["logy"].get():
                ax.set_yscale("log")
            ax.set_xlim(x0, x1)
            ax.set_xlabel("log10 (G / G0)")
            ax.set_ylabel("counts per trace")
            ax.set_title(f"{stem}: {len(traces)} traces", fontsize=10)
            for g in (0.0, np.log10(2), np.log10(3), np.log10(4)):
                ax.axvline(g, color="#999", lw=0.5, ls=":")
            ax.grid(True, alpha=0.3)
            peak = analysis.peak_position(centres, counts, around=0.0, window=0.4)
            note.config(text=f"1 G0 peak at {peak:+.4f} decades; bins {bins}, "
                             f"smooth {smooth} points")
        else:
            nx = max(10, num("nx", 200, int) or 200)
            ny = max(10, num("ny", 300, int) or 300)
            x0, x1 = num("x0", -0.5), num("x1", 2.0)
            y0, y1 = num("y0", -7.0), num("y1", 1.0)
            x0 = -0.5 if x0 is None else x0
            x1 = 2.0 if x1 is None else x1
            y0 = -7.0 if y0 is None else y0
            y1 = 1.0 if y1 is None else y1
            align = num("align", 0.5)
            key = (nx, ny, x0, x1, y0, y1, align)
            if key not in cache:
                cache[key] = analysis.histogram_2d(
                    traces, disp, align_at_g0=align, x_range=(x0, x1), n_x=nx,
                    y_range=(y0, y1), n_y=ny)
            counts, xe, ye = cache[key]
            vmax = num("vmax", None)
            cmap = ctl["cmap"].get().strip() or "viridis"
            try:
                im = ax.pcolormesh(xe, ye, counts.T, cmap=cmap, vmin=0,
                                   vmax=vmax, shading="flat")
            except ValueError:
                im = ax.pcolormesh(xe, ye, counts.T, cmap="viridis", vmin=0,
                                   vmax=vmax, shading="flat")
                note.config(text=f"'{cmap}' is not a colormap; used viridis")
            if ctl["cbar"].get():
                fig.colorbar(im, ax=ax, label="counts per trace")
            ax.set_xlabel("displacement (nm)" + ("" if align is None else
                                                 f", 0 where G first < {align:g} G0"))
            ax.set_ylabel("log10 (G / G0)")
            ax.set_title(f"{stem}: {len(traces)} traces", fontsize=10)
            if not note.cget("text").startswith("'"):
                note.config(text=f"{nx} x {ny} bins; colour max "
                                 f"{counts.max():.3g} counts per trace"
                                 + (f" (shown up to {vmax:g})" if vmax else ""))
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


WIN_BG = "#f0f0f0"      # Windows' window grey, the colour the layout was made on


def _light_window(win) -> None:
    """A light window whatever the Mac's dark mode says. Tk 8.6.10 and later
    on the Mac have the command; an older Tk, or any other platform, has
    nothing to do."""
    if sys.platform == "darwin":
        try:
            win.tk.call("::tk::unsupported::MacWindowStyle", "appearance", win, "aqua")
        except Exception:                                 # noqa: BLE001
            pass


def windows_look(root, style, zoom: float = 1.0) -> None:
    """The Windows window on another platform.

    Tk's own flat "clam" theme, recoloured to Windows' greys, with Windows'
    tick boxes and radio dots (borrowed from Tk's "alt" theme), Windows'
    font sizes (9 pt, which on a Mac Tk draws a third smaller unless the
    scaling is set to 96 dpi, so it is), the classic widgets (labels, the
    readout, the slider, the Status box) on the same light palette, and
    the system's dark mode kept out. ``zoom`` makes everything bigger or
    smaller (1.2 = a fifth bigger) for a small or a very sharp screen.
    """
    from tkinter import font as tkfont
    style.theme_use("clam")
    if sys.platform == "darwin":
        root.tk.call("tk", "scaling", 96.0 / 72.0 * zoom)
    elif zoom != 1.0:
        root.tk.call("tk", "scaling", float(root.tk.call("tk", "scaling")) * zoom)
    # The classic widgets take the palette (which also colours the root and
    # every widget made from now on); the themed ones take the style.
    root.tk_setPalette(background=WIN_BG, foreground="#000000",
                       activeBackground="#e5e5e5", activeForeground="#000000",
                       highlightBackground=WIN_BG, highlightColor="#0078d7",
                       selectBackground="#0078d7", selectForeground="#ffffff",
                       insertBackground="#000000", troughColor="#d6d6d6",
                       disabledForeground="#6d6d6d", selectColor="#ffffff")
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
                 "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont",
                 "TkTooltipFont"):
        tkfont.nametofont(name).configure(family="Arial", size=9)
    tkfont.nametofont("TkFixedFont").configure(family="Courier", size=9)
    style.configure(".", background=WIN_BG, foreground="#000000",
                    fieldbackground="#ffffff", troughcolor="#d6d6d6",
                    selectbackground="#0078d7", selectforeground="#ffffff",
                    font="TkDefaultFont")
    # Windows 10's buttons: a light face, a thin outline, blue when the
    # mouse is over them.
    style.configure("TButton", background="#e1e1e1", lightcolor="#e1e1e1",
                    darkcolor="#e1e1e1", bordercolor="#adadad")
    style.map("TButton",
              background=[("disabled", "#cccccc"), ("pressed", "#cce4f7"),
                          ("active", "#e5f1fb")],
              lightcolor=[("pressed", "#cce4f7"), ("active", "#e5f1fb")],
              darkcolor=[("pressed", "#cce4f7"), ("active", "#e5f1fb")],
              bordercolor=[("disabled", "#bfbfbf"), ("pressed", "#005499"),
                           ("active", "#0078d7")])
    style.configure("TEntry", bordercolor="#7a7a7a")
    style.configure("TCombobox", bordercolor="#7a7a7a", arrowcolor="#606060")
    style.map("TCombobox", fieldbackground=[("readonly", "#ffffff")],
              selectbackground=[("readonly", "#ffffff")],
              selectforeground=[("readonly", "#000000")])
    style.configure("TNotebook.Tab", background="#e1e1e1", lightcolor="#e1e1e1",
                    darkcolor="#e1e1e1", bordercolor="#adadad")
    style.map("TNotebook.Tab", background=[("selected", WIN_BG)],
              lightcolor=[("selected", WIN_BG)])
    style.configure("TScrollbar", background="#cdcdcd", troughcolor=WIN_BG,
                    bordercolor=WIN_BG, lightcolor="#cdcdcd", darkcolor="#cdcdcd",
                    arrowcolor="#606060")
    # Windows' tick box and radio dot in place of clam's black square and
    # filled dot: the indicator elements of Tk's "alt" theme, in clam's layout.
    try:
        style.element_create("Tick.Checkbutton.indicator", "from", "alt",
                             "Checkbutton.indicator")
        style.element_create("Tick.Radiobutton.indicator", "from", "alt",
                             "Radiobutton.indicator")
    except Exception:                                     # noqa: BLE001
        pass                                              # no alt theme: clam's own
    else:
        for kind in ("Checkbutton", "Radiobutton"):
            style.layout(f"T{kind}", [
                (f"{kind}.padding", {"sticky": "nswe", "children": [
                    (f"Tick.{kind}.indicator", {"side": "left", "sticky": ""}),
                    (f"{kind}.focus", {"side": "left", "sticky": "w", "children": [
                        (f"{kind}.label", {"sticky": "nswe"})]})]})])
            style.configure(f"T{kind}", indicatorcolor="#ffffff",
                            indicatormargin=(1, 1, 4, 1))
    _light_window(root)


def run_gui(cfg: RigConfig, out_dir: Path, igor_export: bool,
            config_name: str, autoclose: float | None = None,
            readback: bool = False,
            saving_file: Path | None = None, zoom: float | None = None) -> int:
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
    if themed_buttons:
        for name, bg, down in (("Go", GREEN, GREEN_DOWN), ("Stop", RED, RED_DOWN),
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
            name = "Stop" if bg == RED else "Go"
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
    ro = tk.Text(stb, width=62, height=7, font=("Courier", 9), relief="flat",
                 state="disabled", background=root.cget("background"))
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
    kb = ttk.LabelFrame(left, text="Keithley 428 (GPIB)")
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

    def apply_contact(*_a):
        try:
            contact["ua"] = abs(float(contact_var.get()))
        except ValueError:
            pass
    contact_var.trace_add("write", apply_contact)

    def show_mode():
        af.grid_forget()
        sf.grid_forget()
        (af if mode_var.get() == "actuator" else sf).grid(row=1, column=0, sticky="w")
    show_mode()

    # -- piezo: Igor's PiezoGroupbox, with Igor's readouts under it -----------------
    # Step apart / Z (nm) / Step closer, a slider over the piezo's whole
    # range that applies on mouse release (Igor's SetPiezoBiasFromSlider,
    # live=0), and the readouts Igor kept at the bottom of its panel:
    # I (uA), V (mV), Piezo, plus the sense line this rig has. They are
    # refreshed by every command and, while idle, every 0.3 s by a quiet
    # hold (Igor's Background Sampling) with Igor's beep above the contact
    # current.
    C = cfg.cal
    pb = ttk.LabelFrame(left, text="Piezo (Igor's piezo controls)")
    pb.pack(fill="x", pady=(0, 3))
    lo_v, hi_v = cfg.limits.piezo_ao_min_v, cfg.limits.piezo_ao_max_v
    z_var = tk.StringVar(value="5")

    QUIET = ("monitor", "noop")      # commands that do not count as busy

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
            set_status(f"Z: '{z_var.get()}' is not a number")
            return
        hand_move("step", sign * nm)

    ttk.Button(pb, text="Step apart", command=lambda: on_step(-1)).grid(
        row=0, column=0, padx=2, pady=1, sticky="ew")
    zf = ttk.Frame(pb)
    zf.grid(row=0, column=1, padx=2)
    ttk.Label(zf, text="Z (nm)", font=("Arial", 9)).pack(side="left")
    ttk.Entry(zf, textvariable=z_var, width=6).pack(side="left", padx=2)
    ttk.Button(pb, text="Step closer", command=lambda: on_step(+1)).grid(
        row=0, column=2, padx=2, pady=1, sticky="ew")

    slider_var = tk.DoubleVar(value=rig.piezo_v)
    slide = {"dragging": False}
    target_lbl = ttk.Label(pb, text="", font=("Arial", 9))

    def on_slide(value):
        v = float(value)
        target_lbl.config(text=f"slider {v:.3f} V = {C.piezo_volts_to_nm(v):.1f} nm"
                               + ("   (release to move)" if slide["dragging"] else ""))
        if slide["dragging"]:
            # Igor's readouts kept ticking under a held mouse. Tk's timers
            # should too, but a drag floods the event queue with motion
            # events, so drive the refresh from the drag itself: every
            # 150 ms of dragging, one pass of the window's heartbeat and a
            # repaint, same as the timer would have done.
            if time.monotonic() - live.get("last_poll", 0.0) > 0.15:
                poll_body()
                root.update_idletasks()

    # The classic Tk scale, not the themed one: it has a knob you can see,
    # a 1 mV resolution when dragged, a 0.1 V step for a click beside the
    # knob (the themed scale jumped a whole volt per click), the value shown
    # over the knob and a tick every volt, which is what Igor's looked like.
    scale = tk.Scale(pb, from_=lo_v, to=hi_v, orient="horizontal",
                     variable=slider_var, command=on_slide, length=px(360),
                     resolution=0.001, bigincrement=0.1, tickinterval=1.0,
                     showvalue=True, sliderlength=18, font=("Arial", 9))
    scale.grid(row=1, column=0, columnspan=3, sticky="ew", padx=4, pady=(6, 0))
    target_lbl.grid(row=2, column=0, columnspan=3, sticky="w", padx=4)

    def on_press(_e):
        slide["dragging"] = True

    def on_release(_e):
        slide["dragging"] = False
        v = float(slider_var.get())
        if not hand_move("goto", v):
            slider_var.set(rig.piezo_v)         # put it back where the piezo is
        on_slide(slider_var.get())
    def on_drag(_e):
        # The same refresh as on_slide's, from the motion event itself, in
        # case the platform does not call the scale's -command mid-drag.
        if slide["dragging"] and time.monotonic() - live.get("last_poll", 0.0) > 0.15:
            poll_body()
            root.update_idletasks()
    scale.bind("<ButtonPress-1>", on_press, add="+")
    scale.bind("<B1-Motion>", on_drag, add="+")
    scale.bind("<ButtonRelease-1>", on_release, add="+")

    rof = ttk.Frame(pb)
    rof.grid(row=3, column=0, columnspan=3, sticky="ew", padx=2, pady=(3, 1))
    big: dict[str, tk.Label] = {}
    for col, (key, title) in enumerate((("i", "I (uA)"), ("v", "V (mV)"),
                                        ("p", "Piezo (V)"), ("s", "Sense (V)"))):
        cell = ttk.Frame(rof, relief="groove", borderwidth=1)
        cell.grid(row=0, column=col, padx=2, sticky="ew")
        rof.columnconfigure(col, weight=1)
        ttk.Label(cell, text=title, font=("Arial", 9)).pack()
        big[key] = tk.Label(cell, text="--", font=("Courier", 12, "bold"), width=9)
        big[key].pack()
    bkgd_var = tk.BooleanVar(value=True)
    beep_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(pb, text="background sampling while idle (Igor: Beep is ON)",
                    variable=bkgd_var).grid(row=4, column=0, columnspan=2,
                                            sticky="w", padx=2)
    ttk.Checkbutton(pb, text="beep at the contact current",
                    variable=beep_var).grid(row=4, column=2, sticky="w", padx=2)

    def show_big(i_ua, v_mv, piezo_v, sense_v, beep_ok: bool = False):
        big["i"].config(text=f"{i_ua:9.4f}" if np.isfinite(i_ua) else "--")
        big["v"].config(text=f"{v_mv:8.2f}" if np.isfinite(v_mv) else "--")
        big["p"].config(text=f"{piezo_v:7.4f}")
        big["s"].config(text=f"{sense_v:7.4f}" if sense_v is not None else "none")
        if not slide["dragging"]:
            slider_var.set(piezo_v)             # the slider follows every move
            on_slide(piezo_v)
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
    shown = [row for row in SETTINGS if row[0] != "ramp.smash_every"]
    per_col = (len(shown) + 1) // 2
    for i, (path, label, igor, unit, kind, scale_) in enumerate(shown):
        r, c = i % per_col, (i // per_col) * 2
        ttk.Label(sb, text=f"{label} ({unit})" if unit else label,
                  font=("Arial", 9)).grid(row=r, column=c, sticky="w", padx=(6, 2),
                                          pady=1)
        value = _get(cfg, path) * scale_
        var = svars.setdefault(path, tk.StringVar(value=f"{value:g}"))
        ent = ttk.Entry(sb, textvariable=var, width=9)
        ent.grid(row=r, column=c + 1, padx=2, pady=1, sticky="w")
        ent.bind("<Return>", lambda _e: apply_settings())
        ent.bind("<FocusOut>", lambda _e: apply_settings())
    req_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(sb, text="require engaged start (Igor: off)",
                    variable=req_var,
                    command=lambda: setattr(worker, "require_engaged",
                                            req_var.get())).grid(
        row=per_col, column=0, columnspan=2, sticky="w", padx=6, pady=(6, 0))
    ttk.Button(sb, text="Apply", command=lambda: apply_settings()).grid(
        row=per_col, column=2, sticky="w", padx=2, pady=(6, 0))
    # The safety check, in its own box and large. Every value is tried on a
    # copy of the config as it is typed -- green when it would be accepted,
    # red with the reason when not -- and applied on Enter, Apply or
    # leaving the box.
    cb = ttk.LabelFrame(sb, text="Safety check")
    cb.grid(row=per_col + 1, column=0, columnspan=4, sticky="ew", padx=4,
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
        if "ramp.bias_v" in changes:
            worker.bias_dirty = True
        worker.send("newfile")                     # the config travels with the data
        names = ", ".join(labels[p] for p in changes)
        if warnings:
            verdict(f"applied {names}; warning: " + " | ".join(warnings), "#b06000")
        else:
            verdict(f"applied {names}", "#006000")
        return True

    for var in svars.values():
        var.trace_add("write", preview_settings)

    # -- saving: one experiment per Start N -----------------------------------------
    # <data folder>/<date>/<your name>/<experiment>_<HHMMSS>_<N>traces.*
    # Name, experiment, folder and the boxes are remembered between launches.
    fb = ttk.Frame(nb)
    nb.add(fb, text="Saving")
    remembered = load_saving(saving_file)
    folder_var = tk.StringVar(value=str(remembered.get("folder") or out_dir))
    name_var = tk.StringVar(value=remembered.get("name", ""))
    exp_var = tk.StringVar(value=remembered.get("experiment", ""))
    notes_var = tk.StringVar(value=remembered.get("notes", ""))
    txt_var = tk.BooleanVar(value=bool(remembered.get("txt", False)))
    igor_var = tk.BooleanVar(value=bool(remembered.get("igor", igor_export)))
    save_var = tk.BooleanVar(value=True)

    ttk.Label(fb, text="Data folder").grid(row=0, column=0, sticky="w", padx=2, pady=(4, 1))
    ttk.Entry(fb, textvariable=folder_var, width=36).grid(
        row=0, column=1, sticky="ew", padx=2, pady=(4, 1))

    def browse_folder():
        chosen = filedialog.askdirectory(initialdir=folder_var.get() or str(out_dir),
                                         title="data folder (the date and your "
                                               "name are added under it)")
        if chosen:
            folder_var.set(chosen)
    ttk.Button(fb, text="Browse...", command=browse_folder).grid(
        row=0, column=2, padx=2, pady=(4, 1), sticky="ew")
    ttk.Label(fb, text="Your name").grid(row=1, column=0, sticky="w", padx=2, pady=1)
    ttk.Entry(fb, textvariable=name_var, width=36).grid(row=1, column=1, sticky="ew", padx=2)
    ttk.Label(fb, text="Experiment").grid(row=2, column=0, sticky="w", padx=2, pady=1)
    ttk.Entry(fb, textvariable=exp_var, width=36).grid(row=2, column=1, sticky="ew", padx=2)
    ttk.Label(fb, text="Notes").grid(row=3, column=0, sticky="w", padx=2, pady=1)
    ttk.Entry(fb, textvariable=notes_var, width=36).grid(
        row=3, column=1, columnspan=2, sticky="ew", padx=2)
    ttk.Label(fb, text="experiment: e.g. clean_gold, OPE3_1mM, changed any time, the "
                       "next Start N uses it. Notes: molecule, solvent, tip, sample; "
                       "they go into the file header and into experiment_log.csv in "
                       "the data folder, one row per run, every day",
              font=("Arial", 9), foreground="#444", wraplength=px(560), justify="left").grid(
        row=4, column=0, columnspan=3, sticky="w", padx=2)

    ttk.Checkbutton(fb, text="save accepted traces (.h5, raw volts + config; always "
                             "the master file)", variable=save_var,
                    command=lambda: setattr(worker, "save", save_var.get())).grid(
        row=5, column=0, columnspan=3, sticky="w", padx=2, pady=(6, 0))
    ttk.Checkbutton(fb, text="also write Igor .ibw blocks when the run ends",
                    variable=igor_var,
                    command=lambda: setattr(worker, "igor_export", igor_var.get())).grid(
        row=6, column=0, columnspan=3, sticky="w", padx=2)
    ttk.Checkbutton(fb, text="also write a .txt table when the run ends "
                             "(nm, then one G/G0 column per trace)",
                    variable=txt_var).grid(row=7, column=0, columnspan=3,
                                           sticky="w", padx=2)
    next_lbl = tk.Label(fb, text="", font=("Arial", 9), anchor="w", justify="left",
                        wraplength=px(560))
    next_lbl.grid(row=8, column=0, columnspan=3, sticky="w", padx=2, pady=(4, 0))
    file_lbl = tk.Label(fb, text="no run in progress", font=("Arial", 9), anchor="w",
                        wraplength=px(560), justify="left")
    file_lbl.grid(row=9, column=0, columnspan=3, sticky="w", padx=2)

    def saving_now() -> dict:
        return {"folder": Path(folder_var.get().strip() or str(out_dir)),
                "name": name_var.get(), "experiment": exp_var.get(),
                "notes": notes_var.get(),
                "txt": txt_var.get(), "igor": igor_var.get()}

    def show_next():
        worker.saving.update(saving_now())
        folder, stem = worker.experiment_paths()
        rel = Path(*folder.parts[-2:]) if len(folder.parts) >= 2 else folder
        next_lbl.config(text=f"next Start N: {rel}{os.sep}{stem}_<N>traces.h5"
                             + (" + .ibw" if igor_var.get() else "")
                             + (" + .txt" if txt_var.get() else "")
                             + "  (under the data folder)")
    for var in (folder_var, name_var, exp_var, notes_var, txt_var, igor_var):
        var.trace_add("write", lambda *_a: show_next())
    show_next()

    # -- a saved session, at the bottom of the Saving tab ---------------------------
    bb = ttk.LabelFrame(fb, text="A saved session: browse its traces, plot its histograms")
    bb.grid(row=10, column=0, columnspan=3, sticky="ew", padx=2, pady=(6, 2))
    browse = {"session": None, "path": None, "n": 0, "hist": None}
    idx_var = tk.StringVar(value="0")

    def open_file():
        path = filedialog.askopenfilename(initialdir=folder_var.get() or str(out_dir),
                                          filetypes=[("session", "*.h5")])
        if not path:
            return
        writer = worker.writer
        if writer is not None and Path(path).resolve() == Path(writer.path).resolve():
            set_status("that file is still being written (a run is in "
                               "progress or paused); open it when the run has ended")
            return
        if browse["session"] is not None:
            browse["session"].close()
            browse.update(session=None, path=None, n=0, hist=None)
        try:
            s = storage.Session(path)
        except Exception as exc:                 # noqa: BLE001
            set_status(f"could not open {Path(path).name}: {exc}")
            return
        if len(s) == 0:
            s.close()
            set_status(f"{Path(path).name} holds no traces")
            blbl.config(text=f"{Path(path).name}: 0 traces")
            return
        browse.update(session=s, path=path, n=len(s), hist=None)
        idx_var.set("0")
        blbl.config(text=f"{Path(path).name}: {len(s)} traces")
        show_saved()

    def show_saved(delta: int = 0):
        s = browse["session"]
        if s is None or browse["n"] == 0:
            return
        try:
            i = int(idx_var.get()) + delta
        except ValueError:
            i = 0
        i = max(0, min(i, browse["n"] - 1))
        idx_var.set(str(i))
        live["paused"] = True
        draw_saved(s, i)

    ttk.Button(bb, text="Open .h5 ...", command=open_file).grid(
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
        if browse["path"] is None:
            set_status("open a saved session first")
            return
        try:
            fig2, info = plots.figure_for_session(browse["path"],
                                                  int(idx_var.get()))
            out = Path(browse["path"]).with_name(
                f"{Path(browse['path']).stem}_trace{info['index']:04d}.png")
            fig2.savefig(out, dpi=110)
        except Exception as exc:                 # noqa: BLE001
            set_status(f"PNG not written: {exc}")
            return
        set_status(f"wrote {out}")
    ttk.Button(bb, text="Save PNG of trace", command=save_png).grid(
        row=1, column=0, padx=2, pady=1, sticky="ew")
    ttk.Button(bb, text="Plot 1D histogram",
               command=lambda: open_hist_window("1d")).grid(
        row=1, column=1, columnspan=3, padx=2, pady=1, sticky="ew")
    ttk.Button(bb, text="Plot 2D histogram",
               command=lambda: open_hist_window("2d")).grid(
        row=1, column=4, columnspan=2, padx=2, pady=1, sticky="ew")
    blbl = tk.Label(bb, text="", font=("Arial", 9), anchor="w", wraplength=px(560),
                    justify="left")
    blbl.grid(row=2, column=0, columnspan=6, sticky="w", padx=2)

    def open_hist_window(kind: str):
        s = browse["session"]
        if s is None:
            set_status("open a saved session first (Open .h5 ...)")
            return
        win = tk.Toplevel(root)
        _light_window(win)
        win.title(f"{Path(browse['path']).name}: "
                  + ("1D histogram" if kind == "1d" else "2D histogram"))
        hist_window(win, s, Path(browse["path"]).stem, kind, tk, ttk,
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
                       "i": deque(maxlen=3000), "g": deque(maxlen=3000)}

    def monitor_wants_sample() -> bool:
        """Idle sampling runs for the Piezo box's readouts (its checkbox) or
        for an open Monitor window with its own box ticked."""
        if bkgd_var.get():
            return True
        win = mon_state["win"]
        return (win is not None and win.winfo_exists()
                and mon_state["on"] is not None and mon_state["on"].get())

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
        ("trace", "trace", "nm", "log10 G/G0", "readback nm"),
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
            draw_saved(browse["session"], int(idx_var.get()))
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
        if live["paused"] and browse["session"] is not None:
            draw_saved(browse["session"], int(idx_var.get()))
        else:
            live["dirty"] = True
            canvas.draw_idle()

    def pull_frame(cyc):
        """The default x range of the record panel: the pull, with a little
        of the hold before it, or None for the whole cycle when no pull has
        happened yet. The data behind the panel are always the whole cycle,
        so the Axis limits window can widen the view."""
        if "pull" in cyc.marks and "end" in cyc.marks:
            t0, t1 = cyc.marks["pull"], cyc.marks["end"]
            pad = 0.1 * max(t1 - t0, 1e-3)
            return (t0 - pad, t1 + pad)
        return None

    def draw_live():
        cyc, tr, hist = live["cycle"], live["trace"], live["hist"]
        if cyc is not None and cyc.rec_t:
            frame = pull_frame(cyc)
            plots.plot_record_series(ax["record"], cfg, np.array(cyc.rec_t),
                                     np.array(cyc.rec_v), np.array(cyc.rec_i),
                                     marks=cyc.marks, frame=frame,
                                     title="this cycle: junction V and current"
                                           + (" (framed on the pull)" if frame
                                              else ""))
        if tr is not None and tr.get("record") is not None:
            rec = tr["record"]
            plots.plot_trace(ax["trace"], cfg, tr["g0"], tr["disp"], tr["verdict"],
                             title=f"trace {worker.attempts}",
                             sense_v=rec.piezo_sense_v)
        if cyc is not None and cyc.t:
            plots.plot_piezo(ax["piezo"], cfg, np.array(cyc.t), np.array(cyc.piezo_v),
                             np.array(cyc.sense_v), marks=cyc.marks,
                             title="piezo in and out, this cycle")
        if hist is not None and hist["counts"] is not None:
            plots.plot_histogram(ax["hist"], cfg, hist["centres"], hist["counts"],
                                 hist["n"])
        elif hist is not None:
            ax["hist"].clear()
            ax["hist"].set_title("histogram: 0 traces (new experiment)", fontsize=9)
        apply_limits()
        canvas.draw_idle()

    def draw_saved(s: storage.Session, i: int):
        scfg = s.cfg
        voltage, current = s.raw(i)
        g0 = s.conductance(i)
        fs = float(s.scalar("sample_rate_hz")[i])
        start_v = float(s.scalar("start_piezo_v")[i])
        disp = analysis.displacement_nm(voltage.size, scfg.ramp, fs)
        verdict = analysis.select_trace(g0, scfg.ramp)
        sense = s.piezo_sense(i, in_nm=False)
        plots.plot_record(ax["record"], scfg, np.stack([voltage, current]), fs,
                          title=f"saved trace {i}: junction V and current "
                                f"(the file keeps the trace only)")
        plots.plot_trace(ax["trace"], scfg, g0, disp, verdict,
                         title=f"saved trace {i}", sense_v=sense)
        t = np.arange(voltage.size) / fs
        cmd = start_v - scfg.cal.nm_to_piezo_volts(disp)
        plots.plot_piezo(ax["piezo"], scfg, t, cmd, sense,
                         title="piezo during the saved pull")
        if browse["hist"] is None:
            browse["hist"] = analysis.log_histogram(s.conductances())
        plots.plot_histogram(ax["hist"], scfg, *browse["hist"], browse["n"],
                             title="histogram of the file")
        banner.config(text=f"BROWSING {Path(browse['path']).name} trace {i}; "
                           f"live plots paused")
        apply_limits()
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
                    f"accepted  {p['accepted']} / {p['attempts']}, {p['saved']} saved",
                ]
                lines = [f"{a:<27}{b}" for a, b in zip(left_col, right_col)]
                lines.append(f"file      {live.get('file') or 'none open'}")
                lines.append(f"keithley  {keithley_line()}")
                set_text(ro, "\n".join(lines))
                show_big(p["current_ua"], p["junction_mv"], p["piezo_v"],
                         p["sense_v"])
            elif kind == "approach":
                live["cycle"] = p["cycle"]
                if live_moving.get():
                    live["dirty"] = True       # else: wait for the pull
            elif kind == "moved":
                # A move made by hand is its own event: the piezo and record
                # panels show it at once, whatever "redraw while moving" says.
                live["cycle"] = p["cycle"]
                live["dirty"] = True
            elif kind == "keithley":
                show_keithley(p)
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
                live["file"] = Path(p["path"]).name
                file_lbl.config(text=f"writing {live['file']}: {p['n']} traces")
            elif kind == "exported":
                pass
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
                show_big(i * 1e6, v * 1e3, p["piezo_v"], p["sense_v"], beep_ok=True)
        if worker.busy and worker.current not in QUIET:
            # Igor's slider and readouts followed every write. While a
            # command runs, follow the tracker and the last play's record,
            # so the slider walks up the staircase and down the pull and
            # the readouts show the junction closing, as Igor's did.
            cyc = mon.snapshot()
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
            show_big(i_ua, v_mv, rig.piezo_v, sense_v)
            # A heartbeat on the status line, so a two-minute approach with
            # the plots standing still does not look like a frozen window.
            if live.get("busy_since") is None:
                live["busy_since"] = time.monotonic()
            elapsed = time.monotonic() - live["busy_since"]
            working(True, f"WORKING: {worker.current} running {elapsed:.0f} s -- "
                          f"do not touch the rig; Stop ends it between steps. "
                          f"piezo {rig.piezo_v:.3f} V, junction {v_mv:.1f} mV, "
                          f"{i_ua:.3f} uA")
        else:
            live["busy_since"] = None
            if status2.cget("text"):
                working(False)
        if (monitor_wants_sample() and not worker.busy and worker.commands.empty()
                and time.monotonic() - mon_state["last"] > 0.3):
            mon_state["last"] = time.monotonic()
            worker.send("monitor")
        if live["dirty"] and not live["paused"]:
            draw_live()
            live["dirty"] = False
            banner.config(text="", fg="#b06000")
        elif worker.busy and not live["paused"] and live_moving.get():
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
                                     title="piezo in and out, this cycle (live)")
                    if cyc.rec_t:
                        plots.plot_record_series(
                            ax["record"], cfg, np.array(cyc.rec_t),
                            np.array(cyc.rec_v), np.array(cyc.rec_i),
                            marks=cyc.marks,
                            title="this cycle: junction V and current (live)")
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
    root.after(150, poll)
    if readback:
        root.after(400, open_readback)
    if autoclose is not None:
        root.after(300, lambda: worker.send("zero"))
        root.after(400, lambda: (name_var.set("smoke"), exp_var.set("clean gold"),
                                 txt_var.set(True)))
        root.after(600, on_run)
        root.after(900, open_limits)                 # smoke test: it must open
        root.after(950, open_monitor)
        root.after(1200, lambda: (limits.update(
            trace={"x": (-0.5, 3.0), "y": (-7.0, 1.0), "y2": None}), redraw_now()))
        root.after(3000, lambda: (lim_state["win"].destroy(),   # and close again
                                  mon_state["win"].destroy()))
        # The Settings tab: a refused value and an accepted one, previewed.
        root.after(4500, lambda: (nb.select(sb), left_canvas.yview_moveto(1.0),
                                  svars["ramp.bias_v"].set("900")))
        root.after(6500, lambda: svars["ramp.bias_v"].set("150"))
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
                        "used, else data/); the date and your name are "
                        "added under it")
    p.add_argument("--no-igor", action="store_true",
                   help="do not write Igor .ibw blocks when a file closes")
    p.add_argument("--require-engaged", action="store_true",
                   help="also require each trace to start in contact")
    p.add_argument("--headless", type=int, metavar="N",
                   help="no window: zero, then N cycles, save, export, report")
    p.add_argument("--test-pull", type=float, metavar="VOLTS",
                   help="headless: instead of cycles, N pulls from this piezo "
                        "voltage with no approach and no contact (a rig with "
                        "no tip)")
    p.add_argument("--readback", action="store_true",
                   help="GUI: open the readback-only window at start")
    p.add_argument("--save-test-pulls", action="store_true",
                   help="headless with --test-pull: also save them to a "
                        "TESTPULLS .h5 and export it for Igor (format test)")
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
        if args.headless is not None:
            return run_headless(cfg, args.headless, args.out or _ROOT / "data",
                                not args.no_igor,
                                args.require_engaged, test_pull_v=args.test_pull,
                                save_test_pulls=args.save_test_pulls)
        # The smoke run keeps its remembered settings in its own folder so
        # it never pre-fills a real session's Saving tab.
        saving_file = (args.out / "pullout_saving.json"
                       if args.autoclose is not None and args.out is not None
                       else _ROOT / "data" / "pullout_saving.json")
        out = args.out or Path(load_saving(saving_file).get("folder")
                               or _ROOT / "data")
        return run_gui(cfg, out, not args.no_igor,
                       args.config.name if args.config else "defaults",
                       autoclose=args.autoclose, readback=args.readback,
                       saving_file=saving_file, zoom=args.zoom)
    except (ConfigError, SafetyViolation) as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.info("interrupted; outputs parked")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
