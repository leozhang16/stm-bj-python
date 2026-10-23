"""plot.py: the standalone plots of a saved session or of an Igor day
folder, and the window drawing the same picture through it.

The Igor inputs are exercised on a small synthetic day folder (230 traces
of 400 points, written with ``igor_scheme.write_block_files`` exactly as
pullout.py writes a day) and, when the NAS is mounted, on the real July
2026 data (``07_16_26``: 300 blocks of 100 traces x 10000 points).
"""
from __future__ import annotations

import sys
import time
import weakref
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import plot                                        # noqa: E402
from stmlab import igor_scheme, storage, trace     # noqa: E402
from stmlab.config import G0_SIEMENS, RigConfig    # noqa: E402
from stmlab.instrument import Rig                  # noqa: E402
from stmlab.sim import SimulatedDaqSession         # noqa: E402

NAS_DAY = Path("/Users/ly666/Library/CloudStorage/SynologyDrive-SynNAS/"
               "Masha_Research/Summer_2026/Experiment/Raw_data/07_16_26")

N_DAY, N_PTS = 230, 400               # the synthetic day: 230 traces of 400 points
WHEN = time.mktime((2026, 10, 22, 14, 30, 0, 0, 0, -1))
GATE = RigConfig().ramp.break_g0      # the floor gate of the 1D histogram, 5e-4 G0


@pytest.fixture
def session_file(tmp_path) -> Path:
    cfg = RigConfig()
    cfg.simulate = True
    rig = Rig(cfg, session=SimulatedDaqSession(cfg, seed=3))
    rig.open()
    try:
        path = tmp_path / "clean_gold_120000_4traces.h5"
        with storage.SessionWriter(path, cfg) as writer:
            trace.trace_loop(rig, n=4, on_trace=writer.append)
    finally:
        rig.close()
    return path


def _day_cfg() -> RigConfig:
    cfg = RigConfig()
    cfg.ramp.pull_length_nm = 5.0
    cfg.ramp.pull_rate_nm_per_s = 20.0
    cfg.ramp.sample_rate_hz = N_PTS / 0.25             # a 5 nm pull at 20 nm/s is N_PTS points
    cfg.ramp.bias_v = 0.6
    return cfg


def _gold_like(number: int, n: int = N_PTS) -> np.ndarray:
    """A gold pull in G/G0: contact at 18 G0, a plateau at 1 G0, then the
    exponential tunnelling decay down to the noise floor."""
    rng = np.random.default_rng(number)
    g0 = 10 ** np.linspace(1.2, -6.0, n) + rng.normal(0, 1e-7, n)
    g0[:40] = 18.0
    g0[60:120] = 1.0 + rng.normal(0, 0.02, 60)
    return g0


def _igor_trace(cfg: RigConfig, number: int) -> igor_scheme.IgorTrace:
    g0 = _gold_like(number)
    voltage_v = np.full(N_PTS, cfg.ramp.bias_v)
    current_a = g0 * G0_SIEMENS * voltage_v
    ext = 1000.0 - np.linspace(0.0, 5.0, N_PTS)         # the readback walks 5 nm
    params = igor_scheme.igor_parameters(cfg, 4.0, WHEN + 10.0 * number, extension_nm=ext)
    return igor_scheme.IgorTrace(g0, voltage_v, current_a, ext, None, params)


@pytest.fixture(scope="module")
def day_folder(tmp_path_factory) -> Path:
    """A day folder as pullout.py writes it: blocks 1 and 2 complete, block 3
    with 30 traces, with the Voltage, Current, Extension and Hist files."""
    pytest.importorskip("igor2")
    cfg = _day_cfg()
    folder = tmp_path_factory.mktemp("data") / "10_22_26Merge"
    flags = igor_scheme.SaveFlags()                     # bias, current, sense, hist on
    B = igor_scheme.BLOCK
    for k in range(1, (N_DAY - 1) // B + 2):
        columns = [_igor_trace(cfg, i) for i in range((k - 1) * B + 1, min(k * B, N_DAY) + 1)]
        igor_scheme.write_block_files(folder, k, columns, cfg, flags, note="test day")
    return folder


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def test_the_command_line_reads_files_modes_and_trace_numbers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("a.h5", "x.h5", "y.h5"):
        (tmp_path / name).touch()
    a = plot.parse(["a.h5", "1D"])
    assert [p.name for p in a.files] == ["a.h5"] and a.mode == "1d"
    assert plot.parse(["a.h5", "2d"]).mode == "2d"
    assert plot.parse(["a.h5"]).mode == "both"
    t = plot.parse(["a.h5", "-1"])
    assert t.mode == "trace" and t.trace == 1          # -1 is the first trace
    assert plot.parse(["a.h5", "-7"]).trace == 7
    assert plot.parse(["x.h5", "y.h5", "1D", "--xlim", "-6", "1"]).xlim == [-6.0, 1.0]
    assert plot.parse(["a.h5", "1D"]).even_bins is False
    assert plot.parse(["a.h5", "1D", "--even-bins"]).even_bins is True
    assert plot.parse(["a.h5", "1D"]).no_floor_gate is False
    assert plot.parse(["a.h5", "1D", "--no-floor-gate"]).no_floor_gate is True
    # the options may stand anywhere: before, between or after the words
    b = plot.parse(["--xlim", "-6", "1", "a.h5", "--save", "1D"])
    assert b.xlim == [-6.0, 1.0] and b.save and b.mode == "1d" and [p.name for p in b.files] == ["a.h5"]
    assert plot.parse(["a.h5", "--save", "-7"]).trace == 7          # -7 after an option is still a trace
    assert plot.parse(["--save", "a.h5", "-7"]).trace == 7
    with pytest.raises(SystemExit):
        plot.parse(["a.h5", "3D"])
    with pytest.raises(SystemExit):
        plot.parse(["a.h5", "-0"])
    with pytest.raises(SystemExit):
        plot.parse(["1D"])                               # no file
    with pytest.raises(SystemExit):
        plot.parse(["a.h5", "1D", "--no-such-option"])


def test_a_named_file_that_does_not_exist_is_refused(tmp_path, capsys):
    for name in ("nosuch.h5", "nosuch.ibw", "nosuch.txt"):
        with pytest.raises(SystemExit) as exc:
            plot.parse([str(tmp_path / name), "1D"])
        assert exc.value.code == 2
        assert "no such file" in capsys.readouterr().err
    (tmp_path / "there.txt").write_text("0 1\n")
    assert plot.parse([str(tmp_path / "there.txt"), "1D"]).files == [tmp_path / "there.txt"]


def test_the_command_line_takes_a_day_folder_with_blocks_and_traces(tmp_path):
    folder = tmp_path / "07_16_26"
    folder.mkdir()
    a = plot.parse([str(folder), "1D", "--blocks", "1-5,9", "--traces", "1-500"])
    assert a.files == [folder] and a.mode == "1d"
    assert a.blocks == [1, 2, 3, 4, 5, 9] and a.traces == [(1, 500)]
    assert plot.parse([str(folder), "--traces", "7"]).traces == [(7, 7)]
    assert plot.parse([str(folder), "--blocks", "3"]).blocks == [3]
    assert plot.parse([str(folder), "--traces", "1-100,201-300"]).traces == [(1, 100), (201, 300)]
    assert plot.parse([str(folder), "-205"]).trace == 205
    assert plot.parse([str(folder)]).blocks is None
    # --blocks/--traces between the folder and 1D/2D/-N, as chapter 18 writes them
    b = plot.parse([str(folder), "--blocks", "1-5,9", "1D"])
    assert b.files == [folder] and b.mode == "1d" and b.blocks == [1, 2, 3, 4, 5, 9]
    c = plot.parse([str(folder), "--traces", "1-500", "2D"])
    assert c.mode == "2d" and c.traces == [(1, 500)]
    d = plot.parse([str(folder), "--blocks", "3", "-205"])
    assert d.mode == "trace" and d.trace == 205 and d.blocks == [3]
    assert plot.parse([str(folder), "-205", "--blocks", "3"]).trace == 205
    e = plot.parse(["--save", str(folder), "--traces", "1-500", "--blocks", "1-5", "1D", "--out", "figs"])
    assert e.save and e.out == Path("figs") and e.blocks == [1, 2, 3, 4, 5] and e.mode == "1d"
    for bad in ("0-5", "5-1", "a", "", "1-"):
        with pytest.raises(SystemExit):
            plot.parse([str(folder), "--blocks", bad])
    with pytest.raises(SystemExit):
        plot.parse([str(tmp_path / "no_such_folder"), "1D"])   # neither a file nor a folder
    assert plot.parse_ranges("1-5,9") == [(1, 5), (9, 9)]
    with pytest.raises(ValueError):
        plot.parse_ranges("x")


# --------------------------------------------------------------------------
# This program's sessions
# --------------------------------------------------------------------------

def test_loading_one_file_and_two_files(session_file):
    one = plot.load([session_file])
    assert one.n == 4 and one.disp_nm.size == one.traces[0].size
    assert one.name == session_file.stem
    assert one.numbers == [1, 2, 3, 4] and one.hist_waves == []
    two = plot.load([session_file, session_file])
    assert two.n == 8 and "2 files" in two.name


def test_the_histograms_draw_and_report(session_file):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    data = plot.load([session_file])
    fig = Figure()
    info = plot.hist_1d(fig.add_subplot(121), data, bins=500, smooth=5)
    assert info["centres"].size == 500 and "1 G0 peak" in info["note"]
    assert np.isfinite(info["peak"])                   # gold: a peak near 1 G0
    assert abs(info["peak"]) < 0.3
    assert info["wave_peaks"] == {} and data.report["1d"] is info
    info2 = plot.hist_2d(fig.add_subplot(122), data, xbins=50, ybins=60)
    assert info2["counts"].shape == (50, 60) and info2["max"] > 0
    # the same histogram is not computed twice
    assert len(data.cache) == 2
    plot.hist_1d(fig.add_subplot(121), data, bins=500, smooth=5)
    plot.hist_2d(fig.add_subplot(122), data, xbins=50, ybins=60)
    assert len(data.cache) == 2
    # a wrong colour or colormap name is reported, not fatal
    assert "not a colour" in plot.hist_1d(fig.add_subplot(121), data, bins=500,
                                          smooth=5, color="nosuchcolour")["note"]
    assert "not a colormap" in plot.hist_2d(fig.add_subplot(122), data, xbins=50,
                                            ybins=60, cmap="nosuchmap")["note"]
    assert len(data.cache) == 2


def test_igor_bins_are_the_default_and_even_bins_the_old_way(session_file):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    data = plot.load([session_file])
    ax = Figure().add_subplot(111)
    igor = plot.hist_1d(ax, data)
    even = plot.hist_1d(ax, data, igor_bins=False)
    # Igor: bin i starts at -8 + i*10/999, so the first centre is half of that above -8
    assert igor["centres"][0] == pytest.approx(-8 + 0.5 * 10 / 999)
    assert igor["centres"][1] - igor["centres"][0] == pytest.approx(10 / 999)
    assert even["centres"][0] == pytest.approx(-8 + 0.005)
    assert even["centres"][1] - even["centres"][0] == pytest.approx(0.01)
    assert "Igor bins" in igor["note"] and "even bins" in even["note"]
    assert data.tail_rows == 0                          # a .h5: no block column tail
    assert ("1d", 1000, 11, "igor", 0, GATE) in data.cache
    assert ("1d", 1000, 11, "even", 0, GATE) in data.cache
    assert abs(igor["peak"] - even["peak"]) < 0.02      # the same peak, either binning


def test_the_command_line_writes_the_three_pictures(session_file, tmp_path, capsys):
    out = tmp_path / "figs"
    f = str(session_file)
    assert plot.main([f, "1D", "--save", "--out", str(out)]) == 0
    assert plot.main([f, "2D", "--save", "--out", str(out), "--vmax", "20"]) == 0
    assert plot.main([f, "--save", "--out", str(out)]) == 0
    assert plot.main([f, "-2", "--save", "--out", str(out)]) == 0
    names = sorted(p.name for p in out.glob("*.png"))
    stem = session_file.stem
    assert names == sorted([f"{stem}_1D.png", f"{stem}_2D.png", f"{stem}_hist.png",
                            f"{stem}_trace0002.png"])
    text = capsys.readouterr().out
    assert "4 traces" in text and "trace 2" in text and "1 G0 peak" in text
    assert plot.main([f, f, "-1", "--save", "--out", str(out)]) == 2   # one file per trace


def test_figure_hands_each_knob_to_the_right_histogram(session_file):
    import matplotlib
    matplotlib.use("Agg")
    data = plot.load([session_file])
    fig = plot.figure(data, "both", bins=200, xbins=40, ybins=30, cmap="magma",
                      colorbar=False, igor_bins=False)
    assert len(fig.axes) == 2                          # no colorbar axes
    assert ("1d", 200, 11, "even", 0, GATE) in data.cache
    assert ("2d", 40, 30, (-0.5, 2.0), (-7.0, 1.0), 0.5) in data.cache
    plot.figure(data, "1d", fig=fig, floor_gate=False)
    assert ("1d", 1000, 11, "igor", 0, None) in data.cache


# --------------------------------------------------------------------------
# The legacy Igor export and the .txt table
# --------------------------------------------------------------------------

def _block_files(session_file, tmp_path):
    """A legacy Igor block (NaN blank rows) and a .txt table written from the
    session's traces."""
    pytest.importorskip("igor2")
    with storage.Session(session_file) as s:
        traces = list(s.conductances())
        cfg = s.cfg
    ibw = storage.save_igor_block(tmp_path / "PullOut_0001.ibw", cfg, traces,
                                  start_piezo_v=[2.0] * len(traces))
    txt, _info = storage.save_txt_block(tmp_path / "clean_gold_table.txt", cfg, traces)
    return ibw, txt, traces


def test_an_igor_block_loads_as_the_same_traces(session_file, tmp_path):
    ibw, txt, traces = _block_files(session_file, tmp_path)
    igor = plot.load([ibw])
    assert igor.n == len(traces)
    assert np.allclose(igor.traces[0], traces[0], rtol=1e-6, atol=1e-9)   # single precision
    assert igor.cfg.ramp.pull_length_nm == pytest.approx(RigConfig().ramp.pull_length_nm)
    assert igor.disp_nm.size == traces[0].size and igor.disp_nm[1] > igor.disp_nm[0]
    # Igor's axis: linspace(0, Size, N) from the block's own slot 0, end point included
    assert igor.disp_nm[0] == 0.0 and igor.disp_nm[-1] == pytest.approx(RigConfig().ramp.pull_length_nm)
    assert igor.numbers == list(range(1, len(traces) + 1))   # no block number in the name
    table = plot.load([txt])
    assert table.n == len(traces) and np.allclose(table.traces[1], traces[1], rtol=1e-5)
    # an Igor wave with no parameter tail (a bare trace) is taken whole
    bare = storage.write_ibw(tmp_path / "bare.ibw", "bare", np.asarray(traces[0]))
    assert plot.load([bare]).traces[0].size == traces[0].size


def test_the_three_kinds_mix_in_one_histogram(session_file, tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    ibw, txt, traces = _block_files(session_file, tmp_path)
    data = plot.load([session_file, ibw, txt])
    assert data.n == 3 * len(traces) and len(data.disps) == data.n
    assert "3 files" in data.name
    # the Igor-layout block alone cuts over its 22 tail rows; mixed with .h5/.txt traces, not
    assert plot.load([ibw]).tail_rows == 22 and data.tail_rows == 0
    fig = Figure()
    info = plot.hist_1d(fig.add_subplot(121), data)
    info2 = plot.hist_2d(fig.add_subplot(122), data, xbins=40, ybins=40)
    assert np.isfinite(info["peak"]) and info2["max"] > 0


def test_the_command_line_takes_igor_and_text_files(session_file, tmp_path, capsys):
    ibw, txt, _traces = _block_files(session_file, tmp_path)
    out = tmp_path / "figs"
    assert plot.main([str(ibw), "1D", "--save", "--out", str(out)]) == 0
    assert plot.main([str(txt), "2D", "--save", "--out", str(out)]) == 0
    assert plot.main([str(ibw), "-2", "--save", "--out", str(out)]) == 0   # a block's trace
    names = sorted(p.name for p in out.glob("*.png"))
    assert names == sorted(["PullOut_0001_1D.png", "clean_gold_table_2D.png",
                            "PullOut_0001_trace0002.png"])
    assert "trace 2" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        plot.parse([str(tmp_path / "x.csv"), "1D"])


# --------------------------------------------------------------------------
# Igor's day folder
# --------------------------------------------------------------------------

def test_a_day_folder_loads_every_block_in_order_with_igors_axes(day_folder):
    data = plot.load([day_folder])
    assert data.n == N_DAY and data.numbers == list(range(1, N_DAY + 1))
    assert data.name == day_folder.name
    assert data.traces[0].dtype == np.float32 and data.traces[0].size == N_PTS
    assert np.allclose(data.traces[149], _gold_like(150), rtol=1e-6, atol=1e-12)
    # each trace's axis is Igor's SetScale/I: linspace(0, Size, N), end point included
    d = data.disps[200]
    assert d.size == N_PTS and d[0] == 0.0 and d[-1] == 5.0
    assert d[1] == pytest.approx(5.0 / (N_PTS - 1))
    assert data.disps[0] is data.disps[1]               # one array shared by equal sizes
    assert data.cfg.ramp.pull_length_nm == 5.0 and data.cfg.ramp.pull_rate_nm_per_s == 20.0
    assert data.cfg.ramp.bias_v == pytest.approx(0.6)
    assert data.cfg.ramp.sample_rate_hz == pytest.approx(N_PTS * 20.0 / 5.0)
    # Igor's block column has 22 rows beyond the trace; the 1D histogram's cut counts them
    assert data.tail_rows == igor_scheme.TAIL_ROWS == 22
    # a block file alone, numbered by its block
    one = plot.load([day_folder / "PullOutConductanceBlock_2.ibw"])
    assert one.n == 100 and one.numbers == list(range(101, 201))
    assert np.array_equal(one.traces[49], data.traces[149])
    assert one.tail_rows == 22
    partial = plot.load([day_folder / "PullOutConductanceBlock_3.ibw"])
    assert partial.n == 30 and partial.numbers == list(range(201, 231))


def test_a_folder_is_read_one_block_at_a_time_and_each_block_once(day_folder, monkeypatch):
    reads, alive = [], []
    real = igor_scheme.read_block

    def counting(folder, k, companions=True):
        # the block read before this one has been converted and dropped already:
        # at most one float64 block is alive while a day loads
        assert all(ref() is None for ref in alive), f"block {reads[-1]} is still held"
        b = real(folder, k, companions=companions)
        reads.append(int(k))
        alive.append(weakref.ref(b))
        return b

    monkeypatch.setattr(plot.igor_scheme, "read_block", counting)
    whole = plot.load([day_folder])
    assert reads == [1, 2, 3] and whole.n == N_DAY
    assert all(t.dtype == np.float32 and t.flags.c_contiguous for t in whole.traces)
    # overlapping and adjacent ranges: each block is read once and a trace in
    # two ranges is loaded once
    reads.clear()
    data = plot.load([day_folder], traces=[(1, 60), (41, 120), (121, 130)])
    assert reads == [1, 2] and data.numbers == list(range(1, 131))
    assert "traces 1-60,41-120,121-130" in data.name
    reads.clear()
    assert plot.load([day_folder], blocks=[2, 3], traces=[(150, 160), (155, 158)]).numbers \
        == list(range(150, 161))
    assert reads == [2]                                 # block 3 holds none of them: not read


def test_blocks_and_traces_pick_a_subset_of_the_folder(day_folder):
    assert plot.load([day_folder], blocks=[1, 3]).numbers == list(range(1, 101)) + list(range(201, 231))
    sub = plot.load([day_folder], traces=[(150, 260)])
    assert sub.numbers == list(range(150, 231)) and "traces 150-260" in sub.name
    both = plot.load([day_folder], blocks=[1, 2], traces=[(95, 105)])
    assert both.numbers == list(range(95, 106)) and "blocks 1-2" in both.name
    two = plot.load([day_folder], traces=[(1, 3), (229, 300)])
    assert two.numbers == [1, 2, 3, 229, 230]
    with pytest.raises(ValueError):
        plot.load([day_folder], blocks=[9])             # no such block
    with pytest.raises(ValueError):
        plot.load([day_folder], traces=[(500, 600)])
    with pytest.raises(ValueError):
        plot.from_folder(day_folder.parent)              # no blocks in it


def test_a_companion_block_stands_for_its_conductance_block(day_folder, capsys):
    cur = plot.load([day_folder / "PullOutCurrentBlock_1.ibw"])
    assert cur.n == 100 and cur.numbers == list(range(1, 101))
    assert np.allclose(cur.traces[0], _gold_like(1), rtol=1e-6, atol=1e-12)   # G/G0, not amps
    assert "companion of block 1" in capsys.readouterr().out
    assert plot.block_file_kind("PullOutExtensionBlock_12.ibw") == ("Extension", 12)
    assert plot.block_file_kind("PullOutConductanceBlockHist_1.ibw") is None
    assert plot.block_file_kind("PullOut_0001.ibw") is None


def test_a_saved_histogram_wave_is_drawn_at_its_own_scaling(day_folder):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    hist = day_folder / "PullOutConductanceBlockHist_1.ibw"
    alone = plot.load([hist])
    assert alone.n == 0 and len(alone.hist_waves) == 1
    w = alone.hist_waves[0]
    assert w.per_trace and w.name == hist.stem and w.x.size == 1000
    assert w.x[0] == -8.0 and w.x[1] - w.x[0] == pytest.approx(10 / 999)   # Igor's bin starts
    ax = Figure().add_subplot(111)
    info = plot.hist_1d(ax, alone)
    assert np.isnan(info["peak"]) and "no traces" in info["note"]
    assert list(info["wave_peaks"]) == [w.name] and abs(info["wave_peaks"][w.name]) < 0.05
    assert len(ax.lines) >= 1 and ax.get_title().endswith("saved histogram")
    # over the recomputed histogram of the same block: the two peaks agree
    both = plot.load([hist, day_folder], blocks=[1])
    assert both.n == 100 and len(both.hist_waves) == 1
    fig = Figure()
    info = plot.hist_1d(fig.add_subplot(111), both)
    assert np.isfinite(info["peak"]) and abs(info["peak"] - info["wave_peaks"][w.name]) < 0.02
    assert "1 G0 peak" in info["note"] and w.name in info["note"]
    assert len(fig.axes) == 1                             # counts per trace: the same axis
    # a Loghist of the analysis macro holds raw sums: its own right-hand axis
    counts = np.zeros(1000, dtype=np.float32)
    counts[800] = 39369.0
    loghist = storage.write_ibw(day_folder / "Loghist1_230_10_22_26.ibw", "Loghist1_230_10_22_26",
                                counts, dx=igor_scheme.HIST_DX, x0=igor_scheme.HIST_X0)
    mixed = plot.load([day_folder, loghist], blocks=[1])
    assert len(mixed.hist_waves) == 1 and not mixed.hist_waves[0].per_trace
    fig = Figure()
    plot.hist_1d(fig.add_subplot(111), mixed)
    assert len(fig.axes) == 2
    # "both" with only a saved wave draws the 1D alone; a 2D needs traces
    assert len(plot.figure(alone, "both").axes) == 1
    with pytest.raises(ValueError):
        plot.hist_2d(Figure().add_subplot(111), alone)
    loghist.unlink()                                      # keep the module fixture clean


def test_the_recomputed_histogram_is_the_block_hist_recipe(day_folder):
    """The 1D histogram of an Igor block is Igor's LogHistFromBlocks: the
    95 % cut over the column's N+22 rows, the floor gate at break_g0, Igor's
    bins -- so it lands on the block's own saved Hist wave bin for bin."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    hist = day_folder / "PullOutConductanceBlockHist_1.ibw"
    both = plot.load([hist, day_folder], blocks=[1])
    assert both.tail_rows == 22 and both.n == 100
    info = plot.hist_1d(Figure().add_subplot(111), both)
    saved = both.hist_waves[0].values
    # the same recipe as the writer's igor_scheme.block_histogram over the same columns
    b = igor_scheme.read_block(day_folder, 1, companions=False)
    expect = igor_scheme.block_histogram([b.g0[:, j] for j in range(b.n_traces)], both.cfg, 100)
    assert np.allclose(info["counts"], expect)
    # and the saved wave, written from the float64 traces, read back as float32
    assert np.abs(info["counts"] - saved).max() < 0.05 and saved.sum() > 100
    assert info["counts"].sum() == pytest.approx(saved.sum(), rel=1e-3)
    # the same curve, the saved one drawn at Igor's bin starts: peaks half a bin apart
    assert info["peak"] - info["wave_peaks"][both.hist_waves[0].name] == pytest.approx(
        igor_scheme.HIST_DX / 2, abs=2e-3)
    assert "floor gate 0.0005 G0" in info["note"] and "per column of its block" in info["note"]
    # without the tail rows the cut is 21 points shorter: not the same histogram
    both.tail_rows = 0
    other = plot.hist_1d(Figure().add_subplot(111), both)
    assert not np.allclose(other["counts"], expect) and ("1d", 1000, 11, "igor", 0, GATE) in both.cache


def test_the_floor_gate_leaves_out_a_trace_that_never_reached_a_clean_floor():
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    cfg = RigConfig()
    good = _gold_like(1)                                    # its floor is ~1e-7 G0: passes
    stuck = 10 ** np.linspace(0.0, -2.0, N_PTS)             # ends at 1e-2 G0: never a clean floor
    disp = np.linspace(0.0, 5.0, N_PTS)
    data = plot.Data([good, stuck], disp, cfg, "gate")
    ax = Figure().add_subplot(111)
    gated = plot.hist_1d(ax, data)
    free = plot.hist_1d(ax, data, floor_gate=False)
    alone = plot.hist_1d(ax, plot.Data([good], disp, cfg, "good"))
    assert np.allclose(gated["counts"], alone["counts"])    # the stuck trace is left out ...
    assert not np.allclose(free["counts"], alone["counts"])  # ... unless the gate is off
    window = (free["centres"] > -1.5) & (free["centres"] < -0.5)
    assert free["counts"][window].sum() > 1.5 * gated["counts"][window].sum()
    assert f"floor gate {GATE:g} G0" in gated["note"] and "no floor gate" in free["note"]
    assert ("1d", 1000, 11, "igor", 0, GATE) in data.cache and ("1d", 1000, 11, "igor", 0, None) in data.cache


def test_a_trace_of_the_day_shows_its_companions_beside_the_block_histogram(day_folder, capsys):
    import matplotlib
    matplotlib.use("Agg")
    fig, info = plot.trace_figure(day_folder, 150)
    assert info["number"] == 150 and info["block"] == 2 and info["column"] == 49
    assert info["n"] == N_DAY and info["index"] == 49
    assert info["verdict"].accepted and list(info["numbers"][:2]) == [101, 102]
    # conductance + voltage + current + extension on the left, the histogram on the
    # right (plots.plot_trace also keeps a hidden right-hand axis of its own)
    axes = [ax for ax in fig.axes if ax.get_visible()]
    assert len(axes) == 5
    assert "trace 150" in axes[0].get_title() and "block 2" in axes[0].get_title()
    labels = [ax.get_ylabel() for ax in axes]
    assert any("mV" in s for s in labels) and any("nA" in s for s in labels)
    assert any("nm" in s and "readback" in s for s in labels)
    volt_ax = next(ax for ax in fig.axes if "mV" in ax.get_ylabel())
    assert np.allclose(volt_ax.lines[0].get_ydata(), 600.0)                 # 0.6 V in mV
    ext_ax = next(ax for ax in fig.axes if "readback" in ax.get_ylabel())
    assert ext_ax.lines[0].get_ydata()[0] == pytest.approx(1000.0, abs=1e-3)
    assert ext_ax.lines[0].get_xdata()[-1] == 5.0                            # Igor's axis
    hist_ax = axes[-1]
    assert "block 2" in hist_ax.get_title() and len(hist_ax.lines) >= 2   # recomputed + saved Hist
    # the same trace through its block file, or through a companion file
    _fig, info2 = plot.trace_figure(day_folder / "PullOutConductanceBlock_2.ibw", 150)
    assert info2["number"] == 150 and info2["column"] == 49 and info2["n"] == 100
    _fig, info3 = plot.trace_figure(day_folder / "PullOutExtensionBlock_2.ibw", 150)
    assert info3["number"] == 150
    # a small number on a block file is the position in the block
    _fig, info4 = plot.trace_figure(day_folder / "PullOutConductanceBlock_2.ibw", 5)
    assert info4["number"] == 105 and info4["column"] == 4
    assert "taking -5 as the 5th trace of the block, trace 105" in capsys.readouterr().out
    # the partial block: trace 230 is there, 231 is not; nor is a block that does not exist
    assert plot.trace_figure(day_folder, 230)[1]["column"] == 29
    with pytest.raises(ValueError):
        plot.trace_figure(day_folder, 231)
    with pytest.raises(ValueError):
        plot.trace_figure(day_folder, 1000)
    with pytest.raises(ValueError):
        plot.trace_figure(day_folder.parent, 1)


def test_the_command_line_draws_a_day_folder(day_folder, tmp_path, capsys):
    out = tmp_path / "figs"
    f = str(day_folder)
    assert plot.main([f, "1D", "--blocks", "1-2", "--save", "--out", str(out)]) == 0
    assert plot.main([f, "2D", "--traces", "1-50", "--save", "--out", str(out)]) == 0
    assert plot.main([f, "--save", "--out", str(out)]) == 0
    assert plot.main([f, "-150", "--save", "--out", str(out)]) == 0
    assert plot.main([f, str(day_folder / "PullOutConductanceBlockHist_1.ibw"), "1D",
                      "--blocks", "1", "--save", "--out", str(out)]) == 0
    stem = day_folder.name
    names = sorted(p.name for p in out.glob("*.png"))
    assert names == sorted([f"{stem}_1D.png", f"{stem}_2D.png", f"{stem}_hist.png",
                            f"{stem}_trace0150.png"])
    text = capsys.readouterr().out
    assert "200 traces" in text and "50 traces" in text and f"{N_DAY} traces" in text
    assert "trace 150 (block 2, column 50; accepted)" in text
    assert "1 saved histogram wave" in text and "PullOutConductanceBlockHist_1: 1 G0 peak" in text
    # with no --out the PNG goes inside the day folder
    assert plot.main([f, "1D", "--blocks", "3", "--save"]) == 0
    png = day_folder / f"{stem}_1D.png"
    assert png.exists()
    png.unlink()
    # the options between the folder and the word, as chapter 18 writes them
    assert plot.main([f, "--blocks", "1", "1D", "--save", "--out", str(out)]) == 0
    assert plot.main([f, "--traces", "1-50", "--no-floor-gate", "2D", "--save", "--out", str(out)]) == 0
    assert plot.main([f, "--blocks", "2", "-150", "--save", "--out", str(out)]) == 0
    assert plot.main([f, "1D", "--no-floor-gate", "--save", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "100 traces" in text and "trace 150 (block 2" in text
    notes = [line for line in text.splitlines() if line.startswith("1D: ")]
    assert f"floor gate {GATE:g} G0" in notes[0] and "no floor gate" in notes[-1]


def test_load_errors_are_one_line_on_stderr_not_a_traceback(day_folder, tmp_path, capsys):
    out = tmp_path / "figs"
    f = str(day_folder)
    assert plot.main([f, "1D", "--blocks", "9", "--save", "--out", str(out)]) == 2   # no such block
    err = capsys.readouterr().err
    assert err.startswith("plot.py: ") and "no trace matches" in err and "Traceback" not in err
    assert plot.main([f, "-1000", "--save", "--out", str(out)]) == 2                 # no such trace
    err = capsys.readouterr().err
    assert err.startswith("plot.py: ") and "block 10" in err
    assert plot.main([str(tmp_path), "1D", "--save", "--out", str(out)]) == 2        # a folder with no blocks
    assert "PullOutConductanceBlock_k.ibw" in capsys.readouterr().err
    hist = str(day_folder / "PullOutConductanceBlockHist_1.ibw")
    assert plot.main([hist, "2D", "--save", "--out", str(out)]) == 2                 # 2D of a saved wave alone
    assert "no traces for a 2D histogram" in capsys.readouterr().err
    assert not out.exists() or not list(out.glob("*.png"))


# --------------------------------------------------------------------------
# The real July 2026 Igor data on the NAS
# --------------------------------------------------------------------------

@pytest.mark.skipif(not NAS_DAY.is_dir(), reason="the NAS day folder is not mounted")
def test_the_july_2026_day_folder_plots(tmp_path, capsys):
    pytest.importorskip("igor2")
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    assert len(igor_scheme.list_blocks(NAS_DAY)) == 300          # the day: 300 blocks
    data = plot.load([NAS_DAY], blocks=[1, 2])
    assert data.n == 200 and data.numbers == list(range(1, 201))
    assert all(t.size == 10000 and t.dtype == np.float32 for t in data.traces)
    assert data.disps[0][-1] == 5.0 and data.disps[0].size == 10000
    assert data.cfg.ramp.pull_length_nm == 5.0 and data.cfg.ramp.bias_v == pytest.approx(0.6)
    assert data.cfg.ramp.sample_rate_hz == pytest.approx(40_000.0)
    assert data.tail_rows == 22
    info = plot.hist_1d(Figure().add_subplot(111), data)
    assert np.isfinite(info["peak"]) and info["counts"].sum() > 0
    assert f"floor gate {GATE:g} G0" in info["note"]
    out = tmp_path / "figs"
    f = str(NAS_DAY)
    assert plot.main([f, "1D", "--blocks", "1-2", "--save", "--out", str(out)]) == 0
    assert plot.main([f, "--blocks", "1-2", "2D", "--save", "--out", str(out)]) == 0   # chapter 18's order
    assert (out / "07_16_26_1D.png").exists() and (out / "07_16_26_2D.png").exists()
    assert plot.main([f, "-205", "--save", "--out", str(out)]) == 0
    assert (out / "07_16_26_trace0205.png").exists()
    text = capsys.readouterr().out
    assert "200 traces" in text and "trace 205 (block 3, column 5" in text
    # trace 205 with Igor's companions: voltage, current and extension panels
    fig, info = plot.trace_figure(NAS_DAY, 205)
    assert info["block"] == 3 and info["column"] == 4
    assert len([ax for ax in fig.axes if ax.get_visible()]) == 5
