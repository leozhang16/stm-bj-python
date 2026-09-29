"""SNIPPET 10 -- AC hold, and the sampling limit.  [experiment 04]

Drive the junction with a sine instead of a DC level. The last section is
the one to read: with the shipped defaults you CANNOT do harmonic analysis,
and any second-harmonic number you compute is an artefact.
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
cfg.limits.bias_max_v = 1.2
R, M, C = cfg.ramp, cfg.channels, cfg.cal
A = cfg.ac_hold

rig = Rig(cfg).open()
engage(rig)

rule("The trajectory")
ramp = ramps.build_ac_hold(cfg, rig.piezo_v)
print(f"  init {A.init_pull_nm} nm | cap {A.cap_nm} | HOLD {A.hold_nm} nm "
      f"worth with a {A.amp_v} V sine at {A.freq_khz} kHz | cap | "
      f"final {A.final_pull_nm} nm")
for seg, (a, b) in ramp.segments.items():
    print(f"    {seg:<14} {a:>6}-{b:<6}")

rule("The sine REPLACES the DC baseline; it is not added to it")
a, b = ramp.segments["ac_hold"]
hold_bias = ramp.waveform[M.ROW_BIAS][ramp.pre_pad + a:ramp.pre_pad + b]
before = ramp.waveform[M.ROW_BIAS][ramp.pre_pad + a - 10]
print(f"  just before the hold   {before:+.4f} V (the -100 mV baseline)")
print(f"  during the hold        {hold_bias.min():+.4f} to "
      f"{hold_bias.max():+.4f} V")
print(f"  mean during the hold   {hold_bias.mean():+.5f} V")
print("\n  So the junction spends the hold SYMMETRIC ABOUT ZERO, not about")
print("  -100 mV. That is Igor's behaviour and it changes the interpretation.")

rule("*** THE SAMPLING LIMIT -- read this before believing a number ***")
sps = R.sample_rate_hz / (A.freq_khz * 1000)
print(f"  sample rate   {R.sample_rate_hz:,.0f} Hz")
print(f"  drive         {A.freq_khz:.0f} kHz")
print(f"  -> {sps:.1f} SAMPLES PER CYCLE")
print(f"  -> Nyquist is {R.sample_rate_hz / 2 / 1000:.0f} kHz")
print(f"  -> the 2nd harmonic sits at {2 * A.freq_khz:.0f} kHz, which is "
      f"{'AT' if 2 * A.freq_khz * 1000 >= R.sample_rate_hz / 2 else 'below'}"
      f" Nyquist")
print("\n  Fundamental amplitude: measurable.")
print("  Harmonic analysis:     NOT POSSIBLE with these settings.")
print("\n  Fix it by slowing the drive or raising the rate:")
for f_khz in (1.0, 2.0, 5.0, 10.0):
    n = R.sample_rate_hz / (f_khz * 1000)
    verdict = "harmonics OK" if n >= 20 else \
        ("fundamental only" if n >= 4 else "ALIASED")
    print(f"    {f_khz:>5.1f} kHz -> {n:>5.1f} samples/cycle   {verdict}")
print("\n  This is a property of the SETTINGS, not a defect in the")
print("  translation -- Igor's defaults have it too.")

rule("Play it and count the cycles actually captured")
record = capture(rig, ramp)
if record is None:
    print("  alignment failed")
    rig.close()
    raise SystemExit(1)
v = C.voltage_input_sign * record.voltage_v[a:b]
crossings = np.nonzero(np.diff(np.sign(v - v.mean())) != 0)[0]
expected = (b - a) / R.sample_rate_hz * A.freq_khz * 1000
print(f"  hold is {(b - a) / R.sample_rate_hz * 1e3:.1f} ms")
print(f"  expected {expected:.0f} cycles, found {len(crossings) / 2:.0f} "
      f"zero-crossing pairs")

rule("What the simulator cannot tell you")
print("  The simulated junction's conductance depends on POSITION, not on")
print("  how fast the bias changes. So a simulated AC hold returns a clean")
print("  sine in current, exactly in phase, with no harmonics and no lag.")
print("  That tests the waveform, the segments and the storage. It says")
print("  nothing about a real junction's dynamics.")

if have_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n_show = int(6 * R.sample_rate_hz / (A.freq_khz * 1000))
    t = np.arange(n_show) / R.sample_rate_hz * 1e6
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(t, hold_bias[:n_show] * C.voltage_input_sign, "o-", ms=3, lw=1,
            label=f"commanded, {sps:.0f} samples/cycle")
    ax.set_xlabel("time into the hold (us)")
    ax.set_ylabel("junction bias (V)")
    ax.set_title(f"AC hold at {A.freq_khz:.0f} kHz -- "
                 f"only {sps:.0f} samples per cycle")
    ax.grid(alpha=.3); ax.legend(fontsize=8)
    save(fig, "10_ac_hold.png")

rig.close()
