"""plot.py: the standalone plots of a saved session, and the window drawing
the same picture through it."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import plot                                        # noqa: E402
from stmlab import storage, trace                  # noqa: E402
from stmlab.config import RigConfig                # noqa: E402
from stmlab.instrument import Rig                  # noqa: E402
from stmlab.sim import SimulatedDaqSession         # noqa: E402


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


def test_the_command_line_reads_files_modes_and_trace_numbers():
    a = plot.parse(["a.h5", "1D"])
    assert [p.name for p in a.files] == ["a.h5"] and a.mode == "1d"
    assert plot.parse(["a.h5", "2d"]).mode == "2d"
    assert plot.parse(["a.h5"]).mode == "both"
    t = plot.parse(["a.h5", "-1"])
    assert t.mode == "trace" and t.trace == 1          # -1 is the first trace
    assert plot.parse(["a.h5", "-7"]).trace == 7
    assert plot.parse(["x.h5", "y.h5", "1D", "--xlim", "-6", "1"]).xlim == [-6.0, 1.0]
    with pytest.raises(SystemExit):
        plot.parse(["a.h5", "3D"])
    with pytest.raises(SystemExit):
        plot.parse(["a.h5", "-0"])
    with pytest.raises(SystemExit):
        plot.parse(["1D"])                               # no file


def test_loading_one_file_and_two_files(session_file):
    one = plot.load([session_file])
    assert one.n == 4 and one.disp_nm.size == one.traces[0].size
    assert one.name == session_file.stem
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
    assert "4 traces" in text and "trace 2" in text
    assert plot.main([f, f, "-1", "--save", "--out", str(out)]) == 2   # one file per trace


def test_figure_hands_each_knob_to_the_right_histogram(session_file):
    import matplotlib
    matplotlib.use("Agg")
    data = plot.load([session_file])
    fig = plot.figure(data, "both", bins=200, xbins=40, ybins=30, cmap="magma",
                      colorbar=False)
    assert len(fig.axes) == 2                          # no colorbar axes
    assert ("1d", 200, 11) in data.cache and ("2d", 40, 30, (-0.5, 2.0), (-7.0, 1.0), 0.5) in data.cache


def _block_files(session_file, tmp_path):
    """An Igor block and a .txt table written from the session's traces."""
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
