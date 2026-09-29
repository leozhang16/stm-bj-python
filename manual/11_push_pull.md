# 11. Push-pull

*Igor: `CreateInputs` push-pull branch, `Functions_STMBJ.ipf:1461-1495`.
Experiment folder: `experiments/02_push_pull/`. Builder:
`ramps.build_push_pull`.*

## What it measures

Constant bias breaks a junction once and throws it away. Push-pull **re-forms
the same junction**, over and over, without ever fully separating the
electrodes.

The trajectory, per trace:

```
initial pull 3 nm
  then, per cycle:  hold 1 nm | push IN 1 nm | hold 1 nm | pull OUT 1 nm
  ... repeated `cycles` times ...
final pull 4 nm        -- breaks it for good
```

Bias stays at the DC baseline throughout; only the piezo moves.

The question it answers is **re-binding statistics**. When you pull a
molecular junction apart and push it back together, does the same molecule
re-bind? Does it bind in the same geometry, giving the same conductance? How
many cycles before it is lost?

That matters because the alternative explanations for a conductance plateau —
a molecule, a contamination, a gold point contact that happens to sit low —
behave completely differently under cycling. A real molecular junction can
re-form at the same conductance many times. A stray configuration does not
come back.

## Why the ceiling matters here and nowhere else

Every other mode only ever **retracts** from the contact point. Push-pull
moves the tip *above* it — that is what "push" means.

On a unipolar 0–10 V piezo, retracting is descending, so the hazard for every
other mode is the **floor** at 0 V. Igor guarded only that side, because for
four of its five branches that is the only side that exists.

`build_push_pull` refuses at **both** bounds. A push through the ceiling
would clip, and a clipped push is a push that did not happen: the trace would
show a hold where the code believes there was a re-contact, and the cycle
count would be a lie. Igor would have driven it into the rail silently.

This is one of the few places where this translation is deliberately stricter
than the original, and the reason is written at the point it happens in
`ramps.py`.

## Reading the segments

`ModeRamp.segments` maps names to `(start, stop)` sample indices *within the
pull*. `TraceRecord`'s arrays are already cut to the pull, so the indices
line up directly:

```python
ramp = ramps.build_push_pull(cfg, rig.piezo_v)
g0 = record.conductance_g0(cfg)
for name, (a, b) in ramp.segments.items():
    print(name, np.mean(g0[a:b]))
```

The segment names are `initial_pull`, `hold_out_<i>`, `push_<i>`,
`hold_in_<i>`, `pull_<i>` and `final_pull`. Comparing `hold_in_0` with
`hold_in_1` and `hold_in_2` **is** the experiment: three numbers that should
agree if the same molecule re-bound, and will not if it did not.

## Running it

```bash
python run.py 02 --simulate -n 50
python run.py 02 -n 500 --cycles 5
```

## What the simulator can and cannot tell you

The simulated junction re-rolls its molecule on **every break**, independently.
So a simulated push-pull run shows re-binding at the right *rate* but with no
memory: cycle 3 knows nothing about cycle 1.

Real re-binding is correlated — that correlation is the physics, and the
simulator does not have it. Use simulate to check that the trajectory is right
and the segments land where you think. Do not use it to predict what your
molecule will do.

## Status

The trajectory is an index-for-index translation of Igor's branch with
geometry tests. It has run end to end on the simulator. It has never pushed a
real tip back into a real surface.

The specific risk on hardware is the one the ceiling check exists for: if
`start_piezo_v` is high and `push_pull_nm` is large, the push has nowhere to
go, and you will find out from a refusal rather than a crash — provided the
piezo calibration is right. If `piezo_nm_per_volt` is wrong, the refusal
fires at the wrong place. Verify 62 nm/V before running this mode in anger.
