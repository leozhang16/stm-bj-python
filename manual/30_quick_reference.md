# 30. Quick reference

Keep this one open while working.

## Every command

```bash
python run.py list                          # what can I run?

# --- experiments; add --simulate to any of them -------------------------
python run.py 01 -n 1000 --coarse           # constant bias (the reference)
python run.py 02 -n 500 --cycles 5          # push-pull
python run.py 03 -n 200 --max-bias 1.0      # IV sweep
python run.py 04 -n 200 --amp 0.5 --freq-khz 2   # AC hold
python run.py 05 -n 200 --use-vzero         # high-bias hold / zero-field control
python run.py 06 cv --kind highres --plot   # cyclic voltammetry
python run.py 06 gate --mv -200             # set the gate (LEFT ON)
python run.py 06 traces --gate-mv -200 0 200 -n 200
python run.py 07 --sites 20 -n 200          # lateral map
python run.py 08 --max-bias 1.2 --resume    # Igor's bias campaign

# --- diagnostics --------------------------------------------------------
python -m stmlab.main check                 # validate a config, no hardware
python -m stmlab.main dump-config my.json   # edit the defaults
python -m stmlab.main summarise data/x.h5   # where is the gold peak?
python -m stmlab.main bringup 1             # ... through 5
python -m pytest tests/ -q                  # 93 tests
```

`python run.py <NN|name> ...` and
`python experiments/<NN>_<name>/run_experiment.py ...` are always equivalent.

## Every number

### Physics

| | |
|---|---|
| `G0 = 2e²/h` | 7.7480917346e-5 S = 1 / 12,906 Ω |
| 1 G₀ at 100 mV | 7.748 µA → **7.748 V** at ai1 (Rf = 10⁶) |
| input saturates at | **1.23 G₀** — hard contact reads as a *railed channel* |
| tunnelling decay | ~1 decade per ångström |
| gold peak must be at | **0.000 ± 0.05** decades |
| off by ±1.000 decade | 10× preamp gain error |
| off by ±0.301 decade | factor of 2 in bias, or G₀ as e²/h |

### Piezos

| | |
|---|---|
| Z piezo | 62 nm/V, **0–10 V unipolar**, 620 nm total |
| Z: a 5 nm pull | 80.6 mV |
| Z: a 0.5 nm step | 8.06 mV |
| X piezo | 522 nm/V, 0–10 V, **5.22 µm** total |
| X: a 200 nm step | 383 mV |
| coarse interlock | piezo must be **below 0.1 V** for a coarse step |

### Sampling

| | |
|---|---|
| sample rate | 40 kHz requested — **use what the card grants** |
| a 5 nm pull | 250 ms, 10,000 points |
| whole record | 10,800 (400 pre-pad + 10,000 + 400 post-pad) |
| alignment spike | 5 ms, 7.5→2.5 ms before the end of the ramp |
| AI/AO group delay | tens of samples; **measured per trace**, never assumed |

### Biases, and which need the limit raised

`SafetyLimits.bias_max_v` defaults to **0.5 V**.

| Mode | Default bias | Needs override? |
|---|---|---|
| constant bias | 100 mV | no |
| push-pull | 100 mV | no |
| lateral map | 100 mV | no |
| IV sweep | ±1.0 V | **yes** — the experiment raises it and says so |
| AC hold | 0.8 V amplitude | **yes** |
| high-bias hold | 0.8 V | **yes** |
| bias series | up to 1.1 V | **yes** — `--max-bias 1.2`, refuses without |

### Support systems

| | |
|---|---|
| Keithley gain | 10⁶ V/A (`gain_exponent = 6`), GPIB address 22 |
| Keithley series R | 106,130 Ω — **inherited from Igor, measure your own** |
| suppress sweep | −1 to +1 µA, 21 points, endpoints excluded from the fit |
| Vzero sweep | ±5 mV, 10 points, **in contact**, re-measured every 50 traces |
| CV | 1 kHz sampling, 100 mV/s scan, peaks at ∓1.0 V |
| counter electrode | ±5 V, low-res card ao1, entered in **mV** |

## Where to look when something is wrong

| Symptom | Look at |
|---|---|
| gold peak one decade off | preamp gain — `bringup 4`, chapter 20 |
| gold peak 0.301 off | bias, or a G₀ definition — chapter 10 |
| `alignment` rejections | the timing, not the junction — `bringup 2` |
| approach never terminates | engage threshold vs saturation — chapter 10 |
| approach walks in place | `MAINTAIN_EXISTING_VALUE` refused — `bringup 3` |
| "refusing pull: no headroom" | contact made too low in the unipolar range |
| "refusing coarse step" | the fine piezo is extended — this is the interlock working |
| histogram floor rises at one gate | per-gate zero not measured — chapter 15 |
| control steps disagree | the series measured time, not bias — chapter 17 |
| IV curves all mirrored | the sign flag — chapter 12 |

## The trust order

1. **Validated.** The constant-bias path, against Igor's archived data.
2. **Tested end to end on the simulator.** The four ramp modes, both
   campaigns, CV ramp construction, Vzero, the X piezo range logic. 93 tests.
3. **Never met its instrument.** Every `nidaqmx` call in the new modules, the
   Keithley over GPIB, the second card, the electrochemical cell.

Simulate first. Scope second. Tip last.

## The five safety rules, in one place

| Rule | Enforced by |
|---|---|
| piezo commands **clamp**, loudly | `clamp_piezo`, every DC move and waveform |
| bias **refuses**, never clamps | `check_bias`, every waveform |
| no coarse step while the piezo is out | `require_retracted` — **the interlock** |
| no pull without room beneath it | `check_pull_headroom`, every pull |
| approach runaway budget | `check_step_budget`, every coarse step |

Outputs park at 0 V on normal exit, on exception, and on Ctrl-C. On this
unipolar piezo 0 V is fully retracted, so the safe state is also the state a
dead card falls into by itself.

## The one thing still unverified that can damage hardware

Whether **0–10 V** is the limit at `ao0` or at the piezo *after* the driver
box. If the box has gain, the DAQ-side limit is lower than 10 V and the
config as shipped would over-drive the piezo.

Settle that before connecting the piezo. Everything else can be run today.
