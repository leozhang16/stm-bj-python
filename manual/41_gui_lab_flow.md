# 41. The lab flow, button by button

*Igor: `StartHighResWritingTask`, `ApproachButton`, `FindOffset`, `FindSuppress`, `StartMeasurement`, `MakeAttempt`, `StopWritingTasks` in Controls_STMBJ.ipf; `MeasureBreakJunctions`, Functions_STMBJ.ipf:1664. Module: `stmgui/controller.py`.*

This is the sequence you used in Igor, in the order you used it. Nothing
about the order has changed; what follows is what each press does now, what
you should see, and what to do when you do not see it. Every step is a
method on `stmgui.controller.RigController`; every method runs on the
controller's single worker thread, one at a time, in the order clicked
(chapter 48 explains why that matters).

## 1. Start Writing

**Igor:** `StartHighResWritingTask`, Controls_STMBJ.ipf:127. Created the
output task `G_OD1` with two channels — the piezo at
`G_PiezoOffset_nm / K_ZPiezoScale` volts and the bias at `-TipBias/1000` —
and started it.

**Now:** `RigController.start_writing`. In order:

1. `stmlab.config.validate(cfg)` runs; every warning goes to the History
   prefixed `config:`. On a fresh install you will see `hv_amp_gain is
   unknown` and, before any calibration, `current_zero_v is 0`. Both are
   informational. A fatal problem (bias above `limits.bias_max_v`, a pull
   longer than the piezo range) raises `ConfigError` and nothing opens.
2. On hardware, `safety.verify_devices` (the card is present and is the
   expected product type) and `safety.park_all_outputs` (both outputs to
   0 V through a throw-away task). In simulate, neither.
3. `Rig(cfg).open()` — the AO/AI tasks, the actuator, and the tracked piezo
   position set to the park value.
4. One DC hold at **Piezo offset (nm)** and **Tip Bias**: Igor's
   `HighResWriteWave`.
5. Session calibration — `stmlab.calibrate.session_calibration`: the
   preamp zero with the bias at 0 V, and the AI/AO group delay from twenty
   alignment spikes. Igor never did this; `validate()` warns when it has
   not been done, so it is done here, once per launch, while the tip is
   still retracted. Turn it off with `GuiOptions.calibrate_on_start_writing
   = False` if you have a reason (chapter 48).

**You should see:** in the History, the warnings, then `output task ON:
piezo 0.000 V (0 nm), bias +100.0 mV`, then `session calibration:
current_zero_v=..., group_delay_samples=..., granted_sample_rate_hz=40000`.
On the panel: Start Writing and Reset DAQ Devices grey out, Kill Tasks stays
live, the DAQ-tab entries lock (Igor: `SetVariable ... disable=2`), the
piezo slider and the Background Sampling box become live.

**If not:** `ConfigError` text in the History names the field. On hardware,
`verify_devices` failing means the device name in `channels.device` is not
what NI MAX shows, or the product type differs — set
`channels.expected_product_type` to `None` to skip that check.

## 2. Background Sampling (Beep is ON)

**Igor:** `BkgdSamplingCheckProc` → `StartBkgdSampling`,
Functions_STMBJ.ipf:633: a named background task every 15 ticks (0.25 s)
that read `G_FastReadWaveSize` samples from both cards, put the mean
junction voltage in mV, the mean current in µA and the piezo sense voltage
into the three ValDisplays, and beeped when |I| exceeded 0.15 µA.

**Now:** the checkbox calls `set_background_sampling(on)`. The worker
thread, whenever its command queue has been idle for
`RigController.BKGD_PERIOD_S` (0.25 s), runs `_background_read`: one DC
hold of **Fast Read Wave Size** samples at the present piezo and bias,
`junction_mv = voltage_input_sign × mean(V) × 1000`, `current_ua =
volts_to_amps(mean(I)) × 10⁶`, the tracked piezo voltage, and a beep flag
when |I| exceeds `GuiOptions.beep_current_ua` (0.15). Because it runs only
while the queue is idle, sampling never interleaves with a measurement: it
simply pauses while Start Measurement, Find Offset or an approach is
running, and resumes after — which is what Igor's explicit
`StopBkgdSampling / StartBkgdSampling` bracket around every button did.

**You should see:** the I (µA), V (mV) and Piezo readouts refreshing four
times a second, and the HighRes window opening with the last read. On the
simulator, retracted, the current is noise around zero and there is no
beep; in contact it beeps every read.

**If not:** ticking the box before Start Writing puts `Background sampling
needs the output task; press Start Writing first` in the History and clears
the box. A read that raises (a card error on hardware) clears the box and
logs `background sampling stopped: ...`.

## 3. Start Approach

**Igor:** `ApproachButton`, Controls_STMBJ.ipf:434 → `HighResCardApproach`,
Functions_STMBJ.ipf:1723. Forced `G_ActuatorStepSize` to 5, then looped:
read `G_FastReadWaveSize` samples, print the current, and if |I| < 0.1 µA
take one actuator step closer (`StepActuatorCloser`) and increment
`G_ActuatorCounter`; otherwise stop. Alt aborted.

**Now:** `approach`. Refuses with `NotReady` before Start Writing, and with
`ApproachError: no coarse actuator configured (actuator.kind == 'none');
approach by hand` if the config has no actuator — in which case bring the
tip in by hand until the fine piezo can reach the surface. Otherwise it sets
`cfg.actuator.step_size = 5` as Igor did, zeroes the counter, and loops
exactly as Igor did with `actuator.stop_current_ua` (0.1 µA) as the
threshold. Each step goes through `Rig.coarse_step`, which refuses unless
the fine piezo is retracted (`limits.coarse_step_max_piezo_v`, 0.1 V) and
counts steps against `limits.max_coarse_steps` (2000). On hardware it waits
`actuator.settle_s` (0.1 s) after each step.

**You should see:** the counter beside Step Size climbing, one `Approach:
actual current= 0.0000 uA, Voltage= -0.1000 V` line per step in the
History, then a final line with the current that stopped it. About forty
steps on the simulator, where the surface starts 300 nm away and each
simulated step is 8 nm.

**If not:** if you moved the piezo up with the slider first, the interlock
refuses: `SafetyViolation: refusing coarse step closer: piezo is at ... V,
must be below 0.100 V. Retract the fine piezo first.` Put the slider back
to 0 (Igor's `LateralEXPT` did exactly that before its approach). Two
thousand steps without current is `check_step_budget` refusing — `coarse
approach took 2000 steps without finding current (budget 2000). Either the
tip is not where you think it is, or the current path is open.`

## 4. Find Offset (Find Zero)

**Igor:** `FindOffset`, Controls_STMBJ.ipf:498 → `OffsetVoltage`,
Functions_STMBJ.ipf:920. Stopped background sampling, swept the bias
through ±`G_VoltageInterval` in 2·`G_NumPoints` steps with a contact check
before every point, fitted a line, stored `G_Izero` (the intercept, µA) and
`G_Vzero` (`-Izero/slope`, mV), restored the bias, opened the Izero graph.

**Now:** `find_offset` → `stmlab.vzero.measure_offset`. Chapter 43 has the
algorithm line by line. The result lands in the Voltage Offset panel's
**V0 (fit, mV)** and **I0 (fit, µA)** displays, in the controller's
`vzero_tracker.history`, and in the `Izero` and `Izero_Time` windows.

**You should see:** the piezo readout jump as `_ensure_contact` steps in
2 nm at a time until contact, the Izero window with pink points on a blue
fitted line and the V0 / I0 box, and `Vzero = +0.000 mV (Izero = ...)` in
the History. The simulator has no bias offset, so V0 is a few microvolts of
noise; a real amplifier gives a few millivolts.

**If not:** the piezo ceiling with no contact raises `SafetyViolation:
vzero: piezo at the ceiling with no contact; run the coarse approach before
measuring the offset` — do step 3 first. A flat fit raises `vzero: flat I(V)
-- no contact, or a railed preamp at every point`.

## 5. Find Suppress

**Igor:** `FindSuppress`, Controls_STMBJ.ipf:479. Wrote zero tip bias, ran
`TestVirtualGround` (Functions_STMBJ.ipf:1097): 21 suppress values from −1
to +1, a `sleep/T 5` after each because "the amplifier is slow to respond"
(the SPIKE comment at line 1123), 2000 samples read, then a line fitted
through the points with the two ends excluded and the suppress set to the
zero crossing. Then the tip bias was restored.

**Now:** `find_suppress`. Refuses without the output task and without the
Keithley. Sets the bias to 0 V, calls `stmlab.keithley.find_suppress(rig,
amp)` with Igor's numbers (21 points, 83 ms settle, 2000 samples, endpoints
excluded from the fit), and restores the bias in a `finally` so a failure
mid-sweep cannot leave the junction at zero bias. The new value is stored
back as **Suppress I value** in Igor's units — the panel shows the constant,
and the amplifier receives `const × 10^(3 − gain)` µA (Controls_STMBJ.ipf:473).

**You should see:** `new current suppress: 0.3469 uA` from the module and
`New current suppress is 0.3469 uA` from the controller in the History, and
the Suppress I value entry updating.

**If not:** `KeithleyError: suppress sweep produced a flat response; is the
amplifier connected and out of zero-check?` — untick Zero Check first. On a
real 428 the sweep takes 21 × (83 ms + 50 ms of samples), about three
seconds.

> Zero the bias yourself if you call `keithley.find_suppress` from a script:
> the function does not know what bias you wanted back. The button does it
> for you.

## 6. Start Measurement, and +1

**Igor:** `StartMeasurement`, Controls_STMBJ.ipf:9 → `MeasureBreakJunctions`,
Functions_STMBJ.ipf:1664. Returned at once if `G_PullOutNumber ≥
G_StopNumber`; otherwise `CreateInputs`, then a loop of `SmashFun` and
`SingleBreakJunctionAttempt` (contact, `GenerateTrace`, `TestTrace`,
`SaveOffset`, `SavePullOut`, `CreateInputs` again) until Saved reached
Stop #, Alt was pressed, or attempts hit 100000 ("Catastrophic failure").
`MakeAttempt` (+1) set `G_SingleAttemptFlag` so the loop ran once.

**Now:** `start_measurement(single=False)` and `start_measurement(single=True)`
are the two buttons; both run `_measure_impl`. Step by step:

1. `NotReady` without the output task. `Saved (n) >= Stop # (m): nothing to
   do` in the History if there is nothing to do (not for +1, which always
   makes one attempt).
2. The mode comes from the Options tab checkboxes (`GuiOptions.mode()`):
   `constant` when none is ticked, else `push_pull`, `iv`, `ac_hold` or
   `hb_hold`. `_configure_mode` then does what the corresponding
   `experiments/0N` runner does before its loop: for the four ramp modes,
   `cfg.ramp.pull_length_nm` is set to initial + final pull so the headroom
   check in `engage` matches the mode's real descent, and for IV, AC hold
   and HB hold `limits.bias_max_v` is raised to 1.1 × the sweep or hold
   amplitude with a `RAISING limits.bias_max_v ...` warning in the
   History. Constant mode changes nothing.
3. `validate(cfg)` again; warnings to the History.
4. A session file is opened: `data/<date>/<mode>_<HHMMSS>_from<Saved>.h5`
   (chapter 47). `writing traces to ...` in the History.
5. The bias is set to Tip Bias, and the loop begins. Per attempt:
   Attempts increments (Igor's `G_PullOutAttempt`, global across presses);
   every **Smash Freq.** attempts `approach.smash` drives the tip in
   **Smash In** nm and back **Smash Out** nm; `approach.recover_headroom`
   engages (separate if in contact, close in 0.5 nm at a time until the
   threshold or a railed preamp, back the coarse actuator off up to five
   times if contact lands too low to pull from); the ramp is built for the
   mode (`trace.build_ramp` for constant, `ramps.build_*` otherwise) from
   the actual contact point; `trace.capture` plays it and cuts the trace
   out at the alignment spike.
6. Every generated trace is drawn in the three PullOut windows and
   SenseInDisplay, saved or not — Igor updated `PullOutConductance` inside
   `GenerateTrace` before `TestTrace` judged it.
7. Constant mode only: `analysis.select_trace`, Igor's `TestTrace` — ended
   in tunnelling below **Zero Cutoff**, and has a gold plateau. The four
   ramp modes keep every aligned trace, as their runners do and as Igor
   did (it applied `TestTrace` to constant pulls only).
8. An accepted trace: with **V0 check ON** in constant mode,
   `VzeroTracker.maybe_measure` re-measures the offset every **Frequency
   (traces)** saved traces (Igor's `SaveOffset`); the trace is appended to
   the file; Saved increments; the conductance joins the current histogram
   block; when the block reaches 100, `analysis.log_histogram` runs on it
   and the LogHistOfBlock window redraws (Igor's `LogHistFromBlocks` on
   every saved block).
9. The loop ends when Saved reaches Stop #, when Stop is pressed
   (`stopping: Stop pressed`), when engage fails and the coarse actuator
   cannot help (`cannot make contact: ...`, Igor's return −1), or at
   `max_attempts` (`Catastrophic failure: n attempts`). The partial
   histogram block is drawn, the file is closed with its summary, and the
   History prints `constant: 100 saved / 102 attempts this run (Saved now
   101)`.

**You should see:** Attempts and Saved climbing; the status line reading
`running: Start Measurement`; Start Measurement, +1 and Start Approach
greyed while it runs; the PullOut windows redrawing per attempt; the
histogram after each 100 saved.

**What V0 check ON changes:** in constant mode every trace is applied at
Tip Bias + V0 (`trace.build_ramp(bias_offset_v=...)`, Igor's
`-(TipBias+Vzero)/1000` at Functions_STMBJ.ipf:1611, with the alignment
spike still at +Tip Bias, line 1631) and V0 is re-measured periodically. In
high-bias-hold mode the hold bias *becomes* V0 (Igor lines 1595-1599). In
push-pull, IV and AC hold it has no effect, as in Igor. Chapter 43.

**Rejections** are counted by reason (`engage`, `alignment`, and the
`TestTrace` reasons) and written into the file summary; they are not
individually reported in the History, which would drown it.

## 7. Stop

**Igor:** `GetKeyState(0) == 2`, the Alt key, polled between attempts in
`MeasureBreakJunctions` (line 1697) and between steps in
`HighResCardApproach` (line 1751).

**Now:** `request_stop` sets a `threading.Event` that the measurement loop,
the approach loop, `rungo` and `LateralEXPT` all check between steps. It is
bound to the Alt keys, to Escape, to the **Stop (Alt)** button and to
Macros → Stop. The History prints `stop requested; finishing the current
step`. The step in progress completes — a pull is never cut short, so the
piezo always ends where the waveform said it would and the tracker stays
truthful.

Kill Tasks also sets the flag first, so a Kill pressed during a run stops
the run and then parks.

## 8. Kill Tasks

**Igor:** `StopWritingTasks`, Controls_STMBJ.ipf:172. Stopped background
sampling, sent `C1X` (zero check on), wrote the piezo back to zero with the
bias still applied, stopped and cleared the output task, reset the second
card, re-enabled the EChem gate button and disabled the CV buttons, and
re-enabled the DAQ-tab controls.

**Now:** `kill_tasks`: the stop flag; background sampling off; zero check
on (and the checkbox re-ticked); the session file closed if a run was
interrupted; `Rig.close()` — which withdraws (piezo to park, bias to 0 V)
and closes the tasks, after which the card's idle behaviour holds the
outputs at 0 V; the counter electrode and the X piezo released; the panel
back to its pre-Start state. `output task OFF; outputs parked` in the
History.

Igor left the bias applied while zeroing the piezo and only then cleared
the task. `Rig.withdraw` drops both, deliberately: 0 V on both channels is
the one state that is safe regardless of what the tip is near.

## A complete session on the simulator

The buttons, and the History lines that should follow each one (numbers
will differ):

```
[launch]            Molecular Break Junction Measurement -- SIMULATED rig
                    Igor flow: Start Writing -> (Background Sampling) -> ...
                    Keithley 428 ready (simulated)
[Start Writing]     config: hv_amp_gain is unknown; piezo limits are ...
                    output task ON: piezo 0.000 V (0 nm), bias +100.0 mV
                    preamp zero ... uV, noise ... uV rms
                    session calibration: current_zero_v=..., group_delay_samples=37, ...
[Background on]     (readouts update; no History line)
[Start Approach]    Approach: actual current= 0.0000 uA, Voltage= -0.1000 V   (x ~40)
                    Approach: actual current= 10.0000 uA, Voltage= -0.1000 V
[Find Offset]       Vzero = +0.000 mV (Izero = -5.782e-10 A)
[Find Suppress]     new current suppress: 0.3469 uA
                    New current suppress is 0.3469 uA
[Stop # = 101]
[Start Measurement] writing traces to .../data/20260902/constant_152830_from1.h5
                    no headroom for the pull; backing the coarse actuator off one step (1/5)
                    smashing tip: +30 nm then -40 nm                         (every 50 attempts)
                    wrote loghist_152901_upto101.csv (100 traces)
                    constant: 100 saved / 102 attempts this run (Saved now 101)
[Kill Tasks]        output task OFF; outputs parked
```

The `no headroom` line is normal on the simulator: the approach stops with
the surface within reach of the retracted piezo, contact is made too low to
pull 5 nm from, and `recover_headroom` backs the actuator off one step and
tries again. On a real rig this is the same mechanism that keeps an
overnight run alive as the contact point drifts down the piezo range.

## Between runs

Saved and Attempts persist across presses within a launch, as Igor's
globals did across `StartMeasurement` calls. Each press opens a new session
file whose name carries the Saved number it started from, so a session is
the set of files in one dated folder, in Saved order. Edit Saved by hand if
you want a fresh numbering; edit Stop # to extend a run. The mode can be
changed between presses (each file records its own); the bias can be
changed between presses (Tip Bias applies immediately and every file
records `bias_v` per trace).
