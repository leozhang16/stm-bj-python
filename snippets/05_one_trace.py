"""SNIPPET 05 -- One constant-bias pull, volts to verdict.  [experiment 01]

This is the whole experiment, once. Everything after this is repetition and
statistics.
"""

# _common first, before numpy: it checks the interpreter has the
# dependencies and prints which one to use instead. Imported after
# numpy, a bare ModuleNotFoundError wins and says nothing useful.
from _common import have_matplotlib, rule, save

import logging

import numpy as np

from stmlab import analysis
from stmlab.approach import engage
from stmlab.config import RigConfig
from stmlab.instrument import Rig
from stmlab.trace import single_trace

logging.basicConfig(level=logging.WARNING)

cfg = RigConfig()
cfg.simulate = True
R = cfg.ramp

rig = Rig(cfg).open()

rule("Find a junction, then pull it apart")
engage(rig)
print(f"  engaged at {rig.piezo_v:.4f} V")

# Pull until we get one that actually started in metallic contact. Not every
# attempt does -- and Igor ACCEPTED the ones that did not, because the
# "started engaged" branch of TestTrace is commented out in the Igor source.
trace = None
attempts = engaged_starts = 0
for attempts in range(1, 41):
    engage(rig)
    candidate = single_trace(rig, index=0)
    if candidate is None:
        continue
    started_at = float(np.mean(
        candidate.conductance_g0(cfg)[:len(candidate.voltage_v) // 200]))
    if started_at > R.engage_g0:
        engaged_starts += 1
        trace = candidate
        break
    trace = trace or candidate
print(f"  pulled {attempts} times; kept one that started at "
      f"{started_at:.3f} G0")
print("  Attempts that start BELOW engage_g0 are still accepted by")
print("  select_trace() -- that is Igor's behaviour, faithfully reproduced.")

rule("What a TraceRecord holds -- RAW VOLTS, never conductance")
print(f"  voltage_v         {trace.voltage_v.shape} float64, ai0")
print(f"  current_v         {trace.current_v.shape} float64, ai1")
print(f"  delay_samples     {trace.delay_samples}  <- recovered from ITS OWN spike")
print(f"  start_piezo_v     {trace.start_piezo_v:.4f} V")
print(f"  bias_v            {trace.bias_v} V")
print(f"  sample_rate_hz    {trace.sample_rate_hz:,.0f}")
print()
print("  Conductance is NOT stored. It depends on three measured constants")
print("  that may be revised; baking them in turns a calibration fix into a")
print("  lost dataset instead of a re-analysis.")

rule("Convert to physics")
g0 = trace.conductance_g0(cfg)
z = trace.displacement_nm(cfg)
print(f"  displacement      0 -> {z[-1]:.2f} nm over {len(z)} points")
print(f"  G at the start    {np.mean(g0[:50]):.3e} G0")
print(f"  G at the end      {np.mean(g0[int(len(g0) * .90):int(len(g0) * .91)]):.3e} G0")
print(f"  spans             {np.log10(abs(np.mean(g0[:50])) / abs(np.mean(g0[-500:]))):.1f} decades")

print("\n  a few points along the pull:")
print(f"  {'z (nm)':>8} {'G (G0)':>12} {'log10(G/G0)':>13}")
for frac in (0.0, 0.02, 0.05, 0.1, 0.2, 0.4, 0.6, 0.85):
    i = int(frac * (len(g0) - 1))
    val = float(np.mean(g0[i:i + 20]))
    lg = np.log10(abs(val)) if val > 0 else float("nan")
    print(f"  {z[i]:8.3f} {val:12.3e} {lg:13.2f}")

rule("select_trace(): the accept/reject decision, Igor's TestTrace")
verdict = analysis.select_trace(g0, R)
print(f"  accepted          {verdict.accepted}")
print(f"  reason            {verdict.reason}")
print(f"  end conductance   {verdict.end_conductance:.3e} G0  "
      f"(must be < break_g0 = {R.break_g0:g})")
print(f"  end deviation     {verdict.end_deviation:.3e}  (Igor's V_adev, NOT std)")
print(f"  start conductance {verdict.start_conductance:.3e} G0")
print(f"  plateau counts    {verdict.plateau_counts}  (points between 0.5 and 2.5 G0)")
print()
print("  Selection is where this measurement becomes unfalsifiable if you are")
print("  careless, which is why all of it lives in one function.")

if have_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].plot(z, trace.current_v * 1e3, lw=.6)
    ax[0].set_xlabel("displacement (nm)")
    ax[0].set_ylabel("ai1, preamp output (mV)")
    ax[0].set_title("what the ADC actually saw")
    ax[0].grid(alpha=.3)

    with np.errstate(divide="ignore", invalid="ignore"):
        ax[1].semilogy(z, np.abs(g0), lw=.6)
    ax[1].axhline(1.0, color="goldenrod", ls="--", lw=1, label="1 G0, gold")
    ax[1].axhline(10 ** -3.5, color="seagreen", ls="--", lw=1,
                  label="10^-3.5, molecule")
    ax[1].axhline(R.break_g0, color="crimson", ls=":", lw=1, label="break_g0")
    ax[1].set_ylim(1e-7, 30)
    ax[1].set_xlabel("displacement (nm)")
    ax[1].set_ylabel("G / G0")
    ax[1].set_title("the same trace as physics")
    ax[1].legend(fontsize=8)
    ax[1].grid(alpha=.3, which="both")
    save(fig, "05_one_trace.png")

rig.close()
