#pragma TextEncoding = "UTF-8"
////////////////////////////////////////////////////////////////////////////////

// ALL    EChem_Module Functions

////////////////////////////////////////////////////////////////////////////////
// ---------------------------------------------------------------------------
// [NEWDAQ] Ported 2026-10-22 for ONE NI USB-6453 (Dev1), no Keithley GPIB control,
// no coarse actuator. See PORTING_SPEC.md and README.md in this folder.
// ---------------------------------------------------------------------------

#pragma rtGlobals=3		// Use modern global access method and strict wave access.

Function InitializeEChem()
	if (exists("G_CounterElectrodeBias")==0)
		Declare_EChem_Variables()
	endif
	DoWindow/F EChem
	if (V_Flag==0)
		Execute "EChem()"
	endif
	SetVariable CounterElectrodeSetVar win=EChem, disable=2
End

Function Declare_EChem_Variables()
	// Counter-electrode write task (EChem measurements)	// [NEWDAQ] was the LR card; now an on-demand AO task on CounterElectrodeOut (Dev1)
	Variable/G G_OD2
	////////////////////////////////////////////////////////////////
	
	Variable/G G_CounterElectrodeBias= 0
	Variable/G G_LowResWriteBufferSize= 1	// [NEWDAQ] one sample: software-timed output
		
	Variable/G G_CVAcquisitionRate= 1000
	Variable/G G_NumCVCycles= 1
	Variable/G G_CVCycle 
	Variable/G G_ScanRate= 100
	Variable/G G_VoltagePeakOne= -1
	Variable/G G_VoltagePeakTwo= 1
	
	Make/D/O/N=0 LowResWriteWave
	Make/D/O/N=0 AppliedVoltageRamp, CVAppliedRamp                
	Make/D/O/N=0 CVCurveIn                                 
	Make/D/O/N=0 TipCurrent, WorkingElectrodeVoltage
End

Function CounterElectrodeOn(ctrlName) : ButtonControl
	String ctrlName
	
	StartEChemWriting()
	
	Button StartEChemWriteButton win=EChem, disable=2
	SetVariable CounterElectrodeSetVar win=EChem, disable=0
End

Function CounterElectrodeSetVar(ctrlName,varNum,varStr,varName) : SetVariableControl
	String ctrlName
	Variable varNum
	String varStr
	String varName
	
	NVAR CounterElectrodeBias= G_CounterElectrodeBias
	
	CounterElectrodeBias= varnum
	WriteToCounterElectrode(CounterElectrodeBias)

End

// [NEWDAQ] was: hardware-timed finite task on dev2/ao1 (MXCfgSampClkTiming sampleMode 0, the
// write buffer of G_LowResWriteBufferSize = 20 samples was clocked out at G_AcquisitionRate, and every
// voltage change needed MXStopTask / MXWriteAnalogF64 / MXStartTask). On ONE card a second
// hardware-timed AO task would compete with the piezo/bias task G_OD1 for the AO sample clock, so the
// counter electrode is now a software-timed (on-demand) single-sample output on CounterElectrodeOut.
Function StartEChemWriting()
	
	NVAR G_OD2= G_OD2
	NVAR CardTimeout= G_CardTimeout
	NVAR CounterElectrodeBias= G_CounterElectrodeBias
	
	Wave LowResWriteWave
	NVAR LowResWriteBufferSize= G_LowResWriteBufferSize
	
	LowResWriteBufferSize= 1	// [NEWDAQ] force one sample even in an experiment saved with the old value (20)
	Redimension/D/N=(LowResWriteBufferSize) LowResWriteWave
	LowResWriteWave= 0
	
	MXCreateTask("G_OD2")
	MXCreateAOVoltageChan(G_OD2, CounterElectrodeOut, -5, 5)
	// no MXCfgSampClkTiming: on-demand output, one sample per write
	MXStartTask(G_OD2)
	MXWriteAnalogF64(G_OD2, CardTimeout, 1, LowResWriteWave)	// 1-point wave = 0 V
	
End

Function WriteToCounterElectrode(Voltage)

	Variable Voltage
	
	NVAR G_OD2= G_OD2
	NVAR CardTimeout= G_CardTimeout
	NVAR LowResWriteBufferSize= G_LowResWriteBufferSize
	Wave LowResWriteWave
		
	Redimension/D/N=(LowResWriteBufferSize) LowResWriteWave
	LowResWriteWave= Voltage/1000
	
//[NEWDAQ-REMOVED: LowRes] 	MXStopTask(G_OD2)
	MXWriteAnalogF64(G_OD2,CardTimeout,1,LowResWriteWave)	// [NEWDAQ] on-demand task: the new value goes out immediately, no stop/start
//[NEWDAQ-REMOVED: LowRes] 	MXStartTask(G_OD2)
End

// New CV function: record CV with HighRes card. 
Function CVcurveHighRes()
	NVAR G_ID1= G_ID1		// input task: current through Au tip and voltage on working electrode 
	NVAR G_OD1= G_OD1	// output task: voltage to working electrode. 
	NVAR CurrentVoltConversion = G_CurrentVoltConversion
	NVAR VoltagePeakOne= G_VoltagePeakOne	// Peak voltages
	NVAR VoltagePeakTwo= G_VoltagePeakTwo
	NVAR ScanRate= G_ScanRate	// G_ScanRate is mV/s 
	NVAR CVAcquisitionRate= G_CVAcquisitionRate
	NVAR NumCVCycles= G_NumCVCycles
	NVAR CVCycle= G_CVCycle 

	NVAR HighResOutputRange= G_HighResOutputRange

	Variable HighResOutputRange_1 = HighResOutputRange
	Variable HighResOutputRange_2 = -HighResOutputRange
	
	Wave AppliedVoltageRamp, CVAppliedRamp
	Wave CVCurveIn
	Wave TipCurrent
	Wave WorkingElectrodeVoltage
	
	// [NEWDAQ] one card: this CV builds its own AO task, which cannot coexist with the piezo/bias task G_OD1.
	SVAR HighResOutputTaskStatus= G_HighResOutputTaskStatus	// [NEWDAQ]
	if (StringMatch(HighResOutputTaskStatus,"ON"))   // [NEWDAQ] one card: the CV needs the AO; stop the writing task first
		Print "CV: press Kill Tasks (stop the DAQ writing task) first, then start the CV."
		return -1
	endif
	
	Variable SweepRate= ScanRate/1000	// set the scan rate in V/s 
	
	Variable RampOne= round((2*abs(VoltagePeakOne) / SweepRate) *CVAcquisitionRate)		// number of points for the first voltage ramp to peak one, at fixed sweep rate. 
	Variable RampTwo= round((2*abs(VoltagePeakTwo) / SweepRate) *CVAcquisitionRate)		// number of points for the second voltage ramp to peak two, at fixed sweep rate. 

	Variable SlopeOne= VoltagePeakOne / (RampOne/2) 			// slope for incremental steps in voltage ramp wave to peak one. 
	Variable SlopeTwo= VoltagePeakTwo / (RampTwo/2) 			// slope for incremental steps in voltage ramp wave to peak two.  

	Variable FirstQuarter= RampOne/2
	Variable SecondQuarter= RampOne
	Variable ThirdQuarter= RampOne + RampTwo/2
	Variable FourthQuarter= RampOne + RampTwo
	
	// Variable NumPtsVoltageRamp = 2 * (RampOne + RampTwo)     // Number of points for voltage ramp wave.
	Variable NumPtsVoltageRamp = 2*RampOne + RampTwo
	Variable NumPtsCVCurve = NumPtsVoltageRamp * 2		     	// [NEWDAQ] now only the per-channel clock buffer (2x headroom, unchanged); CVCurveIn is sized separately below
	
	Variable CardTimeout= ceil(NumPtsVoltageRamp / CVAcquisitionRate) + 5	// in seconds. 	// [NEWDAQ] +5 s slack: the read is issued right after the start and the data takes exactly the ramp time to arrive
	
	Redimension/D/N=(NumPtsVoltageRamp) AppliedVoltageRamp, CVAppliedRamp
	Redimension/D/N=(NumPtsVoltageRamp*K_NumAIChans) CVCurveIn	// [NEWDAQ] K_NumAIChans blocks of NumPtsVoltageRamp: voltage, current, piezo sense

	// Linear voltage sweep divided into 4 intervals: from 0 to V1, back to 0, and from 0 to V2, back to 0. 
	// FIRST voltage sweep
	AppliedVoltageRamp[0 , FirstQuarter - 1] = SlopeOne* p												// From 0 to first voltage peak. 
	AppliedVoltageRamp[FirstQuarter, SecondQuarter - 1] = VoltagePeakOne - SlopeOne* (p - FirstQuarter)	// From first peak back to 0. 
	AppliedVoltageRamp[SecondQuarter, ThirdQuarter - 1] = SlopeTwo* (p - SecondQuarter)					// From 0 to second voltage peak. 
	AppliedVoltageRamp[ThirdQuarter, FourthQuarter - 1] = VoltagePeakTwo - SlopeTwo* (p - ThirdQuarter)	// From second peak back to 0. 
	
	// SECOND voltage sweep: needed to avoid "discontinuity" at 0. 
	AppliedVoltageRamp[FourthQuarter, FourthQuarter + (FirstQuarter - 1)] = SlopeOne* (p - FourthQuarter)
	AppliedVoltageRamp[FourthQuarter + FirstQuarter, FourthQuarter + (SecondQuarter - 1)] = VoltagePeakOne - SlopeOne* (p - (FourthQuarter + FirstQuarter))

	// Set up the input task: measure current through Au tip and applied voltage on working electrode (plus the piezo sense channel, which is read but not used here). 	// [NEWDAQ]
	SetUpHRTaskID1()
    	MXCfgSampClkTiming(G_ID1, CVAcquisitionRate, 1, NumPtsCVCurve)
    	
	// Set up the output task: voltage ramp to working electrode on output channel ao1. 
	MXCreateTask("G_OD1")
	MXCreateAOVoltageChan(G_OD1,HighResBiasOut, HighResOutputRange_2,HighResOutputRange_1)
    	MXCfgSampClkTiming(G_OD1, CVAcquisitionRate, 1, NumPtsVoltageRamp)
    	MXWriteAnalogF64(G_OD1, CardTimeout, 1, AppliedVoltageRamp)
	
	CVAppliedRamp= AppliedVoltageRamp
	
	// initialize CV cycle counter to 0. 
	CVCycle= 0
    
// CV cycle. 
//+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
	Variable i, keys
    	for(i= 0; i < NumCVCycles; i+=1)
    	
    		Redimension/D/N=(NumPtsVoltageRamp) TipCurrent
		Redimension/D/N=(NumPtsVoltageRamp) WorkingElectrodeVoltage
    	
		// counter for CV cycle. 
		CVCycle+= 1
		
		MXStartTask(G_OD1)
		MXStartTask(G_ID1)
		MXReadAnalogF64(G_ID1, CardTimeout, K_NumAIChans, CVCurveIn)	// [NEWDAQ] 3-channel read; block 2 (piezo sense) is ignored
		MXStopTask(G_ID1)
		MXStopTask(G_OD1)
		
		WorkingElectrodeVoltage = CVCurveIn[p]		
		WorkingElectrodeVoltage*=1000	// convert to mV!
		
		TipCurrent = CVCurveIn[NumPtsVoltageRamp + p]
		
		TipCurrent[0 , FirstQuarter - 1] = NaN
   		TipCurrent[FourthQuarter + FirstQuarter, FourthQuarter + (SecondQuarter - 1)] = NaN
   		WorkingElectrodeVoltage[0 , FirstQuarter - 1] = NaN
   		WorkingElectrodeVoltage[FourthQuarter + FirstQuarter, FourthQuarter + (SecondQuarter - 1)] = NaN
   		CVAppliedRamp[0 , FirstQuarter - 1] = NaN
   		CVAppliedRamp[FourthQuarter + FirstQuarter, FourthQuarter + (SecondQuarter - 1)] = NaN
		
		// Save current and voltage into two new waves labeled with the loop index. 
    		String TipCurrentName= "Tip_Current_" + Num2Str(CVCycle)
    		String WorkingElectrodeVoltageName= "WE_Voltage_" + Num2Str(CVCycle)
    		String AppliedRampName= "AppliedRamp_" + Num2Str(CVCycle)
    		String CVAppliedRampName= "CVAppliedRamp_" + Num2Str(CVCycle)
    		Duplicate/O TipCurrent $TipCurrentName
   		Duplicate/O WorkingElectrodeVoltage $WorkingElectrodeVoltageName
   		Duplicate/O AppliedVoltageRamp $AppliedRampName
   		Duplicate/O CVAppliedRamp $CVAppliedRampName

		DoWindow/F CyclicVoltammogram
		if(V_Flag==0)	// if there is no such window, create it. 
			Execute "CyclicVoltammogram()"
		endif
		TextBox/W=CyclicVoltammogram/C/N=CVnumber/F=0/Z=1/A=MC/X=5.40/Y=44.30 "\\Z12CV cycle \f01" + Num2Str(CVCycle)
		DoUpdate

	endfor
//+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
	
	// clearing the tasks...
	MXClearTask(G_OD1)
	MXClearTask(G_ID1)

	// Reset the DAQ card. 	// [NEWDAQ]
	MXResetDevice(DAQDevice)	// [NEWDAQ]
	CounterElectrodeGateOff()	// [NEWDAQ] one card: the reset also ended the counter-electrode gate task; show the gate as OFF

End

// [NEWDAQ] After a device reset the on-demand counter-electrode task (G_OD2) is gone and its output is at 0 V:
// [NEWDAQ] put the EChem panel and the gate variable back to "gate off" (the same lines Kill Tasks and Reset DAQ Device use).
Function CounterElectrodeGateOff()
	NVAR CounterElectrodeBias= G_CounterElectrodeBias

	CounterElectrodeBias= 0
	Button StartEChemWriteButton win=EChem, disable=0
	SetVariable CounterElectrodeSetVar win=EChem, disable=2
End

// New CV function: potential is applied to Pt electrode via the counter-electrode output. 	// [NEWDAQ] was: "via LowRes card"; the name CVcurveLowRes is kept because the panel button refers to it
Function CVcurveLowRes()
	NVAR G_ID1= G_ID1		// input task: current through Au tip and voltage on working electrode 
	NVAR G_OD2= G_OD2	// output task: voltage ramp to the counter electrode (CounterElectrodeOut). 	// [NEWDAQ]
	NVAR CurrentVoltConversion = G_CurrentVoltConversion
	NVAR VoltagePeakOne= G_VoltagePeakOne	// Peak voltages
	NVAR VoltagePeakTwo= G_VoltagePeakTwo
	NVAR ScanRate= G_ScanRate	// G_ScanRate is mV/s 
	NVAR CVAcquisitionRate= G_CVAcquisitionRate
	NVAR NumCVCycles= G_NumCVCycles
	NVAR CVCycle= G_CVCycle 
	
	Wave AppliedVoltageRamp, CVAppliedRamp
	Wave CVCurveIn
	Wave TipCurrent
	Wave FullTipCurrent
	Wave WorkingElectrodeVoltage
	
	// [NEWDAQ] one card: this CV builds its own AO task, which cannot coexist with the piezo/bias task G_OD1.
	SVAR HighResOutputTaskStatus= G_HighResOutputTaskStatus	// [NEWDAQ]
	if (StringMatch(HighResOutputTaskStatus,"ON"))   // [NEWDAQ] one card: the CV needs the AO; stop the writing task first
		Print "CV: press Kill Tasks (stop the DAQ writing task) first, then start the CV."
		return -1
	endif

	// [NEWDAQ] the gate task (on-demand, G_OD2) and this CV ramp use the same output CounterElectrodeOut: if the gate is
	// [NEWDAQ] ON, end it first, or DAQmx refuses the ramp task ("resource reserved") and the gate's handle would be lost
	ControlInfo/W=EChem StartEChemWriteButton
	if (V_flag != 0 && V_disable == 2)	// the Counter Electrode ON button is disabled while the gate is on
		Print "CV (CE out): switching the counter-electrode gate off first (its output carries the CV ramp)."
		MXStopTask(G_OD2)
		MXClearTask(G_OD2)
		CounterElectrodeGateOff()
	endif

	Variable SweepRate= ScanRate/1000	// set the scan rate in V/s

	Variable RampOne= round((2*abs(VoltagePeakOne) / SweepRate) *CVAcquisitionRate)		// number of points for the first voltage ramp to peak one, at fixed sweep rate.
	Variable RampTwo= round((2*abs(VoltagePeakTwo) / SweepRate) *CVAcquisitionRate)		// number of points for the second voltage ramp to peak two, at fixed sweep rate.

	Variable SlopeOne= VoltagePeakOne / (RampOne/2) 			// slope for incremental steps in voltage ramp wave to peak one.
	Variable SlopeTwo= VoltagePeakTwo / (RampTwo/2) 			// slope for incremental steps in voltage ramp wave to peak two.

	Variable SetZero= 5000		// sets the counter-electrode output to zero for initial 5000 points	// [NEWDAQ] comment only
	Variable FirstQuarter= RampOne/2 + SetZero
	Variable SecondQuarter= RampOne + SetZero
	Variable ThirdQuarter= RampOne + RampTwo/2 + SetZero
	Variable FourthQuarter= RampOne + RampTwo + SetZero
	Variable FifthQuarter= 2*RampOne + 3*RampTwo/2 + SetZero
	
	// Variable NumPtsVoltageRamp = 2 * (RampOne + RampTwo)     // Number of points for voltage ramp wave.
	Variable NumPtsVoltageRamp = 2*RampOne + 3*RampTwo/2 + SetZero
	Variable NumPtsCVCurve = NumPtsVoltageRamp * 2		     	// [NEWDAQ] now only the per-channel clock buffer (2x headroom, unchanged); CVCurveIn is sized separately below
	
	Variable CardTimeout= ceil(NumPtsVoltageRamp / CVAcquisitionRate) + 5	// in seconds. 	// [NEWDAQ] +5 s slack: the read is issued right after the start and the data takes exactly the ramp time to arrive
	
	Redimension/D/N=(NumPtsVoltageRamp) AppliedVoltageRamp, CVAppliedRamp
	Redimension/D/N=(NumPtsVoltageRamp*K_NumAIChans) CVCurveIn	// [NEWDAQ] K_NumAIChans blocks of NumPtsVoltageRamp: voltage, current, piezo sense

	// Linear voltage sweep divided into 4 intervals: from 0 to V1, back to 0, and from 0 to V2, back to 0. 
	// FIRST voltage sweep
	AppliedVoltageRamp[0 , SetZero - 1] = 0											// first 5000 points are zero. 
	AppliedVoltageRamp[SetZero, FirstQuarter - 1] = SlopeOne* (p-SetZero)											// From 0 to first voltage peak. 
	AppliedVoltageRamp[FirstQuarter, SecondQuarter - 1] = VoltagePeakOne - SlopeOne* (p - FirstQuarter)	       // From first peak back to 0. 
	AppliedVoltageRamp[SecondQuarter, ThirdQuarter - 1] = SlopeTwo* (p - SecondQuarter)					// From 0 to second voltage peak. 
	AppliedVoltageRamp[ThirdQuarter, FourthQuarter - 1] = VoltagePeakTwo - SlopeTwo* (p - ThirdQuarter)	       // From second peak back to 0. 
	
	// SECOND voltage sweep: needed to avoid "discontinuity" at 0. 
	AppliedVoltageRamp[FourthQuarter, FourthQuarter + (FirstQuarter - 1) - SetZero] = SlopeOne* (p - FourthQuarter)
	AppliedVoltageRamp[FourthQuarter + FirstQuarter - SetZero, FourthQuarter + (SecondQuarter - 1) - SetZero] = VoltagePeakOne - SlopeOne* (p - (FourthQuarter + FirstQuarter - SetZero))
	AppliedVoltageRamp[FourthQuarter + SecondQuarter - SetZero, FifthQuarter - 1] = SlopeTwo* (p - (FourthQuarter + SecondQuarter - SetZero))

	// Set up the input tasks: measure current through Au tip. 
	SetUpHRTaskID1()
    	MXCfgSampClkTiming(G_ID1, CVAcquisitionRate, 1, NumPtsCVCurve)
    	
	// Set up the output task: voltage ramp on the counter-electrode output (CounterElectrodeOut, Dev1).	// [NEWDAQ] was: "on output channel ao1" of the LowRes card
	// [NEWDAQ] This CV puts the ramp on the counter-electrode output while the piezo/bias task G_OD1 is OFF
	// (guard above); it is a hardware-timed finite ramp on the one card, so it must not run beside G_OD1.
	MXCreateTask("G_OD2")
	MXCreateAOVoltageChan(G_OD2,CounterElectrodeOut, -10,10)	// [NEWDAQ] was LowResCounterElectrodeOut (dev2/ao1); same -10..10 range
    	MXCfgSampClkTiming(G_OD2, CVAcquisitionRate, 1, NumPtsVoltageRamp)
    	MXWriteAnalogF64(G_OD2, CardTimeout, 1, AppliedVoltageRamp)
	
	CVAppliedRamp= AppliedVoltageRamp
	
	// initialize CV cycle counter to 0. 
	CVCycle= 0

// CV cycle. 
//+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
	Variable i, keys
    	for(i= 0; i < NumCVCycles; i+=1)
    	
    		Redimension/D/N=(NumPtsVoltageRamp) TipCurrent
		Redimension/D/N=(NumPtsVoltageRamp) WorkingElectrodeVoltage
    	
		// counter for CV cycle. 
		CVCycle+= 1
		
		MXStartTask(G_OD2)
		
		MXStartTask(G_ID1)
		MXReadAnalogF64(G_ID1, CardTimeout, K_NumAIChans, CVCurveIn)	// [NEWDAQ] 3-channel read; block 2 (piezo sense) is ignored
		MXStopTask(G_ID1)
		
		MXStopTask(G_OD2)
		
		TipCurrent = CVCurveIn[NumPtsVoltageRamp + p]
		
		String FullTipCurrentName= "FullTip_Current_" + Num2Str(CVCycle)
		Duplicate/O TipCurrent $FullTipCurrentName
		
		TipCurrent[0 , FirstQuarter - 1] = NaN
   		TipCurrent[FourthQuarter + FirstQuarter - SetZero, FifthQuarter - 1] = NaN
//   		WorkingElectrodeVoltage[0 , FirstQuarter - 1] = NaN
//   		WorkingElectrodeVoltage[FourthQuarter + FirstQuarter - SetZero, FourthQuarter + (SecondQuarter - 1) - SetZero] = NaN
   		CVAppliedRamp[0 , FirstQuarter - 1] = NaN
   		CVAppliedRamp[FourthQuarter + FirstQuarter - SetZero, FifthQuarter - 1] = NaN
		
		// Save current and voltage into two new waves labeled with the loop index. 
    		String TipCurrentName= "Tip_Current_" + Num2Str(CVCycle)
    		String WorkingElectrodeVoltageName= "WE_Voltage_" + Num2Str(CVCycle)
    		String AppliedRampName= "AppliedRamp_" + Num2Str(CVCycle)
    		String CVAppliedRampName= "CVAppliedRamp_" + Num2Str(CVCycle)
    		Duplicate/O TipCurrent $TipCurrentName
    		Duplicate/O WorkingElectrodeVoltage $WorkingElectrodeVoltageName
   		Duplicate/O AppliedVoltageRamp $AppliedRampName
   		Duplicate/O CVAppliedRamp $CVAppliedRampName

		DoWindow/F CyclicVoltammogram
		if(V_Flag==0)	// if there is no such window, create it. 
			Execute "CyclicVoltammogram()"
		endif
		TextBox/W=CyclicVoltammogram/C/N=CVnumber/F=0/Z=1/A=MC/X=5.40/Y=44.30 "\\Z12CV cycle \f01" + Num2Str(CVCycle)
		DoUpdate

	endfor
//+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
	
	// clearing the tasks... 
	MXClearTask(G_OD2)
	MXClearTask(G_ID1)

	// Reset the DAQ card. 	// [NEWDAQ]
	MXResetDevice(DAQDevice)	// [NEWDAQ] one card
	CounterElectrodeGateOff()	// [NEWDAQ] the gate task shared this output and is gone after the reset; show the gate as OFF

End

// New button: record CV with HighRes card. 
Function StartCVHighResButton(ctrlName) : ButtonControl
	String ctrlName
	
//[NEWDAQ-REMOVED: Keithley] 	NVAR BoardUD= G_BoardUD
//[NEWDAQ-REMOVED: Keithley] 	NVAR DeviceUD= G_DeviceUD
	
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 board=BoardUD
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 device=DeviceUD
	
//[NEWDAQ-REMOVED: Keithley] 	// Deselect Zero Check box before starting CV.
//[NEWDAQ-REMOVED: Keithley] 	ControlInfo/W=BreakJunctionMeasurement ZeroCheckBox
//[NEWDAQ-REMOVED: Keithley] 	if(V_value == 1)	// V_value=1 if checkbox is selected, 0 otherwise. 
//[NEWDAQ-REMOVED: Keithley] 		GPIBWrite2 "C0X"	// "C0X" deselects checkbox.
//[NEWDAQ-REMOVED: Keithley] 							// "C1X" selects checkbox.
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] 		CVcurveHighRes()	// start CV measurement
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] 		GPIBWrite2 "C1X"  // revert Zero Check to its original status. 
//[NEWDAQ-REMOVED: Keithley] 	else 
//[NEWDAQ-REMOVED: Keithley] 		CVcurveHighRes()
//[NEWDAQ-REMOVED: Keithley] 	endif 
	StopBkgdSampling()	// [NEWDAQ] the CV rebuilds and clears G_ID1, so the background sampler must not be using it (as FindOffset does)
	CVcurveHighRes()	// [NEWDAQ] start CV measurement; no Keithley zero check to toggle (amplifier is set by hand)
	StartBkgdSampling()	// [NEWDAQ]
	
	Button StartCVHighResButton win=EChem, disable=0	
End

Function StartCVLowResButton(ctrlName) : ButtonControl
	String ctrlName
	
//[NEWDAQ-REMOVED: Keithley] 	NVAR BoardUD= G_BoardUD
//[NEWDAQ-REMOVED: Keithley] 	NVAR DeviceUD= G_DeviceUD
	
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 board=BoardUD
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 device=DeviceUD
	
//[NEWDAQ-REMOVED: Keithley] 	// Deselect Zero Check box before starting CV.
//[NEWDAQ-REMOVED: Keithley] 	ControlInfo/W=BreakJunctionMeasurement ZeroCheckBox
//[NEWDAQ-REMOVED: Keithley] 	if(V_value == 1)	// V_value=1 if checkbox is selected, 0 otherwise. 
//[NEWDAQ-REMOVED: Keithley] 		GPIBWrite2 "C0X"	// "C0X" deselects checkbox.
//[NEWDAQ-REMOVED: Keithley] 							// "C1X" selects checkbox.
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] 		CVcurveLowRes()	// start CV measurement
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] 		GPIBWrite2 "C1X"  // revert Zero Check to its original status. 
//[NEWDAQ-REMOVED: Keithley] 	else 
//[NEWDAQ-REMOVED: Keithley] 		CVcurveLowRes()
//[NEWDAQ-REMOVED: Keithley] 	endif 
	StopBkgdSampling()	// [NEWDAQ] the CV rebuilds and clears G_ID1, so the background sampler must not be using it (as FindOffset does)
	CVcurveLowRes()	// [NEWDAQ] start CV measurement; no Keithley zero check to toggle (amplifier is set by hand)
	StartBkgdSampling()	// [NEWDAQ]
	
	Button StartCVLowResButton win=EChem, disable=0	
End

Function VoltagePeakOneSetVar(ctrlName,varNum,varStr,varName) : SetVariableControl
	String ctrlName
	Variable varNum
	String varStr
	String varName
	
	NVAR VoltagePeakOne= G_VoltagePeakOne  // in Volts 
	
	VoltagePeakOne= varnum
End

Function VoltagePeakTwoSetVar(ctrlName,varNum,varStr,varName) : SetVariableControl
	String ctrlName
	Variable varNum
	String varStr
	String varName
	
	NVAR VoltagePeakTwo= G_VoltagePeakTwo   // in Volts 
	
	VoltagePeakTwo= varnum
End

Function ScanRateSetVar(ctrlName,varNum,varStr,varName) : SetVariableControl
	String ctrlName
	Variable varNum
	String varStr
	String varName
	
	NVAR ScanRate= G_ScanRate
	
	ScanRate= varnum		// varnum in mV/s
End
	
Function CVAcquisitionRateSetVar(ctrlName,varNum,varStr,varName) : SetVariableControl
	String ctrlName
	Variable varNum
	String varStr
	String varName
	
	NVAR CVAcquisitionRate= G_CVAcquisitionRate
	
	CVAcquisitionRate= varnum 
End 

Function NumCVCyclesSetVar(ctrlName,varNum,varStr,varName) : SetVariableControl
	String ctrlName
	Variable varNum
	String varStr
	String varName
	
	NVAR NumCVCycles= G_NumCVCycles
	
	NumCVCycles= varnum 
End 