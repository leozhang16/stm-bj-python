# 06 — Code walkthrough: approach, pull, trace

**Scope.** The constant-bias break-junction path and the GUI that drives it —
approach, pull, get traces. Twenty-seven files, 7,751 lines, 445 classes and
functions, every one of them listed below.

Deliberately **not** covered: `stmlab/ramps.py` (push-pull, IV, AC-hold,
high-bias-hold trajectories), `stmlab/echem.py`, `stmlab/xpiezo.py` and
`stmgui/panels/echem_panel.py`. Those are separate experiments. They still
appear at the edges — their config dataclasses live in `config.py` and
therefore travel in every data file — and where that happens it is flagged.

**Status: pass 1.** Every function is listed with its signature, line number,
one-line purpose and Igor origin. The narrative depth — the *why*, the failure
modes, the worked arithmetic — is present for the load-bearing functions and
marked `PASS 2` where it is still to come. Fill those in as you read, on the
days the reading plan in Part 11 suggests.

---

## Part 0 — How to read this

### 0.1 The one true sentence

Everything below is a consequence of this:

> The DAQ card is exposed as a single verb, `play(waveform) -> record`, where
> `waveform` is a `(2, N)` array of volts you want on the outputs and `record`
> is a `(2, N)` array of volts that appeared on the inputs. Python never times
> anything. It computes an array, hands it to the card, and waits.

Row 0 of `waveform` is the **piezo command** (ao0), row 1 is the **junction
bias** (ao1). Row 0 of `record` is the **junction voltage** (ai0), row 1 is the
**preamp output** (ai1). Those four indices are `ChannelMap.ROW_PIEZO`,
`ROW_BIAS`, `ROW_VOLTAGE`, `ROW_CURRENT` and they are `ClassVar`s so they never
leak into a data file.

A 0.5 nm approach step is a `play` of 1,000 identical samples. A 5 nm pull is a
`play` of 10,800 samples that happens to descend. The difference between them
is arithmetic, not control flow. Loop overhead, Python's garbage collector, a
slow disk — all of it lands *between* plays, never inside one, so it cannot
distort a trace.

### 0.2 The five layers

```
  stmgui/           Tk panels, one worker thread, an event queue
     |
  experiments/  run.py  stmlab/main.py        orchestration, CLI
     |
  stmlab/trace.py  approach.py  calibrate.py  physics: ramps, contact, constants
     |
  stmlab/instrument.py (Rig)                  the funnel; tracks the piezo
     |
  stmlab/daq.py   sim.py                      the card, or a stand-in
```

Plus three that sit beside the stack rather than in it: `config.py` (numbers),
`safety.py` (refusals), `analysis.py` + `storage.py` (volts → physics → file).

The rule that makes the safety story work: **nothing above `instrument.py` may
touch the card.** `Rig.play` is the only path, and it updates the tracked piezo
voltage from the waveform it just sent. One stray `task.write()` elsewhere and
the coarse-step interlock becomes confidently wrong.

### 0.3 Notation in the tables

Each module gets a table of every definition in it. Columns are the source line
number, the signature exactly as written (indented for methods), a one-line
summary taken from the docstring, and the Igor procedure it replaces where the
docstring names one. Line numbers are extracted from the source by AST, not
typed by hand, so they are correct as of this build and will drift if you edit
the code — regenerate with `outputs/assemble.py` rather than patching by hand.

Markers used in the prose:

- **`READ CLOSELY`** — you cannot debug this rig without understanding this one.
- **`GOTCHA`** — confirmed defect or surprising behaviour, verified against source.
- **`PASS 2`** — depth still to be written.

### 0.4 The numbers, once

Memorise these six and most of the code explains itself.

| Quantity | Value | Where |
|---|---|---|
| Conductance quantum G₀ | 7.7480917346e-5 S | `config.py:35` (Igor `K_G0`) |
| Piezo | 0–10 V **unipolar**, 62 nm/V → 620 nm full range | `SafetyLimits`, `Calibration` |
| Bias | 100 mV, hard refusal above 500 mV | `RampConfig.bias_v`, `SafetyLimits.bias_max_v` |
| Sample rate | 40 kHz | `RampConfig.sample_rate_hz` |
| One pull | 5 nm at 20 nm/s = 10,000 samples = 0.25 s | `RampConfig.n_pull_samples` |
| Preamp | Rf = 1e6 V/A, railed above 9.5 V | `Calibration`, `SafetyLimits` |

And the arithmetic that falls out of them, which you should be able to redo on
paper at the rig:

> At Rf = 1e6 V/A and 100 mV bias, **1 G₀ reads 7.748 V at the ADC.** That is
> inside the ±10 V input range but *above* the 9.5 V saturation limit. So the
> metallic-contact region of every trace reads **railed**, not large.

That single fact explains why `Rig.probe()` returns a `railed` boolean
alongside the conductance, why `in_contact()` ORs the two, why Igor's
`G_ConductanceThreshold = 5` had to become `engage_g0 = 0.5` here, and why
`config.validate()` spends thirty lines on it.

---

## Part 1 — The numbers and the refusals

### 1.1 `stmlab/config.py` — thirteen dataclasses and one gatekeeper

{{SIZE:stmlab/config.py}}

Nothing in this file *does* anything, and it is still the file to read first.
Every other module's behaviour is a consequence of a number declared here, and
the whole `RigConfig` is serialised to JSON into the attributes of every HDF5
file you will ever write — so this is simultaneously the rig's constants, your
data's provenance, and the reason a file written today can be re-analysed with
a corrected gain in a year.

The split into dataclasses is by **lifetime**, not by topic:

| Class | Changes when | Re-measured |
|---|---|---|
| `ChannelMap` | the rig is rewired or a card moves slot | never |
| `SafetyLimits` | the hardware changes | never |
| `RampConfig` | you tune the experiment | per experiment |
| `Calibration` | the preamp warms up, the gain is reprogrammed | **every session** |

`ActuatorConfig` describes the coarse approach. The remaining seven —
`PushPullConfig`, `IVConfig`, `ACHoldConfig`, `HBHoldConfig`, `VzeroConfig`,
`KeithleyConfig`, `EChemConfig`, `XPiezoConfig` — belong to experiments outside
this walkthrough. They are still constructed on every `RigConfig` so that they
travel in every data file, which is why you will see `iv`, `echem` and `xpiezo`
blocks in the `config_json` attribute of a plain constant-bias run. Ignore
them; do not delete them.

**`READ CLOSELY` — `validate(cfg)`, line 511.** The only place in the codebase
where the *relationships* between numbers are checked, and the only safety
mechanism that runs before any hardware is touched. It returns a list of
warnings and raises `ConfigError` on anything fatal. Called from
`main.run()`, from `main check`, and from the GUI's Start Writing.

The checks worth knowing by name, because you will trip them:

- **The range check** (L523). Computes `g0_to_volts(1.0, bias_v)` and compares
  it to the AI range, then to the preamp saturation limit. This is where the
  7.748 V arithmetic from §0.4 lives. Above `ai_range_v` it is fatal; above
  `preamp_saturation_v` it is a warning that says, correctly, that this is
  usually fine because the science is below 1 G₀.
- **The engage-threshold check** (L539). Asks whether contact can ever be
  detected by the conductance threshold rather than only by saturation. Igor's
  defaults would have failed this: an engage threshold above the saturation
  point makes the approach run the piezo to its ceiling and give up with no
  indication why.
- **The gain-coupling warning** (L609). `keithley.gain_exponent` programs the
  amplifier; `cal.preamp_gain_v_per_a` is what every conductance divides by.
  Nothing else connects them. A mismatch moves the entire histogram by a whole
  number of decades and the warning prints the decade count.
- **The unipolar geometry checks** (L576–605). A descending ramp needs room
  beneath the contact point; `piezo_headroom_v` reserves it.
- **The two "you have not calibrated" warnings** (L660, L666). `current_zero_v == 0`
  means the preamp zero was not measured this session.

**`READ CLOSELY` — `Calibration`'s four converters**, lines 275–291. These are
the only arithmetic in the file and they are used everywhere downstream:
`volts_to_amps` (subtracts the zero, divides by Rf), `volts_to_g0`,
`g0_to_volts` (the inverse, used by the validator), and the
`nm_to_piezo_volts` / `piezo_volts_to_nm` pair. Note `piezo_nm_per_volt = 62`
is **end-to-end at the DAQ output** — it already includes the piezo driver
box's gain, which is why `hv_amp_gain` exists but is never multiplied by
anything.

**`GOTCHA` — `from_dict` silently drops unknown keys** (L466), logging a
warning through `_log_unknown`. That is deliberate and correct: a file written
by an older version must still open. But it means a typo in a hand-edited JSON
config is a log line, not an error.

**`PASS 2` will add:** a worked example of changing `bias_v` and tracing every
downstream number it moves; the full list of Igor `G_*` globals with their
Python homes; what happens to `validate` if you switch to a 1e7 V/A gain.

{{TABLE:stmlab/config.py}}

### 1.2 `stmlab/safety.py` — five hazards, in order of cost

{{SIZE:stmlab/safety.py}}

The module docstring ranks the hazards, and the ranking is the design: a coarse
step while the piezo is extended costs the tip and often the sample; an AO
channel left non-zero when the process dies costs sustained extension; driving
the piezo out of range costs depoled ceramic; approach runaway costs the tip;
the wrong device costs the preamp.

`safety.py` imports only `config`. If it ever needs `daq` or `instrument`, a
check has drifted into the wrong layer.

**`READ CLOSELY` — the clamp/refuse asymmetry.** `clamp_piezo` (L42) forces the
value into range, logs a warning, and carries on. `check_bias` (L57) raises
`SafetyViolation`. The docstrings explain why, and the reasoning is worth
adopting as a habit: a ramp that overshoots by a millivolt should be truncated
rather than aborted mid-pull, but there is no case where you meant to apply
more bias than the limit and would be happy with silently less — quietly
reducing it produces data *labelled* with a bias that was never applied.

`check_pull_headroom` (L72) refuses a third way: before hardware is touched at
all. It exists because the piezo is unipolar, so a pull that starts too low
clips, and a clipped trace is silently short — indistinguishable from a
junction that broke early, which is the worst kind of artefact.

**`READ CLOSELY` — `require_retracted`, line 96.** The single most important
function in the package. It refuses a coarse move unless the fine piezo is at
or below `coarse_step_max_piezo_v` (0.1 V = 6.2 nm of residual extension).

It has no position sensor. `piezo_v` is the **last commanded value**, tracked
by `Rig`. This is a bookkeeping interlock, which means *every piezo write must
go through the tracker or this guard is lying to you.* That is the real
argument for keeping `daq.py` thin and forcing all motion through
`instrument.py` — not elegance, but the fact that this function depends on it.

The three independent defences against a stuck extension, in order of when they
fire: every ramp ends at a safe value; `SafeSession.__exit__` and `Rig.close`
park the outputs; and the card's own `ao_idle_output_behavior`, which is the
only one that survives a SIGKILL or a power cut.

**`GOTCHA` — `park_all_outputs` (L163) wraps its whole body in
`contextlib.suppress(Exception)`** and then logs `"outputs parked at 0 V"`
unconditionally. If the task creation fails, the log line still appears. It
creates its own short-lived tasks rather than reusing the session's, which is
correct — it needs to work when the main tasks are broken — but do not read
that log line as proof.

**`PASS 2` will add:** the exact sequence of `SafeSession` vs `Rig` teardown
when an exception propagates out of `trace_loop`; what `verify_devices` reports
when NI MAX has renamed `Dev1`.

{{TABLE:stmlab/safety.py}}

---

## Part 2 — The card, and the rig that owns it

### 2.1 `stmlab/daq.py` — the entire NI driver surface

{{SIZE:stmlab/daq.py}}

Two DAQmx tasks, one AO and one AI, opened once and kept open. `nidaqmx` is
imported *inside* `open()`, not at module scope, so every other module in the
package imports cleanly on your Mac.

**`READ CLOSELY` — `open()`, line 63.** Four things happen here that you cannot
change without consequences elsewhere:

1. The ao0 channel's range comes from `SafetyLimits`, not from `ChannelMap`, so
   the range the card enforces and the limit the software enforces can never
   disagree. ao1's range comes from `channels.bias_ao_range_v` (±2.5 V, Igor's
   `G_HighResOutputRange`).
2. `ai0` is added **before** `ai1`. That ordering is what makes
   `ROW_VOLTAGE = 0` and `ROW_CURRENT = 1` true. Swap the two lines and every
   trace in the package silently transposes.
3. AO idle behaviour is set to `MAINTAIN_EXISTING_VALUE`, deliberately not
   `ZERO_VOLTS`, so the piezo holds position in the gap between plays. Bring-up
   step 3 exists solely to prove the card actually honoured this.
4. The AI task is hardware-triggered off `/Dev1/ao/StartTrigger` — derived from
   `ChannelMap.ao_start_trigger`, never hardcoded.

**`READ CLOSELY` — `configure(n)`, line 126.** Called at the top of every
`play`. It early-returns if the requested length is unchanged (L134), which is
why an approach loop of a thousand identical 1,000-sample plays reconfigures
the tasks exactly once. It then sets finite timing at the requested rate, wires
the digital start trigger, and tries to make the AI task **retriggerable**
(L167) — falling back gracefully if the card refuses. When retriggerable works,
AI is armed once at L187 and never re-settles; when it does not, AI is re-armed
inside every `play`, and the input filter settles at the start of every record.

The granted sample rate is read back from the driver (L179) but **latched only
the first time**. On a delta-sigma card the granted rate is not always the
requested one, and every time axis in the package uses the granted value.

**`READ CLOSELY` — `play(waveform)`, line 193.** The whole acquisition model in
thirty lines: validate the shape is `(2, n)` → `configure(n)` → stop AO if
running → `write(auto_start=False)` → re-arm AI if not retriggerable → **start
AO, which fires the trigger** → `wait_until_done` → `read(n)`. AO is
deliberately left running when it returns, so the outputs hold their final
value. `timeout_s = 10.0` bounds it; a 5 nm pull takes 0.25 s.

**`GOTCHA` — `DaqError` (L44) is defined and never raised.** Dead code. Driver
failures surface as `nidaqmx.DaqError`, a different class.

**`GOTCHA` — `close()` (L103) wraps every call in a bare `except: pass`.** A
task that fails to close does so silently. On the rig this shows up as "device
reserved" on the next run.

**`PASS 2` will add:** what the 4461's decimation filter actually does to the
first 400 samples, measured; the exact DAQmx error you get when two processes
both hold `Dev1`.

{{TABLE:stmlab/daq.py}}

### 2.2 `stmlab/sim.py` — the stand-in you will live inside for two weeks

{{SIZE:stmlab/sim.py}}

`SimulatedDaqSession` has the same one verb. It returns a plausible `(2, n)`
record, tracks a virtual tip position and surface, and generates conductance
that produces a recognisable gold histogram. You will run the whole GUI against
it on your Mac and on the lab PC before the piezo is ever connected.

**Calibrate your trust in it now**, because this matters more than any single
function. What it models honestly:

- a 1 G₀ single-atom plateau at `1.0 ± 0.04`;
- a metallic region rising as `1 + 4.0·(penetration − 0.12)`;
- an exponential tunnelling tail, `10^(−10 · stretch_nm)` — one decade per
  ångström, which is the right order;
- a molecular plateau at `10^(−3.5 ± 0.25)`, rolled once per break with
  probability 0.45;
- a fixed AI/AO group delay of 37 samples, so the alignment-spike machinery is
  genuinely exercised;
- tip degradation: quality decays 0.01 per pull beyond 3 nm to a 0.15 floor,
  and a >20 nm excursion (i.e. `smash`) resets it and jogs the surface.

What it does **not** model, all of which you will meet for the first time on
real hardware:

- **no decimation settling transient**, so `pre_pad_samples = 400` is never
  stressed and you cannot tell from the simulator whether 400 is enough;
- **no piezo hysteresis, creep or nonlinearity** — displacement is exactly
  linear in commanded volts;
- **no drift, no 1/f, no mains pickup.** Noise is stationary, white, and
  independent of the signal, at 1.87 µV rms;
- **current is strictly ohmic**, so every IV sweep is a perfectly straight line;
- **no preamp rail at 9.5 V**, no amplifier bandwidth or slew limit, no series
  resistance, no capacitive displacement current;
- no stochastic breaking, no jump-to-contact;
- **no DAQmx error surface at all** — nothing ever raises.

**`GOTCHA` — `configure()` (L69) is a no-op.** So neither the AI re-arm path
nor the retriggerable-fallback path in `daq.py` is ever exercised by any test
or any simulated run. Those two branches will execute for the first time on the
rig PC.

**`GOTCHA` — `play()` sets the tip position from the *undelayed* last sample**
(L106) while prepending `_tail` to model the group delay. Harmless for the
position tracker, but it means the simulator's position and its returned record
disagree by 37 samples in a way the real card would not.

**`PASS 2` will add:** a side-by-side of a simulated trace and an Igor `.ibw`
trace at the same axes — the comparison that has never been done.

{{TABLE:stmlab/sim.py}}

### 2.3 `stmlab/instrument.py` — `Rig`, the funnel

{{SIZE:stmlab/instrument.py}}

`Rig` holds exactly two things that must live and die together: the open DAQmx
tasks, and `_piezo_v`, the last commanded piezo voltage. The second is
load-bearing — `safety.require_retracted` has no sensor and trusts it.

**`READ CLOSELY` — `play()`, line 104.** Clamps the piezo row into range
(loudly), calls the session, then updates `_piezo_v` from
`waveform[ROW_PIEZO, -1]` and `_bias_v` from the final bias sample with the
sign convention undone. Updating the tracker *from the waveform actually sent*
rather than from what the caller intended is the whole trick: it cannot fall
out of step.

Everything else in the class is a shape built on top of `play`:

- `hold(piezo_v, bias_v, n_samples)` (L130) — Igor's `WriteToHighRes` plus the
  read that always followed it. Checks bias, clamps piezo, builds a constant
  `(2, n)` array, plays it, returns the record. **Every DC move in the package
  is a `hold`.**
- `piezo_goto` / `piezo_step_nm` / `set_bias` — one-liners over `hold`.
- `conductance_of(record)` (L189) averages only the **tail** of the record —
  `settle_discard = 800` of 1,000 samples are thrown away, because the leading
  samples are still settling in both the amplifier and the card's filter.
  Returns `inf` if the junction voltage is below 1 nV.
- `is_saturated(record)` (L211) — railed over a **majority** of the same tail
  window. One railed sample is a transient; half of them is contact.
- `probe()` (L172) returns `(g0, railed)`; `in_contact()` (L185) ORs `railed`
  with `g0 > engage_g0`. See §0.4 for why the `railed` half is not optional.
- `read_current_ua` (L203) — the coarse approach's only measurement.

**`READ CLOSELY` — `coarse_step(closer)`, line 229.** Calls
`require_retracted`, then `check_step_budget`, then steps. Nothing else in the
package is allowed to touch the actuator, and this is why.

**`GOTCHA` — `open()` builds the actuator with no simulator reference**
(L50–52): `make_actuator(self.cfg)` takes only the config, so a
`SimulatedActuator` is constructed with `sim = None` and its steps move
nothing. Consequence: **a simulated `coarse_approach` never converges** — the
surface never comes closer, current never appears, and the loop runs to the
2,000-step budget and raises. If you want to exercise the coarse approach
against the simulator, construct the `Rig` with an explicit `actuator=`.

**`GOTCHA` — `close()` calls `withdraw()` first** (L65), which itself calls
`hold()`, which calls `play()`. If the card is already in a bad state this
logs an exception and continues to parking, which is the right order — but it
means `close()` can take a further `timeout_s` to return.

**`PASS 2` will add:** a trace through `_piezo_v` over one full `engage()`,
step by step, with the interlock value at each point.

{{TABLE:stmlab/instrument.py}}

### 2.4 `stmlab/actuator.py` — the coarse approach hardware

{{SIZE:stmlab/actuator.py}}

Three implementations behind one `step(closer: bool)` interface: `NullActuator`
(approach by hand), `SimulatedActuator` (moves `sim.surface_nm` by 8 nm per
step), and `NanoPZActuator` (Newport NanoPZ over serial, 19200-8-N-1). The
protocol is five commands: `0MO` motor on, `0MF` off, `0PR<n>` relative move,
`0ST` stop, `0TP?` position, `0TS?` status.

**Sign convention: negative is closer** (L163), from Igor's
`StepActuatorCloser` in `NanoPZ_Actuator_Functions_STM.ipf:22`. Get this
backwards and the coarse approach drives the tip into the sample at 8 nm a
step.

**`GOTCHA` — `make_actuator` tests `kind` before it tests `simulate`.** The
branch `if kind == "nanopz": return NanoPZActuator(cfg)` is evaluated first, so
a config with `simulate = True` *and* `kind = "nanopz"` **opens the real serial
port and energises the motor** while you believe you are simulating.
`NanoPZActuator.__init__` ends by calling `motor_on()` (L127). Before any
simulated run on the lab PC, check `cfg.actuator.kind`, not just
`cfg.simulate`.

**`GOTCHA` — the default port is still `"COM1"`** (`config.py:312`). A USB
NanoPZ is normally COM3 or higher. Bring-up step 5 lists the ports for you.

**`PASS 2` will add:** what `0TS?` returns in each fault state; whether this
controller retraces its step count (bring-up step 5 checks, and warns if not —
a slip-stick drive normally does not).

{{TABLE:stmlab/actuator.py}}

---

## Part 3 — Getting into contact

### 3.1 `stmlab/approach.py` — the state machine before every trace

{{SIZE:stmlab/approach.py}}

**`READ CLOSELY` — `engage(rig)`, line 71.** Igor's `HighResMakeContact`
(`Functions_STMBJ.ipf:1239`). Two halves, and **the order matters**:

```
if rig.in_contact():      separate(rig)     # break any existing contact FIRST
close_in(rig)                               # then close in slowly
if not _headroom_ok(...): raise ApproachError
```

Skipping the first half and approaching from an already-shorted junction is how
you weld the tip to the sample. This function runs before *every* trace, so it
executes tens of thousands of times in a night.

- `separate(rig)` (L35) retracts in 5 nm steps until `not railed and g0 <
  break_g0` (5e-4 G₀). It raises if it reaches the piezo floor still closed —
  meaning the coarse actuator has to back off. Note the asymmetric bound check
  at L44: only the bound being travelled *toward* can block.
- `close_in(rig)` (L55) steps in 0.5 nm at a time until `rig.in_contact()`,
  raising at the ceiling.
- The headroom check at the end is the interesting one. `engage` **refuses to
  report success from a position with no room left for the pull.** On a
  unipolar piezo, contact made low in the range cannot be pulled from, and
  finding that out here rather than mid-ramp keeps the failure legible. Igor
  returned −2 and −3 for the two range failures and terminated the run.

`smash(rig)` (L102) is Igor's `SmashFun`: drive in 30 nm, pull back 40 nm.
Deliberately blunt — reshaping the apex against the substrate is how a tip that
has stopped producing clean traces is recovered without breaking vacuum.
`trace_loop` calls it every `smash_every = 50` attempts.

**`READ CLOSELY` — `recover_headroom(rig, max_backoff=5)`, line 167.** The
routine to call in an unattended overnight loop, and **not** what
`trace_loop` currently calls. Drift pushes the contact point down the piezo
range over hours; without this the run dies with "no headroom" at 3 a.m. It
retries `engage`, backing the coarse actuator off one step each time.

`coarse_approach(rig, stop_flag)` (L120) steps the coarse actuator in until
`abs(current_ua) >= stop_current_ua` (0.1 µA, Igor
`Functions_STMBJ.ipf:1780`). It calls `require_retracted` once at the start
*and* relies on `Rig.coarse_step` enforcing it on **every** step — belt and
braces, because the loop never moves the piezo and a bug that did would
otherwise go unnoticed.

**`PASS 2` will add:** measured step counts for a real approach; what a
`separate` loop looks like on a tip that has picked up contamination.

{{TABLE:stmlab/approach.py}}

### 3.2 `stmlab/calibrate.py` — the three measured constants

{{SIZE:stmlab/calibrate.py}}

**`READ CLOSELY` — `session_calibration(rig)`, line 139.** What Start Writing
runs. Order: `measure_zero` → `measure_group_delay` (wrapped in a bare
`except Exception`, so a failure here is a warning not a stop) → record
`granted_sample_rate_hz`. **The tip must be out of contact when this runs.**

- `measure_zero` (L28) sets the bias to zero, plays 20,000 samples, discards
  the first quarter, and averages. Restores the bias in a `finally`. The result
  is hundreds of microvolts and drifts with temperature, which is why it is a
  per-session measurement rather than a constant.
- `measure_group_delay` (L57) writes an inverted 250-sample block into a
  2,000-sample record, finds the edge, and returns `(mean, sd)` over 20
  repeats, warning if the scatter exceeds one sample. Bring-up step 2 runs it
  with 25 repeats and treats `sd >= 1.0` as a hard FAIL, because scatter above
  a sample means AI is not really triggered off `ao/StartTrigger`.

**`GOTCHA` — two bugs in `measure_zero`.** At L52 the noise figure is computed
via `volts_to_amps(noise)`, which subtracts `current_zero_v` from a *noise*
value — the number it logs is wrong by the zero offset. And if `rig.hold`
raises, `record` is never bound, so the `finally` path produces a `NameError`
that masks the real exception.

**`GOTCHA` — `measure_gain_offset` (L105) cannot run.** It sweeps 17 points
from −2 V to +2 V, but `limits.bias_max_v` is 0.5, so `check_bias` raises
`SafetyViolation` on the first point. It also double-applies
`bias_output_sign` at L119, and the 4461 defaults to AC coupling on AI, which
would null a DC sweep anyway. It is dead code; `cal.ai_gain_error` and
`ai_offset_v` are consequently never measured — and, separately, **never
applied anywhere in the package** either. Treat them as documentation.

**`PASS 2` will add:** the temperature-vs-zero curve for this preamp; whether
the group delay is stable across sample rates.

{{TABLE:stmlab/calibrate.py}}

---

## Part 4 — One pull: `stmlab/trace.py`

{{SIZE:stmlab/trace.py}}

This is the spine. If you read one file properly, read this one.

Traces carry **raw volts, never conductance.** The conversion depends on three
measured constants that can be revised — a mis-measured preamp gain, a zero
taken before the amplifier warmed up — and baking them into stored data turns a
calibration error into a lost dataset instead of a re-analysis.

### 4.1 `build_ramp` — the array

`build_ramp(cfg, start_piezo_v, sample_rate_hz=None, bias_offset_v=0.0)`,
line 77. Igor's `CreateInputs`, constant-bias branch
(`Functions_STMBJ.ipf:1601`). Only that branch is implemented here; Igor's
push-pull, IV, AC-hold and high-bias-hold trajectories are `ramps.py` and out
of scope.

```
[ pre_pad 400 ][ ---------- pull 10,000 ---------- ][ post_pad 400 ]
   hold DC        descending ramp, spike near end      hold final
```

Read it in this order:

1. **Refuse first** (L99–100): `check_bias`, then `check_pull_headroom`. No
   array is built if the geometry is wrong.
2. **Volts per sample** (L104): `dv = pull_rate_nm_per_s / piezo_nm_per_volt /
   fs`. Igor called this `DeltaEx` (`Functions_STMBJ.ipf:1458`). At the
   defaults: 20 / 62 / 40000 = 8.065 µV per sample, and 10,000 samples of it
   is 80.6 mV = 5 nm. The ramp is a plain `np.arange` subtraction.
3. **The baseline bias** (L112): `bias_output_sign * (bias_v + bias_offset_v)`.
   `bias_offset_v` is the Vzero correction — Igor wrote `-(TipBias+Vzero)/1000`
   when the Voltage_Offset panel was active (`:1609-1614`) but kept the spike
   at `+TipBias/1000` (`:1631`), so **the offset is added to the baseline
   only**. The code reproduces that asymmetry exactly.
4. **The alignment spike** (L115–122): `analysis.spike_indices` gives
   `(front, back)`; the spike is written into `[front+1, back-1]` inclusive, at
   `-bias_output_sign * bias_v` — i.e. the opposite polarity to the baseline.
   If it does not fit, a warning and the trace will fall back to the configured
   group delay.
5. **The pads** (L124–127) and the concatenation (L129).
6. **The clamp** (L134–137) is a backstop, not the plan — `check_pull_headroom`
   should already have made it impossible to fire. If you see that warning,
   something upstream is wrong.

The returned `Ramp` carries `spike_front = pre_pad_samples + front`, which is
the index of the spike's rising edge **in the written waveform**. The
fractional edge sits at `spike_front + 0.5`. That half-sample matters in
`_measure_delay`.

### 4.2 Why the spike exists

The card's AI and AO do not start at the same instant. There is a fixed group
delay — about 37 samples in the simulator, whatever the 4461 actually does on
your rig — between commanding a piezo voltage and seeing the consequence. If
you cut the trace at the nominal index you misalign displacement and current by
that much, and a systematic misalignment shifts every feature in the histogram.

So every ramp carries a marker: a short bias pulse of known polarity, 7.5 ms to
2.5 ms before the end. It is written on ao1 and read back on ai0.
`find_alignment_edge` locates its rising edge to sub-sample precision, and the
difference between where it was written and where it was read **is the delay,
measured on that trace, not assumed.**

This is the single most elegant thing in the translation and it is worth
understanding before you touch hardware, because bring-up step 2 exists to
prove the mechanism works with a single BNC cable and nothing else connected.

### 4.3 `capture` — the one path every experiment shares

`capture(rig, ramp, index=0, bias_v=None)`, line 166. Sets state to `PULLING`,
plays the waveform, measures the delay, cuts `[pre_pad + delay : + n_pull]` out
of the record, and returns a `TraceRecord` — or `None`.

It returns `None` in two cases, both of which mean *discard this trace*: the
alignment spike could not be located and there is no fallback group delay, or
the cut would run past the end of the record (fix by increasing
`post_pad_samples`).

`single_trace` (L151) is the thin wrapper that builds a constant-bias ramp and
calls `capture`. The reason `capture` is separate is that push-pull, IV, AC and
high-bias experiments all reuse it unchanged — the spike recovery and the
plausibility cut are identical for every trajectory. For those, note that
`TraceRecord.displacement_nm` does **not** apply, because it assumes a constant
pull rate.

**`READ CLOSELY` — `_measure_delay`, line 206.** Searches from
`spike_front − 0.05·fs` (2,000 samples early at 40 kHz), computes
`delay = round(edge − (spike_front + 0.5))`, then applies a **plausibility
window**: `−0.02·fs ≤ delay ≤ 0.05·fs`, i.e. −800 to +2,000 samples. A delay
outside that means the search locked onto something else — a noise crossing, or
a junction so noisy the bias readback changes sign — and the trace is dropped
rather than shifted by a thousand samples. If no edge is found at all it falls
back to `cal.group_delay_samples` when that is set, and otherwise discards.

### 4.4 `TraceRecord` — what one pull is

Line 47. Nine fields: `index`, `voltage_v`, `current_v`, `delay_samples`,
`start_piezo_v`, `bias_v`, `sample_rate_hz`, `timestamp`, `attempt`. Two
methods, both of which take the config because the record itself is raw:
`conductance_g0(cfg, use_measured_voltage=True)` — note the default uses the
**measured** per-sample junction voltage from ai0, not the commanded scalar
bias — and `displacement_nm(cfg)`, which is computed from the commanded ramp,
not measured.

### 4.5 `trace_loop` — many pulls

`trace_loop(rig, n=None, on_trace=None, stop_flag=None, require_engaged=False)`,
line 236. Igor's `MeasureBreakJunctions` (`Functions_STMBJ.ipf:1664`). The
overnight loop:

```
while accepted < target and attempts < max_attempts:
    stop_flag?  ->  break
    attempts += 1
    every 50th attempt:  approach.smash(rig)
    approach.engage(rig)         # not ENGAGED -> continue
    trace = single_trace(rig)    # None -> count 'alignment', continue
    verdict = analysis.select_trace(...)
    not accepted -> count the reason, continue
    accepted += 1;  on_trace(accepted-1, trace, verdict)
```

Returns `{"accepted", "attempts", "acceptance_rate", "rejections"}`. The
rejection keys are derived from the verdict text by
`reason.split(":")[0].split("(")[0].strip()`, so they are the human-readable
reason with the numbers stripped off.

`on_trace` and `stop_flag` exist so the same loop is callable from a script, a
test, or a GUI worker thread with no modification. `stop_flag` is anything with
`is_set()`; Igor polled the Alt key for this (`:1697`).

**`GOTCHA` — `SafetyViolation` re-raises, everything else is swallowed.**
L272–275: a safety refusal kills the run, any other exception is logged with a
traceback and the loop continues to the next attempt. That is the right policy,
but it means a systematic fault — a disconnected preamp, say — presents as a
run that simply never accepts anything, with the real error only in the log.

**`GOTCHA` — the stop flag is checked only between attempts.** A pull in
progress always runs to completion. `capture` never sees the flag. At 0.25 s
per pull this is a quarter-second latency, which is fine — but it means Stop is
not an emergency stop.

**`PASS 2` will add:** a realistic rejection-reason breakdown from a good night
and a bad night; the acceptance rate to expect for gold at these settings.

{{TABLE:stmlab/trace.py}}

---

## Part 5 — Volts to physics: `stmlab/analysis.py`

{{SIZE:stmlab/analysis.py}}

Pure functions, no hardware, no state. Everything here can be unit-tested on
your laptop, and everything here can be re-run on archived raw volts with a
corrected calibration.

### 5.1 The conversion

`to_conductance(current_v, cal, bias_v=None, voltage_v=None)`, line 66. Three
constants decide where your histogram lands, and they fail in three different
ways:

| Constant | How it enters | What an error does |
|---|---|---|
| `cal.current_zero_v` | additive, subtracted first | **500 µV error ≈ 6.5e-5 G₀** — about 13% of `break_g0`. Corrupts the tunnelling tail; leaves the 1 G₀ peak untouched. |
| `cal.preamp_gain_v_per_a` | multiplicative | A 10× error moves the whole histogram **exactly 1.000 decade**. |
| the denominator | `bias_v` scalar, or `voltage_input_sign · voltage_v` per sample | Wrong sign → negative conductance → nothing survives `select_trace`. |

That table is the debugging tool for "the gold peak is in the wrong place". A
peak displaced by a clean decade is a gain error. A peak in the right place
with a corrupted tail is a zero error.

`displacement_nm` (L96) is computed from the **commanded** ramp — pull rate,
sample count, granted rate — never measured. There is no piezo position sensor
on this rig.

`average_deviation` (L31) is Igor's `V_adev`, mean absolute deviation, roughly
0.8× the standard deviation for Gaussian noise. `boxcar` (L44) is edge-padded,
matching Igor's `Smooth/B`. Both exist so that Python numbers are comparable to
Igor numbers rather than merely correct.

### 5.2 The spike, found

`spike_indices(ramp_cfg, fs)`, line 157. `front = n − round(7.5 ms · fs) − 1`,
`back = n − round(2.5 ms · fs) + 1`. At the defaults (n = 10,000, fs = 40 kHz)
that is a spike occupying **[9700, 9900]** in the pull — 200 samples, 5 ms,
right before the end where the junction has already broken and the bias pulse
disturbs nothing.

`find_alignment_edge` (L115) locates the rising edge in the readback.

### 5.3 `select_trace` — the most important thing in this file

`select_trace(conductance_g0, ramp_cfg, require_engaged=False)`, line 186.
Igor's `TestTrace` (`Functions_STMBJ.ipf:1180`). Returns a `Selection`
dataclass: `accepted`, `reason`, and the start/end conductances.

**`GOTCHA` — the early accept.** When `abs(start_mean) <= engage_g0` **and**
`require_engaged` is False — which is the default, and what `trace_loop` and
the GUI both pass — the function returns

```
Selection(True, "accepted (engage check disabled, as in Igor)", ...)
```

**skipping the noise test and the plateau-count test entirely.** This is
faithful to Igor, whose equivalent `else` branch is commented out at
`:1212-1215`. But it means that in the default configuration a trace whose
start is below the engage threshold is accepted *unconditionally*, and the
quality filters you might assume are running are not.

This is the single biggest behavioural surprise in the codebase. Before you
interpret any acceptance rate, decide deliberately whether you want
`require_engaged=True`. `main.run()` and the GUI both expose it.

### 5.4 The histogram

`log_histogram(traces, ...)`, line 265. Igor's `LogHistFromBlocks`
(`Functions_STMBJ.ipf:785`), with one deliberate divergence: the edges are
`np.linspace(-8.0, 2.0, 1001)`, giving **1000 bins of exactly 0.01 decade**,
where Igor used 10/999 and got bins of 0.01001. Bin edges that are round
numbers make peak positions comparable between sessions.

The pipeline, in order: keep the lowest `keep_fraction = 0.95` of each trace →
`boxcar(width=11)` → estimate a floor from the 0.95–0.96 slice of the truncated
array → skip anything below `zero_cutoff` → accumulate → subtract the floor →
divide by the number of **surviving** traces. That last point matters: counts
are per-trace-normalised by `n_used`, not by `len(traces)`.

`peak_position` (L335) masks to `window = 0.5` decades, takes the argmax, then
refines with a counts-weighted centroid over `refine = 0.15` decades (about 31
bins). `main.py:87` flags a peak more than 0.05 decade from 0.

**`PASS 2` will add:** the same histogram computed from an Igor `.ibw` block
and from a Python `.h5` session, overlaid. This is the validation that has
never been performed and it is a week-2, no-hardware task.

{{TABLE:stmlab/analysis.py}}

---

## Part 6 — The file: `stmlab/storage.py`

{{SIZE:stmlab/storage.py}}

### 6.1 Layout

One HDF5 file per session, **no subgroups**, `FORMAT_VERSION = 1` (L32).

| Dataset | Shape | Type |
|---|---|---|
| `voltage_v`, `current_v` | (n_traces, n_samples) | float64, gzip, chunks (32, n_samples) |
| `delay_samples` | (n_traces,) | int32 |
| `start_piezo_v`, `bias_v`, `sample_rate_hz`, `timestamp`, `start_conductance_g0`, `end_conductance_g0` | (n_traces,) | float64 |
| `attempt` | (n_traces,) | int64 |

Scalar datasets chunk at `max(64, chunk_traces)` = 64. Attributes written at
open: `format_version`, `created_unix`, `created_iso`, **`config_json`**,
`units`. At close: `n_traces`, `closed_unix`. The GUI adds `mode`,
`igor_globals_json` and `segments_json` by reaching through
`writer._h5` (`controller.py:826-831`).

`config_json` is the whole `RigConfig`. That is what makes re-analysis
possible, and it is why the mode configs you do not use still travel.

### 6.2 `SessionWriter`

Igor's `SavePullOut` (`:438`). `__init__` (L38) opens nothing. `open()` (L50)
creates the file — **mode `"w"`, which truncates.** `_create` (L85) builds the
datasets on the first `append`, sizing them from the first trace.

`append(trace, selection)` (L104) resizes and writes one row. **`del index` at
L106**: the caller's trace index is deliberately discarded, so row order is
arrival order and nothing else. Data is flushed only when `_n % 32 == 0`
(L144), so up to 31 traces sit in memory at any moment.

**`GOTCHA` — `n_traces` is written only in `close()`** (L70), and `Session`
reads it at L168 as `attrs.get("n_traces", 0)`. **A killed process leaves a
file that reads as zero traces even though every row is physically present.**
The recovery is one line:

```python
n = session._h5["current_v"].shape[0]
```

Nothing in the codebase does this. If a night's run is interrupted, do not
assume the file is empty.

**`GOTCHA` — `write_summary` is a silent no-op if the file is already closed**
(L147). And `Session.__init__` (L160) leaks the file descriptor if the config
JSON fails to parse.

### 6.3 `Session` — reading back

`raw(i)` (L180) returns the stored volts. `conductance(i)` (L183) applies the
config's calibration on the way out; `conductances()` (L199) is the generator
version. `scalar(name)` (L203) pulls a per-trace column.

### 6.4 The Igor readers — untested, and the week-2 task

`load_ibw(path)` (L211) and `split_igor_block(block, n_parameters=20)` (L223).
These have **never been run against a real Igor file.** The only test
(`tests/test_core.py:346-351`) builds a block with the same assumptions it then
verifies, so it is circular.

They assume `block.shape == (n_samples + 2 + n_parameters, n_traces)`, column
oriented, and **infer** `n_samples = block.shape[0] − 2 − n_parameters` (L240)
rather than reading it from the file. Failure modes, ranked by how likely they
are to waste your time:

1. **`igor2` is not installed** — `ImportError` at L219. It is *not* in
   `requirements.txt`. Add it during week 1.
2. **A transposed block produces silent, plausible garbage.** A 100 × 10,000
   wave yields `n_samples = 78` and a `parameters` array of shape (10000, 20),
   so even a parameter-count assertion passes. **Check `traces.shape[1]` is
   about 10,000** before believing anything.
3. The two blank rows are never inspected. Asserting they are NaN is the
   cheapest real sanity check available and takes one line.
4. `n_parameters = 20` is a guess.
5. There is no lower bound on `n_samples`, so a negative slice succeeds
   silently.
6. Only `wData` is kept — the `x0`/`dx` axis scaling and the wave note are
   discarded.
7. **Igor stored conductance in float32**, not raw volts. So compare an Igor
   trace against `Session.conductance(i)`, never against `raw(i)`. And a packed
   `.pxp` will not load at all — you need unpacked `.ibw`.

**`PASS 2` will add:** the actual shape, dtype and parameter layout of one of
your archived files, replacing every guess above with a measurement.

{{TABLE:stmlab/storage.py}}

---

## Part 7 — The command line

### 7.1 `stmlab/main.py` — orchestration only

{{SIZE:stmlab/main.py}}

Four functions, and `run` (L25) is the one to read. It is the whole experiment
in forty lines, and it is the reference the GUI's worker thread reimplements:

```
validate(cfg)              -> print warnings, raise on fatal
SafeSession(cfg)           -> verify devices, park outputs
  Rig(cfg).open()
    session_calibration()  -> zero, group delay, granted rate   [if do_calibrate]
    SessionWriter.open()
      trace_loop(..., on_trace=writer.append)
    writer.write_summary()
  (Rig.close parks)
(SafeSession.__exit__ parks again)
summarise(out_path)
```

`summarise(path, peak_window=0.5)` (L74) opens a finished session, builds the
log histogram, finds the peak, and prints it — flagging anything beyond 0.05
decade from 0 (L87). **This is your control-measurement readout.** Run it on
every gold-gold session.

`build_parser` (L96) exposes the subcommands: `run`, `summarise`, `check`,
`dump-config`, `bringup`. `main` (L149) dispatches.

**`GOTCHA` — the program name is stale.** `prog="stmbj"` (L98) and
`log = logging.getLogger("stmbj")` (L22), but the package is `stmlab`. So
`--help` prints `usage: stmbj ...` while the command you actually type is
`python -m stmlab.main`. Cosmetic, but confusing on day one.

Default output path is `data/stmbj_<timestamp>.h5` (L200).

{{TABLE:stmlab/main.py}}

### 7.2 `run.py` and `experiments/01_constant_bias/`

{{SIZE:run.py}}

A dispatcher. `discover()` (L25) scans the `experiments/` folder for
subdirectories containing `run_experiment.py`; `main` (L35) runs one by name.
Nothing scientific happens here.

{{TABLE:run.py}}

{{SIZE:experiments/01_constant_bias/run_experiment.py}}

A thin delegator. `delegated_argv` (L34) maps the folder's argv convention onto
the `stmlab.main` CLI, so `python run_experiment.py --simulate -n 50` becomes
`stmbj run --simulate -n 50`. Experiment 01 **is** the constant-bias path —
Igor's `MeasureBreakJunctions` — so there is no separate implementation to
read. Experiments 02–08 cover the out-of-scope modes.

{{TABLE:experiments/01_constant_bias/run_experiment.py}}

---

## Part 8 — First contact with hardware: `stmlab/bringup.py`

{{SIZE:stmlab/bringup.py}}

Five ordered steps, each run **with the piezo disconnected and no tip near the
sample**, so nothing can be damaged while `daq.py` executes for the first time.
Each prints its measurements and a verdict: `PASS`, `CHECK` (the measurement
worked, you decide if the number is acceptable) or `FAIL`.

| Step | What it proves | Wiring |
|---:|---|---|
| 1 | the card is there, is a 4461, has the four channels, and grants the rate | nothing connected |
| 2 | AI is genuinely triggered off AO, with sub-sample-stable delay | one BNC, ao1 → ai0 |
| 3 | **ao0 holds its value between plays** | one BNC, ao0 → ai0 |
| 4 | the preamp gain is what the config claims | 1 MΩ resistor at the preamp input |
| 5 | the NanoPZ answers, and moves when told | NanoPZ on USB |

**This is the acceptance test for your week-1 environment install.** Step 1
passing means NI-DAQmx, the Python bindings and the device alias are all
correct. It needs no wiring and no tip, so run it the moment the software is
installed.

**`READ CLOSELY` — step 3, `step_hold` (L191).** The decisive test for whether
the approach can work at all. Each 0.5 nm step is a separate `play`, and the
piezo has to stay where it was put in the gap between them. The test commands
4.0 V, then plays again and looks at the **opening** 20 samples of the new
record: if the output had fallen to 0 V in the gap, the record would open near
zero and climb. It also confirms the piezo line never goes negative, which a
unipolar piezo cannot tolerate.

If step 3 fails, the step-wise approach does not work as written and the AO
task has to run continuously instead. That is an architecture change, not a
tuning change, which is why it is worth finding out in week 1 rather than
week 4.

**`READ CLOSELY` — step 4, `step_preamp` (L250).** 100 mV across 1 MΩ is
100 nA, which at 1e6 V/A must read exactly 0.1 V. Accepts a ratio between 0.98
and 1.02. If it is wrong, every conductance this rig ever reports is scaled by
the same factor — and the failure message prints the error in decades, because
that is the form in which you will see it in the histogram. It also measures
and prints the preamp zero (put it in the config) and the noise floor in G₀ at
5σ, telling you how many decades below 1 G₀ you actually have.

Step 2 (`step_timing`, L143) additionally reports two things nothing else
reveals: whether the card accepted `MAINTAIN_EXISTING_VALUE` for AO idle, and
whether retriggerable AI is supported. Both are `CHECK` rather than `FAIL`
when unavailable.

Step 5 (`step_actuator`, L309) is communication-only by default. `--move` is
opt-in and steps **away** from the sample first, never toward it.

**`GOTCHA` — the documented command does not exist.** The module docstring and
`prog` both say `python -m stmbj.bringup 1`, but the package is `stmlab`. Typing
the documented command gives `No module named stmbj`. Use either of:

```
python -m stmlab.bringup 1
python -m stmlab.main bringup 1
```

`manual/03_hardware.md` and `manual/30_quick_reference.md` have it right.

**`GOTCHA` — the docstring says "four steps" and then defines five.** The
`STEPS` dict has five entries and argparse accepts `5`. The "step 5 is not
automated, deliberately" sentence in the docstring refers to a *sixth*,
unautomated rung: connect the piezo, watch ao0 on a scope through one
`engage()`, confirm it ramps 0 → 10 V and never goes negative. That rung is
real and you should still do it — it just is not numbered consistently.

{{TABLE:stmlab/bringup.py}}

---

## Part 9 — The GUI

### 9.0 The threading model, before anything else

Three rules. Everything in `stmgui/` is a consequence of them.

1. **One worker thread owns the `Rig`.** `RigController` runs a single daemon
   thread named `stmgui-worker`. It never imports Tk.
2. **Panels never touch the `Rig`.** They put a callable on
   `RigController._q` and return immediately.
3. **Results come back through an event queue.** `App._pump` drains
   `ctl.events` every 50 ms on the Tk thread and fans each event out to the
   panels.

**There is no `Lock` anywhere in `stmgui/.`** Mutual exclusion comes from
serialisation: one consumer, one `queue.Queue`, so two hardware operations
cannot overlap by construction. This is worth internalising, because it means
"is this thread-safe?" is usually the wrong question — the right question is
"does this run on the worker or on the Tk thread?"

### 9.1 `gui.py` and `stmgui/app.py` — the shell

{{SIZE:gui.py}}

Thirty-seven lines. `_check_tk` (L20) gives a readable error if Tk is missing,
then the app launches. Igor equivalent: the `Macros` block, `Setup1_STMBJ.ipf:55`.

{{TABLE:gui.py}}

{{SIZE:stmgui/app.py}}

`App.__init__` (L41–91) is Igor's `InitializeExperiment`: build the state,
start the `RigController` (L61 — this is where the worker thread begins),
create the panels and the graph set, bind **Alt and Escape globally to
`ctl.request_stop`** (L72–73), and arm the pump with `root.after(50, self._pump)`
(L91).

`_pump` (L268) drains **at most 200 events per tick** and re-arms after
`PUMP_MS = 50`. If the worker produces events faster than 4,000/s the queue
grows; in practice it does not. `_fanout` (L258) delivers each event to five
targets — main panel, voltage-offset panel, echem panel, history window, graph
set — each inside a `try` that swallows `TclError`, so a closed window cannot
kill the pump.

`pump_once` (L278) is the synchronous variant the tests use. `quit` (L287)
calls `ctl.shutdown()` (L204).

{{TABLE:stmgui/app.py}}

### 9.2 `stmgui/state.py` — Igor's globals, rehoused

{{SIZE:stmgui/state.py}}

`GuiOptions` (L26) holds the Igor globals that have no `RigConfig` home, using
the Igor names. `GuiState` (L106) is the config plus the options — everything
the panels read and write.

**`READ CLOSELY` — `Param` (L117).** One panel control's binding: a dotted path
into the state, a display unit, a coercion, and the Igor limits. `Param.set`
(L146) coerces, **clamps to the Igor limits**, stores, and returns what was
actually stored in display units, so the widget can show you the clamped value
rather than what you typed. This is how every number you type into the GUI
reaches `RigConfig`, and it is the layer where mV-vs-V and nm-vs-V conversions
live.

`mode` (L84) and `select_mode` (L96) reproduce Igor's `RampOptionsCheckProc`:
ticking one mode box clears the others. Only `constant` is in scope here.

`simulated_state()` (L328) builds a `GuiState` wired for the simulator — the
GUI equivalent of the snippets' `sim_config`. This is what you launch on your
Mac.

{{TABLE:stmgui/state.py}}

### 9.3 `stmgui/widgets.py` — Igor's control types as Tk composites

{{SIZE:stmgui/widgets.py}}

`SetVariable` (L166), `ValDisplay` (L234), `CheckBox` (L259), `button` (L290),
`groupbox` (L316) — one per Igor control type, so the panel code reads like the
Igor panel code.

The part worth knowing: **`tip_text` (L52) and `bind_inspect` (L138).** Given a
controller method, `tip_text` produces the full description — what it does,
which Igor procedure it replaces, and which `stmlab` calls it makes. Hover for
the tooltip; right-click (or Control-click) any control for the inspector. This
is a discovery tool built into the running program, and it is faster than
grepping when you are standing at the rig.

{{TABLE:stmgui/widgets.py}}

### 9.4 `stmgui/controller.py` — the worker, and the whole lab flow

{{SIZE:stmgui/controller.py}}

The largest file in scope by a wide margin, and structurally simple: a queue, a
thread, and one method pair per button.

**The machinery** (read this first, it is about 120 lines):

- `_q` (L122) — `queue.Queue` of `(name, fn, args, kwargs, done_event, box)`.
- `events` (L99) — `queue.Queue` of `(kind, payload)`, drained by `App._pump`.
- `_worker` (L157) — the single consumer. Blocks on `_q.get(timeout=BKGD_PERIOD_S)`
  (L160). On a command it emits `("busy", name)` (L174), logs a
  `-> name: file:line qualname` line (L177), runs it, catches domain errors
  (L182–187), and **always** emits `("idle", name)` (L195).
- The `queue.Empty` branch (L163–169) is where **background sampling** runs —
  see `_background_read` below. Idle time is not wasted.
- `QueueLogHandler` (L74–87) attaches to the `stmlab` and `stmgui` loggers, so
  every log line in the package appears in the History window in order, exactly
  like Igor's history.

**The button pairs.** Each has a public method that queues, and a
`_..._impl` that runs on the worker.

| Button | Public | Impl | Igor |
|---|---|---|---|
| Start Writing | `start_writing` L286 | `_start_writing_impl` L305 | `StartHighResWritingTask`, Controls:127 |
| Background Sampling | `set_background_sampling` L388 | `_background_read` L399 | `BackgroundRead`, Functions:657 |
| Start Approach | `approach` L599 | `_approach_impl` L605 | `HighResCardApproach`, Functions:1723 |
| Find Offset | `find_offset` L551 | `_find_offset_impl` L556 | `OffsetVoltage`, Controls:498 |
| Find Suppress | `find_suppress` L527 | `_find_suppress_impl` L532 | `TestVirtualGround`, Controls:479 |
| Start Measurement | `start_measurement` L646 | `_measure_impl` L722 | `MeasureBreakJunctions`, Functions:1664 |
| Kill Tasks | `kill_tasks` L327 | `_kill_tasks_impl` L333 | — |

`_start_writing_impl` builds the `Rig` (`_make_rig` L292), runs
`config.validate` (L309), holds the outputs (L313–314) and runs
`session_calibration` (L320–325). **The tip must be out of contact.**

**`GOTCHA` — Start Writing calibrates at most once per session.** The call is
guarded by `if self.opts.calibrate_on_start_writing and not self.calibrated`
(L320), and `self.calibrated` is set True at L322 and never reset — not by Kill
Tasks, not by a second Start Writing. The option itself defaults to True
(`state.py:82`). So the preamp zero you measure at 8 p.m. is the one used at
4 a.m., through however many stop/start cycles. If you want a fresh zero, you
need a fresh `RigController`, i.e. restart the GUI.

`_measure_impl` is the GUI's `trace_loop`. `_open_writer` (L699) names files
`constant_HHMMSS_from<Saved>.h5`. The stop flag is polled at L747.
`HIST_BLOCK = 100`, and `_histogram_block` (L872) pushes a histogram to the
graph every hundred accepted traces. Teardown is in a `finally` (L843–849).

**`READ CLOSELY` — `set_background_sampling` (L388) is the one rule-breaker.**
It is *not* queued; it runs on the Tk thread. It is the single place where the
"panels never touch the Rig" rule is bent, and it is deliberate — but it is
the first thing to suspect if you ever see a race.

**`READ CLOSELY` — Stop.** `self.stop` is a `threading.Event` (L106).
`request_stop` (L221) is **not queued** — it sets the event from whichever
thread calls it, which is what makes Alt and Escape responsive. But it is
**polled in only four places**: L617 (coarse approach), L747 (measurement
loop), L998 and L1019. A pull in progress always runs to completion; `trace.capture`
never sees the flag. Stop is "finish this attempt and stop", not an emergency
stop. The emergency stop is Kill Tasks, which sets `stop` on the Tk thread
*before* queuing `_kill_tasks_impl` (L327–333).

After a clean Kill Tasks you are guaranteed: piezo at park voltage, bias 0 V,
tasks closed, Keithley zero-check on.

**`READ CLOSELY` — `COMMAND_MAP` (L1068–1190)** maps every control to
`(panel label, Igor procedure, _impl name, [dotted stmlab calls])`. `_resolve`
(L1193), `locate` (L1211, using `inspect`), `where` (L1227),
`describe_command` (L1234) and `command_table` (L1257) build on it. **Four
routes reach the same text**: hover tooltip, right-click inspect,
Windows/Help → Button map, and the `->` line the worker logs into History.
When you cannot remember what a button does, any of the four answers in a
second.

**`GOTCHA` — `_approach_impl` forces `actuator.step_size = 5` (L611) and never
restores it.** If you changed the step size in the panel, Start Approach
silently overrides it for the rest of the session.

**`GOTCHA` — `ApproachError` breaks the whole measurement run** (L771–775),
rather than backing the coarse actuator off. `approach.recover_headroom` exists
precisely for this and is not wired in. This is the most likely cause of an
overnight run dying early.

**`GOTCHA` — `wait_idle` ignores its `timeout` argument** (`del timeout`,
L202).

**`GOTCHA` — `_histogram_block(partial=True)` does not clear `self.block`**, so
traces in a partial block are histogrammed again on the next run.

**`GOTCHA` — GUI state is set before the hardware call succeeds** in four
places: `zero_check` (L505), `suppress_enable` (L516), `keithley_bias` (L523)
and `kill_tasks` (L330). If the instrument refuses, the checkbox still shows
the new state.

**`GOTCHA` — the module docstring is wrong** about what Stop does during Find
Suppress and Find Offset. Trust the code.

**`PASS 2` will add:** a line-by-line read of `_measure_impl`; the full event
vocabulary (`kind` values) and which panel consumes each.

{{TABLE:stmgui/controller.py}}

### 9.5 The panels

{{SIZE:stmgui/panels/main_panel.py}}

`MainPanel` is Igor's `BreakJunctionMeasurement` panel
(`Windows_STMBJ.ipf:133-375`), rebuilt as three tabs: `_build_daq_tab` (L228),
`_build_inputs_tab` (L263), `_build_options_tab` (L281). `_sv` (L47) and `_cb`
(L52) are the one-line helpers that bind a control to a `Param` by its Igor
name — which means you can find any control by grepping for the Igor global.

`set_writing` (L394) holds the enable/disable lists for
`StartHighResWritingTask` / `StopWritingTasks`; `set_busy` (L407) greys
controls while the worker is running one; `on_event` (L427) is the panel's half
of the pump.

{{TABLE:stmgui/panels/main_panel.py}}

{{SIZE:stmgui/panels/voltage_offset.py}}

The Voltage_Offset panel (`Windows_STMBJ.ipf:378-405`). Small. Drives Find
Offset and shows the result; the measurement itself is `vzero.py` (Appendix A).

{{TABLE:stmgui/panels/voltage_offset.py}}

{{SIZE:stmgui/panels/history.py}}

Igor's history window: every log line, in order, with tags. Fifty-three lines
and the most useful window on the screen — the worker's `->` line for every
command lands here, so History doubles as a record of exactly which Python ran.

{{TABLE:stmgui/panels/history.py}}

{{SIZE:stmgui/panels/button_map.py}}

`ButtonMapWindow` (L17) renders `controller.command_table()` — every control,
its Python, its Igor original, and the `stmlab` calls underneath.
`InspectorWindow` (L71) is what right-click opens. Read these two classes once;
after that, use the windows instead of grep.

{{TABLE:stmgui/panels/button_map.py}}

### 9.6 `stmgui/graphs.py` — the nine Igor graph windows

{{SIZE:stmgui/graphs.py}}

One class per Igor graph window from `Windows_STMBJ.ipf`, all matplotlib in Tk,
all created lazily and positioned to match Igor's `/W=` boxes. `GraphWindow`
(L40) is the base; subclasses override `decorate()` (axes, once) and `update()`
(data, per event).

In scope for you: `HighRes` (L79, the live background sample), `PullOutGvsE`
(L137), `PullOutLow` (L142), `AuAuConductanceLevel` (L177) — the three trace
views sharing `_TraceGraph` (L110) — `LogHistOfBlock` (L204, the histogram that
updates every 100 traces), and `SenseInDisplay` (L185). `Izero` (L232) and
`IzeroTime` (L267) belong to the Vzero workflow; `CyclicVoltammogram` (L289) is
electrochemistry and out of scope.

`GraphSet` (L327) owns all nine. **`on_event` (L375) routes by the `FEEDS`
table (L343–351)** — that table is the mapping from event kind to graph, and it
is the fastest way to answer "why is this window not updating".

{{TABLE:stmgui/graphs.py}}

---

## Part 10 — The lab flow, end to end

The seven buttons in the order you press them, and what each one actually
executes. This is the section to have open at the rig.

### Start Writing

`main_panel` → `RigController.start_writing` (L286) → queue →
`_start_writing_impl` (L305) on the worker.

`_make_rig` (L292) builds the `RigConfig` from `GuiState` → `config.validate`
(warnings into History, `ConfigError` stops here) → `Rig.open()`, which opens
the DAQmx tasks and calls `piezo_goto(piezo_park_v)` to make the tracker
truthful → `rig.hold(...)` to establish the outputs →
`calibrate.session_calibration` measures the preamp zero and the AI/AO group
delay and records the granted sample rate.

**Tip out of contact.** The zero measurement is meaningless otherwise — and
you get one chance at it per GUI launch (§9.4), so do not press this button
with the tip down and expect to fix it by pressing it again.

### Background Sampling

Toggle only. `set_background_sampling` (L388) sets a flag **on the Tk thread**.
The worker's `queue.Empty` branch (L163–169) then calls `_background_read`
(L399) roughly every 0.25 s whenever no command is queued — Igor's
`BackgroundRead` (`Functions_STMBJ.ipf:657`). Feeds the `HighRes` graph. This
is how you watch the current while you adjust anything by hand.

### Start Approach

`approach` (L599) → `_approach_impl` (L605) → `stmlab.approach.coarse_approach`.
Forces `actuator.step_size = 5` (L611, and never restores it). Steps the coarse
actuator in, reading `rig.read_current_ua()` between steps, until
`abs(current) >= 0.1 µA`. Every step passes `Rig.coarse_step`, so
`require_retracted` and `check_step_budget` are enforced per step. Stop is
polled at L617.

Ends with `state = RETRACTED` and the tip close enough that the fine piezo can
reach the surface.

### Find Offset (Find Zero)

`find_offset` (L551) → `_find_offset_impl` (L556) → `vzero.measure_offset`.
Igor's `OffsetVoltage` (`Controls_STMBJ.ipf:498`). Steps into contact, sweeps
the bias through ±`interval_mv`, fits I(V), and reports the bias that nulls the
current. `_record_vzero` (L563–574) stores it and feeds the `Izero` and
`IzeroTime` graphs.

**The offset only affects a measurement if "V0 check ON" is ticked** —
`use_vzero` at L737. Otherwise it is recorded and ignored.

### Find Suppress

`find_suppress` (L527) → `_find_suppress_impl` (L532) →
`keithley.find_suppress`. Igor's `TestVirtualGround`
(`Controls_STMBJ.ipf:479`). Sweeps the 428's suppression current to null the
measured output at zero bias. Bias is restored in a `finally` (L540). Only
relevant if the Keithley is in the loop.

### Start Measurement

`start_measurement` (L646) → `_measure_impl` (L722). The overnight run.

`_open_writer` (L699) creates `constant_HHMMSS_from<Saved>.h5`, then for each
attempt: optional `smash` every 50 → `engage` → `single_trace` → `select_trace`
→ on acceptance, `writer.append` plus an event to the three trace graphs; every
`HIST_BLOCK = 100` accepted traces, `_histogram_block` (L872) rebuilds the log
histogram and pushes it to `LogHistOfBlock`. Stop polled at L747. Teardown in a
`finally` (L843–849), which is where `n_traces` gets written.

**Remember `require_engaged`.** With the default `False`, `select_trace` early-accepts
any trace starting below the engage threshold without running the noise or
plateau tests (§5.3).

### Stop / Kill Tasks

Alt or Escape, or the button. `request_stop` (L221) sets the event immediately
from any thread; the loop notices between attempts. `kill_tasks` (L327) sets
`stop` first and then queues `_kill_tasks_impl` (L333), which closes the tasks
and parks everything.

Guaranteed after a clean kill: **piezo at park voltage, bias 0 V, tasks closed,
Keithley zero-check on.**

### Afterwards

```
python -m stmlab.main summarise data/constant_HHMMSS_from0.h5
```

Prints the log-histogram peak. For a gold-gold control, it should sit within
0.05 decade of 0. Anything else is a calibration question, not a chemistry one
— see §5.1 for which constant moves a peak which way.

---

## Part 11 — Reading plan

Mapped onto the five weeks. Each block is about two hours.

| When | Read | Do |
|---|---|---|
| Wk 1, day 1 | Part 0, §1.1, §1.2 | install NI-DAQmx + Python 3.12 venv on the lab PC |
| Wk 1, day 2 | §2.1, §2.2 | `python -m stmlab.bringup 1` — the acceptance test for the install |
| Wk 1, day 3 | Part 8 in full | add `igor2` to `requirements.txt`; run the 121 tests on the lab PC |
| Wk 1, day 4–5 | §2.3, §2.4 | run the GUI against the simulator on the lab PC end to end |
| Wk 2, day 1–2 | Part 3, Part 4 | trace one simulated pull by hand: print the ramp, the record, the recovered delay |
| Wk 2, day 3 | Part 5 | **open an archived `.ibw` and check `traces.shape`** (§6.4) |
| Wk 2, day 4–5 | Part 6 | histogram an Igor block and a simulated session on the same axes |
| Wk 3, day 1–2 | Part 9 | bring-up steps 2, 3, 4 with BNC cables and a 1 MΩ resistor |
| Wk 3, day 3 | Part 10 | bring-up step 5, then the unautomated scope check on ao0 |
| Wk 3–4 | fill in the `PASS 2` gaps as you meet them | first real approach, first real trace |
| Wk 5 | §5.1, §5.4, §7.1 | gold-gold control; `summarise`; compare the 1 G₀ peak to the Igor archive |

---

## Appendix A — Beside the path

### A.1 `stmlab/vzero.py` — the Voltage_Offset workflow

{{SIZE:stmlab/vzero.py}}

Find the applied bias that nulls the current. Igor's `OffsetVoltage` /
`SaveOffset` (`Functions_STMBJ.ipf:920-1041`).

`_ensure_contact` (L49) is Igor's `HighResContact`: step in 2 nm at a time at
100 mV until above threshold. `measure_offset` (L66) then sweeps ±`interval_mv`
(5 mV, `n_points = 5` per polarity) in contact and fits I(V), returning a
`VzeroResult` (L39). `VzeroTracker` (L112) re-measures every
`every_n_traces = 50` accepted traces and keeps the history;
`as_arrays` (L143) flattens it for an HDF5 attribute.

The correction enters `trace.build_ramp` as `bias_offset_v`, and — see §4.1 —
it is added to the **baseline only**, never to the alignment spike, exactly as
Igor did it.

{{TABLE:stmlab/vzero.py}}

### A.2 `stmlab/keithley.py` — the 428 over GPIB

{{SIZE:stmlab/keithley.py}}

`Keithley428` (L68) needs `pyvisa` and an NI GPIB interface at
`GPIB0::22::INSTR`. `SimulatedKeithley` (L171) has the same surface and records
every command. `make_keithley` (L190) chooses.

The one that matters for your data: **`set_gain(exponent)` (L137)** programs
the transimpedance to 10^exponent V/A. Nothing connects it to
`cal.preamp_gain_v_per_a`, which is what every conductance divides by — the
only link is the warning in `config.validate` (§1.1). Program the gain and
forget the config and your histogram moves by whole decades.

`series_corrected_conductance` (L50) reproduces Igor's `PullOutConductance`,
which subtracts a 106.13 kΩ series resistance. Note that nothing in the
constant-bias path calls it: `analysis.to_conductance` does not apply the series
correction. If you are comparing against Igor numbers, check which of the two
Igor used for that wave.

`find_suppress` (L199) is Igor's `TestVirtualGround`.

{{TABLE:stmlab/keithley.py}}

---

## Appendix B — Confirmed defects

All verified against source. Ordered by how much time they can cost you.

| # | Where | What | Why it matters |
|---:|---|---|---|
| 1 | `actuator.make_actuator` | tests `kind == "nanopz"` **before** `simulate` | a "simulated" run opens the real serial port and energises the motor |
| 2 | `bringup.py` docstring, `main.py:98` | say `stmbj`, package is `stmlab` | the documented command fails on day one |
| 3 | `analysis.select_trace` L210+ | early-accepts when `require_engaged=False` | noise and plateau tests silently skipped in the default config |
| 4 | `storage.SessionWriter.close` L70 | `n_traces` written only on clean close | an interrupted night reads as **zero traces**; rows are still there |
| 5 | `instrument.Rig.open` L52 | `make_actuator(cfg)` with no sim reference | simulated `coarse_approach` never converges, burns the 2,000-step budget |
| 5b | `controller._start_writing_impl` L320 | `self.calibrated` latches True and is never reset | the preamp zero is measured once per GUI launch, not once per run |
| 6 | `controller._measure_impl` L771 | `ApproachError` ends the run | `approach.recover_headroom` exists for this and is not wired in |
| 7 | `calibrate.measure_gain_offset` L105 | sweeps ±2 V against a 0.5 V limit | uncallable dead code; `ai_gain_error`/`ai_offset_v` never measured *or applied* |
| 8 | `calibrate.measure_zero` L52 | `volts_to_amps(noise)` subtracts the zero from a noise value | logged noise figure is wrong; and `record` unbound on early failure → `NameError` masks the real error |
| 9 | `controller._approach_impl` L611 | forces `step_size = 5`, never restores | a panel change is silently overridden for the session |
| 10 | `storage.load_ibw` / `split_igor_block` | never run against a real file; `n_samples` inferred | a transposed block yields plausible garbage — check `traces.shape[1]` ≈ 10,000 |
| 11 | `controller.wait_idle` L202 | `del timeout` | the timeout argument does nothing |
| 12 | `controller._histogram_block` | `partial=True` does not clear `self.block` | partial-block traces re-histogrammed next run |
| 13 | `controller` L505, L516, L523, L330 | GUI state set before the hardware call | checkbox shows a state the instrument refused |
| 14 | `daq.DaqError` L44 | defined, never raised | dead; real failures are `nidaqmx.DaqError` |
| 15 | `sim.configure` L69 | no-op | the AI re-arm and retriggerable-fallback branches in `daq.py` have never executed |

---

## Appendix C — What this code has and has not earned

In descending order of trust:

1. **The constant-bias path** — reviewed, unit-tested, self-consistent on
   synthetic data. Everything in Parts 3–6.
2. **Index-for-index translations exercised on the simulator** — the ramp
   arithmetic, the spike geometry, the histogram binning.
3. **Never met its instrument** — every `nidaqmx` call, the Keithley over GPIB,
   the NanoPZ over serial. None of this has run against hardware.

And the one gap that is neither code nor hardware: **the Igor comparison has
never been done.** No trace produced by this package has ever been checked
against a trace produced by the Igor procedures it replaces. You have archived
`.ibw` files and that check needs no rig, which is why it sits in week 2.

Until it is done, a 1 G₀ peak in the right place proves the Python is
self-consistent. It does not prove the Python agrees with Igor.

<!--NEXT-->
