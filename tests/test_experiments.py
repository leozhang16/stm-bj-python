"""Tests for the two scripted campaigns and the CV file format.

The experiment scripts are not importable as a package (each inserts the
repo root on sys.path and lives in a numbered folder), so they are loaded
here by path. That is deliberate: it tests them the way they actually run.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from stmlab import echem, storage
from stmlab.config import RigConfig
from stmlab.safety import SafetyViolation

ROOT = Path(__file__).resolve().parents[1]


def load_experiment(folder: str):
    """Import experiments/<folder>/run_experiment.py under a unique name."""
    path = ROOT / "experiments" / folder / "run_experiment.py"
    name = f"_exp_{folder}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cfg():
    c = RigConfig()
    c.simulate = True
    return c


# --------------------------------------------------------------------------
# 08 bias series
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def series():
    return load_experiment("08_bias_series")


def test_igor_rungo_list_matches_the_procedure(series):
    """Setup1_STMBJ.ipf:147-155, worked out from the Igor source by hand.

    bias = (p+1)*(-100) for p = 0..13, then five explicit overrides.
    """
    expected = [-(p + 1) * 100.0 for p in range(14)]
    expected[9] = -100.0
    expected[10] = -900.0
    expected[11] = -1000.0
    expected[12] = -1100.0
    expected[13] = -100.0
    assert series.IGOR_RUNGO_BIAS_MV == expected
    assert series.IGOR_RUNGO_TRACES_PER_BIAS == 1000


def test_the_control_repeats_are_present(series):
    """The whole point of Igor's list: -100 mV at steps 0, 9 and 13."""
    biases = series.IGOR_RUNGO_BIAS_MV
    assert [i for i, mv in enumerate(biases) if mv == -100.0] == [0, 9, 13]
    assert [i for i, mv in enumerate(biases) if mv == -900.0] == [8, 10]


def test_bias_limit_refuses_the_igor_series(series, cfg):
    """Igor reached 1100 mV; the default limit is 500 mV."""
    with pytest.raises(SafetyViolation) as exc:
        series.check_bias_limits(cfg, series.IGOR_RUNGO_BIAS_MV)
    message = str(exc.value)
    assert "--max-bias 1.10" in message      # tells you exactly what to pass
    assert "1100" in message


def test_bias_limit_allows_the_series_once_raised(series, cfg):
    cfg.limits.bias_max_v = 1.2
    series.check_bias_limits(cfg, series.IGOR_RUNGO_BIAS_MV)   # no raise


def test_bias_limit_checks_every_step_not_just_the_first(series, cfg):
    """A list that starts safe and ends over the limit must still refuse."""
    with pytest.raises(SafetyViolation):
        series.check_bias_limits(cfg, [-100.0, -200.0, -900.0])


def test_step_filenames_keep_repeated_biases_apart(series, tmp_path):
    """Steps 0 and 13 are both -100 mV. Colliding them would destroy the
    control comparison the series exists to make."""
    a = series.step_path(tmp_path, 0, -100.0)
    b = series.step_path(tmp_path, 13, -100.0)
    assert a != b
    assert a.name == "step_00_-100mV.h5"
    assert b.name == "step_13_-100mV.h5"


def test_plan_marks_missing_partial_and_complete_steps(series, tmp_path, cfg):
    import h5py
    biases = [-100.0, -200.0, -300.0]

    # step 0 complete, step 1 partial, step 2 absent
    for index, n in ((0, 10), (1, 4)):
        path = series.step_path(tmp_path, index, biases[index])
        with h5py.File(path, "w") as h5:
            h5.attrs["n_traces"] = n

    got = series.plan(tmp_path, biases, n_traces=10)
    assert [done for _, _, _, done in got] == [10, 4, 0]


def test_completed_traces_treats_a_corrupt_file_as_incomplete(series,
                                                              tmp_path):
    path = tmp_path / "step_00_-100mV.h5"
    path.write_bytes(b"not an hdf5 file at all")
    assert series.completed_traces(path) == 0


def test_series_run_end_to_end_and_resumes(series, cfg, tmp_path):
    cfg.limits.bias_max_v = 1.2
    biases = [-100.0, -500.0, -100.0]
    out = tmp_path / "series"

    rc = series.run(cfg, out, biases, n_traces=4, do_calibrate=False,
                    resume=False, dry_run=False)
    assert rc == 0
    files = sorted(p.name for p in out.glob("*.h5"))
    assert files == ["step_00_-100mV.h5", "step_01_-500mV.h5",
                     "step_02_-100mV.h5"]

    manifest = json.loads((out / "series_index.json").read_text())
    assert [s["bias_mv"] for s in manifest["steps"]] == biases
    assert all(s["traces"] == 4 for s in manifest["steps"])

    # Every file must carry the bias it was taken at, in its own config.
    for index, mv in enumerate(biases):
        with storage.Session(series.step_path(out, index, mv)) as s:
            assert s.cfg.ramp.bias_v == pytest.approx(mv / 1000.0)
            assert len(s) == 4

    # Resuming a complete series does nothing and says so.
    mtimes = {p.name: p.stat().st_mtime_ns for p in out.glob("*.h5")}
    assert series.run(cfg, out, biases, 4, do_calibrate=False, resume=True,
                      dry_run=False) == 0
    assert {p.name: p.stat().st_mtime_ns for p in out.glob("*.h5")} == mtimes


def test_dry_run_writes_nothing(series, cfg, tmp_path):
    cfg.limits.bias_max_v = 1.2
    out = tmp_path / "series"
    assert series.run(cfg, out, [-100.0, -900.0], 4, do_calibrate=False,
                      resume=False, dry_run=True) == 0
    assert not out.exists()


# --------------------------------------------------------------------------
# 06 echem
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def echem_exp():
    return load_experiment("06_echem_gate_cv")


def test_gate_left_standing_by_default(echem_exp, cfg):
    """No --hold: the channel is released still holding its value, which is
    what Igor's always-open task looked like to the operator."""
    assert echem_exp.cmd_gate(cfg, -250.0, None) == 0
    assert cfg.echem.gate_mv == -250.0


def test_gate_with_hold_returns_to_zero(echem_exp, cfg):
    assert echem_exp.cmd_gate(cfg, -250.0, 0.0) == 0


def test_simulated_electrode_off_accepts_the_zero_keyword(cfg):
    """The simulated subclass must match the base signature, or every
    rehearsal of the gate workflow dies where the real one would not."""
    ce = echem.make_counter_electrode(cfg)
    ce.on()
    ce.set_mv(-100.0)
    ce.off(zero=False)
    assert ce.gate_mv == -100.0
    ce.off(zero=True)
    assert ce.gate_mv == 0.0


def test_gated_traces_write_one_file_per_gate(echem_exp, cfg, tmp_path):
    gates = [-200.0, 0.0, 200.0]
    rc = echem_exp.cmd_traces(cfg, gates, n_traces=3, out_dir=tmp_path,
                              do_calibrate=False, settle_s=0.0)
    assert rc == 0
    assert sorted(p.name for p in tmp_path.glob("*.h5")) == [
        "gate_+0mV.h5", "gate_+200mV.h5", "gate_-200mV.h5"]

    # Each file must know its own gate -- Igor's ParameterWave[18].
    for mv in gates:
        with storage.Session(tmp_path / f"gate_{mv:+.0f}mV.h5") as s:
            assert s.cfg.echem.gate_mv == pytest.approx(mv)


def test_gate_returns_to_zero_after_a_trace_run(echem_exp, cfg, tmp_path):
    echem_exp.cmd_traces(cfg, [300.0], n_traces=2, out_dir=tmp_path,
                         do_calibrate=False, settle_s=0.0)
    assert cfg.echem.gate_mv == 0.0


# --------------------------------------------------------------------------
# CV storage
# --------------------------------------------------------------------------

def test_cv_roundtrip_preserves_volts_and_mask(cfg, tmp_path):
    cycles = echem.run_cv(cfg, kind="highres", cycles=2)
    path = storage.save_cv_cycles(tmp_path / "cv.h5", cfg, cycles, "highres")

    with storage.CVSession(path) as cv:
        assert len(cv) == 2
        assert cv.kind == "highres"
        assert cv.rate_hz == cfg.echem.cv_rate_hz
        np.testing.assert_allclose(cv.applied_v, cycles[0].applied_v)
        np.testing.assert_array_equal(cv.keep, cycles[0].keep)
        # Stored volts -> amps only on the way out, via the calibration.
        np.testing.assert_allclose(
            cv.current_a(0),
            cycles[0].tip_current_v / cfg.cal.preamp_gain_v_per_a)
        assert cv.we_voltage_mv(0) is not None


def test_cv_reader_rejects_a_trace_file(cfg, tmp_path):
    """A CV file and a trace file must not be silently interchangeable."""
    path = tmp_path / "traces.h5"
    with storage.SessionWriter(path, cfg):
        pass
    with pytest.raises(ValueError, match="not a CV file"):
        storage.CVSession(path)


def test_cv_reanalysis_with_a_revised_gain(cfg, tmp_path):
    """The same reason traces store volts: a re-measured preamp gain must
    reprocess the file, not invalidate it."""
    cycles = echem.run_cv(cfg, kind="highres", cycles=1)
    path = storage.save_cv_cycles(tmp_path / "cv.h5", cfg, cycles, "highres")

    with storage.CVSession(path) as cv:
        original = cv.current_a(0)                  # as stored
        cal = replace(cv.cfg.cal, preamp_gain_v_per_a=9.87e5)
        revised = cv.current_a(0, cal=cal)          # as re-measured
    np.testing.assert_allclose(revised / original, 1e6 / 9.87e5, rtol=1e-9)


def test_lowres_cv_has_no_electrode_voltage_channel(cfg, tmp_path):
    """Igor's low-res variant read tip current only."""
    cycles = echem.run_cv(cfg, kind="lowres", cycles=1)
    path = storage.save_cv_cycles(tmp_path / "cv.h5", cfg, cycles, "lowres")
    with storage.CVSession(path) as cv:
        assert cv.we_voltage_mv(0) is None
