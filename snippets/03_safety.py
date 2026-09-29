"""SNIPPET 03 -- The refusals, and why each is a refusal.  [all experiments]

Nothing here touches hardware. Every function is a pure check on numbers, so
you can provoke all five hazards safely and read what the code says back.
"""

# _common first, before numpy: it checks the interpreter has the
# dependencies and prints which one to use instead. Imported after
# numpy, a bare ModuleNotFoundError wins and says nothing useful.
from _common import rule

from stmlab import safety
from stmlab.config import RigConfig
from stmlab.safety import SafetyViolation

cfg = RigConfig()

def try_it(label, fn):
    try:
        result = fn()
        print(f"  {label:<44} -> allowed  {result if result is not None else ''}")
    except SafetyViolation as exc:
        print(f"  {label:<44} -> REFUSED")
        for line in str(exc).splitlines():
            print(f"      {line}")

rule("1. Piezo commands CLAMP (loudly). They do not abort.")
print("  A ramp overshooting by a millivolt should be truncated, not aborted")
print("  mid-pull. But every clamp is logged, so a clamp that fires every")
print("  trace shows up in the session log instead of passing silently.\n")
for v in (5.0, 10.4, -0.3):
    print(f"  clamp_piezo({v:+.1f} V) = {safety.clamp_piezo(cfg, v):+.3f} V")

rule("2. Bias REFUSES. It does not clamp.")
print("  There is no case where you meant more bias than the limit and would")
print("  be happy with silently less: that produces a data file labelled with")
print("  a voltage that was never applied.\n")
for v in (0.1, 0.5, 0.9):
    try_it(f"check_bias({v:+.2f} V)   limit +/-0.5",
           lambda v=v: safety.check_bias(cfg, v))

rule("3. THE interlock: no coarse step while the piezo is extended.")
print("  One coarse actuator step advances further than the piezo's whole")
print("  620 nm range. Taking one while the piezo is out drives the tip into")
print("  the sample. There is NO position sensor -- this trusts the tracked")
print("  last-commanded value, which is why every motion must go through")
print("  Rig.play().\n")
for v in (0.0, 0.05, 0.1, 4.0):
    try_it(f"require_retracted(piezo at {v:.2f} V)",
           lambda v=v: safety.require_retracted(cfg, v, "coarse step closer"))

rule("4. Pull headroom: unipolar piezos cannot ramp below zero.")
print("  A clipped ramp gives a short trace, and a short trace is")
print("  indistinguishable from a junction that broke early. That is the")
print("  worst kind of artefact: it looks exactly like data.\n")
for v in (5.0, 0.10, 0.05):
    try_it(f"check_pull_headroom(contact at {v:.2f} V)",
           lambda v=v: safety.check_pull_headroom(cfg, v))

rule("5. Approach runaway budget.")
for n in (0, 1999, 2000):
    try_it(f"check_step_budget({n} steps taken)",
           lambda n=n: safety.check_step_budget(cfg, n))

rule("6. This folder adds two more refusals Igor did not have")
print("""  Igor's five branches only ever RETRACTED from the contact point, so
  the floor was the only hazard that existed. Two things here go the other
  way, and both refuse:\n""")

from stmlab import ramps, xpiezo                    # noqa: E402
from stmlab.xpiezo import XPiezoError              # noqa: E402

deep = RigConfig()
deep.simulate = True
deep.limits.bias_max_v = 1.2
deep.push_pull.initial_pull_nm = 1.0
deep.push_pull.push_pull_nm = 40.0
try:
    ramps.build_push_pull(deep, 9.9)
    print("  push-pull through the CEILING -> allowed (unexpected)")
except SafetyViolation as exc:
    print("  push-pull through the CEILING -> REFUSED")
    print(f"      {exc}")

xcfg = RigConfig()
xcfg.simulate = True
xcfg.channels.low_res_device = "Dev2"
xp = xpiezo.make_xpiezo(xcfg)
xp.setup()
try:
    xp.move_nm(10_000.0)
except XPiezoError as exc:
    print("\n  X piezo beyond its range -> REFUSED")
    print(f"      {exc}")
print("\n  Igor guarded neither. A clipped push is a push that did not")
print("  happen; a clipped lateral move means every later 'site' is the")
print("  SAME site while the file names go on incrementing.")

rule("Where each one is enforced")
print("""  clamp_piezo          Rig.hold(), Rig.play()      every DC move
  check_bias           Rig.hold(), build_ramp()    every waveform
  require_retracted    Rig.coarse_step()           every coarse step
  check_pull_headroom  build_ramp()                every pull
  check_step_budget    Rig.coarse_step()           every coarse step
  verify_devices       SafeSession.__enter__()     once per run
  park_all_outputs     SafeSession.__exit__()      exit, exception, Ctrl-C""")
