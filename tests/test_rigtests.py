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
        # The simulated surface sits at 300 nm: go past it, by hand.
        worker.cmd_goto(cfg.cal.nm_to_piezo_volts(300.5))
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
