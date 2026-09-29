"""Coarse approach actuator: Newport NanoPZ over a serial port.

The controller speaks RS-232. Connected by USB it appears as a virtual COM
port (either through the controller's own USB, or a USB-to-serial adapter),
so the protocol below is unchanged from Igor's -- only the port name differs.
Igor hardcoded ``Com1``; a USB port is more often COM3 or higher. Use
:func:`list_serial_ports` to find it.

Command set, from the Igor procedures. The STM-BJ file only ever used the
first three; the rest come from the AFM code, which drove the same controller
(``Source_Files/151010_AFM_operating_code.ipf:3316-3389``)::

    0MO             motor on                    NanoPZ_Actuator...:11
    0MF             motor off                   AFM:3336
    0PR<n>          relative move, n steps      NanoPZ_Actuator...:12
    0ST             stop motion                 AFM:3335
    0JA<speed>      start jog                   AFM:3323
    0TS?            tell status                 AFM:3378
    0TP?            tell position               AFM:3382

Serial settings: 19200 baud, 8 data bits, no parity, 1 stop bit, ``\\r\\n``
line endings (Igor's ``in=2, out=2``).

**Replies echo the command.** ``0TP?`` answers with ``0TP? 12345``, which is
what Igor's ``sscanf`` format strings are stripping. :meth:`NanoPZ.query`
handles that.

Sign convention, from ``StepActuatorCloser`` (NanoPZ_Actuator...:22): a
**negative** step count moves the tip **toward** the sample.

Nothing here checks the interlock. ``Rig.coarse_step`` does that, and is the
only thing that should ever call :meth:`step`.
"""

from __future__ import annotations

import logging
import time

from .config import RigConfig

log = logging.getLogger(__name__)


class ActuatorError(RuntimeError):
    pass


def list_serial_ports() -> list[tuple[str, str]]:
    """(device, description) for every serial port the OS can see.

    On Windows the NanoPZ shows up under Device Manager -> Ports (COM & LPT).
    If nothing appears here at all, the controller may be using a proprietary
    USB driver rather than a virtual COM port, in which case pyserial cannot
    reach it and Newport's own DLL is the only route.
    """
    try:
        from serial.tools import list_ports
    except ImportError as exc:
        raise ActuatorError(f"pyserial is not installed: {exc}") from exc
    return [(p.device, p.description) for p in list_ports.comports()]


class Actuator:
    """Interface. ``closer=True`` moves the tip toward the sample."""

    def step(self, closer: bool = True) -> None:
        raise NotImplementedError

    def position(self) -> int | None:
        """Position in steps, or None if the actuator cannot report it."""
        return None

    def stop(self) -> None:
        return

    def close(self) -> None:
        return


class NullActuator(Actuator):
    """No coarse actuator: the approach is done by hand."""

    def step(self, closer: bool = True) -> None:
        raise NotImplementedError(
            "no coarse actuator configured; set actuator.kind to 'nanopz' or "
            "approach by hand")


class SimulatedActuator(Actuator):
    def __init__(self, cfg: RigConfig, rig_sim=None):
        self.cfg = cfg
        self.sim = rig_sim
        self._position = 0

    def step(self, closer: bool = True) -> None:
        delta = -self.cfg.actuator.step_size if closer \
            else self.cfg.actuator.step_size
        self._position += delta
        if self.sim is not None:
            self.sim.surface_nm -= 8.0 if closer else -8.0

    def position(self) -> int:
        return self._position


class NanoPZActuator(Actuator):
    def __init__(self, cfg: RigConfig):
        import serial

        A = cfg.actuator
        self.cfg = cfg
        try:
            self.port = serial.Serial(
                port=A.port, baudrate=A.baud, bytesize=8, parity="N",
                stopbits=1, timeout=2.0)
        except Exception as exc:
            available = ", ".join(f"{d} ({desc})"
                                  for d, desc in list_serial_ports()) or "none"
            raise ActuatorError(
                f"could not open {A.port!r}: {exc}\n"
                f"Serial ports visible to this machine: {available}\n"
                f"Igor used Com1; a USB connection is usually a higher "
                f"number. Set actuator.port in the config.") from exc

        log.info("NanoPZ open on %s at %d baud", A.port, A.baud)
        self.motor_on()

    # -- protocol ---------------------------------------------------------

    def write(self, command: str) -> None:
        self.port.write((command + "\r\n").encode("ascii"))
        self.port.flush()

    def query(self, command: str) -> str:
        """Send a query and return the reply with the echoed command removed.

        The controller answers ``0TP?`` with ``0TP? 12345``. Igor stripped
        that prefix with sscanf format strings; this does the same, and
        tolerates the controller not echoing at all.
        """
        self.port.reset_input_buffer()
        self.write(command)
        raw = self.port.readline().decode("ascii", errors="replace").strip()
        if not raw:
            raise ActuatorError(
                f"no reply to {command!r}. Wrong port, wrong baud rate, or the "
                f"controller is off.")
        if raw.startswith(command):
            raw = raw[len(command):]
        return raw.strip()

    # -- motion -----------------------------------------------------------

    def motor_on(self) -> None:
        self.write("0MO")

    def motor_off(self) -> None:
        self.write("0MF")

    def step(self, closer: bool = True) -> None:
        A = self.cfg.actuator
        steps = -A.step_size if closer else A.step_size   # negative = closer
        self.motor_on()
        self.write(f"0PR{steps}")
        time.sleep(A.settle_s)

    def stop(self) -> None:
        self.write("0ST")

    # -- feedback ---------------------------------------------------------

    def position(self) -> int | None:
        """Position in steps, via ``0TP?``.

        Igor's parser used ``%[0-9]``, which cannot match a leading minus and
        so silently mangled negative positions. This accepts a sign.
        """
        try:
            reply = self.query("0TP?")
        except ActuatorError:
            log.warning("actuator did not report its position", exc_info=True)
            return None
        digits = "".join(c for c in reply if c.isdigit() or c == "-")
        try:
            return int(digits)
        except ValueError:
            log.warning("could not parse position from %r", reply)
            return None

    def status(self) -> str:
        """Controller status character, via ``0TS?``.

        Igor matched against the set ``[QP@]`` (AFM:3380) but never documented
        what they mean, so this returns the raw character rather than
        inventing an interpretation.
        """
        return self.query("0TS?")

    def close(self) -> None:
        try:
            self.stop()
            self.motor_off()
        except Exception:
            pass
        try:
            self.port.close()
        except Exception:
            pass


def make_actuator(cfg: RigConfig, rig_sim=None) -> Actuator:
    kind = cfg.actuator.kind.lower()
    if kind == "nanopz":
        return NanoPZActuator(cfg)
    if kind == "simulated" or (cfg.simulate and kind != "none"):
        return SimulatedActuator(cfg, rig_sim)
    return NullActuator()
