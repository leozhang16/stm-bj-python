# 22. A two-channel current amplifier

*Python: `stmlab/config.py` (`ChannelMap.ai_current_2`, `current_channels`,
`Calibration.preamp_gain_2_v_per_a`), `stmlab/daq.py`
(`DaqSession.set_current_channels`, `last_current2_v`), `stmlab/trace.py`
(`TraceRecord.current2_v`), `stmlab/igor_scheme.py` (the `ch2` subfolder),
`stmlab/plots.py`, `plot.py`, `pullout.py` v66 (the Current amplifier box),
v67 (the junction-open test on channel 2: `Rig.is_open`,
`Rig.open_side_of`, `TraceRecord.open_side_g0`, `analysis.open_side`; the
simulated card's noise, `sim.ai_noise_v_rms`), v68 (the box in the
Keithley box's place), v69 (the sign of each channel: chapter 23) and v75
(channel 2 only as far as it measured: `TraceRecord.railed2`,
`conductance_g0(..., as_measured=)`, `analysis.blank_railed`,
`igor_scheme.read_block_channel2`, `blank_filled_in`).
Tests: `tests/test_two_channel.py`, `tests/test_v75_channel2_sliders.py`.
Config: `configs/newrig_2ch.json`.*

## What it is

Some current amplifiers have two outputs for the same input current: one
with a lower gain, for the high conductances, and one with a higher gain,
for the low ones. No single output covers a break-junction trace. The
lower-gain output follows the junction from several G0 down to its own
noise floor. The higher-gain output carries on below that floor, by as
many decades as its gain is higher.

Where the two floors lie is set by the gains and by the card. The card
adds the same noise to every input (NI lists 88 uV rms for the USB-6453 on
its +/-10 V range), and an output's floor is that noise divided by its
gain: at 100 mV about 1e-3 G0 for 1e4 V/A, 1e-5 G0 for 1e6 V/A and 1e-6 G0
for 1e7 V/A.

Whether the higher-gain output rails while the junction is closed depends
on the gain, on the series resistor and on the bias. Through 106 kohm at
100 mV the current never exceeds 0.94 uA, so a 1e7 V/A output reaches
8.4 V at 1 G0 and stays in range through contact: both channels then show
the gold steps, and the 1 G0 peaks of the two histograms lie on top of
each other. That peak on channel 2 is real. At 300 mV the same output
would have to give 25 V at 1 G0: it is at its rail from contact down to
about 0.06 G0 and has nothing to say above that. A 1e9 V/A output is at
its rail for as long as the junction is closed and comes into range once
the conductance has fallen by three decades.

The highest conductance channel 2 can read is the current that puts its
output at the rail, over the junction voltage the series resistor leaves
at that current:

| Bias | 1e7 V/A, 100 kohm: channel 2 reads up to | The 1 G0 plateau on channel 2 |
|---|---|---|
| 100 mV | about 2.5 G0 (0.95 uA with 5 mV left across the junction) | in range (8.9 V): real |
| 200 mV | about 0.12 G0 | saturated |
| 300 mV | about 0.06 G0 | saturated |

`pullout.py` reads both and keeps them apart:

| | Config | What it is | What the program does with it |
|---|---|---|---|
| **Channel 1** | `channels.ai_current`, `cal.preamp_gain_v_per_a`, `cal.current_zero_v` | the **lower-gain** output, which follows the junction through contact (1 G0 and above) | judges **contact** on it: the engage threshold, the start of a trace, its gold plateau. Exactly what a one-output amplifier does |
| **Channel 2** | `channels.ai_current_2`, `cal.preamp_gain_2_v_per_a`, `cal.current_zero_2_v` | the **higher-gain** output | judges **the junction open** on it: the break threshold, in the approach's separate step and at the end of every trace. Reads it during every play, saves it with every trace, draws it beside channel 1 |

Why the open side is channel 2's (since v67): the break threshold, 5e-4 G0
at 100 mV, is a current of 3.9 nA. On a 1e4 V/A output that is 39 uV:
below the card's noise, and no more than a little offset drift or mains
pickup on that input. Read there, the junction does not reliably count as
open. In the simulation 60 uV of drift on channel 1 is enough for the
separate step to run the piezo to its floor and for every trace to be
refused for its end. On a 1e7 V/A output the same current is 39 mV. Where channel 2 is
at its rail the current is beyond it, and the test reads channel 1
instead, which is good exactly there.

**Channel 2 is shown only as far as it measured (v75).** Where its output
is saturated (its raw volts at or beyond `limits.preamp_saturation_v`) it
has no value: no red line in the trace panel, no counts in the histogram.
Every picture shows channel 1 in blue, whole, and channel 2 in red from
where it comes off its rail. Nothing is scaled to make the two meet.

Why: a saturated output is not a measurement, and the number it gives is
not harmless. The conductance is the current divided by the junction
voltage, and while the current is stuck at rail / gain the junction
voltage still follows the junction through the series resistor. So the
"conductance" of a saturated channel 2 is not a flat line: it has a step
wherever the gold has one, at the wrong height. At 300 mV, 1e7 V/A and
100 kohm (an output that stops at 10 V) the 1 G0 plateau came out at
0.38 G0, the 2 G0 plateau at 0.71 and the 3 G0 plateau at 1.04, each with
its own peak in the histogram, the last one right where a real 1 G0 peak
would be. Up to v74 that stretch was drawn and counted, and on the rig it
read as "the high-gain channel shows G0 peaks too". The program never
built one trace out of the two for the screen, and still does not.

The files for Igor and MATLAB are the one place where the two channels are
put together: see "What is saved".

**Which output goes where matters.** Channel 1 must be the output that can
see contact, channel 2 the one with the higher gain. If the two inputs are
swapped, contact is judged on an output that may be railed whenever the
junction is closed (it would still stop at contact, because a railed
channel 1 counts as contact, but every conductance above the rail would be
wrong), and the junction open on the output that cannot see it. The
validator catches the common case: it refuses a channel-1 gain at which
1 G0 would clip, and it warns when channel 2's gain is not above
channel 1's.

## The config

Two keys in `channels` and two in `cal`. A config without them is a
one-channel rig, as every config was before v66.

```json
"channels": {
    "ai_voltage": "ai1",
    "ai_current": "ai2",
    "ai_current_2": "ai4",
    "current_channels": 2,
    "ai_piezo_sense": "ai3",
    "sense_device": "Dev1",
    "ai_terminal": "rse",
    "sense_terminal": "rse"
},
"cal": {
    "preamp_gain_v_per_a": 10000.0,
    "current_zero_v": 0.0,
    "preamp_gain_2_v_per_a": 10000000.0,
    "current_zero_2_v": 0.0
},
"sim": {
    "ai_noise_v_rms": 8.8e-05
}
```

`ai_current_2` is the card input channel 2 is wired to. `current_channels`
is how many of the two are read: 1 reads channel 1 alone, even when
`ai_current_2` is named, and the rig then behaves as a one-channel rig in
every respect; 2 reads both. `configs/newrig_2ch.json` is a complete
config of this kind for the one-card USB-6453 rig (screws instead of an
actuator, the piezo driver in standard mode). Its input for channel 2, its
two gains (1e4 and 1e7 V/A) and its nm/V are placeholders: put the rig's
own numbers in.

`sim.ai_noise_v_rms` is read by the simulation only (`--simulate`): the
noise of the simulated card's inputs, in volts rms. With the card's own
number in it a simulated run shows the two noise floors where the rig will
have them. Without the key the simulation keeps its old built-in noise of
a couple of microvolts, which puts every floor decades too low.

Channel 2 is wired like channel 1 and is read in the same wiring mode
(`ai_terminal`) and range (`ai_range_v`). With only the BNC centre in the
AI+ terminal, that mode is `rse`.

The record's task reads its inputs in this order: junction voltage,
channel 1, channel 2, the piezo sense line (`ChannelMap.record_inputs`).
The USB-6453 samples its inputs simultaneously (NI lists it with 16
simultaneous converters), so on that card the order makes no difference.
It is chosen for a card that shares one converter between its inputs:
there the input scanned right after a railed one is the most exposed to
what the multiplexer carries over, channel 2 is railed whenever the
junction is closed, and the input after it is then the sense line (a few
volts from a low-impedance monitor output) rather than the junction
voltage (a few millivolts behind the series resistor).

The `ai4` of the shipped config is a placeholder for whichever input
channel 2 is wired to. If the card does not accept the input you name,
bring-up step 1 says so, and so does the window when you select two
channels.

## In the window

The **Current amplifier** box holds the two gains and the switch between
one channel and two.

Where it is depends on the rig. With a config that names channel 2's input
(`channels.ai_current_2`) it stands in the left column, between Status and
Coarse approach, where the Keithley 428 box is on the other rigs: it is in
view as soon as the window opens, and the Keithley box is not shown,
because an amplifier with two outputs is not the 428. (Since v68. Before,
the box was in the Settings tab, which on a laptop screen lies below the
bottom edge of the window until the column is scrolled.) With a
one-channel config it is the first box of the Settings tab, and the
Keithley box is where it always was.

| Control | What it does |
|---|---|
| one channel / two channels | switches live between reading channel 1 alone and reading both. The card's input task is rebuilt, as for the Input mode; the piezo and the bias stay where they are. Refused while the tip is in contact, and greyed out when the config names no `ai_current_2`. To keep the choice for the next launch, put `"current_channels": 2` in the config, as the status line says |
| Gain ch 1 (V/A), Gain ch 2 (V/A) | what the amplifier is set to, typed in: `1e4`, `1e7`, `5e7`. They tell the arithmetic and program nothing, so set the amplifier itself first. They are settings like the others: checked against the safety rules as you type, applied on Enter or Apply, and an accepted change closes the open file so that every file carries one gain. To keep them, put them in the config's `cal` |
| flip the sign of ch 1, flip the sign of ch 2 (v69) | for an amplifier whose output is the other way round from the Keithley's: the current reads negative at a positive bias, the conductance is negative, and the trace panel stays empty. Ticked, that channel's current is `-(V - zero) / gain`. Arithmetic only: nothing on the rig changes. Refused while a command is running. To keep it, put `"current_sign": -1` (channel 2: `"current_sign_2": -1`) in the config's `cal`. Chapter 23 has the whole story |

Channel 1's gain is the same number the Keithley box shows as an exponent.
Setting either one moves the other, as long as the gain is a whole decade.
A config that names `ai_current_2` describes an amplifier that is not the
Keithley 428, and the validator makes no remark about `keithley.gain_exponent`
on it.

With a config that names channel 2, the window has two more readouts. The
Status box gets a line `ch 2`: channel 2's output in volts, as a current in
nA and as a conductance. While it is at its rail the line is `ch 2
+10.0000 V  RAILED: its output is saturated, no reading`: the volts, and no
current or conductance made of them (v75). The Piezo box gets a cell
**I ch 2 (nA)**, which says RAILED in red for as long. With a gain high
enough to rail, RAILED is channel 2's normal state whenever the junction
is closed: the junction-open test reads channel 1 for as long as it lasts,
and channel 2 is not drawn or counted there.

**The volts in that line are worth one look on a new amplifier.** In solid
contact, at a bias that saturates channel 2, they are where its output
stops. If the line shows a steady voltage there and does NOT say RAILED,
the output stops below `limits.preamp_saturation_v`: see "Things to know".

After a move made by hand (the slider, the step buttons) the status line
gives channel 1's conductance and, when channel 2 is the one that judged
it, channel 2's in brackets: `G = 8.612e-04 G0 (ch 2: 2.105e-06 G0), open`.

**Calibrate zero** takes both zeros from the same hold at 0 V bias. If
channel 2 reads its rail during that hold, the junction is closed (a
contact passes the amplifier's own offset current even with no bias), and
the old zero is kept with a message: open the junction and calibrate again.

## What is drawn

The **trace panel** shows both channels against the same displacement, on
one axis: channel 1 in blue, channel 2 in red and slightly see-through, so
the blue still shows where the two lie on top of each other. The y axis
runs a decade further down than with one channel (to -8.5), because
channel 2's floor lies lower. The verdict in the title reads the start of
the trace and its gold plateau from channel 1 and its end from channel 2.

Read from left to right, a trace looks like this. While the junction is
closed, channel 1 shows the contact and its steps down to 1 G0. A channel
2 that stays in range (1e7 V/A behind the series resistor at 100 mV) shows
the same steps, the red on top of the blue. A channel 2 that rails has no
line there (v75): its red line begins where its output comes off the rail.
From there the two lines run together down the tunnelling decay until
channel 1 reaches its noise floor. Channel 2 carries on below it, through
any molecular plateau that lies under channel 1's floor.

The **histogram** shows two curves on the same bins, each made from its own
channel's traces by the one recipe (Igor's: the first 95 % of the trace,
smoothed over 11 points, the floor subtracted) and divided by its own
trace count. So it has **two noise floors**: channel 1's where its gain
runs out, and channel 2's further down. Where both channels are in range
the curves lie on top of each other: the gold peaks of both, when channel
2 stays in range through contact. A channel 2 that rails has no counts
above the highest conductance it can read (v75): its curve simply ends
there, and the gold peaks are channel 1's alone. The x axis starts at -8.

Where the files and `plot.py` apply Igor's floor gate (a trace whose floor
is not below the break threshold is left out of the histogram), the gate
is read on channel 2's floor for both curves. A trace is then in both or
in neither, and an offset on channel 1 cannot take it out. The floor each
curve subtracts stays its own channel's.

The record panel, the Monitor window and the 2D histogram show channel 1,
except that the 2D histogram can be asked for channel 2 (below).

## What is saved

| Where | Channel 1 | Channel 2 |
|---|---|---|
| the raw `.h5` session | `current_v`, raw volts | `current2_v`, raw volts, with both gains and both zeros in `config_json`. `Session.conductance(i, channel=2)` computes its conductance, so a gain corrected later reprocesses the file |
| the Igor day folder | `PullOutConductanceBlock_k.ibw` and its companions, exactly as on a one-channel rig | the same file names in the subfolder `ch2`: the ConductanceBlock, the CurrentBlock and the Hist (chapter 18). Same blocks, same columns, same trace numbers |
| the `.txt` table, when ticked | `<run>.txt` | `<run>_ch2.txt`, the same layout, the same traces in the same columns |
| `experiment_log.csv` | the automatic note names both gains and both zeros | |

A run taken with one channel writes none of the channel-2 items, and its
files are those of a one-channel rig.

**Where channel 2 was saturated, the `ch2` ConductanceBlock and the
`_ch2.txt` table hold channel 1's conductance (v75).** These two files are
for Igor's analysis and for MATLAB, and those need the contact part of a
trace: Igor's panel counts a trace only when its first 2 % average above
1.02 G0, and puts 0 nm where the trace falls through 0.5 G0. A column that
is blank through contact would give them nothing at all, and one with the
saturated numbers in it (as up to v74) gave them peaks at the wrong
places. So in these files a trace is channel 2 wherever channel 2
measured, and channel 1 above that: one whole trace, with channel 2's low
noise floor at the bottom and the real gold steps at the top. The note of
the block and the header of the table say so. Three things follow:

- Opened in Igor's panel, the `ch2` folder shows the 1 G0 peak. It is
  channel 1's reading, at the right place.
- Opened in this program as channel 2 (the window's browser, `plot.py` on
  the day folder), those points are blank again, as on the live screen:
  a point of the `ch2` block that is the same number, bit for bit, as the
  same point of the day folder's own block was put there from channel 1.
  The `ch2` subfolder opened by itself is read as it is: the whole trace.
- The CurrentBlock in `ch2` stays channel 2's own current, saturated where
  it was. The raw volts of both channels are in the `.h5`, whatever the
  other files hold.

Day folders written before v75 hold the saturated numbers themselves, and
nothing in them says where. The `.h5` of the same run does: `plot.py` on
the `.h5` draws channel 2 correctly.

## Plotting it afterwards

`plot.py` recognises two-channel data by itself, from a `.h5` or from a day
folder with a `ch2` subfolder.

```
python plot.py <session>.h5 1D              both channels on one plot, blue and red
python plot.py data/11_14_26Merge 1D        the same from the day folder
python plot.py <session>.h5 -3              trace 3, both channels
python plot.py <session>.h5 1D --channel 1  channel 1 alone (or 2)
python plot.py <session>.h5 2D              the 2D histogram of channel 1
python plot.py <session>.h5 2D --channel 2  the 2D histogram of channel 2
python plot.py data/11_14_26Merge/ch2 1D    the ch2 subfolder read as a day folder
```

The 2D histogram is one channel at a time, because a colour map cannot
carry two. For channel 2 each trace's 0 nm is still taken from channel 1
(where channel 1 drops below 0.5 G0): channel 2 is railed while the gold
contact breaks and cannot say where that was. The histogram windows of the
Saving tab have a `channel` box for the same choices. In all of them
channel 2 is drawn and counted only where its output was not saturated
(v75).

## Bringing it up

1. Simulate first. `python pullout.py --config configs/newrig_2ch.json
   --simulate` runs the whole window on a simulated two-channel amplifier:
   press Calibrate zero, type a name and an experiment, Start N. The
   simulated card has the noise `sim.ai_noise_v_rms` says (88 uV in the
   shipped config), and channel 2 the thermal noise of its feedback
   resistor on top, so changing a gain moves that channel's floor as it
   would on the bench. Calibrate zero prints each channel's noise in the
   terminal, in volts and in G0: that is where its floor will be.
2. On the rig, with nothing but the card connected,
   `python -m stmlab.main bringup 1 --config configs/newrig_2ch.json`
   checks that every input the config names exists, channel 2's included.
3. `python rigcheck.py` reads any input live. Put a known current through
   the amplifier and check each output against its gain before trusting the
   numbers in the config. For a sweep instead of one current, use its
   **Ramp an output** box (v71): pick the output the bias is on, type the
   start and the end voltage and how many volts a second, press Ramp.
   Through a known resistor that is a current ramp. Tick the amplifier's
   inputs and press Start first: the scope and the table then follow each
   amplifier output as the ramp runs. The second plot, under the scope,
   shows the command: the outputs' volts against time, the whole ramp
   drawn thin, the part played so far thick, and a dot at now (it is what
   the card was told, not a measurement). The output stays at the end voltage
   when the ramp is done; "Hold here" stops it on the way; "and back to the
   start" returns it. Start the window with `--config` and the rig's json:
   it then knows which output is the piezo and refuses anything outside
   the piezo's range on it. Below 0 V needs "allow negative volts" ticked.
4. Take one pull. If the status line starts with `CH 1 CURRENT IS NEGATIVE`
   and the trace panel says so in red, the amplifier's output is the other
   way round from the Keithley's: tick "flip the sign of ch 1" in the
   Current amplifier box (chapter 23). The Monitor window's Sample-rate
   check (same chapter) shows which inputs are read and how fast.
5. In `pullout.py`, with the junction open, press Calibrate zero and read
   the `ch 2` line: a few millivolts at most, not RAILED. Bring the tip into
   contact: channel 1 shows the contact current, and channel 2 the same
   current through its own gain, a thousand times channel 1's volts for
   gains a factor of 1000 apart, or RAILED when that is more than its
   output can give. That is the picture of a correctly wired pair. Channel
   1 the larger of the two means the inputs are swapped: swap `ai_current`
   and `ai_current_2` in the config.

## Things to know

The break threshold is judged on channel 2 while both are read, and on
channel 1 while one is (the one channel / two channels switch moves it).
Calibrate zero matters for it as it did for channel 1: an offset on
channel 2 that is not taken out is read as a current, and one of more
than 3.9 nA (39 mV at 1e7 V/A) would keep the junction from ever counting
as open.

RAILED is judged at `limits.preamp_saturation_v`, 9.5 V in the shipped
configs, on both channels. If the amplifier's outputs stop short of that
(an output stage that swings to 5 V, say), lower the limit in the config
to just under where they stop. Otherwise channel 2 is never seen as
railed: Calibrate zero cannot tell a closed junction from an offset, with
a very high gain (1e9 V/A and up) a channel 2 stuck at its own rail could
read as an open junction, and (v75) its saturated stretch is drawn and
counted again, with its false steps and peaks. How to see where an output
stops: bring the tip into solid contact at a bias that saturates channel
2 (300 mV at 1e7 V/A) and read the volts in the Status box's `ch 2` line.

An amplifier takes a moment to come back from saturation. The first
samples after channel 2 leaves its rail can still be wrong, and they are
drawn: nothing here knows how long this amplifier needs. If channel 2
shows a bump just under the highest conductance it can read, that is the
place to look.

Contact is judged on channel 1 the same whether channel 2 is read or not.

The single-cycle experiments in `experiments/`, the older `gui.py` window
and `rigtests/` read channel 1 only.
