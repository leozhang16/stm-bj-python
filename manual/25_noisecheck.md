# 25. noisecheck: at which frequencies does the tip shake?

*Python: `noisecheck.py` v74 (`NoiseWorker`: `cmd_begin`, `cmd_scope`,
`cmd_edge`, `cmd_record`; `best_current`, `with_gap`, `analyse`, `report`,
`save_spectrum`, `load_spectrum`; `SimShake`), `stmlab/noise.py`
(`amplitude_spectrum`, `find_peaks`, `guess_mains`, `describe`, `thin`).
Tests: `tests/test_noisecheck.py`.*

A separate program with its own window. It answers one question about a rig:
when the tip shakes against the sample, at which frequencies?

The tunnelling current is the most sensitive vibration meter on the rig.
With the tip a fraction of a nanometre off the surface, the current changes
by about a factor of ten for every tenth of a nanometre of gap. So the
program makes contact, retracts a little until there is a tunnelling
current, holds the piezo still, records the current, and takes its Fourier
transform. A line in the spectrum is a frequency at which the gap moves, or
at which the amplifier picks something up. A second record with the tip far
away tells the two apart.

It uses pullout's own moves (the same worker, the same limits, the same
signs of contact), so nothing here moves the piezo in a way pullout would
not.

**New in v74, and so far run on the simulated card only.** Try it on the
MacBook first (section 9).

## 1. Starting it

Close pullout, rigcheck and Igor first: only one program can have the card.

    python noisecheck.py --simulate --config configs/newrig_2ch.json
    python noisecheck.py --config configs/<the lab config>.json

The first is the MacBook, the second the lab PC. `--zoom 1.2` makes the
window a fifth bigger, `--out <folder>` says where Save puts its files
(default: `data/noisecheck`).

When it starts it measures the amplifier's zero, as Calibrate zero does. If
the junction is closed at that moment it does not, and says so: step apart
(or turn the screw back) and press **Calibrate zero**.

If the card is still held by another program it says `could not open the
card ... Is pullout, rigcheck or Igor still open?` in the terminal and ends.

## 2. The window

On the left, top to bottom:

| Box | What is in it |
|---|---|
| **Status** | what the program is doing, or what it wants next |
| **Junction** | a light, **OPEN**, **TUNNELLING** or **CONTACT**; the current, G, where the piezo is, the bias |
| **Piezo driver** | standard or bypass and the total displacement, exactly as in pullout's Piezo box (chapter 24, sections 1 to 3). Every distance here hangs on it |
| **1. Get to the edge of contact** | **Approach**, **Find the edge**, **Step apart** and **Step closer** with their Z (nm), **Calibrate zero**, **Stop** |
| **2. Record** | which signal, for how many seconds, **Record**; a name and **Save**; the live picture's tick box; **Keep as reference**, **Load a reference...**, **Clear** |

On the right:

- **the top plot**: the signal against time. While nothing else is going on
  it is live, a quarter of a second at a time. After Record it shows the
  whole record.
- **the bottom plot**: the spectrum of the last record, on logarithmic axes
  from 0.25 Hz to 5 kHz, with its biggest lines labelled in Hz. The
  reference is drawn behind it in grey.
- **The biggest lines**: the same lines as a list (section 5).

The light goes by the conductance: CONTACT above 0.5 G0, OPEN below the
config's break threshold (0.0005 G0), TUNNELLING in between.

## 3. A measurement, step by step

1. **The driver.** Check the Piezo driver box says what the box on the bench
   is set to (standard, 10.776 um on the new rig). Press Set if you change
   it.
2. **A reference, with the tip far away.** The light says OPEN. Press
   **Record**, wait, then **Keep as reference**. This is what the amplifier
   and the cables pick up by themselves, with no current flowing.
3. **Approach.** Bring the surface within the piezo's reach with the screw,
   as for pullout (chapter 24, section 5), and press **Approach**. It ends
   with `CONTACT at ... Now Find the edge`, or with `NO CONTACT for the
   whole range`: then turn the screw a little more and press it again.
4. **Find the edge.** The piezo retracts in small steps until the junction
   lets go, and stops where there is a tunnelling current (section 6). The
   light should now say **TUNNELLING**. If it says OPEN, press **Step
   closer** once or twice (0.3 nm each).
5. **Record.** 16 seconds, and do not touch the rig or the table while it
   runs. The top plot shows each piece as it comes in.
6. **Read the list** (section 5). The lines that are NOT marked `also` and
   not called `mains` are the gap moving.
7. Type a **name** ("plate on 4 bungees") and press **Save**, if you want
   to compare it with something later (section 8).

To see the same record as another signal, pick it in the **signal** box:
nothing is recorded again. A record holds all the signals.

## 4. The signals

| In the box | What it is |
|---|---|
| `current ch 1 (nA)` | the junction current from the amplifier's output 1 |
| `current ch 2 (nA)` | the same from output 2, the high-gain one (two-channel rigs only) |
| `gap (pm)` | the current read as a distance: a tenth of a nanometre for every factor of ten |
| `junction voltage (mV)` | the voltage across the junction |
| `piezo sense (nm)` | the stage's own position sensor (rigs with a sense line) |

**On the new rig the tunnelling current is on channel 2**, and the window
starts with channel 2 selected. At 0.1 V a tunnelling current is a few
nanoamps to a few hundred. Through channel 1 (10^4 V/A) that is tens of
microvolts to a few millivolts, most of it down in the card's noise and the
amplifier's drift. Through channel 2 (10^7 V/A) it is tens of millivolts to
volts. The light and the gap are read
from channel 2 as well, for as long as it is below its rail, and from
channel 1 above that. This is the rule pullout's junction-open test follows
(chapter 22).

## 5. Reading the list

After a record at the edge of contact, with a reference taken far away, the
simulator gives:

    current ch 2 (nA): 4 pieces of 4 s averaged, lines 0.25 Hz apart
    the junction was open 0%, tunnelling 100%, closed 0% of the time; mean 52.86 nA
           Hz          nA  of mean       gap  in ref   what it may be
         7.50       22.45      42%     20 pm           bounce on the suspension, the floor
        15.00       2.281     4.3%   <0.1 pm           2 x 7.50 Hz
        60.00           1     1.9%              also   mains
        22.50      0.1348     0.3%   <0.1 pm           3 x 7.50 Hz

The second line is the first thing to look at. The sizes only mean something
if the junction was in **tunnelling** for nearly all of the record.

| Column | Meaning |
|---|---|
| `Hz` | the frequency of the line, read between the points of the spectrum (to a few hundredths of a hertz for a strong line) |
| `nA` | its amplitude: a sine of that frequency going up and down by that much |
| `of mean` | the same as a share of the mean current. 42% means the current swings by nearly half of itself |
| `gap` | about how far the gap moves at that frequency, in picometres (1000 pm = 1 nm). Only given when the junction was in tunnelling for at least 80% of the record |
| `in ref` | `also` means the reference has this line too |
| `what it may be` | a guess from the frequency alone, for where to look first |

How to read it:

- **`also` in the `in ref` column**: the line is there with no current
  flowing. The gap cannot shake a current that is not there, so this one is
  electrical: pickup in the amplifier or the cables.
- **`mains`, `mains x 2`, ...**: 60 Hz and its multiples (50 Hz where the
  mains is 50; the program sees which). Electrical, almost always.
- **`2 x 7.50 Hz`, `3 x 7.50 Hz`**: multiples of a bigger line in the list.
  They are not separate vibrations. The current is not a straight line in
  the gap, so a gap that moves at one frequency gives the current its
  multiples as well. Their `gap` reads `<0.1 pm`: the gap does not move at
  those frequencies.
- **Anything else, not marked `also`**: the gap moving at that frequency.
  That is the vibration.

The words in the last column come from the frequency only:

| Frequency | The usual suspects |
|---|---|
| under 2 Hz | the whole rig swinging on its suspension like a pendulum; or drift |
| 2 to 20 Hz | the rig bouncing on its suspension; the building's floor |
| 20 to 200 Hz | machines (pumps, fans, a fridge); a part of the rig ringing |
| over 200 Hz | sound; a stiff part ringing |

Two rules of thumb for a hung rig. A mass on a spring or a bungee bounces
at about 5 Hz divided by the square root of how far its weight stretched the
bungee, in centimetres: 1 cm of stretch is 5 Hz, 4 cm is 2.5 Hz, 25 cm is
1 Hz. A pendulum of length L swings at about 5 Hz divided by the square root
of L in centimetres too: 25 cm is 1 Hz. A suspension only helps above its
own bounce frequency, and makes things worse right at it. So a line that
moves when you change the bungees is the bounce.

Under the table the program may add one line of its own:

| It says | Meaning |
|---|---|
| `OPEN nearly all the time: this is the amplifier alone (a good reference)` | no current flowed. Right for the reference, wrong for the measurement: go closer |
| `CLOSED nearly all the time: a contact does not show the gap` | the tip was in contact. Find the edge, or Step apart |
| `In and out of tunnelling: the frequencies are right, the sizes are not` | the junction kept opening or closing during the record (section 7) |
| `Channel 2 was at its rail ...% of the time` | the current was too big for channel 2 for part of the record. Look at channel 1 |
| `no line stands out of the noise` | no line is five times above the noise around it |

## 6. Find the edge

"Make contact, then retract a little."

From contact, the piezo goes apart in steps of 0.1 nm, looking at the
junction after each, until the conductance is at or below 0.1 G0 in six
looks in a row. Much above that two gold surfaces tend to jump back
together, and six looks make sure that a tip which is shaking a little is
clear of the contact over its whole swing.

A gold contact often lets go all at once: the neck breaks and the gap is at
once wider than a tunnelling current reaches. So if the junction is then
open, the piezo comes back toward the surface, in the same 0.1 nm steps,
until there is a tunnelling current (0.005 G0 or more). It never comes back
further than where the contact was.

| It ends with | The status line | What to do |
|---|---|---|
| a tunnelling current | `at the edge of contact: retracted 5.2 nm to 0.2782 V = 299.8 nm, G = 7.55e-03 G0 (tunnelling). Now Record` | Record |
| open on one step, closed on the next | `no place in between here: ... (open), and one step closer it is closed. Record as it is, or try Step closer` | see below |
| no current even where the contact was | `open again where the contact was: ... The tip has changed: press Approach again` | Approach again |
| closed in some looks, open in others | `opens and closes by itself at 0.2787 V: closed in 3 of 6 looks (G 9.7e-05 to 1.0e+01 G0). The tip shakes by more than the tunnelling range. Record as it is: the frequencies will be right` | Record (section 7) |
| still closed after 30 nm | `still closed: retracted 30.0 nm to ... Press Find the edge again, or Step apart by hand` | press it again |
| the bottom of the piezo's range | `still closed with the piezo at the bottom of its range: ... Turn the screw back a little, then Approach again` | the screw |
| **Stop** | `Find the edge stopped by Stop: ...` | |

Before it moves anything, and again when it has ended, it looks at the
junction six times in a row. It retracts when the junction is closed in at
least one of the six and open in none. With a tunnelling current in all six
it says `already at the edge of contact ... Now Record`, with the junction
open it says to press Approach first, and in both cases it moves nothing.

**Closed in some looks and open in others** is the sign of a tip that is
being shaken open and shut: it moves by more than the few tenths of a
nanometre a tunnelling current reaches. No step of the piezo mends that, so
Find the edge stops there and says so. Record there. The list will say
`In and out of tunnelling`, and its lines are still at the frequencies of
the shaking.

**The card's own step.** In standard mode one step of the card's output is
0.33 nm at the piezo (chapter 24, section 1), three times the 0.1 nm asked
for. So two steps out of three move nothing, and the third moves 0.33 nm,
which can be the whole tunnelling range in one go. That is the `no place in
between` ending. In bypass mode the card's step is 0.022 nm and this does
not happen, but the piezo then only reaches 718 nm.

## 7. What it can and cannot tell you

- **The frequencies are right even when the sizes are not.** If the tip
  shakes by more than the tunnelling range (a few tenths of a nanometre),
  the junction opens and closes with every swing, and Find the edge says
  `opens and closes by itself`. The current is then a chopped wave, not a
  small ripple. Its lines are still at the vibration's frequency and its
  multiples, so the list still says where to look. Only the `gap` column is
  left empty.
- **How far it shakes, roughly, without any spectrum.** Step apart from a
  contact a few tenths of a nanometre at a time and watch the light. If it
  flickers between CONTACT and OPEN over more than a nanometre of travel,
  the tip is shaking by about that much.
- **The picometres are a low estimate in air.** The `gap` column takes a
  tenfold change of the current as 0.1 nm, which is right for a clean gap in
  vacuum. In air the current falls more slowly, a factor of ten for every
  0.2 to 0.3 nm, so the real motion is two or three times the number shown.
  The ratio between two records is still right.
- **The reference catches what the amplifier picks up, not everything
  electrical.** A ripple on the bias voltage needs a current to show, so it
  is absent far away and present at the edge, just like a vibration. Mains
  on the bias is still recognised by its frequency.
- **Below about 1 Hz the spectrum is mostly drift.** A piece is 4 s long, so
  the points are 0.25 Hz apart and the lowest two or three are what is left
  of the slow drift of the current.
- **A molecule in the junction hides the gap.** On a plateau the current
  does not change with the distance. Use clean gold.

## 8. Comparing two set-ups

To see whether a change to the rig (other bungees, a plate, a bolt) helped:

1. Before the change: record at the edge, put the signal on **`gap (pm)`**,
   type a name, **Save**.
2. Make the change. Approach, Find the edge, Record again.
3. With the signal on `gap (pm)`, press **Load a reference...** and pick the
   file saved in step 1. The old spectrum is drawn in grey behind the new
   one.

Compare in picometres, not in nanoamps. The nanoamps depend on how close the
tip happened to be; the picometres do not, as long as both records were in
tunnelling. A reference is only drawn, and only compared, when it is in the
same unit as the signal on show. Otherwise the line under the buttons says
`NOT SHOWN: it is in nA, the signal on show in pm`.

**Keep as reference** does the same with the record on show, without a file.

## 9. In the simulator

On the MacBook there is nothing to shake the tip, so with `--simulate` the
program shakes it: the pretend tip moves by 0.02 nm at 7.5 Hz, and the
pretend amplifier hums by 1 nA at 60 Hz. One line of each kind to find. Two
more rows appear in box 1:

    simulator's screw: surface at [300] nm up the piezo's travel   [Turn]
    simulator: shake the tip by [0.02] nm at [7.5] Hz; mains hum [1] nA

The first is pullout's (chapter 24, section 7). The second sets the shake
and the hum; a change takes effect at once.

A first try:

1. `python noisecheck.py --simulate --config configs/newrig_2ch.json`
2. **Record**, then **Keep as reference**. The list shows one line, 60 Hz,
   `mains`.
3. **Approach**, then **Find the edge**. The light says TUNNELLING and the
   live plot shows the current going up and down seven and a half times a
   second.
4. **Record**. The list shows 7.50 Hz with `20 pm` in the gap column (the
   0.02 nm you put in), its multiples, and 60 Hz marked `also`.
5. Type 33 in the Hz box and Record again: the line has moved to 33 Hz. Type
   0 in the nm box: it is gone.

A simulated play takes no time, so a 16 s record is over in a second.

## 10. The files

**Save** writes three files into `data/noisecheck` (which git ignores, like
the rest of `data/`):

    noise_20261119_153012_plate_on_4_bungees_i2.csv
    noise_20261119_153012_plate_on_4_bungees_i2.png
    noise_20261119_153012_plate_on_4_bungees_i2.txt

The name is the date and time of the record, the name you typed, and the
signal (`i1`, `i2`, `gap`, `v`, `z`). The `.csv` is the spectrum of the
signal on show up to 5 kHz: a few lines starting with `#` (the name, the
signal, the piezo's position, the bias, the config, the version), then
`frequency_hz,amplitude_<unit>`. Excel opens it, and **Load a reference...**
reads it back. The `.png` is the two plots as they are on the screen, the
`.txt` is the list.

The record itself, the samples, is not saved.

## 11. How the spectrum is made

A record is taken as pieces of 4 s, one play of the card each (the card does
not play for longer than ten seconds at a time). From each piece the
straight-line trend is taken off, so that a drifting current does not smear
over the low frequencies. The piece is weighted with a Hann window and
Fourier transformed. The powers of the pieces are averaged: a steady line
stays, and the noise around it gets smoother with every piece. The gaps
between two plays do not matter, because each piece is transformed by
itself.

The result is scaled so that a sine of amplitude A reads A. A line is a
point higher than both its neighbours that stands at least five times above
the median of the 40 points around it. Its frequency is read between the
points, and its amplitude from the point and its two neighbours together,
which gives a sine's amplitude to a per cent wherever between two points it
falls.
