"""pullout v72: the piezo driver's two modes and the stage's total
displacement, the two sliders, and a move by hand that stops at contact.

Simulator only: no card. None of these tests moves a real piezo.

The numbers are the new rig's: a stage that moves 10.776 um for the 0-150 V
of its piezo. In standard mode the driver amplifies the card's 0-10 V to
those 150 V (1077.6 nm per card volt); in bypass the card's volts are the
piezo's (71.84 nm per card volt). In November 2026 the second number stood
in a config for a driver in standard mode, and every move was 15 times what
the program believed. Now the config holds the total displacement and the
mode, and the arithmetic is the program's. Whether the mode is where the
switch on the box stands is not checked: that is for the person at the rig.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stmlab.config import Calibration, ConfigError, RigConfig, validate   # noqa: E402

TOTAL_UM = 10.776
STANDARD = 1077.6          # nm per card volt: total / 10 V
BYPASS = 71.84             # nm per card volt: total / 150 V
SURFACE_NM = 300.0         # where the simulated surface is


@pytest.fixture(scope="module")
def ap():
    import pullout
    return pullout


def _cfg(mode: str = "standard", total: float | None = TOTAL_UM) -> RigConfig:
    """A one-card rig with a sense line, simulated."""
    cfg = RigConfig()
    cfg.simulate = True
    cfg.channels.sense_device, cfg.channels.ai_piezo_sense = cfg.channels.device, "ai3"
    cfg.cal.piezo_total_um, cfg.cal.piezo_mode = total, mode
    cfg.cal.apply_piezo_mode()
    return cfg


def _worker(ap, cfg, tmp_path):
    guard, rig = ap.open_rig(cfg)
    worker = ap.Worker(cfg, rig, ap.Monitor(rig), save=False, out_dir=tmp_path,
                       igor_export=False)
    return guard, rig, worker


def _surface(rig, nm: float) -> None:
    """Put the simulated surface ``nm`` up the piezo's travel, as the
    simulator's screw does: the sample moves, and the junction's memory of
    where it last broke moves with it."""
    session = rig._session
    session.move_surface(nm - session.surface_nm)


def _status(worker) -> dict:
    return [p for k, p in list(worker.events.queue) if k == "status"][-1]


def _statuses(worker) -> list[str]:
    return [p["text"] for k, p in list(worker.events.queue) if k == "status"]


# -- the conversion ---------------------------------------------------------------

def test_one_total_displacement_gives_both_modes():
    cal = Calibration(piezo_total_um=TOTAL_UM)                 # standard is the default
    assert cal.piezo_mode == "standard"
    assert cal.piezo_nm_per_volt == pytest.approx(STANDARD)   # total / 10 V
    assert cal.sense_nm_per_volt == pytest.approx(STANDARD)   # the sense line too
    cal.piezo_mode = "bypass"
    assert cal.apply_piezo_mode()
    assert cal.piezo_nm_per_volt == pytest.approx(BYPASS)     # total / 150 V
    assert cal.sense_nm_per_volt == pytest.approx(STANDARD)   # the sensor is the same
    # the two differ by the driver's gain, and the reach of 10 V with them
    assert cal.piezo_scale("standard") / cal.piezo_scale("bypass") == pytest.approx(15.0)
    assert 10 * cal.piezo_scale("standard") == pytest.approx(10776.0)
    assert 10 * cal.piezo_scale("bypass") == pytest.approx(718.4)
    # the old rig: 62 nm per volt in bypass was a stage of 9.3 um
    assert Calibration(piezo_total_um=9.3, piezo_mode="bypass").piezo_nm_per_volt == \
        pytest.approx(62.0)


def test_a_config_without_a_total_displacement_is_as_it_always_was():
    cal = Calibration()
    assert cal.piezo_total_um is None
    assert (cal.piezo_nm_per_volt, cal.sense_nm_per_volt) == (62.0, 314.0)
    assert not cal.apply_piezo_mode()                          # nothing to derive from
    typed = Calibration(piezo_nm_per_volt=600.0, sense_nm_per_volt=590.0)
    assert (typed.piezo_nm_per_volt, typed.sense_nm_per_volt) == (600.0, 590.0)
    validate(RigConfig())                                      # and it still validates


def test_the_total_displacement_wins_over_a_typed_scale_and_travels_in_the_file():
    # the lab's json as it stood, with the two new lines added
    cfg = RigConfig.from_dict({"cal": {"piezo_nm_per_volt": 71.84,
                                       "sense_nm_per_volt": 71.84,
                                       "piezo_total_um": TOTAL_UM,
                                       "piezo_mode": "standard"}})
    assert cfg.cal.piezo_nm_per_volt == pytest.approx(STANDARD)
    assert cfg.cal.sense_nm_per_volt == pytest.approx(STANDARD)
    back = RigConfig.from_dict(cfg.to_dict())
    assert (back.cal.piezo_total_um, back.cal.piezo_mode) == (TOTAL_UM, "standard")
    assert back.cal.piezo_nm_per_volt == pytest.approx(STANDARD)
    assert RigConfig.from_dict({"cal": {"piezo_total_um": TOTAL_UM, "piezo_mode": "BYPASS"}}
                               ).cal.piezo_nm_per_volt == pytest.approx(BYPASS)


def test_the_validator_wants_the_scales_to_follow_from_the_total():
    cfg = _cfg()
    validate(cfg)
    cfg.cal.piezo_mode = "bypass"                # changed, but not applied
    with pytest.raises(ConfigError, match="apply_piezo_mode"):
        validate(cfg)
    cfg.cal.apply_piezo_mode()
    validate(cfg)
    for field, value, words in (("piezo_mode", "sideways", "standard"),
                                ("piezo_mode", " bypass", "standard"),
                                ("piezo_mode", None, "standard"),
                                ("piezo_total_um", 0.0, "positive"),
                                ("piezo_total_um", -3.0, "positive"),
                                # typing mistakes in a json: each is refused in
                                # words, none gets as far as the arithmetic
                                ("piezo_total_um", "10.776", "positive number"),
                                ("piezo_total_um", True, "positive number"),
                                ("piezo_total_um", float("inf"), "positive number"),
                                ("piezo_total_um", float("nan"), "positive number"),
                                ("piezo_drive_full_v", "150", "positive numbers"),
                                ("piezo_drive_gain", None, "positive numbers"),
                                ("piezo_drive_gain", 0, "positive numbers")):
        bad = _cfg()
        setattr(bad.cal, field, value)
        assert not bad.cal.apply_piezo_mode()    # refuses to derive from that
        with pytest.raises(ConfigError, match=words):
            validate(bad)
    # and the same through a file: the scales stay as typed, and it is refused
    typed = RigConfig.from_dict({"cal": {"piezo_nm_per_volt": 71.84,
                                         "piezo_total_um": "10.776"}})
    assert typed.cal.piezo_nm_per_volt == 71.84
    with pytest.raises(ConfigError, match="positive number"):
        validate(typed)


# -- the fine slider's window ------------------------------------------------------

def test_the_fine_window_sits_on_round_numbers_around_the_piezo(ap):
    window = ap.fine_window
    assert window(7.9868, 0.5, 0.0, 10.0) == (7.5, 8.5)       # contact at 8 V
    assert window(5.0, 0.5, 0.0, 10.0) == (4.5, 5.5)
    # at the ends of the piezo's range it is cut off (v73), not slid along:
    # x +/- 0.5 V is what it shows, as far as the piezo can go
    assert window(0.0, 0.5, 0.0, 10.0) == (0.0, 0.5)
    assert window(0.2934, 0.5, 0.0, 10.0) == (0.0, 0.8)
    assert window(9.9, 0.5, 0.0, 10.0) == (9.4, 10.0)
    # a narrower one, and one wider than the range
    assert window(3.21, 0.1, 0.0, 10.0) == (3.1, 3.3)
    assert window(3.0, 6.0, 0.0, 10.0) == (0.0, 10.0)
    assert window(3.0, 0.0, 0.0, 10.0) == (0.0, 10.0)
    for v in np.linspace(0.0, 10.0, 41):
        low, high = window(v, 0.5, 0.0, 10.0)
        assert 0.0 <= low <= v <= high <= 10.0 and 0.5 <= high - low <= 1.0 + 1e-9
        if 0.6 <= v <= 9.4:
            assert high - low == pytest.approx(1.0)


# -- a move made by hand ------------------------------------------------------------

def test_a_move_by_hand_toward_the_surface_stops_at_contact(ap, tmp_path):
    cfg = _cfg()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        assert SURFACE_NM / STANDARD == pytest.approx(0.2784, abs=1e-4)   # the surface, in V
        worker.cmd_goto(0.2)                                   # 215 nm: short of it
        assert rig.piezo_v == pytest.approx(0.2) and rig.state is not ap.RigState.ENGAGED
        assert "STOPPED" not in _status(worker)["text"]
        worker.cmd_goto(1.0)                                   # 1078 nm: far through it
        # it stopped where the junction closed: a little over one 5 nm piece in
        assert SURFACE_NM < rig.piezo_nm <= SURFACE_NM + 1.25 * 5.0 + 1.0
        assert rig.state is ap.RigState.ENGAGED
        said = _status(worker)
        assert said["text"].startswith("STOPPED AT CONTACT") and said["level"] == "warn"
        assert "in contact" in said["text"]
        # away from the surface there is nothing to look out for: at once
        worker.cmd_goto(0.1)
        assert rig.piezo_v == pytest.approx(0.1) and rig.state is not ap.RigState.ENGAGED
        # Step closer goes the same guarded way
        worker.cmd_goto(0.27)
        worker.cmd_step(+100.0)
        assert SURFACE_NM < rig.piezo_nm <= SURFACE_NM + 1.25 * 5.0 + 1.0
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


@pytest.mark.parametrize("mode", ["standard", "bypass"])
@pytest.mark.parametrize("speed", [50.0, 200.0, 2000.0])
def test_how_far_past_the_surface_a_move_by_hand_ends(ap, tmp_path, mode, speed):
    """Wherever in a piece the surface lies, the tip ends at most a little
    over one piece past it: the piece is played to its end, and the
    junction is read from that piece's last millisecond."""
    cfg = _cfg(mode=mode)
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        per_volt = cfg.cal.piezo_nm_per_volt
        piece = speed * worker.HAND_PIECE_S
        worker.hand_speed_nm_s = speed
        deepest = 0.0
        for short in [0.01, 0.1] + list(piece * np.linspace(0.05, 1.5, 30)):
            rig.piezo_ramp_to(0.0)
            _surface(rig, SURFACE_NM)                     # each try from a fresh surface
            rig.piezo_ramp_to((SURFACE_NM - short) / per_volt)
            worker.cmd_goto((SURFACE_NM + 12 * piece + 50.0) / per_volt)
            assert rig.state is ap.RigState.ENGAGED
            assert _status(worker)["text"].startswith("STOPPED AT CONTACT")
            past = rig.piezo_nm - rig._session.surface_nm
            # (v73: the contact current is a sign of contact too, and the
            # tunnelling current passes it 0.16 nm before the surface)
            assert past > -0.2
            deepest = max(deepest, past)
        assert deepest <= 1.15 * piece + 1.0
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_move_toward_the_surface_from_a_closed_junction_is_one_piece(ap, tmp_path):
    cfg = _cfg()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_goto(1.0)                                   # into contact
        assert rig.state is ap.RigState.ENGAGED
        at = rig.piezo_nm
        worker.cmd_goto(1.0)                                   # and asked for more
        assert rig.piezo_nm == pytest.approx(at + 5.0)         # one 5 nm piece, no more
        assert _status(worker)["text"].startswith("STOPPED AT CONTACT")
        # a step that fits in one piece is simply made, and said plainly
        worker.cmd_step(+2.0)
        assert rig.piezo_nm == pytest.approx(at + 7.0)
        said = _status(worker)
        assert said["text"].startswith("piezo ") and "in contact" in said["text"]
        assert said["level"] is None
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_the_speed_of_a_move_by_hand_is_the_size_of_its_pieces(ap, tmp_path, monkeypatch):
    cfg = _cfg()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        pieces = []
        glide = rig.piezo_glide_to

        def counted(volts, seconds):
            pieces.append((volts, seconds))
            return glide(volts, seconds)
        monkeypatch.setattr(rig, "piezo_glide_to", counted)
        worker.cmd_goto(0.2)                       # 215.52 nm at 200 nm/s: 5 nm pieces
        assert len(pieces) == 44 and all(s == pytest.approx(0.025) for _, s in pieces)
        step_nm = (pieces[1][0] - pieces[0][0]) * STANDARD
        assert step_nm == pytest.approx(5.0)
        worker.cmd_goto(0.0)
        pieces.clear()
        worker.hand_speed_nm_s = 1000.0            # 25 nm pieces
        worker.cmd_goto(0.2)
        assert len(pieces) == 9
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_stop_ends_a_move_by_hand_between_two_pieces(ap, tmp_path):
    cfg = _cfg()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.stop_flag.set()
        assert worker._approach_by_hand(0.2) == "stop"
        assert rig.piezo_v == pytest.approx(0.0)
        worker.stop_flag.clear()
        assert worker._approach_by_hand(0.05) == "there"
        assert rig.piezo_v == pytest.approx(0.05)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_voltage_that_is_not_a_number_moves_nothing(ap, tmp_path):
    cfg = _cfg()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_goto(0.1)
        for nonsense in (float("nan"), float("inf")):
            worker.cmd_goto(nonsense)
            assert rig.piezo_v == pytest.approx(0.1)
            assert _status(worker)["level"] == "bad"
        worker.cmd_step(float("nan"))
        assert rig.piezo_v == pytest.approx(0.1)
        # beyond the piezo's range is not nonsense: it goes to the end of it
        _surface(rig, 1e9)
        worker.hand_speed_nm_s = 5000.0
        worker.cmd_goto(12.0)
        assert rig.piezo_v == pytest.approx(cfg.limits.piezo_ao_max_v)
        worker.cmd_goto(-3.0)
        assert rig.piezo_v == pytest.approx(cfg.limits.piezo_ao_min_v)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


@pytest.mark.parametrize("mode", ["standard", "bypass"])
def test_a_run_runs_in_either_mode(ap, tmp_path, mode):
    cfg = _cfg(mode=mode)
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        per_volt = STANDARD if mode == "standard" else BYPASS
        worker.cmd_goto((SURFACE_NM - 10.0) / per_volt)        # close by hand first
        assert rig.piezo_nm == pytest.approx(SURFACE_NM - 10.0)
        # the simulated piezo moves what the program says it does, in either
        # mode: there is no pretend switch, and nothing checks the mode
        assert rig._session.piezo_nm == pytest.approx(rig.piezo_nm)
        worker.cmd_run(2)
        assert worker.accepted == 2 and worker.paused is None
        assert not hasattr(worker, "piezo_alarm")
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


# -- the pictures of a series of moves by hand ------------------------------------------

def test_a_snapshot_of_the_cycle_is_a_copy_of_its_own(ap, tmp_path):
    """Found by the window's self-test failing once in forty runs ("x and y
    must have same first dimension"): the window drew from the very lists
    the worker was still adding to. A series of moves by hand is one cycle,
    and a move toward the surface is many plays."""
    import threading
    cfg = _cfg()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        _surface(rig, 1e9)                         # nothing in the way
        mon = worker.mon
        worker.cmd_goto(0.05)
        snap = mon.snapshot()
        n = len(snap.rec_t)
        assert n > 0 and len(snap.rec_v) == len(snap.rec_i) == n
        worker.cmd_goto(0.1)                       # the same cycle goes on
        assert len(mon.cycle.rec_t) > n
        assert len(snap.rec_t) == len(snap.rec_v) == len(snap.rec_i) == n
        mon.mark("later")                          # and its marks are its own too
        assert "later" in mon.cycle.marks and "later" not in snap.marks
        # the readouts take the last play alone, not the series
        last = mon.last()
        assert last.last_record is mon.cycle.last_record and last.rec_t == []
        # someone drawing all the while never meets a play that is half added
        odd, stop = [], threading.Event()

        def draws():
            while not stop.is_set():
                c = mon.snapshot()
                if not (len(c.rec_t) == len(c.rec_v) == len(c.rec_i)
                        and len(c.t) == len(c.piezo_v) == len(c.sense_v)):
                    odd.append((len(c.rec_t), len(c.rec_v), len(c.rec_i)))
        reader = threading.Thread(target=draws)
        reader.start()
        try:
            worker.cmd_goto(0.4)                   # 60 pieces of 5 nm
        finally:
            stop.set()
            reader.join()
        assert odd == []
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_long_series_of_moves_by_hand_starts_a_fresh_picture(ap, tmp_path, monkeypatch):
    cfg = _cfg()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        _surface(rig, 1e9)
        mon = worker.mon
        assert mon.MAX_POINTS == 200_000           # some minutes of slow approach
        assert mon.spent()                         # nothing in it yet
        worker.cmd_goto(0.05)
        assert not mon.spent()
        monkeypatch.setattr(mon, "MAX_POINTS", 3000)
        worker.cmd_goto(1.0)                       # 205 pieces: far more than that
        assert rig.piezo_v == pytest.approx(1.0)   # the move itself is whole
        assert len(mon.cycle.rec_t) <= 3000 + 8 * 101 + 300
        assert list(mon.cycle.marks) == ["by hand"]
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


# -- Set: the mode and the total displacement, from the window --------------------------

def test_set_takes_the_piezo_to_zero_before_the_switch_is_flipped(ap, tmp_path):
    cfg = _cfg()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_goto(0.2)
        # the total displacement alone: arithmetic, nothing moves
        worker.cmd_piezo_mode("standard", 10.8)
        assert rig.piezo_v == pytest.approx(0.2)
        assert cfg.cal.piezo_nm_per_volt == pytest.approx(1080.0)
        said = _status(worker)
        assert said["level"] == "ok" and "SWITCH" not in said["text"]
        assert '"piezo_total_um": 10.8, "piezo_mode": "standard"' in said["text"]
        # the mode: to 0 V first, and it stays there
        worker.cmd_piezo_mode("bypass", 10.8)
        assert rig.piezo_v == 0.0
        assert rig.state is ap.RigState.RETRACTED
        assert cfg.cal.piezo_mode == "bypass"
        assert cfg.cal.piezo_nm_per_volt == pytest.approx(72.0)
        assert cfg.cal.sense_nm_per_volt == pytest.approx(1080.0)
        validate(cfg)                              # the scales follow
        said = _status(worker)
        assert said["level"] == "warn"
        assert said["text"].startswith("NOW PUT THE SWITCH ON THE DRIVER TO BYPASS.")
        assert "The piezo is at 0 V (it was at 0.200 V). " in said["text"]
        assert '"piezo_total_um": 10.8, "piezo_mode": "bypass"' in said["text"]
        assert len(said["text"]) < 190            # the status box shows three lines
        state = [p for k, p in list(worker.events.queue) if k == "piezo"][-1]
        assert state["mode"] == "bypass" and state["total_um"] == 10.8
        assert state["nm_per_volt"] == pytest.approx(72.0)
        assert state["reach_nm"] == pytest.approx(720.0)
        # nonsense is refused and changes nothing
        for mode, total in (("sideways", 10.8), ("standard", 0.0), ("standard", "ten"),
                            ("standard", 5000.0)):
            worker.cmd_piezo_mode(mode, total)
            assert _status(worker)["level"] == "bad"
            assert (cfg.cal.piezo_mode, cfg.cal.piezo_total_um) == ("bypass", 10.8)
        # and so is a change in the middle of a run
        worker.run_stem, worker.paused = tmp_path / "running", None
        worker.cmd_piezo_mode("standard", 10.8)
        assert "press Stop" in _status(worker)["text"] and cfg.cal.piezo_mode == "bypass"
        worker.run_stem = None
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_the_switch_is_only_flipped_at_zero_volts(ap, tmp_path):
    """The two modes agree at 0 V and nowhere else: 0 V it is, whatever the
    park position, and no change of mode where 0 V cannot be had."""
    cfg = _cfg()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        _surface(rig, 1e9)                         # nothing in the way here
        cfg.ramp.piezo_park_v = 0.5                # a park position that is not 0 V
        for start in (3.0, 0.2):                   # above the park position, and below it
            back = "standard" if cfg.cal.piezo_mode == "bypass" else "bypass"
            rig.piezo_ramp_to(start)
            worker.cmd_piezo_mode(back, TOTAL_UM)
            assert rig.piezo_v == 0.0 and cfg.cal.piezo_mode == back
        # already at 0 V: nothing to move, and it says so
        worker.cmd_piezo_mode("bypass", TOTAL_UM)
        said = _status(worker)["text"]
        assert said.startswith("NOW PUT THE SWITCH ON THE DRIVER TO BYPASS. The piezo "
                               "is at 0 V. To keep it")
        # below 0 V: going up to it would be a move toward the surface. Refused.
        cfg.limits.piezo_ao_min_v = -2.0
        rig.piezo_ramp_to(-1.0)
        worker.cmd_piezo_mode("standard", TOTAL_UM)
        said = _status(worker)
        assert said["level"] == "bad" and "NOT changed" in said["text"]
        assert "-1.000 V, below it" in said["text"]
        assert rig.piezo_v == pytest.approx(-1.0) and cfg.cal.piezo_mode == "bypass"
        assert cfg.cal.piezo_nm_per_volt == pytest.approx(BYPASS)
        # the total displacement alone is still arithmetic there
        worker.cmd_piezo_mode("bypass", 10.8)
        assert _status(worker)["level"] == "ok" and rig.piezo_v == pytest.approx(-1.0)
        # a range that does not include 0 V: no change of mode at all
        rig.piezo_ramp_to(1.0)
        cfg.limits.piezo_ao_min_v = 0.5
        worker.cmd_piezo_mode("standard", 10.8)
        said = _status(worker)
        assert said["level"] == "bad" and "does not include 0 V" in said["text"]
        assert rig.piezo_v == pytest.approx(1.0) and cfg.cal.piezo_mode == "bypass"
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_set_gives_an_old_config_its_total_displacement(ap, tmp_path):
    cfg = RigConfig()                              # 62 nm per volt, typed
    cfg.simulate = True
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        assert worker.piezo_state()["total_um"] is None
        worker.cmd_goto(1.0)
        worker.cmd_piezo_mode("bypass", 9.3)       # what 62 nm per volt is
        assert cfg.cal.piezo_nm_per_volt == pytest.approx(62.0)
        assert rig.piezo_v == 0.0                  # "standard" was only the default: retracted
        assert worker.piezo_state()["reach_nm"] == pytest.approx(620.0)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


# -- the window ------------------------------------------------------------------------

def test_the_window_runs_with_the_driver_row_and_the_two_sliders(tmp_path):
    """pullout.py on a config that knows its stage, simulated, closing
    itself. Its self-test sets the mode, narrows the fine window and makes a
    move by hand before the run; nothing may leave a traceback."""
    tk = pytest.importorskip("tkinter")
    pytest.importorskip("igor2")
    try:
        tk.Tk().destroy()
    except tk.TclError as exc:
        pytest.skip(f"no Tk display: {exc}")
    cfg = _cfg(mode="bypass", total=9.3)           # 62 nm per volt, as the smoke run expects
    path = tmp_path / "stage.json"
    cfg.to_json(path)
    res = subprocess.run([sys.executable, str(ROOT / "pullout.py"), "--simulate",
                          "--config", str(path), "--out", str(tmp_path / "data"),
                          "--autoclose", "6"],
                         capture_output=True, text=True, timeout=180, cwd=ROOT)
    assert res.returncode == 0, res.stderr[-3000:]
    assert "Traceback" not in res.stderr, res.stderr[-3000:]


# The real window, driven from inside: Tk's mainloop is replaced by a script
# that finds the Piezo box's widgets, presses, moves and releases the mouse
# on them and writes down what the window asked the worker for.
_DRIVE = r"""
import os, sys, time, threading, traceback
from pathlib import Path
root_dir, cfg_path, out_dir = sys.argv[1:4]
sys.path.insert(0, root_dir)
import tkinter as tk
import pullout as ap

watchdog = threading.Timer(150, lambda: (print("WATCHDOG", flush=True), os._exit(3)))
watchdog.daemon = True
watchdog.start()
sent, begun, said, errors, W = [], [], [], [], {}
orig_send, orig_begin, orig_status = ap.Worker.send, ap.Worker.follow_begin, ap.Worker.status
def send(self, *command):
    W["w"] = self
    if command and command[0] in ("goto", "step", "piezo_mode"):
        sent.append(command)
    return orig_send(self, *command)
def follow_begin(self, volts):
    begun.append(round(float(volts), 4))
    return orig_begin(self, volts)
def status(self, text, *a, **k):
    said.append(text)
    return orig_status(self, text, *a, **k)
ap.Worker.send, ap.Worker.follow_begin, ap.Worker.status = send, follow_begin, status
tk.Tk.report_callback_exception = lambda self, e, v, tb: errors.append(
    "".join(traceback.format_exception(e, v, tb))[-600:])

def script(root):
    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            root.update()
            time.sleep(0.01)
    def idle(timeout=40):
        pump(0.3)
        end = time.time() + timeout
        quiet = ("monitor", "ratecheck", "noop")
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
    pump(2.5)
    widgets = list(walk(root))
    scales = [w for w in widgets if w.winfo_class() == "Scale"]
    coarse = next(w for w in scales if float(w.cget("tickinterval")) > 0)   # 0..10 V
    fine = next(w for w in scales if w is not coarse and w.master is coarse.master)
    label = next(w for w in widgets if w.winfo_class() == "TLabel"
                 and str(w.cget("text")) == "fine: +/-")
    half_name = next(str(c.cget("textvariable")) for c in label.master.winfo_children()
                     if c.winfo_class() == "TEntry")
    approach = next(w for w in widgets if w.winfo_class() in ("TButton", "Button")
                    and str(w.cget("text")) == "Approach")
    speed_name = next(str(c.cget("textvariable"))
                      for c in approach.master.winfo_children()
                      if c.winfo_class() == "TEntry")
    rig = W["w"].rig
    def knob(scale):
        return float(root.getvar(str(scale.cget("variable"))))
    def knobs(tag):
        print(f"{tag}: piezo {rig.piezo_v:.4f} coarse {knob(coarse):.4f} "
              f"fine {knob(fine):.4f} window {float(fine.cget('from')):g} "
              f"{float(fine.cget('to')):g}", flush=True)
    def pixel(scale, volts=None):
        x, y = scale.coords() if volts is None else scale.coords(volts)
        return int(x), int(y)
    def under(scale, x, y):
        # the volts the slider itself says lie under that pixel
        return float(scale.tk.call(str(scale), "get", x, y))
    def tell(n_said, n_begun, was, want=None):
        # what one mouse gesture did: where the piezo went, whether that is
        # the place under the mouse, how often the worker was asked, and how
        # many lines it said
        moved = abs(rig.piezo_v - was) > 1e-9
        hit = "" if want is None else f" on the spot {abs(rig.piezo_v - want) < 1e-6}"
        lines = sum(" -> " in text for text in said[n_said:])     # "piezo a -> b V ..."
        return (f"moved {moved}{hit} asked {len(begun) - n_begun} "
                f"said {lines} piezo {rig.piezo_v:.4f}")
    def click(scale, volts=None, dx=0, mods=""):
        # the mouse down and up in one place: on the knob (volts None), dx
        # pixels beside it, or on the bar where ``volts`` is
        n_said, n_begun, was = len(said), len(begun), rig.piezo_v
        x, y = pixel(scale, volts)
        x += dx
        want = under(scale, x, y) if (volts is not None or dx) else None
        scale.event_generate(f"<{mods}ButtonPress-1>", x=x, y=y)
        pump(0.05)
        scale.event_generate(f"<{mods}ButtonRelease-1>", x=x, y=y)
        idle()
        return tell(n_said, n_begun, was, want)
    def drag(scale, volts):
        # the mouse down on the knob, the knob taken to ``volts`` in eight
        # moves, the mouse up
        n_said, n_begun, was = len(said), len(begun), rig.piezo_v
        (x0, y), (x1, _) = pixel(scale), pixel(scale, volts)
        grab = under(scale, x0, y) - knob(scale)
        scale.event_generate("<ButtonPress-1>", x=x0, y=y)
        pump(0.05)
        for i in range(1, 9):
            scale.event_generate("<B1-Motion>", x=round(x0 + (x1 - x0) * i / 8), y=y)
            pump(0.03)
        want = under(scale, x1, y) - grab
        scale.event_generate("<ButtonRelease-1>", x=x1, y=y)
        idle()
        return tell(n_said, n_begun, was, want) + f" near {abs(rig.piezo_v - volts) < 0.05}"
    root.setvar(speed_name, "2000")
    pump(0.2)
    print("click on the coarse bar at 2.0:", click(coarse, 2.0))
    knobs("after the click")
    print("drag coarse to 3.0:", drag(coarse, 3.0))
    knobs("after it")
    print("click on the coarse knob:", click(coarse))
    print("click on the fine knob:", click(fine))
    print("control-click right of the coarse knob:", click(coarse, dx=+60, mods="Control-"))
    print("control-click left of the fine knob:", click(fine, dx=-60, mods="Control-"))
    knobs("after the clicks")
    root.setvar(half_name, "")
    pump(0.3)
    print("click on the coarse bar at 1.0, fine box empty:", click(coarse, 1.0))
    knobs("fine box empty")
    print("click on the fine knob, box empty:", click(fine))
    root.setvar(half_name, "0")
    pump(0.3)
    knobs("fine box 0")
    root.setvar(half_name, "0.2")
    pump(0.3)
    knobs("fine box 0.2")
    print("click right of the fine knob:", click(fine, dx=+60))
    knobs("after that click")
    print("drag fine down:", drag(fine, float(fine.cget("from")) + 0.05))
    knobs("after the fine drag")
    print("goto and step commands:", sent)
    print("errors:", len(errors), errors[:2], flush=True)

def driver(root, n=0):
    try:
        script(root)
    except Exception:
        traceback.print_exc(file=sys.stdout)
    sys.stdout.flush()
tk.Tk.mainloop = driver
rc = ap.main(["--simulate", "--config", cfg_path, "--out", out_dir])
print("main returned", rc, flush=True)
os._exit(0)
"""


def test_the_sliders_of_the_real_window_take_the_piezo_where_the_mouse_says(tmp_path):
    """The real window, driven with the mouse. v75: one click on a bar and
    the piezo goes there; a knob that is dragged is followed. Still true
    from v72: a knob that is pressed and let go where it stood asks for
    nothing, nor does Tk's Control-click (which would jump the knob to the
    end of its range), and the fine knob is on the piezo whatever stands in
    the "fine: +/-" box."""
    tk = pytest.importorskip("tkinter")
    pytest.importorskip("igor2")
    try:
        tk.Tk().destroy()
    except tk.TclError as exc:
        pytest.skip(f"no Tk display: {exc}")
    cfg = _cfg(mode="bypass")                      # the surface is at 4.18 V
    path = tmp_path / "stage.json"
    cfg.to_json(path)
    res = subprocess.run([sys.executable, "-c", _DRIVE, str(ROOT), str(path),
                          str(tmp_path / "data")],
                         capture_output=True, text=True, timeout=240, cwd=ROOT)
    out = res.stdout
    assert res.returncode == 0 and "main returned" in out, out[-3000:] + res.stderr[-3000:]
    assert "Traceback" not in out and "WATCHDOG" not in out, out[-3000:]
    lines = dict(line.split(": ", 1) for line in out.splitlines() if ": " in line)
    assert lines["errors"].startswith("0 "), out[-3000:]

    def piezo(line: str) -> float:
        return float(lines[line].split()[1])
    # one click on the bar: the piezo is there, exactly where the slider
    # says the mouse was, and the worker said so once
    assert lines["click on the coarse bar at 2.0"].startswith(
        "moved True on the spot True asked 1 said 1 piezo "), lines
    assert abs(piezo("after the click") - 2.0) < 0.05
    two = piezo("after the click")
    assert lines["after the click"] == (f"piezo {two:.4f} coarse {two:.4f} fine {two:.4f} "
                                        "window 1.5 2.5")
    # a knob that is dragged is followed, and ends where it was let go
    assert lines["drag coarse to 3.0"].startswith("moved True on the spot True asked 1 said 1")
    assert lines["drag coarse to 3.0"].endswith("near True")
    three = piezo("after it")
    assert lines["after it"] == (f"piezo {three:.4f} coarse {three:.4f} fine {three:.4f} "
                                 "window 2.5 3.5")
    # a knob pressed and let go where it stood moves nothing and says
    # nothing; a Control-click does not even ask
    for what, asked in (("click on the coarse knob", 1), ("click on the fine knob", 1),
                        ("control-click right of the coarse knob", 0),
                        ("control-click left of the fine knob", 0),
                        ("click on the fine knob, box empty", 1)):
        assert lines[what].startswith("moved False"), (what, lines[what])
        assert f" asked {asked} said 0 piezo " in lines[what], (what, lines[what])
    assert lines["after the clicks"] == lines["after it"]
    # an empty or useless width keeps the last one, and the knob on the piezo
    assert lines["click on the coarse bar at 1.0, fine box empty"].startswith(
        "moved True on the spot True asked 1 said 1")
    one = piezo("fine box empty")
    assert abs(one - 1.0) < 0.05
    assert lines["fine box empty"] == (f"piezo {one:.4f} coarse {one:.4f} fine {one:.4f} "
                                       "window 0.5 1.5")
    assert lines["fine box 0"] == lines["fine box empty"]
    assert lines["fine box 0.2"] == (f"piezo {one:.4f} coarse {one:.4f} fine {one:.4f} "
                                     f"window {round(one, 1) - 0.2:g} {round(one, 1) + 0.2:g}")
    # a click beside the fine knob takes the piezo there too (up to v74 it
    # was one step of 0.1 mV)
    assert lines["click right of the fine knob"].startswith(
        "moved True on the spot True asked 1 said 1")
    assert 0.01 < piezo("after that click") - one < 0.2
    assert lines["drag fine down"].startswith("moved True on the spot True asked 1 said 1")
    assert lines["drag fine down"].endswith("near True")
    # none of it went through the old goto command
    assert lines["goto and step commands"] == "[]"
