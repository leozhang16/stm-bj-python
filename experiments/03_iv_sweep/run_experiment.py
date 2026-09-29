#!/usr/bin/env python3
"""IV sweep at a held, partially pulled junction.

Igor equivalent: CreateInputs, IV branch, Functions_STMBJ.ipf:1497-1537
(defaults declared at :99-105), played by the same MeasureBreakJunctions loop
(Functions_STMBJ.ipf:1664) as every other mode. The trajectory is: pull
``iv.init_pull_nm`` out of contact into the tunnelling/molecular regime, hold
the piezo, and while holding sweep the bias in a triangle -- 0 to +max over
the first quarter of the ramp window, +max to -max over the middle half,
-max to 0 over the last quarter (Igor lines 1526-1531) -- with a DC cap
either side of the sweep, then a final pull to break the junction. Igor
negated the whole bias wave ("to have normal convention", line 1533) and
G_IVSignFlag flipped the ramp's polarity (line 1535); both are reproduced by
``ramps.build_iv``.

Igor forced BiasSave=1 and CurrentSaveCheck=1 for this mode (lines
1498-1499) because an IV is meaningless without both records. Here the raw
measured voltage and current are ALWAYS stored, so there is nothing to force.

The default sweep reaches 1 V, above the 0.5 V ``limits.bias_max_v`` default,
so this runner raises the limit to 1.1 * cfg.iv.max_bias_v -- deliberately
and with a loud log line -- before any waveform is built.
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

log = logging.getLogger("iv_sweep")

PKG_ROOT = Path(__file__).resolve().parents[2]


def sweep_stats(record: trace.TraceRecord, cfg: RigConfig,
                window: tuple[int, int]) -> tuple[float, float, bool]:
    """(peak |I| in amps, junction-voltage span in volts, clipped?) over the
    iv_ramp window. "Clipped" means the raw preamp output touched the
    saturation limit, where the reading is a rail, not a current."""
    a, b = window
    i_raw = record.current_v[a:b]
    v_junc = cfg.cal.voltage_input_sign * record.voltage_v[a:b]
    clipped = bool(np.max(np.abs(i_raw)) >= cfg.limits.preamp_saturation_v)
    peak_i = float(np.max(np.abs(cfg.cal.volts_to_amps(i_raw))))
    return peak_i, float(v_junc.max() - v_junc.min()), clipped


def run(cfg: RigConfig, out_path: Path, n_traces: int,
        do_calibrate: bool = True, plot: bool = False) -> int:
    stop = threading.Event()

    def on_signal(signum, frame):
        del signum, frame
        if stop.is_set():
            log.warning("second interrupt; exiting now")
            sys.exit(130)
        log.warning("interrupt: finishing the current trace, then stopping")
        stop.set()

    signal.signal(signal.SIGINT, on_signal)

    iv = cfg.iv

    # The headroom pre-check in engage() must match this mode's excursion:
    # the caps and the sweep hold the piezo still, so the net descent is
    # initial + final pull (Igor lines 1512-1518).
    cfg.ramp.pull_length_nm = iv.init_pull_nm + iv.final_pull_nm
    log.info("iv: %.2f nm initial pull, %.2f nm caps around a %.2f nm sweep "
             "window to +/-%.3f V (%s first), %.2f nm final pull; headroom "
             "check set to the %.2f nm net descent",
             iv.init_pull_nm, iv.cap_nm, iv.ramp_nm, iv.max_bias_v,
             "positive" if iv.positive_first else "negative",
             iv.final_pull_nm, cfg.ramp.pull_length_nm)

    # The sweep exceeds the everyday bias limit by design. Raise the limit
    # deliberately, here, and nowhere else -- and say so at WARNING level so
    # it cannot be missed in a log. Igor had no software bias limit at all.
    needed = 1.1 * iv.max_bias_v
    if cfg.limits.bias_max_v < needed:
        log.warning("RAISING limits.bias_max_v from %.3f V to %.3f V "
                    "(1.1 x iv.max_bias_v) for this IV session -- the sweep "
                    "reaches +/-%.3f V at the junction",
                    cfg.limits.bias_max_v, needed, iv.max_bias_v)
        cfg.limits.bias_max_v = needed

    for warning in validate(cfg):
        log.warning("config: %s", warning)

    accepted = 0
    attempts = 0
    clipped_traces = 0
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

                    # Each attempt gets its own ramp anchored at the actual
                    # contact point; the geometry (and so `segments`) is the
                    # same for every trace in the session.
                    ramp = ramps.build_iv(
                        cfg, rig.piezo_v, sample_rate_hz=rig.sample_rate_hz)

                    record = trace.capture(rig, ramp, index=accepted)
                    if record is None:          # alignment failed: retry
                        rejections["alignment"] = \
                            rejections.get("alignment", 0) + 1
                        continue

                    # No TestTrace selection: Igor applied it only to constant
                    # pulls, and an IV of a junction that broke mid-sweep is
                    # still an answer (it shows up as a flat quarter).
                    writer.append(accepted, record)

                    if segments_json is None:
                        # Written once, after the first append has created the
                        # datasets. iv_analysis reads the copy in the summary
                        # stats; this attribute is the 02-style duplicate.
                        segments_json = json.dumps(ramp.segments)
                        writer._h5.attrs["segments_json"] = segments_json

                    peak_i, v_span, clipped = sweep_stats(
                        record, cfg, ramp.segments["iv_ramp"])
                    if clipped:
                        clipped_traces += 1
                        log.warning("trace %3d: preamp railed during the "
                                    "sweep (junction too conductive for "
                                    "gain %.0e V/A) -- IV shape not "
                                    "trustworthy", accepted + 1,
                                    cfg.cal.preamp_gain_v_per_a)
                    log.info("trace %3d/%d: peak |I| %10.2f nA over a "
                             "%.3f V sweep span, from %.4f V on the piezo "
                             "(attempt %d)",
                             accepted + 1, n_traces, peak_i * 1e9, v_span,
                             record.start_piezo_v, attempts)
                    accepted += 1

                stats = {"accepted": accepted,
                         "attempts": attempts,
                         "acceptance_rate":
                             accepted / attempts if attempts else 0.0,
                         "rejections": rejections,
                         "clipped_traces": clipped_traces,
                         # iv_analysis.py reads these two to cut the sweep
                         # out of each stored trace and split its quarters.
                         "segments": ramp.segments if accepted else None,
                         "quarters":
                             list(ramp.meta["quarters"]) if accepted else None,
                         "max_bias_v": iv.max_bias_v,
                         "positive_first": iv.positive_first}
                writer.write_summary(stats)

            rig.withdraw()

    log.info("%d accepted / %d attempts (%.0f%%), %d clipped",
             accepted, attempts,
             100 * accepted / attempts if attempts else 0, clipped_traces)
    for reason, count in sorted(rejections.items(), key=lambda kv: -kv[1]):
        log.info("  rejected %5d  %s", count, reason)

    if plot and accepted:
        plot_first_traces(out_path)
    return 0 if accepted else 1


def plot_first_traces(path: Path, n_show: int = 3) -> None:
    """I-V of the first traces. Guarded: a rig PC without matplotlib (or
    without a display) must still be able to acquire."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:                    # pragma: no cover
        log.warning("matplotlib unavailable, skipping plot: %s", exc)
        return

    import iv_analysis

    with storage.Session(path) as session:
        n_show = min(n_show, len(session))
        fig, (ax_iv, ax_didv) = plt.subplots(1, 2, figsize=(9, 4))
        for i in range(n_show):
            sweep = iv_analysis.extract(session, i)
            ax_iv.plot(sweep.v_junction, sweep.i_amps * 1e9,
                       lw=0.8, label=f"trace {i}")
            ax_didv.plot(sweep.didv_v, sweep.didv_s / iv_analysis.G0_SIEMENS,
                         lw=0.8)
        ax_iv.set_xlabel("junction voltage (V)")
        ax_iv.set_ylabel("current (nA)")
        ax_iv.legend(fontsize=8)
        ax_didv.set_xlabel("junction voltage (V)")
        ax_didv.set_ylabel("dI/dV (G0)")
        fig.suptitle(f"{path.name}: first {n_show} IV sweeps")
        fig.tight_layout()
        png = path.with_suffix(".iv.png")
        fig.savefig(png, dpi=150)
        plt.close(fig)
        log.info("wrote %s", png)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Triangular bias sweep at a held, partially pulled "
                    "junction (Igor: CreateInputs IV branch, "
                    "Functions_STMBJ.ipf:1497-1537).")
    p.add_argument("--config", type=Path,
                   help="rig config JSON; defaults are used if omitted")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--simulate", action="store_true",
                   help="run against the simulated card, no hardware")
    p.add_argument("-n", "--traces", type=int, default=20,
                   help="number of IV traces to collect (default 20)")
    p.add_argument("-o", "--out", type=Path, default=None,
                   help="output .h5 (default: data/iv_sweep_<timestamp>.h5)")
    p.add_argument("--no-calibrate", action="store_true",
                   help="skip the session zero and group-delay measurement")
    p.add_argument("--plot", action="store_true",
                   help="after the run, save an I-V/dI-dV plot of the first "
                        "traces next to the data file (needs matplotlib)")

    m = p.add_argument_group("sweep geometry (override cfg.iv)")
    m.add_argument("--max-bias", type=float, default=None,
                   help="sweep apex in volts (G_IVMaxBias); the bias limit "
                        "is raised to 1.1x this, loudly")
    m.add_argument("--ramp-nm", type=float, default=None,
                   help="sweep window length, nm at the pull rate "
                        "(G_IVRampLength; sets the sweep DURATION -- the "
                        "piezo does not move)")
    m.add_argument("--cap-nm", type=float, default=None,
                   help="DC cap either side of the sweep, nm at the pull "
                        "rate (G_IVCapLength)")
    m.add_argument("--positive-first", action="store_true",
                   help="sweep to the POSITIVE apex first (G_IVSignFlag). "
                        "The default sweeps negative first, because Igor "
                        "negates the whole bias wave at line 1533.")
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

    for flag, field in (("max_bias", "max_bias_v"), ("ramp_nm", "ramp_nm"),
                        ("cap_nm", "cap_nm")):
        value = getattr(args, flag)
        if value is not None:
            setattr(cfg.iv, field, value)
    if args.positive_first:
        cfg.iv.positive_first = True

    out = args.out or PKG_ROOT / "data" / \
        f"iv_sweep_{time.strftime('%Y%m%d_%H%M%S')}.h5"

    try:
        return run(cfg, out, args.traces,
                   do_calibrate=not args.no_calibrate, plot=args.plot)
    except (ConfigError, SafetyViolation) as exc:
        log.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
