#!/usr/bin/env python3
"""High-bias hold: park the junction under a large DC field and watch it.

Igor equivalent: CreateInputs, HB-hold branch, Functions_STMBJ.ipf:1566-1599,
played by the same MeasureBreakJunctions loop (Functions_STMBJ.ipf:1664) that
ran the constant pulls. The trajectory is: an initial pull, a short cap at
the DC baseline, a hold at an elevated DC bias (G_HBBias, written as
``-HBBias``, Igor line 1592), a second cap, and a final pull that breaks the
junction. Igor forced BiasSave on for this mode (line 1566); here the raw
measured voltage and current are always stored, so nothing needs forcing.

The Vzero link (Igor lines 1595-1599): if the Voltage_Offset panel had
VzeroCheckBox ticked, CreateInputs replaced the hold bias with the measured
offset, ``HBBias = Vzero/1000``, so the hold happened at the bias that nulls
the current -- the zero-field control for the high-field runs. ``--use-vzero``
reproduces that: after the first engage, ``stmlab.vzero.measure_offset`` runs
once (Igor: OffsetVoltage, Functions_STMBJ.ipf:920) and its result is passed
into every ``build_hb_hold`` of the session.

The default hold bias (0.8 V) exceeds the config's 0.5 V bias refusal limit
on purpose -- that limit protects the constant-bias modes. This runner raises
``limits.bias_max_v`` to 1.1x the hold bias, deliberately and loudly, before
validating (the same ceiling Igor's rungo sweep reached).

No TestTrace selection is applied: Igor applied TestTrace only to constant
pulls, and a hold record in which the junction dies early is still an answer
about stability, so every aligned trace is kept.
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

from stmlab import approach, calibrate, ramps, storage, trace, vzero
from stmlab.approach import ApproachError
from stmlab.config import ConfigError, RigConfig, validate
from stmlab.instrument import Rig
from stmlab.safety import RigState, SafeSession, SafetyViolation

log = logging.getLogger("hb_hold")

PKG_ROOT = Path(__file__).resolve().parents[2]


def hold_conductance(record: trace.TraceRecord, ramp: ramps.ModeRamp,
                     cfg: RigConfig) -> float:
    """Mean conductance over the hb_hold segment of one cut trace.

    The segment indices from ``ramps.ModeRamp.segments`` index the cut trace
    directly (capture already removed the pads and the alignment delay).
    Divides by the *measured* junction voltage sample by sample, Igor's own
    convention (Functions_STMBJ.ipf:388-389) -- essential here, because the
    bias during the hold is not the baseline the record is labelled with.
    """
    a, b = ramp.segments["hb_hold"]
    g0 = record.conductance_g0(cfg)
    b = min(b, g0.size)
    if a >= b:
        return float("nan")
    return float(np.mean(g0[a:b]))


def run(cfg: RigConfig, out_path: Path, n_traces: int,
        use_vzero: bool = False, do_calibrate: bool = True) -> int:
    stop = threading.Event()

    def on_signal(signum, frame):
        del signum, frame
        if stop.is_set():
            log.warning("second interrupt; exiting now")
            sys.exit(130)
        log.warning("interrupt: finishing the current trace, then stopping")
        stop.set()

    signal.signal(signal.SIGINT, on_signal)

    hb = cfg.hb_hold

    # The headroom pre-check in engage() must match this mode's excursion,
    # not the constant-bias default. The hold and both caps are flat, so the
    # net descent is initial + final pull (Igor lines 1584-1587).
    cfg.ramp.pull_length_nm = hb.init_pull_nm + hb.final_pull_nm
    log.info("hb-hold: %.2f nm hold at %+.3f V after a %.2f nm initial pull "
             "(caps %.2f/%.2f nm); %.2f nm final pull; headroom check set to "
             "the %.2f nm net descent",
             hb.hold_nm, hb.hold_bias_v, hb.init_pull_nm, hb.cap_in_nm,
             hb.cap_fin_nm, hb.final_pull_nm, cfg.ramp.pull_length_nm)

    # The 0.5 V default refusal limit protects the constant-bias modes; the
    # whole point of this mode is to exceed it. Raise it deliberately.
    needed = 1.1 * abs(hb.hold_bias_v)
    if cfg.limits.bias_max_v < needed:
        log.warning("RAISING bias_max_v from %.3f V to %.3f V "
                    "(1.1 x the %.3f V hold bias) -- this mode applies HIGH "
                    "BIAS to the junction on purpose",
                    cfg.limits.bias_max_v, needed, hb.hold_bias_v)
        cfg.limits.bias_max_v = needed

    for warning in validate(cfg):
        log.warning("config: %s", warning)

    accepted = 0
    attempts = 0
    rejections: dict[str, int] = {}
    segments_json: str | None = None
    vzero_mv: float | None = None
    hold_g_sum = 0.0

    with SafeSession(cfg):                      # verifies devices, parks output
        with Rig(cfg) as rig:                   # opens tasks
            if do_calibrate:
                calibrate.session_calibration(rig)

            rig.set_bias(cfg.ramp.bias_v)

            if use_vzero:
                # Igor lines 1595-1599: with VzeroCheckBox ticked the hold
                # bias *becomes* the measured offset. Measure it once, in
                # contact, before the acquisition loop.
                try:
                    if approach.recover_headroom(rig) is not RigState.ENGAGED:
                        log.error("cannot engage to measure Vzero")
                        return 1
                except ApproachError as exc:
                    log.error("cannot engage to measure Vzero: %s", exc)
                    return 1
                result = vzero.measure_offset(rig)
                vzero_mv = result.vzero_mv
                log.info("Vzero = %+.3f mV (Izero = %+.3e A): the hold bias "
                         "for every trace of this session is now the "
                         "measured offset, not the %.3f V of cfg.hb_hold "
                         "(Igor Functions_STMBJ.ipf:1595-1599)",
                         vzero_mv, result.izero_a, hb.hold_bias_v)

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
                    ramp = ramps.build_hb_hold(
                        cfg, rig.piezo_v, sample_rate_hz=rig.sample_rate_hz,
                        vzero_mv=vzero_mv)

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

                    g_hold = hold_conductance(record, ramp, cfg)
                    hold_g_sum += g_hold
                    log.info("trace %3d/%d: mean %8.3f G0 over the %.2f nm "
                             "hold at %+.3f V (attempt %d)",
                             accepted + 1, n_traces, g_hold, hb.hold_nm,
                             ramp.meta["hold_bias_v"], attempts)
                    accepted += 1

                stats = {"accepted": accepted,
                         "attempts": attempts,
                         "acceptance_rate":
                             accepted / attempts if attempts else 0.0,
                         "rejections": rejections,
                         "segments": ramp.segments if accepted else None,
                         "hold_bias_v":
                             ramp.meta["hold_bias_v"] if accepted
                             else hb.hold_bias_v,
                         "vzero_mv": vzero_mv,
                         "mean_hold_g0":
                             hold_g_sum / accepted if accepted else None}
                writer.write_summary(stats)

            rig.withdraw()

    log.info("%d accepted / %d attempts (%.0f%%)",
             accepted, attempts, 100 * accepted / attempts if attempts else 0)
    for reason, count in sorted(rejections.items(), key=lambda kv: -kv[1]):
        log.info("  rejected %5d  %s", count, reason)
    return 0 if accepted else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="High-bias junction hold "
                    "(Igor: CreateInputs HB-hold branch, "
                    "Functions_STMBJ.ipf:1566-1599).")
    p.add_argument("--config", type=Path,
                   help="rig config JSON; defaults are used if omitted")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--simulate", action="store_true",
                   help="run against the simulated card, no hardware")
    p.add_argument("-n", "--traces", type=int, default=20,
                   help="number of hold traces to collect (default 20)")
    p.add_argument("-o", "--out", type=Path, default=None,
                   help="output .h5 (default: data/hb_hold_<timestamp>.h5)")
    p.add_argument("--no-calibrate", action="store_true",
                   help="skip the session zero and group-delay measurement")

    m = p.add_argument_group("hold geometry (override cfg.hb_hold)")
    m.add_argument("--hold-bias", type=float, default=None, metavar="V",
                   help="hold bias in volts (G_HBBias; default 0.8). The "
                        "bias refusal limit is raised to 1.1x this value.")
    m.add_argument("--hold-nm", type=float, default=None,
                   help="hold length, nm (G_HBHoldLength; duration = time "
                        "to pull this far)")
    m.add_argument("--use-vzero", action="store_true",
                   help="measure the amplifier offset once after engaging "
                        "and hold at the measured Vzero instead of "
                        "--hold-bias (Igor Functions_STMBJ.ipf:1595-1599)")
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

    if args.hold_bias is not None:
        cfg.hb_hold.hold_bias_v = args.hold_bias
    if args.hold_nm is not None:
        cfg.hb_hold.hold_nm = args.hold_nm

    out = args.out or PKG_ROOT / "data" / \
        f"hb_hold_{time.strftime('%Y%m%d_%H%M%S')}.h5"

    try:
        return run(cfg, out, args.traces, use_vzero=args.use_vzero,
                   do_calibrate=not args.no_calibrate)
    except (ConfigError, SafetyViolation) as exc:
        log.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
