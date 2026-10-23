"""pullout.py saving in Igor's scheme (v65): every run goes into the day
folder <data folder>/MM_DD<SetupID>YYMerge as PullOut*Block_k.ibw blocks
numbered through the day, with the raw .h5, the .txt and experiment_log.csv
beside them; the numbering carries on from the folder; the window's browser
opens a day folder or one block. Simulator only, no hardware, no display.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("igor2")

from stmlab import igor_scheme, storage        # noqa: E402
from stmlab.config import RigConfig            # noqa: E402


@pytest.fixture(scope="module")
def ap():
    import pullout
    return pullout


@pytest.fixture
def cfg():
    c = RigConfig()
    c.simulate = True
    return c


def _worker(ap, cfg, tmp_path, igor=True):
    guard, rig = ap.open_rig(cfg)
    mon = ap.Monitor(rig)
    worker = ap.Worker(cfg, rig, mon, save=True, out_dir=tmp_path, igor_export=igor)
    return guard, rig, worker


def _day(root: Path, setup_id: str = "_") -> Path:
    return root / igor_scheme.day_folder_name(None, setup_id)


def _events(worker, kind):
    return [p for k, p in list(worker.events.queue) if k == kind]


# -- the version ---------------------------------------------------------------------

def test_version_is_v65(ap):
    assert ap.__version__ == "v65"


# -- headless: the whole path, twice, with the simulator ---------------------------------

def test_headless_runs_write_a_day_folder_and_the_second_run_continues_the_numbering(
        ap, cfg, tmp_path):
    cfg.channels.low_res_device = "dev2"         # the simulator then has a sense line
    assert ap.run_headless(cfg, 3, tmp_path, True, False) == 0
    day = _day(tmp_path)
    assert day.is_dir(), list(tmp_path.iterdir())
    names = sorted(p.name for p in day.iterdir())
    for want in ("PullOutConductanceBlock_1.ibw", "PullOutVoltageBlock_1.ibw",
                 "PullOutCurrentBlock_1.ibw", "PullOutExtensionBlock_1.ibw",
                 "PullOutConductanceBlockHist_1.ibw", "experiment_log.csv"):
        assert want in names, names
    assert not any(n.startswith("PullOutPiezoBiasWave") for n in names)   # off by default
    h5 = [n for n in names if n.endswith(".h5")]
    assert h5 == ["experiment_" + h5[0].split("_")[1] + "_3traces.h5"] or \
        (len(h5) == 1 and h5[0].endswith("_3traces.h5"))
    # Nothing outside the day folder but the folder itself.
    assert [p.name for p in tmp_path.iterdir()] == [day.name]

    b = igor_scheme.read_block(day, 1)
    assert b.g0.shape == (cfg.ramp.n_pull_samples, 3)
    assert list(b.numbers) == [1, 2, 3]
    assert b.params.shape == (3, 20)
    assert b.params[0, 0] == pytest.approx(cfg.ramp.pull_length_nm)
    assert b.params[0, 1] == pytest.approx(cfg.ramp.pull_rate_nm_per_s)
    assert b.params[0, 10] == pytest.approx(cfg.ramp.bias_v * 1e3)
    assert b.params[0, 4] == 1.0                                 # Voltage block written
    # Igor's DateTime: LOCAL seconds since 1904 (float32, so ~256 s resolution)
    assert abs(b.params[0, 17] - igor_scheme.igor_datetime(time.time())) < 600
    assert b.voltage_v.shape == b.current_a.shape == b.extension_nm.shape == b.g0.shape
    assert b.hist is not None and b.hist.shape == (igor_scheme.HIST_POINTS,)
    # The whole 100-column block is on disk, NaN where no trace is yet.
    wave = igor_scheme.read_wave(day / "PullOutConductanceBlock_1.ibw")
    assert wave.data.dtype == np.float32
    assert wave.data.shape == (cfg.ramp.n_pull_samples + igor_scheme.TAIL_ROWS, 100)
    assert np.isnan(wave.data[:, 3:]).all()
    assert wave.note.startswith("pullout v65;") and "traces 1-3" in wave.note
    assert igor_scheme.IgorDayWriter.scan(day) == (1, 3)
    assert ap.next_trace_number(day) == 4

    # A second launch: the numbering continues and the same block is refilled.
    assert ap.run_headless(cfg, 2, tmp_path, True, False) == 0
    assert igor_scheme.list_blocks(day) == [1]
    b = igor_scheme.read_block(day, 1)
    assert list(b.numbers) == [1, 2, 3, 4, 5]
    assert b.voltage_v.shape == (cfg.ramp.n_pull_samples, 5)
    assert ap.next_trace_number(day) == 6
    assert len(list(day.glob("*traces.h5"))) == 2
    with open(day / "experiment_log.csv", newline="") as f:
        lines = list(csv.reader(f))
    assert len(lines) == 1 + 2 * 2
    assert "Igor traces 1-3 in " + day.name in lines[1][6]
    assert "Igor traces 4-5 in " + day.name in lines[3][6]
    assert Path(lines[2][0]).parent == day.resolve()


# -- the worker, as the window drives it ------------------------------------------------

def test_a_run_files_everything_in_the_day_folder(ap, cfg, tmp_path):
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_zero()
        worker.cmd_cycle()                       # a single cycle: not saved
        assert not _day(tmp_path).exists()
        worker.cmd_run(2, {"folder": tmp_path, "name": "Leo Z",
                           "experiment": "clean gold", "txt": True})
        day = _day(tmp_path)
        h5 = list(day.glob("clean_gold_*_2traces.h5"))
        assert len(h5) == 1
        txt = h5[0].with_suffix(".txt")
        assert txt.exists() and txt.with_name(txt.stem + "_info.txt").exists()
        table = np.loadtxt(txt)
        assert table.shape[1] == 3                # displacement + 2 traces
        assert worker.accepted == 2
        assert worker.saved_today() == 2
        assert worker.run_numbers == [1, 2]
        # The Status box's "Saved" is the day counter.
        worker.readout()
        ro = _events(worker, "readout")[-1]
        assert ro["saved"] == 2 and ro["igor_folder"] == str(day)
        # A second run is a second .h5 but the same Igor block, traces 3-5.
        worker.cmd_run(3, {"experiment": "OPE3"})
        assert len(list(day.glob("OPE3_*_3traces.h5"))) == 1
        assert worker.run_numbers == [3, 4, 5]
        b = igor_scheme.read_block(day, 1, companions=False)
        assert list(b.numbers) == [1, 2, 3, 4, 5]
        assert (day / "experiment_log.csv").exists()
        assert not (tmp_path / "experiment_log.csv").exists()
        import h5py
        with h5py.File(h5[0]) as h:
            assert h.attrs["program"] == "pullout v65"
            assert h.attrs["operator"] == "Leo Z"
            assert h.attrs["setup_id"] == "_"
            assert "Igor traces 1-2 in " + day.name in h.attrs["auto_notes"]
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_stop_writes_the_partial_block_and_continue_refills_it(ap, cfg, tmp_path):
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_run(1, {"folder": tmp_path, "name": "leo", "experiment": "au"})
        day = _day(tmp_path)
        assert igor_scheme.IgorDayWriter.scan(day) == (1, 1)     # on disk already
        worker.stop_flag.set()
        worker.cmd_run(3, {"experiment": "au2"})     # pauses at once: nothing taken
        assert worker.paused == {"remaining": 3}
        worker.stop_flag.clear()
        worker.cmd_continue()
        assert worker.paused is None and worker.run_stem is None
        assert igor_scheme.IgorDayWriter.scan(day) == (1, 4)
        b = igor_scheme.read_block(day, 1, companions=False)
        assert list(b.numbers) == [1, 2, 3, 4]
        assert len(list(day.glob("au2_*_3traces.h5"))) == 1
        wave = igor_scheme.read_wave(day / "PullOutConductanceBlock_1.ibw")
        assert "experiment=au2" in wave.note and "traces 1-4" in wave.note
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_the_flags_choose_the_companion_files_and_h5_can_be_left_out(ap, cfg, tmp_path):
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_run(1, {"folder": tmp_path, "name": "leo", "experiment": "au",
                           "bias": False, "current": False, "hist": False,
                           "piezo_wave": True, "h5": False})
        day = _day(tmp_path)
        names = sorted(p.name for p in day.iterdir())
        assert names == ["PullOutConductanceBlock_1.ibw", "PullOutPiezoBiasWave_1.ibw",
                         "experiment_log.csv"]
        b = igor_scheme.read_block(day, 1)
        assert b.params[0, 4] == 0.0                 # BiasSave off
        assert b.voltage_v is None and b.current_a is None and b.hist is None
        ramp = igor_scheme.read_wave(day / "PullOutPiezoBiasWave_1.ibw").data
        assert ramp.dtype == np.float64 and ramp.shape == (cfg.ramp.n_pull_samples,)
        assert ramp[0] == 0.0 and ramp[-1] < 0      # starts at 0, goes negative
        with open(day / "experiment_log.csv", newline="") as f:
            lines = list(csv.reader(f))
        assert Path(lines[2][0]) == day.resolve()    # no .h5: the folder is the data
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_no_igor_writes_only_the_h5_in_the_day_folder(ap, cfg, tmp_path):
    guard, rig, worker = _worker(ap, cfg, tmp_path, igor=False)
    try:
        worker.cmd_run(1, {"folder": tmp_path, "name": "leo", "experiment": "au"})
        day = _day(tmp_path)
        names = sorted(p.name for p in day.iterdir())
        assert not any(n.startswith("PullOut") for n in names)
        assert any(n.endswith("_1traces.h5") for n in names)
        assert worker.igor is None and worker.saved_today() is None
        worker.readout()
        assert _events(worker, "readout")[-1]["saved"] is None
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_the_setup_id_names_the_folder_and_a_change_makes_a_new_writer(ap, cfg, tmp_path):
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_run(1, {"folder": tmp_path, "name": "leo", "experiment": "au",
                           "setup_id": "B"})
        day_b = _day(tmp_path, "B")
        assert day_b.is_dir() and day_b.name.endswith("B" + time.strftime("%y") + "Merge")
        first = worker.igor
        worker.cmd_run(1, {"setup_id": "_"})
        assert worker.igor is not first and worker.igor.folder == _day(tmp_path)
        assert igor_scheme.IgorDayWriter.scan(day_b) == (1, 1)
        assert igor_scheme.IgorDayWriter.scan(_day(tmp_path)) == (1, 1)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_folder_typed_during_a_run_waits_for_the_next_one(ap, cfg, tmp_path):
    """The window pushes every keystroke of the Saving tab into
    worker.saving; a run keeps the settings it started with, so its
    traces and files stay together."""
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.stop_flag.set()
        worker.cmd_run(2, {"folder": tmp_path, "name": "leo", "experiment": "au"})
        assert worker.paused == {"remaining": 2}
        worker.stop_flag.clear()
        worker.saving["folder"] = tmp_path / "elsewhere"      # typed while paused
        worker.saving["experiment"] = "typed_too_soon"
        worker.cmd_continue()
        day = _day(tmp_path)
        assert igor_scheme.IgorDayWriter.scan(day) == (1, 2)
        assert len(list(day.glob("au_*_2traces.h5"))) == 1
        assert not (tmp_path / "elsewhere").exists()
        # The next Start N takes the new settings.
        worker.cmd_run(1)
        assert igor_scheme.IgorDayWriter.scan(_day(tmp_path / "elsewhere")) == (1, 1)
        assert len(list(_day(tmp_path / "elsewhere").glob("typed_too_soon_*_1traces.h5"))) == 1
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_igor_parameters_carry_the_calibrate_zero_as_izero(ap, cfg, tmp_path):
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        cfg.cal.current_zero_v = 2e-3                # 2 mV at 1e6 V/A = 2 nA = 0.002 uA
        vzero, izero = worker.offsets()
        assert vzero == 0.0 and izero == pytest.approx(0.002)
        worker.cmd_run(1, {"folder": tmp_path, "name": "leo", "experiment": "au"})
        b = igor_scheme.read_block(_day(tmp_path), 1, companions=False)
        assert b.params[0, 15] == 0.0
        assert b.params[0, 16] == pytest.approx(0.002, rel=1e-5)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


# -- what the Saving tab remembers --------------------------------------------------------

def test_saving_settings_remember_the_setup_id_and_the_flags(ap, tmp_path):
    f = tmp_path / "s.json"
    sv = dict(ap.DEFAULT_SAVING, folder=tmp_path / "d", name="leo", experiment="x",
              setup_id="B", sense=False, piezo_wave=True, h5=False)
    ap.save_saving(f, sv)
    back = ap.load_saving(f)
    assert back["setup_id"] == "B" and back["sense"] is False
    assert back["piezo_wave"] is True and back["h5"] is False and back["txt"] is False
    assert Path(back["folder"]) == tmp_path / "d"
    assert set(ap.IGOR_FLAG_KEYS) <= set(ap.DEFAULT_SAVING)
    assert ap.load_saving(tmp_path / "missing.json") == {}
    # The worker reads its flags from the same keys.
    flags = igor_scheme.SaveFlags(**{k: sv[k] for k in ap.IGOR_FLAG_KEYS})
    assert flags.sense is False and flags.piezo_wave is True and flags.bias is True


# -- the browser: a day folder, one block, the legacy export ------------------------------

def test_igor_day_opens_a_folder_or_a_block_for_browsing(ap, cfg, tmp_path):
    cfg.channels.low_res_device = "dev2"
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_run(3, {"folder": tmp_path, "name": "leo", "experiment": "au"})
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)
    day = _day(tmp_path)
    d = ap.IgorDay(day)
    assert len(d) == 3 and d.describe() == "block 1, Igor traces 1-3"
    assert d.cfg.ramp.pull_length_nm == pytest.approx(cfg.ramp.pull_length_nm)
    assert d.cfg.ramp.bias_v == pytest.approx(cfg.ramp.bias_v)
    t = d.trace(2)
    n = cfg.ramp.n_pull_samples
    assert t["number"] == 3 and t["block"] == 1
    assert t["g0"].shape == t["disp"].shape == (n,)
    assert t["disp"][0] == 0.0 and t["disp"][-1] == pytest.approx(cfg.ramp.pull_length_nm)
    assert t["fs"] == pytest.approx(cfg.ramp.sample_rate_hz)
    assert t["voltage_v"].shape == t["current_a"].shape == t["extension_nm"].shape == (n,)
    assert t["block_hist"].shape == (igor_scheme.HIST_POINTS,)
    centres, counts = d.hist
    assert centres.shape == counts.shape == (1000,) and counts.max() > 0
    data = d.data()
    assert data.n == 3 and len(data.disps) == 3 and data.name == day.name
    assert len(list(d.conductances())) == 3

    one = ap.IgorDay(day / "PullOutConductanceBlock_1.ibw")
    assert len(one) == 3 and one.name == "PullOutConductanceBlock_1"
    assert one.trace(0)["number"] == 1

    # This program's old export (NaN blank rows, no companions) opens too.
    traces = [t["g0"] for t in (d.trace(i) for i in range(3))]
    old = tmp_path / "old_b000.ibw"
    storage.save_igor_block(old, cfg, traces, name="old_b000")
    legacy = ap.IgorDay(old)
    assert len(legacy) == 3 and legacy.trace(1)["voltage_v"] is None
    assert legacy.trace(1)["number"] == 2

    with pytest.raises(ValueError):
        ap.IgorDay(tmp_path)                       # no blocks in it


# -- when the disk lets go: Stop, a NAS that drops, a folder that will not open ---------

def test_stop_mid_run_puts_the_block_on_disk_while_the_h5_stays_open(ap, cfg, tmp_path):
    """Stop after the first trace of a run: the partial block is in the
    Igor files at once (the window's Stop is a save), the .h5 stays open
    for Continue, and Continue refills the same block and the same .h5."""
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        plain = worker.readout

        def readout():                            # Stop, pressed after the first trace
            plain()
            if worker.accepted >= 1:
                worker.stop_flag.set()
        worker.readout = readout
        worker.cmd_run(3, {"folder": tmp_path, "name": "leo", "experiment": "au"})
        day = _day(tmp_path)
        assert worker.paused == {"remaining": 2}
        assert igor_scheme.IgorDayWriter.scan(day) == (1, 1)
        assert list(igor_scheme.read_block(day, 1, companions=False).numbers) == [1]
        assert worker.writer is not None and worker.writer.path.exists()
        assert not _events(worker, "error")
        worker.readout = plain
        worker.stop_flag.clear()
        worker.cmd_continue()
        assert worker.paused is None and worker.run_stem is None
        assert igor_scheme.IgorDayWriter.scan(day) == (1, 3)
        assert len(list(day.glob("au_*_3traces.h5"))) == 1
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_failed_igor_flush_still_closes_the_run_and_renames_the_h5(
        ap, cfg, tmp_path, monkeypatch):
    """The NAS drops as the run ends: the Igor block cannot be written.
    The .h5 is still closed and renamed, the .txt and the log row are
    written, the window is told the run is over, and the block goes to
    disk the next time a write succeeds (its traces stay in the writer)."""
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_run(1, {"folder": tmp_path, "name": "leo", "experiment": "au",
                           "txt": True})
        day = _day(tmp_path)
        assert igor_scheme.IgorDayWriter.scan(day) == (1, 1)
        real = igor_scheme.write_ibw
        nas = {"gone": True}

        def write_ibw(path, *args, **kw):
            if nas["gone"]:
                raise OSError(5, "Input/output error", str(path))
            return real(path, *args, **kw)
        monkeypatch.setattr(igor_scheme, "write_ibw", write_ibw)
        worker.cmd_run(1, {"experiment": "au2"})          # the flush at the end fails
        assert worker.run_stem is None and worker.paused is None
        assert len(list(day.glob("au2_*_1traces.h5"))) == 1
        assert len(list(day.glob("au2_*_1traces.txt"))) == 1
        with open(day / "experiment_log.csv", newline="") as f:
            assert len(list(csv.reader(f))) == 1 + 2 * 2
        errors = _events(worker, "error")
        assert errors and all(not e["fatal"] for e in errors)
        assert any("Igor block 1 not written" in e["text"] and
                   "Input/output error" in e["text"] for e in errors)
        assert _events(worker, "experiment")[-1] == {"stem": None}
        assert _events(worker, "file")[-1] == {"path": None}
        assert _events(worker, "paused")[-1] == {"remaining": 0}
        assert igor_scheme.IgorDayWriter.scan(day) == (1, 1)   # the disk did not change
        worker.close_file()                                    # does not raise either
        # The disk is back: the next run's flush writes traces 1-3.
        nas["gone"] = False
        worker.cmd_run(1, {"experiment": "au3"})
        assert igor_scheme.IgorDayWriter.scan(day) == (1, 3)
        assert list(igor_scheme.read_block(day, 1, companions=False).numbers) == [1, 2, 3]
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_an_unreadable_igor_folder_turns_the_igor_files_off_for_the_session(
        ap, cfg, tmp_path, monkeypatch):
    """The day folder cannot be opened (not only igor2 missing): one
    non-fatal error naming the folder, the run goes on .h5-only, and the
    next Start N does not complain again."""
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        def no_folder(self, root, cfg, **kw):
            raise OSError(5, "Input/output error", str(root))
        monkeypatch.setattr(igor_scheme.IgorDayWriter, "__init__", no_folder)
        worker.cmd_run(1, {"folder": tmp_path, "name": "leo", "experiment": "au"})
        day = _day(tmp_path)
        assert worker.igor is None and worker.igor_export is False
        assert worker.run_stem is None and worker.accepted == 1
        assert len(list(day.glob("au_*_1traces.h5"))) == 1
        assert not list(day.glob("PullOut*.ibw"))
        errors = _events(worker, "error")
        assert len(errors) == 1 and not errors[0]["fatal"]
        text = errors[0]["text"]
        assert "Igor files OFF for this session" in text and str(day) in text
        assert "Input/output error" in text and ".h5 is still written" in text
        worker.cmd_run(1, {"experiment": "au2"})
        assert len(_events(worker, "error")) == 1
        assert len(list(day.glob("au2_*_1traces.h5"))) == 1
        assert worker.saved_today() is None
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_failed_igor_append_is_reported_and_the_run_goes_on(
        ap, cfg, tmp_path, monkeypatch):
    """The NAS drops for one trace: that trace is not in the Igor files
    (the error says so, and that the .h5 has it); the run is not aborted
    and the next trace takes the number."""
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        real = igor_scheme.IgorDayWriter.append
        calls = []

        def append(self, t):
            calls.append(t.n)
            if len(calls) == 1:
                raise OSError(5, "Input/output error")
            return real(self, t)
        monkeypatch.setattr(igor_scheme.IgorDayWriter, "append", append)
        worker.cmd_run(2, {"folder": tmp_path, "name": "leo", "experiment": "au"})
        day = _day(tmp_path)
        assert worker.accepted == 2 and worker.run_stem is None
        errors = _events(worker, "error")
        assert len(errors) == 1 and not errors[0]["fatal"]
        text = errors[0]["text"]
        assert "Igor block 1" in text and "not written" in text
        assert "Input/output error" in text and "still in the .h5" in text
        assert [p["number"] for p in _events(worker, "saved")] == [None, 1]
        assert worker.run_numbers == [1]
        h5 = list(day.glob("au_*_2traces.h5"))
        assert len(h5) == 1
        with storage.Session(h5[0]) as s:
            assert len(s) == 2
        assert igor_scheme.IgorDayWriter.scan(day) == (1, 1)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


# -- the block status comes from the trace number ----------------------------------------

def _fake_traces(cfg, count: int) -> list:
    """``count`` traces of the rig's length, as another run would have
    left them in a block."""
    n = cfg.ramp.n_pull_samples
    params = igor_scheme.igor_parameters(cfg, 0.0, time.time())
    g0 = np.logspace(0.5, -5, n)
    return [igor_scheme.IgorTrace(g0, np.full(n, 0.1), g0 * 7.748e-5 * 0.1,
                                  None, None, params)
            for _ in range(count)]


def test_the_block_status_follows_the_trace_number(ap, cfg, tmp_path):
    """Trace 100 completes block 1 whoever took traces 1-98 before this
    run; a trace of another length moves on to the next block without
    completing one, and the status says which happened."""
    day = _day(tmp_path)
    igor_scheme.write_block_files(day, 1, _fake_traces(cfg, 98), cfg,
                                  igor_scheme.SaveFlags(), note="pullout test; traces 1-98")
    assert igor_scheme.IgorDayWriter.scan(day) == (1, 98)
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_run(3, {"folder": tmp_path, "name": "leo", "experiment": "au"})
        assert worker.run_numbers == [99, 100, 101]
        texts = [p["text"] for p in _events(worker, "status")]
        assert texts.count(f"Igor block 1 complete: traces 1-100 in {day.name}") == 1
        assert not any("trace length changed" in t for t in texts)
        assert igor_scheme.list_blocks(day) == [1, 2]
        assert igor_scheme.IgorDayWriter.scan(day) == (2, 1)
        assert [(p["number"], p["block"]) for p in _events(worker, "saved")] == \
            [(99, 1), (100, 1), (101, 2)]

        # A longer pull from the second trace on (the .h5 off: it refuses a
        # changed length): block 2 is written with 101-102 as it is and
        # the numbering jumps to block 3 -- not "block 2 complete".
        plain = worker.readout

        def readout():
            plain()
            if worker.accepted == 1 and cfg.ramp.pull_length_nm == 5.0:
                cfg.ramp.pull_length_nm = 6.0
        worker.readout = readout
        worker.cmd_run(3, {"experiment": "au2", "h5": False})
        worker.readout = plain
        assert worker.run_numbers == [102, 201, 202]
        texts = [p["text"] for p in _events(worker, "status")]
        assert sum("complete" in t for t in texts) == 1
        jumped = [t for t in texts if t.startswith("trace length changed")]
        assert len(jumped) == 1
        assert "partial block 2 written, continuing in block 3" in jumped[0]
        assert igor_scheme.list_blocks(day) == [1, 2, 3]
        assert igor_scheme.IgorDayWriter.scan(day) == (3, 2)
        assert list(igor_scheme.read_block(day, 2, companions=False).numbers) == [101, 102]
        assert [(p["number"], p["block"]) for p in _events(worker, "saved")[3:]] == \
            [(102, 2), (201, 3), (202, 3)]
        assert not _events(worker, "error")
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


# -- the Saved counter follows the folder the Saving tab names ---------------------------

def test_the_saved_counter_is_unknown_after_the_folder_setup_id_or_day_changes(
        ap, cfg, tmp_path, monkeypatch):
    """Typed into the Saving tab between runs, another folder or Setup ID
    (or a new day) makes the day writer's count the wrong folder's: the
    worker says None and the window counts the folder's files itself. A
    run keeps its own folder, so typing during a pause changes nothing."""
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_run(1, {"folder": tmp_path, "name": "leo", "experiment": "au"})
        day = _day(tmp_path)
        assert worker.saved_today() == 1
        worker.readout()
        ro = _events(worker, "readout")[-1]
        assert ro["saved"] == 1 and ro["igor_folder"] == str(day)

        worker.saving["folder"] = tmp_path / "elsewhere"
        assert worker.saved_today() is None
        worker.readout()
        ro = _events(worker, "readout")[-1]
        assert ro["saved"] is None and ro["igor_folder"] is None
        worker.saving["folder"] = tmp_path
        assert worker.saved_today() == 1
        worker.saving["setup_id"] = "B"
        assert worker.saved_today() is None
        worker.saving["setup_id"] = "_"
        assert worker.saved_today() == 1
        tomorrow = igor_scheme.day_folder_name(time.time() + 86400, "_")
        monkeypatch.setattr(igor_scheme, "day_folder_name",
                            lambda when=None, setup_id="_": tomorrow)
        assert worker.saved_today() is None
        monkeypatch.undo()
        assert worker.saved_today() == 1

        # Paused: the run's folder counts, whatever is typed meanwhile.
        worker.stop_flag.set()
        worker.cmd_run(1, {"experiment": "au2"})
        assert worker.paused == {"remaining": 1}
        worker.saving["folder"] = tmp_path / "elsewhere"
        assert worker.saved_today() == 1
        worker.stop_flag.clear()
        worker.cmd_continue()
        assert worker.saved_today() is None               # the next run goes elsewhere
        assert igor_scheme.IgorDayWriter.scan(day) == (1, 2)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


# -- --headless saves as Start N does: the remembered Saving tab, --name, --experiment ----

def test_headless_takes_the_remembered_saving_tab_and_the_name_and_experiment_flags(
        ap, tmp_path, monkeypatch):
    """pullout --headless N uses what the Saving tab remembered (name,
    experiment, notes, the save boxes, the Setup ID) with --out for the
    folder; --name and --experiment say otherwise for this run."""
    root = tmp_path / "program"
    out = tmp_path / "out"
    monkeypatch.setattr(ap, "_ROOT", root)
    ap.save_saving(root / "data" / "pullout_saving.json",
                   dict(ap.DEFAULT_SAVING, folder=tmp_path / "elsewhere", setup_id="Q",
                        name="Masha", experiment="OPE3", notes="toluene", txt=True,
                        hist=False))
    assert ap.main(["--simulate", "--headless", "2", "--out", str(out)]) == 0
    day = _day(out, "Q")
    assert day.is_dir() and not (tmp_path / "elsewhere").exists()
    h5 = list(day.glob("OPE3_*_2traces.h5"))
    assert len(h5) == 1 and h5[0].with_suffix(".txt").exists()
    assert not list(day.glob("PullOutConductanceBlockHist_*.ibw"))
    assert igor_scheme.IgorDayWriter.scan(day) == (1, 2)
    import h5py
    with h5py.File(h5[0]) as h:
        assert h.attrs["operator"] == "Masha" and h.attrs["notes"] == "toluene"
    with open(day / "experiment_log.csv", newline="") as f:
        lines = list(csv.reader(f))
    assert lines[1][2:4] == ["Masha", "OPE3"] and lines[1][5] == "toluene"

    assert ap.main(["--simulate", "--headless", "1", "--out", str(out),
                    "--name", "leo", "--experiment", "au"]) == 0
    h5 = list(day.glob("au_*_1traces.h5"))
    assert len(h5) == 1 and h5[0].with_suffix(".txt").exists()   # the boxes still apply
    with h5py.File(h5[0]) as h:
        assert h.attrs["operator"] == "leo" and h.attrs["experiment"] == "au"
    assert igor_scheme.IgorDayWriter.scan(day) == (1, 3)
