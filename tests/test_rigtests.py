"""The parts of pullout.py that decide things: the settings check that stands
between a typed number and the rig, the monitor that watches every play, the
worker's experiments, the Keithley and actuator commands, the histogram
windows. No hardware, simulator only; the window tests skip without a
display."""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from stmlab import approach, storage
from stmlab.config import RigConfig
from stmlab.instrument import Rig
from stmlab.sim import SimulatedDaqSession

@pytest.fixture(scope="module")
def ap():
    import pullout
    return pullout


@pytest.fixture
def cfg():
    c = RigConfig()
    c.simulate = True
    return c


# -- settings ---------------------------------------------------------------

def test_a_bias_above_the_limit_is_refused(ap, cfg):
    problems, warnings = ap.check_settings(cfg, {"ramp.bias_v": 0.9})
    assert problems and "bias" in problems[0]


def test_a_pull_longer_than_the_piezo_is_refused(ap, cfg):
    problems, _ = ap.check_settings(cfg, {"ramp.pull_length_nm": 2000.0})
    assert problems


def test_engage_below_break_is_refused(ap, cfg):
    problems, _ = ap.check_settings(cfg, {"ramp.engage_g0": 1e-5})
    assert problems


def test_a_sane_change_is_accepted_and_the_live_config_untouched(ap, cfg):
    problems, warnings = ap.check_settings(cfg, {"ramp.pull_rate_nm_per_s": 10.0})
    assert not problems
    assert cfg.ramp.pull_rate_nm_per_s == 20.0          # a copy was checked


def test_nonsense_values_are_refused_before_validate(ap, cfg):
    assert ap.check_settings(cfg, {"ramp.approach_step_nm": 0.0})[0]
    assert ap.check_settings(cfg, {"ramp.settle_samples": 3})[0]


# -- the monitor ---------------------------------------------------------------

def test_monitor_sees_every_play_and_probe_without_changing_them(ap, cfg):
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=3)).open()
    try:
        mon = ap.Monitor(rig)
        mon.begin_cycle()
        rig.set_bias(cfg.ramp.bias_v)
        approach.engage(rig)
        cyc = mon.snapshot()
        assert len(cyc.t) == len(cyc.piezo_v) == len(cyc.sense_v) > 5
        assert len(cyc.app_g0) == len(cyc.app_railed) > 1
        assert cyc.piezo_v[-1] == pytest.approx(rig.piezo_v)   # the tracker's value
        assert cyc.last_record.shape[0] == 2
    finally:
        rig.close()


# -- moves made by hand: the slider and the step buttons -------------------------

def test_a_ramped_move_lands_on_the_target_and_is_clamped(cfg):
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=1)).open()
    try:
        rec = rig.piezo_ramp_to(2.0)
        assert rig.piezo_v == pytest.approx(2.0)
        assert rec.shape == (2, int(round(0.05 * rig.sample_rate_hz))
                             + cfg.ramp.settle_samples)
        # The bias row is untouched by a move.
        assert rig.bias_v == pytest.approx(cfg.ramp.bias_v)
        rig.piezo_ramp_to(25.0)                       # beyond the 10 V ceiling
        assert rig.piezo_v == pytest.approx(cfg.limits.piezo_ao_max_v)
    finally:
        rig.close()


def test_a_slider_move_into_contact_engages_and_a_pull_follows(ap, cfg, tmp_path):
    """Igor's slider-then-measure: a contact made by hand can be pulled from."""
    guard, rig = ap.open_rig(cfg)
    mon = ap.Monitor(rig)
    worker = ap.Worker(cfg, rig, mon, save=False, out_dir=tmp_path,
                       igor_export=False)
    try:
        worker.cmd_goto(1.0)                           # far from the surface
        assert rig.state is not ap.RigState.ENGAGED
        # The simulated surface sits at 300 nm: go past it, by hand, far
        # enough for Igor's 5 G0 engage threshold (a few atoms in).
        worker.cmd_goto(cfg.cal.nm_to_piezo_volts(301.0))
        assert rig.state is ap.RigState.ENGAGED
        events = []
        while not worker.events.empty():
            events.append(worker.events.get_nowait())
        assert any(k == "moved" for k, _ in events)
        assert any(k == "status" and "in contact" in p["text"] for k, p in events)
        worker.cmd_pull()                              # allowed from a hand-made contact
        assert worker.attempts == 1
        # Stepping apart by hand leaves contact; the state says so.
        worker.cmd_step(-200.0)
        assert rig.state is not ap.RigState.ENGAGED
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_stop_flag_ends_an_approach_between_steps(cfg):
    """The Stop button and the window's close both set this flag; the
    approach must end at once, cleanly, and run again once it is cleared."""
    import threading
    from stmlab.safety import RigState
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=2)).open()
    try:
        flag = threading.Event()
        flag.set()
        with pytest.raises(approach.ApproachError, match="stopped by request"):
            approach.engage(rig, stop_flag=flag)
        assert rig.piezo_v == pytest.approx(cfg.ramp.piezo_park_v)   # no step taken
        flag.clear()
        assert approach.engage(rig, stop_flag=flag) is RigState.ENGAGED
    finally:
        rig.close()


def test_quitting_the_worker_mid_run_returns_promptly_and_leaves_the_rig_usable(
        ap, cfg, tmp_path):
    """What closing the window does while Start N is going: the stop flag ends
    the approach between steps, the worker thread exits, and only then are
    the cards closed -- no write lands on a closed task."""
    import time
    guard, rig = ap.open_rig(cfg)
    mon = ap.Monitor(rig)
    worker = ap.Worker(cfg, rig, mon, save=False, out_dir=tmp_path,
                       igor_export=False)
    worker.start()
    try:
        worker.send("run", 100000)
        time.sleep(0.5)                      # well into the run
        t0 = time.monotonic()
        worker.stop_flag.set()
        worker.quit()
        worker.join(timeout=60)
        assert not worker.is_alive()
        assert time.monotonic() - t0 < 10
        rig.withdraw()                       # the cards are still open and sane
        assert rig.piezo_v == pytest.approx(cfg.ramp.piezo_park_v)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


# -- saving: one experiment per run ----------------------------------------------

def test_a_run_files_its_traces_under_date_name_experiment(ap, cfg, tmp_path):
    guard, rig = ap.open_rig(cfg)
    mon = ap.Monitor(rig)
    worker = ap.Worker(cfg, rig, mon, save=True, out_dir=tmp_path,
                       igor_export=False)
    try:
        worker.cmd_zero()
        worker.cmd_cycle()                       # a single cycle: not saved
        assert list(tmp_path.rglob("*.h5")) == []
        worker.cmd_run(2, {"folder": tmp_path, "name": "Leo Z",
                           "experiment": "clean gold", "txt": True})
        folder = tmp_path / time.strftime("%Y-%m-%d") / "Leo_Z"
        h5 = list(folder.glob("clean_gold_*_2traces.h5"))
        assert len(h5) == 1
        txt = h5[0].with_suffix(".txt")
        assert txt.exists()
        table = np.loadtxt(txt)                  # comments skipped
        assert table.shape[1] == 3               # displacement + 2 traces
        assert table[0, 0] == 0.0 and table[-1, 0] == pytest.approx(
            cfg.ramp.pull_length_nm, rel=0.01)
        assert np.all(np.isfinite(table[:, 1:]))
        info = h5[0].with_name(h5[0].stem + "_info.txt").read_text()
        assert info.count("\n") == 3                # header + 2 rows
        # The run's counters started fresh.
        assert worker.accepted == 2
        # A second run is a second experiment, its own file.
        worker.cmd_run(1, {"experiment": "OPE3"})
        assert len(list(folder.glob("OPE3_*_1traces.h5"))) == 1
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_every_run_adds_a_row_to_the_experiment_log(ap, cfg, tmp_path):
    import csv
    import h5py
    cfg.ramp.engage_g0 = 2.0          # a solid contact, as the lab's 5 G0 gives
    guard, rig = ap.open_rig(cfg)
    mon = ap.Monitor(rig)
    worker = ap.Worker(cfg, rig, mon, save=True, out_dir=tmp_path,
                       igor_export=False)
    worker.config_name = "labpc_rig.json"
    try:
        worker.cmd_zero()
        worker.cmd_run(2, {"folder": tmp_path, "name": "Leo", "experiment": "au",
                           "notes": "fresh tip, toluene", "txt": True})
        worker.cmd_run(1, {"experiment": "OPE3"})
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)
    log = tmp_path / "experiment_log.csv"           # one file, every day
    with open(log, newline="") as f:
        lines = list(csv.reader(f))
    # A header, then two lines per experiment: the facts, then the path alone.
    assert lines[0] == ["date", "start_time", "name", "experiment", "traces",
                        "notes", "auto_notes"]
    assert len(lines) == 1 + 2 * 2
    first, path_line = lines[1], lines[2]
    assert first[0] == time.strftime("%Y-%m-%d")
    assert first[2:6] == ["Leo", "au", "2", "fresh tip, toluene"]
    # The automatic note: the bias set and the junction voltage measured,
    # open (through the series resistor, ~90 mV) and in contact (a few mV).
    auto = first[6]
    m = re.search(r"junction measured ([\d.]+) mV open, ([\d.]+) mV at pull start", auto)
    assert auto.startswith("bias set 100 mV; ") and m
    assert 85 < float(m.group(1)) < 95
    assert 0 < float(m.group(2)) < 15                  # in contact, G >= 2 G0
    assert "series resistor 106130 ohm" in auto and "gain 1e+06 V/A" in auto
    assert len(path_line) == 1
    data_path = Path(path_line[0])
    assert data_path.is_absolute() and data_path.exists()
    assert data_path.name.startswith("au_") and data_path.name.endswith("_2traces.h5")
    assert lines[3][3] == "OPE3" and len(lines[4]) == 1
    r = {"data_path": str(data_path)}
    # The file header carries the same who / what / notes.
    with h5py.File(r["data_path"]) as h:
        assert h.attrs["operator"] == "Leo"
        assert h.attrs["experiment"] == "au"
        assert h.attrs["notes"] == "fresh tip, toluene"
        assert h.attrs["auto_notes"].startswith("bias set 100 mV")
        assert h.attrs["program"].startswith("pullout v")


def test_saving_settings_are_remembered(ap, tmp_path):
    f = tmp_path / "s.json"
    ap.save_saving(f, {"folder": tmp_path / "d", "name": "leo",
                       "experiment": "x", "txt": True, "igor": False})
    back = ap.load_saving(f)
    assert back["name"] == "leo" and back["txt"] is True
    assert Path(back["folder"]) == tmp_path / "d"
    assert ap.load_saving(tmp_path / "missing.json") == {}


def test_stop_pauses_a_run_and_continue_finishes_it_in_the_same_file(ap, cfg, tmp_path):
    guard, rig = ap.open_rig(cfg)
    mon = ap.Monitor(rig)
    worker = ap.Worker(cfg, rig, mon, save=True, out_dir=tmp_path,
                       igor_export=False)
    try:
        worker.stop_flag.set()                   # as if Stop were pressed at once
        worker.cmd_run(4, {"folder": tmp_path, "name": "leo", "experiment": "au"})
        assert worker.paused == {"remaining": 4}
        assert worker.run_stem is not None       # the experiment stays open
        assert list(tmp_path.rglob("*traces.h5")) == []
        worker.stop_flag.clear()                 # (the worker loop does this per command)
        worker.cmd_cycle()                       # a single cycle while paused
        assert worker.n_saved == 0               # is not written into the file
        worker.cmd_continue()
        assert worker.paused is None and worker.run_stem is None
        files = list(tmp_path.rglob("au_*_4traces.h5"))
        assert len(files) == 1
        with storage.Session(files[0]) as sess:
            assert len(sess) == 4
        # The note says where the run was stopped and that it was continued.
        import csv
        import h5py
        with open(tmp_path / "experiment_log.csv", newline="") as f:
            lines = list(csv.reader(f))
        assert "Stop after trace 0 at " in lines[1][6] and ", continued " in lines[1][6]
        with h5py.File(files[0]) as h:
            assert "Stop after trace 0" in h.attrs["auto_notes"]
        worker.cmd_continue()                    # nothing to continue
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_settings_change_finishes_a_paused_experiment(ap, cfg, tmp_path):
    guard, rig = ap.open_rig(cfg)
    mon = ap.Monitor(rig)
    worker = ap.Worker(cfg, rig, mon, save=True, out_dir=tmp_path,
                       igor_export=False)
    try:
        worker.cmd_run(1, {"folder": tmp_path, "name": "leo", "experiment": "au"})
        worker.stop_flag.set()
        worker.cmd_run(3, {"experiment": "au2"})     # pauses at once, 0 taken
        worker.stop_flag.clear()
        worker.cmd_newfile()                         # what Apply sends
        assert worker.paused is None and worker.run_stem is None
        assert len(list(tmp_path.rglob("au_*_1traces.h5"))) == 1
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


# -- the coarse actuator, simulated ------------------------------------------------

def test_coarse_steps_go_through_the_interlock(ap, cfg, tmp_path):
    from stmlab.safety import SafetyViolation
    cfg.actuator.kind = "simulated"
    guard, rig = ap.open_rig(cfg)
    mon = ap.Monitor(rig)
    worker = ap.Worker(cfg, rig, mon, save=False, out_dir=tmp_path,
                       igor_export=False)
    try:
        worker.cmd_coarse_step(True)             # parked: allowed
        assert rig.coarse_steps == 1
        rig._session.move_surface(400.0)         # the surface out of reach
        worker.cmd_goto(cfg.actuator.approach_piezo_v)   # at the approach position
        worker.cmd_coarse_step(True)             # allowed: room to open the junction
        assert rig.coarse_steps == 2
        worker.cmd_goto(cfg.actuator.approach_piezo_v + 1.0)   # beyond it
        with pytest.raises(SafetyViolation):
            worker.cmd_coarse_step(True)         # refused before the move
        assert rig.coarse_steps == 2
        events = [k for k, _ in list(worker.events.queue)]
        assert "actuator" in events
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_without_an_actuator_the_buttons_only_explain(ap, cfg, tmp_path):
    cfg.actuator.kind = "none"                   # a rig with no coarse actuator
    guard, rig = ap.open_rig(cfg)
    mon = ap.Monitor(rig)
    worker = ap.Worker(cfg, rig, mon, save=False, out_dir=tmp_path,
                       igor_export=False)
    try:
        worker.cmd_coarse_step(True)
        worker.cmd_coarse_approach()
        texts = [p["text"] for k, p in list(worker.events.queue) if k == "status"]
        assert any("no actuator configured" in t for t in texts)
        assert rig.coarse_steps == 0
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


class FakeSerial:
    """A NanoPZ controller on a string: records what is written, answers
    the two queries the driver uses, echoes the command as the real one
    does, and knows when it has been closed."""

    def __init__(self, port, baudrate, bytesize, parity, stopbits, timeout):
        self.opened = dict(port=port, baudrate=baudrate, bytesize=bytesize,
                           parity=parity, stopbits=stopbits, timeout=timeout)
        self.written: list[str] = []
        self.position = -123
        self.closed = False
        self._reply = b""

    def write(self, data: bytes):
        cmd = data.decode().strip()
        self.written.append(cmd)
        if cmd == "0TP?":
            self._reply = f"0TP? {self.position}\r\n".encode()
        elif cmd == "0TS?":
            self._reply = b"0TS? P\r\n"
        elif cmd.startswith("0PR"):
            self.position += int(cmd[3:])
        else:
            self._reply = b""

    def flush(self):
        pass

    def reset_input_buffer(self):
        pass

    def readline(self):
        r, self._reply = self._reply, b""
        return r

    @property
    def in_waiting(self):
        return len(self._reply)

    def read(self, n):
        return self.readline()

    def close(self):
        self.closed = True


def test_nanopz_protocol_on_a_fake_port(cfg):
    from stmlab.actuator import NanoPZActuator, ActuatorError
    cfg.actuator.step_size = 5
    made = []

    def factory(**kw):
        made.append(FakeSerial(**kw))
        return made[-1]
    act = NanoPZActuator(cfg, port="COM7", serial_factory=factory)
    ser = made[0]
    assert ser.opened["port"] == "COM7" and ser.opened["baudrate"] == 19200
    assert ser.written == ["0MO"]                       # motor on, nothing else
    assert act.identify() == {"status": "P", "position": -123, "port": "COM7",
                              "kind": "nanopz"}
    act.step(closer=True)
    assert ser.written[-1] == "0PR-5"                   # negative = toward the sample
    act.step(closer=False)
    assert ser.written[-1] == "0PR5"
    assert act.position() == -123                       # the fake tracks the moves
    act.close()
    assert ser.written[-2:] == ["0ST", "0MF"] and ser.closed

    # A port that answers nothing is reported as such, not as a position.
    class Mute(FakeSerial):
        def readline(self):
            return b""
    mute = NanoPZActuator(cfg, port="COM8", serial_factory=lambda **kw: Mute(**kw))
    with pytest.raises(ActuatorError, match="nothing on COM8 answers"):
        mute.identify()
    assert mute.position() is None


class FakeVisa:
    """The lab's AG-UC2 on a string, through a pyvisa-shaped object: it
    answers VE, TE, TS and TP exactly as the real one did on the rig
    (``AG-UC2 v2.2.1``, ``TE0``, ``1TS0``, ``1TP2086``), keeps a step
    counter that PR moves, refuses a move in local mode with TE-5, and
    records every byte written. The ResourceManager just hands it back."""

    def __init__(self, awake: bool = True):
        self.resource = None
        self.raw: list[bytes] = []
        self.attrs: dict = {}
        self.closed = False
        self.awake = awake
        self.counter = 2086
        self.remote = False
        self.last_error = 0
        self.pending = b""
        self.ignore_mr = False                  # a box that will not go remote

    def open_resource(self, resource):
        self.resource = resource
        return self

    def write_raw(self, data: bytes):
        self.raw.append(bytes(data))
        if not self.awake:
            return
        cmd = data.decode().strip()
        reply = None
        if cmd == "VE":
            reply = "AG-UC2 v2.2.1 "
        elif cmd == "TE":
            reply = f"TE{self.last_error}"
        elif cmd.endswith("TS"):
            reply = f"{cmd}0"
        elif cmd.endswith("TP"):
            if self.remote:                     # the AG-UC2 answers TP in remote only
                reply = f"{cmd}{self.counter}"
        elif cmd == "mr":
            if not self.ignore_mr:
                self.remote = True
            self.last_error = 0
        elif cmd == "ml":
            self.remote, self.last_error = False, 0
        elif "PR" in cmd:
            if self.remote:
                self.counter += int(cmd.split("PR")[1]); self.last_error = 0
            else:
                self.last_error = -5
        elif "SU" in cmd or cmd.startswith("CC") or cmd.endswith("ST"):
            self.last_error = 0 if self.remote or cmd.endswith("ST") else -5
        if reply is not None:
            self.pending += (reply + "\r\n").encode()

    @property
    def bytes_in_buffer(self) -> int:
        return len(self.pending)

    def read_bytes(self, n: int) -> bytes:
        out, self.pending = self.pending[:n], self.pending[n:]
        return out

    def close(self):
        self.closed = True

    def __setattr__(self, name, value):
        if name in ("resource", "raw", "attrs", "closed", "awake", "counter",
                    "remote", "last_error", "pending", "ignore_mr"):
            object.__setattr__(self, name, value)
        else:
            self.attrs[name] = value

    @property
    def sent(self) -> list[str]:
        return [b.decode("ascii").strip() for b in self.raw]

    def moves(self) -> list[str]:
        """What was sent, without the TE/TS/TP queries the driver adds."""
        return [c for c in self.sent if c not in ("TE", "1TS", "1TP", "2TS", "2TP", "VE")]

    def moves_and_counter(self) -> list[str]:
        return [c for c in self.sent if c not in ("TE", "1TS", "2TS", "VE")]


def test_agilis_matches_igor_and_reads_the_controller_back(cfg, monkeypatch):
    """Igor's byte sequence per move (remote, amplitude, PR, local; +PR is
    toward the sample on this rig), each command checked with TE, the
    move waited out with TS, and TP as the position -- as verified on
    the rig, where the counter fell by exactly the count sent."""
    from stmlab.actuator import AgilisActuator, ActuatorError, com_to_visa
    monkeypatch.setattr(AgilisActuator, "GAP_S", 0.0)
    assert com_to_visa("COM4") == "ASRL4::INSTR"
    assert com_to_visa("ASRL4::INSTR") == "ASRL4::INSTR"

    cfg.actuator.step_size = 20                          # PR count
    cfg.actuator.step_amplitude = 50                     # SU
    cfg.actuator.closer_sign = 1                         # +PR = closer (this rig)
    fake = FakeVisa()
    act = AgilisActuator(cfg, port="COM4", rm_factory=lambda backend: fake)
    assert fake.resource == "ASRL4::INSTR"
    assert fake.attrs["baud_rate"] == 921600             # fixed, whatever the json says
    assert fake.sent == []                               # as Igor: nothing on open

    ident = act.identify()
    assert ident["version"] == "AG-UC2 v2.2.1" and ident["status"] == "0"
    assert ident["position"] == 2086 and ident["kind"] == "agilis"

    fake.raw.clear()
    act.step(closer=False)                               # 20 apart, as on the rig
    assert fake.moves() == ["mr", "1SU-50", "1PR-20", "ml"]
    fake.raw.clear()
    assert act.position() == 2066                        # 2086 - 20, the rig's numbers
    assert fake.moves_and_counter() == ["mr", "1TP", "ml"]   # TP needs remote mode

    # A run (the coarse approach): remote and amplitude once, then one
    # command per step -- Igor's dadada, not four commands and four checks.
    fake.raw.clear()
    act.begin_run(closer=True)
    for _ in range(3):
        act.step(closer=True)
    assert act.position() == 2066 + 60                   # in a run: TP straight away
    act.end_run()
    assert fake.moves_and_counter() == ["mr", "1SU50", "1PR20", "1PR20", "1PR20",
                                        "1TP", "ml"]
    fake.raw.clear()
    act.step(closer=False)                               # back to the button sequence
    assert fake.moves() == ["mr", "1SU-50", "1PR-20", "ml"]
    assert act.position() == 2066 + 40
    fake.raw.clear()
    act.step(closer=True)
    assert fake.moves() == ["mr", "1SU50", "1PR20", "ml"]
    assert act.position() == 2066 + 60

    cfg.actuator.closer_sign = -1                        # actuator mounted the other way
    fake.raw.clear()
    act.step(closer=True)
    assert fake.moves() == ["mr", "1SU-50", "1PR-20", "ml"]

    # A refused command is an error, not a silent no-move (TE-5: local mode).
    fake.remote = False
    fake.ignore_mr = True
    with pytest.raises(ActuatorError, match="TE-5"):
        act.step(closer=False)
    fake.ignore_mr = False
    act.close()
    assert fake.closed

    # A box that is switched off answers nothing, and Connect says so.
    asleep = FakeVisa(awake=False)
    dead = AgilisActuator(cfg, port="COM4", rm_factory=lambda backend: asleep)
    with pytest.raises(ActuatorError, match="switched off or asleep"):
        dead.identify()

    # An AG-UC8 selects its channel on open (Igor's Z sends no CC: channel 0).
    cfg.actuator.channel = 2
    cfg.actuator.axis = 2
    fake8 = FakeVisa()
    AgilisActuator(cfg, port="COM4", rm_factory=lambda backend: fake8)
    assert fake8.sent == ["mr", "CC2", "ml"]


def test_connect_picks_the_controller_kind(ap, cfg, tmp_path):
    guard, rig = ap.open_rig(cfg)
    mon = ap.Monitor(rig)
    worker = ap.Worker(cfg, rig, mon, save=False, out_dir=tmp_path,
                       igor_export=False)
    try:
        worker.cmd_actuator("connect", "COM4", "agilis")
        assert worker.a_state["connected"] and worker.a_state["controller"] == "agilis"
        assert cfg.actuator.kind == "agilis" and cfg.actuator.port == "COM4"
        worker.cmd_actuator("connect", "COM1", "nanopz")
        assert cfg.actuator.kind == "nanopz" and cfg.actuator.port == "COM1"
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_port_that_will_not_open_names_the_ports(cfg):
    from stmlab.actuator import NanoPZActuator, ActuatorError

    def refuse(**kw):
        raise OSError("could not open port 'COM1'")
    with pytest.raises(ActuatorError, match="could not open 'COM1'"):
        NanoPZActuator(cfg, port="COM1", serial_factory=refuse)


def test_connect_then_coarse_approach_aims_the_contact_mid_range(ap, cfg, tmp_path):
    """The window's flow on the simulator: Connect attaches the actuator,
    Start approach steps the sample in with the piezo at its low end until
    current, then aims -- single steps apart, a scan, the measured step
    size -- until the contact sits in the band, opens the junction by a
    few nanometres and leaves the piezo there; the piezo Approach then
    makes the contact mid range."""
    from stmlab.safety import RigState
    cfg.actuator.kind = "none"                   # nothing configured yet
    guard, rig = ap.open_rig(cfg)
    mon = ap.Monitor(rig)
    worker = ap.Worker(cfg, rig, mon, save=False, out_dir=tmp_path,
                       igor_export=False)
    try:
        worker.cmd_coarse_approach()             # refused: nothing connected
        texts = [p["text"] for k, p in list(worker.events.queue) if k == "status"]
        assert any("press Connect" in t for t in texts)
        worker.cmd_actuator("ports")
        worker.cmd_actuator("connect", "COM5")
        assert worker.a_state["connected"] and worker.a_state["port"] == "COM5"
        assert cfg.actuator.kind == "nanopz" and cfg.actuator.port == "COM5"
        worker.cmd_zero()
        rig._session.move_surface(400.0)         # the surface out of the piezo's reach
        worker.cmd_coarse_approach()
        assert rig.coarse_steps >= 2             # stepped in until current, then aimed
        lo, hi = cfg.actuator.band_lo_v, cfg.actuator.band_hi_v
        assert lo - 0.5 <= rig.piezo_v <= hi     # open, just under the contact, in band
        assert rig.read_current_ua() < cfg.actuator.stop_current_ua   # open
        texts = [p["text"] for k, p in list(worker.events.queue) if k == "status"]
        done = [t for t in texts if t.startswith("coarse approach done")]
        assert done and "junction opened" in done[-1] and "one single actuator step" in done[-1]
        worker.cmd_engage()
        assert rig.state == RigState.ENGAGED
        assert lo - 0.5 <= rig.piezo_v <= hi + 0.5    # the contact is mid range
        before = rig.coarse_steps
        worker.cmd_coarse_step(True)             # closer into a closed junction
        assert rig.coarse_steps == before        # refused
        texts = [p["text"] for k, p in list(worker.events.queue) if k == "status"]
        assert any("Step closer refused" in t for t in texts)
        acts = [p for k, p in list(worker.events.queue) if k == "actuator"]
        assert acts[-1]["connected"] and acts[-1]["steps"] == rig.coarse_steps
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


# -- histograms of a saved session --------------------------------------------------

def test_histogram_2d_aligns_each_trace_at_the_break(cfg):
    from stmlab import analysis
    n = 2000
    disp = analysis.displacement_nm(n, cfg.ramp)
    # Two traces: a 1 G0 plateau that breaks at different points, then a
    # tunnelling decay. Aligned at 0.5 G0 the breaks must coincide at 0 nm.
    traces = []
    for k_break in (600, 1200):
        g = np.where(np.arange(n) < k_break, 1.0,
                     10.0 ** (-10.0 * (disp - disp[k_break])))
        traces.append(g)
    counts, xe, ye = analysis.histogram_2d(traces, disp, align_at_g0=0.5,
                                           x_range=(-0.5, 1.0), n_x=150,
                                           y_range=(-7, 1), n_y=160)
    assert counts.shape == (150, 160)
    # The plateau column (log G = 0) is filled only at x < 0 for both traces
    # and the two traces' plateaus end in the same x bin: the alignment.
    j0 = np.searchsorted(ye, 0.0) - 1
    filled = np.flatnonzero(counts[:, j0] > 0)
    assert xe[filled[-1] + 1] <= 0.0 + 1e-9
    # Unaligned, 0 nm is the pull's start and the plateaus sit at x > 0.
    counts2, xe2, _ = analysis.histogram_2d(traces, disp, align_at_g0=None,
                                            x_range=(-0.5, 1.0), n_x=150,
                                            y_range=(-7, 1), n_y=160)
    assert np.flatnonzero(counts2[:, j0] > 0).min() >= np.searchsorted(xe2, 0.0) - 1


def test_histogram_windows_draw_and_redraw(ap, cfg, tmp_path):
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no Tk display: {exc}")
    from tkinter import ttk
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    guard, rig = ap.open_rig(cfg)
    mon = ap.Monitor(rig)
    worker = ap.Worker(cfg, rig, mon, save=True, out_dir=tmp_path,
                       igor_export=False)
    try:
        worker.cmd_run(3, {"folder": tmp_path, "name": "leo", "experiment": "au"})
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)
    h5 = list(tmp_path.rglob("*traces.h5"))[0]
    status = ttk.Label(root)
    try:
        with storage.Session(h5) as sess:
            for kind in ("1d", "2d"):
                win = tk.Toplevel(root)
                ctl = ap.hist_window(win, sess, h5.stem, kind, tk, ttk,
                                     FigureCanvasTkAgg, Figure, status)
                if kind == "1d":
                    ctl["lw"].set("2.5")
                    ctl["color"].set("tab:blue")
                    ctl["logy"].set(True)
                else:
                    ctl["cmap"].set("magma")
                    ctl["align"].set("")
                    ctl["vmax"].set("5")
                ctl["redraw"]()
                root.update()
                win.destroy()
    finally:
        root.destroy()


def test_the_whole_window_opens_runs_and_closes(tmp_path):
    """pullout.py as typed at the prompt, on the simulator, closing itself
    after a few seconds: it must lay out every widget, start the smoke run
    and shut down without a traceback. The only test that builds the whole
    window, so a layout mistake (a widget packed into a frame that no longer
    exists, say) fails here rather than at the rig."""
    tk = pytest.importorskip("tkinter")
    try:
        tk.Tk().destroy()
    except tk.TclError as exc:
        pytest.skip(f"no Tk display: {exc}")
    root_dir = Path(__file__).resolve().parents[1]
    cmd = [sys.executable, str(root_dir / "pullout.py"), "--simulate",
           "--out", str(tmp_path), "--autoclose", "4"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                         cwd=root_dir)
    assert res.returncode == 0, res.stderr[-3000:]
    assert "Traceback" not in res.stderr, res.stderr[-3000:]
    # The window remembers its Saving tab in the --out folder, not in data/.
    assert (tmp_path / "pullout_saving.json").exists()


# -- the Keithley tab, on the simulated amplifier ----------------------------------

def test_find_suppress_refuses_a_sweep_the_amplifier_did_not_follow(ap, cfg, tmp_path):
    """Seen on the rig: swept with the suppress off, the output stays flat,
    the fit through the noise puts the zero crossing anywhere, and that
    value switched on rails the amplifier. A flat sweep now ends with the
    suppress at 0 and OFF and a message, never a stray microamp."""
    guard, rig = ap.open_rig(cfg)
    mon = ap.Monitor(rig)
    worker = ap.Worker(cfg, rig, mon, save=False, out_dir=tmp_path,
                       igor_export=False)
    try:
        worker.cmd_keithley("connect")
        rig._session.keithley = None            # the card no longer sees the suppress
        worker.cmd_keithley("find_suppress")
        assert worker.k_state["suppress"] is False
        assert worker.k_state["suppress_ua"] == 0.0
        assert worker.keithley.commands[-2:] == ["H8S0,0X", "N0X"]
        texts = [p["text"] for k, p in list(worker.events.queue) if k == "status"]
        assert any("did not behave" in t and "Calibrate zero" in t for t in texts)
        assert rig.bias_v == pytest.approx(cfg.ramp.bias_v)   # bias restored
    finally:
        worker.close_keithley()
        worker.close_file()
        ap.close_rig(guard, rig)


def test_keithley_commands_track_the_amplifier_state(ap, cfg, tmp_path):
    guard, rig = ap.open_rig(cfg)
    mon = ap.Monitor(rig)
    worker = ap.Worker(cfg, rig, mon, save=False, out_dir=tmp_path,
                       igor_export=False)
    try:
        worker.cmd_keithley("connect")
        k = worker.keithley
        assert k.commands == []                       # joined without touching it
        assert worker.k_state["zero_check"] is None   # unknown until a button
        worker.cmd_keithley("zero_check", True)
        assert k.commands[-1] == "C1X" and worker.k_state["zero_check"] is True
        worker.cmd_keithley("find_suppress")          # refused: zero check on
        assert worker.k_state["suppress"] is None
        worker.cmd_keithley("zero_correct")           # on, correct, off
        assert k.commands[-3:] == ["C1X", "C2X", "C0X"]
        assert worker.k_state["zero_check"] is False
        worker.cmd_keithley("find_suppress")
        assert worker.k_state["suppress"] is True
        n1 = k.commands.index("N1X")                   # switched ON before the sweep,
        assert any(c.startswith("H8S") for c in k.commands[n1:])   # then swept and set
        assert abs(worker.k_state["suppress_ua"]) < 0.01            # a sane offset
        assert rig.bias_v == pytest.approx(cfg.ramp.bias_v)   # bias restored
        worker.cmd_keithley("gain", 7)
        assert cfg.keithley.gain_exponent == 7
        assert cfg.cal.preamp_gain_v_per_a == pytest.approx(1e7)
        events = [kind for kind, _ in list(worker.events.queue)]
        assert events.count("keithley") >= 4
        worker.close_keithley()
        assert "C1B0N0X" not in k.commands             # never left in zero check
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


# -- the trace plot with the readback over it -----------------------------------

def test_trace_plot_draws_the_readback_retraction_on_a_right_axis(ap, cfg):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    from stmlab import analysis

    cfg.channels.low_res_device = "dev2"
    n = cfg.ramp.n_pull_samples
    disp = analysis.displacement_nm(n, cfg.ramp)
    g0 = np.full(n, 1e-5)
    # A readback that follows the command exactly: the piezo starts at 5 V
    # and retracts by disp, so the sense line reads that position in nm.
    pos_nm = cfg.cal.piezo_volts_to_nm(5.0) - disp
    sense = pos_nm / cfg.cal.sense_nm_per_volt + cfg.cal.sense_zero_v

    ax = Figure().add_subplot(111)
    ap.plots.plot_trace(ax, cfg, g0, disp, None, sense_v=sense)
    twin = ax._stm_twin
    assert twin.get_visible()
    retract = twin.lines[-1].get_ydata()
    assert retract[0] == 0.0                                    # zeroed
    assert retract[-1] == pytest.approx(disp[-1], abs=0.1)     # 5 nm back
    assert retract[n // 2] == pytest.approx(disp[n // 2], abs=0.05)

    # Without a readback the right axis is hidden, not left with stale lines.
    ap.plots.plot_trace(ax, cfg, g0, disp, None, sense_v=None)
    assert not ax._stm_twin.get_visible()


# -- a headless cycle end to end --------------------------------------------------

def test_headless_cycles_save_and_export(ap, cfg, tmp_path):
    guard, rig = ap.open_rig(cfg)
    mon = ap.Monitor(rig)
    worker = ap.Worker(cfg, rig, mon, save=True, out_dir=tmp_path,
                       igor_export=True)
    try:
        worker.cmd_zero()
        worker.cmd_run(3)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)
    h5 = list(tmp_path.rglob("*.h5"))
    assert len(h5) == 1
    # <folder>/<date>/<name>/<experiment>_<HHMMSS>_<N>traces.h5
    assert h5[0].parent.name == "unknown"
    assert h5[0].parent.parent.name == time.strftime("%Y-%m-%d")
    assert h5[0].name.endswith(f"_{worker.accepted}traces.h5")
    with storage.Session(h5[0]) as s:
        assert len(s) == worker.accepted >= 1
    pytest.importorskip("igor2")
    ibw = list(tmp_path.rglob("*.ibw"))
    assert len(ibw) == 1
    traces, params = storage.split_igor_block(storage.load_ibw(ibw[0]))
    assert traces.shape == (worker.accepted, cfg.ramp.n_pull_samples)
    assert np.all(params[:, 10] == pytest.approx(cfg.ramp.bias_v * 1e3))
