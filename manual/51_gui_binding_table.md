# 51. Appendix: the binding table

*Generated from `stmgui/state.py` by `manual_build/gen_binding_table.py`. Igor: `Declare_STMBJ_Variables`, Functions_STMBJ.ipf:5-198, and the `value=` bindings in Windows_STMBJ.ipf.*

Every panel control is bound to one row of this table. **Igor global** is the name the control was bound to in Igor; **lives in** is the attribute it writes now, dotted from a `GuiState` (`cfg.` is the `RigConfig` that every data file carries, `opts.` is `GuiOptions`, the panel-only state); **shown as** is the display unit where it differs from the stored one (Tip Bias is stored in volts, shown in mV); **limits** are Igor's `limits={lo, hi, increment}` (an increment gives the control arrow buttons); **default** is what a fresh panel shows.

Bool rows are checkboxes. Rows with no limits are display-only or unbounded, as in Igor.

## DAQ tab

| Igor global | Panel title | Lives in | Kind | Limits (lo, hi, inc) | Default |
|---|---|---|---|---|---|
| `G_AcquisitionRate` | Acquisition Rate | `cfg.ramp.sample_rate_hz` | float | 100, 200000, 0 | 40000 |
| `G_WriteBufferSize` | Write Buffer Size | `cfg.ramp.settle_samples` | int | 25, 2000, 0 | 1000 |
| `G_FastReadWaveSize` | Fast Read Wave Size | `opts.fast_read_wave_size` | int | 25, 2000, 0 | 200 |
| `G_HighResOutputRange` | HighRes Output Range (V) | `cfg.channels.bias_ao_range_v` | float | 0, 10, 0 | 2.5 |
| `K_ZPiezoScale` | Z piezo scale (nm/V) | `cfg.cal.piezo_nm_per_volt` | float |  | 62 |
| `K_SenseScale` | Z Sense scale (nm/V) | `opts.sense_scale_nm_per_v` | float |  | 314 |
| `G_PiezoOffset_nm` | Piezo offset (nm) | `opts.piezo_offset_nm` | float | 0, 620, 0 | 0 |

## Inputs tab

| Igor global | Panel title | Lives in | Kind | Limits (lo, hi, inc) | Default |
|---|---|---|---|---|---|
| `G_PullOutRate` | Pull Rate (nm/s) | `cfg.ramp.pull_rate_nm_per_s` | float | 0, 1000, 0 | 20 |
| `G_PseudoTotalLength_nm` | Excursion (nm) | `cfg.ramp.pull_length_nm` | float | 0.1, 500, 0 | 5 |
| `G_ConductanceThreshold` | Contact Threshold (G0) | `cfg.ramp.engage_g0` | float | 0, 10000, 0 | 0.5 |
| `G_MakeContactApproachStepSize` | Contact step size (nm) | `cfg.ramp.approach_step_nm` | float | 0, 50, 0 | 0.5 |
| `G_SeriesResistance` | Series R (Ohm) | `cfg.keithley.series_resistance_ohm` | float |  | 106130 |
| `G_EndOfTraceNoiseThreshold` | Zero Cutoff (G0) | `cfg.ramp.break_g0` | float | 0, 0.5, 0 | 0.0005 |
| `G_SmashFrequency` | Smash Freq. | `cfg.ramp.smash_every` | int | 0, inf, 0 | 50 |
| `G_SmashInSteps` | Smash In | `cfg.ramp.smash_in_nm` | float |  | 30 |
| `G_SmashOutSteps` | Smash Out | `cfg.ramp.smash_out_nm` | float |  | -40 |
| `G_BiasSaveCheck` | Save Bias | `opts.save_bias` | bool |  | off |
| `G_CurrentSaveCheck` | Save Current | `opts.save_current` | bool |  | off |
| `G_PiezoWaveSaveCheck` | Save Piezo Wave | `opts.save_piezo_wave` | bool |  | off |
| `G_SenseSaveCheck` | Save Sense | `opts.save_sense` | bool |  | off |
| `G_HistSaveCheck` | Save Hist | `opts.save_hist` | bool |  | on |
| `G_VoltageRead` | VoltageRead | `opts.voltage_read` | bool |  | off |

## Options tab: Push-Pull

| Igor global | Panel title | Lives in | Kind | Limits (lo, hi, inc) | Default |
|---|---|---|---|---|---|
| `G_PushPullCheck` | Push-Pull | `opts.push_pull_check` | bool |  | off |
| `G_NumPushPullCycles` | Number of cycles | `cfg.push_pull.cycles` | int | 1, inf, 1 | 2 |
| `G_InitialPullLength` | Initial Pull (nm) | `cfg.push_pull.initial_pull_nm` | float |  | 1 |
| `G_FinalPullLength` | Final Pull (nm) | `cfg.push_pull.final_pull_nm` | float |  | 4 |
| `G_PushPullLength` | Push-Pull length (nm) | `cfg.push_pull.push_pull_nm` | float |  | 1.5 |
| `G_HoldLength` | Hold length (nm) | `cfg.push_pull.hold_nm` | float |  | 1 |

## Options tab: IV

| Igor global | Panel title | Lives in | Kind | Limits (lo, hi, inc) | Default |
|---|---|---|---|---|---|
| `G_IVCheck` | IV | `opts.iv_check` | bool |  | off |
| `G_IVMaxBias` | MaxBias (V) | `cfg.iv.max_bias_v` | float |  | 1 |
| `G_IVSignFlag` | Sign: | `cfg.iv.positive_first` | bool |  | off |
| `G_IVInitPull` | Initial Pull (nm) | `cfg.iv.init_pull_nm` | float |  | 3 |
| `G_IVFinPull` | Final Pull (nm) | `cfg.iv.final_pull_nm` | float |  | 4 |
| `G_IVCapLength` | Cap length (nm) | `cfg.iv.cap_nm` | float |  | 0.5 |
| `G_IVRampLength` | Ramp length (nm) | `cfg.iv.ramp_nm` | float |  | 2 |

## Options tab: AC

| Igor global | Panel title | Lives in | Kind | Limits (lo, hi, inc) | Default |
|---|---|---|---|---|---|
| `G_ACHoldCheck` | AC Hold | `opts.ac_hold_check` | bool |  | off |
| `G_ACAmp` | Amp (V) | `cfg.ac_hold.amp_v` | float |  | 0.8 |
| `G_ACFreq` | Freq (kHz) | `cfg.ac_hold.freq_khz` | float |  | 10 |
| `G_ACInitPullLength` | Initial Pull (nm) | `cfg.ac_hold.init_pull_nm` | float |  | 3 |
| `G_ACHoldLength` | Hold length (nm) | `cfg.ac_hold.hold_nm` | float |  | 3 |
| `G_ACFinPullLength` | Final Pull (nm) | `cfg.ac_hold.final_pull_nm` | float |  | 4 |

## Options tab: High bias hold

| Igor global | Panel title | Lives in | Kind | Limits (lo, hi, inc) | Default |
|---|---|---|---|---|---|
| `G_HBHoldCheck` | High Bias Hold | `opts.hb_hold_check` | bool |  | off |
| `G_HBBias` | Hold bias (V) | `cfg.hb_hold.hold_bias_v` | float |  | 0.8 |
| `G_HBInitPullLength` | Initial Pull (nm) | `cfg.hb_hold.init_pull_nm` | float |  | 3 |
| `G_HBFinPullLength` | Final Pull (nm) | `cfg.hb_hold.final_pull_nm` | float |  | 4 |
| `G_HBHoldLength` | Hold length (nm) | `cfg.hb_hold.hold_nm` | float |  | 3 |
| `G_HBCapLengthIN` | Cap Length IN (nm) | `cfg.hb_hold.cap_in_nm` | float |  | 0.1 |
| `G_HBCapLengthFIN` | Cap Length FIN (nm) | `cfg.hb_hold.cap_fin_nm` | float |  | 0.1 |

## Keithley Controls

| Igor global | Panel title | Lives in | Kind | Limits (lo, hi, inc) | Default |
|---|---|---|---|---|---|
| `G_CurrentVoltGain` | Gain ( log(V/A) ) | `cfg.keithley.gain_exponent` | int | 3, 10, 1 | 6 |
| `G_CurrentSuppressConst` | Suppress I value | `cfg.keithley.suppress_const` | float | -1000, 1000, 0 | 0 |
| `G_KeithleyBiasEnabled` | Bias | `cfg.keithley.enabled` | bool |  | off |
| `ZeroCheckBox` | Zero Check | `opts.zero_check` | bool |  | on |
| `SuppressCheckBox` | Suppress I | `opts.suppress_on` | bool |  | off |

## Actuator and Piezo Controls

| Igor global | Panel title | Lives in | Kind | Limits (lo, hi, inc) | Default |
|---|---|---|---|---|---|
| `G_ActuatorStepSize` | Step Size | `cfg.actuator.step_size` | int | 1, inf, 1 | 5 |
| `G_ActuatorCounter` | (counter) | `opts.actuator_counter` | int |  | 0 |
| `G_PiezoDeltaZ_nm` | Z (nm) | `opts.piezo_step_nm` | float | 0, 100, 1 | 5 |

## Bottom of the panel

| Igor global | Panel title | Lives in | Kind | Limits (lo, hi, inc) | Default |
|---|---|---|---|---|---|
| `G_TipBias` | Tip Bias (mV) | `cfg.ramp.bias_v` | float (x1000 for display) | -5000, 5000, 0 | 100 |
| `G_PullOutNumber` | Saved | `opts.pull_out_number` | int | 0, inf, 0 | 1 |
| `G_StopNumber` | Stop # | `opts.stop_number` | int | 0, inf, 0 | 1001 |
| `G_PullOutAttempt` | Attempts | `opts.pull_out_attempt` | int | 0, inf, 0 | 0 |
| `OnCheck` | Background Sampling (Beep is ON) | `opts.bkgd_sampling` | bool |  | off |

## Voltage_Offset panel

| Igor global | Panel title | Lives in | Kind | Limits (lo, hi, inc) | Default |
|---|---|---|---|---|---|
| `G_VoltageInterval` | Tip Bias interval (mV) | `cfg.vzero.interval_mv` | float | 0.1, 1000, 0 | 5 |
| `G_NumPoints` | Number of points | `cfg.vzero.n_points` | int | 3, 1000, 1 | 5 |
| `G_Vzerofrequency` | Frequency (traces) | `cfg.vzero.every_n_traces` | int | 1, 5000, 10 | 50 |
| `VzeroCheckBox` | V0 check ON | `opts.vzero_check` | bool |  | off |
| `G_Vzero` | V0 (fit, mV) | `opts.vzero_mv` | float |  | 0 |
| `G_Izero` | I0 (fit, uA) | `opts.izero_ua` | float |  | 0 |

## EChem panel

| Igor global | Panel title | Lives in | Kind | Limits (lo, hi, inc) | Default |
|---|---|---|---|---|---|
| `G_CounterElectrodeBias` | Counter Electrode Bias (mV) | `cfg.echem.gate_mv` | float |  | 0 |
| `G_CVAcquisitionRate` | CV Acquisition Rate (samps/s) | `cfg.echem.cv_rate_hz` | float | 50, 40000, 0 | 1000 |
| `G_NumCVCycles` | Number of Cycles | `cfg.echem.cycles` | int | 0, 1000, 1 | 1 |
| `G_ScanRate` | Scan Rate (mV/s) | `cfg.echem.scan_rate_mv_per_s` | float | 0, 2000, 25 | 100 |
| `G_VoltagePeakOne` | Voltage Peak 1 (V) | `cfg.echem.peak_one_v` | float | -2.5, 0, 0.25 | -1 |
| `G_VoltagePeakTwo` | Voltage Peak 2 (V) | `cfg.echem.peak_two_v` | float | 0, 2.5, 0.25 | 1 |

## Readouts

| Igor global | Panel title | Lives in | Kind | Limits (lo, hi, inc) | Default |
|---|---|---|---|---|---|
| `G_CurrentSamplingReadoutVal` | I (uA) | `opts.current_readout_ua` | float |  | 0 |
| `G_JunctionVoltage` | V (mV) | `opts.junction_voltage_mv` | float |  | 0 |
| `G_PiezoBiasSamplingReadoutVal` | Piezo | `opts.piezo_readout_v` | float |  | 0 |
