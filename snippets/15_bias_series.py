"""SNIPPET 15 -- Igor's bias campaign, the refusal, and resume. [experiment 08]

Fourteen biases, 1000 traces each, unattended, overnight. The two things
worth understanding are the CONTROL REPEATS and the RESUME.

Nothing here touches hardware: it runs the plan, the refusal and the resume
logic against a temporary directory.
"""

# _common first, before numpy: it checks the interpreter has the
# dependencies and prints which one to use instead. Imported after
# numpy, a bare ModuleNotFoundError wins and says nothing useful.
from _common import ROOT, rule, sim_config

import importlib.util
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path

from stmlab import storage
from stmlab.safety import SafetyViolation

logging.basicConfig(level=logging.WARNING)

# The experiment scripts live in numbered folders, so load by path -- the
# same way tests/test_experiments.py does.
spec = importlib.util.spec_from_file_location(
    "_series", ROOT / "experiments" / "08_bias_series" / "run_experiment.py")
series = importlib.util.module_from_spec(spec)
sys.modules["_series"] = series
spec.loader.exec_module(series)

cfg = sim_config()

rule("Igor's list (Setup1_STMBJ.ipf:147-155)")
biases = series.IGOR_RUNGO_BIAS_MV
print("  step:  " + " ".join(f"{i:>5}" for i in range(len(biases))))
print("  mV:    " + " ".join(f"{mv:>5.0f}" for mv in biases))
print(f"\n  {series.IGOR_RUNGO_TRACES_PER_BIAS} traces each = "
      f"{len(biases) * series.IGOR_RUNGO_TRACES_PER_BIAS:,} traces total")

rule("*** THE CONTROL REPEATS ARE THE POINT ***")
for mv in sorted(set(biases)):
    where = [i for i, b in enumerate(biases) if b == mv]
    if len(where) > 1:
        print(f"  {mv:>+8.0f} mV appears at steps {where}")
print("""
  Those were put there BY HAND -- the list is built as (p+1)*(-100) and then
  five entries are overridden.

  14,000 traces takes many hours. The tip blunts, the sample drifts, the
  solvent evaporates, the lab warms up. If the -100 mV histogram from step
  13 does not match step 0, the series is not measuring bias dependence --
  IT IS MEASURING THE PASSAGE OF TIME, and every intermediate point is
  suspect.

  Analyse the controls FIRST. If they agree you have a bias series. If they
  do not, you have an equipment log.

  Worth copying into any campaign you design: a long unattended run needs a
  repeated point, and it needs to be at the END.""")

rule("The bias limit refuses, up front, for the whole list")
try:
    series.check_bias_limits(cfg, biases)
except SafetyViolation as exc:
    print("  SafetyViolation:\n    " + str(exc).replace("\n", "\n    "))
print("\n  Checked ONCE for the whole list, not per step. Finding out at")
print("  step 11 of 14 would mean eleven hours of acquisition followed by a")
print("  crash and a series with a hole in it.")
print("  The message says exactly what to type: that is what makes it a")
print("  checkpoint rather than an obstacle. Igor had no guard at all.")

cfg.limits.bias_max_v = 1.2
series.check_bias_limits(cfg, biases)
print(f"\n  with limits.bias_max_v = {cfg.limits.bias_max_v} V -> allowed")

rule("File naming keeps the repeats apart")
tmp = Path(tempfile.mkdtemp())
for i in (0, 9, 13):
    print(f"  step {i:>2} at -100 mV -> {series.step_path(tmp, i, -100.0).name}")
print("\n  The INDEX is in the name because the same bias appears more than")
print("  once and THE ORDER IS THE EXPERIMENT. A filename that collided")
print("  step 0 with step 13 would destroy the control comparison.")

rule("Run a short one, then break it and resume")
short = [-100.0, -500.0, -100.0]
out = tmp / "series"
series.run(cfg, out, short, n_traces=4, do_calibrate=False, resume=False,
           dry_run=False)
print(f"  files: {sorted(p.name for p in out.glob('*.h5'))}")

manifest = json.loads((out / "series_index.json").read_text())
print(f"  manifest: {[(s['index'], s['bias_mv'], s['traces']) for s in manifest['steps']]}")

for i, mv in enumerate(short):
    with storage.Session(series.step_path(out, i, mv)) as s:
        print(f"    step {i}: file's own cfg.ramp.bias_v = "
              f"{s.cfg.ramp.bias_v:+.3f} V, {len(s)} traces")
print("\n  Every file carries the bias it was taken at, in its own config.")

victim = series.step_path(out, 1, -500.0)
victim.unlink()
print(f"\n  deleted {victim.name}, simulating a crash. Now --resume:")
series.run(cfg, out, short, n_traces=4, do_calibrate=False, resume=True,
           dry_run=False)
print(f"  files back: {sorted(p.name for p in out.glob('*.h5'))}")

rule("Why an incomplete step is REDONE, not appended to")
print("""  A step whose file already holds its full complement is skipped.
  An incomplete one is re-run FROM SCRATCH, overwriting the partial file.

  Appending post-crash traces onto pre-crash ones would put two sessions --
  two preamp zeros, two tip states, possibly two days -- into one file
  carrying ONE calibration. Losing a partial step is cheaper than a file
  that lies about what it contains.""")

shutil.rmtree(tmp)
print(f"\n  (cleaned up {tmp})")
