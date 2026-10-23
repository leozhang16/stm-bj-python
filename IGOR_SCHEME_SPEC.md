# Spec: make the Python saving scheme and plot.py identical to Igor's

Goal (the user's words): "change my python plot.py and saving scheme to be the same as
the Igor saving scheme, so that I can use python to plot the old data as well."

Ground truth, in order of authority:
1. The real data on the NAS written by the lab's Igor code in July 2026:
   `/Users/ly666/Library/CloudStorage/SynologyDrive-SynNAS/Masha_Research/Summer_2026/Experiment/Raw_data/07_16_26/`
   (also `07_14_26`, `07_15_26`), 100-trace blocks `PullOutConductanceBlock_1..300.ibw` (30 000 traces) with companions.
2. The Igor source: `SavePullOut`, `LogHistFromBlocks`, `MakePath` in
   `/Users/ly666/STM_Igor/Igor_for_New_DAQ/Functions_STMBJ.ipf` (setup-1 variant, the one ported for
   the new rig) and `/Users/ly666/STM_Igor/STMBJ2/MKLab_STMBJ - Copy/Functions_STMBJ.ipf` (top-level
   variant, which wrote the July data; identical layout plus one more block kind).
3. The consumer: the lab's analysis macro `/Users/ly666/STM_Igor/Igor_for_New_DAQ/STMBJ_HistogramAnalysis.ipf`
   (`LoadCond`, `LoadCurrent`, `LoadVoltage`, `LoadHist`, `DisplayPullOut`), which must be able to read
   what Python writes.

Everything below was verified against (1) with igor2 unless marked "from source".

## 1. The day folder and the trace numbering

- Igor: `MakePath` makes `DataDir + PathDate + "Merge:"` with `PathDate = MM + "_" + DD + SetupID + YY`.
  With the default `SetupID = "_"` and 22 Oct 2026 that is **`10_22_26Merge`**. `DD` is the two
  characters before the comma of Igor's `Date()`, which not every system zero-pads, so a folder can
  read `05_ 2_05Merge`; `parse_day_folder_name` accepts a space-padded or single-digit day, while
  Python always writes `MM_DD`. The NAS copies were renamed by hand to `07_16_26`; the reader must
  accept any folder.
- Traces are numbered across the whole day: `Saved` (Igor's `G_PullOutNumber`) starts at 1 and never
  resets while the experiment is open. Block `k` holds traces `(k-1)*100+1 .. k*100`, column `c`
  (0-based) holds trace `(k-1)*100 + c + 1`.
- Igor writes a block only when trace `k*100` is saved; an unfinished block is lost when Igor quits.
  Python improves on this without changing the format: it writes the block when it completes **and**
  at the end of every run (Stop, pause, quit) with the unfilled columns NaN, and on the next run it
  **continues the numbering** from the folder: `Saved = 100*(k_last-1) + filled(k_last) + 1`, refilling
  the partial block in place. A complete block is then byte-for-byte what Igor would have written
  (apart from the wave note, see 2).
- Python extras (the raw `.h5` session, `experiment_log.csv`, optional `.txt` table) go **into the same
  day folder**. Their names never start with `PullOut`, so the Igor macro ignores them.

## 2. `PullOutConductanceBlock_k.ibw` (always written)

Verified on the July data: wave name = file stem; **float32**; shape `(N + 22, 100)`; **no x scaling**
(dx = 1, x0 = 0); empty note; version-5 IBW.

Column layout (rows), for a trace of `N` points (10000 for 5 nm at 20 nm/s, 40 kHz):

| rows | content |
|---|---|
| `0 .. N-1` | conductance in G/G0 (Igor: `PullOutCurrent/PullOutVoltage/K_G0`, current in A, measured junction voltage in V, both aligned by `DelayOffset`) |
| `N`, `N+1` | **exactly 0.0** (Igor's `Redimension` fills new points with 0; the Python code's NaN here was wrong) |
| `N+2 .. N+21` | the 20 `ParameterWave` slots, see below |

Unfilled columns (traces not yet taken) are NaN throughout (Igor's `Make ... =NAN`).

ParameterWave (float32; unused slots are **0**, not NaN; values seen in the July data in brackets):

| slot | Igor | Python source |
|---|---|---|
| 0 | `Size` nm, pull length [5] | `cfg.ramp.pull_length_nm` |
| 1 | `Rate` nm/s [20] | `cfg.ramp.pull_rate_nm_per_s` |
| 2 | approach step nm [0.5] | `cfg.ramp.approach_step_nm` |
| 3 | `PiezoOffset_nm` **after** the pull (Igor reads it after GenerateTrace moved it by the ramp) [247.6] | `cal.piezo_volts_to_nm(start_piezo_v) - pull_length_nm` |
| 4 | BiasSave flag [1] | 1 if the Voltage block is written, else 0 |
| 5 | `StartX - StopX`: sense readback (nm) at the start minus at the end of the record [1015 / 4.5] | from `piezo_sense_v` when the rig has a sense line: `mean(sense_nm[0:1000]) - mean(sense_nm[-1000:])` (Igor averaged 1000 points at each end); else `pull_length_nm` |
| 6, 7 | thermocouple averages (top-level variant), 0 in setup-1 | 0 |
| 8 | 0 | 0 |
| 9 | `CurrentVoltConversion` uA per V = `10^(6 - gain)` [1] | `10 ** (6 - cfg.keithley.gain_exponent)` |
| 10 | `TipBias` mV [600] | `cfg.ramp.bias_v * 1e3` |
| 11 | 0 | 0 |
| 12 | `SeriesResistance` ohm [1e5] | `cfg.keithley.series_resistance_ohm` |
| 13 | `ConductanceThreshold` G0 [5] | `cfg.ramp.engage_g0` |
| 14 | 0 | 0 |
| 15 | `Vzero` mV [0] | the last Find-Offset result in mV, else 0 |
| 16 | `Izero` [0] | the last Find-Offset result, else 0 |
| 17 | `PullOutTime`: Igor DateTime, **local-time** seconds since 1904-01-01 (float32: ~256 s resolution, as in Igor). Verified on the July data: the IBW header's `modDate` is `mtime + 2082844800 - 14400`, 14400 s = EDT; the same clock is in slot 17 | `igor_datetime(timestamp)` = `timestamp + 2082844800 + localtime(timestamp).tm_gmtoff`; `unix_from_igor_datetime` inverts it |
| 18 | gate voltage mV (setup-1 variant; 0 in the top-level one) | `cfg.echem.gate_mv` |
| 19 | `CurrentSuppress` uA = `CurrentSuppressConst * 10^(3 - gain)` [-0.00338] | `cfg.keithley.suppress_const * 10 ** (3 - cfg.keithley.gain_exponent)` |

Wave note: Igor leaves it empty. Python writes a one-line note (`pullout v65; experiment=...;
operator=...; traces a-b; written <iso time>`); Igor's `LoadWave` ignores notes, so the macro is
unaffected and provenance is kept. This is the only intentional difference.

## 3. Companion blocks (same `k`, same columns, written per the save flags)

All verified on the July data: **float32**, shape `(N, 100)`, `SetScale/I x 0, Size` i.e.
**dx = Size/(N-1), x0 = 0**, empty note, NaN in unfilled columns.

| file | flag (Igor global) | Python default | content |
|---|---|---|---|
| `PullOutVoltageBlock_k.ibw` | `G_BiasSaveCheck` | **on** | `PullOutVoltage`: measured junction voltage in **V**, sign-corrected (`cal.voltage_input_sign * voltage_v`) |
| `PullOutCurrentBlock_k.ibw` | `G_CurrentSaveCheck` | **on** | `PullOutCurrent`: current in **A** (`cal.volts_to_amps(current_v)`) |
| `PullOutExtensionBlock_k.ibw` | `G_SenseSaveCheck` | **on** when the rig has a sense line, else the file is not written | `POExtension`: piezo readback in **nm** (`cal.sense_volts_to_nm(piezo_sense_v)`) |
| `PullOutVoltageLowResBlock_k.ibw` | `G_VoltLowResSaveCheck` (top-level variant only) | never written (one card, no low-res voltage) | read-only support |
| `PullOutPiezoBiasWave_k.ibw` | `G_PiezoWaveSaveCheck` | off | the applied piezo ramp in **V**, 1-D float64, N points: Igor's `PiezoBiasWave` (starts at 0, goes negative over the pull); Python: `-disp_nm / cal.piezo_nm_per_volt` |

Igor's defaults were Bias 0, Current 0, Sense 0, Hist 1, PiezoWave 0; the user's July practice was
Bias, Current and Sense **on**, hence the Python defaults above.

## 4. `PullOutConductanceBlockHist_k.ibw` (flag `G_HistSaveCheck`, default on)

From source (`LogHistFromBlocks`), no July file exists (that flag was off):
**float32**, 1-D, 1000 points, `SetScale/I x -8, 2` i.e. **x0 = -8, dx = 10/999**. Igor's
`Histogram/A` bins by the destination wave's scaling: bin `i` is `[-8 + i*10/999, -8 + (i+1)*10/999)`,
so the edges are `-8 + arange(1001) * 10/999` (the last bin ends at 2 + 10/999). Per column:

1. `Redimension/N=(0.95*N)` (keep the first 95 %; floor)
2. for the ramp modes delete the hold/push section (`StartDelete`, `NumberToDelete`), as
   `analysis.log_histogram` already does through its `segments`; constant mode deletes nothing
3. `Smooth/B 11`
4. floor = mean over points `[0.95*n, 0.96*n]` of the trimmed wave
5. if floor < `ZeroCutoff` (`G_EndOfTraceNoiseThreshold`, `cfg.ramp.break_g0`): subtract the floor,
   `Smooth/B 11` again, `log10`, accumulate
6. after all 100 columns: `LogHistWave /= 100` -> counts per trace

Python: `analysis.log_histogram(..., igor_bins=True)` must reproduce exactly this binning (add the
parameter; default stays as it is for other callers). For a **complete** block divide by 100 exactly as
Igor does; for a partial block divide by the number of filled columns (Igor never wrote a partial
block, so there is nothing to be identical to, and "counts per trace" stays true).

The lab's own saved histograms (`Loghist<start>_<stop>_<MM>_<DD>_<YY>.ibw` in
`Swagger/STM Analysis/Saved Histograms`) are also 1000-point float32 waves with x0 = -8, dx = 10/999,
but hold raw **sums** over many traces (the analysis macro's `RunHist`). plot.py reads both.

## 5. Per-trace files at the end of a block (from source)

When a block completes, Igor also writes, for the **last trace of the block only** (trace `k*100`):

- if `SenseSave == 0`: `PullOutExtension_<k*100>.ibw` (float64, N points, `SetScale/I x 0, Size`)
- if `BiasSave == 0`: `PullOutVoltage_<k*100>.ibw` and `PullOutCurrent_<k*100>.ibw` (float64, same scaling)

Python writes the same when those flags are off. (These are what the macro's non-merge mode loads.)

## 6. API to implement (stmlab/igor_scheme.py, new module)

```python
BLOCK = 100
PARAM_SLOTS = 20

def day_folder_name(when: float | None = None, setup_id: str = "_") -> str   # "10_22_26Merge"
def parse_day_folder_name(name: str) -> tuple[int, int, int, str] | None       # (yy, mm, dd, setup_id) or None, accepts "07_16_26" too

@dataclass
class SaveFlags: bias: bool = True; current: bool = True; sense: bool = True; hist: bool = True; piezo_wave: bool = False

@dataclass
class IgorTrace:            # one accepted trace, everything SavePullOut needs
    g0: np.ndarray          # conductance, N points
    voltage_v: np.ndarray   # measured junction voltage, sign-corrected, V
    current_a: np.ndarray   # A
    extension_nm: np.ndarray | None   # sense readback in nm, or None
    piezo_wave_v: np.ndarray | None   # applied piezo ramp, V, or None
    params: np.ndarray      # the 20 slots (float)
    @classmethod
    def from_record(cls, tr: trace.TraceRecord, cfg: RigConfig, *, vzero_mv=0.0, izero=0.0, bias_save=True) -> "IgorTrace"

def igor_parameters(cfg, start_piezo_v, timestamp, *, extension_nm=None, vzero_mv=0.0, izero=0.0, bias_save=True) -> np.ndarray

class IgorDayWriter:
    def __init__(self, root: Path, cfg: RigConfig, *, setup_id="_", flags: SaveFlags = SaveFlags(), when=None, note_fields: dict | None = None)
    folder: Path                       # root / day_folder_name(when, setup_id), created on first write
    saved: int                         # Igor's PullOutNumber: the number the NEXT trace gets (resumed from the folder)
    def append(self, t: IgorTrace) -> int        # stores the trace, writes the block files when the block completes; returns the trace number
    def flush(self) -> list[Path]                # writes the current partial block (all kinds) now; returns files written
    def close(self) -> list[Path]                # flush
    @staticmethod
    def scan(folder: Path) -> tuple[int, int]    # (k_last, filled) from the files present; (0, 0) for an empty/missing folder

def write_block_files(folder, k, traces: list[IgorTrace | None], cfg, flags, note="") -> list[Path]   # traces has <= 100 entries, None = unfilled
def block_histogram(g0_columns, cfg, n_divide: int) -> np.ndarray     # the 1000-point LogHistWave, Igor bins

# Reading (Igor's own files, the top-level variant's, this module's, and the legacy *_b000 export):
@dataclass
class IgorBlock:
    k: int; folder: Path
    g0: np.ndarray                 # (N, n_cols) only the FILLED columns
    params: np.ndarray             # (n_cols, 20)
    numbers: np.ndarray            # trace numbers (k-1)*100 + c + 1 of the filled columns
    voltage_v / current_a / extension_nm / voltage_lowres_v: np.ndarray | None   # (N, n_cols) when the companion file exists
    hist: np.ndarray | None        # the 1000-point block histogram when its file exists
    @property displacement_nm -> np.ndarray     # linspace(0, params[0,0], N) (SetScale/I semantics)
def read_block(folder, k, companions=True) -> IgorBlock
def list_blocks(folder) -> list[int]                       # natural-sorted k values present
def read_day_folder(folder, blocks=None, traces=None, companions=False) -> list[IgorBlock]   # blocks: iterable of k; traces: (first, last) trace numbers
def split_block(block_2d: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]   # (g0 (N, cols), params (cols, 20), filled mask); detects the 22-row tail by: rows>22, rows N..N+1 both 0 (Igor) or both NaN (legacy export) in every finite column, params[0] > 0 and params[1] > 0
def read_hist_wave(path) -> tuple[np.ndarray, np.ndarray]  # (x centres or bin starts as Igor scales them, values) for PullOutConductanceBlockHist_k and Loghist*.ibw
```

`storage.load_igor_block` keeps working but delegates its tail detection to `igor_scheme.split_block`
(it currently requires NaN blanks and therefore misreads every real Igor file). `storage.write_ibw` is
reused as is. `storage.save_igor_block` stays for the old tests but is marked legacy in its docstring.

## 7. pullout.py integration (version v65)

- The Saving tab becomes the Igor scheme: Data folder (root), **Setup ID** (default `_`), Your name,
  Experiment, Notes; checkboxes **Save Bias, Save Current, Save Sense, Save Hist, Save Piezo wave**
  (defaults from section 3/4) plus "also keep the raw .h5 session (recommended)" (default on) and the
  existing .txt option. The label under them shows `Igor folder: <root>/10_22_26Merge   next trace
  (Saved): N`, where N is `IgorDayWriter.saved` (scanned from the folder, refreshed when the folder
  or setup id changes).
- The Worker owns one `IgorDayWriter` per (root, setup id, day). Every accepted trace goes through
  `IgorTrace.from_record` and `append`; the writer flushes at run end, pause, Stop, `cmd_newfile`, quit.
  The Status box's "Saved" shows the day counter, not a per-launch count.
- `vzero_mv`/`izero` come from the worker's last Find-Offset result (it already keeps them).
- The raw `.h5` session (SessionWriter) and `experiment_log.csv` are unchanged except that they are
  written **into the day folder** (`folder / f"{experiment}_{HHMMSS}_{N}traces.h5"`, log at
  `folder / experiment_log.csv`). The `.txt` option too. The old `<root>/<YYYY-MM-DD>/<name>/` layout
  and the `_bNNN.ibw` export go away; `--no-igor` becomes "do not write the Igor files" (kept for
  bench tests). Remembered settings (`data/pullout_saving.json`) gain `setup_id` and the five flags.
- Headless mode (`--headless N`) uses the same path.
- The saved-session browser accepts a day folder or a `PullOutConductanceBlock_k.ibw` as well as `.h5`
  (through plot.py's loaders), so old Igor data can be looked at from the window.
- `__version__ = "v65"`.

## 8. plot.py

- Inputs: `.h5`, `.txt`, any `.ibw`, **a day folder** (all its ConductanceBlocks, natural order), and
  `--blocks 1-5,9` / `--traces 1-500` to pick a subset of a folder. Mixed inputs still merge.
- Each Igor trace gets its own displacement axis `linspace(0, Size, N)` from its column's slot 0
  (SetScale/I semantics; endpoint inclusive); `.h5` traces keep the commanded axis.
- 1D histogram: Igor's bins (`igor_bins=True`) are the default in plot.py; `--even-bins` restores
  the old behaviour. The 1 G0 reference lines stay.
- A 1-D 1000-point `.ibw` with x0 = -8 (a `PullOutConductanceBlockHist_k` or a `Loghist*`) is drawn as a
  histogram curve, with its own scaling, optionally over the recomputed one; print both peaks.
- `-N` on a folder or block shows trace N (the day number) with, when the companions exist, its
  voltage (mV), current (nA) and extension (nm) under the conductance, beside the block histogram.
- `--save` naming: `<folder or file stem>_1D.png` etc. as now.

## 9. Tests

- `tests/test_igor_scheme.py`: folder name for a fixed time and setup id; `parse_day_folder_name`;
  block layout (shape, dtype, the two zero rows, 20 params with 0 in unused slots, NaN columns, no
  scaling, wave name = stem); companions' shape/dtype/dx; hist wave (1000 pts, x0 -8, dx 10/999, /100
  on a complete block); per-trace files when flags are off; resume (`scan`, `saved`, refilling a
  partial block); `read_day_folder` round trip (traces, numbers, params); `split_block` on the legacy
  NaN-blank export; a bare 1-D wave is not mistaken for a block; `read_hist_wave`.
- Real-data test, skipped unless the NAS folder exists: block 1 of `07_16_26` reads as 100 x 10000,
  slot 0 = 5, slot 1 = 20, slot 10 = 600; companions read with matching shapes; `plot.load([folder,
  "--blocks", "1-2"])`-equivalent gives 200 traces.
- `tests/test_plot.py`: extend for folders, `--blocks/--traces`, Igor bins default, hist-wave input,
  `-N` with companions; keep the existing tests passing.
- pullout: whatever `tests/` already exercises for the worker (`grep -l pullout tests/*.py`) must keep
  passing; add a headless-simulate run that writes a day folder and checks the files and the resume.
- An Igor round trip on the Mac is run by the orchestrator afterwards (Igor's own `LoadCond` on a
  Python-written folder); not part of pytest.

## 10. Documentation

- `manual/18_igor_data_scheme.md` (new): the scheme as above in user language, how to read old data
  with plot.py (`python plot.py <folder> 1D`, `--blocks`, `--traces`, `-N`), the note about the two Igor
  variants, the three deliberate differences (partial blocks written, resume, wave note).
- `manual/47_gui_data_files.md`: a pointer at the top (pullout.py writes the Igor scheme; this chapter
  describes the older stmgui window's HDF5/CSV layout).
- `README.md`: "The data" paragraph updated; version note.
