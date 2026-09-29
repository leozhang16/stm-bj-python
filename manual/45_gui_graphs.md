# 45. The graph windows and the History window

*Igor: the Graph macros in Windows_STMBJ.ipf:33-131, 407-434 and 475-489; the history area. Modules: `stmgui/graphs.py`, `stmgui/panels/history.py`.*

Igor's experiment showed its data in nine small graph windows, each a
macro that displayed one or two waves with fixed axes, and printed its
commentary into the history area. All ten are here. Each graph is a
matplotlib figure in its own Tk window (`GraphWindow`), created the first
time it is needed, hidden rather than destroyed when closed, and listed
under the **Windows** menu. Every figure in this chapter was produced by
the window itself, on the simulator, by `manual_build/make_figures.py`.

## How the windows get their data

The controller posts events; `GraphSet.on_event` routes them. The table is
`GraphSet.FEEDS`:

| Event | Windows fed | Fired by |
|---|---|---|
| `highres` | HighRes | every background read |
| `trace` | PullOutLowG, PullOutGvsE, AuAuConductanceLevel, SenseInDisplay | every generated trace, saved or not |
| `hist` | LogHistOfBlock | every 100 saved traces, and the partial block at the end of a run |
| `izero` | Izero | Find Offset, and each periodic re-measure |
| `izero_time` | Izero_Time | the same |
| `cv` | CyclicVoltammogram | each CV run |

The first time an event reaches a window that does not yet exist, the
window is created and — for the first-listed window of each event, and
always for Izero, LogHistOfBlock and CyclicVoltammogram — shown. That is
Igor's `DoWindow/F name; if (V_flag==0) Execute "name()"` idiom, which
opened a graph on first use and thereafter just brought it forward. The
three secondary trace windows (PullOutGvsE, AuAuConductanceLevel,
SenseInDisplay) are created and kept up to date but not raised, to keep
the first run from covering the screen; open them from the Windows menu.

Updates happen on the Tk thread, at most every 50 ms, from the event pump
(chapter 48). A run on the simulator generates traces faster than that,
so the pull-out windows show every trace but not every one is rendered
before the next arrives; on hardware, at one trace per second or so, every
one is.

## HighRes

**Igor:** `HighRes()`, Windows_STMBJ.ipf:33 — `VoltageIn` (blue) and
`VoltageInLowRes` (orange) against the left axis in mV, `CurrentInLowRes`
(pink) and `CurrentIn` (green) against the right axis in µA; the last
background read from both cards.

**Now:** the last background read from the one card: junction voltage in
mV (`voltage_input_sign × V × 1000`) on the left axis in Igor's blue, tip
current in µA (`volts_to_amps(I) × 10⁶`) on the right axis in Igor's
green, against sample number. **Fast Read Wave Size** sets the length.
Axes autoscale to the data with a 10 % margin and never use matplotlib's
offset notation, so 100.02 mV reads as 100.02, not +0.02 over 1e2. There
is no low-res pair because there is no low-res card.

!FIG[figures/gui/HighRes.png]{HighRes on the simulator, in contact after Start Approach: 200 samples of junction voltage around −100 mV (the bias is applied as −TipBias, so the measured, sign-corrected voltage is −100 mV) and a current of about 10 µA. Retracted, the current trace is noise around zero.}

## PullOutGvsE, PullOutLowG, AuAuConductanceLevel

Three views of the same wave. Igor's `PullOutConductance` was the
conductance of the last generated trace in units of G0 against
displacement in nm; `GenerateTrace` filled it before `TestTrace` judged the
trace, so rejected traces were shown too. The same here: every `trace`
event carries `g0` (from `TraceRecord.conductance_g0`, i.e. the measured
current over the measured voltage), `disp_nm` (the commanded piezo
retraction from the contact point, `piezo_volts_to_nm(start − piezo)`),
`bias_mv` (the measured junction voltage), `piezo_nm` (the absolute
commanded position), the trace number, the mode, and whether it was saved.
Each window prints `trace N saved (constant)` or `trace N rejected` in its
corner.

| Window | Igor macro | Axis | Igor range |
|---|---|---|---|
| PullOutGvsE | `PullOutGvsE()`, line 52 | linear G0 | from 0 upward, autoscaled |
| PullOutLowG | `PullOutLow()`, line 66 | log G0 | 1e-6 to 5.58676 |
| AuAuConductanceLevel | `AuAuConductanceLevel()`, line 86 | linear G0 | 1e-5 to 5 |

**PullOutLowG** is the one you watch. The log axis spans the whole trace
from metallic contact through the molecular plateau to tunnelling; the
odd upper limit is Igor's own `SetAxis left 1e-06,5.58676`. Igor also
appended `PullOutVoltage` — the measured bias in mV — on a right axis and
hid it (`hideTrace(PullOutVoltage)=1`); the same trace is here, hidden,
with a **show PullOutVoltage** checkbox under the plot to reveal it.
Igor's window was titled "PullOutLowG"; so is this one.

**PullOutGvsE** is the linear view of the plateau region, y from 0 to a
little above the trace's maximum (Igor: `SetAxis left 0,*`).

**AuAuConductanceLevel** is Igor's third view, linear from 1e-5 to 5 — in
practice the 1 G0 gold plateau at the left edge of the trace, which is
what the name says.

!FIG[figures/gui/PullOutLowG.png]{PullOutLowG on the simulator: the last saved trace of a 100-trace run. Metallic contact at the left, the gold plateau at 1 G0, then the exponential tunnelling descent to the noise floor; this particular trace caught no molecule, and one that does shows a second plateau three to four decades down. The measured-bias trace on the right axis is hidden, as in Igor.}

!FIG[figures/gui/PullOutGvsE.png]{PullOutGvsE, the same trace on a linear axis from 0.}

!FIG[figures/gui/AuAuConductanceLevel.png]{AuAuConductanceLevel, the same trace between 1e-5 and 5 G0.}

For the four ramp modes the displacement axis is still the commanded
piezo position relative to contact, which for a push-pull cycle goes
negative and comes back, and for a hold stays flat while the bias does
the work. `TraceRecord.displacement_nm`, which assumes a constant pull
rate, is *not* used for these windows for exactly that reason; the ramp's
own waveform is.

## SenseInDisplay

**Igor:** `SenseInDisplay()`, line 100 — `SenseIn`, the piezo position in
nm read back from the low-res card's sense input, against points.

**Now:** the *commanded* piezo position in nm for the last trace, against
sample number. This rig has one card and no sense line; the number shown
is the same tracked command every safety check trusts. A straight
descending line is a constant pull; a push-pull cycle shows its
excursions; a hold shows a flat section. If you ever add a sense input,
`Rig.play` returns the record and this window is where the readback
belongs.

!FIG[figures/gui/SenseInDisplay.png]{SenseInDisplay for a constant pull: the commanded piezo descending at 20 nm/s from the contact point, 10 000 points at 40 kHz for a 5 nm excursion.}

## LogHistOfBlock

**Igor:** `LogHistOfBlock()`, line 113 — `LogHistWave` as bars (`mode=7`,
`hbFill=5`, blue), "Counts/Trace" against "Conductance [Log]", axes
−6 … 1 and 0 … 40. `LogHistFromBlocks` (Functions_STMBJ.ipf:785) built
it from each 100-trace `ConductanceBlock` as it was saved: keep 95 % of
each trace, smooth, estimate the floor from the 95-96 % window, drop the
trace if the floor is above the zero cutoff, subtract, smooth, log10,
histogram into 1000 bins from −8 to 2, divide by 100.

**Now:** `analysis.log_histogram` on the block, called by the controller
when the block reaches 100 saved traces (`HIST_BLOCK`) and again for
whatever is left when a run ends (that second call is a GUI addition; Igor
showed nothing until a block was complete). The zero cutoff is
`cfg.ramp.break_g0`, Igor's `G_EndOfTraceNoiseThreshold`. For the ramp
modes the hold or push-pull section is removed first — Igor's
`Deletepoints StartDelete, NumberToDelete` — using the ramp's segment
table: everything between the end of the initial pull and the start of
the final pull. The bars are Igor's blue; x is fixed at −6 … 1; y starts
at 0 … 40 and grows if a peak exceeds it. The corner text says how many
traces the block holds and whether it is partial. With **Save Hist**
ticked, each block is also written as a CSV (chapter 47).

!FIG[figures/gui/LogHistOfBlock.png]{LogHistOfBlock after the first 100 saved traces on the simulator: the 1 G0 gold peak at log G = 0, the simulator's molecular peak around −3.5, and the tunnelling background.}

The histogram is the measurement. One trace proves nothing; a peak that
recurs across a hundred does. Chapter 10 says why the floor estimate and
the cutoff gate matter, and what a missing gold peak means (usually the
gain).

## Izero and Izero_Time

**Igor:** `Izero()`, line 407 — `CurrentWave` against `TipBiasRamp` as
markers (pink) with `fit_CurrentWave` (blue), "Current (µA)" against "Tip
Applied Bias (mV)", a zero line, and a `TextBox` with `G_Vzero` and
`G_Izero`. `Izero_Time()`, line 421 — `IzeroWave` against
`PullOutNumberWave` as connected markers (green), "I0 (µA × 1e-3)"
against "Saved Trace Number".

**Now:** `Izero` draws each `VzeroResult` from Find Offset or a periodic
re-measure — points at `(bias_mv, current_a × 10⁶)`, a `numpy.polyfit`
line through them, and the V0 / I0 box. `Izero_Time` draws the
controller's `izero_history`, one `(Saved, I0)` pair per measurement, in
µA × 10⁻³ as Igor's `prescaleExp(left)=3` had it. Chapter 43 shows both
figures and explains what to read in them.

## CyclicVoltammogram

**Igor:** `CyclicVoltammogram()`, line 475 — `TipCurrent` against
`CVAppliedRamp`, "Current (µA)" against "Applied Voltage (mV)", x reversed
(`SetAxis/A/R bottom`), a "CV cycle N" text box.

**Now:** every cycle of the last CV, current `tip_current_v /
cal.preamp_gain_v_per_a` in µA against applied potential in mV, masked
samples left out, earlier cycles in a lighter blue and the last cycle in
Igor's blue, x reversed, the cycle number in the corner. Chapter 44 has
the figure.

## The History window

Igor printed to its history area — every `Print`, every command echo —
and that record was the run's log. The **History** window is that: a
scrolling text with one line per log record from the `stmlab` and
`stmgui` loggers at INFO and above, routed there by
`controller.QueueLogHandler` as `log` events, plus every `error` event.
Each line is stamped with the wall-clock time, then the level letter and
the logger name, then the message:

```
15:28:30  -> Start Measurement: stmgui/controller.py:722 RigController._measure_impl
15:28:30  I stmlab.storage: writing to .../constant_152830_from1.h5
15:28:30  W stmgui.controller: config: hv_amp_gain is unknown; ...
15:28:31  ERROR Start Measurement: the output task is not running -- press Start Writing first
```

The `->` line is written by the worker as each command starts: the button
name, then the file, line and function of the Python that is about to run
— so the History is also the answer to "which function did that button
call". `W` lines are amber, `E` and `ERROR` lines red. The buffer keeps
the last 5000 lines. Everything the chapters of this manual quote as "in the
History" is a line here; if you want it on disk too, launch with `-v` and
redirect the console, or read the session file's `run_stats_json`
(chapter 47), which keeps the counts.

## Placement and size

Igor positioned each window with its `Display /W=(left, top, right,
bottom)`; `GraphSet.ORDER` keeps those origins, scaled to today's screens,
and each window's `igor_geometry` is a size in the same spirit — HighRes
small, LogHistOfBlock large. Drag them where you like; positions are not
remembered between launches, as Igor's were in the experiment file. The
figures resize with their windows.
