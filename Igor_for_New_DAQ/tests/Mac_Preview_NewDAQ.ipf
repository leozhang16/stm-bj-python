#pragma TextEncoding = "UTF-8"
#pragma rtGlobals=3

// ---------------------------------------------------------------------------
// Mac_Preview_NewDAQ.ipf -- open THIS file in Igor on a Mac (or any PC without the
// DAQ extension) to compile and look at the STM-BJ code and its panels.
//
// The real code calls MXCreateTask, MXReadAnalogF64, ... from DaqMxFunctions.xop,
// a 32-bit Windows extension that cannot load on a Mac. This wrapper first loads
// Igor stand-ins for those functions, then the real setup file one folder up.
// With the stand-ins the panels open and the buttons run, but nothing is
// measured: reads return zeros. For a pretend junction use MX_Sim_for_test.ipf
// instead of the stubs (see tests/Smoke_NewDAQ.ipf).
//
// NEVER load this file, or anything in tests/, on the lab PC: it would define the
// MX functions twice (extension + stand-ins) and refuse to compile.
// ---------------------------------------------------------------------------

#include ":MX_Stubs_for_compile_test"
#include "::Setup_NewDAQ_STMBJ"
