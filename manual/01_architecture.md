# 01. Architecture

## The module stack

`stmlab/` is layered, and the layering is enforced by what each module is
allowed to import:

```
experiments/*/run_experiment.py    main.py    bringup.py
        |
        v
trace.py   approach.py   ramps.py   vzero.py       (the physics verbs)
echem.py   keithley.py   xpiezo.py
        |
        v
instrument.py                                      (Rig: tasks + tracked position)
        |
        v
daq.py        sim.py        calibrate.py           (the card, real or fake)
        |
        v
config.py   safety.py   storage.py   analysis.py   (foundations: no hardware)
```

* **Foundations.** `config.py` holds every constant as dataclasses (chapter
  02). `safety.py` holds the limits and interlocks and imports *only*
  `config` -- its own docstring says that if it ever needs `daq` or
  `instrument`, a check has drifted into the wrong layer. `analysis.py` and
  `storage.py` are pure functions of arrays and files; they run anywhere,
  which is how the analysis chain was validated against archived Igor data
  before any hardware existed.
* **The card.** `daq.py` is DAQmx and nothing else; `sim.py` is a drop-in
  replacement with the same `configure()`/`play()` surface that behaves like
  a break junction (group delay of 37 samples, noise floor, 1 G0 plateau,
  molecular plateau, degradable tip). `Rig.open()` picks one or the other
  from `cfg.simulate`, so nothing above this line knows which it got.
* **The instrument.** `instrument.Rig` owns the open tasks *and* the last
  commanded piezo voltage, because the two must live and die together (see
  the interlock below).
* **The physics verbs.** `trace.py` (one pull, many pulls), `approach.py`
  (engage, coarse approach, smash), `ramps.py` (the four mode trajectories),
  `vzero.py`, `keithley.py`, `echem.py`, `xpiezo.py`.
* **Orchestration.** `main.py` and the experiment runners: argparse,
  logging, `SafeSession`, and sentences about the experiment. If a line in
  them is about DAQmx, the abstraction has leaked.

## The one-verb play() model

The whole card is exposed through a single verb:
`play(waveform) -> record`, where `waveform` is `(2, N)` volts on the
outputs (row 0 the piezo command, row 1 the bias) and the return is `(2, N)`
volts on the inputs (row 0 the junction voltage on ai0, row 1 the preamp
output on ai1).

An approach step, a DC hold, a constant-bias pull, a push-pull cycle, an IV
sweep -- all are the same operation with different waveforms. This is not a
simplification imposed on the hardware; it is how the hardware behaves: every
AO start fires `ao/StartTrigger`, and AI is triggered off exactly that
terminal (`daq.py`), so every output automatically has a synchronised input
record. Igor did the same thing with `WriteToHighRes` followed by a read
(Functions_STMBJ.ipf:1153, 1347-1352); `Rig.hold()` is that pair.

Two consequences:

* **Python never times anything.** Trajectories are precomputed arrays; AO
  and AI run on the card's clock; loop overhead in Python lands *between*
  plays, never inside one.
* **Between plays the outputs hold their last sample.** The AO idle
  behaviour is set to `MAINTAIN_EXISTING_VALUE` (daq.py) -- deliberately
  different from the ZERO_VOLTS the project-architecture document specified,
  because the step-wise approach depends on the piezo holding position
  across dozens of separate plays. Bring-up step 3 verifies this on a real
  card.

## The tracked-piezo interlock

The most expensive accident on this rig is a coarse-actuator step taken while
the fine piezo is extended: one coarse step advances further than the piezo's
entire 10 V range, and taking it with the tip near the surface drives the tip
into the sample.

The guard is `safety.require_retracted` (safety.py:96): a coarse step is
refused unless the piezo is at or below `coarse_step_max_piezo_v` (0.1 V,
i.e. 6.2 nm of residual extension at 62 nm/V). There is **no position
sensor** -- the check trusts the last *commanded* piezo voltage, tracked by
`Rig`. That is why `Rig.play()` is the only path to the card from above the
instrument layer, and why it updates the tracker itself from the waveform's
final piezo sample rather than asking callers to remember: one direct
`task.write()` that bypasses it and the interlock becomes confidently wrong.
`Rig.coarse_step()` is in turn the only thing allowed to touch the actuator,
and it re-checks the interlock and the step budget (2000 steps) on every
single step, not just at the start of a loop.

## Clamp versus refuse

Out-of-range commands are handled asymmetrically, and the asymmetry is
deliberate (safety.py:42-69):

* **Piezo commands clamp, loudly.** A ramp that overshoots by a millivolt
  should be truncated, not aborted mid-pull -- so `clamp_piezo` clips into
  [0, 10] V and logs every time it fires. A clamp that fires repeatedly shows
  up in the session log instead of passing silently.
* **Bias refuses.** `check_bias` raises `SafetyViolation` above
  `limits.bias_max_v` (0.5 V by default). There is no case where you meant
  to apply more bias than the limit and would be happy with silently less:
  quietly reducing it produces data labelled with a bias that was never
  applied. Experiments that legitimately need more -- IV to 1 V, AC and HB
  holds to 0.8 V -- raise the limit deliberately, with a loud log line, in
  their own runner.
* **Geometry refuses before hardware is touched.** A pull that would
  descend through the piezo floor is refused by `check_pull_headroom`
  (safety.py:72), because on a unipolar piezo a clipped ramp produces a
  silently truncated trace that is indistinguishable from a junction that
  broke early. The mode builders in `ramps.py` extend this to **both**
  bounds: push-pull moves the tip *above* the contact point, so
  `_assemble` (ramps.py:90) refuses trajectories that would cross the 10 V
  ceiling as well -- a hazard Igor never guarded, since Igor only checked
  the retracted side.

`SafetyViolation` is never caught inside the package. `SafeSession` parks
every output at 0 V on entry, on normal exit, on exception, and on Ctrl-C;
0 V is fully retracted on this unipolar piezo and passes no current, so the
parked state is the safe state.

## Raw volts in, raw volts stored

Traces carry and store **raw volts at the ADC**, never conductance
(trace.py, storage.py). Conductance depends on three measured constants --
preamp gain, preamp zero, bias -- any of which can be revised after the
fact; baking them into stored data turns a calibration error into a lost
dataset instead of a re-analysis. The corollary is that the full `RigConfig`
travels as JSON in every HDF5 file's attributes, so the file is
self-describing six months later. `Session.conductance(i, cal=...)` accepts
a corrected calibration for exactly this reason. Every file holds traces of
equal length -- one mode, one geometry, per file.

## How ModeRamp + trace.capture generalise the validated path

The validated constant-bias path was:
`trace.build_ramp` (Igor's `CreateInputs`, constant branch,
Functions_STMBJ.ipf:1601) builds a `Ramp`; `trace.single_trace` plays it and
cuts the trace out of the record. The generalisation splits that in two:

* `trace.capture(rig, ramp, index, bias_v)` plays **any** prebuilt ramp --
  a `trace.Ramp` or a `ramps.ModeRamp`, anything with `waveform`,
  `pre_pad`, `n_pull`, `spike_front`, `start_piezo_v` -- recovers the AI/AO
  delay, applies the plausibility cut, and returns a `TraceRecord` (or
  `None`, meaning discard and retry). It is the single capture path for
  every experiment.
* `ramps.build_push_pull / build_iv / build_ac_hold / build_hb_hold`
  are pure functions `(cfg, start_piezo_v, mode_cfg=None,
  sample_rate_hz=None) -> ModeRamp`, translated index-for-index from
  `CreateInputs`' four GUI-selected branches (Functions_STMBJ.ipf:1461,
  1497, 1539, 1566). They share Igor's conventions exactly: lengths in
  nanometres converted at the pull rate (a 3 nm "hold" lasts as long as
  pulling 3 nm would), trajectories built relative to the contact point and
  shifted to `start_piezo_v`, bias in write-volts at ao1 with Igor's sign
  convention (baseline `-(TipBias/1000)`; the IV wave built positive then
  negated wholesale, Igor line 1533).

What `ModeRamp` adds over Igor is bookkeeping that survives the file:
`segments` maps names like `cycle0_push` or `iv_ramp` to `(start, stop)`
sample indices *within the pull*, and because `TraceRecord` is already cut
(pads and delay removed), those indices apply to the stored arrays directly.
`meta` carries the mode's own numbers (cycles, max bias, hold frequency).
The one caveat is documented in `capture`: `TraceRecord.displacement_nm`
assumes a constant pull rate and does not apply to mode ramps -- use
`segments` instead.

The pre/post pads (400 samples each) are also an addition to Igor: the
leading pad gives the 4461's decimation filter somewhere to settle that is
not the metallic-contact region, and the trailing pad keeps the alignment
spike inside the record after the group delay shifts it later.

## The alignment spike, identical in every mode

Every ramp -- constant pull and all four modes -- ends the same way: a short
spike written on the **bias** channel into `[front+1, back-1]` at
`+(TipBias/1000)` (the negation of the baseline), with the front edge 7.5 ms
and the back edge 2.5 ms before the end of the wave. That is Igor's own
construction, applied in every `CreateInputs` branch
(Functions_STMBJ.ipf:1618-1631), and `ramps._assemble` reproduces it for the
modes exactly as `trace.build_ramp` does for constant bias.

The spike is read straight back on ai0, and
`analysis.find_alignment_edge` locates its rising edge to sub-sample
precision. The lag between where the spike was written and where it appears
is the card's AI/AO group delay plus trigger skew -- tens of samples on the
4461 -- and measuring it **per trace** means it never has to be assumed and
survives a sample-rate change. `trace._measure_delay` then applies a
plausibility window (between -0.02 and +0.05 of a second's worth of
samples): a delay of the wrong order means the search locked onto noise, and
the trace is discarded rather than shifted by a thousand samples. Because
capture is one code path, this alignment -- including the discard-and-retry
behaviour -- is *identical* for a constant pull, a push-pull cycle, an IV
sweep, and a hold. A missing spike with a measured
`cal.group_delay_samples` falls back to that constant; with neither, the
trace is discarded.

One special case: `build_hb_hold` keeps the spike at `+TipBias/1000` even
though its hold runs at a different bias, and the Vzero-corrected constant
pull (`trace.build_ramp(bias_offset_v=...)`) applies the offset to the
baseline only, never to the spike -- both exactly as Igor did
(Functions_STMBJ.ipf:1609-1614, 1631), so the edge detector always sees the
same edge.
