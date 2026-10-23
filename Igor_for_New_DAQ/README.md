# Igor_for_New_DAQ -- the STM-BJ Igor procedures for ONE NI USB-6453

Ported 2026-10-22 from `../STMBJ2/MKLab_STMBJ - Copy/setup 1 code/` (the code the Python
port in `STM_Git` was built from). Two changes, as requested, and nothing else on purpose:

1. **No Keithley over GPIB.** Every GPIB command is commented out (`//[NEWDAQ-REMOVED: Keithley]`).
   The current amplifier is set **by hand on its front panel**. Igor keeps only the *gain number*
   (the Gain control, `G_CurrentVoltGain`) because it converts the preamp's volts to amps. Set the
   same gain on the amplifier and in the panel, or every current and conductance is off by 10x.
   The coarse actuator (NanoPZ over the serial port) and the X piezo are removed too
   (`//[NEWDAQ-REMOVED: Actuator]`); the coarse approach is done by hand.
2. **One DAQ card.** Everything is on `Dev1`, the USB-6453. The old second card (`dev2`, "LowRes")
   is gone (`//[NEWDAQ-REMOVED: LowRes]`). The piezo sense readback that used to be on the second card
   is now the third channel of the main input task, sampled on the same clock as voltage and current.

Changed or added lines carry a trailing `// [NEWDAQ]` comment, so `grep NEWDAQ *.ipf` shows every edit.
`PORTING_SPEC.md` is the design the edits follow.

## Files

| File | What |
|---|---|
| `Setup_NewDAQ_STMBJ.ipf` | **Open this one** (was `Setup1_STMBJ.ipf`). Includes the others, defines constants and the channel map, `InitializeExperiment()`, `rungo()`. |
| `Functions_STMBJ.ipf` | Measurement functions. 3-channel input task, one-clock alignment, piezo-only approach. |
| `Controls_STMBJ.ipf` | Button procedures. GPIB and Keithley procs commented out. |
| `Windows_STMBJ.ipf` | Panels and graphs. Keithley and actuator controls commented out, two group boxes retitled. |
| `EChem_Module.ipf` | Electrochemistry. Counter electrode moved to the one card (see caveats). |
| `STMBJ_HistogramAnalysis.ipf` | Offline analysis and plotting of saved PullOut blocks (histograms, 2D histograms, fits). Copied **unchanged** from `MKLab_STMBJ - Copy`, included by the setup file. Menu "PullOut", macro `PullOutAnalysis()`. No hardware, no extension. |
| `SetUpGPIB_Keithley.ipf` | Fully commented out, kept for reference; not included. |
| `DaqMxFunctions.xop` | The lab's DAQmx extension, unchanged (see caveat 1). |
| `tests/` | Mac-side test harness; **do not load anything from `tests/` on the lab PC** (see Testing). |

Not copied: `NanoPZ_Actuator_Functions_STM.ipf` (actuator and X piezo), `Source_Files/`.

**Opening the code on a Mac** (or any computer without the DAQ extension): `Setup_NewDAQ_STMBJ.ipf`
alone gives "expected a keyword or an object name" at the first `MXCreateTask`, because the `MX...`
functions live in the Windows-only extension. Open `tests/Mac_Preview_NewDAQ.ipf` instead: it loads
Igor stand-ins for those functions and then the real setup file, so everything compiles and the panels
open (Macros > STM Break Junction Measurement), but reads return zeros. Never open that file on the lab PC.

## Channel map (NI USB-6453, DAQmx name `Dev1`)

From the Python one-card config `STM_Git/python_code_entire_igor_w_GUI/configs/newpc_rig.json` (v64).
All constants live at the top of `Setup_NewDAQ_STMBJ.ipf`.

| Signal | Igor constant | Channel | Was |
|---|---|---|---|
| Z-piezo command (through the piezo driver box) | `HighResPiezoOut` | `Dev1/ao2` | `dev1/ao0` |
| Junction bias | `HighResBiasOut` | `Dev1/ao1` | `dev1/ao1` |
| Junction voltage monitor | `HighResVoltageIn` | `Dev1/ai9` | `dev1/ai0` |
| Current preamp output | `HighResCurrentIn` | `Dev1/ai10` | `dev1/ai1` |
| Piezo sense readback | `PiezoSenseIn` | `Dev1/ai11` | `dev2/ai0` (second card) |
| EChem counter electrode | `CounterElectrodeOut` | `Dev1/ao3` | `dev2/ao1` (second card) |

**All three inputs are RSE** (single-ended, BNC centre to the AI pin, shield to AI GND). They sit on
AI 9, 10, 11 rather than the Python config's AI 1, 2, 3 because those are the pins the card reads RSE
by default; see caveat 2. The Python config has to be changed to the same three channels so one
wiring serves both programs.

`HighRes`/`LowRes` in the names are history; there is one card now. The main input task
(`G_ID1`) carries three channels in this order: voltage, current, piezo sense (`K_NumAIChans = 3`).

## What changed in behaviour

- **Alignment.** With one clock there is nothing to cross-correlate between cards, so
  `GetLowHighOffset` is gone and the alignment spike is found in the junction voltage (`VoltageIn`),
  as the Python port does. The piezo readback `POExtension` is now truly aligned with the trace.
- **Start Approach** (panel button) used to step the actuator until the current rose above 0.1 uA.
  It now steps the **Z piezo** by the contact step size until |I| >= 0.1 uA. If the piezo reaches its
  voltage limit without contact, it retracts the piezo to where the approach started and prints: move
  the coarse stage closer by hand (a fraction of a turn), then press Start Approach again. It refuses
  to run until Start Writing has been pressed.
- **Gain** control: no GPIB write; it only updates the volts-to-amps conversion and prints a reminder.
- **Kill Tasks / Reset DAQ Device** reset the one card (`MXResetDevice(DAQDevice)`). A device reset
  puts **every output at 0 V**: piezo (fully retracted on this unipolar piezo), bias and counter
  electrode. On the old rig Kill Tasks left the bias on the junction; now it does not, until Start
  Writing is pressed again. Kill Tasks also enables the two CV buttons (a CV is allowed exactly when
  the writing task is OFF).
- **EChem**: the counter electrode is a software-timed single-sample output on `Dev1/ao3` so it can
  run beside the piezo/bias task; both CV buttons refuse to run while the writing task is ON
  (one card cannot run two hardware-timed output tasks). After a CV the device is reset, so the
  gate is switched off and the EChem panel shows it off; the CE-out CV ends a running gate first
  because the ramp uses the same output. The CV read timeout has 5 s of slack (the original waited
  exactly the ramp time). Buttons retitled "CV (bias out)" and "CV (CE out)"; control and function
  names unchanged.
- Panel text: "Reset DAQ Device" (singular), "Bias Output Range (V)", and the Start Writing tooltip name
  the real channels.
- Saved-file layout (`PullOut*Block_N.ibw`, `ParameterWave` indices) is unchanged.

## First run on the lab PC

1. In **NI MAX**, make sure the USB-6453 is named `Dev1` (every channel constant uses that name). Plug the
   junction-voltage, current and piezo-sense BNCs into **AI 9, AI 10, AI 11** (shields to AI GND) and
   open the Test Panel once to confirm each reads a known voltage in RSE (see caveat 2).
2. Put `DaqMxFunctions.xop` in the **32-bit** Igor's `Igor Extensions` folder (caveat 1) and start the
   32-bit Igor. On the lab PC (Igor Pro 7.08) that means: copy the file to
   `C:\Users\<you>\Documents\WaveMetrics\Igor Pro 7 User Files\Igor Extensions` (not the folder named
   `Igor Extensions (64-bit)`), quit Igor, and start **`Igor.exe`** from
   `C:\Program Files\WaveMetrics\Igor Pro 7 Folder\IgorBinaries_Win32\` (pin it to the taskbar), not
   `Igor64.exe` from `IgorBinaries_x64\`. The program folder's own `Igor Extensions` folder works too.
   Double-clicking an `.ipf` file opens the 64-bit one, so start Igor first and open the file from
   inside it. Check with `Print IgorInfo(0)` (must say `IGORKIND:pro`, not `pro64`) and
   `Print exists("MXCreateTask")` (must print `3`).
3. File > Open File > Procedure: `Setup_NewDAQ_STMBJ.ipf`. Compile. Then **Macros > STM Break Junction
   Measurement** (that runs `InitializeExperiment` and opens the panels). Start from a new experiment.
4. Set the amplifier gain on its front panel **and** type the same number into the panel's Gain box.
5. **Start Writing**, then Background Sampling to watch I, V and Piezo. Move the coarse stage by hand
   until the piezo can reach the surface: press **Start Approach**; at the piezo limit it retracts and
   asks for another fraction of a turn; repeat until it reports contact.
6. Find Offset, then Start Measurement as before. After the first traces look at `G_DelayOffset` in the
   history (the alignment delay the card showed); see the `NEWDAQ-NOTE` in `GenerateTrace` if it comes
   out near 2000 or traces are rejected for a missing pulse.

## Caveats you must read before the first run

1. **The DAQ extension is 32-bit Windows.** `DaqMxFunctions.xop` is a PE32 (32-bit) DLL. It loads
   only in the **32-bit Igor Pro** (`Igor.exe`, Igor 7 or 8), not in Igor64 and not in Igor 9. Put it
   in the 32-bit `Igor Extensions` folder as before. Its source is not in `STM_Igor`; if you ever want
   64-bit Igor, the XOP has to be rebuilt or replaced. **Install only this one extension.** The old
   folder also held `VISA.xop`, `VDT2.xop` (actuator) and `NIGPIB2.xop` (Keithley); none is used any
   more, and without the NI-VISA driver `VISA.xop` pops up "VISA Error: The specified module could not
   be found" every time Igor starts. Remove them from the `Igor Extensions` folder.
2. **Inputs are RSE, and that is why they are on AI 9, 10, 11.** `MXCreateAIVoltageChan` has no
   terminal-configuration argument, so the card's *default* mode applies to each channel and Igor
   cannot ask for RSE. From NI's USB-6453 specification: **AI 0-7 and AI 16-23** default to
   **differential** (AI n pairs with AI n+8); **AI 8-15 and AI 24-31** are single-ended only and
   default to **RSE**. So the three inputs use AI 9, AI 10, AI 11: BNC centre to the AI pin, shield to
   AI GND. Do not move them back to AI 1-3: there Igor would sample differentially with AI 9-11 as the
   floating minus inputs and read drifting nonsense. The Python config (`newpc_rig.json`) currently
   says `ai1`, `ai2`, `ai3`; change `ai_voltage`, `ai_current` and `ai_piezo_sense` to `ai9`, `ai10`,
   `ai11` (its `rse` setting stays) so the same cables work for both programs. Check the first
   Background Sampling reading against a known voltage before trusting a number.
3. **Piezo range.** `G_PiezoChanLow = -10`, `G_PiezoChanHigh = +10` are unchanged from the old code.
   The Z piezo on this rig is unipolar 0..10 V (that is what the Python config enforces). If the piezo
   driver box must never see a negative command, set `G_PiezoChanLow = 0` in `Declare_STMBJ_Variables`
   and the slider limits in `Windows_STMBJ.ipf`. This is your call; the port did not change hardware limits.
4. **Counter electrode on `Dev1/ao3` is a spare channel we chose; nothing is wired to it yet.** If you
   use EChem, wire it or change `CounterElectrodeOut`. Whether an on-demand output can run while the
   piezo/bias task runs has not been tried on this card; if DAQmx answers "resource reserved" (-50103),
   stop the writing task first.
5. **Calibration numbers are the old rig's**: `K_ZPiezoScale = 62` nm/V, `K_SenseScale = 314` nm/V,
   `G_SeriesResistance = 106130`. The Python config says the same and flags them as not re-measured.
6. **Engage threshold.** `G_ConductanceThreshold = 5` G0 cannot be reached with a 1e6 V/A preamp at
   100 mV (the input rails at 1.29 G0). Set the gain to 1e5 on the amplifier and in the panel, or lower
   the threshold, as before.
7. **Data path** is `C:Data:` (`DataDir` in the setup file), so blocks land in `C:\Data\<date>Merge\`. Create `C:\Data` once, or point `DataDir` elsewhere (Igor colon notation, parent folder must exist).
8. Start from a **new experiment**: old `.pxp` files carry the old globals and wave sizes.

## Pre-existing quirks the tests found (not changed)

These were already in the original code; the port keeps them so that new data stays comparable
with the archive. They are listed so you know them.

1. **Bias leads the piezo by one write buffer.** In `GenerateTrace` the bias segments are taken one
   buffer (1000 samples, 25 ms) ahead of the piezo segments, so the alignment spike leaves the card
   25 ms before the piezo ramp it belongs to, and every saved trace begins with 1000 points of pre-ramp
   hold while the last 1000 points of the pull are cut off. The aligned one-line alternative sits next
   to the original line, commented out (`grep NEWDAQ-NOTE Functions_STMBJ.ipf`). Switching it changes
   how new traces compare with old ones, so it is left for you to decide. (The Python port writes the
   whole ramp at once and does not have this shift.)
2. **Switching a ramp mode on in the middle of a 100-trace block fails.** The IV, AC-hold and
   high-bias modes turn "Save Bias" on, but `SavePullOut` creates the `VoltageBlock`/`CurrentBlock`
   waves only at the first trace of a block (Saved = 1, 101, 201, ...). Turning one of these modes on
   at, say, Saved = 37 gives Igor's "attempt to operate on a null (missing) wave" at the next saved
   trace. Start a mode at a block boundary, or tick Save Bias / Save Current before the block starts.
3. Small things: duplicate `NVAR PiezoOffset_nm` in `SavePullOut`; `LogHistFromBlocks` names a global
   `G_PulseFrontEdgePoint` that does not exist (unused there); the hidden checkbox
   `CounterElectrodeCheck_EChem` points at a procedure that was never written; `TestTrace` has its
   "did not start in contact" rejection commented out, so such traces are kept.
4. In `STMBJ_HistogramAnalysis.ipf` (unchanged copy): the "PullOut" menu item "Remove Pull Out /F3"
   calls `RemovePullOutNumber`, which does not exist anywhere, so that item errors when used; two
   buttons in its panel point at procedures that were never written (`FilterPullOutData`, `ButtonProc`);
   `PullOutAnalysis()` sets Windows data paths (`C:Data`, `C:DataAnalysis:SavedHist`) that you may need
   to edit for the new PC. It compiles and its other functions are as they were.

## Testing

Tested on this Mac with Igor Pro 8.04 (64-bit), with the Windows-only XOP replaced by Igor stubs:

- **Compiles** in Igor Pro 8 (`tests/run_compile_test_mac.sh`): all five files, no errors; Keithley and
  actuator functions absent, the rest present.
- **Static checks** (`tests/check_igor.py`): block balance, no reference to the second card, GPIB, VDT,
  Keithley or actuator outside comments, every `NVAR`/`SVAR` target declared, every control procedure defined,
  every read of `G_ID1` sized for three channels; compared against the original code as a baseline.
- **Simulated run** (`tests/MX_Sim_for_test.ipf` + `tests/Smoke_NewDAQ.ipf`): a pretend junction behind a
  pretend card (contact at 300 nm, a 1 G0 plateau, exponential tunnelling, a 37-sample output-to-input
  delay). Pass 1: every panel and graph builds, the Keithley and actuator controls are gone, Start
  Writing, the piezo-only approach stops 0.5 nm before the surface, a background read returns the bias
  and the piezo position, 100 traces through MakeContact / GenerateTrace / TestTrace / SavePullOut in
  17 s, the alignment spike is found, the log histogram peaks at 1 G0, `PullOutConductanceBlock_1.ibw`
  and the histogram file are written, Kill Tasks, and every DAQ task named only `Dev1/ai1;ai2;ai3`,
  `Dev1/ao2;ao1` or `Dev1/ao3`: **27 of 27 checks pass**. Pass 2: tab procedures, the Gain control, Step
  closer/apart, the slider, Tip Bias, Background Sampling on/off, an approach with no reachable surface
  (stops at the piezo limit and retracts to its start), Find Offset (Vzero fit and the Izero graph), one
  attempt in each of the push-pull / IV / AC-hold / high-bias modes, Smash, the EChem gate (500 mV reaches
  `Dev1/ao3`), both CVs refused while the writing task is ON, Kill Tasks, both CVs run with it OFF, Reset
  DAQ Device: **28 of 28 checks pass**. The code was also reviewed by three independent passes (Igor
  runtime, DAQmx on one card, scope and documentation) with every finding cross-checked; the confirmed
  ones are fixed in this version.
- **Static checker against the original** (`tests/check_igor.py --baseline`): 0 regressions; the two
  errors it reports are pre-existing (items 3 above); 7 baseline findings resolved by the port.

Not tested, because it needs the lab PC: the real XOP with the real card (channel grouping of the read
buffer, the RSE/differential question, the on-demand counter-electrode task), and the 32-bit Igor.

To repeat the Mac tests from this folder (**warning: the script quits and relaunches Igor64 on this Mac;
save any open Igor experiment first**):
```bash
tests/run_compile_test_mac.sh
```
```bash
tests/run_compile_test_mac.sh --smoke
```
```bash
python3 -I tests/check_igor.py . --baseline "../STMBJ2/MKLab_STMBJ - Copy/setup 1 code"
```
