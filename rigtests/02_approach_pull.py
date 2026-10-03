"""Approach and pull, one cycle at a time, with every picture that matters.

    python rigtests/02_approach_pull.py --simulate
    python rigtests/02_approach_pull.py --config configs/labpc_rig.json
    python rigtests/02_approach_pull.py --config configs/labpc_rig.json --headless 20

The fine-piezo approach and the constant-bias pull, exactly as the experiment
does them (``approach.engage`` and ``trace.single_trace``), driven by buttons
instead of a loop, with the settings Igor's Inputs tab had, each change
checked against the safety rules before it is accepted, and six live plots:

    record          junction V and current during the last play (Igor HighRes)
    trace           log G vs displacement, with the accept/reject verdict
    gold level      G vs displacement, linear 0..5 (AuAuConductanceLevel)
    piezo in/out    commanded position (and the readback) over the whole cycle
    histogram       counts per trace over the accepted traces so far
    approach / I-V  conductance at each approach step vs piezo position,
                    or current against junction voltage for the pull

Accepted traces are saved to the package's HDF5 session file as raw volts
(``storage.SessionWriter``), and can be exported as Igor binary waves in the
layout Igor's SavePullOut used, so Igor opens them. A saved session can be
browsed in the same plots.

WHAT THIS DOES NOT DO: the coarse approach. Bring the tip within the fine
piezo's reach (620 nm) by hand or with Igor's actuator controls first. When
this program starts it parks the piezo at 0 V, so whatever extension Igor
left is undone; the approach then extends the piezo until contact. Close
Igor's DAQ tasks (or Igor) before starting, or the card will be busy.
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
from stmlab.config import ConfigError, RigConfig, validate         # noqa: E402
from stmlab.instrument import Rig                                   # noqa: E402
from stmlab.safety import RigState, SafeSession, SafetyViolation    # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plots                                                        # noqa: E402

log = logging.getLogger("rigtests.approach_pull")


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
    if problems:
        return problems, []
    try:
        warnings = validate(trial)
    except ConfigError as exc:
        return [str(exc)], []
    return [], list(warnings)


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
    run (n), withdraw, smash. ``stop`` interrupts a run between cycles."""

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
        self.accepted = 0
        self.attempts = 0
        self.rejections: dict[str, int] = {}
        self.hist_sum = None
        self.hist_centres = None
        self.hist_n = 0
        self.bias_dirty = True                 # set_bias before the next cycle

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
            try:
                getattr(self, "cmd_" + name, self.cmd_noop)(*args)
            except SafetyViolation as exc:
                self.post("error", text=f"SAFETY: {exc}", fatal=True)
                self.stop_flag.set()
            except ApproachError as exc:
                self.post("error", text=f"approach: {exc}", fatal=False)
            except Exception as exc:                # noqa: BLE001
                log.exception("command %s failed", name)
                self.post("error", text=f"{name}: {type(exc).__name__}: {exc}",
                          fatal=False)
            finally:
                self.readout()
        self.close_file()

    def cmd_noop(self) -> None:
        return

    # -- the pieces of a cycle ---------------------------------------------------

    def cmd_zero(self) -> None:
        self.status("measuring the preamp zero at 0 V bias ...")
        zero = calibrate.measure_zero(self.rig)
        self.cfg.cal.current_zero_v = zero
        self.bias_dirty = True
        self.status(f"preamp zero {zero * 1e6:+.2f} uV, written into cal")
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
            self.status(f"test pull done (not saved, not counted); the "
                        f"selector would say: {verdict.reason}; alignment "
                        f"delay {tr.delay_samples} samples")
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

    def _save(self, tr, verdict) -> None:
        if self.writer is None:
            path = self.out_dir / f"rigtest02_{time.strftime('%Y%m%d_%H%M%S')}.h5"
            self.writer = storage.SessionWriter(path, self.cfg).open()
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
        self.post("readout", state=rig.state.name, piezo_v=rig.piezo_v,
                  piezo_nm=rig.piezo_nm, bias_mv=rig.bias_v * 1e3,
                  junction_mv=v_mv, current_ua=i_ua, g0=g0, railed=railed,
                  sense_nm=rig.sense_nm, accepted=self.accepted,
                  attempts=self.attempts, saved=self.n_saved,
                  zero_uv=C.current_zero_v * 1e6)


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
                 require_engaged: bool, test_pull_v: float | None = None) -> int:
    guard, rig = open_rig(cfg)
    mon = Monitor(rig)
    worker = Worker(cfg, rig, mon, save=True, out_dir=out_dir,
                    igor_export=igor_export)
    worker.require_engaged = require_engaged
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
            config_name: str, autoclose: float | None = None) -> int:
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
    root.title("rigtests 02: approach and pull" +
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

    ro = tk.Text(rb, width=38, height=9, font=("Courier", 9), relief="flat",
                 state="disabled", background=root.cget("background"))
    ro.grid(row=4, column=0, columnspan=3, sticky="ew", padx=2, pady=(4, 2))

    def set_text(widget, text):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.config(state="disabled")

    # -- settings --------------------------------------------------------------------
    sb = ttk.LabelFrame(left, text="Settings (checked before they apply)")
    sb.pack(fill="x", pady=(0, 6))
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
    fb = ttk.LabelFrame(left, text="Saving")
    fb.pack(fill="x", pady=(0, 6))
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
    ttk.Button(fb, text="New file", command=lambda: worker.send("newfile")).grid(
        row=2, column=0, padx=2, pady=2, sticky="ew")
    ttk.Button(fb, text="Export Igor now", command=lambda: worker.send("export")).grid(
        row=2, column=1, padx=2, pady=2, sticky="ew")
    file_lbl = tk.Label(fb, text="no file open", font=("Arial", 8), anchor="w",
                        wraplength=300, justify="left")
    file_lbl.grid(row=3, column=0, columnspan=2, sticky="w", padx=2)

    # -- browse -----------------------------------------------------------------------
    bb = ttk.LabelFrame(left, text="Browse a saved session")
    bb.pack(fill="x", pady=(0, 6))
    browse = {"session": None, "path": None, "n": 0, "hist": None}
    idx_var = tk.StringVar(value="0")

    def open_file():
        path = filedialog.askopenfilename(initialdir=str(out_dir),
                                          filetypes=[("session", "*.h5")])
        if not path:
            return
        if browse["session"] is not None:
            browse["session"].close()
        s = storage.Session(path)
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
        fig2, info = plots.figure_for_session(browse["path"], int(idx_var.get()))
        out = Path(browse["path"]).with_name(
            f"{Path(browse['path']).stem}_trace{info['index']:04d}.png")
        fig2.savefig(out, dpi=110)
        status.config(text=f"wrote {out}")
    ttk.Button(bb, text="Save PNG of this trace", command=save_png).grid(
        row=1, column=1, columnspan=4, padx=2, pady=2, sticky="ew")
    blbl = tk.Label(bb, text="", font=("Arial", 8), anchor="w", wraplength=300,
                    justify="left")
    blbl.grid(row=2, column=0, columnspan=5, sticky="w", padx=2)

    # -- the plots --------------------------------------------------------------------
    top = ttk.Frame(right)
    top.pack(fill="x")
    panel6 = tk.StringVar(value="approach")
    ttk.Label(top, text="bottom right:").pack(side="left")
    for text, val in (("approach", "approach"), ("I-V", "iv")):
        ttk.Radiobutton(top, text=text, value=val, variable=panel6).pack(
            side="left", padx=3)
    banner = tk.Label(top, text="", font=("Arial", 9, "bold"), fg="#b06000")
    banner.pack(side="right")

    fig = Figure(figsize=(10.5, 6.6), dpi=100)
    axes = fig.subplots(2, 3)
    fig.tight_layout(pad=2.0)
    canvas = FigureCanvasTkAgg(fig, master=right)
    canvas.get_tk_widget().pack(fill="both", expand=True)
    status = ttk.Label(root, text="", font=("Arial", 9), anchor="w")
    status.pack(fill="x", padx=8, pady=(0, 4))

    live = {"paused": False, "cycle": None, "trace": None, "hist": None,
            "dirty": False}
    C = cfg.cal

    def draw_live():
        cyc, tr, hist = live["cycle"], live["trace"], live["hist"]
        if cyc is not None and cyc.last_record is not None:
            fs = rig.sample_rate_hz
            sf = None
            if tr is not None and tr.get("record") is not None:
                try:
                    sf = trace.build_ramp(cfg, tr["record"].start_piezo_v, fs).spike_front
                except Exception:          # noqa: BLE001
                    sf = None
            plots.plot_record(axes[0, 0], cfg, cyc.last_record, fs, spike_front=sf,
                              title="last play: junction V and current")
        if tr is not None and tr.get("record") is not None:
            rec = tr["record"]
            plots.plot_trace(axes[0, 1], cfg, tr["g0"], tr["disp"], tr["verdict"],
                             title=f"trace {worker.attempts}")
            plots.plot_gold_level(axes[0, 2], cfg, tr["g0"], tr["disp"])
            if panel6.get() == "iv":
                plots.plot_iv(axes[1, 2], cfg, rec.voltage_v, rec.current_v)
        if cyc is not None and cyc.t:
            plots.plot_piezo(axes[1, 0], cfg, np.array(cyc.t), np.array(cyc.piezo_v),
                             np.array(cyc.sense_v), marks=cyc.marks,
                             title="piezo in and out, this cycle")
            if panel6.get() == "approach" and cyc.app_piezo_v:
                plots.plot_approach(axes[1, 2], cfg, cyc.app_piezo_v, cyc.app_g0,
                                    cyc.app_railed)
        if hist is not None and hist["counts"] is not None:
            plots.plot_histogram(axes[1, 1], cfg, hist["centres"], hist["counts"],
                                 hist["n"])
        canvas.draw_idle()

    def draw_saved(s: storage.Session, i: int):
        scfg = s.cfg
        voltage, current = s.raw(i)
        g0 = s.conductance(i)
        fs = float(s.scalar("sample_rate_hz")[i])
        start_v = float(s.scalar("start_piezo_v")[i])
        disp = analysis.displacement_nm(voltage.size, scfg.ramp, fs)
        verdict = analysis.select_trace(g0, scfg.ramp)
        plots.plot_record(axes[0, 0], scfg, np.stack([voltage, current]), fs,
                          title=f"saved trace {i}: junction V and current")
        plots.plot_trace(axes[0, 1], scfg, g0, disp, verdict, title=f"saved trace {i}")
        plots.plot_gold_level(axes[0, 2], scfg, g0, disp)
        t = np.arange(voltage.size) / fs
        cmd = start_v - scfg.cal.nm_to_piezo_volts(disp)
        plots.plot_piezo(axes[1, 0], scfg, t, cmd, s.piezo_sense(i, in_nm=False),
                         title="piezo during the saved pull")
        if browse["hist"] is None:
            browse["hist"] = analysis.log_histogram(s.conductances())
        plots.plot_histogram(axes[1, 1], scfg, *browse["hist"], browse["n"],
                             title="histogram of the file")
        plots.plot_iv(axes[1, 2], scfg, voltage, current)
        banner.config(text=f"BROWSING {Path(browse['path']).name} trace {i}; "
                           f"live plots paused")
        canvas.draw_idle()

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
                    f"{p['saved']} saved"))
            elif kind == "approach":
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
                file_lbl.config(text=f"writing {Path(p['path']).name}" if p["path"]
                                else "no file open")
            elif kind == "saved":
                file_lbl.config(text=f"writing {Path(p['path']).name}: {p['n']} traces")
            elif kind == "exported":
                pass
        if live["dirty"] and not live["paused"]:
            draw_live()
            live["dirty"] = False
            banner.config(text="", fg="#b06000")
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
    if autoclose is not None:
        root.after(300, lambda: worker.send("zero"))
        root.after(600, lambda: worker.send("run", 3))
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
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--autoclose", type=float, help=argparse.SUPPRESS)
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
                                args.require_engaged, test_pull_v=args.test_pull)
        return run_gui(cfg, args.out, not args.no_igor,
                       args.config.name if args.config else "defaults",
                       autoclose=args.autoclose)
    except (ConfigError, SafetyViolation) as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.info("interrupted; outputs parked")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
