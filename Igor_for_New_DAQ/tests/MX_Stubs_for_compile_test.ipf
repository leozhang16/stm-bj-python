#pragma TextEncoding = "UTF-8"
#pragma rtGlobals=3

// ---------------------------------------------------------------------------
// MX_Stubs_for_compile_test.ipf
//
// COMPILE-TEST ONLY. DO NOT LOAD THIS FILE ON THE LAB PC.
//
// On the lab PC the functions below are provided by DaqMxFunctions.xop (the
// lab's NI-DAQmx extension, 32-bit Windows). That XOP cannot load on a Mac, so
// this file defines Igor functions with the same names and argument lists,
// doing nothing, purely so that the procedure files in the parent folder can be
// compiled by Igor Pro on a machine without the XOP. Loading it together with
// the XOP would give "function already defined" errors.
//
// Argument lists are inferred from every call site in the procedures:
//   MXCreateTask(globalNameStr)                 sets the named global to a task id
//   MXCreateAIVoltageChan(task, chanStr, lo, hi)
//   MXCreateAOVoltageChan(task, chanStr, lo, hi)
//   MXCfgSampClkTiming(task, rate, sampleMode, samplesPerChannel)   0 = finite, 1 = continuous
//   MXReadAnalogF64(task, timeout, numChannels, wave)   wave holds numChannels blocks
//   MXWriteAnalogF64(task, timeout, numChannels, wave)
//   MXStartTask(task), MXStopTask(task), MXClearTask(task)
//   MXResetDevice(deviceStr)
// ---------------------------------------------------------------------------

Function MXCreateTask(globalName)
	String globalName
	NVAR/Z v = $globalName
	if (NVAR_Exists(v))
		v = 1
	endif
	return 0
End

Function MXCreateAIVoltageChan(task, chan, lo, hi)
	Variable task
	String chan
	Variable lo, hi
	return 0
End

Function MXCreateAOVoltageChan(task, chan, lo, hi)
	Variable task
	String chan
	Variable lo, hi
	return 0
End

Function MXCfgSampClkTiming(task, rate, sampleMode, samplesPerChan)
	Variable task, rate, sampleMode, samplesPerChan
	return 0
End

Function MXReadAnalogF64(task, timeout, numChans, w)
	Variable task, timeout, numChans
	Wave w
	w = 0
	return 0
End

Function MXWriteAnalogF64(task, timeout, numChans, w)
	Variable task, timeout, numChans
	Wave w
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
	return 0
End
