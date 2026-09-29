"""SNIPPET 02 -- All five trajectories, side by side.  [experiments 01-05]

This is the central idea of the whole package: constant pull, push-pull, IV
sweep, AC hold and high-bias hold are all just DIFFERENT (2, N) ARRAYS OF
VOLTS. Same play(), same capture, same alignment spike, same storage.

A mode is a waveform plus a `segments` dict saying where its pieces are.
"""

# _common first, before numpy: it checks the interpreter has the
# dependencies and prints which one to use instead. Imported after
# numpy, a bare ModuleNotFoundError wins and says nothing useful.
from _common import have_matplotlib, rule, save, sim_config

import numpy as np

from stmlab import ramps
from stmlab.trace import build_ramp

cfg = sim_config()
M, R, C = cfg.channels, cfg.ramp, cfg.cal
START = 6.0        # pretend contact was made at 6 V = 372 nm

# Three of the five modes exceed the 0.5 V bias limit, and build_*() REFUSES
# rather than clamping -- try commenting this line out and watch snippet 02
# stop at the IV sweep with a SafetyViolation. That refusal is the point: a
# quietly reduced bias produces a file labelled with a voltage never applied.
# Each experiment script raises the limit itself, deliberately and out loud.
cfg.limits.bias_max_v = 1.2

builders = [
    ("01 constant bias", lambda: build_ramp(cfg, START)),
    ("02 push-pull", lambda: ramps.build_push_pull(cfg, START)),
    ("03 IV sweep", lambda: ramps.build_iv(cfg, START)),
    ("04 AC hold", lambda: ramps.build_ac_hold(cfg, START)),
    ("05 high-bias hold", lambda: ramps.build_hb_hold(cfg, START)),
]

rule("Every mode is the same kind of object")
print(f"  {'mode':<20} {'shape':>12} {'ms':>7} {'piezo start->end':>22}")
built = []
for name, make in builders:
    r = make()
    built.append((name, r))
    ms = r.waveform.shape[1] / R.sample_rate_hz * 1e3
    print(f"  {name:<20} {str(r.waveform.shape):>12} {ms:>7.0f} "
          f"{r.start_piezo_v:>10.4f} -> {r.end_piezo_v:.4f} V")

print("\n  Row 0 is ALWAYS the piezo command at ao0.")
print("  Row 1 is ALWAYS the bias at ao1.")
print("  Nothing downstream needs to know which mode built it.")

rule("Where the pieces are: ModeRamp.segments")
for name, r in built[1:]:
    print(f"\n  {name}")
    for seg, (a, b) in r.segments.items():
        print(f"    {seg:<16} samples {a:>6}-{b:<6} "
              f"({(b - a) / R.sample_rate_hz * 1e3:6.1f} ms)")

print("\n  These indices are WITHIN THE PULL. TraceRecord's arrays are")
print("  already cut to the pull, so they line up directly:")
print("      g0 = record.conductance_g0(cfg)")
print("      a, b = ramp.segments['hold']")
print("      mean_during_hold = g0[a:b].mean()")

rule("Every mode carries the same alignment spike")
for name, r in built:
    bias = r.waveform[M.ROW_BIAS]
    spike_v = bias[r.spike_front + 5]
    print(f"  {name:<20} spike at sample {r.spike_front:>6}, "
          f"{spike_v:+.3f} V (baseline {bias[0]:+.3f} V)")
print("\n  That is why capture() can recover the AI/AO delay for a")
print("  push-pull trace exactly as it does for a constant-bias pull.")

rule("Three modes needed the bias limit raised to even BUILD")
print(f"  limits.bias_max_v raised to {cfg.limits.bias_max_v} V at the top of")
print("  this snippet. Without it, build_iv/build_ac_hold/build_hb_hold raise")
print("  SafetyViolation -- they refuse, they do not clamp:")
from stmlab.safety import SafetyViolation      # noqa: E402
strict = sim_config()
for name, fn in (("03 IV sweep", ramps.build_iv),
                 ("04 AC hold", ramps.build_ac_hold),
                 ("05 high-bias hold", ramps.build_hb_hold)):
    try:
        fn(strict, START)
        print(f"  {name:<20} built (no override needed)")
    except SafetyViolation as exc:
        print(f"  {name:<20} REFUSED: {exc}")

rule("The piezo never leaves 0-10 V in any mode")
for name, r in built:
    row = r.waveform[M.ROW_PIEZO]
    ok = row.min() >= cfg.limits.piezo_ao_min_v and \
        row.max() <= cfg.limits.piezo_ao_max_v
    print(f"  {name:<20} {row.min():.4f} to {row.max():.4f} V   "
          f"{'OK' if ok else 'OUT OF RANGE'}")
pp = built[1][1].waveform[M.ROW_PIEZO]
print(f"\n  With the DEFAULT push-pull settings (pull {cfg.push_pull.initial_pull_nm} nm "
      f"first, then push {cfg.push_pull.push_pull_nm} nm)")
print(f"  the trajectory never gets back above the contact point: max "
      f"{pp.max():.4f} V vs start {START:.4f} V.")
print("\n  But push-pull is the only mode that moves the piezo UPWARD at all,")
print("  so it is the only one that can reach the CEILING. Push further than")
print("  you pulled and it does:")

deep = sim_config()
deep.limits.bias_max_v = 1.2
deep.push_pull.initial_pull_nm = 1.0
deep.push_pull.push_pull_nm = 40.0        # push far past the contact point
try:
    r = ramps.build_push_pull(deep, 9.9)   # start near the 10 V ceiling
    print(f"    built, max {r.waveform[M.ROW_PIEZO].max():.4f} V")
except SafetyViolation as exc:
    print(f"    REFUSED: {exc}")
print("\n  Igor guarded only the floor -- for four of its five branches that")
print("  is the only side that exists. A clipped push is a push that did not")
print("  happen, and the cycle count would be a lie. See snippet 03.")

if have_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(5, 2, figsize=(12, 11), sharex="col")
    for row, (name, r) in enumerate(built):
        t = np.arange(r.waveform.shape[1]) / R.sample_rate_hz * 1e3
        axes[row][0].plot(t, r.waveform[M.ROW_PIEZO], lw=1, color="steelblue")
        axes[row][0].set_ylabel(f"{name}\nao0 (V)", fontsize=8)
        axes[row][1].plot(t, r.waveform[M.ROW_BIAS], lw=1, color="crimson")
        axes[row][1].set_ylabel("ao1 (V)", fontsize=8)
        for ax in axes[row]:
            ax.grid(alpha=.3)
            ax.tick_params(labelsize=7)
    axes[0][0].set_title("piezo command")
    axes[0][1].set_title("bias command")
    axes[-1][0].set_xlabel("time (ms)")
    axes[-1][1].set_xlabel("time (ms)")
    fig.tight_layout()
    save(fig, "02_ramps.png")
