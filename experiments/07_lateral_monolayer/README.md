# Lateral monolayer mapping

Batches of constant-bias break-junction traces at a series of sites stepped
laterally across a molecular monolayer: measure, withdraw, move the X piezo,
re-approach, repeat.

## Physics

A break-junction histogram built at a single spot samples one tiny patch of
the monolayer with one tip apex, and after a few thousand pulls that patch is
ploughed up: molecules are displaced or consumed, and the statistics drift.
The honest fix is fresh area, and the expensive way to get it is to vent,
re-insert the tip somewhere else, and pump back down. The lateral experiment
gets fresh area for free: after each batch the tip is lifted well clear of
the surface and the sample is translated a few hundred nanometres under it
by a dedicated lateral (X) piezo, then the tip is brought back into contact.
Each site contributes an independent batch, so the map yields both a
spatially averaged histogram (thousands of traces that do not all come from
one wounded patch) and per-site histograms that reveal monolayer
inhomogeneity -- domain boundaries, coverage variations, contaminated
regions -- as site-to-site shifts in the conductance peak.

The **order of operations is a hard rule**: the X piezo moves ONLY while the
tip is withdrawn. A lateral move in contact drags the tip through the
monolayer, which both destroys the film along the track and reshapes the tip
apex -- exactly the two things the experiment exists to protect. And a
fine-piezo retract alone is not enough clearance: over a 200 nm lateral step
the sample surface can tilt by more than the fine piezo's few-nm working
range, so each withdrawal takes **three coarse actuator steps apart** (with
short settling pauses) before the move, and the approach afterwards is a
fresh coarse approach if the fine piezo can no longer reach.

Per cycle (Igor's sequence, translated one-to-one):

1. **Measure** -- a batch of constant-bias traces at the current site,
   the same acquisition loop as `experiments/01_constant_bias`.
2. **Withdraw** -- park the fine piezo, then 3 coarse actuator steps apart,
   100 ms pause after each.
3. **Move** -- X piezo by `--step-nm` (default 200 nm), tip clear of the
   surface.
4. **Re-approach** -- reassert the bias, engage; if the fine piezo cannot
   reach the surface, coarse-approach until current appears, then engage.

## Igor origin

- `LateralEXPT(ZDistance, XDistance, XFreq)`, **Setup1_STMBJ.ipf:91-136** --
  the site loop: `StartMeasurement` (:114), `StepActuatorApart` three times
  with `Delay(100)` (:117-122), `MoveXPiezo(XDistance)` (:125),
  `G_ActuatorStepSize=5` + `SetPiezoBiasFromSlider` + `ApproachButton`
  (:129-131), looping until `G_StopNumber` reaches 12201 (:98, :134) --
  i.e. `12201/XFreq` sites; here the count is `--sites` directly.
- The per-site batch: `MeasureBreakJunctions`, **Functions_STMBJ.ipf:1664**
  (translated as `stmlab.trace.trace_loop`).
- X piezo control: `SetupXPiezo`/`MoveXPiezo`/`MoveXPiezoToZero`/`StopXPiezo`,
  **NanoPZ_Actuator_Functions_STM.ipf:25-100** (translated as
  `stmlab.xpiezo`, 522 nm/V on the low-res card's ao0).

## Hardware needed

- The main DAQ card (piezo Z, bias out, current + voltage in) -- as for
  experiment 01.
- A **coarse actuator** (`actuator.kind = "nanopz"`, serial): the withdraw
  sequence is three coarse steps apart, and the re-approach may need to walk
  back in. With `actuator.kind = "none"` the site loop cannot run.
- The **low-res (second) DAQ card** for the X piezo
  (`channels.low_res_device`, X on its `ao0` at 522 nm/V). On a single-card
  rig (`low_res_device = None`) the run refuses cleanly with an
  `XPiezoError`.
- In `--simulate`, none of the above: the actuator is switched to
  `"simulated"` automatically and the X piezo only tracks position.

## Running

Simulated smoke test (no hardware):

    cd D:/Minjung/Masha_Research/STM_with_Python/python_code_entire_igor
    ./.venv/Scripts/python.exe experiments/07_lateral_monolayer/run_experiment.py --simulate --sites 2 --traces-per-site 5 --out-dir data/smoke07

Real measurement (Igor's `LateralEXPT(10, 200, 250)` ballpark: ~48 sites of
250 traces, 200 nm apart):

    ./.venv/Scripts/python.exe experiments/07_lateral_monolayer/run_experiment.py --sites 48 --traces-per-site 250 --step-nm 200 --out-dir data/lateral_map01

Options: `--config PATH` (rig config JSON), `-v/--verbose`,
`--no-calibrate` (skip the session zero / group-delay measurement),
`-o/--out-dir` (default `data/lateral_<timestamp>/`). Ctrl-C finishes the
current site, writes its file, and stops; a second Ctrl-C exits immediately.

## What is stored

One HDF5 file **per site**: `<out-dir>/site_<i>.h5`, standard
`stmlab.storage` layout (`voltage_v`, `current_v` as raw ADC volts, one row
per accepted trace, plus `delay_samples`, `start_piezo_v`, `bias_v`,
`sample_rate_hz`). Extra root attributes identify the site:

- `site_index` -- 0-based site number
- `x_position_nm` -- absolute X piezo position when the batch was taken
- `x_piezo_v` -- the corresponding X channel voltage
- `x_step_nm` -- the commanded step between sites
- `run_stats_json` -- per-site accepted/attempts/rejections

## Reading the data

```python
from stmlab.storage import Session
from stmlab.analysis import log_histogram

with Session("data/smoke07/site_0.h5") as s:
    x_nm = s._h5.attrs["x_position_nm"]
    g0 = s.conductance(0)              # first trace, in units of G0
    print(len(s), "traces at x =", x_nm, "nm")
```

Build one histogram per site to see spatial variation, or concatenate the
conductance traces of every `site_*.h5` for the map-averaged histogram.
