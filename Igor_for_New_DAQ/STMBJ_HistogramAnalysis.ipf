#pragma rtGlobals=1		// Use modern global access method.
//#include LVFunctions
Function Transmission(w,x) : FitFunc
	Wave w
	Variable x

	//CurveFitDialog/ These comments were created by the Curve Fitting dialog. Altering them will
	//CurveFitDialog/ make the function less convenient to work with in the Curve Fitting dialog.
	//CurveFitDialog/ Equation:
	//CurveFitDialog/ f(x) = Gam^2/((x-Eps)^2+(Gam^2))
	//CurveFitDialog/ End of Equation
	//CurveFitDialog/ Independent Variables 1
	//CurveFitDialog/ x
	//CurveFitDialog/ Coefficients 2
	//CurveFitDialog/ w[0] = Gam
	//CurveFitDialog/ w[1] = Eps

	return w[0]^2/((x-w[1])^2+(w[0]^2))
End

//You will see the 1/f^2 dependence in the frequency spectrum.
//Function Gauss_dbl(w,x) : FitFunc
//	Wave w
//	Variable x
//
//	//CurveFitDialog/ These comments were created by the Curve Fitting dialog. Altering them will
//	//CurveFitDialog/ make the function less convenient to work with in the Curve Fitting dialog.
//	//CurveFitDialog/ Equation:
//	//CurveFitDialog/ f(x) = K0*(e^(-(x-K1)^2/K2^2))+K3*(e^(-(x-K4)^2/K5^2))
//	//CurveFitDialog/ End of Equation
//	//CurveFitDialog/ Independent Variables 1
//	//CurveFitDialog/ x
//	//CurveFitDialog/ Coefficients 6
//	//CurveFitDialog/ w[0] = k0
//	//CurveFitDialog/ w[1] = k1
//	//CurveFitDialog/ w[2] = k2
//	//CurveFitDialog/ w[3] = K3
//	//CurveFitDialog/ w[4] = K4
//	//CurveFitDialog/ w[5] = K5
//
//	return w[0]*(e^(-(x-w[1])^2/w[2]^2))+w[3]*(e^(-(x-w[4])^2/w[5]^2))
//End


macro PullOutAnalysis()
	PullOutInitialize()
	PullOut_Analysis()

	NewPath/O Relocate "C:Data"
	NewPath/O SavedHist "C:DataAnalysis:SavedHist"
//	NewPath/O Saved2DHist "Macintosh HD:Users:Latha:Sync:AFM:Analysis:SavedHist:2DHist:"

end
Menu "PullOut"
"Decrease Included # /F4",/Q, DecreaseIncluded()
"Increase Included # /F2",/Q, IncreaseIncluded()
"Remove Pull Out /F3",/Q, RemovePullOutNumber(" ")
End  

//	TempW[0] = MaxExcursion
//	TempW[1] = Rate
//	TempW[2] = EngageStepSize
//	TempW[3] = ExcursionOffset
//	TempW[4] = BiasSave
//	TempW[5] = StartX-StopX
//	TempW[6] = Actual_Bias
//	TempW[7] = CurrentGain
//	TempW[8] = ExtensionGain
//	TempW[9] = CurrentVoltConversion
//	TempW[10] = TipBias
//	TempW[11] = Bias
//	TempW[12] = SeriesResistance
//	TempW[13] = EngageConductance
//	TempW[14] = EngageDelay
//	TempW[15] = MaxIVBias
//	TempW[16] = RiseTime
//	TempW[17] = ExternalBiasCheck
//	TempW[18] = VoltageOffset
//	TempW[19] = CurrentSuppress

function CubeRoot()

Wave xx, yy
Variable i, temp

For (i=0;i<100;i+=1)
	temp=xx[i]
	yy[i]=temp^3

endfor
end

Function PullOutInitialize()
	NewDataFolder/O root:Data

	Variable/G root:Data:G_DisplayNum=1
	Make/O/N=1 root:Data:POConductanceHist
	Variable/G root:Data:G_SmoothCond=1
	Variable/G root:Data:G_SmoothType=3
	Variable/G root:Data:G_SmoothLevel=11
	Variable/G root:Data:G_SmoothRepeat=1
	Variable/G root:Data:G_Total_Included=0
	Variable/G root:Data:G_Hist_Bin_Size=.0001
	Variable/G root:Data:G_Hist_Bin_Start=0
	Variable/G root:Data:G_HighCutOff=2.0
	Variable/G root:Data:G_zero_cutoff=0.0005
	Variable/G root:Data:G_DisplayFromIncluded = 0
	Variable/G root:Data:G_IncludedCurveNumber=0
	Variable/G root:Data:G_RedimStart=0
	Variable/G root:Data:G_RedimStop=1000
	Variable/G root:Data:G_SaveHist=0
	Variable/G root:Data:G_Noise=0
	Variable/G root:Data:G_Offline=0	//Offline button
	Variable/G root:Data:G_Setup=1	//Determines which setup is being used
	Variable/G root:Data:G_Overwrite=0	//whether to overwrite saved histogram

	Variable/G root:Data:G_ReadBlockCurrent=-1
	Variable/G root:Data:G_ReadBlockVoltage=-1
	Variable/G root:Data:G_ReadBlockConductance=-1
	Variable/G root:Data:G_mergecheck=1

	Variable/G root:Data:G_LoadIV=0
	Variable/G root:Data:G_IVStartPt=0
	Variable/G root:Data:G_IVEndPt=0
	Variable/G root:Data:G_HoldStart=0
	Variable/G root:Data:G_HoldEnd=0
	Variable/G root:Data:G_Counter
	Variable/G root:Data:G_2DLog=1
	Variable/G root:Data:G_AlignG=0.5
	Variable/G root:Data:G_2Dxmin=-0.5
	Variable/G root:Data:G_2Dxmax= 1.5
	Variable/G root:Data:G_BackgroundStart=0.95
	Variable/G root:Data:G_BackgroundEnd=0.96


	// Force Variables

	Variable/G root:Data:F_CantileverSlope=0.35
	Variable/G root:Data:F_CantileverSpringConstant=50
	Variable/G root:Data:G_SmoothForce=0
	Variable/G root:Data:G_GoodBadVal=0
	Variable/G root:Data:G_ForceHist_Bin_Size
	Variable/G root:Data:G_StepL_Cutoff
	Variable/G root:Data:G_StepS_Cutoff
	Variable/G root:Data:G_OverWrite
	Variable/G root:Data:G_Interpolate=0
	Variable/G root:Data:G_Num
	Variable/G root:Data:G_SmoothDummy=3
	Variable/G root:Data:G_Xmin=-0.5
	Variable/G root:Data:G_Xmax=0.5
	Variable/G root:Data:G_Ymin=-20
	Variable/G root:Data:G_Ymax=20
	Variable/G root:Data:G_NumXBin=500
	Variable/G root:Data:G_NumYBin=500
	Variable/G root:Data:G_StepMaxG
	Variable/G root:Data:G_StepMinG
	Variable/G root:Data:G_HistRatio_Cutoff
	Variable/G root:Data:G_ReadBlockForce=-1
	Variable/G root:Data:G_LoadForce=0


	PathInfo Relocate
	if (V_flag==1)
		Variable Slen=strlen(S_path)
		S_path=S_path[Slen-14,Slen-7]
	endif

	String/G root:Data:S_ForceName="foo"

	String/G root:Data:G_PathDate="06_04_19"//S_path
	String/G root:Data:G_Drive="C"
	String/G root:Data:G_histName=""		//Used in renaming functions in histogram analysis
	String/G root:Data:G_axisName="left"		//Used in defining which axis range to change
	String/G root:Data:G_LeftLabel="Conductance (G\B0\M)"	//Used in fixgraph and fixgraphbutton
	String/G root:Data:G_BottomLabel="Displacement (nm)"		//Used in fixgraph and fixgraphbutton
	//String/G root:Data:G_SavedHistPath="C:Users:Latha:Documents:Sync:AFM:Analysis:SavedHist:"
	String/G root:Data:G_SavedHistPath="C:DataAnalysis:SavedHist"
	Make/O/N=999 root:Data:IncludedNumbers=p+1
	Make/O/T/N=7 root:Data:TickLabel={"10\S2","10\S1","10\S0", "10\S-1","10\S-2","10\S-3","10\S-4","10\S-5","10\S-6","10\S-7","10\S-8"}
	Make/O/N=7 root:Data:TickPosLog={2,1,0,-1,-2,-3,-4,-5,-6,-7,-8}
	Make/O/N=1 root:Data:Conductance_D

	SetDataFolder root:Data
End

Window PullOut_Analysis() : Panel
	PauseUpdate; Silent 1		// building window...
	NewPanel /W=(1561,53,1863,564)
	ShowTools/A
	SetDrawLayer UserBack
	SetDrawEnv fsize= 14
	DrawText 215,461,"Counter"
	GroupBox box1,pos={21.00,34.00},size={250.00,116.00},title="Display Trace"
	GroupBox box1,font="Times New Roman",fSize=12
	SetVariable setvar4,pos={41.00,60.00},size={90.00,18.00},proc=DisplayPullOut,title="start #"
	SetVariable setvar4,limits={0,100000,1},value= root:Data:G_DisplayNum
	CheckBox check1,pos={164.00,61.00},size={97.00,15.00},title="Smooth Cond.?"
	CheckBox check1,variable= root:Data:G_SmoothCond
	SetVariable setvar0,pos={184.00,83.00},size={65.00,18.00},proc=DisplayPullOut,title="Type"
	SetVariable setvar0,limits={1,3,1},value= root:Data:G_SmoothType
	SetVariable setvar0_1,pos={184.00,105.00},size={65.00,18.00},proc=DisplayPullOut,title="Level"
	SetVariable setvar0_1,limits={1,100,1},value= root:Data:G_SmoothLevel
	GroupBox box101,pos={20.00,156.00},size={255.00,228.00},title="Histogram Analysis"
	GroupBox box101,font="Times New Roman",fSize=12
	ValDisplay valdisp0,pos={180.00,183.00},size={71.00,14.00},title="# Inc."
	ValDisplay valdisp0,fSize=10,format="%d",limits={0,0,0},barmisc={0,1000}
	ValDisplay valdisp0,value= #"root:Data:G_Total_Included"
	Button button102,pos={206.00,208.00},size={56.00,33.00},proc=DisplayHist,title="1D HIST"
	Button button102,labelBack=(65535,65535,65535),fSize=12,fStyle=0
	Button button102,fColor=(0,43520,65280)
	SetVariable setvar6,pos={28.00,183.00},size={71.00,18.00},proc=SetBinSize,title="Bin"
	SetVariable setvar6,limits={0,10000,0},value= root:Data:G_Hist_Bin_size
	SetVariable setvar0_2,pos={174.00,127.00},size={75.00,18.00},proc=DisplayPullOut,title="Repeat"
	SetVariable setvar0_2,limits={0,100,1},value= root:Data:G_SmoothRepeat
	SetVariable setvar12,pos={27.00,207.00},size={100.00,18.00},title="Hist Max"
	SetVariable setvar12,format="%3.1e"
	SetVariable setvar12,limits={0,10000,0},value= root:Data:G_HighCutOff
	CheckBox check2,pos={152.00,76.00},size={76.00,14.00},disable=1,proc=FilterPullOutData,title="Filter Force?"
	CheckBox check2,value= 0
	CheckBox check3,pos={152.00,98.00},size={90.00,14.00},disable=1,title="Smooth Force?"
	CheckBox check3,value= 0
	SetVariable setvar8,pos={102.00,183.00},size={75.00,18.00},title="Zero"
	SetVariable setvar8,limits={0,10000,0},value= root:Data:G_Zero_cutoff
	CheckBox check6,pos={39.00,94.00},size={97.00,15.00},proc=FromIncludedCheck,title="From Included?"
	CheckBox check6,value= 0
	SetVariable setvar14,pos={36.00,118.00},size={90.00,15.00},disable=1,proc=DisplayIncludedNumbers,title="Inc #"
	SetVariable setvar14,limits={0,50000,1},value= root:Data:G_IncludedCurveNumber
	SetVariable setvar3,pos={16.00,446.00},size={108.00,18.00},proc=ChangePath,title="Path"
	SetVariable setvar3,fStyle=1,value= root:Data:G_PathDate
	Button button0,pos={49.00,270.00},size={50.00,20.00},proc=RedimButton,title="Redim"
	Button button0,fSize=12
	SetVariable setvar13,pos={29.00,252.00},size={65.00,18.00},title="Start"
	SetVariable setvar13,format="%d"
	SetVariable setvar13,limits={1,100000,0},value= root:Data:G_RedimStart
	SetVariable setvar15,pos={116.00,252.00},size={65.00,18.00},proc=SetRedimStopProc,title="Stop"
	SetVariable setvar15,format="%d"
	SetVariable setvar15,limits={0,100000,0},value= root:Data:G_RedimStop
	CheckBox check8,pos={204.00,253.00},size={63.00,15.00},title="Save Hist"
	CheckBox check8,variable= root:Data:G_SaveHist
	SetVariable setvar5,pos={135.00,446.00},size={56.00,18.00},title="Drive"
	SetVariable setvar5,fStyle=1,value= root:Data:G_Drive
	Button button1,pos={115.00,270.00},size={63.00,20.00},proc=Plus1000,title="Plus1000"
	Button button1,fSize=12
	SetVariable setvar16,pos={16.00,466.00},size={50.00,18.00},title="Setup"
	SetVariable setvar16,limits={1,2,0},value= root:Data:G_Setup
	CheckBox check4,pos={204.00,273.00},size={66.00,15.00},title="Overwrite"
	CheckBox check4,variable= root:Data:G_Overwrite
	CheckBox check199,pos={76.00,466.00},size={56.00,15.00},title="Merged"
	CheckBox check199,variable= root:Data:G_mergecheck
	Button button5,pos={197.00,60.00},size={55.00,16.00},disable=1,proc=DisplayHistButton,title="Display"
	Button button5,fSize=12
	TitleBox title2,pos={27.00,134.00},size={51.00,12.00},disable=1,title="Axis Scaling"
	TitleBox title2,frame=0
	Button button6,pos={24.00,111.00},size={130.00,16.00},disable=1,proc=CopyCurrentTrace,title="Copy Current Trace"
	Button button6,fSize=12
	Button button8,pos={134.00,153.00},size={129.00,16.00},disable=1,proc=LinLinButton,title="Linear-Linear Scaling"
	Button button8,fSize=12
	Button button9,pos={25.00,153.00},size={103.00,16.00},disable=1,proc=LogLogButton,title="Log-Log Scaling"
	Button button9,fSize=12
	SetVariable setvar1,pos={26.00,85.00},size={234.00,15.00},disable=1,proc=HistogramSearch,title="Search"
	SetVariable setvar1,fStyle=0
	SetVariable setvar1,limits={-inf,inf,0},value= root:Data:G_histName,live= 1
	PopupMenu popup3,pos={23.00,59.00},size={148.00,20.00},bodyWidth=95,disable=1,proc=DisplayListMenu,title="Display List"
	PopupMenu popup3,mode=2,popvalue="wave0",value= #"\"textWave0;wave0;Conductance_D_Raw;Con_YWave;Con_XWave;\""
	Button button7,pos={28.00,540.00},size={60.00,16.00},disable=1,proc=FixGraphButton,title="FixGraph"
	Button button7,fSize=12
	Button button08,pos={93.00,192.00},size={75.00,16.00},disable=1,proc=FixGraphButton,title="FixGraph2D"
	Button button08,fSize=12
	Button button05,pos={174.00,192.00},size={95.00,16.00},disable=1,proc=UndoFixGraphButton,title="Undo FixGraph"
	Button button05,fSize=12
	ValDisplay valdisp0_1,pos={28.00,231.00},size={109.00,17.00},title="Noise"
	ValDisplay valdisp0_1,format="%2.3e",limits={0,0,0},barmisc={0,1000}
	ValDisplay valdisp0_1,value= #"root:Data:G_Noise"
	SetVariable setvar17,pos={26.00,337.00},size={80.00,18.00},title="IV Start"
	SetVariable setvar17,format="%d"
	SetVariable setvar17,limits={0,100000,0},value= root:Data:G_IVStartPt
	SetVariable setvar18,pos={114.00,337.00},size={80.00,18.00},title="IV End"
	SetVariable setvar18,format="%d",limits={0,100000,0},value= root:Data:G_IVEndPt
	CheckBox check5,pos={205.00,338.00},size={54.00,15.00},title="Load IV"
	CheckBox check5,variable= root:Data:G_LoadIV
	GroupBox box102,pos={18.00,37.00},size={259.00,181.00},disable=1,title="Histogram Display"
	GroupBox box102,font="Times New Roman",fSize=12
	Button button103,pos={206.00,296.00},size={56.00,33.00},proc=Hist2D,title="2D HIST"
	Button button103,labelBack=(65535,65535,65535),fSize=12,fStyle=0
	Button button103,fColor=(65535,16385,16385)
	SetVariable setvar19,pos={25.00,315.00},size={80.00,18.00},title="2D X min"
	SetVariable setvar19,format="%1.1f",limits={-5,5,0},value= root:Data:G_2Dxmin
	SetVariable setvar20,pos={117.00,314.00},size={80.00,18.00},title="2D X max"
	SetVariable setvar20,format="%1.1f"
	SetVariable setvar20,limits={0,100000,0},value= root:Data:G_2Dxmax
	CheckBox check7,pos={130.00,292.00},size={52.00,15.00},title="2D Log"
	CheckBox check7,variable= root:Data:G_2DLog
	SetVariable setvar21,pos={25.00,293.00},size={90.00,18.00},title="2D G Align"
	SetVariable setvar21,format="%1.2f"
	SetVariable setvar21,limits={0,100000,0},value= root:Data:G_AlignG
	Button button09,pos={134.00,133.00},size={129.00,16.00},disable=1,proc=LinLogButton,title="Linear-Log Scaling"
	Button button09,fSize=12
	TitleBox title3,pos={25.00,175.00},size={80.00,12.00},disable=1,title="Graph Appearance"
	TitleBox title3,frame=0
	TabControl Tab_0,pos={7.00,8.00},size={283.00,382.00},proc=TabProc
	TabControl Tab_0,tabLabel(0)="Hist Anal.",tabLabel(1)="Display"
	TabControl Tab_0,tabLabel(2)="Params",tabLabel(3)="Force",value= 0
	SetVariable servar0,pos={61.00,390.00},size={50.00,20.00},disable=1
	GroupBox box2,pos={71.00,156.00},size={154.00,225.00},disable=1,title="Parameters"
	GroupBox box2,labelBack=(56576,56576,56576),font="Times New Roman",fSize=14
	GroupBox box2,frame=0
	ValDisplay valdisp1,pos={85.00,181.00},size={125.00,13.00},disable=1,title="Speed (nm/s)"
	ValDisplay valdisp1,fStyle=1,limits={0,0,0},barmisc={0,1000}
	ValDisplay valdisp1,value= #"root:Data:POParameter_Display[1]"
	ValDisplay valdisp2,pos={85.00,203.00},size={125.00,13.00},disable=1,title="Distance (nm)"
	ValDisplay valdisp2,fStyle=1,limits={0,0,0},barmisc={0,1000}
	ValDisplay valdisp2,value= #"root:Data:POParameter_Display[0]"
	ValDisplay valdisp3,pos={85.00,249.00},size={125.00,13.00},disable=1,title="Applied V (V)"
	ValDisplay valdisp3,format="%3.3f",fStyle=1,limits={0,0,0},barmisc={0,1000}
	ValDisplay valdisp3,value= #"root:Data:POParameter_Display[10]/1000"
	ValDisplay valdisp4,pos={85.00,272.00},size={125.00,13.00},disable=1,title="Hit G            "
	ValDisplay valdisp4,format="%3.1f",fStyle=1,limits={0,0,0},barmisc={0,1000}
	ValDisplay valdisp4,value= #"root:Data:POParameter_Display[13]"
	ValDisplay valdisp5,pos={85.00,294.00},size={125.00,13.00},disable=1,title="Suppress I "
	ValDisplay valdisp5,format="%3.1e",fStyle=1,limits={0,0,0},barmisc={0,1000}
	ValDisplay valdisp5,value= #"root:Data:POParameter_Display[19]"
	ValDisplay valdisp6,pos={85.00,317.00},size={125.00,13.00},disable=1,title="Gain           "
	ValDisplay valdisp6,fStyle=1,limits={0,0,0},barmisc={0,1000}
	ValDisplay valdisp6,value= #"6-log(root:Data:POParameter_Display[9])"
	ValDisplay valdisp7,pos={85.00,340.00},size={125.00,13.00},disable=1,title="Bias Save      "
	ValDisplay valdisp7,fStyle=1,limits={0,0,0},barmisc={0,1000}
	ValDisplay valdisp7,value= #"root:Data:POParameter_Display[4]"
	ValDisplay valdisp8,pos={85.00,363.00},size={125.00,13.00},disable=1,title="Series R   "
	ValDisplay valdisp8,fStyle=1,limits={0,0,0},barmisc={0,1000}
	ValDisplay valdisp8,value= #"root:Data:POParameter_Display[12]"
	ValDisplay valdisp9,pos={85.00,226.00},size={125.00,13.00},disable=1,title="Actual D (nm)"
	ValDisplay valdisp9,fStyle=1,limits={0,0,0},barmisc={0,1000}
	ValDisplay valdisp9,value= #"root:Data:POParameter_Display[5]"
	ValDisplay Counter,pos={212.00,463.00},size={70.00,23.00},fSize=16,format="%d"
	ValDisplay Counter,fStyle=1,limits={0,0,0},barmisc={0,1000}
	ValDisplay Counter,value= #"root:Data:G_Counter"
	SetVariable Slope,pos={19.00,183.00},size={88.00,15.00},disable=1,title="Slope"
	SetVariable Slope,limits={-inf,inf,0},value= root:Data:F_CantileverSlope
	SetVariable forceK,pos={115.00,183.00},size={50.00,15.00},disable=1,title="K"
	SetVariable forceK,limits={-inf,inf,0},value= root:Data:F_CantileverSpringConstant
	SetVariable smoothForce,pos={170.00,183.00},size={110.00,15.00},disable=1,title="Smooth F Level"
	SetVariable smoothForce,value= root:Data:G_SmoothForce
	SetVariable setvar2,pos={18.00,209.00},size={130.00,15.00},disable=1,title="Step Length Cutoff"
	SetVariable setvar2,format="%1.4f"
	SetVariable setvar2,limits={-inf,inf,0},value= root:Data:G_StepL_Cutoff
	SetVariable setvar7,pos={18.00,230.00},size={130.00,15.00},disable=1,title="Slope Cutoff"
	SetVariable setvar7,format="%1.2e"
	SetVariable setvar7,limits={-inf,inf,0},value= root:Data:G_StepS_Cutoff
	SetVariable setvar9,pos={18.00,251.00},size={130.00,15.00},disable=1,title="High Cutoff (G)"
	SetVariable setvar9,format="%1.7f"
	SetVariable setvar9,limits={-inf,inf,0},value= root:Data:G_StepMaxG
	SetVariable setvar09,pos={18.00,273.00},size={130.00,15.00},disable=1,title="Low Cutoff (G)"
	SetVariable setvar09,format="%1.7f"
	SetVariable setvar09,limits={-inf,inf,0},value= root:Data:G_StepMinG
	SetVariable setvar10,pos={18.00,294.00},size={130.00,15.00},disable=1,title="Smooth Dummy"
	SetVariable setvar10,format="%d"
	SetVariable setvar10,limits={-inf,inf,0},value= root:Data:G_SmoothDummy
	SetVariable setvar04,pos={192.00,209.00},size={80.00,15.00},disable=1,title="2D Xmin"
	SetVariable setvar04,format="%1.2f",limits={-inf,inf,0},value= root:Data:G_Xmin
	SetVariable setvar05,pos={192.00,230.00},size={80.00,15.00},disable=1,title="2D Xmax"
	SetVariable setvar05,format="%1.2f",limits={-inf,inf,0},value= root:Data:G_Xmax
	SetVariable setvar06,pos={192.00,251.00},size={80.00,15.00},disable=1,title="2D Ymin"
	SetVariable setvar06,format="%1.2f",limits={-inf,inf,0},value= root:Data:G_Ymin
	SetVariable setvar07,pos={192.00,273.00},size={80.00,15.00},disable=1,title="2D Ymax"
	SetVariable setvar07,format="%1.2f",limits={-inf,inf,0},value= root:Data:G_Ymax
	SetVariable setvar08,pos={192.00,294.00},size={80.00,15.00},disable=1,title="2D Xbin"
	SetVariable setvar08,format="%1.2f"
	SetVariable setvar08,limits={-inf,inf,0},value= root:Data:G_NumXBin
	SetVariable setvar11,pos={192.00,315.00},size={80.00,15.00},disable=1,title="2D Ybin"
	SetVariable setvar11,format="%1.2f"
	SetVariable setvar11,limits={-inf,inf,0},value= root:Data:G_NumYBin
	CheckBox check9,pos={20.00,161.00},size={66.00,15.00},disable=1,title="Load Force"
	CheckBox check9,variable= root:Data:G_LoadForce
	Button button104,pos={193.00,346.00},size={79.00,32.00},disable=1,proc=Force2DButton,title="2D ANAL"
	Button button104,labelBack=(65535,65535,65535),fSize=12,fStyle=0
	Button button104,fColor=(0,43520,65280)
	SetVariable setvar22,pos={18.00,315.00},size={100.00,15.00},disable=1,title="FName"
	SetVariable setvar22,limits={-inf,inf,0},value= root:Data:S_ForceName
	SetVariable setvar23,pos={18.00,337.00},size={65.00,15.00},disable=1,title="Start"
	SetVariable setvar23,format="%d"
	SetVariable setvar23,limits={1,100000,0},value= root:Data:G_RedimStart
	SetVariable setvar24,pos={105.00,337.00},size={65.00,15.00},disable=1,proc=SetRedimStopProc,title="Stop"
	SetVariable setvar24,format="%d"
	SetVariable setvar24,limits={0,100000,0},value= root:Data:G_RedimStop
	Button button2,pos={69.00,358.00},size={50.00,20.00},disable=1,proc=RedimButton,title="Redim"
	Button button2,fSize=12
	SetVariable setvar25,pos={27.00,360.00},size={100.00,18.00},title="Hold Start"
	SetVariable setvar25,format="%d"
	SetVariable setvar25,limits={0,100000,0},value= root:Data:G_HoldStart
	SetVariable setvar26,pos={134.00,360.00},size={100.00,18.00},title="Hold End"
	SetVariable setvar26,format="%d",limits={0,100000,0},value= root:Data:G_HoldEnd
	SetVariable BackStart,pos={16.00,403.00},size={165.00,18.00},title="Background Start (fraction)"
	SetVariable BackStart,format="%1.3f"
	SetVariable BackStart,limits={-inf,inf,0},value= root:Data:G_BackgroundStart
	SetVariable BackEnd,pos={16.00,422.00},size={165.00,18.00},title="Background End (fraction)  "
	SetVariable BackEnd,format="%1.3f"
	SetVariable BackEnd,limits={-inf,inf,0},value= root:Data:G_BackgroundEnd
EndMacro

Function TabProc(ctrlName,tabNum) : TabControl
	String ctrlName
	Variable tabNum
	NVAR DisplayFromIncluded = root:Data:G_DisplayFromIncluded

	switch(tabNum)
		case 0:
			//cosmetic tab disable
			PopupMenu popup3 disable =1
			Button button5 disable=1
			Button button6 disable=1
			SetVariable setvar1 disable=1
			Titlebox title2 disable = 1
			GroupBox Box102 disable = 1
			titlebox title3 disable = 1
			Button button09 disable =1
			Button button9 disable =1
			Button button8 disable = 1
			Button button7 disable = 1
			//Button button07 disable =1
			Button button08 disable =1
			Button button05 disable = 1
			//Hist Anal tab enable
			Button button0 disable=0
			Button button1 disable=0
			SetVariable setvar4 disable=0
			GroupBox Box1 disable = 0
			GroupBox box101 disable = 0
			Button button102 disable =0
			Button button103 disable =0
			Button button104 disable =1
			Checkbox check1 disable = 0
			Checkbox check4 disable =  0
			Checkbox check5 disable =  0
			Checkbox check6 disable = 0
			Checkbox check7 disable = 0
			Checkbox check8 disable = 0
			Checkbox check9 disable = 1
			SetVariable setvar0_1 disable = 0 
			SetVariable setvar0_2 disable = 0
			SetVariable setvar6 disable = 0
			SetVariable setvar8 disable = 0
			SetVariable setvar12 disable = 0
			SetVariable setvar13 disable = 0
			SetVariable setvar14 disable = (1-DisplayFromIncluded)
			SetVariable setvar15 disable = 0
			SetVariable setvar17 disable = 0
			SetVariable setvar18 disable = 0 
			SetVariable setvar19 disable = 0 
			SetVariable setvar20 disable = 0
			SetVariable setvar21 disable = 0
			SetVariable setvar25 disable = 0
			SetVariable setvar26 disable = 0
			SetVariable setvar0 disable = 0
			ValDisplay valdisp0 disable = 0
			ValDisplay valdisp0_1 disable = 0
			//enable Params tab
			ValDisplay valdisp1 disable = 1
			ValDisplay valdisp2 disable = 1
			ValDisplay valdisp3 disable = 1
			ValDisplay valdisp4 disable = 1
			ValDisplay valdisp5 disable = 1
			ValDisplay valdisp6 disable = 1
			ValDisplay valdisp7 disable = 1
			ValDisplay valdisp8 disable = 1
			ValDisplay valdisp9 disable = 1
			GroupBox box2 disable = 1
			SetVariable slope disable = 1
			SetVariable forceK disable = 1
			SetVariable smoothForce disable = 1
			SetVariable setvar2 disable=1
			SetVariable setvar7 disable=1
			SetVariable setvar9 disable=1
			SetVariable setvar04 disable=1
			SetVariable setvar05 disable=1
			SetVariable setvar06 disable=1
			SetVariable setvar07 disable=1
			SetVariable setvar08 disable=1
			SetVariable setvar09 disable=1
			SetVariable setvar10 disable=1
			SetVariable setvar11 disable=1
			SetVariable setvar22 disable=1
			SetVariable setvar23 disable=1
			SetVariable setvar24 disable=1
			Button button2 disable=1
			break
		case 1:
			//cosmetics tab enable
			PopupMenu popup3 disable =0
			Button button5 disable=0
			Button button6 disable=0
			SetVariable setvar1 disable=0
			Titlebox title2 disable = 0
			GroupBox Box102 disable = 0
			titlebox title3 disable = 0
			Button button09 disable =0
			Button button9 disable =0
			Button button8 disable = 0
			//Button button07 disable =0
			Button button08 disable =0
			Button button05 disable = 0
			//Hist Anal tab disable
			Button button0 disable=1
			Button button1 disable=1
			SetVariable setvar4 disable=1
			GroupBox Box1 disable = 1
			GroupBox box101 disable = 1
			Button button102 disable =1
			Button button103 disable =1
			Button button104 disable =1
			Checkbox check1 disable = 1
			Checkbox check4 disable =  1
			Checkbox check5 disable =  1
			Checkbox check6 disable = 1
			Checkbox check7 disable = 1
			Checkbox check8 disable = 1
			Checkbox check9 disable = 1
			SetVariable setvar0_1 disable = 1 
			SetVariable setvar0_2 disable = 1
			SetVariable servar0 disable = 1
			SetVariable setvar6 disable = 1
			SetVariable setvar8 disable = 1
			SetVariable setvar12 disable = 1
			SetVariable setvar13 disable = 1
			SetVariable setvar14 disable = 1
			SetVariable setvar15 disable = 1
			SetVariable setvar17 disable = 1
			SetVariable setvar18 disable = 1 
			SetVariable setvar19 disable = 1 
			SetVariable setvar20 disable = 1
			SetVariable setvar21 disable = 1
			ValDisplay valdisp0 disable = 1
			ValDisplay valdisp0_1 disable = 1
			SetVariable setvar0 disable =1
			//disable Params tab
			ValDisplay valdisp1 disable = 1
			ValDisplay valdisp2 disable = 1
			ValDisplay valdisp3 disable = 1
			ValDisplay valdisp4 disable = 1
			ValDisplay valdisp5 disable = 1
			ValDisplay valdisp6 disable = 1
			ValDisplay valdisp7 disable = 1
			ValDisplay valdisp8 disable =1
			ValDisplay valdisp9 disable = 1
			GroupBox box2 disable = 1
			SetVariable slope disable = 1
			SetVariable forceK disable = 1
			SetVariable smoothForce disable = 1
			SetVariable setvar2 disable=1
			SetVariable setvar7 disable=1
			SetVariable setvar9 disable=1
			SetVariable setvar04 disable=1
			SetVariable setvar05 disable=1
			SetVariable setvar06 disable=1
			SetVariable setvar07 disable=1
			SetVariable setvar08 disable=1
			SetVariable setvar09 disable=1
			SetVariable setvar10 disable=1
			SetVariable setvar11 disable=1
			SetVariable setvar22 disable=1
			SetVariable setvar23 disable=1
			SetVariable setvar24 disable=1
			SetVariable setvar25 disable = 1
			SetVariable setvar26 disable = 1
			Button button2 disable=1
			break
		case 2:
			//cosmetic tab disable
			PopupMenu popup3 disable =1
			Button button5 disable=1
			Button button6 disable=1
			SetVariable setvar1 disable=1
			Titlebox title2 disable = 1
			GroupBox Box102 disable = 1
			titlebox title3 disable = 1
			Button button09 disable =1
			Button button9 disable =1
			Button button8 disable = 1
			Button button7 disable = 1
			Button button08 disable =1
			Button button05 disable = 1
			//display tab disable
			Button button0 disable=1
			Button button1 disable=1
			SetVariable setvar4 disable=0
			GroupBox Box1 disable = 0
			GroupBox box101 disable = 1
			Button button102 disable =1
			Button button103 disable =1
			Button button104 disable =1
			Checkbox check1 disable =0
			Checkbox check4 disable = 1
			Checkbox check5 disable =  1
			Checkbox check6 disable = 0
			Checkbox check7 disable = 1
			Checkbox check8 disable = 1
			Checkbox check9 disable = 1
			SetVariable setvar0_1 disable = 0
			SetVariable setvar0_2 disable =0
			SetVariable setvar6 disable =1
			SetVariable setvar8 disable = 1
			SetVariable setvar12 disable = 1
			SetVariable setvar13 disable = 1
			SetVariable setvar15 disable = 1
			SetVariable setvar14 disable = (1-DisplayFromIncluded)
			SetVariable setvar17 disable = 1
			SetVariable setvar18 disable = 1 
			SetVariable setvar19 disable = 1
			SetVariable setvar20 disable = 1
			SetVariable setvar21 disable =1
			SetVariable setvar0 disable =0
			ValDisplay valdisp0 disable = 1
			ValDisplay valdisp0_1 disable = 1
			//enable Params tab
			ValDisplay valdisp1 disable = 0
			ValDisplay valdisp2 disable = 0
			ValDisplay valdisp3 disable = 0
			ValDisplay valdisp4 disable = 0
			ValDisplay valdisp5 disable = 0
			ValDisplay valdisp6 disable = 0
			ValDisplay valdisp7 disable = 0
			ValDisplay valdisp8 disable = 0
			ValDisplay valdisp9 disable = 0
			GroupBox box2 disable = 0
			SetVariable slope disable = 1
			SetVariable forceK disable = 1
			SetVariable smoothForce disable = 1
			SetVariable setvar2 disable=1
			SetVariable setvar7 disable=1
			SetVariable setvar9 disable=1
			SetVariable setvar04 disable=1
			SetVariable setvar05 disable=1
			SetVariable setvar06 disable=1
			SetVariable setvar07 disable=1
			SetVariable setvar08 disable=1
			SetVariable setvar09 disable=1
			SetVariable setvar10 disable=1
			SetVariable setvar11 disable=1
			SetVariable setvar22 disable=1
			SetVariable setvar23 disable=1
			SetVariable setvar24 disable=1
			SetVariable setvar25 disable = 1
			SetVariable setvar26 disable = 1
			Button button2 disable=1
			break

		case 3:
			//cosmetic tab disable
			PopupMenu popup3 disable =1
			Button button5 disable=1
			Button button6 disable=1
			SetVariable setvar1 disable=1
			Titlebox title2 disable = 1
			GroupBox Box102 disable = 1
			titlebox title3 disable = 1
			Button button09 disable =1
			Button button9 disable =1
			Button button8 disable = 1
			Button button7 disable = 1
			Button button08 disable =1
			Button button05 disable = 1
			//display tab disable
			Button button0 disable=1
			Button button1 disable=1
			SetVariable setvar4 disable=0
			GroupBox Box1 disable = 0
			GroupBox box101 disable = 1
			Button button102 disable =1
			Button button103 disable =1
			Button button104 disable =0
			Checkbox check1 disable =0
			Checkbox check4 disable = 1
			Checkbox check5 disable =  1
			Checkbox check6 disable = 0
			Checkbox check7 disable = 1
			Checkbox check8 disable = 1
			Checkbox check9 disable = 0
			SetVariable setvar0_1 disable = 0
			SetVariable setvar0_2 disable =0
			SetVariable setvar6 disable =1
			SetVariable setvar8 disable = 1
			SetVariable setvar12 disable = 1
			SetVariable setvar13 disable = 1
			SetVariable setvar15 disable = 1
			SetVariable setvar14 disable = (1-DisplayFromIncluded)
			SetVariable setvar17 disable = 1
			SetVariable setvar18 disable = 1 
			SetVariable setvar19 disable = 1
			SetVariable setvar20 disable = 1
			SetVariable setvar21 disable =1
			SetVariable setvar0 disable =0
			ValDisplay valdisp0 disable = 1
			ValDisplay valdisp0_1 disable = 1
			//enable Params tab
			ValDisplay valdisp1 disable = 1
			ValDisplay valdisp2 disable = 1
			ValDisplay valdisp3 disable = 1
			ValDisplay valdisp4 disable = 1
			ValDisplay valdisp5 disable = 1
			ValDisplay valdisp6 disable = 1
			ValDisplay valdisp7 disable = 1
			ValDisplay valdisp8 disable = 1
			ValDisplay valdisp9 disable = 1
			GroupBox box2 disable = 1
			SetVariable slope disable = 0
			SetVariable forceK disable = 0
			SetVariable smoothForce disable = 0
			SetVariable setvar2 disable=0
			SetVariable setvar7 disable=0
			SetVariable setvar9 disable=0
			SetVariable setvar04 disable=0
			SetVariable setvar05 disable=0
			SetVariable setvar06 disable=0
			SetVariable setvar07 disable=0
			SetVariable setvar08 disable=0
			SetVariable setvar09 disable=0
			SetVariable setvar10 disable=0
			SetVariable setvar11 disable=0
			SetVariable setvar22 disable=0
			SetVariable setvar23 disable=0
			SetVariable setvar24 disable=0
			SetVariable setvar25 disable = 1
			SetVariable setvar26 disable = 1
			Button button2 disable=0
			break
	endswitch
	return 0
end

Function DisplayListMenu(pa) : PopupMenuControl
	STRUCT WMPopupAction &pa

	SVAR G_histName = root:Data:G_histName
	
	switch( pa.eventCode )
		case 2: // mouse up
			G_histName = pa.popStr
			break
	endswitch

	return 0
End

Function HistogramSearch(sva) : SetVariableControl
	STRUCT WMSetVariableAction &sva

	SVAR G_histName = root:Data:G_histName
	String searchName = ""
	String searchList = ""
	
	switch( sva.eventCode )
		case 1: // mouse up
		case 2: // Enter key
		case 3: // Live update
			G_histName = sva.sval
			searchName = "*" + G_histName + "*"
			searchList = WaveList(searchName, ";", "")
			searchList = "\"" + searchList + "\""	
			if (stringmatch(G_histName, "") == 1)
				searchList = "\"" + WaveList("PO*", ";", "") + WaveList("total*", ";","") + "\""
			endif	
			PopupMenu popup3 value=#searchList
			break
	endswitch

	return 0
End

Function DisplayHistButton(ba) : ButtonControl
	STRUCT WMButtonAction &ba
	
	SVAR G_histName = root:Data:G_histName
	
	switch( ba.eventCode )
		case 2: // mouse up
			if (stringmatch(G_histName,"")==1) //if input is no name, then exit
				break
			endif
			
			switch(WaveDims($G_histname))
				case 0:
					Print "Wave does not exist"
					break
				case 1: 
					Display $G_histName
					break
				case 2:
					Display;AppendImage $G_histName
					ModifyImage $G_histName ctab= {*,150,Geo,1}
					break
			endswitch
			break
	endswitch

	return 0
End

Function DuplicateButtons(buttonType) : ButtonControl
	String buttonType
	
	SVAR G_histName = root:Data:G_histName
	String newName = G_histName
	Variable buttonNum = 0
	
	if (stringmatch(buttonType, "button2")) // LinHist
		buttonNum = 2
	elseif (stringmatch(buttonType, "button0")) // LogHist
		buttonNum = 0
	elseif (stringmatch(buttonType, "button1")) // 2DHist
		buttonNum = 1
	endif
		
	switch (buttonNum)
		case 2:
			if (WaveExists(POConductanceHist)==0) //checks if histogram has been made
				DoAlert 0, "No linear histogram found. Run histogram."
			elseif (stringmatch(G_histName,"")==1) //if input is no name, then exit
				break
			elseif (WaveExists($G_histName)==0) //if it is not a duplicate wave name then create wave
				Duplicate POConductanceHist $G_histName
			elseif (WaveExists($G_histName)==1) //if the wave name is in use, indicate that the wave is in use
				Prompt newName, "This wave name is in use. Please choose another name: "
				DoPrompt "Error", newName
				if(V_flag == 1)
					break
				endif
				G_histName = newName
				DuplicateButtons("button2")
			endif
			break
		case 0:
			if (WaveExists(POConductanceHistLog)==0) //checks if histogram has been made
				DoAlert 0, "No Log histogram found. Run histogram."
			elseif (stringmatch(G_histName,"")==1) //if input is no name, then exit
				break
			elseif (WaveExists($G_histName)==0) //if it is not a duplicate wave name then create wave
				Duplicate POConductanceHistLog $G_histName
			elseif (WaveExists($G_histName)==1) //if the wave name is in use, indicate that the wave is in use
				Prompt newName, "This wave name is in use. Please choose another name: "
				DoPrompt "Error", newName
				if(V_flag == 1)
					break
				endif
				G_histName = newName
				DuplicateButtons("button0")
			endif
			break
		case 1:
			if (WaveExists(total2dhist)==0) //checks if histogram has been made
				Prompt newName, "No 2D histogram found. Run histogram."
				DoPrompt "Error", newName
			elseif (stringmatch(G_histName,"")==1) //if input is no name, then exit
				break
			elseif (WaveExists($G_histName)==0) //if it is not a duplicate wave name then create wave
				Duplicate total2dhist $G_histName
			elseif (WaveExists($G_histName)==1) //if the wave name is in use, indicate that the wave is in use
				Prompt newName, "This wave name is in use. Please choose another name: "
				DoPrompt "Error", newName
				if(V_flag == 1)
					break
				endif
				G_histName = newName
				DuplicateButtons("button1")
			endif
			break
	endswitch

	return 0
End

Function CopyCurrentTrace(ba) : ButtonControl
	STRUCT WMButtonAction &ba
	
	NVAR G_DisplayNum = root:Data:G_DisplayNum
	String traceName
	
	switch( ba.eventCode )
		case 2: // mouse up
			traceName = "Trace" + num2str(G_DisplayNum)
			Duplicate /O POConductance_Display $traceName	
			break
	endswitch

	return 0
End

Function FixGraphButton(ctrlName) : ButtonControl
	String ctrlName
	
	SVAR G_LeftLabel = root:Data:G_LeftLabel
	SVAR G_BottomLabel = root:Data:G_BottomLabel
		
	if ((stringmatch(GetAxisLabel("", "left"), "Conductance (G\B0\M)") == 1)&&(stringmatch(GetAxisLabel("", "bottom"), "Displacement (nm)")==1))
		//Do Nothing
	elseif ((stringmatch(GetAxisLabel("", "left"), "Counts") == 1)&&(stringmatch(GetAxisLabel("", "bottom"), "Conductance (G\B0\M)")==1))
		//Do Nothing
	else
		G_LeftLabel = GetAxisLabel("", "left")
		G_BottomLabel = GetAxisLabel("", "bottom")
	endif
	
	ModifyGraph axisOnTop=1
	ModifyGraph tick=2,fSize=14,axThick=1.5,standoff=0
	ModifyGraph mirror=2
	if (stringmatch(ctrlName, "button8") == 1)
		Label left "Conductance (G\B0\M)";DelayUpdate
		Label bottom "Displacement (nm)"
		ModifyGraph userticks(left)={TickPosLog,TickLabel}
	elseif (stringmatch(ctrlName, "button7") == 1)
		Label left "Counts";DelayUpdate
		Label bottom "Conductance (G\B0\M)"
	endif	
end

Function UndoFixGraphButton(ctrlName) : ButtonControl
	String ctrlName
	String temp_LeftLabel
	String temp_BottomLabel
	
	SVAR G_LeftLabel = root:Data:G_LeftLabel
	SVAR G_BottomLabel = root:Data:G_BottomLabel
	
	temp_LeftLabel = G_LeftLabel
	temp_BottomLabel = G_BottomLabel 

	G_LeftLabel = GetAxisLabel("", "left")
	G_BottomLabel = GetAxisLabel("", "bottom")
	
	ModifyGraph axisOnTop=1
	ModifyGraph tick=2,fSize=14,axThick=1.5,standoff=0
	ModifyGraph mirror=2
	Label left temp_LeftLabel;DelayUpdate
	Label bottom temp_BottomLabel
end

Function SetRange(sva) : SetVariableControl
	STRUCT WMSetVariableAction &sva
	
	NVAR G_axisMin = root:Data:G_axisMin
	NVAR G_axisMax = root:Data:G_axisMax
	SVAR G_axisName = root:Data:G_axisName
	
	switch( sva.eventCode )
		case 2: // mouse up
			SetAxis $G_axisName G_axisMin, G_axisMax
			break
	endswitch

	return 0
End

Function SetAxisMenu(pa) : PopupMenuControl
	STRUCT WMPopupAction &pa
	
	NVAR G_axisMin = root:Data:G_axisMin
	NVAR G_axisMax = root:Data:G_axisMax
	SVAR G_axisName = root:Data:G_axisName
	
	switch( pa.eventCode )
		case 2: // mouse up
			PopupMenu popup0 value=AxisList("")
			G_axisName = pa.popStr
			
			GetAxis /Q $G_axisName
			G_axisMin = V_min
			G_axisMax = V_max
			break
	endswitch

	return 0
End

//Either use these or the leftaxisset functions
Function LogLogButton(ba) : ButtonControl
	STRUCT WMButtonAction &ba

	switch( ba.eventCode )
		case 2: // mouse up
			ModifyGraph log(left)=1
			ModifyGraph log(bottom)=1
			break
	endswitch
End 

Function LinLinButton(ba) : ButtonControl
	STRUCT WMButtonAction &ba

	switch( ba.eventCode )
		case 2: // mouse up
			ModifyGraph log(left)=0
			ModifyGraph log(bottom)=0
			break
	endswitch
End 

Function LinLogButton(ba) : ButtonControl
	STRUCT WMButtonAction &ba

	switch( ba.eventCode )
		case 2: // mouse up
			ModifyGraph log(left)=1
			ModifyGraph log(bottom)=0
			break
	endswitch
End 

Function PartialHistButton(cba) : CheckBoxControl
	STRUCT WMCheckboxAction &cba
	NVAR PartialHist=root:Data:G_PartialHist
	
	switch( cba.eventCode )
		case 2: // mouse up
			if (PartialHist==1)
				SetVariable setvar7 disable=0
				SetVariable setvar9 disable=0
			else
				SetVariable setvar7 disable=2
				SetVariable setvar9 disable=2
			endif
			break
	endswitch

	return 0
End



Function SetBinSize(ctrlName,varNum,varStr,varName) : SetVariableControl
	String ctrlName
	Variable varNum
	String varStr
	String varName
	NVAR HighCutOff = root:Data:G_HighCutOff
	
	if (varNum==0.0001)
		HighCutOff=2.0
	else
		HighCutOff=varNum*10000
	endif
	

End

Function ChangePath(ctrlName,varNum,NPath,varName) : SetVariableControl
	String ctrlName,NPath, varName
	Variable varNum
	String Link
	NVAR MergeCheck=root:Data:G_Mergecheck
	NVAR Setup=root:Data:G_Setup

	Variable i,j
	
	Link = "Data:"
	
	SVAR CurrentPath=root:Data:G_PathDate
	SVAR Drive=root:Data:G_Drive
	NVAR Offline=root:Data:G_Offline
	String OldFullPath,NewFullPath,Folder,OldPath, TempPath
	 
	 PathInfo Relocate;
	 OldFullPath = S_path;
	 Variable index = 	 strsearch(OldfullPath, Link,0);
	 NewFullPath = OldFullPath[0,index+4]+CurrentPath;
	
	NewPath/O/Z/Q Relocate NewFullPath
	Printf "root:Data:G_PathDate = \"%s\"; NewPath/O/Z/Q Relocate \"%s\"\r",CurrentPath,NewFullPath
End
////	Drive=UpperStr(Drive[0])+":"
////	if (stringmatch(Drive,"2:") == 1)
////		Link = "ExpData2:"
////		Drive = Link
////	elseif (stringmatch(Drive,"1:")==1)
////		Link = "ExpData1:"
////		Drive = Link
////	elseif (stringmatch(Drive,"3:")==1)
////		Link = "ExpData3:"
////		Drive = Link
////	elseif (stringmatch(Drive,"A:") == 1)
////		Link = "Data:"
////		Drive = Link
////	elseif (stringmatch(Drive,"B:") == 1)
////		Link = "Data2:"
////		Drive = Link
////	endif
////	
////	if (strsearch(NPath,"J",0)>0)
////		Folder="JExperiments"+CurrentPath[6,7]+":"
////		TempPath=NPath
////	elseif(strsearch(NPath,"F",0)>0)
////		Folder="FExperiments"+CurrentPath[6,7]+":"
////		TempPath=NPath[0,4]+"F"+NPath[6,7]
////	elseif(strsearch(NPath,"K",0)>0)
////		Folder="KExperiments"+CurrentPath[6,7]+":"
////		TempPath=NPath[0,4]+"K"+NPath[6,7]
////	else
////		Folder="Experiments"+CurrentPath[6,7]+":"
////		TempPath=NPath
////	endif
////	
////	if ((strsearch(Drive,"Z:",0)>-1)||(strsearch(Drive,"Y:",0)>-1))
////		Folder=""
////	endif
////	Make/O/T/N=1 AllDrives
//////	Make/O/T/N=5 AllFolders
//////	AllDrives[0]="X:"
//////	AllDrives[1]="W:"
//////	AllDrives[2]="Z:"
//////	AllDrives[3]="V:"
//////	AllDrives[4]="Y:"
////	AllDrives[0]=Link
//////	AllFolders[0]=""
//////	AllFolders[1]="Experiments"+CurrentPath[6,7]+":"
//////	AllFolders[2]="JExperiments"+CurrentPath[6,7]+":"
//////	AllFolders[3]="FExperiments"+CurrentPath[6,7]+":"
////	AllFolders[3]="KExperiments"+CurrentPath[6,7]+":"
//	
//	Variable PathFound=0
//	if (Offline==0)
//		PathInfo Relocate
//		OldFullPath=S_path
//		Variable Slen=strlen(S_path)
//		OldPath=S_path[Slen-14,Slen-7]
////		NewFullPath=Drive+Folder+TempPath+"Waves:"
//		NewFullPath=Drive+Folder+TempPath+"Merge:"
//		NewPath/O/Z/Q Relocate NewFullPath
//		if (V_flag!=0)
//			i=0
//			Do
////				j=0
////				Do
////					NewFullPath=AllDrives[i]+AllFolders[j]+TempPath+"Merge:"
//					NewFullPath=Folder+TempPath+"Merge:"
//					NewPath/O/Z/Q Relocate NewFullPath
////					j+=1
////				while ((V_flag!=0)&&(j<numpnts(AllFolders)))
//				i+=1
//			while ((V_flag!=0)&&(i<numpnts(AllDrives)))
//			if (V_flag!=0)
//				i=0
//				Do
////					j=0
////					Do
////						NewFullPath=AllDrives[i]+AllFolders[j]+TempPath+"Waves:"
//						NewFullPath=Folder+TempPath+"Waves:"
//						NewPath/O/Z/Q Relocate NewFullPath
////						j+=1
////					while ((V_flag!=0)&&(j<numpnts(AllFolders)))
//					i+=1
//				while ((V_flag!=0)&&(i<numpnts(AllDrives)))
//			endif
//			if (V_flag!=0)
//				NewPath/O/Z/Q Relocate OldFullPath
//				CurrentPath=OldPath
//				NewFullPath=OldFullPath
////				Drive=AllDrives[i-1]
//			endif
//		endif
//		if (stringmatch(Link,"Data:")==1)
//			Drive = "A"
//		elseif (stringmatch(Link,"Data2:")==1)
//			Drive = "B"
//		else
//			Drive=Drive[strlen(Drive)-2]
//		endif
//	else
//		print "Offline: No path set", CurrentPath
//	endif
//	if ((strsearch(NewFullPath,"Merge",0)>-1))
//		MergeCheck=1
//	else
//		MergeCheck=0
//	endif
//	if ((strsearch(CurrentPath,"J",0)>-1))
//		Setup=3
//	elseif((strsearch(CurrentPath,"F",0)>-1))
//		Setup=2
//	elseif((strsearch(CurrentPath,"K",0)>-1))
//		Setup=4
//	else
//		Setup=1
//	endif
//	NewPath/O/Z/Q Relocate OldFullPath
//	Printf "root:Data:G_PathDate = \"%s\"; NewPath/O/Z/Q Relocate \"%s\"\r",CurrentPath,NewFullPath
//End

Function DisplayPullOut(ctrlName,varNum,varStr,varName) : SetVariableControl
	String ctrlName
	Variable varNum
	String varStr
	String varName
	variable i,j, error,NumPts
	String POExtension,POConductance,POParameter

	NVAR DisplayStartNumber=root:Data:G_DisplayNum
	NVAR SmoothCond=root:Data:G_SmoothCond
	NVAR SmoothType=root:Data:G_SmoothType
	NVAR SmoothLevel=root:Data:G_SmoothLevel
	NVAR SmoothRepeat=root:Data:G_SmoothRepeat
	NVAR Noise = root:Data:G_Noise
	NVAR LoadIV = root:Data:G_LoadIV
	NVAR Startpt = root:Data:G_IVStartPt
	NVAR Endpt = root:Data:G_IVEndPt
	NVAR CantileverSlope =root:Data:F_CantileverSlope
	NVAR SpringConstant=root:Data:F_CantileverSpringConstant
	NVAR G_LoadForce = root:Data:G_LoadForce
	NVAR G_SmoothForce=root:Data:G_SmoothForce
	NVAR BackStart = root:Data:G_BackgroundStart
	NVAR BackEnd = root:Data:G_BackgroundEnd

	Wave POParameter_Display
	Wave Cond_Block, Force_Block,Conductance_D, Force_D
	NVAR G_IncludedCurveNumber = root:Data:G_IncludedCurveNumber
	
	Variable Ext_offset = 0
	make/O/N=2 coef

	string excmd
	SetDataFolder root:Data
	i = DisplayStartNumber
	make/N=0/O POConductance_Display
	make/N=0/O POForce_Display
	if (LoadCond(POConductance_Display,i,N=NumPts)==-1)
		Print " Trace does not exist"
		return 0
	endif

	if (SmoothCond == 1)
		SmoothData(POConductance_Display,POConductance_Display,SmoothType, SmoothLevel,SmoothRepeat)
	endif

	Wavestats/Q/R=[NumPts*BackStart,NumPts*BackEnd] POConductance_Display
	POConductance_Display-=V_avg
	Noise=V_avg
	//	POAnal(POConductance_Display)

	
	if (G_LoadForce==1)
		if (LoadForce(i, POForce_Display)==0)
			duplicate/o POForce_display POForce_display2
			if (G_SmoothForce > 0)
				smoothdata(POFOrce_Display, POFOrce_Display, SmoothType, G_SmoothForce,SmoothRepeat)
			endif
			POForce_Display*=(1/cantileverslope)*SpringConstant
			Wavestats/Q/R=[Numpts*0.99,Numpts-1] POForce_Display
			POForce_Display-=V_avg
			//print V_sdev
	
			duplicate/o POForce_Display POForce_Display_Smooth
			Differentiate POForce_Display/D=POForce_Display_DIF
			Duplicate/O POForce_Display SriSmoothedForce
			Duplicate/O POForce_Display POForce_Display_smooth
			Smooth/B 11, POForce_Display_smooth
			SriSmoothedForce-=POForce_Display_smooth[p+12]
			SriSmoothedForce=SriSmoothedForce*POForce_Display_DIF^2
			Wavestats/q/R=[numpnts(SriSmoothedForce)-5000,numpnts(SriSmoothedForce)] SriSmoothedForce
			Variable Level=1*(abs(V_avg)+50*V_sdev)
			Make/N=2/O YWave, XWave
			YWave=Level
			XWave[0]=0
			XWave[1]=POParameter_Display[0]
			DoWindow/F POGFXAnalysis
			if(V_Flag==0)
				execute "POGFXAnalysis()"
			endif
			DoWindow/F POGFXAnalysis
			SetAxis RR -Level*3,Level*4
		else
			DoWindow/F POGXAnalysis
			if(V_Flag==0)
				execute "POGXAnalysis()"
			endif
		endif	
		Conductance_D = Cond_Block[p][G_IncludedCurveNumber];
		Force_D = Force_Block[p][G_IncludedCurveNumber]
	endif
	
	if (LoadIV==1)
		if (waveexists(POCurrent_Display)==0)
			make/N=0 POCurrent_Display
		else
			wave POCurrent_Display
		endif
		if (waveexists(POVoltage_Display)==0)
			make/N=0 POVoltage_Display
		else
			wave POVoltage_Display
		endif
		if ((LoadCurrent(POCurrent_Display,i)==0) && (LoadVoltage(POVoltage_Display,i)==0))
			variable midpt = (startpt+endpt)/2
			Duplicate/O POVoltage_Display Voltage_D
			Wavestats/Q/R=[NumPts*BackStart,NumPts*BackEnd] POCurrent_Display
			Wavestats/Q/R=[15900,16200] POCurrent_Display
			POCurrent_Display-=V_avg
			//print V_avg
			Duplicate/O POCurrent_Display Current_D
			Duplicate/O POCurrent_Display,POCurrent_Display_smth;
			wavestats/Q/R=[6500,11000] POCurrent_Display 
			Print V_avg
			Smooth/B 21, POCurrent_Display_smth;	
//			CurveFit/Q/M=2/W=0 line, Current_D[midpt-300,midpt+300]/X=Voltage_D[midpt-300,midpt+300]/D
//			Wave W_coef
//			Current_D-=W_coef[0]
	
			redimension/N=(Endpt) Current_D, Voltage_D
			deletepoints 0, Startpt, Current_D, Voltage_D
			SetScale/I x 0,100,"", Current_D
//			Current_D=log(abs((Current_D)*sign(Voltage_D)))+6
			Current_D*=sign(Voltage_D)
			Current_D=log(abs(Current_D))+6
			Smooth/B 1, Current_D
//			Duplicate/o Current_D Diff_C
//			Diff_C=0
//			Diff_C=Current_D[p]-Current_D[p+5]
//			Diff_C*=Diff_C
//			print mean(Diff_C)
//


			//Current_D=(Current_D)*sign(Voltage_D)
//			fft/Out=2/DEST= Display_MAG_FFTCurrent Current_D
//			SetScale/I x 0,100000/2,"",  Display_MAG_FFTCurrent
			
//			Display_MAG_FFTCurrent/=5000
			variable k=0
			if (k<1)
				DoWindow/F IVData
				if (V_Flag==0)
					Display/W=(425,150,825,400)
					DoWindow/C IVData
					AppendToGraph/W=IVData Current_D[0,(endpt-startpt)/2-10] vs Voltage_D[0,(endpt-startpt)/2-10]
					AppendToGraph/W=IVData Current_D[(endpt-startpt)/2-10,inf] vs Voltage_D[(endpt-startpt)/2-10,inf]
				//	AppendToGraph/W=IVData Current_D vs Voltage_D
					ModifyGraph rgb(Current_D#1)=(1,16019,65535)
					ModifyGraph zero=1
					ModifyGraph margin(left)=50
					ModifyGraph rgb(Current_D#1)=(1,16019,65535)
					ModifyGraph zero=1
					ModifyGraph mirror=2
					ModifyGraph font="Arial"
					ModifyGraph fSize=14
					ModifyGraph standoff=0
					ModifyGraph axThick=1.5
					ModifyGraph notation(left)=1
					ModifyGraph margin(left)=58,margin(bottom)=58
					ModifyGraph axisOnTop=1
					ModifyGraph tick=2
					ModifyGraph lowTrip(left)=0.001
					Label left "Current (\F'Symbol'm\F'Arial'A)"
					Label bottom "Voltage (V)"
				endif
			endif
		endif
	endif
	
	dowindow/F PullOut_Analysis
//	dowindow/H
End

Function POAnal(WaveIn, [CondB, CondA, EndX])
Variable &CondB, &CondA, &EndX
Wave WaveIn

Variable NumPts=numpnts(WaveIn)

Variable FirstCross, SecondCross
EndX=-1

Findlevel/EDGE=2/Q/R=[numpts,0]/P WaveIn, 10
if (V_Flag==0)
	FirstCross = V_Levelx
	Findlevel/EDGE=2/Q/P/R=[FirstCross,NumPts] WaveIn, 0.01
	If (V_Flag==0)
		SecondCross = V_Levelx
		Wavestats/Q/R=[FirstCross, SecondCross] WaveIn
		//print v_avg
		if (V_avg > 1.1)
		//	print SecondCross
	//		DoWindow/F Graph0
	//		DoUpdate
	//		Cursor A, Conductance_D, pnt2x(Conductance_D,SecondCross)
			Findlevel/EDGE=1/Q/B=5/P/R=[SecondCross,NumPts] WaveIn, 0.0006
			if (V_Flag==0)
				EndX=pnt2x(WaveIn,V_Levelx)
				Wavestats/Q/R=[V_Levelx-20, V_Levelx-40] WaveIn
				CondB=V_avg
				Wavestats/Q/R=[V_Levelx, V_Levelx+20] WaveIn
				CondA=V_avg
		//		print condB, CondA
				
	//			DoWindow/F Graph0
	//			Cursor B, Conductance_D, EndX
	//			Sleep/T 5
			endif
		endif
	endif	
endif

end


Function RunLightAnal(TraceNum)
Wave TraceNum

NVAR Counter=root:Data:G_Counter


Variable NN=numpnts(TraceNum)

Make/N=(NN)/O MolLightRatio, AuLightRatio, UltRatio, MolDCCurrent
Wave COnductance_D
Variable StartMol, EndMol, StartAu, EndAu, i, PONum, NumPts

StartMol=3.1*5000+1
EndMol=5.1*5000
StartAu=6.1*5000+1
EndAu=8.1*5000

For (i=0;i<NN;i+=1)
	PONum=TraceNum[i]
//	LoadCond(Conductance_D,PONum,N=NumPts)
	LoadCurrent(POCurrent_Display, PONum)
	NumPts=numpnts(POCurrent_Display)
	SetScale/I x 0,NumPts/1e5,"s", POCurrent_Display
	FFT/OUT=3/RP=[StartMol,EndMol]/DEST=POCurrent_Display_FFT POCurrent_Display
	MolLightRatio[i]=Real(POCurrent_Display_FFT(17000))/Real(POCurrent_Display_FFT(11000))
//	Wavestats/Q/R=[StartMol,EndMol] Conductance_D
	MolDCCUrrent[i]=(POCurrent_Display_FFT[0]/(EndMol-StartMol+1)/0.5)/77.5e-6
	FFT/OUT=3/RP=[StartAu,EndAu]/DEST=POCurrent_Display_FFT POCurrent_Display
	AuLightRatio[i]=Real(POCurrent_Display_FFT(17000))/Real(POCurrent_Display_FFT(11000))
	Counter=i
	DoUpdate/W=PullOut_Analysis
endfor
ultratio=mollightratio/aulightratio
end


Window POGXAnalysis() : Graph
	PauseUpdate; Silent 1		// building window...
	String fldrSav0= GetDataFolder(1)
	SetDataFolder root:Data:
	Display /W=(35,51,644,426) POConductance_Display
	SetDataFolder fldrSav0
	ModifyGraph margin(left)=70
	ModifyGraph lSize=1.5
	ModifyGraph rgb=(65280,0,0)
	ModifyGraph tick=2
	ModifyGraph mirror=2
	ModifyGraph fSize=14
	ModifyGraph standoff=0
	ModifyGraph axThick=1.5
	Label left "Conductance (2e\\Z06\\S2\\Z10\\M/h)"
	Label bottom "Displacement (nm)"
	SetAxis left 1e-05,10
	ShowInfo
	Button button0,pos={1,2},size={50,20},proc=SLButton,title="SL"
	Button button1,pos={2,29},size={50,20},proc=LogLinButton,title="Log/Lin"
EndMacro
Window POGFXAnalysis() : Graph
	PauseUpdate; Silent 1		// building window...
	String fldrSav0= GetDataFolder(1)
	SetDataFolder root:Data:
	Display /W=(185,176,792,591) POConductance_Display
	AppendToGraph/R=RR SriSmoothedForce
	AppendToGraph/R=RR YWave vs XWave
	AppendToGraph/R POForce_Display
	SetDataFolder fldrSav0
	ModifyGraph margin(left)=58
	ModifyGraph lSize(POConductance_Display)=1.5,lSize(SriSmoothedForce)=1.5,lSize(POForce_Display)=1.5
	ModifyGraph lStyle(YWave)=9
	ModifyGraph rgb(POConductance_Display)=(65280,0,0),rgb(SriSmoothedForce)=(3,52428,1)
	ModifyGraph rgb(YWave)=(0,0,0),rgb(POForce_Display)=(0,12800,52224)
	ModifyGraph grid(left)=2,grid(bottom)=2
	ModifyGraph log(left)=1
	ModifyGraph tick=2
	ModifyGraph mirror(bottom)=2,mirror(RR)=2
	ModifyGraph nticks(RR)=3,nticks(right)=3
	ModifyGraph sep(RR)=1
	ModifyGraph fSize=14
	ModifyGraph standoff=0
	ModifyGraph axOffset(bottom)=-1
	ModifyGraph axThick=1.5
	ModifyGraph lblPos(left)=52,lblPos(bottom)=51,lblPos(RR)=59,lblPos(right)=60
	ModifyGraph axisOnTop=1
	ModifyGraph freePos(RR)=0
	ModifyGraph axisEnab(left)={0,0.7}
	ModifyGraph axisEnab(RR)={0.7,1}
	ModifyGraph axisEnab(right)={0,0.7}
	Label left "Conductance (2e\\Z06\\S2\\Z10\\M/h)"
	Label bottom "Displacement (nm)"
	SetAxis left 1e-06,*
	SetAxis bottom 0,*
	SetAxis RR -302843156.446578,403790875.262104
	ShowInfo
	Button button0,pos={1,2},size={50,20},proc=ButtonProc,title="SL"
	Button button1,pos={2,29},size={50,20},proc=LogLinButtonF,title="Log/Lin"
	SetDrawLayer UserFront
	SetDrawEnv linethick= 1.5
	DrawLine 0,0.3,1,0.3
EndMacro

Function DecreaseIncluded()
	NVAR CurveNumber=root:Data:G_IncludedCurveNumber
	CurveNumber = CurveNumber-1
	If (CurveNumber < 0)
		CurveNumber = 0
	endif
	DisplayIncludedNumbers(" ", 0, " ", " ")
end

Function IncreaseIncluded()
	NVAR CurveNumber=root:Data:G_IncludedCurveNumber
	NVAR Total_Included = root:Data:G_Total_Included

	CurveNumber = CurveNumber+1
	If (CurveNumber > Total_Included)
		CurveNumber = Total_Included
	endif
	DisplayIncludedNumbers(" ", 0, " ", " ")	
end


Function DisplayIncludedNumbers(ctrlName,varNum,varStr,varName) : SetVariableControl
	String ctrlName
	Variable varNum
	String varStr
	String varName

	NVAR DisplayStartNumber=root:Data:G_DisplayNum
	NVAR DisplayFromIncluded = root:Data:G_DisplayFromIncluded
	NVAR Total_Included = root:Data:G_Total_Included
	Wave IncludedNumbers=root:Data:IncludedNumbers
	NVAR CurveNumber = root:Data:G_IncludedCurveNumber
	
	if (CurveNumber==-1)
		return 0
	endif
	if (CurveNumber>Total_Included)
		CurveNumber = Total_Included
	endif
	DisplayStartNumber=IncludedNumbers[CurveNumber]
	DisplayPullOut("",0,"","")
End


Function DH([Disp])
Variable Disp

if (ParamIsDefault(Disp))
	DisplayHist("no")
else
	DisplayHist("NP")
endif
DoWindow/H

end

Function FromIncludedCheck(ctrlName,checked) : CheckBoxControl
	String ctrlName
	Variable checked
	NVAR DisplayFromIncluded = root:Data:G_DisplayFromIncluded
	if(checked==0)
		DisplayFromIncluded=0
		SetVariable Setvar14 Win=PullOut_Analysis, disable=1
	else
		DisplayFromIncluded=1
		SetVariable Setvar14 Win=PullOut_Analysis, disable=0
	endif

End
function SmoothData(Wave_in, Wave_out, SmoothType, SmoothLevel,SmoothRepeat)
	Wave Wave_in, Wave_out
	Variable SmoothType, SmoothLevel, SmoothRepeat
	Variable k
	Wave_out=Wave_in

	if (SmoothType==2)
		SmoothLevel=(floor(SmoothLevel/2))*2+1
		if (SmoothLevel<5)
			SmoothLevel=5
		elseif (SmoothLevel > 25)
			SmoothLevel=25
		endif					
		for (k=0;k<SmoothRepeat;k+=1)
			Smooth/S=2 (SmoothLevel), Wave_out
		endfor
	elseif (SmoothType==3)
		SmoothLevel=(floor(SmoothLevel/2))*2+1
		for (k=0;k<SmoothRepeat;k+=1)					
			Smooth/B  (SmoothLevel), Wave_out
		endfor
	else // SmoothType=1
		for (k=0;k<SmoothRepeat;k+=1)
			Smooth (SmoothLevel), Wave_out
		endfor
	endif

end

Function RedimButton(ctrlName) : ButtonControl
	String ctrlName
	NVAR Start=root:Data:G_RedimStart
	NVAR Stop=root:Data:G_RedimStop
	
	print "Redim("+num2str(Start)+","+num2str(Stop)+")"
	Redim(Start,Stop)

End

Function SetRedimStopProc(ctrlName,varNum,varStr,varName) : SetVariableControl
	String ctrlName
	Variable varNum
	String varStr
	String varName
	NVAR Start=root:Data:G_RedimStart
	NVAR Stop=root:Data:G_RedimStop
	
	print "Redim("+num2str(Start)+","+num2str(Stop)+")"
	Redim(Start,Stop)

End


function Redim(start,finish)
	Variable start,finish
	
	Variable i
	Wave IncludedNumbers=root:Data:IncludedNumbers
	NVAR Total_Included = root:Data:G_Total_Included
	NVAR GStart=root:Data:G_RedimStart
	NVAR GStop=root:Data:G_RedimStop
	GStart=start
	GStop=finish
	if (finish<start)
		i=start
		start=finish
		finish=i
	endif

	redimension/N=(Finish-Start+1) IncludedNumbers
	IncludedNumbers=p+Start
	Total_Included=numpnts(IncludedNumbers)
	if (GStart==0)
		deletepoints 0,1,IncludedNumbers
	endif
end

function Plus1000(ctrlName) : ButtonControl
	String ctrlName

	NVAR GStart=root:Data:G_RedimStart
	NVAR GStop=root:Data:G_RedimStop

	GStart+=1000
	GStop+=1000
	
	Redim(GStart,GStop)
	Print "Redim("+num2str(GStart)+","+num2str(GStop)+")"
	//dh()

end


Function LoadCond(Conductance_D,i,[N])
	Wave Conductance_D
	Variable i
	Variable &N

	SVAR CurrentPath=root:Data:G_PathDate
	NVAR MergeCheck=root:Data:G_MergeCheck
	NVAR ReadBlockConductance=root:Data:G_ReadBlockConductance

	String Conductance
	Variable error
	
	if(MergeCheck==1)
		
		String ConductanceBlockName
		variable blocknumber=ceil(i/100)
		if(blocknumber!=ReadBlockConductance)
			
			ConductanceBlockName="PullOutConductanceBlock_"+num2str(blocknumber)
			GetFileFolderInfo/Z=1/P=Relocate /Q ConductanceBlockName+".ibw"
			if (V_flag == 0)
//			print "File Saved:", Secs2Date(V_CreationDate,2),Secs2Time(V_CreationDate,0)
			LoadWave/Q/H/P=Relocate/O ConductanceBlockName+".ibw"
			if (V_flag == 0)
				Print "ConductanceBlock ",blocknumber," does not exist" 
				return -1
			endif
			duplicate/O  $ConductanceBlockName ConductanceBlock
			killwaves $ConductanceBlockName
			ReadBlockConductance=blocknumber
			else
				print "File Not Found",ConductanceBlockName
				return -1
			endif
		endif
		
		
		Wave ConductanceBlock
	//	make/O/N=(dimsize(ConductanceBlock,0)) Conductance_D			
		redimension/N=(dimsize( ConductanceBlock,0)) Conductance_D
		Conductance_D= ConductanceBlock[p][mod(i-1,100)]
		N=numpnts(Conductance_D)-22
		make/O/N=20 POParameter_Display
		POParameter_Display=ConductanceBlock[N+2+p][0]
		redimension/N=(N) Conductance_D
		SetScale/I x 0,POParameter_Display[0],"", Conductance_D

	else

		Conductance="PullOutConductanceBlockHist_"+num2str(i)
		error = WaveExists($Conductance)
		if (error == 1)
			killwaves $Conductance
		endif

		LoadWave/Q/H/P=Relocate/O Conductance+".ibw"
		if (V_flag == 0)
			Print "Wave ",i," does not exist" 
			return -1
		endif
		duplicate/O $Conductance Conductance_D
		Killwaves $Conductance

		N=numpnts(Conductance_D)-22
		make/O/N=20 POParameter_Display
		POParameter_Display=Conductance_D[N+2+p]
		redimension/N=(N) Conductance_D
		SetScale/I x 0,POParameter_Display[0],"", Conductance_D

		
	endif
	return 0

end
Function LoadForce(i,Force_D)
	Wave Force_D
	Variable i
	NVAR Mergecheck = root:Data:G_MergeCheck
	Variable N
	variable pulllength
	Wave POParameter_Display

	if(MergeCheck==1)
		//merge code
		SVAR CurrentPath=root:Data:G_PathDate
		NVAR ReadBlockForce=root:Data:G_ReadBlockForce
		NVAR Excursion =  root:Data:G_ExcursionSize
		String ForceBlockName
		variable blocknumber=ceil(i/100)



		if(blocknumber!=ReadBlockForce)	
			ForceBlockName="PullOutForceBlock_"+num2str(blocknumber)
			GetFileFolderInfo/Z=1/Q/P=Relocate ForceBlockName  + ".ibw"
			if (V_flag == 0)
				ForceBlockName="PullOutForceBlock_"+num2str(blocknumber)			
				LoadWave/Q/H/P=Relocate/O ForceBlockName  +".ibw"
				duplicate/O  $ForceBlockName ForceBlock
				killwaves $ForceBlockName
				ReadBlockForce=blocknumber
			else	
				Print "ForceBlock ",blocknumber," does not exist" 
				return -1
			endif
		endif

		Wave ForceBlock
		redimension/N=(dimsize( ForceBlock,0)) Force_D
		Force_D = ForceBlock[p][mod(i-1,100)]
		SetScale/I x 0,POParameter_Display[0],"", Force_D //aajn
	
		N = numpnts(Force_D)

	elseif(MergeCheck==0)
		String FX
		FX ="PullOutForce_"+num2str(i)

		if (WaveExists($FX)==1)
			killwaves $FX
		endif
		//	GetFileFolderInfo/P=Relocate/Q/Z FX+".ibw"
		LoadWave/Q/H/P=Relocate/O FX+".ibw"

		if (V_flag == 0)
			Print "Wave",FX," ",i," does not exist" 
			return -1
		endif
		duplicate/O $FX Force_D
		killwaves $FX
		N = numpnts(Force_D)

	endif
	return 0
end

Function LoadForce2(i,Force_D)
	Wave Force_D
	Variable i
	NVAR Mergecheck = root:Data:G_MergeCheck
	Variable N
	variable pulllength
	Wave POParameter_Display

	if(MergeCheck==1)
		//merge code
		SVAR CurrentPath=root:Data:G_PathDate
		NVAR ReadBlockForce=root:Data:G_ReadBlockForce
		NVAR Excursion =  root:Data:G_ExcursionSize
		String ForceBlockName
		variable blocknumber=ceil(i/100)



		if(blocknumber!=ReadBlockForce)	
			ForceBlockName="PullOutForceBlock2_"+num2str(blocknumber)
			GetFileFolderInfo/Z=1/Q/P=Relocate ForceBlockName  + ".ibw"
			if (V_flag == 0)
				ForceBlockName="PullOutForceBlock2_"+num2str(blocknumber)			
				LoadWave/Q/H/P=Relocate/O ForceBlockName  +".ibw"
				duplicate/O  $ForceBlockName ForceBlock
				killwaves $ForceBlockName
				ReadBlockForce=blocknumber
			else	
				Print "ForceBlock ",blocknumber," does not exist" 
				return -1
			endif
		endif

		Wave ForceBlock
		redimension/N=(dimsize( ForceBlock,0)) Force_D
		Force_D = ForceBlock[p][mod(i-1,100)]
		SetScale/I x 0,POParameter_Display[0],"", Force_D //aajn
	
		N = numpnts(Force_D)

	elseif(MergeCheck==0)
		String FX
		FX ="PullOutForce_"+num2str(i)

		if (WaveExists($FX)==1)
			killwaves $FX
		endif
		//	GetFileFolderInfo/P=Relocate/Q/Z FX+".ibw"
		LoadWave/Q/H/P=Relocate/O FX+".ibw"

		if (V_flag == 0)
			Print "Wave",FX," ",i," does not exist" 
			return -1
		endif
		duplicate/O $FX Force_D
		killwaves $FX
		N = numpnts(Force_D)

	endif
	return 0
end

Function LoadCurrent(Current_D,i)
	Wave Current_D
	Variable i

	SVAR CurrentPath=root:Data:G_PathDate
	NVAR MergeCheck=root:Data:G_MergeCheck
	NVAR ReadBlockCurrent=root:Data:G_ReadBlockCurrent

	String CurrentBlockName, Current
	Variable error
	Wave POParameter_Display
	Variable Test=0
	if(MergeCheck==1)
	//if(Test==1)
		
		variable blocknumber=ceil(i/100)
		if(blocknumber!=ReadBlockCurrent)
			
			CurrentBlockName="PullOutCurrentBlock_"+num2str(blocknumber)
			LoadWave/Q/H/P=Relocate/O CurrentBlockName+".ibw"
			if (V_flag == 0)
				Print "CurrentBlock ",blocknumber," does not exist" 
				return -1
			endif
			duplicate/O  $CurrentBlockName CurrentBlock
			killwaves $CurrentBlockName
			ReadBlockCurrent=blocknumber
		endif
		
		
		Wave CurrentBlock	
//		make/O/N=(dimsize(CurrentBlock,0)) Current_D
		redimension/N=(dimsize(CurrentBlock,0)) Current_D
		Current_D= CurrentBlock[p][mod(i-1,100)]
		redimension/N=(numpnts(Current_D)-2) Current_D
	else

		Current="PullOutCurrent_"+num2str(i)
		error = WaveExists($Current)
		if (error == 1)
			killwaves $Current
		endif

		LoadWave/Q/H/P=Relocate/O Current+".ibw"
		if (V_flag == 0)
			Print "Wave ",i," does not exist" 
			return -1
		endif
		duplicate/O $Current Current_D
		Killwaves $Current
	endif
	SetScale/I x 0,POParameter_Display[0],"", Current_D

	return 0

end
Function LoadVoltage(Voltage_D,i)
	Wave Voltage_D
	Variable i

	Wave POParameter_Display
	SVAR CurrentPath=root:Data:G_PathDate
	NVAR MergeCheck=root:Data:G_MergeCheck
	NVAR ReadBlockVoltage=root:Data:G_ReadBlockVoltage

	String VoltageBlockName, Voltage
	Variable error
	
	Variable Test=0
	if(MergeCheck==1)
	//if(Test==1)
		
		variable blocknumber=ceil(i/100)
		if(blocknumber!=ReadBlockVoltage)
			
			VoltageBlockName="PullOutVoltageBlock_"+num2str(blocknumber)
			LoadWave/Q/H/P=Relocate/O VoltageBlockName+".ibw"
			if (V_flag == 0)
				Print "VoltageBlock ",blocknumber," does not exist" 
				return -1
			endif
			duplicate/O  $VoltageBlockName VoltageBlock
			killwaves $VoltageBlockName
			ReadBlockVoltage=blocknumber
		endif
		
		
		Wave VoltageBlock			
	//	Make/O/N=(dimsize(VoltageBlock,0)) Voltage_D
		Redimension/N=(dimsize(VoltageBlock,0)) Voltage_D	
		Voltage_D= VoltageBlock[p][mod(i-1,100)]
		redimension/N=(numpnts(Voltage_D)-2) Voltage_D

	else

		Voltage="PullOutVoltage_"+num2str(i)
		error = WaveExists($Voltage)
		if (error == 1)
			killwaves $Voltage
		endif

		LoadWave/Q/H/P=Relocate/O Voltage+".ibw"
		if (V_flag == 0)
			Print "Wave ",i," does not exist" 
			return -1
		endif
		duplicate/O $Voltage Voltage_D
		Killwaves $Voltage
	endif
	SetScale/I x 0,POParameter_Display[0],"", Voltage_D
	
	return 0

end

Function RunHist(Nstart, NStop, [DeltaN])
	Variable Nstart,NStop, DeltaN

	NVAR Start=root:Data:G_RedimStart
	NVAR Stop=root:Data:G_RedimStop
	NVAR SaveHist = root:Data:G_SaveHist
	NVAR Bin_Size = root:Data:G_Hist_Bin_Size

	NStart=NStart*1000
	NStop=NStop*1000
	if (ParamIsDefault(DeltaN))
		DeltaN=1000
	endif

	Variable Num=round((NStop-NStart)/DeltaN)
	Variable G0Peak=0
	SaveHist=1
	Wave w_coef,poconductancehist, poconductancehistlog
	Variable ii,j

	for (ii=0;ii<Num;ii+=1)
		Sleep/S 0.5
		Start=Nstart
		Stop=Start+DeltaN
		print "Redim("+num2str(Start)+","+num2str(Stop)+")"

		Redim(Start+1,Stop)
		DH()

		duplicate/o poconductancehist foo
		duplicate/o poconductancehistlog foolog
		DoUpdate
		Nstart+=DeltaN
		if (ii==0)
			duplicate/o foo namefoo
			duplicate/o foolog namefoolog
			doupdate
		else
			namefoo=((namefoo*ii)+foo)/(ii+1)
			namefoolog=((namefoolog*ii)+foolog)/(ii+1)
		endif
		DoWindow/F FooGraph
		if (V_Flag==0)
			execute "FooGraph()"
		endif
		DoWindow/F LogFoo
		if (V_Flag==0)
			execute "LogFoo()"
		endif
	
	endfor
//	namefoo=namefoo/Num
//	namefoolog=namefoolog/Num
DoWindow/F/H 
	
end



Function DisplayHist(ctrlName) : ButtonControl
	String ctrlName
	
	Variable NoDisplay
	if (stringmatch(ctrlName,"NP")==1)
		NoDisplay=2
	else
		NoDisplay=stringmatch(ctrlName,"button102") // called from button, therefore update graph
	endif
	Wave IncludedNumbers=root:Data:IncludedNumbers
	Wave POConductanceHist=root:Data:POConductanceHist
	wave POParameter_Display=root:Data:POParameter_Display
	NVAR Total_Included = root:Data:G_Total_Included
	NVAR Bin_Size = root:Data:G_Hist_Bin_Size
	NVAR SmoothCond=root:Data:G_SmoothCond
	NVAR SmoothType=root:Data:G_SmoothType
	NVAR SmoothLevel=root:Data:G_SmoothLevel
	NVAR SmoothRepeat=root:Data:G_SmoothRepeat
	NVAR HighCutOff = root:Data:G_HighCutOff
	NVAR Zero_Cutoff=root:Data:G_zero_cutoff
	NVAR Offline=root:Data:G_Offline
	NVAR Counter=root:Data:G_Counter
	NVAR Noise = root:Data:G_Noise
	NVAR LoadIV = root:Data:G_LoadIV
	NVAR HoldStart = root:Data:G_HoldStart
	NVAR HoldEnd = root:Data:G_HoldEnd
	
	SVAR CurrentPath=root:Data:G_PathDate
	SVAR G_SavedHistPath=root:Data:G_SavedHistPath
	NVAR Start=root:Data:G_RedimStart
	NVAR Stop=root:Data:G_RedimStop
	NVAR SaveHist = root:Data:G_SaveHist
	NVAR Overwrite = root:Data:G_OverWrite
	NVAR BackStart = root:Data:G_BackgroundStart
	NVAR BackEnd = root:Data:G_BackgroundEnd

	variable i=0,j=0, error,numskip=0,k
	Variable NumPts, lowcutoff,num, HighCut, LowCut
	Wave Conductance_D, POParameter_Display
	Variable Stopped = 0
	Variable V_fitOptions=4
	
//	duplicate/O IncludedNumbers SnapBackD
//	SnapBackD=-1

	Variable Num_Bin=HighCutOff/Bin_Size
	Variable IVLengthPts
	Variable VStart, Vend

	Total_Included=numpnts(IncludedNumbers)
	if (NoDisplay <2)
		print "Histogram"
	endif
	String histout

	if (Total_Included<1)	// No good waves to make a histogram so quit
		return 0
	endif

	Make/O/N=(Num_Bin) POConductanceHist
	POConductanceHist=0
	SetScale/I x 0,HighCutOff,"", POConductanceHist
	Make/O/N=(1000) POConductanceHistLog
	SetScale/I x -8,2,"", POConductanceHistLog
	POConductanceHistLog=0
 
 	Variable Loaded=0
	if ((SaveHist == 1)&&(OverWrite==0))
		histout = "hist"+num2str(Start)+"_"+num2str(Stop)+"_"+CurrentPath[0,7]+"H"+num2str(-log(Bin_size))
		Loaded+=LoadHist(histout, NoDisplay)
		histout = "Loghist"+num2str(Start)+"_"+num2str(Stop)+"_"+CurrentPath[0,7]
		Loaded+=LoadHist(histout, NoDisplay)
		if (Loaded==2)
			duplicate/o poconductancehist foo
			duplicate/o poconductancehistlog foolog
			return 0
		endif
	endif
	make/N=0/O Conductance_D
	//duplicate/o IncludedNumbers NumPointsHist
//	NumPointsHist=0
	String Conductance
	for (j=0;j<Total_Included;j+=1)
		i=IncludedNumbers[j]
		if (LoadCond(Conductance_D,i,N=Numpts)==0)

			if (SmoothCond == 1)    //Smooth Data if button is checked
				smoothdata(Conductance_D, Conductance_D, SmoothType, SmoothLevel,SmoothRepeat)
			endif		
			redimension/N=10000 Conductance_D
			NumPts=numpnts(Conductance_D)
			Wavestats/Q/R=[NumPts*BackStart,NumPts*BackEnd] Conductance_D
			//Wavestats/Q/R=[4000,4100] POConductance_Display

			Noise=V_avg
			Conductance_D-=V_avg
			
//			duplicate/o Conductance_D CoD2
//			CoD2=log(CoD2)
//			make/N=400/O COD2_Hist
//			histogram/B={-5,0.01,400} CoD2, CoD2_Hist
//			if ((sum(CoD2_Hist,-2,-1.2)>500))//&&(sum(CoD2_Hist,-3.3,-2)<50))
//				NumPointsHist[j]=sum(CoD2_Hist,-2,-1.2)
//			else
//				NumPointsHist[j]=-1
//			endif
//
////			LoadVoltage(CondFromVolt_D,i)
			
			//	CondfromVolt_D=((((POParameter_Display[10]*0.95)/1000/Voltage_D - 1)/POParameter_Display[12])-(0/1e8))/77.5e-6
//			CondfromVolt_D=(POParameter_Display[10]/1000/CondFromVolt_D - 1)/POParameter_Display[12]/1.052/77.5e-6

//			Wavestats/Q/R=[NumPts*0.9992,NumPts-1] CondfromVolt_D
//			CondfromVolt_D-=V_avg
//			Conductance_D = CondfromVolt_D
			
			if (LoadIV==1)
				deletepoints HoldStart,(HoldEnd-HoldStart), Conductance_D
				NumPts=numpnts(Conductance_D)
				if (j==1)
					print "Deleting points",HoldStart,HoldEnd
				endif
			endif
	
			Wavestats/Q/R=[0,round(NumPts*0.02)] Conductance_D

		
			//	Conductance_D=(1/(1/(Conductance_D*77.5e-6)-3500))/77.5e-6

			if ((abs(Noise)<Zero_Cutoff)&&(abs(V_avg)>1.02)) // skip curves that don't go to saturation or noise (change 1.02 to 1.5)
				redimension/N=(NumPts*0.9) Conductance_D
				Histogram/A Conductance_D POConductanceHist
				Conductance_D=Log(Conductance_D)
				Histogram/A Conductance_D POConductanceHistLog
				Counter=j
				DoUpdate/W=PullOut_Analysis
				if (mod(j,100)==0)
					DoUpdate
					DoWindow/F LogFoo
				endif
				//		FindLevel/Q/Edge=2 Conductance_D, 10^-4.6
				//		if (V_flag==0)
				//			VStart=V_Levelx
				//			FindLevel/Edge=1/Q/R=(7,VStart) Conductance_D, 10^-5.5
				//			if (V_flag==0)
				//				VEnd=V_Levelx
				//				FoundNum[j]=VEnd-VStart
				//			endif
				//		endif
				//	SnapBackD[j]=(Vend+Vstart-8)*(POParameter_Display[5]/7)

			else
				numskip+=1
			endif
		else 
			break
		endif
	endfor
//	print sum(FoundNum)
		printf "Number Skipped = %d\r",numskip
		poconductanceHist/=((Total_Included-numskip)/1000) // Normalize by # of traces used
		poconductancehistLog/=((Total_Included-numskip)/1000)

	if (((SaveHist == 1)&&(Stopped==0))&&(numskip<500))
		histout = "hist"+num2str(Start)+"_"+num2str(Stop)+"_"+CurrentPath[0,7]+"H"+num2str(-log(Bin_size))
		duplicate/O poconductancehist $histout
		if (NoDisplay<2)
			print "Saved Hist as: ", histout
		endif
		NewPath/Q/O SavedHist G_SavedHistPath//+"SavedHist"+CurrentPath[5,7]
		if (OverWrite==1)
			Save/C/O/P=SavedHist $histout as histout+".ibw"
		else
			GetFileFolderInfo/P=SavedHist/Q/Z histout+".ibw"
			if (V_flag !=0)		
				Save/C/P=SavedHist $histout as histout+".ibw"
			endif
		endif
		killwaves $histout
		histout = "Loghist"+num2str(Start)+"_"+num2str(Stop)+"_"+CurrentPath[0,7]
		duplicate/O poconductancehistLog $histout			
		Save/C/O/P=SavedHist $histout as histout+".ibw"
		print "Saved LogHist as: ", histout
		killwaves $histout
	endif
	
	duplicate/o poconductancehist foo
	duplicate/o poconductancehistlog foolog
	if (waveexists(namefoo)==0)
		duplicate foo namefoo
	endif
	if (waveexists(namefoolog)==0)
		duplicate foolog namefoolog
	endif
	DoWindow/F FooGraph
	if (V_Flag==0)
		execute "FooGraph()"
	endif
	DoWindow/F LogFoo
	if (V_Flag==0)
		execute "LogFoo()"
	endif

End

Function LoadHist(Name, NoDisplay)
String Name
Variable NoDisplay
SVAR CurrentPath=root:Data:G_PathDate
SVAR G_SavedHistPath=root:Data:G_SavedHistPath

NVAR Offline=root:Data:G_Offline
		NewPath/Q/O SavedHist G_SavedHistPath;//+"SavedHist"
		GetFileFolderInfo/P=SavedHist/Q/Z Name+".ibw"
		if (V_flag==0)
			if (NoDisplay<2)
				LoadWave/O/H/P=SavedHist Name+".ibw"
			else
				LoadWave/O/H/Q/P=SavedHist Name+".ibw"
			endif
			if (stringmatch(Name,"Log*")==1)
				duplicate/O $Name POConductanceHistLog
			else
				duplicate/O $Name POConductanceHist
			endif
				killwaves/Z $Name
			return 1
		elseif (Offline==1)
			print "Histogram Does Not Exist; Offline"
			return 2
		endif
		return -1
end
Function DisplayLogHist()

	Wave IncludedNumbers=root:Data:IncludedNumbers
	NVAR Total_Included = root:Data:G_Total_Included
	NVAR SmoothCond=root:Data:G_SmoothCond
	NVAR SmoothType=root:Data:G_SmoothType
	NVAR SmoothLevel=root:Data:G_SmoothLevel
	NVAR SmoothRepeat=root:Data:G_SmoothRepeat
	NVAR Zero_Cutoff=root:Data:G_zero_cutoff
	NVAR Counter=root:Data:G_Counter

	variable i=0,j=0, error,numskip=0,k
	Variable NumPts, lowcutoff,num, HighCut, LowCut
	Wave Conductance_D
	Total_Included=numpnts(IncludedNumbers)
	print "Log Histogram"
	String histout, Conductance

	if (Total_Included<1)	// No good waves to make a histogram so quit
		DoWindow/F PullOutPOConductanceHistogram
		if(V_Flag==1)
			DoWindow/K PullOutPOConductanceHistogram
		endif
		return 0
	endif

	Variable BinSizeVar=1000
	Make/O/N=(BinSizeVar) POConductanceHistLog
	SetScale/I x -8,2,"", POConductanceHistLog
	POConductanceHistLog=0

//	DoWindow/K CounterWindow
//	Execute "CounterWindow()"	

	for (j=0;j<Total_Included;j+=1)
		i=IncludedNumbers[j]
		Conductance="PullOutConductance_"+num2str(i)
		LoadCond(Conductance_D,i,N=Numpts)

		if (SmoothCond == 1)    //Smooth Data if button is checked
			smoothdata(Conductance_D, Conductance_D, SmoothType, SmoothLevel,SmoothRepeat)
		endif		
		// Get rid of all points below and above thresholds - set them to zero
		Wavestats/Q/R=[NumPts*0.95,NumPts*.96] Conductance_D
		lowcutoff=V_avg
		if (lowcutoff<Zero_Cutoff)	// skip curves which don't go to zero at the end
			redimension/N=(NumPts*0.95) Conductance_D
			Conductance_D-=lowcutoff // Correct for Zero
			Conductance_D=Log(Conductance_D)
			Histogram/A Conductance_D POConductanceHistLog
		endif
		Counter=j
//		DoUpdate/W=CounterWindow
		DoUpdate/W=PullOut_Analysis
		if (floor(j/1000)==j/1000)
			DoUpdate
		endif
	endfor
	POConductanceHistLog/=(Total_Included/1000)
//	DoWindow/K CounterWindow

End



Function Hist2D(ctrlName) : ButtonControl
	String ctrlName
	NVAR AlignG=root:Data:G_AlignG
	NVAR	Linlog=root:Data:G_2DLog
	MakeCond2DHist(AlignG,Linlog)
End


Function MakeCond2DHist(AlignG,Linlog)
	Variable AlignG,LinLog
	String Name

	NVAR Counter=root:Data:G_Counter
	NVAR Total_Included = root:Data:G_Total_Included
	NVAR Xmin=root:Data:G_2DXmin
	NVAR Xmax=root:Data:G_2DXmax
	NVAR Setup = root:Data:G_Setup
	SVAR CurrentPath=root:Data:G_PathDate
	NVAR SaveHist = root:Data:G_SaveHist
	NVAR Start=root:Data:G_RedimStart
	NVAR Stop=root:Data:G_RedimStop
	NVAR SmoothCond=root:Data:G_SmoothCond
	NVAR SmoothType=root:Data:G_SmoothType
	NVAR SmoothLevel=root:Data:G_SmoothLevel
	NVAR SmoothRepeat=root:Data:G_SmoothRepeat
	NVAR Zero_Cutoff=root:Data:G_zero_cutoff
	NVAR LoadIV = root:Data:G_LoadIV
	NVAR Startpt = root:Data:G_IVStartPt
	NVAR Endpt = root:Data:G_IVEndPt
	NVAR BackStart = root:Data:G_BackgroundStart
	NVAR BackEnd = root:Data:G_BackgroundEnd
	NVAR HoldStart = root:Data:G_HoldStart
	NVAR HoldEnd = root:Data:G_HoldEnd
	

	Wave IncludedNumbers=root:Data:IncludedNumbers
	Variable type = 1 // 0-normal, 1 - include all traces, look only for x where trace goes to lowcutoff
	Variable Ymin		// -6 for log, 0 for linear
	Variable Ymax	// 1 for log, 10 for linear

	if (LinLog==1)
		Ymin=-8		// -6 for log, 0 for linear
		Ymax=2	// 1 for log, 10 for linear
	else
		Ymin=0		// -6 for log, 0 for linear
		Ymax=10	// 1 for log, 10 for linear
	endif

	Variable XNum=500; 
	Variable YNum=1000;
	Variable Factor

	If (Setup==1)
		Factor = 0.72 // Setup 1
	elseif (Setup==3)
		Factor = 0.79 // Setup 3
	elseif (Setup==4)
		Factor = 1// Before April 2016- 1.87. After April 2016, 1 Setup 4
	elseif (Setup==2)
		Factor = 0.9
	endif
	
	Total_Included=numpnts(IncludedNumbers)
	duplicate/o IncludedNumbers, HighGSumWave
	HighGSumWave=0
	duplicate/o HighGSumWave, CondBWave
	duplicate/o HighGSumWave, CondAWave

	Make/O/N=(XNum,YNum) total2DHist=0;
	Wave total2DHist
	SetScale/I x Xmin,Xmax,"",total2DHist
	SetScale/I y Ymin,Ymax,"", total2DHist	
	//	DoWindow/K CounterWindow
	//	Execute "CounterWindow()"

	Wave W_Findlevels, Conductance_D

	Variable k, EndX, DeltaEx, j, NumPts, CounterN=0
	Variable Jstartx, JendX

	for (k=0;k<Total_Included;k+=1)
		j=IncludedNumbers[k]
		EndX=0;
		
		if (LoadCond(Conductance_D,j,N=NumPts)==-1)
			print "Check Wave Number"
			return 0
		endif
		if (LoadIV==1)
//			deletepoints Startpt-1000,EndPt-Startpt+2000, Conductance_D
			redimension/N=15000 Conductance_D
			deletepoints HoldStart,(HoldEnd-HoldStart), Conductance_D
			NumPts=numpnts(Conductance_D)
			
			if (k==0)
				print "Deleting points",HoldStart, HoldEnd
			endif
		endif
		
//		Redimension/N=(4500) Conductance_D
//		NumPts=4500
		DeltaEx=deltax(Conductance_D)*Factor
		if (SmoothCond == 1)
			smoothdata(Conductance_D, Conductance_D, SmoothType, SmoothLevel,SmoothRepeat)
		endif		
		Wavestats/Q/R=[NumPts*BackStart,NumPts*BackEnd] Conductance_D
		if ((abs(V_avg)<2*Zero_Cutoff))	
						
			redimension/N=(NumPts*BackStart) Conductance_D
			NumPts*=BackStart

			Conductance_D-=V_avg
			duplicate/O Conductance_D Conductance_D_Raw

// ANALYZE HIST DURING HOLD
//			duplicate/O Conductance_D Cond_DLog
//			Cond_DLog=log(Conductance_D)
//			Make/N=800/O Cond_DLog_Hist=0
//			Histogram/B={-5,0.01,800}/R=[6000,10000] Cond_DLog, Cond_DLog_Hist
//			HighGSumWave[k]=sum(Cond_DLog_Hist,-3.25,-2)
//			if ((HighGSumWave[k]>100)&&(sum(Cond_DLog_Hist,-1,2)<20))

// ANALYZE COND DURING CAP

//			Wavestats/R=[5600,6000]/Q Conductance_D
//			HighGSumWave[k]=V_avg
//
//			if ((HighGSumWave[k]>3e-5)&&(HighGSumWave[k]<1e-2))
					
					
//					Endx=0

//			Variable CondB, CondA
//			POAnal(Conductance_D, CondB=CondB, CondA=CondA, EndX=EndX)
//			EndX*=Factor
//			print CondB, CondA
//			CondBWave[k]=CondB
//			CondAWave[k]=CondA

			
		///REGULAR 2D Hist Code
	
			Findlevel/Q/Edge=2/R=[NumPts,0] Conductance_D, Zero_Cutoff
			if (V_flag==0)
				JEndx=V_LevelX
				FindLevel/Q/Edge=2/R=(JEndx,0) Conductance_D, AlignG
				if (V_flag==0)
					Endx=V_LevelX*Factor
					
		//REGULAR 2D Hist Code COMMENT END
	//		if (Endx>0)
				duplicate/o Conductance_D_Raw Con_YWave
				duplicate/o Conductance_D_Raw Con_XWave
			//	Endx=4
				CounterN+=1

				if (LinLog==1)
					Con_YWave=log((Con_YWave))	//For Log
				endif
				Con_XWave=(p)*DeltaEx-EndX
				if (EndX>Xmax)
					deletepoints 0,round((EndX+Xmin)/DeltaEx), Con_XWave, Con_YWave
				endif
				Findlevel/P/Q Con_XWave, XMax
				if (V_flag==0)
					redimension/N=(V_LevelX) Con_XWave, Con_YWave
				endif

				Make2DHist(total2DHist,Con_XWave, Con_YWave)//,Xmin,Xmax,Ymin,Ymax,XNum,YNum)
				DoUpdate/W=PullOut_Analysis
	
				if (floor(k/100)==k/100)
					DoUpdate
					DoWindow/F Cond2D
					if (V_Flag==0)
						execute "Cond2D()"
					endif				
				endif				
// Comment Start
			else
				IncludedNumbers[k]=0
			endif
// Comment Start

			else
				IncludedNumbers[k]=0
			endif
			
		else
			IncludedNumbers[k]=0
		endif
		Counter=k
	endfor

	total2DHist/=(CounterN/1000)	
	//SetScale/I x Xmin*Factor,Xmax*Factor,"",C_2DHist;
	if (SaveHist==1)
		print "Traces Found", CounterN
// 	SVAR G_SavedHistPath=root:Data:G_SavedHistPath
		duplicate/o total2DHist $("C_2DHist_"+num2str(Start)+"_"+num2str(Stop)+"_"+CurrentPath[0,7])
		NewPath/Q/O Saved2DHist "C:DataAnalysis:SavedHist"
		Save/C/O/P=Saved2DHist $("C_2DHist_"+num2str(Start)+"_"+num2str(Stop)+"_"+CurrentPath[0,7])
		killwaves $("C_2DHist_"+num2str(Start)+"_"+num2str(Stop)+"_"+CurrentPath[0,7])
	endif
	print " X Factor used", Factor
	DoWindow/F Cond2D
	if (V_Flag==0)
		execute "Cond2D()"
	endif
	Sort/R IncludedNumbers IncludedNumbers,HighGSumWave
	redimension/N=(CounterN) IncludedNumbers,HighGSumWave
	Sort IncludedNumbers IncludedNumbers,HighGSumWave

end

Function Make2DHist(Hist2D,XWave, YWave)//,Xmin,Xmax,Ymin,Ymax,NumXBin,NumYBin)
Wave Hist2D, XWave, YWave
//Variable Xmin,Xmax,Ymin,Ymax,NumXBin,NumYBin

Variable Xmin=dimoffset(Hist2D,0)
Variable Ymin=dimoffset(Hist2D,1)
Variable NumXbin=dimsize(Hist2D,0)
Variable NumYbin=dimsize(hist2D,1)
Variable Xmax=Xmin+NumXbin*dimdelta(Hist2D,0)
Variable Ymax=Ymin+NumYbin*dimdelta(Hist2D,1)

Variable XVal, YVal

//SetScale/I x Xmin,Xmax,"", Hist2D;
//SetScale/I y Ymin,Ymax,"", Hist2D;
duplicate/o XWave Xwavein
duplicate/o YWave YWavein
XWavein=(XWave-Xmin)*NumXBin/(XMax-Xmin)
YWavein=(YWave-Ymin)*NumYBin/(YMax-YMin)

	Variable num=numpnts(XWave)
	Variable k
		for(k=0;k<num;k+=1)
			XVal=XWavein[k]
			YVal=YWavein[k]
			if((XVal<numXBin)&&(XVal>0)&&(YVal<numYBin)&&(YVal>0))
				Hist2D[XVal][YVal]+=1
			endif
		endfor

end
Function GetJumps(StartX,EndX,NumPts)
Variable StartX, EndX, NumPts
WAVE POParameter_Display
NVAR LowCutOff =  root:PullOutAnalysis:G_StepMinG
WAVE Waveout
	
	Duplicate/O Force_D POIntermediate
	POIntermediate=abs(mean(Force_D,pnt2x(Force_D,p-10),pnt2x(Force_D,p))-mean(Force_D,pnt2x(Force_D,p),pnt2x(Force_D,p+10)))
	
	Duplicate/O Force_D, Force_Filtered; DelayUpdate
	FilterFIR/LO={0.06,0.065,1001}/HI={0.005,0.009,1001}/WINF=Blackman367 Force_Filtered
	Force_Filtered=-abs(Force_Filtered)
	Variable DeltaEx=DeltaX(Force_Filtered)
	
	Wavestats/Q/R=[(NumPts*.95),(NumPts*.97)] Force_Filtered
	Variable Avg_HF=-abs(V_avg)-2*V_sdev						//cutoff for high frequency jumps
		//Print Avg_HF
	If(Avg_HF<-.5)
		StartX=EndX
		Return StartX
	EndIf
	
	If(Avg_HF<-.2)
		Avg_HF=-0.2
	EndIf
	
	Wavestats/Q/R=[(NumPts*.95),(NumPts*.97)] POIntermediate
	Variable Avg_LF=abs(V_avg)+2*V_sdev						//cutoff for low frequency jumps
		//Print Avg_LF
	If(Avg_LF>.5)
		StartX=EndX
		Return StartX
	EndIf
	
	If(Avg_LF>.2)
		Avg_LF=0.2
	EndIf

	//Print 2.5*Avg_HF, 2.5*Avg_LF
	//Avg_HF=-.1; Avg_LF=.1

//Search for high frequency jumps with rising and falling edges
	Variable jj=0,ii=0,kk=0, V_HFFound_Up=0, V_HFFound_Down=0
	Make/O W_HFJumps_Up, W_HFJumps_Down
//	Findlevels/Q/EDGE=1/R=(StartX-0.4,EndX-.0004)/D=W_HFJumps_Up Force_Filtered, 2.5*Avg_HF			// search for high frequency jumps, going up FOR AG ONLY
	Findlevels/Q/EDGE=1/R=(StartX-0.4,EndX-.0004)/D=W_HFJumps_Up Force_Filtered, 2*Avg_HF			// search for high frequency jumps, going up
	V_HFFound_Up=V_LevelsFound
//	Findlevels/Q/EDGE=2/R=(StartX-0.4,EndX-0.0004)/D=W_HFJumps_Down Force_Filtered, 2.5*Avg_HF			// search for high frequency jumps, goind down FOR AG ONLY
	Findlevels/Q/EDGE=2/R=(StartX-0.4,EndX-0.0004)/D=W_HFJumps_Down Force_Filtered, 2*Avg_HF			// search for high frequency jumps, goind down
	V_HFFound_Down=V_LevelsFound
	
	If(V_HFFound_Up<1||V_HFFound_Down<1)			//Did not find any up or down crossing in the specified range
		StartX=EndX
		Return StartX
	EndIf
	
	Variable FirstHFJump=0, LastHFJump=0															// _HFJump=1 if first jump is found partially, 0 if found fully
	If(W_HFJumps_Up[0]<=W_HFJumps_Down[0])
		FirstHFJump=1
	EndIf
	
	If(W_HFJumps_Up[V_HFFound_Up-1]<=W_HFJumps_Down[V_HFFound_Down-1])
		LastHFJump=1
	EndIf
	
	WAVE W_FindLevels
	Variable NumHFSpikes=(V_HFFound_Down+V_HFFound_Up-FirstHFJump-(LastHFJump))/2
	Make/N=200/O HFSpikes=-2
	Differentiate Force_Filtered/D=Force_Filtered_DIF
	kk=0
	For(jj=0;jj<NumHFSpikes;jj+=1)
	ii=0
		If(max(W_HFJumps_Up[jj+FirstHFJump],W_HFJumps_Down[jj])-min(W_HFJumps_Up[jj+FirstHFJump],W_HFJumps_Down[jj])<=DeltaEx)
			HFSpikes[jj+kk]=max(W_HFJumps_Up[jj],W_HFJumps_Down[jj])
		Else
			Findlevels/Q/R=(min(W_HFJumps_Up[jj+FirstHFJump],W_HFJumps_Down[jj]),max(W_HFJumps_Up[jj+FirstHFJump],W_HFJumps_Down[jj])) Force_Filtered_DIF, 0
			For(ii=0;ii<numpnts(W_FindLevels);ii+=1)
				HFSpikes[jj+kk+ii]=W_FindLevels[ii]
			EndFor
		EndIf
		kk+=(ii-1)
	EndFor
	
	FindLevel/Q/P HFSpikes,0
	DeletePoints (ceil(V_LevelX)), (200-ceil(V_LevelX)), HFSpikes
	Variable NumActualHFSpikes=numpnts(HFSpikes)
	
	Make/O/N=(NumActualHFSpikes,2) HFSpikesDisplay
	HFSpikesDisplay[][1]=-.5
	HFSpikesDisplay[][0]=HFSpikes
	
	//Search for large high frequency jumps with rising and falling edges2 - VERY LARGE HF JUMPS WITHIN A STEP
	jj=0;ii=0;kk=0;
	Variable V_HFFound_Up2=0, V_HFFound_Down2=0
	Make/O W_HFJumps_Up2, W_HFJumps_Down2
	Findlevels/Q/EDGE=1/R=(StartX+.0004,EndX-.0004)/D=W_HFJumps_Up2 Force_Filtered, -.5			// search for high frequency jumps, going up
	V_HFFound_Up2=V_LevelsFound
//	If(V_HFFound_Up2<1)			//Did not find any up crossing
//		Make/O/N=1 W_HFJumps_Up2=0
//	EndIf

	Findlevels/Q/EDGE=2/R=(StartX+.0004,EndX-0.0004)/D=W_HFJumps_Down2 Force_Filtered, -.5			// search for high frequency jumps, going down
	V_HFFound_Down2=V_LevelsFound
//	If(V_HFFound_Down2<1)			//Did not find any up crossing
//		Make/O/N=1 W_HFJumps_Down2=0
//	EndIf
	
	Variable FirstHFJump2=0, LastHFJump2=0															// _HFJump2=1 if first jump is found partially, 0 if found fully
	If(W_HFJumps_Up2[0]<=W_HFJumps_Down2[0])
		FirstHFJump2=1
	EndIf
	
	If(W_HFJumps_Up2[V_HFFound_Up2-1]<=W_HFJumps_Down2[V_HFFound_Down2-1])
		LastHFJump2=1																				// _HFJump2=1 if first jump is found partially, 0 if found fully
	EndIf
	
	WAVE W_FindLevels
	Variable NumHFSpikes2=0
	If(V_HFFound_Up2>0&&V_HFFound_Down2>0)
		NumHFSpikes2=(V_HFFound_Down2+V_HFFound_Up2-FirstHFJump2-(LastHFJump2))/2
	EndIf
	Make/N=200/O HFSpikes2=-2
	//Differentiate Force_Filtered/D=Force_Filtered_DIF
	kk=0
	If(NumHFSpikes2>=1)
		For(jj=0;jj<NumHFSpikes2;jj+=1)
		ii=0
			If(max(W_HFJumps_Up2[jj+FirstHFJump2],W_HFJumps_Down2[jj])-min(W_HFJumps_Up2[jj+FirstHFJump2],W_HFJumps_Down2[jj])<=DeltaEx)
				HFSpikes2[jj+kk]=max(W_HFJumps_Up2[jj],W_HFJumps_Down2[jj])
			Else
				Findlevels/Q/R=(min(W_HFJumps_Up2[jj+FirstHFJump2],W_HFJumps_Down2[jj]),max(W_HFJumps_Up2[jj+FirstHFJump2],W_HFJumps_Down2[jj])) Force_Filtered_DIF, 0
				For(ii=0;ii<numpnts(W_FindLevels);ii+=1)
					HFSpikes2[jj+kk+ii]=W_FindLevels[ii]
				EndFor
			EndIf
			kk+=(ii-1)
		EndFor
	FindLevel/Q/P HFSpikes2,0
	DeletePoints (ceil(V_LevelX)), (200-ceil(V_LevelX)), HFSpikes2
	Variable NumActualHFSpikes2=numpnts(HFSpikes2)
	
	Make/O/N=(NumActualHFSpikes2,2) HFSpikesDisplay2
	HFSpikesDisplay2[][1]=-.5
	HFSpikesDisplay2[][0]=HFSpikes2
	Else
		NumActualHFSpikes2=0
		Make/O/N=(1,2) HFSpikesDisplay2=0
	EndIf
	//Waveout[23]=NumActualHFSpikes2

	
//Search for low frequency jumps with rising and falling edges
	Variable V_LFFound_Up=0, V_LFFound_Down=0
	Make/O W_LFJumps_Up, W_LFJumps_Down
//	Findlevels/Q/EDGE=1/R=(StartX-0.4,EndX-0.0004)/D=W_LFJumps_Up POIntermediate,2.5*Avg_LF			// search for high frequency jumps, going up FOR AG ONLY
	Findlevels/Q/EDGE=1/R=(StartX-0.4,EndX-0.0004)/D=W_LFJumps_Up POIntermediate,2*Avg_LF			// search for high frequency jumps, going up
	V_LFFound_Up=V_LevelsFound
//	Findlevels/Q/EDGE=2/R=(StartX-0.4,EndX-0.0004)/D=W_LFJumps_Down POIntermediate,2.5*Avg_LF			// search for high frequency jumps, goind down FOR AG ONLY
	Findlevels/Q/EDGE=2/R=(StartX-0.4,EndX-0.0004)/D=W_LFJumps_Down POIntermediate,2*Avg_LF			// search for high frequency jumps, goind down
	V_LFFound_Down=V_LevelsFound
	
	Variable FirstLFJump=0, LastLFJump=0															// _LFJump=1 if first jump is found partially, 0 if found fully
	If(W_LFJumps_Up[0]>=W_LFJumps_Down[0])
		FirstLFJump=1
	EndIf
	
	If(W_LFJumps_Up[V_LFFound_Up-1]>=W_LFJumps_Down[V_LFFound_Down-1])
		LastLFJump=1
	EndIf
	
	Variable NumLFSpikes=(V_LFFound_Down+V_LFFound_Up-FirstLFJump-LastLFJump)/2
	Make/N=(NumLFSpikes)/O LFSpikes=0
	Differentiate POIntermediate/D=POIntermediate_DIF
	For(jj=0;jj<NumLFSpikes;jj+=1)
		If(max(W_LFJumps_Up[jj],W_LFJumps_Down[jj+FirstLFJump])-min(W_LFJumps_Up[jj],W_LFJumps_Down[jj+FirstLFJump])<=DeltaEx)
			LFSpikes[jj]=max(W_LFJumps_Up[jj],W_LFJumps_Down[jj])
		Else
			Findlevels/Q/R=(min(W_LFJumps_Up[jj],W_LFJumps_Down[jj+FirstLFJump]),max(W_LFJumps_Up[jj],W_LFJumps_Down[jj+FirstLFJump])) POIntermediate_DIF, 0
			LFSpikes[jj]=W_FindLevels[numpnts(W_FindLevels)-1]
		EndIf
	EndFor
	Make/O/N=(NumLFSpikes,2) LFSpikesDisplay
	LFSpikesDisplay[][1]=.5
	LFSpikesDisplay[][0]=LFSpikes
	
//Determine all locations where LF and HF spikes are close to each other
	Make/O/N=(max(NumActualHFSpikes,NumLFSpikes)) ActualJumps=-2					//NumActualHFSpikes is the upper bound for the number of actual jumps
	kk=0
	For(jj=0;jj<NumActualHFSpikes;jj+=1)
		For(ii=0;ii<NumLFSpikes;ii+=1)
			If(abs(HFSpikes[jj]-LFSpikes[ii])<12*DeltaEx)
				ActualJumps[kk]=(HFSpikes[jj]+LFSpikes[ii])/2
			EndIf
		EndFor
		If(ActualJumps[kk]>0)
			kk+=1
		EndIf
	EndFor
	
	FindLevel/Q/P ActualJumps,0
	DeletePoints (ceil(V_LevelX)), (max(NumActualHFSpikes,NumLFSpikes)-ceil(V_LevelX)), ActualJumps
	Variable NumActualJumps=numpnts(ActualJumps)

	Make/O/N=(NumActualJumps,2) ActualJumpsDisplay=0
	ActualJumpsDisplay[][1]=LowCutOff
	ActualJumpsDisplay[][0]=ActualJumps
	
	Duplicate/O ActualJumps TempJumps
	TempJumps=(TempJumps[p]>(StartX+0.006))
	Waveout[23]=sum(TempJumps)
	//print startx, waveout[23]
	
	StartX=ActualJumps[NumActualJumps-1]
	Return StartX
	
End
Function GetSteps(highcutoff,lowcutoff, [j,Disp])
	Variable highcutoff,lowcutoff,j, Disp
        
	NVAR DisplayNum=root:Data:G_DisplayNum
	NVAR SmoothCond=root:Data:G_SmoothCond
	NVAR SmoothType=root:Data:G_SmoothType
	NVAR SmoothLevel=root:Data:G_SmoothLevel
	NVAR SmoothRepeat=root:Data:G_SmoothRepeat
	NVAR Zero_Cutoff=root:Data:G_zero_cutoff
	NVAR Bin_Size = root:Data:G_ForceHist_Bin_Size
	NVAR SmoothLevel_F=root:Data:G_SmoothLevel
	NVAR LengthCutoff = root:Data:G_StepL_Cutoff
	NVAR SlopeCutoff = root:Data:G_StepS_Cutoff
	
	Bin_Size=1e-5
	Variable Num_Bin=(Highcutoff*2)/Bin_Size

	Wave Conductance_D,W_FindLevels, W_coef, Waveout

	Variable NumPts, V_StepL, V_StepFound=0
	Variable StartX, EndX, StartP, EndP, V_slope, DeltaEx, NumLevels

	Variable SumhistLow, SumHistHigh, SumHist, Tempvar

//	Make/N=1/O Force_D=0
	if (ParamIsDefault(j))
		j=DisplayNum
	endif
	if (LoadCond(Conductance_D,j,N=NumPts)==-1)
		print "Check Wave Number"
		return 0
	endif
//	deletepoints 0,(NumPts-25000), Conductance_D
	NumPts=numpnts(Conductance_D)
	DeltaEx=deltax(Conductance_D)
	Wavestats/Q/R=[NumPts*0.95,NumPts*0.97] Conductance_D
	if ((abs(V_avg)>2*Zero_Cutoff))
		return 0
	endif
	Conductance_D-=V_avg
//	Duplicate/o Conductance_D Conductance_D_Raw
	if (SmoothCond == 1)
		smoothdata(Conductance_D, Conductance_D, SmoothType, SmoothLevel,SmoothRepeat)
	endif
	Make/O/N=1 SingleHist
	Histogram/B={0,Bin_Size,Num_Bin} Conductance_D SingleHist
	sumhist=Sum(SingleHist, lowcutoff,highcutoff)
	
	if (sumhist>((LengthCutoff/DeltaEx)))
		Findlevels/Q/EDGE=2/R=[NumPts/50,NumPts-1] Conductance_D, highcutoff // search only for decreasing levels.
		if (V_flag<2)
			NumLevels=numpnts(W_FindLevels)
			StartX=W_FindLevels[0]
			StartP=x2pnt(Conductance_D, StartX)
			EndX=StartX+0.01
			EndP=x2pnt(Conductance_D, EndX)
			TempVar = sum(Conductance_D,StartX, EndX)/(EndP-StartP+1)
			if (TempVar<highcutoff)
				Findlevels/Q/EDGE=2/R=[StartP,NumPts-1] Conductance_D, lowcutoff // search only for decreasing levels.
				if (V_flag<2)
					NumLevels=numpnts(W_FindLevels)
					EndX=W_FindLevels[NumLevels-1]
					if (EndX>StartX)
						StartP=x2pnt(Conductance_D, StartX)
						if (Conductance_D[StartP]>highCutOff)
							StartP+=1
							StartX=pnt2x(Conductance_D, StartP)
						endif
						EndP=x2pnt(Conductance_D, EndX)
						if (Conductance_D[EndP]<lowcutoff)
							EndP-=1
							EndX=pnt2x(Conductance_D, EndP)
						endif
						If ((EndP-StartP)>5)
							CurveFit/Q/NTHR=0 line Conductance_D[StartP,EndP]/D
							V_Slope=W_coef[1]
							Wavestats/Q/R=(StartX+0.002,EndX-0.002) Conductance_D
							Waveout[4]=V_avg
							V_Slope/=v_avg
						endif
						//Jump condition
												
						Make/O/N=30 Waveout=0
						StartX=GetJumps(StartX,EndX,NumPts)
						
						StartP=x2pnt(Force_D,StartX)
						EndP=x2pnt(Force_D,EndX)

				//		if (sum(Conductance_D,EndX, EndX+0.05)/(0.05/deltaEx)< lowcutoff/50)
						If ((EndX-StartX)>LengthCutoff)
							V_StepL=(EndP-StartP)
							V_StepFound=1.4
						endif
				//		endif
					endif
				endif
			endif
		endif
	endif

	Waveout[0]=V_StepL
	Waveout[1]=V_StepFound
	Waveout[2]=SumHist
	Waveout[3]=DeltaEx
	Waveout[5]=StartX
	Waveout[6]=EndX
	Waveout[7]=V_Slope
	
	if (ParamIsDefault(Disp)|| Disp==1)
		DoWindow/F GetStepsGraph
		if (V_Flag==0)
			Display/W=(0,0,450,300)
			DoWindow/C GetStepsGraph
			AppendToGraph Conductance_D
			ModifyGraph rgb(Conductance_D)=(0,43520,65280)
			AppendToGraph Fit_Conductance_D
			ModifyGraph rgb(fit_Conductance_D)=(0,0,0)
			Label left "Conductance"
			Label bottom "Displacement"	
			ModifyGraph log(left)=1
			SetAxis left 1e-5,10
			ShowInfo
		endif
		printf "Trace %d: Step L %d;  StepS %1.2e; Sum Hist %d;  Hist Ratio %1.2f; SumHistHigh %1.1f; SumHistLow %1.1f \r",DisplayNum, Waveout[0], Waveout[7], SumHist, Waveout[2]/waveout[0], SumHistHigh, SumHistLow
	else
		DoWindow/K GetStepsGraph	
	endif
	return 1
end

Function FindStepForce7([j])
	Variable j
                       
	NVAR DisplayNum=root:Data:G_DisplayNum
	NVAR SmoothCond=root:Data:G_SmoothCond
	NVAR SmoothType=root:Data:G_SmoothType
	NVAR SmoothLevel=root:Data:G_SmoothLevel
	NVAR SmoothLevel_F=root:Data:G_SmoothForce
	NVAR SmoothRepeat=root:Data:G_SmoothRepeat
	NVAR Slope=root:Data:F_CantileverSlope
	NVAR SpringConstant=root:Data:F_CantileverSpringConstant
	NVAR LengthCutoff = root:Data:G_StepL_Cutoff
	NVAR SlopeCutoff = root:Data:G_StepS_Cutoff
	NVAR HighCutOff = root:Data:G_StepMaxG
	NVAR LowCutOff =  root:Data:G_StepMinG
	NVAR Xmin =root:Data:G_Xmin
	NVAR Xmax =root:Data:G_Xmax
	NVAR Ymin =root:Data:G_Ymin
	NVAR Ymax =root:Data:G_Ymax
	NVAR NumXBin =root:Data:G_NumXBin
	NVAR NumYBin =root:Data:G_NumYBin
	NVAR LogLin = root:Data:G_2DLog
	

	Wave Force_2DHist, C_2DHist, POParameter_Display
	Variable DeltaEx, V_fitOptions=4
	Wave Force_D, Conductance_D
		
	Variable StartN, EndN, StartX, EndX, NumPts, EndP
	Wave W_Coef
	Make/N=20/O Waveout=0
	
	if (ParamIsDefault(j))
		j=DisplayNum
	endif
	
	LoadForce(j,Force_D)
	wavestats/R=[NumPts-1000,NumPts]/Q Force_D
	Force_D-=V_avg
	Force_D=Force_D/Slope*SpringConstant

	GetSteps(HighCutOff, LowCutOff,j=j, Disp=0)
	DeltaEx=Waveout[3]
	if (Waveout[7]<SlopeCutoff)
		Waveout[1]=0.5
	endif
	if ((Waveout[6]-Waveout[5])<0.0025)
		Waveout[1]=0.5
	endif
	if (abs(Waveout[1]-1.4)<.1)
		LoadForce(j,Force_D)
		NumPts=numpnts(Force_D)
		//		deletepoints 0,(NumPts-25000), Force_D
		wavestats/R=[NumPts-1000,NumPts]/Q Force_D
		Force_D-=V_avg
		Force_D=Force_D/Slope*SpringConstant
		Wavestats/Q Force_D
		StartN=V_MaxLoc
		EndN=V_npnts*DeltaEx

		smooth/B SmoothLevel_F, Force_D
		Findlevel/EDGE=2/R=(StartN,EndN)/Q Conductance_D,2
		if (V_LevelX<EndN)

			StartX=Waveout[5]
			EndX=Waveout[6]
			EndP=round(EndX/DeltaEx)
			duplicate/o/R=(EndX+xmin,EndX+xmax) Force_D YWave
			duplicate/o/R=(EndX+xmin,EndX+xmax) Force_D XWave
			XWave=(p)*DeltaEx+xmin
			YWave-=Force_D[EndP]
			Waveout[8]=EndP
			doupdate
			duplicate/o/R=(EndX+xmin,EndX+xmax) Conductance_D Con_YWave	
			smooth/B SmoothLevel_F, YWave
			Make2DHist(Force_2DHist,XWave, YWave)//,Xmin,Xmax,Ymin,Ymax,NumXBin,NumYBin)
			if (LogLin==1)
				// For Log-binned conductance hist
				Con_YWave=log(abs(Con_YWave))
				Make2DHist(C_2DHist,XWave, Con_YWave)//,Xmin,Xmax,-7,1,NumXBin,1600)
			else
				//For Linear binned conductance hist
				Make2DHist(C_2DHist,XWave, Con_YWave)//,Xmin,Xmax,0,10,NumXBin,1600)
			endif
		else
			Waveout[1]=0.75
		endif
	endif
end
//
//	Waveout[0]=Step Length in number of points
//	Waveout[1]=Step found or not
//	Waveout[2]=sum histogram
//	Waveout[3]=DeltaEx
//	Waveout[4]=average conductance
//	Waveout[5]=start x value
//	Waveout[6]=end x value
//	Waveout[7]=conductance slope
//	Waveout[8]=EndP
//	Waveout[9]=
//	Waveout[10]=
//	Waveout[11]=
//	Waveout[12]=
//	Waveout[13]=
//	Waveout[14]=
//	Waveout[15]=
//	Waveout[16]=
//	Waveout[17]=
//	Waveout[18]=

Function Force2DButton(ctrlname) : ButtonControl
	String ctrlname
	SVAR ForceName=root:Data:S_ForceName
	
	FindStepForce2D(ForceName)
	
End


Function FindStepForce2D(Name,[Disp])
	Variable Disp
	String Name
	
	Wave IncludedNumbers=root:Data:IncludedNumbers
	NVAR Zero_Cutoff=root:Data:G_zero_cutoff
	NVAR Total_Included = root:Data:G_Total_Included
	NVAR Start = root:Data:G_RedimStart
	NVAR Stop = root:Data:G_RedimStop
	SVAR PathDate=root:Data:G_PathDate
	NVAR SmoothCond=root:Data:G_SmoothCond
	NVAR SmoothType=root:Data:G_SmoothType
	NVAR SmoothLevel=root:Data:G_SmoothLevel
	NVAR SmoothLevel_F=root:Data:F_SmoothLevel
	NVAR SmoothRepeat=root:Data:G_SmoothRepeat
	NVAR Slope=root:Data:F_CantileverSlope
	NVAR SpringConstant=root:Data:F_CantileverSpringConstant
	NVAR LengthCutoff = root:Data:G_StepL_Cutoff
	NVAR SlopeCutoff = root:Data:G_StepS_Cutoff
	NVAR HighCutOff = root:Data:G_StepMaxG
	NVAR LowCutOff =  root:Data:G_StepMinG
	NVAR Bin_Size = root:Data:G_ForceHist_Bin_Size
	NVAR SmoothDummy = root:Data:G_SmoothDummy
	NVAR Xmin =root:Data:G_Xmin
	NVAR Xmax =root:Data:G_Xmax
	NVAR Ymin =root:Data:G_Ymin
	NVAR Ymax =root:Data:G_Ymax
	NVAR NumXBin =root:Data:G_NumXBin
	NVAR NumYBin =root:Data:G_NumYBin
	NVAR CounterN=root:Data:G_Counter
	NVAR LogLin = root:Data:G_2DLog
	
	Variable Starttime=Datetime
	
	Variable i,j,k, DeltaEx, ZPiezoScale=0.9138
	Wave Waveout, AvgForce, Force_2DHist, AvgWidth

	
	if (cmpstr(Name,"foo")==0)
		Name = "foo"
	else
		Name=Name+"_"+num2str(Start)+"_"+num2str(Stop)+"_"+PathDate
		//		Name=Name+"_"+PathDate
	endif
	if (ParamIsDefault(Disp))
		Disp=0
	endif
	
	Make/O/N=(NumXBin,NumYBin) Force_2DHist=0;
	SetScale/I x Xmin,Xmax,"", Force_2DHist;	
	SetScale/I y Ymin,Ymax,"", Force_2DHist
	Make/O/N=(NumXBin,1600) C_2DHist=0;
	if (LogLin==1)
	// For Log-binned conductance hist
		SetScale/I y -7,1,"", C_2DHIst
	else
		// FOr Linear binned cond hist
		SetScale/I y 0,10,"", C_2DHIst
	endif
	SetScale/I x Xmin,Xmax,"",C_2DHist;

	Total_Included=numpnts(IncludedNumbers)

	make/O/N=(Total_Included) StepL=0, StepLoc=0,  IN=0, Keep=0, AvgC=0

	IN=IncludedNumbers
	CounterN=0
	for (k=0;k<=Total_Included;k+=1)
		i=IncludedNumbers[k]
		FindStepForce7(j=i)
		StepL[k]=Waveout[0]
		Keep[k]=Waveout[1]
		DeltaEx=Waveout[3]
		AvgC[k]=Waveout[4]
		StepLoc[k]=Waveout[8]
		CounterN+=1
	endfor

	Sort  Keep IN,StepL,StepLoc,Keep, AvgC
	FindValue/V=1.4 Keep
	if (V_Value > -1)
		deletepoints 0,V_value,IN,StepL,StepLoc,Keep, AvgC
	else
		print "No Traces Found"
		return 0
	endif
	FindValue/V=1.5 Keep
	if (V_Value>0)
		redimension/N=(V_Value) IN,StepL,StepLoc,Keep, AvgC
	endif
	Sort  IN IN, StepL, StepLoc, Keep, AvgC
	
	print "Found", numpnts(IN), "Name",Name	
	duplicate/o IN IncludedNumbers
	If (numpnts(IN) > 0)
		CalcMax()
	endif
	
	Make/O/N=20 Para
	Para[0]=Zero_Cutoff
	Para[1]=Slope
	Para[2]=SpringConstant
	Para[3]=LengthCutoff
	Para[4]=SlopeCutOff
	Para[5]=HighCutOff
	Para[6]=LowCutOff
	Para[7]=Bin_Size
	Para[8]=SmoothDummy
	Para[9]=SmoothLevel
	Para[10]=SmoothLevel_F
	Para[11]=NumXBin
	Para[12]=NumYBin
	Para[13]=Xmin
	Para[14]=Xmax
	Para[15]=Ymin
	Para[16]=Ymax
	Para[17]=DeltaEx
	Para[18]=0

	duplicate/o IN $("IN"+Name)
	duplicate/o Force_2DHist $("Force_2D"+Name)
	duplicate/o AvgForce $("AvgForce"+Name)
	duplicate/o AvgWidth $("AvgWidth"+Name)	
	duplicate/o C_2DHist $("C_2D_"+Name)
	duplicate/o AvgC $("AvgC_"+Name)
	duplicate/o StepL $("StepL"+Name)
	duplicate/o StepLoc $("StepLoc"+Name)
	duplicate/o Para $("Para"+Name)
	
	StepL*=DeltaEx	
	NewPath/O ForceData "Macintosh HD:Users:Latha:Sync:AFM:Analysis:ForceWaves:"
	
	Save/C/O/P=ForceData $("Force_2D"+Name),$("AvgForce"+Name),$("IN"+Name), $("Para"+Name),$("AvgC_"+Name)
	Save/C/O/P=ForceData $("C_2D_"+Name),$("AvgWidth"+Name),$("StepL"+Name), $("StepLoc"+Name)

	killwaves $("Force_2D"+Name), $("C_2D_"+Name), $("AvgC_"+Name),$("IN"+Name)
	killwaves $("Para"+Name),$("StepL"+Name), $("StepLoc"+Name), $("AvgWidth"+Name),$("AvgForce"+Name)
	
	SaveExperiment
	print "Length: ", LengthCutoff, ", Slope: ", SlopeCutoff, ", High: ", HighCutOff, ", Low: ", LowCutOff, ", Bin: ", Bin_Size
	print "Time to run: ",Datetime-Starttime
	DoWindow/F Force2D
	if (V_Flag==0)
		execute "Force2D()"
	endif
	DoWindow/F CondF2D
	if (V_Flag==0)
		execute "CondF2D()"
	endif

end
Function CalcMax()

	Wave Force_2DHist
	NVAR SmoothDummy = root:Data:G_SmoothDummy

	wave w_coef, w_sigma
	Variable V_fitOptions=4 //Stops curve fit window from appearing
	Variable numXpts = dimsize(Force_2DHist, 0)
	Variable numYpts = dimsize(Force_2DHist, 1)
	make/O/N=(numXpts) AvgForce=0, AvgWidth=0
	SetScale x dimoffset(Force_2DHist,0),dimoffset(Force_2DHist,0)+dimdelta(Force_2DHist,0)*(numXpts-1),"", AvgForce, AvgWidth
	Variable k, Num
	For (k=0;k<numXpts-1;k+=1)

		make/O/N=(numYpts) dummy=0
		dummy=Force_2DHist[k][p]
		SetScale/I x dimoffset(Force_2DHist,1),dimoffset(Force_2DHist,1)+dimdelta(Force_2DHist,1)*(numYpts-1),"", dummy
		W_coef=0
		Smooth/B SmoothDummy, dummy
		Num=numpnts(dummy)
		K0 = 0;
			
		CurveFit/Q/H="1000" gauss, dummy/D
		AvgForce[k]=w_coef[2]
		AvgWidth[k]=w_coef[3]//w_sigma[2]
	endfor
	CurveFit/NTHR=0/Q line  AvgForce(.05,.1)
	print "Force from fit", w_coef[0]
end

Function/S GetAxisLabel(gname, axisname)	
	String gname, axisname
 	
 	//Finds top graph
 	gname = WinName(0, 1)
 	
	String grecreation = WinRecreation(gname, 0)
	String oneLine
	String labelStr = ""
	String part1, part2

	Variable i=0
	do
		oneLine = StringFromList(i, grecreation, "\r")
		if (stringmatch(oneLine, "\tLabel *" + axisname + "*"))
			String regexp = "^\\tLabel "+axisname+" \\\"(.*)\\\""
			SplitString/E=regexp oneLine, labelStr
			//Yes you really do need all 3
			labelStr = ReplaceString("\\\\", labelStr, "\\")
			labelStr = ReplaceString("\\\\", labelStr, "\\")
			labelStr = ReplaceString("\\\\", labelStr, "\\")
			break;
		endif
		i += 1
	while(strlen(oneLine) > 0)
 
	return labelStr
end

Function SLButton(ba) : ButtonControl
	STRUCT WMButtonAction &ba

	switch( ba.eventCode )
		case 2: // mouse up
			SetAxis left 1e-06,*
			break
	endswitch

	return 0
End

Function LogLinButton(ctrlName) : ButtonControl
	String ctrlName
	DoWindow/F POGXAnalysis
	If (numberbykey("log(x)",axisinfo("POGXAnalysis","left"),"=")==0)
		ModifyGraph log(left)=1
	else
		ModifyGraph log(left)=0
	endif	
End
Function LogLinButtonF(ctrlName) : ButtonControl
	String ctrlName
	DoWindow/F POGFXAnalysis
	If (numberbykey("log(x)",axisinfo("POGFXAnalysis","left"),"=")==0)
		ModifyGraph log(left)=1
	else
		ModifyGraph log(left)=0
	endif	
End

Window FooGraph() : Graph
	PauseUpdate; Silent 1		// building window...
	String fldrSav0= GetDataFolder(1)
	SetDataFolder root:Data:
	Display /W=(582,200,982,529) foo,namefoo
	SetDataFolder fldrSav0
	ModifyGraph lSize(namefoo)=1.5
	ModifyGraph rgb(foo)=(0,0,0),rgb(namefoo)=(1,4,52428)
	ModifyGraph log=1
	ModifyGraph tick=2
	ModifyGraph mirror=2
	ModifyGraph fSize=12
	ModifyGraph standoff=0
	ModifyGraph axThick=1.5
	Label left "Counts/(1000 Traces)"
	Label bottom "Conductance (G\\B0\\M)"
EndMacro

Window LogFoo() : Graph
	PauseUpdate; Silent 1		// building window...
	String fldrSav0= GetDataFolder(1)
	SetDataFolder root:Data:
	Display /W=(984,199,1553,718) foolog,namefoolog,POConductanceHistLog
	ModifyGraph userticks(bottom)={TickPosLog,TickLabel}
	SetDataFolder fldrSav0
	ModifyGraph lSize(namefoolog)=1.5
	ModifyGraph rgb(foolog)=(0,0,0),rgb(namefoolog)=(1,4,52428)
	ModifyGraph tick=2
	ModifyGraph mirror=2
	ModifyGraph font="Arial"
	ModifyGraph fSize=14
	ModifyGraph standoff=0
	ModifyGraph axThick=1.5
	Label left "Counts/(1000 Traces)"
	Label bottom "Conductance (G\\B0\\M)"
	SetAxis left 0,10000
EndMacro

Window Cond2D() : Graph
	PauseUpdate; Silent 1		// building window...
	Display /W=(481,591,892,953)
	AppendImage :Data:total2DHist
	ModifyImage total2DHist ctab= {*,*,Geo32,1}
	ModifyGraph userticks(left)={TickPosLog,TickLabel}
	ModifyGraph margin(left)=50,margin(bottom)=50
	ModifyGraph tick=2
	ModifyGraph mirror=2
	ModifyGraph font="Arial"
	ModifyGraph fSize=14
	ModifyGraph standoff=0
	ModifyGraph axThick=1.5
	ModifyGraph axisOnTop=1
	Label left "Conductance (G\\B0\\M)"
	Label bottom "Displacement (nm)"
EndMacro

Window Force2D() : Graph
	PauseUpdate; Silent 1		// building window...
	String fldrSav0= GetDataFolder(1)
	SetDataFolder root:Data:
	Display /W=(503,511,943,1009) AvgForce
	AppendImage Force_2DHist
	ModifyImage Force_2DHist ctab= {*,200,Geo32,1}
	SetDataFolder fldrSav0
	ModifyGraph margin(left)=50,margin(bottom)=50,width=360,height=432
	ModifyGraph lSize=2
	ModifyGraph rgb=(0,0,0)
	ModifyGraph tick=2
	ModifyGraph mirror=2
	ModifyGraph fSize=14
	ModifyGraph standoff=0
	ModifyGraph axThick=1.5
	ModifyGraph axisOnTop=1
EndMacro
Window CondF2D() : Graph
	PauseUpdate; Silent 1		// building window...
	Display /W=(57,511,496,1009) as "CondF2D"
	AppendImage :Data:C_2DHist
	ModifyImage C_2DHist ctab= {*,50,Geo32,1}
	ModifyGraph userticks(left)={TickPosLog,TickLabel}
	ModifyGraph margin(left)=50,margin(bottom)=50,width=360,height=432
	ModifyGraph tick=2
	ModifyGraph mirror=2
	ModifyGraph font="Arial"
	ModifyGraph fSize=14
	ModifyGraph standoff=0
	ModifyGraph axThick=1.5
	ModifyGraph axisOnTop=1
	Label left "Conductance (G\\B0\\M)"
	Label bottom "Displacement (nm)"
EndMacro

