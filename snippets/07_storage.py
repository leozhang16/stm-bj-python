"""SNIPPET 07 -- Writing a session, and re-analysing it later.  [all experiments]

The file holds raw volts and the complete config. That is the whole design:
a preamp gain you re-measure next month reprocesses today's files instead of
invalidating them.
"""

# _common first, before numpy: it checks the interpreter has the
# dependencies and prints which one to use instead. Imported after
# numpy, a bare ModuleNotFoundError wins and says nothing useful.
from _common import OUT, ROOT, rule

import logging

import numpy as np

from stmlab import analysis, storage
from stmlab.approach import recover_headroom
from stmlab.config import RigConfig
from stmlab.instrument import Rig
from stmlab.trace import trace_loop

logging.basicConfig(level=logging.WARNING)

PATH = OUT / "demo_session.h5"

cfg = RigConfig()
cfg.simulate = True
cfg.notes = "snippet 7 demo, simulated card"

rule(f"Acquire 60 traces straight into {PATH.relative_to(ROOT)}")
rig = Rig(cfg).open()
recover_headroom(rig)
with storage.SessionWriter(PATH, cfg) as writer:
    stats = trace_loop(rig, n=60, on_trace=writer.append)
    writer.write_summary(stats)
rig.close()
print(f"  {stats['accepted']} traces, file is "
      f"{PATH.stat().st_size / 1e6:.2f} MB on disk")
print("  (traces are appended and flushed as they arrive -- a crash at trace")
print("   59 costs one trace, not the session)")

rule("What is inside")
import h5py
with h5py.File(PATH, "r") as f:
    print("  datasets:")
    for name, ds in f.items():
        print(f"    {name:<24} {str(ds.shape):<16} {ds.dtype}")
    print("\n  attributes:")
    for k in f.attrs:
        v = str(f.attrs[k])
        print(f"    {k:<24} {v[:60]}{'...' if len(v) > 60 else ''}")

rule("Read it back")
with storage.Session(PATH) as s:
    print(f"  {len(s)} traces")
    print(f"  config travelled with the data: bias = {s.cfg.ramp.bias_v} V, "
          f"Rf = {s.cfg.cal.preamp_gain_v_per_a:.3g} V/A")
    print(f"  notes: {s.cfg.notes!r}")
    volts_v, volts_i = s.raw(0)
    print(f"  raw trace 0: ai0 {volts_v.shape}, ai1 {volts_i.shape}, "
          f"ai1 range {volts_i.min() * 1e3:+.2f} to {volts_i.max() * 1e3:+.2f} mV")

    centres, counts = analysis.log_histogram(s.conductances())
    peak_as_stored = analysis.peak_position(centres, counts)
    print(f"\n  gold peak with the stored calibration: {peak_as_stored:+.4f}")

rule("Now re-measure the preamp gain and reprocess the SAME file")
with storage.Session(PATH) as s:
    cal = s.cfg.cal
    cal.preamp_gain_v_per_a = 9.87e5        # what a resistor check told you
    centres, counts = analysis.log_histogram(s.conductances(cal=cal))
    peak_revised = analysis.peak_position(centres, counts)
print("  Rf 1.000e6 -> 9.870e5 V/A")
print(f"  gold peak moved {peak_as_stored:+.4f} -> {peak_revised:+.4f} "
      f"({peak_revised - peak_as_stored:+.4f} decades)")
print(f"  expected shift: log10(1.000e6 / 9.87e5) = "
      f"{np.log10(1e6 / 9.87e5):+.4f}")
print()
print("  Nothing was re-acquired. Had the file stored conductance instead of")
print("  volts, this correction would have required rerunning the experiment.")

rule("Tidy up")
PATH.unlink()
print(f"  deleted {PATH.name}")
