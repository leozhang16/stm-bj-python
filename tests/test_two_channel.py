"""A current amplifier with two outputs, read as two channels (v66, v67).

Channel 1 (``channels.ai_current``) is the lower-gain output that follows
the junction through contact: contact is judged on it, exactly as with one
channel. Channel 2 (``channels.ai_current_2``, read when
``channels.current_channels`` is 2) is the higher-gain output: one more
input of the record's task, carried beside the (2, n) record, saved with
every trace and drawn beside channel 1 -- blue and red, nothing stitched.
Since v67 the junction-open test (the break threshold) is read from it,
and from channel 1 only where channel 2 is at its rail.

Simulator and a fake nidaqmx only: no card, no display. None of these
tests reads a number out of configs/*.json: those files are the rig's own,
and whoever runs the rig changes them.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from stmlab import analysis, approach, calibrate, igor_scheme, storage, trace
from stmlab.config import G0_SIEMENS, ConfigError, RigConfig, validate
from stmlab.instrument import Rig
from stmlab.sim import SimulatedDaqSession

ROOT = Path(__file__).resolve().parents[1]


def _two(seed_cfg: RigConfig | None = None) -> RigConfig:
    cfg = seed_cfg or RigConfig()
    cfg.simulate = True
    cfg.channels.ai_current_2 = "ai4"
    cfg.channels.current_channels = 2
    return cfg


def _rig_config() -> RigConfig:
    """The new rig as configs/newrig_2ch.json describes it at the time of
    writing -- one USB-6453, screws, both outputs of the amplifier at 1e4
    and 1e7 V/A, the card's 88 uV of noise in the simulation -- built here
    so that no test depends on the file."""
    cfg = _two()
    m = cfg.channels
    m.ao_piezo, m.ai_voltage, m.ai_current = "ao2", "ai1", "ai2"
    m.ai_piezo_sense, m.sense_device = "ai3", "Dev1"
    m.ai_terminal = m.sense_terminal = "rse"
    m.expected_product_type, m.low_res_expected_product_type = "USB-6453", None
    cfg.cal.preamp_gain_v_per_a, cfg.cal.preamp_gain_2_v_per_a = 1e4, 1e7
    cfg.cal.piezo_nm_per_volt = cfg.cal.sense_nm_per_volt = 600.0
    cfg.keithley.gain_exponent = 4
    cfg.actuator.kind = "none"
    cfg.sim.ai_noise_v_rms = 8.8e-5
    return cfg


def _traces(cfg: RigConfig, n: int, seed: int = 3) -> list:
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=seed))
    rig.open()
    got = []
    try:
        trace.trace_loop(rig, n=n, on_trace=lambda i, tr, sel: got.append((tr, sel)))
    finally:
        rig.close()
    return got


# --------------------------------------------------------------------------
# The config
# --------------------------------------------------------------------------

def test_one_channel_is_the_default_and_nothing_about_it_changes():
    m = RigConfig().channels
    assert m.current_channels == 1 and m.ai_current_2 is None
    assert not m.two_current_channels and m.current2_path is None
    assert m.ai_channels == ("Dev1/ai0", "Dev1/ai1")
    assert m.record_inputs == ("Dev1/ai0", "Dev1/ai1")


def test_two_channels_need_the_count_and_the_input():
    cfg = RigConfig()
    cfg.channels.ai_current_2 = "ai4"            # named, but not read
    assert not cfg.channels.two_current_channels
    validate(cfg)
    cfg.channels.current_channels = 2
    assert cfg.channels.two_current_channels
    assert cfg.channels.current2_path == "Dev1/ai4"
    assert cfg.channels.ai_channels == ("Dev1/ai0", "Dev1/ai1")   # still the record's two
    validate(cfg)


def test_the_scan_order_keeps_the_junction_voltage_after_the_sense_line():
    cfg = _two()
    cfg.channels.sense_device = "Dev1"
    cfg.channels.ai_piezo_sense = "ai3"
    # voltage, channel 1, channel 2, sense: the input scanned after the
    # (often railed) channel 2 is the sense line, not the junction voltage
    assert cfg.channels.record_inputs == ("Dev1/ai0", "Dev1/ai1", "Dev1/ai4", "Dev1/ai3")


def test_validate_refuses_a_count_without_an_input_and_a_shared_input():
    cfg = RigConfig()
    cfg.channels.current_channels = 2
    with pytest.raises(ConfigError, match="ai_current_2"):
        validate(cfg)
    cfg.channels.current_channels = 3
    with pytest.raises(ConfigError, match="1 or 2"):
        validate(cfg)
    for clash in ("ai0", "AI1"):                  # the voltage input, channel 1's
        cfg = _two()
        cfg.channels.ai_current_2 = clash
        with pytest.raises(ConfigError, match="same input"):
            validate(cfg)
    cfg = _two()
    cfg.channels.sense_device, cfg.channels.ai_piezo_sense = "Dev1", "ai4"
    with pytest.raises(ConfigError, match="same input"):
        validate(cfg)


def test_validate_says_so_when_channel_2_is_not_the_higher_gain():
    cfg = _two()
    assert not any("channel 2's gain" in w for w in validate(cfg))
    cfg.cal.preamp_gain_2_v_per_a = 1e5          # below channel 1's 1e6
    assert any("channel 2's gain" in w and "swap" in w for w in validate(cfg))
    cfg.cal.preamp_gain_2_v_per_a = 0.0
    with pytest.raises(ConfigError, match="preamp_gain_2"):
        validate(cfg)


def test_a_gain_of_zero_is_refused_before_anything_divides_by_it():
    cfg = RigConfig()
    cfg.cal.preamp_gain_v_per_a = 0.0
    with pytest.raises(ConfigError, match="positive"):
        validate(cfg)


def test_the_keithley_remark_is_only_made_about_whole_decades():
    cfg = RigConfig()
    cfg.keithley.gain_exponent = 7               # a decade, and not the calibration's
    assert any("keithley.gain_exponent" in w for w in validate(cfg))
    cfg.cal.preamp_gain_v_per_a = 4.7e6          # a measured or hand-typed gain
    assert not any("keithley.gain_exponent" in w for w in validate(cfg))


def test_the_config_round_trips_and_old_files_still_load(tmp_path):
    cfg = _two()
    cfg.cal.preamp_gain_2_v_per_a = 1e8
    cfg.cal.current_zero_2_v = 1.5e-4
    path = tmp_path / "two.json"
    cfg.to_json(path)
    back = RigConfig.from_json(path)
    assert back.channels.two_current_channels and back.channels.ai_current_2 == "ai4"
    assert back.cal.preamp_gain_2_v_per_a == 1e8 and back.cal.current_zero_2_v == 1.5e-4
    # a config written before v66 has none of the keys: one channel
    blob = json.loads(path.read_text())
    for key in ("ai_current_2", "current_channels"):
        blob["channels"].pop(key)
    for key in ("preamp_gain_2_v_per_a", "current_zero_2_v"):
        blob["cal"].pop(key)
    old = RigConfig.from_dict(blob)
    assert not old.channels.two_current_channels
    assert old.cal.preamp_gain_2_v_per_a == 1e9


def test_every_shipped_config_loads_and_passes_the_validator():
    """Whatever numbers a rig's file holds, it must load and validate.
    Nothing else is asserted about those files."""
    paths = sorted((ROOT / "configs").glob("*.json"))
    assert paths
    for path in paths:
        validate(RigConfig.from_json(path))


def test_the_new_rig_as_these_tests_build_it():
    cfg = _rig_config()
    validate(cfg)
    assert cfg.channels.record_inputs == ("Dev1/ai1", "Dev1/ai2", "Dev1/ai4", "Dev1/ai3")
    assert cfg.channels.two_current_channels and cfg.actuator.kind == "none"
    # no remark about the Keithley on a rig whose amplifier has two outputs,
    # whatever the exponent in its file says
    cfg.keithley.gain_exponent = 6
    assert not any("keithley.gain_exponent" in w for w in validate(cfg))


def test_the_calibration_converts_each_channel_with_its_own_numbers():
    cal = RigConfig().cal
    cal.preamp_gain_v_per_a, cal.current_zero_v = 1e6, 0.002
    cal.preamp_gain_2_v_per_a, cal.current_zero_2_v = 1e9, -0.05
    assert cal.volts_to_amps(1.002) == pytest.approx(1e-6)
    assert cal.volts_to_amps(0.95, channel=2) == pytest.approx(1e-9)
    assert cal.gain_of(1) == 1e6 and cal.gain_of(2) == 1e9
    g1 = analysis.to_conductance(np.array([1.002]), cal, bias_v=0.1)
    g2 = analysis.to_conductance(np.array([0.95]), cal, bias_v=0.1, channel=2)
    assert g1[0] == pytest.approx(1000 * g2[0])


# --------------------------------------------------------------------------
# The simulator and the rig
# --------------------------------------------------------------------------

def test_the_simulated_channel_2_rails_in_contact_and_carries_on_below_channel_1():
    cfg = _two()
    (tr, _), = _traces(cfg, 1)
    assert tr.current2_v is not None and tr.current2_v.size == tr.current_v.size
    g1, g2 = tr.conductance_g0(cfg), tr.conductance_g0(cfg, channel=2)
    n = g1.size
    # at the start of the pull the junction is closed: channel 1 reads the
    # contact, channel 2 sits at the card's range
    assert np.mean(g1[:50]) > 1.0
    assert np.allclose(tr.current2_v[:50], cfg.channels.ai_range_v)
    # in the tunnelling decay both read the same conductance (compared
    # where channel 1's own noise is a few percent of the reading)
    both = (g1 > 1e-5) & (g1 < 3e-4) & (np.abs(tr.current2_v) < 9.0)
    assert both.sum() > 20
    assert np.allclose(g1[both], g2[both], rtol=0.15)
    # and with the junction open channel 2's floor is the lower one
    tail = slice(int(0.90 * n), int(0.94 * n))
    assert np.std(g2[tail]) < 0.5 * np.std(g1[tail])


def test_reading_channel_2_does_not_move_a_sample_of_channel_1():
    one = RigConfig()
    one.simulate = True
    a = [tr for tr, _ in _traces(one, 2, seed=7)]
    b = [tr for tr, _ in _traces(_two(), 2, seed=7)]
    assert a[0].current2_v is None and b[0].current2_v is not None
    for x, y in zip(a, b):
        assert np.array_equal(x.current_v, y.current_v)
        assert np.array_equal(x.voltage_v, y.voltage_v)


def test_the_rig_switches_the_count_live_and_the_config_follows():
    cfg = _two()
    cfg.channels.current_channels = 1
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=2))
    rig.open()
    try:
        rig.hold(n_samples=200)
        assert rig.last_current2_v is None
        rig.set_current_channels(2)
        assert cfg.channels.two_current_channels
        record = rig.hold(n_samples=200)
        assert record.shape == (2, 200)              # the record is still two rows
        assert rig.last_current2_v.shape == (200,)
        reading = rig.channel2_of(record)
        assert set(reading) == {"volts", "amps", "g0", "railed"} and not reading["railed"]
        rig.set_current_channels(1)
        assert not cfg.channels.two_current_channels and rig.last_current2_v is None
        rig.hold(n_samples=200)
        assert rig.last_current2_v is None and rig.channel2_of(record) is None
        with pytest.raises(ValueError):
            rig.set_current_channels(3)
        cfg.channels.ai_current_2 = None
        with pytest.raises(ValueError, match="ai_current_2"):
            rig.set_current_channels(2)
    finally:
        rig.close()


def test_contact_is_judged_on_channel_1_alone():
    """Channel 2 at its rail is its normal state in contact and says
    nothing about contact: with it railed and channel 1 reading an open
    junction, the rig is not in contact."""
    cfg = _two()
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=1))
    rig.open()
    try:
        record = rig.hold(n_samples=400)             # parked: open
        railed = np.full(400, cfg.channels.ai_range_v)
        assert rig.channel2_of(record, railed)["railed"]
        assert not rig.is_saturated(record)
        assert rig.conductance_of(record) < cfg.ramp.engage_g0
        assert not rig.in_contact()
    finally:
        rig.close()


def test_measure_zeros_takes_both_from_the_zero_bias_hold():
    cfg = _two()
    cfg.cal.current_zero_v, cfg.cal.current_zero_2_v = 3e-4, -2e-2
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=4))
    rig.open()
    try:
        zero, zero2 = calibrate.measure_zeros(rig)
        assert zero == pytest.approx(3e-4, abs=1e-6)
        assert zero2 == pytest.approx(-2e-2, abs=2e-5)
        assert calibrate.measure_zero(rig) == pytest.approx(zero, abs=1e-6)   # as before
        cfg.cal.current_zero_2_v = 0.0
        results = calibrate.session_calibration(rig, do_group_delay=False)
        assert "current_zero_2_v" in results
        assert cfg.cal.current_zero_2_v == pytest.approx(0.0, abs=2e-5)
        rig.set_current_channels(1)
        assert calibrate.measure_zeros(rig)[1] is None
    finally:
        rig.close()


# --------------------------------------------------------------------------
# DaqSession against a fake nidaqmx
# --------------------------------------------------------------------------

@pytest.fixture
def fake_nidaqmx(monkeypatch):
    from test_daq_onecard import FakeTask
    FakeTask.made = []
    mod = types.ModuleType("nidaqmx")
    mod.Task = FakeTask
    consts = types.ModuleType("nidaqmx.constants")
    for name in ("AOIdleOutputBehavior", "AcquisitionType", "TaskMode"):
        setattr(consts, name, types.SimpleNamespace(
            MAINTAIN_EXISTING_VALUE=1, FINITE=1, TASK_COMMIT=1))
    consts.TerminalConfiguration = types.SimpleNamespace(
        DEFAULT=0, RSE=1, NRSE=2, DIFF=3)
    mod.constants = consts
    monkeypatch.setitem(sys.modules, "nidaqmx", mod)
    monkeypatch.setitem(sys.modules, "nidaqmx.constants", consts)
    return FakeTask


def _card_config() -> RigConfig:
    cfg = _two()
    cfg.simulate = False
    cfg.channels.ai_voltage, cfg.channels.ai_current = "ai1", "ai2"
    cfg.channels.sense_device, cfg.channels.ai_piezo_sense = "Dev1", "ai3"
    cfg.channels.ai_terminal = cfg.channels.sense_terminal = "rse"
    return cfg


def test_daq_session_reads_channel_2_in_the_record_task(fake_nidaqmx):
    from stmlab.daq import DaqSession
    cfg = _card_config()
    with DaqSession(cfg) as s:
        ai = next(t for t in fake_nidaqmx.made if t.name == "stmbj_ai")
        assert ai.ai_channels.names == ["Dev1/ai1", "Dev1/ai2", "Dev1/ai4", "Dev1/ai3"]
        tc = sys.modules["nidaqmx.constants"].TerminalConfiguration
        assert [c.kw["terminal_config"] for c in ai.ai_channels] == [tc.RSE] * 4
        n = 40
        record = s.play(np.zeros((2, n)))
        # the fake card reads channel c as c + i/n: the rows are telling
        assert record.shape == (2, n)
        assert record[0, 0] == 0.0 and record[1, 0] == 1.0
        assert s.last_current2_v.shape == (n,) and s.last_current2_v[0] == 2.0
        assert s.last_sense_v.shape == (n,) and s.last_sense_v[0] == 3.0


def test_daq_session_without_a_sense_line_and_switching_live(fake_nidaqmx):
    from stmlab.daq import DaqError, DaqSession
    cfg = _two()
    cfg.simulate = False
    with DaqSession(cfg) as s:
        first = [t for t in fake_nidaqmx.made if t.name == "stmbj_ai"][-1]
        assert first.ai_channels.names == ["Dev1/ai0", "Dev1/ai1", "Dev1/ai4"]
        s.play(np.zeros((2, 20)))
        assert s.last_current2_v[0] == 2.0 and s.last_sense_v is None
        ao = next(t for t in fake_nidaqmx.made if t.name == "stmbj_ao")
        s.set_current_channels(1)                       # the input task is rebuilt
        second = [t for t in fake_nidaqmx.made if t.name == "stmbj_ai"][-1]
        assert second is not first
        assert second.ai_channels.names == ["Dev1/ai0", "Dev1/ai1"]
        assert next(t for t in fake_nidaqmx.made if t.name == "stmbj_ao") is ao   # outputs untouched
        record = s.play(np.zeros((2, 20)))
        assert record.shape == (2, 20) and s.last_current2_v is None
        s.set_current_channels(2)
        assert [t for t in fake_nidaqmx.made
                if t.name == "stmbj_ai"][-1].ai_channels.names[-1] == "Dev1/ai4"
        assert s.play(np.zeros((2, 20))).shape == (2, 20)
        assert s.last_current2_v.shape == (20,)
        with pytest.raises(DaqError):
            s.set_current_channels(0)
        cfg.channels.ai_current_2 = ""
        with pytest.raises(DaqError, match="ai_current_2"):
            s.set_current_channels(2)


def test_a_refused_channel_2_puts_the_old_input_task_back(fake_nidaqmx, monkeypatch):
    from stmlab.daq import DaqSession
    from test_daq_onecard import _Chans
    cfg = _two()
    cfg.simulate = False
    cfg.channels.current_channels = 1
    real = _Chans.add_ai_voltage_chan

    def refuse_ai4(self, name, **kw):
        if name.endswith("ai4"):
            raise RuntimeError("Physical channel specified does not exist")
        real(self, name, **kw)
    monkeypatch.setattr(_Chans, "add_ai_voltage_chan", refuse_ai4)
    with DaqSession(cfg) as s:
        with pytest.raises(RuntimeError, match="does not exist"):
            s.set_current_channels(2)
        assert cfg.channels.current_channels == 1       # as it was
        record = s.play(np.zeros((2, 20)))              # and still reading
        assert record.shape == (2, 20) and s.last_current2_v is None


# --------------------------------------------------------------------------
# Files: the .h5 session and Igor's day folder
# --------------------------------------------------------------------------

def test_the_h5_session_keeps_channel_2_as_raw_volts(tmp_path):
    cfg = _two()
    got = _traces(cfg, 3)
    with storage.SessionWriter(tmp_path / "two.h5", cfg) as w:
        for i, (tr, sel) in enumerate(got):
            w.append(i, tr, sel)
    with storage.Session(tmp_path / "two.h5") as s:
        assert len(s) == 3 and s.has_current2
        assert np.array_equal(s.raw2(1), got[1][0].current2_v)
        assert np.allclose(s.conductance(2, channel=2),
                           got[2][0].conductance_g0(cfg, channel=2))
        assert np.allclose(s.conductance(2), got[2][0].conductance_g0(cfg))   # channel 1
        assert len(list(s.conductances(channel=2))) == 3
        assert s.cfg.channels.two_current_channels
        # a gain re-measured later reprocesses channel 2 from the raw volts
        cal = s.cfg.cal
        cal.preamp_gain_2_v_per_a *= 10.0
        assert np.allclose(s.conductance(0, cal=cal, channel=2) * 10.0,
                           got[0][0].conductance_g0(cfg, channel=2))


def test_a_one_channel_session_has_no_second_dataset(tmp_path):
    cfg = RigConfig()
    cfg.simulate = True
    got = _traces(cfg, 1)
    with storage.SessionWriter(tmp_path / "one.h5", cfg) as w:
        w.append(0, *got[0])
    with storage.Session(tmp_path / "one.h5") as s:
        assert not s.has_current2 and s.raw2(0) is None
        with pytest.raises(ValueError, match="second current channel"):
            s.conductance(0, channel=2)
    with pytest.raises(ValueError, match="second current channel"):
        got[0][0].conductance_g0(cfg, channel=2)


def test_channel_2_goes_into_the_ch2_subfolder_under_igors_names(tmp_path):
    pytest.importorskip("igor2")
    cfg = _two()
    cfg.cal.preamp_gain_2_v_per_a = 1e8
    cfg.channels.low_res_device = "dev2"             # a sense line, for the Extension block
    got = _traces(cfg, 3)
    w = igor_scheme.IgorDayWriter(tmp_path, cfg)
    for tr, _ in got:
        w.append(igor_scheme.IgorTrace.from_record(tr, cfg, izero=0.25, izero2=0.5))
    files = w.flush()
    day, sub = w.folder, w.folder / igor_scheme.CH2_FOLDER
    assert sub == igor_scheme.channel2_folder(day)
    names = sorted(p.relative_to(day).as_posix() for p in files)
    assert names == sorted([
        "PullOutConductanceBlock_1.ibw", "PullOutVoltageBlock_1.ibw",
        "PullOutCurrentBlock_1.ibw", "PullOutExtensionBlock_1.ibw",
        "PullOutConductanceBlockHist_1.ibw",
        "ch2/PullOutConductanceBlock_1.ibw", "ch2/PullOutCurrentBlock_1.ibw",
        "ch2/PullOutConductanceBlockHist_1.ibw"])
    # channel 1's files are exactly a one-channel day's
    b1 = igor_scheme.read_block(day, 1, companions=True)
    assert np.allclose(b1.g0[:, 1], got[1][0].conductance_g0(cfg), rtol=1e-5, atol=1e-12)
    assert b1.params[0, 9] == pytest.approx(1.0) and b1.params[0, 4] == 1.0
    assert b1.params[0, 16] == pytest.approx(0.25)
    assert igor_scheme.IgorDayWriter.scan(day) == (1, 3)      # the subfolder is not a block
    assert igor_scheme.list_blocks(day) == [1]
    # channel 2: same block, same columns, its own conductance, gain and zero
    b2 = igor_scheme.read_block_channel2(day, 1, companions=True)
    assert list(b2.numbers) == [1, 2, 3] and b2.g0.shape == b1.g0.shape
    assert np.allclose(b2.g0[:, 1], got[1][0].conductance_g0(cfg, channel=2),
                       rtol=1e-5, atol=1e-12)
    assert np.allclose(b2.current_a[:, 2],
                       cfg.cal.volts_to_amps(got[2][0].current2_v, channel=2),
                       rtol=1e-5, atol=1e-15)
    assert b2.params[0, 9] == pytest.approx(1e-2)             # uA per V at 1e8 V/A
    assert b2.params[0, 4] == 0.0                              # no Voltage block in there
    assert b2.params[0, 16] == pytest.approx(0.5)
    assert b2.params[0, 0] == b1.params[0, 0] and b2.params[0, 17] == b1.params[0, 17]
    assert b2.voltage_v is None and b2.extension_nm is None and b2.hist is not None
    # and the subfolder is a day folder of channel 2 for anything that reads one
    assert igor_scheme.list_blocks(sub) == [1]
    assert igor_scheme.read_day_folder(sub)[0].n_traces == 3
    assert igor_scheme.read_block_channel2(sub, 1) is None      # it has no ch2 of its own
    assert igor_scheme.read_block_channel2(day, 2) is None      # nor has block 2


def test_a_resumed_block_keeps_the_channel_2_it_already_had(tmp_path):
    pytest.importorskip("igor2")
    cfg = _two()
    got = _traces(cfg, 4)
    first = igor_scheme.IgorDayWriter(tmp_path, cfg)
    for tr, _ in got[:2]:
        first.append(igor_scheme.IgorTrace.from_record(tr, cfg))
    first.flush()
    again = igor_scheme.IgorDayWriter(tmp_path, cfg)          # the next launch
    assert again.saved == 3
    assert [t.g0_2 is not None for t in again._pending] == [True, True]
    for tr, _ in got[2:]:
        again.append(igor_scheme.IgorTrace.from_record(tr, cfg))
    again.flush()
    b2 = igor_scheme.read_block_channel2(again.folder, 1)
    assert list(b2.numbers) == [1, 2, 3, 4]
    for j in range(4):
        assert np.allclose(b2.g0[:, j], got[j][0].conductance_g0(cfg, channel=2),
                           rtol=1e-5, atol=1e-12)


def test_a_block_taken_partly_with_one_channel_keeps_the_columns_in_step(tmp_path):
    pytest.importorskip("igor2")
    cfg = _two()
    two = _traces(cfg, 2)
    one_cfg = RigConfig()
    one_cfg.simulate = True
    one = _traces(one_cfg, 2)
    w = igor_scheme.IgorDayWriter(tmp_path, cfg)
    for tr, _ in one + two:                                    # traces 1-2 one channel, 3-4 two
        w.append(igor_scheme.IgorTrace.from_record(tr, cfg))
    w.flush()
    assert list(igor_scheme.read_block(w.folder, 1).numbers) == [1, 2, 3, 4]
    b2 = igor_scheme.read_block_channel2(w.folder, 1)
    assert list(b2.numbers) == [3, 4] and list(b2.columns) == [2, 3]
    wave = igor_scheme.read_wave(w.folder / "ch2" / "PullOutConductanceBlock_1.ibw")
    assert np.isnan(wave.data[:, :2]).all()                    # no channel 2 for traces 1-2
    # one-channel traces alone make no subfolder at all
    lone = igor_scheme.IgorDayWriter(tmp_path / "lone", one_cfg)
    lone.append(igor_scheme.IgorTrace.from_record(one[0][0], one_cfg))
    lone.flush()
    assert not (lone.folder / "ch2").exists()


def test_a_complete_block_of_channel_2_gets_no_stray_single_trace_files(tmp_path):
    pytest.importorskip("igor2")
    cfg = _two()
    cfg.ramp.sample_rate_hz = 1600.0                 # 400-point traces: small blocks
    tr = trace.TraceRecord(
        index=0, voltage_v=np.full(400, -0.09), current_v=np.linspace(1.0, 0.0, 400),
        delay_samples=0, start_piezo_v=4.0, bias_v=0.1, sample_rate_hz=1600.0,
        timestamp=1.7e9, current2_v=np.linspace(10.0, 0.0, 400))
    flags = igor_scheme.SaveFlags(bias=False, current=True, sense=False, hist=False)
    w = igor_scheme.IgorDayWriter(tmp_path, cfg, flags=flags)
    for _ in range(igor_scheme.BLOCK):
        w.append(igor_scheme.IgorTrace.from_record(tr, cfg, bias_save=False))
    day = w.folder
    # Igor's own single-trace files of the block's last trace, Bias being off
    assert (day / "PullOutVoltage_100.ibw").exists()
    assert sorted(p.name for p in (day / "ch2").iterdir()) == [
        "PullOutConductanceBlock_1.ibw", "PullOutCurrentBlock_1.ibw"]
    assert igor_scheme.read_block_channel2(day, 1).n_traces == igor_scheme.BLOCK


# --------------------------------------------------------------------------
# The pictures
# --------------------------------------------------------------------------

def _axes():
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    return Figure(figsize=(6, 4)).add_subplot(111)


def test_the_trace_plot_draws_channel_1_blue_and_channel_2_red():
    from stmlab import plots
    cfg = _two()
    (tr, sel), = _traces(cfg, 1)
    disp = tr.displacement_nm(cfg)
    ax = _axes()
    plots.plot_trace(ax, cfg, tr.conductance_g0(cfg), disp, sel,
                     g0_2=tr.conductance_g0(cfg, channel=2))
    data = [ln for ln in ax.lines if len(ln.get_xdata()) == disp.size]
    assert [ln.get_color() for ln in data] == [plots.C_CH1, plots.C_CH2]
    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    assert labels == ["ch 1 (1e+06 V/A)", "ch 2 (1e+09 V/A)"]
    # each channel as measured: channel 2's line is its own log10 G, railed part included
    with np.errstate(divide="ignore", invalid="ignore"):
        want = np.log10(np.clip(tr.conductance_g0(cfg, channel=2), 1e-12, None))
    assert np.array_equal(data[1].get_ydata(), want)
    assert ax.get_ylim()[0] == -8.5                  # a decade more than one channel's -7.5
    # one channel: one black line, as before
    ax = _axes()
    plots.plot_trace(ax, cfg, tr.conductance_g0(cfg), disp, sel)
    data = [ln for ln in ax.lines if len(ln.get_xdata()) == disp.size]
    assert [ln.get_color() for ln in data] == [plots.C_G]
    assert ax.get_legend() is None and ax.get_ylim()[0] == -7.5


def test_the_histogram_plot_has_two_curves_and_two_noise_floors():
    from stmlab import plots
    cfg = _two()
    got = [tr for tr, _ in _traces(cfg, 6)]
    centres, c1 = analysis.log_histogram([t.conductance_g0(cfg) for t in got])
    _, c2 = analysis.log_histogram([t.conductance_g0(cfg, channel=2) for t in got])
    ax = _axes()
    plots.plot_histogram(ax, cfg, centres, c1, 6, counts2=c2)
    curves = [ln for ln in ax.lines if len(ln.get_xdata()) == centres.size]
    assert [ln.get_color() for ln in curves] == [plots.C_CH1, plots.C_CH2]
    assert np.array_equal(curves[1].get_ydata(), c2)           # channel 2's own histogram
    assert ax.get_xlim() == (-8.0, 1.0) and "two channels" in ax.get_title()
    # the floors: each channel's highest bin below 1e-4 G0, channel 2's further down
    low = centres < -4.0
    floor1 = centres[low][np.argmax(c1[low])]
    floor2 = centres[low][np.argmax(c2[low])]
    assert floor2 < floor1 - 0.3
    # and only channel 1 has the 1 G0 peak: channel 2 is railed there
    gold = np.abs(centres) < 0.1
    assert c1[gold].sum() > 10 * max(c2[gold].sum(), 1e-9)


# --------------------------------------------------------------------------
# plot.py
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def plot_py():
    import matplotlib
    matplotlib.use("Agg")
    import plot
    return plot


@pytest.fixture(scope="module")
def two_channel_run(tmp_path_factory):
    """A headless run of 6 traces on the new rig's two-channel config: the
    day folder (with its ch2 subfolder) and the .h5 session."""
    pytest.importorskip("igor2")
    import pullout
    out = tmp_path_factory.mktemp("twoch")
    cfg = _rig_config()
    saving = {"name": "test", "experiment": "two", "txt": True}
    assert pullout.run_headless(cfg, 6, out, True, False, saving=saving) == 0
    day = out / igor_scheme.day_folder_name(None, "_")
    h5 = next(day.glob("*traces.h5"))
    return {"day": day, "h5": h5, "cfg": cfg}


def test_a_headless_run_saves_both_channels_everywhere(two_channel_run):
    day, h5 = two_channel_run["day"], two_channel_run["h5"]
    names = sorted(p.relative_to(day).as_posix() for p in day.rglob("*") if p.is_file())
    for want in ("PullOutConductanceBlock_1.ibw", "ch2/PullOutConductanceBlock_1.ibw",
                 "ch2/PullOutCurrentBlock_1.ibw", "ch2/PullOutConductanceBlockHist_1.ibw",
                 "experiment_log.csv"):
        assert want in names, names
    assert not any(n.startswith("ch2/PullOutVoltage") or n.startswith("ch2/PullOutExtension")
                   for n in names)
    stem = h5.stem
    assert f"{stem}.txt" in names and f"{stem}_ch2.txt" in names
    assert f"{stem}_ch2_info.txt" in names
    with storage.Session(h5) as s:
        assert len(s) == 6 and s.has_current2
        cfg = s.cfg
        assert cfg.channels.two_current_channels and cfg.channels.ai_current_2 == "ai4"
        g2 = s.conductance(3, channel=2)
    # the three places channel 2 lives in agree with each other
    b2 = igor_scheme.read_block_channel2(day, 1)
    assert np.allclose(b2.g0[:, 3], g2, rtol=1e-5, atol=1e-12)
    table = np.loadtxt(day / f"{stem}_ch2.txt")
    assert table.shape == (g2.size, 7)
    assert np.allclose(table[:, 4], g2, rtol=1e-4, atol=1e-12)
    header = (day / f"{stem}_ch2.txt").read_text().splitlines()[:8]
    assert any("preamp_gain_v_per_a=1e+07" in line and "current_channel=2" in line
               for line in header)
    log_text = (day / "experiment_log.csv").read_text()
    assert "two current channels: ch 1 gain 10000 V/A, ch 2 gain 1e+07 V/A" in log_text


def test_plot_py_loads_both_channels_from_the_session_and_the_day_folder(
        plot_py, two_channel_run):
    for source in (two_channel_run["h5"], two_channel_run["day"],
                   two_channel_run["day"] / "PullOutConductanceBlock_1.ibw"):
        data = plot_py.load([source])
        assert data.n == 6 and data.two_channels and data.n2 == 6, source
        assert len(data.traces2) == 6
        assert data.cfg.cal.preamp_gain_2_v_per_a == pytest.approx(1e7)
    # the same numbers either way (the blocks are single precision)
    a = plot_py.load([two_channel_run["h5"]])
    b = plot_py.load([two_channel_run["day"]])
    assert np.allclose(a.traces2[2], b.traces2[2], rtol=1e-5, atol=1e-12)
    # the ch2 subfolder by itself is a one-channel day of channel 2
    alone = plot_py.load([two_channel_run["day"] / "ch2"])
    assert alone.n == 6 and not alone.two_channels
    assert np.allclose(alone.traces[2], b.traces2[2])


def test_plot_py_1d_draws_both_channels_and_one_on_request(plot_py, two_channel_run):
    from stmlab import plots
    data = plot_py.load([two_channel_run["h5"]])
    ax = _axes()
    info = plot_py.hist_1d(ax, data)
    lines = [ln for ln in ax.lines if len(ln.get_xdata()) == 1000]
    assert [ln.get_color() for ln in lines] == [plots.C_CH1, plots.C_CH2]
    assert info["counts2"] is not None and "nothing stitched" in info["note"]
    assert ax.get_xlim() == (-8.0, 1.0)
    assert [t.get_text() for t in ax.get_legend().get_texts()] == [
        "ch 1 (1e+04 V/A)", "ch 2 (1e+07 V/A)"]
    # each is its own channel's histogram, by the one recipe; the floor
    # gate is read on channel 2 for both
    cutoff = data.cfg.ramp.break_g0
    _, want2 = analysis.log_histogram(data.traces2, zero_cutoff=cutoff, igor_bins=True)
    assert np.array_equal(info["counts2"], want2)
    _, want1 = analysis.log_histogram(data.traces, zero_cutoff=cutoff, igor_bins=True,
                                      gate_by=data.traces2)
    assert np.array_equal(info["counts"], want1)
    for channel, colour in ((1, "k"), ("2", plots.C_CH2)):
        ax = _axes()
        info = plot_py.hist_1d(ax, data, channel=channel)
        lines = [ln for ln in ax.lines if len(ln.get_xdata()) == 1000]
        assert [ln.get_color() for ln in lines] == [colour]
        assert info["counts2"] is None
        assert np.array_equal(info["counts"], want1 if str(channel) == "1" else want2)


def test_plot_py_2d_is_one_channel_and_channel_2_is_aligned_by_channel_1(
        plot_py, two_channel_run):
    data = plot_py.load([two_channel_run["h5"]])
    first = plot_py.hist_2d(_axes(), data, colorbar=False)
    second = plot_py.hist_2d(_axes(), data, colorbar=False, channel=2)
    assert "ch 1" in first["note"] and "0 nm from channel 1" in second["note"]
    assert not np.array_equal(first["counts"], second["counts"])
    # aligned by channel 1, channel 2's tunnelling decay falls where channel
    # 1's does: the bins between 1e-1 and 1e-2 G0, where both outputs are
    # clear of their noise, hold the same counts
    ye = first["y_edges"]
    rows = (ye[:-1] >= -2.0) & (ye[1:] <= -1.0)
    a, b = first["counts"][:, rows], second["counts"][:, rows]
    assert a.sum() > 0 and abs(a.sum() - b.sum()) < 0.15 * a.sum()
    profile_a, profile_b = a.sum(axis=1), b.sum(axis=1)
    assert abs(int(np.argmax(profile_a)) - int(np.argmax(profile_b))) <= 3
    # a channel 2 that is railed while the gold breaks could not say by
    # itself where that was: it is below 0.5 G0 from the first sample on,
    # and its own alignment is not channel 1's
    disp = np.linspace(0.0, 5.0, 2000)
    g1 = np.where(disp < 1.0, 8.0,
                  np.where(disp < 1.2, 1.0, 1e-4 * np.exp(-4.0 * (disp - 1.2))))
    g2 = np.minimum(g1, 1.4e-3)
    made = plot_py.Data([g1, g1], disp, data.cfg, "made", traces2=[g2, g2])
    by_ch1 = plot_py.hist_2d(_axes(), made, colorbar=False, channel=2)
    alone = analysis.histogram_2d(made.traces2, made.disps)
    assert not np.array_equal(alone[0], by_ch1["counts"])


def test_plot_py_draws_a_single_trace_of_either_kind(plot_py, two_channel_run):
    from stmlab import plots
    for source, number in ((two_channel_run["h5"], 2), (two_channel_run["day"], 5)):
        fig, info = plot_py.trace_figure(source, number)
        assert info["number"] == number
        colours = [ln.get_color() for a in fig.axes for ln in a.lines]
        assert plots.C_CH1 in colours and plots.C_CH2 in colours, source


def test_plot_py_command_line_on_two_channel_data(plot_py, two_channel_run, tmp_path, capsys):
    h5, day = two_channel_run["h5"], two_channel_run["day"]
    assert plot_py.main([str(h5), "1D", "--save", "--out", str(tmp_path)]) == 0
    assert plot_py.main([str(day), "2D", "--channel", "2", "--save", "--out", str(tmp_path)]) == 0
    assert plot_py.main([str(day), "-3", "--save", "--out", str(tmp_path)]) == 0
    text = capsys.readouterr().out
    assert "two current channels (6 traces have channel 2)" in text
    assert "0 nm from channel 1" in text
    assert len(list(tmp_path.glob("*.png"))) == 3


def test_plot_py_mixes_one_and_two_channel_inputs(plot_py, two_channel_run, tmp_path):
    cfg = RigConfig()
    cfg.simulate = True
    with storage.SessionWriter(tmp_path / "one.h5", cfg) as w:
        for i, (tr, sel) in enumerate(_traces(cfg, 2)):
            w.append(i, tr, sel)
    data = plot_py.load([tmp_path / "one.h5", two_channel_run["h5"]])
    assert data.n == 8 and data.two_channels and data.n2 == 6
    assert data.traces2[0] is None and data.traces2[1] is None and data.traces2[2] is not None
    info = plot_py.hist_1d(_axes(), data)
    assert "6 of 8 traces have channel 2" in info["note"]
    plot_py.hist_2d(_axes(), data, colorbar=False, channel=2)     # the Nones are skipped


# --------------------------------------------------------------------------
# pullout.py: the worker, as the window drives it
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ap():
    import pullout
    return pullout


def _worker(ap, cfg, tmp_path):
    guard, rig = ap.open_rig(cfg)
    mon = ap.Monitor(rig)
    worker = ap.Worker(cfg, rig, mon, save=True, out_dir=tmp_path, igor_export=False)
    return guard, rig, worker


def _events(worker, kind):
    return [p for k, p in list(worker.events.queue) if k == kind]


def _status(worker) -> str:
    return _events(worker, "status")[-1]["text"]


def test_the_worker_switches_between_one_channel_and_two(ap, tmp_path):
    cfg = _two()
    cfg.channels.current_channels = 1
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_amplifier()
        state = _events(worker, "amplifier")[-1]
        assert state["channels"] == 1 and state["available"]
        assert state["ch1"] == "Dev1/ai1" and state["ch2"] == "Dev1/ai4"
        worker.cmd_current_channels(2)
        assert cfg.channels.two_current_channels
        assert _events(worker, "amplifier")[-1]["channels"] == 2
        assert "two current channels" in _status(worker) and '"current_channels": 2' in _status(worker)
        worker.readout()
        assert _events(worker, "readout")[-1]["two_channels"] is True
        worker.cmd_monitor()
        assert _events(worker, "monitor")[-1]["ch2"] is not None
        worker.readout()
        assert _events(worker, "readout")[-1]["ch2"] is not None
        worker.cmd_current_channels(1)
        assert not cfg.channels.two_current_channels
        assert "one current channel" in _status(worker)
        worker.cmd_monitor()
        assert _events(worker, "monitor")[-1]["ch2"] is None
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_two_channels_are_refused_without_an_input_or_in_contact(ap, tmp_path):
    from stmlab.safety import RigState
    cfg = RigConfig()
    cfg.simulate = True
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_current_channels(2)
        assert not cfg.channels.two_current_channels
        assert "ai_current_2" in _status(worker)
        assert _events(worker, "amplifier")[-1] == worker.amplifier_state()
        assert not worker.amplifier_state()["available"]
        cfg.channels.ai_current_2 = "ai4"
        rig.state = RigState.ENGAGED
        worker.cmd_current_channels(2)
        assert not cfg.channels.two_current_channels and "in contact" in _status(worker)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_calibrate_zero_takes_both_and_refuses_a_railed_channel_2(ap, tmp_path):
    cfg = _two()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        cfg.cal.current_zero_2_v = 0.123             # the simulated amplifier's offset
        worker.cmd_zero()
        assert cfg.cal.current_zero_2_v == pytest.approx(0.123, abs=1e-4)
        assert "channel 2 zero" in _status(worker)
        assert _events(worker, "zero")[-1]["zero2_v"] == pytest.approx(0.123, abs=1e-4)
        # a reading at the rail (the junction closed) is not an offset
        cfg.cal.current_zero_2_v = 50.0              # clips at the card's 10 V
        worker.cmd_zero()
        assert cfg.cal.current_zero_2_v == 50.0      # kept as it was
        assert "NOT taken" in _status(worker)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_run_shows_and_counts_both_channels_and_the_open_side_decides(ap, tmp_path):
    cfg = _two()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_zero()
        worker.cmd_run(4, {"name": "t", "experiment": "two"})
        cycles = [p for p in _events(worker, "cycle") if p.get("record") is not None]
        assert len(cycles) >= 4
        for p in cycles:
            assert p["g0_2"] is not None and p["g0_2"].size == p["g0"].size
            # the verdict reads the end of the trace on the open side
            want = analysis.select_trace(
                p["g0"], cfg.ramp, g0_open=p["record"].open_side_g0(cfg))
            assert p["verdict"].reason == want.reason
            assert p["verdict"].end_conductance == want.end_conductance
        hist = _events(worker, "hist")[-1]
        assert hist["counts"] is not None and hist["counts2"] is not None
        assert hist["counts2"].shape == hist["counts"].shape
        assert worker.hist_n == 4 and worker.hist2_n == 4
        # its own histogram, by the same recipe
        want = sum(analysis.log_histogram([p["g0_2"]])[1] for p in cycles
                   if p["verdict"].accepted) / 4
        assert np.allclose(hist["counts2"], want)
        # the run's list for the .txt tables carries channel 2 of every trace
        assert len(worker.file_traces) == 4
        assert all(entry[3] is not None for entry in worker.file_traces)
        # a new experiment starts both histograms again
        worker.begin_experiment()
        assert worker.hist2_sum is None and worker.hist2_n == 0
        worker.end_experiment()
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_one_channel_runs_exactly_as_before(ap, tmp_path):
    cfg = RigConfig()
    cfg.simulate = True
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_zero()
        assert "channel 2" not in _status(worker)
        worker.cmd_run(2, {"name": "t", "experiment": "one"})
        cycle = [p for p in _events(worker, "cycle") if p.get("record") is not None][-1]
        assert cycle["g0_2"] is None and cycle["record"].current2_v is None
        assert _events(worker, "hist")[-1]["counts2"] is None
        worker.readout()
        readout = _events(worker, "readout")[-1]
        assert readout["two_channels"] is False and readout["ch2"] is None
        day = tmp_path / igor_scheme.day_folder_name(None, "_")
        with storage.Session(next(day.glob("*traces.h5"))) as s:
            assert not s.has_current2
        assert "two current channels" not in (day / "experiment_log.csv").read_text()
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_the_gains_are_settings_checked_like_the_others(ap):
    cfg = _two()
    labels = {row[0]: row[1] for row in ap.SETTINGS}
    assert labels["cal.preamp_gain_v_per_a"] == "Gain ch 1"
    assert labels["cal.preamp_gain_2_v_per_a"] == "Gain ch 2"
    assert ap.AMPLIFIER_SETTINGS == ("cal.preamp_gain_v_per_a", "cal.preamp_gain_2_v_per_a")
    # plain changes are accepted, without a word about the Keithley
    assert ap.check_settings(cfg, {"cal.preamp_gain_v_per_a": 1e5}) == ([], [])
    assert ap.check_settings(cfg, {"cal.preamp_gain_2_v_per_a": 1e8}) == ([], [])
    assert ap.check_settings(cfg, {"cal.preamp_gain_v_per_a": 4.7e5}) == ([], [])
    # zero and negative are refused, for either channel
    for path in ap.AMPLIFIER_SETTINGS:
        for bad in (0.0, -1e6):
            problems, _ = ap.check_settings(cfg, {path: bad})
            assert problems and "positive" in problems[0]
    # channel 1 must be able to see 1 G0: the high gain is refused for it
    problems, _ = ap.check_settings(cfg, {"cal.preamp_gain_v_per_a": 1e9})
    assert problems and "CLIP" in problems[0]
    # and a channel 2 below channel 1 is allowed, with the warning
    problems, warnings = ap.check_settings(cfg, {"cal.preamp_gain_2_v_per_a": 1e4})
    assert not problems and any("swap" in w for w in warnings)
    assert cfg.cal.preamp_gain_v_per_a == 1e6        # the live config was not touched


def test_the_keithley_exponent_follows_a_decade_gain(ap):
    cfg = RigConfig()
    cfg.cal.preamp_gain_v_per_a = 1e5
    ap.follow_gain(cfg)
    assert cfg.keithley.gain_exponent == 5
    assert not any("keithley" in w for w in validate(cfg))
    cfg.cal.preamp_gain_v_per_a = 3.3e7              # no decade to follow
    ap.follow_gain(cfg)
    assert cfg.keithley.gain_exponent == 5


def test_the_browser_reads_channel_2_of_a_day_folder(ap, two_channel_run):
    day = ap.IgorDay(two_channel_run["day"])
    assert len(day) == 6 and day.hist2 is not None and day.n2 == 6
    assert "two current channels" in day.describe()
    assert day.cfg.cal.preamp_gain_2_v_per_a == pytest.approx(1e7)
    t = day.trace(2)
    assert t["g0_2"] is not None and t["g0_2"].size == t["g0"].size
    with storage.Session(two_channel_run["h5"]) as s:
        assert np.allclose(t["g0_2"], s.conductance(2, channel=2), rtol=1e-5, atol=1e-12)
    data = day.data()
    assert data.two_channels and data.n2 == 6
    # the ch2 subfolder opens as a day of its own, and a one-channel day has none
    sub = ap.IgorDay(two_channel_run["day"] / "ch2")
    assert len(sub) == 6 and sub.hist2 is None and sub.trace(0)["g0_2"] is None
    assert np.allclose(sub.trace(2)["g0"], t["g0_2"])
    day.close()
    sub.close()


def test_the_histogram_windows_offer_the_channel_for_two_channel_data(
        ap, two_channel_run, tmp_path):
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
    status = ttk.Label(root)

    def window(source, stem, kind):
        win = tk.Toplevel(root)
        ctl = ap.hist_window(win, source, stem, kind, tk, ttk, FigureCanvasTkAgg,
                             Figure, status)
        return win, ctl

    try:
        h5 = two_channel_run["h5"]
        with storage.Session(h5) as sess:
            # 1D: both channels unless the box says one; a decade further down
            win, ctl = window(sess, h5.stem, "1d")
            assert ctl["channel"].get() == "both" and ctl["x0"].get() == "-8"
            for word in ("1", "2", "nonsense", "both"):
                ctl["channel"].set(word)
                ctl["redraw"]()
                root.update()
            win.destroy()
            # 2D: one channel, 1 unless the box says 2
            win, ctl = window(sess, h5.stem, "2d")
            assert ctl["channel"].get() == "1"
            ctl["channel"].set("2")
            ctl["redraw"]()
            root.update()
            win.destroy()
        # the day folder's data, as the browser hands it over
        day = ap.IgorDay(two_channel_run["day"])
        win, ctl = window(day.data(), day.name, "1d")
        assert "channel" in ctl
        win.destroy()
        day.close()
        # one-channel data: no channel box, the old range
        cfg = RigConfig()
        cfg.simulate = True
        with storage.SessionWriter(tmp_path / "one.h5", cfg) as w:
            w.append(0, *_traces(cfg, 1)[0])
        with storage.Session(tmp_path / "one.h5") as sess:
            win, ctl = window(sess, "one", "1d")
            assert "channel" not in ctl and ctl["x0"].get() == "-7"
            win.destroy()
    finally:
        root.destroy()


def test_the_whole_window_runs_on_a_two_channel_rig(tmp_path):
    """pullout.py on the new rig's two-channel config, simulated, closing
    itself: it must lay out the Current amplifier box and the channel-2
    readouts, take the smoke run with both channels, switch the count and
    a gain, browse the day folder, and shut down without a traceback."""
    import subprocess
    tk = pytest.importorskip("tkinter")
    pytest.importorskip("igor2")
    try:
        tk.Tk().destroy()
    except tk.TclError as exc:
        pytest.skip(f"no Tk display: {exc}")
    config = tmp_path / "rig.json"
    _rig_config().to_json(config)
    cmd = [sys.executable, str(ROOT / "pullout.py"), "--simulate",
           "--config", str(config),
           "--out", str(tmp_path), "--autoclose", "9"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=ROOT)
    assert res.returncode == 0, res.stderr[-3000:]
    assert "Traceback" not in res.stderr, res.stderr[-3000:]
    day = tmp_path / igor_scheme.day_folder_name(None, "_")
    assert (day / "ch2" / "PullOutConductanceBlock_1.ibw").exists()
    with storage.Session(next(day.glob("*traces.h5"))) as s:
        assert s.has_current2 and len(s) == 3


# --------------------------------------------------------------------------
# The open side (v67): the break threshold is read from channel 2
# --------------------------------------------------------------------------

class _Drifting(SimulatedDaqSession):
    """The simulated card with an offset that turns up on channel 1 after
    the zero was taken: what a low-gain output does on a bench, where a
    few tens of microvolts are already more than the break threshold."""
    drift_v = 0.0

    def play(self, waveform, timeout_s: float = 10.0):
        record = super().play(waveform, timeout_s).copy()
        record[1] += self.drift_v                    # channel 1 only
        return record


def _drifted_rig(cfg: RigConfig, drift_v: float, seed: int = 11) -> Rig:
    session = _Drifting(cfg, seed=seed)
    rig = Rig(cfg, session=session)
    rig.open()
    zero, zero2 = calibrate.measure_zeros(rig)
    cfg.cal.current_zero_v = zero
    if zero2 is not None:
        cfg.cal.current_zero_2_v = zero2
    rig.set_bias(cfg.ramp.bias_v)
    session.drift_v = drift_v                        # after the zero
    return rig


def _made_pull(n: int = 2000, floor: float = 0.0) -> np.ndarray:
    """Contact, a gold plateau, then an open junction at ``floor``."""
    g = np.full(n, floor, dtype=float)
    g[:200] = 8.0
    g[200:400] = 1.0
    return g


def test_the_open_side_is_channel_2_in_range_and_channel_1_at_its_rail():
    g1 = np.array([5.0, 1.0, 2e-3, 1e-3, -4e-4])
    g2 = np.array([1.4e-3, 1.4e-3, 1.9e-3, 3e-6, 1e-6])
    railed = np.array([True, True, False, False, False])
    assert np.array_equal(analysis.open_side(g1, g2, railed),
                          [5.0, 1.0, 1.9e-3, 3e-6, 1e-6])
    assert np.array_equal(analysis.open_side(g1, g2), g2)      # no volts to tell by
    assert np.array_equal(analysis.open_side(g1), g1)          # one channel
    assert np.array_equal(analysis.open_side(g1, g2[:3]), g1)  # not the same pull


def test_select_trace_reads_the_end_of_the_trace_from_the_open_side():
    ramp = RigConfig().ramp
    g1 = _made_pull()
    assert analysis.select_trace(g1, ramp).accepted
    # channel 1 with 1e-3 G0 of offset at its open end is above the break
    # threshold, so judged by itself the trace is refused ...
    drifted = _made_pull(floor=1e-3)
    refused = analysis.select_trace(drifted, ramp)
    assert not refused.accepted and "break threshold" in refused.reason
    # ... but the end is read from the open side, where channel 2 says open
    low = _made_pull(floor=2e-6)
    verdict = analysis.select_trace(drifted, ramp, g0_open=low)
    assert verdict.accepted and verdict.end_conductance == pytest.approx(2e-6)
    # the other way round: channel 1 reads nothing, channel 2 a junction
    stuck = analysis.select_trace(g1, ramp, g0_open=_made_pull(floor=3e-3))
    assert not stuck.accepted and "break threshold" in stuck.reason
    # the start of the trace and the gold plateau stay channel 1's
    no_gold = drifted.copy()
    no_gold[200:400] = 1e-3
    assert not analysis.select_trace(no_gold, ramp, g0_open=low).accepted
    no_contact = drifted.copy()
    no_contact[:200] = 1.0
    assert not analysis.select_trace(no_contact, ramp, require_engaged=True,
                                     g0_open=low).accepted
    with pytest.raises(ValueError):
        analysis.select_trace(g1, ramp, g0_open=g1[:100])


def test_the_rig_reads_the_open_side_on_channel_2_below_its_rail():
    cfg = _two()
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=1))
    rig.open()
    try:
        record = rig.hold()                                  # parked: open
        first = (rig.conductance_of(record), rig.is_saturated(record), 1)
        n = record.shape[1]
        keep = n - min(cfg.ramp.settle_discard, n - 1)
        vj = abs(float(np.mean(record[cfg.channels.ROW_VOLTAGE, -keep:])))
        # in range: the reading is channel 2's, with its own gain
        in_range = np.full(n, 0.02)
        g, railed, channel = rig.open_side_of(record, in_range)
        assert (railed, channel) == (False, 2)
        assert g == pytest.approx(0.02 / cfg.cal.preamp_gain_2_v_per_a / vj / G0_SIEMENS)
        # one settled sample at the rail: the current is beyond channel 2,
        # and the reading is channel 1's
        at_rail = in_range.copy()
        at_rail[-1] = -cfg.limits.preamp_saturation_v
        assert rig.open_side_of(record, at_rail) == first
        # a rail before the settled tail does not count
        early = in_range.copy()
        early[:n - keep] = 10.0
        assert rig.open_side_of(record, early)[2] == 2
        # samples of some other play, or none at all: channel 1
        assert rig.open_side_of(record, in_range[:50]) == first
        rig.last_current2_v = None
        assert rig.open_side_of(record) == first
        # with one channel read it is probe's own pair
        rig.set_current_channels(1)
        g1, railed1 = rig.probe()
        assert rig.open_side() == (g1, railed1, 1)
    finally:
        rig.close()


def test_is_open_is_one_probe_against_the_break_threshold():
    cfg = RigConfig()
    cfg.simulate = True                                      # one channel
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=1))
    rig.open()
    try:
        assert rig.open_side() == (float("inf"), True, 1)    # no probe yet
        assert rig.is_open()                                 # parked
        g, railed, channel = rig.open_side()
        assert channel == 1 and not railed and g < cfg.ramp.break_g0
        # whatever stands in for probe, is_open is its pair against the threshold
        for g, railed, want in ((1e-5, False, True), (1e-3, False, False),
                                (1e-5, True, False), (8.0, False, False)):
            rig.probe = lambda n_samples=None, g=g, railed=railed: (g, railed)
            assert rig.is_open() is want
    finally:
        rig.__dict__.pop("probe", None)
        rig.close()


def test_a_drifted_channel_1_zero_no_longer_stops_the_cycle():
    """60 uV of offset on a 1e4 V/A output reads as 8e-4 G0, above the
    break threshold: judged on channel 1 the junction never counts as
    open, the separate step runs the piezo to its floor and every trace is
    refused for its end. On channel 2 the same offset is nowhere."""
    cfg = _rig_config()
    rig = _drifted_rig(cfg, drift_v=60e-6)
    try:
        approach.engage(rig)
        approach.separate(rig)                               # channel 2 says when
        g1, _ = rig.probe()
        g_open, railed, channel = rig.open_side()
        assert channel == 2 and not railed and g_open < cfg.ramp.break_g0
        assert g1 > cfg.ramp.break_g0                        # channel 1 reads its offset
        assert rig.piezo_v > cfg.limits.piezo_ao_min_v + 0.1   # nowhere near the floor
        got = []
        trace.trace_loop(rig, n=5, on_trace=lambda i, tr, sel: got.append((tr, sel)))
        assert len(got) == 5
        for tr, sel in got:
            g0 = tr.conductance_g0(cfg)
            assert sel.accepted and sel.end_conductance < cfg.ramp.break_g0
            alone = analysis.select_trace(g0, cfg.ramp)      # channel 1 by itself
            assert not alone.accepted and "break threshold" in alone.reason
    finally:
        rig.close()


def test_the_open_side_of_a_trace_is_channel_1_where_channel_2_is_railed():
    cfg = _two()                                  # 1e6 and 1e9: channel 2 rails in contact
    (tr, _), = _traces(cfg, 1)
    g1, g2 = tr.conductance_g0(cfg), tr.conductance_g0(cfg, channel=2)
    low = tr.open_side_g0(cfg)
    railed = np.abs(tr.current2_v) >= cfg.limits.preamp_saturation_v
    n = g1.size
    assert railed[:50].all() and not railed[int(0.8 * n):int(0.9 * n)].any()
    assert np.array_equal(low[railed], g1[railed])
    assert np.array_equal(low[~railed], g2[~railed])
    # a one-channel trace is its own open side
    one = RigConfig()
    one.simulate = True
    (tr1, _), = _traces(one, 1)
    assert np.array_equal(tr1.open_side_g0(one), tr1.conductance_g0(one))


def test_a_saved_session_repeats_the_verdict_of_the_pull(two_channel_run):
    with storage.Session(two_channel_run["h5"]) as s:
        for i in range(len(s)):
            g0 = s.conductance(i)
            low = s.open_side(i)
            assert low.shape == g0.shape
            assert analysis.select_trace(g0, s.cfg.ramp, g0_open=low).accepted
            railed = np.abs(s.raw2(i)) >= s.cfg.limits.preamp_saturation_v
            assert np.array_equal(low[~railed], s.conductance(i, channel=2)[~railed])
            assert np.array_equal(low[railed], g0[railed])


def test_the_histogram_gate_is_read_on_channel_2_for_both_channels():
    rng = np.random.default_rng(5)

    def pull(floor, noise):
        g = _made_pull(floor=floor) + rng.normal(0.0, noise, 2000)
        g[:400] = _made_pull()[:400]
        return g
    ch1 = [pull(1e-3, 1e-3) for _ in range(3)]    # an offset above the cutoff
    ch2 = [pull(0.0, 1e-6) for _ in range(3)]
    cutoff = RigConfig().ramp.break_g0
    # by its own floor every channel-1 trace is dropped ...
    assert not analysis.log_histogram(ch1, zero_cutoff=cutoff)[1].any()
    # ... gated by channel 2 they all count, each with its own floor subtracted
    gated = analysis.log_histogram(ch1, zero_cutoff=cutoff, gate_by=ch2)[1]
    assert gated.any()
    assert np.array_equal(gated, analysis.log_histogram(ch1)[1])
    # a channel 2 that never opened takes its trace out
    ch2[1] = pull(2e-3, 1e-6)
    two_left = analysis.log_histogram([ch1[0], ch1[2]])[1]
    assert np.array_equal(
        analysis.log_histogram(ch1, zero_cutoff=cutoff, gate_by=ch2)[1], two_left)
    # and an entry of None leaves that trace gated by itself
    assert np.array_equal(
        analysis.log_histogram(ch1, zero_cutoff=cutoff,
                               gate_by=[ch2[0], None, ch2[2]])[1], two_left)
    # the block histogram Igor's files hold, the same way
    cfg = RigConfig()
    assert not igor_scheme.block_histogram(ch1, cfg, 3).any()
    assert igor_scheme.block_histogram(ch1, cfg, 3, gate_columns=[ch2[0], None, ch2[2]]).any()


def test_the_saved_histogram_of_channel_1_is_gated_by_channel_2(tmp_path, plot_py):
    """A day taken with a drifted channel-1 zero: the Hist file of channel
    1 and plot.py's curve still hold every trace."""
    pytest.importorskip("igor2")
    cfg = _rig_config()
    rig = _drifted_rig(cfg, drift_v=60e-6)
    got = []
    try:
        trace.trace_loop(rig, n=3, on_trace=lambda i, tr, sel: got.append(tr))
    finally:
        rig.close()
    w = igor_scheme.IgorDayWriter(tmp_path, cfg)
    for tr in got:
        w.append(igor_scheme.IgorTrace.from_record(tr, cfg))
    w.flush()
    b1 = igor_scheme.read_block(w.folder, 1, companions=True)
    b2 = igor_scheme.read_block_channel2(w.folder, 1, companions=True)
    assert b1.hist is not None and b1.hist.sum() > 0 and b2.hist.sum() > 0
    # by its own floor (the offset) channel 1 would have been left out whole
    assert not igor_scheme.block_histogram(list(b1.g0.T), cfg, 3).any()
    data = plot_py.load([w.folder])
    info = plot_py.hist_1d(_axes(), data)
    assert info["counts"].sum() > 0 and info["counts2"].sum() > 0
    alone = plot_py.hist_1d(_axes(), data, channel=1)
    assert np.array_equal(alone["counts"], info["counts"])


def test_the_break_threshold_is_checked_on_the_output_that_judges_it():
    cfg = RigConfig()
    cfg.cal.preamp_gain_v_per_a = 1e3            # the break threshold is 0.4 uV there
    cfg.keithley.gain_exponent = 3
    assert any("break threshold" in w for w in validate(cfg))
    two = _two(cfg)
    two.cal.preamp_gain_2_v_per_a = 1e7          # and 4 mV on channel 2
    assert not any("break threshold" in w for w in validate(two))


# --------------------------------------------------------------------------
# The simulated card's noise (v67)
# --------------------------------------------------------------------------

def _open_noise(cfg: RigConfig, **kwargs) -> tuple[float, float]:
    """rms of (the junction voltage input, the current input) with the
    simulated junction open."""
    session = SimulatedDaqSession(cfg, seed=2, **kwargs)
    record = session.play(np.zeros((2, 20_000)))
    return float(np.std(record[0])), float(np.std(record[1]))


def test_the_simulated_card_noise_comes_from_the_config():
    cfg = RigConfig()
    cfg.simulate = True
    assert cfg.sim.ai_noise_v_rms is None
    # nothing said: the built-in noise, as every simulated run had it
    v, i = _open_noise(cfg)
    assert i == pytest.approx(1.87e-6, rel=0.05) and v == pytest.approx(7.48e-6, rel=0.05)
    # the card's own number: on every input alike
    cfg.sim.ai_noise_v_rms = 8.8e-5
    v, i = _open_noise(cfg)
    assert i == pytest.approx(8.8e-5, rel=0.05) and v == pytest.approx(8.8e-5, rel=0.05)
    # an argument still decides, and keeps the old ratio between the inputs
    v, i = _open_noise(cfg, noise_v_rms=1e-5)
    assert i == pytest.approx(1e-5, rel=0.05) and v == pytest.approx(4e-5, rel=0.05)
    # it travels in the json, and a file written before v67 loads without it
    blob = cfg.to_dict()
    assert blob["sim"]["ai_noise_v_rms"] == 8.8e-5
    # (v69: the section also says which way round the simulated amplifier's
    # outputs are; None = the way round cal.current_sign says)
    assert blob["sim"] == {"ai_noise_v_rms": 8.8e-5, "amplifier_output_sign": None,
                           "amplifier_output_sign_2": None}
    assert RigConfig.from_dict(blob).sim.ai_noise_v_rms == 8.8e-5
    del blob["sim"]
    assert RigConfig.from_dict(blob).sim.ai_noise_v_rms is None


def test_the_noise_floors_of_the_new_rig_are_where_its_gains_put_them(ap, tmp_path):
    """88 uV on a 1e4 V/A output is about 1e-3 G0 at 100 mV, and on a
    1e7 V/A output about 1e-6: the two floors three decades apart, with the
    1 G0 peak of both channels in the same place."""
    cfg = _rig_config()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_zero()
        worker.cmd_run(6, {"name": "t", "experiment": "floors"})
        floor1, floor2 = worker.noise_floors()
        assert 5e-4 < floor1 < 3e-3
        assert 5e-7 < floor2 < 3e-6
        centres = worker.hist_centres
        peak1 = analysis.peak_position(centres, worker.histogram(), around=0.0, window=0.4)
        peak2 = analysis.peak_position(centres, worker.histogram2(), around=0.0, window=0.4)
        assert abs(peak1) < 0.1 and abs(peak1 - peak2) < 0.02
        # a hand move says which channel called the junction open
        worker.cmd_goto(0.0)
        assert "(ch 2: " in _status(worker) and _status(worker).endswith("open")
        worker.end_experiment()
        assert worker.noise_floors()[0] is not None
        worker.begin_experiment()
        assert worker.noise_floors() == (None, None)
        worker.end_experiment()
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)
