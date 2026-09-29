# High-bias junction hold

Form a junction, pull it a little way open, then park it under a large DC
bias and record what the field does to it.

## The physics

A molecular (or atomic) junction that sits quietly at 100 mV can be a very
different object at 0.8 V. The electric field across a sub-nanometre gap at
that bias approaches 10^9 V/m: enough to drive electromigration of the
electrode atoms, to tilt the molecular levels toward resonance, to heat the
junction through inelastic current, and to switch or break weak bonds. This
mode measures **junction stability under high field**: each trace forms a
contact, retracts a fixed distance to select a junction geometry, then holds
the tip still while the bias steps from the 100 mV baseline up to the hold
value. The current record during the hold shows whether the junction sits,
telegraphs between states, drifts, or dies -- and the per-trace mean
conductance over the hold, printed as the run goes, is the crudest summary
of that. Short caps at the baseline bias on either side of the hold separate
"what the field did" from "what stepping the bias did".

The trajectory per trace (Igor's parameterisation: a hold's *length in nm*
means "as long as pulling that far would take"):

1. initial pull, 3 nm (`init_pull_nm`) at the 100 mV baseline,
2. cap, 0.1 nm (`cap_in_nm`), still at the baseline,
3. **hold**, 3 nm worth of time (`hold_nm`), bias at `hold_bias_v` (0.8 V),
4. cap, 0.1 nm (`cap_fin_nm`), back at the baseline,
5. final pull, 4 nm (`final_pull_nm`), breaking the junction for good.

### The Vzero link

The complement of the high-field hold is the *zero*-field hold. Zero applied
bias is not zero field: the amplifier chain has an input offset, so a small
current flows at a commanded 0 V. Igor's Voltage_Offset panel measured Vzero
-- the applied bias that actually nulls the current -- by sweeping +/-5 mV in
contact and fitting I(V) (`OffsetVoltage`, `Functions_STMBJ.ipf:920`). With
its VzeroCheckBox ticked, CreateInputs *replaced the hold bias with the
measured Vzero* (`Functions_STMBJ.ipf:1595-1599`), so the "high-bias" hold
became a true zero-current hold: the control experiment that separates
field-driven changes from the junction's own thermal drift. `--use-vzero`
reproduces this: after the first engage, `stmlab.vzero.measure_offset` runs
once, the result is logged, and every trace of the session holds at that
offset. (Expect the printed hold conductances to be noisy in this case --
the denominator is the near-zero measured junction voltage.)

## Igor origin

Translated from `igor_code/Functions_STMBJ.ipf`:

| Python                              | Igor function            | lines |
| ----------------------------------- | ------------------------ | ----- |
| `stmlab.ramps.build_hb_hold`        | `CreateInputs`, HB-hold branch | 1566-1599 |
| the Vzero substitution              | `CreateInputs` (VzeroCheckBox) | 1595-1599 |
| `stmlab.vzero.measure_offset`       | `OffsetVoltage`          | 920   |
| `stmlab.trace.capture` + this loop  | `MeasureBreakJunctions`  | 1664  |

Igor wrote the hold bias as `-HBBias` (line 1592) on top of the
`-(TipBias)/1000` baseline; `build_hb_hold` keeps both sign conventions,
including the `+TipBias` alignment spike at the very end of the wave
(line 1631) that lets `trace.capture` recover the AI/AO delay.

The default `hb_hold` numbers are Igor's own globals
(`Functions_STMBJ.ipf:117-123`): 3/4 nm pulls, 0.1 nm caps, 3 nm hold,
0.8 V hold bias.

## The bias limit

`limits.bias_max_v` defaults to 0.5 V and is a hard refusal, not a clamp --
it protects the constant-bias modes from typos. The whole point of this mode
is to exceed it, so the runner raises the limit to **1.1 x the hold bias**
before validating, with a loud `RAISING bias_max_v ...` warning in the log.
Nothing else in the session gets to use that headroom by accident: the
baseline bias and the spike stay at 100 mV.

## Hardware

- NI DAQ card (analog out: piezo Z + bias; analog in: bias monitor + preamp
  output).
- STM head with Z piezo, tip and substrate prepared for the junction of
  interest.
- Current preamplifier (gain in `cal.preamp_gain_v_per_a`) that tolerates
  the hold bias without railing (`limits.preamp_saturation_v`).
- Optional coarse-approach actuator for automatic headroom recovery.

No hardware is needed with `--simulate`: the simulated card synthesises
traces and the full pipeline, including the Vzero measurement, runs.

## Commands

From `python_code_entire_igor/` (use the venv python):

    # simulate, 5 traces
    .venv/Scripts/python.exe experiments/05_high_bias_hold/run_experiment.py --simulate -n 5 -o data/smoke05.h5

    # simulate, holding at the measured Vzero instead of 0.8 V
    .venv/Scripts/python.exe experiments/05_high_bias_hold/run_experiment.py --simulate -n 5 --use-vzero -o data/smoke05_vzero.h5

    # real rig: 200 holds at 0.9 V, 5 nm worth of hold time
    .venv/Scripts/python.exe experiments/05_high_bias_hold/run_experiment.py --config rig.json -n 200 --hold-bias 0.9 --hold-nm 5 -o data/hb_session.h5

Flags: `-n/--traces`, `-o/--out`, `--simulate`, `--config PATH`,
`--no-calibrate`, `-v/--verbose`, and the mode's own
`--hold-bias V` (G_HBBias), `--hold-nm NM` (G_HBHoldLength),
`--use-vzero` (Vzero replaces the hold bias).

Ctrl-C once finishes the current attempt and stops cleanly; twice exits
immediately.

## What is stored

One HDF5 file per session (`-o`, default `data/hb_hold_<timestamp>.h5`),
written by `stmlab.storage.SessionWriter`: the full `RigConfig` as JSON
(including the raised bias limit), and per accepted trace the raw measured
voltage and current records (volts), alignment delay, start piezo voltage,
and sample rate. Two file attributes are specific to this mode:

- `segments_json` -- `{name: [start, stop]}` sample indices into every cut
  trace: `init_pull`, `cap_in`, `hb_hold`, `cap_out`, `final_pull`. One map
  serves the whole file (the geometry is fixed; only the start voltage
  moves).
- `run_stats_json` -- attempts, acceptance, the hold bias actually applied
  (`hold_bias_v`), `vzero_mv` (null unless `--use-vzero`), and the session
  mean hold conductance.

All traces in one file have equal length -- one mode per file.

## Looking at the data

    import json, numpy as np
    from stmlab import analysis, storage
    from stmlab.config import RigConfig

    with storage.Session("data/hb_session.h5") as s:
        segs = json.loads(s._h5.attrs["segments_json"])
        a, b = segs["hb_hold"]
        v = s._h5["voltage_v"][0]          # trace 0, measured volts
        i = s._h5["current_v"][0]
        g = analysis.to_conductance(i, RigConfig().cal, voltage_v=v)
        hold = g[a:b]                      # conductance during the hold

Plot `hold` against time (`np.arange(a, b) / sample_rate_hz`) to see the
junction's life under field: a flat line is a stable junction, telegraph
noise is bistable switching, a decay to zero is field-driven breakdown. The
fraction of traces still conducting at the end of the hold, as a function of
`--hold-bias`, is the stability curve this experiment exists to measure.
