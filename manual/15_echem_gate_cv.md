# 15. EChem gate and cyclic voltammetry

*Igor: `EChem_Module.ipf`. Experiment folder:
`experiments/06_echem_gate_cv/`. Module: `stmlab/echem.py`.*

## The third terminal

A dry break junction has two terminals. An electrochemical one has three.

Tip and substrate sit in electrolyte; a **counter electrode** holds the
solution at a potential you choose. Because the molecule is immersed in that
solution, changing the solution potential shifts the molecule's energy levels
relative to the Fermi level of the electrodes — **without touching the
source–drain bias**.

That is a gate, in exactly the transistor sense. And it buys you something no
two-terminal measurement can give: as a molecular level is dragged through
resonance with the electrodes, transmission rises and then falls, producing a
**conductance peak versus gate voltage**. The gate potential at that peak
locates the level.

## Three subcommands, because Igor's module held three things

| Command | Igor | Does |
|---|---|---|
| `gate` | `WriteToCounterElectrode` :88 | set the DC gate |
| `cv` | `CVcurveHighRes` / `LowRes` :106 / :234 | a voltammogram |
| `traces` | the gate + `StartMeasurement` | **the actual experiment** |

`traces` is the point. The other two are the instrument controls it is built
from, exposed separately because you will want to set a gate and walk away,
or take a voltammogram to check the cell, without acquiring anything.

## Two things that make this harder than it looks

**The gate is slow.** After changing the counter-electrode potential the
electrical double layer takes time to re-equilibrate. Traces acquired during
that are at an unknown gate. Hence `--settle`, defaulting to **5 s** rather
than 0. If your electrolyte is viscous or your electrode large, 5 s may not
be enough — that is an experimental question, not a software one.

**The zero moves with the gate.** The cell leaks: faradaic and capacitive
currents through the electrolyte are gate-dependent. The preamp reading with
no junction at −200 mV is *not* the reading at +200 mV.

So this experiment re-measures `current_zero_v` **at every gate**, not once
per session. Skipping that puts a false floor under one gate's histogram and
not another's — which is indistinguishable from gate-dependent physics, and
is the most convincing artefact this experiment can produce. It would show up
as a beautiful, entirely fictional conductance peak.

## Cyclic voltammetry

Sweep the electrode potential in a triangle at fixed scan rate, record the
current. You get **capacitive current** (proportional to scan rate, flipping
sign with direction — the rectangular box of the loop) and **faradaic peaks**
where species are oxidised or reduced, ~60 mV apart for a reversible
one-electron couple.

Run it to answer three questions before trusting any gated data: is the cell
connected, is the electrolyte clean, and where are the redox peaks — so you
know which gate range is worth scanning and which will just electrolyse your
solvent.

### Igor's masking, kept as a mask

Igor built `0 → V1 → 0 → V2 → 0`, then repeated the first half and **NaN-ed**
the opening quarter and the repeat, so each saved cycle is a steady-state
loop with the switch-on transient discarded.

This translation reproduces the same choice as a **boolean `keep` array
stored beside the full record**, rather than destroying samples. A later
reader can second-guess where the transient ended; with NaNs they could not.
Same default behaviour, recoverable.

## Which card

The counter electrode is on the **low-res card's ao1**
(`Setup1_STMBJ.ipf:11`). This rig has one card, so:

| | Needs the second card? |
|---|---|
| `cv --kind highres` | **no** — drives `dev1/ao1`, the junction-bias output |
| `cv --kind lowres` | yes |
| `gate`, `traces` | yes |

`gate` and `traces` refuse with a clear message when
`channels.low_res_device` is `None`.

> **`cv --kind highres` repurposes the junction-bias output.** Retract before
> running it. The code warns; it cannot check.

## The gate is left on, deliberately

`gate --mv X` without `--hold` releases the DAQmx task **without zeroing the
channel**, so the card keeps driving it after the process exits. That is what
Igor's always-open task looked like to an operator.

It also means a voltage stays on an electrode with no process watching it, so
the command says so loudly. `--mv 0` clears it. `--hold N` returns to 0 after
N seconds. `traces` always returns the gate to 0 mV on exit, including on
exception and Ctrl-C.

A bug found while writing this chapter: `off()` cleared the object's gate but
not `cfg.echem.gate_mv`, so the config — which is written into every data
file — went on claiming a gate that was no longer applied. Fixed, with a test.

## Status

`echem.py` is a faithful translation and every line runs in simulate.
**None of it has met an electrochemical cell.** The `nidaqmx` calls for the
gate and both CV variants are exactly where `daq.py` was before bring-up:
written, reviewed, never executed.

The simulated cell is a 1 µF double layer plus one reversible couple near
+0.2 V. It produces the right *shape* to exercise the code and contains no
chemistry whatsoever.

Simulate. Then a dummy cell with a known resistor. Then electrolyte.
