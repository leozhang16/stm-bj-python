# 48. How stmgui is built

*Module: `stmgui/` — `state.py`, `controller.py`, `widgets.py`, `graphs.py`, `panels/`, `app.py`. Tests: `tests/test_gui_controller.py`, `tests/test_gui_app.py`.*

This chapter is for the day something needs changing: a new control, a
new graph, a different data path, a hardware quirk. It describes the
design, the one rule that holds it together, and three walkthroughs.

## The shape

```
stmgui/app.py            App: builds everything, the menus, the event pump
stmgui/panels/           MainPanel, VoltageOffsetPanel, EChemPanel, HistoryWindow
stmgui/graphs.py         GraphSet and the nine GraphWindow classes
stmgui/widgets.py        SetVariable, ValDisplay, CheckBox, button, groupbox, Tooltip
        |  Tk thread: reads state, queues commands, drains events
        v
stmgui/controller.py     RigController: one worker thread, owns the Rig, posts events
stmgui/state.py          GuiState = RigConfig + GuiOptions; PARAMS, the binding table
        |
        v
stmlab/                  the translated procedures; unchanged
```

**The one rule:** the controller never imports Tk, and the panels never
touch the `Rig`. A click becomes a command queued to the controller's
worker thread; the worker posts `(kind, payload)` events; the Tk thread
drains them on a timer and fans them out to the panels and graphs. Every
consequence in this chapter follows from that rule.

Why: Tk is single-threaded and a DAQ call blocks for the length of a
waveform. Igor ran everything on its one GUI thread and polled the Alt key
to get a word in edgeways; a Python GUI that did the same would freeze
for the duration of every pull and could not draw a trace while the next
was being taken. Putting the rig on its own thread fixes that, and putting
it on exactly *one* thread with a queue means two buttons can never reach
the card at once — there is no lock to forget, because there is nothing
to contend.

## state.py

**`GuiOptions`** is a dataclass of the Igor globals that have no home in
`RigConfig` — the things a panel needs that do not describe the rig:

- DAQ tab: `fast_read_wave_size`, `piezo_offset_nm`,
  `sense_scale_nm_per_v`; piezo `piezo_step_nm`.
- Counters: `pull_out_number` (Saved), `stop_number`, `pull_out_attempt`,
  `actuator_counter`.
- Save flags: `save_bias`, `save_current`, `save_hist`, `save_sense`,
  `save_piezo_wave`, `voltage_read`.
- Keithley checkboxes: `zero_check`, `suppress_on`.
- Mode checkboxes: `push_pull_check`, `iv_check`, `ac_hold_check`,
  `hb_hold_check`, with `mode()` and `select_mode(name, on)` implementing
  `RampOptionsCheckProc`'s exclusivity.
- Voltage Offset: `vzero_check`, `vzero_mv`, `izero_ua`.
- Background sampling: `bkgd_sampling`, `beep_current_ua`.
- Readouts: `current_readout_ua`, `junction_voltage_mv`, `piezo_readout_v`.
- `data_dir`, and `calibrate_on_start_writing`.

**`GuiState`** is a `RigConfig` and a `GuiOptions` together. Everything
the panels read or write is reachable from it by a dotted path.

**`Param`** is one panel control's binding: the Igor name, the dotted
`path`, the `kind` (`float`, `int` or `bool`), the panel `title`, Igor's
`limits` triple, a printf `fmt`, and a display `scale` (Tip Bias is
stored in volts, shown ×1000). `get(state)` walks the path and applies
the scale; `set(state, value)` coerces, clamps to the limits, divides by
the scale, stores, and returns what was stored in display units so a
widget can show the clamped value.

**`PARAMS`** is the dictionary of every binding, keyed by Igor name. It is
the single place a control's meaning is defined, and chapter 51 is
generated from it. **`simulated_state()`** is the `--simulate` starting
point.

## controller.py

**`RigController(state, events=None, start_worker=True)`** holds the
`Rig` (`None` until Start Writing), the Keithley (`amp`), the counter
electrode (`gate`), the X piezo (`xp`), the `VzeroTracker`, the histogram
block, and the bookkeeping (`izero_history`, `last_suppress`, `last_cv`,
`last_trace`, `session_files`, `rejections`). It starts a daemon thread
running `_worker`.

**Commands.** Every public method — `start_writing`, `kill_tasks`,
`reset_daq`, `piezo_step`, `piezo_goto`, `set_tip_bias`, `set_gain`,
`set_suppress_const`, `zero_check`, `zero_correct`, `suppress_enable`,
`keithley_bias`, `find_suppress`, `find_offset`, `step_actuator`,
`approach`, `start_measurement`, `counter_electrode_on`,
`set_counter_electrode`, `start_cv`, `move_xpiezo`, `zero_xpiezo`,
`rungo`, `lateral_expt`, `connect_instruments` — is a one-liner that
queues its `_impl` through `_run(name, fn, *args, wait=False)`. With
`wait=False` (the panels) it returns at once; with `wait=True` (the tests
and the macros) it blocks until the command has run and re-raises the
command's exception in the caller. `wait_idle()` queues a no-op and waits
for it, which drains everything ahead of it.

**The worker** loops on the queue with a timeout of `BKGD_PERIOD_S`
(0.25 s). A command sets `busy`, posts `busy` with its name, runs, and in
`finally` clears `busy` and posts `idle`. The expected exceptions —
`SafetyViolation`, `ApproachError`, `ConfigError`, `NotReady`,
`KeithleyError`, `EChemError`, `XPiezoError` — are logged and posted as
`error` events with the command name; anything else is logged with a
traceback and posted the same way, so a bug in one command never takes
the thread down. When the queue times out with nothing to do and
`opts.bkgd_sampling` is set and a rig is open, `_background_read` runs
once — which is why sampling pauses during commands and resumes after
without any explicit start/stop.

**Stop** is one `threading.Event`. `request_stop` sets it; `_measure_impl`,
`_approach_impl`, `_rungo_impl` and `_lateral_impl` clear it when they
begin and check it between steps. `kill_tasks` sets it before queueing
itself so that a run ahead of it in the queue ends first.

**Guards.** `_require_rig()` raises `NotReady` with the "press Start
Writing first" message; `_require_amp()` likewise for the Keithley. Every
`_impl` that needs one calls it first, so refusals are uniform and
happen before any hardware is touched.

**Events.** `_emit(kind, payload)` puts a tuple on `events`. The kinds and
payloads:

| Kind | Payload |
|---|---|
| `log` | a formatted log line (from `QueueLogHandler`) |
| `error` | `"<command>: <message>"` |
| `busy`, `idle` | the command name |
| `readout` | `{current_ua, junction_mv, piezo_v, beep}` |
| `highres` | `{voltage_mv, current_ua, piezo_nm}` arrays |
| `piezo` | `{volts, nm}` after any fine-piezo move |
| `writing` | `True` / `False` |
| `bkgd` | `True` / `False` (the checkbox state after `set_background_sampling`) |
| `trace` | `{g0, disp_nm, bias_mv, piezo_nm, accepted, mode, number}` |
| `hist` | `{centres, counts, n, partial}` |
| `izero` | a `VzeroResult` |
| `izero_time` | `(saved_numbers, izero_ua)` arrays |
| `vzero` | `(vzero_mv, izero_ua)` |
| `suppress` | `(new_ua, sweep, readings)` |
| `cv` | list of `CVCycle` |
| `counter` | the actuator step count |
| `saved`, `attempts`, `stop_number` | the counter value |
| `bias` | Tip Bias in mV after `set_tip_bias` |
| `gain` | the exponent after `set_gain` |
| `gate` | counter-electrode mV, or `None` when released |
| `xpiezo` | position in nm |
| `config` | `None`, after a config load |

**`QueueLogHandler`** is a `logging.Handler` attached to the `stmlab` and
`stmgui` loggers at INFO; every log record becomes a `log` event. That is
how the History window sees the package's own messages without the
package knowing about the GUI.

**`_make_rig`.** In simulate, builds the `SimulatedDaqSession` and a
`SimulatedActuator` *linked to it* (`rig_sim=session`), so coarse steps
move the simulated surface — `Rig.open()` alone would build an unlinked
actuator and Start Approach would never find current. On hardware,
`verify_devices`, `park_all_outputs`, then `Rig(cfg).open()`.

**`_measure_impl`** is chapter 41 step 6 in code; read them side by side.
The helpers: `_configure_mode` (the per-mode `pull_length_nm` and bias
limit), `_build_ramp` (constant → `trace.build_ramp`, else
`ramps.build_*`), `_open_writer` / `_close_writer` (the session file and
its summary), `_reject` (the reason counts), `_histogram_input` (removing
the hold section of a mode trace) and `_histogram_block` (the histogram,
the `hist` event, the CSV).

**`shutdown`** sets stop, runs `_kill_tasks_impl` with `wait=True`,
closes the Keithley, stops the thread loop and detaches the log handler.

**The button map.** At the bottom of `controller.py`, `COMMAND_MAP` is a
dictionary from each public method name to (panel control, Igor
procedure, `_impl` name, the `stmlab` functions it calls). Three helpers
read it: `locate(obj)` gives `file:line` for any function or method via
`inspect`; `where("stmlab.keithley.find_suppress")` imports and locates a
dotted name; `describe_command(method)` builds the tooltip text (docstring,
Python file:line of the method and its `_impl`, Igor procedure, calls);
`command_table()` builds the rows the Button map window shows. The worker
also posts a `-> <name>: file:line function` log line as each command
starts. A test (`test_every_public_command_is_in_the_button_map`) fails if
a public method is added without a `COMMAND_MAP` row or if a listed call
cannot be resolved, so the map cannot drift from the code.

## widgets.py

`SetVariable` is label + entry (or spinbox when the Igor increment is
non-zero) bound to a `Param`; it commits on Return, KP_Enter, FocusOut and
the spinbox arrows, rejects non-numeric text by restoring the display,
clamps through `Param.set`, and calls `on_commit(stored)` when the value
changed (or unconditionally when called programmatically with no event).
`refresh()` re-reads the state. `ValDisplay` is a read-only entry with a
format. `CheckBox` is a `ttk.Checkbutton` bound to a bool `Param` with
`on_toggle`. `button()` is a `tk.Button` with Igor's text colour — macOS
Aqua ignores background colours on native buttons, so the text colour
carries the meaning there. `groupbox()` is a `LabelFrame`. `set_enabled()`
works on any of them. `Tooltip` and `param_tip` give every control its
hover text: buttons show the docstring passed as `tip=`, entries and
checkboxes show the Igor name, the path and the limits.

## graphs.py

`GraphWindow` is a `Toplevel` with a matplotlib `Figure`, one axes, a
`FigureCanvasTkAgg`, and a `decorate()` hook for labels and ranges; it
starts withdrawn, `show()` raises it, closing withdraws it. The nine
subclasses each implement `update(payload)`. `GraphSet` creates them
lazily from `ORDER` (name, class, Igor position), routes events by
`FEEDS`, and applies the first-data auto-open rule (chapter 45).

## panels/

`MainPanel` is a `ttk.Frame` in the root window. Its `_sv(parent, igor,
on_commit, **kw)` and `_cb(...)` helpers build a `SetVariable` or
`CheckBox` from a `PARAMS` row and register it in `refreshable`, so a
config load refreshes every control with one loop. `_build_daq_tab`,
`_build_inputs_tab` and `_build_options_tab` are the three tabs.
`set_writing(on)` and `set_busy(name)` are the enable/disable rules
(chapter 42). `on_event(kind, payload)` is one `if/elif` per event kind.
`VoltageOffsetPanel` and `EChemPanel` are `Toplevel`s with the same
pattern; `HistoryWindow` is a `Text` with a scrollbar and two tags.

## app.py

`App(state=None, simulate=False, root=None)` builds, in the order
`InitializeExperiment` did: styles, the controller, the main panel, the
History, the Voltage Offset panel, the EChem panel, the `GraphSet`, the
menus; binds Alt and Escape to `request_stop`; logs the two banner lines;
queues `connect_instruments`; and schedules `_pump`. `_pump` drains up to
200 events from the controller's queue, fans each out (`_fanout`) to the
main panel, the two Toplevels, the History and the graphs — catching and
logging any exception a handler raises, so a plotting error cannot stop
the pump — and reschedules itself every `PUMP_MS` (50 ms). `pump_once()`
drains synchronously, for tests. `quit()` shuts the controller down and
destroys the root. `main(argv)` is the `gui.py` entry point.

## Threading rules, and what they prevent

- Only the worker thread calls anything in `stmlab` that touches hardware.
  Prevents two DAQ calls at once (a card error at best, an untracked piezo
  position at worst).
- Only the Tk thread touches widgets. `_impl` methods communicate by
  events. Prevents the Tk "calling from another thread" crashes.
- The panels read `state` freely and write it through `Param.set` on the
  Tk thread; the worker reads it when a command runs. A value changed
  during a command is picked up at that command's next read of it, which
  is why chapter 42 says "next Start" for most fields. There is no lock;
  the fields are plain attributes and Python's assignment is atomic.
- `stop` is the only cross-thread signal that interrupts anything, and it
  is polled, never forced. A waveform in progress always completes.

## Walkthrough: adding a control

Suppose you want Igor's `G_ACCapLength` (the AC-hold cap length, which
Igor never put on the panel) on the AC sub-tab.

1. In `state.py`, add one row to `PARAMS`:
   `Param("G_ACCapLength", "cfg.ac_hold.cap_nm", float, "Cap length (nm)",
   fmt="%3.1f")`.
2. In `panels/main_panel.py`, in `_build_options_tab` under the AC
   sub-tab, add `self._sv(ac, "G_ACCapLength", width=6).grid(row=3,
   column=1, sticky="w", padx=8)`.
3. Run `manual_build/gen_binding_table.py` — the generator refuses if a
   `PARAMS` row is not in one of its groups, so add the name to the
   `"Options tab: AC"` list there too.

Nothing else: the value is read by `ramps.build_ac_hold` at the next
Start, the tooltip is automatic, `test_every_param_round_trips` covers it.
If the control must *act* at once (like Gain), give it an `on_commit`
that calls a controller method, and write that method as a `_run`
one-liner plus an `_impl`.

## Walkthrough: adding a button

Say a "Zero X piezo" button on the panel instead of only in the menu.

1. Controller: the method exists (`zero_xpiezo`). A new action would be
   `def frob(self, wait=False): return self._run("Frob", self._frob_impl,
   wait=wait)` and `def _frob_impl(self): rig = self._require_rig(); ...;
   self._emit("something", payload)`.
2. Panel: `button(parent, "Zero X", self.ctl.zero_xpiezo, tip=self.ctl.
   zero_xpiezo.__doc__)` and a grid call. If it must be greyed while busy,
   add it to the tuple in `set_busy`.
3. Test: in `test_gui_controller.py`, call it with `wait=True` against
   the simulator and assert on `drain(ctl)`.

## Walkthrough: adding a graph

1. Subclass `GraphWindow` in `graphs.py` with `title_text`, `igor_geometry`,
   `decorate()` and `update(payload)`.
2. Add it to `GraphSet.ORDER` and, under the event that feeds it, to
   `FEEDS`. The Windows menu picks it up from `ORDER` automatically.
3. Post the event from the controller where the data is produced.

## Tests

`tests/test_gui_controller.py` (23 tests) drives the controller headlessly
against the simulator: the binding table round-trips; Tip Bias is in mV;
the mode checkboxes are exclusive; buttons refuse before Start Writing;
Start Writing then Kill Tasks; background sampling updates the readouts;
piezo step and slider; the approach steps until current and forces step
size 5; the standalone actuator when the task is off; the Keithley
controls send Igor's command strings; Tip Bias is quantised with the
Keithley bias on and refused beyond the limit; Find Offset then Find
Suppress with the bias restored; +1 then a run to Stop #, with the
partial-block histogram and the file's trace count; V0 check re-measures
mid-run; each of the four ramp modes; Stop ends a run; counter electrode
and CV; X piezo and LateralEXPT; rungo resumes from Saved; config save
and load. `tests/test_gui_app.py` (6 tests) builds the real widgets with
a withdrawn root: every panel and graph constructs; a SetVariable writes
through and rejects bad text; the mode checkboxes; a simulated run reaches
the graphs and the enable states; a CV reaches the voltammogram; every
button has a tooltip. They skip where Tk has no display.

```
./.venv/bin/python -m pytest tests/ -q               # all 122
./.venv/bin/python -m pytest tests/test_gui_controller.py -q
```

The controller tests need no display because the controller has no Tk in
it. That is the practical payoff of the one rule: the entire lab flow can
be exercised on a build server, and a change to the flow is caught before
anyone opens a window.
