# AC bias hold

Hold the junction at fixed piezo extension while a pure sine wave replaces
the DC bias, and read the conductance out with lock-in demodulation of the
current at the modulation frequency.

## The physics

A DC conductance measurement on a held junction has two problems. First,
everything the current amplifier sees at DC -- amplifier offset, leakage,
electrochemical background in liquid -- is indistinguishable from junction
current. Moving the measurement to a known frequency f rejects all of it:
capacitive charging current is 90 degrees out of phase with the bias and
lands in the quadrature (Y) channel, while the resistive junction current is
in phase (X), so demodulation separates conductance from capacitance in one
shot. Second, a sustained DC bias stresses a molecular junction --
electromigration, local heating, and in solution, sustained electrochemistry
at the contacts. A zero-mean sine of the same amplitude applies no net field
over a period, so the junction can be interrogated for the whole hold
without the DC stress.

The trajectory: pull an atomic contact out by `init_pull_nm` (into the
molecular/tunnelling regime), let it settle through a short cap at DC bias,
then hold the piezo still while the bias channel carries
`amp * sin(2*pi*f*t)` -- the sine **replaces** the DC baseline entirely,
there is no DC offset under the modulation -- then a second cap and a final
pull that breaks the junction for good. Per trace, the runner prints what a
lock-in referenced to the written sine would show:

    X = mean(I * sin(2*pi*f*t)),  Y = mean(I * cos(2*pi*f*t))
    R = 2 * hypot(X, Y)                  amplitude of I at f, in amps
    G = R / (amp * G0)                   conductance in units of G0

All "lengths" including the hold are in nanometres *at the pull rate*
(Igor's parameterisation): a 3 nm hold lasts as long as pulling 3 nm would
(0.15 s at the default 20 nm/s).

## Igor origin

Translated from `igor_code/Functions_STMBJ.ipf`:

| Python                              | Igor                                  | lines     |
| ----------------------------------- | ------------------------------------- | --------- |
| `stmlab.ramps.build_ac_hold`        | `CreateInputs`, AC-hold branch        | 1539-1564 |
| this runner's acquisition loop      | `MeasureBreakJunctions`               | 1664      |
| `stmlab.trace.capture`              | `GenerateTrace`                       | 284       |
| `cfg.ac_hold` defaults              | `G_AC*` globals                       | 108-114   |

Igor line 1564 is the defining line: during the hold the bias wave is
assigned `ACAmp*sin(2*pi*ACFreq*1000*(p-ACindex2)/AcquisitionRate)` --
frequency in kHz, no DC term. The lock-in printout is new here (Igor stored
the raw waves and demodulated offline); the stored data is the same raw
record either way, so both analyses remain possible.

Two deliberate deviations, both loud:

- The default amplitude (0.8 V, Igor's `G_ACAmp`) exceeds the package's
  0.5 V `limits.bias_max_v`, which is set for 100 mV constant-bias work. The
  runner raises the limit to 1.1x the amplitude with a WARNING before
  building the ramp; it never raises it silently or further than needed.
- If the modulation frequency exceeds sample_rate/10 the runner warns: at
  the Igor defaults (10 kHz at 40 kS/s) the DAC steps the sine with only 4
  samples per period.

## Hardware

- NI DAQ card (analog out: piezo Z + bias; analog in: bias monitor + preamp
  output). Single card is enough; the low-res card is not used.
- STM head with Z piezo, tip, substrate; current preamplifier
  (`cal.preamp_gain_v_per_a`). The preamp bandwidth must comfortably pass
  the modulation frequency or `G` reads low and the phase rotates.
- Optional coarse-approach actuator (NanoPZ).

No hardware is needed with `--simulate`: the simulated card runs the full
pipeline (in simulation the junction usually breaks during the initial
pull, so the lock-in reports the open-junction noise floor, ~1e-14 A).

## Commands

From `python_code_entire_igor/` (use the venv python):

    # simulate, 5 traces
    .venv/Scripts/python.exe experiments/04_ac_hold/run_experiment.py --simulate -n 5 -o data/smoke04.h5

    # real rig
    .venv/Scripts/python.exe experiments/04_ac_hold/run_experiment.py --config rig.json -n 200 -o data/ac_session.h5

    # gentler modulation: 0.3 V at 1 kHz, 5 nm hold
    .venv/Scripts/python.exe experiments/04_ac_hold/run_experiment.py --config rig.json --amp 0.3 --freq-khz 1 --hold-nm 5 -n 200

Flags: `-n/--traces`, `-o/--out`, `--simulate`, `--config PATH`,
`--no-calibrate`, `-v/--verbose`, and the mode overrides `--amp` (V),
`--freq-khz` (kHz), `--hold-nm` (nm at the pull rate). Ctrl-C once finishes
the current trace and stops cleanly; twice exits immediately.

## What is stored

One HDF5 file per session, written by `stmlab.storage.SessionWriter`: the
full `RigConfig` as JSON (including `ac_hold`), and per accepted trace the
raw voltage and current records in volts (the whole trajectory: pulls, caps
and hold), alignment delay, start piezo voltage, bias, sample rate. File
attributes add `segments_json` -- the `{name: [start, stop]}` sample-index
map (`init_pull`, `cap_in`, `ac_hold`, `cap_out`, `final_pull`) valid for
every trace in the file -- and `ac_meta_json` (`amp_v`, `freq_hz`). The
run summary (`run_stats_json`) includes the per-trace lock-in conductances
(`lockin_g0`) and their median. Raw volts only: conductance is derived,
never stored.

## Looking at the data

    import json, numpy as np
    from stmlab import storage
    from stmlab.config import G0_SIEMENS

    with storage.Session("data/ac_session.h5") as s:
        seg = json.loads(s._h5.attrs["segments_json"])
        meta = json.loads(s._h5.attrs["ac_meta_json"])
        a, b = seg["ac_hold"]
        f, amp = meta["freq_hz"], meta["amp_v"]
        for i in range(len(s)):
            _, current_v = s.raw(i)
            fs = float(s.scalar("sample_rate_hz")[i])
            I = s.cfg.cal.volts_to_amps(current_v[a:b])
            t = np.arange(b - a) / fs
            X = np.mean(I * np.sin(2 * np.pi * f * t))
            Y = np.mean(I * np.cos(2 * np.pi * f * t))
            G = 2 * np.hypot(X, Y) / (amp * G0_SIEMENS)
            print(i, G)

Shorter demodulation windows inside the hold give G versus time at the held
junction; the Y channel gives the capacitive background.
