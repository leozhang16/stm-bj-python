# IV sweep at a held junction

Current-voltage characteristics of a single-molecule (or tunnelling)
junction: instead of pulling at constant bias, the pull is paused partway
and the bias is swept in a triangle while the piezo holds still.

## The physics

A constant-bias trace gives one number per junction -- its conductance at
100 mV. An IV gives the whole transport curve: pull the tip
`iv.init_pull_nm` (default 3 nm) out of metallic contact so the junction is
in the tunnelling/molecular regime, hold the piezo, let the junction sit at
the DC baseline for a cap (default 0.5 nm worth of time, 25 ms), then sweep
the junction voltage 0 -> +1 V -> -1 V -> 0 (default apex 1 V; the first,
downward flank of the triangle takes the first quarter of the window, the
+max -> -max flank the middle half, the return the last quarter). A second
cap lets it settle back to DC, and a final pull (default 4 nm) breaks the
junction for good. A linear IV is ohmic tunnelling; sub-linear/super-linear
curvature, asymmetry between polarities, and steps in dI/dV are molecular
level structure. Many junctions are measured, because each one's geometry
differs.

## WARNING: gain and clipping

The current preamp gain is 1e6 V/A (`cal.preamp_gain_v_per_a`) and the ADC
input rails near 10 V (`limits.preamp_saturation_v` = 9.5 V), so **any
current above roughly 10 uA clips**. At the 1 V apex that is only ~10 uS,
i.e. **0.13 G0**: a junction still in metallic contact (1 G0 = 77.5 uS)
rails the preamp for the whole sweep and the "IV" is a square wave of the
rail voltage. IVs from this rig are therefore only meaningful in the
tunnelling/molecular regime -- exactly what the initial pull is for. The
runner flags railed sweeps in the log and counts them as `clipped_traces`
in the summary; treat those traces as "junction was too conductive", not as
data. If you genuinely need the high-conductance region, lower the preamp
gain (Keithley `SetGain`) and the recorded config with it.

Note also that the default sweep apex (1 V) exceeds the everyday software
bias limit (0.5 V). The runner raises `limits.bias_max_v` to
`1.1 * iv.max_bias_v` itself and logs the change at WARNING level -- that
line in the log is deliberate, not a fault.

## Igor origin

Translated from `igor_code/Functions_STMBJ.ipf`:

| Python                              | Igor                                | lines |
| ----------------------------------- | ----------------------------------- | ----- |
| `stmlab.ramps.build_iv`             | `CreateInputs`, IV branch           | 1497-1537 |
| `cfg.iv` defaults                   | `G_IVMaxBias` ... `G_IVSignFlag`    | 99-105 |
| acquisition loop (this runner)      | `MeasureBreakJunctions`             | 1664 |
| `stmlab.trace.capture` (alignment)  | `GenerateTrace` + spike, line 1631  | 284 |
| `iv_analysis.split_quarters`        | `BiasIndex1..4`                     | 1521-1524 |

Igor forced `BiasSave=1` and `CurrentSaveCheck=1` for this mode (lines
1498-1499) because an IV is useless without both records; this package
always stores the raw measured voltage and current, so there is nothing to
force. Igor negated the whole bias wave after building it ("to have normal
convention", line 1533) and `G_IVSignFlag` flipped the sweep back to positive first
(line 1535); both conventions are reproduced exactly, so archived Igor
sweeps and these files have the same sign meaning. Igor had no IV analysis
in the acquisition code -- `iv_analysis.py` (quarter splitting by the
stored boundaries, smoothed dI/dV) is new.

## Hardware

- NI PXI-4461 (piezo Z on ao0, junction bias on ao1, junction voltage on
  ai0, preamp output on ai1). Single card is enough.
- STM head with Z piezo, tip and substrate; molecules if you want molecular
  IVs.
- Current preamplifier, gain recorded in `cal.preamp_gain_v_per_a`.

No hardware is needed with `--simulate`: the simulated card plays the real
waveform and the whole pipeline runs, including `iv_analysis`.

## Commands

From `python_code_entire_igor/` (use the venv python):

    # simulate: 5 sweeps into a scratch file, with a quick-look plot
    .venv/Scripts/python.exe experiments/03_iv_sweep/run_experiment.py --simulate -n 5 -o data/smoke03.h5 --plot

    # real rig: 100 sweeps to +/-0.8 V, negative flank first
    .venv/Scripts/python.exe experiments/03_iv_sweep/run_experiment.py --config rig.json -n 100 --max-bias 0.8 --positive-first -o data/iv_session.h5

    # equivalently, via the dispatcher
    python run.py iv_sweep --simulate -n 5

Flags: `-n/--traces`, `-o/--out`, `--simulate`, `--config PATH`,
`--no-calibrate`, `-v/--verbose`, `--plot`, and the sweep geometry
overrides `--max-bias` (V), `--ramp-nm`, `--cap-nm`, `--positive-first`
(all mapped onto `cfg.iv`; lengths are nm *at the pull rate*, so they set
durations -- the piezo does not move during the sweep). Ctrl-C once
finishes the current trace and stops cleanly; twice exits immediately.

## What is stored

One HDF5 file per session, written by `stmlab.storage.SessionWriter`: the
full `RigConfig` as JSON, and per trace the raw voltage and current records
(volts at the ADC, covering the entire pull-cap-sweep-cap-pull trajectory),
the alignment delay, start piezo voltage, DC bias, and sample rate. The
run summary (`run_stats_json` attribute) additionally holds the `segments`
map (`init_pull`, `cap_in`, `iv_ramp`, `cap_out`, `final_pull` as sample
index pairs into each trace), the `quarters` boundaries of the bias
triangle, `max_bias_v`, `positive_first`, and the `clipped_traces` count.
All traces in the file have equal length.

## Looking at the data

    # print one sweep's span, quarters and median dI/dV per quarter
    .venv/Scripts/python.exe experiments/03_iv_sweep/iv_analysis.py data/iv_session.h5 0 --plot

or programmatically:

    import iv_analysis                    # from experiments/03_iv_sweep/
    from stmlab import storage
    with storage.Session("data/iv_session.h5") as s:
        sweep = iv_analysis.extract(s, 0)
        V, I = sweep.v_junction, sweep.i_amps          # volts, amps
        Vq1, Iq1 = sweep.quarter("q1")                 # first flank
        # dI/dV vs V (siemens; NaN gaps at the triangle apexes)
        v_axis, didv = sweep.didv_v, sweep.didv_s

`extract` cuts the `iv_ramp` window using the summary's segment map,
applies `V = cal.voltage_input_sign * voltage_v` and
`I = cal.volts_to_amps(current_v)` with the calibration stored *in that
file*, and splits quarters from the stored boundaries (falling back to the
sign of dV/dt of the measured voltage for files without a summary).
