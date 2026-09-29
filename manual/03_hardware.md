# 03. Hardware

## The rig as wired

This rig runs a **single NI PXI-4461** (two AO, two AI, delta-sigma), which
differs from the two-card layout in project-architecture.pdf but matches the
Igor code exactly (config.py's module docstring): the junction bias comes
from ao1 on the same card, and there is no current-suppression output on the
DAQ -- suppression, when used, is the Keithley 428's own.

| Channel | Signal | Range | Notes |
|---|---|---|---|
| Dev1/ao0 | Z-piezo command | 0 to +10 V (card-enforced from `SafetyLimits`) | Through the piezo driver box; 62 nm/V end to end (`K_ZPiezoScale`). **Unipolar**: 0 V is fully retracted, the safe state |
| Dev1/ao1 | Junction bias | +/-2.5 V (`G_HighResOutputRange`) | Written as `-(TipBias/1000)`, Igor's sign convention (Functions_STMBJ.ipf:347); also carries the alignment spike, and the high-res CV repurposes it |
| Dev1/ai0 | Junction voltage monitor | +/-10 V | Negated to recover the junction voltage (Functions_STMBJ.ipf:358); the alignment spike is found here |
| Dev1/ai1 | Current preamp output | +/-10 V | Rf = 1e6 V/A by default; readings above 9.5 V count as railed, and railed counts as contact |

AI is hardware-triggered off `/Dev1/ao/StartTrigger`, so every output play
has a synchronised input record and Python never times anything. The AO idle
behaviour is `MAINTAIN_EXISTING_VALUE` so the piezo holds position between
plays; if the card refuses it, `daq.py` warns loudly and bring-up step 3 is
the test that decides whether the approach can work at all.

The piezo driver box sits between ao0 and the piezo. Its gain is deliberately
not used in any arithmetic: `cal.piezo_nm_per_volt = 62.0` is an end-to-end
number for the whole chain, and all piezo limits are expressed at the DAQ
output (`SafetyLimits` docstring). The coarse approach is a Newport NanoPZ;
the STM head carries the gold tip over a gold-on-mica substrate, with the
current preamp reading the tip.

## What needs the second card

Igor's rig had a second, low-res card ("dev2", Setup1_STMBJ.ipf:36-41). In
this package it is `channels.low_res_device`, default `None` -- and `None`
means every feature that needs it **refuses cleanly** instead of guessing:

| Feature | Channel on the second card | Refusal without it |
|---|---|---|
| Lateral X piezo (experiment 07) | `<dev2>/ao0`, 0-10 V, 522 nm/V (`K_XPiezoScale`, Setup1_STMBJ.ipf:40) | `XPiezoError: no low-res device configured` (xpiezo.py `setup`) |
| EChem counter electrode / gate | `<dev2>/ao1`, +/-5 V (Igor `MXCreateAOVoltageChan(-5,5)`) | `EChemError: no low-res device configured` (echem.py `CounterElectrode.on`) |
| Low-res CV (`run_cv(kind="lowres")`) | Same counter-electrode channel, driven +/-10 V as Igor did | `EChemError: lowres CV needs channels.low_res_device` |
| Piezo sense readback | Igor read the driver's output voltage back and stored it as POExtension | Not translated: with one card the displacement axis is the commanded trajectory (analysis.py `displacement_nm`); the piezo is open-loop either way |

The high-res CV needs **no** second card -- it drives Dev1/ao1, the
junction-bias channel, with the tip as working electrode. That is exactly why
it must be treated with care (see the pre-flight checks below).

## The Keithley 428 (GPIB address 22)

The current amplifier is a Keithley 428 on `GPIB0::22::INSTR` (Igor:
`ibdev={0,22,...}`, SetUpGPIB_Keithley.ipf:9), reached through pyvisa and an
NI GPIB interface. It speaks a terse command language where `X` executes the
buffer; the init string on open is Igor's `C1P0B0N0X` -- zero-check on,
filter off, bias off, suppress off -- so the amplifier wakes up inert, and
`close()` leaves it inert again (`C1B0N0X`).

What it controls, all in `stmlab/keithley.py`:

* **Gain**: `set_gain(exponent)` programs 10^exponent V/A (`H6R<g>X`) and
  re-derives Igor's globals: conversion `10**(6-g)` uA/V and suppress
  `suppress_const * 10**(3-g)` uA (Controls_STMBJ.ipf:304-310). The config's
  `cal.preamp_gain_v_per_a` must agree with the exponent actually programmed
  or every conductance is scaled.
* **Current suppression**: `set_suppress_ua` / `suppress_enable`, and
  `find_suppress(rig, keithley)` -- Igor's `TestVirtualGround`
  (Functions_STMBJ.ipf:1097): sweep the suppress -1 to +1 uA in 21 steps at
  zero bias, fit the middle points, set the zero crossing.
* **Keithley-sourced bias**: `bias_enable` (`B1X`) and `set_bias_mv`
  (quantised to 5 mV, as Igor's `SetTipBiasVoltage` did). When the Keithley
  sources the bias, the junction voltage is no longer measured at ai0 and
  conductance needs `series_corrected_conductance(current_a, bias_v,
  r_series)` -- Igor's formula from GenerateTrace:390 with
  `G_SeriesResistance = 106130` ohm.

`SimulatedKeithley` has the same surface and records every command, so the
Keithley experiments run on a laptop.

## The NanoPZ (serial)

The coarse actuator is a Newport NanoPZ controller on a serial port: 19200
baud, 8N1, CRLF line endings (Igor's `in=2, out=2`). Igor hardcoded Com1; on
USB it is usually COM3 or higher -- `actuator.list_serial_ports()` or
bring-up step 5 finds it, and if nothing appears at all the controller may be
on a proprietary USB driver rather than a virtual COM port, which pyserial
cannot reach.

Protocol (actuator.py): `0MO` motor on, `0PR<n>` relative move (a
**negative** count moves toward the sample -- `StepActuatorCloser`,
NanoPZ_Actuator_Functions_STM.ipf:22), `0ST` stop, `0TS?`/`0TP?` status and
position (replies echo the command; the reply parser strips it). One
configured step is `actuator.step_size = 5` controller steps
(`G_ActuatorStepSize`), and each `Rig.coarse_step()` passes the retracted-
piezo interlock and the 2000-step budget first. A step advances the tip
further than the piezo's whole 10 V range: nothing but `Rig.coarse_step` is
allowed to call the actuator, and it never runs with the piezo extended
above 0.1 V.

## What refuses cleanly when hardware is absent

The package is importable and testable with no instrument stack installed;
every hardware dependency is imported inside the function that needs it.

| Missing | What happens |
|---|---|
| `nidaqmx` not installed | `Rig.open()` fails at `from .daq import DaqSession` unless `cfg.simulate` is set; `--simulate` replaces the card with `sim.SimulatedDaqSession` and never imports nidaqmx. `bringup` prints "Cannot run ... must run on the rig PC" and exits 1 |
| Configured device absent or renamed | `safety.verify_devices` (run by `SafeSession.__enter__`) raises `SafetyViolation`, naming what is present; aliases move when cards change slots |
| Wrong card model | `verify_devices` refuses: the channel map assumes the 4461's pinout, and driving the piezo ramp into a preamp input destroys the preamp |
| `low_res_device = None` | X piezo and EChem gate/low-res CV raise `XPiezoError`/`EChemError` with an explicit message (see above) |
| `pyserial` missing / port wrong | `ActuatorError`, listing every serial port the OS can see; `actuator.kind = "none"` makes the coarse approach a by-hand step (`coarse_approach` raises `ApproachError` telling you so) |
| `pyvisa` / GPIB missing | `Keithley428.open()` fails at `import pyvisa`; `cfg.simulate` gives `SimulatedKeithley` instead |
| `igor2` missing | Only `storage.load_ibw` (reading archived Igor waves) needs it |

Simulated stand-ins exist for every instrument: the card (`sim.py`), the
actuator (`SimulatedActuator`), the Keithley (`SimulatedKeithley`), the
counter electrode (`SimulatedCounterElectrode`, plus a simulated
electrochemical cell in `run_cv`), and the X piezo (`SimulatedXPiezo`).

## The bring-up ladder

First contact with the card is five ordered steps (`stmlab/bringup.py`), run
on the rig PC as `python run.py constant_bias bringup <step>` or
`python -m stmlab.bringup <step>`. **Every step runs with the piezo
disconnected and no tip near the sample.** Each prints PASS / CHECK / FAIL
rows; do not continue past a FAIL.

| Step | Name | Wiring | What it decides |
|---|---|---|---|
| 1 | devices | none | The card exists, is a PXI-4461, has the four channels; the granted sample rate (a delta-sigma card grants discrete rates -- put the granted value in the config) |
| 2 | timing | one BNC: ao1 -> ai0 | AI is genuinely triggered off `ao/StartTrigger`: group delay measured 25 times, scatter must be well under one sample or displacement and current are not aligned |
| 3 | output hold | one BNC: ao0 -> ai0 | The decisive test for the approach: does ao0 keep its value between plays (MAINTAIN_EXISTING_VALUE), and does the piezo line ever go negative (it must not -- unipolar) |
| 4 | preamp gain | known resistor (default 1 MOhm) at the preamp input | 100 mV across 1 MOhm at 1e6 V/A must read 0.100 V; measures the preamp zero and the noise floor in G0. A gain error here scales every conductance the rig ever reports |
| 5 | coarse actuator | NanoPZ on USB | Serial ports listed, controller replies to `0TS?`/`0TP?`; motion only with `--move`, and it steps *away* from the sample first |

The last rung is deliberately not automated (bringup.py's module
docstring): only after the electrical steps pass, connect the piezo, watch
ao0 on a scope through one `engage()`, and confirm it ramps 0 to 10 V and
never goes negative. Only then does a tip go in.

## Before an EChem or Keithley experiment

The bring-up ladder validates the 4461 path only. The hardware-only code in
`keithley.py`, `echem.py` and `xpiezo.py` has never met its instruments (see
the trust order in chapter 00), so check the following first.

Keithley:

* The GPIB chain answers at address 22 (`pyvisa` resource
  `GPIB0::22::INSTR`) and `open()` reaches the inert init state -- with the
  amplifier's input **disconnected from the tip** the first time.
* `keithley.gain_exponent` matches `cal.preamp_gain_v_per_a`; if you change
  the gain with `set_gain`, change the calibration with it.
* Run `find_suppress` with the applied bias zeroed and restored around the
  call, as Igor's FindSuppress button did (Controls_STMBJ.ipf:479); the
  amplifier must be out of zero-check or the sweep is flat and the fit
  refuses.
* If the Keithley is to source the bias (`B1X`): the junction voltage is no
  longer at ai0, conductance must use `series_corrected_conductance`, and
  `series_resistance_ohm` (default 106130) must be the measured value for
  this wiring.

EChem:

* The gate and the low-res CV need `channels.low_res_device` set and the
  counter electrode actually wired to `<dev2>/ao1`; both refuse otherwise.
* The **high-res CV repurposes Dev1/ao1, the junction-bias output**, with
  the tip as working electrode. Withdraw the tip (`rig.withdraw()`) before
  `run_cv(kind="highres")`, expect the bias to be whatever the ramp left --
  the function parks the channel at 0 V when it finishes, as Igor reset the
  card afterwards -- and unplug nothing mid-run.
* CV peak potentials (`peak_one_v`/`peak_two_v`, default -1/+1 V) exceed
  the 0.5 V junction-bias limit by design; they are electrode potentials in
  solution, applied by a dedicated task with its own range. Confirm the cell
  chemistry tolerates them before starting.
* Simulate first: `run_cv` under `cfg.simulate` produces the classic
  capacitive-plus-faradaic hysteresis loop and exercises the full analysis.
