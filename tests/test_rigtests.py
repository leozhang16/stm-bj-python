"""The parts of rigtests/02_approach_pull.py that decide things: the settings
check that stands between a typed number and the rig, and the monitor that
watches every play. No window, simulator only."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from stmlab import approach, storage
from stmlab.config import RigConfig
from stmlab.instrument import Rig
from stmlab.sim import SimulatedDaqSession

_HERE = Path(__file__).resolve().parents[1] / "rigtests"


def _load(name: str):
    """Import a rigtests script by file name (they start with a digit)."""
    import sys
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module          # dataclasses look the module up
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ap():
    return _load("02_approach_pull")


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
    h5 = list(tmp_path.glob("*.h5"))
    assert len(h5) == 1
    with storage.Session(h5[0]) as s:
        assert len(s) == worker.accepted >= 1
    pytest.importorskip("igor2")
    ibw = list(tmp_path.glob("*.ibw"))
    assert len(ibw) == 1
    traces, params = storage.split_igor_block(storage.load_ibw(ibw[0]))
    assert traces.shape == (worker.accepted, cfg.ramp.n_pull_samples)
    assert np.all(params[:, 10] == pytest.approx(cfg.ramp.bias_v * 1e3))
