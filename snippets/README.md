# Snippets — run the code one piece at a time

Sixteen standalone scripts. Each prints what it found and explains it.
Full commentary is in **chapter 04** of the manual
(`../manual/04_snippets.md`, or the PDF).

Use the **project virtualenv**, not your system Python. Either of these
works — from the folder root, or from inside `snippets/`:

```bash
# from python_code_entire_igor/
./.venv/bin/python snippets/01_numbers.py

# from inside snippets/
../.venv/bin/python 01_numbers.py
```

On Windows swap `.venv/bin/python` for `.venv\Scripts\python`.

If `.venv` does not exist yet:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Plain `python snippets/...` uses your system interpreter, which almost
certainly lacks numpy. The snippets detect that and print the command to use
instead, rather than a traceback.

## Which snippet for which experiment

| Snippet | Covers | For experiment |
|---|---|---|
| `01_numbers.py` | config, the one equation, bias limits per mode | **all** |
| `02_ramps.py` | all five trajectories side by side | **01–05** |
| `03_safety.py` | every refusal, provoked deliberately | **all** |
| `04_engage.py` | approach, engage, the interlock | **all** |
| `05_one_trace.py` | one pull, volts → verdict | **01** |
| `06_histogram.py` | 200 traces, the 1 G₀ ruler | **01** |
| `07_storage.py` | write, read back, re-calibrate | **all** |
| `08_push_pull.py` | re-forming the junction, cycle by cycle | **02** |
| `09_iv_sweep.py` | the sweep, the caps, **the sign convention** | **03** |
| `10_ac_hold.py` | the sine, and **the sampling limit** | **04** |
| `11_high_bias_hold.py` | the hold, and the Vzero control | **05** |
| `12_keithley.py` | GPIB, `find_suppress`, series correction | support |
| `13_echem_cv.py` | the gate, the CV triangle, Igor's masking | **06** |
| `14_lateral_xpiezo.py` | X piezo range, withdraw-move-approach | **07** |
| `15_bias_series.py` | control repeats, the refusal, resume | **08** |
| `16_real_card.py` | **the lab PC only** — the real 4461 | bring-up |

## Order

First time through: **01 → 02 → 03 → 04 → 05 → 06**, about twenty minutes.
That is the whole instrument.

Before a specific experiment: its row above, plus 01 and 03.

Before touching hardware: 03, then 16 on the lab PC, then
`python -m stmlab.main bringup 1` through `5`.

## Notes

Snippets 01–15 need no hardware. 16 detects that `nidaqmx` is absent and
exits cleanly, so it is safe to run anywhere.

Plots are optional: matplotlib is used if installed, skipped if not. Figures
land in `snippets/figures/`.

Each snippet that uses the simulated card ends by saying what that simulation
does **not** model. They test the trajectory, the indices and the plumbing.
They cannot rehearse a result.

If a snippet fails, the one before it is where to look.
