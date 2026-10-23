#pragma TextEncoding = "UTF-8"
#pragma rtGlobals=3

// ---------------------------------------------------------------------------
// RoundTrip_IgorScheme.ipf -- does Igor read what the Python program writes?
// TEST ONLY (Mac test harness). Needs the measurement code and the analysis
// macro loaded (Setup_NewDAQ_STMBJ.ipf includes STMBJ_HistogramAnalysis.ipf).
//
//     ClaudeIgorSchemeRoundTrip("Macintosh HD:...:10_22_26Merge:", "Macintosh HD:...:result.txt")
//
// It uses the lab's OWN loaders on a day folder written by pullout.py:
//   * PullOutInitialize() and LoadCond / LoadVoltage / LoadCurrent from the
//     analysis macro, exactly as the PullOut panel does,
//   * LoadWave for the histogram and extension blocks,
//   * LogHistFromBlocks from the measurement code, recomputed on the loaded
//     block and compared with the PullOutConductanceBlockHist_1 file Python wrote.
// Numbers are written to the result file so the Python side can compare them.
// ---------------------------------------------------------------------------

Static Function Rep(refnum, ok, what)
	Variable refnum, ok
	String what
	fprintf refnum, "%s %s\r", SelectString(ok, "FAIL", "PASS"), what
	return ok
End

Function ClaudeIgorSchemeRoundTrip(folder, resultPath)
	String folder, resultPath

	Variable refnum
	Open refnum as resultPath
	fprintf refnum, "IGOR SCHEME ROUND TRIP %s\r", date() + " " + time()
	fprintf refnum, "INFO folder %s\r", folder

	// the measurement globals (for LogHistFromBlocks) and the analysis macro's environment
	SetDataFolder root:
	if (exists("G_AcquisitionRate") == 0)
		Declare_STMBJ_Variables()
	endif
	PullOutInitialize()					// root:Data globals, G_mergecheck = 1, current folder root:Data
	NewPath/O Relocate folder
	Rep(refnum, V_flag == 0, "NewPath Relocate -> " + folder)
	SetDataFolder root:Data

	// ---- conductance traces through the macro's own loader -------------------------
	Make/O/N=0 Cond_D
	Variable N = 0
	Variable err = LoadCond(Cond_D, 1, N=N)
	Rep(refnum, err == 0, "LoadCond(1): block 1 found and loaded")
	Wave POParameter_Display
	fprintf refnum, "INFO trace 1: N=%d size_nm=%g rate=%g bias_mV=%g conv=%g Rs=%g thr=%g first=%.7g last=%.7g sum=%.7g leftx=%g rightx=%g\r", N, POParameter_Display[0], POParameter_Display[1], POParameter_Display[10], POParameter_Display[9], POParameter_Display[12], POParameter_Display[13], Cond_D[0], Cond_D[N-1], sum(Cond_D), leftx(Cond_D), pnt2x(Cond_D, N-1)
	Rep(refnum, N > 0 && numpnts(Cond_D) == N, "trace 1 has N = " + num2str(N) + " points after the 22-row tail is cut")
	Rep(refnum, POParameter_Display[0] > 0 && POParameter_Display[1] > 0, "trace 1 parameters: size and rate are set")
	Rep(refnum, abs(pnt2x(Cond_D, N-1) - POParameter_Display[0]) < 1e-6, "SetScale/I x 0,Size puts the last point at Size")

	err = LoadCond(Cond_D, 100, N=N)
	Rep(refnum, err == 0 && numtype(Cond_D[0]) == 0, "LoadCond(100): the last column of block 1 holds a trace")
	fprintf refnum, "INFO trace 100: first=%.7g last=%.7g sum=%.7g\r", Cond_D[0], Cond_D[N-1], sum(Cond_D)

	err = LoadCond(Cond_D, 101, N=N)
	Rep(refnum, err == 0, "LoadCond(101): block 2 found")
	fprintf refnum, "INFO trace 101: first=%.7g last=%.7g sum=%.7g\r", Cond_D[0], Cond_D[N-1], sum(Cond_D)
	err = LoadCond(Cond_D, 120, N=N)
	fprintf refnum, "INFO trace 120: first=%.7g last=%.7g sum=%.7g\r", Cond_D[0], Cond_D[N-1], sum(Cond_D)
	err = LoadCond(Cond_D, 121, N=N)
	Rep(refnum, err == 0 && numtype(Cond_D[0]) == 2, "LoadCond(121): an unfilled column of the partial block 2 reads as NaN")

	// ---- companions through the macro's loaders ------------------------------------
	Make/O/N=0 Volt_D, Cur_D
	err = LoadVoltage(Volt_D, 1)
	Rep(refnum, err == 0, "LoadVoltage(1): PullOutVoltageBlock_1 found")
	fprintf refnum, "INFO voltage 1: npnts=%d first=%.7g last=%.7g\r", numpnts(Volt_D), Volt_D[0], Volt_D[numpnts(Volt_D)-1]
	err = LoadCurrent(Cur_D, 1)
	Rep(refnum, err == 0, "LoadCurrent(1): PullOutCurrentBlock_1 found")
	fprintf refnum, "INFO current 1: npnts=%d first=%.7g last=%.7g\r", numpnts(Cur_D), Cur_D[0], Cur_D[numpnts(Cur_D)-1]

	// the Extension block exists only when the rig has a piezo sense line (Save Sense writes it)
	GetFileFolderInfo/Q/Z/P=Relocate "PullOutExtensionBlock_1.ibw"
	if (V_flag == 0)
		LoadWave/Q/H/P=Relocate/O "PullOutExtensionBlock_1.ibw"
		Rep(refnum, V_flag == 1, "PullOutExtensionBlock_1.ibw loads")
		Wave ext = $"PullOutExtensionBlock_1"
		fprintf refnum, "INFO extension block: rows=%d cols=%d dx=%g first=%.7g\r", dimsize(ext,0), dimsize(ext,1), dimdelta(ext,0), ext[0][0]
		Rep(refnum, dimsize(ext,1) == 100 && abs(dimdelta(ext,0)*(dimsize(ext,0)-1) - POParameter_Display[0]) < 1e-6, "extension block: 100 columns, x scaled 0..Size")
	else
		fprintf refnum, "INFO no PullOutExtensionBlock_1.ibw (a rig without a piezo sense line writes none)\r"
	endif

	// ---- the raw block as a wave: shape, type, the two zero rows ----------------------
	LoadWave/Q/H/P=Relocate/O "PullOutConductanceBlock_1.ibw"
	Wave blk = $"PullOutConductanceBlock_1"
	Variable rows = dimsize(blk, 0)
	fprintf refnum, "INFO conductance block 1: rows=%d cols=%d type=%d dx=%g\r", rows, dimsize(blk,1), WaveType(blk), dimdelta(blk,0)
	Rep(refnum, WaveType(blk) == 2, "conductance block is single precision (WaveType 2), as Igor's")
	Rep(refnum, dimsize(blk,1) == 100 && rows == N + 22, "conductance block is (N+22) x 100")
	Rep(refnum, blk[N][0] == 0 && blk[N+1][0] == 0 && blk[N][99] == 0 && blk[N+1][99] == 0, "the two rows after the trace are exactly 0, as Igor's Redimension leaves them")
	Rep(refnum, dimdelta(blk,0) == 1 && dimoffset(blk,0) == 0, "conductance block carries no x scaling, as Igor's")

	// ---- the histogram file against Igor's own LogHistFromBlocks on the same block -------
	LoadWave/Q/H/P=Relocate/O "PullOutConductanceBlockHist_1.ibw"
	Rep(refnum, V_flag == 1, "PullOutConductanceBlockHist_1.ibw loads")
	if (V_flag == 1)
		Wave hfile = $"PullOutConductanceBlockHist_1"
		fprintf refnum, "INFO hist file: npnts=%d leftx=%g dx=%.10g type=%d sum=%.7g\r", numpnts(hfile), leftx(hfile), deltax(hfile), WaveType(hfile), sum(hfile)
		Rep(refnum, numpnts(hfile) == 1000 && leftx(hfile) == -8 && abs(deltax(hfile) - 10/999) < 1e-12, "hist file: 1000 points, x from -8, dx = 10/999 (SetScale/I x -8,2)")
		// recompute with the measurement code (constant mode: no section deleted)
		SetDataFolder root:
		NVAR pp = G_PushPullCheck; NVAR iv = G_IVCheck; NVAR ac = G_ACHoldCheck; NVAR hb = G_HBHoldCheck
		pp = 0; iv = 0; ac = 0; hb = 0
		Duplicate/O blk, root:RT_Block
		Wave rtb = root:RT_Block
		LogHistFromBlocks(rtb)
		Wave LogHistWave
		Duplicate/O LogHistWave, root:RT_Hist
		Wave rth = root:RT_Hist
		Duplicate/O rth, root:RT_Diff
		Wave rtd = root:RT_Diff
		rtd = abs(rth - hfile[p])
		WaveStats/Q rtd
		fprintf refnum, "INFO recomputed hist: sum=%.7g max=%g at %g; max |difference| to the file = %g (relative %g)\r", sum(rth), WaveMax(rth), rth[0] == rth[0] ? pnt2x(rth, 0) : 0, V_max, V_max/max(WaveMax(rth), 1e-12)
		Rep(refnum, V_max < 1e-3*max(WaveMax(rth), 1e-12), "Python's histogram file equals Igor's LogHistFromBlocks on the same block (within 0.1 %: single precision and Smooth/B end handling)")
		SetDataFolder root:Data
	endif

	// ---- the partial block 2 -----------------------------------------------------------
	LoadWave/Q/H/P=Relocate/O "PullOutConductanceBlock_2.ibw"
	Wave blk2 = $"PullOutConductanceBlock_2"
	Variable filled = 0, c
	for (c = 0; c < dimsize(blk2, 1); c += 1)
		if (numtype(blk2[0][c]) == 0)
			filled += 1
		endif
	endfor
	fprintf refnum, "INFO block 2: filled columns = %d of %d\r", filled, dimsize(blk2, 1)
	Rep(refnum, dimsize(blk2, 1) == 100 && filled == 20, "partial block 2 is still 100 columns wide with 20 filled (traces 101-120)")

	fprintf refnum, "END\r"
	Close refnum
	SetDataFolder root:
	return 0
End
