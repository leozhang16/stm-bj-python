"""Approach and pull, one cycle at a time, with every picture that matters.

    python rigtests/02_approach_pull.py --simulate
    python rigtests/02_approach_pull.py --config configs/labpc_rig.json
    python rigtests/02_approach_pull.py --config configs/labpc_rig.json --headless 20

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

plus three more on request, each a checkbox ("also show") or ``--show``:

    gold level      G vs displacement, linear 0..5 (AuAuConductanceLevel):
                    the single-atom plateau as a flat step at exactly 1
    approach        conductance at each approach step vs piezo position:
                    where the junction closed
    I-V             current against junction voltage for the pull

Accepted traces are saved to the package's HDF5 session file as raw volts
(``storage.SessionWriter``), and can be exported as Igor binary waves in the
layout Igor's SavePullOut used, so Igor opens them. A saved session can be
browsed in the same plots.

The Piezo box is Igor's PiezoGroupbox: a slider over the piezo's whole
voltage range (applies when the mouse is released, as Igor's did), Step
closer / Step apart by Z nm, and under them Igor's readouts -- I (uA),
V (mV), Piezo (V) and the sense line -- refreshed every 0.3 s while the rig
is idle by the same quiet 10 ms hold the Monitor window uses (Igor's
Background Sampling), with Igor's beep above 0.15 uA. A move made by hand
is ramped over 50 ms, then the junction is probed: in contact, the state
becomes ENGAGED and Pull once works from there; Approach + pull and Run N
start from wherever the slider left the tip.

WHAT THIS DOES NOT DO: the coarse approach. Bring the tip within the fine
piezo's reach (620 nm) by hand or with Igor's actuator controls first. When
this program starts it parks the piezo at 0 V, so whatever extension Igor
left is undone; the approach (or the slider) then extends the piezo until
contact. Close Igor's DAQ tasks (or Igor) before starting, or the card will
be busy.
"""

from __future__ import annotations

import argparse
import copy
import logging
import queue
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from stmlab import analysis, approach, calibrate, storage, trace   # noqa: E402
from stmlab.approach import ApproachError                           # noqa: E402
from stmlab.config import ConfigError, G0_SIEMENS, RigConfig, validate   # noqa: E402
from stmlab.instrument import Rig                                   # noqa: E402
from stmlab.safety import RigState, SafeSession, SafetyViolation    # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plots                                                        # noqa: E402

log = logging.getLogger("rigtests.approach_pull")

# Shown in the window title and by --version, so a patch can say which
# version it applies to and you can see which one you have.
__version__ = "v24"


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
    monitor. ``stop`` interrupts a run between cycles."""

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

    # -- posting ------------------------------------------------------------

    def post(self, kind: str, **payload) -> None:
        self.events.put((kind, payload))

    def status(self, text: str) -> None:
        self.post("status", text=text)

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
        self.close_file()

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

    # -- moves made by hand: the slider and the step buttons ----------------------

    def cmd_goto(self, volts: float) -> None:
        """Igor's SetPiezoBiasFromSlider: put the piezo at ``volts``.

        Ramped over 50 ms rather than jumped, then the junction is probed and
        the state follows what it reads, so a contact made by hand can be
        pulled from with Pull once, as Igor's slider-then-measure could.
        Approach + pull and Run N need no state: they separate first.
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
        self.status("approaching ...")
        state = approach.engage(self.rig)
        self.mon.mark("contact")
        self.post("approach", cycle=self.mon.snapshot())
        self.status(f"engaged at {self.rig.piezo_v:.4f} V = "
                    f"{self.rig.piezo_nm:.1f} nm")
        return state

    def cmd_pull(self) -> None:
        """One pull from wherever the piezo is (after an engage)."""
        if self.rig.state is not RigState.ENGAGED:
            self.status("not engaged: press Approach first")
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

    def cmd_run(self, n: int) -> None:
        self.stop_flag.clear()
        done = 0
        R = self.cfg.ramp
        while done < n and not self.stop_flag.is_set():
            if R.smash_every and self.attempts and \
                    self.attempts % R.smash_every == 0:
                self.status("smashing the tip")
                approach.smash(self.rig)
            try:
                self._engage()
            except ApproachError as exc:
                self.post("error", text=f"approach: {exc}", fatal=False)
                break
            verdict = self._pull()
            if verdict is not None and verdict.accepted:
                done += 1
            self.readout()
        self.status(f"run finished: {self.accepted} accepted in "
                    f"{self.attempts} attempts; rejected {self.rejections}")

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
        if self.writer is not None and self.writer_is_test != test:
            self.close_file()
        if self.writer is None:
            tag = "rigtest02_TESTPULLS" if test else "rigtest02"
            path = self.out_dir / f"{tag}_{time.strftime('%Y%m%d_%H%M%S')}.h5"
            self.writer = storage.SessionWriter(path, self.cfg).open()
            self.writer_is_test = test
            self.file_traces = []
            self.post("file", path=str(path))
        self.writer.append(self.n_saved, tr, verdict)
        self.n_saved += 1
        self.file_traces.append((tr.conductance_g0(self.cfg).astype(np.float32),
                                 tr.start_piezo_v, tr.timestamp))
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
        self.close_file()
        self.status("session file closed; the next accepted trace opens a new one")

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
        rig = Rig(cfg).open()
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
# The window
# --------------------------------------------------------------------------

def run_gui(cfg: RigConfig, out_dir: Path, igor_export: bool,
            config_name: str, autoclose: float | None = None,
            readback: bool = False, show: set | None = None) -> int:
    show = set(show or ())            # extra panels ticked at start
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
    worker.start()

    root = tk.Tk()
    root.title(f"rigtests 02: approach and pull  {__version__}" +
               ("  [simulate]" if cfg.simulate else f"  [{cfg.channels.device}]")
               + f"  {config_name}")

    outer = ttk.Frame(root)
    outer.pack(fill="both", expand=True, padx=6, pady=6)
    left = ttk.Frame(outer)
    left.pack(side="left", fill="y", padx=(0, 8))
    right = ttk.Frame(outer)
    right.pack(side="right", fill="both", expand=True)

    # -- run ---------------------------------------------------------------------
    rb = ttk.LabelFrame(left, text="Run")
    rb.pack(fill="x", pady=(0, 6))
    n_var = tk.StringVar(value="10")
    ttk.Button(rb, text="Calibrate zero", command=lambda: worker.send("zero")).grid(
        row=0, column=0, padx=2, pady=2, sticky="ew")
    ttk.Button(rb, text="Approach", command=lambda: worker.send("engage")).grid(
        row=0, column=1, padx=2, pady=2, sticky="ew")
    ttk.Button(rb, text="Pull once", command=lambda: worker.send("pull")).grid(
        row=0, column=2, padx=2, pady=2, sticky="ew")
    ttk.Button(rb, text="Approach + pull", command=lambda: worker.send("cycle")).grid(
        row=1, column=0, padx=2, pady=2, sticky="ew")

    def on_run():
        try:
            worker.send("run", max(1, int(n_var.get())))
        except ValueError:
            pass
    ttk.Button(rb, text="Run N", command=on_run).grid(row=1, column=1, padx=2,
                                                      pady=2, sticky="ew")
    ttk.Entry(rb, textvariable=n_var, width=6).grid(row=1, column=2, padx=2)
    ttk.Button(rb, text="Stop", command=worker.stop_flag.set).grid(
        row=2, column=0, padx=2, pady=2, sticky="ew")
    ttk.Button(rb, text="Withdraw", command=lambda: worker.send("withdraw")).grid(
        row=2, column=1, padx=2, pady=2, sticky="ew")
    ttk.Button(rb, text="Smash", command=lambda: worker.send("smash")).grid(
        row=2, column=2, padx=2, pady=2, sticky="ew")
    tp_var = tk.StringVar(value="5.0")

    def on_testpull():
        try:
            worker.send("testpull", float(tp_var.get()))
        except ValueError:
            pass
    ttk.Button(rb, text="Test pull, no contact, from (V):",
               command=on_testpull).grid(row=3, column=0, columnspan=2, padx=2,
                                         pady=2, sticky="ew")
    ttk.Entry(rb, textvariable=tp_var, width=6).grid(row=3, column=2, padx=2)

    ro = tk.Text(rb, width=38, height=10, font=("Courier", 9), relief="flat",
                 state="disabled", background=root.cget("background"))
    ro.grid(row=4, column=0, columnspan=3, sticky="ew", padx=2, pady=(4, 2))

    def set_text(widget, text):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.config(state="disabled")

    # -- piezo: Igor's PiezoGroupbox, with Igor's readouts under it -----------------
    # Step apart / Z (nm) / Step closer, a slider over the piezo's whole
    # range that applies on mouse release (Igor's SetPiezoBiasFromSlider,
    # live=0), and the readouts Igor kept at the bottom of its panel:
    # I (uA), V (mV), Piezo, plus the sense line this rig has. They are
    # refreshed by every command and, while idle, every 0.3 s by a quiet
    # hold (Igor's Background Sampling) with Igor's beep above 0.15 uA.
    C = cfg.cal
    BEEP_UA = 0.15
    pb = ttk.LabelFrame(left, text="Piezo (Igor's piezo controls)")
    pb.pack(fill="x", pady=(0, 6))
    lo_v, hi_v = cfg.limits.piezo_ao_min_v, cfg.limits.piezo_ao_max_v
    z_var = tk.StringVar(value=f"{cfg.ramp.approach_step_nm:g}")

    QUIET = ("monitor", "noop")      # commands that do not count as busy

    def rig_is_free() -> bool:
        """Nothing but idle sampling is running or queued."""
        return ((not worker.busy or worker.current in QUIET)
                and all(c[0] in QUIET for c in list(worker.commands.queue)))

    def hand_move(*command) -> bool:
        """Send a move made by hand, unless a command is already running:
        a slider release in the middle of Run N must not queue up behind it."""
        if not rig_is_free():
            status.config(text="busy: wait for the current command to finish, "
                               "or press Stop")
            return False
        worker.send(*command)
        return True

    def on_step(sign: int):
        try:
            nm = abs(float(z_var.get()))
        except ValueError:
            status.config(text=f"Z: '{z_var.get()}' is not a number")
            return
        hand_move("step", sign * nm)

    ttk.Button(pb, text="Step apart", command=lambda: on_step(-1)).grid(
        row=0, column=0, padx=2, pady=2, sticky="ew")
    zf = ttk.Frame(pb)
    zf.grid(row=0, column=1, padx=2)
    ttk.Label(zf, text="Z (nm)", font=("Arial", 9)).pack(side="left")
    ttk.Entry(zf, textvariable=z_var, width=6).pack(side="left", padx=2)
    ttk.Button(pb, text="Step closer", command=lambda: on_step(+1)).grid(
        row=0, column=2, padx=2, pady=2, sticky="ew")

    slider_var = tk.DoubleVar(value=rig.piezo_v)
    slide = {"dragging": False}
    target_lbl = ttk.Label(pb, text="", font=("Arial", 8))

    def on_slide(value):
        v = float(value)
        target_lbl.config(text=f"slider {v:.3f} V = {C.piezo_volts_to_nm(v):.1f} nm"
                               + ("   (release to move)" if slide["dragging"] else
                                  f"   (range {lo_v:g} to {hi_v:g} V)"))

    scale = ttk.Scale(pb, from_=lo_v, to=hi_v, orient="horizontal",
                      variable=slider_var, command=on_slide, length=300)
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
    scale.bind("<ButtonPress-1>", on_press)
    scale.bind("<ButtonRelease-1>", on_release)

    rof = ttk.Frame(pb)
    rof.grid(row=3, column=0, columnspan=3, sticky="ew", padx=2, pady=(6, 2))
    big: dict[str, tk.Label] = {}
    for col, (key, title) in enumerate((("i", "I (uA)"), ("v", "V (mV)"),
                                        ("p", "Piezo (V)"), ("s", "Sense (V)"))):
        cell = ttk.Frame(rof, relief="groove", borderwidth=1)
        cell.grid(row=0, column=col, padx=2, sticky="ew")
        rof.columnconfigure(col, weight=1)
        ttk.Label(cell, text=title, font=("Arial", 8)).pack()
        big[key] = tk.Label(cell, text="--", font=("Courier", 13, "bold"), width=9)
        big[key].pack()
    bkgd_var = tk.BooleanVar(value=True)
    beep_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(pb, text="background sampling while idle (Igor: Beep is ON)",
                    variable=bkgd_var).grid(row=4, column=0, columnspan=2,
                                            sticky="w", padx=2)
    ttk.Checkbutton(pb, text=f"beep above {BEEP_UA:g} uA",
                    variable=beep_var).grid(row=4, column=2, sticky="w", padx=2)

    def show_big(i_ua, v_mv, piezo_v, sense_v, beep_ok: bool = False):
        big["i"].config(text=f"{i_ua:9.4f}" if np.isfinite(i_ua) else "--")
        big["v"].config(text=f"{v_mv:8.2f}" if np.isfinite(v_mv) else "--")
        big["p"].config(text=f"{piezo_v:7.4f}")
        big["s"].config(text=f"{sense_v:7.4f}" if sense_v is not None else "none")
        if not slide["dragging"]:
            slider_var.set(piezo_v)             # the slider follows every move
            on_slide(piezo_v)
        if beep_ok and beep_var.get() and np.isfinite(i_ua) and abs(i_ua) > BEEP_UA:
            root.bell()

    # The rest of the column is tabbed, as Igor's panel was, so that the Run
    # and Piezo boxes stay in view on a 900-pixel screen: Settings, Saving,
    # Browse.
    nb = ttk.Notebook(left)
    nb.pack(fill="both", expand=True)

    # -- settings --------------------------------------------------------------------
    sb = ttk.Frame(nb)
    nb.add(sb, text="Settings (checked before they apply)")
    svars: dict[str, tk.StringVar] = {}
    for row, (path, label, igor, unit, kind, scale) in enumerate(SETTINGS):
        ttk.Label(sb, text=f"{label} ({unit})" if unit else label,
                  font=("Arial", 9)).grid(row=row, column=0, sticky="w", padx=2)
        value = _get(cfg, path) * scale
        var = tk.StringVar(value=f"{value:g}")
        svars[path] = var
        ent = ttk.Entry(sb, textvariable=var, width=9)
        ent.grid(row=row, column=1, padx=2, pady=1)
        ent.bind("<Return>", lambda _e: apply_settings())
        ent.bind("<FocusOut>", lambda _e: apply_settings())
        ttk.Label(sb, text=igor, font=("Arial", 7), foreground="#666").grid(
            row=row, column=2, sticky="w", padx=2)
    req_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(sb, text="require engaged start (Igor: off)",
                    variable=req_var,
                    command=lambda: setattr(worker, "require_engaged",
                                            req_var.get())).grid(
        row=len(SETTINGS), column=0, columnspan=3, sticky="w", padx=2)
    ttk.Button(sb, text="Apply", command=lambda: apply_settings()).grid(
        row=len(SETTINGS) + 1, column=0, sticky="w", padx=2, pady=2)
    smsg = tk.Label(sb, text="", font=("Arial", 8), wraplength=300,
                    justify="left", anchor="w")
    smsg.grid(row=len(SETTINGS) + 1, column=1, columnspan=2, sticky="w")
    applied = {"values": {path: _get(cfg, path) for path, *_ in SETTINGS}}

    scales = {path: scale for path, *_rest, scale in SETTINGS}

    def apply_settings() -> bool:
        changes = {}
        for path, label, igor, unit, kind, scale in SETTINGS:
            raw = svars[path].get().strip()
            try:
                number = float(raw) / scale
            except ValueError:
                smsg.config(text=f"{label}: '{raw}' is not a number", fg="#b00000")
                return False
            value = int(round(number)) if kind is int else number
            if value != applied["values"][path]:
                changes[path] = value
        if not changes:
            return True
        problems, warnings = check_settings(cfg, changes)
        if problems:
            smsg.config(text="REFUSED: " + "; ".join(problems), fg="#b00000")
            for path in changes:                   # put the boxes back
                svars[path].set(f"{applied['values'][path] * scales[path]:g}")
            return False
        for path, value in changes.items():
            _set(cfg, path, value)
            applied["values"][path] = value
        if "ramp.bias_v" in changes:
            worker.bias_dirty = True
        worker.send("newfile")                     # the config travels with the data
        names = ", ".join(p.split(".")[-1] for p in changes)
        if warnings:
            smsg.config(text=f"applied {names}; warning: " + " | ".join(warnings),
                        fg="#b06000")
        else:
            smsg.config(text=f"applied {names}", fg="#006000")
        return True

    # -- saving ---------------------------------------------------------------------
    fb = ttk.Frame(nb)
    nb.add(fb, text="Saving")
    save_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(fb, text="save accepted traces (.h5, raw volts)",
                    variable=save_var,
                    command=lambda: setattr(worker, "save", save_var.get())).grid(
        row=0, column=0, columnspan=2, sticky="w", padx=2)
    igor_var = tk.BooleanVar(value=igor_export)
    ttk.Checkbutton(fb, text="also write Igor .ibw blocks when a file closes",
                    variable=igor_var,
                    command=lambda: setattr(worker, "igor_export", igor_var.get())).grid(
        row=1, column=0, columnspan=2, sticky="w", padx=2)
    tp_save_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(fb, text="save test pulls too, into a TESTPULLS file "
                             "(format test, not data)",
                    variable=tp_save_var,
                    command=lambda: setattr(worker, "save_test_pulls",
                                            tp_save_var.get())).grid(
        row=2, column=0, columnspan=2, sticky="w", padx=2)
    ttk.Button(fb, text="New file", command=lambda: worker.send("newfile")).grid(
        row=3, column=0, padx=2, pady=2, sticky="ew")
    ttk.Button(fb, text="Export Igor now", command=lambda: worker.send("export")).grid(
        row=3, column=1, padx=2, pady=2, sticky="ew")
    file_lbl = tk.Label(fb, text="no file open", font=("Arial", 8), anchor="w",
                        wraplength=300, justify="left")
    file_lbl.grid(row=4, column=0, columnspan=2, sticky="w", padx=2)

    # -- browse -----------------------------------------------------------------------
    bb = ttk.Frame(nb)
    nb.add(bb, text="Browse a saved session")
    browse = {"session": None, "path": None, "n": 0, "hist": None}
    idx_var = tk.StringVar(value="0")

    def open_file():
        path = filedialog.askopenfilename(initialdir=str(out_dir),
                                          filetypes=[("session", "*.h5")])
        if not path:
            return
        writer = worker.writer
        if writer is not None and Path(path).resolve() == Path(writer.path).resolve():
            status.config(text="that file is still being written: press New "
                               "file to close it, then open it")
            return
        if browse["session"] is not None:
            browse["session"].close()
            browse.update(session=None, path=None, n=0, hist=None)
        try:
            s = storage.Session(path)
        except Exception as exc:                 # noqa: BLE001
            status.config(text=f"could not open {Path(path).name}: {exc}")
            return
        if len(s) == 0:
            s.close()
            status.config(text=f"{Path(path).name} holds no traces")
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
        row=0, column=0, padx=2, pady=2, sticky="ew")
    ttk.Button(bb, text="<", width=3, command=lambda: show_saved(-1)).grid(
        row=0, column=1, padx=1)
    ttk.Entry(bb, textvariable=idx_var, width=6).grid(row=0, column=2, padx=1)
    ttk.Button(bb, text=">", width=3, command=lambda: show_saved(+1)).grid(
        row=0, column=3, padx=1)
    ttk.Button(bb, text="Show", command=lambda: show_saved(0)).grid(
        row=0, column=4, padx=2)
    ttk.Button(bb, text="Back to live",
               command=lambda: live.update(paused=False)).grid(
        row=1, column=0, padx=2, pady=2, sticky="ew")

    def save_png():
        if browse["path"] is None:
            status.config(text="open a saved session first")
            return
        try:
            fig2, info = plots.figure_for_session(browse["path"],
                                                  int(idx_var.get()))
            out = Path(browse["path"]).with_name(
                f"{Path(browse['path']).stem}_trace{info['index']:04d}.png")
            fig2.savefig(out, dpi=110)
        except Exception as exc:                 # noqa: BLE001
            status.config(text=f"PNG not written: {exc}")
            return
        status.config(text=f"wrote {out}")
    ttk.Button(bb, text="Save PNG of this trace", command=save_png).grid(
        row=1, column=1, columnspan=4, padx=2, pady=2, sticky="ew")
    blbl = tk.Label(bb, text="", font=("Arial", 8), anchor="w", wraplength=300,
                    justify="left")
    blbl.grid(row=2, column=0, columnspan=5, sticky="w", padx=2)

    # -- the plots --------------------------------------------------------------------
    # Four panels always: the record, the trace with the readback over it,
    # the piezo in and out, the histogram. Three more on request, each a
    # checkbox: the gold level (the trace on a linear axis), the approach
    # (G at each step against piezo position) and the pull's I-V. The
    # figure is laid out again whenever a box changes.
    top = ttk.Frame(right)
    top.pack(fill="x")
    ttk.Label(top, text="also show:").pack(side="left")
    extras = {key: tk.BooleanVar(value=key in show)
              for key in ("gold", "approach", "iv")}
    for key, text in (("gold", "gold level"), ("approach", "approach"),
                      ("iv", "I-V")):
        ttk.Checkbutton(top, text=text, variable=extras[key],
                        command=lambda: rebuild()).pack(side="left", padx=3)
    # Off by default, every panel redraws together once per trace, when the
    # pull is in; on, the record, piezo and approach panels also redraw
    # while a move is running (the staircase grows as you watch).
    live_moving = tk.BooleanVar(value=False)
    ttk.Checkbutton(top, text="redraw while moving", variable=live_moving).pack(
        side="left", padx=(16, 3))
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
        win.title("piezo readback: " + (cfg.channels.piezo_sense_path or "no sense line"))
        rb_state["win"] = win
        fig2 = Figure(figsize=(7.0, 3.8), dpi=100)
        ax_rb = fig2.add_subplot(111)
        fig2.tight_layout(pad=2.0)
        canvas2 = FigureCanvasTkAgg(fig2, master=win)
        canvas2.get_tk_widget().pack(fill="both", expand=True)
        note = ttk.Label(win, text="the sense line alone, this cycle, y axis "
                                   "fitted to the data; redraws while a move runs",
                         font=("Arial", 8))
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
    status = ttk.Label(root, text="", font=("Arial", 9), anchor="w")
    status.pack(fill="x", padx=8, pady=(0, 4))

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
        ("gold", "gold level", "nm", "G/G0", "junction mV"),
        ("approach", "approach", "piezo nm", "log10 G/G0", None),
        ("iv", "I-V", "junction mV", "current uA", None),
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
        msg = ttk.Label(win, text="", font=("Arial", 8))
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
                  font=("Arial", 8)).pack(side="left", padx=8)

    def redraw_now():
        if live["paused"] and browse["session"] is not None:
            draw_saved(browse["session"], int(idx_var.get()))
        else:
            draw_live()

    def rebuild():
        """Lay the figure out again: two columns of the main panels, then a
        column for every two extras ticked. Everything is redrawn into the
        new axes on the next poll (or at once while browsing)."""
        fig.clear()
        chosen = [k for k in ("gold", "approach", "iv") if extras[k].get()]
        ncols = 2 + (len(chosen) + 1) // 2
        # The figure keeps the canvas's size and the panels share it: with
        # extras ticked they get narrower, and maximising the window gives
        # them room. (Resizing the canvas from here left stale images of
        # the previous layout on screen.)
        grid = fig.subplots(2, ncols, squeeze=False)
        ax.clear()
        ax.update(record=grid[0, 0], trace=grid[0, 1],
                  piezo=grid[1, 0], hist=grid[1, 1])
        for i, key in enumerate(chosen):
            ax[key] = grid[i % 2, 2 + i // 2]
        used = set(id(a_) for a_ in ax.values())
        for col in range(2, ncols):
            for row in range(2):
                if id(grid[row, col]) not in used:
                    grid[row, col].set_visible(False)      # an odd slot
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
            if "gold" in ax:
                plots.plot_gold_level(ax["gold"], cfg, tr["g0"], tr["disp"],
                                      voltage_v=rec.voltage_v)
            if "iv" in ax:
                plots.plot_iv(ax["iv"], cfg, rec.voltage_v, rec.current_v)
        if cyc is not None and cyc.t:
            plots.plot_piezo(ax["piezo"], cfg, np.array(cyc.t), np.array(cyc.piezo_v),
                             np.array(cyc.sense_v), marks=cyc.marks,
                             title="piezo in and out, this cycle")
            if "approach" in ax and cyc.app_piezo_v:
                plots.plot_approach(ax["approach"], cfg, cyc.app_piezo_v,
                                    cyc.app_g0, cyc.app_railed)
        if hist is not None and hist["counts"] is not None:
            plots.plot_histogram(ax["hist"], cfg, hist["centres"], hist["counts"],
                                 hist["n"])
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
        if "gold" in ax:
            plots.plot_gold_level(ax["gold"], scfg, g0, disp, voltage_v=voltage)
        t = np.arange(voltage.size) / fs
        cmd = start_v - scfg.cal.nm_to_piezo_volts(disp)
        plots.plot_piezo(ax["piezo"], scfg, t, cmd, sense,
                         title="piezo during the saved pull")
        if browse["hist"] is None:
            browse["hist"] = analysis.log_histogram(s.conductances())
        plots.plot_histogram(ax["hist"], scfg, *browse["hist"], browse["n"],
                             title="histogram of the file")
        if "iv" in ax:
            plots.plot_iv(ax["iv"], scfg, voltage, current)
        if "approach" in ax:
            ax["approach"].clear()
            ax["approach"].set_title("approach: not stored in the file", fontsize=9)
        banner.config(text=f"BROWSING {Path(browse['path']).name} trace {i}; "
                           f"live plots paused")
        apply_limits()
        canvas.draw_idle()

    rebuild()

    def poll():
        drew = False
        while True:
            try:
                kind, p = worker.events.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                status.config(text=p["text"])
            elif kind == "error":
                status.config(text=p["text"])
                if p.get("fatal"):
                    banner.config(text="SAFETY STOP: see the status line; close "
                                       "and restart", fg="#b00000")
            elif kind == "readout":
                set_text(ro, (
                    f"state      {p['state']}\n"
                    f"piezo      {p['piezo_v']:7.4f} V = {p['piezo_nm']:7.1f} nm\n"
                    + (f"readback   {p['sense_nm']:7.1f} nm\n" if p['sense_nm'] is not None else "") +
                    f"bias       {p['bias_mv']:7.1f} mV\n"
                    f"junction   {p['junction_mv']:7.1f} mV\n"
                    f"current    {p['current_ua']:9.4f} uA"
                    + ("  RAILED" if p['railed'] else "") + "\n"
                    f"G          {p['g0']:.3e} G0\n"
                    f"zero       {p['zero_uv']:+.1f} uV\n"
                    f"accepted   {p['accepted']} / {p['attempts']} attempts, "
                    f"{p['saved']} saved\n"
                    f"file       {live.get('file') or 'none open'}"))
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
            elif kind == "cycle":
                live["cycle"] = p["cycle"]
                live["trace"] = p if p.get("record") is not None else None
                live["dirty"] = True
            elif kind == "hist":
                live["hist"] = p
                live["dirty"] = True
            elif kind == "file":
                live["file"] = Path(p["path"]).name if p["path"] else None
                file_lbl.config(text=f"writing {live['file']}" if p["path"]
                                else "no file open")
            elif kind == "saved":
                live["file"] = Path(p["path"]).name
                file_lbl.config(text=f"writing {live['file']}: {p['n']} traces")
            elif kind == "exported":
                pass
            elif kind == "monitor":
                rec = p["record"]
                M, C = cfg.channels, cfg.cal
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
                    if "approach" in ax and cyc.app_piezo_v:
                        plots.plot_approach(ax["approach"], cfg, cyc.app_piezo_v,
                                            cyc.app_g0, cyc.app_railed,
                                            title="approach (live)")
                    apply_limits()
                    canvas.draw_idle()
        if not live["paused"] and banner.cget("text").startswith("BROWSING"):
            banner.config(text="")
        root.after(150, poll)

    closed = {"done": False}

    def shutdown():
        if closed["done"]:
            return
        closed["done"] = True
        worker.stop_flag.set()
        worker.quit()
        worker.join(timeout=15)
        if browse["session"] is not None:
            browse["session"].close()
        close_rig(guard, rig)

    def on_close():
        try:
            shutdown()
        finally:
            root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)

    worker.send("noop")                              # first readout
    root.after(150, poll)
    if readback:
        root.after(400, open_readback)
    if autoclose is not None:
        root.after(300, lambda: worker.send("zero"))
        root.after(600, lambda: worker.send("run", 3))
        root.after(900, open_limits)                 # smoke test: it must open
        root.after(950, open_monitor)
        root.after(1200, lambda: (limits.update(
            gold={"x": (0.0, 2.0), "y": (0.0, 6.0), "y2": None}), redraw_now()))
        root.after(3000, lambda: (lim_state["win"].destroy(),   # and close again
                                  mon_state["win"].destroy()))
        for ms, key in ((4000, "gold"), (6000, "approach"), (8000, "iv")):
            root.after(ms, lambda k=key: (extras[k].set(True), rebuild()))
        # The Piezo box: a slider move and a step by hand, after the run.
        root.after(9000, lambda: worker.send("goto", 2.0))
        root.after(9500, lambda: worker.send("step", 0.5))
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
    p.add_argument("--out", type=Path, default=_ROOT / "data",
                   help="folder for session files (default: data/)")
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
    p.add_argument("--show", default="", metavar="PANELS",
                   help="GUI: extra panels ticked at start, any of "
                        "gold,approach,iv (default: none)")
    p.add_argument("--save-test-pulls", action="store_true",
                   help="headless with --test-pull: also save them to a "
                        "TESTPULLS .h5 and export it for Igor (format test)")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--autoclose", type=float, help=argparse.SUPPRESS)
    p.add_argument("--version", action="version",
                   version=f"rigtests 02 {__version__}")
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
            return run_headless(cfg, args.headless, args.out, not args.no_igor,
                                args.require_engaged, test_pull_v=args.test_pull,
                                save_test_pulls=args.save_test_pulls)
        show = {s.strip() for s in args.show.split(",") if s.strip()}
        unknown = show - {"gold", "approach", "iv"}
        if unknown:
            p.error(f"--show: unknown panel(s) {sorted(unknown)}; "
                    f"choose from gold, approach, iv")
        return run_gui(cfg, args.out, not args.no_igor,
                       args.config.name if args.config else "defaults",
                       autoclose=args.autoclose, readback=args.readback,
                       show=show)
    except (ConfigError, SafetyViolation) as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.info("interrupted; outputs parked")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
