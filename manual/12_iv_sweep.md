# 12. IV sweep

*Igor: `CreateInputs` IV branch, `Functions_STMBJ.ipf:1497-1537`. Experiment
folder: `experiments/03_iv_sweep/`. Builder: `ramps.build_iv`. Analysis:
`experiments/03_iv_sweep/iv_analysis.py`.*

## What it measures

Everything else in this folder measures conductance at **one** bias.
An IV sweep holds a junction still and sweeps the bias in a triangle,
recording current the whole way. One curve per junction.

```
initial pull 3 nm      at the DC baseline
cap 0.5 nm             baseline, lets the junction settle
IV ramp 2 nm worth     0 -> +max -> -max -> 0, up to 1 V
cap 0.5 nm             baseline again
final pull 4 nm        breaks the junction
```

The shape of `I(V)` is the physics:

* **Linear** through the origin — off-resonant tunnelling, the junction is a
  simple resistor over this range. The slope is the conductance you would
  have measured at constant bias.
* **Sigmoidal / S-shaped** — a molecular level is approaching resonance. The
  bias at which it turns over locates that level relative to the Fermi energy,
  which is a number a constant-bias histogram cannot give you at all.
* **Asymmetric** — the molecule couples more strongly to one electrode than
  the other. Real, common, and interesting.
* **Steps or spikes** — the junction changed *during* the sweep. Discard;
  it is not one junction's IV curve.

## The caps are not padding

The 0.5 nm caps either side of the sweep hold the junction at the baseline
bias, still, before and after the ramp. They exist so you can separate
"what the bias sweep did" from "what holding the junction did".

If the conductance in the leading cap differs from the trailing cap, the
junction changed over the course of the sweep — and the IV curve is a
composite of two different objects, not a measurement of one. The analysis
checks this.

## Igor's sign convention, faithfully reproduced

Igor built the IV ramp **positive** and then negated the entire wave
(`*= -1`, line 1533). Combined with the baseline already being
`-(TipBias/1000)`, this means the sweep runs **negative first** by default.

That wholesale negation is what makes the **default sweep drive `ao1`
negative first**. `G_IVSignFlag` (line 1535) negates the ramp segment a
second time, sending `ao1` positive first.

**Be careful which side of the sign convention you are talking about.**
`Calibration.voltage_input_sign` is also −1, so the *junction* sees the
opposite of what `ao1` does:

| | first quarter of the sweep |
|---|---|
| written to `ao1` | **negative** |
| seen by the junction | **positive** |

Both statements are true and they are opposites. `iv_analysis.py` reports
`v_junction`, so its first quarter runs 0 → +1.0 V with the default settings.
If you compare a Python IV curve against an Igor one and they look mirrored,
this is the first place to look — before suspecting the molecule.

> **This field was renamed during this work.** It arrived called
> `negative_first`, which was backwards: setting it True made the sweep go
> *positive* first, and the CLI help and the run's log line both said the
> opposite of what the card was doing. It is now `IVConfig.positive_first` /
> `--positive-first`, named for what it does. If you have a config JSON
> written before this change, the old key is ignored with a warning —
> check it.

There are tests for both directions, because a sign error here does not
crash. It silently mirrors every IV curve you take, and an asymmetric
junction measured backwards looks like a different molecule.

## Running it

```bash
python run.py 03 --simulate -n 10 --plot
python run.py 03 -n 200 --max-bias 1.0
```

`iv_analysis.py` extracts, per curve: the zero-bias conductance from a linear
fit near the origin, the cap-to-cap conductance drift, and a symmetry ratio.

## The bias limit

`IVConfig.max_bias_v` defaults to 1.0 V, which is above
`SafetyLimits.bias_max_v` (0.5 V). The experiment raises the limit only when
you ask it to, the same way experiment 08 does — see chapter 17 for why that
obstacle exists.

## Status

Translated index-for-index with geometry tests; runs end to end on the
simulator. The simulated junction has a **linear** `I(V)`, so simulated
curves will always fit a straight line. That is enough to test the sweep
geometry, the caps, the segment indices and the analysis plumbing, and tells
you nothing about what a real molecule will do.
