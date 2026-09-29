"""SNIPPET 06 -- Many pulls. The histogram IS the measurement.  [experiment 01]

A single trace proves nothing: junction geometry is different every time.
What survives averaging over hundreds of traces is what recurs, and noise
does not recur.

Takes about a minute for 200 traces on the simulator.
"""

# _common first, before numpy: it checks the interpreter has the
# dependencies and prints which one to use instead. Imported after
# numpy, a bare ModuleNotFoundError wins and says nothing useful.
from _common import have_matplotlib, rule, save

import logging
import time

import numpy as np

from stmlab import analysis
from stmlab.approach import recover_headroom
from stmlab.config import RigConfig
from stmlab.instrument import Rig
from stmlab.trace import trace_loop

logging.basicConfig(level=logging.WARNING)

N = 200

cfg = RigConfig()
cfg.simulate = True
rig = Rig(cfg).open()
recover_headroom(rig)

rule(f"Acquiring {N} accepted traces")
kept = []
t0 = time.time()
stats = trace_loop(rig, n=N,
                   on_trace=lambda i, tr, sel: kept.append(tr.conductance_g0(cfg)))
print(f"  {stats['accepted']} accepted / {stats['attempts']} attempts "
      f"({stats['acceptance_rate']:.0%}) in {time.time() - t0:.1f} s")
print("  rejections:")
for reason, count in sorted(stats["rejections"].items(), key=lambda kv: -kv[1]):
    print(f"    {count:5d}  {reason}")
if not stats["rejections"]:
    print("    (none)")
rig.close()

rule("log_histogram(): Igor's LogHistFromBlocks, step by step")
print("""  per trace:
    1. keep the first 95% of points  (drops the alignment spike)
    2. box-smooth, width 11          (Igor's Smooth/B 11)
    3. estimate the residual current floor from the 95-96% window
    4. subtract it, smooth again, take log10, accumulate

  Step 4's condition is a QUALITY GATE, not just an offset correction: a
  trace whose floor sits above zero_cutoff never entered a clean tunnelling
  regime and is dropped from the histogram entirely.""")

centres, counts = analysis.log_histogram(kept)
print(f"\n  {len(centres)} bins from {centres[0]:.3f} to {centres[-1]:.3f} decades")
print(f"  bin width {centres[1] - centres[0]:.4f} decades")
print("  counts are PER TRACE, as Igor reported them")

rule("Where are the peaks?")
gold = analysis.peak_position(centres, counts, around=0.0, window=0.5)
mol = analysis.peak_position(centres, counts, around=-3.5, window=0.8)
print(f"  1 G0 gold peak         {gold:+.4f} decades   "
      f"({'within' if abs(gold) < 0.05 else 'OUTSIDE'} 0.05 of zero)")
print(f"  molecular peak         {mol:+.4f} decades   "
      f"(simulator truth: {rig._session.molecule_log_g0:+.2f})")
print()
print("  THIS IS THE ACCEPTANCE TEST for the whole analysis path. The gold")
print("  peak has to land at 0.000 because 1 G0 is a constant of nature, not")
print("  a property of your sample. If it does not:")
print("     off by +/-1.000 decade  -> a 10x error in preamp gain")
print("     off by +/-0.301 decade  -> a factor of 2 in bias, or someone")
print("                                defining G0 as e^2/h not 2e^2/h")

rule("Prove it: corrupt the gain by 10x and watch the peak move")
# Same raw volts, a preamp gain ten times too small -> every conductance 10x.
kept_raw_bad = [g * 10.0 for g in kept]
c2, n2 = analysis.log_histogram(kept_raw_bad)
print(f"  gold peak with the wrong gain: "
      f"{analysis.peak_position(c2, n2, around=1.0, window=0.5):+.4f} decades")
print("  exactly +1.000 away. That is what a gain error looks like.")

if have_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))

    for tr in kept[:40]:
        with np.errstate(divide="ignore", invalid="ignore"):
            ax[0].semilogy(np.arange(tr.size) * cfg.ramp.pull_rate_nm_per_s
                           / cfg.ramp.sample_rate_hz, np.abs(tr), lw=.3,
                           alpha=.35, color="steelblue")
    ax[0].set_ylim(1e-7, 30)
    ax[0].set_xlim(0, 2)
    ax[0].axhline(1.0, color="goldenrod", ls="--", lw=1)
    ax[0].axhline(10 ** -3.5, color="seagreen", ls="--", lw=1)
    ax[0].set_xlabel("displacement (nm)")
    ax[0].set_ylabel("G / G0")
    ax[0].set_title(f"{min(40, len(kept))} individual traces")
    ax[0].grid(alpha=.3, which="both")

    ax[1].plot(centres, counts, lw=1.1, color="darkslateblue")
    ax[1].axvline(0.0, color="goldenrod", ls="--", lw=1, label="1 G0")
    ax[1].axvline(-3.5, color="seagreen", ls="--", lw=1, label="molecule")
    ax[1].set_xlim(-6, 0.6)
    ax[1].set_xlabel("log10(G / G0)")
    ax[1].set_ylabel("counts per trace")
    ax[1].set_title(f"1-D histogram, {len(kept)} traces")
    ax[1].legend(fontsize=8)
    ax[1].grid(alpha=.3)
    save(fig, "06_histogram.png")
