# 17. Bias series

*Igor: `rungo`, `Setup1_STMBJ.ipf:138-178`. Experiment folder:
`experiments/08_bias_series/`.*

## What it measures

A histogram at one bias locates the conductance peaks. A histogram at a
*series* of biases shows how they **move** — and that is where the physics is.

For a molecule in the off-resonant tunnelling regime, conductance is roughly
bias-independent at low bias. When it stops being independent, something
happened:

* a molecular level is being pulled toward resonance by the applied field, so
  transmission rises faster than linearly — the onset of **resonant
  tunnelling**;
* the junction is heating and the molecule is desorbing or reorienting;
* at high enough field the molecule breaks, or the gold electrodes
  electromigrate, and you are no longer measuring the same object.

Telling those apart is what the series is for.

## The control repeats are the point

Igor's list, built at lines 147–155 and then overridden by hand:

```
step:   0    1    2    3    4    5    6    7    8    9   10    11    12   13
mV:  -100 -200 -300 -400 -500 -600 -700 -800 -900 -100 -900 -1000 -1100 -100
                                                   ^^^^      ^^^^        ^^^^
```

−100 mV appears at steps **0, 9 and 13**; −900 mV at steps **8 and 10**.
Those repeats were put there deliberately.

Fourteen thousand traces takes many hours. Over that time the tip blunts, the
sample drifts, the solvent evaporates, the lab warms up. **If the −100 mV
histogram from step 13 does not match the one from step 0, the series is not
measuring bias dependence — it is measuring the passage of time**, and every
intermediate point is suspect.

So analyse the controls first. If they agree, you have a bias series. If they
do not, you have an equipment log. The run prints which steps are repeats when
it finishes, so the comparison is hard to forget.

This is the single most important idea in this chapter, and it is worth
copying into any campaign you design yourself: **a long unattended run needs a
repeated point, and it needs to be at the end.**

## The bias limit is a deliberate obstacle

Igor's series reaches **1100 mV**. `SafetyLimits.bias_max_v` defaults to
500 mV, so this experiment **refuses to start**:

```
ERROR  this series reaches -1100, -1000, -900, -800, -700, -600 mV
       but limits.bias_max_v is 500 mV.
       Igor's rungo applied these with no guard. If you mean to,
       pass --max-bias 1.10 (volts).
       At 1.1 V a single-molecule junction can break, the electrodes
       can electromigrate, and any solvent present will do chemistry.
```

Two design points:

**It is checked once, up front, for the whole list** — not per step.
Discovering at step 11 of 14 that the limit blocks 1100 mV would mean eleven
hours of acquisition followed by a crash, and a series with a hole in it.

**The message says exactly what to type.** A refusal that does not tell you
how to proceed is an obstacle; one that does is a checkpoint. Raising the
limit should be something you did on purpose, in a command you can find again
in your shell history. Igor had no guard at all.

## Resume

Igor resumed with `FindLevel/EDGE=1 /P StartNumWave, SavedNumber` (line 163):
look up how many traces are saved, find which segment that falls in, start
there. Runs died; this mattered.

`--resume` here reads the output directory:

* a step whose file already holds its full complement is **skipped**;
* an incomplete one is **re-run from scratch**, overwriting the partial file.

The second is the deliberate part. Appending post-crash traces onto pre-crash
ones would put two sessions — two preamp zeros, two tip states, possibly two
days — into one file carrying **one** calibration. Losing a partial step is
cheaper than a file that lies about what it contains.

A `series_index.json` manifest is written beside the data, so the campaign's
shape survives someone later moving or renaming the `.h5` files.

## Per-step calibration

The preamp zero drifts with temperature and fourteen hours is long enough to
matter, so `measure_zero` runs at **every step** and the result goes into that
step's file. `--no-calibrate` skips it; then the low-conductance tail of the
later steps sits on an offset measured when the lab was a different
temperature.

## File naming

`step_<NN>_<bias>mV.h5`. **The index is in the name because the same bias
appears more than once and the order is the experiment.** Step 00 at −100 mV
and step 13 at −100 mV are the control pair; a filename that collided them
would destroy the comparison the series exists to make.

## Running it

```bash
python run.py 08 --dry-run --max-bias 1.2          # see the plan, touch nothing
python run.py 08 --max-bias 1.2                    # Igor's full series
python run.py 08 --max-bias 1.2 --resume -o data/series_20260828_193000
python run.py 08 --bias-mv -100 -200 -300 -n 500   # your own, gentler
python run.py 08 --simulate --max-bias 1.2 -n 20   # rehearse
```

Ctrl-C once finishes the current step; re-run with `--resume`. Twice exits at
once.

## Status

The loop, the plan, the refusal and the resume are exercised end to end on the
simulator and covered by tests, including a deliberately corrupted file (which
must read as incomplete) and a resume that must not touch already-complete
steps.

What has never been done is **fourteen real hours on a real tip** — and that,
not the code, is where this experiment is hard. Run it simulated once to see
the shape, then four steps at low bias, before you commit a night to it.
