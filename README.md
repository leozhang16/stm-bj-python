# python_code_entire_igor_w_GUI — the complete Igor setup, with its panels

Everything the Igor procedures in `../igor_code/` could run, as one Python
folder — **including the GUI**. This is `../python_code_entire_igor/`
(the complete command-line translation: `stmlab/`, eight `experiments/`,
sixteen `snippets/`, the manual) copied unchanged, plus one new package,
`stmgui/`, that rebuilds Igor's three panels, nine graph windows and history
window in Tkinter on top of it.

```
gui.py            python gui.py --simulate       <- the Igor panels
run.py            python run.py <experiment>     <- the CLI experiments (unchanged)
stmgui/           the GUI: state, controller, widgets, graphs, panels, app
stmlab/           the translated Igor procedures (byte-for-byte from ../python_code_entire_igor)
experiments/      01_constant_bias ... 08_bias_series (unchanged)
snippets/         01 ... 16 (unchanged)
manual/           chapters 00-30 (unchanged) + 40_gui.md (new)
tests/            93 core tests + 28 GUI tests
data/             where the GUI writes: data/<date>/*.h5, *.csv
```

## Quick start

```bash
python3 -m venv .venv                         # a Python WITH Tk, see below
./.venv/bin/pip install -r requirements.txt   # numpy, h5py, matplotlib, pytest

./.venv/bin/python gui.py --simulate          # the panels, simulated rig
./.venv/bin/python -m pytest tests/ -q        # 121 passed
```

On Windows swap `./.venv/bin/` for `.venv\Scripts\`. On the lab PC install
`nidaqmx` (and `pyserial` for the NanoPZ, `pyvisa` for the Keithley) and
drop `--simulate`.

**Tk.** Tkinter ships with the python.org installers (macOS, Windows) and
with `apt install python3-tk` on Linux. Homebrew's Python does *not* include
it: use `brew install python-tk@3.12` or the python.org build, and create
`.venv` from that interpreter. `gui.py` says exactly this if Tk is missing.

## The GUI

Launch it and you are looking at Igor's **Molecular Break Junction
Measurement** panel: the DAQ / Inputs / Options tabs (Options with the
Push-Pull, IV, AC and High-bias-hold sub-tabs), Background Sampling,
Keithley Controls, Actuator Controls, Piezo Controls with the slider, the
I / V / Piezo readouts, Saved, Tip Bias, Stop #, Attempts, Start Measurement
and +1. The **Voltage Offset** and **Electrochemistry** panels open beside
it, as `InitializeExperiment` opened them. The nine graphs — HighRes, the
three PullOut views, SenseInDisplay, LogHistOfBlock, Izero, Izero_Time,
CyclicVoltammogram — open when their data first arrives and live under the
**Windows** menu. Igor's command-line macros `rungo()` and `LateralEXPT()`
are under **Macros**.

The lab sequence is the one you know:

```
Start Writing -> Background Sampling -> Start Approach
   -> Find Offset (Find Zero) -> Find Suppress -> Start Measurement
```

Stop is the Alt key, Escape, or the **Stop** button. Chapter 40 of the
manual, `manual/40_gui.md`, goes through every control, every graph, what
gets written and the handful of deliberate deviations.

Every panel control is bound to the same number the command-line package
uses (`stmgui/state.py` is the table: Igor global → `RigConfig` field), so a
config saved from the GUI (**File → Save config JSON**) runs unchanged under
`run.py`, and vice versa.

**Which Python does a button run?** Hover it: the tooltip gives the Igor
procedure it mirrors, the `RigController` method and its worker-thread
`_impl` with file and line, and every `stmlab` function it calls with file
and line. **Windows → Button map** lists all of them in one window, and the
History window prints `-> <button>: file:line function` as each click runs.

### How it is built

`stmgui/controller.py` owns the `Rig` on one worker thread and exposes every
Igor button as a method; it never imports Tk. The panels queue commands and
drain an event queue every 50 ms; they never touch the Rig. Hence two
clicks can never race for the card, and the whole flow — Start Writing,
approach, Find Offset, Find Suppress, every ramp mode, V0 tracking, CV,
rungo, LateralEXPT — is tested headlessly against the simulator in
`tests/test_gui_controller.py`, with the Tk layer exercised in
`tests/test_gui_app.py`.

## The experiments (unchanged)

| Folder | Igor origin | What it measures |
|---|---|---|
| `experiments/01_constant_bias` | `MeasureBreakJunctions` :1664 | The reference experiment: pull traces, select, log-histogram, 1 G₀ ruler |
| `experiments/02_push_pull` | `CreateInputs` push-pull branch :1461 | Re-form the same junction repeatedly — molecular re-binding statistics |
| `experiments/03_iv_sweep` | IV branch :1497 | Triangular bias sweep at a held junction — transport spectroscopy |
| `experiments/04_ac_hold` | AC-hold branch :1539 | Sine bias during a hold — lock-in-style conductance |
| `experiments/05_high_bias_hold` | HB-hold branch :1566 | Junction stability under high field; optional Vzero-linked hold |
| `experiments/06_echem_gate_cv` | `EChem_Module.ipf` | Counter-electrode gate and cyclic voltammetry (both card variants) |
| `experiments/07_lateral_monolayer` | `LateralEXPT`, Setup1 :91 | Walk the tip across a monolayer, a trace batch per site |
| `experiments/08_bias_series` | `rungo`, Setup1 :138 | Igor's scripted bias campaign, resumable, one file per bias |

`python run.py list` shows them; `python run.py gui --simulate` is the
panels. Each experiment folder has its own README.

## The core (`stmlab/`, unchanged)

The 13 modules of the reference `stmbj` package (config, safety, daq, sim,
instrument, approach, trace, analysis, storage, calibrate, actuator, bringup,
main) plus ramps, keithley, vzero, echem, xpiezo. See
`../python_code_entire_igor/README.md` and `../STMLAB_Manual.pdf` for the
deep story; nothing in that folder was modified here.

## Manual

**`STMLAB_GUI_Manual.pdf`** in this folder (a copy sits beside the other
two manuals at the project root). It opens with **chapter 05, the
structure map**: every file, which file calls which function in which
other file (generated from the source by `manual_build/gen_structure.py`),
one button click and one trace followed top to bottom — read that first.
The same map is interactive in `manual/structure_map.html` (open it in a
browser: click a file, see what it calls and who calls it, search a
function). Then two parts. Part I,
chapters 40–51, is the GUI: the tour, the lab flow button by button, the
three panels control by control, the nine graphs with figures, menus and
macros, the data files, the architecture, deviations and troubleshooting,
a quick reference and the generated binding table. Part II, chapters
00–30, is the core stmlab manual, unchanged.

`manual/README.md` is the index; the Markdown chapters are the source of
truth. `manual_build/build.sh` regenerates the binding table
(`gen_binding_table.py`, from `stmgui/state.py`), converts the chapters
(`md2tex.py`) and runs xelatex; `--figures` also re-runs a simulated
session to regenerate the graph figures (`make_figures.py`).

## Trust order

Inherited from the base folder: the constant-bias path carries 93 tests and
the 1 G₀ self-check on the simulator; the hardware-only paths (Keithley
GPIB, second-card EChem/X-piezo, every `nidaqmx` call) have never met their
instruments, and the comparison against archived Igor `.ibw` data has not
been done. The GUI adds 28 tests and changes none of that: it calls the
same functions, so it is exactly as trustworthy as they are, and no more.

Simulate first, scope second, tip last.
