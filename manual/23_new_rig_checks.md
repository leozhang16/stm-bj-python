# 23. Checks for a new rig: the sign of the current, two plot boxes, the sample rate

*Python: `stmlab/config.py` (`Calibration.current_sign`, `current_sign_2`,
`sign_of`, `volts_to_amps`, `amps_to_volts`; `SimConfig.amplifier_output_sign`),
`stmlab/analysis.py` (`reads_negative`), `stmlab/plots.py` (`plot_record_series(log=)`,
`plot_trace(linear=)`, `plot_piezo(frame=)`), `stmlab/ratecheck.py` (`measure`,
`save_csv`, `lines`), `stmlab/daq.py` (`DaqSession.last_play_seconds`),
`pullout.py` v69 and v70 (`Worker.cmd_current_sign`, `cmd_ratecheck`, `SIGN_STOP`;
`cycle_frame`; the "flip the sign" boxes, the two plot check boxes, the
Sample-rate check box of the Monitor window).
Tests: `tests/test_v69_rig_checks.py`.*

Three things that were added in v69 while the new rig, with its two-channel
amplifier, was being brought up. Each one stands on its own. v70 changed the
third after its first evening on the real card (the big line is now the rate
as counted, and the last second is kept as a file), and gave plot 1 and
plot 3 one time axis.

## 1. The current comes out negative

### What you see

The tip bias is positive, the junction voltage reads positive, but the
current reads negative. Then nothing works:

- the trace panel (plot 2) is empty, or shows only a band of noise at the bottom;
- every trace is rejected;
- the histogram stays empty.

### Why

Conductance is current divided by voltage. If the two have opposite signs
the conductance is negative. The trace panel draws log10(G), and a negative
number has no logarithm. So there is nothing to draw. The data are fine;
only the sign is wrong.

### Why the old amplifier did not do this

It is about which way round the amplifier's output is.

- Igor's wiring, which this program copies, puts **minus** the tip bias on
  the card's bias output (`cal.bias_output_sign = -1`). So the current that
  flows is, physically, a negative one.
- The Keithley 428 **inverts**: a current going in gives a voltage of the
  opposite sign coming out. Negative current in, positive voltage out.
- Two minus signs make a plus. On the old rig the current always read
  positive, and nobody had to think about it.

On the new rig the current reads negative, so one of the two minus signs
is missing. The likely reason is that the new two-channel amplifier does
**not** invert: the first minus sign is still there, the second is gone.
(The other way to lose one is to have the two leads to the junction the
other way round than on the old rig. The amplifier's data sheet says which
it is: look for "inverting" or "non-inverting" output.)

Either way nothing is broken. The program puts the bias out exactly as it
did before; the same current is just reported with the other sign.

### The cure

In the **Current amplifier** box, tick **flip the sign of ch 1**. From then
on the current of channel 1 is computed as

    current = -(V_out - zero) / gain

instead of `(V_out - zero) / gain`. The next trace is drawn and judged as
usual. Channel 2 has its own box, **flip the sign of ch 2**, because it is
its own output.

The tick lasts until the program is closed. To keep it, put the line in the
`cal` part of the rig's config file (the status line tells you the same):

    "cal": {
        "current_sign": -1,
        "current_sign_2": -1,
        ...

Leave out `current_sign_2` (or make it 1) if channel 2 turns out to be the
right way round.

### What the program does on its own

- A pull whose channel 1 gives a negative conductance where the junction
  conducts starts its status line, in red, with
  `CH 1 CURRENT HAS THE WRONG SIGN (opposite to the bias) ...`.
- **Three such pulls in a row stop the run**: `RUN STOPPED: 3 pulls in a row
  gave a NEGATIVE conductance on ch 1 ...`. No trace could ever be accepted,
  so there is no point crashing the tip again and again. Tick the box, press
  Start N.
- The trace panel says so in red instead of standing empty, and its title
  ends in `[ch 1 NEGATIVE]`.
- Channel 2 alone reading negative is said in orange and stops nothing. It
  is either its sign, or an output stuck at its negative rail.

A negative conductance only says that the current and the junction voltage
have opposite signs. Which of the two is the odd one out, the program reads
off the junction voltage: with its sign right, it has the sign of the bias
you set. If it is the *voltage* that reads against the bias, the status
line says `THE JUNCTION VOLTAGE HAS THE WRONG SIGN ...` instead, and the
cure is not a box: it is `"voltage_input_sign"` in the config's `cal`.
"plot 1: log I and V" shows the same thing: the axis label of the negative
one says `NEGATIVE`.

Contact is not affected by any of this. It is judged on the *size* of the
current, so the approach finds the surface with either sign.

"Where the junction conducts" means: the samples that are at least 0.1 G0
in size, or at least ten times the typical size of the trace, whichever is
the lower bar. In a pull those are the samples in contact
(`analysis.reads_negative`). A pull that never touched is only noise, has
no such samples, and gets no note, also when its zero is a little off and
all of it reads slightly negative. So calibrate the zero as usual, and read
the note as what it is: a statement about a pull that touched.

While browsing saved data the red note appears too, for a file that was
taken with the wrong sign. There it says so, and has no box to offer: a
saved trace is drawn with the settings saved in its own file.

### In the simulator

The simulated amplifier is whichever way round your config says the real
one is: it takes `cal.current_sign` and `cal.current_sign_2` when the
program starts. So `--simulate` reads positive with the old rig's config
and with the new rig's config alike, with or without the `current_sign`
line.

To see what a wrong sign looks like, change a "flip the sign" box during a
simulated session: the red status line, the red note in the trace panel,
the run stopping after three pulls. Change it back and it is fine again.
(`sim.amplifier_output_sign` in the config fixes the simulated amplifier
one way round whatever `cal` says; the tests use it.)

## 2. Two check boxes above the plots

Next to "redraw while moving":

| Box | What it does |
|---|---|
| **plot 1: log I and V** | The record panel (junction voltage and current against time) gets logarithmic y axes. They show the *size* of each signal, \|V\| and \|I\|. A current of a few nA next to one of a few uA is then still a line, not a flat zero. A log axis cannot show a sign, so the axis label says `NEGATIVE` when the signal is negative |
| **plot 2: linear G** | The trace panel shows G/G0 itself instead of log10(G/G0): the conductance as it was computed, against distance, sign and all. There is a line at 0, at 1 G0 and at the break threshold. The y range fits the data (the wildest half per cent left out) and always shows 0 to 1.2 G0 |

Both redraw what is on the screen at once, also while browsing saved data.

Plot 1 (junction voltage and current) and plot 3 (the piezo) both run
against the time of the cycle, and since v70 they share one time axis, so a
feature in one can be found in the other straight below it: 0 to 1.2 s. A
cycle that lasted longer (a long approach) stretches both to its end, so
that the pull, which comes last, is never cut off. Before v70 plot 1 showed
only the pull. To look at the pull alone, type its times into the Axis
limits window.
The Axis limits window still overrides the ranges; clear its numbers for a
panel when you switch that panel between log and linear, because a range
typed for one makes no sense for the other.

## 3. Is the card really taking 40000 samples a second?

Open **Monitor**. Its **Sample-rate check** box has one tick box. While it
is ticked and the rig is idle, this happens again and again, about once a
second:

1. The piezo and the bias are **held where they are** for one second.
   Nothing moves. The inputs record during that second exactly as they do
   during a pull.
2. The numbers the card returned are written to a scratch file. The file is
   read back, the numbers of each input are counted, and the file is deleted.
3. The same second is **kept for you to look at**: `sampling_rate_test.csv`
   in the data folder (the folder of the Saving tab). Every check writes it
   afresh, so it always holds the last one.
4. The time the card took is read off the PC's clock, as a rough cross-check.

The big line is the sample rate **as counted**, and it flashes yellow each
time a new one is in:

    40000 samples/s: 40000 samples in 1 s on each of 4 inputs

Under it, one line per input in use (which card input, what is wired to
it, how many samples), the outputs, the scratch file (how many numbers, how
big, read back identical, deleted), where the kept file is, the PC's
stopwatch, and how long after the outputs finished the inputs were all read.

Green means: every input delivered what was asked for, the scratch file
read back identical and is gone, the stopwatch does not disagree, and the
inputs were not late. Red means one of those failed, and the lines say
which. If the card refuses the check altogether the box says `CHECK FAILED`
with the driver's message and unticks itself, so that it does not ask a
failing card again every second.

### Look at the samples yourself: sampling_rate_test.csv

Untick the box first, so that the file is not being rewritten, then open
`sampling_rate_test.csv` from the data folder in Excel. The Monitor line
"kept for Excel" gives the full path.

| Column | What it is |
|---|---|
| `sample` | 1, 2, 3 ... 40000 |
| `time_s` | the time of that sample: its number, less one, over the card's rate. The first is at 0, the last at 0.999975 |
| one per input | the volts that input read, as the card returned them. The header names the card input and what is wired to it, e.g. `Dev1/ai2 junction voltage (V)` |

One header row and 40000 rows, so Excel's last row number is 40001. The
values are raw volts at the card, before any gain or sign: the current
column is the amplifier's output voltage.

While the file is open in Excel, Windows does not let the program replace
it. The check still runs; the line then says `NOT kept for Excel` and why.

### What each number can tell you

- **The count is the sample rate.** The card's sample clock is a crystal,
  and the driver reports the rate it really runs at (the line "asked for
  40000 per input: 1 s at the card's 40000.000 samples/s"). One second on
  that clock is 40000 samples on every input. A record of a fixed length
  either comes back whole or the driver gives up with a time-out, so the
  count does not quietly come out short: it is right, or the box says
  `CHECK FAILED` and why.
- **The stopwatch is only a rough cross-check.** The PC says "go", waits
  for the card to say "done", and looks at its own clock. Starting and
  stopping a card over USB costs 10 to 20 ms, and a long record costs a few
  ms more than a short one. So the stopwatch cannot tell 40000 from 39700,
  and it is never shown as a rate. What it can catch is a card that is
  grossly off: one that really sampled at 20000 a second would need two
  seconds for 40000 samples, and the big line would turn red and say
  `40000 samples, but they took 2.00 s, not 1 s`.

The stopwatch line reads like this (the numbers are the new rig's):

    PC stopwatch (rough, a cross-check only): 1.0176 s from go to done for 1.0000 s of samples
        the 17.6 ms on top are the PC starting and stopping the card (10.1 ms on the 400-sample record before it)

v69 turned those same numbers into "39698 samples/s" in the big line: it
took the short record's 10.1 ms off the long record's time and called all
the rest sampling time. The card was at 40000 all along; the 7.5 ms were
the long record's extra start-and-stop time. v70 shows the count.

The stopwatch runs while the *outputs* play their second. The inputs start
on the same trigger and should finish at the same moment, so the check
looks at the stopwatch once more when it has all their numbers. A few
milliseconds later is normal. Inputs that sampled slower than the outputs
would keep it waiting, and the line then says `FAR TOO LATE` in a red box.

On the simulated card a play takes no real time. There is a count but no
stopwatch, and the box says so.

While the box is ticked the readouts and the strip charts of the Monitor
window keep updating (from the end of each one-second record), and a button
you press waits a little over one second at most for the check in progress
to finish. The check does not run during a run.
