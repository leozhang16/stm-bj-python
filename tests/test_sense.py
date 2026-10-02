"""The piezo sense readback (Igor's SenseIn / POExtension) on a two-card rig.

Two configs run through the same code: a one-card rig, where nothing about
the sense line may be visible, and a two-card rig on the simulator, where the
readback must be the right length, agree with the command, and survive a trip
through the data file.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from stmlab import storage, trace
from stmlab.config import RigConfig, validate
from stmlab.instrument import Rig
from stmlab.sim import SimulatedDaqSession


def _rig(two_cards: bool) -> tuple[RigConfig, Rig]:
    cfg = RigConfig()
    cfg.simulate = True
    cfg.ramp.traces_target = 3
    if two_cards:
        cfg.channels.low_res_device = "dev2"
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=11))
    rig.open()
    return cfg, rig


# --------------------------------------------------------------------------
# one card: the default, and nothing changes
# --------------------------------------------------------------------------

def test_one_card_rig_has_no_sense():
    cfg, rig = _rig(two_cards=False)
    try:
        assert not cfg.channels.has_piezo_sense
        assert cfg.channels.piezo_sense_path is None
        rig.hold(n_samples=200)
        assert rig.last_sense_v is None
        assert rig.sense_nm is None
        got = []
        trace.trace_loop(rig, n=1, on_trace=lambda i, tr, sel: got.append(tr))
        assert len(got) == 1
        assert got[0].piezo_sense_v is None
        assert got[0].piezo_sense_nm(cfg) is None
    finally:
        rig.close()


def test_one_card_file_has_no_sense_dataset(tmp_path):
    cfg, rig = _rig(two_cards=False)
    try:
        path = tmp_path / "one.h5"
        with storage.SessionWriter(path, cfg) as writer:
            trace.trace_loop(rig, n=2, on_trace=writer.append)
    finally:
        rig.close()
    with storage.Session(path) as session:
        assert not session.has_piezo_sense
        assert session.piezo_sense(0) is None


# --------------------------------------------------------------------------
# two cards: the readback rides along
# --------------------------------------------------------------------------

def test_two_card_config_names_the_channel():
    cfg = RigConfig()
    cfg.channels.low_res_device = "dev2"
    assert cfg.channels.has_piezo_sense
    assert cfg.channels.piezo_sense_path == "dev2/ai2"
    cfg.channels.ai_piezo_sense = None
    assert not cfg.channels.has_piezo_sense
    assert cfg.channels.piezo_sense_path is None


def test_two_card_config_round_trips_through_json():
    cfg = RigConfig()
    cfg.channels.low_res_device = "dev2"
    cfg.channels.ai_piezo_sense = "ai3"
    cfg.cal.sense_nm_per_volt = 300.0
    back = RigConfig.from_dict(json.loads(json.dumps(cfg.to_dict())))
    assert back.channels.piezo_sense_path == "dev2/ai3"
    assert back.cal.sense_nm_per_volt == 300.0
    assert "ROW_VOLTAGE" not in cfg.to_dict()["channels"]
    validate(back)


def test_validate_rejects_a_nonpositive_sense_scale():
    from stmlab.config import ConfigError
    cfg = RigConfig()
    cfg.channels.low_res_device = "dev2"
    cfg.cal.sense_nm_per_volt = 0.0
    with pytest.raises(ConfigError):
        validate(cfg)


def test_hold_carries_a_sense_record_of_the_same_length():
    cfg, rig = _rig(two_cards=True)
    try:
        record = rig.hold(n_samples=500)
        assert record.shape == (2, 500)          # the record is untouched
        assert rig.last_sense_v is not None
        assert rig.last_sense_v.shape == (500,)
        # The settled readback, in nm, is the commanded position.
        assert rig.sense_nm == pytest.approx(rig.piezo_nm, abs=0.5)
    finally:
        rig.close()


def test_trace_sense_matches_the_commanded_ramp():
    cfg, rig = _rig(two_cards=True)
    try:
        from stmlab import approach
        approach.engage(rig)
        tr = None
        for _ in range(5):
            tr = trace.single_trace(rig)
            if tr is not None:
                break
            approach.engage(rig)
        assert tr is not None
        assert tr.piezo_sense_v is not None
        assert tr.piezo_sense_v.shape == tr.voltage_v.shape

        sense_nm = tr.piezo_sense_nm(cfg)
        commanded_nm = (cfg.cal.piezo_volts_to_nm(tr.start_piezo_v)
                        - tr.displacement_nm(cfg))
        # Same cut as the two record rows, so sample for sample the readback
        # follows the descending command to within the sense line's noise.
        assert np.allclose(sense_nm, commanded_nm, atol=0.3)
        assert sense_nm[0] > sense_nm[-1]
    finally:
        rig.close()


def test_two_card_file_round_trips_the_sense(tmp_path):
    cfg, rig = _rig(two_cards=True)
    try:
        path = tmp_path / "two.h5"
        with storage.SessionWriter(path, cfg) as writer:
            stats = trace.trace_loop(rig, n=2, on_trace=writer.append)
    finally:
        rig.close()
    assert stats["accepted"] == 2
    with storage.Session(path) as session:
        assert session.has_piezo_sense
        nm = session.piezo_sense(0)
        volts = session.piezo_sense(0, in_nm=False)
        assert nm.shape == (cfg.ramp.n_pull_samples,)
        assert np.allclose(nm, volts * cfg.cal.sense_nm_per_volt)
        voltage, _ = session.raw(0)
        assert voltage.shape == nm.shape


def test_a_missing_readback_mid_session_is_stored_as_nan(tmp_path):
    cfg, rig = _rig(two_cards=True)
    try:
        path = tmp_path / "gap.h5"
        with storage.SessionWriter(path, cfg) as writer:
            trace.trace_loop(rig, n=1, on_trace=writer.append)
            tr = None
            while tr is None:
                from stmlab import approach
                approach.engage(rig)
                tr = trace.single_trace(rig)
            tr.piezo_sense_v = None           # a dropped read
            writer.append(1, tr, None)
    finally:
        rig.close()
    with storage.Session(path) as session:
        assert len(session) == 2
        assert np.isfinite(session.piezo_sense(0)).all()
        assert np.isnan(session.piezo_sense(1)).all()


def test_validate_rejects_an_unknown_sense_terminal():
    from stmlab.config import ConfigError
    cfg = RigConfig()
    cfg.channels.low_res_device = "dev2"
    cfg.channels.sense_terminal = "single"
    with pytest.raises(ConfigError):
        validate(cfg)
    for ok in ("default", "RSE", "nrse", "diff"):
        cfg.channels.sense_terminal = ok
        validate(cfg)


def test_sense_zero_is_removed_before_scaling():
    cfg = RigConfig()
    cfg.cal.sense_nm_per_volt = 1262.0
    cfg.cal.sense_zero_v = 0.85
    assert cfg.cal.sense_volts_to_nm(0.85) == pytest.approx(0.0)
    assert cfg.cal.sense_volts_to_nm(1.35) == pytest.approx(631.0)


def test_simulated_readback_with_an_offset_still_matches_the_command():
    cfg, rig = _rig(two_cards=True)
    cfg.cal.sense_nm_per_volt = 1262.0
    cfg.cal.sense_zero_v = 0.85
    try:
        record = rig.hold(piezo_v=5.0, n_samples=400)
        del record
        # raw volts carry the offset; the nm conversion removes it
        settled = rig.last_sense_v[-200:]      # the first samples are delayed
        assert settled.mean() == pytest.approx(0.85 + 5.0 * 62 / 1262, abs=0.01)
        assert rig.sense_nm == pytest.approx(rig.piezo_nm, abs=1.0)
    finally:
        rig.close()
