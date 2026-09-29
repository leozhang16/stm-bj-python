#!/usr/bin/env python3
"""Lateral monolayer mapping: fresh break-junction statistics at many sites.

Igor equivalent: ``LateralEXPT(ZDistance, XDistance, XFreq)``,
Setup1_STMBJ.ipf:91-136. Each loop iteration:

    StartMeasurement("")            :114  -- a batch of constant-bias traces
    StepActuatorApart("") x3        :117-122, 100 ms pause after each step
    MoveXPiezo(XDistance)           :125  -- lateral move, tip WITHDRAWN
    G_ActuatorStepSize=5            :129
    SetPiezoBiasFromSlider("",0,0)  :130  -- reassert the bias
    ApproachButton("")              :131  -- coarse approach back into contact

until ``G_StopNumber`` reaches 12201 (:98,134) -- i.e. 12201/XFreq sites.
Here the site count is ``--sites`` directly, and the batch at each site is
``stmlab.trace.trace_loop`` (the same constant-bias loop as experiment 01,
Igor MeasureBreakJunctions, Functions_STMBJ.ipf:1664).

The order matters: the X piezo moves ONLY while the tip is withdrawn --
three coarse actuator steps apart, not just a fine-piezo retract -- because
a lateral move in contact drags the tip through the monolayer and reshapes
the apex. Each site's traces go to their own ``site_<i>.h5`` with the site
index and absolute X position in the file attributes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import logging
import signal
import threading
import time

from stmlab import approach, calibrate, storage, trace, xpiezo
from stmlab.approach import ApproachError
from stmlab.config import ConfigError, RigConfig, validate
from stmlab.instrument import Rig
from stmlab.safety import RigState, SafeSession, SafetyViolation
from stmlab.xpiezo import XPiezoError

log = logging.getLogger("lateral")

PKG_ROOT = Path(__file__).resolve().parents[2]

# Igor withdrew by exactly three coarse steps with 100 ms pauses
# (Setup1_STMBJ.ipf:117-122). Three steps is the point: far enough that a
# sample tilt across a 200 nm lateral move cannot crash the tip, close
# enough that the coarse re-approach takes seconds, not minutes.
WITHDRAW_STEPS = 3
WITHDRAW_PAUSE_S = 0.1


def engage_site(rig, cfg: RigConfig) -> RigState:
    """Bring the tip into contact at the current lateral position.

    ``recover_headroom`` (engage + coarse backoff on a too-low contact) is
    tried first. In simulate the fine piezo reaches the surface from the
    parked position, so this always succeeds and the fallback below is never
    taken. On hardware, three coarse steps apart put the surface out of the
    fine piezo's reach, and the coarse actuator must walk back in first --
    Igor's ApproachButton with G_ActuatorStepSize=5 (Setup1_STMBJ.ipf:129-131).
    """
    try:
        return approach.recover_headroom(rig)
    except ApproachError:
        if cfg.actuator.kind == "none":
            raise
        log.info("fine piezo cannot reach the surface here; coarse "
                 "approaching (Igor ApproachButton, Setup1_STMBJ.ipf:131)")
        rig.withdraw()
        rig.set_bias(cfg.ramp.bias_v)   # coarse_approach watches the current;
        # it needs the bias on to see contact (Igor line 130 reasserted the
        # bias from the slider before pressing Approach).
        approach.coarse_approach(rig)
        return approach.recover_headroom(rig)


def withdraw_site(rig) -> None:
    """Retract fine, then three coarse steps apart with short pauses.

    Igor: StepActuatorApart("") three times with Delay(100) after each
    (Setup1_STMBJ.ipf:117-122). ``rig.withdraw()`` first: the coarse-step
    interlock refuses to move the actuator unless the fine piezo is parked.
    """
    rig.withdraw()
    for _ in range(WITHDRAW_STEPS):
        rig.coarse_step(closer=False)
        time.sleep(WITHDRAW_PAUSE_S)


def run(cfg: RigConfig, out_dir: Path, n_sites: int, traces_per_site: int,
        step_nm: float, do_calibrate: bool = True) -> int:
    stop = threading.Event()

    def on_signal(signum, frame):
        del signum, frame
        if stop.is_set():
            log.warning("second interrupt; exiting now")
            sys.exit(130)
        log.warning("interrupt: finishing the current site, then stopping")
        stop.set()

    signal.signal(signal.SIGINT, on_signal)

    # Constant-bias traces at every site: the default pull_length_nm IS this
    # mode's net descent, so the headroom pre-check in engage() is already
    # correct -- no override needed (unlike the push-pull/IV/hold modes).
    log.info("lateral map: %d site(s), %d trace(s)/site, %.0f nm X step, "
             "%.2f nm pulls at %.0f mV",
             n_sites, traces_per_site, step_nm,
             cfg.ramp.pull_length_nm, 1000 * cfg.ramp.bias_v)

    for warning in validate(cfg):
        log.warning("config: %s", warning)

    total_accepted = 0
    sites_done = 0
    per_site: list[dict] = []

    with SafeSession(cfg):                      # verifies devices, parks output
        with Rig(cfg) as rig:                   # opens tasks
            with xpiezo.make_xpiezo(cfg) as xp:  # setup() drives X to 0 V
                if do_calibrate:
                    calibrate.session_calibration(rig)

                for site in range(n_sites):
                    if stop.is_set():
                        log.info("stopping: stop flag set")
                        break

                    rig.set_bias(cfg.ramp.bias_v)
                    try:
                        if engage_site(rig, cfg) is not RigState.ENGAGED:
                            log.error("site %d: could not engage; stopping",
                                      site)
                            break
                    except ApproachError as exc:
                        log.error("site %d: cannot engage: %s", site, exc)
                        break

                    path = out_dir / f"site_{site}.h5"
                    with storage.SessionWriter(path, cfg) as writer:
                        writer._h5.attrs["site_index"] = site
                        writer._h5.attrs["x_position_nm"] = xp.position_nm
                        writer._h5.attrs["x_piezo_v"] = xp.voltage
                        writer._h5.attrs["x_step_nm"] = step_nm

                        stats = trace.trace_loop(
                            rig, n=traces_per_site,
                            on_trace=writer.append, stop_flag=stop)

                        stats["site_index"] = site
                        stats["x_position_nm"] = xp.position_nm
                        writer.write_summary(stats)

                    total_accepted += stats["accepted"]
                    per_site.append(stats)
                    sites_done += 1
                    log.info("site %d/%d at x = %.0f nm: %d trace(s), "
                             "%d attempt(s) -> %s",
                             site + 1, n_sites, xp.position_nm,
                             stats["accepted"], stats["attempts"], path)

                    if site == n_sites - 1 or stop.is_set():
                        break

                    # Withdraw -> move -> (re-approach at the top of the
                    # next iteration). The X piezo moves only with the tip
                    # three coarse steps off the surface.
                    withdraw_site(rig)
                    xp.move_nm(step_nm)
                    time.sleep(WITHDRAW_PAUSE_S)   # Igor Delay(100), :126

                rig.withdraw()
                # xp context exit re-zeros the X piezo (Igor StopXPiezo).

    log.info("done: %d site(s), %d trace(s) total", sites_done, total_accepted)
    for s in per_site:
        log.info("  site %d at %6.0f nm: %4d accepted / %4d attempts",
                 s["site_index"], s["x_position_nm"],
                 s["accepted"], s["attempts"])
    return 0 if total_accepted else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Lateral monolayer mapping: constant-bias trace batches "
                    "at sites stepped across the sample "
                    "(Igor: LateralEXPT, Setup1_STMBJ.ipf:91-136).")
    p.add_argument("--config", type=Path,
                   help="rig config JSON; defaults are used if omitted")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--simulate", action="store_true",
                   help="run against the simulated card, no hardware")
    p.add_argument("--sites", type=int, default=5,
                   help="number of measurement sites (default 5; Igor ran "
                        "12201/XFreq iterations)")
    p.add_argument("-n", "--traces-per-site", type=int, default=50,
                   help="accepted traces per site (default 50)")
    p.add_argument("--step-nm", type=float, default=200.0,
                   help="lateral X step between sites, nm (default 200; "
                        "Igor's XDistance)")
    p.add_argument("-o", "--out-dir", type=Path, default=None,
                   help="output directory for site_<i>.h5 files "
                        "(default: data/lateral_<timestamp>/)")
    p.add_argument("--no-calibrate", action="store_true",
                   help="skip the session zero and group-delay measurement")
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
        if cfg.actuator.kind == "none":
            # The withdraw sequence is three coarse steps apart; without an
            # actuator the site loop cannot run at all, so simulate one.
            cfg.actuator.kind = "simulated"

    out_dir = args.out_dir or PKG_ROOT / "data" / \
        f"lateral_{time.strftime('%Y%m%d_%H%M%S')}"

    try:
        return run(cfg, out_dir, args.sites, args.traces_per_site,
                   args.step_nm, do_calibrate=not args.no_calibrate)
    except (ConfigError, SafetyViolation, XPiezoError) as exc:
        log.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
