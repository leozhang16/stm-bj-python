"""rigcheck.py: the bench window's pieces, and the window itself opening,
running its smoke sequence on the pretend card and closing."""
from __future__ import annotations

import subprocess
import sys
import time
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


def test_a_ramp_is_a_straight_line_at_the_volts_a_second_asked_for():
    # the sample rate keeps two samples at most 0.1 mV apart
    rate = rigcheck.ramp_rate(0.1, 50_000.0)
    assert rate == 1000.0
    assert rigcheck.ramp_rate(100.0, 50_000.0) == 50_000.0     # never above the rate box
    assert rigcheck.ramp_rate(0.001, 50_000.0) == 100.0        # never below 100 S/s
    up = rigcheck.ramp_wave(0.0, 1.0, 0.1, rate)
    assert up.size == 10_001 and up[0] == 0.0 and up[-1] == 1.0   # 10 s; it ends on the end
    assert np.allclose(np.diff(up) * rate, 0.1)                # volts a second
    down = rigcheck.ramp_wave(2.0, -1.0, 0.5, 1000.0)
    assert down[0] == 2.0 and down[-1] == -1.0
    assert np.allclose(np.diff(down) * 1000.0, -0.5)
    both = rigcheck.ramp_wave(0.0, 1.0, 0.1, rate, back=True)
    assert both.size == 20_001
    assert both[0] == 0.0 and both[10_000] == 1.0 and both[-1] == 0.0
    assert np.allclose(np.abs(np.diff(both)) * rate, 0.1)
    for bad in ((1.0, 1.0, 0.1), (0.0, 1.0, 0.0), (0.0, 1.0, -1.0)):
        with pytest.raises(ValueError):
            rigcheck.ramp_wave(*bad, rate)
    with pytest.raises(ValueError, match="too long"):
        rigcheck.ramp_wave(0.0, 10.0, 1e-7, 100.0)             # years


def test_where_a_wave_played_once_has_got_to():
    wave = rigcheck.ramp_wave(0.0, 1.0, 1.0, 1000.0)           # 1 s, 1001 samples
    assert rigcheck.played_once(wave, 1000.0, 0.0) == (0.0, 0.0)
    t, v = rigcheck.played_once(wave, 1000.0, 0.25)
    assert t == pytest.approx(0.25) and v == pytest.approx(0.25)
    # past its end it stays on the last sample; before its start, on the first
    assert rigcheck.played_once(wave, 1000.0, 7.0) == (1.0, 1.0)
    assert rigcheck.played_once(wave, 1000.0, -3.0) == (0.0, 0.0)


def test_what_an_output_may_not_do():
    refusal = rigcheck.output_refusal
    span = (0.0, 10.0)                                        # the piezo's range
    assert refusal("Dev1/ao3", 0.0, 1.0, 5.0, False, None, span) is None
    assert "exceed the limit of +/-5 V" in refusal("Dev1/ao3", 0.0, 6.0, 5.0, False, None, span)
    # below 0 V only with the box ticked
    assert "goes below 0 V" in refusal("Dev1/ao3", -1.0, 1.0, 5.0, False, None, span)
    assert refusal("Dev1/ao3", -1.0, 1.0, 5.0, True, None, span) is None
    # the piezo output never leaves its range, box or no box, limit or no limit
    assert "PIEZO" in refusal("Dev1/ao1", -0.5, 1.0, 5.0, True, "dev1/ao1", span)
    assert "PIEZO" in refusal("Dev1/ao1", -0.001, -0.001, 5.0, True, "Dev1/ao1", span)
    assert "PIEZO" in refusal("Dev1/ao1", 0.0, 10.5, 20.0, True, "Dev1/ao1", span)
    assert refusal("Dev1/ao1", 0.0, 4.0, 5.0, False, "Dev1/ao1", span) is None
    # and it is only the piezo output that the rule is about
    assert refusal("Dev1/ao3", -1.0, 1.0, 5.0, True, "Dev1/ao1", span) is None


def test_the_pretend_card_plays_a_ramp_once_and_holds_its_end():
    d = rigcheck.SimDaq()
    wave = rigcheck.ramp_wave(0.0, 2.0, 20.0, 10_000.0)        # 0.1 s
    granted = d.play_once("Dev1", {"Dev1/ao1": wave,
                                   "Dev1/ao2": np.full(wave.size, 0.7)}, 10_000.0)
    assert granted == 10_000.0
    first = d.read(["Dev1/ai1"], "card default", 10.0, 10_000.0, 200)[0]
    assert first.mean() < 1.0 and first[-1] > first[0] + 0.2  # on its way up
    time.sleep(0.15)
    data = d.read(["Dev1/ai1", "Dev1/ai2"], "card default", 10.0, 10_000.0, 200)
    assert data[0].mean() == pytest.approx(2.0, abs=0.01)     # stays at the end
    assert data[1].mean() == pytest.approx(0.7, abs=0.01)     # the other output held
    # a continuous output afterwards repeats again, and zero is zero
    d.drive("Dev1", {"Dev1/ao1": np.full(10_000, 1.5)}, 10_000.0)
    assert d.read(["Dev1/ai1"], "card default", 10.0, 10_000.0, 100).mean() == \
        pytest.approx(1.5, abs=0.01)
    d.zero("Dev1", ["Dev1/ao1"])
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
    # a sine that goes below 0 V was refused until the box was ticked
    assert "ao0: -1 to 1 V goes below 0 V" in res.stderr
    # the ramp: started, held half-way, started again and run to its end
    assert "ramping ao2 from 0 V to 1 V at 2 V/s: 0.5 s, ao0 held at 0.5 V, ao1 held at 2.5 V" \
        in res.stderr
    assert "ramp stopped: ao2 held at about" in res.stderr
    assert "ramp done: ao2 holds 1 V" in res.stderr
    assert "all outputs at 0 V" in res.stderr              # and the outputs zeroed
    assert "Keithley connected" in res.stderr
    assert "moved apart" in res.stderr
