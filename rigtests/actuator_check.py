"""Find the coarse actuator and confirm it moves. Run with Igor CLOSED (a
serial port can be held by one program at a time).

    python rigtests/actuator_check.py                 # list ports, probe both
    python rigtests/actuator_check.py --port COM4     # one port, both protocols
    python rigtests/actuator_check.py --agilis-move -20 --port COM4
                                              # one Agilis move, 20 steps APART, with
                                              # the step counter read before and after
    python rigtests/actuator_check.py --listen --port COM4
                                              # three apart moves at amplitude 23, 35, 50

Two Newport controllers do this job and are told apart by how they talk:

    NanoPZ (PZC200)      19200 baud over pyserial: answers 0TS?, 0TP?
    Agilis (AG-UC2/UC8)  921600 baud over NI-VISA: answers VE, TE, 1TS, 1TP

This lab's actuator is an Agilis AG-UC2 on the "Newport AG-UC2-UC8" port
(COM4 = ASRL4::INSTR), the one Igor's Actuator_VISA_functions.ipf drives.
If it answers nothing at all, it is switched off or asleep: its USB port
shows up in Windows either way, and a Step from Igor's panel has woken it.
A NEGATIVE count is APART, away from the sample, the safe direction.

Paste the whole output into the chat.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SKIP = ("Intel(R) Active Management",)      # a virtual port on the motherboard


def _agilis_open(port: str, amplitude: int, steps: int):
    """The real driver on the port, with the link proved first."""
    from stmlab.config import RigConfig
    from stmlab.actuator import AgilisActuator, ActuatorError
    cfg = RigConfig()
    cfg.actuator.step_amplitude = amplitude
    cfg.actuator.step_size = abs(steps)
    try:
        act = AgilisActuator(cfg, port=port)
        ident = act.identify()
    except ActuatorError as exc:
        print(f"  could not talk to the Agilis: {exc}")
        return None
    print(f"  {ident['version']} at {ident['resource']}: status {ident['status']!r} "
          f"(0 = ready), step counter {ident['position']}")
    return act


def _agilis_move(port: str, steps: int, amplitude: int) -> int:
    """One move through the real VISA driver, the step counter read before
    and after. Negative = apart."""
    way = "APART (away from the sample)" if steps < 0 else "CLOSER (TOWARD the sample)"
    print(f"\nAgilis on {port}: {abs(steps)} steps at amplitude {amplitude}, {way} ...")
    if steps >= 0:
        print("  WARNING: a positive count moves TOWARD the sample. Make sure "
              "the tip is withdrawn first. Ctrl-C now to abort.")
    act = _agilis_open(port, amplitude, steps)
    if act is None:
        return 1
    try:
        before = act.position()
        act.step(closer=(steps > 0))
        after = act.position()
    except Exception as exc:                          # noqa: BLE001
        print(f"  FAILED: {exc}")
        act.close()
        return 1
    act.close()
    delta = None if before is None or after is None else after - before
    print(f"  step counter {before} -> {after}"
          + (f" (changed by {delta:+d}; asked for {steps:+d})" if delta is not None else ""))
    if delta == steps:
        print("  the controller did exactly what was asked. In the window: "
              "Agilis, this port, Connect.")
    elif delta is not None and delta == -steps:
        print("  it moved the OTHER way: set actuator.closer_sign to the "
              "opposite sign.")
    else:
        print("  the counter did not change as expected: tell me these numbers.")
    return 0


def _agilis_listen(port: str, steps: int = 3) -> int:
    """Three moves apart, at rising step amplitudes, with a pause between
    them: a piezo motor below its threshold amplitude does not step at all
    (no click), so this finds the amplitude this stage needs."""
    import time
    print(f"\nthree moves APART on {port}, {abs(steps)} steps each, amplitude "
          "23 then 35 then 50, 3 s between them. LISTEN for the clicks.")
    for amp in (23, 35, 50):
        print(f"  ... amplitude {amp} NOW")
        act = _agilis_open(port, amp, -abs(steps))
        if act is None:
            return 1
        try:
            before = act.position()
            act.step(closer=False)
            print(f"      counter {before} -> {act.position()}")
        finally:
            act.close()
        time.sleep(3.0)
    print("  done. Which amplitude(s) clicked? That is the smallest amplitude "
          "that moves this stage: put it in actuator.step_amplitude (and in "
          "the Amplitude box). None at all: tell me, and check that Igor's "
          "own Step button clicks right now with the controller on.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--port", help="COM port (default: every port Windows lists)")
    p.add_argument("--kind", choices=("nanopz", "agilis"),
                   help="probe in one language only (default: both)")
    p.add_argument("--agilis-move", type=int, default=None, metavar="N",
                   help="a WATCHED Agilis move of N steps through the real "
                        "driver (negative = apart/safe); needs --port")
    p.add_argument("--amplitude", type=int, default=23,
                   help="Agilis step amplitude for --agilis-move (1-50, "
                        "default 23, Igor's value)")
    p.add_argument("--listen", action="store_true",
                   help="three Agilis moves APART at amplitude 23, 35, 50 with "
                        "3 s between: listen for which one clicks (needs --port)")
    p.add_argument("--deep", action="store_true",
                   help="a silent NanoPZ port: also try CR and LF endings, the "
                        "wake-up command first, XON/XOFF, a longer wait, and "
                        "read the handshake pins")
    args = p.parse_args(argv)

    print(f"python {sys.version.split()[0]} on {sys.platform}")
    try:
        import serial
        from serial.tools import list_ports
    except ImportError as exc:
        print(f"pyserial is NOT installed ({exc}).  Install it in the venv:  "
              f"pip install pyserial")
        return 2
    print(f"pyserial {serial.__version__}")

    ports = list(list_ports.comports())
    print("serial ports this PC can see:")
    for q in ports:
        print(f"    {q.device:8s} {q.description}")
    if not ports:
        print("    NONE. Check Device Manager -> Ports (COM & LPT).")

    if args.listen:
        if not args.port:
            p.error("--listen needs --port (e.g. --port COM4)")
        return _agilis_listen(args.port)
    if args.agilis_move is not None:
        if not args.port:
            p.error("--agilis-move needs --port (e.g. --port COM4)")
        return _agilis_move(args.port, args.agilis_move, args.amplitude)

    from stmlab.actuator import PROBES, TERMINATORS, modem_lines, probe_port
    kinds = (args.kind,) if args.kind else tuple(PROBES)
    targets = ([args.port] if args.port else
               [q.device for q in ports
                if not any(skip in q.description for skip in SKIP)])
    found = []
    for port in targets:
        agilis_port = any(port == q.device and "AG-UC" in q.description.upper()
                          for q in ports)
        if args.deep:
            try:
                pins = modem_lines(port)
                print(f"\n{port} handshake pins: "
                      + ", ".join(f"{k.upper()} {'high' if v else 'low'}"
                                  for k, v in pins.items()))
            except Exception as exc:                      # noqa: BLE001
                print(f"\n{port}: could not open: {type(exc).__name__}: {exc}")
                continue
        for kind in kinds:
            baud = PROBES[kind]["baud"]
            if kind == "agilis":
                # Through NI-VISA, as Igor and the driver: pyserial is not
                # the road this box is proven on.
                print(f"\n{port} as agilis at {baud} baud over NI-VISA ...")
                act = _agilis_open(port, 23, 1)
                if act is not None:
                    act.close()
                    found.append((port, kind))
                elif agilis_port:
                    print("    (this IS the Newport port: the box is switched off "
                          "or asleep -- press a Step on Igor's panel once, close "
                          "Igor, and run this again)")
                continue
            print(f"\n{port} as {kind} at {baud} baud ...")
            try:
                replies = probe_port(port, kind)
            except Exception as exc:                      # noqa: BLE001
                print(f"    could not open: {type(exc).__name__}: {exc}")
                break
            answered = False
            for cmd, raw in replies:
                print(f"    sent {cmd!r:8s} -> got {raw!r}")
                answered = answered or bool(raw.strip())
            if answered:
                found.append((port, kind))
            else:
                print("    nothing came back")

    print()
    if found:
        for port, kind in found:
            print(f"ANSWERED: {port} as {kind}. In configs/labpc_rig.json under "
                  f"\"actuator\": \"kind\": \"{kind}\", \"port\": \"{port}\".")
    agilis = [q.device for q in ports if "AG-UC" in q.description.upper()]
    if agilis and not any(k == "agilis" for _, k in found):
        print(f"A Newport Agilis is on {', '.join(agilis)} but did not answer: "
              "it is switched off or asleep (its USB port shows up either way). "
              "A Step from Igor's panel wakes it; then close Igor and rerun.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
