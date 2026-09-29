#!/usr/bin/env python3
"""AC bias hold: park the junction and replace the DC bias with a pure sine.

Igor equivalent: CreateInputs, AC-hold branch, Functions_STMBJ.ipf:1539-1564,
played by the same MeasureBreakJunctions loop (Functions_STMBJ.ipf:1664) as
every other mode. The trajectory is: initial pull, cap (DC bias, junction
settles), hold at constant piezo while the bias channel carries
``ACAmp * sin(2*pi*ACFreq*1000*t)`` -- the sine *replaces* the DC baseline,
there is no DC offset under the modulation (Igor line 1564) -- then a second
cap and a final pull. ``ACFreq`` is in kHz, as Igor's G_ACFreq was.

Amplitude (default 0.8 V, Igor's G_ACAmp) exceeds the 0.5 V baseline bias
limit, so this runner deliberately -- and loudly -- raises
``limits.bias_max_v`` to 1.1x the amplitude before building the ramp, the
same way Igor's rungo() sweeps simply went where their globals said.

Per trace a lock-in-style demodulation is printed over the ac_hold segment:
with f the modulation frequency and I(t) the calibrated current,

    X = mean(I * sin(2*pi*f*t)),  Y = mean(I * cos(2*pi*f*t))
    R = 2 * hypot(X, Y)           # amplitude of the current at f, in amps
    G = R / (amp_v * G0_SIEMENS)  # conductance in G0

which is what a lock-in referenced to the written sine would report. No
TestTrace selection is applied: Igor selected only constant pulls, and a
hold that broke early is still an answer, so every aligned trace is kept.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import json
import logging
import math
import signal
import threading
import time

import numpy as np

from stmlab import approach, calibrate, ramps, storage, trace
from stmlab.approach import ApproachError
from stmlab.config import G0_SIEMENS, ConfigError, RigConfig, validate
from stmlab.instrument import Rig
from stmlab.safety import RigState, SafeSession, SafetyViolation

log = logging.getLogger("ac_hold")

PKG_ROOT = Path(__file__).resolve().parents[2]


def lockin_summary(record: trace.TraceRecord, ramp: ramps.ModeRamp,
                   cfg: RigConfig) -> dict:
    """Software lock-in over the ac_hold segment of one aligned trace.

    ``record`` is already cut at the measured AI/AO delay, so
    ``ramp.segments`` indexes it directly and the reference sine
    ``sin(2*pi*f*t)`` with t = 0 at the segment start is phase-true to what
    was written (Igor line 1564 wrote exactly that phase).
    """
    a, b = ramp.segments["ac_hold"]
    f = ramp.meta["freq_hz"]
    amp_v = ramp.meta["amp_v"]
    fs = record.sample_rate_hz

    current_a = cfg.cal.volts_to_amps(record.current_v[a:b])
    t = np.arange(b - a) / fs
    x = float(np.mean(current_a * np.sin(2 * np.pi * f * t)))
    y = float(np.mean(current_a * np.cos(2 * np.pi * f * t)))
    r = 2.0 * math.hypot(x, y)
    g_g0 = r / (amp_v * G0_SIEMENS)
    phase_deg = math.degrees(math.atan2(y, x))
    return {"X_a": x, "Y_a": y, "R_a": r, "G_g0": g_g0,
            "phase_deg": phase_deg, "n_samples": b - a}


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

    ac = cfg.ac_hold

    # The sine replaces the DC baseline at full amplitude, and the baseline
    # bias limit (0.5 V) was set for 100 mV constant-bias work. Raise it
    # deliberately and loudly, exactly as far as this mode needs -- never
    # silently, and never further.
    needed_limit = 1.1 * abs(ac.amp_v)
    if cfg.limits.bias_max_v < needed_limit:
        log.warning("RAISING bias_max_v from %.3f V to %.3f V (1.1 x the "
                    "%.3f V AC amplitude). This limit exists to protect the "
                    "junction from accidental large bias; the AC hold needs "
                    "it this high on purpose.",
                    cfg.limits.bias_max_v, needed_limit, ac.amp_v)
        cfg.limits.bias_max_v = needed_limit

    # The headroom pre-check in engage() must match this mode's excursion:
    # the caps and the hold sit at constant piezo, so the net descent is
    # initial + final pull (Igor lines 1557-1560).
    cfg.ramp.pull_length_nm = ac.init_pull_nm + ac.final_pull_nm
    log.info("ac hold: %.2f nm hold at %.3f V amplitude, %.3f kHz, after a "
             "%.2f nm initial pull; %.2f nm caps; %.2f nm final pull; "
             "headroom check set to the %.2f nm net descent",
             ac.hold_nm, ac.amp_v, ac.freq_khz, ac.init_pull_nm, ac.cap_nm,
             ac.final_pull_nm, cfg.ramp.pull_length_nm)

    for warning in validate(cfg):
        log.warning("config: %s", warning)

    freq_hz = ac.freq_khz * 1e3
    if freq_hz > cfg.ramp.sample_rate_hz / 10:
        log.warning("modulation at %.0f Hz gives only %.1f samples per "
                    "period at %.0f Hz sampling: the sine is coarsely "
                    "stepped by the DAC and the lock-in sums converge "
                    "slowly. Consider lowering --freq-khz below %.1f.",
                    freq_hz, cfg.ramp.sample_rate_hz / freq_hz,
                    cfg.ramp.sample_rate_hz,
                    cfg.ramp.sample_rate_hz / 10 / 1e3)

    accepted = 0
    attempts = 0
    rejections: dict[str, int] = {}
    segments_json: str | None = None
    lockin_g0: list[float] = []

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

                    # Each attempt gets its own ramp anchored at wherever
                    # contact actually is.
                    ramp = ramps.build_ac_hold(
                        cfg, rig.piezo_v, sample_rate_hz=rig.sample_rate_hz)

                    record = trace.capture(rig, ramp, index=accepted)
                    if record is None:          # alignment failed: retry
                        rejections["alignment"] = \
                            rejections.get("alignment", 0) + 1
                        continue

                    # No TestTrace: Igor selected only constant pulls.
                    writer.append(accepted, record)

                    if segments_json is None:
                        # Same segment map for every trace in this file: the
                        # geometry is fixed for the session, only its
                        # start_piezo_v moves. Written once, after the first
                        # append has created the datasets.
                        segments_json = json.dumps(ramp.segments)
                        writer._h5.attrs["segments_json"] = segments_json
                        writer._h5.attrs["ac_meta_json"] = \
                            json.dumps(ramp.meta)

                    li = lockin_summary(record, ramp, cfg)
                    lockin_g0.append(li["G_g0"])
                    log.info("trace %3d/%d: lock-in over the %d-sample hold "
                             "at %.3f kHz: R = %.3e A, G = %8.4f G0, "
                             "phase %+6.1f deg (attempt %d)",
                             accepted + 1, n_traces, li["n_samples"],
                             ac.freq_khz, li["R_a"], li["G_g0"],
                             li["phase_deg"], attempts)
                    accepted += 1

                stats = {"accepted": accepted,
                         "attempts": attempts,
                         "acceptance_rate":
                             accepted / attempts if attempts else 0.0,
                         "rejections": rejections,
                         "segments": ramp.segments if accepted else None,
                         "amp_v": ac.amp_v,
                         "freq_khz": ac.freq_khz,
                         "lockin_g0": lockin_g0,
                         "lockin_g0_median":
                             float(np.median(lockin_g0))
                             if lockin_g0 else None}
                writer.write_summary(stats)

            rig.withdraw()

    log.info("%d accepted / %d attempts (%.0f%%)",
             accepted, attempts, 100 * accepted / attempts if attempts else 0)
    for reason, count in sorted(rejections.items(), key=lambda kv: -kv[1]):
        log.info("  rejected %5d  %s", count, reason)
    if lockin_g0:
        log.info("median lock-in conductance over %d holds: %.4f G0",
                 len(lockin_g0), float(np.median(lockin_g0)))
    return 0 if accepted else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="AC bias hold: sine bias on a held junction "
                    "(Igor: CreateInputs AC-hold branch, "
                    "Functions_STMBJ.ipf:1539-1564).")
    p.add_argument("--config", type=Path,
                   help="rig config JSON; defaults are used if omitted")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--simulate", action="store_true",
                   help="run against the simulated card, no hardware")
    p.add_argument("-n", "--traces", type=int, default=20,
                   help="number of AC-hold traces to collect (default 20)")
    p.add_argument("-o", "--out", type=Path, default=None,
                   help="output .h5 (default: data/ac_hold_<timestamp>.h5)")
    p.add_argument("--no-calibrate", action="store_true",
                   help="skip the session zero and group-delay measurement")

    m = p.add_argument_group("AC hold (override cfg.ac_hold)")
    m.add_argument("--amp", type=float, default=None,
                   help="sine amplitude in volts, replaces the DC bias "
                        "during the hold (G_ACAmp, default 0.8)")
    m.add_argument("--freq-khz", type=float, default=None,
                   help="modulation frequency in kHz (G_ACFreq, default 10)")
    m.add_argument("--hold-nm", type=float, default=None,
                   help="hold length in nm at the pull rate, i.e. the hold "
                        "lasts as long as pulling this far would "
                        "(G_ACHoldLength, default 3)")
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

    for flag, field in (("amp", "amp_v"), ("freq_khz", "freq_khz"),
                        ("hold_nm", "hold_nm")):
        value = getattr(args, flag)
        if value is not None:
            setattr(cfg.ac_hold, field, value)

    out = args.out or PKG_ROOT / "data" / \
        f"ac_hold_{time.strftime('%Y%m%d_%H%M%S')}.h5"

    try:
        return run(cfg, out, args.traces,
                   do_calibrate=not args.no_calibrate)
    except (ConfigError, SafetyViolation) as exc:
        log.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
