# Bias series — Igor's scripted campaign

Acquire a full histogram at each of a list of biases, unattended, overnight,
and survive being interrupted halfway.

## The physics

A break-junction histogram at one bias tells you where the conductance peaks
are. The same histogram at a *series* of biases tells you how they move — and
that is where the physics is.

For a molecule in the off-resonant tunnelling regime, conductance is roughly
bias-independent at low bias: the peak sits at the same `log10(G/G0)` whether
you measure at 100 mV or 200 mV. When it stops being independent, something
happened. The peak shifts, splits, or vanishes as bias rises because:

* a molecular level is being pulled toward resonance by the applied field, so
  transmission rises faster than linearly — the onset of **resonant tunnelling**;
* the junction is heating and the molecule is desorbing or reorienting;
* at high enough field the molecule breaks, or the gold electrodes
  electromigrate, and you are no longer measuring the same object.

Distinguishing those is what the series is for, and it is why the **control
repeats** matter more than any individual point.

## The controls are the point

Igor's list, from `rungo` at `Setup1_STMBJ.ipf:147-155`:

```
step:   0    1    2    3    4    5    6    7    8    9   10    11    12   13
mV:  -100 -200 -300 -400 -500 -600 -700 -800 -900 -100 -900 -1000 -1100 -100
                                                   ^^^^      ^^^^        ^^^^
```

−100 mV appears at steps **0, 9 and 13**. −900 mV appears at steps 8 and 10.
That is not sloppiness — the list was overridden by hand to put them there.

Fourteen thousand traces takes many hours. Over that time the tip blunts, the
sample drifts, the solvent evaporates, the lab warms up. If the −100 mV
histogram from step 13 does not match the one from step 0, **the series is not
measuring bias dependence — it is measuring the passage of time**, and every
intermediate point is suspect.

So: analyse the controls first. If they agree, you have a bias series. If they
do not, you have an equipment log.

The run prints which steps are repeats when it finishes, so the comparison is
hard to forget.

## Igor origin

`Setup1_STMBJ.ipf:138-178`. Igor's loop, in full:

| Igor | Line | Here |
|---|---|---|
| `bias = (p+1)*(-100)`, then five overrides | 147–155 | `IGOR_RUNGO_BIAS_MV` |
| `counts_EachBias = 1000` | 145 | `-n`, default 1000 |
| `StopNumWave = (p+1)*counts + StartNum` | 156 | one file per step instead |
| `FindLevel/EDGE=1 /P StartNumWave, SavedNumber` | 163 | `--resume` |
| `TipBias = bias[i]` | 168 | `cfg.ramp.bias_v`, into every file |
| `StartMeasurement(" ")` | 173 | `trace.trace_loop` |
| `GetKeyState(0)` Alt-to-abort | 174 | Ctrl-C, finishing the current step |

## The bias limit is a deliberate obstacle

Igor's series reaches **1100 mV**. `SafetyLimits.bias_max_v` defaults to
500 mV, so this experiment **refuses to start** until you raise it:

```
$ python run.py 08 --dry-run
ERROR  this series reaches -1100, -1000, -900, -800, -700, -600 mV
       but limits.bias_max_v is 500 mV.
       Igor's rungo applied these with no guard. If you mean to,
       pass --max-bias 1.10 (volts).
       At 1.1 V a single-molecule junction can break, the electrodes
       can electromigrate, and any solvent present will do chemistry.
```

This is checked **once, up front, for the whole list** — not per step.
Discovering at step 11 of 14 that the limit blocks 1100 mV would mean eleven
hours of acquisition followed by a crash and a series with a hole in it.

Raising the limit should be something you did on purpose, in a command you can
find again in your shell history. Igor had no guard at all.

## Resume

Igor resumed by looking up how many traces were already saved and finding
which segment that count fell in. Runs died; this mattered.

Here `--resume` reads the output directory:

* a step whose file already holds its full complement is **skipped**;
* an incomplete one is **re-run from scratch**, overwriting the partial file.

The second is deliberate. Appending post-crash traces onto pre-crash ones
would put two sessions — two preamp zeros, two tip states, possibly two days —
into one file carrying one calibration. Losing a partial step is cheaper than
a file that lies about what it contains.

A `series_index.json` manifest is written beside the data so the campaign's
shape survives someone later moving or renaming the `.h5` files.

## Running it

```bash
# See the plan without touching anything
python run.py 08 --dry-run --max-bias 1.2

# Igor's full series: 14 steps x 1000 traces
python run.py 08 --max-bias 1.2

# Picked up after a crash
python run.py 08 --max-bias 1.2 --resume -o data/series_20260828_193000

# Your own list, gentler
python run.py 08 --bias-mv -100 -200 -300 -400 -n 500

# Rehearse the whole thing first
python run.py 08 --simulate --max-bias 1.2 --bias-mv -100 -500 -100 -n 20
```

Ctrl-C once finishes the current step and stops; re-run with `--resume`.
Ctrl-C twice exits immediately. Outputs are parked at 0 V either way.

## Per-step calibration

The preamp zero drifts with temperature, and fourteen hours is long enough to
matter. `measure_zero` runs at **every step**, not once per campaign, and the
result goes into that step's file. Pass `--no-calibrate` to skip it, and
accept that the low-conductance tail of the later steps sits on an offset
measured when the lab was a different temperature.

## What gets stored

One file per step, named `step_<NN>_<bias>mV.h5` — the index is in the name
because the same bias appears more than once and **the order is the
experiment**. Step 00 at −100 mV and step 13 at −100 mV are the control pair;
a filename that collided them would destroy the comparison the series exists
to make.

Each file is the standard trace schema plus `series_index`,
`series_bias_mv` and `series_length` attributes.

## Status

The loop, the plan, the refusal, and the resume are exercised end to end on the
simulator and covered by tests. What has never been done is **fourteen real
hours on a real tip** — and that, not the code, is where this experiment is
hard. Run it simulated once to see the shape, then run four steps at low bias
before you commit a night to it.
