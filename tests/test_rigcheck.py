"""rigcheck.py: the bench window's pieces, and the window itself opening,
running its smoke sequence on the pretend card and closing."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import rigcheck                                     # noqa: E402


def test_waveforms_are_what_the_boxes_say():
    rate, n = 1000.0, 1000
    dc = rigcheck.waveform("DC", 2.5, 2.5, 10, 0, rate, n)
    assert dc.shape == (n,) and np.all(dc == 2.5)
    sine = rigcheck.waveform("sine", 1.0, 1.0, 10, 0.5, rate, n)
    assert sine.max() == pytest.approx(1.5, abs=1e-3)
    assert sine.min() == pytest.approx(-0.5, abs=1e-3)
    assert sine[0] == pytest.approx(0.5)               # starts at the offset
    square = rigcheck.waveform("square", 2.0, 2.0, 5, 0, rate, n)
    assert set(np.round(square, 6)) == {-2.0, 2.0}
    # a whole-Hz frequency makes a one-second buffer seamless
    assert rigcheck.waveform("sine", 1, 1, 7.4, 0, rate, n)[-1] == pytest.approx(
        rigcheck.waveform("sine", 1, 1, 7, 0, rate, n)[-1])


def test_the_pretend_card_loops_outputs_back_to_inputs():
    d = rigcheck.SimDaq()
    devs = d.devices()
    assert devs[0]["name"] == "Dev1" and len(devs[0]["ai"]) == 32 and len(devs[0]["ao"]) == 4
    assert "self-test passed" in d.self_test("Dev1")
    assert "USB-6453" in d.details("Dev1")
    d.drive("Dev1", {"Dev1/ao1": np.full(50_000, 2.5)}, 50_000.0)
    data = d.read(["Dev1/ai1", "Dev1/ai5"], "card default", 10.0, 10_000.0, 200)
    assert data.shape == (2, 200)
    assert data[0].mean() == pytest.approx(2.5, abs=0.01)     # ai1 sees ao1
    assert abs(data[1].mean()) < 0.01                        # ai5 sees noise
    assert "0 V" in d.zero("Dev1", ["Dev1/ao1"])
    assert abs(d.read(["Dev1/ai1"], "card default", 10.0, 10_000.0, 100).mean()) < 0.01


def test_the_bench_window_opens_runs_and_closes():
    tk = pytest.importorskip("tkinter")
    try:
        tk.Tk().destroy()
    except tk.TclError as exc:
        pytest.skip(f"no Tk display: {exc}")
    root_dir = Path(__file__).resolve().parents[1]
    res = subprocess.run([sys.executable, str(root_dir / "rigcheck.py"), "--simulate",
                          "--autoclose", "4.5"],
                         capture_output=True, text=True, timeout=120, cwd=root_dir)
    assert res.returncode == 0, res.stderr[-3000:]
    assert "Traceback" not in res.stderr, res.stderr[-3000:]
    assert "driving ao0, ao1" in res.stderr                 # the smoke sequence ran
    assert "Keithley connected" in res.stderr
    assert "moved apart" in res.stderr
