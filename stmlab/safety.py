"""Limits, interlocks, and output parking.

Five hazards, in rough order of how much they cost:

    1  coarse step while the piezo is extended  -> tip, often the sample
    2  AO left non-zero when the process dies   -> sustained extension
    3  piezo driven outside its range           -> depoled or cracked ceramic
    4  approach runaway                         -> tip into the surface
    5  wrong device                             -> preamp and tip

This module imports only ``config``. If it ever needs to import ``daq`` or
``instrument``, a check has drifted into the wrong layer.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from enum import Enum

from .config import RigConfig

log = logging.getLogger(__name__)


class SafetyViolation(Exception):
    """A refusal. Never caught inside this package."""


class RigState(Enum):
    UNKNOWN = "unknown"
    RETRACTED = "retracted"
    APPROACHING = "approaching"
    ENGAGED = "engaged"
    PULLING = "pulling"


# --------------------------------------------------------------------------
# Clamp or refuse
# --------------------------------------------------------------------------

def clamp_piezo(cfg: RigConfig, volts: float) -> float:
    """Force a piezo command inside its limits, loudly.

    A ramp that overshoots by a millivolt should be truncated, not aborted
    mid-pull -- so this clamps. But it logs every time, so a clamp that fires
    repeatedly shows up in the session log instead of passing silently.
    """
    lo, hi = cfg.limits.piezo_ao_min_v, cfg.limits.piezo_ao_max_v
    if volts < lo or volts > hi:
        clamped = min(max(volts, lo), hi)
        log.warning("piezo command %.4f V clamped to %.4f V", volts, clamped)
        return clamped
    return volts


def check_bias(cfg: RigConfig, volts: float) -> float:
    """Bias is a hard refusal, not a clamp.

    The asymmetry with :func:`clamp_piezo` is deliberate. There is no case
    where you meant to apply more bias than the limit and would be happy with
    silently less: quietly reducing it produces data labelled with a bias that
    was never applied, which is worse than stopping.
    """
    if abs(volts) > cfg.limits.bias_max_v:
        raise SafetyViolation(
            f"bias {volts:+.3f} V exceeds limit "
            f"+/-{cfg.limits.bias_max_v} V")
    return volts


def check_pull_headroom(cfg: RigConfig, start_v: float) -> None:
    """Refuse a pull that would descend through the piezo's floor.

    Only meaningful because this piezo is unipolar. The ramp descends from
    wherever contact was made; if contact happened low in the range, the ramp
    would clip and the trace would be silently short -- a truncated trace looks
    exactly like a junction that broke early, which is the worst kind of
    artefact because it is indistinguishable from data.
    """
    need = cfg.cal.nm_to_piezo_volts(cfg.ramp.pull_length_nm)
    floor = cfg.limits.piezo_ao_min_v + cfg.ramp.piezo_headroom_v
    if start_v - need < floor:
        raise SafetyViolation(
            f"refusing pull: contact at {start_v:.4f} V, a "
            f"{cfg.ramp.pull_length_nm} nm pull needs {need:.4f} V, which "
            f"would reach {start_v - need:.4f} V -- below the {floor:.4f} V "
            f"working floor. Retract with the coarse actuator and re-approach "
            f"higher in the piezo range.")


# --------------------------------------------------------------------------
# The interlock
# --------------------------------------------------------------------------

def require_retracted(cfg: RigConfig, piezo_v: float, action: str) -> None:
    """Refuse a coarse move unless the fine piezo is retracted.

    The single most important function here. A coarse step advances the tip
    further than the piezo's full range; taking one while the piezo is
    extended drives the tip into the sample.

    ``piezo_v`` is the LAST COMMANDED value, tracked by the instrument layer.
    There is no position sensor, so this is a bookkeeping interlock -- which
    means every piezo write must go through the tracker or this guard is
    lying to you. That is the real argument for keeping ``daq.py`` thin and
    forcing all motion through ``instrument.py``: not elegance, but the fact
    that this function depends on it.
    """
    limit = cfg.limits.coarse_step_max_piezo_v
    if piezo_v > limit:
        raise SafetyViolation(
            f"refusing {action}: piezo is at {piezo_v:.3f} V, must be below "
            f"{limit:.3f} V. Retract the fine piezo first.")


def check_step_budget(cfg: RigConfig, steps_taken: int) -> None:
    """Approach runaway protection."""
    if steps_taken >= cfg.limits.max_coarse_steps:
        raise SafetyViolation(
            f"coarse approach took {steps_taken} steps without finding "
            f"current (budget {cfg.limits.max_coarse_steps}). Either the tip "
            f"is not where you think it is, or the current path is open.")


# --------------------------------------------------------------------------
# Devices
# --------------------------------------------------------------------------

def verify_devices(cfg: RigConfig) -> None:
    """Check the configured device exists and is the card we think it is.

    With one card there is no alias-swap hazard of the kind
    project-architecture.pdf warns about -- that needed two cards to confuse.
    What remains is worth catching anyway: a device that is absent, renamed
    after a MAX reset, or a different model entirely.
    """
    if cfg.simulate:
        return

    import nidaqmx.system  # imported here so the module works without DAQmx

    system = nidaqmx.system.System.local()
    names = [d.name for d in system.devices]
    if cfg.channels.device not in names:
        raise SafetyViolation(
            f"device {cfg.channels.device!r} not found. Present: "
            f"{', '.join(names) or '(none)'}. Check NI MAX, and remember "
            f"aliases are reassigned when cards move slots.")

    expected = cfg.channels.expected_product_type
    if expected:
        actual = system.devices[cfg.channels.device].product_type
        if expected.lower().replace("-", "") not in \
                actual.lower().replace("-", ""):
            raise SafetyViolation(
                f"device {cfg.channels.device!r} is a {actual!r}, expected "
                f"{expected!r}. Refusing to run: the channel map assumes the "
                f"4461's pinout, and driving the piezo ramp into a preamp "
                f"input destroys the preamp.")


def park_all_outputs(cfg: RigConfig) -> None:
    """Drive every output to its safe value, using short-lived tasks.

    Creates its own tasks rather than reusing the session's, so it still works
    when the main tasks are broken -- which is exactly when it is needed.

    Safe means 0 V on both channels: 0 V is fully retracted on this unipolar
    piezo, and 0 V bias passes no current. This is the third of three
    independent defences, the other two being the card's own idle behaviour
    and every ramp ending at a safe value.
    """
    if cfg.simulate:
        log.info("simulate: park_all_outputs()")
        return

    import nidaqmx

    with suppress(Exception):
        with nidaqmx.Task() as task:
            task.ao_channels.add_ao_voltage_chan(
                cfg.channels.path(cfg.channels.ao_piezo),
                min_val=cfg.limits.piezo_ao_min_v,
                max_val=cfg.limits.piezo_ao_max_v)
            task.ao_channels.add_ao_voltage_chan(
                cfg.channels.path(cfg.channels.ao_bias),
                min_val=-cfg.channels.bias_ao_range_v,
                max_val=cfg.channels.bias_ao_range_v)
            task.write([0.0, 0.0], auto_start=True)
            task.stop()
    log.info("outputs parked at 0 V")


# --------------------------------------------------------------------------
# Session
# --------------------------------------------------------------------------

class SafeSession:
    """Parks outputs on normal exit, on exception, and on Ctrl-C.

    Cannot protect against SIGKILL or a power cut -- that is what the card's
    ``ao_idle_output_behavior`` is for, set when the task is created in
    ``daq.py``.
    """

    def __init__(self, cfg: RigConfig):
        self.cfg = cfg
        self.state = RigState.UNKNOWN

    def __enter__(self) -> "SafeSession":
        verify_devices(self.cfg)
        park_all_outputs(self.cfg)   # known state before starting
        self.state = RigState.RETRACTED
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        park_all_outputs(self.cfg)
        return False                 # never swallow the exception
