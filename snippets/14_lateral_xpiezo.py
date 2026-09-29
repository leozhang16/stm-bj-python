"""SNIPPET 14 -- The lateral X piezo and the site loop.  [experiment 07]

A histogram from one spot tells you about that spot. This walks the tip
across the sample and takes a fresh batch at each site.

The ORDER is the whole thing: the X piezo moves only while the tip is
withdrawn by three COARSE steps.
"""

# _common first, before numpy: it checks the interpreter has the
# dependencies and prints which one to use instead. Imported after
# numpy, a bare ModuleNotFoundError wins and says nothing useful.
from _common import rule, sim_config

import logging

from stmlab import xpiezo
from stmlab.instrument import Rig
from stmlab.safety import SafetyViolation
from stmlab.xpiezo import XPiezoError

logging.basicConfig(level=logging.WARNING)

cfg = sim_config()
X = cfg.xpiezo

rule("The X piezo")
print(f"  {X.nm_per_volt} nm/V (K_XPiezoScale) on the 2nd card's {X.channel}")
print(f"  range {X.min_v}-{X.max_v} V = "
      f"{(X.max_v - X.min_v) * X.nm_per_volt / 1000:.2f} um of travel")
print(f"  a 200 nm step = {200 / X.nm_per_volt:.4f} V")
print(f"  -> {int((X.max_v - X.min_v) * X.nm_per_volt / 200)} sites at "
      f"200 nm spacing before you run out")

rule("It tracks position and REFUSES out of range")
xp = xpiezo.make_xpiezo(cfg)
xp.setup()
print(f"  {'move':>12} {'position (nm)':>16} {'volts':>9}")
for step in (200.0, 200.0, 200.0):
    xp.move_nm(step)
    print(f"  {step:>+12.0f} {xp.position_nm:>16.1f} {xp.voltage:>9.4f}")
try:
    xp.move_nm(10_000.0)
except XPiezoError as exc:
    print(f"\n  move_nm(+10000) -> REFUSED\n    {exc}")
print("\n  Igor did NOT check. It would simply have clipped, and every site")
print("  past the clip point would be the SAME site while the file names")
print("  went on incrementing.")
xp.stop()

rule("The order that is not negotiable")
print("""  Per site, Igor did:

      StartMeasurement("")          a batch of constant-bias traces
      StepActuatorApart("") x3      withdraw, 100 ms between steps
      MoveXPiezo(XDistance)         the lateral move
      ApproachButton("")            coarse approach back into contact

  The X piezo moves ONLY while the tip is withdrawn -- and withdrawn by
  three COARSE actuator steps, not merely a fine-piezo retract.

  A lateral move in contact drags the tip through the monolayer. It
  destroys the film along the path, reshapes the tip apex, and does both
  SILENTLY: the next site's traces look fine and are measuring a different
  tip on damaged sample.""")

rule("The interlock enforces it, every step")
rig = Rig(cfg).open()
rig.piezo_goto(4.0)                      # extend the fine piezo
print(f"  fine piezo at {rig.piezo_v:.3f} V")
try:
    rig.coarse_step(closer=False)
except SafetyViolation as exc:
    print(f"  coarse_step() -> REFUSED\n    {exc}")
rig.withdraw()
print(f"\n  after withdraw(): {rig.piezo_v:.3f} V")
rig.coarse_step(closer=False)
print(f"  coarse_step() -> allowed, {rig.coarse_steps} step(s) taken")
print("\n  Checked on EVERY step, not just at the start of the loop -- the")
print("  site loop never moves the fine piezo, and a bug that did would")
print("  otherwise go unnoticed until it cost a tip.")

rule("What to compare across sites")
print("""  peak position stable, area stable  -> uniform coverage; pool the sites
  position stable, area varies       -> patchy; same molecule where present
  POSITION VARIES                    -> the sites are not measuring the same
                                        thing. DO NOT POOL.

  That third case is the reason to run this experiment at all: it stops you
  publishing an average of two different molecules.""")

rule("Status")
print("  The simulated surface does not vary with X -- every site is")
print("  identical by construction. Simulate tests the choreography and")
print("  nothing about coverage. The hardware path needs a second card")
print("  this rig does not currently have.")
rig.close()
