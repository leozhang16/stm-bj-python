#pragma TextEncoding = "UTF-8"
#pragma rtGlobals=3

// ---------------------------------------------------------------------------
// Smoke_NewDAQ.ipf -- end-to-end dry run of the ported procedures on the
// simulated DAQ (MX_Sim_for_test.ipf). TEST ONLY, do not load on the lab PC.
//
// Run from the command line (or from tests/run_compile_test_mac.sh --run):
//     ClaudeSmokeRun("Macintosh HD:path:to:result.txt")
//
// It goes through the lab sequence with the simulator standing in for the card:
//   declare globals -> build every panel and graph -> Start Writing ->
//   Start Approach (piezo only) -> one background read -> Start Measurement
//   for two traces (saved numbers 99 and 100, so the 100-block save and the
//   log histogram run) -> Kill Tasks.
// Then it writes a result file with PASS/FAIL lines a script can grep.
// Any Igor runtime error aborts the function; "do script" returns its text.
// ---------------------------------------------------------------------------

Static Function Rep(refnum, ok, what)
	Variable refnum, ok
	String what
	fprintf refnum, "%s %s\r", SelectString(ok, "FAIL", "PASS"), what
	return ok
End

// Run one Igor command with runtime errors caught (no dialog): a FAIL line with the
// error text instead of an aborted test. Returns 1 if the command ran cleanly.
Static Function RunStep(refnum, cmd)
	Variable refnum
	String cmd
	Variable t0 = StopMSTimer(-2)
	Variable err = 0
	String msg = ""
	try
		Execute/Q/Z cmd; AbortOnRTE
		err = V_Flag
		if (err != 0)
			msg = GetErrMessage(err)
		endif
	catch
		err = GetRTError(1)
		msg = GetErrMessage(err)
	endtry
	Variable secs = (StopMSTimer(-2) - t0)*1e-6
	if (err != 0)
		fprintf refnum, "FAIL %s -> Igor error %d: %s\r", cmd, err, msg
		return 0
	endif
	fprintf refnum, "INFO %s ran in %.1f s\r", cmd, secs
	return 1
End

Function ClaudeSmokeRun(resultPath)
	String resultPath

	Variable refnum
	Open refnum as resultPath
	fprintf refnum, "SMOKE RUN %s\r", date() + " " + time()

	// ---- 1. globals, path, panels -------------------------------------------------
	Declare_STMBJ_Variables()
	Declare_EChem_Variables()
	Sim_Init()
	NVAR simZ = sim_ZScale
	NVAR simS = sim_SenseScale
	simZ = K_ZPiezoScale
	simS = K_SenseScale

	// a fresh folder per run: Save without /O asks "replace?" in a dialog if the file exists,
	// which would stall a headless run at trace 100
	String tmp = SpecialDirPath("Temporary", 0, 0, 0) + "ClaudeIgorSmoke_" + num2istr(DateTime) + ":"
	NewPath/O/C/Q Data tmp
	Rep(refnum, V_flag == 0, "NewPath Data -> " + tmp)
	String/G G_PathDate = "smoke"

	Execute "BreakJunctionMeasurement()"
	Execute "Voltage_Offset()"
	Execute "EChem()"
	Execute "HighRes()"
	Execute "SenseInDisplay()"
	Execute "PullOutGvsE()"
	Execute "PullOutLow()"
	Execute "AuAuConductanceLevel()"
	Execute "LogHistOfBlock()"
	Rep(refnum, WinType("BreakJunctionMeasurement") == 7, "main panel built")
	Rep(refnum, WinType("EChem") == 7 && WinType("Voltage_Offset") == 7, "EChem and Voltage_Offset panels built")
	Rep(refnum, WinType("HighRes") == 1 && WinType("SenseInDisplay") == 1, "HighRes and SenseInDisplay graphs built")
	// the removed Keithley / actuator controls must be gone, the kept ones present
	ControlInfo/W=BreakJunctionMeasurement ZeroCheckBox
	Rep(refnum, V_flag == 0, "ZeroCheckBox (Keithley) absent from the panel")
	ControlInfo/W=BreakJunctionMeasurement StepTogether
	Rep(refnum, V_flag == 0, "StepTogether (actuator) absent from the panel")
	ControlInfo/W=BreakJunctionMeasurement StartApproachButton
	Rep(refnum, V_flag != 0, "StartApproachButton present")
	ControlInfo/W=BreakJunctionMeasurement setvar43
	Rep(refnum, V_flag != 0, "Gain control present")

	// ---- 2. make the thresholds reachable on the simulated preamp -----------------
	NVAR Gain = G_CurrentVoltGain
	NVAR Conv = G_CurrentVoltConversion
	NVAR Thresh = G_ConductanceThreshold
	NVAR simGain = sim_GainExp
	Gain = 5
	Conv = 10^(6-Gain)
	simGain = Gain
	Thresh = 1.5			// G0; 1.5 G0 * 0.1 V * 1e5 V/A = 1.16 V at the preamp, well below the 10 V rail

	// ---- 3. Start Writing, approach, background read -----------------------------
	StartHighResWritingTask("")
	SVAR status = G_HighResOutputTaskStatus
	Rep(refnum, StringMatch(status, "ON"), "writing task ON")
	NVAR Offset_nm = G_PiezoOffset_nm
	NVAR TipBias = G_TipBias
	WriteToHighRes(250 - Offset_nm, TipBias)		// park 50 nm short of the simulated surface
	Rep(refnum, abs(Offset_nm - 250) < 1e-6, "piezo parked at 250 nm")

	RunStep(refnum, "HighResCardApproach()")
	NVAR Iread = G_CurrentSamplingReadoutVal
	Rep(refnum, abs(Iread) >= 0.1, "fine approach stopped on current >= 0.1 uA (I = " + num2str(Iread) + " uA)")
	Rep(refnum, Offset_nm > 290 && Offset_nm < 300.5, "approach ended just before the surface (z = " + num2str(Offset_nm) + " nm)")

	StartBkgdSampling()
	STRUCT WMBackgroundStruct s
	BackgroundRead(s)
	NVAR Vread = G_JunctionVoltage
	NVAR Pread = G_PiezoBiasSamplingReadoutVal
	Rep(refnum, abs(Vread - TipBias) < 1, "background read: junction voltage " + num2str(Vread) + " mV ~ tip bias " + num2str(TipBias) + " mV")
	Rep(refnum, abs(Pread*K_SenseScale - Offset_nm) < 2, "background read: sense " + num2str(Pread*K_SenseScale) + " nm ~ piezo " + num2str(Offset_nm) + " nm")
	StopBkgdSampling()

	// ---- 4. two traces through the whole pipeline ---------------------------------
	NVAR PullOutNumber = G_PullOutNumber
	NVAR StopNumber = G_StopNumber
	NVAR Attempt = G_PullOutAttempt
	NVAR SingleFlag = G_SingleAttemptFlag
	NVAR DelayOffset = G_DelayOffset
	NVAR simDelay = sim_DelayPts
	NVAR WriteBufferSize = G_WriteBufferSize
	// A full block of 100 traces, numbered 1..100 as in the lab: SavePullOut makes the block
	// waves at trace 1 and writes the .ibw files and the log histogram at trace 100.
	PullOutNumber = 1
	StopNumber = 101
	SingleFlag = 0
	Variable attemptsBefore = Attempt
	RunStep(refnum, "MeasureBreakJunctions()")
	Rep(refnum, PullOutNumber == 101, "100 traces accepted and saved (PullOutNumber = " + num2str(PullOutNumber) + ", attempts used = " + num2str(Attempt - attemptsBefore) + ")")
	// LEGACY BEHAVIOUR, inherited from the original code (GenerateTrace's segment loop):
	//   HighResWriteWave[WriteBufferSize,2*WriteBufferSize-1] = JunctionBiasWave[k*WriteBufferSize+p]
	// uses the destination index p (WriteBufferSize..2*WriteBufferSize-1), so every bias segment
	// is taken ONE SEGMENT AHEAD of the piezo segment: the bias (and its alignment spike) leaves
	// the card WriteBufferSize samples before the piezo ramp it belongs to. GenerateTrace therefore
	// recovers (true delay - WriteBufferSize) and aligns the trace to that. The simulator reproduces
	// the card faithfully, so this test asserts the legacy relation and prints both numbers.
	fprintf refnum, "INFO recovered DelayOffset = %d samples; simulated true delay = %d; WriteBufferSize = %d\r", DelayOffset, simDelay, WriteBufferSize
	Rep(refnum, abs(DelayOffset - (simDelay - WriteBufferSize)) <= 2, "alignment spike found where the legacy code puts it (DelayOffset = true delay - WriteBufferSize, see comment in Smoke_NewDAQ.ipf)")
	Wave PullOutConductance
	WaveStats/Q/R=[0, 50] PullOutConductance
	Rep(refnum, V_avg > 0.8 && V_avg < 5, "trace starts in contact (mean G of first 50 points = " + num2str(V_avg) + " G0)")
	Variable np = numpnts(PullOutConductance)
	WaveStats/Q/R=[np*0.9, np*0.91] PullOutConductance
	Rep(refnum, abs(V_avg) < 5e-4, "trace ends open (G at 90% = " + num2str(V_avg) + " G0)")
	Wave POExtension
	// with the legacy one-segment lead the first WriteBufferSize points of the saved trace are
	// the pre-ramp hold, so the readback spans (5 nm) * (1 - WriteBufferSize/np)
	Variable expectSpan = 5 * (1 - WriteBufferSize/np)
	Rep(refnum, abs((POExtension[0] - POExtension[np-1]) - expectSpan) < 0.3, "sense readback spans the pull as saved (" + num2str(POExtension[0] - POExtension[np-1]) + " nm, expected " + num2str(expectSpan) + " nm)")
	Wave LogHistWave
	WaveStats/Q LogHistWave
	Variable oneG0bin = LogHistWave[x2pnt(LogHistWave, 0)]
	fprintf refnum, "INFO log histogram: max %g counts/trace at log10(G) = %g; the 1 G0 bin holds %g counts/trace\r", V_max, V_maxloc, oneG0bin
	Rep(refnum, oneG0bin > 3, "log histogram shows the simulated 1 G0 plateau (bin at log10(1) = " + num2str(oneG0bin) + " counts/trace)")
	GetFileFolderInfo/Q/Z/P=Data "PullOutConductanceBlock_1.ibw"
	Rep(refnum, V_flag == 0, "PullOutConductanceBlock_1.ibw written to the Data path")
	GetFileFolderInfo/Q/Z/P=Data "PullOutConductanceBlockHist_1.ibw"
	Rep(refnum, V_flag == 0, "PullOutConductanceBlockHist_1.ibw written to the Data path")

	// ---- 5. stop, and the simulator's own bookkeeping ----------------------------
	StopWritingTasks("")
	Rep(refnum, StringMatch(status, "OFF"), "writing task OFF after Kill Tasks")
	SVAR simErr = sim_Errors
	Rep(refnum, strlen(simErr) == 0, "simulator saw no channel-count or task errors [" + simErr + "]")
	NVAR lowAsked = sim_PiezoMinAsked
	NVAR highAsked = sim_PiezoMaxAsked
	NVAR numRefused = sim_NumRefusedWrites
	Rep(refnum, lowAsked >= K_PiezoMinVolt && highAsked <= K_PiezoMaxVolt && numRefused == 0, "piezo output stayed inside 0 to 10 V for the whole run (lowest " + num2str(lowAsked) + " V, highest " + num2str(highAsked) + " V)")
	Wave/T chans = sim_TaskChans
	Wave isAO = sim_TaskIsAO
	Variable i, aoOK = 1, aiOK = 1, nAO = 0, nAI = 0
	for (i = 0; i < numpnts(chans); i += 1)
		if (strlen(chans[i]) == 0)
			continue
		endif
		if (isAO[i])
			nAO += 1
			if (!StringMatch(chans[i], "Dev1/ao2;Dev1/ao1;") && !StringMatch(chans[i], "Dev1/ao3;"))
				aoOK = 0
			endif
		else
			nAI += 1
			if (!StringMatch(chans[i], "Dev1/ai9;Dev1/ai10;Dev1/ai11;"))
				aiOK = 0
			endif
		endif
	endfor
	Rep(refnum, aiOK && nAI > 0, "every AI task was Dev1/ai9;Dev1/ai10;Dev1/ai11, the RSE-default inputs (" + num2str(nAI) + " tasks)")
	Rep(refnum, aoOK && nAO > 0, "every AO task was Dev1/ao2;Dev1/ao1 or Dev1/ao3 (" + num2str(nAO) + " tasks)")
	SVAR simLog = sim_Log
	Rep(refnum, strsearch(simLog, "ev2", 0) < 0, "no second card named in any task")

	fprintf refnum, "END\r"
	Close refnum
	return 0
End

// ---------------------------------------------------------------------------
// Second pass: the paths the first run does not touch. Run AFTER ClaudeSmokeRun
// in the same Igor session (it relies on the globals and panels being there).
//     ClaudeSmokeRun2("Macintosh HD:path:to:result2.txt")
// Covers: panel tab procs, Gain control, tip bias / piezo step / slider procs,
// Background Sampling checkbox, Find Offset (Vzero), the four ramp modes with one
// attempt each, EChem gate on/set, the CV guard with the writing task ON, both CVs
// with the writing task OFF, Reset DAQ Devices.
// ---------------------------------------------------------------------------
Function ClaudeSmokeRun2(resultPath)
	String resultPath

	Variable refnum
	Open refnum as resultPath
	fprintf refnum, "SMOKE RUN 2 %s\r", date() + " " + time()

	// ---- panel procs that only shuffle controls -----------------------------------
	MainWindowTabProc("", 1)
	MainWindowTabProc("", 2)
	SubWindowTabProc("", 1)
	SubWindowTabProc("", 3)
	MainWindowTabProc("", 0)
	Rep(refnum, 1, "tab procedures ran")

	SetGain("", 6, "", "")
	NVAR Gain = G_CurrentVoltGain
	NVAR Conv = G_CurrentVoltConversion
	Rep(refnum, Gain == 6 && Conv == 1, "Gain control sets gain 6 -> conversion 1 uA/V")
	SetGain("", 5, "", "")
	NVAR simGain = sim_GainExp
	simGain = 5
	Rep(refnum, Conv == 10, "Gain control sets gain 5 -> conversion 10 uA/V")

	// ---- writing task on, piezo and bias procs ----------------------------------------
	StartHighResWritingTask("")
	NVAR Offset_nm = G_PiezoOffset_nm
	NVAR TipBias = G_TipBias
	NVAR hb = sim_HoldBiasV
	NVAR hp = sim_HoldPiezoV
	Variable z0 = Offset_nm
	PiezoStepCloser("")
	NVAR dz = G_PiezoDeltaZ_nm
	Rep(refnum, abs(Offset_nm - (z0 + dz)) < 1e-9 && abs(hp*K_ZPiezoScale - Offset_nm) < 1e-6, "Step closer moved the piezo by Z (nm) and the card saw it")
	PiezoStepApart("")
	Rep(refnum, abs(Offset_nm - z0) < 1e-9, "Step apart moved it back")
	SetPiezoBiasFromSlider("", 4.0, 0)
	Rep(refnum, abs(Offset_nm - 4.0*K_ZPiezoScale) < 1e-6, "slider set the piezo to 4 V (" + num2str(Offset_nm) + " nm)")
	SetTipBiasVoltage("", 0, "", "")
	Rep(refnum, abs(hb + TipBias/1000) < 1e-9, "tip bias control wrote -(TipBias/1000) = " + num2str(hb) + " V to the bias output")

	// ---- background sampling checkbox -----------------------------------------------
	BkgdSamplingCheckProc("", 1)
	STRUCT WMBackgroundStruct s
	BackgroundRead(s)
	BkgdSamplingCheckProc("", 0)
	Rep(refnum, 1, "Background Sampling on, one read, off")

	// ---- Vzero offset measurement -----------------------------------------------------
	// approach with no reachable surface: must stop at the piezo limit and come back to where it started
	NVAR ContactZ = sim_ContactZ_nm
	Variable savedContact = ContactZ
	ContactZ = 5000
	WriteToHighRes(0 - Offset_nm, TipBias)		// park at 0 V
	RunStep(refnum, "HighResCardApproach()")
	Rep(refnum, abs(Offset_nm) < 1e-6, "approach with no reachable surface stopped at the piezo limit and retracted to its start (z = " + num2str(Offset_nm) + " nm)")
	ContactZ = savedContact

	// park near the surface so HighResContact finds contact quickly
	WriteToHighRes((ContactZ - 2) - Offset_nm, TipBias)
	NVAR NumPts = G_NumPoints
	NumPts = 3
	RunStep(refnum, "FindOffset(\"\")")
	NVAR Vzero = G_Vzero
	NVAR Izero = G_Izero
	Wave CurrentWave, TipBiasRamp
	Rep(refnum, numpnts(CurrentWave) == 2*NumPts && numpnts(TipBiasRamp) == 2*NumPts, "Find Offset measured " + num2str(2*NumPts) + " bias points")
	Rep(refnum, numtype(Vzero) == 0 && numtype(Izero) == 0, "Find Offset produced finite Vzero = " + num2str(Vzero) + " mV, Izero = " + num2str(Izero))
	Rep(refnum, WinType("Izero") == 1, "Izero graph built")
	Rep(refnum, abs(hb + TipBias/1000) < 1e-9, "tip bias restored after Find Offset")

	// ---- the four ramp modes, one attempt each ---------------------------------------
	NVAR PushPullCheck = G_PushPullCheck
	NVAR IVCheck = G_IVCheck
	NVAR ACHoldCheck = G_ACHoldCheck
	NVAR HBHoldCheck = G_HBHoldCheck
	NVAR InitialPullLength = G_InitialPullLength
	NVAR FinalPullLength = G_FinalPullLength
	NVAR PushPullLength = G_PushPullLength
	NVAR HoldLength = G_HoldLength
	NVAR NumPushPullCycles = G_NumPushPullCycles
	NVAR PullOutNumber = G_PullOutNumber
	NVAR StopNumber = G_StopNumber
	NVAR Size = G_PseudoTotalLength_nm
	StopNumber = PullOutNumber + 1000
	InitialPullLength = 1; FinalPullLength = 4; PushPullLength = 1.5; HoldLength = 1; NumPushPullCycles = 2
	Wave PiezoBiasWave, JunctionBiasWave
	NVAR NumPtsInAppliedWaves = G_NumPtsInAppliedWaves

	// Each mode starts at a block boundary (PullOutNumber = 1 mod 100). The IV, AC and
	// high-bias modes switch "Save Bias" on inside CreateInputs, and SavePullOut only
	// creates the VoltageBlock/CurrentBlock waves at the first trace of a block; turning
	// a mode on in the middle of a block therefore fails with "null (missing) wave" --
	// in the original code as well. Pre-existing; documented in README.md.
	PullOutNumber = 201
	RampOptionsCheckProc("PushPullCheck_PushPullRamps", 1)
	RunStep(refnum, "MakeAttempt(\"\")")
	Rep(refnum, PushPullCheck == 1 && numpnts(PiezoBiasWave) == NumPtsInAppliedWaves && numpnts(JunctionBiasWave) == NumPtsInAppliedWaves && NumPtsInAppliedWaves > 0, "push-pull mode: one attempt ran, waves built (" + num2str(NumPtsInAppliedWaves) + " points, Size " + num2str(Size) + " nm)")
	PullOutNumber = 301
	RampOptionsCheckProc("IVCheck_IVRamps", 1)
	RunStep(refnum, "MakeAttempt(\"\")")
	WaveStats/Q JunctionBiasWave
	Rep(refnum, IVCheck == 1 && PushPullCheck == 0 && V_max > 0.5 && V_min < -0.5, "IV mode: one attempt ran, bias ramp spans +/-" + num2str(V_max) + " V")
	PullOutNumber = 401
	RampOptionsCheckProc("ACHoldCheck_ACHoldRamps", 1)
	RunStep(refnum, "MakeAttempt(\"\")")
	Rep(refnum, ACHoldCheck == 1 && IVCheck == 0 && numpnts(JunctionBiasWave) == NumPtsInAppliedWaves, "AC-hold mode: one attempt ran")
	PullOutNumber = 501
	RampOptionsCheckProc("HBHoldCheck_HBHoldRamps", 1)
	RunStep(refnum, "MakeAttempt(\"\")")
	Rep(refnum, HBHoldCheck == 1 && ACHoldCheck == 0 && numpnts(JunctionBiasWave) == NumPtsInAppliedWaves, "high-bias-hold mode: one attempt ran")
	RampOptionsCheckProc("HBHoldCheck_HBHoldRamps", 0)
	Rep(refnum, PushPullCheck + IVCheck + ACHoldCheck + HBHoldCheck == 0, "all ramp modes off again")
	SmashFun()
	Rep(refnum, 1, "SmashFun ran")

	// ---- EChem gate while the writing task is ON --------------------------------------
	NVAR ce = sim_CEVolts
	CounterElectrodeOn("")
	CounterElectrodeSetVar("", 500, "", "")
	Rep(refnum, abs(ce - 0.5) < 1e-9, "counter electrode set to 500 mV reached the card (" + num2str(ce) + " V)")
	// CV guard: must refuse while the writing task is ON, and leave the writing task alone
	SVAR status = G_HighResOutputTaskStatus
	Variable cvHigh = CVcurveHighRes()
	Variable cvLow = CVcurveLowRes()
	Rep(refnum, cvHigh == -1 && cvLow == -1 && StringMatch(status, "ON"), "both CVs refused while the writing task is ON")

	// ---- Kill Tasks, then the two CVs with the writing task OFF ----------------------
	StopWritingTasks("")
	Rep(refnum, StringMatch(status, "OFF") && abs(ce) < 1e-9, "Kill Tasks: writing OFF and the device reset put the counter electrode at 0 V")
	NVAR CVRate = G_CVAcquisitionRate
	NVAR ScanRate = G_ScanRate
	CVRate = 1000
	ScanRate = 1000		// 1 V/s: short ramps for the test
	RunStep(refnum, "StartCVHighResButton(\"\")")
	Rep(refnum, WinType("CyclicVoltammogram") == 1 && WaveExists($"Tip_Current_1"), "CV (bias out) ran one cycle and saved Tip_Current_1")
	RunStep(refnum, "StartCVLowResButton(\"\")")
	Rep(refnum, WaveExists($"FullTip_Current_1"), "CV (CE out) ran one cycle and saved FullTip_Current_1")
	RunStep(refnum, "EChemResetDAQDevices(\"\")")
	Rep(refnum, 1, "Reset DAQ Devices ran")

	SVAR simErr = sim_Errors
	Rep(refnum, strlen(simErr) == 0, "simulator saw no channel-count or task errors [" + simErr + "]")
	NVAR lowAsked = sim_PiezoMinAsked
	NVAR highAsked = sim_PiezoMaxAsked
	NVAR numRefused = sim_NumRefusedWrites
	Rep(refnum, lowAsked >= K_PiezoMinVolt && highAsked <= K_PiezoMaxVolt && numRefused == 0, "piezo output stayed inside 0 to 10 V for both runs (lowest " + num2str(lowAsked) + " V, highest " + num2str(highAsked) + " V)")
	SVAR simLog = sim_Log
	Rep(refnum, strsearch(simLog, "ev2", 0) < 0, "no second card named in any task")
	Rep(refnum, strsearch(simLog, "Dev1/ao3", 0) >= 0, "the counter-electrode task used Dev1/ao3")

	fprintf refnum, "END\r"
	Close refnum
	return 0
End

// ---------------------------------------------------------------------------
// Third pass: PIEZO SAFETY. The piezo must never get a negative voltage and never more
// than 10 V (K_PiezoMinVolt / K_PiezoMaxVolt in Functions_STMBJ.ipf). Run AFTER
// ClaudeSmokeRun in the same Igor session (it needs the globals, the panels and the Data path):
//     ClaudePiezoSafetyRun("Macintosh HD:path:to:result3.txt")
// Every way the code can move the piezo is asked for a voltage outside the range. The simulated
// card remembers the lowest and highest piezo voltage any write asked for and refuses a write
// outside the channel range, so "the card never saw it" is checked, not assumed.
// ---------------------------------------------------------------------------
Function ClaudePiezoSafetyRun(resultPath)
	String resultPath

	Variable refnum
	Open refnum as resultPath
	fprintf refnum, "PIEZO SAFETY RUN %s\r", date() + " " + time()

	NVAR Offset_nm = G_PiezoOffset_nm
	NVAR TipBias = G_TipBias
	NVAR ChanLow = G_PiezoChanLow
	NVAR ChanHigh = G_PiezoChanHigh
	SVAR status = G_HighResOutputTaskStatus
	NVAR Gain = G_CurrentVoltGain
	NVAR Conv = G_CurrentVoltConversion
	NVAR Thresh = G_ConductanceThreshold
	NVAR PullOutNumber = G_PullOutNumber
	NVAR StopNumber = G_StopNumber
	NVAR Attempt = G_PullOutAttempt
	NVAR SingleFlag = G_SingleAttemptFlag
	NVAR dz = G_PiezoDeltaZ_nm

	// nothing running, then a fresh simulator so that its lowest/highest start clean
	if (StringMatch(status, "ON"))
		StopWritingTasks("")
	endif
	Sim_Init()
	NVAR ContactZ = sim_ContactZ_nm
	NVAR simGain = sim_GainExp
	NVAR simZ = sim_ZScale
	NVAR simS = sim_SenseScale
	NVAR hp = sim_HoldPiezoV
	NVAR lowAsked = sim_PiezoMinAsked
	NVAR highAsked = sim_PiezoMaxAsked
	NVAR numRefused = sim_NumRefusedWrites
	NVAR chanLo = sim_PiezoChanLo
	NVAR chanHi = sim_PiezoChanHi
	SVAR simErr = sim_Errors
	simZ = K_ZPiezoScale
	simS = K_SenseScale
	Gain = 5
	Conv = 10^(6-Gain)
	simGain = Gain
	Thresh = 1.5
	ContactZ = 300
	SingleFlag = 0
	Rep(refnum, K_PiezoMinVolt == 0 && K_PiezoMaxVolt == 10, "the limits in the code are " + num2str(K_PiezoMinVolt) + " V and " + num2str(K_PiezoMaxVolt) + " V")

	// ---- A. an experiment file saved with the older code: -10 V limit, negative stored position, -10..10 slider
	ChanLow = -10
	ChanHigh = 10
	Offset_nm = -300		// -4.84 V
	Slider SliderPos_Z win=BreakJunctionMeasurement, limits={-10,10,0.01}
	StartHighResWritingTask("")
	Rep(refnum, StringMatch(status, "ON"), "A: Start Writing: writing task ON")
	Rep(refnum, chanLo == 0 && chanHi == 10, "A: the piezo channel was created with the range " + num2str(chanLo) + " to " + num2str(chanHi) + " V")
	Rep(refnum, ChanLow == 0 && ChanHigh == 10, "A: the old limits -10/+10 left in the experiment were put back to 0/10")
	Rep(refnum, Offset_nm == 0 && hp == 0, "A: a stored position of -4.84 V started at " + num2str(hp) + " V")
	ControlInfo/W=BreakJunctionMeasurement SliderPos_Z
	Rep(refnum, strsearch(S_recreation, "limits={0,10,0.01}", 0) >= 0, "A: the slider on the panel runs 0 to 10 V")

	// ---- B. the slider
	SetPiezoBiasFromSlider("", -5, 0)
	Rep(refnum, Offset_nm == 0 && hp == 0, "B: slider asked for -5 V -> piezo held at " + num2str(hp) + " V")
	SetPiezoBiasFromSlider("", 12, 0)
	Rep(refnum, abs(Offset_nm - 10*K_ZPiezoScale) < 1e-9 && hp == 10, "B: slider asked for +12 V -> piezo held at " + num2str(hp) + " V")
	SetPiezoBiasFromSlider("", 0.02, 0)
	Rep(refnum, abs(hp - 0.02) < 1e-12, "B: slider to 0.02 V -> " + num2str(hp) + " V (normal moves still work)")

	// ---- C. the step buttons next to 0 V
	dz = 5
	PiezoStepApart("")		// 0.02 V minus 5 nm would be -0.06 V
	Rep(refnum, Offset_nm == 0 && hp == 0, "C: Step apart (5 nm) from 0.02 V -> held at " + num2str(hp) + " V, not -0.06 V")
	PiezoStepApart("")
	Rep(refnum, Offset_nm == 0 && hp == 0, "C: Step apart again at 0 V -> still " + num2str(hp) + " V")
	PiezoStepCloser("")
	Rep(refnum, abs(Offset_nm - 5) < 1e-9 && abs(hp - 5/K_ZPiezoScale) < 1e-12, "C: Step closer from 0 V still works (" + num2str(Offset_nm) + " nm)")

	// ---- D. the write function itself, with nonsense
	WriteToHighRes(-1e6, TipBias)
	Rep(refnum, Offset_nm == 0 && hp == 0, "D: WriteToHighRes(-1e6 nm) -> " + num2str(hp) + " V")
	WriteToHighRes(1e6, TipBias)
	Rep(refnum, hp == 10, "D: WriteToHighRes(+1e6 nm) -> " + num2str(hp) + " V")
	WriteToHighRes(NaN, TipBias)
	Rep(refnum, hp == 0 && numtype(Offset_nm) == 0, "D: WriteToHighRes(NaN) -> " + num2str(hp) + " V, and the stored position is a number again (" + num2str(Offset_nm) + " nm)")
	Offset_nm = -124		// a negative position typed into the global by hand (-2 V)
	SetTipBiasVoltage("", 0, "", "")		// the tip-bias box rewrites both outputs
	Rep(refnum, Offset_nm == 0 && hp == 0, "D: a negative G_PiezoOffset_nm typed by hand is not sent out (" + num2str(hp) + " V)")

	// ---- E. Kill Tasks, then Start Writing with a stored position above the range
	StopWritingTasks("")
	Offset_nm = 2000		// +32 V
	StartHighResWritingTask("")
	Rep(refnum, hp == 10, "E: a stored position of +32 V started at " + num2str(hp) + " V")
	WriteToHighRes(0 - Offset_nm, TipBias)

	// ---- F. the surface sits 2 nm above full retraction: contact is found at about 2.5 nm (0.04 V),
	//         and the 5 nm pull from there would need -0.04 V. It must be refused, once, cleanly.
	ContactZ = 2
	PullOutNumber = 601
	StopNumber = 611
	Variable n0 = PullOutNumber
	Variable att0 = Attempt
	RunStep(refnum, "MeasureBreakJunctions()")
	Rep(refnum, PullOutNumber == n0, "F: surface 2 nm above full retraction: no trace taken, because the pull would need a negative voltage")
	Rep(refnum, Attempt - att0 == 1, "F: the experiment stopped after that one attempt (attempts: " + num2str(Attempt - att0) + ")")
	Rep(refnum, Offset_nm >= 0 && hp >= 0, "F: piezo left at " + num2str(hp) + " V")

	// ---- G. the tip touches even at 0 V: moving out must stop at 0 V and end the experiment
	ContactZ = -50
	WriteToHighRes(30 - Offset_nm, TipBias)		// 30 nm = 0.48 V
	att0 = Attempt
	RunStep(refnum, "MeasureBreakJunctions()")
	Rep(refnum, PullOutNumber == n0 && Attempt - att0 == 1, "G: tip touching even at 0 V: the experiment stopped, no trace taken")
	Rep(refnum, Offset_nm >= 0 && Offset_nm < 5 && hp >= 0, "G: moving out stopped at " + num2str(hp) + " V (" + num2str(Offset_nm) + " nm)")

	// ---- H. Find Offset with no surface anywhere: must stop at 10 V, go back, and not loop for ever
	ContactZ = 5000
	WriteToHighRes(100 - Offset_nm, TipBias)
	NVAR Vzero = G_Vzero
	Variable vz0 = Vzero
	DoWindow/K Izero		// as if Find Offset had never worked in this experiment:
	KillWaves/Z fit_CurrentWave	// no Izero graph yet and no fit wave for it
	RunStep(refnum, "FindOffset(\"\")")
	Rep(refnum, abs(Offset_nm - 100) < 1e-6, "H: Find Offset with no surface gave up at the top of the range and went back to where it started (" + num2str(Offset_nm) + " nm)")
	Rep(refnum, Vzero == vz0 || (numtype(Vzero) == 2 && numtype(vz0) == 2), "H: Vzero was left as it was")
	Rep(refnum, WinType("Izero") == 0, "H: no Izero graph was drawn for a measurement that gave up")
	CtrlNamedBackground BkgdRead, status
	Rep(refnum, NumberByKey("RUN", S_info) == 1, "H: Background Sampling was switched back on afterwards")
	StopBkgdSampling()

	// ---- I. normal use still works: start at exactly 0 V, surface at 40 nm, three traces
	ContactZ = 40
	WriteToHighRes(0 - Offset_nm, TipBias)
	PullOutNumber = 601
	StopNumber = 604
	RunStep(refnum, "MeasureBreakJunctions()")
	Rep(refnum, PullOutNumber == 604, "I: starting from 0 V with the surface at 40 nm, three traces were taken (PullOutNumber = " + num2str(PullOutNumber) + ")")
	Wave PullOutConductance
	WaveStats/Q/R=[0, 50] PullOutConductance
	Rep(refnum, V_avg > 0.8 && V_avg < 5, "I: the last trace starts in contact (" + num2str(V_avg) + " G0)")

	// ---- L. no surface anywhere and the piezo near the top: making contact must stop at 10 V and end the experiment
	ContactZ = 5000
	WriteToHighRes(600 - Offset_nm, TipBias)		// 9.68 V
	StopNumber = PullOutNumber + 5
	n0 = PullOutNumber
	att0 = Attempt
	RunStep(refnum, "MeasureBreakJunctions()")
	Rep(refnum, PullOutNumber == n0 && Attempt - att0 == 1, "L: no surface up to 10 V: the experiment stopped, no trace taken")
	Rep(refnum, hp <= 10 && Offset_nm <= 10*K_ZPiezoScale + 1e-9, "L: stepping in stopped at " + num2str(hp) + " V (" + num2str(Offset_nm) + " nm)")

	// ---- M. the smash (in 30 nm, then out 40 nm) next to both ends of the range
	NVAR SmashNum = G_SmashFrequency
	WriteToHighRes(610 - Offset_nm, TipBias)		// 9.84 V; 30 nm more would be 10.32 V
	Attempt = SmashNum		// SmashFun smashes when the attempt number is a multiple of this
	SmashFun()
	Rep(refnum, highAsked <= 10 && abs(Offset_nm - 580) < 1e-6, "M: smash at 9.84 V: the way in was held at 10 V, then out 40 nm (now " + num2str(Offset_nm) + " nm)")
	WriteToHighRes(5 - Offset_nm, TipBias)		// 0.08 V; 5 + 30 - 40 would be -5 nm
	SmashFun()
	Rep(refnum, lowAsked >= 0 && Offset_nm == 0 && hp == 0, "M: smash at 0.08 V: the way out was held at " + num2str(hp) + " V")

	// ---- N. a pull whose ramp would go ABOVE 10 V is refused too (a made-up ramp that rises by 0.01 V)
	Wave PiezoBiasWave
	NVAR numWrites = sim_NumWrites
	Duplicate/O PiezoBiasWave, sim_SavedRamp
	WriteToHighRes(10*K_ZPiezoScale - Offset_nm, TipBias)		// 10 V
	PiezoBiasWave = 0.01*p/numpnts(PiezoBiasWave)
	Variable writesBefore = numWrites
	Variable gt = GenerateTrace()
	Rep(refnum, gt == -2 && numWrites == writesBefore && hp == 10, "N: a ramp that would rise to 10.01 V was refused before anything was written (GenerateTrace returned " + num2str(gt) + ")")
	Duplicate/O sim_SavedRamp, PiezoBiasWave
	KillWaves/Z sim_SavedRamp

	// ---- J. the whole run, as the card saw it
	Rep(refnum, lowAsked >= 0 && highAsked <= 10, "J: over this whole run the card was never asked for a piezo voltage outside 0 to 10 V (lowest " + num2str(lowAsked) + " V, highest " + num2str(highAsked) + " V)")
	Rep(refnum, numRefused == 0 && strlen(simErr) == 0, "J: the card refused no write and saw no error [" + simErr + "]")

	// ---- K. can these checks fail at all? Hand the simulated card a -1 V write directly, past the Igor code.
	NVAR G_OD1 = G_OD1
	NVAR WriteBufferSize = G_WriteBufferSize
	Make/O/D/N=(2*WriteBufferSize) sim_BadWrite = 0
	sim_BadWrite[0, WriteBufferSize-1] = -1
	Variable hpBefore = hp
	MXWriteAnalogF64(G_OD1, 10, 2, sim_BadWrite)
	Rep(refnum, numRefused == 1 && hp == hpBefore && lowAsked == -1, "K: a -1 V write handed straight to the simulated card is refused and counted (so J can fail)")
	KillWaves/Z sim_BadWrite
	simErr = ""

	StopWritingTasks("")
	Rep(refnum, StringMatch(status, "OFF") && hp == 0, "Kill Tasks: writing OFF, piezo output at " + num2str(hp) + " V")

	fprintf refnum, "END\r"
	Close refnum
	return 0
End
