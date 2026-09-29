# Electrochemical gate and cyclic voltammetry

Put the junction in electrolyte, hold the solution at a controlled potential
with a counter electrode, and measure conductance as a function of that
potential. Plus the voltammetry you need to know the cell is alive.

## The physics

A dry break junction has two terminals: tip and substrate. An electrochemical
one has a third. The tip and substrate sit in electrolyte, and a **counter
electrode** holds the solution at a potential you choose. Because the
molecule is immersed in that solution, shifting the solution potential shifts
the molecule's energy levels relative to the Fermi level of the electrodes —
without changing the source–drain bias at all.

That is a **gate**, and it is the electrochemical analogue of a transistor's
gate terminal. Sweep it while measuring conductance and you get a transfer
curve. For a redox-active molecule the interesting feature is a **conductance
peak**: as a molecular level is dragged through resonance with the electrodes,
transmission rises and then falls again. The gate voltage at the peak tells
you where that level sits, which is a number you cannot get from a two-terminal
measurement at any bias.

Two things make this harder than it sounds, and both shape the code:

**The gate is slow.** After you change the counter-electrode potential the
electrical double layer has to re-equilibrate. Traces taken during that are
at an unknown gate. Hence `--settle`, defaulting to 5 s rather than 0.

**The zero moves.** The cell leaks. Faradaic and capacitive currents through
the electrolyte are gate-dependent, so the preamp reading at "no junction" at
−200 mV is not the reading at +200 mV. This experiment therefore re-measures
`current_zero_v` at **every gate**, not once per session. An uncorrected
offset would put a false floor under one gate's histogram and not another's —
which reads exactly like gate-dependent physics, and is the most convincing
artefact this experiment can produce.

## Cyclic voltammetry

A CV sweeps the electrode potential in a triangle at a fixed scan rate and
records the current. You get:

* **capacitive current**, proportional to scan rate, flipping sign with sweep
  direction — the rectangular "box" of the loop;
* **faradaic peaks** where a species is oxidised or reduced, anodic on the
  up-sweep and cathodic on the down-sweep, separated by ~60 mV for a
  reversible one-electron couple.

You run it to answer three questions before trusting any gated data: is the
cell connected, is the electrolyte clean, and where are the redox peaks — so
you know which gate range is worth scanning and which will just electrolyse
your solvent.

Igor built the triangle as `0 → V1 → 0 → V2 → 0`, then repeated the first
half and **NaN-ed** the opening quarter and the repeat, so each saved cycle is
a steady-state loop with the switch-on transient discarded. This translation
keeps that masking as a boolean `keep` array beside the full record instead of
destroying samples, so a later reader can second-guess the choice.

## Igor origin

`igor_code/EChem_Module.ipf`:

| Python | Igor | Line |
|---|---|---|
| `echem.CounterElectrode.set_mv` | `WriteToCounterElectrode` | 88 |
| `echem.CounterElectrode.on` | `StartEChemWriting` | 63 |
| `echem.build_cv_ramp_highres` | `CVcurveHighRes` ramp | 127–158 |
| `echem.build_cv_ramp_lowres` | `CVcurveLowRes` ramp | 251–286 |
| `echem.run_cv` | the acquisition loops of both | 178, 306 |

Igor saved the gate with every trace as `ParameterWave[18]`. Here it lives in
`cfg.echem.gate_mv`, which is serialised into every file's `config_json`, plus
a `gate_mv` attribute on the file.

## Two cards

The counter electrode is on the **low-res card's ao1** (`Setup1_STMBJ.ipf:11`).
This rig currently has one card, so:

| Command | Needs the second card? |
|---|---|
| `cv --kind highres` | **no** — drives `dev1/ao1`, the junction-bias output |
| `cv --kind lowres` | yes |
| `gate`, `traces` | yes |

`gate` and `traces` refuse with a clear message if `channels.low_res_device`
is `None`. The high-res CV works on the card you have, because there the tip
itself is the working electrode.

> **`cv --kind highres` repurposes the junction-bias output.** Retract before
> running it. The code warns, but it cannot check.

## Running it

```bash
# Is the cell alive? (no hardware needed to rehearse)
python run.py 06 cv --simulate --cycles 3 --plot

# Set a gate and walk away (leaves the card holding it, as Igor's did)
python run.py 06 gate --mv -200

# Set it, hold it for 60 s, then return to 0
python run.py 06 gate --mv -200 --hold 60

# The actual experiment: a gate sweep, 200 traces at each of five gates
python run.py 06 traces --gate-mv -400 -200 0 200 400 -n 200
```

Add `--simulate` to any of them. `gate` and `traces` will still refuse without
a configured second card unless simulating.

### The gate is left on, on purpose

`gate --mv X` without `--hold` releases the DAQmx task **without zeroing the
channel**, so the card keeps driving it after the process exits. That matches
what Igor's always-open task looked like to the operator. It also means a
voltage stays on an electrode with nothing watching it, so the command says so
loudly. `--mv 0` clears it; `traces` always returns the gate to 0 mV on exit,
including on exception and Ctrl-C.

## What gets stored

**`traces`** — one `gate_<mv>mV.h5` per gate, the standard trace schema
(raw volts, full config, per-trace scalars), plus a `gate_mv` attribute.

**`cv`** — a `record_kind="cv"` file with its own schema, because a
voltammogram is not a trace: no piezo axis, no alignment spike, no verdict.

| Dataset | Shape | |
|---|---|---|
| `applied_v` | `(n,)` | commanded electrode potential, stored once |
| `keep` | `(n,)` bool | Igor's mask; False over the transient and the repeat |
| `tip_current_v` | `(cycles, n)` | raw preamp output |
| `we_voltage_mv` | `(cycles, n)` | measured electrode potential (high-res only) |

Read it back with `storage.CVSession`:

```python
from stmlab import storage
with storage.CVSession("data/cv_20260828.h5") as cv:
    v = cv.applied_v[cv.keep]
    i = cv.current_a(0)[cv.keep]        # amps, from raw volts
```

## Status

`echem.py` is a faithful translation, and every line of it runs in simulate.
**None of it has met an electrochemical cell.** The `nidaqmx` calls for the
gate and for both CV variants are in the same position `daq.py` was in before
bring-up: written, reviewed, never executed against hardware. The simulated
cell (a 1 µF double layer plus one reversible couple near +0.2 V) produces
data with the right *shape* to exercise the code, and no chemistry whatsoever.

Simulate first. Then a dummy cell with a known resistor. Then real electrolyte.
