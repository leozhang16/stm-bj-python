"""Find the coarse actuator and confirm it moves. Run with Igor CLOSED (a
serial port can be held by one program at a time).

    python rigtests/actuator_check.py                 # list ports, probe both
    python rigtests/actuator_check.py --port COM1     # one port, both protocols
    python rigtests/actuator_check.py --agilis-move -5 --port COM4
                                              # a WATCHED Agilis move: 5 steps APART

Two Newport controllers do this job and are told apart by how they talk:

    NanoPZ (PZC200)      19200 baud, read/write: answers 0TS?, 0TP?
    Agilis (AG-UC2/UC8)  921600 baud over NI-VISA, WRITE-ONLY: it accepts
                         mr / 1SU.. / 1PR.. / ml but answers nothing, so a
                         read probe cannot see it even when it is working.

So: the read probe below finds a NanoPZ. For an Agilis the only proof is a
move you watch -- --agilis-move sends ONE move through the real driver (a
NEGATIVE count is APART, away from the sample, the safe direction) and asks
you to watch the stage. This lab's Igor (Actuator_VISA_functions.ipf) drives
an Agilis on the "Newport AG-UC2-UC8" port, so that is almost certainly what
you have.

Paste the whole output into the chat.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SKIP = ("Intel(R) Active Management",)      # a virtual port on the motherboard


def _agilis_move(port: str, steps: int, amplitude: int) -> int:
    """One watched move through the real VISA driver. Negative = apart."""
    from stmlab.config import RigConfig
    from stmlab.actuator import AgilisActuator, ActuatorError
    cfg = RigConfig()
    cfg.actuator.step_amplitude = amplitude
    cfg.actuator.step_size = abs(steps)
    way = "APART (away from the sample)" if steps < 0 else "CLOSER (TOWARD the sample)"
    print(f"\nopening the Agilis on {port} and moving {abs(steps)} steps at "
          f"amplitude {amplitude}, {way} ...")
    if steps >= 0:
        print("  WARNING: a positive count moves TOWARD the sample. Make sure "
              "the tip is withdrawn first. Ctrl-C now to abort.")
    try:
        act = AgilisActuator(cfg, port=port)
    except ActuatorError as exc:
        print(f"  could not open: {exc}")
        return 1
    try:
        act.step(closer=(steps > 0))
    finally:
        act.close()
    print("  sent. WATCH THE STAGE: did the Z actuator move "
          + ("apart" if steps < 0 else "closer") + "?")
    print("  - if yes, it works; in the window choose Agilis and this port, "
          "Connect.")
    print("  - if it moved the WRONG way, set actuator.closer_sign to the "
          "opposite sign.")
    print("  - if nothing moved: wrong port, controller off, or Igor/another "
          "program holds the port.")
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
            elif kind == "agilis" and agilis_port:
                print("    nothing came back -- EXPECTED: the Agilis is "
                      "write-only. Confirm it with a watched move:")
                print(f"      python rigtests/actuator_check.py --agilis-move "
                      f"-5 --port {port}")
            else:
                print("    nothing came back")

    print()
    if found:
        for port, kind in found:
            print(f"ANSWERED: {port} as {kind}. In configs/labpc_rig.json under "
                  f"\"actuator\": \"kind\": \"{kind}\", \"port\": \"{port}\".")
    agilis = [q.device for q in ports if "AG-UC" in q.description.upper()]
    if agilis and not any(k == "agilis" for _, k in found):
        print(f"A Newport Agilis is on {', '.join(agilis)} but is write-only, so "
              "it will not answer the probe. Confirm it with:")
        print(f"      python rigtests/actuator_check.py --agilis-move -5 "
              f"--port {agilis[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
