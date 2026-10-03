# rigtests: small hands-on tests for the rig

One file per test. Each one is a standalone script with its own small window
(or none), runs on the simulator with `--simulate` so it can be tried on the
MacBook first, and runs on the lab PC with `--config configs/labpc_rig.json`.
They are not experiments: nothing here engages a junction or saves traces.
They are for the hour when you want to move one thing and watch one plot.

Every test goes through the same `Rig` as the experiments, so the clamp on
the piezo range, the position tracker and the parking of every output at
exit are the ones the experiments trust. Nothing in this folder talks to the
card directly.

| Test | What it moves | What it shows | Needs |
|---|---|---|---|
| `02_approach_pull.py` | the fine-piezo approach and the constant-bias pull, one button at a time (`approach.engage`, `trace.single_trace`), or N cycles | six live plots: the record (junction V and current, Igor HighRes), log G vs displacement with the verdict (PullOutLowG), the gold level (AuAuConductanceLevel), piezo in and out over the cycle with the readback, the running histogram (LogHistOfBlock), and the approach (G at each step vs piezo) or the pull's I-V; Igor's Inputs-tab settings, each change checked by `validate` before it applies; accepted traces saved as `.h5` (raw volts) and exported as Igor `.ibw` blocks in SavePullOut's layout; a saved session can be browsed in the same plots; `plots.py` makes the PNGs | the coarse approach done first (by hand or Igor's actuator controls), tip within the piezo's 620 nm; Igor's DAQ tasks closed |
| `01_piezo_sweep.py` | Z piezo (`dev1/ao0`), by slider or by a sweep | commanded volts and the sense readback (`dev2/ai2`) against time; a side panel with the config's ranges, the position now, and a live straight-line fit of readback against command that gives `cal.sense_nm_per_volt` and `cal.sense_zero_v` as config lines (Copy config lines), plus the up/down loop and the ADC step; a readback-only window (button, or `--readback`) that shows the sense line alone, mean removed, in microvolts and picometres: one point per hold for creep and drift, and every sample of the last hold for ripple and hum. The main plot has two y axes, command (left) and readback (right), linked through the config's calibration; the y-axis row chooses full range, the sweep's own range, auto, or manual limits. `--sweep 4.90 4.98 --sweep-rate 0.02 --ymode sweep` starts a 5 nm sweep with the axes on it | tip FAR from the sample; the second card for the readback |

## Running

From the repo folder, with the venv active:

    python rigtests/01_piezo_sweep.py --simulate
    python rigtests/01_piezo_sweep.py --config configs/labpc_rig.json

Options every test shares: `--config`, `--simulate`, `-v`. `02_approach_pull.py --headless N` runs N cycles with no window, saves and exports, and prints the 1 G0 peak; `plots.py session.h5 --trace i` draws a saved trace to a PNG. Each file's
docstring (the top of the file) says what it does, what to look for, and
what its own options are. `--headless SECONDS` on the piezo sweep runs a
full-range sweep with no window, prints the ratio and writes a CSV: useful
as a first check on the lab PC before opening any window.

## Adding a test

Copy `01_piezo_sweep.py`, keep its shape: a worker thread that owns the rig
and does the moving, a window that only sets targets and reads the worker's
samples, `open_rig()` / `close_rig()` so the outputs are parked whatever
happens. Number the file, add a row to the table above, and say in the
docstring where the tip has to be before anyone runs it.
