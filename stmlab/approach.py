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

def _run_in(rig, stop_flag) -> int:
    """Phase one: the actuator steps the sample in, with the piezo at its
    low end, until the current passes the stop level. Igor watched the
    sampled current and stopped above 0.1 uA (Functions_STMBJ.ipf:1780).
    A controller that can hold a run (the Agilis) gets one command per
    step; the loop is one move and one current read per step."""
    A = rig.cfg.actuator
    act = rig.actuator
    begin, end = getattr(act, "begin_run", None), getattr(act, "end_run", None)
    if begin is not None:
        begin(closer=True)
    start = rig.coarse_steps
    try:
        while True:
            _check_stop(rig, stop_flag, "coarse approach")
            if abs(rig.read_current_ua()) >= A.stop_current_ua:
                break
            rig.coarse_step(closer=True)          # interlock + budget checked here
    finally:
        if end is not None:
            end()
    return rig.coarse_steps - start


def _single_steps(rig, closer: bool, n: int, stop_flag) -> None:
    """``n`` single actuator steps, whatever the configured step count."""
    A = rig.cfg.actuator
    saved = A.step_size
    A.step_size = 1
    try:
        for _ in range(n):
            _check_stop(rig, stop_flag, "coarse approach")
            rig.coarse_step(closer=closer)
    finally:
        A.step_size = saved


def _open_with_single_steps(rig, stop_flag) -> int:
    """Single steps apart, with the piezo at its low end, until the current
    is below the stop level. Returns the number of steps."""
    A = rig.cfg.actuator
    n = 0
    while abs(rig.read_current_ua()) >= A.stop_current_ua:
        if n >= A.max_backoff_steps:
            raise ApproachError(
                f"the junction is still closed after {n} single steps apart "
                "with the piezo at its low end; the tip may be crashed. Step "
                "apart by hand and look at the current.")
        _single_steps(rig, closer=False, n=1, stop_flag=stop_flag)
        n += 1
    return n


def _scan_up(rig, stop_flag) -> float | None:
    """The piezo from its low end upward in ``scan_step_nm`` steps until the
    current passes the stop level: the contact voltage, or None when the
    top of the range is reached with nothing there."""
    cfg = rig.cfg
    A, L = cfg.actuator, cfg.limits
    rig.piezo_goto(A.approach_piezo_v)
    step_v = cfg.cal.nm_to_piezo_volts(A.scan_step_nm)
    while True:
        _check_stop(rig, stop_flag, "coarse approach")
        if abs(rig.read_current_ua()) >= A.stop_current_ua:
            return rig.piezo_v
        if rig.piezo_v + step_v > L.piezo_ao_max_v:
            return None
        rig.piezo_step_nm(A.scan_step_nm)


def coarse_approach(rig, stop_flag=None) -> dict:
    """Bring the surface to where the fine piezo meets it mid range.

    Phase one, Igor's: with the piezo at its low end the actuator steps
    the sample in until current. Phase two aims: single steps apart until
    the junction is open, a quick piezo scan upward to find the contact
    voltage, and then -- contact below the band: the sample goes apart;
    above it, or none within reach: closer. The first two scans measure
    how many volts of contact one single actuator step is worth, and
    from then on the number of steps is computed so the next scan lands
    in the band. Done when the contact is inside [band_lo_v, band_hi_v]:
    the junction is opened by a few nanometres and the piezo left there,
    with room both ways, which is where Approach and the pulls want it.

    Every coarse step passes ``Rig.coarse_step`` (the interlock: piezo at
    or below its low end; the step budget) and is taken with the piezo
    at its low end, never into a closed junction.

    Returns a dict: steps_in, rounds, contact_v, open_v, step_v (volts of
    contact per single actuator step, when measured). Raises ApproachError
    when stopped by request or when it cannot converge.
    """
    cfg: RigConfig = rig.cfg
    A, L = cfg.actuator, cfg.limits

    if A.kind == "none":
        raise ApproachError(
            "no coarse actuator is configured (actuator.kind == 'none'), so "
            "the coarse approach must be done by hand. Bring the tip in until "
            "the fine piezo can reach the surface, then call engage().")

    rig.state = RigState.APPROACHING
    rig.piezo_goto(A.approach_piezo_v)
    require_retracted(cfg, rig.piezo_v, "coarse approach",
                      limit=rig.coarse_step_limit_v())

    steps_in = _run_in(rig, stop_flag)
    log.info("coarse approach: current after %d steps in", steps_in)

    centre = 0.5 * (A.band_lo_v + A.band_hi_v)
    step_v: float | None = None          # volts of contact per single step apart
    prev: float | None = None            # the previous scan's contact voltage
    net = 0                              # signed single steps apart since that scan
    contact_v = None
    for round_ in range(1, A.max_approach_rounds + 1):
        rig.piezo_goto(A.approach_piezo_v)
        net += _open_with_single_steps(rig, stop_flag)
        contact_v = _scan_up(rig, stop_flag)
        if contact_v is not None and A.band_lo_v <= contact_v <= A.band_hi_v:
            break
        if contact_v is not None and prev is not None and net != 0:
            # Two scans with a known number of single steps between them:
            # that is the step size, in volts of contact per step apart.
            measured = (contact_v - prev) / net
            if measured > 0.02:
                step_v = measured
                log.info("one single actuator step is worth %.3f V of contact",
                         step_v)
        prev, net = contact_v, 0
        if contact_v is None:
            closer = True                       # out of reach: in, and look again
            n = 1 if step_v is None else max(
                1, int(round((L.piezo_ao_max_v - centre) / step_v)))
        else:
            want = centre - contact_v           # +: the surface must go apart
            closer = want < 0
            n = 1 if step_v is None else max(1, int(round(abs(want) / step_v)))
        rig.piezo_goto(A.approach_piezo_v)      # never a coarse step extended
        if closer and abs(rig.read_current_ua()) >= A.stop_current_ua:
            n, closer = 1, False                # closed at the low end: open first
        _single_steps(rig, closer=closer, n=n, stop_flag=stop_flag)
        net += -n if closer else n
        log.info("round %d: contact at %s V, %d single step(s) %s", round_,
                 f"{contact_v:.3f}" if contact_v is not None else "none",
                 n, "closer" if closer else "apart")
    else:
        raise ApproachError(
            f"coarse approach did not land the contact between {A.band_lo_v} "
            f"and {A.band_hi_v} V in {A.max_approach_rounds} rounds (last "
            f"contact at {contact_v}); the actuator's step may be larger than "
            "the band is wide: widen band_lo_v/band_hi_v in the config.")

    # In contact at contact_v, inside the band: open the junction by a few
    # nanometres and leave the piezo there.
    separate(rig, stop_flag)
    rig.state = RigState.RETRACTED
    return {"steps_in": steps_in, "rounds": round_, "contact_v": contact_v,
            "open_v": rig.piezo_v, "step_v": step_v}


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
