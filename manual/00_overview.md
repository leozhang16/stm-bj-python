# 00. Overview

## What this folder is

`python_code_entire_igor/` is the **complete** Igor STM break-junction setup,
translated to Python: everything the procedures in `../igor_code/` could run,
as one package (`stmlab/`) plus one folder per experiment (`experiments/`).

It is a strict superset of `../python_code/stmbj`, the minimal package that
translated **only** the constant-bias experiment. That reference core was
copied in unchanged as the
first thirteen modules of `stmlab/` (config, safety, daq, sim, instrument,
approach, trace, analysis, storage, calibrate, actuator, bringup, main) and
extended with five new modules:

| Module | Igor origin | What it adds |
|---|---|---|
| `stmlab/ramps.py` | `CreateInputs`, Functions_STMBJ.ipf:1398-1633 | The four non-constant trajectories (push-pull, IV, AC hold, HB hold) as pure functions returning a `ModeRamp` |
| `stmlab/keithley.py` | SetUpGPIB_Keithley.ipf; `SetGain`, Controls_STMBJ.ipf:290 | The Keithley 428 current amplifier over GPIB, the suppress-current calibration (`TestVirtualGround`, Functions_STMBJ.ipf:1097), and the series-resistance-corrected conductance |
| `stmlab/vzero.py` | `OffsetVoltage`/`SaveOffset`, Functions_STMBJ.ipf:920/993 | The zero-current bias offset: measure it in contact, re-measure every N traces, feed it back into the applied bias |
| `stmlab/echem.py` | EChem_Module.ipf | The counter-electrode gate and both cyclic-voltammetry ramp builders, with Igor's cycle masking and a simulated electrochemical cell |
| `stmlab/xpiezo.py` | `SetupXPiezo`/`MoveXPiezo`, NanoPZ_Actuator_Functions_STM.ipf:25-100 | The lateral X piezo at 522 nm/V, with tracked position and out-of-range refusal |

One design decision carries the whole extension: every trajectory --
constant-bias pull, push-pull cycle, IV sweep, AC or high-bias hold -- is a
`(2, N)` array of volts played through the same `Rig.play()`, captured and
aligned by the same `trace.capture()`, and stored as the same raw-volt
records. A mode is a different waveform plus a `segments` dictionary saying
where its pieces live. Chapter 01 explains why this works.

## The experiment menu

**01_constant_bias** -- the reference measurement, and the one path that
carries the 1 G0 self-check. A gold tip is crashed into and pulled out of a
gold surface thousands of times at a fixed 100 mV bias; each pull thins the
contact to a single atom (1 G0 = 2e^2/h), sometimes catches a molecule, and
ends in tunnelling. Accepted traces accumulate into a histogram of
log10(G/G0); molecular conductance is a peak in that histogram, and the 1 G0
peak position is a whole-chain calibration check. Igor:
`MeasureBreakJunctions`, Functions_STMBJ.ipf:1664.

**02_push_pull** -- instead of breaking the junction once, re-form it: an
initial pull, then per cycle {hold, push back in, hold, pull out}, then a
final pull. The result is re-binding statistics for the same junction, cycle
by cycle. Bias stays at the DC baseline throughout. Igor: `CreateInputs`
push-pull branch, Functions_STMBJ.ipf:1461-1495.

**03_iv_sweep** -- transport spectroscopy: pull to a held junction, sweep the
bias in a triangle (0 to +max, through -max, back to 0, up to 1 V), with DC
caps either side so the junction settles. One IV curve per held junction.
Igor: IV branch, Functions_STMBJ.ipf:1497-1537.

**04_ac_hold** -- hold the junction while the bias is a pure sine (default
0.8 V amplitude at 10 kHz, replacing the DC baseline entirely during the
hold), for lock-in-style conductance analysis. Igor: AC-hold branch,
Functions_STMBJ.ipf:1539-1564.

**05_high_bias_hold** -- junction stability under field: hold at an elevated
DC bias (default 0.8 V) between an initial and final pull. The hold bias can
optionally be the measured Vzero offset, reproducing Igor's Voltage_Offset
link (Functions_STMBJ.ipf:1595-1599). Igor: HB-hold branch,
Functions_STMBJ.ipf:1566-1599.

**06_echem_gate_cv** -- electrochemistry. A DC gate on the counter electrode
shifts molecular levels relative to tip and substrate; a cyclic voltammogram
sweeps the electrode potential in a triangle and records tip current. Two CV
variants: high-res (drives the junction-bias channel; the tip is the working
electrode) and low-res (drives the counter electrode on the second card).
Igor: EChem_Module.ipf.

**07_lateral_monolayer** -- walk the tip across a monolayer with the X piezo
(522 nm/V on the second card), taking a batch of traces at each site, with a
full withdraw before every lateral move so the tip is never dragged in
contact. Igor: the LateralEXPT campaign, Setup1_STMBJ.ipf:91.

**08_bias_series** -- Igor's `rungo` scripted campaign (Setup1_STMBJ.ipf:138):
the constant-bias experiment repeated over a series of biases, one file per
bias, resumable. Biases above the 0.5 V default limit are raised deliberately
and loudly, never silently.

## Folder map

```
python_code_entire_igor/
    run.py                  dispatcher: python run.py list / <name> / <NN>
    requirements.txt        numpy, h5py, matplotlib, pytest
    README.md
    stmlab/                 the package (reference core + 5 new modules)
        config.py           every constant, as dataclasses -> chapter 02
        safety.py           limits, interlocks, output parking
        daq.py              DAQmx; the one verb play()
        sim.py              the fake card that behaves like a junction
        instrument.py       Rig: open tasks + tracked piezo position
        approach.py         engage, coarse approach, smash, recover_headroom
        trace.py            build_ramp, capture, trace_loop, TraceRecord
        ramps.py            build_push_pull / build_iv / build_ac_hold / build_hb_hold
        analysis.py         conductance, selection, log histogram, peak position
        storage.py          HDF5 SessionWriter / Session, .ibw import
        calibrate.py        zero, group delay, gain sweep, session_calibration
        actuator.py         NanoPZ coarse actuator over serial
        keithley.py         Keithley 428 over GPIB
        vzero.py            zero-current offset workflow
        echem.py            counter electrode + CV
        xpiezo.py           lateral piezo
        bringup.py          first-contact hardware checks 1-5
        main.py             the constant-bias CLI (run/check/summarise/...)
    experiments/
        01_constant_bias/ ... 08_bias_series/
                            run_experiment.py + README.md each
    snippets/               16 runnable scripts (chapter 04)
    tests/                  93 tests; all pass without hardware
    data/                   session .h5 files land here by default
    manual/                 this manual
```

## Quick start

From `python_code_entire_igor/`:

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt

.venv/Scripts/python run.py list                     # what can I run?
.venv/Scripts/python run.py constant_bias --simulate -n 200
.venv/Scripts/python -m pytest tests/ -q             # 93 passed
```

Rules of the road:

1. **Simulate first.** Every experiment runs end to end with `--simulate` on
   any machine -- no hardware, no NI drivers. The simulated card (`sim.py`)
   produces traces with a 1 G0 plateau, a molecular plateau, a tunnelling
   tail, an AI/AO group delay, and a noise floor, so the entire pipeline
   including alignment and selection is exercised, not stubbed.
2. `python run.py list` prints one line per experiment;
   `python run.py <name>` and
   `python experiments/<NN>_<name>/run_experiment.py` are exactly
   equivalent (`run.py` is a dispatcher, nothing more).
3. On the rig PC, additionally install `nidaqmx` (and `pyserial` for the
   NanoPZ, `pyvisa` for the Keithley) and drop `--simulate`. Run the
   bring-up ladder (chapter 03) before the first real trace.
4. Validate before touching hardware:
   `python run.py constant_bias check --config rig.json`.

## Relationship to the neighbouring folders

**`../igor_code/`** is the original: Setup1_STMBJ.ipf, Functions_STMBJ.ipf,
Controls_STMBJ.ipf, Windows_STMBJ.ipf, EChem_Module.ipf,
SetUpGPIB_Keithley.ipf, NanoPZ_Actuator_Functions_STM.ipf. Every function
translated here cites its Igor source and line numbers in its docstring, and
Igor's defaults were kept wherever they were safe so an archived Igor run and
a Python run are directly comparable. `igor_code/Source_Files/` (an AFM, an
older Setup 3) is reference material and was not translated. The Igor GUI,
the 0.25 s background readout, and the thermocouple were deliberately not
translated; the reasons are in the top-level README.

**`../python_code/`** is the constant-bias reference: the `stmbj` package,
built first, reviewed line by line against the Igor source, and covered by 38
tests. It stays frozen as the ground truth. This folder's `stmlab/` began as
a byte-for-byte copy of it, so the constant-bias path here is that same code,
and those 38 tests are part of this folder's 93. When in doubt about the core
behaviour, the reference package and `../STMBJ_Python_Manual.pdf` are the
deep story.

**The Igor comparison has NOT been done.** The intended milestone — push
archived `.ibw` blocks through `storage.split_igor_block` →
`analysis.to_conductance` → `log_histogram` and check the 1 G0 peak agrees
with Igor's to within 0.05 decade — is still outstanding, because no archived
`.ibw` file was available. The 1 G0 peak *has* been reproduced to +0.02
decade, but from the **simulator**, which proves the analysis arithmetic is
self-consistent and says nothing about whether it matches Igor. Until a real
`.ibw` goes through it, "validated" is the wrong word for any path here.
`storage.load_ibw` is written and untested for the same reason.

**Trust order.**

1. **Reviewed and unit-tested, self-consistent on synthetic data** — the
   constant-bias path. The strongest claim currently available.
2. **Index-for-index translations with geometry tests, exercised end to end
   on the simulator** — the four ramp modes, both campaigns, CV ramp
   construction, Vzero, the X piezo.
3. **Never met its instrument** — every `nidaqmx` call in the new modules,
   the Keithley over GPIB, the second card, the electrochemical cell.

Simulate first, scope second, tip last.
