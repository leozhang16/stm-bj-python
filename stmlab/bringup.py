"""First contact with the card, in four steps.

Run these in order on the rig PC. **Every step here runs with the piezo
disconnected and no tip near the sample**, so nothing can be damaged while
``daq.py`` executes for the first time.

    python -m stmbj.bringup 1     # devices          no connections
    python -m stmbj.bringup 2     # timing           BNC: ao1 -> ai0
    python -m stmbj.bringup 3     # output hold      BNC: ao0 -> ai0
    python -m stmbj.bringup 4     # preamp gain      resistor at the preamp

Each prints the numbers it measured and a verdict. A CHECK verdict means the
measurement worked but you have to decide whether the number is acceptable;
FAIL means something is wrong that will bite later.

Only after all four pass should the piezo be connected. Step 5 is not
automated, deliberately: connect the piezo, watch ao0 on a scope through one
``engage()``, and confirm it ramps 0 -> 10 V and never goes negative.
"""

from __future__ import annotations

import argparse
import logging
import sys

import numpy as np

from . import calibrate
from .config import RigConfig
from .instrument import Rig

log = logging.getLogger("stmbj.bringup")

PASS, FAIL, CHECK = "PASS", "FAIL", "CHECK"


class Result:
    def __init__(self):
        self.rows: list[tuple[str, str, str]] = []

    def add(self, verdict: str, label: str, detail: str = "") -> None:
        self.rows.append((verdict, label, detail))

    def report(self) -> int:
        print()
        width = max((len(r[1]) for r in self.rows), default=0)
        for verdict, label, detail in self.rows:
            print(f"  [{verdict:5}] {label:<{width}}  {detail}")
        failed = sum(1 for r in self.rows if r[0] == FAIL)
        checks = sum(1 for r in self.rows if r[0] == CHECK)
        print()
        if failed:
            print(f"{failed} check(s) FAILED -- do not continue to the next "
                  f"step until these are resolved.")
            return 1
        if checks:
            print(f"No failures, but {checks} result(s) need your judgement.")
        else:
            print("All checks passed.")
        return 0


# --------------------------------------------------------------------------
# Step 1: devices. No connections needed.
# --------------------------------------------------------------------------

def step_devices(cfg: RigConfig) -> int:
    """Is the card there, is it the card we think, do the channels exist?"""
    import nidaqmx
    import nidaqmx.system
    from nidaqmx.constants import AcquisitionType

    r = Result()
    system = nidaqmx.system.System.local()

    v = system.driver_version
    print(f"NI-DAQmx {v.major_version}.{v.minor_version}.{v.update_version}")
    print("Devices present:")
    for d in system.devices:
        print(f"  {d.name:<10} {d.product_type}")

    names = [d.name for d in system.devices]
    if cfg.channels.device not in names:
        r.add(FAIL, "device present",
              f"{cfg.channels.device!r} not found among {names}. "
              f"Check NI MAX; aliases move when cards change slots.")
        return r.report()
    r.add(PASS, "device present", cfg.channels.device)

    device = system.devices[cfg.channels.device]
    expected = cfg.channels.expected_product_type or ""
    got = device.product_type
    if expected and expected.lower().replace("-", "") not in \
            got.lower().replace("-", ""):
        r.add(FAIL, "product type",
              f"{got!r}, expected {expected!r}. The channel map assumes the "
              f"4461 pinout.")
    else:
        r.add(PASS, "product type", got)

    ai_names = {c.name for c in device.ai_physical_chans}
    ao_names = {c.name for c in device.ao_physical_chans}
    for label, path, available in (
            ("ai0 junction voltage", cfg.channels.path(cfg.channels.ai_voltage), ai_names),
            ("ai1 preamp output", cfg.channels.path(cfg.channels.ai_current), ai_names),
            ("ao0 piezo command", cfg.channels.path(cfg.channels.ao_piezo), ao_names),
            ("ao1 junction bias", cfg.channels.path(cfg.channels.ao_bias), ao_names)):
        r.add(PASS if path in available else FAIL, label, path)

    # Rate coercion: a delta-sigma card grants discrete rates.
    requested = cfg.ramp.sample_rate_hz
    try:
        with nidaqmx.Task() as task:
            task.ai_channels.add_ai_voltage_chan(
                cfg.channels.path(cfg.channels.ai_voltage),
                min_val=-cfg.channels.ai_range_v,
                max_val=cfg.channels.ai_range_v)
            task.timing.cfg_samp_clk_timing(
                requested, sample_mode=AcquisitionType.FINITE,
                samps_per_chan=1000)
            granted = float(task.timing.samp_clk_rate)
    except Exception as exc:
        r.add(FAIL, "sample rate", f"could not configure timing: {exc}")
        return r.report()

    error_ppm = abs(granted - requested) / requested * 1e6
    if error_ppm < 1:
        r.add(PASS, "sample rate", f"{granted:.4f} Hz as requested")
    else:
        r.add(CHECK, "sample rate",
              f"requested {requested:.1f} Hz, granted {granted:.4f} Hz "
              f"({error_ppm:.0f} ppm). Harmless -- the granted rate is used "
              f"for every time axis -- but put {granted:.4f} in the config "
              f"so it stops being a surprise.")
    return r.report()


# --------------------------------------------------------------------------
# Step 2: timing. Needs one BNC from ao1 to ai0.
# --------------------------------------------------------------------------

def step_timing(cfg: RigConfig) -> int:
    """Is AI genuinely triggered off AO, with a stable delay?

    Connect ao1 (bias out) to ai0 (voltage in) with one BNC. Coax carries both
    the signal and its return, so a single cable makes both connections.
    """
    r = Result()
    print("Wiring for this step: ao1 -> ai0, one BNC cable.\n")

    with Rig(cfg) as rig:
        session = rig._session
        r.add(PASS if session.idle_behavior == "maintain" else CHECK,
              "AO idle behaviour",
              "MAINTAIN_EXISTING_VALUE" if session.idle_behavior == "maintain"
              else "card refused MAINTAIN; outputs fall to 0 V between plays. "
                   "Step 3 measures whether this matters.")

        retrig = getattr(session, "_retriggerable", None)
        r.add(PASS if retrig else CHECK, "retriggerable AI",
              "armed once, never re-settles" if retrig
              else "not supported; AI re-arms per play and the input filter "
                   "settles at the start of every record")

        try:
            mean, sd = calibrate.measure_group_delay(rig, repeats=25)
        except Exception as exc:
            r.add(FAIL, "group delay",
                  f"no edges found: {exc}. Is ao1 really connected to ai0?")
            return r.report()

        r.add(PASS, "group delay", f"{mean:.2f} samples "
              f"({mean / rig.sample_rate_hz * 1e6:.1f} us)")

        if sd < 1.0:
            r.add(PASS, "delay scatter",
                  f"{sd:.3f} samples -- AI is locked to ao/StartTrigger")
        else:
            r.add(FAIL, "delay scatter",
                  f"{sd:.2f} samples, above one sample. AI is not actually "
                  f"triggered off ao/StartTrigger, so displacement and current "
                  f"are not reliably aligned. Fix this before acquiring.")
    return r.report()


# --------------------------------------------------------------------------
# Step 3: does the piezo command line hold between plays?
# --------------------------------------------------------------------------

def step_hold(cfg: RigConfig) -> int:
    """Does ao0 keep its value between plays?

    Connect ao0 (piezo command) to ai0 (voltage in) with one BNC. The piezo
    stays disconnected.

    This is the decisive test for the approach. Each 0.5 nm step is a separate
    play, and the piezo has to stay where it was put in the gap between them.
    If the card drops the output to 0 V, the approach walks in place forever
    and every step kicks the piezo from 0 V back up to where it was.
    """
    r = Result()
    print("Wiring for this step: ao0 -> ai0, one BNC. Piezo NOT connected.\n")

    probe_v = 4.0
    with Rig(cfg) as rig:
        rig.piezo_goto(probe_v)

        record = rig.hold(piezo_v=probe_v)
        row = record[cfg.channels.ROW_VOLTAGE]

        settled = float(np.mean(row[-200:]))
        opening = float(np.mean(row[:20]))

        if abs(settled - probe_v) < 0.05:
            r.add(PASS, "loopback reads ao0", f"{settled:.4f} V for a "
                  f"{probe_v:.1f} V command")
        else:
            r.add(FAIL, "loopback reads ao0",
                  f"commanded {probe_v:.1f} V, measured {settled:.4f} V. "
                  f"Wrong cable, wrong channel, or AC coupling on ai0.")
            return r.report()

        # If the output had fallen to 0 V between plays, the record would open
        # near 0 and climb; holding means it opens already at the value.
        if abs(opening - probe_v) < 0.10:
            r.add(PASS, "output holds between plays",
                  f"record opens at {opening:.4f} V")
        else:
            r.add(FAIL, "output holds between plays",
                  f"record opens at {opening:.4f} V, not {probe_v:.1f} V -- "
                  f"the output dropped in the gap between plays. The "
                  f"step-wise approach will not work as written; the AO task "
                  f"needs to run continuously instead.")

        # And confirm nothing ever asks the piezo line to go negative.
        if row.min() > -0.1:
            r.add(PASS, "never negative", f"minimum {row.min():+.4f} V")
        else:
            r.add(FAIL, "never negative",
                  f"saw {row.min():+.4f} V on the piezo line, which is "
                  f"unipolar 0-10 V")
    return r.report()


# --------------------------------------------------------------------------
# Step 4: preamp gain, zero, and noise floor.
# --------------------------------------------------------------------------

def step_preamp(cfg: RigConfig, resistance_ohm: float = 1e6) -> int:
    """Is the preamp gain what the config claims?

    Put a known resistor where the junction goes, at the preamp input. Piezo
    still disconnected, no tip involved.

    100 mV across 1 MOhm is 100 nA, which at 1e6 V/A must read exactly 0.1 V.
    If it does not, every conductance this rig ever reports is scaled by the
    same factor -- and that is the error that produces a plausible histogram
    in the wrong place.
    """
    r = Result()
    print(f"Wiring for this step: a {resistance_ohm:.3g} ohm resistor at the "
          f"preamp input. Piezo NOT connected.\n")

    expected_v = calibrate.expected_resistor_v(cfg, resistance_ohm)
    print(f"At {cfg.ramp.bias_v * 1e3:.0f} mV through {resistance_ohm:.3g} "
          f"ohm, expect {expected_v:.4f} V on ai1.\n")

    with Rig(cfg) as rig:
        zero = calibrate.measure_zero(rig)
        cfg.cal.current_zero_v = zero

        record = rig.hold(bias_v=cfg.ramp.bias_v,
                          n_samples=cfg.ramp.settle_samples * 20)
        current_v = float(np.mean(record[cfg.channels.ROW_CURRENT, -4000:]))
        noise_v = float(np.std(record[cfg.channels.ROW_CURRENT, -4000:]))

        measured = current_v - zero
        implied_gain = abs(measured) / (cfg.ramp.bias_v / resistance_ohm)
        ratio = abs(measured) / expected_v if expected_v else float("nan")

        r.add(PASS, "preamp zero",
              f"{zero * 1e6:+.2f} uV (put this in the config)")

        if 0.98 < ratio < 1.02:
            r.add(PASS, "preamp gain",
                  f"read {measured:.4f} V, expected {expected_v:.4f} V "
                  f"({ratio:.4f}x). Implied Rf = {implied_gain:.4g} V/A")
        else:
            r.add(FAIL, "preamp gain",
                  f"read {measured:.4f} V but expected {expected_v:.4f} V "
                  f"({ratio:.3f}x). Implied Rf = {implied_gain:.4g} V/A, "
                  f"config says {cfg.cal.preamp_gain_v_per_a:.4g}. Every "
                  f"conductance would be off by {ratio:.3f}x "
                  f"({np.log10(ratio):+.3f} decades in the histogram).")

        floor_g0 = abs(cfg.cal.volts_to_amps(5 * noise_v)) / \
            (cfg.ramp.bias_v * 7.7480917346e-5)
        r.add(CHECK, "noise floor",
              f"{noise_v * 1e6:.2f} uV rms -> usable floor about "
              f"{floor_g0:.2e} G0 at 5 sigma. Six decades below 1 G0 is "
              f"1e-6; you have "
              f"{-np.log10(floor_g0):.1f} decades.")
    return r.report()


# --------------------------------------------------------------------------

def step_actuator(cfg: RigConfig, move: bool = False) -> int:
    """Can we talk to the coarse actuator, and does it move when told?

    Communication only by default. A coarse step advances the tip further than
    the whole piezo range, so ``--move`` is opt-in and steps *away* from the
    sample first, never toward it.
    """
    from .actuator import ActuatorError, NanoPZActuator, list_serial_ports

    r = Result()

    print("Serial ports visible to this machine:")
    try:
        ports = list_serial_ports()
    except ActuatorError as exc:
        r.add(FAIL, "pyserial", str(exc))
        return r.report()

    for device, description in ports:
        print(f"  {device:<10} {description}")
    if not ports:
        print("  (none)")
        r.add(FAIL, "serial ports",
              "no serial ports at all. If the NanoPZ is plugged in, it may be "
              "using a proprietary USB driver rather than a virtual COM port, "
              "in which case pyserial cannot reach it. Check Device Manager "
              "-> Ports (COM & LPT).")
        return r.report()
    r.add(PASS, "serial ports", f"{len(ports)} found")

    if cfg.actuator.kind != "nanopz":
        r.add(FAIL, "config",
              f"actuator.kind is {cfg.actuator.kind!r}. Set it to 'nanopz' "
              f"and actuator.port to the right COM port, then re-run.")
        return r.report()

    print(f"\nOpening {cfg.actuator.port} at {cfg.actuator.baud} baud...\n")
    try:
        actuator = NanoPZActuator(cfg)
    except ActuatorError as exc:
        r.add(FAIL, "open port", str(exc))
        return r.report()

    try:
        try:
            status = actuator.status()
            r.add(PASS, "controller replies", f"0TS? -> {status!r}")
        except ActuatorError as exc:
            r.add(FAIL, "controller replies", str(exc))
            return r.report()

        before = actuator.position()
        if before is None:
            r.add(CHECK, "reports position",
                  "0TP? did not parse; motion cannot be verified, and the "
                  "coarse approach will be blind as it was under Igor")
        else:
            r.add(PASS, "reports position", f"{before} steps")

        if not move:
            r.add(CHECK, "motion",
                  "not tested. Re-run with --move once you are certain the "
                  "tip is clear of the sample; it steps AWAY first, then back.")
        elif before is None:
            r.add(CHECK, "motion", "cannot verify without a position readout")
        else:
            actuator.step(closer=False)             # away from the sample
            away = actuator.position()
            actuator.step(closer=True)              # and back
            back = actuator.position()

            if away is None or away == before:
                r.add(FAIL, "motion",
                      f"commanded a step away but the position stayed at "
                      f"{before}. Motor off, controller in a fault state, or "
                      f"the axis number in the command is wrong.")
            else:
                r.add(PASS, "motion",
                      f"{before} -> {away} -> {back} "
                      f"({away - before:+d} steps, then back)")
                if back != before:
                    r.add(CHECK, "returned to start",
                          f"ended at {back}, started at {before}: the "
                          f"actuator does not retrace exactly. Normal for a "
                          f"slip-stick drive; just do not treat step count as "
                          f"a distance.")
    finally:
        actuator.close()

    return r.report()


STEPS = {
    1: ("devices", "no connections", step_devices),
    2: ("timing", "BNC: ao1 -> ai0", step_timing),
    3: ("output hold", "BNC: ao0 -> ai0", step_hold),
    4: ("preamp gain", "resistor at the preamp input", step_preamp),
    5: ("coarse actuator", "NanoPZ on USB", step_actuator),
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m stmbj.bringup",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", type=int, choices=sorted(STEPS),
                   help="which bring-up step to run")
    p.add_argument("--config", help="rig config JSON")
    p.add_argument("--resistor", type=float, default=1e6,
                   help="resistance used in step 4, in ohms")
    p.add_argument("--move", action="store_true",
                   help="step 5 only: actually move the actuator. Only with "
                        "the tip clear of the sample.")
    p.add_argument("--port",
                   help="serial port for step 5, e.g. COM3 (overrides config)")
    p.add_argument("--simulate", action="store_true",
                   help="exercise the harness against the simulator; the "
                        "numbers are meaningless, only the plumbing is tested")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)-7s %(name)s: %(message)s")

    cfg = RigConfig.from_json(args.config) if args.config else RigConfig()
    if args.simulate:
        cfg.simulate = True
    if args.port:
        cfg.actuator.port = args.port
        cfg.actuator.kind = "nanopz"

    name, wiring, func = STEPS[args.step]
    print(f"=== Step {args.step}: {name} ({wiring}) ===\n")

    try:
        if args.step == 4:
            return func(cfg, args.resistor)
        if args.step == 5:
            return func(cfg, args.move)
        return func(cfg)
    except ImportError as exc:
        print(f"\nCannot run: {exc}\nThis step needs NI-DAQmx and must run on "
              f"the rig PC.")
        return 1
    except Exception as exc:
        print(f"\nStep {args.step} raised: {type(exc).__name__}: {exc}")
        if args.verbose:
            raise
        print("Re-run with -v for the traceback.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
