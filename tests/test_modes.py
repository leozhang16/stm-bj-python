"""Tests for the new core: ramps, echem, keithley, vzero, xpiezo.

Every number asserted here is worked out independently from the Igor code
these modules translate -- CreateInputs (Functions_STMBJ.ipf:1398-1633),
EChem_Module.ipf, SetUpGPIB_Keithley.ipf / Controls_STMBJ.ipf, and
OffsetVoltage (Functions_STMBJ.ipf:920) -- never read back from the module
under test.
"""

from __future__ import annotations

import numpy as np
import pytest

from stmlab import approach, echem, keithley, ramps, trace, vzero, xpiezo
from stmlab.config import G0_SIEMENS, PushPullConfig, RigConfig
from stmlab.instrument import Rig
from stmlab.safety import RigState, SafetyViolation
from stmlab.sim import SimulatedDaqSession

# A start position with headroom both ways on the 0-10 V unipolar piezo.
START = 6.0

ALL_BUILDERS = [ramps.build_push_pull, ramps.build_iv,
                ramps.build_ac_hold, ramps.build_hb_hold]


def n_points(cfg: RigConfig, length_nm: float) -> int:
    """Igor: round(Length / ExcursionRate * AcquisitionRate)."""
    return int(round(length_nm / cfg.ramp.pull_rate_nm_per_s
                     * cfg.ramp.sample_rate_hz))


@pytest.fixture
def cfg() -> RigConfig:
    c = RigConfig()
    c.simulate = True
    # The IV sweep reaches +/-1 V and the AC/HB holds reach 0.8 V; the
    # constant-bias limit of 0.5 V must be raised deliberately, exactly as
    # the mode runners do before validate().
    c.limits.bias_max_v = 1.0
    return c


@pytest.fixture
def rig(cfg):
    r = Rig(cfg, session=SimulatedDaqSession(cfg, seed=7))
    r.open()
    yield r
    r.close()


def pull_slice(ramp: ramps.ModeRamp, name: str) -> slice:
    """Segment indices -> indices into the written waveform."""
    a, b = ramp.segments[name]
    return slice(ramp.pre_pad + a, ramp.pre_pad + b)


# --------------------------------------------------------------------------
# Point counts: Igor's round(length/rate*fs), summed per segment
# --------------------------------------------------------------------------

def test_push_pull_point_count_matches_igor(cfg):
    pp = cfg.push_pull
    ramp = ramps.build_push_pull(cfg, START)
    expected = (n_points(cfg, pp.initial_pull_nm)
                + pp.cycles * 2 * (n_points(cfg, pp.push_pull_nm)
                                   + n_points(cfg, pp.hold_nm))
                + n_points(cfg, pp.final_pull_nm))
    assert ramp.n_pull == expected
    assert ramp.waveform.shape == (2, expected + cfg.ramp.pre_pad_samples
                                   + cfg.ramp.post_pad_samples)


def test_iv_point_count_matches_igor(cfg):
    iv = cfg.iv
    ramp = ramps.build_iv(cfg, START)
    expected = (n_points(cfg, iv.init_pull_nm) + 2 * n_points(cfg, iv.cap_nm)
                + n_points(cfg, iv.ramp_nm) + n_points(cfg, iv.final_pull_nm))
    assert ramp.n_pull == expected
    assert ramp.waveform.shape == (2, expected + cfg.ramp.pre_pad_samples
                                   + cfg.ramp.post_pad_samples)


def test_ac_hold_point_count_matches_igor(cfg):
    ac = cfg.ac_hold
    ramp = ramps.build_ac_hold(cfg, START)
    expected = (n_points(cfg, ac.init_pull_nm) + 2 * n_points(cfg, ac.cap_nm)
                + n_points(cfg, ac.hold_nm) + n_points(cfg, ac.final_pull_nm))
    assert ramp.n_pull == expected
    assert ramp.waveform.shape == (2, expected + cfg.ramp.pre_pad_samples
                                   + cfg.ramp.post_pad_samples)


def test_hb_hold_point_count_matches_igor(cfg):
    hb = cfg.hb_hold
    ramp = ramps.build_hb_hold(cfg, START)
    expected = (n_points(cfg, hb.init_pull_nm) + n_points(cfg, hb.cap_in_nm)
                + n_points(cfg, hb.hold_nm) + n_points(cfg, hb.cap_fin_nm)
                + n_points(cfg, hb.final_pull_nm))
    assert ramp.n_pull == expected
    assert ramp.waveform.shape == (2, expected + cfg.ramp.pre_pad_samples
                                   + cfg.ramp.post_pad_samples)


# --------------------------------------------------------------------------
# Piezo row: continuous, no teleports
# --------------------------------------------------------------------------

@pytest.mark.parametrize("build", ALL_BUILDERS)
def test_piezo_row_is_continuous(cfg, build):
    """No jump bigger than 2*dv between neighbours (pad boundaries aside)."""
    ramp = build(cfg, START)
    dv = cfg.ramp.pull_rate_nm_per_s / cfg.cal.piezo_nm_per_volt \
        / cfg.ramp.sample_rate_hz
    row = ramp.waveform[cfg.channels.ROW_PIEZO]
    steps = np.abs(np.diff(row))
    ok = np.ones(steps.size, dtype=bool)
    ok[ramp.pre_pad - 1] = False                    # pre-pad -> pull
    ok[ramp.pre_pad + ramp.n_pull - 1] = False      # pull -> post-pad
    assert steps[ok].max() <= 2 * dv + 1e-12
    # And the pads themselves are dead flat.
    assert np.ptp(row[:ramp.pre_pad]) == 0.0
    assert np.ptp(row[ramp.pre_pad + ramp.n_pull:]) == 0.0


# --------------------------------------------------------------------------
# Bias extremes
# --------------------------------------------------------------------------

def test_iv_bias_reaches_exactly_plus_minus_max(cfg):
    ramp = ramps.build_iv(cfg, START)
    bias = ramp.waveform[cfg.channels.ROW_BIAS]
    sweep = bias[pull_slice(ramp, "iv_ramp")]
    assert sweep.min() == pytest.approx(-cfg.iv.max_bias_v, abs=1e-12)
    assert sweep.max() == pytest.approx(+cfg.iv.max_bias_v, abs=1e-12)
    # Nothing outside the sweep (the spike included) exceeds it.
    assert np.max(np.abs(bias)) <= cfg.iv.max_bias_v + 1e-12


def test_ac_hold_bias_is_a_sine_of_the_right_amplitude(cfg):
    ramp = ramps.build_ac_hold(cfg, START)
    hold = ramp.waveform[cfg.channels.ROW_BIAS][pull_slice(ramp, "ac_hold")]
    # 10 kHz sampled at 40 kHz hits the crests exactly (4 samples/period);
    # allow the sine's floating-point resolution.
    assert hold.max() == pytest.approx(+cfg.ac_hold.amp_v, rel=1e-9)
    assert hold.min() == pytest.approx(-cfg.ac_hold.amp_v, rel=1e-9)
    assert hold[0] == pytest.approx(0.0, abs=1e-12)   # sine, no DC offset


def test_hb_hold_bias_is_minus_hold_bias(cfg):
    """Igor line 1592: InputWave1 = -G_HBBias during the hold."""
    ramp = ramps.build_hb_hold(cfg, START)
    hold = ramp.waveform[cfg.channels.ROW_BIAS][pull_slice(ramp, "hb_hold")]
    assert np.all(hold == -cfg.hb_hold.hold_bias_v)


def test_hb_hold_takes_the_measured_vzero(cfg):
    """Igor lines 1595-1599: VzeroCheckBox replaces the hold bias."""
    ramp = ramps.build_hb_hold(cfg, START, vzero_mv=-42.0)
    hold = ramp.waveform[cfg.channels.ROW_BIAS][pull_slice(ramp, "hb_hold")]
    assert np.all(hold == pytest.approx(+0.042))
    assert ramp.meta["from_vzero"] is True


@pytest.mark.parametrize("build", ALL_BUILDERS)
def test_alignment_spike_at_plus_bias_near_the_end(cfg, build):
    """Igor line 1631: +(TipBias/1000) in every mode, 7.5-2.5 ms from the end."""
    ramp = build(cfg, START)
    bias = ramp.waveform[cfg.channels.ROW_BIAS]
    assert bias[ramp.spike_front + 1] == pytest.approx(+cfg.ramp.bias_v)
    end_of_pull = ramp.pre_pad + ramp.n_pull
    front_pts = int(round(cfg.ramp.spike_front_ms * 1e-3
                          * cfg.ramp.sample_rate_hz))
    assert end_of_pull - ramp.spike_front == front_pts + 1


# --------------------------------------------------------------------------
# IV sign convention
# --------------------------------------------------------------------------

def test_iv_sweeps_to_the_negative_apex_by_default(cfg):
    """Igor builds the ramp positive then negates the whole wave (*= -1,
    line 1533): with positive_first=False the first quarter goes NEGATIVE."""
    cfg.iv.positive_first = False
    ramp = ramps.build_iv(cfg, START)
    b1, b2, b3, b4 = ramp.meta["quarters"]
    mid = ramp.pre_pad + (b1 + b2) // 2
    assert ramp.waveform[cfg.channels.ROW_BIAS][mid] < 0


def test_iv_sign_flag_flips_the_sweep_positive(cfg):
    """G_IVSignFlag (line 1535) negates the ramp segment a second time."""
    cfg.iv.positive_first = True
    ramp = ramps.build_iv(cfg, START)
    b1, b2, b3, b4 = ramp.meta["quarters"]
    mid = ramp.pre_pad + (b1 + b2) // 2
    assert ramp.waveform[cfg.channels.ROW_BIAS][mid] > 0


# --------------------------------------------------------------------------
# Push-pull structure
# --------------------------------------------------------------------------

def test_push_pull_holds_are_flat_and_push_raises_the_piezo(cfg):
    ramp = ramps.build_push_pull(cfg, START)
    piezo = ramp.waveform[cfg.channels.ROW_PIEZO]
    for k in range(cfg.push_pull.cycles):
        hold_out = piezo[pull_slice(ramp, f"cycle{k}_hold_out")]
        hold_in = piezo[pull_slice(ramp, f"cycle{k}_hold_in")]
        assert np.ptp(hold_out) == 0.0
        assert np.ptp(hold_in) == 0.0
        push = piezo[pull_slice(ramp, f"cycle{k}_push")]
        pull = piezo[pull_slice(ramp, f"cycle{k}_pull")]
        assert np.all(np.diff(push) > 0)          # push moves the tip IN (up)
        assert np.all(np.diff(pull) < 0)
        assert hold_in[0] > hold_out[0]           # held closer after the push


def test_push_pull_cycle_count_is_honoured(cfg):
    cfg.push_pull.cycles = 3
    ramp = ramps.build_push_pull(cfg, START)
    assert ramp.meta["cycles"] == 3
    cycle_keys = [k for k in ramp.segments if k.startswith("cycle")]
    assert len(cycle_keys) == 4 * 3               # four segments per cycle
    assert "cycle2_pull" in ramp.segments
    assert "cycle3_push" not in ramp.segments
    assert set(ramp.segments) >= {"initial_pull", "final_pull"}


def test_push_pull_bias_is_constant_outside_the_spike(cfg):
    ramp = ramps.build_push_pull(cfg, START)
    bias = ramp.waveform[cfg.channels.ROW_BIAS]
    baseline = cfg.cal.bias_output_sign * cfg.ramp.bias_v
    off_spike = np.abs(bias - baseline) < 1e-12
    assert off_spike[:ramp.spike_front].all()
    assert bias[0] == pytest.approx(baseline)


# --------------------------------------------------------------------------
# Refusals: floor and ceiling
# --------------------------------------------------------------------------

@pytest.mark.parametrize("build", ALL_BUILDERS)
def test_builders_refuse_a_start_through_the_floor(cfg, build):
    """Every mode nets a 7 nm descent by default; 0.05 V of headroom is not
    enough on a 62 nm/V piezo with a 0.02 V working floor."""
    with pytest.raises(SafetyViolation, match="floor"):
        build(cfg, start_piezo_v=0.05)


def test_push_pull_refuses_a_push_through_the_ceiling(cfg):
    """Igor only guarded the retracted side; a big push from a contact made
    near the top of the range would over-extend the piezo."""
    pp = PushPullConfig(initial_pull_nm=1.0, push_pull_nm=5.0, hold_nm=1.0,
                        final_pull_nm=1.0, cycles=1)
    with pytest.raises(SafetyViolation, match="ceiling"):
        ramps.build_push_pull(cfg, start_piezo_v=9.95, pp=pp)


# --------------------------------------------------------------------------
# capture: the one alignment path serves every mode
# --------------------------------------------------------------------------

def test_capture_recovers_the_group_delay_for_every_mode(cfg, rig):
    assert approach.engage(rig) is RigState.ENGAGED
    for build in ALL_BUILDERS:
        ramp = build(cfg, rig.piezo_v)
        tr = trace.capture(rig, ramp, index=0)
        assert tr is not None, f"{ramp.mode}: trace discarded"
        # The simulator delays by exactly 37 samples in every mode.
        assert tr.delay_samples == 37, ramp.mode
        assert tr.voltage_v.size == ramp.n_pull
        assert tr.current_v.size == ramp.n_pull


# --------------------------------------------------------------------------
# echem
# --------------------------------------------------------------------------

def _cv_r1_r2(ec):
    sweep_v_per_s = ec.scan_rate_mv_per_s / 1000.0
    r1 = int(round(2 * abs(ec.peak_one_v) / sweep_v_per_s * ec.cv_rate_hz))
    r2 = int(round(2 * abs(ec.peak_two_v) / sweep_v_per_s * ec.cv_rate_hz))
    return r1, r2


def test_cv_highres_ramp_matches_igor(cfg):
    """Igor CVcurveHighRes:127-158: 0 -> V1 -> 0 -> V2 -> 0 plus a repeated
    first half; NaN (here: keep=False) over the switch-on quarter and the
    repeat, leaving exactly one steady-state loop of R1+R2 points."""
    ec = cfg.echem
    r1, r2 = _cv_r1_r2(ec)
    applied, keep = echem.build_cv_ramp_highres(ec)

    assert applied.size == 2 * r1 + r2
    assert keep.size == applied.size
    assert applied[0] == 0.0
    assert applied.min() == pytest.approx(ec.peak_one_v, abs=1e-12)
    assert applied.max() == pytest.approx(ec.peak_two_v, abs=1e-12)
    assert applied[r1 // 2] == pytest.approx(ec.peak_one_v)   # first vertex
    assert applied[r1 + r2 // 2] == pytest.approx(ec.peak_two_v)
    assert not keep[:r1 // 2].any()               # switch-on quarter
    assert not keep[r1 + r2 + r1 // 2:].any()     # the repeated half
    assert keep.sum() == r1 + r2                  # one full loop survives


def test_cv_lowres_ramp_matches_igor(cfg):
    """Igor CVcurveLowRes:251-286: 5000 samples of 0 V first, total
    2*R1 + 3*R2/2 + SetZero points, same keep arithmetic shifted by z."""
    ec = cfg.echem
    r1, r2 = _cv_r1_r2(ec)
    z = 5000
    applied, keep = echem.build_cv_ramp_lowres(ec, set_zero=z)

    assert applied.size == 2 * r1 + 3 * r2 // 2 + z
    assert np.all(applied[:z] == 0.0)
    assert applied.min() == pytest.approx(ec.peak_one_v, abs=1e-12)
    assert applied.max() == pytest.approx(ec.peak_two_v, abs=1e-12)
    assert not keep[:z + r1 // 2].any()
    assert not keep[z + r1 + r2 + r1 // 2:].any()
    assert keep.sum() == r1 + r2


def test_run_cv_simulated_returns_the_asked_cycles(cfg):
    cycles = echem.run_cv(cfg, kind="highres", cycles=3)
    assert [c.cycle for c in cycles] == [1, 2, 3]
    for c in cycles:
        assert c.tip_current_v.shape == c.applied_v.shape
        assert c.we_voltage_mv is not None        # high-res reads ai0
        assert c.rate_hz == cfg.echem.cv_rate_hz

    lowres = echem.run_cv(cfg, kind="lowres", cycles=2)
    assert len(lowres) == 2
    assert lowres[0].we_voltage_mv is None        # tip current only


def test_counter_electrode_gate_travels_in_the_config(cfg):
    gate = echem.make_counter_electrode(cfg)
    assert isinstance(gate, echem.SimulatedCounterElectrode)
    with gate:
        gate.set_mv(250.0)
        assert gate.gate_mv == 250.0
        assert cfg.echem.gate_mv == 250.0         # saved with every trace
    assert gate.gate_mv == 0.0                    # off() resets


# --------------------------------------------------------------------------
# keithley
# --------------------------------------------------------------------------

def test_simulated_keithley_speaks_428(cfg):
    k = keithley.make_keithley(cfg)
    assert isinstance(k, keithley.SimulatedKeithley)
    k.open()
    assert k.commands[0] == "C1P0B0N0X"           # Igor's inert init

    k.set_gain(7)
    assert "H6R7X" in k.commands                  # Igor: "H6R"+gain+"X"

    k.set_bias_mv(103.0)                          # quantised to 5 mV steps
    assert k.commands[-1] == "V105E-3X"

    k.bias_enable(True)
    assert k.commands[-1] == "B1X" and k.bias_enabled


def test_series_corrected_conductance_hand_value():
    """A junction of exactly 1/G0 ohms behind the Igor default series
    resistance must read 1.0 G0 after the correction."""
    r_series = 106130.0
    bias = 0.1
    r_junction = 1.0 / G0_SIEMENS
    current = bias / (r_junction + r_series)
    g = keithley.series_corrected_conductance(current, bias, r_series)
    assert g == pytest.approx(1.0, rel=1e-9)
    # And without the correction the same current would look much smaller.
    assert current / bias / G0_SIEMENS < 0.2


# --------------------------------------------------------------------------
# vzero
# --------------------------------------------------------------------------

def test_measure_offset_on_the_simulated_rig(cfg):
    cfg.vzero.n_points = 3        # 6-point sweep, keeps the test quick
    cfg.vzero.settle_s = 0.0
    with Rig(cfg, session=SimulatedDaqSession(cfg, seed=3)) as rig:
        result = vzero.measure_offset(rig)
        restored_bias = rig.bias_v
    assert np.isfinite(result.vzero_mv)
    # The simulator has no input offset, so Vzero must come out near zero --
    # well inside the +/-5 mV sweep window.
    assert abs(result.vzero_mv) < cfg.vzero.interval_mv
    assert result.bias_mv.size == 2 * cfg.vzero.n_points
    assert np.isfinite(result.current_a).all()
    assert restored_bias == pytest.approx(cfg.ramp.bias_v)   # Igor :980


def test_vzero_tracker_measures_on_schedule(cfg):
    cfg.vzero.n_points = 2
    cfg.vzero.settle_s = 0.0
    cfg.vzero.every_n_traces = 2
    with Rig(cfg, session=SimulatedDaqSession(cfg, seed=5)) as rig:
        tracker = vzero.VzeroTracker(cfg)
        assert tracker.maybe_measure(rig, 0) is None
        assert tracker.maybe_measure(rig, 1) is None
        assert tracker.maybe_measure(rig, 2) is not None
    assert tracker.offset_v == pytest.approx(
        tracker.current.vzero_mv / 1000.0)
    assert tracker.as_arrays()["vzero_mv"].size == 1


# --------------------------------------------------------------------------
# xpiezo
# --------------------------------------------------------------------------

def test_simulated_xpiezo_refuses_beyond_its_range(cfg):
    xp = xpiezo.make_xpiezo(cfg)
    assert isinstance(xp, xpiezo.SimulatedXPiezo)
    with xp:
        xp.move_nm(2000.0)
        assert xp.position_nm == pytest.approx(2000.0)
        assert xp.voltage == pytest.approx(2000.0 / cfg.xpiezo.nm_per_volt)

        # 6000 nm needs 11.5 V of a 10 V channel: refuse, do not move.
        with pytest.raises(xpiezo.XPiezoError, match="outside"):
            xp.move_nm(4000.0)
        assert xp.position_nm == pytest.approx(2000.0)

        # The floor is guarded too (min_v = 0 on this unipolar channel).
        with pytest.raises(xpiezo.XPiezoError):
            xp.move_nm(-2500.0)

        xp.zero()
        assert xp.position_nm == 0.0
    assert xp.position_nm == 0.0                  # stop() parks at zero
