# 42. The main panel, control by control

*Igor: `BreakJunctionMeasurement()` panel macro, Windows_STMBJ.ipf:133-375; the control procedures in Controls_STMBJ.ipf. Module: `stmgui/panels/main_panel.py`.*

Igor's panel was one tall window of absolutely positioned controls. The
rebuild keeps every group, every control and every title, in the same
top-to-bottom order, laid out with a grid instead of pixel coordinates.
This chapter goes through them in Igor's groups. For each control the
table gives the Igor control name (what `ControlInfo` would have called
it), its title on the panel, the procedure Igor attached to it, and what
it is bound to or does now. The complete list of limits, formats and
defaults is the generated table in chapter 51; here the columns are kept
to what you need at the panel.

Two words about **bindings**. Every entry and checkbox is bound to one row
of `stmgui.state.PARAMS` (chapter 48), which names a dotted attribute of
the `GuiState`: `cfg.…` is a field of the `RigConfig` that every data file
carries, `opts.…` is a field of `GuiOptions`, the panel-only state. Editing
the control writes that attribute at once — on Return, on leaving the
field, or on a spinbox arrow — and clamps to Igor's `limits`. Whether the
new value *does* anything at once depends on the control: "immediate"
below means the hardware or the running state changes now, "next Start"
means it is read the next time Start Measurement builds its ramps.

## The TabControl: DAQ, Inputs, Options

**Igor:** `TabControl TAB`, tabs DAQ / Inputs / Options, with
`MainWindowTabProc` (Controls_STMBJ.ipf:39) showing the controls whose
names end in `_DAQ`, `_Inputs` or `_Ramps`. The Options tab held a second
`TabControl RampSubTabs_Ramps` with Push-Pull / IV / AC / High bias hold,
handled by `SubWindowTabProc` (line 74). Here both are `ttk.Notebook`s.

### DAQ tab

| Igor name | Title | Igor proc | Bound to / does |
|---|---|---|---|
| `ZPiezoScale_DAQ` | Z piezo scale (nm/V) | ValDisplay of `K_ZPiezoScale` | shows `cfg.cal.piezo_nm_per_volt` (62) |
| `ZSenseScale_DAQ` | Z Sense scale (nm/V) | ValDisplay of `K_SenseScale` | shows `opts.sense_scale_nm_per_v` (314) |
| `AcqRate_DAQ` | Acquisition Rate | — | `cfg.ramp.sample_rate_hz`; next Start Writing |
| `WriteBufferSize_DAQ` | Write Buffer Size | — | `cfg.ramp.settle_samples`; immediate (every DC hold) |
| `ReadWaveSize_DAQ` | Fast Read Wave Size | — | `opts.fast_read_wave_size`; immediate (background reads, approach) |
| `OutputRangeHighRes_DAQ` | HighRes Output Range (V) | — | `cfg.channels.bias_ao_range_v`; next Start Writing |
| (new) | Piezo offset (nm) | — | `opts.piezo_offset_nm`; where Start Writing puts the piezo |
| `Start_DAQ` | Start Writing | `StartHighResWritingTask` | `RigController.start_writing` |
| `Stop_DAQ` | Kill Tasks | `StopWritingTasks` | `RigController.kill_tasks` |
| `Reset_DAQ` | Reset DAQ Devices | `EChemResetDAQDevices` | `RigController.reset_daq` |

The two scale ValDisplays are constants in Igor (`Constant K_ZPiezoScale =
62`, Setup1_STMBJ.ipf:26-28) and read-only here too; change
`cal.piezo_nm_per_volt` in a config file if you re-calibrate the piezo.

**Piezo offset (nm)** is the one control on this tab Igor did not have.
`G_PiezoOffset_nm` existed (Functions_STMBJ.ipf:44, with the comment "MUST
BE LARGER THAN EXCURSION SIZE when used with unipolar piezos") but was only
settable from the command line. Start Writing parks the piezo at this
height; on a unipolar piezo it is the number that gives a pull somewhere
to go, so it belongs on the panel.

**Enable rules** (Igor's `disable=` lists at Controls_STMBJ.ipf:159-166 and
210-217): while the output task is running, Start Writing and Reset DAQ
Devices are greyed, the five entries are locked, the slider and the
Background Sampling box are live. Kill Tasks reverses all of it. Reset
DAQ Devices refuses while the task is running (`Kill Tasks before resetting
the DAQ devices`), since resetting a card under an open task would
invalidate the tracked piezo position.

### Inputs tab

| Igor name | Title | Bound to / does |
|---|---|---|
| `PullRate_Inputs` | Pull Rate (nm/s) | `cfg.ramp.pull_rate_nm_per_s`; next Start |
| `Excursion_Inputs` | Excursion (nm) | `cfg.ramp.pull_length_nm`; next Start (constant mode; the ramp modes overwrite it, chapter 41) |
| `EngageG_Inputs` | Contact Threshold (G0) | `cfg.ramp.engage_g0`; next engage |
| `EngageStep_Inputs` | Contact step size (nm) | `cfg.ramp.approach_step_nm`; next engage |
| `SeriesR_Inputs` | Series R (Ohm) | `cfg.keithley.series_resistance_ohm`; used only with Keithley-sourced bias (chapter 20) |
| `ZerCutoff_Inputs` | Zero Cutoff (G0) | `cfg.ramp.break_g0`; next trace (selection and histogram floor) |
| `SmashFreq_Inputs` | Smash Freq. | `cfg.ramp.smash_every`; next attempt (0 disables) |
| `SmashIn_Inputs` | Smash In | `cfg.ramp.smash_in_nm` |
| `SmashOut_Inputs` | Smash Out | `cfg.ramp.smash_out_nm` |
| `SaveBias_Inputs` | Save Bias | `opts.save_bias`; recorded in the file header |
| `SaveCurrent_Inputs` | Save Current | `opts.save_current`; recorded |
| `SavePiezoWave_Inputs` | Save Piezo Wave | `opts.save_piezo_wave`; recorded |
| `SaveSense_Inputs` | Save Sense | `opts.save_sense`; recorded |
| `SaveHist_Inputs` | Save Hist | `opts.save_hist`; writes the histogram CSV per block |
| `VoltageRead_Inputs` | VoltageRead | `opts.voltage_read`; recorded |

Igor's default Contact Threshold was 5 G0 (`G_ConductanceThreshold = 5`),
which at gain 10⁶ and 100 mV is 38.7 V at the ADC and unreachable; the
package's default is 0.5 G0 and a railed preamp also counts as contact.
Chapter 02 argues this out. If you type 5 here you get what Igor got: the
approach loop climbs to the piezo ceiling and refuses.

The five Save boxes did real work in Igor's `SavePullOut` — each selected a
wave to write into the `.ibw` block. The HDF5 session file always stores
both raw channels for every accepted trace, so nothing is lost by leaving
them unticked; they are written into the file header so an archived run
says what Igor would have kept. Save Hist is the exception: it controls
whether each histogram block is also written as a CSV (chapter 47).

Two controls that Igor created on this tab are not reproduced:
`CounterElectrodeCheck_EChem` and `CounterElectrodeSetVar_EChem`
(Windows_STMBJ.ipf:334-338). They were created `disable=1` and no tab
procedure ever enabled them — their names end in `_EChem`, which none of
the `ControlNameList` filters matched — so they were invisible in Igor.
The live counter-electrode controls are on the Electrochemistry panel,
chapter 44.

### Options tab

Four sub-tabs, each with one checkbox and its numbers. **The four
checkboxes are mutually exclusive**: ticking one clears the other three,
as `RampOptionsCheckProc` (Controls_STMBJ.ipf:343) did, and with none
ticked the next Start Measurement is a constant-bias run. The selection is
read at Start, not before.

| Sub-tab | Igor name | Title | Bound to |
|---|---|---|---|
| Push-Pull | `PushPullCheck_PushPullRamps` | Push-Pull | `opts.push_pull_check` |
| | `NoPPCyclesSetvar_PushPullRamps` | Number of cycles | `cfg.push_pull.cycles` |
| | `PPInitialPull_PushPullRamps` | Initial Pull (nm) | `cfg.push_pull.initial_pull_nm` |
| | `PPFinalPull_PushPullRamps` | Final Pull (nm) | `cfg.push_pull.final_pull_nm` |
| | `PushPullLength_PushPullRamps` | Push-Pull length (nm) | `cfg.push_pull.push_pull_nm` |
| | `HoldLength_PushPullRamps` | Hold length (nm) | `cfg.push_pull.hold_nm` |
| IV | `IVCheck_IVRamps` | IV | `opts.iv_check` |
| | `IVSignPopup_IVRamps` | Sign: (+ / − or − / +) | `cfg.iv.positive_first` (item 2 = True) |
| | `MaxBias_IVRamps` | MaxBias (V) | `cfg.iv.max_bias_v` |
| | `IVInitPull_IVRamps` | Initial Pull (nm) | `cfg.iv.init_pull_nm` |
| | `IVIFinPull_IVRamps` | Final Pull (nm) | `cfg.iv.final_pull_nm` |
| | `IVCapLength_IVRamps` | Cap length (nm) | `cfg.iv.cap_nm` |
| | `IVRampLength_IVRamps` | Ramp length (nm) | `cfg.iv.ramp_nm` |
| AC | `ACHoldCheck_ACHoldRamps` | AC Hold | `opts.ac_hold_check` |
| | `ACAmp_ACHoldRamps` | Amp (V) | `cfg.ac_hold.amp_v` |
| | `ACFreq_ACHoldRamps` | Freq (kHz) | `cfg.ac_hold.freq_khz` |
| | `ACInitPull_ACHoldRamps` | Initial Pull (nm) | `cfg.ac_hold.init_pull_nm` |
| | `ACHoldLength_ACHoldRamps` | Hold length (nm) | `cfg.ac_hold.hold_nm` |
| | `ACFinalPulll_ACHoldRamps` | Final Pull (nm) | `cfg.ac_hold.final_pull_nm` |
| High bias hold | `HBHoldCheck_HBHoldRamps` | High Bias Hold | `opts.hb_hold_check` |
| | `HBBias_HBHoldRamps` | Hold bias (V) | `cfg.hb_hold.hold_bias_v` |
| | `HBInitPull__HBHoldRamps` | Initial Pull (nm) | `cfg.hb_hold.init_pull_nm` |
| | `HBFinalPulll_HBHoldRamps` | Final Pull (nm) | `cfg.hb_hold.final_pull_nm` |
| | `HBHoldLength_HBHoldRamps` | Hold length (nm) | `cfg.hb_hold.hold_nm` |
| | `HBCapIN__HBHoldRamps` | Cap Length IN (nm) | `cfg.hb_hold.cap_in_nm` |
| | `HBCapFIN__HBHoldRamps` | Cap Length FIN (nm) | `cfg.hb_hold.cap_fin_nm` |

The Sign popup is Igor's `IVSignPopup` (Controls_STMBJ.ipf:445): the first
item set `G_IVSignFlag = 0`, the second `= 1`. The package names the flag
for what it does, `positive_first`, because Igor negated the whole bias
wave before applying the flag (chapter 12): the default `+ / −` sweeps to
the *negative* apex first. Igor's push-pull globals had no defaults (they
were set from the panel); the values shown are the package's working
defaults, and `validate()` warns if the push-pull length does not exceed
the initial pull, which would mean the junction is never re-formed.

The lengths of the AC cap (`cfg.ac_hold.cap_nm`, Igor `G_ACCapLength`)
have no panel control in Igor either; edit the config file.

## Background Sampling (Beep is ON)

**Igor:** `CheckBox OnCheck`, `BkgdSamplingCheckProc`. **Now:** bound to
`opts.bkgd_sampling`, calls `set_background_sampling`. Live only while the
output task runs. Reads **Fast Read Wave Size** samples every 0.25 s, feeds
the three readouts and the HighRes window, and rings the terminal bell when
|I| exceeds 0.15 µA (`GuiOptions.beep_current_ua`). The read runs only when
the command queue is idle, so it never collides with a measurement.
Chapter 41, step 2.

## Keithley Controls

**Igor:** `GroupBox box10105`. Every control here talks to the Keithley
428 over GPIB; in simulate the commands are recorded, on hardware they go
to `cfg.keithley.resource` (`GPIB0::22::INSTR`, Igor's `ibdev={0,22,...}`).
If the GPIB open failed at launch, each of these refuses with `the Keithley
428 is not connected` and the rest of the panel is unaffected.

| Igor name | Title | Igor proc | Does now |
|---|---|---|---|
| `KeithleyBias` | Bias | `KeithleyBias` | `B1X` / `B0X`; `cfg.keithley.enabled`; Tip Bias then quantised to 5 mV |
| `ZeroCheckBox` | Zero Check | `ZeroCheckProc` | `C1X` / `C0X`; `opts.zero_check`; re-ticked by Kill Tasks |
| `ZeroCorrectButton` | Zero Correct | `ZeroCorrectProc` | `C2X` |
| `SuppressCheckBox` | Suppress I | `CurrentSuppressCheckProc` | `N1X` / `N0X`; `opts.suppress_on` |
| `FindSuppressButton` | Find Suppress | `FindSuppress` | bias to 0, `keithley.find_suppress`, bias back; chapter 41 step 5 |
| `setvar43` | Gain ( log(V/A) ) | `SetGain` | `H6R<g>X`; `cfg.keithley.gain_exponent` **and** `cfg.cal.preamp_gain_v_per_a = 10^g` |
| `SuppressSetVar` | Suppress I value | `SetCurrentSuppress` | `H8S<amps>,0X` with amps = const × 10^(3−g) µA; `cfg.keithley.suppress_const` |

Gain deserves a sentence. Igor's `SetGain` (Controls_STMBJ.ipf:290) sent
the gain to the box and recomputed `G_CurrentVoltConversion = 10^(6-gain)`
for the readouts. The package keeps the box's exponent and the number every
conductance divides by as two separate fields, and `validate()` warns when
they disagree because a mismatch scales every histogram by a power of ten.
The panel's Gain entry therefore writes both at once, so they cannot
disagree from here. The same entry appears on the Electrochemistry panel
(Igor had it in both places) and both write the same fields.

The Suppress I value is stored and shown as Igor's *constant*; what the
amplifier receives is `const × 10^(3 − gain)` µA, Igor's
`G_CurrentSuppress` (Controls_STMBJ.ipf:473). Find Suppress writes the
result back in the same units, and changing Gain re-sends the suppress at
its rescaled value, as `SetGain` did (lines 306-310).

## Actuator Controls

**Igor:** `GroupBox ActuatorGroupBox`; the two step buttons live in
NanoPZ_Actuator_Functions_STM.ipf:6-23 and send `0MO` then `0PR±n` over
COM1 at 19200 baud.

| Igor name | Title | Igor proc | Does now |
|---|---|---|---|
| `StepSizeSetVar` | Step Size | — | `cfg.actuator.step_size`; Start Approach forces it to 5 |
| `ActuatorCounter_Valdisp` | (counter) | ValDisplay of `G_ActuatorCounter` | `opts.actuator_counter`, steps of the last approach |
| `StartApproachButton` | Start Approach | `ApproachButton` | `RigController.approach`; chapter 41 step 3 |
| `StepTogether` | Step closer | `StepActuatorCloser` | one step in |
| `StepOpen` | Step apart | `StepActuatorApart` | one step out |

With the output task running, a step goes through `Rig.coarse_step`, which
refuses unless the fine piezo is retracted below
`limits.coarse_step_max_piezo_v` (0.1 V, 6 nm) — the interlock that stops
a coarse step driving an extended tip into the sample — and counts against
`limits.max_coarse_steps`. With the output task off (no piezo energised)
the step goes straight to a fresh `make_actuator(cfg)`, as Igor's buttons
did at any time. Igor had no interlock at all.

## Piezo Controls

**Igor:** `GroupBox PiezoGroupbox`.

| Igor name | Title | Igor proc | Does now |
|---|---|---|---|
| `MoveZIn` | Step closer | `PiezoStepCloser` | `piezo_step(+Z)` — extend by Z nm |
| `MoveZStepSize` | Z (nm) | — | `opts.piezo_step_nm`, the step size |
| `MoveZout` | Step apart | `PiezoStepApart` | `piezo_step(−Z)` — retract by Z nm |
| `SliderPos_Z` | (slider) | `SetPiezoBiasFromSlider` | `piezo_goto(volts)` on release |

The slider's value is the **voltage at the DAQ output**, not a distance —
Igor's own comment above `SetPiezoBiasFromSlider` (Controls_STMBJ.ipf:376)
says so. Its range is `limits.piezo_ao_min_v .. piezo_ao_max_v`, 0 to 10 V
on this unipolar piezo, where Igor's was −10 to +10 for a bipolar one
(chapter 02 on why the difference is load-bearing). It applies on mouse
release (Igor's `live=0`), and every fine-piezo move made anywhere — a
step, an approach, a pull — moves the slider to follow, so it always shows
where the piezo is. Closer is +nm: extension is the positive direction on
this rig and a pull descends.

## The readouts

| Igor name | Title | Igor variable | Shows |
|---|---|---|---|
| `CurrentReadOut` | I (uA) | `G_CurrentSamplingReadoutVal` | mean current of the last background read, in µA |
| `JunctionVoltageReadout` | V (mV) | `G_JunctionVoltage` | mean junction voltage, sign-corrected, in mV |
| `PiezoVoltReadout` | Piezo | `G_PiezoBiasSamplingReadoutVal` | the commanded piezo voltage |

Igor's Piezo readout came from the second card's sense input
(`LowResPiezoIn`); this rig has one card and no sense line, so the readout
is the tracked command voltage — the same number the interlock trusts.
Chapter 45 says the same about SenseInDisplay.

## Saved, Tip Bias, Stop #, Start Measurement, Attempts, +1

| Igor name | Title | Igor proc / variable | Does now |
|---|---|---|---|
| `Saved_setVar` | Saved | `G_PullOutNumber` | `opts.pull_out_number`; editable |
| `TipBias` | Tip Bias (mV) | `SetTipBiasVoltage` | `set_tip_bias`: `cfg.ramp.bias_v` (V), applied immediately |
| `StopNo_setVar` | Stop # | `G_StopNumber` | `opts.stop_number`; editable |
| `StartMeasurementButton` | Start Measurement | `StartMeasurement` | `start_measurement(single=False)` |
| `setvar17` | Attempts | `G_PullOutAttempt` | `opts.pull_out_attempt`; editable |
| (new) | Stop (Alt) | the Alt key | `request_stop` |
| `SingleAttemptButton` | +1 | `MakeAttempt` | `start_measurement(single=True)` |

Tip Bias is stored in volts (`cfg.ramp.bias_v`) and shown in millivolts.
With **Bias** ticked in Keithley Controls it is quantised down to a
multiple of 5 mV and sent to the box as well (`SetTipBiasVoltage`,
Controls_STMBJ.ipf:425-427). A value beyond `limits.bias_max_v` (0.5 V by
default) is refused with `tip bias +900.0 mV exceeds the limit of +/-500 mV
(limits.bias_max_v); raise it deliberately in the config if the experiment
needs it` — Igor had no software bias limit, and `rungo`'s sweep to −1.1 V
needs the limit raised on purpose (chapter 46). A second `TipBias_Inputs`
entry existed on Igor's Inputs tab bound to the same global; one is enough.

The status line under this group is new: `idle`, or `running: <command>`
while the worker is busy, during which Start Measurement, +1, Start
Approach, Find Suppress, Start Writing and Reset DAQ Devices are greyed.
Everything else — Stop, Kill Tasks, the entries — stays live.

## Controls Igor created but never showed

Besides the two `_EChem` controls, the Igor panel macro creates `check08`,
`setvar15`, `setvar5` and `setvar7` (Windows_STMBJ.ipf:234-239), all
`disable=1`, untitled and unbound: leftovers of an earlier layout. They are
not reproduced.

## Tooltips, and the Button map

Hover over any of the above. A button's tooltip is built by
`stmgui.controller.describe_command` from the method it calls: the
docstring (what happens, which Igor procedure), then `Python:` with the
controller method's file and line, the worker-thread `_impl` that does the
work, `Igor:` the procedure, and `Calls:` every `stmlab` function reached,
each as `file:line name`. Entries and checkboxes show the Igor global, the
attribute they write, the display scale if any, and the limits. Igor only
had a `help=` string on Start Writing.

The same information for every control at once is the **Button map** —
the **"Which code runs this?"** button beside the status line at the
bottom of the panel, or **Windows → Button map**: one row per command in
`controller.COMMAND_MAP`, with the line numbers taken from the loaded code
(press Refresh after editing). It is the table in chapter 50, kept alive.
**Right-click** any control (macOS: Control-click or two-finger tap) and
the **Inspector** window opens with that control's text, staying open
where a tooltip would vanish. The orange hint line under the status line
says so.
