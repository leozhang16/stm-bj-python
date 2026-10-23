# Porting spec: Igor STM-BJ code -> one NI USB-6453, no Keithley GPIB, no actuator

This file is the single source of truth for the port. Every edit in this folder
follows it. Base code: `../STMBJ2/MKLab_STMBJ - Copy/setup 1 code/` (byte-identical
to the `igor_code/` folder the Python port was built from). The files in this folder
started as normalized copies of those originals (CRLF -> LF, Latin-1 -> UTF-8).

Reference for the new wiring: `/Users/ly666/STM_Git/python_code_entire_igor_w_GUI/configs/newpc_rig.json`
(Python v64, the one-card USB-6453 config).

## 0. Three rules

1. **One DAQ card.** Every channel is on `Dev1`. Nothing references `dev2`, `Dev2`,
   `LowRes*` channel constants, or the second-card tasks `G_ID2`, `G_ID3`, `G_ID6`, `G_OD5`.
2. **No Keithley over GPIB.** Nothing calls `GPIB2`, `GPIBWrite2`, `NI4882`, `SetUpGPIB_Keithley`,
   `KeithleyBias*`, `KeithleyFilter*`, `LocalGPIB`, `RemoteGPIB`, `ZeroCheckProc`, `ZeroCorrectProc`,
   `CurrentSuppressCheckProc`, `SetCurrentSuppress`, `TestVirtualGround`, `FindSuppress`.
   The current preamp (physically still a current-to-voltage amplifier, possibly the same
   Keithley 428) is now set **by hand on its front panel**. Igor keeps only the *numbers* it
   needs to convert volts to amps: `G_CurrentVoltGain` and `G_CurrentVoltConversion` stay,
   and the panel's Gain control stays (it just updates those numbers, no GPIB write).
3. **No coarse actuator.** Nothing calls `VDT2`, `VDTWrite2`, `VDTOperationsPort2`,
   `StepActuatorApart`, `StepActuatorCloser`, `SetupXPiezo`, `MoveXPiezo`, `MoveXPiezoToZero`,
   `StopXPiezo`, `LateralEXPT`. The file `NanoPZ_Actuator_Functions_STM.ipf` is **not** copied
   into this folder (it is removed, not commented). The coarse approach is done by hand.

## 1. How to mark edits (so the diff is reviewable and greppable)

- A line that is disabled is kept in place and commented out with the prefix
  `//[NEWDAQ-REMOVED: <reason>]` where reason is one of `Keithley`, `Actuator`, `LowRes`.
  Example: `//[NEWDAQ-REMOVED: Keithley] GPIBWrite2 "C1X"`
- A line that is changed or added gets a trailing comment `// [NEWDAQ] <what/why>`.
- A rewritten block (more than ~5 lines) is preceded by a block comment
  `// [NEWDAQ] was: <one-paragraph summary of the old behaviour>` and the old lines are
  **not** kept (to avoid unreadable walls of commented code). Exception: Keithley code is
  always kept commented (the user asked for Keithley to be *commented out*).
- Every `.ipf` file gets, right after its existing header block, a short banner:
  ```
  // ---------------------------------------------------------------------------
  // [NEWDAQ] Ported 2026-10-22 for ONE NI USB-6453 (Dev1), no Keithley GPIB control,
  // no coarse actuator. See PORTING_SPEC.md and README.md in this folder.
  // ---------------------------------------------------------------------------
  ```
- Keep the files' existing `#pragma` lines exactly as they are (do not add `rtGlobals=3`
  to files that did not have it; it would change strictness and can break compilation).
  Do add `#pragma TextEncoding = "UTF-8"` as the first line of every file (Igor 7+).
- Write files as UTF-8 with LF line endings. (They are converted to CRLF at the end.)

## 2. Channel map (all `Strconstant`s live ONLY in `Setup_NewDAQ_STMBJ.ipf`)

| Igor constant | Value | Was | Signal |
|---|---|---|---|
| `DAQDevice` | `"Dev1"` | `"Dev1"` / `"Dev2"` literals | the one card; use it in every `MXResetDevice(...)` |
| `HighResPiezoOut` | `"Dev1/ao2"` | `dev1/ao0` | Z-piezo command (through the piezo driver box) |
| `HighResBiasOut` | `"Dev1/ao1"` | `dev1/ao1` | junction bias |
| `HighResVoltageIn` | `"Dev1/ai9"` | `dev1/ai0` | junction voltage monitor (RSE; AI 9 is an RSE-default pin, see note) |
| `HighResCurrentIn` | `"Dev1/ai10"` | `dev1/ai1` | current preamp output (RSE) |
| `PiezoSenseIn` | `"Dev1/ai11"` | `LowResPiezoIn = dev2/ai0` | piezo driver box sense (readback), now a 3rd channel of the main AI task (RSE) |

Note (2026-10-22, after the user asked for all inputs RSE): the XOP cannot set the terminal mode, and on the
USB-6453 AI 0-7 / 16-23 default to differential while AI 8-15 / 24-31 are single-ended only (RSE default).
The inputs were therefore moved from the Python config's ai1/ai2/ai3 to ai9/ai10/ai11; the Python config
must follow.
| `CounterElectrodeOut` | `"Dev1/ao3"` | `LowResCounterElectrodeOut = dev2/ao1` | EChem counter electrode. **Spare channel chosen by us, not yet wired; flagged in README** |

Removed constants (no replacement): `LowResPiezoIn`, `LowResCurrentIn`, `LowResVoltageIn`,
`LowResXPiezoOut`, `LowResCounterElectrodeOut`, `TCchan4`, `TCchan5`.

The names `HighRes*` are kept for the four main channels because they are used in hundreds
of places; a comment in the setup file says "HighRes/LowRes are historical names, there is
one card now".

Also in the setup file:
```
Constant K_NumAIChans = 3      // [NEWDAQ] channels in the main AI task G_ID1: voltage, current, piezo sense (in this order)
Constant K_G0= 77.480917346e-6
Constant K_ZPiezoScale = 62
Constant K_XPiezoScale = 522   // kept for reference; the X piezo is not driven in this version
Constant K_SenseScale = 314
Strconstant Setup= "Setup 1 (USB-6453)"
Strconstant SetupID= "_"
Strconstant DataDir= "D:Experiments:"
```

## 3. The main AI task `G_ID1` now has THREE channels

`SetUpHRTaskID1()` creates, in this order: `HighResVoltageIn`, `HighResCurrentIn`, `PiezoSenseIn`.

Facts about the XOP calls (inferred from the base code, keep them true):
- `MXCfgSampClkTiming(task, rate, sampleMode, N)`: `sampleMode` 0 = finite, 1 = continuous;
  `N` is **samples per channel**. Keep every existing per-channel `N` unchanged.
- `MXReadAnalogF64(task, timeout, numChans, wave)`: the wave must hold
  `numChans * samplesPerChannel` points, grouped **by channel**: block 0 = channel 0, etc.
  Every read of `G_ID1` becomes `MXReadAnalogF64(G_ID1, <timeout>, K_NumAIChans, <wave>)`
  and the wave is redimensioned to `<samplesPerChannel> * K_NumAIChans`.
- Partition after a read of `N` samples per channel:
  ```
  VoltageIn/VolHighResIn = <wave>[p]              (then negated where the old code negated)
  CurrentIn/CurHighResIn = <wave>[N + p]
  SenseIn (nm)           = <wave>[2*N + p] * K_SenseScale     (GenerateTrace)
  SenseInBkgd (volts)    = <wave>[2*N + p]                    (BackgroundRead; the Piezo (V) readout stays in volts as before)
  ```
- A read of the sense block that a function does not need may simply be ignored
  (the block is still read because the task has 3 channels).

The old second-card read waves `LowResReadWave`, `LowResReadWaveBkgd`, `CurrentInLowRes`,
`VoltageInLowRes` are removed (their `Make` lines commented out with the LowRes tag, and
every use removed). `SenseIn`, `SenseInBkgd`, `POExtension` stay.

## 4. File-by-file

### `Setup_NewDAQ_STMBJ.ipf` (was `Setup1_STMBJ.ipf`)
- Header comment updated; banner; `#pragma TextEncoding`; `#pragma rtGlobals=3` stays.
- Includes: `":Functions_STMBJ"`, `":Controls_STMBJ"`, `":Windows_STMBJ"`, `":EChem_Module"`.
  `#include ":SetUpGPIB_Keithley"` -> commented out `//[NEWDAQ-REMOVED: Keithley]`.
  `#include ":NanoPZ_Actuator_Functions_STM"` -> commented out `//[NEWDAQ-REMOVED: Actuator]`.
- Constants and channel map exactly as in section 2, with a comment table.
- `InitializeExperiment()`: drop the `SetUpGPIB_Keithley()` call (commented, Keithley tag). Keep
  the rest (Declare, MakePath, BreakJunctionMeasurement, InitializeEChem, Voltage_Offset).
- `Delay(ms)` stays. `rungo()` stays (it only uses StartMeasurement/StopWritingTasks).
- The three stray top-level calls `SetupXPiezo()`, `StopXPiezo()`, `MoveXPiezoToZero()` and the
  whole `LateralEXPT()` function -> commented out with the Actuator tag (they need the
  actuator and the X piezo on the second card).

### `SetUpGPIB_Keithley.ipf`
- Whole content commented out (every code line prefixed `//[NEWDAQ-REMOVED: Keithley] `),
  with a header explaining that the amplifier is set by hand and how to restore GPIB control
  (uncomment this file and the include, and the Keithley block in the panel).
  The file is kept in the folder but is NOT included.

### `Functions_STMBJ.ipf`
- `Declare_STMBJ_Variables()`:
  - comment out (LowRes tag): `G_ID2`, `G_ID3`, `G_ID6`, the `LowResReadWave`,
    `LowResReadWaveBkgd`, `CurrentInLowRes`, `VoltageInLowRes` Makes. Keep `SenseIn`, `SenseInBkgd`.
  - comment out (Keithley tag): `G_DeviceUD`, `G_BoardUD`, `G_KeithleyBiasEnabled`.
    KEEP `G_CurrentVoltGain`, `G_CurrentVoltConversion`, `G_CurrentSuppress`,
    `G_CurrentSuppressConst` (they are written into `ParameterWave` and used for V->A
    conversion; the saved-file layout must not change).
  - comment out (Actuator tag): `G_ActuatorStepSize`, `G_ActuatorCounter`.
  - `G_PiezoChanLow/High` stay as they are (-10/+10). Do NOT change them (README flags it).
- `SetUpHRTaskID1()`: add the third channel `PiezoSenseIn`.
- `SetUpLRTaskID3()`, `ClearLRTaskID3()`, `GetLowHighOffset()`: whole functions commented out (LowRes tag).
- `GenerateTrace()`: rewritten per section 3. Specifically:
  - no `G_ID3`, no `LowResReadWave`, `CurrentInLowRes`, `VoltageInLowRes`;
  - `HighResReadWave` -> `NumPtsIn*K_NumAIChans`; read with `K_NumAIChans`;
  - `SenseIn = HighResReadWave[2*NumPtsIn+p]*K_SenseScale`, then `Smooth/B 11, SenseIn` as before;
  - `LowHighOffset` is gone (one clock, nothing to cross-correlate);
  - the alignment pulse is found in `VoltageIn` (same sign convention as before: `VoltageIn = -HighResReadWave[p]`):
    `FindLevels/Q/P/R=[NumPtsIn-1,NumPtsIn-6000]/EDGE=0/N=2 VoltageIn, 0`;
    `DelayOffset = HighResFrontPulsePt - PulseFrontEdgePt`;
  - `PullOutVoltage=VoltageIn[p+DelayOffset]`, `PullOutConductance=PullOutCurrent/PullOutVoltage/K_G0`
    (DAQ-bias path only; the Keithley-bias `else` branch is commented out);
  - `POExtension=SenseIn[p+DelayOffset]` and update the stale comment: it IS aligned now
    (same clock);
  - graph offsets: `ModifyGraph Offset(CurrentIn)={0,0}`, `Offset(VoltageIn)={-DelayOffset,0}`;
    the `VoltageInLowRes` offset line is removed.
- `StartBkgdSampling()`: no `G_ID2` task; `SetUpHRTaskID1()`; `MXCfgSampClkTiming(G_ID1,AcquisitionRate,1,ReadWaveSize*2)`
  may stay as is (per-channel buffer, 2x headroom is fine) -- just make sure the bkgd read wave is
  `ReadWaveSize*K_NumAIChans`.
- `BackgroundRead()`: read `K_NumAIChans`; `SenseInBkgd = HighResReadWaveBkgd[2*ReadWaveSize+p]`;
  `PiezoBiasSample = Mean(SenseInBkgd)` (volts, as before). No `G_ID2`, no `LowResReadWaveBkgd`.
- `StopBkgdSampling()`: no `MXClearTask(G_ID2)`.
- `ReadCurrentAndVoltage()`: keep 2500 samples per channel: `ReadWaveSize=2500`,
  `HighResReadWaveSize = ReadWaveSize*K_NumAIChans`; read `K_NumAIChans`; partition first two blocks.
- `OffsetVoltage()`: its `MXCfgSampClkTiming(G_ID1,AcquisitionRate,1,HighResReadWaveSize)` with
  `HighResReadWaveSize=5000` is a per-channel buffer >= 2500; keep.
- `TestVirtualGround()`: whole function commented out (Keithley tag; it drives the Keithley suppress).
- `HighResMakeContact()`: `ContactCheckWave` -> `ReadWaveSize*K_NumAIChans`; three reads use
  `K_NumAIChans`; partition first two blocks; Keithley-bias branches commented out (keep the
  DAQ formula `Conductance= (Abs(Current)/Abs(Voltage))/K_G0`); `NVAR KeithleyBiasEnabled`
  and `NVAR SeriesResistance` lines handled accordingly (SeriesResistance NVAR may be removed
  if unused in the function).
- `CreateInputs()`: unchanged except the comment "Creates 2 waves for writing to NI PXI-4461" -> USB-6453.
- `MeasureBreakJunctions()`: remove the `SetUpLRTaskID3()` / `ClearLRTaskID3()` calls (LowRes tag).
- `HighResCardApproach()`: **rewritten** (block comment `// [NEWDAQ] was: coarse approach that stepped the
  NanoPZ actuator closer until |I| > 0.1 uA`). New behaviour, piezo only:
  ```
  // Fine approach with the Z piezo only. The coarse stage is moved BY HAND in this version.
  // Steps the piezo toward the sample by G_MakeContactApproachStepSize nm per step and reads
  // the current after each step (3-channel read of G_ID1, ReadWaveSize samples per channel).
  // Stops when |I| >= 0.1 uA (same stop level the old actuator loop used), or when the piezo
  // voltage would leave [G_PiezoChanLow, G_PiezoChanHigh], or on the Alt key.
  // At the limit it prints: "Approach: piezo at its limit with no contact. Move the coarse stage
  // closer BY HAND (a fraction of a turn), then press Start Approach again."
  ```
  It uses only existing globals (`G_MakeContactApproachStepSize`, `G_TipBias`, `G_PiezoOffset_nm`,
  `G_PiezoChanLow/High`, `G_CurrentSamplingReadoutVal`, `G_CurrentVoltConversion`,
  `G_FastReadWaveSize`, `G_AcquisitionRate`, `G_ID1`), `WriteToHighRes(step, TipBias)` for the
  step, and clears `G_ID1` on every exit path like the old function did. No new globals.
- Everything else (SavePullOut, LogHistFromBlocks, WriteToHighRes, TestTrace, SmashFun,
  SingleBreakJunctionAttempt, HighResContact, HighResOutOfContact, SaveOffset, MakePath):
  unchanged, except `NVAR` lines for removed globals, which must go.

### `Controls_STMBJ.ipf`
- `CurrentSuppressCheckProc`, `ZeroCheckProc`, `ZeroCorrectProc`, `SetCurrentSuppress`,
  `FindSuppress`: whole functions commented out (Keithley tag). The panel no longer has these controls.
- `StartHighResWritingTask`: unchanged (constants resolve to the new channels).
- `StopWritingTasks`: GPIB zero-check lines and `NVAR BoardUD/DeviceUD` -> commented (Keithley);
  `MXResetDevice("Dev2")` -> `MXResetDevice(DAQDevice)   // [NEWDAQ] one card; also stops the EChem counter-electrode task`;
  `CheckBox ZeroCheckBox value=1` -> commented (Keithley). Keep the EChem button enable/disable lines.
- `EChemResetDAQDevices`: one `MXResetDevice(DAQDevice)`.
- `SetGain`: GPIB lines and `NVAR BoardUD/DeviceUD` commented (Keithley). It still sets
  `CurrentVoltGain`, `CurrentVoltConversion`, `CurrentSuppress`, prints
  `"Gain set to <n> (software only: set the same gain on the amplifier front panel)"`, and still
  enables the two CV buttons.
- `SetTipBiasVoltage`: Keithley branch commented out; just `WriteToHighRes(0,TipBias)`.
- `ApproachButton`: unchanged (calls the new piezo-only `HighResCardApproach`).
- Everything else unchanged.

### `Windows_STMBJ.ipf`
- `HighRes()` graph: `Display ... VoltageIn` ; `AppendToGraph/R CurrentIn`; drop every
  `VoltageInLowRes`/`CurrentInLowRes` reference (rgb, offset). Keep the rest of the styling.
- `BreakJunctionMeasurement()` panel:
  - Keithley group: comment out (Keithley tag) `ZeroCheckBox` (2 lines), `KeithleyBias` (2 lines),
    `SuppressSetVar` (3 lines), `SuppressCheckBox` (2 lines), `FindSuppressButton` (2 lines),
    `ZeroCorrectButton` (2 lines). Keep `GroupBox box10105` but retitle it
    `"Current Amplifier (gain by hand)"`, and keep `setvar43` (the Gain control).
  - Actuator group: comment out (Actuator tag) `StepOpen` (2 lines), `StepTogether` (2 lines),
    `StepSizeSetVar` (3 lines), `ActuatorCounter_Valdisp` (4 lines). Keep `GroupBox ActuatorGroupBox`
    retitled `"Approach (coarse stage by hand)"` and keep `StartApproachButton` (title stays
    `"Start\rApproach"`).
  - Leave every other control exactly as it is (including the pre-existing orphan
    `CounterElectrodeCheck_EChem` whose proc does not exist in the base code either).
- `EChem()` panel: `StartCVLowResButton` title -> `"CV (CE out)"`; `StartCVHighResButton` title ->
  `"CV (bias out)"`. Nothing else.
- All other windows unchanged.

### `EChem_Module.ipf`
- `Declare_EChem_Variables`: `G_OD2` stays (counter-electrode task on Dev1); `G_LowResWriteBufferSize`
  stays as a name but its value becomes 1 (`// [NEWDAQ] one sample: software-timed output`).
- `StartEChemWriting()`: **rewritten**. Block comment `// [NEWDAQ] was: hardware-timed finite task on dev2/ao1`.
  New: a software-timed (on-demand) single-sample output so it can run beside the hardware-timed
  piezo/bias task `G_OD1` on the same card:
  ```
  MXCreateTask("G_OD2")
  MXCreateAOVoltageChan(G_OD2, CounterElectrodeOut, -5, 5)
  // no MXCfgSampClkTiming: on-demand output, one sample per write
  MXStartTask(G_OD2)
  MXWriteAnalogF64(G_OD2, CardTimeout, 1, LowResWriteWave)   // 1-point wave = 0 V
  ```
- `WriteToCounterElectrode(Voltage)`: redimension the 1-point wave, set `Voltage/1000`, and just
  `MXWriteAnalogF64(G_OD2, CardTimeout, 1, LowResWriteWave)` (no stop/start).
- `CVcurveHighRes()`: add a guard at the top:
  ```
  SVAR HighResOutputTaskStatus= G_HighResOutputTaskStatus
  if (StringMatch(HighResOutputTaskStatus,"ON"))   // [NEWDAQ] one card: the CV needs the AO; stop the writing task first
  	Print "CV: press Kill Tasks (stop the DAQ writing task) before running a CV."
  	return -1
  endif
  ```
  `CVCurveIn` -> `NumPtsVoltageRamp*K_NumAIChans`; read with `K_NumAIChans`; partition unchanged for
  the first two blocks. `MXResetDevice("Dev1")` -> `MXResetDevice(DAQDevice)`.
- `CVcurveLowRes()`: keep the function name (the button proc and the Controls file refer to the
  button by name). Same guard. Output channel `CounterElectrodeOut` instead of `LowResCounterElectrodeOut`
  (range -10,10 as before). `CVCurveIn` -> `*K_NumAIChans`, read `K_NumAIChans`. End with
  `MXResetDevice(DAQDevice)`. Add a comment that this CV puts the ramp on the counter-electrode
  output while the piezo/bias task is off.
- `StartCVHighResButton`, `StartCVLowResButton`: the GPIB zero-check dance is commented out
  (Keithley tag); each just calls its CV function and re-enables its button.

### `STMBJ_HistogramAnalysis.ipf` (added 2026-10-22 at the user's request)
Copied byte-for-byte from `../STMBJ2/MKLab_STMBJ - Copy/` and `#include`d from the setup file. Offline
analysis/plotting only: no hardware, no extension, no name collisions with the measurement files.
Pre-existing issues inside it are listed in README.md and left alone.

## 5. Globals that are REMOVED (no `NVAR` to them may remain anywhere)
`G_ID2`, `G_ID3`, `G_ID6`, `G_OD5`, `G_DeviceUD`, `G_BoardUD`, `G_KeithleyBiasEnabled`,
`G_ActuatorStepSize`, `G_ActuatorCounter`, `G_XPiezoPosition`? -- NO: `G_XPiezoPosition` and
`G_XPiezoVoltage` are declared in `Declare_STMBJ_Variables`; comment them out too (Actuator tag),
they were only used by the X-piezo functions.

## 6. Waves that are REMOVED (no reference may remain outside comments)
`LowResReadWave`, `LowResReadWaveBkgd`, `CurrentInLowRes`, `VoltageInLowRes`, `XPiezoVoltage`.

## 7. Functions that are REMOVED (no call may remain outside comments)
`SetUpLRTaskID3`, `ClearLRTaskID3`, `GetLowHighOffset`, `TestVirtualGround`,
`CurrentSuppressCheckProc`, `ZeroCheckProc`, `ZeroCorrectProc`, `SetCurrentSuppress`, `FindSuppress`,
`SetUpGPIB_Keithley`, `LocalGPIB`, `RemoteGPIB`, `KeithleyFilter`, `KeithleyFilterRiseTime`,
`KeithleyBias`, `KeithleyBiasVolt`, `StepActuatorApart`, `StepActuatorCloser`, `SetupXPiezo`,
`MoveXPiezo`, `MoveXPiezoToZero`, `StopXPiezo`, `LateralEXPT`.

## 8. Things deliberately NOT changed (flagged in README instead)
- `G_PiezoChanLow = -10` (the piezo is believed to be unipolar 0..10 V; changing a hardware limit is the user's call).
- `K_ZPiezoScale`, `K_SenseScale`, `G_SeriesResistance`: old rig's calibration numbers.
- The XOP cannot set the input terminal configuration (RSE/DIFF); the card's default applies.
- The data path `D:Experiments:`.
