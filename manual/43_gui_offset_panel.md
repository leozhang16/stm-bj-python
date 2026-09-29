# 43. The Voltage Offset panel and V0 tracking

*Igor: `Voltage_Offset()` panel, Windows_STMBJ.ipf:378-405; `FindOffset`, Controls_STMBJ.ipf:498; `OffsetVoltage` / `SaveOffset`, Functions_STMBJ.ipf:920 / 993. Modules: `stmgui/panels/voltage_offset.py`, `stmlab/vzero.py`.*

The lab calls this button **Find Zero**, and it is the first of the two
calibrations pressed before every Igor run. What it finds is the applied
bias at which no current flows — the amplifier chain's input offset,
expressed as an equivalent bias — and, optionally, keeps finding it as the
run goes on. Chapter 21 is the physics; this chapter is the panel.

## The panel

Igor's panel was a single group box titled "Voltage Offset" with seven
controls. Same seven here.

| Igor name | Title | Bound to / does |
|---|---|---|
| `TipBiasInterval` | Tip Bias interval (mV) | `cfg.vzero.interval_mv`: the sweep runs from −interval to +interval (default 5) |
| `NumPoints` | Number of points | `cfg.vzero.n_points`: points *per polarity*; the sweep has 2N (default 5, so 10) |
| `NumPoints1` | Frequency (traces) | `cfg.vzero.every_n_traces`: re-measure every N saved traces when V0 check is ON (default 50) |
| `VzeroCheckBox` | V0 check ON | `opts.vzero_check` |
| `FindOffset` | Find Offset | `RigController.find_offset` |
| `Vzero` | V0 (fit, mV) | display of `opts.vzero_mv` (Igor `G_Vzero`) |
| `Vzero1` | I0 (fit, uA) | display of `opts.izero_ua` (Igor `G_Izero`) |

Igor's V0 and I0 were editable SetVariables bound to the globals; here they
are read-only displays, because a hand-typed V0 would be fed into the
applied bias with nothing to say where it came from.

## What Find Offset does

**Igor** (`OffsetVoltage`, Functions_STMBJ.ipf:920-982): redimension the
waves to 2·NumPts; build a ramp from −|Bound| upward in steps of
|Bound|/NumPts; for each point call `HighResContact()` (step in at 100 mV
until above the conductance threshold), write the low bias, `Sleep/T 3`
(3 ticks, 50 ms), `ReadCurrentAndVoltage()` (5000 samples); then
`CurveFit line` of current against applied bias; `Izero = W_coef[0]` (the
intercept, in µA), `Vzero = -Izero / W_coef[1]` (mV); finally write the
original tip bias back.

**Now** (`stmlab.vzero.measure_offset`, called by `find_offset` on the
worker thread):

1. Remember the original bias, `cfg.ramp.bias_v`.
2. Build the bias points: `bias_mv = −|interval| + (|interval|/N) × k` for
   k = 0 … 2N−1 — Igor's line 951, so the sweep ends one increment short
   of +interval, as Igor's did.
3. For each point: `_ensure_contact` (Igor's `HighResContact`) sets 100 mV
   and steps the piezo in 2 nm at a time until `Rig.in_contact()` — above
   `cfg.ramp.engage_g0` or a railed preamp. It refuses at the piezo ceiling
   with `vzero: piezo at the ceiling with no contact; run the coarse
   approach before measuring the offset`; Igor's loop had no exit on that
   side. Then the bias point is applied, `cfg.vzero.settle_s` (50 ms)
   elapses, and 5000 samples are read, the last 4200 averaged (the
   `settle_discard` tail rule every DC read uses).
4. The original bias is restored (Igor line 980).
5. `numpy.polyfit(bias_mv, current_a, 1)`: slope in A/mV, intercept
   `izero` in A; `vzero_mv = −izero / slope`. A zero slope raises
   `vzero: flat I(V) -- no contact, or a railed preamp at every point`.

The controller then records the result (`_record_vzero`): `opts.vzero_mv`
and `opts.izero_ua = izero_a × 10⁶` for the two displays; the result
appended to `vzero_tracker.history`; `(Saved, I0)` appended to
`izero_history`; and three events — `vzero` for the panel, `izero` for the
Izero graph, `izero_time` for the Izero_Time graph. The piezo readout and
slider follow the position `_ensure_contact` left the tip at.

**You should see** the History line `Vzero = +0.000 mV (Izero =
-5.782e-10 A)` (the simulator's numbers; a real amplifier gives millivolts
and nanoamps), the two displays filling in, and the Izero window opening.

!FIG[figures/gui/Izero.png]{The Izero window after Find Offset on the simulator: the measured current at each applied bias (Igor's CurrentWave, pink markers), the fitted line (fit_CurrentWave, blue), and the V0 / I0 box Igor drew with a TextBox.}

## Why it is measured in contact

A line can only be fitted through a current that is measurable. Out of
contact, 5 mV across a tunnelling gap gives picoamps of current and a slope
made of noise. In contact the junction is a few kΩ, the current at 5 mV is
microamps, and the intercept is clean. That is why every point re-checks
contact first — a junction that breaks halfway through the sweep would
otherwise fit a line through two regimes — and why the routine has to
restore your bias afterwards: it has been driving the junction at voltages
you did not ask for.

It is also why the button belongs *after* Start Approach in the lab
sequence and before the run: the tip must be able to reach the surface,
and the number is only worth having if it is applied to what follows.

## V0 check ON

The checkbox is Igor's `VzeroCheckBox`, read in two places by
`CreateInputs` and in one by `SingleBreakJunctionAttempt`:

- **Constant-bias mode** (Functions_STMBJ.ipf:1609-1614): with the box
  ticked the applied bias wave became `-(TipBias + Vzero)/1000` instead of
  `-(TipBias)/1000`. Now: `_measure_impl` passes
  `vzero_tracker.offset_v` (V0 in volts, 0 if nothing has been measured)
  into `trace.build_ramp(bias_offset_v=...)`, which adds it to the DC
  baseline only. The alignment spike stays at +Tip Bias, as Igor's line
  1631 wrote it, so trace alignment does not depend on the offset. The
  bias recorded per trace in the session file is `bias_v + offset`, so a
  later reader knows what was actually applied.
- **High-bias-hold mode** (lines 1595-1599): with the box ticked the hold
  bias *became* the offset, `HBBias = Vzero/1000` — the zero-field control
  for the high-field runs. Now: `_build_ramp` passes `opts.vzero_mv` into
  `ramps.build_hb_hold(vzero_mv=...)`, whose `meta["from_vzero"]` records
  that it did.
- **Push-pull, IV, AC hold**: no effect, in Igor or here.
- **After every saved trace** (`SaveOffset`, line 993, called from
  `SingleBreakJunctionAttempt` at 1649): Igor re-measured the offset every
  `G_VzeroFrequency` saved traces and appended the result to `OffsetWave`,
  `IzeroWave` and `PullOutNumberWave`, then called `CreateInputs` again so
  the new V0 was in the next trace's bias. Now: `VzeroTracker.maybe_measure
  (rig, Saved)` runs after each accepted constant-mode trace, measures when
  `Saved % every_n_traces == 0`, and the next `build_ramp` picks up
  `tracker.offset_v`. Each measurement goes through the same
  `_record_vzero`, so the panel, the Izero window and the Izero_Time window
  all update mid-run.

The tracker's history is written into the session file's summary as
`vzero_history` (arrays of `vzero_mv`, `izero_a`, `timestamp`; chapter 47),
which is the equivalent of Igor's three waves.

!FIG[figures/gui/Izero_Time.png]{Izero_Time on the simulator with V0 check ON and Frequency set to 25 during a 100-trace run: one Find Offset before the run and four re-measurements, plotted against the Saved number at which each was taken. Igor's prescaleExp(left)=3 put the axis in µA × 10⁻³, kept here.}

## The history is the diagnostic

A single V0 is a correction. A *series* of them is a measurement of the
rig: an offset that drifts steadily over a session says the amplifier is
warming, the electrolyte is changing, or the tip is ageing — long before
the histogram shows it. Igor plotted `IzeroWave` against
`PullOutNumberWave` for exactly this reason, and the Izero_Time window is
that plot. Leave V0 check ON with a Frequency of 50 for any run that cares
about the low-bias region, and look at the window before trusting the
day's data.

## Pitfalls

- **Pressing Find Offset before Start Writing** refuses with `the output
  task is not running -- press Start Writing first`.
- **Before Start Approach**, on a real rig, the fine piezo cannot reach the
  surface; `_ensure_contact` climbs to the ceiling and refuses (message
  above). On the simulator the surface happens to be within reach from
  park, so this step is optional there.
- **At the piezo floor.** The routine steps *in*; it does not step out. If
  the tip is already in hard contact it fits a line through a metallic
  contact, which is fine — a few kΩ is exactly what it wants.
- **Simulator numbers.** The simulated card has a current offset but no
  bias offset, so V0 comes out at microvolts of noise. Do not read the
  simulator's V0 as a test of the fit; read the Izero window's straight
  line as one.
- **Zero check on the Keithley** must be off (Keithley Controls) for the
  current to be real; Igor ticked it on at every Kill Tasks and left it to
  you to untick.
- **The offset is not the preamp zero.** `calibrate.measure_zero` (run at
  Start Writing) measures the amplifier's *output* at zero bias out of
  contact and stores it as `cal.current_zero_v`, which every conductance
  subtracts. V0 is the *input* offset expressed as a bias, measured in
  contact, and is added to the applied bias. Both are needed; they correct
  different things.
