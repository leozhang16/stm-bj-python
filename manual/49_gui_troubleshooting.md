# 49. Deviations, limitations, troubleshooting

*Igor: Controls_STMBJ.ipf and Functions_STMBJ.ipf throughout. Modules: `stmgui/controller.py`, `stmlab/safety.py`, `stmlab/approach.py`.*

## Deviations from Igor, and why

Every one of these is deliberate and is called out in a docstring at the
point it happens. The list is complete as far as a line-by-line comparison
of `controller.py` with the Igor control procedures goes.

| What | Igor | Here | Why |
|---|---|---|---|
| Stop | polled the Alt key inside loops | a Stop button, plus Alt and Escape | a mouse-only operator; same flag, same semantics |
| Session calibration | none | preamp zero and group delay measured at Start Writing | `validate()` warns without them; the tip is retracted at that moment, which is when they are valid |
| Piezo offset | `G_PiezoOffset_nm`, command line only | an entry on the DAQ tab | on a unipolar piezo it decides whether a pull has room |
| Slider range | −10 … +10 V | `limits.piezo_ao_min_v .. max_v`, 0 … 10 V | the piezo is unipolar; Igor's own defaults would drive it 10 V the wrong way (chapter 02) |
| Contact threshold default | 5 G0 | 0.5 G0 | 5 G0 is 38.7 V at the ADC at gain 10⁶ and unreachable; a railed preamp also counts as contact |
| Coarse steps | no interlock | refused unless the fine piezo is retracted; step budget | a coarse step with the piezo extended drives the tip into the sample |
| Kill Tasks | zeroed the piezo, kept the bias, cleared the task | withdraws both to 0 V | 0 V on both channels is safe regardless of what the tip is near |
| Histogram | complete 100-trace blocks only | also the partial block when a run ends | you see what a short run gave you |
| Data files | one `.ibw` block per 100 traces, conductance only | one HDF5 file per Start press, raw volts on both channels | re-analysis with a corrected calibration is the whole reason to keep raw volts |
| Find Offset V0 / I0 | editable SetVariables | read-only displays | a hand-typed V0 would be applied with no record of where it came from |
| Find Suppress | restored the bias after the sweep | restores it in a `finally` | a failed sweep cannot leave the junction at zero bias |
| CV HighRes on hardware | ran with the output task open, then reset the card | refuses while the task is open | two tasks cannot own `dev1/ao1`; Igor let them collide |
| CV timing | AI and AO started back to back | AI triggered by the AO start | removes the skew for free |
| X piezo | no range check | refuses a move outside 0 … 10 V | the headroom is finite |
| Mode ramps | bias refused nowhere | `limits.bias_max_v` raised to 1.1× the sweep/hold with a warning | the limit exists to protect the constant-bias modes, and lifting it should be visible |
| `LateralEXPT` | slider to 0 *after* the actuator steps | `Rig.withdraw()` *before* them | the interlock needs the fine piezo parked before a coarse step |
| Readout "Piezo" | the second card's sense input | the commanded piezo voltage | the interlock trusts the command, so that is what is shown |
| SenseInDisplay | the second card's sense input | the sense readback when `channels.low_res_device` is set, else the commanded trajectory | one-card rigs have no sense line |
| Inputs-tab `_EChem` controls | created disabled, never enabled | not reproduced | they were invisible in Igor |
| `check08`, `setvar15`, `setvar5`, `setvar7` | disabled placeholders | not reproduced | untitled and unbound |
| Thermocouple sampling | commented out | absent | as in Igor |
| Suppress sweep units | `SetCurrentSuppress(CurSup)` with CurSup in the constant's units | `keithley.find_suppress` sweeps ±1 µA and the constant is derived back | the module translated the sweep in µA; the panel shows Igor's constant either way |

## Limitations

- **Hardware has never met this code.** Every `nidaqmx` call in
  `stmlab/daq.py`, `echem.py` and `xpiezo.py`, the Keithley over
  `pyvisa`, the NanoPZ over `pyserial` and the second card are
  transcriptions of Igor's calls, reviewed but unexercised. The GUI adds
  no hardware code of its own; it inherits this status whole. Chapter 03
  is the bring-up plan.
- **One command at a time.** The worker thread runs commands in order. A
  click during a long command queues behind it, and the status line says
  `running: ...` until then. Only Stop and Kill Tasks act on a running
  command.
- **macOS button colours.** Aqua ignores background colours on native
  buttons; the text colour carries the meaning. On Windows and Linux the
  buttons look like Igor's.
- **No panel screenshots in this manual.** The graph figures are real;
  the panels are described, not pictured, because the build machine did
  not permit screen capture. Launch `--simulate` to see them.
- **Window positions** are not remembered between launches.
- **The tooltip on a spinbox arrow** may not appear on every platform;
  hover the entry itself.

## Config warnings at Start Writing

`validate()` runs at Start Writing and at every Start Measurement; the
History shows each warning prefixed `config:`. What they mean:

| Warning begins | Meaning | Do |
|---|---|---|
| `hv_amp_gain is unknown` | the piezo driver gain is not recorded; limits are enforced at the DAQ output | nothing, if `cal.piezo_nm_per_volt` is an end-to-end number (it is, 62 nm/V from Igor) |
| `current_zero_v is 0` | the preamp zero has not been measured | it will be, at Start Writing; if you turned that off, run `calibrate.measure_zero` |
| `1 G0 produces ... V, above the preamp saturation limit` | the metallic-contact region will read railed | normal at gain 10⁶ and 100 mV; the science is below 1 G0 |
| `engage threshold ... needs ... V at the ADC but the input saturates` | contact can only be detected by saturation | lower Contact Threshold, or the gain |
| `keithley.gain_exponent = g programs ... but cal.preamp_gain_v_per_a is ...` | the box and the arithmetic disagree | set Gain from the panel, which writes both |
| `push-pull: push_pull_nm ... does not exceed initial_pull_nm` | every cycle holds below the contact point | raise Push-Pull length above Initial Pull |
| `a ... nm pull uses ...% of the usable piezo range` | contact must be made high in the range | raise Piezo offset, or approach higher |
| `requested ... Hz but the card granted ... Hz` | delta-sigma rate rounding | nothing; every time axis uses the granted rate |
| `RAISING limits.bias_max_v from ... to ...` | a mode's sweep or hold exceeds the everyday limit | expected for IV / AC / HB hold; check the number is what you meant |

A `ConfigError` (not a warning) stops the command; its text names the
field: bias beyond the limit, bias of 0 V, a pull longer than the piezo
range, an engage threshold below the break threshold, a spike that does
not fit in the pull, a sample rate that gives fewer than 100 points.

## Symptom, cause, fix

| Symptom | Cause | Fix |
|---|---|---|
| `gui.py` prints three install lines and exits | this Python has no Tk | use the python.org build or `brew install python-tk@3.12`, recreate `.venv` |
| `ModuleNotFoundError: matplotlib` | wrong interpreter | run with `./.venv/bin/python`, not `python` |
| `Keithley 428 not available: ...` at launch | pyvisa missing, no GPIB interface, wrong address | install pyvisa and NI-488.2; check `keithley.resource`; the rest works meanwhile |
| `the output task is not running -- press Start Writing first` | a button that needs the rig, before Start Writing | Start Writing |
| `the Keithley 428 is not connected` | see above | connect, relaunch |
| `Background sampling needs the output task` | ticked before Start Writing | Start Writing first |
| `background sampling stopped: ...` | a read raised (card error) | check the History for the underlying error; Kill Tasks, Start Writing |
| `Kill Tasks before resetting the DAQ devices` | Reset with the task open | Kill Tasks first |
| `no coarse actuator configured (actuator.kind == 'none')` | one-card rig with no NanoPZ in the config | set `actuator.kind` to `nanopz` with the port, or approach by hand |
| `refusing coarse step ...: piezo is at ... V, must be below 0.100 V` | fine piezo extended | slider to 0 (or Step apart) before any coarse step |
| `coarse approach took 2000 steps without finding current` | actuator direction, wiring, or the tip is far away | check the NanoPZ direction and the current path |
| `bias ... V exceeds limit +/-... V` or `tip bias ... exceeds the limit` | above `limits.bias_max_v` | raise the limit in a config file, deliberately |
| `piezo command ... V clamped to ... V` (warning) | a move beyond the piezo range | the move was clamped; expected during smash near the floor |
| `refusing pull: contact at ... V, a ... nm pull needs ... V` | contact too low in the range for the excursion | `recover_headroom` backs the actuator off automatically up to five times; if it still fails, raise Piezo offset or approach higher |
| `could not separate contacts: piezo is at the ... V floor` | in contact at the bottom of the range | back the coarse actuator off (Step apart) |
| `could not make contact: piezo is at the ... V ceiling` | surface out of reach of the fine piezo | Start Approach |
| `cannot make contact: ...` ends a run | engage failed and the actuator could not help | see the two rows above; the file is closed cleanly |
| `vzero: piezo at the ceiling with no contact` | Find Offset before the approach | Start Approach first |
| `vzero: flat I(V) -- no contact, or a railed preamp` | no measurable current, or every point railed | check contact and gain |
| `suppress sweep produced a flat response` | Keithley in zero check, or disconnected | untick Zero Check |
| `no low-res device configured (channels.low_res_device is None)` | EChem or X piezo on a one-card config | set `channels.low_res_device` if you have the card; `--simulate` pretends one |
| `press Counter Electrode ON first` | typed a gate bias before ON | ON, then the bias |
| `CV HighRes drives the junction-bias channel; Kill Tasks first` | CV HighRes with the task open, on hardware | Kill Tasks, CV, Start Writing |
| `CV ramp too short; slow the scan rate or raise cv_rate_hz` | fewer than four samples per leg | as it says |
| `lateral move to ... nm needs ... V, outside [0.0, 10.0] V` | X piezo range | MoveXPiezoToZero, re-centre |
| `Saved (n) >= Stop # (m): nothing to do` | Stop # not above Saved | raise Stop # |
| `Catastrophic failure: 100000 attempts` | Igor's own guard: the loop never accepted a trace | something is wrong with contact or selection; look at PullOutLowG |
| a run with Attempts climbing and Saved not | every trace rejected by `TestTrace` | watch PullOutLowG: no plateau (tip needs a smash, or the gain is wrong) or no tunnelling tail (Zero Cutoff too low) |
| constant beeping | current above 0.15 µA during background sampling | expected in contact; retract, or untick sampling |
| the GUI "hangs" | a long command is running; the status line says which | wait, or Stop; the window is never actually blocked, only greyed |
| Start Measurement greyed | a command is running, or the task is off | see the status line |
| CV buttons greyed | Gain not yet committed this launch | type the Gain (either panel) and press Return |
| no histogram after 60 traces | blocks are 100 traces | finish the run (partial block) or reach 100 |
| `a ramp parameter changed mid-session` | a mode config edited during a run | cannot happen from the panel; from a script, open a new writer |

## If the History shows a traceback

An unexpected exception in a command is logged with its traceback and
posted as `error`; the worker thread survives and the next command runs.
Copy the traceback from the History (select and copy works in the text
widget) — it names the `stmlab` function. Nothing in the GUI needs a
restart after an error; Kill Tasks and Start Writing re-establish a known
output state.

## What to check before the first hardware run

1. `python run.py 01 bringup` — chapter 03, with the card, the scope and a
   resistor, before any tip is near a sample.
2. `keithley.resource` matches the GPIB address, and the gain on the box's
   front panel matches the Gain entry.
3. `actuator.kind`, `port` and `baud` match the NanoPZ, and Step apart
   moves it *apart*.
4. `limits.piezo_ao_max_v` and `cal.piezo_nm_per_volt` match the driver
   box and the piezo; Piezo offset larger than Excursion.
5. Start Writing with the tip far from the sample; watch the HighRes
   window read noise around zero; Step closer and apart on the piezo and
   watch the readout follow.
6. Only then Start Approach.
