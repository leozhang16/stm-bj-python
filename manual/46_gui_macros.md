# 46. Menus and macros: rungo, LateralEXPT, the X piezo, config files

*Igor: the `Macros` menu, Setup1_STMBJ.ipf:50; `rungo()`, :138; `LateralEXPT()`, :91; `SetupXPiezo` / `MoveXPiezo` / `MoveXPiezoToZero`, NanoPZ_Actuator_Functions_STM.ipf:25-91. Module: `stmgui/app.py` (menus), `stmgui/controller.py` (the macros).*

Igor's menu bar had one item of its own — **Macros → STM Break Junction
Measurement**, which ran `InitializeExperiment` — and two procedures that
were only ever typed into the command line: `rungo()`, the bias series,
and `LateralEXPT(...)`, the monolayer walk. The rebuild has four menus.
This chapter is what is in them.

## File

| Item | Does |
|---|---|
| Load config JSON... | `RigConfig.from_json` into the live config; every panel refreshes |
| Save config JSON... | `RigConfig.to_json` of the live config |
| Open data folder | opens `data/<today>/` in the file browser |
| Quit | `controller.shutdown()` — Kill Tasks, release the Keithley — then closes |

A saved config is the complete `RigConfig` — channels, limits, ramp,
calibration, actuator, the four mode configs, vzero, keithley, echem,
xpiezo, the simulate flag and notes — as indented JSON. It is the same
file `run.py <experiment> --config my.json` reads and the same dictionary
every session file carries as `config_json`, so a config tuned at the
panel runs unchanged from the command line, and a command-line config
loads unchanged into the panel. What it does *not* contain is
`GuiOptions`: Saved, Stop #, the checkbox states, Piezo offset, Fast Read
Wave Size. Those are panel state, not rig description, and start fresh
each launch (chapter 48 lists them).

Loading replaces every section of the live config in place, so the
controller, the open `Rig` and the tracker all see the new values at
once. Load before Start Writing; a config loaded under a running task
takes effect at the next command that reads each field, which is
consistent but rarely what you meant.

## Macros

| Item | Igor | Does |
|---|---|---|
| STM Break Junction Measurement | `InitializeExperiment` | raises the main panel |
| Voltage Offset panel | `Voltage_Offset()` | raises it (chapter 43) |
| Electrochemistry panel | `EChem()` | raises it (chapter 44) |
| rungo()  bias series... | `rungo()` | the bias campaign, below |
| LateralEXPT(Z, X, XFreq)... | `LateralEXPT` | the monolayer walk, below |
| MoveXPiezo(nm)... | `MoveXPiezo` | relative lateral move |
| MoveXPiezoToZero() | `MoveXPiezoToZero` | lateral piezo to 0 V |
| Stop (Alt) | `GetKeyState` | `request_stop` |

### rungo(): the bias series

**Igor** (Setup1_STMBJ.ipf:138-179) built three waves of fourteen entries:
`bias` = −100, −200, … −900, then −100, −900, −1000, −1100, −100 mV;
`StopNumWave[i] = (i+1) × 1000 + 1`; `StartNumWave = StopNumWave − 1000`.
It then found where the current `G_PullOutNumber` fell in `StartNumWave`
(`FindLevel/EDGE=1`) and, from that index on, set `G_TipBias` and
`G_StopNumber` and called `StartMeasurement` — so a campaign interrupted
after 3400 saved traces resumed at step 3, bias −400 mV, and ran it to
4001. Two `PiezoStepApart` calls and a `FindSuppress` per step were
commented out. Alt between steps aborted. At the end: `SaveExperiment`
and `StopWritingTasks`.

**Now**, Macros → rungo() asks two questions — the bias list in mV, comma
separated, pre-filled with Igor's fourteen values, and the number of
traces per bias, pre-filled with 1000 — and calls
`RigController.rungo(biases_mv, counts_each)`. `_rungo_impl` computes the
same `stop_nums` and `start_nums`, resumes from the last step whose start
number is at or below the current Saved (the `FindLevel` logic), and for
each remaining step logs `rungo step i: tip bias ±… mV, stop # n`, sets
Tip Bias through the same `_set_tip_bias_impl` the panel entry uses, sets
Stop # (the panel entry follows), and runs `_measure_impl` — a full Start
Measurement, with its own session file per step. Stop ends the campaign
after the current step's attempt (`rungo aborted at step i`); otherwise
`rungo complete`.

Two things to set first:

- **The bias limit.** Igor's list reaches −1100 mV; the package's
  `limits.bias_max_v` is 0.5 V and `set_tip_bias` refuses beyond it
  (chapter 42). Raise it deliberately in a config file (`"bias_max_v":
  1.2`) before a full `rungo`, or give a shorter list. The campaign stops
  with the refusal in the History at the first step it cannot apply.
- **Saved.** The resume logic reads it. To start a fresh campaign, set
  Saved to 1; to resume, leave it.

`experiments/08_bias_series` is the command-line version of the same
campaign, with one file per bias and a `--resume` flag that reads the
files instead of a counter; chapter 17. The GUI's `rungo` does not read
those files and they do not read the GUI's.

### LateralEXPT(ZDistance, XDistance, XFreq): the monolayer walk

**Igor** (Setup1_STMBJ.ipf:91-136) looped until `G_StopNumber` reached
12201: add `XFreq` to `G_StopNumber`; print the X piezo voltage;
`Delay(500)`; `StartMeasurement` (so `XFreq` traces at this site); three
`StepActuatorApart` calls with `Delay(100)` after each (withdraw in Z);
`MoveXPiezo(XDistance)` and `Delay(100)`; set `G_ActuatorStepSize = 5`,
`SetPiezoBiasFromSlider("", 0, 0)` (fine piezo to 0 V), `ApproachButton`
(coarse approach back into current), `Delay(100)`. `ZDistance` set the
actuator step size for the withdraw. Alt broke the loop.

**Now**, Macros → LateralEXPT asks for ZDistance (actuator steps per
withdraw, pre-filled 10), XDistance (nm per site, pre-filled 200) and
XFreq (traces per site, pre-filled 250), and calls
`lateral_expt(z, x, x_freq)` with Igor's `final_stop_number` of 12201.
`_lateral_impl` needs the output task and mirrors the loop: Stop # =
Saved + XFreq; log the X piezo voltage; `_measure_impl`; `Rig.withdraw()`
(fine piezo to park — the interlock needs it before a coarse step, which
Igor's `SetPiezoBiasFromSlider(0)` only did *after* the withdraw); three
`Rig.coarse_step(closer=False)` with 0.1 s pauses on hardware; the X
piezo move; step size 5; fine piezo to 0 V; bias re-applied
(`coarse_approach` watches the current, so the bias must be on);
`_approach_impl`; step size back to ZDistance. Stop ends it after the
current site. The final History line is `LateralEXPT done at Saved = n`.

Every site's traces go into that site's session file (one per
`_measure_impl` call), whose `igor_globals_json` records the Stop # of the
site, but not the X position — `experiments/07_lateral_monolayer`, the
command-line version (chapter 16), writes `x_position_nm` into each site
file and is the better tool for a map you intend to analyse by position.
The macro is here because Igor had it.

### MoveXPiezo(nm) and MoveXPiezoToZero()

**Igor** (NanoPZ_Actuator_Functions_STM.ipf:25-91): `SetupXPiezo` created
an output task on `dev2/ao0` with a 0 … 10 V range and drove it to 0;
`MoveXPiezo(XDistance)` added `XDistance` to `G_XPiezoPosition` and wrote
`position / K_XPiezoScale` volts (522 nm/V); `MoveXPiezoToZero` wrote 0.
`Setup1_STMBJ.ipf:86-88` called setup, stop and zero at load. No range
check.

**Now**: the first lateral command creates `stmlab.xpiezo.make_xpiezo
(cfg).setup()` — `SimulatedXPiezo` in simulate, otherwise an `nidaqmx`
task on `{channels.low_res_device}/{xpiezo.channel}` over
`xpiezo.min_v .. max_v` (0 … 10 V) driven to 0 — and keeps it until Kill
Tasks. MoveXPiezo asks for a relative distance in nm and calls
`XPiezo.move_nm`, which computes the target voltage at
`xpiezo.nm_per_volt` (522) and **refuses** a move outside the channel's
range with `lateral move to … nm needs … V, outside [0.0, 10.0] V.
Re-centre the sample or zero the X piezo.` — Igor did not check, and
12 200 accumulated 200 nm steps is 4.7 V of a 10 V range, so the headroom
is real but finite. MoveXPiezoToZero calls `XPiezo.zero`. Both post an
`xpiezo` event with the new position; the History logs `X piezo at … nm
(… V)`. Without a second card configured, `XPiezoError: no low-res
device configured (channels.low_res_device is None); the X piezo lives on
the second card`.

### Stop (Alt)

The same `request_stop` as the Stop button, the Alt keys and Escape
(chapter 41). It is in the menu so it can be reached when the main panel
is behind a graph.

## Windows

The nine graph windows by their Igor names — HighRes, PullOutGvsE,
PullOutLowG, AuAuConductanceLevel, SenseInDisplay, LogHistOfBlock, Izero,
Izero_Time, CyclicVoltammogram — then History, then **Button map**.
Selecting one creates it if it has never been shown and raises it.
Chapter 45 for the graphs and History.

**Button map (control → Python → Igor)** is one window listing every
command: the panel control, the `RigController` method with its file and
line, the worker-thread `_impl` with its file and line, the Igor procedure
it mirrors, and each `stmlab` function it reaches with file and line. It
is generated from `stmgui.controller.COMMAND_MAP` and the loaded code when
it opens; **Refresh** regenerates it. Hovering a control on a panel shows
the same entry as a tooltip.

## Help

**Button map** — the same window, for people who look in Help first.
**About / where the manual is** shows the package path, the manual
(`STMLAB_GUI_Manual.pdf`, source `manual/4x_gui_*.md`), and the data path.

## Keyboard

| Key | Does |
|---|---|
| Alt (left or right) | Stop |
| Escape | Stop |
| Return, in an entry | commit the value |
| Tab / click elsewhere | commit the value (focus-out) |
| Up / Down, in a spinbox entry | step by Igor's increment |

There are no other accelerators. Igor's "Alt" was `GetKeyState(0) == 2`
polled inside the loops; here it is a key binding on every window that
sets the same flag the loops poll.

## What the menus do not do

There is no "save experiment" — Igor's `SaveExperiment` wrote the whole
`.pxp`; here every result is already on disk in `data/` as it is taken
(chapter 47), and the config can be saved from File. There is no
"load data" — analysis happens outside the GUI, with `storage.Session`
and the experiments' analysis scripts (chapters 10-17). And there is no
preferences dialog: everything adjustable is a config field or a panel
control, and both round-trip through the JSON.
