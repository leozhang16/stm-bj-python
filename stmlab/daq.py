"""DAQmx, and nothing else.

The whole card is exposed through one verb: :meth:`DaqSession.play`, which
puts a two-channel waveform on the outputs and hands back what the inputs saw
during it. Approach steps, DC moves, and the pull ramp are all the same
operation with different waveforms, which is not a simplification for its own
sake -- it is how the hardware actually behaves, since every AO start triggers
an AI capture.

**Python never times anything.** The ramp is precomputed and handed to the
card. AI is armed once, retriggerable, and triggered off ``ao/StartTrigger``,
so both run on the card's own clock and loop overhead lands between plays,
never inside one.

Two deviations from project-architecture.pdf, both forced by this rig:

*Idle output behaviour.* The document specifies
``AOIdleOutputBehavior.ZERO_VOLTS`` so the card parks itself if the process
dies. On a unipolar piezo 0 V is fully retracted, so that is the right *final*
state -- but it is the wrong *between-plays* state, because the approach
depends on the piezo holding position across dozens of separate plays. Dropping
to 0 V between them would retract the tip after every step and the approach
would never converge. This asks for ``MAINTAIN_EXISTING_VALUE`` instead and
warns loudly if the card refuses it. Parking is then done explicitly by
``safety.park_all_outputs`` on every exit path.

*Reading.* The document uses ``register_every_n_samples_acquired_into_buffer``
with a queue. A blocking ``read`` of a known sample count is equivalent here
and has no callback thread to reason about; the queue matters when traces
arrive faster than the consumer, which at one pull per second they do not.
"""

from __future__ import annotations

import logging

import numpy as np

from .config import RigConfig

log = logging.getLogger(__name__)


class DaqError(RuntimeError):
    pass


def sense_terminal_config(m):
    """ChannelMap.sense_terminal -> nidaqmx TerminalConfiguration."""
    from nidaqmx.constants import TerminalConfiguration as TC
    names = {"default": "DEFAULT", "rse": "RSE", "nrse": "NRSE", "diff": "DIFF"}
    key = names.get(m.sense_terminal.lower())
    if key is None:
        raise DaqError(f"channels.sense_terminal {m.sense_terminal!r} is not "
                       f"one of {sorted(names)}")
    member = getattr(TC, key, None)
    if member is None and key == "DIFF":        # older nidaqmx spelling
        member = getattr(TC, "DIFFERENTIAL")
    return member


class DaqSession:
    """Open AI and AO tasks on one card, with a fixed record length.

    On a two-card rig (``channels.low_res_device`` set) a third, one-channel
    AI task reads the piezo sense line on the second card during every play:
    same N, same rate, started by the same ``ao/StartTrigger``. Its samples
    are left in :attr:`last_sense_v` rather than added to the record, so the
    (2, n) contract of :meth:`play` -- and every row index above this layer --
    is untouched.
    """

    def __init__(self, cfg: RigConfig):
        self.cfg = cfg
        self._ai = None
        self._ao = None
        self._sense = None                   # piezo sense task, or None
        self._n = 0
        self._ao_running = False
        self._retriggerable = True
        self.granted_rate_hz: float | None = None
        self.idle_behavior: str = "unknown"
        # Piezo sense readback from the last play, (n,) volts, or None when
        # this rig has no sense line.
        self.last_sense_v: np.ndarray | None = None
        # "hardware" once the sense task triggers off ao/StartTrigger,
        # "software" if that route was refused and it is started by Python.
        self.sense_sync: str = "none"
        self._warned_retrigger = False
        self._warned_sense_rate = False

    # -- lifecycle --------------------------------------------------------

    def open(self) -> "DaqSession":
        import nidaqmx
        from nidaqmx.constants import AOIdleOutputBehavior

        m, lim = self.cfg.channels, self.cfg.limits

        self._ao = nidaqmx.Task("stmbj_ao")
        # The piezo channel's card-enforced range is taken straight from
        # SafetyLimits, so the range the hardware clips at and the range the
        # software checks can never drift apart.
        self._ao.ao_channels.add_ao_voltage_chan(
            m.path(m.ao_piezo),
            min_val=lim.piezo_ao_min_v, max_val=lim.piezo_ao_max_v)
        self._ao.ao_channels.add_ao_voltage_chan(
            m.path(m.ao_bias),
            min_val=-m.bias_ao_range_v, max_val=m.bias_ao_range_v)

        try:
            for chan in self._ao.ao_channels:
                chan.ao_idle_output_behavior = \
                    AOIdleOutputBehavior.MAINTAIN_EXISTING_VALUE
            self.idle_behavior = "maintain"
        except Exception as exc:                      # device may not support
            self.idle_behavior = "zero"
            log.warning(
                "card refused MAINTAIN_EXISTING_VALUE (%s). Outputs will fall "
                "to 0 V in the gap between plays. 0 V is retracted on this "
                "piezo so it is safe, but the approach will lose position "
                "every step and each play starts with a mechanical kick. "
                "Check this on a scope before trusting an approach.", exc)

        self._ai = nidaqmx.Task("stmbj_ai")
        for chan in m.ai_channels:
            self._ai.ai_channels.add_ai_voltage_chan(
                chan, min_val=-m.ai_range_v, max_val=m.ai_range_v)

        # The piezo sense line lives on the other card, so it cannot join the
        # task above (a DSA card and an X-series card never share a task).
        # One channel, its own task, read alongside the record.
        sense_path = m.piezo_sense_path
        if sense_path is not None:
            self._sense = nidaqmx.Task("stmbj_sense")
            self._sense.ai_channels.add_ai_voltage_chan(
                sense_path, terminal_config=sense_terminal_config(m),
                min_val=-m.sense_ai_range_v, max_val=m.sense_ai_range_v)
            log.info("piezo sense readback on %s (%s)", sense_path,
                     m.sense_terminal)

        # Timing and triggering are deferred to configure(), which the first
        # play() calls with the record length it needs.
        return self

    def close(self) -> None:
        for task in (self._sense, self._ai, self._ao):
            if task is not None:
                try:
                    task.stop()
                except Exception:
                    pass
                try:
                    task.close()
                except Exception:
                    pass
        self._ai = self._ao = self._sense = None
        self._ao_running = False

    def __enter__(self) -> "DaqSession":
        return self.open()

    def __exit__(self, *exc) -> bool:
        self.close()
        return False

    # -- configuration ----------------------------------------------------

    def configure(self, n_samples: int) -> None:
        """Set the record length for subsequent plays.

        Cheap to call with an unchanged value, expensive otherwise: changing
        it re-arms AI, and on a delta-sigma card re-arming means the
        decimation filter settles again. Switch between the approach's short
        records and the pull's long one once per attempt, not once per step.
        """
        if n_samples == self._n:
            return

        from nidaqmx.constants import AcquisitionType

        rate = self.cfg.ramp.sample_rate_hz

        try:
            self._ai.stop()
        except Exception:
            pass
        try:
            self._ao.stop()
        except Exception:
            pass
        self._ao_running = False

        self._ao.timing.cfg_samp_clk_timing(
            rate, sample_mode=AcquisitionType.FINITE,
            samps_per_chan=n_samples)
        self._ai.timing.cfg_samp_clk_timing(
            rate, sample_mode=AcquisitionType.FINITE,
            samps_per_chan=n_samples)

        # AI follows AO's start trigger, so the two share the card's clock and
        # a fixed skew rather than whatever Python's scheduler decides.
        self._ai.triggers.start_trigger.cfg_dig_edge_start_trig(
            self.cfg.channels.ao_start_trigger)

        # Preferred: arm AI once and let it re-trigger, so the decimation
        # filter never re-settles between traces. Not every card supports a
        # retriggerable start trigger, and a DSA card is exactly where it
        # might not, so fall back to arming per play rather than failing.
        try:
            self._ai.triggers.start_trigger.retriggerable = True
            self._retriggerable = True
        except Exception as exc:
            self._retriggerable = False
            if not self._warned_retrigger:          # once, not per configure()
                self._warned_retrigger = True
                log.warning(
                    "card refused a retriggerable start trigger (%s); arming "
                    "AI once per play instead. Correct, but the input filter "
                    "re-settles at the start of every record -- keep "
                    "pre_pad_samples comfortably above the settling length or "
                    "the metallic-contact region of each trace will be "
                    "corrupt.", str(exc).splitlines()[0])

        granted = float(self._ai.timing.samp_clk_rate)
        if self.granted_rate_hz is None:
            self.granted_rate_hz = granted
            if abs(granted - rate) > 1e-6:
                log.warning(
                    "requested %.6f Hz, card granted %.6f Hz; the granted "
                    "rate is what every time axis uses", rate, granted)

        if self._sense is not None:
            self._configure_sense(n_samples, rate, granted)

        if self._retriggerable:
            self._ai.start()      # armed once, stays armed for the session
        self._n = n_samples

    def _configure_sense(self, n_samples: int, rate: float,
                         record_rate: float) -> None:
        """Time the sense task like the record and start it on AO's trigger.

        The second card runs on its own oscillator and is asked for the
        *nominal* rate, not the rate the first card granted: a DSA card grants
        40000.000035 Hz, and an X-series card asked for that rounds UP to the
        next divisor of its 100 MHz timebase, 40016 Hz, four samples of
        stretch over a trace. Asked for 40000 Hz it divides exactly, and the
        two clocks then differ by under a part per million.

        The start trigger crosses the PXI backplane: DAQmx routes
        ``/dev1/ao/StartTrigger`` to the second card by itself when both
        cards sit in one chassis that NI MAX knows about. If that route is
        refused, the task is started from Python just before the outputs
        instead -- good to about a millisecond, enough to watch the piezo,
        not enough to time anything -- and says so loudly.
        """
        from nidaqmx.constants import AcquisitionType

        try:
            self._sense.stop()
        except Exception:
            pass
        self._sense.timing.cfg_samp_clk_timing(
            rate, sample_mode=AcquisitionType.FINITE,
            samps_per_chan=n_samples)

        try:
            self._sense.triggers.start_trigger.cfg_dig_edge_start_trig(
                self.cfg.channels.ao_start_trigger)
            # Commit so a refused route fails here, not inside play().
            from nidaqmx.constants import TaskMode
            self._sense.control(TaskMode.TASK_COMMIT)
            self.sense_sync = "hardware"
        except Exception as exc:
            self._sense.triggers.start_trigger.disable_start_trig()
            self.sense_sync = "software"
            log.warning(
                "could not start the piezo sense task from %s (%s). It will "
                "be software-started instead, so the readback is aligned to "
                "the record only to about a millisecond. Check that both "
                "cards are in one PXI chassis identified in NI MAX.",
                self.cfg.channels.ao_start_trigger, exc)

        got = float(self._sense.timing.samp_clk_rate)
        stretch = n_samples * abs(got - record_rate) / record_rate
        if stretch > 0.25 and not self._warned_sense_rate:
            self._warned_sense_rate = True
            log.warning("sense card granted %.6f Hz against the record's "
                        "%.6f Hz; the readback will stretch by %.2f samples "
                        "over a %d-sample record", got, record_rate, stretch,
                        n_samples)

    # -- the one verb -----------------------------------------------------

    def play(self, waveform: np.ndarray, timeout_s: float = 10.0) -> np.ndarray:
        """Output ``waveform`` and return what the inputs saw during it.

        ``waveform`` is (2, n): row 0 the piezo command, row 1 the bias, both
        in volts at the DAQ. The return is (2, n): row 0 the junction voltage
        on ai0, row 1 the preamp output on ai1. On a two-card rig the piezo
        sense readback for the same n samples is left in ``last_sense_v``.
        """
        waveform = np.asarray(waveform, dtype=float)
        if waveform.ndim != 2 or waveform.shape[0] != 2:
            raise ValueError(f"waveform must be (2, n), got {waveform.shape}")
        n = waveform.shape[1]
        self.configure(n)

        if self._ao_running:
            self._ao.stop()          # required before rewriting the buffer
            self._ao_running = False

        self._ao.write(waveform, auto_start=False, timeout=timeout_s)

        # AI must be armed before AO starts, since AO's start is the trigger.
        if not self._retriggerable:
            self._ai.stop()
            self._ai.start()
        if self._sense is not None:
            # Armed per play: an X-series input has no filter to settle, so
            # re-arming costs nothing. Hardware-triggered, this waits for the
            # same edge as AI; software-started, it begins now, a few hundred
            # microseconds before the outputs.
            self._sense.stop()
            self._sense.start()

        self._ao.start()             # fires ao/StartTrigger -> AI begins
        self._ao_running = True
        self._ao.wait_until_done(timeout=timeout_s)

        data = self._ai.read(number_of_samples_per_channel=n,
                             timeout=timeout_s)
        if self._sense is not None:
            sense = self._sense.read(number_of_samples_per_channel=n,
                                     timeout=timeout_s)
            self.last_sense_v = np.asarray(sense, dtype=float).ravel()
        # AO is left running: the outputs hold their last sample, which is how
        # the piezo keeps its position between plays.
        return np.asarray(data, dtype=float)

    @property
    def effective_rate_hz(self) -> float:
        return self.granted_rate_hz or self.cfg.ramp.sample_rate_hz
