#pragma TextEncoding = "UTF-8"		// [NEWDAQ] first line of every file (Igor 7+)
// Setup_NewDAQ_STMBJ.ipf  (was Setup1_STMBJ.ipf)
// Includes files for STM-based Break Junction measurement and defines constants
// for the ONE-card rig: NI USB-6453 as Dev1, current amplifier set by hand (no Keithley GPIB),
// coarse stage moved by hand (no NanoPZ actuator, no X piezo).
// ---------------------------------------------------------------------------
// [NEWDAQ] Ported 2026-10-22 for ONE NI USB-6453 (Dev1), no Keithley GPIB control,
// no coarse actuator. See PORTING_SPEC.md and README.md in this folder.
// ---------------------------------------------------------------------------

#pragma rtGlobals=3	// Use modern global access method and strict wave access.

Strconstant Setup= "Setup 1 (USB-6453)"	// [NEWDAQ] was "Setup 1"

// For EChem measurement, uncomment following lines and associated
// declaration function in the InitializeExperiment() function below
#include ":EChem_Module"
//[NEWDAQ-REMOVED: LowRes] Strconstant LowResCounterElectrodeOut= "dev2/ao1"
// [NEWDAQ] the counter-electrode output is now CounterElectrodeOut (Dev1/ao3), see the channel map below

// These files are specific to the STMBJ technique
#include ":Functions_STMBJ"
#include ":Controls_STMBJ"
#include ":Windows_STMBJ"

// [NEWDAQ] Offline analysis and plotting of saved PullOut blocks (histograms, 2D histograms, fits). No hardware,
// [NEWDAQ] no extension needed. Copied unchanged from MKLab_STMBJ - Copy; menu "PullOut", macro PullOutAnalysis().
// [NEWDAQ] Its data paths (C:Data, C:DataAnalysis:SavedHist) are set when PullOutAnalysis() runs, not here.
#include ":STMBJ_HistogramAnalysis"	// [NEWDAQ] added at the user's request

// For Keithley Current-to-Voltage amplifier
//[NEWDAQ-REMOVED: Keithley] #include ":SetUpGPIB_Keithley"
// [NEWDAQ] The amplifier (gain, filter, zero check, suppress, bias) is set BY HAND on its front panel.
// [NEWDAQ] Igor keeps only the gain numbers G_CurrentVoltGain / G_CurrentVoltConversion for the V->A conversion.
// [NEWDAQ] SetUpGPIB_Keithley.ipf stays in this folder, fully commented out, with restore instructions in its header.

// Setup-specific: points to the actuator used on Setup 2
//[NEWDAQ-REMOVED: Actuator] #include ":NanoPZ_Actuator_Functions_STM"
// [NEWDAQ] The coarse approach is done BY HAND. NanoPZ_Actuator_Functions_STM.ipf is not in this folder.

// Declare Constants
Constant K_NumAIChans = 3	// [NEWDAQ] channels in the main AI task G_ID1: voltage, current, piezo sense (in this order)
Constant K_G0= 77.480917346e-6	// Quantum conductance in micro S, from Wikipedia
Constant K_ZPiezoScale = 62
Constant K_XPiezoScale = 522	// [NEWDAQ] kept for reference; the X piezo is not driven in this version
Constant K_SenseScale = 314

// [NEWDAQ] Channel map for the ONE card, NI USB-6453 (32 AI / 4 AO), from the Python config
// [NEWDAQ] STM_Git/python_code_entire_igor_w_GUI/configs/newpc_rig.json.
// [NEWDAQ] HighRes/LowRes are historical names, there is one card now.
// [NEWDAQ]
// [NEWDAQ] ALL INPUTS ARE RSE (single-ended, referenced to AI GND). The DAQ extension cannot choose the terminal mode, so the
// [NEWDAQ] card's default applies: on the USB-6453 AI 0-7 and AI 16-23 default to DIFFERENTIAL, while AI 8-15 and AI 24-31 are
// [NEWDAQ] single-ended only and default to RSE. That is why the three inputs sit on AI 9, AI 10, AI 11 (not AI 1-3 as in the
// [NEWDAQ] Python config): wire BNC centre to the AI pin and shield to AI GND, and use the same three channels in Python.
// [NEWDAQ]
// [NEWDAQ]  constant              value      was                                   signal
// [NEWDAQ]  DAQDevice             Dev1       "Dev1" / "Dev2" literals              the one card; use it in every MXResetDevice(...)
// [NEWDAQ]  HighResPiezoOut       Dev1/ao2   dev1/ao0                              Z-piezo command (through the piezo driver box)
// [NEWDAQ]  HighResBiasOut        Dev1/ao1   dev1/ao1                              junction bias
// [NEWDAQ]  HighResVoltageIn      Dev1/ai9   dev1/ai0                              junction voltage monitor (RSE: BNC centre to AI 9, shield to AI GND)
// [NEWDAQ]  HighResCurrentIn      Dev1/ai10  dev1/ai1                              current preamp output (RSE: BNC centre to AI 10, shield to AI GND)
// [NEWDAQ]  PiezoSenseIn          Dev1/ai11  LowResPiezoIn = dev2/ai0              piezo driver box sense (readback), 3rd channel of the main AI task G_ID1 (RSE: centre to AI 11, shield to AI GND)
// [NEWDAQ]  CounterElectrodeOut   Dev1/ao3   LowResCounterElectrodeOut = dev2/ao1  EChem counter electrode. SPARE CHANNEL CHOSEN BY US, NOT YET WIRED (see README.md)
// [NEWDAQ]
// [NEWDAQ] Removed, no replacement: LowResPiezoIn, LowResCurrentIn, LowResVoltageIn, LowResXPiezoOut,
// [NEWDAQ] LowResCounterElectrodeOut, TCchan4, TCchan5.
Strconstant DAQDevice= "Dev1"	// [NEWDAQ] the one card; use it in every MXResetDevice(...)

// dev1 is the high res card
// [NEWDAQ] (historical comment above; every channel is on Dev1 now)
Strconstant HighResPiezoOut= "Dev1/ao2"	// [NEWDAQ] was dev1/ao0; Z-piezo command
Strconstant HighResBiasOut= "Dev1/ao1"	// [NEWDAQ] was dev1/ao1 (same number, new card); junction bias
Strconstant HighResVoltageIn= "Dev1/ai9"	// [NEWDAQ] was dev1/ai0; junction voltage monitor. AI 9: single-ended-only input, RSE by default
Strconstant HighResCurrentIn= "Dev1/ai10"	// [NEWDAQ] was dev1/ai1; current preamp output. AI 10: single-ended-only input, RSE by default
Strconstant PiezoSenseIn= "Dev1/ai11"	// [NEWDAQ] was LowResPiezoIn dev2/ai0; piezo sense readback, 3rd channel of G_ID1. AI 11: single-ended-only input, RSE by default
Strconstant CounterElectrodeOut= "Dev1/ao3"	// [NEWDAQ] was LowResCounterElectrodeOut dev2/ao1; spare AO chosen by us, NOT YET WIRED

// dev2 is the low res card
// [NEWDAQ] (historical comment above; the second card is gone, its channel constants are disabled)
//[NEWDAQ-REMOVED: LowRes] Strconstant LowResPiezoIn= "dev2/ai0"
//[NEWDAQ-REMOVED: LowRes] Strconstant LowResCurrentIn= "dev2/ai1"
//[NEWDAQ-REMOVED: LowRes] Strconstant LowResVoltageIn= "dev2/ai3"
//[NEWDAQ-REMOVED: LowRes] Strconstant LowResXPiezoOut= "dev2/ao0"
//Strconstant LowResXPiezoIn= "dev2/ai4"

// Needed for creating path ("Data") and creating folders
// that are named in the group convention for identifying
// the date and setup used for experiments
Strconstant SetupID= "_"
Strconstant DataDir= "D:Experiments:"

// create item in 'Macros' menu
Menu "Macros"
	"STM Break Junction Measurement", InitializeExperiment()
End

// Initializes variables and path and calls main window macro if needed
Function InitializeExperiment()
	SetDataFolder root:
	if (exists("G_PathDate")==0)
		Declare_STMBJ_Variables()
		MakePath()
	endif
	
	DoWindow/F BreakJunctionMeasurement
	if (V_FLag==0)
		Execute "BreakJunctionMeasurement()"
	endif
	
//[NEWDAQ-REMOVED: Keithley] 	SetUpGPIB_Keithley() // for Keithley
	// [NEWDAQ] no GPIB: the current amplifier is set by hand on its front panel
	
	InitializeEChem()
	
	DoWindow/F Voltage_Offset
	if (V_FLag==0)
		Execute "Voltage_Offset()"
	endif
End

// Function to add a delay
Function Delay(ms)
	Variable ms
	Variable delay = ms*1000
	Variable start = StopMSTimer(-2)
		do
	while(StopMSTimer(-2) - start < delay)
End

// [NEWDAQ] stray top-level X-piezo calls; the X piezo was on the second card and is not driven any more
//[NEWDAQ-REMOVED: Actuator] SetupXPiezo()
//[NEWDAQ-REMOVED: Actuator] StopXPiezo()
//[NEWDAQ-REMOVED: Actuator] MoveXPiezoToZero()

// [NEWDAQ] LateralEXPT() needs the NanoPZ actuator and the X piezo on the second card; both are gone in this version
//[NEWDAQ-REMOVED: Actuator] // Function for monolayer measurement (lateral movement)
//[NEWDAQ-REMOVED: Actuator] Function LateralEXPT(ZDistance,XDistance, XFreq)  // e.g. LateralEXPT(10,200,250)
	
//[NEWDAQ-REMOVED: Actuator] 	Variable ZDistance
//[NEWDAQ-REMOVED: Actuator] 	Variable XDistance
//[NEWDAQ-REMOVED: Actuator] 	Variable XFreq
//[NEWDAQ-REMOVED: Actuator] 	Variable/G G_ActuatorStepSize=ZDistance
//[NEWDAQ-REMOVED: Actuator] 	Variable/G G_StopNumber
//[NEWDAQ-REMOVED: Actuator] 	Variable FinalStopNumber = 12201
//[NEWDAQ-REMOVED: Actuator] 	Variable keys
//[NEWDAQ-REMOVED: Actuator] 	NVAR G_XPiezoVoltage
	
//[NEWDAQ-REMOVED: Actuator] 	do
//[NEWDAQ-REMOVED: Actuator] 		// Gives user ability to abort loop by pushing 'Alt' button
//[NEWDAQ-REMOVED: Actuator] 		keys= GetKeyState(0)
//[NEWDAQ-REMOVED: Actuator] 		if(keys==2)
//[NEWDAQ-REMOVED: Actuator] 			break
//[NEWDAQ-REMOVED: Actuator] 		endif
			
//[NEWDAQ-REMOVED: Actuator] 		G_StopNumber = G_StopNumber+XFreq
		
//[NEWDAQ-REMOVED: Actuator] 		print G_XPiezoVoltage
//[NEWDAQ-REMOVED: Actuator] 		Delay(500)
		
//[NEWDAQ-REMOVED: Actuator] 		StartMeasurement("")

//[NEWDAQ-REMOVED: Actuator] 		// Withdraw tip in Z direction
//[NEWDAQ-REMOVED: Actuator] 		StepActuatorApart("")
//[NEWDAQ-REMOVED: Actuator] 		Delay(100)
//[NEWDAQ-REMOVED: Actuator] 		StepActuatorApart("")
//[NEWDAQ-REMOVED: Actuator] 		Delay(100)
//[NEWDAQ-REMOVED: Actuator] 		StepActuatorApart("")
//[NEWDAQ-REMOVED: Actuator] 		Delay(100)

//[NEWDAQ-REMOVED: Actuator] 		// Move tip in X direction
//[NEWDAQ-REMOVED: Actuator] 		MoveXPiezo(XDistance)	
//[NEWDAQ-REMOVED: Actuator] 		Delay(100)	

//[NEWDAQ-REMOVED: Actuator] 		// Approach tip into contact
//[NEWDAQ-REMOVED: Actuator] 		Variable/G G_ActuatorStepSize=5
//[NEWDAQ-REMOVED: Actuator] 		SetPiezoBiasFromSlider("", 0, 0)
//[NEWDAQ-REMOVED: Actuator] 		ApproachButton("")
//[NEWDAQ-REMOVED: Actuator] 		Delay(100)

//[NEWDAQ-REMOVED: Actuator] 	while (G_StopNumber<FinalStopNumber)
	
//[NEWDAQ-REMOVED: Actuator] End

Function rungo()
	NVAR TipBias = G_TipBias
	NVAR StopNumber = G_StopNumber
	NVAR SavedNumber = G_PullOutNumber
	
	Variable Num, counts_EachBias, StartNum
	Num = 14
	StartNum = 1
	counts_EachBias = 1000
	
	make/O/N=(Num) bias, StopNumWave,StartNumWave
	
	bias=(p+1)*(-100)
//	bias[14]=100
	bias[9]=-100	
	bias[10]=-900
	bias[11]=-1000
	bias[12]=-1100
	bias[13]=-100
	StopNumWave=(p+1)*counts_EachBias+StartNum
	StartNumWave=StopNumWave-counts_EachBias
	
	Variable i,starti
	Variable keys
	FindLevel/EDGE=1 /P StartNumWave, SavedNumber
	starti=floor(V_levelx)
	for ( i = starti; i < Num; i += 1 )
		TipBias = bias[i]
		StopNumber =StopNumWave[i]
		print i, tipbias, stopnumber
//		PiezoStepApart(" ")
//		PiezoStepApart(" ")
//		FindSuppress(" ")
		StartMeasurement(" ")
		keys= GetKeyState(0)
		if(keys==2)
			return 0
		endif
	endfor
SaveExperiment	
StopWritingTasks(" ")
End
