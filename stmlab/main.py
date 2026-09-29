"""Entry point: orchestration only.

Every line below should be a sentence about the experiment, not about DAQmx.
If this stops reading that way, the abstraction has leaked.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path

from . import analysis, approach, calibrate, storage, trace
from .config import ConfigError, RigConfig, validate
from .instrument import Rig
from .safety import RigState, SafeSession, SafetyViolation

log = logging.getLogger("stmbj")


def run(cfg: RigConfig, out_path: Path, n_traces: int,
        do_calibrate: bool = True, require_engaged: bool = False,
        coarse: bool = False) -> int:
    stop = threading.Event()

    def on_signal(signum, frame):
        del signum, frame
        if stop.is_set():
            log.warning("second interrupt; exiting now")
            sys.exit(130)
        log.warning("interrupt: finishing the current attempt, then stopping")
        stop.set()

    signal.signal(signal.SIGINT, on_signal)

    for warning in validate(cfg):
        log.warning("config: %s", warning)

    with SafeSession(cfg):                      # verifies devices, parks output
        with Rig(cfg) as rig:                   # opens tasks
            if do_calibrate:
                calibrate.session_calibration(rig)

            rig.set_bias(cfg.ramp.bias_v)

            if coarse:
                approach.coarse_approach(rig, stop_flag=stop)

            if approach.recover_headroom(rig) is not RigState.ENGAGED:
                log.error("could not engage")
                return 1

            with storage.SessionWriter(out_path, cfg) as writer:
                stats = trace.trace_loop(
                    rig, n=n_traces, on_trace=writer.append,
                    stop_flag=stop, require_engaged=require_engaged)
                writer.write_summary(stats)

            rig.withdraw()

    log.info("%d accepted / %d attempts (%.0f%%)",
             stats["accepted"], stats["attempts"],
             100 * stats["acceptance_rate"])
    for reason, count in sorted(stats["rejections"].items(),
                                key=lambda kv: -kv[1]):
        log.info("  rejected %5d  %s", count, reason)
    return 0


def summarise(path: Path, peak_window: float = 0.5) -> int:
    """Print the histogram peak of a finished session."""
    with storage.Session(path) as session:
        n = len(session)
        if n == 0:
            log.error("%s contains no traces", path)
            return 1
        centres, counts = analysis.log_histogram(session.conductances())

    peak = analysis.peak_position(centres, counts, around=0.0,
                                  window=peak_window)
    print(f"{path.name}: {n} traces")
    print(f"  1 G0 peak at {peak:+.4f} decades "
          f"({'within' if abs(peak) < 0.05 else 'OUTSIDE'} 0.05 of 0)")
    if abs(abs(peak) - 1.0) < 0.05:
        print("  an offset of ~1.000 decade is a 10x gain error")
    elif abs(abs(peak) - 0.301) < 0.03:
        print("  an offset of ~0.301 decade is a factor of two in bias, "
              "or G0 defined as e^2/h instead of 2e^2/h")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stmbj",
        description="STM break-junction acquisition (constant bias).")
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path,
                        help="rig config JSON; defaults are used if omitted")
    common.add_argument("-v", "--verbose", action="store_true")

    r = sub.add_parser("run", parents=[common], help="acquire traces")
    r.add_argument("-n", "--traces", type=int, default=None,
                   help="number of accepted traces to collect")
    r.add_argument("-o", "--out", type=Path, default=None,
                   help="output .h5 (default: data/stmbj_<timestamp>.h5)")
    r.add_argument("--simulate", action="store_true",
                   help="run against the simulated card, no hardware")
    r.add_argument("--no-calibrate", action="store_true",
                   help="skip the session zero and group-delay measurement")
    r.add_argument("--coarse", action="store_true",
                   help="run the coarse approach first")
    r.add_argument("--require-engaged", action="store_true",
                   help="also require that each trace started in metallic "
                        "contact; Igor left this criterion disabled")

    sub.add_parser("check", parents=[common],
                   help="validate a config without touching hardware")

    s = sub.add_parser("summarise", parents=[common],
                       help="histogram peak of a finished session")
    s.add_argument("path", type=Path)

    d = sub.add_parser("dump-config", parents=[common],
                       help="write the default config as JSON")
    d.add_argument("path", type=Path)

    b = sub.add_parser("bringup", parents=[common],
                       help="first-contact hardware checks (rig PC)")
    b.add_argument("step", type=int, choices=(1, 2, 3, 4, 5))
    b.add_argument("--resistor", type=float, default=1e6,
                   help="resistance used in step 4, in ohms")
    b.add_argument("--move", action="store_true",
                   help="step 5 only: actually move the coarse actuator. "
                        "Only with the tip clear of the sample.")
    b.add_argument("--port",
                   help="step 5 only: serial port, e.g. COM3")
    b.add_argument("--simulate", action="store_true",
                   help="exercise the harness, not the hardware")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S")

    cfg = RigConfig.from_json(args.config) if args.config else RigConfig()

    if args.command == "dump-config":
        cfg.to_json(args.path)
        print(f"wrote {args.path}")
        return 0

    if args.command == "check":
        try:
            warnings = validate(cfg)
        except ConfigError as exc:
            print(exc)
            return 1
        for w in warnings:
            print(f"warning: {w}")
        print("config is valid")
        return 0

    if args.command == "summarise":
        return summarise(args.path)

    if args.command == "bringup":
        from . import bringup
        argv_bringup = [str(args.step)]
        if args.config:
            argv_bringup += ["--config", str(args.config)]
        if args.simulate:
            argv_bringup.append("--simulate")
        if args.verbose:
            argv_bringup.append("-v")
        if args.move:
            argv_bringup.append("--move")
        if args.port:
            argv_bringup += ["--port", args.port]
        argv_bringup += ["--resistor", str(args.resistor)]
        return bringup.main(argv_bringup)

    # run
    if args.simulate:
        cfg.simulate = True
    n_traces = args.traces if args.traces is not None \
        else cfg.ramp.traces_target
    out = args.out or Path("data") / \
        f"stmbj_{time.strftime('%Y%m%d_%H%M%S')}.h5"

    try:
        return run(cfg, out, n_traces,
                   do_calibrate=not args.no_calibrate,
                   require_engaged=args.require_engaged,
                   coarse=args.coarse)
    except (ConfigError, SafetyViolation) as exc:
        log.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
