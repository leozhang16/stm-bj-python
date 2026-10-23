#pragma TextEncoding = "UTF-8"
////////////////////////////////////////////////////////////////////////////////
// ALL STM Functions for STM-BJ measurements
////////////////////////////////////////////////////////////////////////////////
// ---------------------------------------------------------------------------
// [NEWDAQ] Ported 2026-10-22 for ONE NI USB-6453 (Dev1), no Keithley GPIB control,
// no coarse actuator. See PORTING_SPEC.md and README.md in this folder.
// ---------------------------------------------------------------------------

Function Declare_STMBJ_Variables()
	// PXI Variables
	Variable/G G_AcquisitionRate= 40000
	Variable/G G_CardTimeout= 10
	Variable/G G_WriteBufferSize= 1000
	Variable/G G_FastReadWaveSize= 200
	
	// HR card Write Voltage
	Variable/G G_OD1
	///////////////////////////////////
	// HR card read piezo and voltage 
	// FOR BOTH MAKE CONTACT, GENERATE TRACE 
	// AND VOLTAGE OFFSET ESTIMATE. 
	Variable/G G_ID1
	/////////////////////////////////////////////////
	// LowRes background sampling
	//[NEWDAQ-REMOVED: LowRes] Variable/G G_ID2
	////////////////////////////////////////////////
	// LowRes read piezo, thermocouples
	//[NEWDAQ-REMOVED: LowRes] Variable/G G_ID3
	/////////////////////////////////////////
	// LR card read thermocouples background
	//[NEWDAQ-REMOVED: LowRes] Variable/G G_ID6
	////////////////////////////////////////////////////////////////
	
	String/G G_HighResOutputTaskStatus= "OFF"

	// Saving flags
	Variable/G G_BiasSaveCheck=0
	Variable/G G_HistSaveCheck=1
	Variable/G G_CurrentSaveCheck=0
	Variable/G G_SenseSaveCheck=0
	Variable/G G_PiezoWaveSaveCheck=0	
      	
      	Variable/G G_PiezoChanHigh=10
      	Variable/G G_PiezoChanLow=-10
      	
	// General Variables
	String/G G_PathDate	// encodes date and setup ID into path and folder where data is saved
	Variable/G G_PiezoOffset_nm=0	// in nm and MUST BE LARGER THAN EXCURSION SIZE when used with unipolar piezos, zero with bipolar piezo!!!!
	Variable/G G_PiezoDeltaZ_nm=5	//nm
	Variable/G G_CurrentSamplingReadoutVal = 0
	Variable/G G_PiezoBiasSamplingReadoutVal = 0
	Variable/	G G_JunctionVoltage= 0
	Variable/G G_NumPtsInAppliedWaves	// Number of points in both PiezoBiasWave and JunctionBiasWave
	Variable/G G_HighResOutputRange= 2.5
	//[NEWDAQ-REMOVED: Actuator] Variable/G G_XPiezoPosition = 0
	//[NEWDAQ-REMOVED: Actuator] Variable/G G_XPiezoVoltage = 0
	
	// PullOut Variables
	Variable/G G_PseudoTotalLength_nm = 5	// nm
	Variable/G G_ConductanceThreshold = 5 // microS 
	Variable/G G_MakeContactApproachStepSize = .5 //nm
	Variable/G G_PullOutAttempt=0
	Variable/G G_SingleAttemptFlag=0
	Variable/G G_PullOutRate=20 // nm/s
	Variable/G G_PullOutNumber=1
	Variable/G G_StopNumber=1001
	Variable/G G_EndOfTraceNoiseThreshold=0.0005
	Variable/G G_SeriesResistance=106130
	Variable/G G_SmashFrequency=50
	Variable/G G_SmashInSteps=30
	Variable/G G_SmashOutSteps=-40
	Variable/G G_PullOutDatetime	// Igor DateTime of moment before fundamental MX data generation tasks are called in GenerateTrace
	
	// Keithley Current-to-Voltage Converter Variables
	Variable/G G_CurrentVoltGain = 6
	Variable/G G_CurrentVoltConversion=1		// microAmps per Volt
	Variable/G G_TipBias=100 // Bias in mV
	//[NEWDAQ-REMOVED: Keithley] Variable/G G_DeviceUD = 0 // Device ID for IV converter
	//[NEWDAQ-REMOVED: Keithley] Variable/G G_BoardUD = 0 // Board ID for GPIB IV converter
	Variable/G G_CurrentSuppress = -0.0004 // search for 17.15 (3 times) and replace with new number if changing
	Variable/G G_CurrentSuppressConst = 0
	//[NEWDAQ-REMOVED: Keithley] Variable/G G_KeithleyBiasEnabled = 0
	// Actuator Variables
	//[NEWDAQ-REMOVED: Actuator] Variable/G G_ActuatorStepSize=5
	//[NEWDAQ-REMOVED: Actuator] Variable/G G_ActuatorCounter=0

	// Keeps track of last tab seen in sub tab
	Variable/G G_SubTabNum=0

       //Make the option of reading voltage through lowres card (now through ai3)
       Variable/G G_VoltageRead=0
       Variable/G G_ReadChan
       
	// PushPull experiment variables
	Variable/G G_InitialPullLength
	Variable/G G_FinalPullLength
	Variable/G G_PushPullLength
	Variable/G G_HoldLength
	Variable/G G_PushPullCheck=0
	Variable/G G_NumPushPullCycles

	// IV experiment variables
	Variable/G G_IVCheck=0
	Variable/G G_IVMaxBias=1
	Variable/G G_IVInitPull=3
	Variable/G G_IVFinPull=4
	Variable/G G_IVCapLength=0.5
	Variable/G G_IVRampLength=2
	Variable/G G_IVSignFlag=0

	// AC Hold variables
	Variable/G G_ACHoldCheck=0
	Variable/G G_ACInitPullLength=3
	Variable/G G_ACFinPullLength=4
	Variable/G G_ACHoldLength=3
	Variable/G G_ACAmp=0.8
	Variable/G G_ACFreq=10		// kHz
	Variable/G G_ACCapLength=0.5
	
	// HB Hold variables
	Variable/G G_HBHoldCheck=0
	Variable/G G_HBInitPullLength=3
	Variable/G G_HBFinPullLength=4
	Variable/G G_HBHoldLength=3
	Variable/G G_HBBias=0.8
	Variable/G G_HBCapLengthIN=0.1
	Variable/G G_HBCapLengthFIN=0.1

	// Alignment pulse variables
	Variable/G G_startLevel			// voltage of spike
	Variable/G G_endLevel			// voltage before and after spike
	Variable/G G_PulseFrontEdgePt	// point at endLevel volts just before spike
	Variable/G G_PulseBackEdgePt	// point at startLevel volts just after spike
	Variable/G G_DelayOffset
	
	// Input waves for writing to High Res in main experiment loop
	Make/N=0/D/O PiezoBiasWave, JunctionBiasWave // defined in CreateInputs

	// Wave used for reading current in MakeContact		
	Make/N=0/O/D ContactCheckWave

	// Wave used for writing to high res
	Make/N=0/O/D HighResWriteWave

	// Wave used for reading from high res
	Make/N=0/O/D HighResReadWave
	Make/N=0/O/D HighResReadWaveBkgd
	
	// Waves used for partitioning raw data from high res
	Make/N=0/O/D CurrentIn, VoltageIn
	
	Make/N=0/O/D CurHighResIn
	Make/N=0/O/D VolHighResIn

	// Waves used for storing trace data
	Make/N=0/O/D PullOutVoltage, PullOutCurrent, PullOutConductance, POExtension

	// Histogram used for testing low-integer G region of traces
	Make/O/N=5 HistLowG

	// Wave used for testing whether trace drops to noise threshold at end
	Make/O/N=(0.01*G_AcquisitionRate) EndConductance

	// Wave used for storing Parameters in SavePullOut
	Make/O/N=20 ParameterWave

	// Wave used for saving conductance with parameters
	Make/O/N=0 PullOutConductanceSave

	// Wave for reading from low res in background task
	//[NEWDAQ-REMOVED: LowRes] Make/N=0/O/D LowResReadWave, LowResReadWaveBkgd

	// Waves for partitioning raw data from low res
	//[NEWDAQ-REMOVED: LowRes] Make/N=0/O/D SenseIn, CurrentInLowRes, SenseInBkgd
	//[NEWDAQ-REMOVED: LowRes] Make/N=0/O/D VoltageInLowRes
	Make/N=0/O/D SenseIn, SenseInBkgd	// [NEWDAQ] piezo sense is now the 3rd channel of G_ID1 on the one card (nm in GenerateTrace, V in BackgroundRead)

	// Histogram used for identifying peak of current in TestVirtualGround
	Make/N=100/O CurrentIn_Hist=0	

	// Waves used in finding suppress value
	Make/O/N=21 CurSup, CurOffset

	// Wave for histogram of last Conductance block written
	Make/O/N=0 LogHistWave

//	To estimate the Voltage Offset at zero bias
	Variable/G G_VoltageInterval= 5
	Variable/G G_NumPoints= 5
	Variable/G G_Vzero= 0
	Variable/G G_Izero= 0
	Variable/G G_Cur, G_Vol, G_Cond
	Variable/G G_VzeroFrequency= 50
	Variable/G G_J= 0
	Variable/G G_OldPullOutNumber= 0
	
	Make/O/N=0 CurrentWave, VoltageWave, ConductanceWave
	Make/O/N=0 TipBiasRamp
	If(WaveExists(OffsetWave) == 0 && WaveExists(PullOutNumberWave) == 0 && WaveExists(IzeroWave) == 0)
		Make/O/N=0 OffsetWave, IzeroWave, PullOutNumberWave
	EndIf

End

Function MakePath()
	SVAR PathDate= G_PathDate
	
	String DateStr= Date()
	Variable comma1= strsearch(DateStr,",",0)
	Variable comma2= strsearch(DateStr,",",comma1+1)
	
	String Month
	String Day= DateStr[comma2-2,comma2-1]
	String Year= DateStr[comma2+4,comma2+5]
	
	if (stringmatch(DateStr,"*Jan*")==1)
		Month="01"
	elseif (stringmatch(DateStr,"*Feb*")==1)
		Month="02"	
	elseif (stringmatch(DateStr,"*Mar*")==1)
		Month="03"
	elseif (stringmatch(DateStr,"*Apr*")==1)
		Month="04"	
	elseif (stringmatch(DateStr,"*May*")==1)
		Month="05"
	elseif (stringmatch(DateStr,"*Jun*")==1)
		Month="06"
	elseif (stringmatch(DateStr,"*Jul*")==1)
		Month="07"
	elseif (stringmatch(DateStr,"*Aug*")==1)
		Month="08"
	elseif (stringmatch(DateStr,"*Sep*")==1)
		Month="09"
	elseif (stringmatch(DateStr,"*Oct*")==1)
		Month="10"
	elseif (stringmatch(DateStr,"*Nov*")==1)
		Month="11"
	elseif (stringmatch(DateStr,"*Dec*")==1)
		Month="12"
	endif
	
	PathDate= Month+"_"+Day+SetupID+Year
	NewPath/O/C Data DataDir+PathDate+"Merge:"
	Print "name of path: Data"
	DoWindow/T kwFrame, PathDate	
end

Function SetUpHRTaskID1()
	NVAR G_ID1=G_ID1

	MXCreateTask("G_ID1");
	MXCreateAIVoltageChan(G_ID1,HighResVoltageIn,-10,10);
	MXCreateAIVoltageChan(G_ID1,HighResCurrentIn,-10,10);
	MXCreateAIVoltageChan(G_ID1,PiezoSenseIn,-10,10);	// [NEWDAQ] 3rd channel: piezo driver sense (was ai0 of the second card)
End

//[NEWDAQ-REMOVED: LowRes] Function SetUpLRTaskID3()
	//[NEWDAQ-REMOVED: LowRes] NVAR G_ID3=G_ID3
	//[NEWDAQ-REMOVED: LowRes] NVAR AcquisitionRate=G_AcquisitionRate
	//[NEWDAQ-REMOVED: LowRes]
	//[NEWDAQ-REMOVED: LowRes] NVAR NumPtsInAppliedWaves=G_NumPtsInAppliedWaves
	//[NEWDAQ-REMOVED: LowRes] Variable NumPtsIn= NumPtsInAppliedWaves+2000
	//[NEWDAQ-REMOVED: LowRes] Variable NumPoints= NumPtsIn * 3
	//[NEWDAQ-REMOVED: LowRes]
	//[NEWDAQ-REMOVED: LowRes] MXCreateTask("G_ID3")
	//[NEWDAQ-REMOVED: LowRes] MXCreateAIVoltageChan(G_ID3,LowResPiezoIn,-10,10);
	//[NEWDAQ-REMOVED: LowRes] //MXCreateAIVoltageChan(G_ID3,LowResXPiezoIn,-10,10);
	//[NEWDAQ-REMOVED: LowRes] MXCreateAIVoltageChan(G_ID3,LowResCurrentIn,-10,10);
	//[NEWDAQ-REMOVED: LowRes] MXCreateAIVoltageChan(G_ID3,LowResVoltageIn,-10,10);
	//[NEWDAQ-REMOVED: LowRes] MXCfgSampClkTiming(G_ID3,AcquisitionRate,1,NumPoints)
//[NEWDAQ-REMOVED: LowRes] End

Function ClearHRTaskID1()
	NVAR G_ID1=G_ID1
	
	MXClearTask(G_ID1)
End

//[NEWDAQ-REMOVED: LowRes] Function ClearLRTaskID3()
	//[NEWDAQ-REMOVED: LowRes] NVAR G_ID3=G_ID3
//[NEWDAQ-REMOVED: LowRes]
	//[NEWDAQ-REMOVED: LowRes] MXClearTask(G_ID3)
//[NEWDAQ-REMOVED: LowRes] End


// Function GenerateTrace()
//
// This function is the outgrowth of the old GetPullOut function.
// 
// [NEWDAQ] was: two-card version. G_ID1 (card 1) read junction voltage and current; G_ID3
// (card 2) read piezo sense, current and voltage on its own clock. The two records were
// aligned by cross-correlating the two current traces (GetLowHighOffset -> LowHighOffset)
// and the alignment pulse was searched in the second-card voltage. Now the one task G_ID1
// reads voltage, current and piezo sense on ONE clock (K_NumAIChans blocks of NumPtsIn
// points), the pulse is found in VoltageIn and LowHighOffset is gone. The removed
// second-card lines are kept below with the LowRes tag; the Keithley-bias branch is kept
// commented out.
Function GenerateTrace()
	Wave HighResWriteWave, HighResReadWave	// [NEWDAQ] LowResReadWave removed: one card
	Wave CurrentIn, VoltageIn
	Wave SenseIn	// [NEWDAQ] CurrentInLowRes, VoltageInLowRes removed: one card
	Wave PullOutVoltage,PullOutCurrent,PullOutConductance,POExtension
	Wave PiezoBiasWave, JunctionBiasWave  // already set up in CreateInputs
	Wave W_Findlevels
	NVAR NumPtsInAppliedWaves=G_NumPtsInAppliedWaves
	NVAR G_OD1=G_OD1
	NVAR G_ID1=G_ID1
	//[NEWDAQ-REMOVED: LowRes] NVAR G_ID3=G_ID3
	NVAR AcquisitionRate=G_AcquisitionRate
	NVAR WriteBufferSize = G_WriteBufferSize
	NVAR DCOffset_nm=G_PiezoOffset_nm	// in nm
	NVAR CurrentVoltGain = G_CurrentVoltGain 
	NVAR Size = G_PseudoTotalLength_nm
	NVAR CardTimeout = G_CardTimeout
	NVAR TipBias = G_TipBias
	NVAR startLevel=G_startLevel					// voltage of spike
	NVAR endLevel=G_endLevel					// voltage before and after spike
	NVAR PulseFrontEdgePt=G_PulseFrontEdgePt	// point at startLevel volts just after spike
	NVAR PullOutTime= G_PullOutDatetime
	NVAR DelayOffset = G_DelayOffset
	//[NEWDAQ-REMOVED: Keithley] NVAR KeithleyBiasEnabled=G_KeithleyBiasEnabled
	//[NEWDAQ-REMOVED: Keithley] NVAR SeriesResistance = G_SeriesResistance

	Variable HighResFrontPulsePt, error
	Variable k=0
	// [NEWDAQ-NOTE] The 2000 extra samples (50 ms at 40 kHz) are the room for the card's output-to-input latency: the
	// [NEWDAQ-NOTE] alignment spike has to land inside the last 6000 samples searched by FindLevels below. Tuned on the
	// [NEWDAQ-NOTE] PXI-4461, not yet measured on the USB-6453. If the first real traces print "Did not find both sides
	// [NEWDAQ-NOTE] of pulse" or G_DelayOffset comes out near 2000, raise this 2000 (and the 6000 in the FindLevels range).
	Variable NumPtsIn= NumPtsInAppliedWaves+2000
	Variable NumSeg=NumPtsInAppliedWaves/WriteBufferSize
	Variable PiezoOrigin=DCOffset_nm/K_ZPiezoScale

	Redimension/D/N=(WriteBufferSize*2) HighResWriteWave
	Redimension/D/N=(NumPtsIn*K_NumAIChans) HighResReadWave	// [NEWDAQ] 3 channel blocks: voltage, current, piezo sense
	//[NEWDAQ-REMOVED: LowRes] Redimension/D/N=(NumPtsIn*3) LowResReadWave
	//[NEWDAQ-REMOVED: LowRes] Redimension/D/N=(NumPtsIn) SenseIn, CurrentInLowRes, VoltageInLowRes
	Redimension/D/N=(NumPtsIn) SenseIn	// [NEWDAQ] filled from the 3rd block of HighResReadWave
	Redimension/D/N=(NumPtsIn) CurrentIn, VoltageIn
	Redimension/D/N=(NumPtsInAppliedWaves) PullOutVoltage,PullOutCurrent,PullOutConductance, POExtension

	SetScale/I x 0,Size, PullOutVoltage,PullOutCurrent,PullOutConductance, POExtension
	
	PullOutTime= DateTime
	// HR card: redimension wave to NumPtsIn and start reading task. 
	// this is because the task is the same one used in HR MakeContact. 
	MXCfgSampClkTiming(G_ID1,AcquisitionRate,1,NumPtsIn)
	MXStartTask(G_ID1)
	//[NEWDAQ-REMOVED: LowRes] MXStartTask(G_ID3)

	// Execute writing task
	// Loop over segments of ramps that are WriteBufferSize (1000 pts) long, writing ramps to high-res card
	// The reading tasks were just started and are happening simultaneously to the writing tasks
	for (k=0;k<NumSeg;k+=1)	   
		// PiezoBiasWave needs to be offset to starting piezo displacement
		HighResWriteWave[0,WriteBufferSize-1]=PiezoBiasWave[k*WriteBufferSize+p]+PiezoOrigin
		// [NEWDAQ-NOTE] Pre-existing behaviour, deliberately NOT changed by the port: on the line below p is the
		// [NEWDAQ-NOTE] destination index (WriteBufferSize..2*WriteBufferSize-1), so segment k of the BIAS wave is
		// [NEWDAQ-NOTE] taken from JunctionBiasWave[(k+1)*WriteBufferSize ...], one segment AHEAD of the piezo segment
		// [NEWDAQ-NOTE] on the line above (the last segment reads past the end and Igor repeats the last point).
		// [NEWDAQ-NOTE] The bias and its alignment spike therefore leave the card WriteBufferSize samples (25 ms at
		// [NEWDAQ-NOTE] 40 kHz) before the piezo ramp they belong to, GenerateTrace recovers DelayOffset = (true delay
		// [NEWDAQ-NOTE] - WriteBufferSize), and every saved trace starts with WriteBufferSize points of pre-ramp hold
		// [NEWDAQ-NOTE] while its last WriteBufferSize points of pull are cut off. Found with the simulated card
		// [NEWDAQ-NOTE] (tests/Smoke_NewDAQ.ipf). To align bias and piezo as CreateInputs intends, swap the two lines
		// [NEWDAQ-NOTE] below (this changes how new traces compare with the archived ones):
		//HighResWriteWave[WriteBufferSize,WriteBufferSize*2-1]=JunctionBiasWave[k*WriteBufferSize+p-WriteBufferSize]	// [NEWDAQ-NOTE] aligned alternative, off by default
		HighResWriteWave[WriteBufferSize,WriteBufferSize*2-1]=JunctionBiasWave[k*WriteBufferSize+p]
		MXWriteAnalogF64(G_OD1,CardTimeout,2,HighResWriteWave)
	endfor

	// save final state of piezo at the end of JunctionBiasWave
	DCOffset_nm+= PiezoBiasWave[NumPtsInAppliedWaves-1]*K_ZPiezoScale
	
	// Do one more write
	HighResWriteWave[0,WriteBufferSize-1]=DCOffset_nm/K_ZPiezoScale
	HighResWriteWave[WriteBufferSize,WriteBufferSize*2-1]=-(TipBias/1000)
	MXWriteAnalogF64(G_OD1,CardTimeout,2,HighResWriteWave)
	
	// Read in data to Igor wave
	MXReadAnalogF64(G_ID1,10,K_NumAIChans,HighResReadWave);	// [NEWDAQ] 3 channels, NumPtsIn samples each, grouped by channel
	//[NEWDAQ-REMOVED: LowRes] MXReadAnalogF64(G_ID3,10,3,LowResReadWave);
	
	// Stop and clear reading tasks
	//[NEWDAQ-REMOVED: LowRes] MXStopTask(G_ID3)
	MXStopTask(G_ID1)
	
	VoltageIn= -HighResReadWave[p]		// Voltage (high-res)
	CurrentIn= HighResReadWave[NumPtsIn+p]	// Current (high-res)
	
	SenseIn= HighResReadWave[2*NumPtsIn+p] * K_SenseScale	// [NEWDAQ] piezo sense in nm, block 2 (was the second card)
	//[NEWDAQ-REMOVED: LowRes] SenseIn= LowResReadWave[p] * K_SenseScale		// piezo (low-res)
	//[NEWDAQ-REMOVED: LowRes] CurrentInLowRes= LowResReadWave[p + NumPtsIn]	// current (low-res)
	//[NEWDAQ-REMOVED: LowRes] VoltageInLowRes=- LowResReadWave[p + 2*NumPtsIn]	// voltage before SeriesResistance (low-res)
	
	Smooth/B 11, SenseIn
	
	//[NEWDAQ-REMOVED: LowRes] Variable LowHighOffset
	//[NEWDAQ-REMOVED: LowRes] LowHighOffset=GetLowHighOffset(CurrentIn, CurrentInLowRes)

	Make/O destWave
	FindLevels/Q/P/R=[NumPtsIn-1,NumPtsIn-6000]/EDGE=0/N=2 VoltageIn, 0	// [NEWDAQ] alignment pulse found in the one-card voltage (was VoltageInLowRes)
	if (V_flag!=0)
		print "GenerateTrace: Did not find both sides of pulse for alignment"
		return -1
	endif
	HighResFrontPulsePt=round(W_Findlevels[1])
	DelayOffset=HighResFrontPulsePt-PulseFrontEdgePt	// [NEWDAQ] one clock: no LowHighOffset
	//[NEWDAQ-REMOVED: LowRes] DelayOffset=HighResFrontPulsePt-PulseFrontEdgePt-LowHighOffset
	//DelayOffset=2000-LowHighOffset
	// final factor saves current in amps rather than microamps
	PullOutCurrent=CurrentIn[p+DelayOffset]*(10^(-CurrentVoltGain))
	
	
	
	// save G in units of G0. 
	// 10^-6 in expression for G0 (77.5*10^-6) in denominator
	// CHANGE SIGN TO - FOR KEITHLEY AND + FOR DAQ BIAS
	//[NEWDAQ-REMOVED: Keithley] if (KeithleyBiasEnabled==0)
	PullOutVoltage=VoltageIn[p+DelayOffset]	// [NEWDAQ] DAQ-bias path only (bias comes from HighResBiasOut)
	PullOutConductance=PullOutCurrent/PullOutVoltage/(K_G0)
	//[NEWDAQ-REMOVED: Keithley] else
		//[NEWDAQ-REMOVED: Keithley] PullOutVoltage=-VoltageIn[p+DelayOffset]
		//[NEWDAQ-REMOVED: Keithley] PullOutConductance=(1/((TipBias*1e-3/PullOutCurrent)-SeriesResistance))/K_G0
	//[NEWDAQ-REMOVED: Keithley] endif
	// [NEWDAQ] POExtension IS aligned now: SenseIn comes from the same task and clock as
	// VoltageIn, so the DelayOffset found in VoltageIn applies to it directly.
	POExtension=SenseIn[p+DelayOffset]
	Slider SliderPos_Z win=BreakJunctionMeasurement, value=DCOffset_nm/K_ZPiezoScale
	
	// Update Graphs
	DoWindow/F PullOutGvsE
	if (V_Flag==0)
		execute "PullOutGvsE()"
	endif
	
	DoWindow/F AuAuConductanceLevel
	if (V_Flag==0)
		execute "AuAuConductanceLevel()"
	endif
	
	DoWindow/F PullOutLow
	if (V_Flag==0)
		execute "PullOutLow()"
	endif
	
	DoWindow/F HighRes
	if(V_flag==0)
		execute "HighRes()"
	endif
	// check that the voltage offsets are correct (graph)
	ModifyGraph Offset(CurrentIn)={0,0}	// [NEWDAQ] one clock: no LowHighOffset
	ModifyGraph Offset(VoltageIn)={-DelayOffset,0}
	//[NEWDAQ-REMOVED: LowRes] ModifyGraph Offset(VoltageInLowRes)={-(DelayOffset+LowHighOffset),0}

	DoWindow/F SenseInDisplay
	if (V_flag==0)
		execute "SenseInDisplay()"
	endif
	
	DoUpdate
	
	return 1
	
End

// Blocks are made and killed within this function
Function SavePullOut()
	NVAR PullOutNumber=G_PullOutNumber
	NVAR Size=G_PseudoTotalLength_nm// in nm
	NVAR Rate=G_PullOutRate// in nm/s
	NVAR ApproachStepSize = G_MakeContactApproachStepSize
	NVAR CurrentVoltConversion=G_CurrentVoltConversion
	NVAR TipBias = G_TipBias
	NVAR ConductanceThreshold = G_ConductanceThreshold
	NVAR CurrentSuppress = G_CurrentSuppress // in MicroAmps
	NVAR CurrentSuppressConst = G_CurrentSuppressConst
	NVAR PiezoOffset_nm=G_PiezoOffset_nm	// in nm
	NVAR PiezoOffset_nm=G_PiezoOffset_nm	// in nm
	NVAR SeriesResistance = G_SeriesResistance
	NVAR PullOutTime= G_PullOutDatetime
	
//	NVAR TipTCAvg=G_TipTCAvg
//	NVAR SubTCAvg=G_SubTCAvg

	SVAR PathDate=G_PathDate

	NVAR CurrentSave=G_CurrentSaveCheck
	NVAR BiasSave=G_BiasSaveCheck
	NVAR SenseSave= G_SenseSaveCheck	
	NVAR HistSave=G_HistSaveCheck
	NVAR PiezoWaveSave=G_PiezoWaveSaveCheck
	NVAR GateVoltage=G_CounterElectrodeBias
	
	NVAR Vzero= G_Vzero
	NVAR Izero= G_Izero
	
	Wave PullOutVoltage, PullOutConductance, PullOutCurrent
	Wave SenseIn, POExtension
	Wave PiezoBiasWave
	Wave ParameterWave, PullOutConductanceSave
	Wave LogHistWave

	Variable StartX= Mean(SenseIn,0,999)
	Variable StopX= Mean(SenseIn,numpnts(SenseIn)-1000,numpnts(SenseIn)-1)

	ParameterWave[0] = Size
	ParameterWave[1] = Rate
	ParameterWave[2] = ApproachStepSize
	ParameterWave[3] = PiezoOffset_nm
	ParameterWave[4] = BiasSave
	ParameterWave[5] = StartX-StopX
//	ParameterWave[6] = TipTCAvg
//	ParameterWave[7] = SubTCAvg
	ParameterWave[8] =  0
	ParameterWave[9] = CurrentVoltConversion
	ParameterWave[10] = TipBias
	ParameterWave[11] = 0
	ParameterWave[12] = SeriesResistance
	ParameterWave[13] = ConductanceThreshold
	ParameterWave[14] = 0
	ParameterWave[15] = Vzero
	ParameterWave[16] =  Izero
	ParameterWave[17] = PullOutTime
	ParameterWave[18] = GateVoltage	
	ParameterWave[19] = CurrentSuppress
	
	// Make Blocks
	if(mod(PullOutNumber,100)==1)
		
		Make/O/N=(Numpnts(PullOutConductance) +2+numpnts(ParameterWave),100) ConductanceBlock=NAN

		if (BiasSave==1)			
			Make/O/N=(Numpnts(PullOutVoltage),100) VoltageBlock=NAN
			SetScale/I x 0, Size, "" VoltageBlock
		endif
		
		if (CurrentSave==1)
			Make/O/N=(Numpnts(PullOutCurrent),100) CurrentBlock=NAN
			SetScale/I x 0, Size, "" CurrentBlock
		endif
	
		if (SenseSave==1)
			Make/O/N=(Numpnts(POExtension),100) ExtensionBlock=NAN
			SetScale/I x 0, Size, "" ExtensionBlock
		endif
	  
	endif
	
	// Write to blocks
	Variable i 
	Variable k=numpnts(PullOutConductance)
	Wave PullOutConductanceSave, POCondHist
	Redimension/N=(k) PullOutConductanceSave
	PullOutConductanceSave = PullOutConductance
	Redimension/N=(k+2+numpnts(ParameterWave)) PullOutConductanceSave	
	
	for (i=0;i<numpnts(ParameterWave);i+=1)
		PullOutConductanceSave[k+i+2]=ParameterWave[i]
	endfor
	
	// Save Conductance
	variable m = 0
	for(m=0; m<numpnts(PullOutConductanceSave); m+=1)
		ConductanceBlock[m][mod(PullOutNumber-1,100)]=PullOutConductanceSave[m]
	endfor
	
	if (BiasSave==1)	// Save measured voltage
		m=0
		for(m=0; m<numpnts(PullOutVoltage); m+=1)
			VoltageBlock[m][mod(PullOutNumber-1,100)]=PullOutVoltage[m]
		endfor
	endif
	
	if (CurrentSave==1)	// Save current
		m=0
		for(m=0; m<numpnts(PullOutCurrent); m+=1)
			CurrentBlock[m][mod(PullOutNumber-1,100)]=PullOutCurrent[m]
		endfor
	endif	

	if (SenseSave==1) 	// Save Piezo
		m=0
		for(m=0; m<numpnts(POExtension); m+=1)
			ExtensionBlock[m][mod(PullOutNumber-1,100)] = POExtension[m]
		endfor	
	endif
	

	// Save blocks to file
	// Histogram is one wave instead of a block
	if(mod(PullOutNumber,100)==0 && WaveExists(ConductanceBlock))
		String ConductanceBlockName="PullOutConductanceBlock_"+Num2Str(Round(PullOutNumber/100))
		Duplicate/O ConductanceBlock $ConductanceBlockName
		Save/C/P=Data $ConductanceBlockName
			
		if(BiasSave==1)
			String Voltage="PullOutVoltageBlock_"+Num2Str(Round(PullOutNumber/100))
			Duplicate/O VoltageBlock $Voltage
			Save/C/P=Data $Voltage
			Killwaves $Voltage, VoltageBlock	
		endif
		
		if(CurrentSave==1)
			String Current="PullOutCurrentBlock_"+Num2Str(Round(PullOutNumber/100))
			Duplicate/O CurrentBlock $Current
			Save/C/P=Data $Current
			Killwaves $Current, CurrentBlock	
		endif

		if(SenseSave==1)
			String ExtensionBlockName="PullOutExtensionBlock_"+Num2Str(Round(PullOutNumber/100))
			Duplicate/O ExtensionBlock $ExtensionBlockName
			Save/C/P=Data $ExtensionBlockName
			killwaves $ExtensionBlockName, ExtensionBlock
		endif

		if(SenseSave==0)		
			String Extension2="PullOutExtension_"+Num2Str(PullOutNumber)
			Duplicate/O POExtension $Extension2
			Save/C/P=Data $Extension2
			Killwaves $Extension2		
		endif
		If(BiasSave==0)	
			String Voltage2="PullOutVoltage_"+Num2Str(PullOutNumber)
			String Current2="PullOutCurrent_"+Num2Str(PullOutNumber)		
			Duplicate/O PullOutVoltage $Voltage2		
			Save/C/P=Data $Voltage2
			Killwaves $Voltage2		
			Duplicate/O PullOutCurrent $Current2
			Save/C/P=Data $Current2
			Killwaves $Current2	
		endif

             if(PiezoWaveSave==1)
			String PiezoBiasWaveName="PullOutPiezoBiasWave_"+Num2Str(Round(PullOutNumber/100))
			Duplicate/O PiezoBiasWave, $PiezoBiasWaveName
			Save/C/P=Data $PiezoBiasWaveName
			killwaves $PiezoBiasWaveName
			//PiezoBiasWave is the applied wave on piezo, so wasn't killed
		endif

		LogHistFromBlocks(ConductanceBlock)
	
		if (HistSave==1)	
	        	String ConductanceBlockHistname = "PullOutConductanceBlockHist_" +Num2Str(Round(PullOutNumber/100)) 
			Duplicate/O LoghistWave, $ConductanceBlockHistname
			Save/C/P=Data $ConductanceBlockHistName
			Killwaves  $ConductanceBlockHistName	// Don't kill LogHistWave-- it is displayed during measurement
		endif

		killwaves $ConductanceBlockName, ConductanceBlock

	endif

	PullOutNumber+=1
	Beep
	DoWindow/T kwFrame, "Exp: "+num2str(pulloutnumber) + " "+num2str(round(PiezoOffset_nm))
	
	DoUpdate
End

Function StartBkgdSampling()
	NVAR G_ID1= G_ID1
	//[NEWDAQ-REMOVED: LowRes] NVAR G_ID2=G_ID2
	NVAR CardTimeout = G_CardTimeout;
	NVAR ReadWaveSize= G_FastReadWaveSize
	NVAR AcquisitionRate= G_AcquisitionRate
	
	Variable HighResReadWaveSize
	HighResReadWaveSize= ReadWaveSize * 2	// [NEWDAQ] per-channel buffer of the continuous task (2x headroom); the read wave is sized in BackgroundRead
		
	// LowRes piezo voltage readout background task
	//[NEWDAQ-REMOVED: LowRes] MXCreateTask("G_ID2");
	//[NEWDAQ-REMOVED: LowRes] MXCreateAIVoltageChan(G_ID2,LowResPiezoIn,-10,10);
	//[NEWDAQ-REMOVED: LowRes] MXCfgSampClkTiming(G_ID2,AcquisitionRate,0,ReadWaveSize)
	
	// [NEWDAQ] junction voltage, current and piezo sense readout background task (one card, 3 channels)
	SetUpHRTaskID1()
	// Needed for setting correct size of wave to be read 
	MXCfgSampClkTiming(G_ID1,AcquisitionRate,1,HighResReadWaveSize)
	
	CtrlNamedBackground BkgdRead, period=15, proc=BackgroundRead
	CtrlNamedBackground BkgdRead, start
end

Function BackgroundRead(s)
	STRUCT WMBackgroundStruct &s

	//[NEWDAQ-REMOVED: LowRes] Wave LowResReadWaveBkgd
	Wave HighResReadWaveBkgd
	Wave SenseInBkgd	
	Wave VolHighResIn, CurHighResIn
	
	NVAR G_ID1= G_ID1
	//[NEWDAQ-REMOVED: LowRes] NVAR G_ID2= G_ID2
	NVAR CurrentSample= G_CurrentSamplingReadoutVal
	NVAR JunctionVoltage= G_JunctionVoltage
	NVAR PiezoBiasSample= G_PiezoBiasSamplingReadoutVal
	NVAR CurrentVoltConversion= G_CurrentVoltConversion
	NVAR ReadWaveSize= G_FastReadWaveSize
	NVAR AcquisitionRate= G_AcquisitionRate

	Redimension/D/N=(ReadWaveSize) VolHighResIn, CurHighResIn
	Redimension/D/N=(ReadWaveSize*K_NumAIChans) HighResReadWaveBkgd	// [NEWDAQ] 3 channel blocks
	//[NEWDAQ-REMOVED: LowRes] Redimension/D/N=(ReadWaveSize) LowResReadWaveBkgd, SenseInBkgd
	Redimension/D/N=(ReadWaveSize) SenseInBkgd	// [NEWDAQ]
	
	//[NEWDAQ-REMOVED: LowRes] // LowRes piezo voltage readout
	//[NEWDAQ-REMOVED: LowRes] MXReadAnalogF64(G_ID2,10,1,LowResReadWaveBkgd);
	//[NEWDAQ-REMOVED: LowRes] SenseInBkgd= LowResReadWaveBkgd
	//[NEWDAQ-REMOVED: LowRes] PiezoBiasSample= Mean(SenseInBkgd)
	
	// [NEWDAQ] junction voltage, current and piezo sense readout (one card, 3 channels)
	MXStartTask(G_ID1)
	MXReadAnalogF64(G_ID1,10,K_NumAIChans,HighResReadWaveBkgd);	// [NEWDAQ]
	MXStopTask(G_ID1)
	
	VolHighResIn= HighResReadWaveBkgd[p]
	CurHighResIn= HighResReadWaveBkgd[ReadWaveSize+p]
	SenseInBkgd= HighResReadWaveBkgd[2*ReadWaveSize+p]	// [NEWDAQ] piezo sense, block 2 (volts)
	PiezoBiasSample= Mean(SenseInBkgd)	// [NEWDAQ] the Piezo (V) readout stays in volts as before
	
	JunctionVoltage= -Mean(VolHighResIn) * 1e3	// in mV
	CurrentSample = Mean(CurHighResIn)*CurrentVoltConversion	// in micro Amps
	
	if (abs(CurrentSample)>.15)
		beep
	endif
	
	DoUpdate
	return 0
End

Function StopBkgdSampling()
	//[NEWDAQ-REMOVED: LowRes] NVAR G_ID2=G_ID2

	CtrlNamedBackground BkgdRead, stop
	
	ClearHRTaskID1()
	//[NEWDAQ-REMOVED: LowRes] MXClearTask(G_ID2)
end

//+++++++++++++++++++++++++++++++++++++++++++++++++++++++
// Thermocouple voltage sampling. 
//Function StartThermoSampling()
//	NVAR G_ID6=G_ID6
//	NVAR CardTimeout = G_CardTimeout;
//	NVAR ReadWaveSize= G_FastReadWaveSize
//	NVAR AcquisitionRate= G_AcquisitionRate
//		
//	// Set Up the Input Task, Input Channel and Timing
//	MXCreateTask("G_ID6");
//	MXCreateAIVoltageChan(G_ID6,TCchan4,-0.001,0.001);
//	MXCreateAIVoltageChan(G_ID6,TCchan5,-0.001,0.001);
//	MXCfgSampClkTiming(G_ID6,AcquisitionRate,0,ReadWaveSize)
//
//	CtrlNamedBackground TempRead, period=30, proc=ThermoBkgdRead
//	CtrlNamedBackground TempRead, start
//end
//+++++++++++++++++++++++++++++++++++++++++++++++++++++++
// Stop sampling TC voltage. 
//Function StopThermoSampling()
//	NVAR G_ID6=G_ID6
//	
//	CtrlNamedBackground TempRead, stop
//	MXClearTask(G_ID6)
//end
//+++++++++++++++++++++++++++++++++++++++++++++++++++++++
// Thermocouple background reading procedure. 
//Function ThermoBkgdRead(s)
//	STRUCT WMBackgroundStruct &s
//
//	Wave LowResReadWave
//	Wave TCTipVoltageIn, TCSubVoltageIn
//	Wave HighTConversionConstant, LowTConversionConstant
//	NVAR ReadWaveSize= G_FastReadWaveSize
//	NVAR G_ID6= G_ID6
//	NVAR TCTipSample= G_TCTipSample
//	NVAR TCSubSample= G_TCSubSample
//	NVAR RT= G_RT
//	
//	Redimension/D/N=(ReadWaveSize*2) LowResReadWave
//	Redimension/D/N=(ReadWaveSize) TCTipVoltageIn
//	Redimension/D/N=(ReadWaveSize) TCSubVoltageIn
//	
//	MXReadAnalogF64(G_ID6,10,2,LowResReadWave);
//	
//	TCTipVoltageIn= LowResReadWave[p]
//	TCSubVoltageIn= LowResReadWave[ReadWaveSize+p]
//	
//	TCTipSample= Mean(TCTipVoltageIn)*1e3		// in mV
//	TCSubSample = Mean(TCSubVoltageIn)*1e3		// in mV
//	
//	// convert based on NIST k-thermocouple constants
//	if (TCTipSample > 0)
//		TCTipSample = poly(HighTConversionConstant,TCTipSample)
//	else
//		TCTipSample = poly(LowTConversionConstant,TCTipSample)
//	endif
//	
//	if (TCSubSample > 0)
//		TCSubSample = poly(HighTConversionConstant,TCSubSample)
//	else
//		TCSubSample = poly(LowTConversionConstant,TCSubSample)
//	endif
//	
//	// reference junction is at room temperature
//	TCTipSample+= RT
//	TCSubSample+= RT
//
//	DoUpdate
//	return 0
//End
//+++++++++++++++++++++++++++++++++++++++++++++++++++++++

//Cut off the hold and extra push sections before making a histogram
Function LogHistFromBlocks(ConductanceBlock)
	Wave ConductanceBlock

	Wave LogHistWave
	NVAR AcquisitionRate= G_AcquisitionRate
	NVAR ExcursionRate= G_PullOutRate// in nm/s
	NVAR Size= G_PseudoTotalLength_nm
	NVAR PulseFrontEdgePt= G_PulseFrontEdgePoint
	NVAR ZeroCutoff= G_EndOfTraceNoiseThreshold
	
	// PushPull Variables
	NVAR PushPullCheck= G_PushPullCheck
	NVAR InitialPullLength= G_InitialPullLength
	NVAR FinalPullLength= G_FinalPullLength
	
	// IV Variables
	NVAR IVCheck= G_IVCheck
	NVAR IVInitPull= G_IVInitPull
	NVAR IVFinPull= G_IVFinPull
	
	// AC Hold variables
	NVAR ACHoldCheck= G_ACHoldCheck
	NVAR ACInitPullLength= G_ACInitPullLength
	NVAR ACFinPullLength= G_ACFinPullLength
	
	// HB Hold variables
	NVAR HBHoldCheck= G_HBHoldCheck
	NVAR HBInitPullLength= G_HBInitPullLength
	NVAR HBFinPullLength= G_HBFinPullLength
	
	Variable StartDelete=0, NumberToDelete=0, Numpts, i

	if (PushPullCheck==1)	
		StartDelete=round(InitialPullLength/ExcursionRate*AcquisitionRate)
		NumberToDelete=round((Size-InitialPullLength-FinalPullLength)/ExcursionRate*AcquisitionRate)	
	elseif (IVCheck==1)	
		StartDelete=round(IVInitPull/ExcursionRate*AcquisitionRate)
		NumberToDelete=round((Size-IVInitPull-IVFinPull)/ExcursionRate*AcquisitionRate)		
	elseif (ACHoldCheck==1)		
      		StartDelete=round(ACInitPullLength/ExcursionRate*AcquisitionRate)
		NumberToDelete=round((Size-ACInitPullLength-ACFinPullLength)/ExcursionRate*AcquisitionRate)	
	elseif(HBHoldCheck==1)
	      StartDelete=round(HBInitPullLength/ExcursionRate*AcquisitionRate)
		NumberToDelete=round((Size-HBInitPullLength-HBFinPullLength)/ExcursionRate*AcquisitionRate)
	endif

	Redimension/N=1000 LogHistWave
	Loghistwave = 0 
	Setscale/I x -8,2,"", Loghistwave
	
	Variable Lowcutoff

	for(i=0; i< 100; i+=1)
		Make/O/N=(dimsize(ConductanceBlock,0)) Tempwave
		Tempwave = 0
		Tempwave[]=ConductanceBlock[p][i] 

		// Removes parameters and spike
		
		Redimension/N=(NumPnts(Tempwave)*0.95) Tempwave
             		
		//delete points for the hold or push-pull section
             	if (PushPullCheck==1||IVCheck==1||ACHoldCheck==1||HBHoldCheck==1)
			Deletepoints StartDelete, NumberToDelete, tempwave
		       endif
		
		
		Smooth/B  11, tempwave
	
		Numpts=Numpnts(Tempwave)
		Wavestats/Q/R = [Numpts*.95,Numpts*.96] tempwave
		Lowcutoff = V_avg

		//adjust noise
		if(Lowcutoff<ZeroCutoff)
			Tempwave-= Lowcutoff
			Smooth/B 11, Tempwave
			Tempwave= log(tempwave)
			Histogram/A tempwave, Loghistwave	
		endif
	endfor
	
	LogHistWave= LogHistWave/100		// Counts/Trace
	
	DoWindow/F LogHistofBlock
	if (V_Flag==0)
		Execute "LogHistOfBlock()"
	endif

End

// Read Current, Voltage, calculate Conductance with HighRes card
Function ReadCurrentAndVoltage()
	Wave HighResReadWave
	Wave CurrentIn, VoltageIn

	NVAR G_ID1=G_ID1
	NVAR CurrentVoltGain= G_CurrentVoltGain
	NVAR Vol= G_Vol
	NVAR Cur= G_Cur
	NVAR Cond= G_Cond
	
	Variable AvgVoltageIn, AvgCurrentIn, Conductance
	Variable ReadWaveSize= 2500	// [NEWDAQ] samples per channel (unchanged: was 5000/2)
	Variable HighResReadWaveSize= ReadWaveSize * K_NumAIChans	// [NEWDAQ] 3 channel blocks
		
	Redimension/D/N=(HighResReadWaveSize) HighResReadWave
	Redimension/D/N=(ReadWaveSize) CurrentIn, VoltageIn
	
	MXStartTask(G_ID1)
	MXReadAnalogF64(G_ID1,10,K_NumAIChans,HighResReadWave)	// [NEWDAQ]
	MXStopTask(G_ID1)
	
	VoltageIn= HighResReadWave[p]
	CurrentIn= HighResReadWave[p+ReadWaveSize]
	
	AvgVoltageIn= Mean(VoltageIn)		// in Volts
	AvgCurrentIn= Mean(CurrentIn)*10^(-CurrentVoltGain)		// in Amps

	
	// G(G0) = [ I(A) / V(V) / G(uS) ]
	Conductance= abs(AvgCurrentIn/AvgVoltageIn)/K_G0	// in G0

	
	// Voltage, current and conductance are stored in 3 global variables
	Vol= AvgVoltageIn
	Cur= AvgCurrentIn
	Cond= Conductance
	
//	Print "current= ", cur, "voltage= ", vol, "conductance= ", cond
	
End

// Estimate the Voltage Offset value at zero bias. 
//******************************************************************************************************************************
Function OffsetVoltage()
	Wave CurrentWave, VoltageWave
	Wave ConductanceWave
	Wave TipBiasRamp
	
	Variable i, Increment
	Variable HighResReadWaveSize= 5000
	
	NVAR G_ID1=G_ID1
	NVAR AcquisitionRate= G_AcquisitionRate
	
	NVAR TipBias= G_TipBias
	NVAR NumPts= G_NumPoints
	NVAR Bound= G_VoltageInterval	// in mV
	NVAR Vzero= G_Vzero 			// in mV
	NVAR Izero= G_Izero		// in microAmps 
	NVAR Vol= G_Vol
	NVAR Cur= G_Cur
	NVAR Cond= G_Cond

	Redimension/D/N=(2*NumPts) CurrentWave, VoltageWave
	Redimension/D/N=(2*NumPts) ConductanceWave
	Redimension/D/N=(2*NumPts) TipBiasRamp
	
//	SetUpHRTaskID1()
	MXCfgSampClkTiming(G_ID1,AcquisitionRate,1,HighResReadWaveSize)
	
	Increment= Abs(Bound) / NumPts
	
	// TipBias ramp wave from -Bound to +Bound voltage values 
	For(i= 0; i < 2*NumPts; i+= 1)
		TipBiasRamp[i] = -Abs(Bound) + Increment * i
	EndFor
	
	// measure current and voltage for NumPts low bias values, from TipBias+Increment to +Bound
	// from point 0 to NumPts tip bias is in the negative region
	For(i= 0; i < 2*NumPts; i+= 1)
		// check contact at 100mV
		HighResContact()
		// apply low bias
		WriteToHighRes(0,TipBiasRamp[i])
		Sleep/T 3
		// measure current and voltage, calculate conductance
		ReadCurrentAndVoltage()
		// make wave with current, voltage and conductance values
		VoltageWave[i]= Vol	// voltage in Volts
		CurrentWave[i]= Cur	// current in micro Amps
		ConductanceWave[i]= Cond
	EndFor

//	Extrapolate Voltage Offset value at zero applied bias by linear fitting. 
//	Voltage Offset Vzero is voltage to be applied to get zero current flowing.
	VoltageWave*= 1e6	// voltage in micro Volts
	Make/O/N=2 W_coef
	CurveFit/Q/M=0/W=0 line, kwCWave=W_coef, CurrentWave/X= TipBiasRamp/D
	Izero= W_coef[0]	// in micro Amps
	Vzero= -(Izero / W_Coef[1]) // in mV
	
//	ClearHRTaskID1()
		
	WriteToHighRes(0, TipBias)
	
End

// CheckBox: measure and save Vzero offset periodically
Function VzeroCheckProc(ctrlName,checked) : CheckBoxControl
	String ctrlName
	Variable checked

End

//	Save Offset Voltage if VzeroCheckBox is checked. 
//***********************************************************************
Function SaveOffset()
	Wave OffsetWave
	Wave PullOutNumberWave
	Wave ParameterWave
	Wave IzeroWave
	
	NVAR PullOutNumber= G_PullOutNumber
	NVAR Vzero= G_Vzero
	NVAR Izero= G_Izero
	NVAR Frequency= G_VzeroFrequency
	NVAR J= G_J
	NVAR StopNumber= G_StopNumber
	
	ControlInfo/W=Voltage_Offset VzeroCheckBox
	if(V_Value == 1)
		if(Mod(PullOutNumber, Frequency) == 0)
		
				Redimension/D/N=(StopNumber/Frequency) OffsetWave
				Redimension/D/N=(StopNumber/Frequency) IzeroWave
				Redimension/D/N=(StopNumber/Frequency) PullOutNumberWave

				J+= 1	

				OffsetVoltage()
				OffsetWave[J - 1]= Vzero
				IzeroWave[J - 1]= Izero 
				PullOutNumberWave[J - 1]= PullOutNumber
				
				Variable i
				For(i= J; i < StopNumber/Frequency; i+= 1)
					OffsetWave[i]= NaN
					IzeroWave[i]= NaN
					PullOutNumberWave[i]= NaN
				EndFor
				
				DoWindow/F Izero
				if(V_flag==0)
					execute "Izero()"
				endif
							
//				DoWindow/F Izero_Time
//				if(V_flag==0)
//					execute "Izero_Time()"
//				endif
//				DoUpdate
		endif
	endif
	
End 
//***********************************************************************

// In contact with current, voltage, conductance measured by HighRes card
Function HighResContact()
	NVAR ConductanceThreshold= G_ConductanceThreshold
	NVAR Cond= G_Cond
	
	Variable StepIn
	Variable TipBiasContact= 100	// in mV
	
	StepIn= +2	// piezo step
	
	Do	
		// set tip bias to 100mV
		WriteToHighRes(0, TipBiasContact)
		
		// read current, voltage, calculate conductance
		ReadCurrentAndVoltage()
		
		if(Cond > ConductanceThreshold)
			break
		endif
		// move to contact
		WriteToHighRes(StepIn, TipBiasContact)
	While(1)
End

// Ou of contact with current, voltage, conductance measured by HighRes card
Function HighResOutOfContact()
	NVAR ConductanceThreshold= G_ConductanceThreshold
	NVAR Cond= G_Cond
	NVAR NoiseThreshold= G_EndOfTraceNoiseThreshold

	Variable StepOut
	Variable TipBiasContact= 100	// in mV
	
	StepOut= -5	// piezo step 
	
	Do
		// set tip bias to 100mV
		WriteToHighRes(0, TipBiasContact)
		
		// read current, voltage, calculate conductance
		ReadCurrentAndVoltage()
		
		if(Cond < NoiseThreshold)
			break
		endif
		// move out of contact
		WriteToHighRes(StepOut,TipBiasContact)
	While(1)
End

// Measures current at zero V applied bias, at the present tip location
// Called by FindSuppress button.
//[NEWDAQ-REMOVED: Keithley] Function TestVirtualGround()
	//[NEWDAQ-REMOVED: Keithley] Wave CurSup, CurOffset, HighResReadWave
	//[NEWDAQ-REMOVED: Keithley] Wave CurHighResIn, VolHighResIn
	//[NEWDAQ-REMOVED: Keithley]
	//[NEWDAQ-REMOVED: Keithley] NVAR G_ID1= G_ID1
	//[NEWDAQ-REMOVED: Keithley] NVAR TipBias= G_TipBias
	//[NEWDAQ-REMOVED: Keithley] NVAR AcquisitionRate= G_AcquisitionRate
	//[NEWDAQ-REMOVED: Keithley]
	//[NEWDAQ-REMOVED: Keithley] Variable HighResReadWaveSize
	//[NEWDAQ-REMOVED: Keithley] Variable ReadWaveSize= 2000
	//[NEWDAQ-REMOVED: Keithley] Variable NewSuppress
	//[NEWDAQ-REMOVED: Keithley]
	//[NEWDAQ-REMOVED: Keithley] Redimension/N=21 CurSup, CurOffset
	//[NEWDAQ-REMOVED: Keithley] CurSup = p*(2/(numpnts(CurSup)-1)) -1
//[NEWDAQ-REMOVED: Keithley]
	//[NEWDAQ-REMOVED: Keithley] HighResReadWaveSize= ReadWaveSize * 2
	//[NEWDAQ-REMOVED: Keithley]
	//[NEWDAQ-REMOVED: Keithley] SetUpHRTaskID1()
	//[NEWDAQ-REMOVED: Keithley] MXCfgSampClkTiming(G_ID1,AcquisitionRate,1,HighResReadWaveSize)
	//[NEWDAQ-REMOVED: Keithley]
	//[NEWDAQ-REMOVED: Keithley] Redimension/D/N=(HighResReadWaveSize) HighResReadWave
	//[NEWDAQ-REMOVED: Keithley] Redimension/D/N=(ReadWaveSize) CurHighResIn, VolHighResIn
//[NEWDAQ-REMOVED: Keithley]
	//[NEWDAQ-REMOVED: Keithley] Variable k
	//[NEWDAQ-REMOVED: Keithley] for (k=0;k<numpnts(CurSup)+1;k+=1)
//[NEWDAQ-REMOVED: Keithley] //++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
//[NEWDAQ-REMOVED: Keithley] // 	This is the real SPIKE problem: the amplifier is slow to respond to the command, so
//[NEWDAQ-REMOVED: Keithley] //	a delay in Igor flow execution is needed to avoid the spikes in the sup current.
		//[NEWDAQ-REMOVED: Keithley] SetCurrentSuppress("",CurSup[k],"","")
		//[NEWDAQ-REMOVED: Keithley] sleep/T 5
//[NEWDAQ-REMOVED: Keithley] //++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
		//[NEWDAQ-REMOVED: Keithley] MXStartTask(G_ID1)
		//[NEWDAQ-REMOVED: Keithley] MXReadAnalogF64(G_ID1,10,2,HighResReadWave)
		//[NEWDAQ-REMOVED: Keithley] MXStopTask(G_ID1)
		//[NEWDAQ-REMOVED: Keithley]
		//[NEWDAQ-REMOVED: Keithley] VolHighResIn= HighResReadWave[p]
		//[NEWDAQ-REMOVED: Keithley] CurHighResIn= HighResReadWave[p + ReadWaveSize]
		//[NEWDAQ-REMOVED: Keithley] CurOffset[k] = Mean(CurHighResIn)
		//[NEWDAQ-REMOVED: Keithley]
		//[NEWDAQ-REMOVED: Keithley] DoUpdate
	//[NEWDAQ-REMOVED: Keithley] endfor
//[NEWDAQ-REMOVED: Keithley]
	//[NEWDAQ-REMOVED: Keithley] ClearHRTaskID1()
	//[NEWDAQ-REMOVED: Keithley]
	//[NEWDAQ-REMOVED: Keithley] Make/O/N=2 W_coef
	//[NEWDAQ-REMOVED: Keithley] CurveFit/Q/M=0/W=0 line, kwCWave=W_coef, CurSup[1,numpnts(CurSup)-2]/X=CurOffset[1,numpnts(CurSup)-2]/D
	//[NEWDAQ-REMOVED: Keithley] NewSuppress= W_coef[0]
	//[NEWDAQ-REMOVED: Keithley] SetCurrentSuppress("",NewSuppress,"","")
		//[NEWDAQ-REMOVED: Keithley]
	//[NEWDAQ-REMOVED: Keithley] Print "New current suppress is " + num2str(NewSuppress)
	//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] End

// HighResWriteWave -- wave used for writing to high res
// deltaZ_nm		the change to be added to current position
// TipBias is in mV (as entered on the panel)
Function WriteToHighRes(deltaZ_nm,TipBias)
	Variable deltaZ_nm, TipBias
	
	Wave HighResWriteWave	
	NVAR DCOffset_nm= G_PiezoOffset_nm	// in nm
	NVAR G_OD1= G_OD1;		// Task Variable for output channel
	NVAR CardTimeout= G_CardTimeout;
	NVAR WriteBufferSize= G_WriteBufferSize;
	NVAR AcquisitionRate= G_AcquisitionRate
	
	Variable DCOffset
	
	DCOffset_nm= DCOffset_nm + deltaZ_nm
	DCOffset= DCOffset_nm / K_ZPiezoScale

	Redimension/D/N=(WriteBufferSize*2) HighResWriteWave

	HighResWriteWave[0,WriteBufferSize-1]= DCOffset
	HighResWriteWave[WriteBufferSize,WriteBufferSize*2-1]= -(TipBias/1000)
	
	MXWriteAnalogF64(G_OD1,CardTimeout,2,HighResWriteWave)
	if (GetRTError(1))
	endif
	
	Slider SliderPos_Z win=BreakJunctionMeasurement, value=DCOffset_nm/K_ZPiezoScale
End

Function TestTrace()
	NVAR PulseFrontEdgePt=G_PulseFrontEdgePt
	NVAR ZeroCutOff = G_EndOfTraceNoiseThreshold
	NVAR PullOutAttempt = G_PullOutAttempt
	NVAR EngageConductance = G_ConductanceThreshold
	Wave PullOutConductance, HistLowG, EndConductance
	
	Variable Mean_EndCond, Dev_Conductance, PointsPerTrace, HistSum
	Make/O/N=1 CondHist

	PointsPerTrace=numpnts(PullOutConductance)
	WaveStats/Q/R=[PointsPerTrace*0.9, PointsPerTrace*0.91] PullOutConductance
	Mean_EndCond = V_avg
	Dev_Conductance = V_adev
	if (abs(V_avg)<ZeroCutoff)  // end of PullOutConductance is not close to zero
 		printf("End Conductance, %3.3e\r"), V_avg
		WaveStats/Q/R=[0,round(PointsPerTrace/200)] PullOutConductance
			if (abs(V_avg)>EngageConductance)
				HistSum=0
				CondHist=0
				Histogram/B={0.1,.1,40} PullOutConductance CondHist
				HistSum=sum(condhist,0.5,2.5)
				if (Dev_Conductance < .01) 
					if (HistSum>10)	// Save if there are enough low conductance points
						return 1
					else
						return -1
					endif
				else
					printf("Avg = %3.3e, Dev = %3.3e\r"),  Mean_EndCond, Dev_Conductance
					return -1
				endif
			//else
				//printf " No Contact, Deviation = %2.6f\r, Average = %2.6f\r",V_adev, V_avg
				//return -1
			endif
	else
		print "Ending G= "+num2str(Mean_EndCond)+" > ZeroCutoff"
		return -1
	endif
		
//	HistLowG=0
//	Histogram/b={.1, 0.1, 40} Pulloutconductance HistLowG
//	if(sum(HistLowG,0.5,2.5)<10)
//		print "No Low G features",PullOutAttempt
//		return -1
//	endif
//	
//	Duplicate/O/R=[PulseFrontEdgePt-numpnts(EndConductance)+1,PulseFrontEdgePt] PullOutConductance EndConductance
//	Variable AvgEndG= Mean(EndConductance)
//	
//	if (AvgEndG>ZeroCutOff)
//		print "Ending G= "+num2str(AvGEndG)+" > ZeroCutoff"
//		return -1
//	endif
	
	return 1
End

Function HighResMakeContact()
	Wave ContactCheckWave
	Wave VolHighResIn, CurHighResIn
	
	NVAR G_ID1=G_ID1
	NVAR AcquisitionRate=G_AcquisitionRate
	NVAR CardTimeout = G_CardTimeout
	NVAR ReadWaveSize= G_FastReadWaveSize
	
	NVAR TipBias = G_TipBias
	NVAR ConductanceThreshold = G_ConductanceThreshold
	NVAR ApproachStepSize = G_MakeContactApproachStepSize
	NVAR DCOffset_nm=G_PiezoOffset_nm	// in nm
	NVAR PiezoChanHigh= G_PiezoChanHigh
	NVAR PiezoChanLow= G_PiezoChanLow
	NVAR CurrentVoltGain= G_CurrentVoltGain
	
	NVAR NoiseThreshold= G_EndOfTraceNoiseThreshold
	//[NEWDAQ-REMOVED: Keithley] NVAR KeithleyBiasEnabled=G_KeithleyBiasEnabled
	//[NEWDAQ-REMOVED: Keithley] NVAR SeriesResistance = G_SeriesResistance
	
//	NVAR VoltageRead= G_VoltageRead
//	NVAR ReadChan= G_ReadChan
	 
	Variable Current, Conductance, keys
	Variable RetractionStep= -5	// distance in nm that the tip will be retracted if there is contact at beginning
	Variable Voltage
	Variable HighResReadWaveSize= ReadWaveSize * K_NumAIChans	// [NEWDAQ] 3 channel blocks
	
	Redimension/D/N=(HighResReadWaveSize) ContactCheckWave
	Redimension/D/N=(ReadWaveSize) CurHighResIn, VolHighResIn

	MXCfgSampClkTiming(G_ID1,AcquisitionRate,1,ReadWaveSize)
	MXStartTask(G_ID1)
	MXReadAnalogF64(G_ID1,10,K_NumAIChans,ContactCheckWave)	// [NEWDAQ]
	MXStopTask(G_ID1)
	
	VolHighResIn= ContactCheckWave[p]
	CurHighResIn= ContactCheckWave[p + ReadWaveSize]
	
	Current= (Mean(CurHighResIn))*10^(-CurrentVoltGain)	
	Voltage= (Mean(VolHighResIn)) // in Volts
	
	//[NEWDAQ-REMOVED: Keithley] if (KeithleyBiasEnabled==0)
	Conductance= (Abs(Current)/Abs(Voltage))/K_G0	// [NEWDAQ] in units of G0; DAQ-bias formula only
	//[NEWDAQ-REMOVED: Keithley] else
		//[NEWDAQ-REMOVED: Keithley] Conductance=(1/((TipBias*1e-3/Current)-SeriesResistance))/K_G0
	//[NEWDAQ-REMOVED: Keithley] endif
     if (Conductance > ConductanceThreshold)
//		print "Tip and substrate are in contact at start of MakeContact"
//		print "Attempting to break contacts..."
		print "Moving out in steps of "+num2str(-RetractionStep)+" nm"
		
		// Try to move them apart until contact is broken
		do  
			if (DCOffset_nm/K_ZPiezoScale<=PiezoChanLow||DCOffset_nm/K_ZPiezoScale>=PiezoChanHigh)
				print "Could not separate contacts"
				print "Piezo overextended, voltage= "+num2str(DCOffset_nm/K_ZPiezoScale)
				return -3
			endif
			
			keys= GetKeyState(0)
			if(keys==2)
				return -1
			endif
			
			WriteToHighRes(RetractionStep,TipBias)	// Move out one (big) step
	//		Print "Moved out 1 step"
			
			// Make new current measurement
			MXStartTask(G_ID1)
			MXReadAnalogF64(G_ID1,10,K_NumAIChans,ContactCheckWave)	// [NEWDAQ]
			MXStopTask(G_ID1)
	
		 	VolHighResIn= ContactCheckWave[p]
			CurHighResIn= ContactCheckWave[p + ReadWaveSize]
	
			Current= (Mean(CurHighResIn))*10^(-CurrentVoltGain)	
			Voltage= (Mean(VolHighResIn)) // in Volts
		
			//[NEWDAQ-REMOVED: Keithley] if (KeithleyBiasEnabled==0)
			Conductance= (Abs(Current)/Abs(Voltage))/K_G0	// [NEWDAQ] in units of G0; DAQ-bias formula only
			//[NEWDAQ-REMOVED: Keithley] else
				//[NEWDAQ-REMOVED: Keithley] Conductance=(1/((TipBias*1e-3/Current)-SeriesResistance))/K_G0
			//[NEWDAQ-REMOVED: Keithley] endif
           
             while(Conductance > NoiseThreshold)

//		print "Successfully broke contacts. Moving on."
		
	EndIf
	
	// Now push tip and substrate together until contact is made
	do
		if (DCOffset_nm/K_ZPiezoScale >= PiezoChanHigh||DCOffset_nm/K_ZPiezoScale <= PiezoChanLow)
			print "Could not make contact"
			print "Piezo overextended, voltage= "+num2str(DCOffset_nm/K_ZPiezoScale)	
			return -2
		endif

		keys= GetKeyState(0)
		if(keys==2)
			return -1
		endif
		
		WriteToHighRes(ApproachStepSize,TipBias)		// move tip in one (little) step
             
		// Make new conductance measurement
		MXStartTask(G_ID1)
		MXReadAnalogF64(G_ID1,10,K_NumAIChans,ContactCheckWave)	// [NEWDAQ]
		MXStopTask(G_ID1)
		
		VolHighResIn= ContactCheckWave[p]
		CurHighResIn= ContactCheckWave[p + ReadWaveSize]
	
		Current= (Mean(CurHighResIn))*10^(-CurrentVoltGain)	
		Voltage= (Mean(VolHighResIn)) // in Volts
	
		//[NEWDAQ-REMOVED: Keithley] if (KeithleyBiasEnabled==0)
		Conductance= (Abs(Current)/Abs(Voltage))/K_G0	// [NEWDAQ] in units of G0; DAQ-bias formula only
		//[NEWDAQ-REMOVED: Keithley] else
			//[NEWDAQ-REMOVED: Keithley] Conductance=(1/((TipBias*1e-3/Current)-SeriesResistance*.99))/K_G0
		//[NEWDAQ-REMOVED: Keithley] endif
		
//		Print "current= ", Current, "voltage= ", Voltage, "cond= ", Conductance
	 
	      
		while (Conductance < ConductanceThreshold)
		
	return 1
End

// Function SmashFun()
// 
// Smashes tip when G_PullOutAttempt is a multiple of the smashing frequency
// 
Function SmashFun()
	NVAR PullOutAttempt= G_PullOutAttempt
	NVAR SmashNum= G_SmashFrequency
	NVAR SmashInSteps= G_SmashInSteps
	NVAR SmashOutSteps= G_SmashOutSteps
	NVAR TipBias= G_TipBias
	
	if (mod(PullOutAttempt,SmashNum)==0)
		WriteToHighRes(SmashInSteps,TipBias)
		WriteToHighRes(SmashOutSteps,TipBias)
		Print "Smashed Tip"
	endif
End


// Creates 2 waves for writing to the NI USB-6453:	// [NEWDAQ] was: NI PXI-4461
//
// PiezoBiasWave: 	The wave of voltages sent to piezo
// JunctionBiasWave: 	The wave of voltages applied across junction
///
// Four modes implemented: Push/Pull, IV, AC, and constant. Mode is selected 
// by the user from GUI-based on CheckBox controls.

Function CreateInputs()
	Wave PiezoBiasWave
	Wave JunctionBiasWave	
	NVAR AcquisitionRate= G_AcquisitionRate
	NVAR ExcursionRate= G_PullOutRate// in nm/s
	NVAR Size= G_PseudoTotalLength_nm
	NVAR TipBias= G_TipBias
	NVAR NumPtsInAppliedWaves= G_NumPtsInAppliedWaves		// Number of points in both PiezoBiasWave and JunctionBiasWave
	
	// Alignment spike variables
	NVAR startLevel= G_startLevel					// voltage of spike
	NVAR endLevel= G_endLevel					// voltage before and after spike
	NVAR PulseFrontEdgePt= G_PulseFrontEdgePt	// point at endLevel volts just before spike
	NVAR PulseBackEdgePt= G_PulseBackEdgePt	// point at startLevel volts just after spike

	// Flags for Data Saving
	NVAR CurrentSaveCheck= G_CurrentSaveCheck
	NVAR BiasSave= G_BiasSaveCheck	

	// PushPull Variables
	NVAR PushPullCheck= G_PushPullCheck
	NVAR InitialPullLength= G_InitialPullLength
	NVAR FinalPullLength= G_FinalPullLength
	NVAR PushPullLength= G_PushPullLength
	NVAR HoldLength= G_HoldLength
	NVAR NumPushPullCycles= G_NumPushPullCycles
	
	// IV Variables
	NVAR IVCheck= G_IVCheck
	NVAR IVSign=G_IVSignFlag
	NVAR IVMaxBias= G_IVMaxBias
	NVAR IVInitPull= G_IVInitPull
	NVAR IVFinPull= G_IVFinPull
	NVAR IVCapLength= G_IVCapLength
	NVAR IVRampLength= G_IVRampLength	
	
	// AC Hold variables
	NVAR ACHoldCheck= G_ACHoldCheck
	NVAR ACInitPullLength= G_ACInitPullLength
	NVAR ACFinPullLength= G_ACFinPullLength
	NVAR ACHoldLength= G_ACHoldLength
	NVAR ACAmp= G_ACAmp
	NVAR ACFreq= G_ACFreq
	NVAR ACCapLength= G_ACCapLength
	
	// HB Hold variables
	NVAR HBHoldCheck= G_HBHoldCheck
	NVAR HBInitPullLength= G_HBInitPullLength
	NVAR HBFinPullLength= G_HBFinPullLength
	NVAR HBHoldLength= G_HBHoldLength
	NVAR HBBias= G_HBBias
	NVAR HBCapLengthIN= G_HBCapLengthIN
	NVAR HBCapLengthFIN= G_HBCapLengthFIN
	NVAR Vzero= G_Vzero
	
	if (PushPullCheck+IVCheck+ACHoldCheck+HBHoldCheck>1)
		Print "Ramp options not designed for simultaneous use"
		return -1
	endif
	
	Variable DeltaEx=ExcursionRate/K_ZPiezoScale/AcquisitionRate
	Variable PulseMidPt
	
	if (PushPullCheck==1)
		Variable NumInitialPullPoints=round(InitialPullLength/ExcursionRate*AcquisitionRate)
		Variable NumPushPullPoints=round(PushPullLength/ExcursionRate*AcquisitionRate)
		Variable NumHoldPoints= round(HoldLength/ExcursionRate*AcquisitionRate)
		Variable NumEndingPoints= round(FinalPullLength/ExcursionRate*AcquisitionRate)
		
		Size=InitialPullLength+NumPushPullCycles*2*(PushPullLength+HoldLength)+FinalPullLength
		NumPtsInAppliedWaves= NumInitialPullPoints+NumPushPullCycles*2*(NumPushPullPoints+NumHoldPoints)+NumEndingPoints
		
		Redimension/N=(NumPtsInAppliedWaves) PiezoBiasWave
		
		Variable index0= NumInitialPullPoints			// Starting index for first Push/Pull cycle		
		PiezoBiasWave[0,index0-1]=-p*DeltaEx
		
		Variable k, index1, index2, index3, index4
		for (k=0;k<NumPushPullCycles;k+=1)

			index1=	index0+NumHoldPoints 		// Index at end of first hold in cycle
			index2=	index1+NumPushPullPoints	// Index at end of push in cycle
			index3=	index2+NumHoldPoints 		// Index at end of second hold cycle
			index4=	index3+NumPushPullPoints	// Index at end of push in cycle
			
			PiezoBiasWave[index0,index1-1]= PiezoBiasWave[index0-1]
			PiezoBiasWave[index1,index2-1]= PiezoBiasWave[index0-1]+(p-index1)*DeltaEx
			PiezoBiasWave[index2,index3-1]= PiezoBiasWave[index2-1]
			PiezoBiasWave[index3,index4-1]= PiezoBiasWave[index2-1]-(p-index3)*DeltaEx
			
			index0= index4
			
		endfor
		
		PiezoBiasWave[index4,NumPtsInAppliedWaves-1]= PiezoBiasWave[index4-1]-(p-index4)*DeltaEx
			
		Redimension/N=(NumPtsInAppliedWaves) JunctionBiasWave
		JunctionBiasWave = -(TipBias/1000)
	
	elseif (IVCheck==1)
		BiasSave=1
		CurrentSaveCheck=1
		
		Variable NumIVInitialPullPoints= round(IVInitPull/ExcursionRate*AcquisitionRate)
		Variable NumIVCapPoints= round(IVCapLength/ExcursionRate*AcquisitionRate)
		Variable NumIVRampPoints= round(IVRampLength/ExcursionRate*AcquisitionRate)
		Variable NumIVFinalPullPoints= round(IVFinPull/ExcursionRate*AcquisitionRate)
	
		Size= IVInitPull+IVCapLength+IVRampLength+IVCapLength+IVFinPull
		NumPtsInAppliedWaves= NumIVInitialPullPoints+NumIVCapPoints+NumIVRampPoints+NumIVCapPoints+NumIVFinalPullPoints
		Redimension/N=(NumPtsInAppliedWaves) PiezoBiasWave
		
		Variable IVindex1= NumIVInitialPullPoints
		Variable IVindex2= IVindex1+NumIVCapPoints
		Variable IVindex3= IVindex2+NumIVRampPoints
		Variable IVindex4= IVindex3+NumIVCapPoints
		Variable IVindex5= IVindex4+NumIVFinalPullPoints
		
		PiezoBiasWave[0,IVindex1-1]= -p*DeltaEx
		PiezoBiasWave[IVindex1,IVindex4-1]= PiezoBiasWave[IVindex1-1]
		PiezoBiasWave[IVindex4,IVindex5]= -(p-2*NumIVCapPoints+-NumIVRampPoints)*DeltaEx
		
		Variable BiasIndex1= IVindex2
		Variable BiasIndex2= IVindex2+(NumIVRampPoints/4)
		Variable BiasIndex3= IVindex3-(NumIVRampPoints/4)
		Variable BiasIndex4= IVindex3
		
		// Bias ramp
		Redimension/N=(NumPtsInAppliedWaves) JunctionBiasWave
		JunctionBiasWave= (TipBias/1000)
		Variable DelBias= 4*IVMaxBias/NumIVRampPoints
		JunctionBiasWave[BiasIndex1,BiasIndex2-1]= (p-NumIVInitialPullPoints-NumIVCapPoints)*DelBias
		JunctionBiasWave[BiasIndex2,BiasIndex3-1]= IVMaxBias-(p-NumIVInitialPullPoints-NumIVCapPoints-NumIVRampPoints/4)*DelBias
		JunctionBiasWave[BiasIndex3,BiasIndex4]= -IVMaxBias+(p-NumIVInitialPullPoints-NumIVCapPoints-3*NumIVRampPoints/4)*DelBias
		
		JunctionBiasWave*= -1 // To have normal convention???
		
		if (IVSign==1)	// If IVSign==1, the ramp goes 'negative' first
			JunctionBiasWave[BiasIndex1,BiasIndex4]*= -1
		endif

	elseif (ACHoldCheck==1)
		BiasSave=1
		Variable NumACInitialPullPoints= round(ACInitPullLength/ExcursionRate*AcquisitionRate)
		Variable NumACCapPoints= round(ACCapLength/ExcursionRate*AcquisitionRate)
		Variable NumACHoldPoints= round(ACHoldLength/ExcursionRate*AcquisitionRate)
		Variable NumACFinalPullPoints= round(ACFinPullLength/ExcursionRate*AcquisitionRate)		
		
		Size= ACInitPullLength+2*ACCapLength+ACHoldLength+ACFinPullLength	// nm
		NumPtsInAppliedWaves= NumACInitialPullPoints+2*NumACCapPoints+NumACHoldPoints+NumACFinalPullPoints
		Redimension/N=(NumPtsInAppliedWaves) PiezoBiasWave
		
		Variable ACindex1= NumACInitialPullPoints
		Variable ACindex2= ACindex1+NumACCapPoints
		Variable ACindex3= ACindex2+NumACHoldPoints
		Variable ACindex4= ACindex3+NumACCapPoints
		Variable ACindex5= ACindex4+NumACFinalPullPoints
		
		// Piezo
		PiezoBiasWave[0,ACindex1-1]= -p*DeltaEx
		PiezoBiasWave[ACindex1,ACindex4-1]= PiezoBiasWave[ACindex1-1]
		PiezoBiasWave[ACindex4,ACindex5-1]= -(p-2*NumACCapPoints-NumACHoldPoints)*DeltaEx
		
		// Bias
		Redimension/N=(NumPtsInAppliedWaves) JunctionBiasWave
		JunctionBiasWave= -(TipBias)/1000
		JunctionBiasWave[ACindex2,ACindex3-1]=ACAmp*sin(2*pi*ACFreq*1000*(p-ACindex2)/AcquisitionRate)
	
	elseif (HBHoldCheck==1)
		BiasSave=1
		Variable NumHBInitialPullPoints= round(HBInitPullLength/ExcursionRate*AcquisitionRate)
		Variable NumHBCapPointsIN= round(HBCapLengthIN/ExcursionRate*AcquisitionRate)
		Variable NumHBCapPointsFIN= round(HBCapLengthFIN/ExcursionRate*AcquisitionRate)
		Variable NumHBHoldPoints= round(HBHoldLength/ExcursionRate*AcquisitionRate)
		Variable NumHBFinalPullPoints= round(HBFinPullLength/ExcursionRate*AcquisitionRate)		
		
		Size= HBInitPullLength+ (HBCapLengthIN + HBCapLengthFIN) +HBHoldLength+HBFinPullLength	// nm
		NumPtsInAppliedWaves= NumHBInitialPullPoints+ (NumHBCapPointsIN + NumHBCapPointsFIN) +NumHBHoldPoints+NumHBFinalPullPoints
		Redimension/N=(NumPtsInAppliedWaves) PiezoBiasWave
		
		Variable HBindex1= NumHBInitialPullPoints
		Variable HBindex2= HBindex1+NumHBCapPointsIN
		Variable HBindex3= HBindex2+NumHBHoldPoints
		Variable HBindex4= HBindex3+NumHBCapPointsFIN
		Variable HBindex5= HBindex4+NumHBFinalPullPoints
		
		// Piezo
		PiezoBiasWave[0,HBindex1-1]= -p*DeltaEx
		PiezoBiasWave[HBindex1,HBindex4-1]= PiezoBiasWave[HBindex1-1]
		PiezoBiasWave[HBindex4,HBindex5-1]= -(p - (NumHBCapPointsIN + NumHBCapPointsFIN) -NumHBHoldPoints)*DeltaEx
		
		// Bias
		Redimension/N=(NumPtsInAppliedWaves) JunctionBiasWave
		JunctionBiasWave= -(TipBias)/1000					// TipBias is in millivolts!
		JunctionBiasWave[HBindex2,HBindex3-1]=-HBBias
		
		// checks if voltage offset is being calculated
		ControlInfo/W=Voltage_Offset VzeroCheckBox
		if(V_Value==1)
			HBBias= Vzero/1000 // in V, to be displayed in HBHold Tab. 
			JunctionBiasWave[HBindex2,HBindex3-1]=-HBBias
		endif
		
	else  // make applied bias constant at TipBias millivolts
	
		NumPtsInAppliedWaves = round(Size/ExcursionRate*AcquisitionRate)
		Redimension/N=(NumPtsInAppliedWaves) PiezoBiasWave		
		PiezoBiasWave[0,NumPtsInAppliedWaves-1]=-p*DeltaEx // pull out at constant rate
		
		Redimension/N=(NumPtsInAppliedWaves) JunctionBiasWave
		// checks if voltage offset is being calculated
		ControlInfo/W=Voltage_Offset VzeroCheckBox
		if(V_Value==1)
			JunctionBiasWave = -(TipBias + Vzero)/1000
		else 
			JunctionBiasWave = -(TipBias/1000)
		endif		

	endif

	// Front edge is 7.5 msec before end of trace. This is point just before spike.
	PulseFrontEdgePt= NumPtsInAppliedWaves-round(7.5e-3*AcquisitionRate)-1

	// Back edge is 2.5 msec before end of trace. This is point just after spike.
	PulseBackEdgePt= NumPtsInAppliedWaves-round(2.5e-3*AcquisitionRate)+1

	// Mid point is 5 msec before end of trace
	PulseMidPt= NumPtsInAppliedWaves-round(5e-3*AcquisitionRate)

	endLevel= JunctionBiasWave[NumPtsInAppliedWaves-PulseMidPt]
	startLevel= -sign(JunctionBiasWave[NumPtsInAppliedWaves-PulseMidPt])
	
	// Alignment spike (5 msec long)
	JunctionBiasWave[PulseFrontEdgePt+1,PulseBackEdgePt-1]= (TipBias/1000)

End

// Makes single PullOutAttempt
// If MakeContact returns -2 or -3, the piezo is overextended and the experiment will terminate
Function SingleBreakJunctionAttempt()
	NVAR PullOutAttempt= G_PullOutAttempt
	
	Variable MakeContactReturnVal
	
	PullOutAttempt+=1
	
	MakeContactReturnVal=HighResMakeContact()
	
	if (MakeContactReturnVal==1)
		if (GenerateTrace()==1)
			if(TestTrace()==1)
				// Save Offset Voltage and Current if VzeroCheckBox is checked. 
				SaveOffset()
				SavePullOut()
				// Updates JunctionBias wave with new Vzero. 
				CreateInputs()
			endif
		endif
	elseif (MakeContactReturnVal<-1)
		return -1
	endif
	
End

// Similar to old Go_PullOut function
// Displays the main algorithmic logic of the experiment
Function MeasureBreakJunctions()
	NVAR PullOutNumber= G_PullOutNumber
	NVAR StopNumber= G_StopNumber
	NVAR PullOutAttempt= G_PullOutAttempt
	NVAR SingleAttemptFlag= G_SingleAttemptFlag
	
	Variable keys
	
	if (PullOutNumber>=StopNumber)
		return 0
	endif
	
	CreateInputs()	// Makes waves for applied bias and piezo
	
	// Sets up G_ID1 Task FOR BOTH VOLTAGE AND CURRENT READING
	// BY HIGH-RES CARD IN MAKE CONTACT, GENERATE TRACE
	// AND VOLTAGE OFFSET ESTIMATE. 
	// [NEWDAQ] G_ID1 also carries the piezo sense channel now (one card, 3 channels).
	SetUpHRTaskID1()
	
	//[NEWDAQ-REMOVED: LowRes] // LowRes card reads 3 channels: Piezo voltage in and Thermocouple voltages
	//[NEWDAQ-REMOVED: LowRes] SetUpLRTaskID3()
	
		do	// Generate desired data
	
			SmashFun()
	
			if (SingleBreakJunctionAttempt()==-1)
				ClearHRTaskID1()
				//[NEWDAQ-REMOVED: LowRes] ClearLRTaskID3()
				return -1
			endif
	
			// Gives user ability to abort loop by pushing 'Alt' button
			keys= GetKeyState(0)
			if(keys==2)
				ClearHRTaskID1()
				//[NEWDAQ-REMOVED: LowRes] ClearLRTaskID3()
				return 0
			endif
		
			// If this happens, something is definitely wrong
			if (PullOutAttempt>=100000)
				ClearHRTaskID1()
				//[NEWDAQ-REMOVED: LowRes] ClearLRTaskID3()
				Print "Catastrophic failure"
				return 0
			endif

			if (SingleAttemptFlag==1)
				return 0
			endif

             while (PullOutNumber<StopNumber)	// keep iterating until all the desired traces are created

	ClearHRTaskID1()
	//[NEWDAQ-REMOVED: LowRes] ClearLRTaskID3()

End

// [NEWDAQ] was: coarse approach that stepped the NanoPZ actuator closer until |I| > 0.1 uA
// (after each 2-channel read of G_ID1 it called StepActuatorCloser over the serial port and
// counted the steps in G_ActuatorCounter; the Z piezo itself was not moved).
//
// Fine approach with the Z piezo only. The coarse stage is moved BY HAND in this version.
// Steps the piezo toward the sample by G_MakeContactApproachStepSize nm per step and reads
// the current after each step (3-channel read of G_ID1, ReadWaveSize samples per channel).
// Stops when |I| >= 0.1 uA (same stop level the old actuator loop used), or when the piezo
// voltage would leave [G_PiezoChanLow, G_PiezoChanHigh], or on the Alt key.
// At the limit it prints: "Approach: piezo at its limit with no contact. Move the coarse stage
// closer BY HAND (a fraction of a turn), then press Start Approach again."
Function HighResCardApproach()
	Wave HighResReadWave
	Wave VolHighResIn, CurHighResIn

	NVAR G_ID1= G_ID1
	NVAR AcquisitionRate= G_AcquisitionRate
	NVAR ReadWaveSize= G_FastReadWaveSize

	NVAR Actual_Current= G_CurrentSamplingReadoutVal
	NVAR CurrentVoltConversion= G_CurrentVoltConversion

	NVAR TipBias= G_TipBias
	NVAR DCOffset_nm= G_PiezoOffset_nm
	NVAR ApproachStepSize= G_MakeContactApproachStepSize	// nm per piezo step (replaces the actuator step)
	NVAR PiezoChanHigh= G_PiezoChanHigh
	NVAR PiezoChanLow= G_PiezoChanLow
	SVAR HighResOutputTaskStatus= G_HighResOutputTaskStatus	// the piezo is moved through the writing task G_OD1

	Variable keys
	Variable StepCount= 0
	Variable NextPiezoVolt
	Variable StartOffset_nm= DCOffset_nm	// [NEWDAQ] where this approach started; the piezo goes back there if no surface is found
	Variable HighResReadWaveSize= ReadWaveSize * K_NumAIChans	// 3 channel blocks

	// WriteToHighRes() swallows DAQ errors, so without the writing task this loop would advance
	// G_PiezoOffset_nm without moving the piezo. Refuse to start instead (nothing to clear yet).
	if (!StringMatch(HighResOutputTaskStatus,"ON"))
		Print "Approach: start the DAQ writing task first (the piezo is driven through it)."
		return -1
	endif

	Redimension/D/N=(HighResReadWaveSize) HighResReadWave
	Redimension/D/N=(ReadWaveSize) CurHighResIn, VolHighResIn

	SetUpHRTaskID1()
	MXCfgSampClkTiming(G_ID1,AcquisitionRate,1,ReadWaveSize*2)	// per-channel buffer with 2x headroom (same N as before)

	Actual_Current=0
	Print "Approach: stepping the piezo in by "+num2str(ApproachStepSize)+" nm per step; Alt stops."

	Do
		keys= GetKeyState(0)
		if(keys==2)
			Print "Approach: stopped by the user (Alt key)."
			ClearHRTaskID1()
			break
		endif

		//++++++++++++++++++++++++++++++++++++++++++++++++++++++
		// If sampleMode= 1, MXStopTask after calling the MXRead function is
		// REQUIRED for stopping the reading operation. Without MXStopTask,
		// the reading operation will not be stopped and an error message will appear.
		MXStartTask(G_ID1)
		MXReadAnalogF64(G_ID1,10,K_NumAIChans,HighResReadWave)
		MXStopTask(G_ID1)
		//++++++++++++++++++++++++++++++++++++++++++++++++++++++

		VolHighResIn= HighResReadWave[p]
		CurHighResIn= HighResReadWave[p + ReadWaveSize]
		// block 2 (piezo sense) is read with the task but is not needed here

		Actual_Current = Mean(CurHighResIn)*CurrentVoltConversion	// in microamps
		if (mod(StepCount,20)==0)
			Print "Approach: step ", StepCount, " piezo (V)= ", DCOffset_nm/K_ZPiezoScale, " current (uA)= ", Actual_Current, " voltage (V)= ", Mean(VolHighResIn)
		endif

		if(abs(Actual_Current)>=.1)
			Print "Approach: contact found, |I| >= 0.1 uA at piezo (V)= "+num2str(DCOffset_nm/K_ZPiezoScale)
			ClearHRTaskID1()
			break
		endif

		// the next step must stay inside the output range of the piezo channel
		NextPiezoVolt= (DCOffset_nm + ApproachStepSize)/K_ZPiezoScale
		if (NextPiezoVolt >= PiezoChanHigh || NextPiezoVolt <= PiezoChanLow)
			Print "Approach: piezo at its limit ("+num2str(DCOffset_nm/K_ZPiezoScale)+" V) with no contact."
			// [NEWDAQ] retract to where this approach started BEFORE the coarse stage is moved by hand; otherwise the
			// [NEWDAQ] piezo would stay fully extended and the next Start Approach could not step anywhere
			WriteToHighRes(StartOffset_nm-DCOffset_nm,TipBias)
			Print "Approach: piezo retracted to "+num2str(DCOffset_nm/K_ZPiezoScale)+" V. Move the coarse stage closer BY HAND (a fraction of a turn), then press Start Approach again."
			ClearHRTaskID1()
			break
		endif

		WriteToHighRes(ApproachStepSize,TipBias)	// one piezo step toward the sample
		StepCount+=1
		DoUpdate
	While(1)

end

//[NEWDAQ-REMOVED: LowRes] Function GetLowHighOffset(CurrentIn, CurrentInLowRes)
	//[NEWDAQ-REMOVED: LowRes] Wave CurrentIn, CurrentInLowRes
	//[NEWDAQ-REMOVED: LowRes] Variable  BestDelta, BestDiff, i
//[NEWDAQ-REMOVED: LowRes]
	//[NEWDAQ-REMOVED: LowRes] Duplicate/O CurrentIn TestWave
	//[NEWDAQ-REMOVED: LowRes] Variable NumPts=NumPnts(TestWave), Diff
	//[NEWDAQ-REMOVED: LowRes]
//[NEWDAQ-REMOVED: LowRes] //	print "test 1"
	//[NEWDAQ-REMOVED: LowRes] BestDelta=1000
	//[NEWDAQ-REMOVED: LowRes] BestDiff=5000
	//[NEWDAQ-REMOVED: LowRes] For (i=-1000;i<1000;i+=100)
		//[NEWDAQ-REMOVED: LowRes] TestWave=(CurrentInLowRes-CurrentIn[p-i])^2
		//[NEWDAQ-REMOVED: LowRes] Diff= Sum(TestWave)
//[NEWDAQ-REMOVED: LowRes] //		print diff, i
//[NEWDAQ-REMOVED: LowRes]
		//[NEWDAQ-REMOVED: LowRes] if (Diff < BestDiff)
			//[NEWDAQ-REMOVED: LowRes] BestDiff=Diff
			//[NEWDAQ-REMOVED: LowRes] BestDelta=i
		//[NEWDAQ-REMOVED: LowRes] endif
	//[NEWDAQ-REMOVED: LowRes] endfor
//[NEWDAQ-REMOVED: LowRes]
//[NEWDAQ-REMOVED: LowRes] //	print "test 2"
	//[NEWDAQ-REMOVED: LowRes] For (i=BestDelta-100;i<BestDelta+100;i+=10)
		//[NEWDAQ-REMOVED: LowRes] TestWave=(CurrentInLowRes-CurrentIn[p-i])^2
		//[NEWDAQ-REMOVED: LowRes] Diff= Sum(TestWave)
//[NEWDAQ-REMOVED: LowRes] //		print diff, i
//[NEWDAQ-REMOVED: LowRes]
		//[NEWDAQ-REMOVED: LowRes] if (Diff < BestDiff)
			//[NEWDAQ-REMOVED: LowRes] BestDiff=Diff
			//[NEWDAQ-REMOVED: LowRes] BestDelta=i
		//[NEWDAQ-REMOVED: LowRes] endif
	//[NEWDAQ-REMOVED: LowRes] endfor
//[NEWDAQ-REMOVED: LowRes]
//[NEWDAQ-REMOVED: LowRes] //	print "test 3"
	//[NEWDAQ-REMOVED: LowRes] For (i=BestDelta-10;i<BestDelta+10;i+=1)
		//[NEWDAQ-REMOVED: LowRes] TestWave=(CurrentInLowRes-CurrentIn[p-i])^2
		//[NEWDAQ-REMOVED: LowRes] Diff= Sum(TestWave)
//[NEWDAQ-REMOVED: LowRes] //		print diff, i
//[NEWDAQ-REMOVED: LowRes]
		//[NEWDAQ-REMOVED: LowRes] if (Diff < BestDiff)
			//[NEWDAQ-REMOVED: LowRes] BestDiff=Diff
			//[NEWDAQ-REMOVED: LowRes] BestDelta=i
		//[NEWDAQ-REMOVED: LowRes] endif
	//[NEWDAQ-REMOVED: LowRes] endfor
	//[NEWDAQ-REMOVED: LowRes]
//[NEWDAQ-REMOVED: LowRes] //	print "best delta= ", BestDelta
//[NEWDAQ-REMOVED: LowRes] //	print "best diff= ", BestDiff
	//[NEWDAQ-REMOVED: LowRes]
	//[NEWDAQ-REMOVED: LowRes] return BestDelta
	//[NEWDAQ-REMOVED: LowRes]
//[NEWDAQ-REMOVED: LowRes] end
