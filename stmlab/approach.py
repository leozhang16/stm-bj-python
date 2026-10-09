"""Getting into contact, and back out of it.

Igor equivalents:

    engage          HighResMakeContact      Functions_STMBJ.ipf:1239
    coarse_approach HighResCardApproach     Functions_STMBJ.ipf:1723
    smash           SmashFun                Functions_STMBJ.ipf:1375

``engage`` is the state machine that runs before every trace. It has two
halves, and the order matters: break any existing contact *first*, then close
in slowly. Skipping the first half and approaching from an already-shorted
junction is how you weld the tip to the sample.
"""

from __future__ import annotations

import logging

from .config import RigConfig
from .safety import RigState, SafetyViolation, require_retracted

log = logging.getLogger(__name__)


class ApproachError(RuntimeError):
    """Approach could not reach the requested state. Not a safety failure."""


def _headroom_ok(cfg: RigConfig, piezo_v: float) -> bool:
    need = cfg.cal.nm_to_piezo_volts(cfg.ramp.pull_length_nm)
    floor = cfg.limits.piezo_ao_min_v + cfg.ramp.piezo_headroom_v
    return piezo_v - need >= floor


def _check_stop(rig, stop_flag, what: str) -> None:
    """A long loop that can be interrupted from outside: the Stop button, or
    the window closing. Raising here, between two steps, leaves the rig in a
    consistent state (the tracker is true, no play is in flight) -- which is
    exactly what closing the cards under a running loop does not."""
    if stop_flag is not None and stop_flag.is_set():
        raise ApproachError(f"{what} stopped by request at {rig.piezo_v:.4f} V")


def separate(rig, stop_flag=None) -> None:
    """Retract until the junction is open. Igor's first loop."""
    cfg: RigConfig = rig.cfg
    R, L = cfg.ramp, cfg.limits

    log.debug("breaking contact in %.1f nm steps", R.retract_step_nm)
    while True:
        _check_stop(rig, stop_flag, "separate")
        # Only the bound being travelled toward can block. Retracting from the
        # top of the range is fine; it is the floor that ends this loop.
        if rig.piezo_v <= L.piezo_ao_min_v:
            raise ApproachError(
                f"could not separate contacts: piezo is at the {rig.piezo_v:.3f} V "
                f"floor and the junction is still closed. Back the coarse "
                f"actuator off.")
        rig.piezo_step_nm(-R.retract_step_nm)
        g0, railed = rig.probe()
        if not railed and g0 < R.break_g0:
            return


def close_in(rig, stop_flag=None) -> None:
    """Approach in small steps until contact. Igor's second loop."""
    cfg: RigConfig = rig.cfg
    R, L = cfg.ramp, cfg.limits

    while True:
        _check_stop(rig, stop_flag, "approach")
        if rig.piezo_v >= L.piezo_ao_max_v:
            raise ApproachError(
                f"could not make contact: piezo is at the "
                f"{rig.piezo_v:.3f} V ceiling with no contact. The coarse "
                f"actuator needs to take up the difference.")
        rig.piezo_step_nm(R.approach_step_nm)
        if rig.in_contact():
            return


def engage(rig, stop_flag=None) -> RigState:
    """Break any existing contact, then make a fresh one.

    Returns ``RigState.ENGAGED`` on success. Raises ApproachError if the piezo
    runs out of range in either direction -- Igor returned -2 and -3 for those
    two cases and terminated the run (Functions_STMBJ.ipf:1297, 1336) -- or,
    when a ``stop_flag`` (a ``threading.Event``) is given and set, between
    two steps: an approach over the whole range takes two minutes, and the
    person waiting must be able to end it cleanly.

    Also refuses to report success from a position with no room left for the
    pull. On a unipolar piezo, contact made low in the range cannot be pulled
    from, and finding that out here rather than mid-ramp keeps the failure
    legible.
    """
    cfg: RigConfig = rig.cfg
    rig.state = RigState.APPROACHING

    if rig.in_contact():
        separate(rig, stop_flag)

    close_in(rig, stop_flag)

    if not _headroom_ok(cfg, rig.piezo_v):
        raise ApproachError(
            f"contact made at {rig.piezo_v:.4f} V, too low in the piezo range "
            f"to pull {cfg.ramp.pull_length_nm} nm without hitting the "
            f"{cfg.limits.piezo_ao_min_v} V floor. Retract the coarse "
            f"actuator by a step and re-approach.")

    rig.state = RigState.ENGAGED
    return rig.state


def smash(rig) -> None:
    """Drive the tip in hard, then pull it back. Igor's SmashFun.

    Deliberately blunt: reshaping the apex against the substrate is how a tip
    that has stopped producing clean traces is recovered without breaking
    vacuum or changing sample.
    """
    R = rig.cfg.ramp
    log.info("smashing tip: %+.0f nm then %+.0f nm",
             R.smash_in_nm, R.smash_out_nm)
    rig.piezo_step_nm(R.smash_in_nm)
    rig.piezo_step_nm(R.smash_out_nm)


# --------------------------------------------------------------------------
# Coarse approach
# --------------------------------------------------------------------------

def coarse_approach(rig, stop_flag=None) -> int:
    """Step the coarse actuator in until current appears.

    Igor watched the sampled current and stopped above 0.1 uA
    (Functions_STMBJ.ipf:1780). The fine piezo must be retracted throughout --
    ``Rig.coarse_step`` enforces that on every single step, not just at the
    start, because the loop below never moves the piezo and a bug that did
    would otherwise go unnoticed.

    Returns the number of steps taken.
    """
    cfg: RigConfig = rig.cfg
    A = cfg.actuator

    if A.kind == "none":
        raise ApproachError(
            "no coarse actuator is configured (actuator.kind == 'none'), so "
            "the coarse approach must be done by hand. Bring the tip in until "
            "the fine piezo can reach the surface, then call engage().")

    require_retracted(cfg, rig.piezo_v, "coarse approach")
    rig.state = RigState.APPROACHING

    start = rig.coarse_steps
    while True:
        if stop_flag is not None and stop_flag.is_set():
            log.info("coarse approach stopped by request")
            break

        current_ua = rig.read_current_ua()
        if abs(current_ua) >= A.stop_current_ua:
            log.info("coarse approach: %.3f uA after %d steps",
                     current_ua, rig.coarse_steps - start)
            break

        rig.coarse_step(closer=True)          # interlock + budget checked here

    rig.state = RigState.RETRACTED
    return rig.coarse_steps - start


def withdraw_coarse(rig, steps: int = 1) -> None:
    """Back the coarse actuator off, for when contact is made too low."""
    for _ in range(steps):
        rig.coarse_step(closer=False)


def recover_headroom(rig, max_backoff: int = 5) -> RigState:
    """Engage, backing the coarse actuator off if contact lands too low.

    The routine to call in an unattended loop: drift pushes the contact point
    down the piezo range over hours, and without this the run dies with
    'no headroom' at 3 a.m. Falls back to raising the error if the coarse
    actuator cannot help.
    """
    for attempt in range(max_backoff + 1):
        try:
            return engage(rig)
        except ApproachError:
            if attempt == max_backoff or rig.cfg.actuator.kind == "none":
                raise
            log.info("no headroom for the pull; backing the coarse actuator "
                     "off one step (%d/%d)", attempt + 1, max_backoff)
            rig.withdraw()
            try:
                withdraw_coarse(rig, 1)
            except SafetyViolation:
                raise
    raise ApproachError("unreachable")
