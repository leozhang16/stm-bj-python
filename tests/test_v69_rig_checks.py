"""v69: three things for bringing a new rig up.

1. The sign of each current channel (``cal.current_sign``,
   ``cal.current_sign_2``). An amplifier whose output is the other way
   round from the Keithley's gives a negative current at a positive bias:
   negative conductance, no logarithm, an empty trace panel. The sign is
   applied in the one place the current is computed, the window has a
   "flip the sign" box per channel, and a pull that reads negative says so.
2. The first two panels can be drawn differently: the record with |V| and
   |I| on logarithmic axes, the trace as G/G0 itself on a linear axis.
3. The Monitor window's sample-rate check (``stmlab.ratecheck``): one
   second on every input in use, counted through a scratch file that is
   written, read back and deleted, and timed against the PC's clock.

Simulator and a fake nidaqmx only: no card. None of these tests reads a
number out of configs/*.json.
"""
from __future__ import annotations

import sys
import time
import types
from pathlib import Path

import numpy as np
import pytest

from stmlab import analysis, approach, ratecheck, trace
from stmlab.config import ConfigError, RigConfig, validate
from stmlab.instrument import Rig
from stmlab.safety import RigState
from stmlab.sim import SimulatedDaqSession

ROOT = Path(__file__).resolve().parents[1]


def _sim(two: bool = False) -> RigConfig:
    cfg = RigConfig()
    cfg.simulate = True
    if two:
        cfg.channels.ai_current_2 = "ai4"
        cfg.channels.current_channels = 2
    return cfg


def _one_pull(cfg: RigConfig, seed: int = 3):
    """One engage and one pull on the simulated card: (trace, state)."""
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=seed))
    rig.open()
    try:
        state = approach.engage(rig)
        return trace.single_trace(rig, index=0), state
    finally:
        rig.close()


# --------------------------------------------------------------------------
# 1. The sign of the current
# --------------------------------------------------------------------------

def test_the_sign_is_applied_where_the_current_is_computed():
    cal = RigConfig().cal
    cal.preamp_gain_v_per_a, cal.current_zero_v = 1e6, 0.002
    cal.preamp_gain_2_v_per_a, cal.current_zero_2_v = 1e9, -0.004
    v = np.array([-3.0, 0.0, 0.5, 9.9])
    # as it always was: exactly (v - zero) / gain, bit for bit
    assert cal.current_sign == 1.0 and cal.current_sign_2 == 1.0
    assert np.array_equal(cal.volts_to_amps(v), (v - 0.002) / 1e6)
    assert np.array_equal(cal.volts_to_amps(v, channel=2), (v + 0.004) / 1e9)
    # flipped: the same numbers with the other sign, each channel on its own
    cal.current_sign = -1.0
    assert np.array_equal(cal.volts_to_amps(v), -((v - 0.002) / 1e6))
    assert np.array_equal(cal.volts_to_amps(v, channel=2), (v + 0.004) / 1e9)
    cal.current_sign_2 = -1.0
    assert np.array_equal(cal.volts_to_amps(v, channel=2), -((v + 0.004) / 1e9))
    assert cal.sign_of(1) == -1.0 and cal.sign_of(2) == -1.0
    # and back again: amps_to_volts undoes volts_to_amps, zero and sign included
    for channel in (1, 2):
        assert np.allclose(cal.amps_to_volts(cal.volts_to_amps(v, channel), channel), v,
                           rtol=0, atol=1e-12)
    # the conductance follows
    assert cal.volts_to_g0(-0.5, 0.1) > 0


def test_the_validator_takes_plus_or_minus_one_and_nothing_else():
    for bad in (0, 2, -0.5, float("nan")):
        cfg = _sim()
        cfg.cal.current_sign = bad
        with pytest.raises(ConfigError, match="current_sign must be 1 or -1"):
            validate(cfg)
    cfg = _sim(two=True)
    cfg.cal.current_sign_2 = 0
    with pytest.raises(ConfigError, match="current_sign_2 must be 1 or -1"):
        validate(cfg)
    cfg = _sim()
    cfg.cal.current_sign = -1
    validate(cfg)                                    # no error


def test_the_sign_travels_in_the_json_and_old_files_load_without_it(tmp_path):
    cfg = _sim(two=True)
    cfg.cal.current_sign = -1.0
    path = tmp_path / "rig.json"
    cfg.to_json(path)
    back = RigConfig.from_json(path)
    assert back.cal.current_sign == -1.0 and back.cal.current_sign_2 == 1.0
    blob = cfg.to_dict()
    del blob["cal"]["current_sign"], blob["cal"]["current_sign_2"]
    old = RigConfig.from_dict(blob)                  # a file written before v69
    assert old.cal.current_sign == 1.0 and old.cal.current_sign_2 == 1.0


def test_an_amplifier_the_other_way_round_reads_negative_until_it_is_flipped():
    # the reference: the simulated amplifier as it always was
    tr, _ = _one_pull(_sim(two=True))
    ref = tr.conductance_g0(_sim(two=True))
    ref2 = tr.conductance_g0(_sim(two=True), channel=2)
    assert not analysis.reads_negative(ref) and not analysis.reads_negative(ref2)

    # the new amplifier: its outputs go negative at a positive bias
    cfg = _sim(two=True)
    cfg.sim.amplifier_output_sign = cfg.sim.amplifier_output_sign_2 = -1.0
    tr, state = _one_pull(cfg)
    # contact was still found: it is judged on the size of the current
    assert state is RigState.ENGAGED
    wrong = tr.conductance_g0(cfg)
    assert analysis.reads_negative(wrong)
    assert analysis.reads_negative(tr.conductance_g0(cfg, channel=2))
    assert np.nanmax(wrong[:200]) < 0                # in contact: all negative
    assert not analysis.select_trace(wrong, cfg.ramp).accepted

    # flip both channels: the reference run again. (The junction and the
    # card's noise are the same samples; only the noise now enters with the
    # other sign, so the two agree to the noise and not to the last bit.)
    cfg.cal.current_sign = cfg.cal.current_sign_2 = -1.0
    right, right2 = tr.conductance_g0(cfg), tr.conductance_g0(cfg, channel=2)
    assert np.array_equal(right, -wrong)             # the flip is exact
    assert not analysis.reads_negative(right) and not analysis.reads_negative(right2)
    contact = ref > 0.5
    assert contact.sum() > 500
    assert np.allclose(right[contact], ref[contact], rtol=1e-3)
    assert np.allclose(right2[contact], ref2[contact], rtol=1e-3)
    assert analysis.select_trace(right, cfg.ramp).accepted == \
        analysis.select_trace(ref, cfg.ramp).accepted


def test_reads_negative_looks_at_the_conducting_part_only():
    rng = np.random.default_rng(0)
    noise = rng.normal(0.0, 1e-5, 20_000)            # an open junction: half negative
    assert not analysis.reads_negative(noise)
    pull = np.concatenate([np.full(1500, 3.0), np.full(500, 1.0), noise])
    assert not analysis.reads_negative(pull)
    assert analysis.reads_negative(-pull)
    # a contact that breaks at once: 40 samples are enough, 10 are not
    assert analysis.reads_negative(np.concatenate([np.full(40, -2.0), noise]))
    assert not analysis.reads_negative(np.concatenate([np.full(10, -2.0), noise]))
    # a tip that never lets go: negative all the way
    assert analysis.reads_negative(np.full(5000, -4.0) + rng.normal(0, 0.05, 5000))
    assert not analysis.reads_negative(np.full(5000, 4.0))
    # a molecular plateau standing clear of the noise counts as conducting
    plateau = np.concatenate([np.full(300, -1e-3), noise])
    assert analysis.reads_negative(plateau) and not analysis.reads_negative(-plateau)
    assert not analysis.reads_negative(np.full(5000, np.nan))
    assert not analysis.reads_negative(np.zeros(5000))
    assert not analysis.reads_negative([])


def test_a_pull_that_never_touched_says_nothing_about_the_sign():
    """An open junction whose zero is a little off reads slightly negative
    all the way. That is an offset, not a wrong sign: no flag, whatever the
    offset is in units of the noise."""
    rng = np.random.default_rng(1)
    for sigma in (1e-6, 1e-5, 1e-3):
        for offset in (-0.3, -0.5, -1.0, -3.0, -10.0, -50.0):
            for _ in range(20):
                open_junction = rng.normal(offset * sigma, sigma, 10_000)
                assert not analysis.reads_negative(open_junction), (sigma, offset)


def test_the_saved_current_has_the_flipped_sign(tmp_path):
    from stmlab import igor_scheme
    cfg = _sim()
    cfg.sim.amplifier_output_sign = -1.0
    cfg.cal.current_sign = -1.0
    tr, _ = _one_pull(cfg)
    it = igor_scheme.IgorTrace.from_record(tr, cfg)
    start = slice(0, 200)                            # in contact
    assert np.all(it.current_a[start] > 0) and np.all(it.g0[start] > 0)


# --------------------------------------------------------------------------
# The worker and the window's box
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


def _status(worker) -> dict:
    return _events(worker, "status")[-1]


def test_the_worker_flips_a_channel_and_says_how_to_keep_it(ap, tmp_path):
    cfg = _sim(two=True)
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_amplifier()
        state = _events(worker, "amplifier")[-1]
        assert state["sign1"] == 1.0 and state["sign2"] == 1.0
        worker.cmd_current_sign(1, -1.0)
        assert cfg.cal.current_sign == -1.0 and cfg.cal.current_sign_2 == 1.0
        assert _events(worker, "amplifier")[-1]["sign1"] == -1.0
        text = _status(worker)["text"]
        assert "ch 1: sign flipped" in text and '"current_sign": -1' in text
        assert len(text) < 200                       # the Status box shows three lines
        worker.cmd_current_sign(2, -1.0)
        assert cfg.cal.current_sign_2 == -1.0
        assert '"current_sign_2": -1' in _status(worker)["text"]
        worker.cmd_current_sign(1, 1.0)
        assert cfg.cal.current_sign == 1.0
        assert "as the amplifier gives it" in _status(worker)["text"]
        # asking for what it already is changes nothing and says nothing new
        n = len(_events(worker, "status"))
        worker.cmd_current_sign(1, 1.0)
        assert len(_events(worker, "status")) == n
        # the readouts follow: with the sign flipped a positive output is a negative current
        worker.cmd_current_sign(1, -1.0)
        assert cfg.cal.volts_to_amps(1.0) < 0
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_run_with_the_wrong_sign_stops_itself_and_says_why(ap, tmp_path):
    cfg = _sim(two=True)
    cfg.sim.amplifier_output_sign = cfg.sim.amplifier_output_sign_2 = -1.0
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_zero()
        worker.cmd_run(5)
        # three pulls, all negative, and the run gave up: not five accepted, not for ever
        assert worker.attempts == ap.Worker.SIGN_STOP == 3 and worker.accepted == 0
        last = _status(worker)
        assert last["level"] == "bad" and last["text"].startswith("RUN STOPPED")
        assert 'flip the sign of ch 1' in last["text"] and len(last["text"]) < 200
        per_trace = [p["text"] for p in _events(worker, "status")
                     if p["text"].startswith("CH 1 CURRENT HAS THE WRONG SIGN")]
        assert len(per_trace) == 3
        assert worker.paused is not None             # nothing is lost: it is a pause

        # flip channel 1 as the box does, start again: traces are accepted
        worker.cmd_current_sign(1, -1.0)
        worker.cmd_run(2)
        assert worker.accepted == 2
        # channel 2 alone still the wrong way round: said in orange, ends nothing
        notes = [p for p in _events(worker, "status")
                 if p["text"].startswith("ch 2 reads a NEGATIVE conductance")]
        assert notes and all(p["level"] == "warn" for p in notes)
        worker.cmd_current_sign(2, -1.0)
        before = len(_events(worker, "status"))
        worker.cmd_run(1)
        new = _events(worker, "status")[before:]
        assert not [p for p in new if "NEGATIVE" in p["text"]]
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_which_of_the_two_has_the_wrong_sign_is_read_off_the_voltage(ap, tmp_path):
    cfg = _sim(two=True)
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        rng = np.random.default_rng(0)
        noise = rng.normal(0.0, 1e-5, 8000)
        g_neg = np.concatenate([np.full(2000, -3.0), noise])
        raw_v = np.full(10_000, -0.09)               # raw: the sign setting makes it +90 mV
        # the junction voltage has the sign of the bias: the current is the odd one
        note, level, negative = worker.sign_words(g_neg, None, raw_v)
        assert note.startswith("CH 1 CURRENT HAS THE WRONG SIGN") and level == "bad" and negative
        assert worker.sign_cure.startswith('Tick "flip the sign of ch 1"')
        cfg.cal.current_sign = -1.0                  # the box is ticked, and that is the wrong way
        note, _, _ = worker.sign_words(g_neg, None, raw_v)
        assert 'untick "flip the sign of ch 1"' in note
        assert worker.sign_cure.startswith('Untick "flip the sign of ch 1"')
        cfg.cal.current_sign = 1.0
        # the junction voltage reads against the bias: it is the odd one, and no box cures it
        note, level, negative = worker.sign_words(g_neg, None, -raw_v)
        assert note.startswith("THE JUNCTION VOLTAGE HAS THE WRONG SIGN") and negative
        assert "voltage_input_sign" in worker.sign_cure and "flip" not in worker.sign_cure
        # channel 2 alone: orange, and it does not count
        note, level, negative = worker.sign_words(-g_neg, g_neg, raw_v)
        assert note.startswith("ch 2 reads a NEGATIVE conductance") and level == "warn"
        assert not negative
        # nothing wrong, and a pull that never touched: no note
        assert worker.sign_words(-g_neg, -g_neg, raw_v) == ("", None, False)
        assert worker.sign_words(noise - 5e-6, None, raw_v) == ("", None, False)
        for text in (worker.sign_words(g_neg, None, raw_v)[0],
                     worker.sign_words(g_neg, None, -raw_v)[0]):
            assert len(text) < 150                   # room left for the trace's own line
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_the_simulated_amplifier_is_the_way_round_the_config_says():
    """A rig's config with current_sign -1 must simulate as that rig behaves:
    positive currents. The simulated amplifier takes its polarity from the
    config when it is made; un-ticking the box afterwards shows a wrong sign."""
    cfg = _sim(two=True)
    assert cfg.sim.amplifier_output_sign is None and cfg.sim.amplifier_output_sign_2 is None
    cfg.cal.current_sign = cfg.cal.current_sign_2 = -1.0
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=3))
    assert rig._session.amplifier_output_sign == -1.0
    assert rig._session.amplifier_output_sign_2 == -1.0
    rig.open()
    try:
        approach.engage(rig)
        tr = trace.single_trace(rig, index=0)
    finally:
        rig.close()
    assert not analysis.reads_negative(tr.conductance_g0(cfg))
    assert not analysis.reads_negative(tr.conductance_g0(cfg, channel=2))
    cfg.cal.current_sign = 1.0                       # the box unticked, mid-session
    assert analysis.reads_negative(tr.conductance_g0(cfg))
    # said outright, the config's word decides
    cfg = _sim()
    cfg.cal.current_sign = -1.0
    cfg.sim.amplifier_output_sign = 1.0
    assert SimulatedDaqSession(cfg).amplifier_output_sign == 1.0
    # and it is a setting like any other
    blob = cfg.to_dict()
    assert blob["sim"]["amplifier_output_sign"] == 1.0
    assert blob["sim"]["amplifier_output_sign_2"] is None


def test_a_run_with_the_right_sign_is_not_stopped(ap, tmp_path):
    cfg = _sim()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_zero()
        worker.cmd_run(4)
        assert worker.accepted == 4 and worker.negative_in_a_row == 0
        assert not [p for p in _events(worker, "status") if "NEGATIVE" in p["text"]]
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


# --------------------------------------------------------------------------
# 2. The two plot check boxes
# --------------------------------------------------------------------------

def _axes():
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    return Figure(figsize=(6, 4)).add_subplot(111)


def test_the_record_panel_on_logarithmic_axes():
    from stmlab import plots
    cfg = _sim()
    t = np.linspace(0.0, 1.0, 500)
    voltage_v = np.full(500, -0.09)                  # raw: the sign setting makes it +90 mV
    current_v = np.concatenate([np.full(250, 0.9), np.full(250, 1e-4)])
    ax = _axes()
    plots.plot_record_series(ax, cfg, t, voltage_v, current_v)
    twin = ax._stm_twin
    assert ax.get_yscale() == "linear" and twin.get_yscale() == "linear"
    assert ax.get_ylabel() == "junction (mV)" and twin.get_ylabel() == "current (uA)"

    plots.plot_record_series(ax, cfg, t, voltage_v, current_v, log=True)
    assert ax.get_yscale() == "log" and twin.get_yscale() == "log"
    assert ax.get_ylabel() == "|junction| (mV), log"
    assert twin.get_ylabel() == "|current| (uA), log"
    assert np.allclose(ax.lines[0].get_ydata(), 90.0)
    assert np.allclose(twin.lines[0].get_ydata()[:250], 0.9)

    # a negative current is drawn by its size, and the label says it is negative
    plots.plot_record_series(ax, cfg, t, voltage_v, -current_v, log=True)
    assert twin.get_ylabel() == "|current| (uA), log, NEGATIVE"
    assert np.all(twin.lines[0].get_ydata() > 0)

    # all zeros have no logarithm: no error, the axis stays linear
    plots.plot_record_series(ax, cfg, t, voltage_v, np.zeros(500), log=True)
    assert twin.get_yscale() == "linear"
    # and back to linear axes with the box unticked
    plots.plot_record_series(ax, cfg, t, voltage_v, current_v)
    assert ax.get_yscale() == "linear" and twin.get_yscale() == "linear"
    # plot_record passes it on
    plots.plot_record(ax, cfg, np.stack([voltage_v, current_v]), 40000.0, log=True)
    assert ax.get_yscale() == "log"


def test_the_trace_panel_as_linear_conductance():
    from stmlab import plots
    cfg = _sim(two=True)
    tr, _ = _one_pull(cfg)
    g0, g0_2 = tr.conductance_g0(cfg), tr.conductance_g0(cfg, channel=2)
    disp = tr.displacement_nm(cfg)
    sel = analysis.select_trace(g0, cfg.ramp)

    ax = _axes()
    plots.plot_trace(ax, cfg, g0, disp, sel)         # the default: Igor's log picture
    line = next(ln for ln in ax.lines if len(ln.get_xdata()) == disp.size)
    with np.errstate(divide="ignore", invalid="ignore"):
        assert np.array_equal(line.get_ydata(), np.log10(np.clip(g0, 1e-12, None)))
    assert ax.get_ylabel() == "log10 (G / G0)" and ax.get_ylim() == (-7.5, 1.0)

    plots.plot_trace(ax, cfg, g0, disp, sel, linear=True)
    line = next(ln for ln in ax.lines if len(ln.get_xdata()) == disp.size)
    assert np.array_equal(line.get_ydata(), g0)      # G itself, nothing done to it
    assert ax.get_ylabel() == "G / G0 (linear)"
    lo, hi = ax.get_ylim()
    assert lo < 0 < 1.2 < hi                         # 0 and the gold step are in view
    flat = sorted(round(float(ln.get_ydata()[0]), 6) for ln in ax.lines
                  if len(ln.get_xdata()) == 2)
    assert flat == sorted([0.0, round(cfg.ramp.break_g0, 6), 1.0])   # 0, break, 1 G0

    # two channels, linear: both as measured
    plots.plot_trace(ax, cfg, g0, disp, sel, g0_2=g0_2, linear=True)
    data = [ln for ln in ax.lines if len(ln.get_xdata()) == disp.size]
    assert [ln.get_color() for ln in data] == [plots.C_CH1, plots.C_CH2]
    assert np.array_equal(data[1].get_ydata(), g0_2)


def test_a_negative_trace_says_so_instead_of_an_empty_panel():
    from stmlab import plots
    cfg = _sim(two=True)
    cfg.sim.amplifier_output_sign = cfg.sim.amplifier_output_sign_2 = -1.0
    tr, _ = _one_pull(cfg)
    g0, g0_2 = tr.conductance_g0(cfg), tr.conductance_g0(cfg, channel=2)
    disp = tr.displacement_nm(cfg)

    ax = _axes()
    plots.plot_trace(ax, cfg, g0, disp)              # log: a note in the panel
    assert "[ch 1 NEGATIVE]" in ax.get_title()
    note = " ".join(t.get_text() for t in ax.texts)
    assert "NEGATIVE" in note and "flip the sign" in note and "linear G" in note

    plots.plot_trace(ax, cfg, g0, disp, g0_2=g0_2)   # both channels named
    assert "[ch 1 and ch 2 NEGATIVE]" in ax.get_title()

    plots.plot_trace(ax, cfg, g0, disp, saved=True)  # a trace from a file: no box to tick
    note = " ".join(t.get_text() for t in ax.texts)
    assert "saved data" in note and "flip the sign" not in note and "linear G" in note

    plots.plot_trace(ax, cfg, g0, disp, linear=True) # linear: the trace itself, no note
    assert "[ch 1 NEGATIVE]" in ax.get_title() and not ax.texts
    line = next(ln for ln in ax.lines if len(ln.get_xdata()) == disp.size)
    assert np.nanmin(line.get_ydata()) < -1 and ax.get_ylim()[0] < -1

    cfg.cal.current_sign = -1.0                       # flipped: an ordinary trace again
    plots.plot_trace(ax, cfg, tr.conductance_g0(cfg), disp)
    assert "NEGATIVE" not in ax.get_title() and not ax.texts


# --------------------------------------------------------------------------
# 3. The sample-rate check
# --------------------------------------------------------------------------

def test_counting_through_a_scratch_file(tmp_path):
    a = np.arange(1000, dtype=float)
    b = np.linspace(-1.0, 1.0, 1000)
    got = ratecheck.count_through_file([a, b], folder=tmp_path)
    assert got["counts"] == [1000, 1000] and got["numbers"] == 2000
    assert got["bytes"] == 16000 and got["identical"] and got["deleted"]
    assert got["file"].startswith("stm_ratecheck_") and list(tmp_path.iterdir()) == []
    # inputs of different lengths are counted each on its own
    got = ratecheck.count_through_file([a, b[:10], np.empty(0)], folder=tmp_path)
    assert got["counts"] == [1000, 10, 0] and got["identical"]
    # NaN survives the round trip and still counts
    c = a.copy()
    c[3] = np.nan
    assert ratecheck.count_through_file([c], folder=tmp_path)["identical"]
    # the default folder is the system's scratch folder, and nothing is left there either
    import tempfile
    before = set(Path(tempfile.gettempdir()).glob("stm_ratecheck_*"))
    assert ratecheck.count_through_file([a])["deleted"]
    assert set(Path(tempfile.gettempdir()).glob("stm_ratecheck_*")) == before


def test_the_check_on_the_simulated_rig_counts_every_input_in_use(tmp_path):
    cfg = _sim(two=True)
    cfg.channels.sense_device, cfg.channels.ai_piezo_sense = cfg.channels.device, "ai3"
    assert [what for _, what in ratecheck.inputs_in_use(cfg)] == \
        ["junction voltage", "current ch 1", "current ch 2", "piezo sense"]
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=1))
    rig.open()
    try:
        rig.hold(piezo_v=1.25)
        state, piezo, bias = rig.state, rig.piezo_v, rig.bias_v
        got = ratecheck.measure(rig, 1.0, folder=tmp_path)
        # nothing moved, and nothing was left behind
        assert (rig.state, rig.piezo_v, rig.bias_v) == (state, piezo, bias)
        assert list(tmp_path.iterdir()) == []
        fs = cfg.ramp.sample_rate_hz
        assert got["asked"] == int(fs) and got["card_rate_hz"] == fs
        assert [i["samples"] for i in got["inputs"]] == [int(fs)] * 4
        assert got["inputs"][0]["channel"] == "Dev1/ai0"
        assert got["numbers"] == 4 * int(fs) and got["identical"] and got["deleted"]
        assert got["record"].shape == (2, int(fs))
        # the simulated card takes no real time: a count, no stopwatch
        assert got["simulated"] and got["play_seconds"] is None
        assert got["stopwatch_ok"] is None and got["extra_seconds"] is None
        assert got["count_rate_hz"] == fs and got["record_seconds"] == 1.0
        assert got["ok"]
        # nothing was kept either: no folder was named for the csv
        assert got["csv"] is None and got["csv_error"] is None
        head, text = ratecheck.lines(got)
        # the headline is the rate as counted
        assert head == f"{int(fs)} samples/s: {int(fs)} samples in 1 s on each of 4 inputs"
        assert not any("Excel" in line for line in text)
        assert any("read back identical, deleted" in line for line in text)
        assert any("simulated card" in line for line in text)
        # one channel, no sense line: two inputs
        cfg1 = _sim()
        rig1 = Rig(cfg1, session=SimulatedDaqSession(cfg1, seed=1))
        rig1.open()
        try:
            got1 = ratecheck.measure(rig1, 0.25, folder=tmp_path)
        finally:
            rig1.close()
        assert [i["what"] for i in got1["inputs"]] == ["junction voltage", "current ch 1"]
        assert got1["asked"] == int(0.25 * fs) and got1["ok"]
    finally:
        rig.close()


class _Clocked(SimulatedDaqSession):
    """The simulated card with a clock: it says how long each play took, as
    the real driver does -- n samples at ``true_rate`` plus ``overhead``
    seconds of starting and stopping -- and when the inputs were all read,
    ``read_lag`` seconds later."""
    true_rate = 40000.0
    overhead = 0.0031
    read_lag = 0.004

    def play(self, waveform, timeout_s: float = 10.0):
        record = super().play(waveform, timeout_s)
        self.last_play_seconds = np.asarray(waveform).shape[1] / self.true_rate \
            + self.overhead
        self.last_read_seconds = self.last_play_seconds + self.read_lag
        return record


def test_the_rate_by_the_pc_clock_and_a_card_at_half_the_rate(tmp_path):
    cfg = _sim()
    rig = Rig(cfg, session=_Clocked(cfg, seed=1))
    rig.open()
    try:
        got = ratecheck.measure(rig, 1.0, folder=tmp_path)
        # go to done, less the samples' own time, is the starting and stopping
        assert got["play_seconds"] == pytest.approx(1.0031, abs=1e-9)
        assert got["ref_samples"] == 400 and got["ref_seconds"] == pytest.approx(0.0131, abs=1e-9)
        assert got["extra_seconds"] == pytest.approx(0.0031, abs=1e-9)
        assert got["ref_extra_seconds"] == pytest.approx(0.0031, abs=1e-9)
        assert got["stopwatch_ok"] and got["ok"]
        head, text = ratecheck.lines(got)
        # the headline is the rate as counted, never the stopwatch
        assert head == "40000 samples/s: 40000 samples in 1 s on each of 2 inputs"
        assert any("PC stopwatch" in line and "1.0031 s from go to done" in line
                   for line in text)
        assert any("the 3.1 ms on top are the PC starting and stopping the card" in line
                   for line in text)
        assert got["input_lag_seconds"] == pytest.approx(0.004, abs=1e-9)
        assert not got["inputs_late"]
        assert any("read 4 ms after the outputs finished" in line for line in text)

        rig._session.true_rate = 20000.0             # a card that samples at half the rate
        got = ratecheck.measure(rig, 1.0, folder=tmp_path)
        assert [i["samples"] for i in got["inputs"]] == [40000, 40000]   # the count is right
        assert got["extra_seconds"] == pytest.approx(1.0031, abs=1e-9)   # the time is not
        assert got["stopwatch_ok"] is False and not got["ok"]
        head, text = ratecheck.lines(got)
        assert head == "40000 samples, but they took 2.00 s, not 1 s"
        assert any("FAR TOO MUCH OFF" in line for line in text)

        # outputs at the right rate, but the inputs come in a second late:
        # they sample slower than the outputs
        rig._session.true_rate = 40000.0
        rig._session.read_lag = 1.0
        got = ratecheck.measure(rig, 1.0, folder=tmp_path)
        assert got["stopwatch_ok"]
        assert got["inputs_late"] and not got["ok"]
        assert any("FAR TOO LATE" in line for line in ratecheck.lines(got)[1])
    finally:
        rig.close()


class _LikeTheRig(_Clocked):
    """What the USB card on the new rig did on 2026-11-17: exact at 40000,
    10.1 ms of starting and stopping on the 10 ms record, 17.6 ms on the
    one-second record (a long record has more to send to the card)."""

    def play(self, waveform, timeout_s: float = 10.0):
        self.overhead = 0.0176 if np.asarray(waveform).shape[1] > 8000 else 0.0101
        return super().play(waveform, timeout_s)


def test_the_real_rigs_numbers_read_40000_and_never_39698(tmp_path):
    """v69 showed "39698 samples/s" for these very numbers: it took the
    short record's start-and-stop time off the long one's and called the
    rest sampling time. The card was at 40000 all along."""
    cfg = _sim(two=True)
    cfg.channels.sense_device, cfg.channels.ai_piezo_sense = cfg.channels.device, "ai3"
    rig = Rig(cfg, session=_LikeTheRig(cfg, seed=1))
    rig.open()
    try:
        got = ratecheck.measure(rig, 1.0, folder=tmp_path)
        assert got["play_seconds"] == pytest.approx(1.0176, abs=1e-9)
        assert got["count_rate_hz"] == 40000.0
        assert got["stopwatch_ok"] and got["ok"]
        head, text = ratecheck.lines(got)
        assert head == "40000 samples/s: 40000 samples in 1 s on each of 4 inputs"
        assert any("the 17.6 ms on top are the PC starting and stopping the card "
                   "(10.1 ms on the 400-sample record before it)" in line for line in text)
        assert "39698" not in head and not any("39698" in line for line in text)
        assert "pc_rate_hz" not in got
    finally:
        rig.close()


def test_the_last_second_is_kept_as_a_csv_for_excel(tmp_path):
    cfg = _sim(two=True)
    cfg.channels.sense_device, cfg.channels.ai_piezo_sense = cfg.channels.device, "ai3"
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=1))
    rig.open()
    try:
        data = tmp_path / "data"                      # not there yet: it is made
        got = ratecheck.measure(rig, 1.0, folder=tmp_path, keep=data)
        kept = data / "sampling_rate_test.csv"
        assert got["csv"] == str(kept) and got["csv_rows"] == 40000 and got["ok"]
        assert sorted(p.name for p in data.iterdir()) == ["sampling_rate_test.csv"]
        rows = kept.read_text().splitlines()
        assert len(rows) == 40001                     # one header row, 40000 samples
        assert rows[0] == ("sample,time_s,Dev1/ai0 junction voltage (V),"
                           "Dev1/ai1 current ch 1 (V),Dev1/ai4 current ch 2 (V),"
                           "Dev1/ai3 piezo sense (V)")
        assert rows[1].startswith("1,0.0000000,") and rows[-1].startswith("40000,0.9999750,")
        table = np.loadtxt(kept, delimiter=",", skiprows=1)
        assert table.shape == (40000, 6)
        M = cfg.channels
        assert np.allclose(table[:, 2], got["record"][M.ROW_VOLTAGE], atol=1e-7)
        assert np.allclose(table[:, 3], got["record"][M.ROW_CURRENT], atol=1e-7)
        assert np.allclose(table[:, 4], rig.last_current2_v, atol=1e-7)
        assert np.allclose(table[:, 5], rig.last_sense_v, atol=1e-7)
        head, text = ratecheck.lines(got)
        assert any(line == f"kept for Excel: {kept}" for line in text)
        assert any("40000 rows under the header" in line for line in text)

        # the next check writes the file afresh: still one file, the new numbers
        again = ratecheck.measure(rig, 0.25, folder=tmp_path, keep=data)
        assert again["csv_rows"] == 10000
        assert len(kept.read_text().splitlines()) == 10001
        assert sorted(p.name for p in data.iterdir()) == ["sampling_rate_test.csv"]

        # a folder that cannot be made does not fail the check; the lines say so
        (tmp_path / "a_file").write_text("x")
        bad = ratecheck.measure(rig, 0.25, folder=tmp_path, keep=tmp_path / "a_file" / "data")
        assert bad["ok"] and bad["csv"] is None and "sampling_rate_test.csv" in bad["csv_error"]
        assert any(line.startswith("NOT kept for Excel:") for line in ratecheck.lines(bad)[1])
    finally:
        rig.close()


def test_a_short_count_fails_the_check(tmp_path, monkeypatch):
    cfg = _sim(two=True)
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=1))
    rig.open()
    try:
        hold = rig.hold

        def short(**kw):                              # channel 2 comes back short
            record = hold(**kw)
            rig.last_current2_v = rig.last_current2_v[:-7]
            return record
        monkeypatch.setattr(rig, "hold", short)
        got = ratecheck.measure(rig, 0.1, folder=tmp_path)
        assert [i["samples"] for i in got["inputs"]] == [4000, 4000, 3993]
        assert not got["ok"]
        head, text = ratecheck.lines(got)
        assert "3993/4000" in head and any("NOT what was asked" in line for line in text)
    finally:
        rig.close()


def test_the_real_driver_times_every_play(monkeypatch):
    """DaqSession on a fake nidaqmx whose card takes real time: the play is
    timed from start to done, and the check turns that into a rate."""
    sys.path.insert(0, str(ROOT / "tests"))
    from test_daq_onecard import FakeTask
    FakeTask.made = []
    mod = types.ModuleType("nidaqmx")
    mod.Task = FakeTask
    consts = types.ModuleType("nidaqmx.constants")
    for name in ("AOIdleOutputBehavior", "AcquisitionType", "TaskMode"):
        setattr(consts, name, types.SimpleNamespace(
            MAINTAIN_EXISTING_VALUE=1, FINITE=1, TASK_COMMIT=1))
    consts.TerminalConfiguration = types.SimpleNamespace(DEFAULT=0, RSE=1, NRSE=2, DIFF=3)
    mod.constants = consts
    monkeypatch.setitem(sys.modules, "nidaqmx", mod)
    monkeypatch.setitem(sys.modules, "nidaqmx.constants", consts)

    def takes_time(self, timeout=0):                 # the card: n samples at 40 kHz
        if self.written is not None:
            time.sleep(self.written.shape[1] / 40000.0)
    monkeypatch.setattr(FakeTask, "wait_until_done", takes_time)

    from stmlab.daq import DaqSession
    cfg = _sim()
    cfg.simulate = False
    with DaqSession(cfg) as session:
        assert session.last_play_seconds is None
        session.play(np.zeros((2, 4000)))            # 0.1 s
        assert 0.1 <= session.last_play_seconds < 0.2
        assert session.last_play_seconds <= session.last_read_seconds < 0.25
        rig = Rig(cfg, session=session)
        rig._piezo_v = 0.0
        got = ratecheck.measure(rig, 0.5)
        assert got["asked"] == 20000 and not got["simulated"]
        assert got["play_seconds"] >= 0.5
        assert got["count_rate_hz"] == 40000.0
        assert 0.0 <= got["extra_seconds"] < 0.03 and got["stopwatch_ok"] and got["ok"]
        assert got["input_lag_seconds"] < 0.05 and not got["inputs_late"]


def test_the_worker_runs_the_check_quietly_and_feeds_the_readouts(ap, tmp_path):
    cfg = _sim(two=True)
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        rig.hold(piezo_v=0.5)
        cycle_points = len(worker.mon.snapshot().t)
        worker.cmd_ratecheck(0.25)
        got = _events(worker, "ratecheck")[-1]
        assert got["ok"] and "record" not in got
        assert [i["samples"] for i in got["inputs"]] == [10000, 10000, 10000]
        # the record of the check stays in the data folder, for Excel
        kept = tmp_path / "sampling_rate_test.csv"
        assert got["csv"] == str(kept) and got["csv_rows"] == 10000
        assert len(kept.read_text().splitlines()) == 10001
        # kept out of the cycle log, like the idle sampling
        assert len(worker.mon.snapshot().t) == cycle_points and not worker.mon.quiet
        # and its last samples are a monitor sample for the readouts
        sample = _events(worker, "monitor")[-1]
        assert sample["record"].shape == (2, 400) and sample["ch2"] is not None
        assert rig.piezo_v == 0.5

        def broken(*a, **kw):
            raise RuntimeError("the card timed out\nsecond line")
        import stmlab.ratecheck as rc
        real = rc.measure
        rc.measure = broken
        try:
            worker.cmd_ratecheck()
        finally:
            rc.measure = real
        failed = _events(worker, "ratecheck")[-1]
        assert failed == {"error": "RuntimeError: the card timed out"}
        assert ratecheck.lines(failed) == ("CHECK FAILED", ["RuntimeError: the card timed out"])
        assert not worker.mon.quiet
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_the_check_is_a_quiet_command_that_does_not_clear_stop(ap, tmp_path):
    cfg = _sim()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    worker.start()
    try:
        worker.stop_flag.set()                       # Stop was pressed
        worker.send("ratecheck", 0.05)
        deadline = time.time() + 20
        while not _events(worker, "ratecheck") and time.time() < deadline:
            time.sleep(0.02)
        assert _events(worker, "ratecheck")
        assert worker.stop_flag.is_set()             # still set: the check is not a command to stop
    finally:
        worker.quit()
        worker.join(timeout=20)
        ap.close_rig(guard, rig)


def test_the_whole_window_runs_with_the_new_boxes(tmp_path):
    """pullout.py, simulated, closing itself. Its self-test ticks the
    sample-rate check in the Monitor window, switches both plot check
    boxes on and off, and flips the sign of channel 1 and back; nothing
    may leave a traceback."""
    import subprocess
    tk = pytest.importorskip("tkinter")
    pytest.importorskip("igor2")
    try:
        tk.Tk().destroy()
    except tk.TclError as exc:
        pytest.skip(f"no Tk display: {exc}")
    config = tmp_path / "rig.json"
    cfg = _sim(two=True)
    cfg.actuator.kind = "none"
    cfg.to_json(config)
    cmd = [sys.executable, str(ROOT / "pullout.py"), "--simulate", "--config", str(config),
           "--out", str(tmp_path), "--autoclose", "9"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=ROOT)
    assert res.returncode == 0, res.stderr[-3000:]
    assert "Traceback" not in res.stderr, res.stderr[-3000:]
    assert "window update failed" not in res.stderr, res.stderr[-3000:]
    assert not list(Path(tmp_path).rglob("stm_ratecheck_*"))
