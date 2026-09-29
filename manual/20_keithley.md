# 20. Keithley 428

*Igor: `SetUpGPIB_Keithley.ipf`, plus `SetGain` and `SetCurrentSuppress` in
`Controls_STMBJ.ipf`. Module: `stmlab/keithley.py`.*

## What it is

The Keithley 428 is the **current preamplifier** — the box that turns the
picoamps-to-microamps flowing through your junction into volts the DAQ card
can read. Everything in this folder that says "conductance" ultimately says
"the 428's output voltage, divided by its gain".

It sits on GPIB at address 22 (Igor's `ibdev={0,22,...}`), and speaks a terse
command language where `X` executes the buffer.

| Command | Means | Igor |
|---|---|---|
| `C1X` / `C0X` | zero-check on / off | `ZeroCheckProc` :262 |
| `C2X` | zero-correct | `ZeroCorrectProc` :277 |
| `H6R<g>X` | gain = 10^g V/A | `SetGain` :290 |
| `H8S<amps>,0X` | suppress value | `SetCurrentSuppress` |
| `N1X` / `N0X` | suppress on / off | |
| `B1X` / `B0X` | internal bias source on / off | `KeithleyBias` :67 |
| `V<mV>E-3X` | bias value | `KeithleyBiasVolt` :95 |
| `P1X` / `P0X`, `T<n>X` | filter on/off, rise time | `KeithleyFilter` :37 |

Igor's init string is `C1P0B0N0X`: zero-check on, filter off, bias off,
suppress off. **The amplifier wakes up inert**, which is the right default for
a box wired to a tip.

## Gain is the number that scales every result

`gain_exponent = 6` means 10⁶ V/A. That single number multiplies every
conductance in every file. Get it wrong by a factor of ten and your gold peak
lands exactly one decade off — which chapter 10 will tell you, but only if you
look.

Two derived values Igor kept as globals live here as properties:

```
conversion_ua_per_v = 10**(6 - gain)              G_CurrentVoltConversion
suppress_from_const = const * 10**(3 - gain)      G_CurrentSuppress
```

## Current suppress, and `find_suppress`

The amplifier has an offset. At zero junction current its output is not zero.
**Suppress** is a compensating current you dial in to null that.

`find_suppress` is Igor's `TestVirtualGround` (`Functions_STMBJ.ipf:1097`):

1. sweep the suppress from −1 to +1 µA in 21 steps;
2. after each step, wait for the amplifier to settle — Igor's `sleep/T 5`,
   with a comment about "the SPIKE problem" at line 1123;
3. read 2000 samples of the output;
4. fit a line through the **middle** points and set the suppress to the zero
   crossing.

The endpoints are excluded from the fit deliberately: the amplifier is still
settling at the extremes of the sweep, and including them tilts the line.

Igor's `FindSuppress` button zeroed the applied bias first and restored it
afterwards (`Controls_STMBJ.ipf:479`). **Do the same around this call** — the
function itself does not, because it cannot know what bias you wanted back.

## When the Keithley sources the bias

`B1X` turns on the 428's internal bias source. When that is driving the
junction, the junction voltage is **no longer measured at `ai0`** — you know
only the total two-terminal current, and the wiring's series resistance is in
the path.

So the conductance needs a correction, and Igor had it at `GenerateTrace:390`:

```
G/G0 = (1 / (V_bias/I - R_series)) / G0
```

That is `series_corrected_conductance()`. `R_series` defaults to
**106,130 Ω** — Igor's `G_SeriesResistance`, an inherited number for that
rig's wiring, not a measurement of yours.

> If you use Keithley-sourced bias, **measure your own series resistance**.
> 106 kΩ is comparable to the resistance of a 0.1 G₀ junction, so a wrong
> value does not scale your result — it distorts the shape of the whole
> low-conductance region, and it does it in a way that looks like physics.

## Simulated

`SimulatedKeithley` has the same surface and records state, so every
experiment script runs on a laptop. It does not model the amplifier's
noise, bandwidth, or settling.

## Status

**Never connected to a Keithley.** The command strings are transcribed from
the Igor source and reviewed; pyvisa is not even in `requirements.txt` by
default. Before trusting it:

1. talk to the amplifier with `pyvisa` by hand and confirm it answers;
2. set a gain and verify it on the front panel;
3. run `find_suppress` and check the resulting output offset with a meter;
4. only then wire it to a tip.

Chapter 03 covers what needs what.
