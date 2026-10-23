# 18. The data: Igor's saving scheme, written and read by Python

*Igor: `MakePath`, Functions_STMBJ.ipf:206; `SavePullOut`, :469;
`LogHistFromBlocks`, :819 (the `Igor_for_New_DAQ` variant). The analysis
macro that reads them: `DisplayPullOut` :1185, `LoadCond` :1662,
`LoadCurrent` :1860, `LoadVoltage` :1916, `RunHist` :1975, `LoadHist` :2239
in STMBJ_HistogramAnalysis.ipf. Python: `stmlab/igor_scheme.py` (the
scheme), `plot.py` (the pictures), `pullout.py` v65 (the experiment).
The checked specification is `IGOR_SCHEME_SPEC.md` at the top of the
repository.*

Since **pullout v65** the Python experiment saves its traces exactly the way
the lab's Igor code saved them for years: one folder per day, one hundred
traces to a block, one `.ibw` file per block and per kind of signal, with
the same names, the same numbers and the same twenty parameters in the same
order. Two things follow, and they are the point of this chapter:

- **Igor's analysis macro opens a Python day** as if Igor had taken it
  (`LoadCond`, `LoadCurrent`, `LoadVoltage`, `LoadHist` need no change).
- **Python opens an Igor day.** `python plot.py <day folder> 1D` draws the
  histogram of the July 2026 data on the NAS (`07_14_26`, `07_15_26`,
  `07_16_26`; the last holds 300 blocks, 30 000 traces) the same way it
  draws today's, with the same histogram recipe Igor used for its block
  histograms.

Every number below was checked against those July files with the `igor2`
reader, not copied from the Igor source alone.

## The day folder

Igor's `MakePath` built the folder name from the date: `MM_DD` + the setup
id + `YY` + `Merge`. With the default setup id `_`, 22 October 2026 is

```
<data folder>/10_22_26Merge/
```

The setup id is a short tag that told two rigs apart (Igor's `SetupID`);
it is the **Setup ID** box of the Saving tab and `_` unless you change
it. The folders on the NAS were renamed by hand to `07_16_26` (no `Merge`);
Python accepts any folder name and only looks at the files inside.

What else goes into the same folder, beside Igor's files:

| File | What it is |
|---|---|
| `<experiment>_<HHMMSS>_<N>traces.h5` | the raw session: both channels in volts at the ADC, the whole config, per-trace scalars (chapter 47 has the layout). One per Start, named for the experiment, the time of the click and, at the end, the number of traces it holds. Written when "also keep the raw .h5 session" is ticked (default on). |
| `experiment_log.csv` | the day's notebook: one line per Start (date, time, your name, experiment, traces, your notes, the automatic note), then the data file's full path on the next line. One file for the whole day, appended to. |
| `….txt` (named like the `.h5`) | the plain-text table (displacement, then one G/G0 column per trace), only when that box is ticked |

None of these names starts with `PullOut`, so Igor's macro never sees them.
The raw `.h5` is the one file from which everything else can be
recomputed: Igor's blocks hold conductance, not volts, so a gain corrected
later can only be applied to the `.h5`.

## The numbering: Saved, and blocks of 100

Igor numbered traces through the whole day with `G_PullOutNumber`; here it
is called **Saved**, shown in the Status box and in the label under the
Saving tab (`next trace (Saved): N`). It starts at 1 and never resets while
the day lasts; a Stop and a new Start continue where it left off.

Block `k` holds traces `(k-1)*100 + 1` to `k*100`. Inside the block, column
`c` (counted from 0, as the computer does) is trace `(k-1)*100 + c + 1`. To
find a trace by its number: the block is `ceil(N/100)`, the column is
`(N-1) mod 100`.

| Trace | Block `k` | Column `c` |
|---|---|---|
| 1 | 1 | 0 |
| 100 | 1 | 99 |
| 101 | 2 | 0 |
| 250 | 3 | 49 |
| 30 000 | 300 | 99 |

Igor wrote the files of block `k` only at the moment trace `k*100` was
saved; whatever was in memory below a full hundred was lost when Igor
quit. Python keeps the files identical but also writes the **unfinished
block** at the end of every run (Stop, pause, quit, New file), with the
columns not yet taken filled with NaN, and on the next run it **continues
the numbering from the folder**: it looks at the highest block present,
counts its filled columns, sets `Saved = 100*(k-1) + filled + 1`, reads the
partial block back into memory and refills it in place. When that block
reaches its hundredth trace it is rewritten complete, and is then
byte-for-byte what Igor would have written (apart from the wave note, see
below). The label `next trace (Saved)` on the Saving tab is this scan,
refreshed whenever you change the data folder or the setup id.

## The files of one block

All of Igor's block files are Igor binary waves (version 5), the wave
name inside equals the file name without `.ibw` (Igor's macro relies on
this), and the numbers are **single precision** (float32, about seven
significant digits), as Igor's were. `N` is the number of points in a
trace: 10 000 for a 5 nm pull at 20 nm/s sampled at 40 kHz, which is what
the July data has. The companion files all share `k` and the column
layout of the ConductanceBlock, so column 17 means trace `(k-1)*100 + 18`
in every file of the block.

| File (Igor name) | What is inside | Units | Shape and type | Written when |
|---|---|---|---|---|
| `PullOutConductanceBlock_k.ibw` | the conductance of up to 100 traces, one per column: the `N` points of the pull, then two rows of exactly 0, then the 20 parameters (next table) | G/G0 (dimensionless) | `(N+22, 100)` float32, no x scaling | **always** |
| `PullOutVoltageBlock_k.ibw` | the junction voltage as measured, sign-corrected (Igor's `PullOutVoltage`) | V | `(N, 100)` float32, x = 0 … Size nm | **Save Bias** (default on) |
| `PullOutCurrentBlock_k.ibw` | the current through the junction (Igor's `PullOutCurrent`) | A | `(N, 100)` float32, x = 0 … Size nm | **Save Current** (default on) |
| `PullOutExtensionBlock_k.ibw` | the piezo position read back on the sense line (Igor's `POExtension`) | nm | `(N, 100)` float32, x = 0 … Size nm | **Save Sense** (default on), and only when the rig has a sense line |
| `PullOutVoltageLowResBlock_k.ibw` | the junction voltage from the second, low-resolution input of the old two-card rig | V | `(N, 100)` float32, x = 0 … Size nm | never by Python (one card, no low-res input); **read** when present |
| `PullOutPiezoBiasWave_k.ibw` | the piezo ramp that was applied, one per block, the same for every trace: starts at 0 V and goes negative over the pull (Igor's `PiezoBiasWave`) | V | `(N,)` float64, no x scaling | **Save Piezo wave** (default off) |
| `PullOutConductanceBlockHist_k.ibw` | the log-conductance histogram of the block, counts per trace | counts per trace against log10(G/G0) | `(1000,)` float32, x = −8 … 2 | **Save Hist** (default on) |
| `PullOutExtension_<k*100>.ibw` | the **last trace of the block alone**: its piezo readback | nm | `(N,)` float64, x = 0 … Size nm | only when the block completes **and Save Sense is off** |
| `PullOutVoltage_<k*100>.ibw`, `PullOutCurrent_<k*100>.ibw` | the last trace of the block alone: its voltage and current | V, A | `(N,)` float64, x = 0 … Size nm | only when the block completes **and Save Bias is off** |

The last three rows are what Igor's macro loads in its non-merge mode;
they exist so that a day saved with a flag off still has one trace per
block in full. Igor's own defaults were Bias 0, Current 0, Sense 0,
Hist 1, PiezoWave 0; the lab's practice in July 2026 was Bias, Current and
Sense **on**, and those are the Python defaults.

**Unfilled columns** — traces not yet taken in a partial block — are NaN
from top to bottom, in every file (Igor's `Make … = NAN`). A reader skips
them by looking for a column with any finite value.

**The x axis.** The ConductanceBlock has no x scaling (Igor's "dx = 1"), so
the displacement along a pull is not in the file's header; it is
reconstructed from parameter slot 0, the pull length `Size`: point `i` sits
at `Size * i / (N-1)` nm, i.e. `linspace(0, Size, N)` with both ends
included (Igor's `SetScale/I x 0, Size`). The companions carry exactly that
scaling in their header: `dx = Size/(N-1)` = 5/9999 = 0.00050005 nm for the
July data. The point spacing is 0.5 pm; the sample spacing in time is
25 µs.

### One column of the ConductanceBlock

For a trace of `N` points:

| Rows | Content |
|---|---|
| `0 … N-1` | conductance in G/G0: Igor's `PullOutCurrent / PullOutVoltage / K_G0` — current in A over the **measured** junction voltage in V, over G0 = 7.748e-5 S, both signals aligned for the AI/AO delay |
| `N`, `N+1` | exactly 0.0 (Igor's `Redimension` fills new points with 0) |
| `N+2 … N+21` | the 20 `ParameterWave` slots, in order |

So a block of 10 000-point traces is 10 022 rows by 100 columns, and that
is what each of the 300 blocks of `07_16_26` is.

### The 20 parameters (slots `N+2 … N+21`)

Unused slots are 0 (not NaN). The last column gives the value seen in the
July 2026 data.

| Slot | Igor name | What it is | Unit | July 2026 |
|---|---|---|---|---|
| 0 | `Size` | pull length | nm | 5 |
| 1 | `Rate` | pull rate | nm/s | 20 |
| 2 | approach step | the fine-approach step | nm | 0.5 |
| 3 | `PiezoOffset_nm` | the piezo position **after** the pull (Igor read it once the ramp had moved it): the contact position minus the pull length | nm | 247.6 |
| 4 | `BiasSave` | 1 when the Voltage block was written, else 0 | flag | 1 |
| 5 | `StartX − StopX` | the sense readback averaged over the first 1000 points minus the average over the last 1000; the pull length on a rig without a sense line | nm | as Igor computed it |
| 6, 7 | thermocouples | tip and substrate thermocouple averages of the old two-card rig; 0 here | — | 0 |
| 8 | — | unused | — | 0 |
| 9 | `CurrentVoltConversion` | the Keithley's scale, µA per V = 10^(6 − gain exponent) | µA/V | 1 |
| 10 | `TipBias` | the bias set | mV | 600 |
| 11 | — | unused | — | 0 |
| 12 | `SeriesResistance` | the resistor in series with the junction | Ω | 1e5 |
| 13 | `ConductanceThreshold` | the engage threshold | G0 | 5 |
| 14 | — | unused | — | 0 |
| 15 | `Vzero` | the last Find-Offset result (0 if none) | mV | 0 |
| 16 | `Izero` | the last Find-Offset result (0 if none) | — | 0 |
| 17 | `PullOutTime` | when the trace was taken, as Igor's `DateTime`: seconds since 1 Jan 1904 (Unix time + 2 082 844 800). In float32 this is good to about 4 minutes, as in Igor | s | 3.867e9 = 16 Jul 2026, 07:41 |
| 18 | gate voltage | the electrochemical gate (this variant; 0 in the two-card one) | mV | 0 |
| 19 | `CurrentSuppress` | the Keithley suppress current = `suppress_const * 10^(3 − gain exponent)` | µA | −0.00338 |

In Python these are `igor_scheme.PARAM_NAMES`, in the same order, and
`igor_scheme.igor_parameters(...)` fills them from the config and the trace.

### The block histogram file

`PullOutConductanceBlockHist_k.ibw` is Igor's `LogHistWave` from
`LogHistFromBlocks`: 1000 points, x from −8 to 2 (`SetScale/I x -8, 2`, so
`x0 = -8`, `dx = 10/999`). Igor's `Histogram/A` binned by that scaling, so
**bin `i` starts at `−8 + i·10/999`** and is `10/999` ≈ 0.01 decades wide
(the last bin ends just above 2). Per column Igor kept the first 95 % of
the points, box-smoothed over 11 points, took the mean over the 95–96 %
window as the noise floor and, only if that floor was below the
end-of-trace threshold (`G_EndOfTraceNoiseThreshold`, `cfg.ramp.break_g0`),
subtracted it, smoothed again, took log10 and added the trace to the
histogram; after all hundred columns it divided by 100. The result is
**counts per trace**: the 1 G0 peak of clean gold is a few counts per
trace high. Two details of that recipe matter when a histogram is
recomputed: Igor ran the 95 % cut on the **whole block column**, the `N`
points plus the 22 tail rows, so it kept `floor(0.95·(N+22))` points
(9520 of 10 000 for the July data, 21 more than 95 % of the trace alone);
and the floor condition is a **quality gate**, not only an offset
correction — a trace whose floor never came below the threshold is left
out of the histogram altogether. `plot.py`'s 1D histogram follows both
(below); the threshold is not among the 20 parameters, so for Igor data
it is the config's `break_g0` (5e-4 G0 by default), for a `.h5` the
session's own.

The lab's own saved histograms — `Loghist<start>_<stop>_<MM>_<DD>_<YY>.ibw`
in `Swagger/STM Analysis/Saved Histograms`, written by the macro's
`RunHist` — have the same 1000 points and the same x scaling but hold the
**raw sums** over many traces, not counts per trace. `plot.py` reads both.

## Three deliberate differences from Igor

None of them changes a complete block; Igor's `LoadWave` reads a
Python-written day without noticing.

1. **Partial blocks are written and resumed.** Igor lost the traces below
   a full hundred when it quit; Python writes them at the end of every run
   with NaN in the empty columns, and the next run refills the same block
   in place and continues the numbering (above). A partial block looks to
   Igor like a block with some empty traces.
2. **The wave note.** Igor left the ConductanceBlock's note empty. Python
   writes one line into it — `pullout v65; experiment=…; operator=…;
   traces 201-300; written 2026-10-22T14:05:31` — so a file says which
   program, which experiment and whose hands it came from. Igor's macro
   ignores notes.
3. **The histogram of a partial block** is divided by the number of filled
   columns, not by 100, so it stays "counts per trace". Igor never wrote
   a partial block, so there is nothing to be identical to; a complete
   block is divided by 100 exactly as Igor did.

## The two Igor variants

The lab ran two copies of the Igor code. The **top-level** variant
(`STMBJ2/MKLab_STMBJ - Copy`) drove the old two-card rig and **wrote the
July 2026 data**; it also saved `PullOutVoltageLowResBlock_k.ibw` (the
second, coarser voltage input) and reserved slots 6 and 7 for thermocouple
averages (0 in the July data). The **setup-1** variant (`Igor_for_New_DAQ`) is the one ported to
Python: no low-res block, no thermocouples, slot 18 for the gate. The two
layouts are otherwise identical, so every reader here takes both;
`PullOutVoltageLowResBlock_k` is **read-only** in Python — shown by `-N`
when present, never written, because the new rig has one card and no
low-res input.

## Plotting old Igor data with plot.py

`plot.py` takes, in any mixture: a `.h5` session, a `.txt` table, any
`.ibw`, and **a whole day folder**. The `.ibw` files need the `igor2`
package (`pip install igor2`, already in the `.venv`). The commands below
are run from the repository folder (`./.venv/bin/python` on the Mac,
`.venv\Scripts\python` on the lab PC); `NAS` stands for the folder that
holds the day folders (`07_16_26` has 300 blocks). The options
(`--blocks`, `--traces`, `--save`, the knobs) may stand before, between or
after the inputs and the `1D`/`2D`/`-N` word. The same list is at the top
of `plot.py` and `python plot.py -h` prints every knob.

```bash
# the whole day: every PullOutConductanceBlock_k in the folder (300), in order
python plot.py NAS/07_16_26 1D                   # conductance histogram
python plot.py NAS/07_16_26 2D                   # log G against displacement
python plot.py NAS/07_16_26                      # both side by side

# part of a day
python plot.py NAS/07_16_26 1D --blocks 1-5,9    # blocks 1 to 5 and 9 (traces 1-500, 801-900)
python plot.py NAS/07_16_26 --traces 1-500 1D    # traces 1 to 500 by their day number

# one block as a file (traces 601-700)
python plot.py NAS/07_16_26/PullOutConductanceBlock_7.ibw 1D

# one trace, by its day number: trace 250 (block 3, column 49)
python plot.py NAS/07_16_26 -250

# a saved histogram wave, drawn as the curve it is (the macro's RunHist output;
# the lab's Saved Histograms folder holds the 2025 days)
python plot.py "Saved Histograms/Loghist1_1000_07_10_25.ibw" 1D
# ... a block's own Hist file over the histogram recomputed from its block
# (a Python day writes one per block; the July 2026 days have none)
python plot.py data/10_22_26Merge --blocks 1 data/10_22_26Merge/PullOutConductanceBlockHist_1.ibw 1D

# today's Python day and an Igor day in one histogram
python plot.py data/10_22_26Merge NAS/07_16_26 1D

# a PNG instead of a window, in the day folder (or in --out <folder>)
python plot.py NAS/07_16_26 1D --save
```

A whole day is read one block at a time and kept as single precision, as
Igor stored it: `07_16_26` is 1.2 GB of traces in memory and takes a
minute or two to read and histogram. A folder with no blocks, a block
or trace that is not there, or a `2D` of a saved wave alone ends with one
line, `plot.py: <what is wrong>`, and exit code 2, not a traceback.

What the pictures do with Igor's files:

- **The displacement axis** of every Igor trace is `linspace(0, Size, N)`
  from its own column's slot 0, so a day in which the pull length changed
  draws each trace at its true length; `.h5` traces keep the commanded
  axis they were taken with. The 2D histogram's `--align 0.5` (0 nm where
  the conductance first drops below 0.5 G0) works on both alike.
- **The 1D histogram is the block histogram's recipe** (`LogHistFromBlocks`,
  above): per trace the first 95 % of the points — counting the block
  column's 22 tail rows for a trace read from an Igor block, as Igor cut the
  whole column — smoothed over `--smooth` points, the noise floor from the
  95–96 % window, and the trace counts only if that floor is below the
  end-of-trace threshold (`break_g0`), which is then subtracted. The gate
  applies to `.h5` and `.txt` traces too, as it did to everything Igor
  histogrammed; `--no-floor-gate` counts every trace (floor subtracted),
  and the printed note says which (`floor gate 0.0005 G0` or `no floor
  gate`). Igor blocks mixed with `.h5`/`.txt` traces in one histogram are
  cut without the tail rows. **It uses Igor's bins** (bin `i` from
  `−8 + i·10/999`) by default, so a Python histogram of an Igor block lands
  on the same x values as Igor's own `PullOutConductanceBlockHist_k`;
  `--even-bins` restores the earlier evenly spaced bins over −8 … 2. The
  dotted 1, 2, 3, 4 G0 reference lines stay. `--bins`, `--xlim`, `--logy`,
  `--fill`, `--color`, `--lw` are as before.
- **A 1-D wave of 1000 points starting at −8** — a
  `PullOutConductanceBlockHist_k` or a `Loghist*` — is recognised as a
  histogram and drawn as a curve with its own x scaling, not re-binned. Given
  together with traces (a folder, blocks or a `.h5`), it is drawn over the
  recomputed histogram and both 1 G0 peak positions are printed, which is
  the quickest check that Python and Igor agree on a day. With the recipe
  above, the histogram recomputed from a block equals the block's Hist file
  bin for bin (`tests/test_plot.py` checks it on a Python-written day); what
  the picture still shows as different is honest and the note says so: the
  saved wave is drawn at Igor's bin starts, 0.005 decade left of the
  recomputed centres (so the two printed peaks differ by that half bin), and
  a block's Hist is divided by its 100 columns where the recomputed one is
  divided by the traces that passed the floor gate — the same number unless
  a trace of the block was left out.
- **`-N` on a folder or a block** is the trace with the day number `N`
  (not the N-th file in the folder): its conductance against displacement
  with the accept/reject verdict and, when the companion files exist, its
  **voltage in mV, current in nA and extension in nm** under it, beside the
  histogram of its block. On a `.h5` it is the six-panel raw-record view
  as before.
- **`--save`** names the PNG after the folder or file: `07_16_26_1D.png`,
  `07_16_26_2D.png`, `07_16_26_hist.png` (both), `07_16_26_trace0250.png`.
- The program's window has the same loaders: the saved-session browser in
  `pullout.py` accepts a day folder or a `PullOutConductanceBlock_k.ibw` as
  well as a `.h5`, so an old Igor day can be looked at from the window.

## Reading the files in your own script

Everything `plot.py` does starts from `stmlab/igor_scheme.py`:

```python
from stmlab import igor_scheme as ig

day = "NAS/07_16_26"
ig.list_blocks(day)                        # [1, 2, 3, ..., 300]

b = ig.read_block(day, 1)                  # block 1 with its companions
b.g0.shape                                 # (10000, 100): N points x filled traces, G/G0
b.numbers                                  # array([1, 2, ..., 100]) the day numbers
b.params[:, 0], b.params[:, 10]            # pull length (nm), bias (mV) of every trace
b.displacement_nm                          # 0 ... 5 nm, 10000 points
b.voltage_v, b.current_a, b.extension_nm   # (N, traces) when the file exists, else None
b.voltage_lowres_v                         # the July data has it; a Python day has None
b.hist                                     # the block histogram when its file exists

blocks = ig.read_day_folder(day, traces=(1, 500))      # five blocks, traces 1-500
blocks = ig.read_day_folder(day, blocks=[1, 2], companions=True)

x, counts = ig.read_hist_wave("Loghist1_3000_07_16_26.ibw")   # x = bin starts, -8 + i*10/999
```

`read_block` gives only the filled columns; `split_block` underneath is
what tells a ConductanceBlock (22-row tail, two zero rows, positive pull
length and rate) from a companion or a bare wave. `ig.PARAM_NAMES[i]` says
what slot `i` is. For the raw `.h5` beside the blocks, chapter 47's
`storage.Session` is unchanged.

## What pullout.py's Saving tab controls

| Control | Igor global | Default | What it changes |
|---|---|---|---|
| Data folder | `DataDir` | `data/` | the root under which the day folder is made |
| Setup ID | `SetupID` | `_` | the tag in the folder name, `10_22_26Merge` |
| Your name, Experiment, Notes | — | remembered | name and experiment go into the ConductanceBlock's wave note (`operator=…; experiment=…`); all three into the `.h5` header and `experiment_log.csv` |
| Save Bias | `G_BiasSaveCheck` | on | `PullOutVoltageBlock_k` (off: `PullOutVoltage_<k*100>` and `PullOutCurrent_<k*100>` instead) |
| Save Current | `G_CurrentSaveCheck` | on | `PullOutCurrentBlock_k` |
| Save Sense | `G_SenseSaveCheck` | on | `PullOutExtensionBlock_k` when the rig has a sense line (off: `PullOutExtension_<k*100>`) |
| Save Hist | `G_HistSaveCheck` | on | `PullOutConductanceBlockHist_k` |
| Save Piezo wave | `G_PiezoWaveSaveCheck` | off | `PullOutPiezoBiasWave_k` |
| also keep the raw .h5 session (recommended) | — | on | the `<experiment>_<HHMMSS>_<N>traces.h5` beside the blocks |
| .txt table | — | off | the plain-text table |

Under the boxes the label reads `Igor folder: <root>/10_22_26Merge   next
trace (Saved): N`. The settings are remembered between launches in
`data/pullout_saving.json` (including the setup id and the five flags).
`--headless N` saves through the same path; `--no-igor` (bench tests only)
writes the `.h5` but no Igor files. The Status box's **Saved** is the day
counter, not a count since the last Start.

## Opening a Python day in Igor

Point the analysis macro's path at the day folder (its merge mode,
`G_MergeCheck = 1`): `LoadCond(w, i)` loads `PullOutConductanceBlock_<ceil(i/100)>`
and takes trace `i` from it, `LoadCurrent`/`LoadVoltage` do the same from
the Current and Voltage blocks, `LoadHist` the histogram waves. The wave
inside each file is named like the file, as Igor needs. This Igor-side
round trip is checked by hand on the Mac with Igor itself; the Python tests
(`tests/test_igor_scheme.py`) check the files against the July 2026 data and
against the Igor source, not through Igor.

## Fine print

- A block holds traces of one length. If the pull length or the sample
  rate changes mid-day, the partial block is written as it is and the
  numbering jumps to the next block (a warning says so); Igor could not
  put two lengths in one block either.
- The block histogram follows the constant-bias recipe above. Igor's ramp
  modes also deleted their hold/push section before binning; that step is
  not part of the block histogram file.
- Igor limits a wave name to 31 characters, and
  `PullOutConductanceBlockHist_1000` is 32: from block 1000 on (trace
  99 901) the Hist file is skipped with a warning. All other names stay
  legal.
- `PullOutTime` (slot 17) is a float32 and therefore good to about four
  minutes; the `.h5` beside the blocks has every trace's Unix time in
  double precision.
- The earlier Python export (`..._b000.ibw`, pre-v65) put NaN where Igor
  puts the two zero rows; the readers accept both, the writer only writes
  Igor's zeros.
- Rejected traces are not saved, as in Igor.
