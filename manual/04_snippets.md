# 04. The snippets

*Folder: `snippets/`. Sixteen runnable scripts. Fifteen need no hardware.*

Reading code tells you what it does. Running it tells you what it *means*.
Each snippet prints what it found, explains it, and where useful draws it.

```bash
cd python_code_entire_igor
./.venv/bin/python snippets/01_numbers.py
```

**Use the project virtualenv, not your system Python.** The snippets need
numpy (and h5py for 07); a system interpreter almost certainly has neither.
On Windows the interpreter is `.venv\Scripts\python`. If `.venv` is missing:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

**Any working directory is fine.** Each snippet puts the package on
`sys.path` itself and writes figures to an absolute path, so
`../.venv/bin/python 01_numbers.py` from inside `snippets/` works exactly as
well as running from the folder root.

Run one with the wrong interpreter and it prints a single absolute command to
use instead — copy the whole line, and it works from wherever you are.

## Which snippet for which experiment

**This is the table to use.** About to run experiment 04? Read snippets 01,
02, 04 and 10.

| Snippet | | Covers | Experiments |
|---|---|---|---|
| `01_numbers.py` | the numbers | config, the one equation, which mode needs the bias limit raised | **all** |
| `02_ramps.py` | the waveforms | all five trajectories side by side, segments, the shared spike | **01–05** |
| `03_safety.py` | the refusals | all seven, provoked deliberately | **all** |
| `04_engage.py` | approach | break contact, close in, the interlock | **all** |
| `05_one_trace.py` | one pull | volts → conductance → verdict | **01** |
| `06_histogram.py` | the measurement | 200 traces, the 1 G₀ ruler, a deliberate gain error | **01** |
| `07_storage.py` | the file | write, read back, re-calibrate without re-acquiring | **all** |
| `08_push_pull.py` | re-forming | segments per cycle, and the push/pull constraint | **02** |
| `09_iv_sweep.py` | spectroscopy | the sweep, the caps, **the sign convention** | **03** |
| `10_ac_hold.py` | the sine | the hold, and **the sampling limit** | **04** |
| `11_high_bias_hold.py` | the field | the hold, and the Vzero zero-field control | **05** |
| `12_keithley.py` | the amplifier | GPIB commands, `find_suppress`, series correction | support |
| `13_echem_cv.py` | the third terminal | the gate, the CV triangle, Igor's masking | **06** |
| `14_lateral_xpiezo.py` | the lateral axis | X piezo range, and the withdraw-move-approach order | **07** |
| `15_bias_series.py` | the campaign | control repeats, the refusal, resume after a crash | **08** |
| `16_real_card.py` | **the lab PC** | the real 4461 — the only untested code | bring-up |

## Suggested order

**First time through:** 01 → 02 → 03 → 04 → 05 → 06. That is the whole
instrument: the numbers, the waveforms, the refusals, getting into contact,
one trace, and the measurement. About twenty minutes.

**Before running a specific experiment:** its row above, plus 01 and 03.

**Before touching hardware:** 03, then 16 on the lab PC, then the packaged
bring-up steps.

## Four that are worth your time even if you skip the rest

!FIG[02_ramps.png]{Snippet 02: all five trajectories. Left column is the piezo command at ao0, right column the bias at ao1. Every one is a (2, N) array of volts played through the same play().}

**`02_ramps.py`** shows the central idea: constant pull, push-pull, IV sweep
and both holds are all just different `(2, N)` arrays of volts, played through
the same `play()`, captured by the same code, aligned by the same spike. Once
that lands, the whole package is one experiment with five waveforms.

**`06_histogram.py`** puts the gold peak at +0.02 decades, then deliberately
corrupts the preamp gain by 10× and shows the peak move to +1.02 — exactly one
decade. That is your calibration self-check, demonstrated.

!FIG[06_histogram.png]{Snippet 06: 200 simulated traces, and their histogram. The gold peak lands at +0.02 decades because 1 G0 is a constant of nature.}

**`09_iv_sweep.py`** shows that `ao1` and the junction see **opposite**
polarity. Both statements are true and they are opposites. This is the single
easiest way to publish a mirrored IV curve.

**`10_ac_hold.py`** shows that at 40 kHz sampling and a 10 kHz drive you have
**four samples per cycle** — enough for the fundamental, not enough for any
harmonic. Read it before you believe a second-harmonic number.

## What the simulator cannot tell you

Every snippet that uses the simulated card says so at the end, and says what
that particular simulation does *not* model:

| Snippet | The simulator has no… |
|---|---|
| 08 push-pull | memory between breaks — cycle 3 knows nothing about cycle 1 |
| 09 IV | non-linearity — its `I(V)` is a straight line, always |
| 10 AC hold | frequency response — no harmonics, no phase lag |
| 11 HB hold | field-driven degradation — the junction always just sits |
| 13 EChem | chemistry — a capacitor and one Gaussian bump |
| 14 lateral | variation with X — every site is identical |

They test the trajectory, the segment indices, the plumbing and the storage.
They cannot rehearse a result.

## Figures

Snippets 02, 05, 06, 08, 09, 10 and 13 write PNGs to `snippets/figures/` when
matplotlib is installed, and skip them cleanly when it is not. Nothing else
depends on matplotlib, so the lab PC does not need it.

## Things the snippets found

These were not planted. Writing snippets that print real numbers is how they
turned up:

* **push-pull never re-formed the junction.** The shipped defaults pulled
  3 nm and pushed 1 nm, leaving every hold 2 nm *below* contact. Experiment 02
  recorded tunnelling for every cycle and measured nothing. Defaults fixed;
  `validate()` now warns. See snippet 08.
* **the IV sign flag was inverted.** `negative_first=True` swept *positive*
  first, and the CLI help and log line both said the opposite of what the card
  was doing. Renamed to `positive_first`. See snippet 09.
* **the gate survived being switched off.** `CounterElectrode.off()` cleared
  its own state but not `cfg.echem.gate_mv`, so files written afterwards
  claimed a gate no longer applied. See snippet 13.
* **nothing connected the amplifier's gain to the arithmetic's gain.**
  `keithley.gain_exponent` programs the box; `cal.preamp_gain_v_per_a` is what
  every conductance divides by. `validate()` now checks they agree. See
  snippet 12.
