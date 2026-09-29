# 10. Constant bias

*The reference measurement. Igor: `MeasureBreakJunctions`,
`Functions_STMBJ.ipf:1664`. Experiment folder:
`experiments/01_constant_bias/`.*

This is the only path in this folder that has been validated against Igor's
own archived data, and everything else inherits its correctness. Read this
chapter before any of the mode chapters, because they are all variations on
its loop.

## What it measures

A gold tip is driven into a gold surface and withdrawn, thousands of times.
On each withdrawal the contact thins to a chain of atoms, then to a single
atom, then breaks. The single-atom gold contact conducts at almost exactly

```
G0 = 2e^2/h = 7.7480917346e-5 S = 1 / 12,906 ohm
```

If molecules are in solution, one sometimes bridges the gap as it opens,
holding a plateau three to five decades lower. Once the junction is fully
open, current decays about **one decade per angstrom**.

A single trace proves nothing — every junction breaks differently. The
measurement is the **histogram** of `log10(G/G0)` over hundreds or thousands
of accepted traces. Recurring configurations make peaks; noise does not.

## The loop

```
while accepted < target:
    if attempt % smash_every == 0:  smash(rig)      # recondition the tip
    engage(rig)                                     # break contact, close in
    trace = single_trace(rig)                       # play the ramp, capture
    verdict = select_trace(...)                     # accept or reject
    if verdict.accepted: writer.append(trace)
```

Four things happen per attempt, and each has a chapter's worth of reasoning
behind it. The short version:

**`engage`** breaks any existing contact *first*, then closes in at 0.5 nm
per step. The order is not cosmetic — approaching from an already-shorted
junction welds the tip to the sample.

**`single_trace`** plays a precomputed `(2, N)` waveform: the piezo row
descends 5 nm over 10,000 samples at 40 kHz, the bias row sits at −100 mV
with a 5 ms inverted spike near the end. Python does not time anything; the
card does.

**The spike** is read straight back on `ai0`. The lag between where it was
written and where it appears is the AI/AO group delay, measured **per trace**
so it is never assumed. A trace whose delay cannot be recovered, or comes
back implausible, is discarded rather than misaligned.

**`select_trace`** applies Igor's `TestTrace` criteria. This is the most
dangerous function in the package — see below.

## The 1 G0 ruler

The gold peak must land at `log10(G/G0) = 0.000`, because 1 G0 is a constant
of nature and not a property of your sample. That makes the histogram a
**self-check on the entire measurement chain**:

| Gold peak lands at | Diagnosis |
|---|---|
| `0.000 ± 0.05` | the analysis path is correct |
| off by exactly ±1.000 | a 10× error in preamp gain |
| off by ±0.301 | a factor of two in bias — or G0 defined as `e^2/h`, not `2e^2/h` |

`python run.py 01 --summarise <file>` prints these interpretations. Nothing
else in this folder gives you a check this strong, which is why the other
seven experiments are all judged against constant-bias data taken the same
day.

## Two Igor findings you inherit

**The engage threshold in Igor was unreachable.** `G_ConductanceThreshold = 5`
G0 would need 38.7 V at the ADC, but a ±10 V input at `Rf = 1e6` and 100 mV
saturates at 1.29 G0. Igor's approach loop could only ever have terminated
with the Keithley set to a lower gain than its own default. Here `engage_g0`
defaults to **0.5 G0**, contact is *also* detected by preamp saturation, and
`validate()` warns if the threshold is unreachable.

**Igor's "started in contact" criterion is switched off.** The check exists at
`Functions_STMBJ.ipf:1197` but its `else` branch is commented out, so a trace
that fails it falls through to `return 1` and is kept. `select_trace(
require_engaged=False)` is the default here, reproducing that exactly —
because matching archived Igor histograms is the validation milestone, and a
translation that silently "fixes" the original cannot be compared to it.

Pass `--require-engaged` for the stricter criterion. If you do: **say so in
the paper, and apply it identically to controls.** Selection is where this
measurement becomes unfalsifiable if you are careless, which is why all of it
lives in one function rather than being scattered through the acquisition
code where it would be invisible.

## Running it

```bash
python run.py 01 --simulate -n 200          # rehearse
python run.py 01 -n 1000 --coarse           # a real session
python run.py 01 --summarise data/run.h5    # where is the gold peak?
```

Ctrl-C once finishes the current attempt and stops cleanly; twice exits at
once. Outputs park at 0 V either way.

## What to watch during a run

The acceptance rate and the **rejection breakdown**. A rate that collapses
means the tip needs smashing; *which* reason dominates tells you why:

| Dominant rejection | Usually means |
|---|---|
| `end G >= break threshold` | the junction is not opening — tip too blunt, or drifted in |
| `only N points between 0.5 and 2.5 G0` | no gold plateau — the contact is not metallic |
| `end of trace is noisy` | mechanical or electrical noise; check the isolation |
| `alignment` | the spike is not being found — a timing problem, not a physics one |

The last one is different in kind from the others: it means the **instrument**
is misbehaving, not the junction. If it appears at all, stop and re-run
`bringup 2`.

## See also

* Chapter 01 for `play()` and the capture path
* Chapter 02 for every `RampConfig` field
* Chapter 30 for the numbers
* `../STMBJ_Python_Manual.pdf` — the 45-page deep story of this one experiment
