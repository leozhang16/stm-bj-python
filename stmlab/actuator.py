"""Coarse approach actuator: a Newport NanoPZ (PZC200) or a Newport Agilis
(AG-UC2 / AG-UC8) over a serial port.

Two controllers, two languages. The NanoPZ is what the older Igor
procedures drove and what the notes below describe. The Agilis is what
this lab's Igor drives today (Actuator_VISA_functions.ipf, an AG-UC2 at
``ASRL4::INSTR``): it appears in Windows as "Newport AG-UC2-UC8 USB Serial
Port", talks at a fixed 921600 baud through NI-VISA, and its commands are
``mr`` (remote mode, required before a move), ``ml`` (local mode),
``<axis>SU<amp>`` (step amplitude 1-50), ``<axis>PR<n>`` (relative move,
n steps), ``<axis>TP`` (the step count), ``<axis>TS`` (status: 0 ready, 1
stepping, 2 jogging, 3 moving to a limit), ``<axis>ST`` (stop), ``CC<n>``
(channel 1-4, AG-UC8 only), ``TE`` (error of the previous command, 0 =
none) and ``VE`` (firmware version). Commands end in CR LF; replies carry
the command back in front of the value (``1TP2066``). On this rig +PR is
toward the sample (``actuator.closer_sign`` = +1).

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


def com_to_visa(port: str) -> str:
    """COM4 -> ASRL4::INSTR, the VISA resource name NI-VISA uses for a serial
    port. An already-VISA name (``ASRL4::INSTR``) is passed through."""
    p = port.strip()
    if p.upper().startswith("ASRL") or "::" in p:
        return p
    digits = "".join(c for c in p if c.isdigit())
    return f"ASRL{digits}::INSTR" if digits else p


AGILIS_ERRORS = {0: "no error", -1: "unknown command", -2: "axis out of range",
                 -3: "wrong format for parameter", -4: "parameter out of range",
                 -5: "not allowed in local mode", -6: "not allowed in current state"}


class AgilisActuator(Actuator):
    """A Newport Agilis AG-UC2 / AG-UC8, driven the way this lab's Igor does
    (Actuator_VISA_functions.ipf): through NI-VISA, 921600 baud, 8N1, no
    flow control, and the same four strings per move -- ``mr`` (remote),
    ``<axis>SU<amp>`` (step amplitude), ``<axis>PR<n>`` (n steps), ``ml``
    (local). Closer to the sample is +PR on this rig (``closer_sign`` = +1);
    apart is -PR, as Igor's StepActuatorApart. Verified on the rig: the
    controller's step counter moved by exactly the count sent.

    Where this goes beyond Igor: the controller answers, so every command
    is followed by ``TE`` (its error code) and refused loudly if it was not
    accepted, a move waits for ``TS`` = 0 (ready) instead of a fixed sleep,
    ``VE`` proves the link on Connect, and ``TP`` (the net step count since
    power-on) is the position shown in the window.
    """

    BAUD = 921600
    GAP_S = 0.02                  # after a command before the next
    connected = True
    kind = "agilis"

    def __init__(self, cfg: RigConfig, port: str | None = None,
                 resource: str | None = None, rm_factory=None):
        A = cfg.actuator
        self.cfg = cfg
        self.axis = int(A.axis) if int(A.axis) in (1, 2) else 1
        self.port_name = port or A.port
        self.resource = resource or A.visa_resource or com_to_visa(self.port_name)
        self.version: str | None = None
        # A run (the coarse approach) holds remote mode and the amplitude
        # and sends only the move per step: Igor's button sequence per step
        # is four commands and four error checks, far too slow for a loop.
        self._run_sign: int | None = None
        self._run_steps = 0

        if rm_factory is None:
            try:
                import pyvisa
            except ImportError as exc:
                raise ActuatorError(
                    f"pyvisa is not installed ({exc}); on the lab PC it is "
                    "already there for the Keithley. The Agilis needs it too "
                    "(NI-VISA, the same backend)") from exc

            def rm_factory(backend):
                return pyvisa.ResourceManager(backend)
            self._pyvisa = pyvisa
        else:
            self._pyvisa = None

        try:
            rm = rm_factory(A.visa_backend or "")
            self.inst = rm.open_resource(self.resource)
            self._configure()
        except ActuatorError:
            raise
        except Exception as exc:                 # noqa: BLE001
            raise ActuatorError(
                f"could not open the Agilis at {self.resource} "
                f"(from {self.port_name}): {exc}. Is Igor still holding the "
                "port, and is NI-VISA installed?") from exc

        log.info("Agilis open at %s (%s), axis %d", self.resource,
                 self.port_name, self.axis)
        # As Igor: nothing is sent on open; ``mr`` goes out around each move.
        # An AG-UC8 channel, if configured, is selected once here.
        if int(A.channel) > 0:
            self.write("mr")
            self.write(f"CC{int(A.channel)}")
            self.write("ml")

    def _configure(self) -> None:
        """NI-VISA serial attributes, matching Igor's SetupVISASerialPort."""
        inst = self.inst
        inst.baud_rate = self.BAUD
        inst.data_bits = 8
        inst.timeout = 500
        inst.write_termination = ""
        inst.read_termination = ""
        pv = self._pyvisa
        if pv is not None:
            inst.parity = pv.constants.Parity.none
            inst.stop_bits = pv.constants.StopBits.one
            try:
                inst.flow_control = pv.constants.ControlFlow.none
            except Exception:                    # some backends name it differently
                pass

    # -- protocol ---------------------------------------------------------

    def write(self, command: str, gap_s: float | None = None) -> None:
        """One command, CR LF, then the gap the controller needs."""
        self.inst.write_raw((command + "\r\n").encode("ascii"))
        time.sleep(self.GAP_S if gap_s is None else gap_s)

    def query(self, command: str, wait_s: float = 0.4) -> str | None:
        """Send a query and return its reply line, or None when nothing
        comes back within ``wait_s`` (an unpowered box answers nothing)."""
        waiting = int(getattr(self.inst, "bytes_in_buffer", 0) or 0)
        if waiting:
            self.inst.read_bytes(waiting)        # drop anything stale
        self.inst.write_raw((command + "\r\n").encode("ascii"))
        t0 = time.monotonic()
        while time.monotonic() - t0 < wait_s:
            time.sleep(0.004)
            waiting = int(getattr(self.inst, "bytes_in_buffer", 0) or 0)
            if waiting:
                time.sleep(0.004)                # the rest of the line
                waiting = int(getattr(self.inst, "bytes_in_buffer", 0) or waiting)
                raw = self.inst.read_bytes(waiting)
                return raw.decode("ascii", errors="replace").strip()
        return None

    def error(self) -> int | None:
        """``TE``: the controller's error code for the previous command."""
        reply = self.query("TE")
        if reply is None:
            return None
        digits = "".join(c for c in reply.split("TE")[-1] if c.isdigit() or c == "-")
        try:
            return int(digits)
        except ValueError:
            return None

    def _checked(self, command: str) -> None:
        """Send a command and refuse to go on if the controller did not
        accept it -- a parameter out of range or a wrong state would
        otherwise pass silently, as it did in Igor."""
        self.write(command)
        code = self.error()
        if code not in (0, None):
            raise ActuatorError(
                f"the Agilis refused {command!r}: TE{code} "
                f"({AGILIS_ERRORS.get(code, 'unknown error')})")

    def identify(self) -> dict:
        """Prove the link: VE (firmware), the axis status and step count.
        Raises when nothing answers -- the box's USB port shows up in
        Windows even when the controller is switched off."""
        self.version = self.query("VE")
        status = self.status()
        if self.version is None and status is None:
            raise ActuatorError(
                f"nothing at {self.resource} answers VE or TS: the Agilis "
                "is switched off or asleep (its USB port shows up in Windows "
                "either way), or Igor is still holding the port")
        return {"status": status, "position": self.position(),
                "port": self.port_name, "resource": self.resource,
                "kind": "agilis", "version": self.version}

    # -- motion -----------------------------------------------------------

    def _direction(self, closer: bool) -> tuple[int, int, int]:
        A = self.cfg.actuator
        amp = max(1, min(50, int(A.step_amplitude)))
        count = max(1, int(A.step_size))
        toward = 1 if int(A.closer_sign) >= 0 else -1     # +PR is closer on this rig
        return (toward if closer else -toward), amp, count

    def begin_run(self, closer: bool = True) -> None:
        """Start a run of steps in one direction: remote mode and the
        amplitude once, checked, so that each ``step`` is one command."""
        sign, amp, _count = self._direction(closer)
        self._checked("mr")
        self._checked(f"{self.axis}SU{'' if sign > 0 else '-'}{amp}")
        self._run_sign, self._run_steps = sign, 0

    def end_run(self) -> None:
        """Back to local mode, as Igor leaves the box after every move."""
        if self._run_sign is not None:
            self._run_sign = None
            self.write("ml")

    def step(self, closer: bool = True) -> None:
        sign, amp, count = self._direction(closer)
        if self._run_sign == sign:
            # In a run: the move alone, waited out; the first one checked.
            self.write(f"{self.axis}PR{sign * count}")
            self._run_steps += 1
            if self._run_steps == 1:
                code = self.error()
                if code not in (0, None):
                    raise ActuatorError(
                        f"the Agilis refused the move: TE{code} "
                        f"({AGILIS_ERRORS.get(code, 'unknown error')})")
            self.wait_ready(timeout=2.0 + 0.02 * count)
            return
        if self._run_sign is not None:                    # a run the other way
            self.end_run()
        self._checked("mr")                                # Igor's button, exactly
        self._checked(f"{self.axis}SU{'' if sign > 0 else '-'}{amp}")
        self._checked(f"{self.axis}PR{sign * count}")
        self.wait_ready(timeout=2.0 + 0.02 * count)
        self._checked("ml")
        time.sleep(self.cfg.actuator.settle_s)

    def wait_ready(self, timeout: float = 5.0) -> None:
        """Block until the axis reports ready (TS = 0), or the timeout."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            st = self.status()
            if st is None or st == "0":
                return
            time.sleep(0.01)
        log.warning("Agilis axis %d still busy after %.1f s", self.axis, timeout)

    def stop(self) -> None:
        self.write(f"{self.axis}ST")

    # -- feedback ---------------------------------------------------------

    def status(self) -> str | None:
        """``TS``: '0' ready, '1' stepping, '2' jogging, '3' to a limit."""
        reply = self.query(f"{self.axis}TS")
        if reply is None:
            return None
        return reply.split("TS")[-1].strip()

    def position(self) -> int | None:
        """``TP``: the controller's net step count since power-on (or the
        last ZP) -- a counter, not a calibrated position. The AG-UC2 only
        answers it in remote mode, so outside a run it is asked between a
        ``mr`` and an ``ml``."""
        if self._run_sign is None:
            self.write("mr")
            reply = self.query(f"{self.axis}TP")
            self.write("ml")
        else:
            reply = self.query(f"{self.axis}TP")
        if reply is None:
            return None
        digits = "".join(c for c in reply.split("TP")[-1] if c.isdigit() or c == "-")
        try:
            return int(digits)
        except ValueError:
            log.warning("could not parse the step count from %r", reply)
            return None

    def close(self) -> None:
        self._run_sign = None
        try:
            self.write("ml")                     # the front panel works again
        except Exception:
            pass
        try:
            self.inst.close()
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
               "wake": ("0MO",), "move": lambda n: ("0MO", f"0PR{n}"),
               "after": "0TP?"},
    "agilis": {"baud": 921600, "queries": ("VE", "1TS", "1TP", "TE"),
               "wake": ("MR",), "move": lambda n: ("MR", f"1PR{n}"),
               "after": "1TP"},
}

TERMINATORS = {"CRLF": "\r\n", "CR": "\r", "LF": "\n"}


def probe_port(port: str, kind: str = "nanopz", move: int = 0,
               serial_factory=None, terminator: str = "\r\n",
               wake: bool = False, xonxoff: bool = False,
               wait_s: float = 0.5) -> list[tuple[str, bytes]]:
    """What the controller answers, raw, to that kind's read-only queries
    -- and, with ``move`` != 0, the step count after one relative move of
    that many steps (sign as given: watch which way it goes).

    ``terminator``, ``wake`` (send the controller's harmless first command,
    motor on or remote mode, before asking) and ``xonxoff`` are the knobs a
    silent port is probed with; ``modem_lines`` reads the handshake pins.
    """
    probe = PROBES[kind]
    if serial_factory is None:
        import serial
        serial_factory = serial.Serial
    out: list[tuple[str, bytes]] = []
    ser = serial_factory(port=port, baudrate=probe["baud"], bytesize=8,
                         parity="N", stopbits=1, timeout=2.0, xonxoff=xonxoff)
    try:
        def send(cmd: str) -> None:
            ser.write((cmd + terminator).encode("ascii"))
            ser.flush()

        def ask(cmd: str) -> None:
            ser.reset_input_buffer()
            send(cmd)
            time.sleep(wait_s)                  # let the whole reply arrive
            waiting = getattr(ser, "in_waiting", 0)
            out.append((cmd, ser.read(waiting) if waiting else ser.readline()))
        if wake:
            for cmd in probe["wake"]:
                send(cmd)
                time.sleep(0.2)
                waiting = getattr(ser, "in_waiting", 0)
                out.append((cmd, ser.read(waiting) if waiting else b""))
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


def modem_lines(port: str, baud: int = 19200, serial_factory=None) -> dict:
    """The handshake inputs as the PC sees them. A powered RS-232 device
    usually drives DSR and CTS high; an unpowered one, an unplugged cable
    or a bare header leave them low. (A USB virtual port reports whatever
    its chip says.)"""
    if serial_factory is None:
        import serial
        serial_factory = serial.Serial
    ser = serial_factory(port=port, baudrate=baud, bytesize=8, parity="N",
                         stopbits=1, timeout=0.5)
    try:
        return {name: bool(getattr(ser, name, False))
                for name in ("cts", "dsr", "cd", "ri")}
    finally:
        ser.close()
