# Constant-bias STM break junctions

The reference experiment of this package. Everything else in `experiments/`
is a variation on what happens here, and the analysis chain (conductance
calibration, trace selection, log histogram) was validated against Igor's own
archived data for exactly this mode.

## The physics

A gold STM tip is repeatedly crashed into and pulled out of a gold surface
while a fixed bias (default 100 mV) sits across the junction and a
current-to-voltage preamplifier reads the tip current. On each pull-out the
metallic contact thins to a single atom -- conductance G = 1 G0 = 2e^2/h --
and then, if molecules are present, a single molecule can bridge the gap and
hold a plateau at its own characteristic conductance before the junction
breaks. One trace is conductance versus pulled distance; one experiment is
thousands of traces. Nothing is concluded from any single trace: the traces
that pass the crude selection tests are accumulated into a histogram of
log10(G/G0), and molecular conductance is read off as a peak in that
histogram. The position of the 1 G0 peak doubles as a whole-chain calibration
check -- `summarise` reports it and names the classic failure modes (a 1.000
decade offset is a 10x gain error; a 0.301 decade offset is a factor of two
in bias, or G0 defined as e^2/h).

## Igor origin

Translated from `igor_code/Functions_STMBJ.ipf`:

| Python (in `stmlab/`)              | Igor function          | line |
| ---------------------------------- | ---------------------- | ---- |
| `trace.trace_loop`, `main.run`     | `MeasureBreakJunctions`| 1664 |
| `trace.build_ramp`                 | `CreateInputs` (constant-bias branch) | 1601 |
| `trace.capture` / `single_trace`   | `GenerateTrace`        | 284  |
| `analysis.select_trace`            | `TestTrace`            | 1180 |
| `analysis.log_histogram`           | `LogHistFromBlocks`    | 785  |

This folder's `run_experiment.py` is deliberately a thin delegator into the
validated CLI `stmlab/main.py` -- it only inserts `run` in front of the
arguments when no sub-command is given, so the folder convention matches the
other experiments.

## Hardware

- NI DAQ card (analog out: piezo Z + bias; analog in: bias monitor + preamp
  output). A second low-res card is optional (`channels.low_res_device`).
- STM head with Z piezo, gold tip, gold-on-mica substrate.
- Current preamplifier (gain in `cal.preamp_gain_v_per_a`).
- Optional coarse-approach actuator (NanoPZ) for `--coarse` /
  `bringup 5`.

No hardware is needed with `--simulate`: a simulated card synthesises traces
with a 1 G0 plateau and the full pipeline runs.

## Commands

From `python_code_entire_igor/` (use the venv python):

    # simulate, 50 traces
    .venv/Scripts/python.exe experiments/01_constant_bias/run_experiment.py --simulate -n 50 -o data/sim.h5

    # real rig: validate the config first, then acquire 1000 traces
    .venv/Scripts/python.exe experiments/01_constant_bias/run_experiment.py check --config rig.json
    .venv/Scripts/python.exe experiments/01_constant_bias/run_experiment.py --config rig.json -n 1000 -o data/session.h5

    # equivalently, via the dispatcher
    python run.py constant_bias --simulate -n 50

Sub-commands (anything else is passed to `run`):

- `run` -- acquire traces. Flags: `-n/--traces`, `-o/--out`, `--simulate`,
  `--config PATH`, `--no-calibrate`, `--coarse` (coarse approach first),
  `--require-engaged` (enable the start-in-contact test Igor left disabled),
  `-v/--verbose`.
- `check` -- validate a config without touching hardware.
- `summarise PATH` -- histogram peak of a finished session, with the
  calibration-failure diagnostics described above.
- `dump-config PATH` -- write the default config as JSON to edit for the rig.
- `bringup STEP` -- first-contact hardware checks 1-5 on the rig PC
  (step 4 takes `--resistor OHMS`, step 5 takes `--port COM3 --move`).

Ctrl-C once finishes the current attempt and stops cleanly; twice exits
immediately.

## What is stored

One HDF5 file per session (`-o`, default `data/stmbj_<timestamp>.h5`),
written by `stmlab.storage.SessionWriter`: the full `RigConfig` as JSON, and
per accepted trace the raw voltage and current records (volts), the
alignment delay, start piezo voltage, bias, and sample rate, plus a summary
(attempts, acceptance rate, rejection reasons). All traces in one file have
equal length -- one mode per file.

## Looking at the data

    .venv/Scripts/python.exe experiments/01_constant_bias/run_experiment.py summarise data/session.h5

or programmatically:

    from stmlab import analysis, storage
    with storage.Session("data/session.h5") as s:
        centres, counts = analysis.log_histogram(s.conductances())

then plot `counts` against `centres` (log10(G/G0) on x) and look for the
1 G0 peak at 0 and the molecular peak below it.
