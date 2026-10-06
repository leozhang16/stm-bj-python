"""SNIPPET 01 -- The numbers, for every experiment.  [all experiments]

No hardware, no simulation. The config and the arithmetic that turns volts
at the ADC into conductance in units of G0.

If these numbers are wrong, every histogram this folder ever produces is
wrong in the same way, and no amount of good data fixes it.
"""

# _common first, before numpy: it checks the interpreter has the
# dependencies and prints which one to use instead. Imported after
# numpy, a bare ModuleNotFoundError wins and says nothing useful.
from _common import rule

from stmlab.config import G0_SIEMENS, RigConfig, validate

cfg = RigConfig()
C, R, L, M = cfg.cal, cfg.ramp, cfg.limits, cfg.channels

rule("The rig")
print(f"  device            {M.device} ({M.expected_product_type})")
print(f"  ao0 piezo         {M.path(M.ao_piezo)}")
print(f"  ao1 bias          {M.path(M.ao_bias)}")
print(f"  ai0 junction V    {M.path(M.ai_voltage)}")
print(f"  ai1 preamp out    {M.path(M.ai_current)}")
print(f"  second card       {M.low_res_device}   "
      f"<-- needed by experiments 06 and 07")

rule("The one equation")
print("    G/G0 = (V_ai1 - V_zero) / (Rf * V_junction * G0)")
print(f"\n  Rf = {C.preamp_gain_v_per_a:.3g} V/A, "
      f"G0 = {G0_SIEMENS:.6e} S, bias = {R.bias_v * 1e3:.0f} mV, "
      f"series R = {cfg.keithley.series_resistance_ohm:.0f} ohm\n")
print("  V_junction is MEASURED on ai0 every sample: the series resistor")
print("  takes most of the bias once the junction conducts, so the current")
print("  is capped at bias / R_series and the amplifier output is small.\n")
from stmlab.config import amplifier_volts, junction_volts
for g in (10.0, 5.0, 1.0, 0.5, 0.1, 1e-3, 10 ** -3.5, 5e-4, 1e-6):
    v = amplifier_volts(cfg, g)
    flag = "  <-- CLIPS" if v > M.ai_range_v else \
        ("  <-- preamp railed" if v > L.preamp_saturation_v else "")
    print(f"  {g:>10.3e} G0  ->  {v:>9.4f} V at ai1, "
          f"{junction_volts(cfg, g) * 1e3:7.2f} mV across the junction{flag}")
print(f"\n  the current can never exceed bias / R_series = "
      f"{R.bias_v / cfg.keithley.series_resistance_ohm * 1e6:.3f} uA, so at this")
print("  bias the amplifier never rails: contact is judged on the measured")
print("  junction voltage falling toward zero, not on a railed channel.")

rule("The two piezos")
print(f"  Z (ao0)   {C.piezo_nm_per_volt} nm/V, "
      f"{L.piezo_ao_min_v}-{L.piezo_ao_max_v} V unipolar, "
      f"{C.piezo_volts_to_nm(L.piezo_ao_max_v - L.piezo_ao_min_v):.0f} nm total")
print(f"            a {R.pull_length_nm} nm pull = "
      f"{C.nm_to_piezo_volts(R.pull_length_nm):.4f} V")
print(f"            a {R.approach_step_nm} nm step = "
      f"{C.nm_to_piezo_volts(R.approach_step_nm):.5f} V")
X = cfg.xpiezo
print(f"  X (ao0 on the 2nd card)  {X.nm_per_volt} nm/V, {X.min_v}-{X.max_v} V, "
      f"{(X.max_v - X.min_v) * X.nm_per_volt / 1000:.2f} um total")
print(f"            a 200 nm step = {200 / X.nm_per_volt:.4f} V")
print("  UNIPOLAR: 0 V is fully retracted. The pull ramp DESCENDS.")

rule("Which experiment needs the bias limit raised?")
print(f"  limits.bias_max_v = {L.bias_max_v} V\n")
rows = [
    ("01 constant bias", R.bias_v, "no"),
    ("02 push-pull", R.bias_v, "no"),
    ("07 lateral map", R.bias_v, "no"),
    ("03 IV sweep", cfg.iv.max_bias_v, "YES"),
    ("04 AC hold", cfg.ac_hold.amp_v, "YES"),
    ("05 high-bias hold", cfg.hb_hold.hold_bias_v, "YES"),
    ("08 bias series", 1.1, "YES -- refuses without --max-bias"),
]
for name, bias, need in rows:
    print(f"  {name:<20} {bias:>5.2f} V   {need}")

rule("Timing")
print(f"  sample rate       {R.sample_rate_hz:,.0f} Hz requested "
      f"(use what the card GRANTS)")
print(f"  a {R.pull_length_nm} nm pull      {R.seconds_per_pull * 1e3:.0f} ms, "
      f"{R.n_pull_samples} points")
print(f"  whole record      {R.n_record_samples} "
      f"({R.pre_pad_samples} pre + {R.n_pull_samples} + {R.post_pad_samples} post)")
print(f"  AC hold at {cfg.ac_hold.freq_khz:.0f} kHz -> "
      f"{R.sample_rate_hz / (cfg.ac_hold.freq_khz * 1000):.0f} samples per cycle")
print("    ^ four is enough for the fundamental, NOT for harmonics "
      "(see snippet 10)")

rule("validate(): the checks that run before any hardware is touched")
for w in validate(cfg):
    print(f"  warning: {w}\n")

rule("Break it on purpose")
bad = RigConfig()
bad.ramp.bias_v = 1.0
try:
    validate(bad)
except Exception as exc:
    print(f"  ConfigError: {exc}")
