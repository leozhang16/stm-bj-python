# 47. What the GUI writes, and how to read it back

*Igor: `MakePath`, Functions_STMBJ.ipf:200; `SavePullOut`, :438; `LogHistFromBlocks`, :785. Modules: `stmgui/controller.py` (naming, headers), `stmlab/storage.py` (formats).*

Igor wrote its data as `.ibw` blocks — one two-dimensional wave per
hundred saved traces, each column a trace with twenty parameters stacked
on top of the conductance — into a dated folder under `D:Experiments:`
(`DataDir`, `MakePath`). The GUI writes HDF5 session files, CSV
histograms and HDF5 voltammograms into a dated folder under `data/`. This
chapter is the exact layout of each, how to read them, and how they relate
to what Igor kept.

## Where

`GuiOptions.data_dir` (default `data`, relative to the package folder)
plus a folder named for the day, `YYYYMMDD` — `RigController.data_dir()`,
Igor's `G_PathDate`. Created on first use. **File → Open data folder**
opens today's. Set `data_dir` to an absolute path in a script or a custom
launcher to write elsewhere; there is no panel control for it.

## Session files

**Name:** `<mode>_<HHMMSS>_from<Saved>.h5`, where `mode` is `constant`,
`push_pull`, `iv`, `ac_hold` or `hb_hold`, the time is when Start
Measurement (or +1) was pressed, and `Saved` is the Saved counter at that
moment — the number the first trace in the file will have. One file per
press. A run of three presses at Saved 1, 101 and 201 leaves
`constant_152830_from1.h5`, `constant_153102_from101.h5`,
`constant_153340_from201.h5`, and the numbering carries through them.

Igor's unit was the 100-trace block, written by `SavePullOut` whenever
`PullOutNumber` crossed a multiple of 100; a run stopped at 250 left two
full blocks and 50 traces in memory. Here the file is flushed every 32
traces and closed properly at the end of every run, including a stopped
one, so nothing is left in memory.

**Written by** `stmlab.storage.SessionWriter`. The layout:

| Dataset | Shape | Meaning |
|---|---|---|
| `voltage_v` | (n, samples) float64 | raw ADC volts, junction-voltage channel, one row per accepted trace |
| `current_v` | (n, samples) float64 | raw ADC volts, preamp output |
| `delay_samples` | (n,) int32 | the AI/AO lag recovered from the alignment spike |
| `start_piezo_v` | (n,) float64 | the piezo voltage at which the pull started (the contact point) |
| `bias_v` | (n,) float64 | the applied DC bias, in volts, **including V0** when V0 check was ON |
| `sample_rate_hz` | (n,) float64 | the granted rate |
| `timestamp` | (n,) float64 | Unix time of capture |
| `attempt` | (n,) int64 | the global attempt number (Attempts on the panel) |
| `end_conductance_g0` | (n,) float64 | from `TestTrace`; NaN for the ramp modes |
| `start_conductance_g0` | (n,) float64 | from `TestTrace`; NaN for the ramp modes |

`samples` is the number of points in the pull proper — 10 000 for a 5 nm
pull at 20 nm/s and 40 kHz — or the full length of a mode ramp. A ramp
parameter changed mid-file is refused (`a ramp parameter changed
mid-session`); that cannot happen from the panel, because each press
opens a new file, but it is why the file is per press.

**Header attributes:**

| Attribute | Written by | Content |
|---|---|---|
| `format_version` | storage | 1 |
| `created_unix`, `created_iso` | storage | when the file was opened |
| `config_json` | storage | the complete `RigConfig` as JSON, the same document File → Save writes |
| `units` | storage | the sentence "voltage_v and current_v are raw volts at the ADC. Conductance is derived, not stored." |
| `n_traces`, `closed_unix` | storage, at close | the row count and when the file was closed |
| `mode` | the GUI | the mode string |
| `igor_globals_json` | the GUI | every panel value, keyed by its Igor global name |
| `segments_json` | the GUI, ramp modes only | the ramp's segment table: name → (start, stop) sample indices |
| `run_stats_json` | the GUI, at close | `saved_upto`, `attempts_total`, `rejections` by reason, `vzero_history` |

Two of these are the GUI's own. `igor_globals_json` is what the panel
showed when the file was opened — `G_TipBias: 100.0`,
`G_PseudoTotalLength_nm: 5.0`, `ZeroCheckBox: false`, all seventy-odd rows
of chapter 51 — so a file can be read the way an Igor block was, by the
names in the panel, and so the non-config state (Stop #, the save flags,
the mode checkboxes) is on record. `run_stats_json` is the run's
bookkeeping: `rejections` is a dictionary of reason → count
(`engage`, `alignment`, and `select_trace`'s reasons), `vzero_history`
holds the arrays `vzero_mv`, `izero_a` and `timestamp` of every offset
measurement so far in the launch — Igor's `OffsetWave`, `IzeroWave`.

Conductance is **not** stored. It is `current / voltage / G0` with the
calibration in `config_json`, recomputed on every read, so that a
corrected gain six months later re-analyses the raw data instead of
invalidating it. That is the reason the raw volts are always kept and the
Save Bias / Save Current boxes are records rather than switches.

## Reading a session file

```python
from stmlab import analysis, storage
from stmlab.config import RigConfig

with storage.Session("data/20260902/constant_152830_from1.h5") as s:
    n = len(s)
    v, i = s.raw(0)                     # raw volts, first trace
    g0 = s.conductance(0)               # measured V and I -> G/G0
    starts = s.scalar("start_piezo_v")  # any per-trace scalar
    centres, counts = analysis.log_histogram(
        s.conductances(), zero_cutoff=5e-4)
```

`Session.conductance(i, cal=None, use_measured_voltage=True)` uses the
calibration stored in the file unless you pass another; with
`use_measured_voltage=False` it divides by the recorded `bias_v` instead
of the measured junction voltage, which is what to do when the voltage
channel was not trustworthy. `conductances()` is a generator over all
traces, which is what `log_histogram` wants. The header attributes are on
`s._h5.attrs`; `json.loads(s._h5.attrs["igor_globals_json"])` gives the
panel back as a dictionary, `RigConfig.from_dict(json.loads(
s._h5.attrs["config_json"]))` the config.

For the ramp modes, cut the segment you want with `segments_json`:

```python
import json
seg = json.loads(s._h5.attrs["segments_json"])   # e.g. {"iv_ramp": [6000, 10000], ...}
a, b = seg["iv_ramp"]
v_sweep, i_sweep = (x[a:b] for x in s.raw(0))
```

`experiments/03_iv_sweep/iv_analysis.py` and the other analysis scripts
do this for each mode; chapters 11-14.

## Histogram files

**Name:** `loghist_<HHMMSS>_upto<Saved>.csv`, written when a block of 100
saved traces completes and, at the end of a run, for the partial block —
only when **Save Hist** is ticked (`G_HistSaveCheck`, on by default). Two
columns, `log10(G/G0)` and `counts_per_trace`, 1000 rows from −8 to 2, a
one-line header. It is `analysis.log_histogram` of that block with the
zero cutoff `cfg.ramp.break_g0`, exactly what the LogHistOfBlock window
showed. `Saved` in the name is the counter *after* the block, so
`upto101` is traces 1-100.

The CSV is a convenience; the session file is the record. Recomputing the
histogram from the file, as above, gives the same numbers, or different
ones if you choose a different cutoff — which is the point of keeping the
raw data.

## CV files

**Name:** `cv_<kind>_<HHMMSS>.h5`, `kind` = `highres` or `lowres`. Written
by `storage.save_cv_cycles`:

| Item | Content |
|---|---|
| `applied_v` | (samples,) the commanded potential in volts, shared by every cycle |
| `keep` | (samples,) bool, False where Igor NaN-ed (switch-on quarter, repeated tail) |
| `tip_current_v` | (cycles, samples) raw preamp volts |
| `we_voltage_mv` | (cycles, samples) measured electrode voltage — highres only |
| attrs | `format_version`, `record_kind = "cv"`, `cv_variant`, `created_*`, `config_json`, `n_cycles`, `rate_hz`, `gate_mv`, `units` |

`gate_mv` is the counter-electrode potential in force when the CV ran.
Read with `storage.CVSession`: `applied_v`, `keep`, `current_a(i)` (raw
volts over the stored gain), `we_voltage_mv(i)`.

## What is not stored

- Rejected traces. Igor did not keep them either. The count per reason is
  in `run_stats_json`; if you need the traces, lower the selection
  thresholds or use a ramp mode, which keeps everything.
- Background reads, approach reads, the Find Suppress sweep and the Find
  Offset points. The last of each lives in the controller
  (`last_suppress`, `vzero_tracker.history`) for the duration of the
  launch, and the offset history is written into every session file's
  summary.
- The History text. Launch with `-v` and redirect the console if you want
  it on disk.

## Size

A constant-bias trace is two channels × 10 000 samples × 8 bytes, 160 kB
raw; gzip on the chunked datasets brings a hundred traces to a few
megabytes. A 5000-trace day is well under a gigabyte. Igor's single-
precision `.ibw` blocks were smaller; the difference is the price of raw
volts on both channels at full resolution.

## Comparing with an archived Igor block

`storage.load_ibw(path)` reads an Igor binary wave; `storage.split_igor_
block(block, n_parameters=20)` separates the twenty-row parameter header
`SavePullOut` stacked above each column from the conductance below it.
Igor stored *conductance*, not raw volts, so the comparison is between
Igor's conductance columns and `Session.conductance(i)` here — same
displacement axis, same bias, same gain. The 1 G0 peak position of the
two histograms is the whole-chain check (chapter 10).

> That comparison has not been done. No `.ibw` file from this rig was
> available when the package was written, and the 1 G0 peak has only been
> reproduced from the simulator. Until an archived block has been read
> and matched, the analysis is self-consistent, not validated.
