"""SNIPPET 13 -- The gate and cyclic voltammetry.  [experiment 06]

The counter electrode is the THIRD terminal: it shifts the molecule's energy
levels without touching the source-drain bias. This shows the gate, the CV
triangle, and Igor's cycle masking.
"""

# _common first, before numpy: it checks the interpreter has the
# dependencies and prints which one to use instead. Imported after
# numpy, a bare ModuleNotFoundError wins and says nothing useful.
from _common import have_matplotlib, rule, save, sim_config

import logging

import numpy as np

from stmlab import echem, storage
from stmlab.echem import EChemError

logging.basicConfig(level=logging.WARNING)

cfg = sim_config()
EC = cfg.echem

rule("The gate")
print("  In electrolyte the tip and substrate are two terminals and the")
print("  COUNTER ELECTRODE is a third. Changing the solution potential moves")
print("  the molecule's levels relative to the electrodes' Fermi level --")
print("  a gate, in the transistor sense.\n")
ce = echem.make_counter_electrode(cfg)
ce.on()
for mv in (-200.0, 0.0, +200.0):
    ce.set_mv(mv)
    print(f"  set_mv({mv:+7.1f})  ->  ao1 on the 2nd card = {mv / 1000:+.4f} V,"
          f"  cfg.echem.gate_mv = {cfg.echem.gate_mv:+.1f}")
print("\n  Igor saved the gate with every trace as ParameterWave[18]. Here it")
print("  lives in cfg.echem.gate_mv, which is serialised into every file.")

rule("Releasing the gate: two honest options")
ce.set_mv(-250.0)
ce.off(zero=False)
print(f"  off(zero=False) -> gate_mv still {ce.gate_mv:+.1f}; the card KEEPS")
print("    DRIVING the channel after the process exits. This is what Igor's")
print("    always-open task looked like to an operator -- and it leaves a")
print("    voltage on an electrode with nothing watching it.")
ce.on(); ce.set_mv(-250.0); ce.off(zero=True)
print(f"  off(zero=True)  -> gate_mv {ce.gate_mv:+.1f}, cfg.echem.gate_mv "
      f"{cfg.echem.gate_mv:+.1f}")
print("    Both are cleared -- a bug found while writing the manual: off()")
print("    used to clear the object but NOT the config, so files written")
print("    afterwards claimed a gate that was no longer applied.")

rule("Without a second card, the gate refuses")
one_card = sim_config()
one_card.channels.low_res_device = None
one_card.simulate = False           # force the real class
try:
    echem.CounterElectrode(one_card).on()
except EChemError as exc:
    print(f"  EChemError: {exc}")

rule("The CV triangle, and Igor's masking")
applied, keep = echem.build_cv_ramp_highres(EC)
print(f"  scan {EC.scan_rate_mv_per_s} mV/s, sampled at {EC.cv_rate_hz} Hz")
print(f"  peaks {EC.peak_one_v:+.2f} V and {EC.peak_two_v:+.2f} V")
print(f"  {applied.size} samples = {applied.size / EC.cv_rate_hz:.1f} s")
print(f"  range {applied.min():+.3f} to {applied.max():+.3f} V")
print(f"\n  keep: {int(keep.sum())} kept, {int((~keep).sum())} masked "
      f"({100 * (~keep).mean():.0f}%)")
edges = np.nonzero(np.diff(keep.astype(int)))[0]
print(f"  mask boundaries at samples {edges.tolist()}")
print("\n  Igor built 0 -> V1 -> 0 -> V2 -> 0, then repeated the first half")
print("  and NaN-ed the opening quarter and the repeat, so a saved cycle is")
print("  a STEADY-STATE loop with the switch-on transient gone.")
print("  Here the same choice is a boolean mask stored BESIDE the full")
print("  record, so a later reader can second-guess where the transient")
print("  ended. With NaNs they could not.")

rule("Low-res variant: 5000 samples of 0 V first")
lo_applied, lo_keep = echem.build_cv_ramp_lowres(EC)
print(f"  {lo_applied.size} samples vs {applied.size} for high-res")
print(f"  first 5000 samples all zero? {bool(np.all(lo_applied[:5000] == 0))}")
print("  high-res drives dev1/ao1 (the tip IS the working electrode) and")
print("  needs NO second card. Low-res drives the counter electrode and does.")

rule("Run it and store it")
cycles = echem.run_cv(cfg, kind="highres", cycles=2)
path = storage.save_cv_cycles(
    __import__("_common").OUT / "13_cv.h5", cfg, cycles, "highres")
with storage.CVSession(path) as cv:
    print(f"  {len(cv)} cycles, {cv.kind}, {cv.rate_hz:.0f} Hz")
    i_ua = cv.current_a(0) * 1e6
    print(f"  cycle 0 current {i_ua.min():+.4f} to {i_ua.max():+.4f} uA")
    print(f"  we_voltage_mv present? {cv.we_voltage_mv(0) is not None}")
print("\n  A CV file is NOT a trace file: no piezo axis, no alignment spike,")
print("  no verdict. It gets its own schema (record_kind='cv') and")
print("  CVSession refuses to open a trace file.")

if have_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    t = np.arange(applied.size) / EC.cv_rate_hz
    ax[0].plot(t, applied, lw=1)
    ax[0].plot(t[~keep], applied[~keep], lw=0, marker=".", ms=1,
               color="crimson", label="masked (Igor NaN-ed these)")
    ax[0].set_xlabel("time (s)"); ax[0].set_ylabel("applied (V)")
    ax[0].set_title("the CV ramp"); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3)
    for c in cycles:
        i = cfg.cal.volts_to_amps(c.tip_current_v) * 1e6
        ax[1].plot(c.applied_v[c.keep], i[c.keep], lw=.9,
                   label=f"cycle {c.cycle}")
    ax[1].set_xlabel("applied potential (V)"); ax[1].set_ylabel("current (uA)")
    ax[1].set_title("the voltammogram (simulated cell)")
    ax[1].axhline(0, color="grey", lw=.6); ax[1].grid(alpha=.3)
    ax[1].legend(fontsize=8)
    save(fig, "13_echem_cv.png")

rule("Status")
print("  echem.py has NEVER met an electrochemical cell. The simulated cell")
print("  is a 1 uF double layer plus one reversible couple near +0.2 V: the")
print("  right SHAPE to exercise the code, and no chemistry whatsoever.")
print("  Simulate. Then a dummy cell with a known resistor. Then electrolyte.")
