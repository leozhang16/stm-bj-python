"""The sample-rate check of the Monitor window.

The question: the config asks the card for 40000 samples a second. Does
the card really hand over 40000 numbers a second, on every input in use?

What the check does, once a second while its box is ticked:

1. The piezo and the bias are HELD exactly where they are for one second
   (``rig.hold``, the call every approach step makes; nothing moves)
   while the inputs record, exactly as they record during a pull.
2. The numbers the card returned are written to a scratch file, the file
   is read back, the numbers of each input are counted, and the file is
   deleted.
3. The time the card took to play and record that second is read off this
   PC's clock. Count divided by time is the sample rate as the PC saw it.

What each part can tell you:

* The count. A record of a fixed length either comes back whole or the
  driver gives up with a time-out, so the count is the number asked for
  unless something is broken; then the check says FAILED and why. It shows
  every input in use and how many numbers each one delivered.
* The time. This is the independent part. The card keeps its own clock;
  the PC's clock knows nothing about it. A card that really sampled at
  20000 a second would need two seconds for 40000 samples, and the rate
  shown would be 20000. Starting and stopping the card costs a few
  milliseconds, and those must not be counted as sampling time. So a
  10 ms hold is played just before the long one, and the rate is the
  EXTRA samples of the long hold divided by the EXTRA time it took: the
  start-and-stop time is in both and drops out. What is left is good to
  a part in a thousand or so (the PC's own timing).

The stopwatch runs while the OUTPUTS play their second. The inputs start
on the same trigger, so on a healthy card they are finished at the same
moment, and the PC has all their numbers a few milliseconds later. The
check reads the stopwatch a second time when it has them: inputs that
sampled slower than the outputs would keep it waiting, and the check then
fails and says the inputs came in late.

On the simulated card a play takes no real time, so there is a count but
no time; the window says so.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import numpy as np

from .config import RigConfig

# The short hold whose duration is nearly all start-and-stop: 10 ms.
REFERENCE_SECONDS = 0.01


def inputs_in_use(cfg: RigConfig) -> list[tuple[str, str]]:
    """(card input, what is wired to it) for every input a play reads, in
    the order ``measure`` counts them: junction voltage, current channel 1,
    channel 2 while it is read, the piezo sense line when the rig has one."""
    M = cfg.channels
    inputs = [(M.path(M.ai_voltage), "junction voltage"),
              (M.path(M.ai_current), "current ch 1")]
    if M.two_current_channels:
        inputs.append((M.current2_path, "current ch 2"))
    if M.has_piezo_sense:
        inputs.append((M.piezo_sense_path, "piezo sense"))
    return inputs


def count_through_file(arrays, folder=None) -> dict:
    """Write ``arrays`` (one per input) to a scratch file, read the file
    back, count the numbers of each input in it, delete the file.

    Returns ``counts`` (numbers read back for each array, in order),
    ``numbers`` and ``bytes`` (the whole file), ``file`` (its name),
    ``identical`` (what was read back is, bit for bit, what was written)
    and ``deleted`` (the file is gone).
    """
    arrays = [np.ascontiguousarray(a, dtype="<f8").ravel() for a in arrays]
    fd, name = tempfile.mkstemp(prefix="stm_ratecheck_", suffix=".bin",
                                dir=None if folder is None else str(folder))
    path = Path(name)
    try:
        with os.fdopen(fd, "wb") as fh:
            for a in arrays:
                fh.write(a.tobytes())
        size = path.stat().st_size
        back = np.fromfile(path, dtype="<f8")
    finally:
        try:
            path.unlink()
        except OSError:
            pass
    counts, identical, start = [], True, 0
    for a in arrays:
        part = back[start:start + a.size]
        counts.append(int(part.size))
        identical = identical and part.size == a.size \
            and part.tobytes() == a.tobytes()
        start += a.size
    return {"counts": counts, "numbers": int(back.size), "bytes": int(size),
            "file": path.name, "identical": bool(identical and start == back.size),
            "deleted": not path.exists()}


def measure(rig, seconds: float = 1.0, folder=None) -> dict:
    """One sample-rate check on ``rig``; see the module text. Nothing
    moves: both holds are at the present piezo position and bias.

    Returns a dict for the window: ``seconds``, ``asked`` (samples per
    input asked for), ``card_rate_hz`` (the rate the card says it runs
    at), ``inputs`` (a list of {"channel", "what", "samples"}),
    ``outputs`` (the two output channels, which were written ``asked``
    samples each), the scratch file's ``file``, ``numbers``, ``bytes``,
    ``identical`` and ``deleted``, ``play_seconds`` (how long the card
    took, PC clock; None on the simulated card), ``ref_samples`` and
    ``ref_seconds`` (the short hold before it), ``pc_rate_hz`` (the extra
    samples over the extra time; None when there is no time),
    ``overhead_seconds`` (what starting and stopping cost, as that rate
    makes it), ``input_lag_seconds`` (how long after the outputs finished
    the inputs were all read; None without a time) and ``inputs_late``
    (that took far too long: the inputs sample slower than the outputs),
    ``simulated``, ``ok`` (every count is ``asked``, the file read back
    identical and is deleted, the PC's rate is within 2 % of the card's
    when there is one, and the inputs were not late), ``when`` (time of
    day) and ``record`` (the (2, n) record itself, for the readouts).
    """
    cfg = rig.cfg
    M = cfg.channels
    card_rate = float(rig.sample_rate_hz)
    asked = max(4, int(round(float(seconds) * card_rate)))
    n_ref = max(4, int(round(REFERENCE_SECONDS * card_rate)))

    # A short hold first: its duration on the PC's clock is the few
    # milliseconds it costs to start and stop the card, plus its 10 ms.
    rig.hold(n_samples=n_ref)
    t_ref = getattr(rig, "last_play_seconds", None)
    record = rig.hold(n_samples=asked)
    t_play = getattr(rig, "last_play_seconds", None)
    t_read = getattr(rig, "last_read_seconds", None)

    arrays = [record[M.ROW_VOLTAGE], record[M.ROW_CURRENT]]
    if M.two_current_channels:
        second = rig.last_current2_v
        arrays.append(second if second is not None else np.empty(0))
    if M.has_piezo_sense:
        sense = rig.last_sense_v
        arrays.append(sense if sense is not None else np.empty(0))
    filed = count_through_file(arrays, folder)
    inputs = [{"channel": channel, "what": what, "samples": count}
              for (channel, what), count in zip(inputs_in_use(cfg), filed["counts"])]

    # The rate by the PC's clock: the extra samples of the long hold over
    # the extra time it took. Starting and stopping the card is in both
    # holds and drops out; nothing is assumed about the card's rate.
    overhead = pc_rate = None
    if t_play is not None and t_play > 0:
        if t_ref is not None and t_play > t_ref and asked > n_ref:
            pc_rate = (asked - n_ref) / (t_play - t_ref)
            overhead = max(0.0, t_ref - n_ref / pc_rate)
        else:
            pc_rate, overhead = asked / t_play, 0.0

    # The inputs start with the outputs and should be done with them: all
    # read within a few milliseconds of the outputs finishing. A fifth of
    # the record later (plus 50 ms for a slow PC) is not that.
    lag = late = None
    if t_play is not None and t_read is not None:
        lag = max(0.0, t_read - t_play)
        late = lag > 0.05 + 0.2 * float(seconds)

    ok = (all(i["samples"] == asked for i in inputs) and filed["identical"]
          and filed["deleted"]
          and (pc_rate is None or abs(pc_rate / card_rate - 1.0) < 0.02)
          and not late)
    return {"seconds": float(seconds), "asked": asked, "card_rate_hz": card_rate,
            "inputs": inputs, "outputs": list(M.ao_channels),
            "file": filed["file"], "numbers": filed["numbers"],
            "bytes": filed["bytes"], "identical": filed["identical"],
            "deleted": filed["deleted"], "play_seconds": t_play,
            "ref_samples": n_ref, "ref_seconds": t_ref,
            "overhead_seconds": overhead, "pc_rate_hz": pc_rate,
            "input_lag_seconds": lag, "inputs_late": bool(late),
            "simulated": bool(cfg.simulate), "ok": bool(ok),
            "when": time.strftime("%H:%M:%S"), "record": record}


def lines(result: dict) -> tuple[str, list[str]]:
    """The check in words: (the headline, the lines under it). The window
    shows them; a terminal can print them."""
    if result.get("error"):
        return "CHECK FAILED", [result["error"]]
    inputs = result["inputs"]
    counts = sorted({i["samples"] for i in inputs})
    each = str(counts[0]) if len(counts) == 1 else "/".join(str(c) for c in counts)
    # The headline carries what was MEASURED: the count that came back
    # and, when there is a time, the rate by the PC's clock.
    if result["pc_rate_hz"] is not None:
        head = (f"{each} samples x {len(inputs)} inputs: "
                f"{result['pc_rate_hz']:.0f} samples/s")
    else:
        head = f"{each} samples x {len(inputs)} inputs in {result['seconds']:g} s"
    out = [f"{i['channel']:<12}{i['what']:<18}{i['samples']:>8} samples"
           + ("" if i["samples"] == result["asked"] else "   <-- NOT what was asked")
           for i in inputs]
    out.append(f"asked for {result['asked']} per input: {result['seconds']:g} s at the "
               f"card's {result['card_rate_hz']:.3f} samples/s")
    out.append(f"outputs {', '.join(result['outputs'])}: {result['asked']} samples "
               "written to each (held, nothing moved)")
    out.append(f"file {result['file']}: {result['numbers']} numbers, "
               f"{result['bytes'] / 1e6:.2f} MB, read back "
               + ("identical" if result["identical"] else "DIFFERENT")
               + (", deleted" if result["deleted"] else ", NOT DELETED"))
    if result["pc_rate_hz"] is not None:
        out.append(f"by this PC's clock the card took {result['play_seconds']:.4f} s "
                   f"for these, {result['overhead_seconds'] * 1e3:.1f} ms of it "
                   "starting and stopping:")
        out.append(f"    {result['pc_rate_hz']:.0f} samples/s by the PC's clock, "
                   f"{result['card_rate_hz']:.0f} by the card's")
        if result.get("input_lag_seconds") is not None:
            out.append(f"the inputs were all read {result['input_lag_seconds'] * 1e3:.0f} ms "
                       "after the outputs finished"
                       + ("   <-- FAR TOO LATE: the inputs sample slower than the outputs"
                          if result.get("inputs_late") else ""))
    elif result["simulated"]:
        out.append("simulated card: a play takes no real time, so there is no "
                   "PC-clock rate here (the rig has one)")
    else:
        out.append("no time for this play: the driver did not report one")
    out.append(f"checked at {result['when']}")
    return head, out
