#pragma TextEncoding = "UTF-8"
////////////////////////////////////////////////////////////////////////////////
// ALL STM-BJ Button control functions
////////////////////////////////////////////////////////////////////////////////
// ---------------------------------------------------------------------------
// [NEWDAQ] Ported 2026-10-22 for ONE NI USB-6453 (Dev1), no Keithley GPIB control,
// no coarse actuator. See PORTING_SPEC.md and README.md in this folder.
// ---------------------------------------------------------------------------

// There is a basic correspondence between control functions and operations 
// available in the panel. These control functions mostly just call other functions. 
// Button starts experiment

Function StartMeasurement(ctrlName) : ButtonControl
	String ctrlName
	NVAR SingleAttemptFlag= G_SingleAttemptFlag
	SingleAttemptFlag= 0
	
	StopBkgdSampling()
	
	MeasureBreakJunctions()
	
	StartBkgdSampling()
End

// Button makes single attempt at generating a trace

Function MakeAttempt(ctrlName) : ButtonControl
	String ctrlName
	NVAR SingleAttemptFlag= G_SingleAttemptFlag
	SingleAttemptFlag= 1
	
	StopBkgdSampling()

	MeasureBreakJunctions()
	
	StartBkgdSampling()
End

// Called when tabs are clicked. The essential requirement is that the
// names of the controls be terminated with identifying endings so that
// they can be sorted using a grep. See ModifyControlList, page V-409

Function MainWindowTabProc(ctrlName,tabNum) : TabControl
	String ctrlName
	Variable tabNum

	NVAR SubTabNum= G_SubTabNum
	
	String DAQControls= ControlNameList("",";","*DAQ")
	String InputParamControls= ControlNameList("",";","*Inputs")
	String RampOptions= ControlNameList("",";","*Ramps")
	
	if (tabNum==0)	// DAQ On
		ModifyControlList InputParamControls disable=1
		ModifyControlList RampOptions disable=1
		ModifyControlList DAQControls disable=0
	elseif (tabNum==1)	// Inputs
		ModifyControlList DAQControls disable=1
		ModifyControlList RampOptions disable=1
		ModifyControlList InputParamControls disable=0
	elseif (tabNum==2)	// Ramps
		ModifyControlList DAQControls disable=1
		ModifyControlList InputParamControls disable=1
		//		ModifyControlList RampOptions disable=0
		ModifyControl RampSubTabs_Ramps disable=0
		SubWindowTabProc("",SubTabNum)
	endif

End

// Called when the nested tabs for the different ramp options are clicked. 
// Names of the controls in the sub tab must be terminated with identifying
// that point to both the correct parent tab ("Ramps") as well as the correct
// sub tab. A global variable, G_SubTabNum, is used to store the last
// viewed sub tab and return the view to this sub tab when the parent 
// tab is clicked. See ModifyControlList, page V-409

Function SubWindowTabProc(ctrlName,tabNum) : TabControl
	String ctrlName
	Variable tabNum
	
	NVAR SubTabNum= G_SubTabNum
	SubTabNum= tabNum
	
	String PushPullControls= ControlNameList("",";","*PushPullRamps")
	String IVControls= ControlNameList("",";","*IVRamps")
	String ACHoldOptions= ControlNameList("",";","*ACHoldRamps")
	String HBHoldOptions= ControlNameList("",";","*HBHoldRamps")
	
	if (tabNum==0)	// PushPull
		ModifyControlList IVControls disable=1
		ModifyControlList ACHoldOptions disable=1
		ModifyControlList HBHoldOptions disable=1
		ModifyControlList PushPullControls disable=0
	elseif (tabNum==1)	// IV
		ModifyControlList PushPullControls disable=1
		ModifyControlList ACHoldOptions disable=1
		ModifyControlList HBHoldOptions disable=1
		ModifyControlList IVControls disable=0
	elseif (tabNum==2)	// AC Hold
		ModifyControlList PushPullControls disable=1
		ModifyControlList IVControls disable=1
		ModifyControlList HBHoldOptions disable=1
		ModifyControlList ACHoldOptions disable=0
	elseif (tabNum==3)
		ModifyControlList PushPullControls disable=1
		ModifyControlList IVControls disable=1
		ModifyControlList ACHoldOptions disable=1
		ModifyControlList HBHoldOptions disable=0
	endif

End

//[NEWDAQ-REMOVED: Keithley] Function CurrentSuppressCheckProc(ctrlName,checked) : CheckBoxControl
//[NEWDAQ-REMOVED: Keithley] 	String ctrlName
//[NEWDAQ-REMOVED: Keithley] 	Variable checked
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] 	NVAR BoardUD=G_BoardUD
//[NEWDAQ-REMOVED: Keithley] 	NVAR DeviceUD=G_DeviceUD
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 board=BoardUD
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 device=DeviceUD
//[NEWDAQ-REMOVED: Keithley] 	if(checked==0)
//[NEWDAQ-REMOVED: Keithley] 		GPIBWrite2 "N0X"
//[NEWDAQ-REMOVED: Keithley] 	else
//[NEWDAQ-REMOVED: Keithley] 		GPIBWrite2 "N1X"
//[NEWDAQ-REMOVED: Keithley] 	endif
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] End

Function StartHighResWritingTask(ctrlName) : ButtonControl
	String ctrlName
	
	Wave HighResWriteWave
	
	NVAR G_OD1= G_OD1
	NVAR rate= G_AcquisitionRate
	NVAR PiezoOffset_nm= G_PiezoOffset_nm
	NVAR CardTimeout= G_CardTimeout;
	NVAR WriteBufferSize= G_WriteBufferSize;
	NVAR TipBias= G_TipBias	//-(TipBias/1000)
	NVAR PiezoChanLow= G_PiezoChanLow
	NVAR PiezoChanHigh= G_PiezoChanHigh
	NVAR HighResOutputRange= G_HighResOutputRange
	SVAR HighResOutputTaskStatus= G_HighResOutputTaskStatus
	
	Redimension/D/N=(WriteBufferSize*2) HighResWriteWave
	HighResWriteWave[0,WriteBufferSize-1]= PiezoOffset_nm/K_ZPiezoScale;
	HighResWriteWave[WriteBufferSize,2*WriteBufferSize-1]= -(TipBias/1000)

	Variable HighResOutputRange_1 = HighResOutputRange
	Variable HighResOutputRange_2 = -HighResOutputRange

	// Output Commands
	MXCreateTask("G_OD1")
	MXCreateAOVoltageChan(G_OD1,HighResPiezoOut,PiezoChanLow,PiezoChanHigh)
	MXCreateAOVoltageChan(G_OD1,HighResBiasOut, HighResOutputRange_2,HighResOutputRange_1)
	MXCfgSampClkTiming(G_OD1,rate,1,WriteBufferSize)
	MXWriteAnalogF64(G_OD1,CardTimeout,2,HighResWriteWave)
	MXStartTask(G_OD1)

	DoWindow/F Current_Measurement
	Button Start_DAQ disable=2
	Button Reset_DAQ disable=2
	Button Stop_DAQ disable=0
	Slider SliderPos_Z win=BreakJunctionMeasurement, disable=0
	SetVariable WriteBufferSize_DAQ disable=2
	SetVariable ReadWaveSize_DAQ disable=2
	SetVariable AcqRate_DAQ disable=2
	CheckBox OnCheck disable=0
	
	HighResOutputTaskStatus= "ON"
	
End

Function StopWritingTasks(ctrlName) : ButtonControl
	String ctrlName
	
	NVAR G_OD1= G_OD1
	NVAR G_ID1= G_ID1
//[NEWDAQ-REMOVED: Keithley] 	NVAR BoardUD= G_BoardUD
//[NEWDAQ-REMOVED: Keithley] 	NVAR DeviceUD= G_DeviceUD
	NVAR DCOffset_nm= G_PiezoOffset_nm
	NVAR TipBias= G_TipBias
	NVAR CounterElectrodeBias= G_CounterElectrodeBias
	SVAR HighResOutputTaskStatus= G_HighResOutputTaskStatus
	
	StopBkgdSampling()

//[NEWDAQ-REMOVED: Keithley] 	// Turn zero check on?
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 board=BoardUD
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 device=DeviceUD
//[NEWDAQ-REMOVED: Keithley] 	GPIBWrite2 "C1X"

	If(StringMatch(HighResOutputTaskStatus,"ON"))
		// Zero Out bias applied to piezo
		WriteToHighRes(-DCOffset_nm,TipBias)
		// Stop Writing task
		MXStopTask(G_OD1)
		MXClearTask(G_OD1)
		HighResOutputTaskStatus= "OFF"
	EndIf
	
	// Best known way to close the EChem counter-electrode output task (G_OD2)	// [NEWDAQ] was: "close low res output channel"
	MXResetDevice(DAQDevice)	// [NEWDAQ] one card; also stops the EChem counter-electrode task
	Button StartEChemWriteButton win=EChem, disable=0
	SetVariable CounterElectrodeSetVar win=EChem, disable=2
	Button StartCVHighResButton win= EChem, disable= 0	// [NEWDAQ] one card: a CV is allowed exactly when the writing task is OFF, so Kill Tasks enables the CV buttons (was disable= 2)
	Button StartCVLowResButton win= EChem, disable= 0	// [NEWDAQ] (was disable= 2)
	
	// Bring main window into front for control operations
	DoWindow/F BreakJunctionMeasurement
		
	Button Start_DAQ disable=0
	Button Reset_DAQ disable=0
	Slider SliderPos_Z win=BreakJunctionMeasurement, disable=2
	SetVariable WriteBufferSize_DAQ disable=0
	SetVariable ReadWaveSize_DAQ disable=0
	SetVariable AcqRate_DAQ disable=0
	CheckBox OnCheck value=0, disable=2
//[NEWDAQ-REMOVED: Keithley] 	CheckBox ZeroCheckBox value=1

end

Function EChemResetDAQDevices(ctrlName) : ButtonControl
	String ctrlName
	NVAR CounterElectrodeBias= G_CounterElectrodeBias
	
	MXResetDevice(DAQDevice)	// [NEWDAQ] one card: this single reset replaces the Dev1 + Dev2 pair
//[NEWDAQ-REMOVED: LowRes] 	MXResetDevice("Dev2")

	CounterElectrodeBias= 0
	Button StartEChemWriteButton win=EChem, disable=0
	SetVariable CounterElectrodeSetVar win=EChem, disable=2

end

//Function HRWrite()
//	NVAR G_OD1= G_OD1
//
//	Wave HighResWriteWave
//	Wave BiasOutWave
//	NVAR AcquisitionRate= G_AcquisitionRate
//	NVAR CardTimeout= G_CardTimeout
//	
//	Variable  WriteBufferSize= 500
//	
//	Redimension/D/N=(WriteBufferSize) HighResWriteWave
//	Make/O/N=(WriteBufferSize) BiasOutWave
//	
//	HighResWriteWave= 0.3
//	
//	MXCreateTask("G_OD1")
//	MXCreateAOVoltageChan(G_OD1,HighResBiasOut,-2.5,2.5)
//	MXCfgSampClkTiming(G_OD1,AcquisitionRate,1,WriteBufferSize)
//	MXWriteAnalogF64(G_OD1,CardTimeout,1,HighResWriteWave)
//	MXStartTask(G_OD1)
//
////	BiasOutWave= HighResWriteWave
//
////	MXStopTask(G_OD1)
////	MXClearTask(G_OD1)
//
//End 

//[NEWDAQ-REMOVED: Keithley] Function ZeroCheckProc(ctrlName,checked) : CheckBoxControl
//[NEWDAQ-REMOVED: Keithley] 	String ctrlName
//[NEWDAQ-REMOVED: Keithley] 	Variable checked
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] 	NVAR BoardUD=G_BoardUD
//[NEWDAQ-REMOVED: Keithley] 	NVAR DeviceUD=G_DeviceUD
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 board=BoardUD
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 device=DeviceUD
//[NEWDAQ-REMOVED: Keithley] 	if(checked==0)
//[NEWDAQ-REMOVED: Keithley] 		GPIBWrite2 "C0X"	
//[NEWDAQ-REMOVED: Keithley] 	else
//[NEWDAQ-REMOVED: Keithley] 		GPIBWrite2 "C1X"
//[NEWDAQ-REMOVED: Keithley] 	endif
//[NEWDAQ-REMOVED: Keithley] End

//[NEWDAQ-REMOVED: Keithley] Function ZeroCorrectProc(ctrlName) : ButtonControl
//[NEWDAQ-REMOVED: Keithley] 	String ctrlName
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] 	NVAR BoardUD=G_BoardUD
//[NEWDAQ-REMOVED: Keithley] 	NVAR DeviceUD=G_DeviceUD
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 board=BoardUD
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 device=DeviceUD
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] // 	Reset Keithley
//[NEWDAQ-REMOVED: Keithley] 	execute "GPIBWrite2 \"C2X\""
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] End

Function SetGain(ctrlName,varNum,varStr,varName) : SetVariableControl
	String ctrlName
	Variable varNum
	String varStr
	String varName
	
	NVAR CurrentVoltConversion= G_CurrentVoltConversion
	NVAR CurrentVoltGain= G_CurrentVoltGain
	NVAR CurrentSuppress= G_CurrentSuppress // in MicroAmps
	NVAR CurrentSuppressConst= G_CurrentSuppressConst
	NVAR ConductanceThreshold= G_ConductanceThreshold
//[NEWDAQ-REMOVED: Keithley] 	NVAR BoardUD= G_BoardUD
//[NEWDAQ-REMOVED: Keithley] 	NVAR DeviceUD= G_DeviceUD
	
	CurrentVoltGain= varNum
	CurrentVoltConversion= 10^(6-CurrentVoltGain)
	CurrentSuppress=  CurrentSuppressConst*10^(3-CurrentVoltGain)
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 board= BoardUD
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 device= DeviceUD
//[NEWDAQ-REMOVED: Keithley] 	GPIBWrite2 "H6R"+num2str(CurrentVoltGain)+"X"
//[NEWDAQ-REMOVED: Keithley] 	GPIBWrite2 "H8S"+num2str(CurrentSuppress/1000000)+",0X"
	Print "Gain set to "+num2str(CurrentVoltGain)+" (software only: set the same gain on the amplifier front panel)"	// [NEWDAQ] no GPIB write; the amplifier gain is set by hand
	
	// For EChem measurements: enable button. 
	Button StartCVHighResButton win=EChem, disable=0
	Button StartCVLowResButton win=EChem, disable=0
end

Function BkgdSamplingCheckProc(ctrlName,checked) : CheckBoxControl
	String ctrlName
	Variable checked
		
	if(checked==1)
		StartBkgdSampling()
	elseif(checked==0)
		StopBkgdSampling()
	endif
End

//+++++++++++++++++++++++++++++++++++++++++++++++++++++++
// Check box for thermocouple readout. 
//Function ThermoCheckProc(ctrlName,checked) : CheckBoxControl
//	String ctrlName
//	Variable checked
//		
//	if(checked==1)
//		StartThermoSampling()
//	elseif(checked==0)
//		StopThermoSampling()
//	endif
//End
//+++++++++++++++++++++++++++++++++++++++++++++++++++++++

Function RampOptionsCheckProc(ctrlName,checkVar) : CheckBoxControl
	String ctrlName
	Variable checkVar
	
	NVAR IVCheck= G_IVCheck
	NVAR PushPullCheck= G_PushPullCheck
	NVAR ACHoldCheck= G_ACHoldCheck
	NVAR HBHoldCheck= G_HBHoldCheck
	
	if (GrepString(ctrlName,"IVCheck*")==1)
		IVCheck= checkVar
		PushPullCheck= 0
		ACHoldCheck= 0
		HBHoldCheck= 0
	elseif (GrepString(ctrlName,"PushPullCheck*")==1)
		PushPullCheck= checkVar
		IVCheck= 0
		ACHoldCheck= 0
		HBHoldCheck= 0
	elseif (GrepString(ctrlName,"ACHoldCheck*")==1)
		ACHoldCheck= checkVar
		PushPullCheck= 0
		IVCheck= 0
		HBHoldCheck= 0
	elseif (GrepString(ctrlName,"HBHoldCheck*")==1)
		HBHoldCheck= checkVar
		ACHoldCheck= 0
		PushPullCheck= 0
		IVCheck= 0
	endif

End

// The value of the slider is the applied voltage to the piezo-- NOT the distance caused by the voltage.
// This function sets the bias of the piezo to the value the slider is pointing at when the slider is clicked.
// Calls the function WriteToHighRes and sets the distance value of piezo to value*K_ZPiezoScale nm.

Function SetPiezoBiasFromSlider(name, value, event) : SliderControl			// slider sets Offset
	String name
	Variable value
	Variable event
	
	NVAR DCOffset_nm= G_PiezoOffset_nm
	NVAR TipBias= G_TipBias
	Variable deltaZ_nm= value*K_ZPiezoScale-DCOffset_nm
	
	WriteToHighRes(deltaZ_nm,TipBias)
	
End

// When 'opening' add a negative voltage increment
Function PiezoStepApart(ctrlName) : ButtonControl
	String ctrlName
	
	NVAR deltaZ_nm= G_PiezoDeltaZ_nm
	NVAR TipBias= G_TipBias
	
	WriteToHighRes(-deltaZ_nm,TipBias)
	
End

// When 'closing' add a positive voltage increment
Function PiezoStepCloser(ctrlName) : ButtonControl
	String ctrlName
	
	NVAR deltaZ_nm= G_PiezoDeltaZ_nm
	NVAR TipBias= G_TipBias
	
	WriteToHighRes(deltaZ_nm,TipBias)
	
End


Function SetTipBiasVoltage(ctrlName,varNum,varStr,varName) : SetVariableControl
	String ctrlName
	Variable varNum
	String varStr
	String varName
	
	NVAR TipBias = G_TipBias	//-(TipBias/1000)
//[NEWDAQ-REMOVED: Keithley] 	NVAR KeithleyBiasEnabled = G_KeithleyBiasEnabled
	
//[NEWDAQ-REMOVED: Keithley] 	if (KeithleyBiasEnabled==1)
//[NEWDAQ-REMOVED: Keithley] 		TipBias=floor(Tipbias/5)*5
//[NEWDAQ-REMOVED: Keithley] 		KeithleyBiasVolt(TipBias)
//[NEWDAQ-REMOVED: Keithley] 	endif
	WriteToHighRes(0,TipBias)
	
end

// Calls the piezo-only fine approach HighResCardApproach (the coarse stage is moved by hand)	// [NEWDAQ] was: "Calls actuator-specific CoarseApproach"
Function ApproachButton(ctrlName) : ButtonControl
	String ctrlName
	
	StopBkgdSampling()
	HighResCardApproach()
	StartBkgdSampling()
	
	Slider SliderPos_Z win=BreakJunctionMeasurement, disable=0
End

// Determines the order in which the IV ramp goes + and -
Function IVSignPopup(ctrlName,popNum,popStr) : PopupMenuControl
	String ctrlName
	Variable popNum
	String popStr
	
	NVAR IVSign= G_IVSignFlag

	if (popNum==1)
		IVSign=0
	elseif (popNum==2)
		IVSign=1
	endif

End

//[NEWDAQ-REMOVED: Keithley] Function SetCurrentSuppress(ctrlName,varNum,varStr,varName) : SetVariableControl
//[NEWDAQ-REMOVED: Keithley] 	String ctrlName
//[NEWDAQ-REMOVED: Keithley] 	Variable varNum
//[NEWDAQ-REMOVED: Keithley] 	String varStr
//[NEWDAQ-REMOVED: Keithley] 	String varName
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] 	NVAR CurrentSuppress = G_CurrentSuppress // in MicroAmps
//[NEWDAQ-REMOVED: Keithley] 	NVAR CurrentSuppressConst = G_CurrentSuppressConst
//[NEWDAQ-REMOVED: Keithley] 	NVAR CurrentVoltGain = G_CurrentVoltGain
//[NEWDAQ-REMOVED: Keithley] 	NVAR BoardUD=G_BoardUD
//[NEWDAQ-REMOVED: Keithley] 	NVAR DeviceUD=G_DeviceUD
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] 	CurrentSuppressConst = varNum
//[NEWDAQ-REMOVED: Keithley] 	CurrentSuppress = CurrentSuppressConst*10^(3-CurrentVoltGain)
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 board=BoardUD
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 device=DeviceUD
//[NEWDAQ-REMOVED: Keithley] 	GPIBWrite2 "H8S"+num2str(CurrentSuppress/1000000)+",0X"
//[NEWDAQ-REMOVED: Keithley] end

//[NEWDAQ-REMOVED: Keithley] Function FindSuppress(ctrlName) : ButtonControl
//[NEWDAQ-REMOVED: Keithley] 	String ctrlName
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] 	NVAR TipBias= G_TipBias
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] 	StopBkgdSampling()
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] 	// High-res card: write ZERO tip bias. 
//[NEWDAQ-REMOVED: Keithley] 	WriteToHighRes(0,0)
//[NEWDAQ-REMOVED: Keithley] 	// Determine suppress current value. 
//[NEWDAQ-REMOVED: Keithley] 	TestVirtualGround()
//[NEWDAQ-REMOVED: Keithley] 	// Revert tip bias to its normal value. 
//[NEWDAQ-REMOVED: Keithley] 	WriteToHighRes(0,TipBias)
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] 	StartBkgdSampling()
//[NEWDAQ-REMOVED: Keithley]
//[NEWDAQ-REMOVED: Keithley] End

// Button control: "Find Offset"
Function FindOffset(ctrlName) : ButtonControl
	String ctrlName

	// Stop ID_1 background task 
	// since OffsetVoltage also uses ID_1
	StopBkgdSampling()
	
	SetUpHRTaskID1()
	OffsetVoltage()
	ClearHRTaskID1()
	
	DoWindow/F Izero
	if(V_flag==0)
		execute "Izero()"
	endif
	DoUpdate
	
	StartBkgdSampling()
End