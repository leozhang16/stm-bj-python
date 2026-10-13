"""Coarse approach actuator: a Newport NanoPZ (PZC200) or a Newport Agilis
(AG-UC2 / AG-UC8) over a serial port.

Two controllers, two languages. The NanoPZ is what Igor's procedures drove
and what the notes below describe. The Agilis is the other Newport
piezo-motor controller a lab may have on the same job: it appears in
Windows as "Newport AG-UC2-UC8 USB Serial Port", talks at a fixed 921600
baud, and its commands are ``MR`` (remote mode, required first), ``ML``
(local mode), ``<axis>PR<n>`` (relative move, n steps), ``<axis>TP`` (tell
the step count), ``<axis>TS`` (status: 0 ready, 1 stepping, 2 jogging, 3
moving to a limit), ``<axis>ST`` (stop), ``CC<n>`` (channel 1-4, AG-UC8
only), ``TE`` (error of the previous command, 0 = none) and ``VE``
(firmware version). Axis is 1 or 2; commands end in CR LF; replies carry
the command back in front of the value (``1TP-12``). Which sign of ``PR``
moves the tip toward the sample depends on the mounting:
``actuator.closer_sign``.

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

The port is opened when the controller is *connected*, not when the program
starts: ``UnconnectedActuator`` stands in for a configured NanoPZ until
``NanoPZActuator(cfg, port=...)`` succeeds, so a wrong COM port costs a
message in the window, not the session. ``rigtests/nanopz_check.py`` is the
stand-alone check of the serial link.
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


class UnconnectedActuator(Actuator):
    """A NanoPZ that is configured but whose port has not been opened yet.
    Every move refuses with the instruction; ``Rig.attach_actuator`` swaps
    the real one in once Connect has succeeded."""

    connected = False

    def step(self, closer: bool = True) -> None:
        raise ActuatorError(
            "the NanoPZ is not connected: choose its COM port and press "
            "Connect in the Coarse approach box (or use the screw by hand)")


class SimulatedActuator(Actuator):
    def __init__(self, cfg: RigConfig, rig_sim=None):
        self.cfg = cfg
        self.sim = rig_sim
        self._position = 0

    # One controller step of the PZA12 actuator is tens of nanometres, so a
    # configured step (5 of them, Igor's G_ActuatorStepSize) moves the
    # sample by about a quarter of the fine piezo's range. The simulated
    # surface moves by this much per step, and a coarse approach lands in
    # contact within a step, as the real one does. (Not a divisor of the
    # surface's 300 nm start, so the landing has a random-looking phase
    # and the step back leaves a real gap, as on the rig.)
    NM_PER_STEP = 140.0
    connected = True

    def step(self, closer: bool = True) -> None:
        delta = -self.cfg.actuator.step_size if closer \
            else self.cfg.actuator.step_size
        self._position += delta
        if self.sim is not None:
            self.sim.move_surface(-self.NM_PER_STEP if closer else self.NM_PER_STEP)

    def position(self) -> int:
        return self._position


def _open_serial(port_name: str, baud: int, serial_factory=None,
                 timeout: float = 2.0):
    """Open a serial port 8N1, with the message a person needs when it fails."""
    if serial_factory is None:
        try:
            import serial
        except ImportError as exc:
            raise ActuatorError(
                f"pyserial is not installed ({exc}); on the lab PC: "
                f"pip install pyserial") from exc
        serial_factory = serial.Serial
    try:
        return serial_factory(port=port_name, baudrate=baud, bytesize=8,
                              parity="N", stopbits=1, timeout=timeout)
    except Exception as exc:
        try:
            available = ", ".join(f"{d} ({desc})"
                                  for d, desc in list_serial_ports()) or "none"
        except ActuatorError:
            available = "unknown (pyserial missing)"
        raise ActuatorError(
            f"could not open {port_name!r}: {exc}. Serial ports visible to "
            f"this machine: {available}. Is Igor still holding the port?") from exc


class NanoPZActuator(Actuator):
    """The PZC200. ``port`` overrides ``cfg.actuator.port`` for the session;
    ``serial_factory`` stands in for ``serial.Serial`` in tests."""

    connected = True
    kind = "nanopz"

    def __init__(self, cfg: RigConfig, port: str | None = None,
                 serial_factory=None):
        A = cfg.actuator
        self.cfg = cfg
        self.port_name = port or A.port
        self.port = _open_serial(self.port_name, A.baud, serial_factory)
        log.info("NanoPZ open on %s at %d baud", self.port_name, A.baud)
        self.motor_on()

    def identify(self) -> dict:
        """Prove the link: the controller's status character and position.
        Raises ActuatorError when nothing answers (wrong port or baud, the
        controller off, or Igor still holding the port)."""
        try:
            status = self.status()
        except ActuatorError:
            status = None
        position = self.position()
        if status is None and position is None:
            raise ActuatorError(
                f"nothing on {self.port_name} answers 0TS? or 0TP? at "
                f"{self.cfg.actuator.baud} baud: wrong port, wrong "
                "controller (an Agilis talks at 921600 and does not know these "
                "commands), the controller off, or Igor still holding the port")
        return {"status": status, "position": position, "port": self.port_name,
                "kind": "nanopz"}

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


class AgilisActuator(Actuator):
    """A Newport Agilis AG-UC2 or AG-UC8. Fixed 921600 baud. The controller
    is put in remote mode on open (its front-panel buttons stop working
    until ``close`` returns it to local mode) and the configured channel is
    selected on an AG-UC8."""

    BAUD = 921600
    connected = True
    kind = "agilis"

    def __init__(self, cfg: RigConfig, port: str | None = None,
                 serial_factory=None):
        A = cfg.actuator
        self.cfg = cfg
        self.axis = int(A.axis) if int(A.axis) in (1, 2) else 1
        self.port_name = port or A.port
        self.port = _open_serial(self.port_name, self.BAUD, serial_factory,
                                 timeout=1.0)
        log.info("Agilis open on %s at %d baud, axis %d", self.port_name,
                 self.BAUD, self.axis)
        self.write("MR")                          # remote mode, required first
        time.sleep(0.05)
        if int(A.channel) > 0:
            self.write(f"CC{int(A.channel)}")
            time.sleep(0.05)

    # -- protocol ---------------------------------------------------------

    def write(self, command: str) -> None:
        self.port.write((command + "\r\n").encode("ascii"))
        self.port.flush()

    def query(self, command: str) -> str:
        """Send and read one reply line, with the command's own letters
        stripped off the front: ``1TP`` answers ``1TP-12`` -> ``-12``."""
        self.port.reset_input_buffer()
        self.write(command)
        raw = self.port.readline().decode("ascii", errors="replace").strip()
        if not raw:
            raise ActuatorError(
                f"no reply to {command!r} on {self.port_name}: wrong port, "
                "not an Agilis (a NanoPZ talks at 19200), or the controller off")
        if raw.startswith(command):
            raw = raw[len(command):]
        return raw.strip()

    def identify(self) -> dict:
        version = self.query("VE")
        status = self.status()
        return {"status": status, "position": self.position(),
                "port": self.port_name, "kind": "agilis", "version": version}

    # -- motion -----------------------------------------------------------

    def step(self, closer: bool = True) -> None:
        A = self.cfg.actuator
        sign = -1 if int(A.closer_sign) < 0 else 1
        steps = sign * A.step_size if closer else -sign * A.step_size
        self.write(f"{self.axis}PR{steps}")
        self.wait_ready(timeout=5.0)
        time.sleep(A.settle_s)

    def wait_ready(self, timeout: float = 5.0) -> None:
        """Block until the axis reports ready (status 0), or the timeout."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            try:
                if self.status().strip() == "0":
                    return
            except ActuatorError:
                return
            time.sleep(0.05)
        log.warning("Agilis axis %d still busy after %.1f s", self.axis, timeout)

    def stop(self) -> None:
        self.write(f"{self.axis}ST")

    # -- feedback ---------------------------------------------------------

    def position(self) -> int | None:
        """The controller's step counter (``TP``): steps since power-on or
        the last zero, not an absolute position."""
        try:
            reply = self.query(f"{self.axis}TP")
        except ActuatorError:
            log.warning("Agilis did not report its step count", exc_info=True)
            return None
        digits = "".join(c for c in reply if c.isdigit() or c == "-")
        try:
            return int(digits)
        except ValueError:
            log.warning("could not parse the step count from %r", reply)
            return None

    def status(self) -> str:
        return self.query(f"{self.axis}TS")

    def error(self) -> str:
        """``TE``: the error of the previous command, 0 when there was none."""
        return self.query("TE")

    def close(self) -> None:
        try:
            self.stop()
            self.write("ML")                      # the front panel works again
        except Exception:
            pass
        try:
            self.port.close()
        except Exception:
            pass


KINDS = {"nanopz": NanoPZActuator, "agilis": AgilisActuator}


def make_actuator(cfg: RigConfig, rig_sim=None, connect: bool = True) -> Actuator:
    """The actuator for this config. ``connect=False`` leaves a configured
    controller as an ``UnconnectedActuator`` until Connect is pressed."""
    kind = cfg.actuator.kind.lower()
    if kind == "simulated" or (cfg.simulate and kind != "none"):
        return SimulatedActuator(cfg, rig_sim)
    if kind in KINDS:
        return KINDS[kind](cfg) if connect else UnconnectedActuator()
    return NullActuator()


# What each controller is asked, read-only, and how a move is sent. For
# rigtests/actuator_check.py; nothing else should use these.
PROBES = {
    "nanopz": {"baud": 19200, "queries": ("0TS?", "0TP?", "0VE?"),
               "move": lambda n: ("0MO", f"0PR{n}"), "after": "0TP?"},
    "agilis": {"baud": 921600, "queries": ("VE", "1TS", "1TP", "TE"),
               "move": lambda n: ("MR", f"1PR{n}"), "after": "1TP"},
}


def probe_port(port: str, kind: str = "nanopz", move: int = 0,
               serial_factory=None) -> list[tuple[str, bytes]]:
    """What the controller answers, raw, to that kind's read-only queries
    -- and, with ``move`` != 0, the step count after one relative move of
    that many steps (sign as given: watch which way it goes)."""
    probe = PROBES[kind]
    if serial_factory is None:
        import serial
        serial_factory = serial.Serial
    out: list[tuple[str, bytes]] = []
    ser = serial_factory(port=port, baudrate=probe["baud"], bytesize=8,
                         parity="N", stopbits=1, timeout=2.0)
    try:
        def send(cmd: str) -> None:
            ser.write((cmd + "\r\n").encode("ascii"))
            ser.flush()

        def ask(cmd: str) -> None:
            ser.reset_input_buffer()
            send(cmd)
            time.sleep(0.5)                     # let the whole reply arrive
            waiting = getattr(ser, "in_waiting", 0)
            out.append((cmd, ser.read(waiting) if waiting else ser.readline()))
        for cmd in probe["queries"]:
            ask(cmd)
        if move:
            for cmd in probe["move"](int(move)):
                send(cmd)
                time.sleep(0.1)
            time.sleep(1.5)
            ask(probe["after"])
            if kind == "agilis":
                send("ML")                      # the front panel works again
    finally:
        ser.close()
    return out
