"""pullout v73: the Approach button, the three signs of contact, volts and
nanometres on the sliders, and the simulator's screw.

Simulator only: no card. None of these tests moves a real piezo.

Approach is for a rig whose coarse approach is a screw turned by hand. The
screw brings the surface within the piezo's reach (10.8 um on the new rig in
standard mode), and the piezo itself comes up to the surface: toward it at
the speed in the box, stopping where the junction closes. With no contact
all the way to the top of the range the piezo is taken back, and the status
line says to approach with the screw again.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from stmlab.config import validate                                        # noqa: E402
from test_v72_piezo import (BYPASS, STANDARD, SURFACE_NM, _cfg, _status,  # noqa: E402
                            _surface, _worker)

NEAR_8_V = 8600.0          # nm: where the surface was on the rig (7.98 V)


@pytest.fixture(scope="module")
def ap():
    import pullout
    return pullout


def _watch_the_pieces(rig, monkeypatch) -> list:
    """Every piece of a move toward the surface: the voltage it ends at."""
    ends = []
    glide = rig.piezo_glide_to

    def counted(volts, seconds):
        ends.append(volts)
        return glide(volts, seconds)
    monkeypatch.setattr(rig, "piezo_glide_to", counted)
    return ends


# -- Approach ---------------------------------------------------------------------

def test_approach_brings_the_piezo_up_to_the_surface_and_stops_at_contact(ap, tmp_path):
    cfg = _cfg()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        _surface(rig, NEAR_8_V)                    # the screws left it 8.6 um away
        worker.hand_speed_nm_s = 2000.0            # 50 nm pieces
        worker.cmd_piezo_approach()
        # at the surface, at most a little over one piece in
        assert NEAR_8_V - 0.2 < rig.piezo_nm <= NEAR_8_V + 1.15 * 50.0 + 1.0
        assert rig.state is ap.RigState.ENGAGED
        said = _status(worker)
        assert said["level"] == "ok"
        assert said["text"].startswith(f"CONTACT at {rig.piezo_v:.4f} V = "
                                       f"{rig.piezo_nm:.1f} nm (")
        assert "The piezo stays there" in said["text"] and "Now Start N" in said["text"]
        assert len(said["text"]) < 190             # the status box shows three lines
        # the window is told, and puts its fine slider around the contact:
        # x +/- 0.5 V on round numbers
        assert [k for k, _ in list(worker.events.queue)][-2] == "moved"
        assert ap.fine_window(rig.piezo_v, 0.5, 0.0, 10.0) == (7.5, 8.5)
        # and a run starts from the contact the piezo found
        worker.cmd_run(2)
        assert worker.accepted == 2 and worker.paused is None
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_no_contact_for_the_whole_range_says_so_and_takes_the_piezo_back(
        ap, tmp_path, monkeypatch):
    cfg = _cfg()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        _surface(rig, 50_000.0)                    # 50 um away: out of the piezo's reach
        worker.cmd_goto(0.2)                       # it starts from here
        ends = _watch_the_pieces(rig, monkeypatch)
        worker.hand_speed_nm_s = 5000.0
        worker.cmd_piezo_approach()
        assert max(ends) == pytest.approx(10.0)    # it went all the way to the top
        assert rig.piezo_v == pytest.approx(0.2)   # and is back where it started
        assert rig.state is not ap.RigState.ENGAGED
        said = _status(worker)
        assert said["level"] == "warn"
        assert said["text"] == ("NO CONTACT for the whole range (up to 10 V = 10776 nm): "
                                "approach with the screw again. The piezo is back at "
                                "0.200 V")
        # the screw brings the surface within reach, and the next one finds it
        worker.cmd_sim_surface(NEAR_8_V)
        worker.cmd_piezo_approach()
        assert _status(worker)["text"].startswith("CONTACT at ")
        assert rig.piezo_nm == pytest.approx(NEAR_8_V, abs=1.15 * 125.0 + 1.0)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_stop_ends_an_approach_where_it_is(ap, tmp_path, monkeypatch):
    cfg = _cfg()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        _surface(rig, NEAR_8_V)
        ends = []
        glide = rig.piezo_glide_to

        def counted(volts, seconds):
            ends.append(volts)
            if len(ends) == 5:
                worker.stop_flag.set()             # Stop, during the fifth piece
            return glide(volts, seconds)
        monkeypatch.setattr(rig, "piezo_glide_to", counted)
        worker.cmd_piezo_approach()
        assert len(ends) == 5 and rig.piezo_v == pytest.approx(ends[-1])
        assert rig.piezo_nm == pytest.approx(25.0)             # five pieces of 5 nm
        said = _status(worker)
        assert said["text"].startswith("Approach stopped by Stop at 0.0232 V = 25.0 nm")
        assert said["text"].endswith(", open")
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_approach_with_nothing_to_approach_moves_nothing(ap, tmp_path, monkeypatch):
    cfg = _cfg()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_goto(1.0)                       # into contact, by the slider
        assert rig.state is ap.RigState.ENGAGED
        at = rig.piezo_v
        ends = _watch_the_pieces(rig, monkeypatch)
        worker.cmd_piezo_approach()                # already there
        assert ends == [] and rig.piezo_v == at
        said = _status(worker)
        assert said["level"] == "warn"
        assert said["text"].startswith("already in contact at ")
        assert "nothing to approach" in said["text"]
        # at the top of the range with the junction open: nowhere to go
        worker.cmd_goto(0.0)
        _surface(rig, 50_000.0)
        worker.hand_speed_nm_s = 5000.0
        worker.cmd_goto(10.0)
        ends.clear()
        worker.cmd_piezo_approach()
        assert ends == [] and rig.piezo_v == pytest.approx(10.0)
        assert _status(worker)["text"].startswith(
            "NO CONTACT, and the piezo is at the top of its range (10 V)")
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_contact_too_low_in_the_range_to_pull_from_is_said(ap, tmp_path):
    cfg = _cfg()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        _surface(rig, 12.0)                        # 12 nm up: 0.011 V
        worker.cmd_piezo_approach()
        said = _status(worker)
        assert said["level"] == "warn" and said["text"].startswith("CONTACT at ")
        assert "too low in the range to pull from" in said["text"]
        assert "turn the screw back a little" in said["text"]
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


# -- the three signs of contact ------------------------------------------------------

def test_the_contact_current_stops_an_approach_that_engage_would_not(ap, tmp_path):
    """The new rig: a few millivolts on the junction voltage cap the
    conductance reading near 4 G0, and through the series resistor the
    amplifier never rails. With Engage at 5 neither of the old two signs of
    contact ever came. The current does not need the junction voltage."""
    cfg = _cfg()
    cfg.keithley.series_resistance_ohm = 106130.0  # the current stops at 0.94 uA
    cfg.ramp.engage_g0 = 1e6                       # a G the reading never reaches
    validate(cfg)
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        assert worker.contact_ua == 0.15           # the CONTACT light's level
        worker.cmd_piezo_approach()
        assert SURFACE_NM - 0.2 < rig.piezo_nm <= SURFACE_NM + 1.15 * 5.0 + 1.0
        assert rig.state is ap.RigState.ENGAGED
        said = _status(worker)
        assert said["text"].startswith("CONTACT at ")
        assert "uA, above the contact current" in said["text"]
        # the sliders and Step closer stop by the same sign
        worker.cmd_goto(0.2)
        worker.cmd_goto(1.0)
        said = _status(worker)
        assert said["text"].startswith("STOPPED AT CONTACT (")
        assert "above the contact current" in said["text"] and "in contact" in said["text"]
        assert rig.piezo_nm <= SURFACE_NM + 1.15 * 5.0 + 1.0
        # without it nothing stops the piezo on this rig: all the way up
        worker.cmd_goto(0.0)
        worker.contact_ua = 0.0                    # 0 switches that sign off
        worker.hand_speed_nm_s = 5000.0
        worker.cmd_piezo_approach()
        assert _status(worker)["text"].startswith("NO CONTACT for the whole range")
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_what_closed_the_junction_is_said_in_words(ap, tmp_path):
    cfg = _cfg()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        assert worker._closed(rig.hold()) == ""                # open: none of the three
        worker.cmd_goto(1.0)                                   # into contact
        record = rig.hold()
        assert worker._closed(record).startswith("G = ")       # the conductance says so
        cfg.ramp.engage_g0 = 1e6
        why = worker._closed(record)
        # this default rig has no series resistor: its amplifier rails, or the
        # current is far above the contact current
        assert why == "the amplifier is at its rail" or why.endswith(
            "uA, above the contact current")
        worker.contact_ua = 0.0
        cfg.limits.preamp_saturation_v = 1e9
        assert worker._closed(record) == ""                    # all three switched off
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


# -- the simulator's screw --------------------------------------------------------------

def test_the_simulators_screw_puts_the_surface_where_it_is_told(ap, tmp_path):
    cfg = _cfg()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        session = rig._session
        assert session.surface_nm == SURFACE_NM
        worker.cmd_sim_surface(NEAR_8_V)
        assert session.surface_nm == NEAR_8_V
        said = _status(worker)
        assert said["level"] == "ok" and "which is 7.981 V" in said["text"]
        worker.cmd_sim_surface(50_000.0)
        assert session.surface_nm == 50_000.0
        assert "out of the piezo's reach (10776 nm)" in _status(worker)["text"]
        # not into the tip, not nonsense, and not on a real card
        worker.hand_speed_nm_s = 5000.0
        worker.cmd_goto(1.0)                                   # the tip at 1078 nm
        for nm in (500.0, "close", float("nan")):
            worker.cmd_sim_surface(nm)
            assert _status(worker)["level"] == "bad" and session.surface_nm == 50_000.0
        cfg.simulate = False
        worker.cmd_sim_surface(NEAR_8_V)
        assert _status(worker)["level"] == "bad" and session.surface_nm == 50_000.0
        cfg.simulate = True
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


@pytest.mark.parametrize("mode", ["standard", "bypass"])
def test_bypass_reaches_a_fifteenth_as_far(ap, tmp_path, mode):
    """A surface 2 um away: within the piezo's reach in standard mode
    (10.8 um), out of it in bypass (718 nm), where the screws have to bring
    it back."""
    cfg = _cfg(mode=mode)
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        _surface(rig, 2000.0)
        worker.hand_speed_nm_s = 5000.0 if mode == "standard" else 500.0
        worker.cmd_piezo_approach()
        said = _status(worker)["text"]
        if mode == "standard":
            assert said.startswith("CONTACT at ") and rig.piezo_v == pytest.approx(
                2000.0 / STANDARD, abs=0.15)
        else:
            assert said.startswith("NO CONTACT for the whole range (up to 10 V = 718 nm)")
            assert rig.piezo_v == 0.0 and 10 * BYPASS == pytest.approx(718.4)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


# -- the real window ----------------------------------------------------------------------

# As in test_v72_piezo: Tk's mainloop is replaced by a script that works the
# window's own widgets and writes down what it sees.
_DRIVE = r"""
import os, sys, time, threading, traceback
root_dir, cfg_path, out_dir = sys.argv[1:4]
sys.path.insert(0, root_dir)
import tkinter as tk
import pullout as ap

watchdog = threading.Timer(150, lambda: (print("WATCHDOG", flush=True), os._exit(3)))
watchdog.daemon = True
watchdog.start()
said, errors, W = [], [], {}
orig_send, orig_status = ap.Worker.send, ap.Worker.status
def send(self, *command):
    W["w"] = self
    return orig_send(self, *command)
def status(self, text, *a, **k):
    said.append(text)
    return orig_status(self, text, *a, **k)
ap.Worker.send, ap.Worker.status = send, status
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
    def button(text):
        return next(w for w in widgets if w.winfo_class() == "TButton"
                    and str(w.cget("text")) == text)
    def entry_beside(widget):
        return str(next(c for c in widget.master.winfo_children()
                        if c.winfo_class() == "TEntry").cget("textvariable"))
    approach, turn = button("Approach"), button("Turn")
    scales = [w for w in widgets if w.winfo_class() == "Scale"]
    coarse = next(w for w in scales if float(w.cget("tickinterval")) > 0)
    fine = next(w for w in scales if w is not coarse and w.master is coarse.master)
    rig = W["w"].rig
    def texts(cls):
        # "Label": the labels riding on the knobs (each in its own strip, a
        # Frame); "TLabel": the two ends written under the fine slider
        return [str(w.cget("text")) for w in walk(coarse.master)
                if w.winfo_class() == cls and " V = " in str(w.cget("text"))
                and (cls == "TLabel" or w.master.winfo_class() == "Frame")]
    def look(tag):
        print(f"{tag}: piezo {rig.piezo_v:.4f} window {float(fine.cget('from')):g} "
              f"{float(fine.cget('to')):g} | knobs {texts('Label')} | ends {texts('TLabel')}"
              f" | {said[-1][:60] if said else ''}", flush=True)
    def knob_over(scale):
        # is the label that rides on the knob over the knob?
        strip = next(w for w in walk(coarse.master) if w.winfo_class() == "Frame"
                     and w.winfo_y() < scale.winfo_y()
                     and scale.winfo_y() - w.winfo_y() < 40 and w.winfo_children())
        lbl = strip.winfo_children()[0]
        centre = lbl.winfo_x() + lbl.winfo_width() / 2
        return abs(centre - scale.coords()[0]) < 3 or lbl.winfo_x() <= 1 \
            or lbl.winfo_x() + lbl.winfo_width() >= strip.winfo_width() - 1
    look("start")
    root.setvar(entry_beside(approach), "2000")
    root.setvar(entry_beside(turn), "8600")
    pump(0.2)
    turn.invoke(); idle()
    look("screw 8600")
    approach.invoke(); idle()
    look("approach")
    print("knobs over their knobs:", knob_over(coarse), knob_over(fine), flush=True)
    x, y = coarse.coords()
    coarse.event_generate("<ButtonPress-1>", x=x, y=y); pump(0.1)
    print("held:", texts("Label"), flush=True)
    coarse.event_generate("<ButtonRelease-1>", x=x, y=y); idle()
    # down again, by the coarse slider: the mouse down on the knob, the knob
    # taken to 0 V, the mouse up
    x, y = coarse.coords()
    coarse.event_generate("<ButtonPress-1>", x=x, y=y); pump(0.05)
    root.setvar(str(coarse.cget("variable")), 0.0)
    coarse.event_generate("<ButtonRelease-1>", x=x, y=y); idle()
    look("down")
    root.setvar(entry_beside(turn), "50000")
    root.setvar(entry_beside(approach), "5000")
    pump(0.2)
    turn.invoke(); idle()
    approach.invoke(); idle()
    look("no contact")
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


def test_the_real_window_approach_button_knob_labels_and_screw(tmp_path):
    """The window itself: the simulator's screw puts the surface near 8 V,
    Approach finds it, the fine slider is then 7.5 to 8.5 V with both ends
    in volts and nanometres, each knob carries its volts and nanometres, and
    a surface out of reach gives the words asked for."""
    tk = pytest.importorskip("tkinter")
    pytest.importorskip("igor2")
    try:
        tk.Tk().destroy()
    except tk.TclError as exc:
        pytest.skip(f"no Tk display: {exc}")
    cfg = _cfg()                                   # standard: 1077.6 nm per volt
    path = tmp_path / "stage.json"
    cfg.to_json(path)
    res = subprocess.run([sys.executable, "-c", _DRIVE, str(ROOT), str(path),
                          str(tmp_path / "data")],
                         capture_output=True, text=True, timeout=300, cwd=ROOT)
    out = res.stdout
    assert res.returncode == 0 and "main returned" in out, out[-3000:] + res.stderr[-3000:]
    assert "Traceback" not in out and "WATCHDOG" not in out, out[-3000:]
    lines = dict(line.split(": ", 1) for line in out.splitlines() if ": " in line)
    assert lines["errors"].startswith("0 "), out[-3000:]
    # at start-up the piezo is at 0 V: the fine window is cut off there, and
    # everything is said in volts and in nanometres
    assert lines["start"].startswith(
        "piezo 0.0000 window 0 0.5 | knobs ['0.000 V = 0.0 nm', '0.0000 V = 0.0 nm'] "
        "| ends ['0 V = 0 nm', '0.5 V = 539 nm']")
    assert "the surface is now 8600 nm" in lines["screw 8600"]
    # Approach: contact near 7.98 V, the fine slider around it
    after = lines["approach"]
    volts = float(after.split()[1])
    assert 8600.0 / STANDARD - 0.001 < volts < (8600.0 + 60.0) / STANDARD
    assert f"piezo {volts:.4f} window 7.5 8.5 | knobs ['{volts:.3f} V = " in after
    assert f"'{volts:.4f} V = {volts * STANDARD:.1f} nm']" in after
    assert "| ends ['7.5 V = 8082 nm', '8.5 V = 9160 nm'] | CONTACT at " in after
    assert lines["knobs over their knobs"] == "True True"
    # a knob held by the mouse says that letting go will move the piezo
    assert "(release to move)" in lines["held"]
    # out of reach: the words asked for, and the piezo back where it started
    gone = lines["no contact"]
    assert gone.startswith("piezo 0.0000 window 0 0.5 ")
    assert "NO CONTACT for the whole range (up to 10 V = 10776 nm): app" in gone
