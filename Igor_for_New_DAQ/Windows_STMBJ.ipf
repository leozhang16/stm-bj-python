#pragma TextEncoding = "UTF-8"
////////////////////////////////////////////////////////////////////////////////
//       1         2         3         4         5         6         7         8
////////////////////////////////////////////////////////////////////////////////
//
// Name:     Windows_General.ipf
//
// Purpose:  Windows common to all experimental modes
//
// Author:   Jeff Taylor
//
// Date:     October 26, 2015
//
// Code:     STMBJ, CAFMBJ
//
// Includes: HighRes() : Graph
//           PullOutGvsE() : Graph
//           PullOutLow() : Graph
//           AuAuConductanceLevel() : Graph
//           SenseInDisplay() : Graph
//           LogHistOfBlock() : Graph
//           BreakJunctionMeasurement() : Panel
//
// Sources:  151010_AFM_operating_code.ipf
//
// History:     11/13/15 HL: Add Savehist checkbox
//                10/26/15 JCT: SenseInDisplay, ForceConductanceDisplay moved
//               10/26/15 JCT: CurrentReadings, VoltageReadings, RampSpike deleted
//               10/27/15 JCT: Put main window back in here
////////////////////////////////////////////////////////////////////////////////
//       1         2         3         4         5         6         7         8
////////////////////////////////////////////////////////////////////////////////
// ---------------------------------------------------------------------------
// [NEWDAQ] Ported 2026-10-22 for ONE NI USB-6453 (Dev1), no Keithley GPIB control,
// no coarse actuator. See PORTING_SPEC.md and README.md in this folder.
// ---------------------------------------------------------------------------

Window HighRes() : Graph
	PauseUpdate; Silent 1		// building window...
	Display /W=(622.5,439.25,874.5,578) VoltageIn	// [NEWDAQ] one card: the second-card voltage trace is gone
	AppendToGraph/R CurrentIn	// [NEWDAQ] one card: the second-card current trace is gone
	ModifyGraph margin(left)=36,margin(bottom)=36,margin(right)=36
	ModifyGraph rgb(VoltageIn)=(0,0,65280)	// [NEWDAQ] rgb clauses of the two removed traces dropped
	ModifyGraph rgb(CurrentIn)=(0,39168,0)
	ModifyGraph offset(VoltageIn)={-612,0},offset(CurrentIn)={-231,0}	// [NEWDAQ] offset clause of the removed trace dropped; GenerateTrace resets these at run time
	ModifyGraph tick=2
	ModifyGraph fSize=11
	ModifyGraph standoff=0
	ModifyGraph zapTZ(right)=1
	ModifyGraph zapLZ(right)=1
	ModifyGraph prescaleExp(left)=3,prescaleExp(bottom)=-3
	ModifyGraph axisOnTop=1
	Label left "Voltage (mV)"
	Label right "Current (µA)"
EndMacro

Window PullOutGvsE() : Graph
	PauseUpdate; Silent 1		// building window...
	Display /W=(6,44,282,184.25) PullOutConductance
	ModifyGraph margin(left)=36
	ModifyGraph grid(left)=1
	ModifyGraph tick=2
	ModifyGraph fSize=11
	ModifyGraph standoff=0
	ModifyGraph axisOnTop=1
	Label left "Conductance (G\\B0\\M)"
	Label bottom "Displacement (nm)"
	SetAxis left 0,*
EndMacro

Window PullOutLow() : Graph
	PauseUpdate; Silent 1		// building window...
	Display /W=(4.5,385.25,425.25,588.5)/R PullOutVoltage as "PullOutLowG"
	AppendToGraph PullOutConductance
	ModifyGraph margin(left)=36,margin(right)=36
	ModifyGraph rgb(PullOutVoltage)=(24576,24576,65280)
	ModifyGraph hideTrace(PullOutVoltage)=1
	ModifyGraph grid(left)=1
	ModifyGraph log(left)=1
	ModifyGraph tick=2
	ModifyGraph fSize=11
	ModifyGraph standoff=0
	ModifyGraph prescaleExp(right)=3
	ModifyGraph axisOnTop=1
	Label right "Measured Bias(mV)"
	Label bottom "Displacement (nm)"
	Label left "Conductance (G\\B0\\M)"
	SetAxis left 1e-06,5.58676
EndMacro

Window AuAuConductanceLevel() : Graph
	PauseUpdate; Silent 1		// building window...
	Display /W=(4.5,213.5,282.75,356) PullOutConductance as "PullOutLowG"
	ModifyGraph margin(left)=36
	ModifyGraph grid(left)=1
	ModifyGraph tick=2
	ModifyGraph fSize=11
	ModifyGraph standoff=0
	ModifyGraph axisOnTop=1
	Label left "Conductance (G\\B0\\M)"
	Label bottom "Displacement (nm)"
	SetAxis left 1e-05,5
EndMacro

Window SenseInDisplay() : Graph
	PauseUpdate; Silent 1		// building window...
	Display /W=(447,403.25,600.75,541.25) SenseIn
	ModifyGraph margin(left)=36
	ModifyGraph tick=2
	ModifyGraph fSize=11
	ModifyGraph standoff=0
	ModifyGraph axisOnTop=1
	Label left "Piezo (nm)"
	Label bottom "Points"
EndMacro


Window LogHistOfBlock() : Graph
	PauseUpdate; Silent 1		// building window...
	Display /W=(295.5,43.25,618,349.25) LogHistWave
	ModifyGraph margin(left)=36,margin(bottom)=36,margin(right)=30,gFont="Arial",gfSize=14
	ModifyGraph mode=7
	ModifyGraph rgb=(0,0,65280)
	ModifyGraph hbFill=5
	ModifyGraph tick=2
	ModifyGraph mirror=2
	ModifyGraph fSize=11
	ModifyGraph standoff=0
	ModifyGraph lblPosMode=3
	ModifyGraph lblPos(left)=55,lblPos(bottom)=45
	ModifyGraph axisOnTop=1
	Label left "Counts/Trace"
	Label bottom "Conductance [Log]"
	SetAxis left 0,40
	SetAxis bottom -6,1
EndMacro

Window BreakJunctionMeasurement() : Panel
	PauseUpdate; Silent 1		// building window...
	NewPanel /W=(1265,60,1660,884) as "Molecular Break Junction Measurement"
	ModifyPanel cbRGB=(48896,52992,65280), frameStyle=1
	SetDrawLayer UserBack
	SetDrawEnv save
	DrawRect -4,153,-4,153
	Slider SliderPos_Z,pos={47,610},size={301,53},disable=2,proc=SetPiezoBiasFromSlider
	Slider SliderPos_Z,font="Arial",fSize=12
	Slider SliderPos_Z,limits={-10,10,0.01},value= 0,live= 0,vert= 0,ticks= 20,thumbColor= (26112,0,0)
	SetVariable MoveZStepSize,pos={161,581},size={75,18},title="Z (nm)",font="Arial"
	SetVariable MoveZStepSize,limits={0,100,1},value= G_PiezoDeltaZ_nm
	SetVariable setvar43,pos={45,405},size={143,20},proc=SetGain,title="Gain ( log(V/A) )"
	SetVariable setvar43,font="Arial",fSize=14
	SetVariable setvar43,limits={3,10,1},value= G_CurrentVoltGain
	SetVariable TipBias_Inputs,pos={56,220},size={153,20},disable=1,proc=SetTipBiasVoltage,title="Tip Bias (mV)"
	SetVariable TipBias_Inputs,font="Arial",fSize=14,format="%3.1f"
	SetVariable TipBias_Inputs,limits={-5000,5000,0},value= G_TipBias
	Button MoveZIn,pos={60,580},size={76,23},proc=PiezoStepCloser,title="Step closer"
	Button MoveZIn,font="Arial"
	Button MoveZout,pos={264,581},size={76,22},proc=PiezoStepApart,title="Step apart"
	Button MoveZout,font="Arial"
	SetVariable Excursion_Inputs,pos={58,69},size={146,20},disable=1,title="Excursion (nm)"
	SetVariable Excursion_Inputs,font="Arial",fSize=14
	SetVariable Excursion_Inputs,limits={0.1,500,0},value= G_PseudoTotalLength_nm
	SetVariable EngageG_Inputs,pos={38,98},size={190,20},disable=1,title="Contact Threshold (G0)"
	SetVariable EngageG_Inputs,font="Arial",fSize=14
	SetVariable EngageG_Inputs,limits={0,10000,0},value= G_ConductanceThreshold
	SetVariable EngageStep_Inputs,pos={36,128},size={194,20},disable=1,title="Contact step size (nm)"
	SetVariable EngageStep_Inputs,font="Arial",fSize=14
	SetVariable EngageStep_Inputs,limits={0,50,0},value= G_MakeContactApproachStepSize
	SetVariable Saved_setVar,pos={39,721},size={139,22},title="Saved",font="Arial"
	SetVariable Saved_setVar,fSize=16,fStyle=1
	SetVariable Saved_setVar,limits={0,inf,0},value= G_PullOutNumber
	SetVariable PullRate_Inputs,pos={54,41},size={146,20},disable=1,title="Pull Rate (nm/s)"
	SetVariable PullRate_Inputs,font="Arial",fSize=14
	SetVariable PullRate_Inputs,limits={0,1000,0},value= G_PullOutRate
	//[NEWDAQ-REMOVED: Keithley] CheckBox ZeroCheckBox,pos={137,324},size={91,16},proc=ZeroCheckProc,title="Zero Check"
	//[NEWDAQ-REMOVED: Keithley] CheckBox ZeroCheckBox,font="Arial",fSize=14,fStyle=0,value= 1
	//[NEWDAQ-REMOVED: Keithley] CheckBox KeithleyBias,pos={52,324},size={45,16},proc=KeithleyBias,title="Bias"
	//[NEWDAQ-REMOVED: Keithley] CheckBox KeithleyBias,font="Arial",fSize=14,fStyle=0,value= 0, variable=G_KeithleyBiasEnabled
	//[NEWDAQ-REMOVED: Keithley] SetVariable SuppressSetVar,pos={197,396},size={153,36},proc=SetCurrentSuppress,title="Suppress I \r value"
	//[NEWDAQ-REMOVED: Keithley] SetVariable SuppressSetVar,font="Arial",fSize=14,format="%3.2f"
	//[NEWDAQ-REMOVED: Keithley] SetVariable SuppressSetVar,limits={-1000,1000,0},value= G_CurrentSuppressConst
	//[NEWDAQ-REMOVED: Keithley] CheckBox SuppressCheckBox,pos={138,368},size={85,16},proc=CurrentSuppressCheckProc,title="Suppress I"
	//[NEWDAQ-REMOVED: Keithley] CheckBox SuppressCheckBox,font="Arial",fSize=14,value= 0
	SetVariable setvar17,pos={38,790},size={139,20},title="Attempts",font="Arial"
	SetVariable setvar17,fSize=14,fStyle=1,limits={0,inf,0},value= G_PullOutAttempt
	CheckBox SaveBias_Inputs,pos={241,34},size={81,16},disable=1,title="Save Bias"
	CheckBox SaveBias_Inputs,font="Arial",fSize=14,variable= G_BiasSaveCheck
	CheckBox SaveCurrent_Inputs,pos={241,53},size={102,16},disable=1,title="Save Current"
	CheckBox SaveCurrent_Inputs,font="Arial",fSize=14,variable= G_CurrentSaveCheck
	CheckBox SaveHist_Inputs,pos={241,110},size={77,16},disable=1,title="Save Hist"
	CheckBox SaveHist_Inputs,font="Arial",fSize=14,variable= G_HistSaveCheck
	SetVariable AcqRate_DAQ,pos={52,122},size={193,20},title="Acquisition Rate"
	SetVariable AcqRate_DAQ,font="Arial",fSize=14
	SetVariable AcqRate_DAQ,limits={100,200000,0},value= G_AcquisitionRate
	Button Start_DAQ,pos={261,43},size={94,46},proc=StartHighResWritingTask,title="Start\rWriting"
	Button Start_DAQ,help={"Starts the DAQ writing task (G_OD1): piezo on Dev1/ao2, bias on Dev1/ao1"}	// [NEWDAQ] was: "... in the high-res card"
	Button Start_DAQ,font="Arial",fSize=14,fStyle=1,fColor=(0,0,39168)
	Button Stop_DAQ,pos={262,101},size={94,46},proc=StopWritingTasks,title="Kill\rTasks"
	Button Stop_DAQ,font="Arial",fSize=14,fStyle=1,fColor=(52224,0,0)
	SetVariable WriteBufferSize_DAQ,pos={81,156},size={164,20},title="Write Buffer Size"
	SetVariable WriteBufferSize_DAQ,font="Arial",fSize=14
	SetVariable WriteBufferSize_DAQ,limits={25,2000,0},value= G_WriteBufferSize
	TabControl TAB,pos={29,6},size={351,240},proc=MainWindowTabProc
	TabControl TAB,labelBack=(48896,65280,57344),font="Arial",fSize=14
	TabControl TAB,tabLabel(0)="DAQ",tabLabel(1)="Inputs",tabLabel(2)="Options"
	TabControl TAB,value= 0
	Button Reset_DAQ,pos={262,158},size={94,46},proc=EChemResetDAQDevices,title="Reset DAQ\rDevice"	// [NEWDAQ] one device (was "Devices")
	Button Reset_DAQ,labelBack=(65535,65535,65535),font="Arial",fSize=14,fStyle=1
	Button Reset_DAQ,fColor=(52224,52224,52224)
	ValDisplay CurrentReadOut,pos={35,685},size={110,20},title="I (µA)",font="Arial"
	ValDisplay CurrentReadOut,fSize=16,format="%3.5f",frame=2,fStyle=1
	ValDisplay CurrentReadOut,limits={0,0,0},barmisc={0,1000}
	ValDisplay CurrentReadOut,value= #"root:G_CurrentSamplingReadoutVal"
	CheckBox OnCheck,pos={50,259},size={288,19},disable=2,proc=BkgdSamplingCheckProc,title="Background Sampling (Beep is ON)"
	CheckBox OnCheck,font="Arial",fSize=16,fStyle=1,value= 0
	SetVariable StopNo_setVar,pos={38,756},size={139,22},title="Stop #",font="Arial"
	SetVariable StopNo_setVar,fSize=16,fStyle=1,limits={0,inf,0},value= G_StopNumber
	SetVariable ZerCutoff_Inputs,pos={41,191},size={178,20},disable=1,title="Zero Cutoff (G0)"
	SetVariable ZerCutoff_Inputs,font="Arial",fSize=14
	SetVariable ZerCutoff_Inputs,limits={0,0.5,0},value= G_EndOfTraceNoiseThreshold
	ValDisplay PiezoVoltReadout,pos={275,685},size={90,20},title="Piezo"
	ValDisplay PiezoVoltReadout,font="Arial",fSize=16,format="%3.2f",frame=2
	ValDisplay PiezoVoltReadout,fStyle=1,limits={0,0,0},barmisc={0,1000}
	ValDisplay PiezoVoltReadout,value= #"root:G_PiezoBiasSamplingReadoutVal"
	SetVariable SeriesR_Inputs,pos={43,160},size={165,20},disable=1,title="Series R (Ohm)"
	SetVariable SeriesR_Inputs,font="Arial",fSize=14
	SetVariable SeriesR_Inputs,limits={-inf,inf,0},value= G_SeriesResistance
	SetVariable SmashFreq_Inputs,pos={223,169},size={142,20},disable=1,title="Smash Freq."
	SetVariable SmashFreq_Inputs,font="Arial",fSize=14
	SetVariable SmashFreq_Inputs,limits={0,inf,0},value= G_SmashFrequency
	GroupBox box10105,pos={33,288},size={329,152},title="Current Amplifier (gain by hand)"	// [NEWDAQ] retitled: the amplifier gain is set on its front panel; only the Gain number (setvar43) stays
	GroupBox box10105,font="Arial",fSize=12,frame=0
	ValDisplay ZPiezoScale_DAQ,pos={66,52},size={170,17},title="Z piezo scale (nm/V)"
	ValDisplay ZPiezoScale_DAQ,font="Arial",fSize=14,limits={0,0,0},barmisc={0,1000}
	ValDisplay ZPiezoScale_DAQ,value= #"K_ZPiezoScale"
	ValDisplay ZSenseScale_DAQ,pos={62,83},size={175,17},title="Z Sense scale (nm/V)"
	ValDisplay ZSenseScale_DAQ,font="Arial",fSize=14,limits={0,0,0},barmisc={0,1000}
	ValDisplay ZSenseScale_DAQ,value= #"K_SenseScale"
	CheckBox check08,pos={176,572},size={50,20},disable=1,value= 0
	SetVariable setvar15,pos={236,572},size={50,18},disable=1
	//[NEWDAQ-REMOVED: Keithley] Button FindSuppressButton,pos={244,361},size={107,28},proc=FindSuppress,title="Find Suppress"
	//[NEWDAQ-REMOVED: Keithley] Button FindSuppressButton,font="Arial",fSize=14,fColor=(0,65280,0)
	SetVariable setvar5,pos={260,543},size={50,20},disable=1
	SetVariable setvar7,pos={-21,568},size={50,20},disable=1
	Button StartMeasurementButton,pos={193,755},size={129,55},proc=StartMeasurement,title="Start\rMeasurement"
	Button StartMeasurementButton,labelBack=(65280,54528,32768),font="Arial"
	Button StartMeasurementButton,fSize=16,fStyle=1,fColor=(0,52224,26368)
	//[NEWDAQ-REMOVED: Actuator] Button StepOpen,pos={165,507},size={85,24},proc=StepActuatorApart,title="Step apart"
	//[NEWDAQ-REMOVED: Actuator] Button StepOpen,font="Arial",fSize=14
	//[NEWDAQ-REMOVED: Actuator] Button StepTogether,pos={65,507},size={89,24},proc=StepActuatorCloser,title="Step closer"
	//[NEWDAQ-REMOVED: Actuator] Button StepTogether,font="Arial",fSize=14
	//[NEWDAQ-REMOVED: Actuator] SetVariable StepSizeSetVar,pos={45,479},size={128,20},title="Step Size"
	//[NEWDAQ-REMOVED: Actuator] SetVariable StepSizeSetVar,font="Arial",fSize=14
	//[NEWDAQ-REMOVED: Actuator] SetVariable StepSizeSetVar,limits={1,inf,1},value= G_ActuatorStepSize
	Button StartApproachButton,pos={261,479},size={91,49},proc=ApproachButton,title="Start\rApproach"
	Button StartApproachButton,font="Arial",fSize=14,fStyle=1,fColor=(0,43520,65280)
	SetVariable SmashIn_Inputs,pos={247,196},size={110,20},disable=1,title="Smash In"
	SetVariable SmashIn_Inputs,font="Arial",fSize=14
	SetVariable SmashIn_Inputs,limits={-inf,inf,0},value= G_SmashInSteps
	SetVariable SmashOut_Inputs,pos={236,219},size={121,20},disable=1,title="Smash Out"
	SetVariable SmashOut_Inputs,font="Arial",fSize=14
	SetVariable SmashOut_Inputs,limits={-inf,inf,0},value= G_SmashOutSteps
	GroupBox PiezoGroupbox,pos={33,555},size={330,112},title="Piezo Controls"
	GroupBox PiezoGroupbox,font="Arial",frame=0
	GroupBox ActuatorGroupBox,pos={32,452},size={331,90},title="Approach (coarse stage by hand)"	// [NEWDAQ] retitled: the coarse stage is moved by hand; only Start Approach (piezo-only) stays
	GroupBox ActuatorGroupBox,font="Arial",frame=0
	TabControl RampSubTabs_Ramps,pos={29,27},size={350,222},disable=1,proc=SubWindowTabProc
	TabControl RampSubTabs_Ramps,labelBack=(65280,65280,32768),font="Arial"
	TabControl RampSubTabs_Ramps,tabLabel(0)="Push-Pull",tabLabel(1)="IV"
	TabControl RampSubTabs_Ramps,tabLabel(2)="AC",tabLabel(3)="High bias hold"
	TabControl RampSubTabs_Ramps,value= 0
	CheckBox PushPullCheck_PushPullRamps,pos={59,81},size={78,16},disable=1,proc=RampOptionsCheckProc,title="Push-Pull"
	CheckBox PushPullCheck_PushPullRamps,font="Arial",fSize=14
	CheckBox PushPullCheck_PushPullRamps,variable= G_PushPullCheck
	SetVariable NoPPCyclesSetvar_PushPullRamps,pos={166,79},size={181,20},disable=1,title="Number of cycles"
	SetVariable NoPPCyclesSetvar_PushPullRamps,font="Arial",fSize=14
	SetVariable NoPPCyclesSetvar_PushPullRamps,value= G_NumPushPullCycles
	SetVariable PPInitialPull_PushPullRamps,pos={61,119},size={137,20},disable=1,title="Initial Pull (nm)"
	SetVariable PPInitialPull_PushPullRamps,font="Arial",fSize=14
	SetVariable PPInitialPull_PushPullRamps,limits={-inf,inf,0},value= G_InitialPullLength
	SetVariable PPFinalPull_PushPullRamps,pos={210,119},size={136,20},disable=1,title="Final Pull (nm)"
	SetVariable PPFinalPull_PushPullRamps,font="Arial",fSize=14
	SetVariable PPFinalPull_PushPullRamps,limits={-inf,inf,0},value= G_FinalPullLength
	SetVariable PushPullLength_PushPullRamps,pos={110,160},size={180,20},disable=1,title="Push-Pull length (nm)"
	SetVariable PushPullLength_PushPullRamps,font="Arial",fSize=14
	SetVariable PushPullLength_PushPullRamps,limits={-inf,inf,0},value= G_PushPullLength
	SetVariable HoldLength_PushPullRamps,pos={123,200},size={148,20},disable=1,title="Hold length (nm)"
	SetVariable HoldLength_PushPullRamps,font="Arial",fSize=14
	SetVariable HoldLength_PushPullRamps,limits={-inf,inf,0},value= G_HoldLength
	CheckBox IVCheck_IVRamps,pos={64,79},size={30,16},disable=1,proc=RampOptionsCheckProc,title="IV"
	CheckBox IVCheck_IVRamps,font="Arial",fSize=14,variable= G_IVCheck
	SetVariable MaxBias_IVRamps,pos={216,76},size={119,20},disable=1,title="MaxBias (V)"
	SetVariable MaxBias_IVRamps,font="Arial",fSize=14,format="%1.2f"
	SetVariable MaxBias_IVRamps,limits={-inf,inf,0},value= G_IVMaxBias
	PopupMenu IVSignPopup_IVRamps,pos={111,76},size={84,21},disable=1,proc=IVSignPopup,title="Sign:"
	PopupMenu IVSignPopup_IVRamps,font="Arial",fSize=14
	PopupMenu IVSignPopup_IVRamps,mode=1,popvalue="+ / -",value= #"\"+ / -;- / +\""
	SetVariable IVInitPull_IVRamps,pos={58,120},size={124,20},disable=1,title="Initial Pull (nm)"
	SetVariable IVInitPull_IVRamps,font="Arial",fSize=14,format="%3.1f"
	SetVariable IVInitPull_IVRamps,limits={-inf,inf,0},value= G_IVInitPull
	SetVariable IVIFinPull_IVRamps,pos={205,120},size={124,20},disable=1,title="Final Pull (nm)"
	SetVariable IVIFinPull_IVRamps,font="Arial",fSize=14,format="%3.1f"
	SetVariable IVIFinPull_IVRamps,limits={-inf,inf,0},value= G_IVFinPull
	SetVariable IVCapLength_IVRamps,pos={128,164},size={138,20},disable=1,title="Cap length (nm)"
	SetVariable IVCapLength_IVRamps,font="Arial",fSize=14,format="%3.1f"
	SetVariable IVCapLength_IVRamps,limits={-inf,inf,0},value= G_IVCapLength
	SetVariable IVRampLength_IVRamps,pos={121,204},size={149,20},disable=1,title="Ramp length (nm)"
	SetVariable IVRampLength_IVRamps,font="Arial",fSize=14,format="%3.1f"
	SetVariable IVRampLength_IVRamps,limits={-inf,inf,0},value= G_IVRampLength
	CheckBox ACHoldCheck_ACHoldRamps,pos={163,66},size={69,16},disable=1,proc=RampOptionsCheckProc,title="AC Hold"
	CheckBox ACHoldCheck_ACHoldRamps,font="Arial",fSize=14,variable= G_ACHoldCheck
	SetVariable ACAmp_ACHoldRamps,pos={77,100},size={92,20},disable=1,title="Amp (V)"
	SetVariable ACAmp_ACHoldRamps,font="Arial",fSize=14,format="%1.2f"
	SetVariable ACAmp_ACHoldRamps,limits={-inf,inf,0},value= G_ACAmp
	SetVariable ACFreq_ACHoldRamps,pos={196,101},size={113,20},disable=1,title="Freq (kHz)"
	SetVariable ACFreq_ACHoldRamps,font="Arial",fSize=14,format="%3.1f"
	SetVariable ACFreq_ACHoldRamps,limits={-inf,inf,0},value= G_ACFreq
	SetVariable ACInitPull_ACHoldRamps,pos={134,138},size={125,20},disable=1,title="Initial Pull (nm)"
	SetVariable ACInitPull_ACHoldRamps,font="Arial",fSize=14,format="%3.1f"
	SetVariable ACInitPull_ACHoldRamps,limits={-inf,inf,0},value= G_ACInitPullLength
	SetVariable ACHoldLength_ACHoldRamps,pos={128,173},size={137,20},disable=1,title="Hold length (nm)"
	SetVariable ACHoldLength_ACHoldRamps,font="Arial",fSize=14,format="%3.1f"
	SetVariable ACHoldLength_ACHoldRamps,limits={-inf,inf,0},value= G_ACHoldLength
	SetVariable ACFinalPulll_ACHoldRamps,pos={134,209},size={126,20},disable=1,title="Final Pull (nm)"
	SetVariable ACFinalPulll_ACHoldRamps,font="Arial",fSize=14,format="%3.1f"
	SetVariable ACFinalPulll_ACHoldRamps,limits={-inf,inf,0},value= G_ACFinPullLength
	SetVariable TipBias,pos={189,720},size={168,22},proc=SetTipBiasVoltage,title="Tip Bias (mV)"
	SetVariable TipBias,font="Arial",fSize=16,format="%3.1f",fStyle=1
	SetVariable TipBias,limits={-5000,5000,0},value= G_TipBias
	Button SingleAttemptButton,pos={332,765},size={25,37},proc=MakeAttempt,title="+1"
	Button SingleAttemptButton,font="Arial",fSize=14,fStyle=1,fColor=(0,43520,65280)
	SetVariable ReadWaveSize_DAQ,pos={53,189},size={193,20},title="Fast Read Wave Size"
	SetVariable ReadWaveSize_DAQ,font="Arial",fSize=14
	SetVariable ReadWaveSize_DAQ,limits={25,2000,0},value= G_FastReadWaveSize
	//[NEWDAQ-REMOVED: Actuator] ValDisplay ActuatorCounter_Valdisp,pos={185,480},size={64,17},font="Arial"
	//[NEWDAQ-REMOVED: Actuator] ValDisplay ActuatorCounter_Valdisp,fSize=14,frame=0
	//[NEWDAQ-REMOVED: Actuator] ValDisplay ActuatorCounter_Valdisp,limits={0,0,0},barmisc={0,1000}
	//[NEWDAQ-REMOVED: Actuator] ValDisplay ActuatorCounter_Valdisp,value= #"G_ActuatorCounter"
	SetVariable CounterElectrodeSetVar_EChem,pos={22,79},size={258,22},disable=1,proc=CounterElectrodeSetVar,title="Counter Electrode Bias (mV)"
	SetVariable CounterElectrodeSetVar_EChem,font="Arial",fSize=16
	SetVariable CounterElectrodeSetVar_EChem,limits={-5000,5000,0},value= G_CounterElectrodeBias
	CheckBox CounterElectrodeCheck_EChem,pos={52,48},size={185,19},disable=1,proc=CounterElectrodeCheckProc,title="Counter Electrode ON"
	CheckBox CounterElectrodeCheck_EChem,font="Arial",fSize=16,fStyle=1,value= 0
	CheckBox SaveSense_Inputs,pos={241,90},size={94,16},disable=1,title="Save Sense"
	CheckBox SaveSense_Inputs,font="Arial",fSize=14,variable= G_SenseSaveCheck
	CheckBox HBHoldCheck_HBHoldRamps,pos={235,65},size={109,16},disable=1,proc=RampOptionsCheckProc,title="High Bias Hold"
	CheckBox HBHoldCheck_HBHoldRamps,font="Arial",fSize=14,variable= G_HBHoldCheck
	SetVariable HBBias_HBHoldRamps,pos={44,80},size={153,20},disable=1,title="Hold bias (V)"
	SetVariable HBBias_HBHoldRamps,font="Arial",fSize=14,format="%1.5f"
	SetVariable HBBias_HBHoldRamps,limits={-inf,inf,0},value= G_HBBias
	SetVariable HBInitPull__HBHoldRamps,pos={48,113},size={149,20},disable=1,title="Initial Pull (nm)"
	SetVariable HBInitPull__HBHoldRamps,font="Arial",fSize=14,format="%3.2f"
	SetVariable HBInitPull__HBHoldRamps,limits={-inf,inf,0},value= G_HBInitPullLength
	SetVariable HBHoldLength_HBHoldRamps,pos={44,146},size={153,20},disable=1,title="Hold length (nm)"
	SetVariable HBHoldLength_HBHoldRamps,font="Arial",fSize=14,format="%3.2f"
	SetVariable HBHoldLength_HBHoldRamps,limits={-inf,inf,0},value= G_HBHoldLength
	SetVariable HBFinalPulll_HBHoldRamps,pos={206,113},size={143,20},disable=1,title="Final Pull (nm)"
	SetVariable HBFinalPulll_HBHoldRamps,font="Arial",fSize=14,format="%3.2f"
	SetVariable HBFinalPulll_HBHoldRamps,limits={-inf,inf,0},value= G_HBFinPullLength
	SetVariable HBCapIN__HBHoldRamps,pos={38,180},size={160,36},disable=1,title="Cap \rLength IN (nm)"
	SetVariable HBCapIN__HBHoldRamps,font="Arial",fSize=14,format="%3.5f"
	SetVariable HBCapIN__HBHoldRamps,limits={-inf,inf,0},value= G_HBCapLengthIN
	CheckBox VoltageRead_Inputs,pos={241,130},size={100,16},disable=1,title="VoltageRead"
	CheckBox VoltageRead_Inputs,font="Arial",fSize=14,variable= G_VoltageRead
	CheckBox SavePiezoWave_Inputs,pos={241,71},size={128,16},disable=1,title="Save Piezo Wave"
	CheckBox SavePiezoWave_Inputs,font="Arial",fSize=14
	CheckBox SavePiezoWave_Inputs,variable= G_PiezoWaveSaveCheck
	//[NEWDAQ-REMOVED: Keithley] Button ZeroCorrectButton,pos={244,317},size={107,28},proc=ZeroCorrectProc,title="Zero Correct"
	//[NEWDAQ-REMOVED: Keithley] Button ZeroCorrectButton,font="Arial",fSize=14,fColor=(52224,34816,0)
	ValDisplay JunctionVoltageReadout,pos={155,685},size={110,20},title="V (mV)"
	ValDisplay JunctionVoltageReadout,font="Arial",fSize=16,format="%3.2f",frame=2
	ValDisplay JunctionVoltageReadout,fStyle=1,limits={0,0,0},barmisc={0,1000}
	ValDisplay JunctionVoltageReadout,value= #"root:G_JunctionVoltage"
	SetVariable OutputRangeHighRes_DAQ,pos={53,216},size={227,20},title="Bias Output Range (V)"	// [NEWDAQ] was "HighRes Output Range (V)"; it is the range of the bias output ao1
	SetVariable OutputRangeHighRes_DAQ,font="Arial",fSize=14
	SetVariable OutputRangeHighRes_DAQ,limits={0,10,0},value= G_HighResOutputRange
	SetVariable HBCapFIN__HBHoldRamps,pos={206,181},size={166,36},disable=1,title="Cap \rLength FIN (nm)"
	SetVariable HBCapFIN__HBHoldRamps,font="Arial",fSize=14,format="%3.5f"
	SetVariable HBCapFIN__HBHoldRamps,limits={-inf,inf,0},value= G_HBCapLengthFIN
EndMacro

// Window macro for voltage offset (setup 1)
Window Voltage_Offset() : Panel
	PauseUpdate; Silent 1		// building window...
	NewPanel /W=(790,655,1205,855) as "Voltage Offset"
	ModifyPanel cbRGB=(56576,56576,56576), frameStyle=1
	SetDrawLayer UserBack
	GroupBox VoltageOffsetBox,pos={7,11},size={399,177},title="Voltage Offset"
	GroupBox VoltageOffsetBox,labelBack=(65280,48896,48896),font="Arial",fSize=18
	GroupBox VoltageOffsetBox,frame=0,fStyle=0
	SetVariable TipBiasInterval,pos={14,48},size={226,22},title="Tip Bias interval (mV)"
	SetVariable TipBiasInterval,font="Arial",fSize=16,format="%3.1f"
	SetVariable TipBiasInterval,limits={0.1,1000,0},value= G_VoltageInterval
	SetVariable NumPoints,pos={53,73},size={187,22},title="Number of points"
	SetVariable NumPoints,font="Arial",fSize=16,format="%3.0f"
	SetVariable NumPoints,limits={3,1000,1},value= G_NumPoints
	SetVariable Vzero,pos={222,116},size={168,26},title="V\\B0\\M (fit, mV)"
	SetVariable Vzero,font="Arial",fSize=16,format="%3.4f",fStyle=1
	SetVariable Vzero,limits={-10000,10000,0},value= G_Vzero
	Button FindOffset,pos={45,143},size={144,35},proc=FindOffset,title="Find Offset"
	Button FindOffset,font="Arial",fSize=16,fStyle=0,fColor=(0,52224,0)
	SetVariable NumPoints1,pos={254,53},size={145,40},title="Frequency \r \\JC(traces)"
	SetVariable NumPoints1,font="Arial",fSize=16,format="%3.0f"
	SetVariable NumPoints1,limits={1,5000,10},value= G_Vzerofrequency
	CheckBox VzeroCheckBox,pos={60,115},size={113,22},proc=VzeroCheckProc,title="V\\B0\\M check ON"
	CheckBox VzeroCheckBox,font="Arial",fSize=16,fStyle=1,value= 0
	SetVariable Vzero1,pos={224,151},size={167,26},title="I\\B0\\M (fit, µA)"
	SetVariable Vzero1,font="Arial",fSize=16,format="%3.6f",fStyle=1
	SetVariable Vzero1,limits={-10000,10000,0},value= G_Izero
EndMacro

Window Izero() : Graph
	PauseUpdate; Silent 1		// building window...
	Display /W=(354,46.25,621,214.25) CurrentWave vs TipBiasRamp as "I(Applied Bias) fit - Izero estimate"
	AppendToGraph fit_CurrentWave
	ModifyGraph mode(CurrentWave)=3
	ModifyGraph rgb(CurrentWave)=(65280,0,52224),rgb(fit_CurrentWave)=(0,0,65280)
	ModifyGraph tick=2
	ModifyGraph zero(left)=3
	ModifyGraph mirror=2
	Label left "Current (µA)"
	Label bottom "Tip Applied Bias (mV)"
	TextBox/C/N=text0/S=3/Z=1/A=MC/X=26.09/Y=-28.30 "V\\B0\\M = \\{G_Vzero} mV\rI\\B0\\M = \\{G_Izero} µA"
EndMacro

Window Izero_Time() : Graph
	PauseUpdate; Silent 1		// building window...
	Display /W=(341.25,243.5,615,415.25) IzeroWave vs PullOutNumberWave as "Izero change over time"
	ModifyGraph mode=4
	ModifyGraph marker=16
	ModifyGraph rgb=(0,52224,0)
	ModifyGraph useMrkStrokeRGB=1
	ModifyGraph tick=2
	ModifyGraph mirror=2
	ModifyGraph prescaleExp(left)=3
	Label left "I\\B0\\M (µA x 1e-3)"
	Label bottom "Saved Trace Number"
	SetAxis/A=2 left
EndMacro

Window EChem() : Panel
	PauseUpdate; Silent 1		// building window...
	NewPanel /W=(847,62,1202,609) as "Electrochemistry"
	ModifyPanel cbRGB=(48896,65280,65280)
	Button StartEChemWriteButton,pos={129,43},size={98,73},proc=CounterElectrodeOn,title="Counter\rElectrode\rON"
	Button StartEChemWriteButton,font="Arial",fSize=16,fStyle=1
	Button StartEChemWriteButton,fColor=(0,26112,13056)
	SetVariable CounterElectrodeSetVar,pos={43,133},size={263,22},disable=2,proc=CounterElectrodeSetVar,title="Counter Electrode Bias (mV)"
	SetVariable CounterElectrodeSetVar,font="Arial",fSize=16
	SetVariable CounterElectrodeSetVar,limits={-inf,inf,0},value= G_CounterElectrodeBias
	Button StartCVHighResButton,pos={44,456},size={126,53},disable=2,proc=StartCVHighResButton,title="CV (bias out)"	// [NEWDAQ] retitled: ramp on the bias output (control name kept, Controls refers to it)
	Button StartCVHighResButton,font="Arial",fSize=16,fStyle=1
	Button StartCVHighResButton,valueColor=(65280,0,0)
	SetVariable CVAcquisitionRateSetVar,pos={32,270},size={287,22},proc=CVAcquisitionRateSetVar,title="CV Acquisition Rate (samps/s)"
	SetVariable CVAcquisitionRateSetVar,font="Arial",fSize=16
	SetVariable CVAcquisitionRateSetVar,limits={50,40000,0},value= G_CVAcquisitionRate
	SetVariable NumCVCyclesSetVar,pos={123,301},size={178,22},proc=NumCVCyclesSetVar,title="Number of Cycles"
	SetVariable NumCVCyclesSetVar,font="Arial",fSize=16
	SetVariable NumCVCyclesSetVar,limits={0,1000,1},value= G_NumCVCycles
	SetVariable ScanRateSetVar,pos={122,332},size={196,22},proc=ScanRateSetVar,title="Scan Rate (mV/s)"
	SetVariable ScanRateSetVar,font="Arial",fSize=16
	SetVariable ScanRateSetVar,limits={0,2000,25},value= G_ScanRate
	SetVariable VoltagePeakOneSetVar,pos={113,375},size={194,22},proc=VoltagePeakOneSetVar,title="Voltage Peak 1 (V)"
	SetVariable VoltagePeakOneSetVar,font="Arial",fSize=16
	SetVariable VoltagePeakOneSetVar,limits={-2.5,0,0.25},value= G_VoltagePeakOne
	SetVariable VoltagePeakTwoSetVar,pos={113,406},size={194,22},proc=VoltagePeakTwoSetVar,title="Voltage Peak 2 (V)"
	SetVariable VoltagePeakTwoSetVar,font="Arial",fSize=16
	SetVariable VoltagePeakTwoSetVar,limits={0,2.5,0.25},value= G_VoltagePeakTwo
	SetVariable SetGain,pos={134,229},size={155,22},proc=SetGain,title="Gain ( log(V/A) )"
	SetVariable SetGain,font="Arial",fSize=16
	SetVariable SetGain,limits={1,10,1},value= G_CurrentVoltGain
	GroupBox CVBox,pos={11,190},size={333,340},title="Cyclic Voltammetry"
	GroupBox CVBox,font="Arial",fSize=14,frame=0
	GroupBox ECGatingBox,pos={9,10},size={335,162},title="Electrochemical Gating"
	GroupBox ECGatingBox,font="Arial",fSize=14,frame=0
	Button StartCVLowResButton,pos={182,456},size={126,53},disable=2,proc=StartCVLowResButton,title="CV (CE out)"	// [NEWDAQ] retitled: ramp on the counter-electrode output (control name kept, Controls refers to it)
	Button StartCVLowResButton,font="Arial",fSize=16,fStyle=1,fColor=(65280,0,52224)
EndMacro

Window CyclicVoltammogram() : Graph
	PauseUpdate; Silent 1		// building window...
	Display /W=(128.25,47,616.5,374.75) TipCurrent vs CVAppliedRamp as "Cyclic Voltammogram"
	ModifyGraph rgb=(0,0,65280)
	ModifyGraph msize=2
	ModifyGraph grid(bottom)=2
	ModifyGraph tick=2
	ModifyGraph mirror=2
	ModifyGraph minor(bottom)=1
	ModifyGraph fSize=12
	Label left "\\Z12Current (µA)"
	Label bottom "\\Z12Applied Voltage (mV)"
	SetAxis/A/R bottom
	TextBox/C/N=CVnumber/F=0/Z=1/A=MC/X=5.40/Y=44.30 "\\Z12CV cycle \\f011"
EndMacro
