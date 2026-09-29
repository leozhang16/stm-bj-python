"""SNIPPET 04 -- Approach and engage on the simulated card.  [all experiments]

This is the first snippet with a `Rig`. `cfg.simulate = True` swaps
`daq.DaqSession` for `sim.SimulatedDaqSession`; every layer above it is the
same code that runs on the real card.

Watch the piezo voltage. It is the number the interlock trusts, and it is
updated by Rig.play() and nothing else.
"""

# _common first, before numpy: it checks the interpreter has the
# dependencies and prints which one to use instead. Imported after
# numpy, a bare ModuleNotFoundError wins and says nothing useful.
from _common import rule

import logging

from stmlab.approach import engage, smash
from stmlab.config import RigConfig
from stmlab.instrument import Rig

logging.basicConfig(level=logging.INFO, format="    %(levelname)-7s %(message)s")

cfg = RigConfig()
cfg.simulate = True

rule("Opening a simulated rig")
rig = Rig(cfg).open()
print(f"  state             {rig.state.value}")
print(f"  piezo             {rig.piezo_v:.4f} V = {rig.piezo_nm:.1f} nm (parked)")
print(f"  sample rate       {rig.sample_rate_hz:,.0f} Hz")
print(f"  simulated surface {rig._session.surface_nm:.1f} nm  "
      f"(the fake card's secret; the real rig has no such number)")

rule("Rig.probe() -- conductance now, plus 'is the preamp railed?'")
g0, railed = rig.probe()
print(f"  at {rig.piezo_nm:6.1f} nm:  G = {g0:.3e} G0   railed={railed}")
print("  Far from the surface the simulator gives a tunnelling floor set by")
print("  the current-channel noise, not a true zero. Real rigs do too.")

rule("Walking in by hand, 25 nm at a time")
print(f"  {'piezo (V)':>10} {'piezo (nm)':>11} {'G (G0)':>12}  railed")
for _ in range(12):
    rig.piezo_step_nm(25.0)
    g0, railed = rig.probe()
    print(f"  {rig.piezo_v:10.4f} {rig.piezo_nm:11.1f} {g0:12.3e}  {railed}")
    if railed or g0 > cfg.ramp.engage_g0:
        print("  ^ contact. Note it is detected EITHER by crossing engage_g0")
        print("    (0.5 G0) OR by the preamp railing: at Rf=1e6 and 100 mV the")
        print("    input saturates at 1.23 G0, so hard contact reads as a rail")
        print("    rather than as a big number. Rig.probe() returns both.")
        break

rule("engage(): break contact first, then close in slowly")
print("  Order matters. Approaching from an already-shorted junction is how")
print("  you weld the tip to the sample.\n")
state = engage(rig)
print(f"\n  state             {state.value}")
print(f"  contact at        {rig.piezo_v:.4f} V = {rig.piezo_nm:.1f} nm")
print(f"  headroom for pull {rig.piezo_v - cfg.cal.nm_to_piezo_volts(cfg.ramp.pull_length_nm):.4f} V "
      f"above the {cfg.limits.piezo_ao_min_v} V floor")

rule("The interlock, live")
try:
    rig.coarse_step(closer=True)
except Exception as exc:
    print(f"  coarse_step() while engaged -> REFUSED\n      {exc}")
rig.withdraw()
print(f"\n  after withdraw(): piezo {rig.piezo_v:.4f} V, state {rig.state.value}")
print("  coarse_step() would now be allowed (if an actuator were configured)")

rule("smash(): deliberate tip reconditioning, Igor's SmashFun")
engage(rig)
before = rig._session.surface_nm
smash(rig)
print(f"  simulated surface moved {rig._session.surface_nm - before:+.3f} nm "
      f"and tip quality reset to {rig._session._tip_quality:.2f}")

rig.close()
print("\n  rig.close() withdrew the piezo and dropped the bias to 0 V.")
