"""SNIPPET 11 -- High-bias hold, and the zero-field control.  [experiment 05]

Park a junction under a large DC bias and watch. Then do the SAME hold at
the measured zero-current bias (Vzero) -- that is the control that separates
field-driven changes from the junction's own drift.
"""

# _common first, before numpy: it checks the interpreter has the
# dependencies and prints which one to use instead. Imported after
# numpy, a bare ModuleNotFoundError wins and says nothing useful.
from _common import rule, sim_config

import logging

import numpy as np

from stmlab import ramps, vzero
from stmlab.approach import engage
from stmlab.instrument import Rig
from stmlab.trace import capture

logging.basicConfig(level=logging.WARNING)

cfg = sim_config()
cfg.limits.bias_max_v = 1.2
R, M, C, H = cfg.ramp, cfg.channels, cfg.cal, cfg.hb_hold

rig = Rig(cfg).open()
engage(rig)

rule("The trajectory")
ramp = ramps.build_hb_hold(cfg, rig.piezo_v)
print(f"  init {H.init_pull_nm} nm | cap {H.cap_in_nm} | "
      f"HOLD {H.hold_nm} nm worth at {H.hold_bias_v} V | "
      f"cap {H.cap_fin_nm} | final {H.final_pull_nm} nm")
for seg, (a, b) in ramp.segments.items():
    print(f"    {seg:<14} {a:>6}-{b:<6}")

a, b = ramp.segments["hb_hold"]
bias_row = ramp.waveform[M.ROW_BIAS]
print(f"\n  baseline outside the hold  {bias_row[ramp.pre_pad]:+.3f} V at ao1")
print(f"  during the hold            "
      f"{bias_row[ramp.pre_pad + a + 50]:+.3f} V at ao1")
print(f"  the junction therefore sees "
      f"{C.voltage_input_sign * bias_row[ramp.pre_pad + a + 50]:+.3f} V")

rule("The field across the gap")
gap_nm = 0.5
field = H.hold_bias_v / (gap_nm * 1e-9)
print(f"  {H.hold_bias_v} V across a {gap_nm} nm gap = {field:.2e} V/m")
print("  Enough to drive electromigration of the electrode atoms, tilt")
print("  molecular levels toward resonance, heat the junction through")
print("  inelastic current, and break weak bonds.")

rule("What the hold shows: sit / telegraph / drift / die")
record = capture(rig, ramp)
if record is None:
    print("  alignment failed")
    rig.close()
    raise SystemExit(1)
g0 = record.conductance_g0(cfg)
hold = np.abs(g0[a:b])
print(f"  hold lasts {(b - a) / R.sample_rate_hz * 1e3:.0f} ms, "
      f"{b - a} samples")
print(f"  mean   {np.nanmean(hold):.3e} G0")
print(f"  spread {np.nanstd(hold) / np.nanmean(hold) * 100:.1f} % of the mean")
print(f"  first tenth {np.nanmean(hold[:len(hold)//10]):.3e} -> "
      f"last tenth {np.nanmean(hold[-len(hold)//10:]):.3e} G0")
print("\n  Those four numbers are the result. The SIMULATED junction does not")
print("  degrade under field -- it has no bias-dependent behaviour at all --")
print("  so it always reads 'sits'. You cannot rehearse this one.")

rule("The zero-field control: --use-vzero")
print("  Zero APPLIED bias is not zero current: the amplifier chain has an")
print("  input offset. Vzero is the bias that actually nulls the current.")
print("  Igor's VzeroCheckBox replaced the hold bias with it (lines 1595-99),")
print("  turning the high-bias hold into a TRUE ZERO-CURRENT HOLD.\n")

result = vzero.measure_offset(rig)
print(f"  measured Vzero = {result.vzero_mv:+.4f} mV "
      f"(Izero = {result.izero_a:+.3e} A)")

engage(rig)
zero_ramp = ramps.build_hb_hold(cfg, rig.piezo_v, vzero_mv=result.vzero_mv)
za, zb = zero_ramp.segments["hb_hold"]
print(f"  hold bias with Vzero: "
      f"{zero_ramp.waveform[M.ROW_BIAS][zero_ramp.pre_pad + za + 50]:+.5f} V "
      f"at ao1")
print(f"  meta.from_vzero = {zero_ramp.meta['from_vzero']}")
print("\n  If a junction is unstable at 0.8 V AND equally unstable at Vzero,")
print("  the field is not what is destroying it. That is the whole point.")
print("\n  Expect NOISY hold conductances in this mode: the denominator is")
print("  the near-zero measured junction voltage. The CURRENT record is the")
print("  meaningful thing; the conductance column is not.")
print("\n  The simulator has no amplifier offset, so Vzero comes out at")
print("  essentially zero here. On hardware it is a few mV, and it drifts.")

rig.close()
