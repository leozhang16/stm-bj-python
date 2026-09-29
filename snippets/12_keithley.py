"""SNIPPET 12 -- The Keithley 428 amplifier.  [support: chapter 20]

Every conductance in this folder is "the 428's output voltage divided by its
gain". This snippet shows the exact GPIB commands, the suppress
calibration, and the series-resistance correction -- all against
SimulatedKeithley, which records commands instead of sending them.
"""

# _common first, before numpy: it checks the interpreter has the
# dependencies and prints which one to use instead. Imported after
# numpy, a bare ModuleNotFoundError wins and says nothing useful.
from _common import rule, sim_config

import logging

import numpy as np

from stmlab import keithley
from stmlab.approach import engage
from stmlab.config import G0_SIEMENS
from stmlab.instrument import Rig

logging.basicConfig(level=logging.WARNING)

cfg = sim_config()
K = cfg.keithley

rule("Opening it: Igor's init string is deliberately inert")
amp = keithley.make_keithley(cfg)
amp.open()
print(f"  resource {K.resource}   (Igor: ibdev={{0,22,...}})")
print(f"  sent: {amp.commands}")
print("  C1 zero-check ON, P0 filter off, B0 bias off, N0 suppress off.")
print("  The amplifier wakes up doing nothing -- the right default for a box")
print("  wired to a tip.")

rule("The command language")
amp.commands.clear()
amp.zero_check(False)
amp.set_gain(6)
amp.set_suppress_ua(0.25)
amp.suppress_enable(True)
amp.filter(True)
for c in amp.commands:
    print(f"  -> {c}")
print("\n  X executes the buffer. H6R<g> sets gain 10^g V/A;")
print("  H8S<amps>,0 the suppress value; N1/N0 turns it on and off.")

rule("Gain is the number that scales EVERY result")
for g in (5, 6, 7):
    amp.set_gain(g)
    v_at_1g0 = 1.0 * G0_SIEMENS * cfg.ramp.bias_v * 10 ** g
    print(f"  gain 10^{g} V/A -> 1 G0 reads {v_at_1g0:8.3f} V at ai1"
          f"{'   <-- CLIPS' if v_at_1g0 > 10 else ''}")
amp.set_gain(K.gain_exponent)
print(f"\n  cfg.cal.preamp_gain_v_per_a = {cfg.cal.preamp_gain_v_per_a:.3g} V/A")
print(f"  cfg.keithley.gain_exponent  = {K.gain_exponent}  (10^6 = 1e6)")
print("  THESE TWO MUST AGREE: the exponent programs the box, the config's")
print("  gain is what every conductance divides by. validate() now checks:")
from stmlab.config import RigConfig, validate     # noqa: E402
mismatch = RigConfig()
mismatch.keithley.gain_exponent = 7
for w in validate(mismatch):
    if "keithley" in w:
        print(f"\n    warning: {w}")

rule("find_suppress: Igor's TestVirtualGround")
print("  The amplifier has an offset -- at zero junction current its output")
print("  is not zero. Suppress is a compensating current dialled in to null")
print("  it. find_suppress sweeps -1 to +1 uA in 21 steps at zero bias, fits")
print("  a line through the MIDDLE points, and sets the zero crossing.\n")
rig = Rig(cfg).open()
engage(rig)
new_s, sweep, readings = keithley.find_suppress(rig, amp, n_points=11,
                                                settle_s=0.0,
                                                read_samples=500)
print(f"  {'suppress (uA)':>14} {'mean output (V)':>18}")
for s, r in zip(sweep, readings):
    print(f"  {s:>14.3f} {r:>18.6f}")
print(f"\n  zero crossing -> suppress = {new_s:+.4f} uA")
print("  The ENDPOINTS are excluded from the fit: the amplifier is still")
print("  settling at the extremes, and including them tilts the line.")
print("  (Igor's sleep/T 5 and its 'SPIKE problem' comment at :1123.)")
print("\n  Igor's FindSuppress button zeroed the applied bias first and")
print("  restored it after. Do the same around this call -- the function")
print("  cannot know what bias you wanted back.")

rule("Keithley-sourced bias needs the series correction")
print("  B1X turns on the 428's internal bias source. Then the junction")
print("  voltage is NO LONGER measured at ai0: you know only the total")
print("  two-terminal current, with the wiring resistance in the path.\n")
print("      G/G0 = (1 / (V_bias/I - R_series)) / G0     Igor GenerateTrace:390\n")
bias = 0.1
for g0_true in (1.0, 0.1, 0.01):
    r_junction = 1.0 / (g0_true * G0_SIEMENS)
    i = bias / (r_junction + K.series_resistance_ohm)
    naive = (i / bias) / G0_SIEMENS
    fixed = float(keithley.series_corrected_conductance(
        np.array([i]), bias, K.series_resistance_ohm)[0])
    print(f"  true {g0_true:>6.2f} G0 -> uncorrected {naive:>8.4f} G0, "
          f"corrected {fixed:>8.4f} G0")
print(f"\n  R_series = {K.series_resistance_ohm:,.0f} ohm, INHERITED from Igor.")
print("  That is comparable to a 0.1 G0 junction, so a wrong value does not")
print("  just scale your result -- it DISTORTS THE SHAPE of the whole")
print("  low-conductance region, in a way that looks like physics.")
print("  If you use Keithley-sourced bias, measure your own.")

rule("Status")
print("  This has NEVER been connected to a Keithley. The command strings")
print("  are transcribed from the Igor source and reviewed; pyvisa is not")
print("  even a default requirement. Before trusting it:")
print("    1. talk to the amplifier with pyvisa by hand")
print("    2. set a gain and verify it on the FRONT PANEL")
print("    3. run find_suppress, check the output offset with a meter")
print("    4. only then wire it to a tip")

amp.close()
rig.close()
