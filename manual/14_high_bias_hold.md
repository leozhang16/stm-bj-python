# 14. High-bias hold

*Igor: `CreateInputs` HB-hold branch, `Functions_STMBJ.ipf:1566-1599`.
Experiment folder: `experiments/05_high_bias_hold/`. Builder:
`ramps.build_hb_hold`.*

## What it measures

Form a junction, retract a fixed distance to select a geometry, then **park
it under a large DC bias** and watch.

```
initial pull 3 nm      at the 100 mV baseline
cap 0.1 nm             baseline
hold 3 nm worth        bias = hold_bias_v (0.8 V default)
cap 0.1 nm             baseline
final pull 4 nm
```

A molecular junction that sits quietly at 100 mV can be a very different
object at 0.8 V. Across a sub-nanometre gap that is a field approaching
10⁹ V/m — enough to drive electromigration of the electrode atoms, tilt
molecular levels toward resonance, heat the junction through inelastic
current, and break weak bonds.

The current record during the hold shows whether the junction **sits**,
**telegraphs** between two states, **drifts**, or **dies**. Those four
behaviours are the result.

The short caps at the baseline on either side separate *what the field did*
from *what stepping the bias did* — the same logic as the IV caps in
chapter 12.

## The Vzero link — this is the interesting part

The complement of a high-field hold is a **zero-field** hold. And zero
applied bias is *not* zero field.

The amplifier chain has an input offset, so a small current flows at a
commanded 0 V. The bias that actually nulls the current is **Vzero**, and it
is not zero — it is a few millivolts, and it drifts.

Igor's Voltage_Offset panel measured it by sweeping ±5 mV in contact and
fitting `I(V)` (`OffsetVoltage`, `Functions_STMBJ.ipf:920`). With its
`VzeroCheckBox` ticked, `CreateInputs` **replaced the hold bias with the
measured Vzero** (lines 1595–1599).

That turns this experiment inside out. The "high-bias hold" becomes a true
**zero-current hold**: the control that separates field-driven changes from
the junction's own thermal drift. If a junction is unstable at 0.8 V *and*
equally unstable at Vzero, the field is not what is destroying it.

`--use-vzero` reproduces this: after the first engage, `vzero.measure_offset`
runs once, the result is logged, and every trace of the session holds at that
offset. See chapter 21.

> Expect the printed hold conductances to be **noisy** in this mode. The
> denominator is the near-zero measured junction voltage, and dividing by a
> number close to zero does what you would expect. The current record is the
> meaningful thing; the conductance column is not.

## Running it

```bash
python run.py 05 --simulate -n 20
python run.py 05 -n 200 --hold-bias 0.8
python run.py 05 -n 200 --use-vzero          # the control experiment
```

## The bias limit

0.8 V exceeds `SafetyLimits.bias_max_v` (0.5 V). The experiment raises it
deliberately and says so, the same pattern as chapters 12 and 17. If you want
a lower hold, `--hold-bias 0.4` needs no override at all.

## Status

Translated index-for-index with geometry tests, including the Vzero
substitution. Runs end to end on the simulator.

The **simulated junction does not degrade under field** — it has a tip that
blunts with hard contact, and nothing that responds to bias. So a simulated
high-bias hold shows a flat, stable junction every time. The four behaviours
this experiment exists to distinguish are all absent from the simulation by
construction. Simulate to check the trajectory; you cannot rehearse the
result.
