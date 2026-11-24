"""noisecheck.py (v74): the tunnelling current, Fourier transformed.

Simulator only: no card. None of these tests moves a real piezo.

Two halves. ``stmlab/noise.py`` is plain arithmetic on arrays: a spectrum
averaged over the pieces of a record, its biggest lines, which of them are
mains or a multiple of another. ``noisecheck.py`` is the program: pullout's
worker with commands of its own (a live look, the way from contact to its
edge, the record), the analysis of a record, and the window. In simulation
the pretend tip is shaken at 7.5 Hz by 0.02 nm and the pretend amplifier
hums at 60 Hz, so there is one line of each kind to find.

A record is taken in pieces of 4 s, so its lines are 0.25 Hz apart. With a
two-channel amplifier the tunnelling current is channel 2's.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from stmlab import noise                                                  # noqa: E402
from test_v72_piezo import SURFACE_NM, _cfg, _surface                     # noqa: E402

RATE = 40_000.0


@pytest.fixture(scope="module")
def ap():
    import pullout
    return pullout


@pytest.fixture(scope="module")
def nc():
    import noisecheck
    return noisecheck


def _display():
    """Skip the test where there is no Tk, or no screen for it."""
    tk = pytest.importorskip("tkinter")
    pytest.importorskip("igor2")
    try:
        tk.Tk().destroy()
    except tk.TclError as exc:
        pytest.skip(f"no Tk display: {exc}")


def _made_up(lines, pieces: int = 4, seconds: float = 2.0, sigma: float = 0.0,
             level: float = 77.0, drift: float = 0.0, seed: int = 0) -> list:
    """A record with known lines in it: (Hz, amplitude) pairs on a level,
    with noise and a drift, as pieces with a gap of 15 ms between them."""
    rng = np.random.default_rng(seed)
    n = int(RATE * seconds)
    out = []
    for k in range(pieces):
        t = np.arange(n) / RATE + k * (seconds + 0.015) + 0.37
        x = level + drift * t + sigma * rng.normal(size=n)
        for hz, amp in lines:
            x = x + amp * np.sin(2 * np.pi * hz * t + 0.3)
        out.append(x)
    return out


def _cfg2():
    """The new rig's amplifier: two outputs, 1e4 and 1e7 V/A, both read."""
    cfg = _cfg()
    cfg.channels.ai_current_2, cfg.channels.current_channels = "ai4", 2
    cfg.cal.preamp_gain_v_per_a, cfg.cal.preamp_gain_2_v_per_a = 1e4, 1e7
    cfg.limits.preamp_saturation_v = 9.5
    return cfg


def _session(ap, nc, cfg, tmp_path):
    guard, rig = ap.open_rig(cfg)
    shake = nc.SimShake(rig._session, cfg)
    worker = nc.NoiseWorker(cfg, rig, ap.Monitor(rig), save=False, out_dir=tmp_path,
                            igor_export=False)
    return guard, rig, shake, worker


def _last(worker, kind: str) -> dict:
    return [p for k, p in list(worker.events.queue) if k == kind][-1]


def _fits(worker) -> bool:
    """Every status line so far fits the window's Status box (four lines)."""
    return all(len(p["text"]) < 200 for k, p in list(worker.events.queue)
               if k == "status")


def _to_the_edge(worker) -> None:
    worker.cmd_zero()
    worker.cmd_piezo_approach()
    worker.cmd_edge()


# -- the arithmetic -----------------------------------------------------------------

@pytest.mark.parametrize("hz", [10.0, 10.1, 10.25, 999.9])
def test_a_sine_reads_its_frequency_and_its_amplitude(hz):
    """On a bin or between two: the frequency to a hundredth of a bin, the
    amplitude to a per cent or two."""
    freqs, amp = noise.amplitude_spectrum(_made_up([(hz, 3.0)]), RATE)
    assert freqs[1] == pytest.approx(0.5)              # 1 / (2 s)
    peak = noise.find_peaks(freqs, amp, count=1)[0]
    assert peak.hz == pytest.approx(hz, abs=0.01)
    assert peak.amp == pytest.approx(3.0, rel=0.02)


def test_lines_are_found_under_noise_and_on_a_drift_biggest_first():
    lines = [(7.5, 35.0), (22.11, 4.0), (60.0, 1.0), (333.3, 0.6)]
    freqs, amp = noise.amplitude_spectrum(
        _made_up(lines, pieces=8, sigma=8.8, drift=1.0), RATE)
    found = noise.find_peaks(freqs, amp)
    assert [round(p.hz, 1) for p in found] == [7.5, 22.1, 60.0, 333.3]
    for peak, (hz, size) in zip(found, lines):
        assert peak.hz == pytest.approx(hz, abs=0.05)
        assert peak.amp == pytest.approx(size, rel=0.12)
        assert peak.over >= 5.0
    # and what they are called
    assert noise.guess_mains(freqs, amp) == 60.0
    assert noise.describe(found, 60.0, 0.5) == [
        "bounce on the suspension, the floor",
        "machines, or a part of the rig ringing",
        "mains",
        "sound, or a stiff part ringing"]


@pytest.mark.parametrize("pieces", [1, 8])
def test_noise_and_drift_alone_give_no_line(pieces):
    freqs, amp = noise.amplitude_spectrum(
        _made_up([], pieces=pieces, sigma=8.8, drift=30.0), RATE)
    assert noise.find_peaks(freqs, amp) == []


def test_more_pieces_make_the_floor_smoother_not_lower():
    one = noise.amplitude_spectrum(_made_up([], pieces=1, sigma=8.8), RATE)[1][100:4000]
    many = noise.amplitude_spectrum(_made_up([], pieces=16, sigma=8.8), RATE)[1][100:4000]
    assert np.std(many) < 0.4 * np.std(one)
    assert np.mean(many) == pytest.approx(np.mean(one), rel=0.25)


def test_mains_and_multiples_are_named():
    P = noise.Peak
    peaks = [P(7.5, 30.0, 400.0), P(15.01, 3.0, 40.0), P(60.02, 1.0, 13.0),
             P(22.48, 0.5, 9.0), P(120.0, 0.4, 8.0), P(1.2, 0.3, 6.0)]
    assert noise.describe(peaks, 60.0, 0.5) == [
        "bounce on the suspension, the floor", "2 x 7.50 Hz", "mains",
        "3 x 7.50 Hz", "mains x 2", "slow swing of the rig, or drift"]
    # a 50 Hz country
    freqs, amp = noise.amplitude_spectrum(
        _made_up([(50.0, 1.0), (150.0, 0.5)], sigma=1.0), RATE)
    assert noise.guess_mains(freqs, amp) == 50.0
    assert noise.multiple_of(149.9, 50.0, 0.4) == 3 and noise.multiple_of(149.0, 50.0, 0.4) == 0


def test_a_long_record_is_thinned_for_the_plot_without_losing_its_spikes():
    y = np.zeros(200_000)
    y[123_456], y[7] = 9.0, -4.0
    t, thinned = noise.thin(np.arange(y.size) / RATE, y)
    assert thinned.size <= 4000 and thinned.max() == 9.0 and thinned.min() == -4.0
    assert np.all(np.diff(t) >= 0)                     # still in the order it came
    short = np.arange(10.0)
    assert noise.thin(short, short)[1] is short or np.array_equal(
        noise.thin(short, short)[1], short)


# -- the program, on the simulated card ----------------------------------------------

def test_the_whole_path_finds_the_shake_and_tells_it_from_the_hum(ap, nc, tmp_path):
    """Approach, Find the edge, Record: the line at 7.5 Hz is the 0.02 nm
    the pretend tip is shaken by. Then the same far away: the hum is still
    there, the shake is not, and with that as the reference the hum is
    marked and the shake is not."""
    cfg = _cfg()
    guard, rig, shake, worker = _session(ap, nc, cfg, tmp_path)
    try:
        assert (shake.shake_hz, shake.shake_nm, shake.hum_na) == (7.5, 0.02, 1.0)
        _to_the_edge(worker)
        said = _last(worker, "status")
        assert said["text"].startswith("at the edge of contact: retracted ")
        assert "(tunnelling). Now Record" in said["text"] and said["level"] == "ok"
        worker.cmd_record(16.0)
        rec = _last(worker, "noise")
        assert len(rec["pieces"]) == 4 and rec["piece_s"] == 4.0
        assert rec["pieces"][0]["i1"].size == 160_000
        assert set(rec["pieces"][0]) == {"i1", "v", "z"}          # this rig's inputs
        result = nc.analyse(rec["pieces"], rec["rate"], "i1", break_g0=rec["break_g0"])
        assert result["step_hz"] == pytest.approx(0.25) and result["railed"] == 0.0
        assert result["shares"][1] > 0.99                         # tunnelling throughout
        top = result["peaks"][0]
        assert top["hz"] == pytest.approx(7.5, abs=0.02)
        assert top["pm"] == pytest.approx(20.0, rel=0.05)         # 0.02 nm of gap
        assert top["what"] == "bounce on the suspension, the floor"
        hum = next(p for p in result["peaks"] if p["what"] == "mains")
        assert hum["hz"] == pytest.approx(60.0, abs=0.05)
        assert hum["amp"] == pytest.approx(1.0, rel=0.1) and hum["pm"] is None
        # the multiples of the shake are named, and are no motion of the gap
        twice = next(p for p in result["peaks"] if p["what"] == "2 x 7.50 Hz")
        assert twice["pm"] < 0.1
        # far away: the reference
        worker.cmd_step(-200.0)
        worker.cmd_record(4.0)
        far = nc.analyse(_last(worker, "noise")["pieces"], rec["rate"], "i1",
                         break_g0=rec["break_g0"])
        assert far["shares"][0] > 0.9
        assert [p["what"] for p in far["peaks"]] == ["mains"]
        again = nc.analyse(rec["pieces"], rec["rate"], "i1", break_g0=rec["break_g0"],
                           reference=far)
        marks = {p["what"]: p["in_reference"] for p in again["peaks"]}
        assert marks["mains"] is True
        assert marks["bounce on the suspension, the floor"] is False
        text = "\n".join(nc.report(again))
        assert "7.50" in text and "20 pm" in text and "also" in text
        assert _fits(worker)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_the_gap_can_be_looked_at_directly_and_follows_the_simulators_boxes(
        ap, nc, tmp_path):
    cfg = _cfg(mode="bypass")
    guard, rig, shake, worker = _session(ap, nc, cfg, tmp_path)
    try:
        shake.shake_hz, shake.shake_nm, shake.hum_na = 33.3, 0.01, 0.0
        _to_the_edge(worker)
        worker.cmd_record(8.0)
        rec = _last(worker, "noise")
        gap = nc.analyse(rec["pieces"], rec["rate"], "gap", break_g0=rec["break_g0"])
        assert gap["unit"] == "pm"
        top = gap["peaks"][0]
        assert top["hz"] == pytest.approx(33.3, abs=0.02)
        assert top["amp"] == pytest.approx(10.0, rel=0.05)       # 0.01 nm
        assert not any(p["what"].startswith("mains") for p in gap["peaks"])
        # nothing shaking, nothing humming: nothing to find
        shake.shake_nm = 0.0
        worker.cmd_record(4.0)
        still = nc.analyse(_last(worker, "noise")["pieces"], rec["rate"], "i1",
                           break_g0=rec["break_g0"])
        assert still["peaks"] == []
        assert "no line stands out of the noise" in nc.report(still)
        assert _fits(worker)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_find_the_edge_retracts_in_small_steps_and_stays(ap, nc, tmp_path, monkeypatch):
    cfg = _cfg()
    guard, rig, shake, worker = _session(ap, nc, cfg, tmp_path)
    try:
        shake.shake_nm = 0.0                       # a still tip: a step reads the gap
        # with the junction open there is nothing to retract from
        worker.cmd_edge()
        said = _last(worker, "status")
        assert said["level"] == "warn" and said["text"].startswith(
            "Find the edge: the junction is open (G = ")
        assert "Press Approach first" in said["text"] and rig.piezo_v == 0.0
        worker.cmd_piezo_approach()
        start = rig.piezo_v
        asked = []
        hold = rig.hold

        def watched(piezo_v=None, bias_v=None, n_samples=None):
            asked.append(rig.piezo_v if piezo_v is None else piezo_v)
            return hold(piezo_v=piezo_v, bias_v=bias_v, n_samples=n_samples)
        monkeypatch.setattr(rig, "hold", watched)
        worker.cmd_edge()
        # this junction lets go gently (the simulator's does): every step is
        # away from the surface, and none is longer than 0.1 nm
        assert max(asked) <= start + 1e-12
        assert all(b <= a + 1e-12 for a, b in zip(asked, asked[1:]))
        step_v = worker.EDGE_STEP_NM / cfg.cal.piezo_nm_per_volt
        assert min(np.diff(asked)) >= -step_v - 1e-12
        went = (start - rig.piezo_v) * cfg.cal.piezo_nm_per_volt
        assert 0.0 < went < 12.0
        g1, best = worker._look()
        assert worker.AIM_G0 <= best and g1 <= nc.EDGE_G0  # a tenth of G0 and under
        assert abs(rig.piezo_nm - SURFACE_NM) < 0.5        # right at the surface
        said = _last(worker, "status")
        assert said["level"] == "ok" and said["text"].startswith(
            f"at the edge of contact: retracted {went:.1f} nm to ")
        # pressed again there, it says so and stays
        at = rig.piezo_v
        worker.cmd_edge()
        said = _last(worker, "status")
        assert said["level"] == "ok" and said["text"].startswith(
            "already at the edge of contact: G = ")
        assert said["text"].endswith(". Now Record") and rig.piezo_v == at
        # a junction that will not let go: it gives up after 30 nm and says so
        worker.cmd_piezo_approach()
        _surface(rig, rig.piezo_nm - 500.0)                # pressed far in
        start = rig.piezo_v
        worker.cmd_edge()
        said = _last(worker, "status")
        assert said["level"] == "warn" and said["text"].startswith(
            "still closed: retracted 30.0 nm to ")
        assert "(contact). Press Find the edge again" in said["text"]
        assert (start - rig.piezo_v) * cfg.cal.piezo_nm_per_volt == pytest.approx(30.0, abs=0.11)
        assert _fits(worker)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_find_the_edge_comes_back_for_a_tunnelling_current(ap, nc, tmp_path, monkeypatch):
    """A gold contact lets go all at once: the neck breaks and the gap is at
    once wider than a tunnelling current reaches. Find the edge then comes
    back toward the surface, a step at a time, until there is one, and no
    further. (The simulator's junction lets go gently, so the break is made
    here: the surface jumps back 0.45 nm when the junction first opens.)"""
    cfg = _cfg()
    guard, rig, shake, worker = _session(ap, nc, cfg, tmp_path)
    try:
        shake.shake_nm = 0.0                       # a still tip: a step reads the gap
        worker.cmd_zero()
        worker.cmd_piezo_approach()
        start = rig.piezo_v
        look, seen = worker._look, []

        def snapping(piezo_v=None):
            g1, best = look(piezo_v)
            if not seen and g1 <= nc.EDGE_G0:
                rig._session.move_surface(0.45)
                g1, best = look()
            if piezo_v is not None and g1 <= nc.EDGE_G0:       # after a step
                seen.append((rig.piezo_v, best))
            return g1, best
        monkeypatch.setattr(worker, "_look", snapping)
        worker.cmd_edge()
        where = [v for v, _g in seen]
        assert seen[0][1] < 1e-4                           # open, all at once
        assert len(seen) >= 3 and where[0] == min(where)   # the furthest it went
        assert all(b > a for a, b in zip(where, where[1:]))     # then only closer
        step_v = worker.EDGE_STEP_NM / cfg.cal.piezo_nm_per_volt
        assert max(np.diff(where)) <= step_v + 1e-12       # a step at a time
        assert all(g < worker.AIM_G0 for _v, g in seen[:-1])    # until there is one
        assert worker.AIM_G0 <= seen[-1][1] <= nc.EDGE_G0
        assert where[0] < rig.piezo_v < start              # and not back to the contact
        said = _last(worker, "status")
        assert said["level"] == "ok" and "(tunnelling). Now Record" in said["text"]
        assert said["text"].startswith("at the edge of contact: retracted ")
        told = [p["text"] for k, p in list(worker.events.queue) if k == "status"]
        assert told[-3].startswith("retracting from the contact in steps of 0.1 nm")
        assert told[-2].startswith("it let go all at once (G = ")
        assert "coming back in steps of 0.1 nm for a tunnelling current" in told[-2]
        assert _fits(worker)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


@pytest.mark.parametrize("phase", range(8))
def test_a_tip_that_shakes_a_little_ends_clear_of_the_contact(ap, nc, tmp_path, phase):
    """One look is 5 ms, and a tip that is being shaken is closer in one
    look than in the next. Wherever in its swing the tip is when the
    junction first reads open, Find the edge ends where the whole swing is
    clear of the contact, so the record is a tunnelling current throughout
    and the line has its size. (With a single look it ended, one time in
    seven, where the tip still touched once a swing.)"""
    cfg = _cfg2() if phase % 2 else _cfg()
    guard, rig, shake, worker = _session(ap, nc, cfg, tmp_path)
    try:
        shake.samples = phase * 667                # an eighth of a swing each
        _surface(rig, SURFACE_NM + 0.37 * phase)   # and where the approach lands
        worker.cmd_zero()
        worker.cmd_piezo_approach()
        worker.cmd_edge()
        said = _last(worker, "status")
        assert said["level"] == "ok", said["text"]
        assert said["text"].startswith("at the edge of contact: retracted ")
        assert said["text"].endswith("(tunnelling). Now Record")
        for _ in range(3):
            seen = worker._watch()
            assert seen.word == "tunnelling" and seen.high <= nc.CLOSED_G0
        worker.cmd_record(4.0)
        rec = _last(worker, "noise")
        key = "i2" if phase % 2 else "i1"
        result = nc.analyse(rec["pieces"], rec["rate"], key, break_g0=rec["break_g0"])
        assert result["shares"][1] > 0.99
        top = result["peaks"][0]
        assert top["hz"] == pytest.approx(7.5, abs=0.02)
        assert top["pm"] == pytest.approx(20.0, rel=0.05)
        assert _fits(worker)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_junction_that_is_shaken_open_and_shut_is_called_that(ap, nc, tmp_path):
    """A tip shaken by more than a tunnelling current reaches: in contact
    in one look, open in the next. Find the edge moves nothing then (no
    step of the piezo mends it) and says what it sees; the record still
    has the frequency in it, and no picometres."""
    cfg = _cfg()
    guard, rig, shake, worker = _session(ap, nc, cfg, tmp_path)
    try:
        shake.shake_nm = 1.0                               # a nanometre, at 7.5 Hz
        worker.cmd_zero()
        worker.cmd_piezo_approach()
        assert _last(worker, "status")["text"].startswith("CONTACT at ")
        # the middle of the swing right at the surface: half in, half out
        _surface(rig, rig.piezo_nm)
        at = rig.piezo_v
        worker.cmd_edge()
        said = _last(worker, "status")
        assert said["level"] == "warn" and said["text"].startswith(
            f"opens and closes by itself at {at:.4f} V: closed in ")
        assert " of 6 looks (G " in said["text"] and said["text"].endswith(
            "The tip shakes by more than the tunnelling range. Record as it is: "
            "the frequencies will be right")
        assert rig.piezo_v == at                           # nothing moved
        seen = worker._watch()
        assert 0 < seen.words.count("contact") < 6 and "open" in seen.words
        assert seen.chopping and seen.clear and seen.word == "contact"
        worker.cmd_record(16.0)
        rec = _last(worker, "noise")
        result = nc.analyse(rec["pieces"], rec["rate"], "i1", break_g0=rec["break_g0"])
        o, t, c = result["shares"]
        assert o > 0.2 and c > 0.2 and t < 0.5             # mostly one or the other
        top = result["peaks"][0]
        assert top["hz"] == pytest.approx(7.5, abs=0.02) and top["pm"] is None
        assert all(p["pm"] is None for p in result["peaks"])
        assert any(line.startswith("In and out of tunnelling: the frequencies are "
                                   "right") for line in nc.report(result))
        # a still tip in contact is not that: every look is closed
        shake.shake_nm = 0.0
        worker.cmd_step(+3.0)
        seen = worker._watch()
        assert seen.words == ["contact"] * 6 and seen.chopping == ""
        assert seen.middle > 1.0 and seen.high > 1.0 and not seen.clear
        assert _fits(worker)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_find_the_edge_says_when_it_ends_open(ap, nc, tmp_path, monkeypatch):
    """Two ways to end with the junction open. With steps too coarse for
    the tunnelling range (the card's own step can be: 0.33 nm at a
    micrometre to the volt) it is open on one step and closed on the next:
    no place in between. And when the tip has changed, there is no current
    even where the contact was."""
    cfg = _cfg()
    guard, rig, shake, worker = _session(ap, nc, cfg, tmp_path)
    try:
        shake.shake_nm = 0.0
        worker.cmd_zero()
        worker.cmd_piezo_approach()
        start = rig.piezo_v
        pressed_in = rig.piezo_nm - rig._session.surface_nm
        assert 0.0 < pressed_in < 5.5
        # one step from the contact to half a nanometre off the surface
        monkeypatch.setattr(worker, "EDGE_STEP_NM", pressed_in + 0.5)
        asked = []
        hold = rig.hold

        def watched(piezo_v=None, bias_v=None, n_samples=None):
            asked.append(rig.piezo_v if piezo_v is None else piezo_v)
            return hold(piezo_v=piezo_v, bias_v=bias_v, n_samples=n_samples)
        monkeypatch.setattr(rig, "hold", watched)
        worker.cmd_edge()
        said = _last(worker, "status")
        assert said["level"] == "warn" and said["text"].startswith(
            "no place in between here: retracted ")
        assert "(open), and one step closer it is closed" in said["text"]
        assert max(asked) <= start + 1e-12                 # never past the contact
        low = start - (pressed_in + 0.5) / cfg.cal.piezo_nm_per_volt
        assert rig.piezo_v == pytest.approx(low, abs=1e-9)
        # out, back in to the contact, and out again
        moves = [v for v, w in zip(asked[1:], asked) if abs(v - w) > 1e-12]
        assert moves == pytest.approx([low, start, low], abs=1e-9)
        # the tip has changed: the surface is 50 nm further away than it was
        monkeypatch.setattr(worker, "EDGE_STEP_NM", 0.1)
        monkeypatch.setattr(rig, "hold", hold)
        worker.cmd_piezo_approach()
        start = rig.piezo_v
        look, done = worker._look, []

        def losing(piezo_v=None):
            g1, best = look(piezo_v)
            if not done and g1 <= nc.EDGE_G0:
                done.append(True)
                rig._session.move_surface(50.0)
                g1, best = look()
            return g1, best
        monkeypatch.setattr(worker, "_look", losing)
        worker.cmd_edge()
        said = _last(worker, "status")
        assert said["level"] == "warn" and said["text"].startswith(
            "open again where the contact was: retracted 0.")
        assert said["text"].endswith("The tip has changed: press Approach again")
        # it came back to within a step of the contact, and not past it
        assert start - 0.1 / cfg.cal.piezo_nm_per_volt < rig.piezo_v <= start + 1e-12
        assert _fits(worker)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_at_the_bottom_of_the_range_the_screw_has_to_turn_back(ap, nc, tmp_path):
    cfg = _cfg()
    guard, rig, shake, worker = _session(ap, nc, cfg, tmp_path)
    try:
        # contact a few nanometres up: no room under it
        _surface(rig, 3.0)
        worker.cmd_piezo_approach()
        said = _last(worker, "status")
        assert said["level"] == "warn" and said["text"].startswith("CONTACT at ")
        assert said["text"].endswith(
            "That is at the bottom of the piezo's range, with no room to retract: "
            "turn the screw back a little, then Approach again")
        # the screw went too far: in contact with the piezo all the way down
        worker.cmd_goto(0.0)
        _surface(rig, -2.0)
        worker.cmd_edge()
        said = _last(worker, "status")
        assert said["level"] == "warn" and said["text"].startswith(
            "still closed with the piezo at the bottom of its range: retracted 0.0 nm")
        assert said["text"].endswith(
            "Turn the screw back a little, then Approach again")
        assert rig.piezo_v == 0.0
        assert _fits(worker)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_the_zero_at_the_start_is_not_taken_from_a_contact(ap, nc, tmp_path):
    """The window's first command measures the amplifier's zero, as
    Calibrate zero does, but not through a closed junction."""
    cfg = _cfg()
    guard, rig, shake, worker = _session(ap, nc, cfg, tmp_path)
    try:
        worker.cmd_begin()
        assert _last(worker, "status")["text"].startswith("preamp zero ")
        assert len([1 for k, _p in list(worker.events.queue) if k == "zero"]) == 1
        zero = cfg.cal.current_zero_v
        worker.cmd_bias()                                  # back on, after the zero
        logged = len(worker.mon.cycle.rec_t)
        _surface(rig, -2.0)                                # in contact at 0 V
        worker.cmd_begin()
        said = _last(worker, "status")
        assert said["level"] == "warn" and said["text"].startswith(
            "the junction is closed at the start (G = ")
        assert "the amplifier's zero was NOT measured" in said["text"]
        assert cfg.cal.current_zero_v == zero
        assert len([1 for k, _p in list(worker.events.queue) if k == "zero"]) == 1
        assert len(worker.mon.cycle.rec_t) == logged       # a quiet look
        assert _fits(worker)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_with_two_channels_the_tunnelling_current_is_channel_2(ap, nc, tmp_path):
    """The new rig's amplifier has two outputs. A tunnelling current of a
    few hundred nanoamps is a few millivolts on channel 1 and volts on
    channel 2, so the junction is read from channel 2 while that is below
    its rail, and from channel 1 above."""
    # sample by sample, the channel that reads it best
    piece = {"i1": np.array([1.0, 2.0, 3.0]), "i2": np.array([10.0, 20.0, 30.0]),
             "railed2": np.array([False, True, False])}
    assert nc.best_current(piece).tolist() == [10.0, 2.0, 30.0]
    assert nc.best_current({"i1": piece["i1"]}).tolist() == [1.0, 2.0, 3.0]
    cfg = _cfg2()
    guard, rig, shake, worker = _session(ap, nc, cfg, tmp_path)
    try:
        _to_the_edge(worker)
        assert "(tunnelling). Now Record" in _last(worker, "status")["text"]
        worker.cmd_record(8.0)
        rec = _last(worker, "noise")
        assert set(rec["pieces"][0]) == {"i1", "i2", "railed2", "v", "z"}
        assert not rec["pieces"][0]["railed2"].any()
        two = nc.analyse(rec["pieces"], rec["rate"], "i2", break_g0=rec["break_g0"])
        assert two["railed"] == 0.0 and two["shares"][1] > 0.99
        top = two["peaks"][0]
        assert top["hz"] == pytest.approx(7.5, abs=0.02)
        assert top["pm"] == pytest.approx(20.0, rel=0.05)
        assert two["mean"] == pytest.approx(
            float(np.mean([p["i2"].mean() for p in rec["pieces"]])))
        assert 10.0 < two["mean"] < 800.0                  # nA: volts on channel 2
        # the gap is channel 2's: channel 1 can read anything
        gap = nc.analyse(rec["pieces"], rec["rate"], "gap", break_g0=rec["break_g0"])
        blind = [dict(p, i1=np.zeros_like(p["i1"])) for p in rec["pieces"]]
        for p in blind:
            del p["gap"], p["g0"]
        same = nc.analyse(blind, rec["rate"], "gap", break_g0=rec["break_g0"])
        assert np.allclose(same["amp"], gap["amp"]) and same["shares"] == gap["shares"]
        assert gap["peaks"][0]["amp"] == pytest.approx(20.0, rel=0.05)
        # the words go by both: channel 1 for contact, the best for open
        assert worker.word_for(40.0, 40.0) == "contact"
        assert worker.word_for(0.3, 0.3) == "tunnelling"
        assert worker.word_for(2e-3, 1e-5) == "open"       # channel 1's noise, no current
        assert worker.word_for(1e-5, 2e-2) == "tunnelling"
        assert worker.word_for(float("inf")) == "contact"
        # A contact at 0.2 V of bias is 1.9 uA through this rig's series
        # resistor: channel 2 is at its rail, and the record says so.
        worker.cmd_step(+3.0)
        cfg.ramp.bias_v, worker.bias_dirty = 0.2, True
        worker.cmd_record(4.0)
        rec = _last(worker, "noise")
        assert rec["bias_mv"] == pytest.approx(200.0)
        assert rec["pieces"][0]["railed2"].all()
        closed = nc.analyse(rec["pieces"], rec["rate"], "i2", break_g0=rec["break_g0"])
        assert closed["railed"] == 1.0 and closed["shares"][2] > 0.99   # by channel 1
        text = nc.report(closed)
        assert any(line.startswith("CLOSED nearly all the time") for line in text)
        assert ("Channel 2 was at its rail 100% of the time: its spectrum is cut "
                "off there. Look at channel 1.") in text
        assert nc.analyse(rec["pieces"], rec["rate"], "i1",
                          break_g0=rec["break_g0"])["railed"] == 0.0
        assert _fits(worker)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_record_moves_nothing_and_stop_keeps_what_was_taken(ap, nc, tmp_path, monkeypatch):
    cfg = _cfg()
    guard, rig, shake, worker = _session(ap, nc, cfg, tmp_path)
    try:
        _to_the_edge(worker)
        at, logged = rig.piezo_v, len(worker.mon.cycle.rec_t)
        grabs = []
        grab = worker._grab

        def counted(n):
            grabs.append(n)
            if len(grabs) == 3:
                worker.stop_flag.set()                 # Stop, during the third piece
            return grab(n)
        monkeypatch.setattr(worker, "_grab", counted)
        worker.cmd_record(16.0)
        assert grabs == [160_000] * 3                  # 4 s at 40 kHz, three of four
        assert rig.piezo_v == at                       # the piezo was not touched
        assert len(worker.mon.cycle.rec_t) == logged   # and pullout's log not filled
        said = _last(worker, "status")
        assert said["text"].startswith("recorded 3 x 4 s at ") and "stopped early" in said["text"]
        assert len(_last(worker, "noise")["pieces"]) == 3
        # each piece was shown as it came
        shown = [p for k, p in list(worker.events.queue) if k == "scope"]
        assert [(p["piece"], p["of"]) for p in shown] == [(1, 4), (2, 4), (3, 4)]
        # a time that is no time is refused
        worker.stop_flag.clear()
        for nonsense in ("long", 0.0, 3.9, 121.0, float("nan")):
            worker.cmd_record(nonsense)
            said = _last(worker, "status")
            assert said["level"] == "bad" and said["text"] == (
                "Record: the time is a number of seconds, 4 to 120 (it is taken "
                "in pieces of 4 s)")
        assert len(grabs) == 3
        assert _fits(worker)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_an_open_and_a_closed_junction_are_called_what_they_are(ap, nc, tmp_path):
    cfg = _cfg()
    guard, rig, shake, worker = _session(ap, nc, cfg, tmp_path)
    try:
        worker.cmd_zero()
        worker.cmd_record(4.0)                             # the piezo at 0 V: far away
        rec = _last(worker, "noise")
        far = nc.analyse(rec["pieces"], rec["rate"], "i1", break_g0=rec["break_g0"])
        assert far["shares"][0] > 0.9
        assert any(line.startswith("OPEN nearly all the time") for line in nc.report(far))
        worker.cmd_piezo_approach()                        # pressed into contact
        worker.cmd_record(4.0)
        rec = _last(worker, "noise")
        closed = nc.analyse(rec["pieces"], rec["rate"], "i1", break_g0=rec["break_g0"])
        assert closed["shares"][2] > 0.9
        assert any(line.startswith("CLOSED nearly all the time")
                   for line in nc.report(closed))
        assert all(p["pm"] is None for p in closed["peaks"])   # no gap to read there
        assert worker.word_for(40.0) == "contact" and worker.word_for(1e-2) == "tunnelling"
        assert worker.word_for(1e-5) == "open"
        assert _fits(worker)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_pullouts_words_are_fitted_to_this_window(ap, nc, tmp_path):
    """pullout's Approach ends on words about pullout's own window. Here the
    next thing to do is Find the edge. (If pullout's wording changes, this
    is where it shows.)"""
    cfg = _cfg()
    guard, rig, shake, worker = _session(ap, nc, cfg, tmp_path)
    try:
        worker.cmd_piezo_approach()
        said = _last(worker, "status")["text"]
        assert said.startswith("CONTACT at ") and said.endswith(
            "The piezo stays there. Now Find the edge")
        worker.cmd_piezo_approach()
        said = _last(worker, "status")["text"]
        assert said.startswith("already in contact at ") and said.endswith(
            "nothing to approach. Now Find the edge")
        for text in (p["text"] for k, p in list(worker.events.queue) if k == "status"):
            assert "Start N" not in text and "fine slider" not in text
        assert _fits(worker)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_spectrum_is_saved_for_excel_and_comes_back_as_a_reference(ap, nc, tmp_path):
    cfg = _cfg()
    guard, rig, shake, worker = _session(ap, nc, cfg, tmp_path)
    try:
        _to_the_edge(worker)
        worker.cmd_record(4.0)
        rec = _last(worker, "noise")
        result = nc.analyse(rec["pieces"], rec["rate"], "i1", break_g0=rec["break_g0"])
        path = nc.save_spectrum(tmp_path / "noise", "plate on 4 bungees!", result,
                                {"piezo_v": "0.2783", "config": "stage.json",
                                 "when": rec["when"]})
        assert path.parent == tmp_path / "noise"
        assert path.name.startswith("noise_") and path.name.endswith(
            "_plate_on_4_bungees__i1.csv")
        text = path.read_text().splitlines()
        assert text[0] == "# name: plate on 4 bungees!"
        assert "# unit: nA" in text and "# config: stage.json" in text
        head = next(i for i, line in enumerate(text) if not line.startswith("#"))
        assert text[head] == "frequency_hz,amplitude_nA"
        assert text[head + 1] == "0.0000,0" and text[head + 2].startswith("0.2500,")
        assert float(text[-1].split(",")[0]) == nc.TOP_HZ          # up to 5 kHz
        back = nc.load_spectrum(path)
        assert back["name"] == "plate on 4 bungees!" and back["unit"] == "nA"
        assert back["signal"] == "current ch 1 (nA)"
        keep = result["freqs"] <= nc.TOP_HZ
        assert np.allclose(back["freqs"], result["freqs"][keep], atol=1e-4)
        assert np.allclose(back["amp"], result["amp"][keep], rtol=1e-5)
        # loaded, it is a reference like any other: the record against itself
        same = nc.analyse(rec["pieces"], rec["rate"], "i1", break_g0=rec["break_g0"],
                          reference=back)
        assert all(p["in_reference"] for p in same["peaks"])
        # a reference of another signal is not compared at all
        gap = nc.analyse(rec["pieces"], rec["rate"], "gap", break_g0=rec["break_g0"],
                         reference=back)
        assert not any(p["in_reference"] for p in gap["peaks"])
        with pytest.raises(ValueError, match="holds no spectrum"):
            (tmp_path / "empty.csv").write_text("# name: nothing\n")
            nc.load_spectrum(tmp_path / "empty.csv")
        assert _fits(worker)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_the_version_is_the_repos(ap, nc):
    assert nc.__version__ == ap.__version__ == "v75"


def test_a_card_another_program_holds_is_said_in_two_lines(tmp_path):
    """pullout still open: the card refuses, at length. noisecheck says so
    in two lines and ends, without a traceback."""
    _display()
    code = (
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import pullout, noisecheck\n"
        "def held(cfg):\n"
        "    raise RuntimeError('The specified resource is reserved.\\n"
        "Task Name: _unnamedTask<0>\\nStatus Code: -50103')\n"
        "pullout.open_rig = held\n"
        "raise SystemExit(noisecheck.main(['--simulate', '--out', sys.argv[2]]))\n")
    res = subprocess.run([sys.executable, "-c", code, str(ROOT), str(tmp_path / "n")],
                         capture_output=True, text=True, timeout=120, cwd=ROOT)
    assert res.returncode == 1, res.stderr[-2000:]
    assert "Traceback" not in res.stderr and "Status Code" not in res.stderr
    assert ("could not open the card: RuntimeError: The specified resource is "
            "reserved.") in res.stderr
    assert "Only one program can have the card" in res.stderr
    assert not (tmp_path / "n").exists()


def test_a_window_that_fails_still_parks_the_outputs(tmp_path):
    """Whatever happens to the window, the worker is ended and the card is
    closed (which parks the outputs)."""
    _display()
    code = (
        "import sys, threading\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import pullout, noisecheck\n"
        "parked, close = [], pullout.close_rig\n"
        "def spy(guard, rig):\n"
        "    parked.append(rig.piezo_v)\n"
        "    return close(guard, rig)\n"
        "pullout.close_rig = spy\n"
        "def broken(*a, **k):\n"
        "    raise RuntimeError('no window today')\n"
        "noisecheck._window = broken\n"
        "try:\n"
        "    noisecheck.main(['--simulate', '--out', sys.argv[2]])\n"
        "except RuntimeError as exc:\n"
        "    print('raised:', exc)\n"
        "print('parked:', parked)\n"
        "print('workers:', [t.name for t in threading.enumerate()"
        " if t.name == 'rig-worker'])\n")
    res = subprocess.run([sys.executable, "-c", code, str(ROOT), str(tmp_path / "n")],
                         capture_output=True, text=True, timeout=120, cwd=ROOT)
    assert res.returncode == 0, res.stderr[-2000:]
    assert res.stdout.splitlines() == ["raised: no window today", "parked: [0.0]",
                                       "workers: []"]


# -- the window ----------------------------------------------------------------------

def test_the_window_runs_its_whole_path_and_saves(tmp_path):
    """noisecheck.py on the simulated card, closing itself: its self-test
    approaches, finds the edge, records, saves, keeps that as the reference
    and records again. Nothing may leave a traceback, and the saved list
    must have the shake in it."""
    _display()
    cfg = _cfg2()                      # two channels: the light and the list are ch 2's
    path = tmp_path / "stage.json"
    cfg.to_json(path)
    res = subprocess.run([sys.executable, str(ROOT / "noisecheck.py"), "--simulate",
                          "--config", str(path), "--out", str(tmp_path / "noise"),
                          "--autoclose", "8"],
                         capture_output=True, text=True, timeout=180, cwd=ROOT)
    assert res.returncode == 0, res.stderr[-3000:]
    assert "Traceback" not in res.stderr, res.stderr[-3000:]
    saved = sorted(p.name for p in (tmp_path / "noise").iterdir())
    assert len(saved) == 3 and [Path(n).suffix for n in saved] == [".csv", ".png", ".txt"]
    listing = (tmp_path / "noise" / saved[2]).read_text()
    assert "current ch 2 (nA): 2 pieces of 4 s averaged, lines 0.25 Hz apart" in listing
    assert all(n.endswith(("_self_test_i2.csv", "_self_test_i2.png", "_self_test_i2.txt"))
               for n in saved)
    assert "     7.50" in listing and "20 pm" in listing and "mains" in listing


# The window's own buttons, pressed from inside (as in test_v72_piezo).
_DRIVE = r"""
import os, sys, time, threading, traceback
root_dir, cfg_path, out_dir = sys.argv[1:4]
sys.path.insert(0, root_dir)
import tkinter as tk
import pullout, noisecheck as nc

watchdog = threading.Timer(150, lambda: (print("WATCHDOG", flush=True), os._exit(3)))
watchdog.daemon = True
watchdog.start()
said, errors, W, sent = [], [], {}, []
orig_send, orig_status = pullout.Worker.send, nc.NoiseWorker.status
def send(self, *command):
    W["w"] = self
    sent.append(command[0])
    return orig_send(self, *command)
def status(self, text, *a, **k):
    said.append(text)
    return orig_status(self, text, *a, **k)
pullout.Worker.send, nc.NoiseWorker.status = send, status
tk.Tk.report_callback_exception = lambda self, e, v, tb: errors.append(
    "".join(traceback.format_exception(e, v, tb))[-600:])

def script(root):
    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            root.update()
            time.sleep(0.01)
    def idle(timeout=60):
        pump(0.3)
        end = time.time() + timeout
        quiet = ("scope", "monitor", "noop")
        while time.time() < end:
            w = W["w"]
            if (not w.busy or w.current in quiet) and \
                    all(c[0] in quiet for c in list(w.commands.queue)):
                break
            pump(0.05)
        pump(0.8)
    def walk(widget):
        yield widget
        for child in widget.winfo_children():
            yield from walk(child)
    pump(2.0)
    widgets = list(walk(root))
    def button(text):
        return next(w for w in widgets if w.winfo_class() == "TButton"
                    and str(w.cget("text")).strip() == text)
    def entry_beside(widget, nth=0):
        return str([c for c in widget.master.winfo_children()
                    if c.winfo_class() == "TEntry"][nth].cget("textvariable"))
    listing = next(w for w in widgets if w.winfo_class() == "Text")
    light = next(w for w in widgets if w.winfo_class() == "Label"
                 and str(w.cget("text")).strip() in ("--", "OPEN", "TUNNELLING", "CONTACT"))
    box = next(w for w in widgets if w.winfo_class() == "TCombobox")
    status = next(w for w in widgets if w.winfo_class() == "Label"
                  and int(w.cget("height")) == 4)
    def lines():
        return listing.get("1.0", "end").strip().splitlines()
    def look(tag):
        print(f"{tag}: {str(light.cget('text')).strip()} | {said[-1][:70] if said else ''}",
              flush=True)
    idle()
    look("start")
    button("Approach").invoke(); idle()
    look("approach")
    button("Find the edge").invoke(); idle()
    look("edge")
    record = button("Record")
    root.setvar(entry_beside(record), "8")
    record.invoke(); idle()
    look("record")
    print("list:", " / ".join(lines()[:2]), flush=True)
    print("line:", next((l for l in lines() if l.strip().startswith("7.5")), "none"),
          flush=True)
    box.set(nc.SIGNALS["gap"]); box.event_generate("<<ComboboxSelected>>"); pump(0.5)
    print("gap:", lines()[0], "/", next((l for l in lines()
                                         if l.strip().startswith("7.5")), "none"), flush=True)
    box.set(nc.SIGNALS["i1"]); box.event_generate("<<ComboboxSelected>>"); pump(0.5)
    button("Keep as reference").invoke(); pump(0.5)
    print("kept:", next((l for l in lines() if l.strip().startswith("7.5")), "none"),
          flush=True)
    ref = next(w for w in widgets if w.winfo_class() == "TLabel"
               and str(w.cget("text")).startswith("reference (grey)"))
    print("ref:", ref.cget("text"), flush=True)
    box.set(nc.SIGNALS["gap"]); box.event_generate("<<ComboboxSelected>>"); pump(0.5)
    print("ref in pm:", ref.cget("text"), "/",
          next((l for l in lines() if l.strip().startswith("7.5")), "none"), flush=True)
    box.set(nc.SIGNALS["i1"]); box.event_generate("<<ComboboxSelected>>"); pump(0.5)
    button("Clear").invoke(); pump(0.5)
    print("cleared:", next((l for l in lines() if l.strip().startswith("7.5")), "none"),
          flush=True)
    step = button("Step apart")
    root.setvar(entry_beside(step), "200")
    step.invoke(); idle()
    look("far away")
    root.setvar(entry_beside(record), "nonsense")
    record.invoke(); pump(0.3)
    print("nonsense:", status.cget("text")[:60], flush=True)
    button("Save").invoke(); pump(0.5)
    print("saved:", status.cget("text")[:20], sorted(os.listdir(out_dir)) if
          os.path.isdir(out_dir) else [], flush=True)
    print("idle:", sorted(set(sent[-3:])), flush=True)
    next(w for w in widgets if w.winfo_class() == "TCheckbutton").invoke()
    pump(1.6)
    print("idle, no live picture:", sorted(set(sent[-3:])),
          str(light.cget("text")).strip(), flush=True)
    print("errors:", len(errors), errors[:2], flush=True)

def driver(root, n=0):
    try:
        script(root)
    except Exception:
        traceback.print_exc(file=sys.stdout)
    sys.stdout.flush()
tk.Tk.mainloop = driver
rc = nc.main(["--simulate", "--config", cfg_path, "--out", out_dir])
print("main returned", rc, flush=True)
os._exit(0)
"""


def test_the_buttons_of_the_real_window(tmp_path):
    """Approach, Find the edge, Record, the signal box, Keep as reference,
    Clear, Step apart, a time that is no number, Save: pressed in the real
    window, with what the light, the status line and the list then say."""
    _display()
    cfg = _cfg()
    path = tmp_path / "stage.json"
    cfg.to_json(path)
    res = subprocess.run([sys.executable, "-c", _DRIVE, str(ROOT), str(path),
                          str(tmp_path / "noise")],
                         capture_output=True, text=True, timeout=300, cwd=ROOT)
    out = res.stdout
    assert res.returncode == 0 and "main returned" in out, out[-3000:] + res.stderr[-3000:]
    assert "Traceback" not in out and "WATCHDOG" not in out, out[-3000:]
    lines = dict(line.split(": ", 1) for line in out.splitlines() if ": " in line)
    assert lines["errors"].startswith("0 "), out[-3000:]
    assert lines["start"].startswith("OPEN | ")
    assert lines["approach"].startswith("CONTACT | CONTACT at ")
    assert lines["edge"].startswith("TUNNELLING | at the edge of contact: retracted ")
    assert lines["record"].startswith("TUNNELLING | recorded 2 x 4 s at ")
    assert lines["list"].startswith("current ch 1 (nA): 2 pieces of 4 s averaged, lines "
                                    "0.25 Hz apart / the junction was open 0%, "
                                    "tunnelling 100%, closed 0%")
    row = lines["line"].split()
    assert row[0] == "7.50" and row[2].endswith("%") and row[3:5] == ["20", "pm"]
    assert lines["gap"].startswith("gap (pm): 2 pieces of 4 s averaged")
    assert lines["gap"].split(" / ")[1].split()[:2] == ["7.50", "20"]
    assert " also " in lines["kept"] and " also " not in lines["cleared"]
    assert lines["ref"] == "reference (grey): the record before  [current ch 1 (nA)]"
    shown, row = lines["ref in pm"].split(" / ")
    assert shown.endswith("NOT SHOWN: it is in nA, the signal on show in pm")
    assert " also " not in row                  # and not compared either
    assert lines["idle"] == "['scope']"
    assert lines["idle, no live picture"] == "['monitor'] OPEN"
    assert lines["far away"].startswith("OPEN | ")
    assert lines["nonsense"].startswith("Record: 'nonsense' is not a number of seconds")
    assert lines["saved"].startswith("saved noise_")
    assert lines["saved"].count(".csv") == 1 and lines["saved"].count(".png") == 1
