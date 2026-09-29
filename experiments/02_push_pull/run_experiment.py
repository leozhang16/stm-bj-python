#!/usr/bin/env python3
"""Push-pull cycling: re-form the same junction over and over.

Igor equivalent: CreateInputs, PushPull branch, Functions_STMBJ.ipf:1461-1495
(trajectory), played by the same MeasureBreakJunctions loop
(Functions_STMBJ.ipf:1664) that ran the constant pulls. The trajectory is:
an initial pull, then per cycle {hold, push back in, hold, pull out}, then a
final pull to break the junction for good. The bias stays at the DC baseline
throughout (Igor line 1495: JunctionBiasWave = -(TipBias/1000)).

No TestTrace selection is applied: Igor applied TestTrace only to constant
pulls, and a push-pull record that never re-binds is still an answer, so every
aligned trace is kept.
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

import numpy as np

from stmlab import approach, calibrate, ramps, storage, trace
from stmlab.approach import ApproachError
from stmlab.config import ConfigError, RigConfig, validate
from stmlab.instrument import Rig
from stmlab.safety import RigState, SafeSession, SafetyViolation

log = logging.getLogger("push_pull")

PKG_ROOT = Path(__file__).resolve().parents[2]


def start_conductance(record: trace.TraceRecord, cfg: RigConfig) -> float:
    """Median conductance over the first 0.5% of the trace (>= 10 samples).

    The trace begins at the contact point, so this is the conductance of the
    junction the cycling is about to be performed on -- the same window
    Igor's TestTrace used for its (disabled) started-in-contact criterion.
    """
    g0 = record.conductance_g0(cfg)
    n = max(10, int(round(0.005 * g0.size)))
    return float(np.median(g0[:n]))


def run(cfg: RigConfig, out_path: Path, n_traces: int,
        do_calibrate: bool = True) -> int:
    stop = threading.Event()

    def on_signal(signum, frame):
        del signum, frame
        if stop.is_set():
            log.warning("second interrupt; exiting now")
            sys.exit(130)
        log.warning("interrupt: finishing the current trace, then stopping")
        stop.set()

    signal.signal(signal.SIGINT, on_signal)

    pp = cfg.push_pull

    # The headroom pre-check in engage() must match this mode's excursion,
    # not the constant-bias default. Net descent of a push-pull trajectory is
    # initial + final: every push is undone by a matching pull, so the cycles
    # net to zero (Igor lines 1483-1486).
    cfg.ramp.pull_length_nm = pp.initial_pull_nm + pp.final_pull_nm
    log.info("push-pull: %d cycle(s) of %+.2f nm with %.2f nm holds, after a "
             "%.2f nm initial pull; %.2f nm final pull; headroom check set "
             "to the %.2f nm net descent",
             pp.cycles, pp.push_pull_nm, pp.hold_nm, pp.initial_pull_nm,
             pp.final_pull_nm, cfg.ramp.pull_length_nm)

    for warning in validate(cfg):
        log.warning("config: %s", warning)

    accepted = 0
    attempts = 0
    rejections: dict[str, int] = {}
    segments_json: str | None = None

    with SafeSession(cfg):                      # verifies devices, parks output
        with Rig(cfg) as rig:                   # opens tasks
            if do_calibrate:
                calibrate.session_calibration(rig)

            rig.set_bias(cfg.ramp.bias_v)

            with storage.SessionWriter(out_path, cfg) as writer:
                while accepted < n_traces and attempts < cfg.ramp.max_attempts:
                    if stop.is_set():
                        log.info("stopping: stop flag set")
                        break

                    attempts += 1
                    rig.attempts = attempts

                    try:
                        if approach.recover_headroom(rig) \
                                is not RigState.ENGAGED:
                            rejections["engage"] = \
                                rejections.get("engage", 0) + 1
                            continue
                    except ApproachError as exc:
                        log.error("cannot engage and the coarse actuator "
                                  "cannot help: %s", exc)
                        break

                    # Build the trajectory from wherever contact actually is:
                    # each attempt gets its own ramp anchored at rig.piezo_v.
                    ramp = ramps.build_push_pull(
                        cfg, rig.piezo_v, sample_rate_hz=rig.sample_rate_hz)

                    record = trace.capture(rig, ramp, index=accepted)
                    if record is None:          # alignment failed: retry
                        rejections["alignment"] = \
                            rejections.get("alignment", 0) + 1
                        continue

                    # No TestTrace here -- Igor selected only constant pulls.
                    writer.append(accepted, record)

                    if segments_json is None:
                        # Same segment map for every trace in this file: the
                        # ramp geometry is fixed for the session, only its
                        # start_piezo_v moves. Written once, after the first
                        # append has created the datasets.
                        segments_json = json.dumps(ramp.segments)
                        writer._h5.attrs["segments_json"] = segments_json

                    g_start = start_conductance(record, cfg)
                    log.info("trace %3d/%d: started at %8.3f G0 from "
                             "%.4f V on the piezo (attempt %d)",
                             accepted + 1, n_traces, g_start,
                             record.start_piezo_v, attempts)
                    accepted += 1

                stats = {"accepted": accepted,
                         "attempts": attempts,
                         "acceptance_rate":
                             accepted / attempts if attempts else 0.0,
                         "rejections": rejections,
                         "segments": ramp.segments if accepted else None,
                         "cycles": pp.cycles}
                writer.write_summary(stats)

            rig.withdraw()

    log.info("%d accepted / %d attempts (%.0f%%)",
             accepted, attempts, 100 * accepted / attempts if attempts else 0)
    for reason, count in sorted(rejections.items(), key=lambda kv: -kv[1]):
        log.info("  rejected %5d  %s", count, reason)
    return 0 if accepted else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Push-pull junction cycling "
                    "(Igor: CreateInputs PushPull branch, "
                    "Functions_STMBJ.ipf:1461-1495).")
    p.add_argument("--config", type=Path,
                   help="rig config JSON; defaults are used if omitted")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--simulate", action="store_true",
                   help="run against the simulated card, no hardware")
    p.add_argument("-n", "--traces", type=int, default=20,
                   help="number of push-pull traces to collect (default 20)")
    p.add_argument("-o", "--out", type=Path, default=None,
                   help="output .h5 (default: data/push_pull_<timestamp>.h5)")
    p.add_argument("--no-calibrate", action="store_true",
                   help="skip the session zero and group-delay measurement")

    m = p.add_argument_group("push-pull geometry (override cfg.push_pull)")
    m.add_argument("--cycles", type=int, default=None,
                   help="push-pull cycles per trace (G_NumPushPullCycles)")
    m.add_argument("--push-nm", type=float, default=None,
                   help="push/pull excursion per half-cycle, nm "
                        "(G_PushPullLength)")
    m.add_argument("--hold-nm", type=float, default=None,
                   help="hold length either side of each push, nm "
                        "(G_HoldLength; duration = time to pull this far)")
    m.add_argument("--initial-nm", type=float, default=None,
                   help="initial pull before the first cycle, nm "
                        "(G_InitialPullLength)")
    m.add_argument("--final-nm", type=float, default=None,
                   help="final pull after the last cycle, nm "
                        "(G_FinalPullLength)")
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

    for flag, field in (("cycles", "cycles"), ("push_nm", "push_pull_nm"),
                        ("hold_nm", "hold_nm"), ("initial_nm",
                                                 "initial_pull_nm"),
                        ("final_nm", "final_pull_nm")):
        value = getattr(args, flag)
        if value is not None:
            setattr(cfg.push_pull, field, value)

    out = args.out or PKG_ROOT / "data" / \
        f"push_pull_{time.strftime('%Y%m%d_%H%M%S')}.h5"

    try:
        return run(cfg, out, args.traces,
                   do_calibrate=not args.no_calibrate)
    except (ConfigError, SafetyViolation) as exc:
        log.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
