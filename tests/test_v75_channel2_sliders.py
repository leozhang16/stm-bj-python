"""pullout v75: channel 2 only as far as it measured, and sliders that the
piezo follows.

1. Channel 2 where its output is saturated. Up to v74 the high-gain output
   of a two-channel amplifier was drawn and counted through contact too,
   where it sits at its rail. A saturated current divided by the junction
   voltage is not a flat line: the junction voltage still follows the
   junction through the series resistor, so the result has steps where the
   gold steps are and makes peaks in a histogram, at conductances that are
   wrong (at 300 mV through 100 kohm, 0.38 G0 for the 1 G0 plateau). On the
   rig this read as "the high gain channel shows G0 peaks too". Now channel
   2 has no value where its raw volts are at or beyond
   ``limits.preamp_saturation_v``: not drawn, not counted. In the files for
   Igor and MATLAB (the ``ch2`` subfolder, the ``_ch2.txt`` table) those
   points hold channel 1's conductance, because those programs need the
   contact part of a trace; read back as channel 2 they are blank again.

2. The sliders. One click on the bar and the piezo goes there; a knob that
   is dragged is followed while the mouse holds it (``Worker.cmd_follow``).
   The rules of every move made by hand stay: away from the surface at
   once, toward it at the speed in the box, stopping at contact. The window
   itself is worked by the mouse in ``test_v72_piezo.py`` and
   ``test_v73_approach.py``.

Simulator only: no card. None of these tests reads a number out of
configs/*.json.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stmlab import analysis, igor_scheme, storage, trace          # noqa: E402
from stmlab.config import G0_SIEMENS, RigConfig                   # noqa: E402
from stmlab.instrument import Rig                                 # noqa: E402
from stmlab.sim import SimulatedDaqSession                        # noqa: E402

STANDARD = 1077.6          # nm per card volt of the new rig's stage
SURFACE_NM = 300.0         # where the simulated surface is


@pytest.fixture(scope="module")
def ap():
    import pullout
    return pullout


# --------------------------------------------------------------------------
# 1. Channel 2 where its output is saturated
# --------------------------------------------------------------------------

def _rig_like_the_lab(bias_v: float) -> RigConfig:
    """Two outputs at 750 kV/A and 1e7 V/A, the bias through 100 kohm: the
    numbers the new rig was run with in November 2026 (typed here, not read
    from a file)."""
    cfg = RigConfig()
    cfg.simulate = True
    cfg.channels.ai_current_2 = "ai4"
    cfg.channels.current_channels = 2
    cfg.cal.preamp_gain_v_per_a, cfg.cal.preamp_gain_2_v_per_a = 7.5e5, 1e7
    cfg.keithley.series_resistance_ohm = 1e5
    cfg.keithley.gain_exponent = 6
    cfg.ramp.bias_v = bias_v
    cfg.ramp.engage_g0 = 2.0
    cfg.sim.ai_noise_v_rms = 8.8e-5
    return cfg


def _traces(cfg: RigConfig, n: int, seed: int = 5) -> list:
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=seed))
    rig.open()
    got = []
    try:
        trace.trace_loop(rig, n=n, on_trace=lambda i, tr, sel: got.append((tr, sel)))
    finally:
        rig.close()
    return got


def _ceiling_g0(cfg: RigConfig, input_ohm: float | None = None) -> float:
    """The largest conductance channel 2 can read: the current that puts
    its output at the saturation level, over the junction voltage the
    series resistor leaves at that current. ``input_ohm`` is the input
    resistance of the card's voltage input, which draws a little current
    through the series resistor as well (default: the simulated card's
    1 Mohm; ``inf`` for a card that draws none)."""
    if input_ohm is None:
        input_ohm = SimulatedDaqSession(cfg).ai_input_ohm
    rs = cfg.keithley.series_resistance_ohm
    amps = cfg.limits.preamp_saturation_v / cfg.cal.preamp_gain_2_v_per_a
    left = (cfg.ramp.bias_v - amps * rs) / (1.0 + rs / input_ohm)
    return amps / left / G0_SIEMENS if left > 0 else float("inf")


def test_what_a_saturated_channel_2_used_to_show_at_300_mv():
    """The fault itself, kept as arithmetic: on the 1 G0 plateau channel 2
    is at its rail, and its rail divided by the junction voltage reads
    about 0.38 G0, a plateau of its own at the wrong place."""
    cfg = _rig_like_the_lab(0.3)
    (tr, _), = _traces(cfg, 1)
    g1 = tr.conductance_g0(cfg)
    plateau = (g1 > 0.9) & (g1 < 1.1)
    assert plateau.sum() > 50
    railed = tr.railed2(cfg)
    assert railed[plateau].all()                     # channel 2 cannot see 1 G0 here
    ghost = tr.conductance_g0(cfg, channel=2, as_measured=True)[plateau]
    assert 0.33 < np.median(ghost) < 0.43            # ... and used to say this
    # by hand: 10 V / 1e7 V/A = 1 uA, over the 34 mV that 100 kohm leave
    # across 1 G0 at 300 mV
    left = 0.3 / (1.0 + G0_SIEMENS * 1e5)
    assert left == pytest.approx(0.0343, abs=0.0002)
    assert 1e-6 / left / G0_SIEMENS == pytest.approx(0.376, abs=0.002)


def test_channel_2_has_no_value_where_its_output_is_saturated():
    cfg = _rig_like_the_lab(0.3)
    (tr, _), = _traces(cfg, 1)
    railed = tr.railed2(cfg)
    assert np.array_equal(railed, np.abs(tr.current2_v) >= cfg.limits.preamp_saturation_v)
    assert railed[:100].all() and not railed[-2000:-500].any()   # contact, then open
    g2 = tr.conductance_g0(cfg, channel=2)
    assert np.array_equal(np.isnan(g2), railed)
    # where it has a value it is the value it always had
    raw = tr.conductance_g0(cfg, channel=2, as_measured=True)
    assert np.isfinite(raw).all() and np.array_equal(g2[~railed], raw[~railed])
    # nothing channel 2 shows is above what it can read: 0.95 uA, which at
    # 300 mV through 100 kohm is a junction of 0.06 G0
    assert _ceiling_g0(cfg, input_ohm=float("inf")) == pytest.approx(0.0598, abs=0.0005)
    top = _ceiling_g0(cfg)                           # with the simulated card's 1 Mohm
    assert top == pytest.approx(0.0658, abs=0.0005)
    assert np.nanmax(g2) <= top * 1.02
    # channel 1 is untouched: no NaN, the same numbers
    g1 = tr.conductance_g0(cfg)
    assert np.isfinite(g1).all()
    assert np.array_equal(g1, analysis.to_conductance(tr.current_v, cfg.cal,
                                                      voltage_v=tr.voltage_v))
    # a one-channel trace has no channel 2 to ask about
    one = RigConfig()
    one.simulate = True
    (tr1, _), = _traces(one, 1)
    assert tr1.railed2(one) is None
    with pytest.raises(ValueError, match="second current channel"):
        tr1.conductance_g0(one, channel=2)


def test_the_two_channels_as_one_trace_are_channel_1_where_channel_2_is_saturated():
    cfg = _rig_like_the_lab(0.3)
    (tr, _), = _traces(cfg, 1)
    railed = tr.railed2(cfg)
    g1, g2 = tr.conductance_g0(cfg), tr.conductance_g0(cfg, channel=2)
    one = tr.open_side_g0(cfg)
    assert np.isfinite(one).all()
    assert np.array_equal(one[railed], g1[railed])
    assert np.array_equal(one[~railed], g2[~railed])
    # analysis.open_side goes by the NaN alone, or by a mask as before
    assert np.array_equal(analysis.open_side(g1, g2), one)
    raw = tr.conductance_g0(cfg, channel=2, as_measured=True)
    assert np.array_equal(analysis.open_side(g1, raw, railed), one)
    assert np.array_equal(analysis.blank_railed(raw, railed), g2, equal_nan=True)
    # the verdict is the one it always was
    assert analysis.select_trace(g1, cfg.ramp, g0_open=one).accepted


def test_the_histogram_of_channel_2_ends_where_channel_2_ends():
    cfg = _rig_like_the_lab(0.3)
    got = [tr for tr, sel in _traces(cfg, 12) if sel.accepted]
    assert len(got) >= 8
    centres, h1 = analysis.log_histogram([t.conductance_g0(cfg) for t in got])
    _, h2 = analysis.log_histogram([t.conductance_g0(cfg, channel=2) for t in got])
    _, was = analysis.log_histogram(
        [t.conductance_g0(cfg, channel=2, as_measured=True) for t in got])
    above = centres > np.log10(_ceiling_g0(cfg)) + 0.05
    assert h2[above].sum() == 0                      # no "G0 peaks" on channel 2
    assert was[above].sum() > 500                    # where there used to be plenty
    assert h1[above].sum() > 500                     # channel 1 has the real ones
    # below its ceiling channel 2's histogram is what it was, bar the dozen
    # points beside each rail that the 11-point smoothing loses
    below = centres < np.log10(_ceiling_g0(cfg)) - 0.3
    assert h2[below].sum() == pytest.approx(was[below].sum(), rel=0.02)
    # and its noise floor is still decades under channel 1's
    low = centres < -4.0
    assert centres[low][np.argmax(h2[low])] < centres[low][np.argmax(h1[low])] - 0.5


def test_at_100_mv_channel_2_really_does_see_1_g0():
    """Through 100 kohm at 100 mV the current never passes 1 uA, which is
    10 V at 1e7 V/A: channel 2 stays in range through the 1 G0 plateau
    (8.9 V) and its 1 G0 peak lies on channel 1's. That one is real."""
    cfg = _rig_like_the_lab(0.1)
    assert _ceiling_g0(cfg, input_ohm=float("inf")) == pytest.approx(2.45, abs=0.05)
    assert _ceiling_g0(cfg) == pytest.approx(2.70, abs=0.05)     # the simulated card
    got = [tr for tr, sel in _traces(cfg, 12) if sel.accepted]
    centres, h1 = analysis.log_histogram([t.conductance_g0(cfg) for t in got])
    _, h2 = analysis.log_histogram([t.conductance_g0(cfg, channel=2) for t in got])
    p1 = analysis.peak_position(centres, h1, around=0.0, window=0.3)
    p2 = analysis.peak_position(centres, h2, around=0.0, window=0.3)
    assert abs(p1) < 0.03 and abs(p2 - p1) < 0.01
    near = np.abs(centres) < 0.1
    assert h2[near].sum() == pytest.approx(h1[near].sum(), rel=0.02)
    assert h2[centres > np.log10(_ceiling_g0(cfg)) + 0.05].sum() == 0   # above it: nothing


def test_the_h5_file_gives_channel_2_as_far_as_it_measured(tmp_path):
    cfg = _rig_like_the_lab(0.3)
    got = _traces(cfg, 2)
    with storage.SessionWriter(tmp_path / "two.h5", cfg) as w:
        for i, (tr, sel) in enumerate(got):
            w.append(i, tr, sel)
    with storage.Session(tmp_path / "two.h5") as s:
        tr = got[1][0]
        assert np.array_equal(s.raw2(1), tr.current2_v)          # the raw volts: all of them
        assert np.array_equal(s.railed2(1), tr.railed2(cfg))
        assert np.array_equal(s.conductance(1, channel=2),
                              tr.conductance_g0(cfg, channel=2), equal_nan=True)
        assert np.array_equal(s.conductance(1, channel=2, as_measured=True),
                              tr.conductance_g0(cfg, channel=2, as_measured=True))
        assert np.array_equal(s.open_side(1), tr.open_side_g0(cfg))
        both = list(s.conductances(channel=2))
        assert len(both) == 2 and all(np.isnan(g).any() for g in both)
        # a rail level put right afterwards reprocesses the file: an
        # amplifier that clips at 8 V is cut off at 8 V
        s.cfg.limits.preamp_saturation_v = 8.0
        lower = s.conductance(1, channel=2)
        assert np.isnan(lower).sum() > np.isnan(both[1]).sum()
    with storage.Session(tmp_path / "two.h5") as s:
        assert s.cfg.limits.preamp_saturation_v == cfg.limits.preamp_saturation_v


def test_the_ch2_folder_holds_a_whole_trace_that_igors_analysis_can_use(tmp_path):
    """Igor's panel counts a trace only when its first 2 % average above
    1.02 G0, and puts 0 nm where the trace falls through 0.5 G0. A ch2
    column that is blank through contact would give it nothing at all, so
    on disk the saturated part holds channel 1's conductance."""
    pytest.importorskip("igor2")
    cfg = _rig_like_the_lab(0.3)
    got = [(tr, sel) for tr, sel in _traces(cfg, 6) if sel.accepted][:3]
    assert len(got) == 3
    w = igor_scheme.IgorDayWriter(tmp_path, cfg)
    for tr, _ in got:
        w.append(igor_scheme.IgorTrace.from_record(tr, cfg))
    w.flush()
    day = w.folder
    b1 = igor_scheme.read_block(day, 1, companions=True)
    disk = igor_scheme.read_block_channel2(day, 1, companions=True, as_saved=True)
    seen = igor_scheme.read_block_channel2(day, 1, companions=True)
    again = igor_scheme.read_block_channel2(day, 1, first=b1)    # the block handed in
    for j, (tr, _) in enumerate(got):
        railed = tr.railed2(cfg)
        column = disk.g0[:, j]
        # on disk: a whole trace, channel 1's numbers where channel 2 was saturated
        assert np.isfinite(column).all()
        assert np.array_equal(column[railed], b1.g0[railed, j])
        assert np.allclose(column, tr.open_side_g0(cfg), rtol=1e-5, atol=1e-12)
        n = column.size
        assert np.mean(column[:n // 50]) > 1.02                  # Igor's start test
        below = np.flatnonzero(column < 0.5)
        assert below.size and 0 < below[0] < n                   # and its 0 nm
        # read as channel 2: only what channel 2 measured
        assert np.array_equal(np.isnan(seen.g0[:, j]), railed)
        assert np.array_equal(seen.g0[~railed, j], column[~railed])
        assert np.array_equal(seen.g0[:, j], again.g0[:, j], equal_nan=True)
        # the current block is channel 2's own, saturated where it was
        assert np.allclose(disk.current_a[:, j],
                           cfg.cal.volts_to_amps(tr.current2_v, channel=2),
                           rtol=1e-5, atol=1e-15)
        assert np.max(np.abs(disk.current_a[railed, j])) > 0.9e-6
    # the note of the block says what its numbers are
    note = igor_scheme.read_wave(
        igor_scheme.block_file(igor_scheme.channel2_folder(day), "conductance", 1)).note
    assert igor_scheme.CH2_NOTE in note and "channel 1's" in note
    # the ch2 subfolder opened by itself is a day folder like any other
    alone = igor_scheme.read_day_folder(igor_scheme.channel2_folder(day))[0]
    assert np.array_equal(alone.g0, disk.g0)
    # and a restart refills the block without changing a number in it
    again_w = igor_scheme.IgorDayWriter(tmp_path, cfg)
    assert again_w.saved == 4
    again_w.flush()
    after = igor_scheme.read_block_channel2(day, 1, as_saved=True)
    assert np.array_equal(after.g0, disk.g0)


def test_a_ch2_block_written_before_v75_is_read_as_it_is(tmp_path):
    """Up to v74 the ch2 block held channel 2's own numbers, saturated or
    not, and nothing in the file says where: it is shown as it is."""
    pytest.importorskip("igor2")
    cfg = _rig_like_the_lab(0.3)
    (tr, _), = _traces(cfg, 1)
    old = igor_scheme.IgorTrace.from_record(tr, cfg)
    old.g0_2 = np.asarray(tr.conductance_g0(cfg, channel=2, as_measured=True))
    w = igor_scheme.IgorDayWriter(tmp_path, cfg)
    w.append(old)
    w.flush()
    seen = igor_scheme.read_block_channel2(w.folder, 1)
    assert np.isfinite(seen.g0).all()
    assert np.allclose(seen.g0[:, 0], old.g0_2, rtol=1e-5, atol=1e-12)


def test_blank_filled_in_only_blanks_what_is_channel_1s():
    g1 = np.array([[5.0, 4.0], [3.0, 2.5], [1.0, 1.0], [1e-3, 2e-3], [1e-5, 3e-5]])
    g2 = g1.copy()
    g2[3:, 0] = [1.1e-3, 0.9e-5]                     # channel 2's own readings
    g2[2:, 1] = [0.99, 2.1e-3, 2.8e-5]
    params = np.zeros((2, 20))
    first = igor_scheme.IgorBlock(1, Path("."), g1, params, np.array([0, 1]), np.array([1, 2]))
    second = igor_scheme.IgorBlock(1, Path("."), g2.copy(), params, np.array([0, 1]),
                                   np.array([1, 2]))
    assert igor_scheme.blank_filled_in(second, first) == 5
    assert np.array_equal(np.isnan(second.g0), g2 == g1)
    assert np.array_equal(second.g0[3:, 0], g2[3:, 0])
    # a column the day folder does not have, and a block of another length:
    # left alone
    lone = igor_scheme.IgorBlock(1, Path("."), g2.copy(), params[:1], np.array([7]),
                                 np.array([8]))
    lone.g0 = g2[:, :1].copy()
    assert igor_scheme.blank_filled_in(lone, first) == 0
    short = igor_scheme.IgorBlock(1, Path("."), g2[:3].copy(), params, np.array([0, 1]),
                                  np.array([1, 2]))
    assert igor_scheme.blank_filled_in(short, first) == 0 and np.isfinite(short.g0).all()


def test_the_trace_panel_draws_channel_2_from_where_it_comes_off_its_rail():
    from matplotlib.figure import Figure

    from stmlab import plots
    cfg = _rig_like_the_lab(0.3)
    (tr, sel), = _traces(cfg, 1)
    disp = tr.displacement_nm(cfg)
    g2 = tr.conductance_g0(cfg, channel=2)
    for linear in (False, True):
        ax = Figure().subplots()
        plots.plot_trace(ax, cfg, tr.conductance_g0(cfg), disp, sel, g0_2=g2, linear=linear)
        red = next(ln for ln in ax.lines if ln.get_color() == plots.C_CH2
                   and len(ln.get_xdata()) == disp.size)
        y = np.asarray(red.get_ydata(), dtype=float)
        assert np.array_equal(np.isnan(y), tr.railed2(cfg))       # no line through contact
        top = np.nanmax(y) if linear else 10.0 ** np.nanmax(y)
        assert top <= _ceiling_g0(cfg) * 1.02
        assert "NEGATIVE" not in ax.get_title()


def test_a_channel_2_the_wrong_way_round_is_still_said(ap, tmp_path):
    """The sign of channel 2 is read with its saturated part left in: the
    part that is drawn has no value there and could not tell."""
    from matplotlib.figure import Figure

    from stmlab import plots
    cfg = _rig_like_the_lab(0.3)
    cfg.sim.amplifier_output_sign_2 = -1.0
    (tr, _), = _traces(cfg, 1)
    assert (tr.current2_v[:100] <= -cfg.limits.preamp_saturation_v).all()   # negative rail
    g2 = tr.conductance_g0(cfg, channel=2)
    raw = tr.conductance_g0(cfg, channel=2, as_measured=True)
    assert analysis.reads_negative(raw)
    ax = Figure().subplots()
    plots.plot_trace(ax, cfg, tr.conductance_g0(cfg), tr.displacement_nm(cfg), g0_2=g2,
                     negative2=True)
    assert "[ch 2 NEGATIVE]" in ax.get_title()
    assert "flip the sign" in " ".join(t.get_text() for t in ax.texts)
    # the worker says it in its status line and hands the panel the word
    guard, rig = ap.open_rig(cfg)
    worker = ap.Worker(cfg, rig, ap.Monitor(rig), save=False, out_dir=tmp_path,
                       igor_export=False)
    try:
        worker.cmd_cycle()
        events = list(worker.events.queue)
        cycle = [p for k, p in events if k == "cycle" and p.get("record") is not None][-1]
        assert cycle["negative2"] is True
        assert np.isnan(cycle["g0_2"][:100]).all()
        said = [p["text"] for k, p in events if k == "status"][-1]
        assert said.startswith("ch 2 reads a NEGATIVE conductance")
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_the_sign_of_channel_2_is_read_with_its_saturated_part_in(ap, tmp_path, monkeypatch):
    """A contact that lets go all at once: channel 2 sits at its negative
    rail and is then at once in its noise. What is drawn of it has no
    conducting sample at all, so the sign can only be read from the rail."""
    cfg = _rig_like_the_lab(0.3)
    guard, rig = ap.open_rig(cfg)
    worker = ap.Worker(cfg, rig, ap.Monitor(rig), save=False, out_dir=tmp_path,
                       igor_export=False)
    try:
        rng = np.random.default_rng(1)
        n, hold = 4000, 1500
        g_true = np.where(np.arange(n) < hold, 3.0, 0.0)             # 3 G0, then open
        vj = cfg.ramp.bias_v / (1.0 + g_true * G0_SIEMENS * 1e5)
        amps = g_true * G0_SIEMENS * vj
        record = trace.TraceRecord(
            index=0, voltage_v=cfg.cal.voltage_input_sign * vj,
            current_v=amps * cfg.cal.preamp_gain_v_per_a + rng.normal(0, 1e-5, n),
            delay_samples=0, start_piezo_v=1.0, bias_v=cfg.ramp.bias_v,
            sample_rate_hz=cfg.ramp.sample_rate_hz,
            # channel 2 the wrong way round: at -10 V through contact
            current2_v=np.clip(-amps * cfg.cal.preamp_gain_2_v_per_a
                               + rng.normal(0, 1e-4, n), -10.0, 10.0))
        drawn = record.conductance_g0(cfg, channel=2)
        assert np.isnan(drawn[:hold]).all()
        assert not analysis.reads_negative(drawn)        # what is drawn cannot tell
        assert analysis.reads_negative(record.conductance_g0(cfg, channel=2, as_measured=True))
        monkeypatch.setattr(ap.trace, "single_trace", lambda *a, **k: record)
        worker._pull(test=True)
        events = list(worker.events.queue)
        cycle = [p for k, p in events if k == "cycle" and p.get("record") is not None][-1]
        assert cycle["negative2"] is True
        said = [p["text"] for k, p in events if k == "status"][-1]
        assert said.startswith("ch 2 reads a NEGATIVE conductance")
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_run_counts_channel_2_only_where_it_measured(ap, tmp_path):
    """The window's worker over a run at 300 mV: what it hands the trace
    panel, its channel-2 histogram, its noise floors, and its files."""
    pytest.importorskip("igor2")
    pytest.importorskip("h5py")
    cfg = _rig_like_the_lab(0.3)
    guard, rig = ap.open_rig(cfg)
    worker = ap.Worker(cfg, rig, ap.Monitor(rig), save=True, out_dir=tmp_path,
                       igor_export=True)
    try:
        worker.cmd_zero()
        worker.cmd_run(4, {"name": "t", "experiment": "gold", "notes": "", "folder":
                           str(tmp_path), "txt": True, "h5": True})
        assert worker.accepted == 4
        events = list(worker.events.queue)
        cycle = [p for k, p in events if k == "cycle" and p.get("record") is not None][-1]
        rec = cycle["record"]
        assert np.array_equal(np.isnan(cycle["g0_2"]), rec.railed2(cfg))
        assert cycle["negative2"] is False
        centres, h2 = worker.hist_centres, worker.histogram2()
        assert worker.hist2_n == 4
        assert h2[centres > np.log10(_ceiling_g0(cfg)) + 0.05].sum() == 0
        assert worker.histogram()[np.abs(centres) < 0.1].sum() > 100     # channel 1: the peak
        floor1, floor2 = worker.noise_floors()
        assert floor2 is not None and np.isfinite(floor2) and floor2 < floor1 / 5
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)
    # the table for MATLAB: the two channels as one trace, no blanks
    table = next(p for p in tmp_path.rglob("*_ch2.txt"))
    data = np.loadtxt(table)
    assert data.shape[1] == 5 and np.isfinite(data).all()
    assert (data[:5, 1:] > 1.0).all()                # channel 1's contact at the top
    assert "where its output was saturated the conductance is channel 1's" in table.read_text()
    # the day folder, read back by the window's browser: channel 2 as it measured
    day = next(p.parent for p in tmp_path.rglob("ch2")).joinpath("")
    folder = ap.IgorDay(day)
    t = folder.trace(0)
    assert np.isnan(t["g0_2"]).any() and np.isfinite(t["g0_2"]).any()
    assert np.nanmax(t["g0_2"]) <= _ceiling_g0(cfg) * 1.02
    centres_i = folder.hist[0]
    assert folder.hist2[centres_i > np.log10(_ceiling_g0(cfg)) + 0.05].sum() == 0
    both = folder.data()
    assert all(np.isnan(x).any() for x in both.traces2)
    # the end of the trace is still judged on the two channels as one
    verdict = analysis.select_trace(t["g0"], folder.cfg.ramp,
                                    g0_open=analysis.open_side(t["g0"], t["g0_2"]))
    assert verdict.accepted


# --------------------------------------------------------------------------
# 2. The sliders: the piezo follows the knob
# --------------------------------------------------------------------------

def _stage() -> RigConfig:
    """A one-card rig whose stage has a micrometre to the volt, simulated."""
    cfg = RigConfig()
    cfg.simulate = True
    cfg.channels.sense_device, cfg.channels.ai_piezo_sense = cfg.channels.device, "ai3"
    cfg.cal.piezo_total_um, cfg.cal.piezo_mode = 10.776, "standard"
    cfg.cal.apply_piezo_mode()
    return cfg


def _worker(ap, cfg, tmp_path):
    guard, rig = ap.open_rig(cfg)
    worker = ap.Worker(cfg, rig, ap.Monitor(rig), save=False, out_dir=tmp_path,
                       igor_export=False)
    return guard, rig, worker


def _surface(rig, nm: float) -> None:
    session = rig._session
    session.move_surface(nm - session.surface_nm)


def _said(worker) -> list[str]:
    return [p["text"] for k, p in list(worker.events.queue) if k == "status"]


def _click(worker, volts: float) -> None:
    """What one click on a slider's bar asks of the worker: the mouse down
    with the knob at ``volts``, the mouse up, and the queued command run."""
    worker.follow_begin(volts)
    worker.follow_end()
    assert list(worker.commands.queue) == [("follow",)]
    worker.commands.get_nowait()
    worker.cmd_follow()


def test_one_click_and_the_piezo_goes_there(ap, tmp_path):
    cfg = _stage()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        _surface(rig, 6000.0)
        _click(worker, 3.0)                              # toward the surface, short of it
        assert rig.piezo_v == pytest.approx(3.0) and not worker.following
        assert _said(worker)[-1].startswith("piezo 0.0000 -> 3.0000 V (3232.8 nm)")
        assert "open" in _said(worker)[-1]
        _click(worker, 0.5)                              # away from it: at once
        assert rig.piezo_v == pytest.approx(0.5)
        assert _said(worker)[-1].startswith("piezo 3.0000 -> 0.5000 V")
        # out of the piezo's range: to the end of it, no further
        _click(worker, -3.0)
        assert rig.piezo_v == cfg.limits.piezo_ao_min_v
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_click_past_the_surface_stops_at_contact(ap, tmp_path):
    cfg = _stage()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        _click(worker, 5.0)                              # the surface is at 0.278 V
        assert SURFACE_NM < rig.piezo_nm <= SURFACE_NM + 1.25 * 5.0 + 1.0
        assert rig.state is ap.RigState.ENGAGED and not worker.following
        said = [p for k, p in list(worker.events.queue) if k == "status"][-1]
        assert said["text"].startswith("STOPPED AT CONTACT (") and said["level"] == "warn"
        assert f"{5.0 - rig.piezo_v:.4f} V short of the 5.0000 V asked for" in said["text"]
        assert "in contact" in said["text"]
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_slider_never_pushes_into_a_junction_that_is_closed(ap, tmp_path):
    """Clicking past a contact again and again must cost nothing. (With the
    rule of Step closer, one more piece each time, ten clicks at 2000 nm/s
    would be half a micrometre into the surface.)"""
    cfg = _stage()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.hand_speed_nm_s = 2000.0                  # 50 nm pieces
        _click(worker, 5.0)
        at = rig.piezo_v
        assert SURFACE_NM < rig.piezo_nm <= SURFACE_NM + 1.25 * 50.0 + 1.0
        assert _said(worker)[-1].startswith("STOPPED AT CONTACT (")
        for volts in (5.0, 9.0, at + 0.001, 10.0):
            _click(worker, volts)
            assert rig.piezo_v == at                     # not one piece further
            said = [p for k, p in list(worker.events.queue) if k == "status"][-1]
            assert said["text"].startswith("ALREADY IN CONTACT (") and said["level"] == "warn"
            assert "a slider does not push further in" in said["text"]
            assert rig.state is ap.RigState.ENGAGED
        # a little way back that leaves the junction closed, and up again: the
        # same, from where it now stands
        back = at - 20.0 / STANDARD                      # 20 nm back: still in the surface
        _click(worker, back)
        assert rig.piezo_v == pytest.approx(back) and rig.piezo_nm > SURFACE_NM
        _click(worker, 5.0)
        assert rig.piezo_v == pytest.approx(back)
        assert _said(worker)[-1].startswith("ALREADY IN CONTACT (")
        # out of the contact and up again: it comes up, and stops at the contact
        _click(worker, 0.1)
        assert "open" in _said(worker)[-1]
        _click(worker, 5.0)
        assert SURFACE_NM < rig.piezo_nm <= SURFACE_NM + 1.25 * 50.0 + 2.0
        assert _said(worker)[-1].startswith("STOPPED AT CONTACT (")
        # Step closer still presses in, one piece at the most: that is what it is for
        deep = rig.piezo_nm
        worker.cmd_step(+2.0)
        assert rig.piezo_nm == pytest.approx(deep + 2.0)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_toward_the_surface_it_goes_in_pieces_at_the_speed_in_the_box(ap, tmp_path,
                                                                     monkeypatch):
    cfg = _stage()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        pieces, looks, ramps = [], [], []
        glide, ramp = rig.piezo_glide_to, rig.piezo_ramp_to

        def counted(volts, seconds):
            # a glide that goes nowhere is a look at the junction
            (looks if abs(volts - rig.piezo_v) < 1e-12 else pieces).append((volts, seconds))
            return glide(volts, seconds)
        monkeypatch.setattr(rig, "piezo_glide_to", counted)
        monkeypatch.setattr(rig, "piezo_ramp_to",
                            lambda v, *a, **k: (ramps.append(v), ramp(v, *a, **k))[1])
        _click(worker, 0.2)                              # 215.52 nm at 200 nm/s: 5 nm pieces
        assert len(pieces) == 44 and all(s == pytest.approx(0.025) for _, s in pieces)
        assert (pieces[1][0] - pieces[0][0]) * STANDARD == pytest.approx(5.0)
        assert ramps == []
        assert len(looks) == 1                           # one look, before the first piece
        pieces.clear()
        _click(worker, 0.0)                              # away: one ramp, no pieces
        assert ramps == [0.0] and pieces == [] and len(looks) == 1
        worker.hand_speed_nm_s = 1000.0                  # 25 nm pieces
        _click(worker, 0.2)
        assert len(pieces) == 9 and len(looks) == 2
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_press_that_takes_the_knob_nowhere_moves_nothing_and_says_nothing(ap, tmp_path):
    cfg = _stage()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        _click(worker, 0.1)
        state, n, bias = rig.state, len(_said(worker)), rig.bias_v
        played = len(worker.mon.last().rec_t)
        worker.bias_dirty = True                         # as after a change of the bias box
        _click(worker, rig.piezo_v)                      # down and up on the knob itself
        assert rig.piezo_v == pytest.approx(0.1) and rig.state is state
        assert len(_said(worker)) == n and not worker.following
        assert worker.bias_dirty and rig.bias_v == bias  # not even the bias was touched
        assert len(worker.mon.last().rec_t) == played    # and nothing was played
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_stop_ends_a_slider_move_where_it_is(ap, tmp_path, monkeypatch):
    cfg = _stage()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        _surface(rig, 6000.0)
        glide, n = rig.piezo_glide_to, [0]

        def three_then_stop(volts, seconds):
            if abs(volts - rig.piezo_v) > 1e-12:         # a piece, not the look before it
                n[0] += 1
            if n[0] == 3:
                worker.stop_flag.set()
            return glide(volts, seconds)
        monkeypatch.setattr(rig, "piezo_glide_to", three_then_stop)
        worker.follow_begin(2.0)                         # the mouse stays down
        worker.commands.get_nowait()
        worker.cmd_follow()
        assert rig.piezo_nm == pytest.approx(15.0)       # three 5 nm pieces
        assert not worker.following
        assert _said(worker)[-1].startswith(
            f"stopped by Stop, {2.0 - rig.piezo_v:.4f} V short of the 2.0000 V asked for")
        # the drag is over: the knob's later moves ask for nothing
        assert worker.follow_to(1.5) is False
        worker.follow_end()
        worker.stop_flag.clear()
        worker.cmd_follow()                              # a leftover command: nothing to do
        assert rig.piezo_nm == pytest.approx(15.0)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_second_click_on_the_way_changes_its_mind(ap, tmp_path, monkeypatch):
    cfg = _stage()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        _surface(rig, 6000.0)
        glide, n = rig.piezo_glide_to, [0]

        def click_again(volts, seconds):
            n[0] += 1
            if n[0] == 11:                               # 50 nm up: the user clicks lower
                worker.follow_begin(0.02)
                worker.follow_end()
            return glide(volts, seconds)
        monkeypatch.setattr(rig, "piezo_glide_to", click_again)
        worker.follow_begin(3.0)
        worker.follow_end()
        worker.commands.get_nowait()
        worker.cmd_follow()
        assert rig.piezo_v == pytest.approx(0.02) and not worker.following
        assert _said(worker)[-1].startswith("piezo 0.0000 -> 0.0200 V")
        # the second click queued one more command, as every press does; it
        # finds nothing left to do and says nothing
        assert list(worker.commands.queue) == [("follow",)]
        said = len(_said(worker))
        worker.commands.get_nowait()
        worker.cmd_follow()
        assert len(_said(worker)) == said and rig.piezo_v == pytest.approx(0.02)
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def _wait(worker, timeout: float = 20.0) -> None:
    end = time.time() + timeout
    time.sleep(0.05)
    while time.time() < end and (worker.busy or not worker.commands.empty()):
        time.sleep(0.01)
    assert not worker.busy and worker.commands.empty()


def _until(test, timeout: float = 10.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if test():
            return True
        time.sleep(0.01)
    return False


def test_a_knob_that_is_dragged_is_followed_while_the_mouse_holds_it(ap, tmp_path):
    """The worker on its own thread, as in the window: the knob is taken
    from place to place with the mouse down, and the piezo is at each
    before the next; nothing is said until the mouse lets go."""
    cfg = _stage()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    worker.start()
    try:
        _surface(rig, 6000.0)
        worker.hand_speed_nm_s = 5000.0
        worker.follow_begin(rig.piezo_v)                 # the mouse down on the knob
        assert _until(lambda: worker.current == "follow")
        before = len(_said(worker))
        for volts in (1.0, 2.5, 0.7, 0.9):
            assert worker.follow_to(volts) is True
            assert _until(lambda: abs(rig.piezo_v - volts) < 1e-9), (volts, rig.piezo_v)
            assert worker.busy and worker.following      # still held: still following
        moves = [t for t in _said(worker)[before:] if " -> " in t]
        assert moves == []
        worker.follow_end()                              # the mouse up
        _wait(worker)
        assert rig.piezo_v == pytest.approx(0.9) and not worker.following
        moves = [t for t in _said(worker)[before:] if " -> " in t]
        assert len(moves) == 1 and moves[0].startswith("piezo 0.0000 -> 0.9000 V")
    finally:
        worker.quit()
        worker.join(5)
        ap.close_rig(guard, rig)


def test_after_a_contact_it_goes_no_further_until_the_knob_comes_back(ap, tmp_path):
    cfg = _stage()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    worker.start()
    try:
        _surface(rig, 2000.0)
        worker.hand_speed_nm_s = 2000.0
        worker.follow_begin(4.0)                         # the bar clicked far past the surface
        assert _until(lambda: rig.piezo_nm > 2000.0)
        time.sleep(0.3)                                  # the mouse still down, the knob at 4 V
        at = rig.piezo_nm
        assert 2000.0 < at <= 2000.0 + 1.25 * 50.0 + 1.0 # one 50 nm piece past, no more
        time.sleep(0.3)
        assert rig.piezo_nm == at and worker.following   # held back, and staying there
        assert worker.follow_to(4.5)                     # pushed further: nothing
        time.sleep(0.2)
        assert rig.piezo_nm == at
        assert worker.follow_to(1.0)                     # brought back below the piezo
        assert _until(lambda: abs(rig.piezo_v - 1.0) < 1e-9)
        assert worker.follow_to(4.0)                     # and up again: it comes again
        assert _until(lambda: rig.piezo_nm > 1990.0)
        worker.follow_end()
        _wait(worker)
        assert rig.state is ap.RigState.ENGAGED and not worker.following
        assert _said(worker)[-1].startswith("STOPPED AT CONTACT (")
        assert "short of the 4.0000 V asked for" in _said(worker)[-1]
    finally:
        worker.quit()
        worker.join(5)
        ap.close_rig(guard, rig)


def test_a_press_is_never_lost_between_two_moves(ap, tmp_path):
    """Every press queues a command unless one is waiting already, and a
    command that finds nothing asked since the last one ended does nothing:
    so a press that arrives while a move is ending is served by the next."""
    cfg = _stage()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        worker.cmd_follow()                              # nothing asked at all: nothing
        assert rig.piezo_v == 0.0 and _said(worker) == []
        worker.follow_begin(0.1)
        worker.follow_begin(0.15)                        # pressed again before it ran
        assert list(worker.commands.queue) == [("follow",)]
        worker.follow_end()
        worker.commands.get_nowait()
        worker.cmd_follow()
        assert rig.piezo_v == pytest.approx(0.15)        # the last word counts
        # a press after the move has ended: following again, a command queued
        worker.follow_begin(0.05)
        assert worker.following and list(worker.commands.queue) == [("follow",)]
        worker.follow_end()
        worker.commands.get_nowait()
        worker.cmd_follow()
        assert rig.piezo_v == pytest.approx(0.05) and not worker.following
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)


def test_a_press_while_a_move_is_ending_is_served_by_the_next(ap, tmp_path, monkeypatch):
    """The worker on its own thread. A move has left its loop and is
    writing its last line when the mouse goes down again: that press must
    not be dropped because "a move is running"."""
    cfg = _stage()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    _surface(rig, 6000.0)
    worker.hand_speed_nm_s = 5000.0
    ending, go_on = threading.Event(), threading.Event()
    settle = worker._settle_by_hand

    def slow_settle():
        ending.set()                                     # the loop is over ...
        go_on.wait(5)                                    # ... and the command is not
        return settle()
    monkeypatch.setattr(worker, "_settle_by_hand", slow_settle)
    worker.start()
    try:
        worker.follow_begin(1.0)
        worker.follow_end()
        assert ending.wait(10) and worker.busy and not worker.following
        monkeypatch.setattr(worker, "_settle_by_hand", settle)
        worker.follow_begin(2.0)                         # the next click, right then
        worker.follow_end()
        assert worker.following
        go_on.set()
        _wait(worker)
        assert rig.piezo_v == pytest.approx(2.0) and not worker.following
    finally:
        go_on.set()
        worker.quit()
        worker.join(5)
        ap.close_rig(guard, rig)


def test_in_the_simulated_window_a_move_toward_the_surface_takes_its_time(ap, tmp_path):
    """A simulated card plays in no time. With ``sim_real_time`` (the
    window sets it in a simulation) each 25 ms piece takes 25 ms, so a
    slider tried on a laptop is as slow as it will be on the rig."""
    cfg = _stage()
    guard, rig, worker = _worker(ap, cfg, tmp_path)
    try:
        assert worker.sim_real_time is False             # headless: as fast as it goes
        started = time.monotonic()
        _click(worker, 0.05)                             # 54 nm: 11 pieces
        assert time.monotonic() - started < 0.2
        worker.sim_real_time = True
        _click(worker, 0.0)
        started = time.monotonic()
        _click(worker, 0.05)
        assert time.monotonic() - started >= 11 * 0.025
        started = time.monotonic()
        worker.cmd_goto(0.1)                             # Step closer and Approach alike
        assert time.monotonic() - started >= 10 * 0.025
    finally:
        worker.close_file()
        ap.close_rig(guard, rig)
