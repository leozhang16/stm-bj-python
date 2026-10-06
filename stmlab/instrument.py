"""The rig: open tasks, and where the tip is.

``Rig`` holds two things that must live and die together -- the open DAQmx
tasks, and the last commanded piezo voltage. The second is load-bearing:
``safety.require_retracted`` has no position sensor to consult, so it trusts
that tracked variable.

Which is why :meth:`Rig.play` is the only way to reach the card from above
this layer, and why it updates the tracker itself rather than asking callers
to remember. One direct ``task.write()`` that bypasses it and the interlock
becomes confidently wrong.
"""

from __future__ import annotations

import logging

import numpy as np

from . import safety
from .config import RigConfig
from .safety import RigState

log = logging.getLogger(__name__)


class Rig:
    def __init__(self, cfg: RigConfig, session=None, actuator=None):
        self.cfg = cfg
        self.state = RigState.UNKNOWN
        self.attempts = 0

        self._session = session
        self._actuator = actuator
        self._piezo_v = cfg.ramp.piezo_park_v
        self._bias_v = cfg.ramp.bias_v
        self.coarse_steps = 0

        # Piezo sense readback from the last play, (n,) volts, or None on a
        # rig without a sense line. Informational: nothing decides on it.
        self.last_sense_v: np.ndarray | None = None

    # -- lifecycle --------------------------------------------------------

    def open(self) -> "Rig":
        if self._session is None:
            if self.cfg.simulate:
                from .sim import SimulatedDaqSession
                self._session = SimulatedDaqSession(self.cfg)
            else:
                from .daq import DaqSession
                self._session = DaqSession(self.cfg).open()

        if self._actuator is None:
            from .actuator import make_actuator
            self._actuator = make_actuator(self.cfg)

        # Establish a known output state, and with it a truthful tracker.
        self.piezo_goto(self.cfg.ramp.piezo_park_v)
        self.state = RigState.RETRACTED

        rate = self.sample_rate_hz
        if self.cfg.cal.granted_sample_rate_hz is None:
            self.cfg.cal.granted_sample_rate_hz = rate
        return self

    def close(self) -> None:
        try:
            self.withdraw()
        except Exception:
            log.exception("withdraw during close failed; parking anyway")
        for obj in (self._session, self._actuator):
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass

    def __enter__(self) -> "Rig":
        return self.open()

    def __exit__(self, *exc) -> bool:
        self.close()
        return False

    # -- state ------------------------------------------------------------

    @property
    def piezo_v(self) -> float:
        """Last commanded piezo voltage. The interlock trusts this."""
        return self._piezo_v

    @property
    def piezo_nm(self) -> float:
        return self.cfg.cal.piezo_volts_to_nm(self._piezo_v)

    @property
    def bias_v(self) -> float:
        return self._bias_v

    @property
    def sample_rate_hz(self) -> float:
        return getattr(self._session, "effective_rate_hz",
                       self.cfg.ramp.sample_rate_hz)

    # -- the funnel -------------------------------------------------------

    def play(self, waveform: np.ndarray) -> np.ndarray:
        """Output a waveform, capture the inputs, and update the tracker.

        Every motion in the package goes through here. The tracker is updated
        from the waveform's final piezo sample, so it cannot fall out of step
        with what was actually commanded.
        """
        waveform = np.asarray(waveform, dtype=float)
        M = self.cfg.channels

        lo, hi = self.cfg.limits.piezo_ao_min_v, self.cfg.limits.piezo_ao_max_v
        row = waveform[M.ROW_PIEZO]
        if row.min() < lo or row.max() > hi:
            log.warning("piezo waveform clamped into [%.3f, %.3f] V", lo, hi)
            waveform = waveform.copy()
            waveform[M.ROW_PIEZO] = np.clip(row, lo, hi)

        record = self._session.play(waveform)
        self.last_sense_v = getattr(self._session, "last_sense_v", None)

        self._piezo_v = float(waveform[M.ROW_PIEZO, -1])
        self._bias_v = float(self.cfg.cal.bias_output_sign
                             * waveform[M.ROW_BIAS, -1])
        return record

    @property
    def sense_nm(self) -> float | None:
        """Piezo position the sense line reported at the end of the last play,
        in nm; None without a sense line. The tracker ``piezo_v`` is what the
        interlock trusts -- this is the number you compare it against."""
        if self.last_sense_v is None or self.last_sense_v.size == 0:
            return None
        discard = min(self.cfg.ramp.settle_discard, self.last_sense_v.size - 1)
        tail = self.last_sense_v[discard:]
        return float(self.cfg.cal.sense_volts_to_nm(np.mean(tail)))

    # -- DC moves ---------------------------------------------------------

    def hold(self, piezo_v: float | None = None, bias_v: float | None = None,
             n_samples: int | None = None) -> np.ndarray:
        """Hold a DC output for a moment and return what the inputs saw.

        Igor's WriteToHighRes plus the read that always followed it
        (Functions_STMBJ.ipf:1153, 1347-1352).
        """
        R = self.cfg.ramp
        piezo_v = self._piezo_v if piezo_v is None else piezo_v
        bias_v = self._bias_v if bias_v is None else bias_v
        n = n_samples or R.settle_samples

        safety.check_bias(self.cfg, bias_v)
        piezo_v = safety.clamp_piezo(self.cfg, piezo_v)

        waveform = np.repeat(
            [[piezo_v], [self.cfg.cal.bias_output_sign * bias_v]], n, axis=1)
        return self.play(waveform)

    def piezo_goto(self, volts: float) -> np.ndarray:
        return self.hold(piezo_v=volts)

    def piezo_step_nm(self, delta_nm: float) -> np.ndarray:
        """Move the fine piezo by a relative distance."""
        target = self._piezo_v + self.cfg.cal.nm_to_piezo_volts(delta_nm)
        return self.hold(piezo_v=target)

    def piezo_ramp_to(self, volts: float, ramp_s: float = 0.05) -> np.ndarray:
        """Move the fine piezo to ``volts`` along a short linear ramp, then
        hold there for the usual settle time; returns the record of both.

        ``hold`` jumps in one sample, which is right for the approach's small
        steps. This is for moves a person makes by hand -- the panel's slider
        or its step buttons, Igor's SetPiezoBiasFromSlider -- where the move
        can be large: a 50 ms ramp is kinder to the stage, and the record
        shows the junction closing or opening as the tip travels. The clamp,
        the bias check and the tracker are ``hold``'s, through ``play``.
        """
        R = self.cfg.ramp
        safety.check_bias(self.cfg, self._bias_v)
        target = safety.clamp_piezo(self.cfg, volts)
        n_ramp = max(2, int(round(ramp_s * self.sample_rate_hz)))
        piezo = np.concatenate([np.linspace(self._piezo_v, target, n_ramp),
                                np.full(R.settle_samples, target)])
        bias = np.full(piezo.size, self.cfg.cal.bias_output_sign * self._bias_v)
        return self.play(np.stack([piezo, bias]))

    def set_bias(self, volts: float) -> None:
        safety.check_bias(self.cfg, volts)
        self.hold(bias_v=volts)

    # -- measurement ------------------------------------------------------

    def read_conductance(self, n_samples: int | None = None) -> float:
        """Conductance in G0 at the present position.

        Averages only the tail of the record: the leading samples are still
        settling, both the amplifier's and the card's filter.
        """
        record = self.hold(n_samples=n_samples)
        return self.conductance_of(record)

    def probe(self, n_samples: int | None = None) -> tuple[float, bool]:
        """(conductance in G0, whether the preamp railed).

        The second value matters on a rig without a series resistor, where
        metallic contact is *past* the top of the measurable range: at
        Rf = 1e6 V/A and 100 mV bias the input saturates around 1.3 G0, so
        solid contact reads as a railed channel rather than a large number,
        and treating saturation as contact is what makes the approach
        terminate at all; the returned conductance is then a floor, not a
        measurement. Through this rig's 106 kohm series resistor the current
        is capped at bias / R and the amplifier does not rail at 100 mV, so
        contact is the first value, the conductance from the measured
        junction voltage, crossing ``ramp.engage_g0``.
        """
        record = self.hold(n_samples=n_samples)
        return self.conductance_of(record), self.is_saturated(record)

    def in_contact(self, n_samples: int | None = None) -> bool:
        g0, railed = self.probe(n_samples)
        return railed or g0 > self.cfg.ramp.engage_g0

    def conductance_of(self, record: np.ndarray) -> float:
        M, C, R = self.cfg.channels, self.cfg.cal, self.cfg.ramp
        keep = record.shape[1] - min(R.settle_discard, record.shape[1] - 1)

        current_v = float(np.mean(record[M.ROW_CURRENT, -keep:]))
        voltage_v = float(np.mean(record[M.ROW_VOLTAGE, -keep:]))

        junction_v = C.voltage_input_sign * voltage_v
        if abs(junction_v) < 1e-9:
            return float("inf")

        from .config import G0_SIEMENS
        return abs(C.volts_to_amps(current_v)) / abs(junction_v) / G0_SIEMENS

    def read_current_ua(self, n_samples: int | None = None) -> float:
        """Junction current in microamps. Used by the coarse approach."""
        record = self.hold(n_samples=n_samples)
        M, R = self.cfg.channels, self.cfg.ramp
        keep = record.shape[1] - min(R.settle_discard, record.shape[1] - 1)
        current_v = float(np.mean(record[M.ROW_CURRENT, -keep:]))
        return self.cfg.cal.volts_to_amps(current_v) * 1e6

    def is_saturated(self, record: np.ndarray, fraction: float = 0.5) -> bool:
        """Is the current channel railed over the settled part of the record?

        Judged on the same tail window the conductance uses, and on a majority
        of it: a single railed sample is a transient, half of them is contact.
        """
        M, R = self.cfg.channels, self.cfg.ramp
        keep = record.shape[1] - min(R.settle_discard, record.shape[1] - 1)
        tail = np.abs(record[M.ROW_CURRENT, -keep:])
        return bool(np.mean(tail >= self.cfg.limits.preamp_saturation_v)
                    >= fraction)

    # -- coarse actuator --------------------------------------------------

    @property
    def actuator(self):
        return self._actuator

    def coarse_step(self, closer: bool = True) -> None:
        """One coarse step, behind the interlock.

        Refuses unless the fine piezo is retracted. This is the guard that
        protects the tip, and it is why nothing else in the package is allowed
        to touch the actuator directly.
        """
        safety.require_retracted(
            self.cfg, self._piezo_v,
            f"coarse step {'closer' if closer else 'apart'}")
        safety.check_step_budget(self.cfg, self.coarse_steps)
        self._actuator.step(closer=closer)
        self.coarse_steps += 1

    # -- exits ------------------------------------------------------------

    def withdraw(self) -> None:
        """Retract the fine piezo to the park position and drop the bias."""
        self.hold(piezo_v=self.cfg.ramp.piezo_park_v, bias_v=0.0)
        self.state = RigState.RETRACTED
