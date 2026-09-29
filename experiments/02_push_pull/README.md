# Push-pull junction cycling

Instead of breaking a fresh junction on every trace, this mode re-forms the
*same* junction over and over within a single trace: pull partway out, hold,
push back in, hold, pull out again -- and watch whether a molecule re-binds
each time.

## The physics

In a constant pull the molecular plateau tells you a molecule bridged the gap
once. Push-pull cycling asks the follow-up question: is that binding
repeatable at the same spot? The trajectory is an initial pull (default 3 nm)
that thins the fresh metallic contact, then per cycle {hold, push 1 nm back
in, hold, pull 1 nm back out} (default 2 cycles), then a long final pull
(default 4 nm) that breaks the junction for good. The bias stays at the DC
baseline the whole time, so the current record is directly a conductance
record. If the molecular junction re-forms on each push, the conductance
returns to the molecular plateau on each cycle; if the molecule diffused away
or the contact restructured, it does not. The holds either side of each push
(1 nm worth of time at the pull rate) give the junction time to settle, so
re-binding kinetics are visible rather than smeared by motion.

Because every push is undone by a matching pull, the cycles net to zero and
the trajectory's net descent is just initial + final pull; the runner sets
`cfg.ramp.pull_length_nm` to that sum so the headroom pre-check in `engage()`
matches this mode's real excursion.

**Every captured trace is stored.** Igor's `TestTrace` selection applied only
to constant pulls, and here a trace that never re-binds is still an answer --
so no selection is applied, only the alignment check inside `trace.capture`
(a misaligned play is discarded and retried, never written).

## Igor origin

Translated from `igor_code/Functions_STMBJ.ipf`:

| Python                                   | Igor                              | line      |
| ---------------------------------------- | --------------------------------- | --------- |
| `stmlab.ramps.build_push_pull`           | `CreateInputs`, PushPull branch   | 1461-1495 |
| trajectory geometry (init/cycles/final)  | segment index bookkeeping         | 1467-1493 |
| constant bias during cycling             | `JunctionBiasWave = -(TipBias/1000)` | 1495   |
| `run_experiment.py` acquisition loop     | `MeasureBreakJunctions`           | 1664      |

Geometry parameters map to Igor globals: `--initial-nm` = G_InitialPullLength,
`--push-nm` = G_PushPullLength, `--hold-nm` = G_HoldLength, `--final-nm` =
G_FinalPullLength, `--cycles` = G_NumPushPullCycles (defaults 3 / 1 / 1 / 4 nm
and 2 cycles, in `cfg.push_pull`).

## Hardware

- NI DAQ card (analog out: piezo Z + bias; analog in: bias monitor + preamp
  output); optional second low-res card (`channels.low_res_device`).
- STM head with Z piezo, gold tip, gold-on-mica substrate (with the molecule
  of interest deposited -- the mode only makes sense with molecules present).
- Current preamplifier (gain in `cal.preamp_gain_v_per_a`).
- Optional coarse actuator for automatic headroom recovery.

No hardware is needed with `--simulate`: the simulated card runs the full
pipeline.

## Commands

From `python_code_entire_igor/` (use the venv python):

    # simulate, 3 quick traces
    .venv/Scripts/python.exe experiments/02_push_pull/run_experiment.py --simulate -n 3 -o data/rm02.h5

    # real rig: 200 traces with a longer hold and 5 cycles
    .venv/Scripts/python.exe experiments/02_push_pull/run_experiment.py --config rig.json -n 200 --cycles 5 --hold-nm 2 -o data/pp_session.h5

    # equivalently, via the dispatcher
    python run.py push_pull --simulate -n 3

Flags: `-n/--traces`, `-o/--out` (default `data/push_pull_<timestamp>.h5`),
`--simulate`, `--config PATH`, `--no-calibrate`, `-v/--verbose`, plus the
geometry overrides `--cycles`, `--push-nm`, `--hold-nm`, `--initial-nm`,
`--final-nm`. Ctrl-C once finishes the current trace and stops cleanly; twice
exits immediately.

## What is stored

One HDF5 file per session, written by `stmlab.storage.SessionWriter`: the
full `RigConfig` as JSON, and per trace the raw voltage and current records
(volts), alignment delay, start piezo voltage, bias, and sample rate, plus a
summary (attempts, acceptance rate, rejection counts -- only `engage` and
`alignment` are possible here -- and the cycle count). All traces in one file
have equal length. Additionally the root attribute `segments_json` maps each
trajectory segment name to its `(start, stop)` index pair into the cut trace:
`initial_pull`, then per cycle `cycle<k>_hold_out`, `cycle<k>_push`,
`cycle<k>_hold_in`, `cycle<k>_pull`, then `final_pull`. The segment map is
identical for every trace in the file (only the trajectory's starting piezo
voltage moves between attempts), which is why it is written once.

## Looking at the data

    import json
    from stmlab import storage

    with storage.Session("data/pp_session.h5") as s:
        segments = json.loads(s._h5.attrs["segments_json"])
        a, b = segments["cycle0_hold_in"]          # after the first push
        for i in range(len(s)):
            g0 = s.conductance(i)                  # computed from raw volts
            print(g0[a:b].mean())                  # did it re-bind?

Compare the conductance during each `cycle<k>_hold_in` window against the
molecular plateau value from a constant-bias session: re-binding shows up as
the hold-in conductance returning to the plateau cycle after cycle.
