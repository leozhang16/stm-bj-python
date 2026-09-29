# 05. The structure map: which file calls what

*Generated from the source by `manual_build/gen_structure.py` (Python's `ast`, every `def`, every call). Figures: `manual/figures/structure/`. Regenerate after editing code.*

Read this before chapter 00. It is the whole code on a few pages: what the files are, which file calls which function in which other file, and the two paths you will follow most — a button click, and one break-junction trace. Everything below the purpose column and the layer names is extracted from the code, not written; if a table here disagrees with a chapter, the table is right and the chapter is stale.

## The shape, in one picture

Five layers. Arrows point from the file that calls to the file that is called; nothing calls upward. The GUI and the command-line experiments are alternative tops on the same `stmlab` body, and only `daq.py` / `sim.py` (and, through `keithley.py`, `actuator.py`, `echem.py`, `xpiezo.py`, the driver libraries) ever touch an instrument.

!FIGL[figures/structure/layers.png]{The whole code by layer, on its own page. Every arrow is at least one real call found in the source; thickness is the number of distinct functions called, colour is the calling layer. config.py is read by every file and its arrows are left out.}

| Layer | Files | What lives there |
|----|--------|----------|
| Entry points | `gui.py`, `run.py`, `experiments/*/run_experiment.py`, `stmlab/main.py` | Where a run starts. `gui.py` starts the panels; `run.py` forwards to an experiment script or to `gui.py`; `stmlab/main.py` is the constant-bias command line that experiment 01 delegates to. |
| The GUI | `stmgui/` | The panels, graphs and menus (Tk thread) and `controller.py` (the worker thread that owns the Rig). Every button is a `RigController` method. |
| Recipes | `stmlab/trace.py`, `approach.py`, `ramps.py`, `analysis.py`, `vzero.py`, `calibrate.py`, `keithley.py`, `echem.py`, `xpiezo.py`, `storage.py`, `bringup.py` | The Igor procedures, one concern per file. They know *what* to do to the junction and call the Rig to do it. |
| The rig | `stmlab/instrument.py`, `safety.py`, `config.py`, `actuator.py` | `Rig` is the only way to the card; `safety` is what it checks; `config` is every number; `actuator` is the coarse motor. |
| Card and instruments | `stmlab/daq.py`, `stmlab/sim.py`, `nidaqmx`, `pyvisa`, `pyserial` | `DaqSession.play()` is the one function that talks to the NI card; `SimulatedDaqSession.play()` is its stand-in. |

## Follow one click

Press **Find Suppress** on the panel. This is the path, file by file, top to bottom. Every button takes the same route; only the `_impl` and the recipe module change (chapter 50 lists them all, and the Button map window shows this for any control).

!FIG[figures/structure/click.png]{One click, from gui.py to the card and back to the screen.}

Three things to notice. The panel never calls `stmlab` directly: it calls the controller, which queues the work. The controller never draws: it posts events, which `app.py` delivers to the panels 20 times a second. And the recipe (`keithley.find_suppress`) never touches the card: it asks the `Rig`, which checks the limits and calls `play()`.

## Follow one trace

`python run.py constant_bias --simulate -n 100`, or Start Measurement in constant mode. The command line path is shown; the GUI's `_measure_impl` does the same steps in the same order, with its own loop instead of `trace_loop`.

!FIG[figures/structure/trace.png]{One constant-bias trace, from the command line to the histogram.}

## Every file

| File | Lines | Purpose | Called by |
|--------|--|--------------|--------|
| `gui.py` | 37 | Launcher for the panels: checks Tk, calls stmgui.app.main | (entry point) |
| `run.py` | 65 | Dispatcher: python run.py <experiment> or gui | (entry point) |
| `stmlab/main.py` | 213 | The command line: run / check / summarise / dump-config / bringup | `experiments/01_constant_bias/run_experiment.py` |
| `stmlab/config.py` | 677 | Every number, as dataclasses (RigConfig); validate() refuses unsafe configs | `experiments/* (8 scripts)`, `stmgui/app.py`, `stmgui/controller.py`, `stmlab/analysis.py`, `stmlab/approach.py`, `stmlab/bringup.py`, `stmlab/calibrate.py`, `stmlab/echem.py`, `stmlab/instrument.py`, `stmlab/main.py`, `stmlab/safety.py`, `stmlab/storage.py`, `stmlab/vzero.py` |
| `stmlab/safety.py` | 219 | Limits and interlocks: check_bias, clamp_piezo, require_retracted, SafeSession, park_all_outputs | `experiments/* (7 scripts)`, `stmgui/controller.py`, `stmlab/approach.py`, `stmlab/instrument.py`, `stmlab/main.py`, `stmlab/ramps.py`, `stmlab/trace.py`, `stmlab/vzero.py` |
| `stmlab/instrument.py` | 248 | Rig: the one funnel to the card -- play(), hold(), tracked piezo position, coarse_step() behind the interlock | `experiments/* (7 scripts)`, `stmgui/controller.py`, `stmlab/approach.py`, `stmlab/bringup.py`, `stmlab/calibrate.py`, `stmlab/keithley.py`, `stmlab/main.py`, `stmlab/trace.py`, `stmlab/vzero.py` |
| `stmlab/daq.py` | 229 | The real NI card: DaqSession.play() writes a waveform and reads both inputs | `stmlab/instrument.py` |
| `stmlab/sim.py` | 214 | The fake card: SimulatedDaqSession with a junction model (gold plateau, molecule, tunnelling) | `stmgui/controller.py`, `stmlab/instrument.py` |
| `stmlab/actuator.py` | 218 | The coarse actuator: NanoPZ over serial, simulated, or none | `stmgui/controller.py`, `stmlab/bringup.py`, `stmlab/instrument.py` |
| `stmlab/approach.py` | 188 | engage() = separate + close_in; smash(); coarse_approach(); recover_headroom() | `experiments/* (7 scripts)`, `stmgui/controller.py`, `stmlab/main.py`, `stmlab/trace.py` |
| `stmlab/trace.py` | 301 | build_ramp() the constant pull; capture() play + align at the spike; single_trace(); trace_loop() | `experiments/* (7 scripts)`, `stmgui/controller.py`, `stmlab/main.py` |
| `stmlab/ramps.py` | 370 | The four mode waveforms: build_push_pull, build_iv, build_ac_hold, build_hb_hold | `experiments/* (4 scripts)`, `stmgui/controller.py` |
| `stmlab/analysis.py` | 363 | Volts to physics: to_conductance, select_trace (Igor TestTrace), log_histogram, peak_position | `experiments/03_iv_sweep/iv_analysis.py`, `stmgui/controller.py`, `stmlab/calibrate.py`, `stmlab/main.py`, `stmlab/storage.py`, `stmlab/trace.py` |
| `stmlab/storage.py` | 346 | HDF5 files: SessionWriter / Session, save_cv_cycles / CVSession, Igor .ibw readers | `experiments/* (8 scripts)`, `stmgui/controller.py`, `stmlab/main.py` |
| `stmlab/calibrate.py` | 159 | measure_zero, measure_group_delay, session_calibration | `experiments/* (7 scripts)`, `stmgui/controller.py`, `stmlab/bringup.py`, `stmlab/main.py` |
| `stmlab/keithley.py` | 233 | Keithley 428 over GPIB, find_suppress (Igor TestVirtualGround) | `stmgui/controller.py` |
| `stmlab/vzero.py` | 149 | measure_offset (Igor OffsetVoltage) and VzeroTracker (SaveOffset) | `experiments/05_high_bias_hold/run_experiment.py`, `stmgui/controller.py` |
| `stmlab/echem.py` | 332 | CounterElectrode gate; CV ramp builders and run_cv | `experiments/06_echem_gate_cv/run_experiment.py`, `stmgui/controller.py` |
| `stmlab/xpiezo.py` | 128 | XPiezo: the lateral piezo on the second card | `experiments/07_lateral_monolayer/run_experiment.py`, `stmgui/controller.py` |
| `stmlab/bringup.py` | 464 | Hardware bring-up checks: devices, timing, hold, preamp, actuator | `stmlab/main.py` |
| `stmgui/app.py` | 324 | App: builds panels, menus, the 50 ms event pump; InitializeExperiment | `gui.py`, `stmgui/panels/voltage_offset.py` |
| `stmgui/controller.py` | 1278 | RigController: every button as a method; one worker thread owns the Rig; events out; COMMAND_MAP | `stmgui/app.py`, `stmgui/panels/button_map.py`, `stmgui/panels/echem_panel.py`, `stmgui/panels/main_panel.py`, `stmgui/widgets.py` |
| `stmgui/state.py` | 337 | GuiOptions (Igor globals without a config home), Param, PARAMS binding table | `stmgui/app.py` |
| `stmgui/widgets.py` | 331 | SetVariable, ValDisplay, CheckBox, button, Tooltip, Inspector binding | `stmgui/panels/echem_panel.py`, `stmgui/panels/main_panel.py`, `stmgui/panels/voltage_offset.py` |
| `stmgui/graphs.py` | 388 | The nine Igor graph windows (matplotlib in Tk) and GraphSet routing | `stmgui/app.py` |
| `stmgui/panels/main_panel.py` | 470 | The BreakJunctionMeasurement panel | `stmgui/app.py` |
| `stmgui/panels/voltage_offset.py` | 90 | The Voltage_Offset panel | `stmgui/app.py` |
| `stmgui/panels/echem_panel.py` | 103 | The EChem panel | `stmgui/app.py` |
| `stmgui/panels/history.py` | 53 | The History window | `stmgui/app.py` |
| `stmgui/panels/button_map.py` | 110 | The Button map and Inspector windows | `stmgui/app.py` |
| `experiments/01_constant_bias/run_experiment.py` | 47 | delegates to stmlab.main (the reference loop) | `run.py` |
| `experiments/02_push_pull/run_experiment.py` | 231 | loop: engage, ramps.build_push_pull, capture, save | `run.py` |
| `experiments/03_iv_sweep/run_experiment.py` | 312 | loop: engage, ramps.build_iv, capture, save; iv_analysis.py reads it back | `run.py` |
| `experiments/04_ac_hold/run_experiment.py` | 287 | loop: engage, ramps.build_ac_hold, capture, save | `run.py` |
| `experiments/05_high_bias_hold/run_experiment.py` | 281 | loop: engage, ramps.build_hb_hold (optionally at Vzero), capture, save | `run.py` |
| `experiments/06_echem_gate_cv/run_experiment.py` | 332 | gate / cv / traces sub-commands over echem.py | `run.py` |
| `experiments/07_lateral_monolayer/run_experiment.py` | 244 | per site: trace_loop, withdraw, xpiezo.move_nm, approach | `run.py` |
| `experiments/08_bias_series/run_experiment.py` | 318 | Igor rungo: one trace_loop per bias, resumable | `run.py` |

## Who calls whom, file by file

For each file: the functions it defines, and for each one the functions in *other* files it calls (`file: function`). Calls within the same file are left out, as are calls to numpy, h5py, Tk and the standard library. A method is shown as `Class.method`; `self.x` means a method of the same class.

### gui.py

| Function | Calls (file: function) |
|-------|----------------|
| `(module level)` | stmgui/app.py: main |

### run.py

Calls nothing in another file of this package (a leaf: it is called, it does not call).

### stmlab/main.py

| Function | Calls (file: function) |
|-------|----------------|
| `run (:25)` | stmlab/approach.py: coarse_approach; stmlab/approach.py: recover_headroom; stmlab/calibrate.py: session_calibration; stmlab/config.py: validate; stmlab/instrument.py: Rig; stmlab/instrument.py: Rig.set_bias; stmlab/instrument.py: Rig.withdraw; stmlab/safety.py: SafeSession; stmlab/storage.py: SessionWriter; stmlab/storage.py: SessionWriter.write_summary; stmlab/trace.py: trace_loop |
| `summarise (:74)` | stmlab/analysis.py: log_histogram; stmlab/analysis.py: peak_position; stmlab/storage.py: Session; stmlab/storage.py: Session.conductances |
| `main (:149)` | stmlab/bringup.py: main; stmlab/config.py: RigConfig; stmlab/config.py: RigConfig.from_json; stmlab/config.py: RigConfig.to_json; stmlab/config.py: validate |

### stmlab/config.py

Calls nothing in another file of this package (a leaf: it is called, it does not call).

### stmlab/safety.py

| Function | Calls (file: function) |
|-------|----------------|
| `check_pull_headroom (:72)` | stmlab/config.py: Calibration.nm_to_piezo_volts |
| `park_all_outputs (:163)` | stmlab/config.py: ChannelMap.path |

### stmlab/instrument.py

| Function | Calls (file: function) |
|-------|----------------|
| `Rig.open (:41)` | stmlab/actuator.py: make_actuator; stmlab/daq.py: DaqSession; stmlab/sim.py: SimulatedDaqSession |
| `Rig.piezo_nm (:90)` | stmlab/config.py: Calibration.piezo_volts_to_nm |
| `Rig.play (:104)` | stmlab/daq.py: DaqSession.play |
| `Rig.hold (:130)` | stmlab/safety.py: check_bias; stmlab/safety.py: clamp_piezo |
| `Rig.piezo_step_nm (:152)` | stmlab/config.py: Calibration.nm_to_piezo_volts |
| `Rig.set_bias (:157)` | stmlab/safety.py: check_bias |
| `Rig.conductance_of (:189)` | stmlab/config.py: Calibration.volts_to_amps |
| `Rig.read_current_ua (:203)` | stmlab/config.py: Calibration.volts_to_amps |
| `Rig.coarse_step (:229)` | stmlab/actuator.py: Actuator.step; stmlab/safety.py: check_step_budget; stmlab/safety.py: require_retracted |

### stmlab/daq.py

Calls nothing in another file of this package (a leaf: it is called, it does not call).

### stmlab/sim.py

Calls nothing in another file of this package (a leaf: it is called, it does not call).

### stmlab/actuator.py

Calls nothing in another file of this package (a leaf: it is called, it does not call).

### stmlab/approach.py

| Function | Calls (file: function) |
|-------|----------------|
| `_headroom_ok (:29)` | stmlab/config.py: Calibration.nm_to_piezo_volts |
| `separate (:35)` | stmlab/instrument.py: Rig.piezo_step_nm; stmlab/instrument.py: Rig.probe |
| `close_in (:55)` | stmlab/instrument.py: Rig.in_contact; stmlab/instrument.py: Rig.piezo_step_nm |
| `engage (:71)` | stmlab/instrument.py: Rig.in_contact |
| `smash (:102)` | stmlab/instrument.py: Rig.piezo_step_nm |
| `coarse_approach (:120)` | stmlab/instrument.py: Rig.coarse_step; stmlab/instrument.py: Rig.read_current_ua; stmlab/safety.py: require_retracted |
| `withdraw_coarse (:161)` | stmlab/instrument.py: Rig.coarse_step |
| `recover_headroom (:167)` | stmlab/instrument.py: Rig.withdraw |

### stmlab/trace.py

| Function | Calls (file: function) |
|-------|----------------|
| `TraceRecord.conductance_g0 (:60)` | stmlab/analysis.py: to_conductance |
| `TraceRecord.displacement_nm (:68)` | stmlab/analysis.py: displacement_nm |
| `build_ramp (:77)` | stmlab/analysis.py: spike_indices; stmlab/safety.py: check_bias; stmlab/safety.py: check_pull_headroom |
| `capture (:166)` | stmlab/instrument.py: Rig.play |
| `_measure_delay (:206)` | stmlab/analysis.py: find_alignment_edge |
| `trace_loop (:236)` | stmlab/analysis.py: select_trace; stmlab/approach.py: engage; stmlab/approach.py: smash |

### stmlab/ramps.py

| Function | Calls (file: function) |
|-------|----------------|
| `_assemble (:90)` | stmlab/safety.py: SafetyViolation; stmlab/safety.py: check_bias |

### stmlab/analysis.py

| Function | Calls (file: function) |
|-------|----------------|
| `to_conductance (:66)` | stmlab/config.py: Calibration.volts_to_amps |

### stmlab/storage.py

| Function | Calls (file: function) |
|-------|----------------|
| `SessionWriter.open (:50)` | stmlab/config.py: RigConfig.to_dict |
| `Session.__init__ (:160)` | stmlab/config.py: RigConfig.from_dict |
| `Session.conductance (:183)` | stmlab/analysis.py: to_conductance |
| `save_cv_cycles (:255)` | stmlab/config.py: RigConfig.to_dict |
| `CVSession.__init__ (:305)` | stmlab/config.py: RigConfig.from_dict |
| `CVSession.current_a (:338)` | stmlab/config.py: Calibration.volts_to_amps |

### stmlab/calibrate.py

| Function | Calls (file: function) |
|-------|----------------|
| `measure_zero (:28)` | stmlab/config.py: Calibration.volts_to_amps; stmlab/instrument.py: Rig.hold |
| `measure_group_delay (:57)` | stmlab/analysis.py: find_alignment_edge; stmlab/instrument.py: Rig.play |
| `measure_gain_offset (:105)` | stmlab/instrument.py: Rig.hold |

### stmlab/keithley.py

| Function | Calls (file: function) |
|-------|----------------|
| `find_suppress (:199)` | stmlab/instrument.py: Rig.hold |

### stmlab/vzero.py

| Function | Calls (file: function) |
|-------|----------------|
| `_ensure_contact (:49)` | stmlab/instrument.py: Rig.in_contact; stmlab/instrument.py: Rig.piezo_step_nm; stmlab/instrument.py: Rig.set_bias; stmlab/safety.py: SafetyViolation |
| `measure_offset (:66)` | stmlab/config.py: Calibration.volts_to_amps; stmlab/instrument.py: Rig.hold; stmlab/instrument.py: Rig.set_bias |

### stmlab/echem.py

| Function | Calls (file: function) |
|-------|----------------|
| `_run_cv_hardware (:283)` | stmlab/config.py: ChannelMap.path |

### stmlab/xpiezo.py

Calls nothing in another file of this package (a leaf: it is called, it does not call).

### stmlab/bringup.py

| Function | Calls (file: function) |
|-------|----------------|
| `step_devices (:68)` | stmlab/config.py: ChannelMap.path |
| `step_timing (:143)` | stmlab/calibrate.py: measure_group_delay; stmlab/instrument.py: Rig |
| `step_hold (:191)` | stmlab/instrument.py: Rig; stmlab/instrument.py: Rig.hold; stmlab/instrument.py: Rig.piezo_goto |
| `step_preamp (:250)` | stmlab/calibrate.py: expected_resistor_v; stmlab/calibrate.py: measure_zero; stmlab/config.py: Calibration.volts_to_amps; stmlab/instrument.py: Rig; stmlab/instrument.py: Rig.hold |
| `step_actuator (:309)` | stmlab/actuator.py: NanoPZActuator; stmlab/actuator.py: list_serial_ports |
| `main (:410)` | stmlab/config.py: RigConfig; stmlab/config.py: RigConfig.from_json |

### stmgui/app.py

| Function | Calls (file: function) |
|-------|----------------|
| `App.__init__ (:41)` | stmgui/controller.py: RigController; stmgui/controller.py: RigController.connect_instruments; stmgui/controller.py: RigController.request_stop; stmgui/graphs.py: GraphSet; stmgui/panels/echem_panel.py: EChemPanel; stmgui/panels/history.py: HistoryWindow; stmgui/panels/main_panel.py: MainPanel; stmgui/panels/voltage_offset.py: VoltageOffsetPanel; stmgui/state.py: GuiState; stmgui/state.py: simulated_state |
| `App.log (:95)` | stmgui/panels/history.py: HistoryWindow.append |
| `App._build_menus (:98)` | stmgui/graphs.py: GraphSet.names; stmgui/graphs.py: GraphSet.show |
| `App._load_cfg (:156)` | stmgui/controller.py: RigController.load_config |
| `App._save_cfg (:166)` | stmgui/controller.py: RigController.save_config |
| `App._open_data (:173)` | stmgui/controller.py: RigController.data_dir |
| `App._rungo (:184)` | stmgui/controller.py: RigController.rungo |
| `App._lateral (:204)` | stmgui/controller.py: RigController.lateral_expt |
| `App._move_x (:221)` | stmgui/controller.py: RigController.move_xpiezo |
| `App.show_button_map (:227)` | stmgui/panels/button_map.py: ButtonMapWindow; stmgui/panels/button_map.py: ButtonMapWindow.refresh; stmgui/panels/button_map.py: ButtonMapWindow.show |
| `App.inspect (:237)` | stmgui/panels/button_map.py: InspectorWindow; stmgui/panels/button_map.py: InspectorWindow.show_text; stmgui/panels/history.py: HistoryWindow.append |
| `App._fanout (:258)` | stmgui/panels/history.py: HistoryWindow.append |
| `App.quit (:287)` | stmgui/controller.py: RigController.shutdown |
| `main (:299)` | stmgui/state.py: GuiState; stmgui/state.py: simulated_state; stmlab/config.py: RigConfig.from_json |

### stmgui/controller.py

| Function | Calls (file: function) |
|-------|----------------|
| `RigController.__init__ (:93)` | stmlab/vzero.py: VzeroTracker |
| `RigController.shutdown (:204)` | stmlab/keithley.py: Keithley428.close |
| `RigController._connect_impl (:269)` | stmlab/keithley.py: make_keithley |
| `RigController._make_rig (:292)` | stmlab/actuator.py: SimulatedActuator; stmlab/instrument.py: Rig; stmlab/safety.py: park_all_outputs; stmlab/safety.py: verify_devices; stmlab/sim.py: SimulatedDaqSession |
| `RigController._start_writing_impl (:305)` | stmlab/calibrate.py: session_calibration; stmlab/config.py: Calibration.nm_to_piezo_volts; stmlab/config.py: validate; stmlab/instrument.py: Rig.hold |
| `RigController._kill_tasks_impl (:333)` | stmlab/instrument.py: Rig.close; stmlab/keithley.py: Keithley428.zero_check |
| `RigController._reset_daq_impl (:366)` | stmlab/echem.py: CounterElectrode.off; stmlab/safety.py: park_all_outputs |
| `RigController._background_read (:399)` | stmlab/config.py: Calibration.volts_to_amps; stmlab/instrument.py: Rig.hold |
| `RigController._piezo_step_impl (:434)` | stmlab/instrument.py: Rig.piezo_step_nm |
| `RigController._piezo_goto_impl (:445)` | stmlab/instrument.py: Rig.piezo_goto |
| `RigController._set_tip_bias_impl (:460)` | stmlab/instrument.py: Rig.set_bias; stmlab/keithley.py: Keithley428.set_bias_mv; stmlab/safety.py: SafetyViolation |
| `RigController._set_gain_impl (:483)` | stmlab/keithley.py: Keithley428.set_gain |
| `RigController._find_suppress_impl (:532)` | stmlab/instrument.py: Rig.set_bias; stmlab/keithley.py: find_suppress |
| `RigController._find_offset_impl (:556)` | stmlab/vzero.py: measure_offset |
| `RigController._step_actuator_impl (:586)` | stmlab/actuator.py: Actuator.close; stmlab/actuator.py: Actuator.step; stmlab/actuator.py: make_actuator; stmlab/instrument.py: Rig.coarse_step |
| `RigController._approach_impl (:605)` | stmlab/approach.py: ApproachError; stmlab/config.py: Calibration.volts_to_amps; stmlab/instrument.py: Rig.coarse_step; stmlab/instrument.py: Rig.hold |
| `RigController._build_ramp (:681)` | stmlab/ramps.py: build_ac_hold; stmlab/ramps.py: build_hb_hold; stmlab/ramps.py: build_iv; stmlab/ramps.py: build_push_pull; stmlab/trace.py: build_ramp |
| `RigController._open_writer (:699)` | stmlab/storage.py: SessionWriter |
| `RigController._close_writer (:707)` | stmlab/storage.py: SessionWriter.close; stmlab/storage.py: SessionWriter.write_summary; stmlab/vzero.py: VzeroTracker.as_arrays |
| `RigController._measure_impl (:722)` | stmlab/analysis.py: select_trace; stmlab/approach.py: recover_headroom; stmlab/approach.py: smash; stmlab/config.py: Calibration.piezo_volts_to_nm; stmlab/config.py: validate; stmlab/instrument.py: Rig.set_bias; stmlab/storage.py: SessionWriter.append; stmlab/trace.py: capture; stmlab/vzero.py: VzeroTracker.maybe_measure |
| `RigController._histogram_block (:872)` | stmlab/analysis.py: log_histogram |
| `RigController._gate_on_impl (:897)` | stmlab/echem.py: CounterElectrode.set_mv; stmlab/echem.py: make_counter_electrode |
| `RigController._gate_set_impl (:910)` | stmlab/echem.py: CounterElectrode.set_mv |
| `RigController._cv_impl (:922)` | stmlab/echem.py: run_cv; stmlab/keithley.py: Keithley428.zero_check; stmlab/storage.py: save_cv_cycles |
| `RigController._xp (:944)` | stmlab/xpiezo.py: make_xpiezo |
| `RigController._lateral_impl (:1012)` | stmlab/instrument.py: Rig.coarse_step; stmlab/instrument.py: Rig.piezo_goto; stmlab/instrument.py: Rig.set_bias; stmlab/instrument.py: Rig.withdraw |
| `RigController.save_config (:1048)` | stmlab/config.py: RigConfig.to_json |
| `RigController.load_config (:1052)` | stmlab/config.py: RigConfig.from_json |

### stmgui/state.py

Calls nothing in another file of this package (a leaf: it is called, it does not call).

### stmgui/widgets.py

| Function | Calls (file: function) |
|-------|----------------|
| `tip_text (:52)` | stmgui/controller.py: describe_command |

### stmgui/graphs.py

Calls nothing in another file of this package (a leaf: it is called, it does not call).

### stmgui/panels/main_panel.py

| Function | Calls (file: function) |
|-------|----------------|
| `MainPanel._sv (:47)` | stmgui/widgets.py: SetVariable |
| `MainPanel._cb (:52)` | stmgui/widgets.py: CheckBox |
| `MainPanel._build (:57)` | stmgui/controller.py: RigController.piezo_step; stmgui/controller.py: RigController.start_measurement; stmgui/controller.py: RigController.step_actuator; stmgui/widgets.py: Tooltip; stmgui/widgets.py: ValDisplay; stmgui/widgets.py: button; stmgui/widgets.py: groupbox; stmgui/widgets.py: tip_text |
| `MainPanel._build_daq_tab (:228)` | stmgui/widgets.py: ValDisplay; stmgui/widgets.py: button |
| `MainPanel._slider_release (:382)` | stmgui/controller.py: RigController.piezo_goto |
| `MainPanel.set_writing (:394)` | stmgui/widgets.py: set_enabled |
| `MainPanel.set_busy (:407)` | stmgui/widgets.py: set_enabled |

### stmgui/panels/voltage_offset.py

| Function | Calls (file: function) |
|-------|----------------|
| `VoltageOffsetPanel.__init__ (:26)` | stmgui/widgets.py: CheckBox; stmgui/widgets.py: SetVariable; stmgui/widgets.py: ValDisplay; stmgui/widgets.py: button; stmgui/widgets.py: groupbox |
| `VoltageOffsetPanel._toggled (:71)` | stmgui/app.py: App.log |

### stmgui/panels/echem_panel.py

| Function | Calls (file: function) |
|-------|----------------|
| `EChemPanel.__init__ (:27)` | stmgui/controller.py: RigController.start_cv; stmgui/widgets.py: SetVariable; stmgui/widgets.py: button; stmgui/widgets.py: groupbox; stmgui/widgets.py: set_enabled |
| `EChemPanel.set_cv_enabled (:79)` | stmgui/widgets.py: set_enabled |
| `EChemPanel.on_event (:88)` | stmgui/widgets.py: set_enabled |

### stmgui/panels/history.py

Calls nothing in another file of this package (a leaf: it is called, it does not call).

### stmgui/panels/button_map.py

| Function | Calls (file: function) |
|-------|----------------|
| `ButtonMapWindow.refresh (:47)` | stmgui/controller.py: command_table |

### experiments/01_constant_bias/run_experiment.py

| Function | Calls (file: function) |
|-------|----------------|
| `(module level)` | stmlab/main.py: main |

### experiments/02_push_pull/run_experiment.py

| Function | Calls (file: function) |
|-------|----------------|
| `run (:55)` | stmlab/approach.py: recover_headroom; stmlab/calibrate.py: session_calibration; stmlab/config.py: validate; stmlab/instrument.py: Rig; stmlab/instrument.py: Rig.set_bias; stmlab/instrument.py: Rig.withdraw; stmlab/ramps.py: build_push_pull; stmlab/safety.py: SafeSession; stmlab/storage.py: SessionWriter; stmlab/storage.py: SessionWriter.append; stmlab/storage.py: SessionWriter.write_summary; stmlab/trace.py: capture |
| `main (:199)` | stmlab/config.py: RigConfig; stmlab/config.py: RigConfig.from_json |

### experiments/03_iv_sweep/run_experiment.py

| Function | Calls (file: function) |
|-------|----------------|
| `sweep_stats (:52)` | stmlab/config.py: Calibration.volts_to_amps |
| `run (:65)` | stmlab/approach.py: recover_headroom; stmlab/calibrate.py: session_calibration; stmlab/config.py: validate; stmlab/instrument.py: Rig; stmlab/instrument.py: Rig.set_bias; stmlab/instrument.py: Rig.withdraw; stmlab/ramps.py: build_iv; stmlab/safety.py: SafeSession; stmlab/storage.py: SessionWriter; stmlab/storage.py: SessionWriter.append; stmlab/storage.py: SessionWriter.write_summary; stmlab/trace.py: capture |
| `plot_first_traces (:207)` | stmlab/storage.py: Session |
| `main (:280)` | stmlab/config.py: RigConfig; stmlab/config.py: RigConfig.from_json |

### experiments/04_ac_hold/run_experiment.py

| Function | Calls (file: function) |
|-------|----------------|
| `lockin_summary (:57)` | stmlab/config.py: Calibration.volts_to_amps |
| `run (:82)` | stmlab/approach.py: recover_headroom; stmlab/calibrate.py: session_calibration; stmlab/config.py: validate; stmlab/instrument.py: Rig; stmlab/instrument.py: Rig.set_bias; stmlab/instrument.py: Rig.withdraw; stmlab/ramps.py: build_ac_hold; stmlab/safety.py: SafeSession; stmlab/storage.py: SessionWriter; stmlab/storage.py: SessionWriter.append; stmlab/storage.py: SessionWriter.write_summary; stmlab/trace.py: capture |
| `main (:257)` | stmlab/config.py: RigConfig; stmlab/config.py: RigConfig.from_json |

### experiments/05_high_bias_hold/run_experiment.py

| Function | Calls (file: function) |
|-------|----------------|
| `run (:75)` | stmlab/approach.py: recover_headroom; stmlab/calibrate.py: session_calibration; stmlab/config.py: validate; stmlab/instrument.py: Rig; stmlab/instrument.py: Rig.set_bias; stmlab/instrument.py: Rig.withdraw; stmlab/ramps.py: build_hb_hold; stmlab/safety.py: SafeSession; stmlab/storage.py: SessionWriter; stmlab/storage.py: SessionWriter.append; stmlab/storage.py: SessionWriter.write_summary; stmlab/trace.py: capture; stmlab/vzero.py: measure_offset |
| `main (:252)` | stmlab/config.py: RigConfig; stmlab/config.py: RigConfig.from_json |

### experiments/06_echem_gate_cv/run_experiment.py

| Function | Calls (file: function) |
|-------|----------------|
| `cmd_gate (:62)` | stmlab/echem.py: CounterElectrode.off; stmlab/echem.py: CounterElectrode.on; stmlab/echem.py: CounterElectrode.set_mv; stmlab/echem.py: make_counter_electrode |
| `cmd_cv (:101)` | stmlab/config.py: Calibration.volts_to_amps; stmlab/echem.py: run_cv; stmlab/storage.py: save_cv_cycles |
| `_plot_cv (:130)` | stmlab/config.py: Calibration.volts_to_amps |
| `cmd_traces (:158)` | stmlab/approach.py: recover_headroom; stmlab/calibrate.py: measure_zero; stmlab/calibrate.py: session_calibration; stmlab/config.py: validate; stmlab/echem.py: CounterElectrode.off; stmlab/echem.py: CounterElectrode.on; stmlab/echem.py: CounterElectrode.set_mv; stmlab/echem.py: make_counter_electrode; stmlab/instrument.py: Rig; stmlab/instrument.py: Rig.set_bias; stmlab/instrument.py: Rig.withdraw; stmlab/safety.py: SafeSession; stmlab/storage.py: SessionWriter; stmlab/storage.py: SessionWriter.write_summary; stmlab/trace.py: trace_loop |
| `main (:303)` | stmlab/config.py: RigConfig; stmlab/config.py: RigConfig.from_json |

### experiments/07_lateral_monolayer/run_experiment.py

| Function | Calls (file: function) |
|-------|----------------|
| `engage_site (:58)` | stmlab/approach.py: coarse_approach; stmlab/approach.py: recover_headroom; stmlab/instrument.py: Rig.set_bias; stmlab/instrument.py: Rig.withdraw |
| `withdraw_site (:83)` | stmlab/instrument.py: Rig.coarse_step; stmlab/instrument.py: Rig.withdraw |
| `run (:96)` | stmlab/calibrate.py: session_calibration; stmlab/config.py: validate; stmlab/instrument.py: Rig; stmlab/instrument.py: Rig.set_bias; stmlab/instrument.py: Rig.withdraw; stmlab/safety.py: SafeSession; stmlab/storage.py: SessionWriter; stmlab/storage.py: SessionWriter.write_summary; stmlab/trace.py: trace_loop; stmlab/xpiezo.py: XPiezo.move_nm; stmlab/xpiezo.py: make_xpiezo |
| `main (:216)` | stmlab/config.py: RigConfig; stmlab/config.py: RigConfig.from_json |

### experiments/08_bias_series/run_experiment.py

| Function | Calls (file: function) |
|-------|----------------|
| `check_bias_limits (:106)` | stmlab/safety.py: SafetyViolation |
| `run (:127)` | stmlab/approach.py: recover_headroom; stmlab/calibrate.py: measure_zero; stmlab/calibrate.py: session_calibration; stmlab/config.py: validate; stmlab/instrument.py: Rig; stmlab/instrument.py: Rig.set_bias; stmlab/instrument.py: Rig.withdraw; stmlab/safety.py: SafeSession; stmlab/storage.py: SessionWriter; stmlab/storage.py: SessionWriter.write_summary; stmlab/trace.py: trace_loop |
| `main (:287)` | stmlab/config.py: RigConfig; stmlab/config.py: RigConfig.from_json |

## How to use this chapter

- To find where something happens, start at the entry point you used (`gui.py` or `run.py`), find the row in *Who calls whom*, and follow the `file: function` entries downward; each one is a row in the next table. Three hops reach the card.
- To find who uses a function, search this chapter for its name: every caller lists it.
- In the GUI, hover or right-click any control: the tooltip and the Inspector give the same file:line chain for that control (chapter 40).
- `less -N stmlab/trace.py` then `/def capture` opens the source at the function; the `:line` after each name in the tables is where the `def` is.
