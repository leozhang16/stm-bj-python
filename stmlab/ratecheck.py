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
3. The same second is kept where a person can look at it:
   ``sampling_rate_test.csv`` in the data folder, one row per sample (its
   number, its time, then one column of volts per input). It is written
   afresh by every check, so it always holds the last one. Open it in
   Excel: 40000 rows under the header row.
4. The time the card took to play that second is read off this PC's clock,
   as a rough cross-check.

What each part can tell you:

* The count is the sample rate. The card's sample clock is a crystal, and
  the driver reports the rate it really runs at (``samp_clk_rate``, which
  is what ``rig.sample_rate_hz`` returns). A record of one second on that
  clock is 40000 samples on every input, or the driver gives up with a
  time-out and the check says FAILED and why. The big line of the window
  is this: the samples each input delivered, per second of the card's own
  clock.
* The stopwatch is only a cross-check, and a rough one. The PC says "go",
  waits for the card to say "done" and looks at its own clock. Starting
  and stopping a card over USB costs 10 to 20 ms, and how much depends on
  the length of the record, so the stopwatch cannot tell 40000 from 39700.
  (v69 tried: it took a 10 ms record's start-and-stop time off the long
  one's and showed the result as a rate. On the real card the long record
  cost 7.5 ms more to start and stop than the short one, and the window
  said 39698 samples/s for a card that was sampling at 40000.) What the
  stopwatch can catch is a card that is grossly off: one that really
  sampled at 20000 a second would need two seconds for 40000 samples.
  The lines under the headline give the time measured and how much of it
  is on top of the samples' own; the check fails when that is more than
  about 3 % of the record (plus 30 ms) away from what the short record
  before it cost.

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

# The record of the last check, kept in the data folder for Excel.
CSV_NAME = "sampling_rate_test.csv"


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


def save_csv(folder, card_rate_hz: float, inputs, arrays) -> dict:
    """Keep one check's record where a person can look at it:
    ``sampling_rate_test.csv`` in ``folder`` (made if it is not there).

    One header row, then one row per sample: ``sample`` (1, 2, ...),
    ``time_s`` (the sample's index over the card's rate: the first is at
    0, the 40000th at 0.999975), then one column per input, named by its
    card input and what is wired to it, in volts as the card read them.
    An input that came back short leaves its last cells ``nan``. The file
    is written under another name and then moved into place, so a check
    that fails half-way never leaves half a file.

    Returns ``csv`` (the file, or None), ``csv_rows`` (rows under the
    header) and ``csv_error`` (why it was not written; a file that is
    open in Excel cannot be replaced on Windows).
    """
    path = Path(folder).absolute() / CSV_NAME        # the whole path, to be found by
    part = path.with_name(path.name + ".part")
    try:
        arrays = [np.asarray(a, dtype=float).ravel() for a in arrays]
        n = max((a.size for a in arrays), default=0)
        table = np.full((n, 2 + len(arrays)), np.nan)
        table[:, 0] = np.arange(1, n + 1)
        table[:, 1] = np.arange(n) / float(card_rate_hz)
        for k, a in enumerate(arrays):
            table[:a.size, 2 + k] = a
        header = ",".join(["sample", "time_s"]
                          + [f"{channel} {what} (V)" for channel, what in inputs])
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savetxt(part, table, delimiter=",", header=header, comments="",
                   fmt=["%d", "%.7f"] + ["%.7f"] * len(arrays))
        os.replace(part, path)
        return {"csv": str(path), "csv_rows": int(n), "csv_error": None}
    except OSError as exc:
        try:
            part.unlink()
        except OSError:
            pass
        why = exc.strerror or str(exc)
        if isinstance(exc, PermissionError):
            why += " (is it open in Excel? close it there)"
        return {"csv": None, "csv_rows": None, "csv_error": f"{path}: {why}"}


def measure(rig, seconds: float = 1.0, folder=None, keep=None) -> dict:
    """One sample-rate check on ``rig``; see the module text. Nothing
    moves: both holds are at the present piezo position and bias.
    ``keep`` is the folder in which the record is kept as
    ``sampling_rate_test.csv`` (``save_csv``); None keeps nothing.

    Returns a dict for the window: ``seconds``, ``asked`` (samples per
    input asked for), ``card_rate_hz`` (the rate the card says it runs
    at), ``record_seconds`` (how long ``asked`` samples last on that
    clock), ``inputs`` (a list of {"channel", "what", "samples"}),
    ``count_rate_hz`` (THE SAMPLE RATE, counted: what the input that
    delivered least delivered, per second of the card's clock),
    ``outputs`` (the two output channels, which were written ``asked``
    samples each), the scratch file's ``file``, ``numbers``, ``bytes``,
    ``identical`` and ``deleted``, the kept file's ``csv``, ``csv_rows``
    and ``csv_error``, ``play_seconds`` (go to done on the PC's clock;
    None on the simulated card), ``ref_samples`` and ``ref_seconds`` (the
    short hold before it), ``extra_seconds`` and ``ref_extra_seconds``
    (what each of the two took on top of its samples' own time: the
    starting and stopping), ``stopwatch_ok`` (the long hold's extra is
    within 3 % of the record plus 30 ms of the short hold's; None without
    a time), ``input_lag_seconds`` (how long after the outputs finished
    the inputs were all read; None without a time) and ``inputs_late``
    (that took far too long: the inputs sample slower than the outputs),
    ``simulated``, ``ok`` (every count is ``asked``, the scratch file read
    back identical and is deleted, the stopwatch does not disagree, and
    the inputs were not late), ``when`` (time of day) and ``record`` (the
    (2, n) record itself, for the readouts).
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
    wired = inputs_in_use(cfg)
    inputs = [{"channel": channel, "what": what, "samples": count}
              for (channel, what), count in zip(wired, filed["counts"])]
    kept = (save_csv(keep, card_rate, wired, arrays) if keep is not None
            else {"csv": None, "csv_rows": None, "csv_error": None})

    # The sample rate, counted: the samples the inputs delivered over the
    # time the record lasts on the card's own clock.
    record_seconds = asked / card_rate
    least = min((i["samples"] for i in inputs), default=0)
    count_rate = least / record_seconds

    # The stopwatch, a rough cross-check: go to done on the PC's clock,
    # less the samples' own time, is what starting and stopping cost. The
    # short hold before says roughly how much that is; the long one may
    # cost some milliseconds more (it has more to send to the card), so
    # only a difference well beyond that is the card not keeping its rate.
    extra = ref_extra = stopwatch_ok = None
    if t_play is not None and t_play > 0:
        extra = t_play - record_seconds
        if t_ref is not None and t_ref > 0:
            ref_extra = t_ref - n_ref / card_rate
        stopwatch_ok = bool(abs(extra - (ref_extra or 0.0))
                            <= 0.03 + 0.03 * record_seconds)

    # The inputs start with the outputs and should be done with them: all
    # read within a few milliseconds of the outputs finishing. A fifth of
    # the record later (plus 50 ms for a slow PC) is not that.
    lag = late = None
    if t_play is not None and t_read is not None:
        lag = max(0.0, t_read - t_play)
        late = lag > 0.05 + 0.2 * float(seconds)

    ok = (all(i["samples"] == asked for i in inputs) and filed["identical"]
          and filed["deleted"] and stopwatch_ok is not False and not late)
    return {"seconds": float(seconds), "asked": asked, "card_rate_hz": card_rate,
            "record_seconds": record_seconds, "count_rate_hz": count_rate,
            "inputs": inputs, "outputs": list(M.ao_channels),
            "file": filed["file"], "numbers": filed["numbers"],
            "bytes": filed["bytes"], "identical": filed["identical"],
            "deleted": filed["deleted"], "csv": kept["csv"],
            "csv_rows": kept["csv_rows"], "csv_error": kept["csv_error"],
            "play_seconds": t_play,
            "ref_samples": n_ref, "ref_seconds": t_ref,
            "extra_seconds": extra, "ref_extra_seconds": ref_extra,
            "stopwatch_ok": stopwatch_ok,
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
    secs = result["record_seconds"]
    # The headline is the sample rate as COUNTED: the samples each input
    # delivered over the time the record lasts on the card's own clock.
    # The PC's stopwatch is never shown as a rate; it only speaks up here
    # when it disagrees grossly.
    if len(counts) != 1 or counts[0] != result["asked"]:
        head = f"{each} samples in {secs:g} s: NOT what was asked"
    elif result["stopwatch_ok"] is False:
        head = (f"{each} samples, but they took {result['play_seconds']:.2f} s, "
                f"not {secs:g} s")
    else:
        head = (f"{result['count_rate_hz']:.0f} samples/s: {each} samples in "
                f"{secs:g} s on each of {len(inputs)} inputs")
    out = [f"{i['channel']:<12}{i['what']:<18}{i['samples']:>8} samples"
           + ("" if i["samples"] == result["asked"] else "   <-- NOT what was asked")
           for i in inputs]
    out.append(f"asked for {result['asked']} per input: {secs:g} s at the "
               f"card's {result['card_rate_hz']:.3f} samples/s")
    out.append(f"outputs {', '.join(result['outputs'])}: {result['asked']} samples "
               "written to each (held, nothing moved)")
    out.append(f"file {result['file']}: {result['numbers']} numbers, "
               f"{result['bytes'] / 1e6:.2f} MB, read back "
               + ("identical" if result["identical"] else "DIFFERENT")
               + (", deleted" if result["deleted"] else ", NOT DELETED"))
    if result.get("csv"):
        out.append(f"kept for Excel: {result['csv']}")
        out.append(f"    {result['csv_rows']} rows under the header: sample, time_s, "
                   "then one column per input (volts)")
    elif result.get("csv_error"):
        out.append(f"NOT kept for Excel: {result['csv_error']}")
    if result["play_seconds"] is not None and result.get("extra_seconds") is not None:
        out.append(f"PC stopwatch (rough, a cross-check only): {result['play_seconds']:.4f} s "
                   f"from go to done for {secs:.4f} s of samples")
        extra = f"    the {result['extra_seconds'] * 1e3:.1f} ms on top"
        if result["stopwatch_ok"] is False:
            extra += "   <-- FAR TOO MUCH OFF: the card does not keep the rate it reports"
        else:
            extra += " are the PC starting and stopping the card"
        if result.get("ref_extra_seconds") is not None:
            extra += (f" ({result['ref_extra_seconds'] * 1e3:.1f} ms on the "
                      f"{result['ref_samples']}-sample record before it)")
        out.append(extra)
        if result.get("input_lag_seconds") is not None:
            out.append(f"the inputs were all read {result['input_lag_seconds'] * 1e3:.0f} ms "
                       "after the outputs finished"
                       + ("   <-- FAR TOO LATE: the inputs sample slower than the outputs"
                          if result.get("inputs_late") else ""))
    elif result["simulated"]:
        out.append("simulated card: a play takes no real time, so there is no "
                   "PC stopwatch here (the rig has one)")
    else:
        out.append("no time for this play: the driver did not report one")
    out.append(f"checked at {result['when']}")
    return head, out
