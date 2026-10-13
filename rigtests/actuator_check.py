"""Which serial port is the coarse actuator on, and which Newport controller
is it? Run this with Igor CLOSED (a serial port can be held by one program
at a time).

    python rigtests/actuator_check.py                 # every port, both protocols
    python rigtests/actuator_check.py --port COM4     # one port, both protocols
    python rigtests/actuator_check.py --port COM4 --kind agilis --move 10
                                                      # one move of +10 steps: watch it

Two Newport controllers do this job and speak different languages:

    NanoPZ (PZC200)      19200 baud; 0TS? status, 0TP? position (Igor's)
    Agilis (AG-UC2/UC8)  921600 baud; VE version, 1TS status, 1TP steps

With no --kind, each port is asked in both languages, read-only, and the
raw bytes that come back are printed: the controller that answers is the
one you have. Nothing moves unless --move is given; then one relative move
of that many steps is sent (sign as typed) and the step count read again,
so you can watch which way the sample goes and set actuator.closer_sign.

Paste the whole output into the chat.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SKIP = ("Intel(R) Active Management",)      # a virtual port on the motherboard


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--port", help="COM port (default: every port Windows lists)")
    p.add_argument("--kind", choices=("nanopz", "agilis"),
                   help="ask in one language only (default: both)")
    p.add_argument("--move", type=int, default=0, metavar="N",
                   help="after the queries, one relative move of N steps "
                        "(needs --kind and --port); watch which way it goes")
    args = p.parse_args(argv)
    if args.move and not (args.kind and args.port):
        p.error("--move needs --port and --kind")

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

    from stmlab.actuator import PROBES, probe_port
    kinds = (args.kind,) if args.kind else tuple(PROBES)
    if args.port:
        targets = [args.port]
    else:
        targets = [q.device for q in ports
                   if not any(skip in q.description for skip in SKIP)]
    found = []
    for port in targets:
        for kind in kinds:
            baud = PROBES[kind]["baud"]
            print(f"\n{port} as {kind} at {baud} baud ...")
            try:
                replies = probe_port(port, kind, move=args.move)
            except Exception as exc:                      # noqa: BLE001
                print(f"    could not open: {type(exc).__name__}: {exc}")
                break                                     # no point trying the other language
            answered = False
            for cmd, raw in replies:
                print(f"    sent {cmd!r:8s} -> got {raw!r}")
                answered = answered or bool(raw.strip())
            if answered:
                found.append((port, kind))
            else:
                print("    nothing came back")

    print()
    if not found:
        print("no controller answered. Wrong port, Igor still holding it, the "
              "controller off, or a cable problem.")
        return 1
    for port, kind in found:
        print(f"ANSWERED: {port} as {kind}. In configs/labpc_rig.json under "
              f"\"actuator\": \"kind\": \"{kind}\", \"port\": \"{port}\" -- or "
              f"choose them in the Coarse approach box and press Connect.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
