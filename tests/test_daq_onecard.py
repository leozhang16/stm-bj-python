"""The piezo sense line on a one-card rig (channels.sense_device = the
record's own card): the config names it, the simulator carries it, and the
real DaqSession reads it as the record task's third channel and keeps the
(2, n) record contract. DaqSession is exercised against a small fake
nidaqmx, since no card is attached to the test machine."""
from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from stmlab import trace
from stmlab.config import RigConfig
from stmlab.instrument import Rig
from stmlab.sim import SimulatedDaqSession


def _one_card_with_sense() -> RigConfig:
    cfg = RigConfig()
    cfg.simulate = True
    cfg.channels.device = "Dev1"
    cfg.channels.ao_piezo, cfg.channels.ao_bias = "ao1", "ao2"
    cfg.channels.ai_voltage, cfg.channels.ai_current = "ai1", "ai2"
    cfg.channels.low_res_device = None
    cfg.channels.sense_device = "Dev1"
    cfg.channels.ai_piezo_sense = "ai3"
    return cfg


def test_the_config_puts_the_sense_line_on_the_record_card():
    cfg = _one_card_with_sense()
    m = cfg.channels
    assert m.has_piezo_sense and m.sense_in_record
    assert m.piezo_sense_path == "Dev1/ai3"
    assert m.ai_channels == ("Dev1/ai1", "Dev1/ai2")
    # the two-card layout is untouched by the new field
    two = RigConfig()
    two.channels.low_res_device = "dev2"
    assert two.channels.has_piezo_sense and not two.channels.sense_in_record
    assert two.channels.piezo_sense_path == "dev2/ai2"
    # and a one-card rig that names no sense card has no sense line, as before
    assert not RigConfig().channels.has_piezo_sense


def test_the_config_round_trips_sense_device_through_json(tmp_path):
    cfg = _one_card_with_sense()
    path = tmp_path / "onecard.json"
    cfg.to_json(path)
    back = RigConfig.from_json(path)
    assert back.channels.sense_device == "Dev1"
    assert back.channels.piezo_sense_path == "Dev1/ai3" and back.channels.sense_in_record


def test_the_simulator_carries_the_readback_on_one_card():
    cfg = _one_card_with_sense()
    cfg.ramp.traces_target = 2
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=5))
    rig.open()
    try:
        rig.hold(n_samples=300)
        assert rig.last_sense_v is not None and rig.last_sense_v.size == 300
        got = []
        trace.trace_loop(rig, n=1, on_trace=lambda i, tr, sel: got.append(tr))
        assert got[0].piezo_sense_v is not None
        assert got[0].piezo_sense_v.size == got[0].current_v.size
    finally:
        rig.close()


# --------------------------------------------------------------------------
# DaqSession against a fake nidaqmx
# --------------------------------------------------------------------------

class _Chans:
    def __init__(self):
        self.names: list[str] = []
        self._objs: list = []

    def add_ai_voltage_chan(self, name, **kw):
        self.names.append(name)
        self._objs.append(types.SimpleNamespace(name=name, kw=kw))

    def add_ao_voltage_chan(self, name, **kw):
        self.names.append(name)
        self._objs.append(types.SimpleNamespace(name=name, kw=kw,
                                                ao_idle_output_behavior=None))

    def __iter__(self):
        return iter(self._objs)


class _Timing:
    samp_clk_rate = 40000.0

    def cfg_samp_clk_timing(self, rate, sample_mode=None, samps_per_chan=0):
        self.rate, self.n = rate, samps_per_chan


class _Trig:
    retriggerable = False

    def cfg_dig_edge_start_trig(self, terminal):
        self.terminal = terminal

    def disable_start_trig(self):
        self.terminal = None


class FakeTask:
    made: list = []

    def __init__(self, name=""):
        self.name = name
        self.ai_channels = _Chans()
        self.ao_channels = _Chans()
        self.timing = _Timing()
        self.triggers = types.SimpleNamespace(start_trigger=_Trig())
        self.written = None
        FakeTask.made.append(self)

    def write(self, data, auto_start=False, timeout=0):
        self.written = np.asarray(data)

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass

    def control(self, mode):
        pass

    def wait_until_done(self, timeout=0):
        pass

    def read(self, number_of_samples_per_channel=0, timeout=0):
        n = number_of_samples_per_channel
        k = len(self.ai_channels.names)
        # channel c reads as c + sample index / n, so rows are telling
        return [[c + i / n for i in range(n)] for c in range(k)]


@pytest.fixture
def fake_nidaqmx(monkeypatch):
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
    return mod


def test_daq_session_reads_the_sense_as_the_third_channel(fake_nidaqmx):
    from stmlab.daq import DaqSession
    cfg = _one_card_with_sense()
    cfg.simulate = False
    with DaqSession(cfg) as s:
        ai = next(t for t in FakeTask.made if t.name == "stmbj_ai")
        assert ai.ai_channels.names == ["Dev1/ai1", "Dev1/ai2", "Dev1/ai3"]
        assert not any(t.name == "stmbj_sense" for t in FakeTask.made)
        assert s.sense_sync == "hardware"
        n = 50
        record = s.play(np.zeros((2, n)))
        assert record.shape == (2, n)               # the contract above this layer
        assert record[0, 0] == 0.0 and record[1, 0] == 1.0
        assert s.last_sense_v.shape == (n,)
        assert s.last_sense_v[0] == 2.0             # channel 2 = the sense line


def test_daq_session_keeps_a_separate_task_on_two_cards(fake_nidaqmx):
    from stmlab.daq import DaqSession
    cfg = RigConfig()
    cfg.channels.low_res_device = "dev2"             # the original layout
    with DaqSession(cfg) as s:
        ai = next(t for t in FakeTask.made if t.name == "stmbj_ai")
        sense = next(t for t in FakeTask.made if t.name == "stmbj_sense")
        assert ai.ai_channels.names == ["Dev1/ai0", "Dev1/ai1"]
        assert sense.ai_channels.names == ["dev2/ai2"]
        record = s.play(np.zeros((2, 20)))
        assert record.shape == (2, 20) and s.last_sense_v.shape == (20,)


# --------------------------------------------------------------------------
# The record inputs' wiring mode: channels.ai_terminal, switched live
# --------------------------------------------------------------------------

def test_ai_terminal_is_checked_by_validate():
    from stmlab.config import ConfigError, validate
    cfg = RigConfig()
    cfg.channels.ai_terminal = "rse"
    validate(cfg)
    cfg.channels.ai_terminal = "sideways"
    with pytest.raises(ConfigError):
        validate(cfg)


def test_the_simulator_switches_the_mode_and_the_config_follows():
    cfg = _one_card_with_sense()
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=2))
    rig.open()
    try:
        assert "rse" in rig.ai_terminal_modes()
        rig.set_ai_terminal("RSE")
        assert cfg.channels.ai_terminal == "rse"
        assert cfg.channels.sense_terminal == "rse"       # same card: switched together
        rig.hold(n_samples=100)                       # still reads afterwards
        with pytest.raises(ValueError):
            rig.set_ai_terminal("sideways")
    finally:
        rig.close()


def test_daq_session_rebuilds_the_input_task_in_the_new_mode(fake_nidaqmx):
    from stmlab.daq import DaqSession
    cfg = _one_card_with_sense()
    cfg.simulate = False
    cfg.channels.ai_terminal = "default"
    with DaqSession(cfg) as s:
        first = next(t for t in FakeTask.made if t.name == "stmbj_ai")
        tc = fake_nidaqmx.constants.TerminalConfiguration
        assert [c.kw["terminal_config"] for c in first.ai_channels][:2] == [tc.DEFAULT, tc.DEFAULT]
        s.play(np.zeros((2, 20)))
        s.set_ai_terminal("rse")
        second = [t for t in FakeTask.made if t.name == "stmbj_ai"][-1]
        assert second is not first
        assert [c.kw["terminal_config"] for c in second.ai_channels][:2] == [tc.RSE, tc.RSE]
        assert second.ai_channels.names == ["Dev1/ai1", "Dev1/ai2", "Dev1/ai3"]  # the sense rides along
        assert second.ai_channels._objs[2].kw["terminal_config"] == tc.RSE      # in the same mode
        assert cfg.channels.sense_terminal == "rse"
        assert cfg.channels.ai_terminal == "rse"
        record = s.play(np.zeros((2, 20)))            # timed again, still (2, n)
        assert record.shape == (2, 20) and s.last_sense_v.shape == (20,)


def test_a_two_card_rig_keeps_its_own_sense_mode():
    cfg = RigConfig()
    cfg.channels.low_res_device = "dev2"               # the original layout
    cfg.simulate = True
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=4))
    rig.open()
    try:
        rig.set_ai_terminal("rse")
        assert cfg.channels.ai_terminal == "rse"
        assert cfg.channels.sense_terminal == "default"   # the other card: untouched
    finally:
        rig.close()


def test_a_rig_opens_without_touching_the_actuator_port():
    """Bring-up, the piezo sweep and a pull need the card, not the actuator:
    an Agilis in the config with no NI-VISA, no port, or Igor holding it
    must not stop the rig from opening. The port opens on connect_actuator()."""
    from stmlab.actuator import ActuatorError, UnconnectedActuator
    cfg = RigConfig()
    cfg.channels.device = "Dev1"
    cfg.actuator.kind = "agilis"
    cfg.actuator.port = "COM99"                        # nothing there
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=1))
    rig.open()                                         # no exception
    try:
        assert isinstance(rig.actuator, UnconnectedActuator)
        with pytest.raises(ActuatorError):
            rig.coarse_step(closer=False)              # a move says: connect first
        with pytest.raises(ActuatorError):
            rig.connect_actuator()                     # and connecting fails loudly
    finally:
        rig.close()
