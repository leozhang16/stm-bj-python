# 23. Checks for a new rig: the sign of the current, two plot boxes, the sample rate

*Python: `stmlab/config.py` (`Calibration.current_sign`, `current_sign_2`,
`sign_of`, `volts_to_amps`, `amps_to_volts`; `SimConfig.amplifier_output_sign`),
`stmlab/analysis.py` (`reads_negative`), `stmlab/plots.py` (`plot_record_series(log=)`,
`plot_trace(linear=)`), `stmlab/ratecheck.py`, `stmlab/daq.py`
(`DaqSession.last_play_seconds`), `pullout.py` v69 (`Worker.cmd_current_sign`,
`cmd_ratecheck`, `SIGN_STOP`; the "flip the sign" boxes, the two plot check
boxes, the Sample-rate check box of the Monitor window).
Tests: `tests/test_v69_rig_checks.py`.*

Three things that were added in v69 while the new rig, with its two-channel
amplifier, was being brought up. Each one stands on its own.

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
3. The time the card took is read off the PC's clock.

The big line shows what was measured and flashes yellow each time a new
one is in: the count that came back, and the rate by the PC's clock.

    40000 samples x 4 inputs: 39998 samples/s

(On the simulated card, which has no clock: `40000 samples x 4 inputs in 1 s`.)

Under it, one line per input in use (which card input, what is wired to
it, how many samples), the outputs, the scratch file (how many numbers, how
big, read back identical, deleted), the rate by the PC's clock next to the
rate the card itself reports, and how long after the outputs finished the
inputs were all read.

Green means: every input delivered what was asked for, the file read back
identical and is gone, the PC's rate agrees with the card's within 2 %, and
the inputs were not late. Red means one of those failed, and the lines say
which. If the card refuses the check altogether the box says `CHECK FAILED`
with the driver's message and unticks itself, so that it does not ask a
failing card again every second.

### What each number can tell you

- **The count** shows which inputs are being read and that each delivered a
  full second. A record of a fixed length either comes back whole or the
  driver gives up with a time-out, so the count does not quietly come out
  short: it is right, or the box says `CHECK FAILED` and why.
- **The time** is the independent part. The card has its own clock and the
  PC has another. A card that really sampled at 20000 a second would need
  two seconds for 40000 samples, and the box would show 20000 samples/s in red.

Starting and stopping the card costs a few milliseconds, and those are not
sampling time. So a 10 ms hold is played just before the long one, and the
rate is the *extra* samples of the long hold divided by the *extra* time it
took. The start-and-stop time is in both and drops out.

The stopwatch runs while the *outputs* play their second. The inputs start
on the same trigger and should finish at the same moment, so the check
looks at the stopwatch once more when it has all their numbers. A few
milliseconds later is normal. Inputs that sampled slower than the outputs
would keep it waiting, and the line then says `FAR TOO LATE` in a red box.

How close to 40000 the PC's number comes on the real card has not been
tried yet: the tests run on a simulated card and on a fake driver. A PC's
timing is good to a few milliseconds, so a few tens of samples/s either way
would be the PC, not the card. Only red (more than 2 % off) is a finding.

On the simulated card a play takes no real time. There is a count but no
time, and the box says so.

While the box is ticked the readouts and the strip charts of the Monitor
window keep updating (from the end of each one-second record), and a button
you press waits at most one second for the check in progress to finish.
The check does not run during a run.
