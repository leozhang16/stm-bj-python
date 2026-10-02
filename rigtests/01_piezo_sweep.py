"""Piezo sweep: one slider, one plot.

Move the Z piezo by hand with the slider, or let it sweep between two
voltages, and watch two lines against time: the voltage we *command* on
``dev1/ao0`` and the voltage the sense line *reads back* on ``dev2/ai2``.

    python rigtests/01_piezo_sweep.py --simulate
    python rigtests/01_piezo_sweep.py --config configs/labpc_rig.json
    python rigtests/01_piezo_sweep.py --config configs/labpc_rig.json --headless 20

Every move goes through ``Rig.hold()``: the same clamp, the same position
tracker, the same parking at 0 V on exit as a real run. The bias is held at
0 V for the whole test, so no current flows even if the tip were in contact.

ONLY WITH THE TIP FAR FROM THE SAMPLE. 10 V on this piezo is 620 nm of travel,
and the slider has no idea where the surface is. Slider moves are slew-limited
(``--rate``, default 2 V/s) so the piezo ramps rather than jumps, but nothing
here can stop a ramp into a sample that is 100 nm away.

What to look for on the plot:

* the sense line should follow the command with no visible lag at these
  rates, scaled by sense_nm_per_volt / piezo_nm_per_volt (314/62 = 0.197 by
  Igor's numbers): 10 V commanded ~ 1.97 V read back. The "ratio" readout
  shows the measured value; if it is not ~0.197, one of the two scales in
  the config is off, and the sense scale is the one to adjust;
* tick "show in nm" and the two lines should lie on top of each other;
* a slow creep after the command stops moving is the piezo, not the code;
* a flat readback while the command moves means the sense cable or the
  low-res card: run ``bringup 1`` and look at the ``ai2 piezo sense`` lines.
"""

from __future__ import annotations

import argparse
import collections
import csv
import logging
import sys
import threading
import time
from pathlib import Path

import numpy as np

# Make ``import stmlab`` work when this file is run from anywhere.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from stmlab.config import ConfigError, RigConfig, validate      # noqa: E402
from stmlab.instrument import Rig                               # noqa: E402
from stmlab.safety import SafeSession, SafetyViolation          # noqa: E402

log = logging.getLogger("rigtests.piezo_sweep")


# --------------------------------------------------------------------------
# The worker: the only thing that touches the rig
# --------------------------------------------------------------------------

class PiezoWorker(threading.Thread):
    """Moves the piezo towards a target at a limited rate and logs what the
    sense line reads. Runs in its own thread so the window never blocks on
    the card; the window only ever sets ``target_v`` and reads ``samples``.
    """

    def __init__(self, rig: Rig, rate_v_per_s: float, hold_ms: float,
                 period_s: float = 0.05):
        super().__init__(daemon=True, name="piezo-worker")
        self.rig = rig
        self.cfg = rig.cfg
        self.rate = float(rate_v_per_s)
        self.period = float(period_s)
        fs = rig.sample_rate_hz
        self.n_hold = max(50, int(round(hold_ms * 1e-3 * fs)))

        self.target_v = rig.piezo_v
        self.sweep: tuple[float, float, float, bool] | None = None
        self._sweep_dir = +1
        self._sweep_phase = "sweep"
        self._quit = threading.Event()     # not _stop: Thread owns that name
        self._lock = threading.Lock()
        self.samples: collections.deque = collections.deque(maxlen=200_000)
        self.last_raw: np.ndarray | None = None      # the last hold, every sample
        self.t0 = time.monotonic()
        self.error: str | None = None

    # -- commands from the window -----------------------------------------

    def goto(self, volts: float) -> None:
        with self._lock:
            self.sweep = None
            self.target_v = float(volts)

    def start_sweep(self, start_v: float, stop_v: float, rate_v_per_s: float,
                    bounce: bool) -> None:
        """Ramp from start to stop at the given rate; with ``bounce`` keep
        going back and forth until told otherwise."""
        with self._lock:
            self.sweep = (float(start_v), float(stop_v),
                          max(1e-3, float(rate_v_per_s)), bool(bounce))
            self._sweep_dir = +1
            self.target_v = float(start_v)
            self._sweep_phase = "approach"      # first get to the start

    def stop_motion(self) -> None:
        """Stay where we are."""
        with self._lock:
            self.sweep = None
            self.target_v = self.rig.piezo_v

    def stop(self) -> None:
        self._quit.set()

    def reset(self) -> None:
        """Forget every point so far; the fit starts over from here."""
        with self._lock:
            self.samples.clear()
            self.t0 = time.monotonic()

    def raw_snapshot(self) -> np.ndarray | None:
        """Every sample of the last hold, volts on the sense line."""
        with self._lock:
            return None if self.last_raw is None else self.last_raw.copy()

    def snapshot(self) -> np.ndarray:
        """(n, 3): seconds since start, commanded V, sense V (nan if none)."""
        with self._lock:
            if not self.samples:
                return np.zeros((0, 3))
            return np.array(self.samples, dtype=float)

    # -- the loop -----------------------------------------------------------

    def run(self) -> None:
        last = time.monotonic()
        try:
            while not self._quit.is_set():
                now = time.monotonic()
                dt = max(1e-3, now - last)
                last = now

                with self._lock:
                    target, rate = self._next_target(dt)

                # One slew-limited step towards the target.
                here = self.rig.piezo_v
                step = rate * dt
                if abs(target - here) <= step:
                    nxt = target
                else:
                    nxt = here + step * np.sign(target - here)

                record = self.rig.hold(piezo_v=nxt, bias_v=0.0,
                                       n_samples=self.n_hold)
                del record                      # bias is 0 V: nothing in it
                sense = self.rig.last_sense_v
                if sense is None:
                    sense_v = float("nan")
                else:
                    half = sense.size // 2      # settled half of the hold
                    sense_v = float(np.mean(sense[half:]))

                with self._lock:
                    self.samples.append((now - self.t0, self.rig.piezo_v,
                                         sense_v))
                    self.last_raw = None if sense is None else sense.copy()

                time.sleep(max(0.0, self.period - (time.monotonic() - now)))
        except Exception as exc:                # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"
            log.exception("worker stopped")

    def _next_target(self, dt: float) -> tuple[float, float]:
        """Target voltage and slew rate for this step (lock held)."""
        if self.sweep is None:
            return self.target_v, self.rate

        start, stop, rate, bounce = self.sweep
        here = self.rig.piezo_v
        if self._sweep_phase == "approach":
            if abs(here - start) < 1e-6:
                self._sweep_phase = "sweep"
                self._sweep_dir = +1
            return start, self.rate

        dest = stop if self._sweep_dir > 0 else start
        if abs(here - dest) < 1e-6:
            if not bounce:
                self.sweep = None                   # arrived: stay there
                self.target_v = dest
                return dest, rate
            self._sweep_dir = -self._sweep_dir      # turn around
            dest = stop if self._sweep_dir > 0 else start
        return dest, rate


# --------------------------------------------------------------------------
# Opening the rig
# --------------------------------------------------------------------------

def open_rig(cfg: RigConfig) -> tuple[SafeSession, Rig]:
    for w in validate(cfg):
        log.warning("config: %s", w)
    guard = SafeSession(cfg)
    guard.__enter__()                       # verifies devices, parks outputs
    try:
        rig = Rig(cfg).open()               # tasks open, piezo parked
        rig.set_bias(0.0)                   # no current for this test
    except Exception:
        guard.__exit__(*sys.exc_info())
        raise
    return guard, rig


def close_rig(guard: SafeSession, rig: Rig) -> None:
    try:
        rig.close()                         # withdraws to park, closes tasks
    finally:
        guard.__exit__(None, None, None)    # parks every output once more


# --------------------------------------------------------------------------
# Headless: for a smoke test, or a logged sweep without clicking
# --------------------------------------------------------------------------

def run_headless(cfg: RigConfig, seconds: float, rate: float, hold_ms: float,
                 out: Path | None) -> int:
    guard, rig = open_rig(cfg)
    worker = PiezoWorker(rig, rate, hold_ms)
    lo, hi = cfg.limits.piezo_ao_min_v, cfg.limits.piezo_ao_max_v
    try:
        worker.start()
        worker.start_sweep(lo, hi, rate, bounce=True)
        t_end = time.monotonic() + seconds
        while time.monotonic() < t_end and worker.is_alive():
            time.sleep(0.5)
            data = worker.snapshot()
            if data.size:
                print(f"  t={data[-1, 0]:6.1f} s  command {data[-1, 1]:6.3f} V"
                      f"  sense {data[-1, 2]:7.4f} V", flush=True)
        worker.stop()
        worker.join(timeout=5)
    finally:
        close_rig(guard, rig)
    if worker.error:
        print(f"worker error: {worker.error}")
        return 1
    data = worker.snapshot()
    report(cfg, data)
    if out is not None:
        save_csv(out, data)
        print(f"wrote {out}")
    return 0


def fit_summary(cfg: RigConfig, data: np.ndarray) -> dict:
    """Everything the report and the side panel say, as numbers.

    Keys always present: n, seconds, has_sense. Once the command has moved:
    corr, verdict ("not following" / "following"). Once it follows: a, b
    (sense = a * command + b), resid_mv, scale (nm per sense volt, through
    the command's nm/V), loop_mv / loop_nm / lag_s when both legs exist,
    lsb_mv / lsb_nm, sense_min / sense_max, better_range, max_dev_nm.
    """
    C, M = cfg.cal, cfg.channels
    out: dict = {"n": int(data.shape[0]),
                 "seconds": float(data[-1, 0]) if data.shape[0] else 0.0,
                 "has_sense": False, "verdict": None, "corr": None}
    if data.shape[0] < 2:
        return out
    cmd, sense = data[:, 1], data[:, 2]
    out["cmd_min"], out["cmd_max"] = float(cmd.min()), float(cmd.max())
    fin = np.isfinite(sense)
    if not fin.any():
        return out
    out["has_sense"] = True
    cmd, sense = cmd[fin], sense[fin]
    r = following(cmd, sense)
    out["corr"] = r
    if r is None:
        return out                               # not enough motion yet
    out["verdict"] = "following" if r >= 0.9 else "not following"
    if r < 0.9:
        return out

    a, b = np.polyfit(cmd, sense, 1)
    resid = sense - (a * cmd + b)
    out.update(a=float(a), b=float(b), resid_mv=float(1e3 * resid.std()),
               scale=float(C.piezo_nm_per_volt / a))

    # Legs: points where the command was moving up, and moving down. Points
    # where it stood still belong to neither, and a leg has to span more than
    # a volt before a line through it means anything.
    step = np.r_[0.0, np.diff(cmd)]
    rising, falling = step > 1e-4, step < -1e-4
    if (rising.sum() > 10 and falling.sum() > 10
            and np.ptp(cmd[rising]) > 1.0 and np.ptp(cmd[falling]) > 1.0):
        mid = 0.5 * (cmd.min() + cmd.max())
        up = np.polyval(np.polyfit(cmd[rising], sense[rising], 1), mid)
        down = np.polyval(np.polyfit(cmd[falling], sense[falling], 1), mid)
        loop = float(down - up)
        rate = _rate_v_per_s(data)
        out.update(loop_mid_v=float(mid), loop_mv=1e3 * loop,
                   loop_nm=float(loop / a * C.piezo_nm_per_volt),
                   lag_s=float(abs(loop / a) / 2 / rate) if rate > 0 else None)

    lsb = 2 * M.sense_ai_range_v / 65536
    out.update(lsb_mv=1e3 * lsb, lsb_nm=float(lsb / a * C.piezo_nm_per_volt),
               sense_min=float(sense.min()), sense_max=float(sense.max()))
    span = sense.max() - sense.min()
    out["better_range"] = None
    if sense.max() < 0.4 * M.sense_ai_range_v and span < 0.2 * M.sense_ai_range_v:
        out["better_range"] = next(
            (rr for rr in (1.0, 2.0, 5.0) if sense.max() < 0.8 * rr), None)
    out["max_dev_nm"] = float(np.max(np.abs(
        C.sense_volts_to_nm(sense) - C.piezo_volts_to_nm(cmd))))
    return out


def report(cfg: RigConfig, data: np.ndarray) -> None:
    """The headless printout, from fit_summary."""
    f = fit_summary(cfg, data)
    if f["n"] < 2:
        print("no samples")
        return
    print(f"{f['n']} points over {f['seconds']:.1f} s; command "
          f"{f['cmd_min']:.3f} .. {f['cmd_max']:.3f} V")
    if not f["has_sense"]:
        print("no sense readback (channels.low_res_device is None)")
        return
    if f["corr"] is None:
        print("the command did not move enough to judge the readback")
        return
    print(f"correlation(sense, command) = {f['corr']:+.3f}")
    if f["verdict"] == "not following":
        print("THE SENSE LINE IS NOT FOLLOWING THE COMMAND. The readback "
              "drifted or sat still while the piezo was commanded over "
              f"{f['cmd_max'] - f['cmd_min']:.1f} V. No ratio can be taken "
              "from this. Check: is the piezo driver box on; is its monitor "
              f"output cabled to {cfg.channels.piezo_sense_path} on the "
              "second card's terminal block; is the input wired as the "
              f"config says (channels.sense_terminal = "
              f"{cfg.channels.sense_terminal!r}; a BNC from a box is "
              "usually 'rse').")
        return
    C = cfg.cal
    # A straight-line fit, sense = a * command + b. The line need not pass
    # through the origin: a driver box can sit at some volts with the
    # command at 0 V, and that offset is cal.sense_zero_v.
    print(f"sense = {f['a']:.5f} * command + {f['b']:.4f} V   (rms residual "
          f"{f['resid_mv']:.1f} mV)")
    print(f"slope {f['a']:.5f} V/V; config implies "
          f"{C.piezo_nm_per_volt / C.sense_nm_per_volt:.5f} = "
          f"{C.piezo_nm_per_volt:g} / {C.sense_nm_per_volt:g}")
    print(f"with the command's {C.piezo_nm_per_volt:g} nm/V, this readback is "
          f"{f['scale']:.0f} nm per sense volt, zero {f['b']:.4f} V. For the "
          f"config:")
    print(f'    "sense_nm_per_volt": {f["scale"]:.1f},')
    print(f'    "sense_zero_v": {f["b"]:.4f},')
    # Up legs against down legs at the same command: a loop is hysteresis
    # of the piezo, or a lag in the driver; two sweep rates tell them apart
    # (a lag loop grows with the rate, hysteresis does not).
    if "loop_mv" in f:
        lag = f"~{f['lag_s']:.2f} s" if f["lag_s"] is not None else "?"
        print(f"up/down loop at {f['loop_mid_v']:.1f} V command: "
              f"{f['loop_mv']:+.1f} mV = {f['loop_nm']:+.1f} nm "
              f"(hysteresis, or a lag of {lag})")
    print(f"readback spans {f['sense_min']:.3f} .. {f['sense_max']:.3f} V on a "
          f"+/-{cfg.channels.sense_ai_range_v:g} V input: one ADC step is "
          f"{f['lsb_mv']:.2f} mV = {f['lsb_nm']:.2f} nm of command")
    if f["better_range"]:
        print(f"    (channels.sense_ai_range_v = {f['better_range']:g} would give "
              f"{cfg.channels.sense_ai_range_v / f['better_range']:.0f}x finer steps)")
    print(f"largest |sense - command| = {f['max_dev_nm']:.1f} nm with the "
          f"config's scale and zero")


def panel_text(cfg: RigConfig, f: dict, now_cmd: float | None,
               now_sense: float | None, config_name: str,
               rate: float) -> str:
    """The side panel: config, the position now, and the live fit."""
    C, M, L = cfg.cal, cfg.channels, cfg.limits
    lo_nm, hi_nm = C.piezo_volts_to_nm(L.piezo_ao_min_v), \
        C.piezo_volts_to_nm(L.piezo_ao_max_v)
    lines = [
        f"CONFIG  {config_name}",
        f" command  {M.path(M.ao_piezo):<10} {L.piezo_ao_min_v:.2f} .. "
        f"{L.piezo_ao_max_v:.2f} V",
        f" piezo    {C.piezo_nm_per_volt:g} nm/V  (Igor K_ZPiezoScale)",
        f" window   {lo_nm:.0f} .. {hi_nm:.0f} nm of travel",
        f" sense    {M.piezo_sense_path or 'none':<10} +/-{M.sense_ai_range_v:g} V"
        f"  {M.sense_terminal}",
        f" sense cal {C.sense_nm_per_volt:g} nm/V, zero {C.sense_zero_v:.4f} V",
        "",
        "NOW",
    ]
    if now_cmd is None:
        lines.append(" (no samples yet)")
    else:
        lines.append(f" command  {now_cmd:7.3f} V  = {C.piezo_volts_to_nm(now_cmd):7.1f} nm")
        if now_sense is None or not np.isfinite(now_sense):
            lines.append(" sense    (no sense line)")
        else:
            lines.append(f" sense    {now_sense:7.4f} V = "
                         f"{C.sense_volts_to_nm(now_sense):7.1f} nm")
    lines += [f" slider ramps at {rate:g} V/s", ""]

    lines.append(f"FIT  (all {f['n']} points, {f['seconds']:.0f} s)")
    if not f["has_sense"]:
        lines.append(" no sense line")
    elif f["corr"] is None:
        lines.append(" move the piezo > 1 V to fit")
    elif f["verdict"] == "not following":
        lines += [f" corr     {f['corr']:+.3f}   NOT FOLLOWING",
                  " the readback ignores the command:",
                  " driver box on? cable on the sense",
                  " input? sense_terminal right?"]
    else:
        lines += [
            f" corr     {f['corr']:+.4f}   following",
            f" sense = {f['a']:.5f} x cmd + {f['b']:.4f} V",
            f" rms resid {f['resid_mv']:.1f} mV",
            f" => {f['scale']:.0f} nm per sense volt",
        ]
        if "loop_mv" in f:
            lag = f"~{f['lag_s']:.2f} s" if f["lag_s"] is not None else "?"
            lines += [f" loop     {f['loop_mv']:+.1f} mV = {f['loop_nm']:+.1f} nm",
                      f"          (hysteresis, or lag {lag})"]
        lines.append(f" ADC step {f['lsb_mv']:.2f} mV = {f['lsb_nm']:.2f} nm")
        if f["better_range"]:
            lines.append(f"          (+/-{f['better_range']:g} V input: "
                         f"{M.sense_ai_range_v / f['better_range']:.0f}x finer)")
        lines += ["",
                  f' for "cal" in {config_name}:',
                  f'   "sense_nm_per_volt": {f["scale"]:.1f},',
                  f'   "sense_zero_v": {f["b"]:.4f},']
    return "\n".join(lines)


def _rate_v_per_s(data: np.ndarray) -> float:
    """Typical |d command / dt| while moving, V/s."""
    t, cmd = data[:, 0], data[:, 1]
    if t.size < 3:
        return 0.0
    v = np.abs(np.diff(cmd) / np.maximum(np.diff(t), 1e-6))
    v = v[v > 0.05]
    return float(np.median(v)) if v.size else 0.0


def following(cmd: np.ndarray, sense: np.ndarray) -> float | None:
    """Correlation between readback and command, or None if the command
    hardly moved. 0.99 is a connected sense line; a floating input gives
    anything, usually near zero."""
    if cmd.size < 10 or cmd.max() - cmd.min() < 1.0:
        return None
    if np.std(sense) == 0:
        return 0.0
    return float(np.corrcoef(cmd, sense)[0, 1])


def save_csv(path: Path, data: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time_s", "command_v", "sense_v"])
        w.writerows(data.tolist())


# --------------------------------------------------------------------------
# The window
# --------------------------------------------------------------------------

def run_gui(cfg: RigConfig, rate: float, hold_ms: float, window_s: float,
            out: Path | None, autoclose: float | None = None,
            config_name: str = "defaults", readback: bool = False,
            sweep: tuple[float, float] | None = None,
            sweep_rate: float | None = None,
            ymode_start: str = "full") -> int:
    import tkinter as tk
    from tkinter import ttk

    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    guard, rig = open_rig(cfg)
    worker = PiezoWorker(rig, rate, hold_ms)
    worker.start()

    L, C = cfg.limits, cfg.cal
    root = tk.Tk()
    root.title("rigtests 01: piezo sweep" + ("  [simulate]" if cfg.simulate
                                               else f"  [{cfg.channels.device}]"))

    # -- the bar, like the big GUI's --------------------------------------
    pb = ttk.LabelFrame(root, text="Piezo")
    pb.pack(fill="x", padx=8, pady=(8, 4))
    dragging = {"on": False}

    def on_press(_event=None):
        dragging["on"] = True

    def on_release(_event=None):
        dragging["on"] = False
        worker.goto(float(slider.get()))

    slider = tk.Scale(pb, from_=L.piezo_ao_min_v, to=L.piezo_ao_max_v,
                      resolution=0.01, orient="horizontal", length=520,
                      tickinterval=(L.piezo_ao_max_v - L.piezo_ao_min_v) / 5,
                      label="SliderPos_Z (piezo volts at the DAQ)",
                      font=("Arial", 9))
    slider.set(rig.piezo_v)
    slider.bind("<ButtonPress-1>", on_press)
    slider.bind("<ButtonRelease-1>", on_release)
    slider.grid(row=0, column=0, columnspan=6, sticky="ew", padx=4)

    ttk.Label(pb, text="go to (V)").grid(row=1, column=0, sticky="e", padx=4)
    goto_var = tk.StringVar(value=f"{rig.piezo_v:.2f}")
    goto_entry = ttk.Entry(pb, textvariable=goto_var, width=7)
    goto_entry.grid(row=1, column=1, sticky="w")

    def on_goto(_event=None):
        try:
            worker.goto(float(goto_var.get()))
        except ValueError:
            pass
    goto_entry.bind("<Return>", on_goto)
    ttk.Button(pb, text="Go", command=on_goto).grid(row=1, column=2, padx=4)
    ttk.Button(pb, text="Park (0 V)",
               command=lambda: worker.goto(L.piezo_ao_min_v)).grid(
        row=1, column=3, padx=4)
    ttk.Button(pb, text="Stop",
               command=worker.stop_motion).grid(row=1, column=4, padx=4)
    ttk.Label(pb, text=f"slider moves ramp at {rate:g} V/s").grid(
        row=1, column=5, sticky="w", padx=8)

    # -- the sweep ----------------------------------------------------------
    sb = ttk.LabelFrame(root, text="Sweep")
    sb.pack(fill="x", padx=8, pady=4)
    sw_lo, sw_hi = sweep if sweep else (L.piezo_ao_min_v, L.piezo_ao_max_v)
    from_var = tk.StringVar(value=f"{sw_lo:.3f}")
    to_var = tk.StringVar(value=f"{sw_hi:.3f}")
    rate_var = tk.StringVar(value=f"{sweep_rate if sweep_rate else rate:g}")
    bounce_var = tk.BooleanVar(value=True)
    for col, (label, var) in enumerate((("from (V)", from_var),
                                        ("to (V)", to_var),
                                        ("rate (V/s)", rate_var))):
        ttk.Label(sb, text=label).grid(row=0, column=2 * col, sticky="e",
                                       padx=(8, 2))
        ttk.Entry(sb, textvariable=var, width=7).grid(row=0, column=2 * col + 1)
    ttk.Checkbutton(sb, text="back and forth", variable=bounce_var).grid(
        row=0, column=6, padx=8)

    def on_sweep():
        try:
            worker.start_sweep(float(from_var.get()), float(to_var.get()),
                               float(rate_var.get()), bounce_var.get())
        except ValueError:
            pass
    ttk.Button(sb, text="Sweep", command=on_sweep).grid(row=0, column=7, padx=4)
    ttk.Button(sb, text="Stop", command=worker.stop_motion).grid(
        row=0, column=8, padx=4)

    # -- readouts -------------------------------------------------------------
    rb = ttk.Frame(root)
    rb.pack(fill="x", padx=8, pady=4)
    ro = {}
    titles = {"command": "command", "sense": "sense",
              "ratio": "sense vs command (last 15 s)"}
    for col, key in enumerate(("command", "sense", "ratio")):
        ttk.Label(rb, text=titles[key], font=("Arial", 9, "bold")).grid(
            row=0, column=col, padx=12, sticky="w")
        ro[key] = ttk.Label(rb, text="--", font=("Courier", 10), width=30)
        ro[key].grid(row=1, column=col, padx=12, sticky="w")
    nm_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(rb, text="show in nm", variable=nm_var).grid(
        row=0, column=3, rowspan=2, padx=12)

    def on_save():
        path = out or (_ROOT / "data" /
                       f"piezo_sweep_{time.strftime('%Y%m%d_%H%M%S')}.csv")
        save_csv(path, worker.snapshot())
        status.config(text=f"saved {path}")
    ttk.Button(rb, text="Save CSV", command=on_save).grid(
        row=0, column=4, rowspan=2, padx=12)
    ttk.Button(rb, text="Readback window",
               command=lambda: open_readback()).grid(
        row=0, column=5, rowspan=2, padx=12)

    # -- the readback-only window ------------------------------------------
    # Two plots of the sense line alone, auto-scaled and with the mean taken
    # out, so the y axis reads in microvolts and picometres rather than
    # volts. Top: one point per hold (the settled mean of each 10 ms hold,
    # so ADC noise is averaged down), the slow picture: creep, drift, steps.
    # Bottom: every sample of the last hold at the full 40 kHz, the fast
    # picture: ripple, mains hum, the ADC's own noise. What it watches is the
    # driver's monitor output, so it sees the drive, not the tip: mechanical
    # vibration of the junction only shows in the tunnelling current.
    rb_state: dict = {"win": None}

    def open_readback():
        if rb_state["win"] is not None and rb_state["win"].winfo_exists():
            rb_state["win"].lift()
            return
        win = tk.Toplevel(root)
        win.title("readback only: " + (cfg.channels.piezo_sense_path or "no sense line"))
        rb_state["win"] = win
        fig2 = Figure(figsize=(6.4, 5.0), dpi=100)
        ax_slow = fig2.add_subplot(211)
        ax_fast = fig2.add_subplot(212)
        for a_ in (ax_slow, ax_fast):
            a_.tick_params(labelsize=8)
            a_.grid(True, alpha=0.3)
        ax_slow.set_title("one point per hold (settled mean), minus the mean shown",
                          fontsize=9)
        ax_slow.set_xlabel("time (s)", fontsize=8)
        ax_slow.set_ylabel("sense (uV)", fontsize=8)
        ax_fast.set_title("the last hold, every sample, minus its mean",
                          fontsize=9)
        ax_fast.set_xlabel("time within the hold (ms)", fontsize=8)
        ax_fast.set_ylabel("sense (uV)", fontsize=8)
        (l_slow,) = ax_slow.plot([], [], color="#d62728", lw=1.0)
        (l_fast,) = ax_fast.plot([], [], color="#d62728", lw=0.6)
        pm_slow = ax_slow.secondary_yaxis(
            "right", functions=(lambda v: v * C.sense_nm_per_volt * 1e-3,
                                lambda nm: nm / (C.sense_nm_per_volt * 1e-3)))
        pm_slow.set_ylabel("pm", fontsize=8)
        pm_slow.tick_params(labelsize=8)
        pm_fast = ax_fast.secondary_yaxis(
            "right", functions=(lambda v: v * C.sense_nm_per_volt * 1e-3,
                                lambda nm: nm / (C.sense_nm_per_volt * 1e-3)))
        pm_fast.set_ylabel("pm", fontsize=8)
        pm_fast.tick_params(labelsize=8)
        fig2.tight_layout()
        canvas2 = FigureCanvasTkAgg(fig2, master=win)
        canvas2.get_tk_widget().pack(fill="both", expand=True)
        stats = ttk.Label(win, text="", font=("Courier", 9), justify="left")
        stats.pack(fill="x", padx=8, pady=(0, 6))
        secs_var = tk.StringVar(value="10")
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(bar, text="seconds shown").pack(side="left")
        ttk.Entry(bar, textvariable=secs_var, width=5).pack(side="left", padx=4)
        ttk.Label(bar, text=f"hold = {worker.n_hold} samples = "
                            f"{1e3 * worker.n_hold / rig.sample_rate_hz:.0f} ms; "
                            f"--hold-ms 50 shows three mains cycles per hold").pack(
            side="left", padx=12)

        def refresh_readback():
            if not win.winfo_exists():
                rb_state["win"] = None
                return
            try:
                secs = max(1.0, float(secs_var.get()))
            except ValueError:
                secs = 10.0
            data = worker.snapshot()
            text = []
            if data.shape[0] and np.isfinite(data[:, 2]).any():
                t, sv = data[:, 0], data[:, 2]
                keep = (t >= t[-1] - secs) & np.isfinite(sv)
                if keep.sum() >= 2:
                    ts, ss = t[keep], sv[keep]
                    mean = ss.mean()
                    y = (ss - mean) * 1e6
                    l_slow.set_data(ts, y)
                    ax_slow.set_xlim(ts[-1] - secs, ts[-1])
                    pad = max(5.0, 0.15 * np.ptp(y)) if y.size else 5.0
                    ax_slow.set_ylim(y.min() - pad, y.max() + pad)
                    rms = y.std()
                    moved = np.ptp(data[keep, 1]) > 0.005
                    text.append(f"per-hold means, last {secs:g} s: mean "
                                f"{mean:.4f} V, rms {rms:6.1f} uV = "
                                f"{rms * C.sense_nm_per_volt * 1e-3:6.1f} pm, "
                                f"peak-to-peak {np.ptp(y):6.1f} uV"
                                + ("   (the command moved in this window: "
                                   "wait for it to stand still)" if moved else ""))
            raw = worker.raw_snapshot()
            if raw is not None and raw.size > 1:
                half = raw.size // 2
                seg = raw[half:]                      # the settled half
                yr = (seg - seg.mean()) * 1e6
                tr = (np.arange(seg.size) + half) / rig.sample_rate_hz * 1e3
                l_fast.set_data(tr, yr)
                ax_fast.set_xlim(tr[0], tr[-1])
                pad = max(5.0, 0.15 * np.ptp(yr))
                ax_fast.set_ylim(yr.min() - pad, yr.max() + pad)
                lsb = 2 * cfg.channels.sense_ai_range_v / 65536 * 1e6
                text.append(f"within the last hold ({seg.size} samples at "
                            f"{rig.sample_rate_hz / 1e3:.0f} kHz): rms "
                            f"{yr.std():6.1f} uV = "
                            f"{yr.std() * C.sense_nm_per_volt * 1e-3:6.1f} pm; "
                            f"ADC step {lsb:.0f} uV on +/-"
                            f"{cfg.channels.sense_ai_range_v:g} V")
            stats.config(text="\n".join(text) or "waiting for samples")
            canvas2.draw_idle()
            win.after(200, refresh_readback)

        refresh_readback()

    # -- the plot, with the fit panel beside it --------------------------------
    body = ttk.Frame(root)
    body.pack(fill="both", expand=True, padx=8, pady=4)

    plot_col = ttk.Frame(body)
    plot_col.pack(side="left", fill="both", expand=True)

    # Y axis control. The command and the readback live on two axes, left
    # and right, because a 5 nm pull is 81 mV of command but 4 mV of
    # readback: on one axis the readback is a flat line. The right axis is
    # linked to the left through the config's scale and zero, so when the
    # calibration is right the two lines lie on top of each other at any
    # zoom; "unlink" lets the readback find its own scale instead.
    yrow = ttk.Frame(plot_col)
    yrow.pack(fill="x", pady=(0, 2))
    ttk.Label(yrow, text="y axis:").pack(side="left")
    ymode = tk.StringVar(value=ymode_start)
    for text, val in (("full range", "full"), ("sweep range", "sweep"),
                      ("auto", "auto"), ("manual", "manual")):
        ttk.Radiobutton(yrow, text=text, value=val, variable=ymode).pack(
            side="left", padx=3)
    ymin_var = tk.StringVar(value=f"{L.piezo_ao_min_v:.2f}")
    ymax_var = tk.StringVar(value=f"{L.piezo_ao_max_v:.2f}")
    ttk.Entry(yrow, textvariable=ymin_var, width=7).pack(side="left", padx=(6, 2))
    ttk.Label(yrow, text="to").pack(side="left")
    ttk.Entry(yrow, textvariable=ymax_var, width=7).pack(side="left", padx=2)
    ylink = tk.BooleanVar(value=True)
    ttk.Checkbutton(yrow, text="readback axis linked", variable=ylink).pack(
        side="left", padx=8)

    fig = Figure(figsize=(6.4, 3.6), dpi=100)
    ax = fig.add_subplot(111)
    ax2 = ax.twinx()
    ax.set_xlabel("time (s)", fontsize=9)
    for a_ in (ax, ax2):
        a_.tick_params(labelsize=9)
    ax.grid(True, alpha=0.3)
    (l_cmd,) = ax.plot([], [], color="#1f77b4", lw=1.2,
                       label=f"command  {cfg.channels.path(cfg.channels.ao_piezo)}")
    sense_label = (cfg.channels.piezo_sense_path or "no sense line")
    (l_sense,) = ax2.plot([], [], color="#d62728", lw=1.2,
                          label=f"sense  {sense_label}")
    ax.tick_params(axis="y", colors="#1f77b4")
    ax2.tick_params(axis="y", colors="#d62728")
    ax.legend([l_cmd, l_sense], [l_cmd.get_label(), l_sense.get_label()],
              loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2,
              fontsize=8, frameon=False)
    canvas = FigureCanvasTkAgg(fig, master=plot_col)
    canvas.get_tk_widget().pack(fill="both", expand=True)

    def cmd_to_sense_v(v):
        """Where the readback should sit for a command, by the config."""
        return C.piezo_volts_to_nm(v) / C.sense_nm_per_volt + C.sense_zero_v

    def y_limits(cmd_v: np.ndarray, sense_v: np.ndarray, in_nm: bool):
        """(left lo, left hi, right lo, right hi) for the chosen mode."""
        mode = ymode.get()
        if mode == "sweep":
            try:
                lo, hi = sorted((float(from_var.get()), float(to_var.get())))
            except ValueError:
                lo, hi = L.piezo_ao_min_v, L.piezo_ao_max_v
        elif mode == "manual":
            try:
                lo, hi = sorted((float(ymin_var.get()), float(ymax_var.get())))
            except ValueError:
                lo, hi = L.piezo_ao_min_v, L.piezo_ao_max_v
            if in_nm:                       # the boxes are in the shown unit
                lo, hi = C.nm_to_piezo_volts(lo), C.nm_to_piezo_volts(hi)
        elif mode == "auto" and cmd_v.size:
            lo, hi = float(cmd_v.min()), float(cmd_v.max())
        else:
            lo, hi = L.piezo_ao_min_v, L.piezo_ao_max_v
        if hi - lo < 1e-6:
            lo, hi = lo - 0.005, hi + 0.005
        pad = 0.05 * (hi - lo) if mode != "manual" else 0.0
        lo, hi = lo - pad, hi + pad

        fin = np.isfinite(sense_v)
        if ylink.get() or not fin.any():
            s_lo, s_hi = cmd_to_sense_v(lo), cmd_to_sense_v(hi)
        else:                               # the readback on its own scale
            sv = sense_v[fin]
            s_lo, s_hi = float(sv.min()), float(sv.max())
            if s_hi - s_lo < 1e-6:
                s_lo, s_hi = s_lo - 1e-4, s_hi + 1e-4
            s_pad = 0.05 * (s_hi - s_lo)
            s_lo, s_hi = s_lo - s_pad, s_hi + s_pad
        if in_nm:
            return (C.piezo_volts_to_nm(lo), C.piezo_volts_to_nm(hi),
                    C.sense_volts_to_nm(s_lo), C.sense_volts_to_nm(s_hi))
        return lo, hi, s_lo, s_hi

    side = ttk.LabelFrame(body, text="Fit and ranges")
    side.pack(side="right", fill="y", padx=(8, 0))
    panel = tk.Text(side, width=44, height=26, font=("Courier", 9),
                    relief="flat", wrap="none", state="disabled",
                    background=root.cget("background"))
    panel.pack(fill="both", expand=True, padx=4, pady=4)
    last_fit = {"f": fit_summary(cfg, np.zeros((0, 3))), "tick": 0}

    def set_panel(text: str) -> None:
        panel.config(state="normal")
        panel.delete("1.0", "end")
        panel.insert("1.0", text)
        panel.config(state="disabled")

    def on_clear():
        worker.reset()
        last_fit["f"] = fit_summary(cfg, np.zeros((0, 3)))
        status.config(text="points cleared; the fit starts over")

    def on_copy():
        f = last_fit["f"]
        if f.get("verdict") != "following":
            status.config(text="nothing to copy: no fit yet")
            return
        text = (f'"sense_nm_per_volt": {f["scale"]:.1f},\n'
                f'"sense_zero_v": {f["b"]:.4f},')
        root.clipboard_clear()
        root.clipboard_append(text)
        status.config(text="config lines copied to the clipboard")

    pbtn = ttk.Frame(side)
    pbtn.pack(fill="x", padx=4, pady=(0, 4))
    ttk.Button(pbtn, text="Clear points", command=on_clear).pack(
        side="left", padx=2)
    ttk.Button(pbtn, text="Copy config lines", command=on_copy).pack(
        side="left", padx=2)

    status = ttk.Label(root, text="", font=("Arial", 9))
    status.pack(fill="x", padx=8, pady=(0, 6))
    set_panel(panel_text(cfg, last_fit["f"], None, None, config_name, rate))

    def refresh():
        if worker.error:
            status.config(text=f"worker stopped: {worker.error}")
        data = worker.snapshot()
        if data.shape[0]:
            t, cmd, sense = data[:, 0], data[:, 1], data[:, 2]
            in_nm = nm_var.get()
            right = max(t[-1], window_s)
            shown = t >= right - window_s
            if in_nm:
                y_cmd, y_sense = C.piezo_volts_to_nm(cmd), C.sense_volts_to_nm(sense)
                ax.set_ylabel("command (nm)", fontsize=9, color="#1f77b4")
                ax2.set_ylabel("readback (nm)", fontsize=9, color="#d62728")
            else:
                y_cmd, y_sense = cmd, sense
                ax.set_ylabel("command (V at the DAQ)", fontsize=9, color="#1f77b4")
                ax2.set_ylabel("readback (V)", fontsize=9, color="#d62728")
            lo, hi, s_lo, s_hi = y_limits(cmd[shown], sense[shown], in_nm)
            ax.set_ylim(lo, hi)
            ax2.set_ylim(s_lo, s_hi)
            l_cmd.set_data(t, y_cmd)
            l_sense.set_data(t, y_sense)
            ax.set_xlim(right - window_s, right)
            canvas.draw_idle()

            c, s = cmd[-1], sense[-1]
            ro["command"].config(text=f"{c:7.3f} V  = {C.piezo_volts_to_nm(c):7.1f} nm")
            if np.isnan(s):
                ro["sense"].config(text="   (no sense line)")
                ro["ratio"].config(text="")
            else:
                ro["sense"].config(text=f"{s:7.4f} V  = {C.sense_volts_to_nm(s):7.1f} nm")
                recent = data[-300:]                 # the last ~15 s
                fin = np.isfinite(recent[:, 2])
                rc, rs = recent[fin, 1], recent[fin, 2]
                r = following(rc, rs) if fin.any() else None
                if r is None:
                    ro["ratio"].config(text="(move the piezo to judge)")
                elif r < 0.9:
                    ro["ratio"].config(text=f"NOT FOLLOWING  r={r:+.2f}")
                else:
                    a = np.polyfit(rc, rs, 1)[0]
                    ro["ratio"].config(
                        text=f"slope {a:.4f}  (config {C.piezo_nm_per_volt / C.sense_nm_per_volt:.4f})")
            if not dragging["on"]:
                slider.set(c)               # the knob follows the piezo

            # The side panel: the fit over every point, twice a second.
            last_fit["tick"] += 1
            if last_fit["tick"] % 5 == 0:
                last_fit["f"] = fit_summary(cfg, data[-50_000:])
            set_panel(panel_text(cfg, last_fit["f"], float(c),
                                 None if np.isnan(s) else float(s),
                                 config_name, rate))
        root.after(100, refresh)

    parked = {"done": False}

    def park_and_close():
        """Stop the worker and park the rig, exactly once."""
        if parked["done"]:
            return
        parked["done"] = True
        worker.stop()
        worker.join(timeout=5)
        close_rig(guard, rig)

    def on_close():
        try:
            park_and_close()
        finally:
            root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)

    root.after(100, refresh)
    if readback:
        root.after(300, open_readback)
    if sweep is not None:                       # --sweep: start it at once
        root.after(500, on_sweep)
    if autoclose is not None:                   # smoke test: sweep, then quit
        if readback:                            # (readback: hold still instead)
            root.after(500, lambda: worker.goto(5.0))
        elif sweep is None:
            root.after(500, lambda: worker.start_sweep(
                L.piezo_ao_min_v, L.piezo_ao_max_v, rate, bounce=True))
        root.after(int(autoclose * 1000), on_close)
    try:
        root.mainloop()
    finally:
        # Ctrl-C in the terminal, or any error out of the window: the rig
        # is parked here, the same as on the close button.
        park_and_close()
    return 0


# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Move the Z piezo with a slider or a sweep and watch the "
                    "command and the sense readback against time.")
    p.add_argument("--config", type=Path, help="rig config JSON")
    p.add_argument("--simulate", action="store_true",
                   help="fake card, no hardware")
    p.add_argument("--rate", type=float, default=2.0,
                   help="slew rate for slider moves, V/s (default 2 = 124 nm/s)")
    p.add_argument("--hold-ms", type=float, default=10.0,
                   help="length of each hold, ms (default 10)")
    p.add_argument("--window", type=float, default=30.0,
                   help="seconds of history shown (default 30)")
    p.add_argument("--headless", type=float, metavar="SECONDS",
                   help="no window: sweep the whole range back and forth for "
                        "this long, print a report, exit")
    p.add_argument("--readback", action="store_true",
                   help="also open the readback-only window at start")
    p.add_argument("--sweep", type=float, nargs=2, metavar=("FROM", "TO"),
                   help="GUI: fill the sweep boxes with these volts and start "
                        "sweeping at once, e.g. --sweep 4.90 4.98 for a 5 nm pull")
    p.add_argument("--sweep-rate", type=float, default=None,
                   help="GUI: the sweep box's rate in V/s (default: --rate). "
                        "A 5 nm pull at the experiment's 20 nm/s is 0.32 V/s; "
                        "0.02 V/s makes it slow enough to watch")
    p.add_argument("--ymode", choices=("full", "sweep", "auto", "manual"),
                   default="full", help="GUI: y-axis mode at start")
    p.add_argument("--out", type=Path, help="CSV to write (headless: always; "
                                            "GUI: the Save CSV button)")
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
        if cfg.channels.low_res_device is None:
            # The point of this test is the readback; give the fake rig one.
            cfg.channels.low_res_device = "dev2"
            log.info("simulate: pretending a second card so the sense line "
                     "has something to show")
    if not cfg.simulate and not cfg.channels.has_piezo_sense:
        log.warning("channels.low_res_device is None: the command will be "
                    "plotted but there is no sense readback to compare it with")

    try:
        if args.headless is not None:
            out = args.out or (_ROOT / "data" /
                               f"piezo_sweep_{time.strftime('%Y%m%d_%H%M%S')}.csv")
            return run_headless(cfg, args.headless, args.rate, args.hold_ms, out)
        return run_gui(cfg, args.rate, args.hold_ms, args.window, args.out,
                       autoclose=args.autoclose,
                       config_name=args.config.name if args.config else "defaults",
                       readback=args.readback,
                       sweep=tuple(args.sweep) if args.sweep else None,
                       sweep_rate=args.sweep_rate, ymode_start=args.ymode)
    except (ConfigError, SafetyViolation) as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.info("interrupted; outputs parked")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
