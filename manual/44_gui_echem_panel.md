# 44. The Electrochemistry panel

*Igor: `EChem()` panel, Windows_STMBJ.ipf:436-473; EChem_Module.ipf. Modules: `stmgui/panels/echem_panel.py`, `stmlab/echem.py`.*

Igor's EChem module did two unrelated things through one panel: it held a
DC potential on a counter electrode while break-junction traces were
taken (electrochemical gating), and it ran cyclic voltammetry by driving a
triangle wave out of one card and recording the tip current. The panel
has the same two group boxes — **Electrochemical Gating** and **Cyclic
Voltammetry** — with Igor's controls in each. Chapter 15 is the physics
and the command-line version (`experiments/06_echem_gate_cv`); this
chapter is the panel.

> Nothing in this panel has ever driven a real second card or a real cell
> from this code. The simulator exercises every line; the hardware paths
> are transcriptions of Igor's calls. Bring up on the scope first.

## Electrochemical Gating

| Igor name | Title | Igor proc | Does now |
|---|---|---|---|
| `StartEChemWriteButton` | Counter Electrode ON | `CounterElectrodeOn` → `StartEChemWriting` | `RigController.counter_electrode_on` |
| `CounterElectrodeSetVar` | Counter Electrode Bias (mV) | `CounterElectrodeSetVar` → `WriteToCounterElectrode` | `set_counter_electrode(mv)`; `cfg.echem.gate_mv` |

**Igor** created an output task on the low-res card's `ao1`
(`LowResCounterElectrodeOut = "dev2/ao1"`, Setup1_STMBJ.ipf:11) with a
±5 V range, wrote the current `G_CounterElectrodeBias`, then greyed the
button and enabled the entry (EChem_Module.ipf:41-48). Typing a new bias
wrote it at once. `StopWritingTasks` and `EChemResetDAQDevices` reversed
the enable states and reset the card.

**Now**, Counter Electrode ON calls `stmlab.echem.make_counter_electrode
(cfg).on()` — a `SimulatedCounterElectrode` in simulate, otherwise a
`CounterElectrode` that opens an `nidaqmx` task on
`{channels.low_res_device}/{echem.counter_electrode_channel}` with
`min_val=-5.0, max_val=5.0`, as Igor's `MXCreateAOVoltageChan(-5,5)` — and
then writes the bias currently in the entry. If `channels.low_res_device`
is `None`, which is this one-card rig's default, it refuses with
`EChemError: no low-res device configured (channels.low_res_device is
None); the counter electrode lives on the second card`. `--simulate`
pretends a `Dev2` so the panel can be exercised.

After ON the button greys, the entry wakes, and every committed value goes
to `CounterElectrode.set_mv`, which writes `mv/1000` volts and stores the
value in **`cfg.echem.gate_mv`** — so the gate potential travels in the
`config_json` of every session file written while it is applied. That is
the point of doing it through the config rather than a local variable: a
trace file taken under gate says so.

The entry is refused before ON with `press Counter Electrode ON first`.
**Kill Tasks** releases the gate (`CounterElectrode.off()`, which writes
0 V, closes the task and zeroes `cfg.echem.gate_mv`) and puts the panel
back to its starting state; **Reset DAQ Devices** does the same after
resetting the cards, as Igor's `EChemResetDAQDevices` set
`CounterElectrodeBias = 0` (Controls_STMBJ.ipf:228). Both emit a `gate`
event with `None`, which is what the panel listens for.

A gate that should outlive the process — set from a script, then left
standing while the command-line experiment runs — is `off(zero=False)` in
the module; the GUI never does that, because the panel is the process.

## Cyclic Voltammetry

| Igor name | Title | Bound to |
|---|---|---|
| `SetGain` | Gain ( log(V/A) ) | `cfg.keithley.gain_exponent` and `cfg.cal.preamp_gain_v_per_a` (the same entry as on the main panel) |
| `CVAcquisitionRateSetVar` | CV Acquisition Rate (samps/s) | `cfg.echem.cv_rate_hz` (50 … 40000, default 1000) |
| `NumCVCyclesSetVar` | Number of Cycles | `cfg.echem.cycles` (default 1) |
| `ScanRateSetVar` | Scan Rate (mV/s) | `cfg.echem.scan_rate_mv_per_s` (0 … 2000 in steps of 25, default 100) |
| `VoltagePeakOneSetVar` | Voltage Peak 1 (V) | `cfg.echem.peak_one_v` (−2.5 … 0 in steps of 0.25, default −1) |
| `VoltagePeakTwoSetVar` | Voltage Peak 2 (V) | `cfg.echem.peak_two_v` (0 … 2.5 in steps of 0.25, default 1) |
| `StartCVHighResButton` | CV HighRes | `start_cv("highres")` |
| `StartCVLowResButton` | CV LowRes | `start_cv("lowres")` |

Igor's five SetVariable procedures (`VoltagePeakOneSetVar` and friends,
EChem_Module.ipf:414-466) each copied the typed value into its global;
the bindings do that directly.

### The two buttons

Igor enabled both CV buttons only after `SetGain` had run
(Controls_STMBJ.ipf:314-315) and disabled them again at `StopWritingTasks`
(lines 204-205). The reason is worth keeping: a voltammogram is a current,
and the current is the amplifier's output divided by a gain the analysis
has to know. So the buttons are greyed until the Gain entry (either copy)
has been committed once in this launch, and greyed again by Kill Tasks.

**CV HighRes** (`CVcurveHighRes`, EChem_Module.ipf:106) drove the triangle
out of the *high-res card's bias channel* — `dev1/ao1`, the same output
the break-junction bias uses — with the tip as working electrode, and read
both `ai0` (the electrode voltage) and `ai1` (the tip current). **CV
LowRes** (`CVcurveLowRes`, line 234) drove it out of the low-res card's
counter-electrode channel with a ±10 V range and read the tip current only.
`stmlab.echem.run_cv(cfg, kind)` does the same two things:

- `kind="highres"`: `build_cv_ramp_highres` builds the wave (below); on
  hardware `_run_cv_hardware` opens an AO task on
  `channels.path(ao_bias)` with a range wide enough for both peaks, an AI
  task on both input channels, both finite at `cv_rate_hz`, and — one
  deliberate improvement — starts the AI on the AO's start trigger, where
  Igor started the two tasks back to back and lived with the skew. Each
  cycle returns a `CVCycle` with `applied_v`, `tip_current_v` (raw preamp
  volts), `we_voltage_mv` (the measured electrode voltage) and `keep`.
- `kind="lowres"`: `build_cv_ramp_lowres` (5000 samples of 0 V first, then
  the triangle with a longer repeated tail, Igor lines 251-286); the AO
  task on the second card's counter-electrode channel at ±10 V; tip
  current only, `we_voltage_mv` is `None`.

In simulate, `_run_cv_simulated` replaces the cell with a model: a 1 µF
double-layer capacitance whose current flips sign with the scan direction
(the rectangular part of the loop) and one reversible couple with anodic
and cathodic peaks 60 mV apart around +0.2 V, plus noise. Not chemistry —
shape, enough to test every line of the analysis and the plot.

### The ramp and the keep mask

Igor's high-res wave (lines 127-158) was 0 → Peak 1 → 0 → Peak 2 → 0, then
the first half again, and it NaN-ed the first quarter (the switch-on
transient) and the repeated half so that what remained was one closed
cycle starting and ending at the same potential. `build_cv_ramp_highres`
builds exactly that wave, with the number of samples per leg from
`2 × |peak| / scan_rate × cv_rate_hz`, and returns beside it a boolean
`keep` that is `False` where Igor wrote NaN. Keeping the mask *beside* the
complete record instead of destroying the samples means a later reader can
second-guess the choice. A ramp with fewer than four samples per leg is
refused: `CV ramp too short; slow the scan rate or raise cv_rate_hz`.

### What the button does around the sweep

`StartCVHighResButton` (EChem_Module.ipf:364-387) checked the main panel's
Zero Check box, sent `C0X` to lift zero check if it was ticked, ran the
sweep, and sent `C1X` to put it back. `RigController._cv_impl` does the
same: if `opts.zero_check` is set and the Keithley is connected, zero
check is lifted, the sweep runs inside a `try`, and zero check is restored
in the `finally`.

One refusal Igor did not have: on hardware, **CV HighRes while the output
task is running** is refused with `CV HighRes drives the junction-bias
channel; Kill Tasks first (Igor reset the card afterwards)`. Two tasks
cannot own `dev1/ao1` at once; Igor let them collide and then
`MXResetDevice`'d the card. In simulate there is nothing to collide with
and the refusal is not raised.

After the sweep, `storage.save_cv_cycles` writes
`data/<date>/cv_<kind>_<HHMMSS>.h5` (layout in chapter 47), the cycles are
kept as `controller.last_cv`, and a `cv` event opens or redraws the
CyclicVoltammogram window.

!FIG[figures/gui/CyclicVoltammogram.png]{The Cyclic Voltammogram window after CV HighRes on the simulator: tip current in µA against applied potential in mV, x axis reversed as Igor's SetAxis/A/R bottom had it, the masked switch-on quarter and repeated tail left out. The rectangle is the double-layer current; the pair of peaks is the model couple.}

### Reading the numbers

The plotted current is `tip_current_v / cal.preamp_gain_v_per_a`, in µA.
With the default gain of 10⁶ V/A, 0.1 µA of double-layer current is
0.1 V at the ADC; a real cell with a large electrode can put out far more,
and a railed channel shows as a flat top at ±10 V. Lower the gain (the
Gain entry on this panel) before a CV on a real cell, and remember that
the same entry sets the gain the break-junction conductance divides by —
put it back before the next Start Measurement, or `validate()` will tell
you about the mismatch in the History.

## Between the two groups

Igor's gating and CV were independent — you could gate while measuring
traces and never run a CV, or run CVs with no gate. The same holds here,
with one practical link: on hardware a CV HighRes needs the output task
off, so the sequence for a gated voltammogram on this rig is Counter
Electrode ON, set the bias, Kill Tasks if the task was running, CV
HighRes, then Start Writing again for traces.
