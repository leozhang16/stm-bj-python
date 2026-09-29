# 21. Vzero — the zero-current offset

*Igor: `OffsetVoltage` / `SaveOffset`, `Functions_STMBJ.ipf:920` / `:993`.
Module: `stmlab/vzero.py`.*

## The problem

**Zero applied bias is not zero current.**

An amplifier chain has an input offset. Command exactly 0 V and a small
current still flows through the junction. That offset is a few millivolts of
equivalent bias, and it **drifts** — with temperature, with the electrolyte,
with the age of the tip.

For a constant-bias run at 100 mV this is a small error. For anything that
cares about the zero — a low-bias measurement, a rectification study, the
zero-field control in chapter 14 — it is the whole experiment.

## The measurement

`measure_offset` is Igor's `OffsetVoltage`:

1. hold the tip **in contact** (`_ensure_contact`, Igor's `HighResContact`);
2. step the applied bias through ±`interval_mv` (±5 mV) in `2 * n_points`
   steps — Igor's ten;
3. re-check contact before **every** point, settle 50 ms after each bias
   change, read 5000 samples;
4. fit a straight line to current against bias.

From that line:

```
Izero = current at zero applied bias      (the intercept)
Vzero = -Izero / slope                    (the bias that nulls the current)
```

Igor fed Vzero back into the applied bias as `-(TipBias + Vzero)/1000`
(`CreateInputs`, line 1611).

**Why in contact?** The fit needs a measurable current at ±5 mV. Out of
contact, 5 mV across a tunnelling gap gives nothing to fit, and the slope
comes out as noise. In contact the junction is a few kΩ and the line is
clean. This is also why the routine restores your original bias afterwards
(Igor line 980) — it has been driving the junction at a bias you did not ask
for.

## The history is the diagnostic

`VzeroTracker` is Igor's `SaveOffset`: re-measure every
`every_n_traces = 50` accepted traces and **keep every result**.

The history matters more than any single value. A Vzero that drifts steadily
over a session is an early warning that the amplifier is drifting, the
junction chemistry is changing, or the temperature is not settled. Igor
plotted it — the Izero graph — for exactly that reason.

```python
tracker = vzero.VzeroTracker(cfg)
# inside the trace loop:
tracker.maybe_measure(rig, trace_number)
bias_offset = tracker.offset_v          # volts, add to the applied bias
```

`tracker.as_arrays()` returns flat `vzero_mv`, `izero_a` and `timestamp`
arrays, ready to write into an HDF5 file beside the traces. **Do write them.**
A session whose Vzero moved 3 mV is a session you want to know about six
months later, and the traces alone will not tell you.

## The cost

Each measurement is 10 bias points × (contact check + 50 ms settle + 5000
samples). At 40 kHz that is well over a second of acquisition plus the
settling, and it happens **in contact** — so the junction you were measuring
is gone afterwards and has to be re-formed.

`every_n_traces = 50` is Igor's compromise: often enough to catch drift,
rare enough not to dominate the run. Setting it to 1 would give you a
beautifully characterised offset and almost no data.

## Where it is used

| Chapter | Use |
|---|---|
| 14, high-bias hold | `--use-vzero` makes the hold bias *be* Vzero — the zero-field control experiment |
| any long run | periodic tracking, as a drift diagnostic |
| low-bias work | feed `offset_v` into the applied bias |

## Status

Exercised end to end on the simulator and covered by tests, including the
tracker's schedule. The simulated junction has **no amplifier offset**, so a
simulated Vzero comes out at essentially zero every time — which tests the
fit, the contact handling and the bookkeeping, and tells you nothing about
what your amplifier actually does.

This is one of the routines most worth running early on real hardware,
because its answer is a single number you can sanity-check against the preamp
zero from `bringup 4`. If `measure_zero` says the preamp sits at 300 µV and
Vzero says the nulling bias is 30 mV, one of the two is wrong.
