# 40. The GUI: what it is and how to start it

*Igor: `InitializeExperiment`, Setup1_STMBJ.ipf:55; the window macros in Windows_STMBJ.ipf. Module: `stmgui/`, launcher `gui.py`.*

## What this folder is

`python_code_entire_igor_w_GUI/` is `python_code_entire_igor/` — the complete
command-line translation of the Igor procedures, with its `stmlab/` package,
eight `experiments/`, sixteen `snippets/` and the core manual — copied
byte for byte, plus one new package, `stmgui/`, that rebuilds everything the
Igor experiment put on screen:

- the **Molecular Break Junction Measurement** panel (Igor:
  `BreakJunctionMeasurement`), with its DAQ / Inputs / Options tabs, the
  Keithley, actuator and piezo groups, the live readouts and the counters;
- the **Voltage Offset** panel (Igor: `Voltage_Offset`) — Find Offset, which
  the lab calls Find Zero;
- the **Electrochemistry** panel (Igor: `EChem`);
- the nine graph windows — `HighRes`, `PullOutGvsE`, `PullOutLowG`,
  `AuAuConductanceLevel`, `SenseInDisplay`, `LogHistOfBlock`, `Izero`,
  `Izero_Time`, `CyclicVoltammogram`;
- a **History** window standing in for Igor's history area;
- and, under a **Macros** menu, the two procedures you ran from Igor's
  command line, `rungo()` and `LateralEXPT()`.

Nothing in `stmlab/` was changed. Every button calls the same function the
command-line experiment calls, so the GUI is exactly as trustworthy as the
package underneath it — and no more: the hardware paths (the NI card, the
Keithley over GPIB, the second card, the NanoPZ) have still never met their
instruments.

There are now three ways into the same code:

| Way in | Command | When |
|---|---|---|
| The panels | `python gui.py --simulate` | The lab flow you know from Igor |
| The dispatcher | `python run.py <experiment> --simulate` | Unattended runs, campaigns, scripts |
| The snippets | `python snippets/01_numbers.py` | Learning one piece at a time |

`python run.py gui --simulate` is the same as `python gui.py --simulate`;
the dispatcher just forwards to the launcher.

## Installing

Tkinter is part of Python itself, not a pip package, and not every Python
has it. The python.org installers for macOS and Windows bundle it; Debian
and Ubuntu need `apt install python3-tk`; Homebrew's Python does **not**
include it and needs `brew install python-tk@3.12` (matching the Python
version) or, simpler, the python.org build. Check with:

```
python3 -c "import tkinter; print(tkinter.TkVersion)"
```

Create the virtual environment from an interpreter that passes that test,
then install the same requirements as the command-line folder:

```
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt      # numpy, h5py, matplotlib, pytest
./.venv/bin/python gui.py --simulate
./.venv/bin/python -m pytest tests/ -q           # 122 passed
```

On Windows replace `./.venv/bin/` with `.venv\Scripts\`. On the lab PC add
the hardware drivers — `nidaqmx` for the card, `pyserial` for the NanoPZ,
`pyvisa` (with NI-488.2) for the Keithley 428 — and launch without
`--simulate`.

If you launch with an interpreter that has no Tk, `gui.py` does not
traceback; it prints the three install lines above and exits.

## Launch options

```
python gui.py [--simulate] [--config FILE.json] [-v]
```

- `--simulate` builds the state with `stmgui.state.simulated_state()`:
  `cfg.simulate = True`, a pretend second card (`channels.low_res_device =
  "Dev2"`) so the EChem and X-piezo features can be exercised, and
  `actuator.kind = "simulated"`. The window title gains `[SIMULATED]`.
- `--config FILE.json` starts from a saved `RigConfig` (chapter 46
  explains saving one from the File menu). With `--simulate` as well, the
  loaded config is forced into simulate mode.
- `-v` sets the console log level to DEBUG. The History window shows INFO
  and above regardless.

## What opens, and why

Igor's `InitializeExperiment` (Setup1_STMBJ.ipf:55-75) declared the globals,
opened the main panel, set up the Keithley over GPIB, initialised the EChem
module and opened the Voltage Offset panel. `stmgui.app.App` does the same
things in the same order:

1. `GuiState()` — the config (`RigConfig`) and the panel-only options
   (`GuiOptions`); chapter 48.
2. The main panel, in the root window.
3. The History window, the Voltage Offset panel and the Electrochemistry
   panel, as separate windows.
4. `RigController.connect_instruments()` — Igor's `SetUpGPIB_Keithley`. In
   simulate this is a `SimulatedKeithley` that records every command; on
   hardware it opens the GPIB resource, and if that fails the History says
   so and the Keithley controls refuse until it succeeds, while everything
   else works.

The graph windows are not opened at launch. Each opens itself the first
time data arrives for it — the `HighRes` window on the first background
read, the pull-out graphs on the first trace, `Izero` after Find Offset,
`LogHistOfBlock` after the first histogram block, `CyclicVoltammogram`
after a CV — which is what Igor's `DoWindow/F ...; if (V_flag==0) Execute
"Window()"` idiom did. All of them are also under the **Windows** menu.
Closing a graph or a panel only hides it; the menu brings it back.

## The window map

| Window title | Igor macro | Chapter |
|---|---|---|
| Molecular Break Junction Measurement | `BreakJunctionMeasurement()` : Panel | 42 |
| Voltage Offset | `Voltage_Offset()` : Panel | 43 |
| Electrochemistry | `EChem()` : Panel | 44 |
| HighRes | `HighRes()` : Graph | 45 |
| PullOutGvsE | `PullOutGvsE()` : Graph | 45 |
| PullOutLowG | `PullOutLow()` : Graph | 45 |
| AuAuConductanceLevel | `AuAuConductanceLevel()` : Graph | 45 |
| SenseInDisplay | `SenseInDisplay()` : Graph | 45 |
| LogHistOfBlock | `LogHistOfBlock()` : Graph | 45 |
| I(Applied Bias) fit - Izero estimate | `Izero()` : Graph | 45 |
| Izero change over time | `Izero_Time()` : Graph | 45 |
| Cyclic Voltammogram | `CyclicVoltammogram()` : Graph | 45 |
| History | Igor's history area | 45 |

## What "simulate" swaps in

With `--simulate` no driver is imported and no instrument is touched. In
place of each one the package's own stand-ins run:

- `stmlab.sim.SimulatedDaqSession` for the PXI-4461: a junction model
  with a gold plateau, an occasional molecule, tunnelling decay, an
  amplifier offset and noise, and a group delay of 37 samples so the
  alignment spike has something to find.
- `stmlab.actuator.SimulatedActuator` for the NanoPZ, **linked to the
  simulated surface**: each step moves the surface 8 nm, so Start Approach
  really does walk in until current appears and `recover_headroom` really
  does back off when contact is too low to pull from. The command-line
  package's `Rig.open()` creates an unlinked actuator; the GUI's
  `RigController._make_rig` links it on purpose.
- `stmlab.keithley.SimulatedKeithley`: same command surface, records the
  command strings (`C0X`, `H6R6X`, ...) instead of sending them.
- `stmlab.echem.SimulatedCounterElectrode` and the simulated
  electrochemical cell inside `echem.run_cv` (a double-layer capacitance
  plus one reversible redox couple).
- `stmlab.xpiezo.SimulatedXPiezo`.

What the simulator cannot tell you: whether the card's clocks, the
Keithley's GPIB address, the serial port or the second card's channels are
right on your rig. That is bring-up, chapter 03, and it has not been done
with this code.

## The menus, briefly

**File** loads and saves the config as JSON, opens today's data folder in
the file browser, and quits. **Macros** is Igor's Macros menu grown up: the
three panels, `rungo()`, `LateralEXPT()`, the X piezo moves, and Stop.
**Windows** lists the nine graphs and History. **Help** says where this
manual is. Chapter 46 has the details.

## Stopping, and quitting

Igor polled the Alt key inside every loop (`GetKeyState`,
Functions_STMBJ.ipf:1697). Here the Alt key, the Escape key and the red
**Stop (Alt)** button beside Start Measurement all set the same flag. The
running command finishes the step it is on — the current attempt of a
measurement, the current actuator step of an approach, the current point of
a suppress sweep — and returns; nothing is interrupted half-way through a
waveform.

Quitting (File → Quit, or the window's close box) runs the controller's
`shutdown()`: Kill Tasks — outputs parked, the session file closed, zero
check back on — then the Keithley released. Do this rather than killing the
process: the card's own idle behaviour is the only thing that parks the
outputs if you do not.

## Every control says which Python it runs

Hover over any button and a tooltip says what the click does, which Igor
procedure it mirrors, and **exactly which Python runs**: the controller
method with its file and line, the worker-thread `_impl` that does the
work, and the `stmlab` functions it calls, each with its file and line.
For Find Suppress:

```
Button 'Find Suppress': FindSuppress, Controls_STMBJ.ipf:479. Zero the
tip bias, TestVirtualGround, restore the bias.
Python: stmgui/controller.py:527  RigController.find_suppress
        stmgui/controller.py:532  RigController._find_suppress_impl  (worker thread)
Igor:   FindSuppress -> TestVirtualGround
Calls:  stmlab/instrument.py:157 Rig.set_bias; stmlab/keithley.py:199 find_suppress
```

Hover over any entry or checkbox and it names the Igor global it was bound
to, the config attribute it writes now, and its limits.

Four ways to the same information, from the most visible:

1. **The "Which code runs this?" button** at the bottom of the main panel
   opens the **Button map**: one window with every control, its
   `RigController` method and worker-thread `_impl` (file:line), the Igor
   procedure, and the `stmlab` functions reached — generated from the
   loaded code, so the line numbers are current. The same window is under
   **Windows** and **Help** (on macOS the menu bar is at the top of the
   screen, not in the window).
2. **Right-click any control** (macOS: Control-click, or a two-finger tap)
   and the **Inspector** window opens with that control's text — the same
   as its tooltip, but it stays open and can be copied from.
3. **Hover** for half a second: the tooltip.
4. **The History window** prints, for every click, a line
   `-> Find Suppress: stmgui/controller.py:532 RigController._find_suppress_impl`
   before the command's own output, and the status line at the bottom of
   the main panel says `running: <command>` while it is in progress.

The orange hint line under the status line says the same thing in one
sentence, so a fresh launch shows where to look.

> The lab flow has not changed. **Start Writing → Background Sampling →
> Start Approach → Find Offset → Find Suppress → Start Measurement**, then
> **Kill Tasks** at the end. Stop is Alt, Escape, or the Stop button.

## The first five minutes on the simulator

1. `./.venv/bin/python gui.py --simulate`. Four windows open: the main
   panel, Voltage Offset, Electrochemistry, History. The History says
   `SIMULATED rig` and then `Keithley 428 ready (simulated)`.
2. DAQ tab → **Start Writing**. The History shows the config warnings
   (`hv_amp_gain is unknown ...` is normal), `output task ON: piezo 0.000 V
   (0 nm), bias +100.0 mV`, and the session calibration line. Start Writing
   greys out, Kill Tasks stays live, the slider wakes up.
3. Tick **Background Sampling (Beep is ON)**. The I / V / Piezo readouts
   start updating four times a second and the HighRes window opens.
4. **Start Approach**. The counter beside Step Size climbs — about forty
   steps on the simulator — and the History prints one `Approach: actual
   current= ...` line per step until the current appears.
5. Voltage Offset panel → **Find Offset**. The Izero window opens with the
   fitted line; V0 and I0 fill in (near zero on the simulator, which has
   no bias offset).
6. **Find Suppress**. The History prints `New current suppress is ... uA`
   and the Suppress I value updates.
7. Set **Stop #** to 101 and press **Start Measurement**. Saved and
   Attempts count up, the three PullOut windows redraw on every attempt,
   and when Saved reaches 101 the LogHistOfBlock window opens with the
   first 100-trace histogram and the History names the file that was
   written.
8. **Kill Tasks**, then File → Quit.

The whole sequence takes under a minute on the simulator. Chapter 41 goes
through each of those steps in depth.

## Where to read next

- **41** — the lab flow, step by step, with what to expect and what can go
  wrong.
- **42, 43, 44** — the three panels, control by control.
- **45** — the graph windows and History.
- **46** — menus and macros: `rungo`, `LateralEXPT`, config files.
- **47** — what gets written to disk and how to read it back.
- **48** — how `stmgui` is built, for the day something needs changing.
- **49** — deviations from Igor, limitations, troubleshooting.
- **50, 51** — the quick reference and the complete binding table.
- Part II (chapters 00–30) is the core manual: the physics of each
  experiment, every config field, the hardware, and the command line.
