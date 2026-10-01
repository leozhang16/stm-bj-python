# 02. Configuration reference

The source of truth is `stmlab/config.py`. Everything below is generated from
reading it; if this chapter and the file ever disagree, the file wins.

`RigConfig` is one object holding thirteen dataclasses, split by lifecycle:
`ChannelMap` changes when the rig changes, `SafetyLimits` is set once and
rarely touched, `RampConfig` is tuned per experiment, `Calibration` is
re-measured every session, and the mode/support configs (`PushPullConfig`
through `XPiezoConfig`) belong to individual experiments but are present on
every `RigConfig` so they travel in every data file. The whole config is
written as JSON into every HDF5 file's attributes -- a file whose gain you
cannot reconstruct six months later is not data.

Igor origins: the channel names and scale constants come from
Setup1_STMBJ.ipf:25-41, the `G_*` globals from `Declare_STMBJ_Variables`
(Functions_STMBJ.ipf:5-198), and the mode branches' globals from
Functions_STMBJ.ipf:91-123. Where a default deliberately differs from
Igor's, the table says so.

Module-level constant: `G0_SIEMENS = 7.7480917346e-5` -- the conductance
quantum 2e^2/h, Igor's `K_G0` (Setup1_STMBJ.ipf:25).

## ChannelMap (`cfg.channels`)

Which physical channel carries what. AI channels enter the DAQmx task in the
order of `ai_channels` -- voltage first, current second, the same order as
Igor's `SetUpHRTaskID1` (Functions_STMBJ.ipf:243).

| Field | Default | Unit | Igor origin | Meaning |
|---|---|---|---|---|
| `device` | `"Dev1"` | -- | Setup1_STMBJ.ipf:25-34 | DAQmx alias of the PXI-4461 |
| `ao_piezo` | `"ao0"` | -- | Setup1_STMBJ.ipf | Z-piezo command, via the piezo driver box |
| `ao_bias` | `"ao1"` | -- | Setup1_STMBJ.ipf | Junction bias output |
| `ai_voltage` | `"ai0"` | -- | Setup1_STMBJ.ipf | Junction-voltage monitor input |
| `ai_current` | `"ai1"` | -- | Setup1_STMBJ.ipf | Current-preamp output input |
| `ai_range_v` | `10.0` | V | -- | Symmetric range of both AI channels |
| `bias_ao_range_v` | `2.5` | V | `G_HighResOutputRange` | Card-enforced range of the bias AO channel (the piezo AO range comes from `SafetyLimits`, so hardware clip and software check can never disagree -- Igor passed `G_PiezoChanLow/High` into `MXCreateAOVoltageChan`, Controls_STMBJ.ipf:152) |
| `expected_product_type` | `"PXI-4461"` | -- | -- | Product-type check in `verify_devices()`; `None` skips it |
| `low_res_device` | `None` | -- | Setup1_STMBJ.ipf:36-41 ("dev2") | Igor's second card: piezo sense readback, X piezo on ao0, EChem counter electrode on ao1. `None` means "this rig has one card" and every feature needing it refuses cleanly |
| `low_res_expected_product_type` | `"PXIe-6361"` | -- | -- | Product-type check of the second card in `verify_devices()` and `bringup 1`, only when `low_res_device` is set; `None` skips it |
| `ai_piezo_sense` | `"ai2"` | -- | Setup1_STMBJ.ipf (SenseIn / POExtension) | Piezo sense readback: the driver box's monitor output, on the *low-res* card. Read in its own one-channel task during every play, same N and rate, started by the same `ao/StartTrigger`, and carried beside the record as `Rig.last_sense_v` / `TraceRecord.piezo_sense_v`. Needs `low_res_device`; `None` means no sense line |
| `sense_ai_range_v` | `10.0` | V | -- | Range of the sense input |

Class constants (`ClassVar`, deliberately excluded from `asdict()` and the
data files because they describe this code's array layout, not the rig):
`ROW_VOLTAGE = 0`, `ROW_CURRENT = 1` (input rows), `ROW_PIEZO = 0`,
`ROW_BIAS = 1` (output rows). Derived helpers: `path(ch)`, `ai_channels`,
`ao_channels`, `ao_start_trigger` (`/<device>/ao/StartTrigger` -- the
terminal AI triggers off, derived rather than hardcoded), `has_piezo_sense`
and `piezo_sense_path` (`<low_res_device>/<ai_piezo_sense>`, or `None`).

## SafetyLimits (`cfg.limits`)

Values beyond which something breaks -- not values you intend to use. All
piezo limits are expressed at the DAQ output, before the driver box, because
the displacement calibration (`cal.piezo_nm_per_volt`) is also DAQ-side and
already folds in the box's gain. This piezo is **unipolar, 0 to 10 V**:
Igor's own bipolar defaults (`G_PiezoChanLow/High` = -10/+10,
Functions_STMBJ.ipf:1294) would drive it 10 V the wrong way, and Igor itself
flagged the unipolar case at Functions_STMBJ.ipf:44.

| Field | Default | Unit | Igor origin | Meaning |
|---|---|---|---|---|
| `piezo_ao_min_v` | `0.0` | V | replaces `G_PiezoChanLow` (-10) | Piezo output floor; 0 V is fully retracted, the safe state |
| `piezo_ao_max_v` | `10.0` | V | `G_PiezoChanHigh` | Piezo output ceiling |
| `bias_max_v` | `0.5` | V | -- (Igor's tip bias was 0.1 V; `rungo` reached 1.1 V) | Hard refusal, not a clamp; IV (1 V), AC (0.8 V) and HB (0.8 V) runners raise it deliberately with a loud log line |
| `preamp_saturation_v` | `9.5` | V | -- | Above this the preamp output is railed and the reading is meaningless; a railed channel counts as contact |
| `max_coarse_steps` | `2000` | steps | -- | Approach runaway budget |
| `coarse_step_max_piezo_v` | `0.1` | V | -- | THE interlock: a coarse step is refused unless the piezo is at or below this (0.1 V = 6.2 nm residual extension) |

## RampConfig (`cfg.ramp`)

Trajectory and sampling; Igor's `Declare_STMBJ_Variables` defaults.

| Field | Default | Unit | Igor origin | Meaning |
|---|---|---|---|---|
| `sample_rate_hz` | `40_000.0` | Hz | `G_AcquisitionRate` | Requested AI/AO sample rate (the *granted* rate is what time axes use) |
| `pull_length_nm` | `5.0` | nm | `G_PseudoTotalLength_nm` | Length of one constant-bias pull; mode runners overwrite it with the mode's net descent so the headroom pre-check matches |
| `pull_rate_nm_per_s` | `20.0` | nm/s | `G_PullOutRate` | Retraction speed; also the rate at which every mode length is converted to samples |
| `bias_v` | `0.100` | V | `G_TipBias` (100 mV) | DC junction bias baseline |
| `engage_g0` | `0.5` | G0 | `G_ConductanceThreshold` (Igor: 5) | Contact threshold. Deliberately lowered: 5 G0 at Rf = 1e6 V/A and 100 mV needs 38.7 V at the ADC, unreachable on a +/-10 V input; 0.5 G0 needs 3.87 V. Saturation additionally counts as contact |
| `break_g0` | `5e-4` | G0 | `G_EndOfTraceNoiseThreshold` | Below this the junction counts as broken |
| `approach_step_nm` | `0.5` | nm | `G_MakeContactApproachStepSize` | Fine-approach step size |
| `retract_step_nm` | `5.0` | nm | -- | Separation step magnitude (applied negative) |
| `settle_samples` | `1000` | samples | `G_WriteBufferSize` | Samples played/captured per DC move (Igor wrote 1000 per `WriteToHighRes`) |
| `settle_discard` | `800` | samples | cf. `G_FastReadWaveSize` (Igor averaged 200) | Leading samples discarded before averaging a DC record |
| `pre_pad_samples` | `400` | samples | -- (new) | Constant lead-in so the 4461's decimation filter settles outside the region of interest |
| `post_pad_samples` | `400` | samples | -- (new) | Constant tail keeping the delayed alignment spike inside the record |
| `spike_front_ms` | `7.5` | ms | Functions_STMBJ.ipf:1618-1631 | Alignment-spike front edge, before the end of the ramp |
| `spike_back_ms` | `2.5` | ms | Functions_STMBJ.ipf:1618-1631 | Alignment-spike back edge |
| `smash_every` | `50` | attempts | `SmashFun`, Functions_STMBJ.ipf:1375 | Tip conditioning interval; 0 disables |
| `smash_in_nm` | `30.0` | nm | `SmashFun` | Smash drive-in distance |
| `smash_out_nm` | `-40.0` | nm | `SmashFun` | Smash pull-back distance |
| `traces_target` | `1000` | traces | `G_StopNumber - G_PullOutNumber` | Default accepted-trace target |
| `max_attempts` | `100_000` | attempts | -- | Attempt budget for a run |
| `piezo_park_v` | `0.0` | V | -- | Idle fine-piezo position; 0 V is retracted and is where the card parks itself |
| `piezo_headroom_v` | `0.02` | V | cf. Functions_STMBJ.ipf:44 (`G_PiezoOffset_nm` "MUST BE LARGER THAN EXCURSION SIZE") | Reserve above the floor; a pull that would descend below it is refused rather than clipped |

Derived properties: `n_pull_samples` (Igor's `G_NumPtsInAppliedWaves`,
`round(pull_length / pull_rate * sample_rate)`), `n_record_samples`
(pull plus both pads), `seconds_per_pull`.

## Calibration (`cfg.cal`)

Measured constants; produced by `calibrate.py`, saved per session.

| Field | Default | Unit | Igor origin | Meaning |
|---|---|---|---|---|
| `preamp_gain_v_per_a` | `1e6` | V/A | `G_CurrentVoltGain` (stored as the exponent 6) | Transimpedance of the current preamp |
| `current_zero_v` | `0.0` | V | -- | Preamp resting offset; hundreds of microvolts, drifts with temperature, re-measure every session (`validate` warns while it is 0) |
| `piezo_nm_per_volt` | `62.0` | nm/V | `K_ZPiezoScale` | Displacement per volt at the DAQ output, end to end including the driver box |
| `hv_amp_gain` | `None` | -- | -- | Driver-box gain if ever measured separately; documentation only, nothing multiplies by it |
| `sense_nm_per_volt` | `314.0` | nm/V | `K_SenseScale` | Displacement per volt on the piezo *sense* line (`channels.ai_piezo_sense`). Converts the readback to nm for SenseInDisplay and `Session.piezo_sense()`; the displacement axis of every trace stays the commanded one |
| `bias_output_sign` | `-1.0` | -- | Functions_STMBJ.ipf:347 | Igor writes `-(TipBias/1000)` to ao1 |
| `voltage_input_sign` | `-1.0` | -- | Functions_STMBJ.ipf:358 | Igor negates ai0 to recover the junction voltage |
| `ai_gain_error` | `1.0` | -- | -- | Slope from the DC loopback sweep; identity until measured |
| `ai_offset_v` | `0.0` | V | -- | Offset from the DC loopback sweep |
| `granted_sample_rate_hz` | `None` | Hz | -- | Filled at run time; a delta-sigma card does not always grant the requested rate, and every time axis must use the granted one |
| `group_delay_samples` | `None` | samples | -- | Fixed AI/AO delay if measured; left `None`, each trace recovers its own delay from the alignment spike |

Conversion methods: `volts_to_amps`, `volts_to_g0`, `g0_to_volts` (used by
the validator to catch clipping before acquiring), `nm_to_piezo_volts`,
`piezo_volts_to_nm`.

## ActuatorConfig (`cfg.actuator`)

Coarse-approach actuator. Igor drove a Newport NanoPZ over serial with
`0MO` then `0PR<n>` (NanoPZ_Actuator_Functions_STM.ipf:6-23).

| Field | Default | Unit | Igor origin | Meaning |
|---|---|---|---|---|
| `kind` | `"none"` | -- | -- | `"none"` (approach by hand), `"nanopz"` (serial), or `"simulated"` |
| `port` | `"COM1"` | -- | Igor hardcoded Com1 | Serial port; USB connections usually appear as COM3 or higher |
| `baud` | `19200` | baud | NanoPZ_Actuator_Functions_STM.ipf | Serial rate (8N1, CRLF line endings) |
| `step_size` | `5` | steps | `G_ActuatorStepSize` | Steps per coarse move; negative counts move toward the sample |
| `settle_s` | `0.10` | s | -- | Wait after each coarse step |
| `stop_current_ua` | `0.1` | uA | `G_CurrentSamplingReadoutVal`, Functions_STMBJ.ipf:1780 | Current above which the coarse approach stops |

## Mode configs

Igor: `CreateInputs`' four GUI-selected branches
(Functions_STMBJ.ipf:1461-1599) and their globals (:91-123). All lengths are
nanometres *at the pull rate* -- Igor's parameterisation, so a 3 nm "hold"
lasts as long as pulling 3 nm would (150 ms at the default 20 nm/s).

### PushPullConfig (`cfg.push_pull`)

Igor declared these globals with no defaults (set from the GUI,
Functions_STMBJ.ipf:91-96); the values below are working values, not Igor's.

| Field | Default | Unit | Igor origin | Meaning |
|---|---|---|---|---|
| `initial_pull_nm` | `3.0` | nm | `G_InitialPullLength` | Pull before the first cycle |
| `push_pull_nm` | `1.0` | nm | `G_PushPullLength` | Excursion of each push and each pull within a cycle |
| `hold_nm` | `1.0` | nm | `G_HoldLength` | Hold length either side of each push |
| `final_pull_nm` | `4.0` | nm | `G_FinalPullLength` | Pull after the last cycle, breaking the junction for good |
| `cycles` | `2` | -- | `G_NumPushPullCycles` | Cycles per trace |

Net descent is `initial_pull_nm + final_pull_nm`: the cycles net to zero.

### IVConfig (`cfg.iv`)

Igor defaults, Functions_STMBJ.ipf:99-105.

| Field | Default | Unit | Igor origin | Meaning |
|---|---|---|---|---|
| `init_pull_nm` | `3.0` | nm | `G_IVInitPull` | Pull before the held sweep |
| `final_pull_nm` | `4.0` | nm | `G_IVFinPull` | Pull after it |
| `cap_nm` | `0.5` | nm | `G_IVCapLength` | DC settling cap either side of the sweep |
| `ramp_nm` | `2.0` | nm | `G_IVRampLength` | Length (i.e. duration at the pull rate) of the triangular sweep window |
| `max_bias_v` | `1.0` | V | `G_IVMaxBias` | Sweep peak, both polarities |
| `positive_first` | `False` | -- | `G_IVSignFlag` | Negate the ramp segment a second time (Igor line 1535), so the sweep goes to the POSITIVE apex first. Left False, Igor's wholesale negation at line 1533 makes the sweep go negative first. |

### ACHoldConfig (`cfg.ac_hold`)

Igor defaults, Functions_STMBJ.ipf:108-114.

| Field | Default | Unit | Igor origin | Meaning |
|---|---|---|---|---|
| `init_pull_nm` | `3.0` | nm | `G_ACInitPullLength` | Pull before the hold |
| `final_pull_nm` | `4.0` | nm | `G_ACFinPullLength` | Pull after it |
| `hold_nm` | `3.0` | nm | `G_ACHoldLength` | Hold length; the sine replaces the DC baseline entirely here (Igor line 1564) |
| `cap_nm` | `0.5` | nm | `G_ACCapLength` | DC cap either side of the hold |
| `amp_v` | `0.8` | V | `G_ACAmp` | Sine amplitude |
| `freq_khz` | `10.0` | kHz | `G_ACFreq` | Sine frequency, in kHz as Igor's was |

### HBHoldConfig (`cfg.hb_hold`)

Igor defaults, Functions_STMBJ.ipf:117-123.

| Field | Default | Unit | Igor origin | Meaning |
|---|---|---|---|---|
| `init_pull_nm` | `3.0` | nm | `G_HBInitPullLength` | Pull before the hold |
| `final_pull_nm` | `4.0` | nm | `G_HBFinPullLength` | Pull after it |
| `hold_nm` | `3.0` | nm | `G_HBHoldLength` | Hold length |
| `cap_in_nm` | `0.1` | nm | `G_HBCapLengthIN` | Cap before the hold |
| `cap_fin_nm` | `0.1` | nm | `G_HBCapLengthFIN` | Cap after the hold |
| `hold_bias_v` | `0.8` | V | `G_HBBias` | Hold bias, written as `-hold_bias_v` like the baseline; overridden by the measured Vzero when `build_hb_hold(vzero_mv=...)` is passed (Igor lines 1595-1599) |

## VzeroConfig (`cfg.vzero`)

The Voltage_Offset workflow: find the applied bias that nulls the current.
Igor: `OffsetVoltage`/`SaveOffset`, Functions_STMBJ.ipf:920-1041.

| Field | Default | Unit | Igor origin | Meaning |
|---|---|---|---|---|
| `interval_mv` | `5.0` | mV | `G_VoltageInterval` | The bias sweep is +/- this |
| `n_points` | `5` | points | `G_NumPoints` | Points per polarity (2N total) |
| `every_n_traces` | `50` | traces | `G_VzeroFrequency` | `VzeroTracker.maybe_measure` re-measures at this interval; <= 0 disables |
| `settle_s` | `0.05` | s | Igor `Sleep/T 3` (3 ticks = 50 ms) | Wait after each bias step |

## KeithleyConfig (`cfg.keithley`)

Keithley 428 current amplifier over GPIB. Igor: SetUpGPIB_Keithley.ipf
(address 22) and `SetGain`/`SetCurrentSuppress`,
Controls_STMBJ.ipf:290-311, 460-477.

| Field | Default | Unit | Igor origin | Meaning |
|---|---|---|---|---|
| `resource` | `"GPIB0::22::INSTR"` | -- | `ibdev={0,22,...}` | VISA resource string |
| `gain_exponent` | `6` | log10(V/A) | `G_CurrentVoltGain` | Transimpedance gain exponent; `set_gain` programs `H6R<g>X` |
| `suppress_const` | `0.0` | -- | `G_CurrentSuppressConst` | Constant from which the suppress current is derived: `suppress_ua = const * 10**(3 - gain)` |
| `series_resistance_ohm` | `106130.0` | ohm | `G_SeriesResistance` | Series resistance for the corrected conductance when the Keithley sources the bias |
| `enabled` | `False` | -- | `G_KeithleyBiasEnabled` (started 0) | Whether the Keithley's internal bias source is in use |

## EChemConfig (`cfg.echem`)

Electrochemistry. Igor: EChem_Module.ipf; the counter electrode lived on the
low-res card's ao1 (Setup1_STMBJ.ipf:11), the high-res CV drove the junction
bias channel (dev1/ao1) instead.

| Field | Default | Unit | Igor origin | Meaning |
|---|---|---|---|---|
| `counter_electrode_channel` | `"ao1"` | -- | Setup1_STMBJ.ipf:11 | Channel on `channels.low_res_device` carrying the gate |
| `gate_mv` | `0.0` | mV | `G_CounterElectrodeBias` | DC gate potential; updated by `CounterElectrode.set_mv` so it travels in every data file (Igor saved it as ParameterWave[18]) |
| `cv_rate_hz` | `1000.0` | Hz | `G_CVAcquisitionRate` | CV sample rate |
| `scan_rate_mv_per_s` | `100.0` | mV/s | `G_ScanRate` | Potential sweep rate |
| `peak_one_v` | `-1.0` | V | `G_VoltagePeakOne` | First triangle vertex |
| `peak_two_v` | `1.0` | V | `G_VoltagePeakTwo` | Second triangle vertex |
| `cycles` | `1` | -- | `G_NumCVCycles` | CV cycles per run |

## XPiezoConfig (`cfg.xpiezo`)

Lateral X piezo on the low-res card, for monolayer experiments. Igor:
`SetupXPiezo`/`MoveXPiezo`, NanoPZ_Actuator_Functions_STM.ipf:25-100.

| Field | Default | Unit | Igor origin | Meaning |
|---|---|---|---|---|
| `channel` | `"ao0"` | -- | Setup1_STMBJ.ipf:40 | Channel on `channels.low_res_device` |
| `nm_per_volt` | `522.0` | nm/V | `K_XPiezoScale` | Lateral scale -- almost an order of magnitude coarser than the Z piezo's 62 nm/V |
| `min_v` | `0.0` | V | -- | Output floor; moves outside the range are refused (Igor did not check) |
| `max_v` | `10.0` | V | -- | Output ceiling |

## RigConfig (top level)

| Field | Default | Meaning |
|---|---|---|
| `channels` .. `xpiezo` | the thirteen dataclasses above | See each table |
| `simulate` | `False` | Run against `sim.SimulatedDaqSession` and the simulated instruments instead of hardware |
| `notes` | `""` | Free text, travels in every data file |

Serialisation: `to_dict()` / `to_json(path)` and `from_dict()` /
`from_json(path)`. `from_dict` tolerates unknown keys (with a logged
warning) so files written by older versions of the package still open --
re-analysis with a corrected calibration is the whole reason raw volts are
stored.

## validate(cfg)

`validate` checks a config **before any hardware is touched**. It raises
`ConfigError` on fatal problems and returns a list of warning strings
otherwise; every runner calls it first and logs the warnings. Fatal checks
include: 1 G0 clipping the AI range, bias over its own limit or zero, engage
threshold at or below the break threshold, a pull longer than the piezo range
or its usable headroom, a park position or interlock threshold outside the
piezo range, non-positive sample rate, a pull under 100 points, and an
alignment spike that does not fit in the pull. Warnings include: 1 G0 above
preamp saturation (usually acceptable), an engage threshold only reachable by
saturation (the failure Igor's own defaults would have hit), a break
threshold at the noise floor, a granted rate differing from the requested
one, an unmeasured `current_zero_v`, an unknown `hv_amp_gain`, and a pull
using more than half of the usable piezo range.
