# 16. Lateral monolayer mapping

*Igor: `LateralEXPT`, `Setup1_STMBJ.ipf:91-136`. Experiment folder:
`experiments/07_lateral_monolayer/`. Module: `stmlab/xpiezo.py`.*

## What it measures

A histogram from one spot on the sample tells you about **that spot**. If the
monolayer is patchy, or the coverage varies, or there is a defect under the
tip, you will never know from the histogram alone — a clean single peak is
perfectly compatible with having measured one unrepresentative site a thousand
times.

This experiment walks the tip laterally across the sample and takes a **fresh
batch of traces at each site**. Comparing histograms site to site tells you
whether the molecular peak is a property of the monolayer or a property of the
place you happened to land.

## The sequence, and why the order is not negotiable

Per site, Igor did:

```
StartMeasurement("")             a batch of constant-bias traces
StepActuatorApart("") x3         withdraw, 100 ms between steps
MoveXPiezo(XDistance)            the lateral move
G_ActuatorStepSize = 5
SetPiezoBiasFromSlider(...)      reassert the bias
ApproachButton("")               coarse approach back into contact
```

**The X piezo moves only while the tip is withdrawn** — and withdrawn by
three *coarse actuator* steps, not merely a fine-piezo retract.

A lateral move in contact drags the tip through the monolayer. That does three
bad things at once: it destroys the film along the path, it reshapes the tip
apex, and it does both *silently* — the next site's traces look fine and are
measuring a different tip on damaged sample.

Three steps is the specific number Igor used and it is a good one: far enough
that a sample tilt across a 200 nm lateral move cannot crash the tip, close
enough that the coarse re-approach takes seconds rather than minutes.

## The X piezo

522 nm/V (`K_XPiezoScale`), on the low-res card's `ao0`. So a 200 nm step is
0.383 V, and the full 0–10 V range is **5.22 µm** of travel — about 26 sites
at 200 nm spacing before you run out.

`xpiezo.XPiezo` tracks its position and **refuses** out-of-range moves. Igor
did not check; it would simply have clipped, and every site past the clip
point would have been the *same* site while the file names went on
incrementing.

## Two cards

The X piezo is on the second card. Without `channels.low_res_device` this
experiment cannot run on hardware. `--simulate` substitutes
`SimulatedXPiezo`, which tracks position and enforces the same range.

## Running it

```bash
python run.py 07 --simulate --sites 5 -n 20
python run.py 07 --sites 20 -n 200 --step-nm 200
```

One `site_<i>.h5` per site, each carrying `site_index`, `x_position_nm`,
`x_piezo_v` and `x_step_nm` as file attributes — so a site's absolute
position survives independently of its filename.

## Reading the result

Compare the **peak position** and the **peak area per trace** across sites.

* Peak position stable, area stable → uniform coverage. Pool the sites.
* Position stable, area varies → patchy coverage; the molecule is the same
  where it is present. Still poolable, but report the variation.
* **Position varies** → the sites are not measuring the same thing. Do not
  pool. Something is wrong with the sample, or with the tip, and the
  site-to-site comparison has just saved you from publishing an average of
  two different molecules.

That third case is the reason to run this experiment at all.

## Status

The site loop, the withdraw/move/re-approach ordering, and the X piezo
range refusal are exercised end to end on the simulator and covered by tests.
The hardware path needs a second card that this rig does not currently have.

The simulated surface does not vary with X — every site is identical by
construction — so simulate tests the choreography and nothing about coverage.
