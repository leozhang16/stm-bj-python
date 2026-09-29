"""Tests that need no hardware -- the validated core, ported from stmbj.

Phases 1 and 2 of the original build order: the validator catches a bad
config, every guard is exercised, and the analysis path is checked against
numbers that can be worked out by hand. This file is the stmbj suite with
imports pointed at stmlab; every test's substance is unchanged.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from stmlab import analysis, approach, safety, storage, trace
from stmlab.config import (G0_SIEMENS, ConfigError, RigConfig, validate)
from stmlab.instrument import Rig
from stmlab.safety import RigState, SafetyViolation
from stmlab.sim import SimulatedDaqSession


@pytest.fixture
def cfg() -> RigConfig:
    c = RigConfig()
    c.simulate = True
    c.ramp.traces_target = 5
    return c


@pytest.fixture
def rig(cfg):
    r = Rig(cfg, session=SimulatedDaqSession(cfg, seed=7))
    r.open()
    yield r
    r.close()


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------

def test_defaults_are_valid(cfg):
    validate(cfg)                       # must not raise


def test_validator_catches_clipping(cfg):
    cfg.cal.preamp_gain_v_per_a = 1e9   # 1 G0 would be 7748 V
    with pytest.raises(ConfigError, match="CLIP"):
        validate(cfg)


def test_validator_catches_unreachable_engage_threshold(cfg):
    """The mistake Igor's own defaults contain."""
    cfg.ramp.engage_g0 = 5.0            # needs 38.7 V at the ADC
    warnings = validate(cfg)
    assert any("saturat" in w for w in warnings)


def test_validator_catches_zero_bias(cfg):
    cfg.ramp.bias_v = 0.0
    with pytest.raises(ConfigError, match="divide by zero"):
        validate(cfg)


def test_validator_catches_bias_over_limit(cfg):
    cfg.ramp.bias_v = 1.0               # limit is 0.5
    with pytest.raises(ConfigError, match="exceeds"):
        validate(cfg)


def test_one_g0_matches_the_documented_budget(cfg):
    """1 G0 at 100 mV through 1e6 V/A is 7.748 V. From the setup document."""
    assert cfg.cal.g0_to_volts(1.0, 0.1) == pytest.approx(7.748, abs=1e-3)


def test_config_round_trips_through_json(cfg, tmp_path):
    cfg.cal.current_zero_v = 1.234e-4
    cfg.notes = "round trip"
    path = tmp_path / "rig.json"
    cfg.to_json(path)
    back = RigConfig.from_json(path)
    assert back.cal.current_zero_v == pytest.approx(1.234e-4)
    assert back.notes == "round trip"
    assert back.limits.piezo_ao_max_v == cfg.limits.piezo_ao_max_v


def test_row_indices_do_not_reach_the_data_file(cfg):
    assert "ROW_VOLTAGE" not in cfg.to_dict()["channels"]


# --------------------------------------------------------------------------
# safety
# --------------------------------------------------------------------------

def test_piezo_clamps_rather_than_raising(cfg):
    assert safety.clamp_piezo(cfg, 99.0) == cfg.limits.piezo_ao_max_v
    assert safety.clamp_piezo(cfg, -5.0) == cfg.limits.piezo_ao_min_v
    assert safety.clamp_piezo(cfg, 4.0) == 4.0


def test_bias_refuses_rather_than_clamping(cfg):
    with pytest.raises(SafetyViolation):
        safety.check_bias(cfg, 5.0)
    assert safety.check_bias(cfg, 0.1) == 0.1


def test_interlock_refuses_coarse_step_when_extended(cfg):
    with pytest.raises(SafetyViolation, match="Retract the fine piezo"):
        safety.require_retracted(cfg, piezo_v=5.0, action="coarse step")
    safety.require_retracted(cfg, piezo_v=0.0, action="coarse step")


def test_interlock_fires_through_the_rig(rig):
    """The guard must be reachable from where it actually matters."""
    rig.piezo_goto(5.0)
    with pytest.raises(SafetyViolation):
        rig.coarse_step(closer=True)


def test_step_budget_stops_a_runaway(cfg):
    with pytest.raises(SafetyViolation, match="without finding"):
        safety.check_step_budget(cfg, cfg.limits.max_coarse_steps)


def test_pull_headroom_refuses_a_ramp_through_the_floor(cfg):
    safety.check_pull_headroom(cfg, start_v=5.0)
    with pytest.raises(SafetyViolation, match="working floor"):
        safety.check_pull_headroom(cfg, start_v=0.05)


# --------------------------------------------------------------------------
# analysis
# --------------------------------------------------------------------------

def test_average_deviation_is_not_the_standard_deviation():
    x = np.array([-1.0, 1.0, -1.0, 1.0])
    assert analysis.average_deviation(x) == pytest.approx(1.0)
    # For gaussian noise the two differ by sqrt(2/pi); confirm we did not
    # quietly implement std.
    rng = np.random.default_rng(0)
    g = rng.normal(size=100_000)
    assert analysis.average_deviation(g) == pytest.approx(
        math.sqrt(2 / math.pi), abs=0.01)


def test_boxcar_holds_the_ends_rather_than_pulling_them_to_zero():
    x = np.full(50, 5.0)
    assert analysis.boxcar(x, 11) == pytest.approx(x)


def test_conductance_of_one_g0(cfg):
    """A junction at exactly 1 G0 must read 1.0, by construction."""
    bias = 0.1
    current_v = np.full(10, cfg.cal.g0_to_volts(1.0, bias))
    voltage_v = np.full(10, cfg.cal.bias_output_sign * bias)
    g0 = analysis.to_conductance(current_v, cfg.cal, voltage_v=voltage_v)
    assert g0 == pytest.approx(1.0)


def test_conductance_uses_2e2_over_h():
    assert G0_SIEMENS == pytest.approx(7.748e-5, rel=1e-3)


def test_alignment_edge_is_found_sub_sample():
    v = np.full(1000, -0.1)
    v[700:760] = 0.1                      # a spike, rising between 699 and 700
    edge = analysis.find_alignment_edge(v)
    assert edge == pytest.approx(699.5, abs=0.51)


def test_alignment_edge_returns_none_without_a_spike():
    assert analysis.find_alignment_edge(np.full(1000, -0.1)) is None


def test_selection_rejects_a_trace_that_never_broke(cfg):
    g0 = np.full(10_000, 1.0)             # never falls into tunnelling
    verdict = analysis.select_trace(g0, cfg.ramp)
    assert not verdict.accepted
    assert "break threshold" in verdict.reason


def test_selection_rejects_a_trace_with_no_gold_plateau(cfg):
    g0 = np.full(10_000, 1e-8)
    g0[:100] = 50.0                       # engaged, but nothing near 1 G0
    verdict = analysis.select_trace(g0, cfg.ramp)
    assert not verdict.accepted


def test_selection_reproduces_igors_disabled_engage_check(cfg):
    """Igor commented out the else branch, so a non-engaged trace passes.

    The trace below has a gold plateau and ends in tunnelling, but its opening
    samples -- the window the engage check looks at -- sit below the
    threshold, as they would for a junction that was already partly broken
    when the pull began.
    """
    n = 10_000
    head = int(round(n / 200)) + 1        # the window select_trace samples
    g0 = np.full(n, 1e-8)
    g0[:head] = 0.3 * cfg.ramp.engage_g0  # never engaged
    g0[head:2000] = 1.0                   # but there is a plateau

    lenient = analysis.select_trace(g0, cfg.ramp, require_engaged=False)
    strict = analysis.select_trace(g0, cfg.ramp, require_engaged=True)
    assert lenient.accepted
    assert not strict.accepted
    assert "engage" in strict.reason


def test_histogram_puts_a_known_plateau_where_it_belongs():
    """A synthetic trace held at 1e-3 G0 must peak at -3 decades."""
    trace_g0 = np.concatenate([np.full(5000, 1.0), np.full(5000, 1e-3)])
    centres, counts = analysis.log_histogram([trace_g0], subtract_floor=False)
    peak = analysis.peak_position(centres, counts, around=-3.0, window=0.3)
    assert peak == pytest.approx(-3.0, abs=0.02)


def test_histogram_is_counts_per_trace():
    one = np.full(1000, 1e-3)
    _, a = analysis.log_histogram([one], subtract_floor=False)
    _, b = analysis.log_histogram([one] * 7, subtract_floor=False)
    assert a.sum() == pytest.approx(b.sum())


# --------------------------------------------------------------------------
# ramp construction
# --------------------------------------------------------------------------

def test_ramp_descends_by_exactly_the_pull_length(cfg):
    ramp = trace.build_ramp(cfg, start_piezo_v=5.0)
    travelled = (ramp.start_piezo_v - ramp.end_piezo_v) \
        * cfg.cal.piezo_nm_per_volt
    assert travelled == pytest.approx(cfg.ramp.pull_length_nm, rel=1e-3)


def test_ramp_stays_inside_the_piezo_range(cfg):
    ramp = trace.build_ramp(cfg, start_piezo_v=5.0)
    piezo = ramp.waveform[cfg.channels.ROW_PIEZO]
    assert piezo.min() >= cfg.limits.piezo_ao_min_v
    assert piezo.max() <= cfg.limits.piezo_ao_max_v


def test_ramp_carries_an_alignment_spike_of_the_right_sign(cfg):
    ramp = trace.build_ramp(cfg, start_piezo_v=5.0)
    bias = ramp.waveform[cfg.channels.ROW_BIAS]
    baseline = cfg.cal.bias_output_sign * cfg.ramp.bias_v
    assert bias[0] == pytest.approx(baseline)
    assert np.any(np.sign(bias) != np.sign(baseline))


def test_ramp_refuses_to_start_too_low(cfg):
    with pytest.raises(SafetyViolation):
        trace.build_ramp(cfg, start_piezo_v=0.01)


# --------------------------------------------------------------------------
# the loop, against the simulator
# --------------------------------------------------------------------------

def test_rig_tracks_the_piezo_through_play(rig, cfg):
    rig.piezo_goto(3.0)
    assert rig.piezo_v == pytest.approx(3.0)
    rig.piezo_step_nm(62.0)               # exactly one volt
    assert rig.piezo_v == pytest.approx(4.0)


def test_engage_reaches_contact(rig):
    assert approach.engage(rig) is RigState.ENGAGED
    assert rig.in_contact()


def test_single_trace_recovers_the_group_delay(rig):
    approach.engage(rig)
    tr = trace.single_trace(rig)
    assert tr is not None
    # The simulator delays by 37 samples; the spike must find it.
    assert tr.delay_samples == pytest.approx(37, abs=2)
    assert tr.voltage_v.size == rig.cfg.ramp.n_pull_samples


def test_group_delay_probe_is_detectable(rig):
    """The calibration probe must be a shape find_alignment_edge can read.

    Regression: the probe was originally a single step, which produces one
    level crossing, while the detector needs the two that a spike produces.
    It returned None every time -- and would have on the real card too.
    """
    from stmlab import calibrate
    mean, sd = calibrate.measure_group_delay(rig, repeats=5)
    assert mean == pytest.approx(37, abs=2)     # the simulator's delay
    assert sd < 1.0


def test_trace_loop_collects_and_reports(rig):
    stats = trace.trace_loop(rig, n=4)
    assert stats["accepted"] == 4
    assert stats["acceptance_rate"] > 0


def test_gold_peak_lands_at_zero_decades(rig, cfg):
    """The end-to-end check: simulated physics through to a histogram."""
    traces = []
    trace.trace_loop(rig, n=25,
                     on_trace=lambda i, tr, sel: traces.append(
                         tr.conductance_g0(cfg)))
    centres, counts = analysis.log_histogram(traces)
    peak = analysis.peak_position(centres, counts, around=0.0, window=0.4)
    assert peak == pytest.approx(0.0, abs=0.05)


# --------------------------------------------------------------------------
# storage
# --------------------------------------------------------------------------

def test_session_round_trips_raw_volts(rig, cfg, tmp_path):
    path = tmp_path / "session.h5"
    with storage.SessionWriter(path, cfg) as writer:
        trace.trace_loop(rig, n=3, on_trace=writer.append)

    with storage.Session(path) as session:
        assert len(session) == 3
        voltage, current = session.raw(0)
        assert voltage.size == cfg.ramp.n_pull_samples
        assert np.isfinite(current).all()
        assert session.cfg.cal.preamp_gain_v_per_a == \
            cfg.cal.preamp_gain_v_per_a


def test_reanalysis_with_a_corrected_gain_changes_the_answer(rig, cfg,
                                                            tmp_path):
    """The reason raw volts are stored rather than conductance."""
    path = tmp_path / "session.h5"
    with storage.SessionWriter(path, cfg) as writer:
        trace.trace_loop(rig, n=2, on_trace=writer.append)

    with storage.Session(path) as session:
        as_stored = session.conductance(0)
        corrected_cal = session.cfg.cal
        corrected_cal.preamp_gain_v_per_a *= 10.0
        corrected = session.conductance(0, cal=corrected_cal)

    assert np.nanmedian(as_stored / corrected) == pytest.approx(10.0, rel=1e-6)


def test_igor_block_splits_into_traces_and_parameters():
    n_samples, n_traces = 500, 4
    block = np.zeros((n_samples + 2 + 20, n_traces))
    block[n_samples + 2 + 10, :] = 100.0          # tip bias, mV
    traces, params = storage.split_igor_block(block)
    assert traces.shape == (n_traces, n_samples)
    assert params.shape == (n_traces, 20)
    assert np.all(params[:, 10] == 100.0)
