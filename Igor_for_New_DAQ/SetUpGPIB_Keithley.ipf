#pragma TextEncoding = "UTF-8"		// [NEWDAQ] first line of every file (Igor 7+)
////////////////////////////////////////////////////////////////////////////////

// SetUpGPIB_Keithley

////////////////////////////////////////////////////////////////////////////////
// ---------------------------------------------------------------------------
// [NEWDAQ] Ported 2026-10-22 for ONE NI USB-6453 (Dev1), no Keithley GPIB control,
// no coarse actuator. See PORTING_SPEC.md and README.md in this folder.
// ---------------------------------------------------------------------------
// [NEWDAQ] THIS FILE IS DISABLED. It is kept for reference only and is NOT #included:
// [NEWDAQ] Setup_NewDAQ_STMBJ.ipf has '#include ":SetUpGPIB_Keithley"' commented out.
// [NEWDAQ]
// [NEWDAQ] Why: the current-to-voltage amplifier (Keithley 428 or equivalent) is now set BY HAND on
// [NEWDAQ] its front panel: gain, filter / rise time, zero check, zero correct, current suppress, bias.
// [NEWDAQ] Igor no longer talks to it over GPIB (no NI4882 / GPIB2 / GPIBWrite2). Igor only keeps the
// [NEWDAQ] gain numbers G_CurrentVoltGain / G_CurrentVoltConversion (set with the panel's Gain control,
// [NEWDAQ] software only) to convert the amplifier output volts to amps. Set the SAME gain on the box.
// [NEWDAQ]
// [NEWDAQ] To restore GPIB control of the Keithley:
// [NEWDAQ]   1. In this file remove the prefix "//[NEWDAQ-REMOVED: Keithley] " from every line
// [NEWDAQ]      (e.g.  sed -i 's|^//\[NEWDAQ-REMOVED: Keithley\] ||' SetUpGPIB_Keithley.ipf ).
// [NEWDAQ]   2. In Setup_NewDAQ_STMBJ.ipf uncomment '#include ":SetUpGPIB_Keithley"' and the
// [NEWDAQ]      SetUpGPIB_Keithley() call in InitializeExperiment().
// [NEWDAQ]   3. Uncomment the "NEWDAQ-REMOVED: Keithley" lines in Functions_STMBJ.ipf (G_DeviceUD,
// [NEWDAQ]      G_BoardUD, G_KeithleyBiasEnabled, TestVirtualGround, the Keithley-bias branches),
// [NEWDAQ]      Controls_STMBJ.ipf (SetGain GPIB lines, StopWritingTasks zero check, CurrentSuppressCheckProc,
// [NEWDAQ]      ZeroCheckProc, ZeroCorrectProc, SetCurrentSuppress, FindSuppress), Windows_STMBJ.ipf (the
// [NEWDAQ]      Keithley controls of the BreakJunctionMeasurement panel) and EChem_Module.ipf (the CV
// [NEWDAQ]      buttons' zero-check lines).
// [NEWDAQ]   4. NI-488.2 must be installed with the NI4882 and GPIB2 XOPs; the amplifier is GPIB address 22.
// [NEWDAQ] grep -n "NEWDAQ-REMOVED: Keithley" *.ipf  lists every disabled line.



//[NEWDAQ-REMOVED: Keithley] // initialize GPIB to read and set-up Keithley Current Amplifier
//[NEWDAQ-REMOVED: Keithley] Function SetUpGPIB_Keithley()
//[NEWDAQ-REMOVED: Keithley] 	NVAR BoardUD = G_BoardUD
//[NEWDAQ-REMOVED: Keithley] 	NVAR DeviceUD = G_DeviceUD
//[NEWDAQ-REMOVED: Keithley] 	NVAR IVConversion = G_CurrentVoltConversion // MicroA to Volts
//[NEWDAQ-REMOVED: Keithley] //	NVAR TipBias = G_TipBias // milli Volts
	
//[NEWDAQ-REMOVED: Keithley] 	NI4882 ibfind={"gpib0"};BoardUD=V_flag
//[NEWDAQ-REMOVED: Keithley] 	NI4882 ibdev={0,22,0,13,1,0};DeviceUD=V_flag
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 board=BoardUD
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 device=DeviceUD
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 KillIO
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 InterfaceClear
//[NEWDAQ-REMOVED: Keithley] 	GPIBWrite2 "C1P0B0N0X"
//[NEWDAQ-REMOVED: Keithley] end


//[NEWDAQ-REMOVED: Keithley] Function LocalGPIB()
//[NEWDAQ-REMOVED: Keithley] //execute "GPIBWrite \"H2X\""

//[NEWDAQ-REMOVED: Keithley] GPIBWrite2 "H2X"
//[NEWDAQ-REMOVED: Keithley] End

//[NEWDAQ-REMOVED: Keithley] Function RemoteGPIB()
//[NEWDAQ-REMOVED: Keithley] //execute "GPIBWrite \"H2X\""
//[NEWDAQ-REMOVED: Keithley] //GPIBWrite2 "C1P0B0N0X"
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 InterfaceClear
//[NEWDAQ-REMOVED: Keithley] End

//[NEWDAQ-REMOVED: Keithley] Function KeithleyFilter(FilterONOFF)

//[NEWDAQ-REMOVED: Keithley] Variable FilterONOFF

//[NEWDAQ-REMOVED: Keithley] If (FilterONOFF==1)
//[NEWDAQ-REMOVED: Keithley] 	GPIBWrite2 "P1X"
//[NEWDAQ-REMOVED: Keithley] else
//[NEWDAQ-REMOVED: Keithley] 	GPIBWrite2 "P0X"
//[NEWDAQ-REMOVED: Keithley] endif
//[NEWDAQ-REMOVED: Keithley] End

//[NEWDAQ-REMOVED: Keithley] Function KeithleyFilterRiseTime(TimeMicroSec)
//[NEWDAQ-REMOVED: Keithley] Variable TimeMicroSec

//[NEWDAQ-REMOVED: Keithley] Variable FilterTime

//[NEWDAQ-REMOVED: Keithley] if ((TimeMicroSec>=10)||(TimeMicroSec<=300000))
//[NEWDAQ-REMOVED: Keithley] If (floor(TimeMicroSec/3)*3==TimeMicroSec) // TimeMicrosec is a multiple of 3
//[NEWDAQ-REMOVED: Keithley] 	FilterTime=log((TimeMicroSec/30)^2)+1
//[NEWDAQ-REMOVED: Keithley] elseif (floor(TimeMicroSec/10)*10==TimeMicroSec)
//[NEWDAQ-REMOVED: Keithley] 	FilterTime=log((TimeMicroSec/10)^2)
//[NEWDAQ-REMOVED: Keithley] endif
//[NEWDAQ-REMOVED: Keithley] Print FilterTime, "T"+num2str(FilterTime)+"X"
//[NEWDAQ-REMOVED: Keithley] GPIBWrite2 "T"+num2str(FilterTime)+"X"
//[NEWDAQ-REMOVED: Keithley] else
//[NEWDAQ-REMOVED: Keithley] 	Print "Filter rise time out of range"
//[NEWDAQ-REMOVED: Keithley] endif

//[NEWDAQ-REMOVED: Keithley] End

//[NEWDAQ-REMOVED: Keithley] Function KeithleyBias(ctrlName,checked) : CheckBoxControl
//[NEWDAQ-REMOVED: Keithley] 	String ctrlName
//[NEWDAQ-REMOVED: Keithley] 	Variable checked
	
//[NEWDAQ-REMOVED: Keithley] 	NVAR BoardUD=G_BoardUD
//[NEWDAQ-REMOVED: Keithley] 	NVAR DeviceUD=G_DeviceUD
//[NEWDAQ-REMOVED: Keithley] 	NVAR KeithleyBiasEnabled=G_KeithleyBiasEnabled
	
//[NEWDAQ-REMOVED: Keithley] 	KeithleyBiasEnabled=checked
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 board=BoardUD
//[NEWDAQ-REMOVED: Keithley] 	GPIB2 device=DeviceUD
//[NEWDAQ-REMOVED: Keithley] 	if(checked==0)
//[NEWDAQ-REMOVED: Keithley] 		GPIBWrite2 "B0X"	
//[NEWDAQ-REMOVED: Keithley] 	else
//[NEWDAQ-REMOVED: Keithley] 		GPIBWrite2 "B1X"
//[NEWDAQ-REMOVED: Keithley] 	endif
//[NEWDAQ-REMOVED: Keithley] End

//[NEWDAQ-REMOVED: Keithley] //Function KeithleyBias(BiasONOFF)
//[NEWDAQ-REMOVED: Keithley] //
//[NEWDAQ-REMOVED: Keithley] //Variable BiasONOFF
//[NEWDAQ-REMOVED: Keithley] //
//[NEWDAQ-REMOVED: Keithley] //If (BiasONOFF==1)
//[NEWDAQ-REMOVED: Keithley] //	GPIBWrite2 "B1X"
//[NEWDAQ-REMOVED: Keithley] //else
//[NEWDAQ-REMOVED: Keithley] //	GPIBWrite2 "B0X"
//[NEWDAQ-REMOVED: Keithley] //endif
//[NEWDAQ-REMOVED: Keithley] //End
//[NEWDAQ-REMOVED: Keithley] Function KeithleyBiasVolt(BiasEntered)
//[NEWDAQ-REMOVED: Keithley] 	Variable BiasEntered
//[NEWDAQ-REMOVED: Keithley] 	NVAR TipBias = G_TipBias
//[NEWDAQ-REMOVED: Keithley] 	TipBias=BiasEntered
//[NEWDAQ-REMOVED: Keithley] 	String Bias = "V"+num2str(Tipbias)+"E-3X"
//[NEWDAQ-REMOVED: Keithley] 	GPIBWrite2 Bias
//[NEWDAQ-REMOVED: Keithley] 	Print "Enabled Keithley Bias at ",Bias
//[NEWDAQ-REMOVED: Keithley] End
