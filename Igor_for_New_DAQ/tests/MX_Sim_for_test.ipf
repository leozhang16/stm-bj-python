#pragma TextEncoding = "UTF-8"
#pragma rtGlobals=3

// ---------------------------------------------------------------------------
// MX_Sim_for_test.ipf -- a pretend one-card DAQ for dry runs WITHOUT the XOP.
//
// TEST ONLY. DO NOT LOAD THIS FILE ON THE LAB PC (it defines the same function
// names as DaqMxFunctions.xop). Do not load it together with
// MX_Stubs_for_compile_test.ipf either.
//
// What it pretends:
//   * The AO task that writes [piezo block][bias block] (2 channels) drives a
//     simulated junction. Every write appends its samples to a history, so a
//     later read can return what "happened" during a trace.
//   * The AI task (3 channels: voltage, current, piezo sense) returns, for each
//     sample, the applied bias as the junction-voltage monitor, the preamp
//     output for a junction whose conductance depends on the piezo extension,
//     and the piezo sense readback.
//   * Reads whose length equals G_NumPtsInAppliedWaves + 2000 (the trace read
//     in GenerateTrace) are "trace reads": they return the trace with a fixed
//     output-to-input delay of sim_DelayPts samples, exactly the thing
//     GenerateTrace has to recover from the alignment spike. Any other read is
//     a "hold read": every sample is the current hold value.
//   * Junction model, z = piezo extension (nm), d = sim_ContactZ_nm - z (gap):
//        d <= 0           metallic, G = G0 * (1 + 2*|d|/nm)   (pushing harder: more G)
//        0 < d <= 0.3 nm  G = 1 G0 plateau (the gold 1 G0 step)
//        d > 0.3 nm       tunnelling, G = G0 * exp(-(d-0.3)/0.1 nm)
//     preamp output = G * V * 10^sim_GainExp volts, clipped to +/-10 V.
//   * Every task remembers its channel list, read channel counts are checked
//     against the task's channel count, and any mismatch is appended to the
//     string sim_Errors so a test can assert on it.
// ---------------------------------------------------------------------------

Function Sim_Init()
	// parameters (created once, test code may change them)
	if (exists("sim_ContactZ_nm")==0)
		Variable/G sim_ContactZ_nm = 300		// nm of piezo extension where the tip touches
		Variable/G sim_DelayPts = 37			// output -> input latency in samples
		Variable/G sim_GainExp = 6				// preamp gain 10^n V/A (match G_CurrentVoltGain)
		Variable/G sim_NoiseV = 2e-5			// rms noise on every input, volts
		Variable/G sim_ZScale = 62				// nm per piezo volt (match K_ZPiezoScale)
		Variable/G sim_SenseScale = 314		// nm per sense volt (match K_SenseScale)
		Variable/G sim_G0 = 77.480917346e-6	// siemens
	endif
	// state
	Variable/G sim_NextTaskID = 100
	Variable/G sim_HoldPiezoV = 0
	Variable/G sim_HoldBiasV = 0
	Variable/G sim_CEVolts = 0
	Variable/G sim_NumWrites = 0
	Variable/G sim_NumReads = 0
	String/G sim_Errors = ""
	String/G sim_Log = ""
	Make/O/D/N=0 sim_PiezoHist, sim_BiasHist
	Make/O/T/N=0 sim_TaskChans		// text wave: index = task id - 100, value = "chan1;chan2;..."
	Make/O/N=0 sim_TaskNumChans
	Make/O/N=0 sim_TaskIsAO
	SetRandomSeed 0.5
End

Static Function Sim_Err(msg)
	String msg
	SVAR/Z e = sim_Errors
	if (SVAR_Exists(e))
		e += msg + ";"
	endif
	Print "SIM ERROR: " + msg
End

Static Function Sim_LogIt(msg)
	String msg
	SVAR/Z l = sim_Log
	if (SVAR_Exists(l))
		l += msg + ";"
	endif
End

// Conductance in siemens for a piezo command voltage
Static Function Sim_Conductance(piezoV)
	Variable piezoV
	NVAR ContactZ = sim_ContactZ_nm
	NVAR ZScale = sim_ZScale
	NVAR G0 = sim_G0
	Variable d = ContactZ - piezoV*ZScale		// gap in nm; negative = pushed into contact
	Variable G
	if (d <= 0)
		G = G0*(1 + 2*(-d))
		G = min(G, 20*G0)
	elseif (d <= 0.3)
		G = G0
	else
		G = G0*exp(-(d-0.3)/0.1)
	endif
	return G
End

// Preamp output volts for a bias and a piezo command
Static Function Sim_CurrentVolts(piezoV, biasV)
	Variable piezoV, biasV
	NVAR GainExp = sim_GainExp
	// the junction sees the applied bias; current = G*V; preamp converts with 10^GainExp V/A.
	// Sign: the real rig writes -(TipBias/1000) on the bias output and the preamp output has
	// been positive for positive TipBias in the archived data, so flip the sign once here.
	Variable I = Sim_Conductance(piezoV) * (-biasV)
	Variable v = I * 10^GainExp
	return limit(v, -10, 10)
End

// --------------------------------------------------------------- XOP look-alikes

Function MXCreateTask(globalName)
	String globalName
	if (exists("sim_NextTaskID")==0)
		Sim_Init()
	endif
	NVAR nextID = sim_NextTaskID
	Wave/T chans = sim_TaskChans
	Wave nch = sim_TaskNumChans
	Wave isAO = sim_TaskIsAO
	Variable id = nextID
	nextID += 1
	Redimension/N=(id-100+1) chans, nch, isAO
	chans[id-100] = ""
	nch[id-100] = 0
	isAO[id-100] = 0
	NVAR/Z v = $globalName
	if (NVAR_Exists(v))
		v = id
	else
		Sim_Err("MXCreateTask: no global named " + globalName)
	endif
	Sim_LogIt("CreateTask " + globalName + "=" + num2str(id))
	return id
End

Static Function Sim_AddChan(task, chan, ao)
	Variable task
	String chan
	Variable ao
	Wave/T chans = sim_TaskChans
	Wave nch = sim_TaskNumChans
	Wave isAO = sim_TaskIsAO
	Variable i = task - 100
	if (i < 0 || i >= numpnts(chans))
		Sim_Err("AddChan: unknown task id " + num2str(task))
		return -1
	endif
	chans[i] += chan + ";"
	nch[i] += 1
	isAO[i] = ao
	return 0
End

Function MXCreateAIVoltageChan(task, chan, lo, hi)
	Variable task
	String chan
	Variable lo, hi
	Sim_LogIt("AI " + num2str(task) + " " + chan + " [" + num2str(lo) + "," + num2str(hi) + "]")
	return Sim_AddChan(task, chan, 0)
End

Function MXCreateAOVoltageChan(task, chan, lo, hi)
	Variable task
	String chan
	Variable lo, hi
	Sim_LogIt("AO " + num2str(task) + " " + chan + " [" + num2str(lo) + "," + num2str(hi) + "]")
	return Sim_AddChan(task, chan, 1)
End

Function MXCfgSampClkTiming(task, rate, sampleMode, samplesPerChan)
	Variable task, rate, sampleMode, samplesPerChan
	Sim_LogIt("Clk " + num2str(task) + " rate=" + num2str(rate) + " mode=" + num2str(sampleMode) + " N=" + num2str(samplesPerChan))
	return 0
End

Function MXStartTask(task)
	Variable task
	return 0
End

Function MXStopTask(task)
	Variable task
	return 0
End

Function MXClearTask(task)
	Variable task
	return 0
End

Function MXResetDevice(dev)
	String dev
	Sim_LogIt("ResetDevice " + dev)
	// a device reset puts every output at 0 V
	NVAR/Z hp = sim_HoldPiezoV
	NVAR/Z hb = sim_HoldBiasV
	NVAR/Z ce = sim_CEVolts
	if (NVAR_Exists(hp))
		hp = 0; hb = 0; ce = 0
	endif
	return 0
End

// Write: [block per channel]. 2-channel AO task = piezo, bias. 1-channel AO task = counter electrode.
Function MXWriteAnalogF64(task, timeout, numChans, w)
	Variable task, timeout, numChans
	Wave w
	if (exists("sim_NextTaskID")==0)
		Sim_Init()
	endif
	Wave nch = sim_TaskNumChans
	NVAR hp = sim_HoldPiezoV
	NVAR hb = sim_HoldBiasV
	NVAR ce = sim_CEVolts
	NVAR nw = sim_NumWrites
	Variable i = task - 100
	if (i < 0 || i >= numpnts(nch))
		Sim_Err("Write: unknown task " + num2str(task))
		return -1
	endif
	if (nch[i] != numChans)
		Sim_Err("Write: task " + num2str(task) + " has " + num2str(nch[i]) + " channels, write says " + num2str(numChans))
	endif
	Variable n = floor(numpnts(w)/numChans)
	if (n*numChans != numpnts(w))
		Sim_Err("Write: wave length " + num2str(numpnts(w)) + " not a multiple of " + num2str(numChans))
	endif
	nw += 1
	if (numChans == 2)
		Wave ph = sim_PiezoHist
		Wave bh = sim_BiasHist
		Variable old = numpnts(ph)
		if (old > 200000)
			// keep the history bounded (a trace read needs traceLen + 1000 samples, ~11000 here);
			// without this every write gets slower as the run goes on
			DeletePoints 0, old - 60000, ph, bh
			old = numpnts(ph)
		endif
		Redimension/N=(old+n) ph, bh
		ph[old, old+n-1] = w[p-old]
		bh[old, old+n-1] = w[n + p-old]
		hp = w[n-1]
		hb = w[2*n-1]
	elseif (numChans == 1)
		ce = w[n-1]
	else
		Sim_Err("Write: unexpected channel count " + num2str(numChans))
	endif
	return 0
End

// Read: [voltage block][current block][sense block], N samples per channel.
Function MXReadAnalogF64(task, timeout, numChans, w)
	Variable task, timeout, numChans
	Wave w
	if (exists("sim_NextTaskID")==0)
		Sim_Init()
	endif
	Wave nch = sim_TaskNumChans
	NVAR hp = sim_HoldPiezoV
	NVAR hb = sim_HoldBiasV
	NVAR noise = sim_NoiseV
	NVAR delay = sim_DelayPts
	NVAR ZScale = sim_ZScale
	NVAR SenseScale = sim_SenseScale
	NVAR nr = sim_NumReads
	Wave ph = sim_PiezoHist
	Wave bh = sim_BiasHist
	Variable i = task - 100
	if (i < 0 || i >= numpnts(nch))
		Sim_Err("Read: unknown task " + num2str(task))
		return -1
	endif
	if (nch[i] != numChans)
		Sim_Err("Read: task " + num2str(task) + " has " + num2str(nch[i]) + " channels, read says " + num2str(numChans))
	endif
	if (numChans != 3)
		Sim_Err("Read: expected a 3-channel read (voltage, current, sense), got " + num2str(numChans))
		w = 0
		return -1
	endif
	Variable n = floor(numpnts(w)/numChans)
	if (n*numChans != numpnts(w))
		Sim_Err("Read: wave length " + num2str(numpnts(w)) + " not a multiple of " + num2str(numChans))
	endif
	nr += 1

	// Which piezo/bias sample belongs to read sample k?
	Make/O/D/N=(n) sim_rdPiezo, sim_rdBias
	NVAR/Z NumPtsApplied = G_NumPtsInAppliedWaves
	Variable traceLen = 0
	if (NVAR_Exists(NumPtsApplied))
		traceLen = NumPtsApplied
	endif
	Variable histLen = numpnts(ph)
	if (traceLen > 0 && n == traceLen + 2000 && histLen >= traceLen + 1000)
		// trace read: the trace was written as traceLen samples followed by one 1000-sample hold buffer
		Variable traceStart = histLen - 1000 - traceLen
		sim_rdPiezo = ph[limit(traceStart - delay + p, 0, histLen-1)]
		sim_rdBias  = bh[limit(traceStart - delay + p, 0, histLen-1)]
	else
		sim_rdPiezo = hp
		sim_rdBias  = hb
	endif

	// voltage block: the junction-voltage monitor reads the applied bias
	w[0, n-1] = sim_rdBias[p] + gnoise(noise)
	// current block: preamp output
	w[n, 2*n-1] = Sim_CurrentVolts(sim_rdPiezo[p-n], sim_rdBias[p-n]) + gnoise(noise)
	// sense block: piezo readback in volts, so that volts*SenseScale = extension in nm
	w[2*n, 3*n-1] = sim_rdPiezo[p-2*n]*ZScale/SenseScale + gnoise(noise)
	return 0
End
