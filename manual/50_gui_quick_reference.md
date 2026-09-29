# 50. GUI quick reference

*Every button, event, key and file on two pages. Chapter 51 is the complete binding table; chapter 30 is the command-line quick reference.*

## The lab flow

| Step | Press | Needs | Ends with |
|---|---|---|---|
| 1 | DAQ tab → Start Writing | a valid config | `output task ON ...` in the History |
| 2 | Background Sampling (Beep is ON) | step 1 | readouts updating, HighRes open |
| 3 | Start Approach | step 1, an actuator | `Approach: actual current= ...` above 0.1 µA |
| 4 | Voltage Offset → Find Offset | step 1 (and 3 on hardware) | V0, I0, the Izero window |
| 5 | Find Suppress | step 1, the Keithley, zero check off | `New current suppress is ...` |
| 6 | Start Measurement (or +1) | step 1, Stop # above Saved | `<mode>: n saved / m attempts` |
| 7 | Stop (Alt / Escape) | — | `stopping: Stop pressed` |
| 8 | Kill Tasks | — | `output task OFF; outputs parked` |

## Buttons and checkboxes

| Control | `RigController` method | Igor procedure | stmlab |
|---|---|---|---|
| Start Writing | `start_writing` | `StartHighResWritingTask` | `Rig.open`, `Rig.hold`, `calibrate.session_calibration` |
| Kill Tasks | `kill_tasks` | `StopWritingTasks` | `Keithley428.zero_check`, `Rig.close` |
| Reset DAQ Devices | `reset_daq` | `EChemResetDAQDevices` | `nidaqmx.system.Device.reset_device`, `safety.park_all_outputs` |
| Background Sampling | `set_background_sampling` | `BkgdSamplingCheckProc` | `Rig.hold` every 0.25 s |
| Bias | `keithley_bias` | `KeithleyBias` | `Keithley428.bias_enable` (B1X/B0X) |
| Zero Check | `zero_check` | `ZeroCheckProc` | `Keithley428.zero_check` (C1X/C0X) |
| Zero Correct | `zero_correct` | `ZeroCorrectProc` | `Keithley428.zero_correct` (C2X) |
| Suppress I | `suppress_enable` | `CurrentSuppressCheckProc` | `Keithley428.suppress_enable` (N1X/N0X) |
| Find Suppress | `find_suppress` | `FindSuppress` → `TestVirtualGround` | `Rig.set_bias(0)`, `keithley.find_suppress`, `Rig.set_bias` |
| Gain | `set_gain` | `SetGain` | `Keithley428.set_gain` (H6R<g>X) |
| Suppress I value | `set_suppress_const` | `SetCurrentSuppress` | `Keithley428.set_suppress_ua` (H8S...X) |
| Start Approach | `approach` | `ApproachButton` → `HighResCardApproach` | `Rig.hold`, `Rig.coarse_step` |
| Step closer / apart (actuator) | `step_actuator` | `StepActuatorCloser` / `Apart` | `Rig.coarse_step` or `Actuator.step` |
| Step closer / apart (piezo) | `piezo_step` | `PiezoStepCloser` / `Apart` | `Rig.piezo_step_nm` |
| Slider | `piezo_goto` | `SetPiezoBiasFromSlider` | `Rig.piezo_goto` |
| Tip Bias (mV) | `set_tip_bias` | `SetTipBiasVoltage` | `Rig.set_bias`, `Keithley428.set_bias_mv` |
| Start Measurement | `start_measurement(False)` | `StartMeasurement` → `MeasureBreakJunctions` | `approach.recover_headroom`, `trace.build_ramp` / `ramps.build_*`, `trace.capture`, `analysis.select_trace`, `storage.SessionWriter`, `analysis.log_histogram` |
| +1 | `start_measurement(True)` | `MakeAttempt` | as above, once |
| Stop (Alt) | `request_stop` | `GetKeyState` | — |
| Find Offset | `find_offset` | `FindOffset` → `OffsetVoltage` | `vzero.measure_offset` |
| V0 check ON | (read at Start) | `VzeroCheckBox` | `trace.build_ramp(bias_offset_v)`, `VzeroTracker.maybe_measure`, `ramps.build_hb_hold(vzero_mv)` |
| Counter Electrode ON | `counter_electrode_on` | `CounterElectrodeOn` | `echem.make_counter_electrode(...).on()` |
| Counter Electrode Bias | `set_counter_electrode` | `CounterElectrodeSetVar` | `CounterElectrode.set_mv` |
| CV HighRes / LowRes | `start_cv(kind)` | `StartCVHighResButton` / `LowRes` | `echem.run_cv`, `storage.save_cv_cycles` |
| Macros → rungo | `rungo` | `rungo()` | `_set_tip_bias_impl`, `_measure_impl` per bias |
| Macros → LateralEXPT | `lateral_expt` | `LateralEXPT()` | `_measure_impl`, `Rig.withdraw`, `Rig.coarse_step`, `XPiezo.move_nm`, `_approach_impl` |
| Macros → MoveXPiezo / ToZero | `move_xpiezo`, `zero_xpiezo` | `MoveXPiezo`, `MoveXPiezoToZero` | `XPiezo.move_nm`, `XPiezo.zero` |
| File → Load / Save config | `load_config`, `save_config` | — | `RigConfig.from_json`, `to_json` |
| Quit | `shutdown` | — | `_kill_tasks_impl`, `Keithley428.close` |

## Events

| Kind | Payload | Consumed by |
|---|---|---|
| `log`, `error` | text | History (and the status via `error`) |
| `busy`, `idle` | command name | main panel status line, button greying; Voltage Offset button |
| `readout` | current_ua, junction_mv, piezo_v, beep | readouts; the bell |
| `highres` | arrays | HighRes |
| `piezo` | volts, nm | Piezo readout, slider |
| `writing` | bool | enable rules on all three panels |
| `bkgd` | bool | the Background Sampling box |
| `trace` | g0, disp_nm, bias_mv, piezo_nm, accepted, mode, number | the three PullOut windows, SenseInDisplay |
| `hist` | centres, counts, n, partial | LogHistOfBlock |
| `izero`, `izero_time`, `vzero` | result / arrays / (mV, µA) | Izero, Izero_Time, the V0 and I0 displays |
| `suppress` | new_ua, sweep, readings | Suppress I value |
| `cv` | cycles | CyclicVoltammogram |
| `counter`, `saved`, `attempts`, `stop_number` | ints | the counters |
| `bias`, `gain` | mV / exponent | Tip Bias, Gain (and the CV buttons' enable) |
| `gate`, `xpiezo` | mV or None / nm | EChem panel |
| `config` | — | every panel refreshes |

## Keys and menus

| Key or item | Does |
|---|---|
| Alt, Escape, Stop (Alt), Macros → Stop | `request_stop` |
| Return / focus-out in an entry | commit |
| File | Load config JSON, Save config JSON, Open data folder, Quit |
| Macros | the three panels; rungo(); LateralEXPT(...); MoveXPiezo(nm); MoveXPiezoToZero(); Stop |
| Windows | HighRes, PullOutGvsE, PullOutLowG, AuAuConductanceLevel, SenseInDisplay, LogHistOfBlock, Izero, Izero_Time, CyclicVoltammogram, History, Button map |
| Help | Button map (which Python does each button run?), About / where the manual is |
| Hover any control | tooltip: what it does, Igor procedure, Python file:line of the method and its `_impl`, the stmlab functions called |
| Right-click any control (macOS: Control-click) | the Inspector window with the same text, kept open |
| "Which code runs this?" (bottom of the main panel) | the Button map window, all controls at once |

## Files written

| File | When | Content |
|---|---|---|
| `data/<date>/<mode>_<HHMMSS>_from<Saved>.h5` | each Start Measurement / +1 | raw traces, config, panel state, run summary (chapter 47) |
| `data/<date>/loghist_<HHMMSS>_upto<Saved>.csv` | each 100-trace block and the final partial block, with Save Hist on | log10(G/G0), counts per trace |
| `data/<date>/cv_<kind>_<HHMMSS>.h5` | each CV | applied potential, keep mask, tip current per cycle |

## Commands

| Do | Command |
|---|---|
| Launch, simulated | `./.venv/bin/python gui.py --simulate` |
| Launch, hardware | `./.venv/bin/python gui.py` |
| Launch from a saved config | `./.venv/bin/python gui.py --config my.json` |
| Same through the dispatcher | `./.venv/bin/python run.py gui --simulate` |
| All tests | `./.venv/bin/python -m pytest tests/ -q` |
| GUI tests only | `./.venv/bin/python -m pytest tests/test_gui_controller.py tests/test_gui_app.py -q` |
| Rebuild this manual | `manual_build/build.sh` (add `--figures` to regenerate the graph figures from a simulated run) |
| Regenerate the binding table | `./.venv/bin/python manual_build/gen_binding_table.py` |

## The numbers you change most

| Panel control | Default | Lives in |
|---|---|---|
| Tip Bias (mV) | 100 | `cfg.ramp.bias_v` (V) |
| Excursion (nm) | 5 | `cfg.ramp.pull_length_nm` |
| Pull Rate (nm/s) | 20 | `cfg.ramp.pull_rate_nm_per_s` |
| Contact Threshold (G0) | 0.5 | `cfg.ramp.engage_g0` |
| Contact step size (nm) | 0.5 | `cfg.ramp.approach_step_nm` |
| Zero Cutoff (G0) | 0.0005 | `cfg.ramp.break_g0` |
| Smash Freq. / In / Out | 50 / 30 / −40 | `cfg.ramp.smash_every`, `smash_in_nm`, `smash_out_nm` |
| Stop # | 1001 | `opts.stop_number` |
| Saved | 1 | `opts.pull_out_number` |
| Piezo offset (nm) | 0 | `opts.piezo_offset_nm` |
| Fast Read Wave Size | 200 | `opts.fast_read_wave_size` |
| Z (nm), piezo step | 5 | `opts.piezo_step_nm` |
| Step Size, actuator | 5 | `cfg.actuator.step_size` |
| Gain ( log(V/A) ) | 6 | `cfg.keithley.gain_exponent` and `cfg.cal.preamp_gain_v_per_a` |
| Tip Bias interval (mV) / Number of points / Frequency (traces) | 5 / 5 / 50 | `cfg.vzero.interval_mv`, `n_points`, `every_n_traces` |
| CV rate / cycles / scan rate / peaks | 1000 / 1 / 100 / −1, +1 | `cfg.echem.*` |
| Bias limit (config file only) | 0.5 V | `cfg.limits.bias_max_v` |

Everything else: chapter 51.
