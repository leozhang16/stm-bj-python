"""SNIPPET 09 -- IV sweep, and the sign convention that bites.  [experiment 03]

Everything else measures conductance at ONE bias. This holds a junction
still and sweeps the bias in a triangle.

The section on signs is the important one: `ao1` and the junction see
OPPOSITE polarity, and confusing them mirrors every IV curve you take.
"""

# _common first, before numpy: it checks the interpreter has the
# dependencies and prints which one to use instead. Imported after
# numpy, a bare ModuleNotFoundError wins and says nothing useful.
from _common import have_matplotlib, rule, save, sim_config

import logging

import numpy as np

from stmlab import ramps
from stmlab.approach import engage
from stmlab.instrument import Rig
from stmlab.trace import capture

logging.basicConfig(level=logging.WARNING)

cfg = sim_config()
cfg.limits.bias_max_v = 1.2          # the sweep reaches +/-1.0 V
R, M, C = cfg.ramp, cfg.channels, cfg.cal

rig = Rig(cfg).open()
engage(rig)

rule("The trajectory")
ramp = ramps.build_iv(cfg, rig.piezo_v)
print(f"  init pull {cfg.iv.init_pull_nm} nm | cap {cfg.iv.cap_nm} | "
      f"SWEEP {cfg.iv.ramp_nm} nm worth to +/-{cfg.iv.max_bias_v} V | "
      f"cap | final {cfg.iv.final_pull_nm} nm")
for seg, (a, b) in ramp.segments.items():
    print(f"    {seg:<14} {a:>6}-{b:<6}")

rule("SIGNS: ao1 and the junction are OPPOSITE")
bias_row = ramp.waveform[M.ROW_BIAS]
b1, b2, b3, b4 = ramp.meta["quarters"]
mid_q1 = ramp.pre_pad + (b1 + b2) // 2
ao1 = bias_row[mid_q1]
print(f"  cal.bias_output_sign  = {C.bias_output_sign:+.0f}")
print(f"  cal.voltage_input_sign = {C.voltage_input_sign:+.0f}")
print(f"  iv.positive_first      = {cfg.iv.positive_first}")
print("\n  first quarter of the sweep:")
print(f"    written to ao1     {ao1:+.3f} V")
print(f"    seen by the junction {C.voltage_input_sign * ao1:+.3f} V")
print("\n  BOTH ARE TRUE AND THEY ARE OPPOSITES. Igor negates the whole bias")
print("  wave at line 1533 ('to have normal convention'), which is what makes")
print("  the default drive ao1 negative first. iv_analysis.py reports the")
print("  JUNCTION voltage, so its first quarter runs 0 -> +1.0 V.")
print("\n  If a Python IV curve looks mirrored against an Igor one, look here")
print("  BEFORE suspecting the molecule.")

rule("The flag was renamed during this work")
print("  It arrived as `negative_first`, which was backwards: setting it True")
print("  made the sweep go POSITIVE first, and both the CLI help and the log")
print("  line said the opposite of what the card was doing.")
print("  It is now `iv.positive_first` / `--positive-first`.")
flipped = sim_config()
flipped.limits.bias_max_v = 1.2
flipped.iv.positive_first = True
r2 = ramps.build_iv(flipped, rig.piezo_v)
print(f"\n  positive_first=False -> ao1 first quarter {ao1:+.3f} V")
print(f"  positive_first=True  -> ao1 first quarter "
      f"{r2.waveform[M.ROW_BIAS][mid_q1]:+.3f} V")

rule("Play it, and look at the caps")
record = capture(rig, ramp)
if record is None:
    print("  alignment failed")
    rig.close()
    raise SystemExit(1)

g0 = record.conductance_g0(cfg)
a_in, b_in = ramp.segments["cap_in"]
a_out, b_out = ramp.segments["cap_out"]
g_in = float(np.nanmean(np.abs(g0[a_in:b_in])))
g_out = float(np.nanmean(np.abs(g0[a_out:b_out])))
print(f"  cap_in  {g_in:.3e} G0")
print(f"  cap_out {g_out:.3e} G0")
drift = np.log10(g_out / g_in) if g_in > 0 and g_out > 0 else float("nan")
print(f"  drift   {drift:+.3f} decades")
print("\n  The caps are NOT padding. If they disagree, the junction changed")
print("  DURING the sweep, and the IV curve is a composite of two different")
print("  objects rather than one junction's I(V).")

rule("The curve itself")
a, b = ramp.segments["iv_ramp"]
v_junction = C.voltage_input_sign * record.voltage_v[a:b]
i_amps = C.volts_to_amps(record.current_v[a:b])
print(f"  {b - a} samples, V from {v_junction.min():+.3f} to "
      f"{v_junction.max():+.3f} V")
print(f"  peak |I| {np.max(np.abs(i_amps)) * 1e9:.2f} nA")
fit = np.polyfit(v_junction, i_amps, 1)
from stmlab.config import G0_SIEMENS      # noqa: E402
print(f"  linear fit slope -> {fit[0] / G0_SIEMENS:.3e} G0")
print("\n  The SIMULATED junction is ohmic, so this fit is always perfect.")
print("  It tests the sweep geometry and the analysis plumbing, and tells")
print("  you nothing about what a real molecule will do.")

if have_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    t = np.arange(ramp.n_pull) / R.sample_rate_hz * 1e3
    ax[0].plot(t, C.voltage_input_sign
               * ramp.waveform[M.ROW_BIAS][ramp.pre_pad:ramp.pre_pad + ramp.n_pull],
               lw=1, color="crimson")
    ax[0].set_xlabel("time (ms)"); ax[0].set_ylabel("junction bias (V)")
    ax[0].set_title("commanded, as the junction sees it"); ax[0].grid(alpha=.3)
    ax[1].plot(v_junction, i_amps * 1e9, lw=.7)
    ax[1].set_xlabel("junction V"); ax[1].set_ylabel("I (nA)")
    ax[1].set_title("the IV curve"); ax[1].grid(alpha=.3)
    ax[1].axhline(0, color="grey", lw=.6); ax[1].axvline(0, color="grey", lw=.6)
    save(fig, "09_iv_sweep.png")

rig.close()
