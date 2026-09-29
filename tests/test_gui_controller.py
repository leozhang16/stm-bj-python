"""Every Igor button, pressed headlessly against the simulator.

The controller has no Tk in it, so this exercises the same code the panels
call, in the same worker thread, and asserts on the events the panels would
have drawn.
"""

from __future__ import annotations

import queue

import numpy as np
import pytest

from stmgui.controller import RigController, NotReady
from stmgui.state import PARAMS, GuiState, simulated_state


@pytest.fixture
def ctl(tmp_path):
    state = simulated_state()
    state.opts.data_dir = str(tmp_path)
    state.cfg.vzero.n_points = 3
    state.cfg.vzero.settle_s = 0.0
    events: "queue.Queue" = queue.Queue()
    c = RigController(state, events)
    c.connect_instruments(wait=True)
    yield c
    c.shutdown()


def drain(c: RigController) -> dict[str, list]:
    out: dict[str, list] = {}
    while True:
        try:
            kind, payload = c.events.get_nowait()
        except queue.Empty:
            return out
        out.setdefault(kind, []).append(payload)


# -- binding table ---------------------------------------------------------

def test_every_param_round_trips():
    state = GuiState()
    for name, p in PARAMS.items():
        value = p.get(state)
        stored = p.set(state, value)
        assert p.get(state) == pytest.approx(stored) if p.kind is not bool \
            else p.get(state) == stored, name


def test_tip_bias_param_is_millivolts():
    state = GuiState()
    assert PARAMS["G_TipBias"].get(state) == pytest.approx(100.0)
    PARAMS["G_TipBias"].set(state, 250.0)
    assert state.cfg.ramp.bias_v == pytest.approx(0.250)


def test_mode_checkboxes_are_exclusive():
    o = GuiState().opts
    o.select_mode("iv", True)
    assert o.mode() == "iv"
    o.select_mode("hb_hold", True)
    assert o.mode() == "hb_hold" and not o.iv_check
    o.select_mode("hb_hold", False)
    assert o.mode() == "constant"


# -- DAQ tab ---------------------------------------------------------------

def test_buttons_refuse_without_start_writing(ctl):
    with pytest.raises(NotReady):
        ctl.piezo_step(5.0, wait=True)
    with pytest.raises(NotReady):
        ctl.start_measurement(single=True, wait=True)


def test_start_writing_then_kill(ctl):
    ctl.start_writing(wait=True)
    ev = drain(ctl)
    assert ev["writing"] == [True]
    assert ctl.rig is not None
    assert ctl.calibrated
    ctl.kill_tasks(wait=True)
    ev = drain(ctl)
    assert ev["writing"] == [False]
    assert ctl.rig is None
    assert ctl.opts.zero_check is True


def test_background_sampling_updates_readouts(ctl):
    ctl.set_background_sampling(True)
    assert "error" in drain(ctl)              # needs the output task
    ctl.start_writing(wait=True)
    ctl.set_background_sampling(True)
    import time
    deadline = time.time() + 3.0
    got = None
    while time.time() < deadline and got is None:
        ev = drain(ctl)
        if "readout" in ev:
            got = ev["readout"][-1]
        time.sleep(0.05)
    assert got is not None and "current_ua" in got
    ctl.set_background_sampling(False)


# -- piezo / actuator ------------------------------------------------------

def test_piezo_step_and_slider(ctl):
    ctl.start_writing(wait=True)
    drain(ctl)
    ctl.piezo_step(5.0, wait=True)
    ev = drain(ctl)
    assert ev["piezo"][-1]["nm"] == pytest.approx(5.0, abs=0.01)
    ctl.piezo_goto(1.0, wait=True)
    assert drain(ctl)["piezo"][-1]["volts"] == pytest.approx(1.0)


def test_approach_steps_until_current(ctl):
    ctl.start_writing(wait=True)
    drain(ctl)
    n = ctl.approach(wait=True)
    ev = drain(ctl)
    assert n > 0 and ev["counter"][-1] == n
    assert ctl.cfg.actuator.step_size == 5        # Igor forced this


def test_step_actuator_without_rig_uses_standalone_actuator(ctl):
    ctl.step_actuator(closer=False, wait=True)    # must not raise


# -- Keithley --------------------------------------------------------------

def test_keithley_controls_send_igor_commands(ctl):
    amp = ctl.amp
    amp.commands.clear()
    ctl.zero_check(False, wait=True)
    ctl.zero_correct(wait=True)
    ctl.suppress_enable(True, wait=True)
    ctl.set_gain(7, wait=True)
    ctl.set_suppress_const(2.0, wait=True)
    ctl.keithley_bias(True, wait=True)
    assert amp.commands[:3] == ["C0X", "C2X", "N1X"]
    assert "H6R7X" in amp.commands and "B1X" in amp.commands
    assert ctl.cfg.cal.preamp_gain_v_per_a == pytest.approx(1e7)
    assert ctl.cfg.keithley.enabled


def test_tip_bias_quantised_with_keithley_bias(ctl):
    ctl.keithley_bias(True, wait=True)
    ctl.set_tip_bias(123.0, wait=True)
    assert ctl.cfg.ramp.bias_v == pytest.approx(0.120)
    with pytest.raises(Exception):
        ctl.set_tip_bias(9000.0, wait=True)      # beyond limits.bias_max_v


# -- Find Zero (Find Offset) then Find Suppress ----------------------------

def test_find_offset_then_find_suppress(ctl):
    ctl.start_writing(wait=True)
    drain(ctl)
    result = ctl.find_offset(wait=True)
    ev = drain(ctl)
    assert np.isfinite(result.vzero_mv)
    assert ev["vzero"][-1][0] == pytest.approx(result.vzero_mv)
    assert "izero" in ev and "izero_time" in ev
    assert ctl.opts.izero_ua == pytest.approx(result.izero_a * 1e6)

    bias_before = ctl.cfg.ramp.bias_v
    ctl.find_suppress(wait=True)
    ev = drain(ctl)
    new_ua, sweep, readings = ev["suppress"][-1]
    assert sweep.size == 21 and readings.size == 21
    assert ctl.rig.bias_v == pytest.approx(bias_before)   # restored


# -- Start Measurement / +1 --------------------------------------------------

def test_single_attempt_and_run(ctl):
    ctl.start_writing(wait=True)
    drain(ctl)
    ctl.opts.stop_number = ctl.opts.pull_out_number + 3
    ctl.start_measurement(single=True, wait=True)
    ev = drain(ctl)
    assert ev["attempts"][-1] == 1
    assert "trace" in ev
    stats = ctl.start_measurement(wait=True)
    ev = drain(ctl)
    assert ctl.opts.pull_out_number == ctl.opts.stop_number
    assert stats["accepted"] >= 1
    assert "hist" in ev and ev["hist"][-1]["partial"]
    assert len(ctl.session_files) == 2
    from stmlab.storage import Session
    with Session(ctl.session_files[-1]) as s:
        assert len(s) == stats["accepted"]


def test_vzero_check_feeds_the_bias(ctl):
    ctl.start_writing(wait=True)
    ctl.opts.vzero_check = True
    ctl.cfg.vzero.every_n_traces = 2
    ctl.find_offset(wait=True)
    ctl.opts.stop_number = ctl.opts.pull_out_number + 4
    ctl.start_measurement(wait=True)
    assert len(ctl.vzero_tracker.history) >= 2      # re-measured mid-run


@pytest.mark.parametrize("mode", ["push_pull", "iv", "ac_hold", "hb_hold"])
def test_ramp_modes(ctl, mode):
    ctl.start_writing(wait=True)
    ctl.opts.select_mode(mode, True)
    ctl.opts.stop_number = ctl.opts.pull_out_number + 2
    stats = ctl.start_measurement(wait=True)
    ev = drain(ctl)
    assert stats["mode"] == mode and stats["accepted"] == 2
    assert ev["trace"][-1]["mode"] == mode


def test_stop_ends_a_run(ctl):
    ctl.start_writing(wait=True)
    ctl.opts.stop_number = 10_000
    ctl.start_measurement()            # queued, not waited
    import time
    time.sleep(0.5)
    ctl.request_stop()
    ctl.wait_idle()
    assert ctl.opts.pull_out_number < 10_000


# -- EChem / X piezo / macros ----------------------------------------------

def test_counter_electrode_and_cv(ctl):
    ctl.counter_electrode_on(wait=True)
    ctl.set_counter_electrode(250.0, wait=True)
    assert ctl.cfg.echem.gate_mv == 250.0
    cycles = ctl.start_cv("highres", wait=True)
    ev = drain(ctl)
    assert len(cycles) == ctl.cfg.echem.cycles and "cv" in ev


def test_xpiezo_and_lateral(ctl):
    ctl.start_writing(wait=True)
    ctl.move_xpiezo(200.0, wait=True)
    assert drain(ctl)["xpiezo"][-1] == pytest.approx(200.0)
    start = ctl.opts.pull_out_number
    ctl.lateral_expt(z_distance=5, x_distance_nm=200.0, x_freq=2,
                     final_stop_number=start + 3, wait=True)
    assert ctl.opts.pull_out_number >= start + 3


def test_rungo_resumes_from_saved(ctl):
    ctl.start_writing(wait=True)
    ctl.cfg.limits.bias_max_v = 0.5
    ctl.opts.pull_out_number = 5                  # inside step 1's range
    ctl.rungo(biases_mv=[-100.0, -200.0, -300.0], counts_each=3, wait=True)
    assert ctl.opts.pull_out_number == 10          # 3*3 + 1
    assert ctl.cfg.ramp.bias_v == pytest.approx(-0.300)


def test_config_save_load(ctl, tmp_path):
    path = tmp_path / "cfg.json"
    ctl.cfg.ramp.pull_length_nm = 7.5
    ctl.save_config(path)
    ctl.cfg.ramp.pull_length_nm = 1.0
    ctl.load_config(path)
    assert ctl.cfg.ramp.pull_length_nm == 7.5


# -- the button map ---------------------------------------------------------

def test_every_public_command_is_in_the_button_map():
    from stmgui.controller import COMMAND_MAP, RigController, command_table, \
        describe_command
    public = {n for n in dir(RigController)
              if not n.startswith("_") and callable(getattr(RigController, n))
              and n not in ("wait_idle", "igor_globals", "data_dir")}
    assert public <= set(COMMAND_MAP), public - set(COMMAND_MAP)
    rows = command_table()
    assert len(rows) == len(COMMAND_MAP)
    for row in rows:
        assert row["where"].startswith("stmgui/controller.py:"), row
        for call in row["calls"]:
            assert not call.startswith("?"), (row["method"], call)
    text = describe_command(RigController.find_suppress)
    assert "stmgui/controller.py:" in text
    assert "stmlab/keithley.py:" in text and "find_suppress" in text
    assert "TestVirtualGround" in text
