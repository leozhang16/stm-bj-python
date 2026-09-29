# 13. AC hold

*Igor: `CreateInputs` AC-hold branch, `Functions_STMBJ.ipf:1539-1564`.
Experiment folder: `experiments/04_ac_hold/`. Builder:
`ramps.build_ac_hold`.*

## What it measures

Hold the junction still and make the bias a **pure sine** — 0.8 V amplitude
at 10 kHz by default — instead of a DC level.

```
initial pull 3 nm      DC baseline
cap 0.5 nm             DC baseline
hold 3 nm worth        bias = amp * sin(2*pi*f*t), replacing the baseline entirely
cap 0.5 nm             DC baseline
final pull 4 nm
```

The sine **replaces** the DC baseline during the hold; it is not added to it.
That is Igor's behaviour and it matters for interpretation: the junction
spends the hold symmetrically biased about zero, not about −100 mV.

## Why drive a junction with a sine

Three reasons, in increasing order of ambition:

**Noise rejection.** The interesting response is concentrated at one
frequency. Everything else — 1/f drift, mains pickup, the slow wander of the
preamp zero — is somewhere else in the spectrum and can be filtered away.
This is the lock-in principle, and it is why a 10 kHz sine can measure a
conductance that a DC hold cannot resolve.

**Harmonics.** A linear (ohmic) junction driven at frequency *f* responds
only at *f*. A **non-linear** one also responds at 2*f*, 3*f*, … The
amplitude of the second harmonic is a direct measure of the curvature of
`I(V)` at zero bias — the same physics chapter 12 gets from a full sweep,
but at one frequency and in a fraction of the time.

**Speed.** An IV sweep takes the whole hold. A sine gives you a
conductance estimate every cycle: at 10 kHz that is 100 µs, fast enough to
watch a junction switch between states in real time.

## The one number to check before trusting anything

**The sample rate must be far above the drive frequency.** At 40 kHz sampling
and a 10 kHz sine you have **four samples per cycle**. That is above Nyquist,
so the fundamental is recoverable in principle — but it is nowhere near
enough to see the second harmonic at 20 kHz, which sits exactly *at* Nyquist
and is indistinguishable from DC aliasing.

So with the shipped defaults:

* the fundamental amplitude is measurable;
* **harmonic analysis is not possible**, and any second-harmonic number you
  compute from this data is an artefact.

If harmonics are what you are after, either drop `freq_khz` to 1–2 kHz
(20–40 samples per cycle) or raise `sample_rate_hz`. The 4461 will go to
204.8 kHz; check what it actually grants, because a delta-sigma card coerces
(chapter 03).

This is not a defect in the translation — Igor's defaults have the same
property. It is a limit of the settings, and it is worth knowing before you
believe a number.

## Running it

```bash
python run.py 04 --simulate -n 20
python run.py 04 -n 200 --amp 0.5 --freq-khz 2
```

## Status

Translated index-for-index with geometry tests; the sine's amplitude,
frequency and placement inside the hold are all asserted. It runs end to end
on the simulator.

The **simulated junction has no frequency response at all** — its conductance
depends on position, not on how fast the bias is changing. So a simulated AC
hold returns a clean sine in current, exactly in phase, with no harmonics and
no phase lag. That tests the waveform, the segments and the storage. It
cannot tell you anything about a real junction's dynamics, and it will never
warn you about the sampling limit above.
