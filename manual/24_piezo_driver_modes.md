# 24. The piezo driver's two modes, Approach, and the two sliders

*Python: `stmlab/config.py` (`Calibration.piezo_total_um`, `piezo_mode`,
`piezo_drive_full_v`, `piezo_drive_gain`, `piezo_scale`, `sense_scale`,
`apply_piezo_mode`), `stmlab/instrument.py` (`Rig.piezo_glide_to`, and the
`tail` of `conductance_of` and `is_saturated`, `current_ua_of`),
`pullout.py` v72 and v73 (`fine_window`; `Worker.cmd_piezo_mode`,
`piezo_state`, `cmd_goto`, `cmd_piezo_approach`, `_approach_by_hand`,
`_closed`, `cmd_sim_surface`; the Driver row, the Approach button and the
two sliders of the Piezo box).
Tests: `tests/test_v72_piezo.py`, `tests/test_v73_approach.py`.*

Every distance this program moves the tip is a voltage at the card divided
by one number: how many nanometres the piezo moves per volt. This chapter is
about where that number comes from, and about moving the piezo by hand:
the Approach button (section 5) and the two sliders (section 4).

## 1. One number from the stage's sheet, and a switch

The piezo is driven through a driver box (a Nano-Drive). The stage's sheet
gives one number: how far the piezo moves for its whole drive voltage,
0 to 150 V. That is the **total displacement**. For the new rig it is
10.776 um.

The box has a switch with two positions.

| | Standard | Bypass |
|---|---|---|
| What the box does | amplifies the card's 0 to 10 V to the piezo's 0 to 150 V (a gain of 15) | nothing: the card's volts go to the piezo as they are |
| nm per volt at the card | total / 10 V | total / 150 V |
| For 10.776 um | 1077.6 nm/V | 71.84 nm/V |
| What the card's 0 to 10 V reaches | all 10.776 um | 718 nm |
| One step of a 16-bit card output (0.3 mV) | 0.33 nm | 0.022 nm |

The two differ by exactly the box's gain, 15.

- **Standard** reaches far. After the screws the piezo itself can come up to
  the surface over micrometres. But the card's output moves in steps of a
  third of a nanometre, about the length of a gold step, so a slow pull is a
  staircase.
- **Bypass** reaches a fifteenth as far, in steps fifteen times finer. The
  old rig ran like this: its 62 nm/V is a stage of 9.3 um.

The stage's sensor (the sense line) is taken to read the whole displacement
over its 10 V in either mode: total / 10 V per sense volt.

## 2. Telling the program

The first row of the **Piezo** box:

    Driver   (o) standard   ( ) bypass     total displacement [10.776] um   [Set]

Pick the mode the box's switch is in, type the total displacement, press
**Set**. Nothing changes before Set. The line under the row says what is in
force, in green:

    STANDARD: 1 V at the card = 1077.60 nm; the whole 0 to 10 V = 10776 nm

and, while the row differs from that, what Set would do, in orange.

Set lasts until the program is closed. To keep it, put the two lines in the
`cal` part of the rig's config (the status line prints them for you):

    "cal": {
        "piezo_total_um": 10.776,
        "piezo_mode": "standard",
        ...

With `piezo_total_um` in the config, `piezo_nm_per_volt` and
`sense_nm_per_volt` are worked out from it, and whatever is typed for those
two is ignored. A config without it (every config written before v72) is as
it always was: the two numbers as typed. The Driver row then says so in
orange, and Set gives it a total displacement for the session. Set works
out both numbers, the sense line's too (total / 10 V per sense volt).

### The program takes your word for the switch

**Nothing in the program checks where the switch on the box stands.** The
Driver row is what you say it is. If the row says one mode and the box is in
the other, every move is 15 times too big or 15 times too small, and the
program will not notice.

In November 2026 a bypass number (71.84) stood in the config of a box in
standard mode. Every move was 15 times what the screen said for days: a pull
of "5 nm at 20 nm/s" was 75 nm at 300 nm/s, an approach step of "0.5 nm" was
7.5 nm, a smash of "30 nm" was 450 nm. The command and the readback agreed
with each other throughout, because both were scaled by the same wrong
number.

One thing on the screen does show the box's mode, if you look for it. The
Sense (V) readout is the stage's own sensor. With the box in standard mode
it reads the same volts as Piezo (V) beside it (seen on the new rig). With
the box in bypass it should read a fifteenth of Piezo (V); that has not been
tried on a rig yet.

## 3. A change of mode takes the piezo to 0 V first

When Set changes the **mode**, the program first takes the piezo to 0 V and
leaves it there. Then the status line says, in capitals, to put the switch
on the box to the new mode.

The reason: the switch changes what the card's voltage means. With the card
holding 8 V in bypass, the piezo has 8 V on it. Flip the switch to standard
and the same 8 V at the card becomes 120 V at the piezo: the tip goes
8 micrometres toward the surface, at once. At 0 V, and only there, the two
modes agree. So that is where the switch is flipped.

It is exactly 0 V, whatever `ramp.piezo_park_v` is. Where 0 V cannot be had
the mode is not changed, and the status line says why in red:

- the piezo stands below 0 V (going up to 0 V would be a move toward the
  surface): take it to 0 V with the slider first;
- the rig's piezo range (`limits.piezo_ao_min_v` to `piezo_ao_max_v`) does
  not include 0 V.

A change of the total displacement alone is arithmetic. Nothing moves.

After a change to bypass the surface is usually out of the piezo's reach
(718 nm instead of 10.8 um), and the screws have to bring it back.

## 4. Two sliders

Under the Approach row there are two sliders. Both move the one piezo
output.

- **coarse: the whole range.** 0 to 10 V, in steps of 1 mV. In standard mode
  that is the whole 10.8 um.
- **fine.** A window of the range, in steps of 0.1 mV: half a volt either
  side of where the piezo is, on round numbers. With contact at 7.99 V it
  runs from 7.5 V to 8.5 V. Its two ends are written under it in volts and
  in nanometres (`7.5 V = 8082 nm` and `8.5 V = 9160 nm`). They are real
  volts at the card, not a scale of its own. Where the piezo's range ends
  the window is cut off: around 0.29 V it runs from 0 V to 0.8 V. The box
  beside it (`fine: +/- 0.5 V`) changes the width; while that box holds
  nothing usable (it is being typed in) the last width stays. The window
  walks along with the piezo: it is put around the place a move by hand
  ended (after Approach that is the contact), and during a run it follows
  when the piezo nears one of its ends.

On each knob rides a label with where the knob is, in volts and in
nanometres: `8.027 V = 8650.0 nm`. Both knobs stand on the piezo: they are
two rulers on one position. While the mouse holds a knob the label turns
orange and says `(release to move)`: that is where the piezo will go.

How a slider is worked:

- **Drag the knob and let go.** The piezo moves when the mouse is released,
  to where the knob then is.
- **Click beside the knob.** One step of that slider toward the click: 1 mV
  on the coarse one, 0.1 mV on the fine one. Hold the mouse down for more.
- **Click on the knob without moving it.** Nothing. Only a knob that was
  moved moves the piezo.
- A Control-click, which in other programs sends a slider's knob to the end
  of its range, does nothing here.

## 5. Approach: the piezo comes up to the surface (v73)

For a rig whose coarse approach is a screw turned by hand. In standard mode
the piezo reaches 10.8 um, so the screw does not have to find the contact.
It only has to bring the surface within the piezo's reach. Then:

    [Approach]  toward the surface at [200] nm/s, stopping at contact

**Approach** takes the piezo toward the surface from where it is, at the
speed in the box, and stops where the junction closes (section 6 says how
it goes and what counts as closed). Three ways it can end:

| It ends with | What the status line says | Where the piezo is |
|---|---|---|
| contact | `CONTACT at 8.0271 V = 8650.0 nm (G = 318 G0). The piezo stays there and the fine slider is around it. Now Start N` | at the contact; the fine slider runs from 7.5 V to 8.5 V |
| no contact up to the top of the range | `NO CONTACT for the whole range (up to 10 V = 10776 nm): approach with the screw again. The piezo is back at 0.000 V` | back where it started, taken there over half a second |
| **Stop** | `Approach stopped by Stop at ...` | where it was when Stop was pressed |

How to use it:

1. Have the piezo low (0 V: the coarse slider at the left).
2. Turn the screw in until the tip is close, but the CONTACT light is still
   off.
3. Press **Approach**. At 200 nm/s the whole 10.8 um takes about a minute,
   more on the rig (section 6). A higher speed is quicker and presses the
   tip further into the surface at the end.
4. `NO CONTACT`: turn the screw in a little more, press Approach again.
5. `CONTACT`: press Start N.

Two things it says instead of moving:

- `already in contact at ...: nothing to approach`. The junction is closed
  before the piezo has moved. If that is at 0 V, the screw went too far:
  turn it back.
- `CONTACT at ... That is too low in the range to pull from`. A pull goes
  down from the contact, and there is no room under it. Turn the screw back
  a little and Approach again.

## 6. A move toward the surface goes slowly and stops at contact

A slider is a coarse thing. With a micrometre to the volt, a finger's width
of it is hundreds of nanometres. So:

- A move **away** from the surface is made at once (a 50 ms ramp), as before.
- A move **toward** the surface (Approach, either slider, or Step closer)
  goes at the speed in the Approach row, in pieces of 25 ms. At the end of
  each piece the program reads the junction. When it has closed the move
  ends there. For a slider the status line then says `STOPPED AT CONTACT
  (...), ... short of the ... asked for`. **Stop** ends it between two
  pieces.

### What counts as closed

Any one of three signs, read from the last millisecond of the piece. The
status line says which one it was.

| Sign | In the status line |
|---|---|
| the conductance is above the Engage threshold | `G = 318 G0` |
| the current is above the contact current, the number in the Coarse approach box that also lights the CONTACT light (0.15 uA) | `0.941 uA, above the contact current` |
| the amplifier is at its rail | `the amplifier is at its rail` |

The second one is new in v73, and it is there for the new rig. A few
millivolts of offset on the junction voltage cap its conductance reading
near 4 G0, and through the series resistor the amplifier never rails. With
Engage at 5 neither of the other two signs ever came, and a move toward the
surface would not have stopped. The current does not need the junction
voltage: in contact it is 0.94 uA whatever the conductance reading says. A
contact current of 0 switches this sign off.

It only applies to moves made by hand. The automatic approach of a run
(Start N) is as it was: it goes by Engage, so Engage still has to be below
that ceiling (2 on the new rig).

### How far in the tip ends

A little more than one piece past the place where the junction closed. A
piece is speed times 25 ms: 5 nm at 200 nm/s, 25 nm at 1000 nm/s. The piece
in which the junction closed is played to its end. In the simulator that
comes to at most 5.2 nm at 200 nm/s and 52 nm at 2000 nm/s. So the speed is
a choice between waiting and pressing in. On the rig a piece also costs the
card's start-and-stop time, so the real speed is somewhat below the number
in the box.

Asked for more while the junction is already closed, the piezo goes one
piece further in and stops again. So a slip of the slider in contact costs
one piece, not the whole slip.

After a move by hand that ended in contact the state is ENGAGED, and
Start N starts from there, separating first.

## 7. In the simulator

The simulated piezo moves what the program says it does, in whichever mode
the Driver row is in: there is no pretend switch to forget.

The simulated surface starts 300 nm up the piezo's travel: 0.28 V in
standard mode and 4.18 V in bypass, for a 10.776 um stage. A real one ends
up wherever the screw left it. So with `--simulate` the Coarse approach box
has one more row, the **simulator's screw**:

    simulator's screw: surface at [8600] nm up the piezo's travel   [Turn]

Type where the surface should be and press **Turn**. 8600 puts it near 8 V
in standard mode, as on the rig: Approach then finds it there and the fine
slider runs from 7.5 V to 8.5 V. 50000 puts it out of the piezo's reach:
Approach then ends with `NO CONTACT for the whole range`. The screw will not
push the surface into the tip: take the piezo down first.

A simulated play takes no time, so a move toward the surface that takes
a minute on the rig is over at once in the simulator.
