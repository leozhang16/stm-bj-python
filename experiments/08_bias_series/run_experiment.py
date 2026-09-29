#!/usr/bin/env python3
"""Igor's scripted bias campaign: N traces at each of a list of biases.

Igor equivalent: ``rungo()``, Setup1_STMBJ.ipf:138-178. A flat loop that set
``G_TipBias``, set ``G_StopNumber`` to the cumulative trace count, and called
``StartMeasurement`` -- fourteen times, unattended, overnight.

Igor's list, built at :147-155::

    bias = (p+1) * (-100)     mV, so -100, -200, ... -1400
    bias[9]  = -100           then five entries overridden by hand
    bias[10] = -900
    bias[11] = -1000
    bias[12] = -1100
    bias[13] = -100

giving -100 -200 -300 -400 -500 -600 -700 -800 -900 -100 -900 -1000 -1100
-100 mV, 1000 traces each. The repeats are not sloppiness: -100 mV appears at
positions 0, 9 and 13 as a CONTROL. If the -100 mV histogram at the end of a
fourteen-hour run does not match the one from the start, the tip or the
sample changed and the whole series is suspect. That structure is preserved
in ``IGOR_RUNGO_BIAS_MV`` and is the default.

**Resume.** Igor resumed with ``FindLevel/EDGE=1 /P StartNumWave,
SavedNumber`` (:163-165): look up how many traces are already saved, find
which segment that count falls in, and start there. That mattered because
runs died. Here the same idea reads the output directory: a step whose file
already holds its full complement is skipped, and an incomplete one is
re-run from scratch (its partial file is overwritten, not appended to --
mixing traces from before and after a crash into one file, with one
calibration attached, would be worse than losing them).

**The bias limit is a real obstacle, on purpose.** Igor's series reaches
1100 mV. ``SafetyLimits.bias_max_v`` defaults to 500 mV, so this experiment
REFUSES to start until you raise it with ``--max-bias``. That is not
bureaucracy: 1.1 V across a single-molecule junction is enough to break the
molecule, electromigrate the electrodes, and drive faradaic chemistry if
there is any solvent present. Igor applied it with no guard at all. Raising
the limit should be a thing you did on purpose, in a command you can find
again in your shell history.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import json
import logging
import signal
import threading
import time

from stmlab import approach, calibrate, storage, trace
from stmlab.approach import ApproachError
from stmlab.config import ConfigError, RigConfig, validate
from stmlab.instrument import Rig
from stmlab.safety import RigState, SafeSession, SafetyViolation

log = logging.getLogger("bias_series")

PKG_ROOT = Path(__file__).resolve().parents[2]

# Igor rungo(), Setup1_STMBJ.ipf:147-155. Sign included: Igor's biases are
# negative. Positions 0, 9 and 13 are the -100 mV control repeats.
IGOR_RUNGO_BIAS_MV = [-100.0, -200.0, -300.0, -400.0, -500.0, -600.0,
                      -700.0, -800.0, -900.0, -100.0, -900.0, -1000.0,
                      -1100.0, -100.0]
IGOR_RUNGO_TRACES_PER_BIAS = 1000       # counts_EachBias, :145


def step_path(out_dir: Path, index: int, bias_mv: float) -> Path:
    """One file per step. The index is in the name because the same bias
    appears more than once and the ORDER is the experiment: step 00 at
    -100 mV and step 13 at -100 mV are the control pair, and a filename that
    collided them would destroy the comparison the series exists to make."""
    return out_dir / f"step_{index:02d}_{bias_mv:+.0f}mV.h5"


def completed_traces(path: Path) -> int:
    """How many traces a step file already holds, or 0 if it is absent or
    unreadable. A half-written file from a crash reads as incomplete, which
    is what we want."""
    if not path.exists():
        return 0
    try:
        import h5py
        with h5py.File(path, "r") as h5:
            return int(h5.attrs.get("n_traces", 0))
    except Exception:
        log.warning("could not read %s; treating it as incomplete", path.name)
        return 0


def plan(out_dir: Path, biases_mv: list[float], n_traces: int
         ) -> list[tuple[int, float, Path, int]]:
    """(index, bias_mv, path, already_done) for every step, in order."""
    return [(i, mv, step_path(out_dir, i, mv),
             completed_traces(step_path(out_dir, i, mv)))
            for i, mv in enumerate(biases_mv)]


def check_bias_limits(cfg: RigConfig, biases_mv: list[float]) -> None:
    """Refuse the whole campaign if any step exceeds the bias limit.

    Checked up front, not per step: discovering at step 11 of 14 that the
    limit blocks 1100 mV means eleven hours of acquisition followed by a
    crash, and a series with a hole in it.
    """
    limit_mv = cfg.limits.bias_max_v * 1000.0
    over = sorted({mv for mv in biases_mv if abs(mv) > limit_mv})
    if over:
        need = max(abs(mv) for mv in over) / 1000.0
        raise SafetyViolation(
            f"this series reaches {', '.join(f'{mv:+.0f}' for mv in over)} mV "
            f"but limits.bias_max_v is {limit_mv:.0f} mV.\n"
            f"Igor's rungo applied these with no guard. If you mean to, pass "
            f"--max-bias {need:.2f} (volts).\n"
            f"At {need:.1f} V a single-molecule junction can break, the "
            f"electrodes can electromigrate, and any solvent present will do "
            f"chemistry.")


def run(cfg: RigConfig, out_dir: Path, biases_mv: list[float], n_traces: int,
        do_calibrate: bool, resume: bool, dry_run: bool) -> int:
    check_bias_limits(cfg, biases_mv)

    steps = plan(out_dir, biases_mv, n_traces)
    todo = [s for s in steps if not (resume and s[3] >= n_traces)]

    log.info("bias series: %d step(s) x %d trace(s) = %d traces total",
             len(biases_mv), n_traces, len(biases_mv) * n_traces)
    for i, mv, path, done in steps:
        state = "done" if (resume and done >= n_traces) else \
            (f"partial ({done}), will redo" if done else "pending")
        log.info("  step %2d  %+8.1f mV  %-28s %s", i, mv, path.name, state)

    if resume and len(todo) < len(steps):
        log.info("resuming: %d step(s) already complete, %d to run",
                 len(steps) - len(todo), len(todo))
    if dry_run:
        log.info("--dry-run: stopping before touching hardware")
        return 0
    if not todo:
        log.info("nothing to do; every step is complete")
        return 0

    stop = threading.Event()

    def on_signal(signum, frame):
        del signum, frame
        if stop.is_set():
            log.warning("second interrupt; exiting now")
            sys.exit(130)
        log.warning("interrupt: finishing the current step, then stopping. "
                    "Re-run with --resume to pick up where this left off.")
        stop.set()

    signal.signal(signal.SIGINT, on_signal)

    for warning in validate(cfg):
        log.warning("config: %s", warning)

    out_dir.mkdir(parents=True, exist_ok=True)
    done_steps: list[tuple[int, float, dict]] = []
    t0 = time.time()

    with SafeSession(cfg):
        with Rig(cfg) as rig:
            if do_calibrate:
                calibrate.session_calibration(rig)

            for index, bias_mv, path, _ in todo:
                if stop.is_set():
                    break

                # The bias is a config field, and the config is written into
                # the file -- so setting it here is what makes each file
                # self-describing. Igor set G_TipBias and relied on
                # ParameterWave[10] to record it.
                cfg.ramp.bias_v = bias_mv / 1000.0
                rig.set_bias(cfg.ramp.bias_v)

                # The preamp zero drifts, and fourteen hours is long enough
                # to matter. Re-measure per step, not once per campaign.
                if do_calibrate:
                    cfg.cal.current_zero_v = calibrate.measure_zero(rig)

                log.info("step %d/%d: %+.0f mV, %d traces -> %s",
                         index + 1, len(biases_mv), bias_mv, n_traces,
                         path.name)

                try:
                    if approach.recover_headroom(rig) is not RigState.ENGAGED:
                        log.error("step %d: could not engage; stopping", index)
                        break
                except ApproachError as exc:
                    log.error("step %d: cannot engage: %s", index, exc)
                    break

                with storage.SessionWriter(path, cfg) as writer:
                    writer._h5.attrs["series_index"] = index
                    writer._h5.attrs["series_bias_mv"] = bias_mv
                    writer._h5.attrs["series_length"] = len(biases_mv)
                    stats = trace.trace_loop(
                        rig, n=n_traces, on_trace=writer.append,
                        stop_flag=stop)
                    stats["series_index"] = index
                    stats["series_bias_mv"] = bias_mv
                    writer.write_summary(stats)

                done_steps.append((index, bias_mv, stats))
                log.info("step %d: %d accepted / %d attempts (%.0f%%)",
                         index, stats["accepted"], stats["attempts"],
                         100 * stats["acceptance_rate"])

            rig.withdraw()

    elapsed = time.time() - t0
    log.info("ran %d step(s) in %.1f min", len(done_steps), elapsed / 60)
    for index, bias_mv, stats in done_steps:
        log.info("  step %2d  %+8.1f mV  %4d accepted / %4d attempts",
                 index, bias_mv, stats["accepted"], stats["attempts"])

    _write_index(out_dir, biases_mv, n_traces)

    controls = [(i, mv) for i, mv in enumerate(biases_mv)
                if biases_mv.count(mv) > 1]
    if controls:
        log.info("control repeats to compare when analysing: %s",
                 ", ".join(f"step {i} ({mv:+.0f} mV)" for i, mv in controls))
    return 0 if done_steps else 1


def _write_index(out_dir: Path, biases_mv: list[float], n_traces: int) -> None:
    """A manifest beside the files, so the campaign's shape survives even if
    someone later renames or moves the .h5 files."""
    index = {
        "written_iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "traces_per_step": n_traces,
        "steps": [{"index": i, "bias_mv": mv,
                   "file": step_path(out_dir, i, mv).name,
                   "traces": completed_traces(step_path(out_dir, i, mv))}
                  for i, mv in enumerate(biases_mv)],
    }
    path = out_dir / "series_index.json"
    path.write_text(json.dumps(index, indent=2))
    log.info("wrote %s", path.name)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Scripted bias campaign: N traces at each of a list of "
                    "biases (Igor: rungo, Setup1_STMBJ.ipf:138).")
    p.add_argument("--config", type=Path,
                   help="rig config JSON; defaults are used if omitted")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--simulate", action="store_true",
                   help="run against the simulated card, no hardware")
    p.add_argument("--bias-mv", type=float, nargs="+", default=None,
                   metavar="MV",
                   help="the bias list in millivolts (default: Igor's "
                        "fourteen-step rungo series, control repeats and all)")
    p.add_argument("-n", "--traces", type=int,
                   default=IGOR_RUNGO_TRACES_PER_BIAS,
                   help=f"accepted traces per bias "
                        f"(default {IGOR_RUNGO_TRACES_PER_BIAS}, Igor's "
                        f"counts_EachBias)")
    p.add_argument("-o", "--out-dir", type=Path, default=None,
                   help="output directory (default: data/series_<timestamp>/)")
    p.add_argument("--resume", action="store_true",
                   help="skip steps whose file already holds a full complement "
                        "(Igor's FindLevel resume, :163)")
    p.add_argument("--max-bias", type=float, default=None, metavar="VOLTS",
                   help="raise limits.bias_max_v for this run. Required for "
                        "Igor's series, which reaches 1.1 V.")
    p.add_argument("--dry-run", action="store_true",
                   help="print the plan and exit without touching hardware")
    p.add_argument("--no-calibrate", action="store_true",
                   help="skip the session and per-step zero measurement")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S")

    cfg = RigConfig.from_json(args.config) if args.config else RigConfig()
    if args.simulate:
        cfg.simulate = True
    if args.max_bias is not None:
        log.warning("raising the bias limit from %.0f mV to %.0f mV for this "
                    "run, as requested", cfg.limits.bias_max_v * 1000,
                    args.max_bias * 1000)
        cfg.limits.bias_max_v = args.max_bias

    biases = list(args.bias_mv) if args.bias_mv else list(IGOR_RUNGO_BIAS_MV)
    out_dir = args.out_dir or PKG_ROOT / "data" / \
        f"series_{time.strftime('%Y%m%d_%H%M%S')}"

    try:
        return run(cfg, out_dir, biases, args.traces,
                   do_calibrate=not args.no_calibrate, resume=args.resume,
                   dry_run=args.dry_run)
    except (ConfigError, SafetyViolation) as exc:
        log.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
