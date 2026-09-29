"""SNIPPET 08 -- Push-pull: re-forming the same junction.  [experiment 02]

Constant bias breaks a junction once and throws it away. Push-pull re-forms
it, cycle after cycle, and the question is whether the SAME molecule
re-binds at the SAME conductance.

Comparing hold_in_0 with hold_in_1 and hold_in_2 IS the experiment.
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
cfg.push_pull.cycles = 3
R, M = cfg.ramp, cfg.channels

rig = Rig(cfg).open()
engage(rig)

rule("Build the trajectory")
ramp = ramps.build_push_pull(cfg, rig.piezo_v)
print(f"  {cfg.push_pull.cycles} cycles: initial pull "
      f"{cfg.push_pull.initial_pull_nm} nm, then per cycle "
      f"{{hold {cfg.push_pull.hold_nm}, push {cfg.push_pull.push_pull_nm}, "
      f"hold, pull}}, final {cfg.push_pull.final_pull_nm} nm")
print(f"  waveform {ramp.waveform.shape}, "
      f"{ramp.waveform.shape[1] / R.sample_rate_hz * 1e3:.0f} ms")
print(f"  piezo {ramp.start_piezo_v:.4f} -> {ramp.end_piezo_v:.4f} V\n")
for seg, (a, b) in ramp.segments.items():
    print(f"    {seg:<16} {a:>6}-{b:<6}")

rule("Play it through the SAME capture path as a constant-bias pull")
record = capture(rig, ramp)
if record is None:
    print("  alignment failed -- try again")
    rig.close()
    raise SystemExit(1)
print(f"  delay recovered from the spike: {record.delay_samples} samples")
print(f"  voltage_v {record.voltage_v.shape}, current_v {record.current_v.shape}")
print("\n  Note: TraceRecord.displacement_nm does NOT apply here -- it")
print("  assumes a constant pull rate. Use ramp.segments instead.")

rule("The measurement: conductance in each segment")
g0 = record.conductance_g0(cfg)
print(f"  {'segment':<16} {'mean G (G0)':>14} {'log10':>8}")
holds_in = []
for seg, (a, b) in ramp.segments.items():
    val = float(np.mean(np.abs(g0[a:b])))
    lg = np.log10(val) if val > 0 else float("nan")
    print(f"  {seg:<16} {val:>14.3e} {lg:>8.2f}")
    if "hold_in" in seg:
        holds_in.append((seg, val))

rule("THE constraint: the push must exceed the initial pull")
net = cfg.push_pull.push_pull_nm - cfg.push_pull.initial_pull_nm
print(f"  initial pull {cfg.push_pull.initial_pull_nm} nm, "
      f"push {cfg.push_pull.push_pull_nm} nm")
print(f"  -> each hold_in sits {net:+.2f} nm relative to the contact point")
print(f"  -> {'IN CONTACT, the junction re-forms' if net > 0 else 'STILL OPEN -- nothing re-forms'}")
print("\n  This folder shipped with initial_pull=3.0 and push=1.0, which puts")
print("  every hold 2 nm BELOW contact: experiment 02 recorded tunnelling for")
print("  every cycle and measured nothing. Defaults fixed; validate() now")
print("  warns. Try it:")
from stmlab.config import RigConfig, validate    # noqa: E402
broken = RigConfig()
broken.push_pull.initial_pull_nm = 3.0
broken.push_pull.push_pull_nm = 1.0
for w in validate(broken):
    if "push-pull" in w:
        print(f"    warning: {w}")

rule("Did the junction re-form the same way?")
if len(holds_in) > 1:
    vals = [v for _, v in holds_in]
    spread = np.log10(max(vals) / min(vals)) if min(vals) > 0 else float("nan")
    for seg, v in holds_in:
        print(f"  {seg:<16} {v:.3e} G0")
    print(f"\n  spread across cycles: {spread:.2f} decades")
    print("  A real re-binding molecule gives a small spread. A stray")
    print("  configuration does not come back at all.")

print("\n  CAUTION: the simulator re-rolls its molecule INDEPENDENTLY on")
print("  every break, so it has re-binding at the right rate but with NO")
print("  MEMORY. Cycle 3 knows nothing about cycle 1. Use this to check the")
print("  trajectory and the segment indices; not to predict your molecule.")

if have_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = np.arange(g0.size) / R.sample_rate_hz * 1e3
    fig, ax = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    piezo = ramp.waveform[M.ROW_PIEZO][ramp.pre_pad:ramp.pre_pad + ramp.n_pull]
    ax[0].plot(t, cfg.cal.piezo_volts_to_nm(piezo - ramp.start_piezo_v), lw=1)
    ax[0].set_ylabel("piezo (nm, rel.)")
    ax[0].set_title(f"Push-pull, {cfg.push_pull.cycles} cycles")
    with np.errstate(divide="ignore", invalid="ignore"):
        ax[1].semilogy(t, np.abs(g0), lw=.5)
    ax[1].axhline(1.0, color="goldenrod", ls="--", lw=1)
    ax[1].set_ylim(1e-7, 30)
    ax[1].set_ylabel("G / G0")
    ax[1].set_xlabel("time (ms)")
    for seg, (a, b) in ramp.segments.items():
        if "hold_in" in seg:
            for axis in ax:
                axis.axvspan(t[a], t[min(b, len(t) - 1)], alpha=.15,
                             color="seagreen")
    for axis in ax:
        axis.grid(alpha=.3)
    save(fig, "08_push_pull.png")

rig.close()
