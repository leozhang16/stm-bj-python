"""stmlab.igor_scheme: Igor's day-folder saving scheme, written and read back.

Synthetic traces are short (N = 400) so the whole file runs in seconds; the
one test against the real July 2026 Igor data on the NAS is skipped when
that folder is not mounted.
"""

from __future__ import annotations

import logging
import struct
import time
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

pytest.importorskip("igor2")
from igor2 import binarywave                        # noqa: E402

from stmlab import analysis, igor_scheme, storage, trace   # noqa: E402
from stmlab.config import G0_SIEMENS, RigConfig           # noqa: E402
from stmlab.igor_scheme import (BLOCK, HIST_DX, HIST_POINTS, HIST_X0,     # noqa: E402
                                IGOR_EPOCH_OFFSET, PARAM_SLOTS, TAIL_ROWS,
                                IgorDayWriter, IgorTrace, SaveFlags,
                                igor_datetime, unix_from_igor_datetime)

NAS_DAY = Path("/Users/ly666/Library/CloudStorage/SynologyDrive-SynNAS/"
               "Masha_Research/Summer_2026/Experiment/Raw_data/07_16_26")

N = 400
# A fixed moment: 22 Oct 2026, 14:30 local time.
WHEN = time.mktime((2026, 10, 22, 14, 30, 0, 0, 0, -1))


def _cfg() -> RigConfig:
    cfg = RigConfig()
    cfg.ramp.pull_length_nm = 5.0
    cfg.ramp.pull_rate_nm_per_s = 20.0
    cfg.ramp.sample_rate_hz = N / (5.0 / 20.0)          # so a pull is N points
    cfg.ramp.bias_v = 0.6
    cfg.keithley.gain_exponent = 6
    cfg.keithley.suppress_const = -3.38            # Igor G_CurrentSuppressConst
    cfg.keithley.series_resistance_ohm = 1e5
    return cfg


def _record(cfg: RigConfig, number: int, n: int = N, with_sense: bool = True
            ) -> trace.TraceRecord:
    """A gold-like pull as raw volts: from ~18 G0 down to the noise floor."""
    rng = np.random.default_rng(number)
    g0 = 10 ** np.linspace(1.25, -6.0, n) + rng.normal(0, 1e-7, n)
    g0[:40] = 18.5                                      # metallic contact
    g0[60:120] = 1.0 + rng.normal(0, 0.02, 60)          # the 1 G0 plateau
    v_junction = cfg.ramp.bias_v * np.ones(n)
    current_a = g0 * G0_SIEMENS * v_junction
    current_v = current_a * cfg.cal.preamp_gain_v_per_a + cfg.cal.current_zero_v
    voltage_v = v_junction / cfg.cal.voltage_input_sign  # what ai0 reads
    sense_v = None
    if with_sense:
        # The readback walks 5 nm over the pull, from 1000 nm.
        sense_v = (1000.0 - np.linspace(0, 5, n)) / cfg.cal.sense_nm_per_volt \
            + cfg.cal.sense_zero_v
    return trace.TraceRecord(index=number - 1, voltage_v=voltage_v,
                             current_v=current_v, delay_samples=12,
                             start_piezo_v=4.0 + 0.001 * number, bias_v=cfg.ramp.bias_v,
                             sample_rate_hz=cfg.ramp.sample_rate_hz,
                             timestamp=WHEN + 10.0 * number,
                             piezo_sense_v=sense_v)


def _igor_trace(cfg: RigConfig, number: int, **kw) -> IgorTrace:
    return IgorTrace.from_record(_record(cfg, number, **kw), cfg)


def _wave(path):
    w = binarywave.load(str(path))["wave"]
    return w["wData"], w["wave_header"], w.get("note", b"")


def _write_ibw_v2(path, name: str, data, hsA: float = 1.0, hsB: float = 0.0,
                  note: bytes = b"") -> Path:
    """A version-2 Igor binary wave (Igor 2 and 3), by hand from Technical
    Note 003: BinHeader2, the 110-byte WaveHeader2 with its scalar hsA/hsB
    scaling, float32 data, 16 bytes of padding, the note."""
    data = np.asarray(data, dtype=np.float32)
    payload = data.tobytes()
    wave_header = struct.pack(
        "<h L 20s h h L 4s 4s l h d d h h h d d c c L l L 2s L L",
        2, 0, name.encode().ljust(20, b"\0"), 0, 0, 0, b"\0" * 4, b"\0" * 4,
        data.size, 0, hsA, hsB, 0, 0, 0, 0.0, 0.0, b"\0", b"\0", 0, 0, 0, b"\0\0", 0, 0)
    assert len(wave_header) == 110
    bin_header = struct.pack("<h l l l h", 2, 110 + len(payload) + 16, len(note), 0, 0)
    path = Path(path)
    path.write_bytes(bin_header + wave_header + payload + b"\0" * 16 + note)
    return path


# --------------------------------------------------------------------------
# The folder name
# --------------------------------------------------------------------------

def test_day_folder_name_for_a_fixed_time_and_setup_id():
    assert igor_scheme.day_folder_name(WHEN) == "10_22_26Merge"
    assert igor_scheme.day_folder_name(WHEN, setup_id="_B_") == "10_22_B_26Merge"
    assert igor_scheme.day_folder_name(time.mktime((2026, 7, 16, 9, 0, 0, 0, 0, -1))) \
        == "07_16_26Merge"
    # writing is always zero-padded, whatever Igor's Date() did on a 2 May
    assert igor_scheme.day_folder_name(time.mktime((2005, 5, 2, 9, 0, 0, 0, 0, -1))) \
        == "05_02_05Merge"
    assert igor_scheme.day_folder_name().endswith("Merge")    # now: no error


def test_parse_day_folder_name_takes_igor_and_hand_renamed_folders():
    assert igor_scheme.parse_day_folder_name("10_22_26Merge") == (26, 10, 22, "_")
    assert igor_scheme.parse_day_folder_name("07_16_26") == (26, 7, 16, "_")
    assert igor_scheme.parse_day_folder_name("10_22_B_26Merge") == (26, 10, 22, "_B_")
    assert igor_scheme.parse_day_folder_name("/data/07_15_26") == (26, 7, 15, "_")
    # Igor's Date() is not zero-padded on every system: MakePath's two
    # characters before the comma then give a space-padded day
    assert igor_scheme.parse_day_folder_name("05_ 2_05Merge") == (5, 5, 2, "_")
    assert igor_scheme.parse_day_folder_name("05_2_05Merge") == (5, 5, 2, "_")
    assert igor_scheme.parse_day_folder_name("5_2_05") == (5, 5, 2, "_")
    assert igor_scheme.parse_day_folder_name("05_ 2_B_05Merge") == (5, 5, 2, "_B_")
    for bad in ("2026-10-22", "clean_gold", "13_01_26", "10_32_26Merge", "",
                "10_223_26", "10_22_2026Merge"):
        assert igor_scheme.parse_day_folder_name(bad) is None


# --------------------------------------------------------------------------
# Parameters and the per-trace conversion
# --------------------------------------------------------------------------

def test_igor_parameters_fill_the_20_slots_as_igor_did():
    cfg = _cfg()
    ext = np.concatenate([np.full(1000, 1015.0), np.full(1000, 1010.5)])
    p = igor_scheme.igor_parameters(cfg, 4.0, WHEN, extension_nm=ext,
                                    vzero_mv=1.5, izero=-2e-3, bias_save=True)
    assert p.shape == (PARAM_SLOTS,)
    assert p[0] == 5.0 and p[1] == 20.0 and p[2] == 0.5
    assert p[3] == pytest.approx(cfg.cal.piezo_volts_to_nm(4.0) - 5.0)   # after the pull
    assert p[4] == 1.0
    assert p[5] == pytest.approx(4.5)                                     # StartX - StopX
    assert p[9] == 1.0                                                    # 10^(6-6) uA/V
    assert p[10] == pytest.approx(600.0)                                  # mV
    assert p[12] == 1e5 and p[13] == 5.0
    assert p[15] == 1.5 and p[16] == -2e-3
    assert p[17] == igor_datetime(WHEN)                                   # local-time DateTime
    assert p[17] == WHEN + IGOR_EPOCH_OFFSET + time.localtime(WHEN).tm_gmtoff
    assert p[18] == cfg.echem.gate_mv
    assert p[19] == pytest.approx(-0.00338)                               # const * 10^(3-6)
    assert all(p[i] == 0.0 for i in (6, 7, 8, 11, 14))                    # unused: 0, not NaN
    # no readback: slot 5 is the pull length; bias off: slot 4 is 0
    q = igor_scheme.igor_parameters(cfg, 4.0, WHEN, bias_save=False)
    assert q[5] == 5.0 and q[4] == 0.0
    cfg.keithley.gain_exponent = 8
    assert igor_scheme.igor_parameters(cfg, 4.0, WHEN)[9] == pytest.approx(1e-2)


def test_igor_datetime_is_local_seconds_since_1904_and_round_trips():
    # Igor's DateTime is the local clock, not UTC: on the July 2026 files the
    # header's modDate was mtime + 2082844800 - 14400 (EDT).
    x = igor_datetime(WHEN)
    assert x == WHEN + IGOR_EPOCH_OFFSET + time.localtime(WHEN).tm_gmtoff
    assert time.gmtime(x - IGOR_EPOCH_OFFSET)[:6] == time.localtime(WHEN)[:6]   # reads as 14:30
    assert time.gmtime(x - IGOR_EPOCH_OFFSET).tm_hour == 14
    assert unix_from_igor_datetime(x) == WHEN
    winter = time.mktime((2026, 1, 15, 9, 0, 0, 0, 0, -1))
    summer = time.mktime((2026, 7, 16, 11, 41, 52, 0, 0, -1))
    for ts in (winter, summer, WHEN + 0.25):
        assert unix_from_igor_datetime(igor_datetime(ts)) == pytest.approx(ts, abs=1e-6)
    # the IBW header dates and the legacy export run on the same clock
    assert storage.igor_datetime is igor_datetime
    assert storage.igor_parameters(_cfg(), 0.0, WHEN)[17] == igor_datetime(WHEN)


def test_from_record_converts_raw_volts_to_igors_units():
    cfg = _cfg()
    rec = _record(cfg, 1)
    t = IgorTrace.from_record(rec, cfg, vzero_mv=0.7, izero=1e-4, bias_save=False)
    assert t.n == N
    assert np.allclose(t.g0, rec.conductance_g0(cfg))
    assert np.allclose(t.voltage_v, 0.6)                     # sign-corrected junction voltage
    assert np.allclose(t.current_a, t.g0 * G0_SIEMENS * 0.6)
    assert np.allclose(t.extension_nm, 1000.0 - np.linspace(0, 5, N))
    assert t.piezo_wave_v[0] == 0.0 and t.piezo_wave_v[-1] < 0  # starts at 0, goes negative
    assert t.piezo_wave_v[-1] == pytest.approx(-rec.displacement_nm(cfg)[-1]
                                               / cfg.cal.piezo_nm_per_volt)
    assert t.params[15] == 0.7 and t.params[16] == 1e-4 and t.params[4] == 0.0
    assert t.params[5] == pytest.approx(np.mean(t.extension_nm[:1000])
                                        - np.mean(t.extension_nm[-1000:]))
    bare = IgorTrace.from_record(_record(cfg, 2, with_sense=False), cfg)
    assert bare.extension_nm is None and bare.params[5] == 5.0


# --------------------------------------------------------------------------
# The block files
# --------------------------------------------------------------------------

def test_conductance_block_has_igors_layout(tmp_path):
    cfg = _cfg()
    traces = [_igor_trace(cfg, i) for i in range(1, 4)]
    files = igor_scheme.write_block_files(tmp_path, 1, traces, cfg, SaveFlags(),
                                          note="pullout v65; traces 1-3")
    names = sorted(p.name for p in files)
    assert names == sorted(["PullOutConductanceBlock_1.ibw", "PullOutVoltageBlock_1.ibw",
                            "PullOutCurrentBlock_1.ibw", "PullOutExtensionBlock_1.ibw",
                            "PullOutConductanceBlockHist_1.ibw"])
    data, header, note = _wave(tmp_path / "PullOutConductanceBlock_1.ibw")
    assert data.shape == (N + TAIL_ROWS, BLOCK) and data.dtype == np.float32
    assert header["bname"].split(b"\0")[0] == b"PullOutConductanceBlock_1"   # name = stem
    assert header["sfA"][0] == 1.0 and header["sfB"][0] == 0.0                # no scaling
    assert note == b"pullout v65; traces 1-3"
    for c in range(3):
        assert np.allclose(data[:N, c], traces[c].g0, rtol=1e-6, atol=1e-12)
        assert data[N, c] == 0.0 and data[N + 1, c] == 0.0                   # exactly 0
        assert np.allclose(data[N + 2:, c], traces[c].params.astype(np.float32))
        assert all(data[N + 2 + s, c] == 0.0 for s in (6, 7, 8, 11, 14))
    assert np.isnan(data[:, 3:]).all()                                       # not yet taken
    assert data[N + 2, 0] == 5.0 and data[N + 3, 0] == 20.0 and data[N + 12, 0] == 600.0


def test_companions_have_the_setscale_i_scaling(tmp_path):
    cfg = _cfg()
    traces = [_igor_trace(cfg, i) for i in range(1, 3)]
    igor_scheme.write_block_files(tmp_path, 7, traces, cfg, SaveFlags())
    for kind, pick in (("voltage", lambda t: t.voltage_v), ("current", lambda t: t.current_a),
                       ("extension", lambda t: t.extension_nm)):
        path = igor_scheme.block_file(tmp_path, kind, 7)
        data, header, note = _wave(path)
        assert data.shape == (N, BLOCK) and data.dtype == np.float32
        assert header["bname"].split(b"\0")[0] == path.stem.encode()
        assert header["sfA"][0] == pytest.approx(5.0 / (N - 1))      # dx = Size/(N-1)
        assert header["sfB"][0] == 0.0 and note == b""
        assert np.allclose(data[:, 0], pick(traces[0]), rtol=1e-6)
        assert np.isnan(data[:, 2:]).all()
    # the Igor x axis of the companions ends exactly at Size
    header = _wave(igor_scheme.block_file(tmp_path, "voltage", 7))[1]
    assert header["sfB"][0] + header["sfA"][0] * (N - 1) == pytest.approx(5.0)


def test_flags_choose_the_companions_and_the_rig_without_sense_writes_none(tmp_path):
    cfg = _cfg()
    traces = [_igor_trace(cfg, 1, with_sense=False)]
    files = igor_scheme.write_block_files(tmp_path, 1, traces, cfg,
                                          SaveFlags(bias=False, current=True, sense=True,
                                                    hist=False, piezo_wave=True))
    names = sorted(p.name for p in files)
    assert names == ["PullOutConductanceBlock_1.ibw", "PullOutCurrentBlock_1.ibw",
                     "PullOutPiezoBiasWave_1.ibw"]
    data, header, _ = _wave(tmp_path / "PullOutPiezoBiasWave_1.ibw")
    assert data.shape == (N,) and data.dtype == np.float64      # Igor: Make/D, no scaling
    assert data[0] == 0.0 and data[-1] < 0 and header["sfA"][0] == 1.0


def test_hist_wave_is_igors_1000_points_divided_by_100_on_a_complete_block(tmp_path):
    cfg = _cfg()
    traces = [_igor_trace(cfg, i) for i in range(1, BLOCK + 1)]
    igor_scheme.write_block_files(tmp_path, 1, traces, cfg, SaveFlags())
    path = igor_scheme.block_file(tmp_path, "hist", 1)
    data, header, _ = _wave(path)
    assert data.shape == (HIST_POINTS,) and data.dtype == np.float32
    assert header["sfB"][0] == -8.0 and header["sfA"][0] == pytest.approx(10 / 999)
    assert header["bname"].split(b"\0")[0] == b"PullOutConductanceBlockHist_1"
    # /100: the sum of per-trace histograms over 100, bin for bin
    edges = -8 + np.arange(1001) * 10 / 999
    expected = np.zeros(HIST_POINTS)
    for t in traces:
        col = np.concatenate([t.g0, np.zeros(TAIL_ROWS)])       # Igor cut the N+22-row column
        g = analysis.boxcar(col[:int(col.size * 0.95)], 11)
        floor = np.mean(g[int(g.size * 0.95):int(g.size * 0.96) + 1])
        assert floor < cfg.ramp.break_g0
        g = analysis.boxcar(g - floor, 11)
        with np.errstate(divide="ignore", invalid="ignore"):
            logs = np.log10(g)
        expected += np.histogram(logs[np.isfinite(logs)], bins=edges)[0]
    expected /= BLOCK
    assert np.allclose(data, expected.astype(np.float32))
    assert data.sum() > 0
    # the 1 G0 plateau sits in the bin containing 0.0
    x, values = igor_scheme.read_hist_wave(path)
    assert np.allclose(x, -8 + np.arange(1000) * 10 / 999)
    assert abs(x[np.argmax(values)]) < 0.03
    # a partial block divides by the number of filled columns instead
    hist_partial = igor_scheme.block_histogram([t.g0 for t in traces[:4]], cfg, 4)
    hist_full = igor_scheme.block_histogram([t.g0 for t in traces[:4]], cfg, BLOCK)
    assert np.allclose(hist_partial * 4, hist_full * BLOCK)


def test_log_histogram_igor_bins_are_the_setscale_edges():
    rng = np.random.default_rng(0)
    traces = [10 ** rng.uniform(-6, 0.5, 2000) for _ in range(3)]
    centres, counts = analysis.log_histogram(traces, igor_bins=True)
    edges = -8 + np.arange(1001) * 10 / 999
    assert centres.size == 1000 and counts.size == 1000
    assert np.allclose(centres, 0.5 * (edges[:-1] + edges[1:]))
    assert centres[-1] > 2.0                                     # the last bin hangs past 2
    even_centres, _ = analysis.log_histogram(traces)             # default: unchanged
    assert np.allclose(even_centres, np.linspace(-8, 2, 1001)[:-1] + 0.005)


def test_log_histogram_tail_rows_makes_igors_cut_on_a_block_column():
    """Igor cut floor(0.95 * (N + 22)) points of the N+22-row block column:
    20 points more of a 10000-point trace than a plain 95 % cut."""
    cfg = _cfg()
    g0 = 10 ** np.linspace(1.0, -6.0, 10000)                   # monotonic: every log10 finite
    _, plain = analysis.log_histogram([g0], igor_bins=True, subtract_floor=False)
    _, igor_cut = analysis.log_histogram([g0], igor_bins=True, subtract_floor=False,
                                         tail_rows=TAIL_ROWS)
    assert plain.sum() == 9500
    assert igor_cut.sum() == int(0.95 * (10000 + TAIL_ROWS)) == 9520
    # the same as appending the 22 rows before the cut, the column as Igor saw it
    padded = np.concatenate([g0, np.zeros(TAIL_ROWS)])
    _, from_padded = analysis.log_histogram([padded], igor_bins=True, subtract_floor=False)
    assert np.array_equal(from_padded, igor_cut)
    # with the floor subtraction and the cutoff too; block_histogram takes this path
    _, with_floor = analysis.log_histogram([g0], igor_bins=True, zero_cutoff=cfg.ramp.break_g0,
                                           tail_rows=TAIL_ROWS)
    assert with_floor.sum() > 0
    assert np.array_equal(igor_scheme.block_histogram([g0], cfg, 1), with_floor)
    # the cut never runs past the trace
    short = np.full(100, 1e-3)
    _, capped = analysis.log_histogram([short], subtract_floor=False, tail_rows=TAIL_ROWS)
    assert capped.sum() == 100
    assert analysis.log_histogram([short], subtract_floor=False)[1].sum() == 95


def test_boxcar_bounces_at_the_ends_as_igors_smooth_b_does():
    # Igor's Smooth/B default end effect is Bounce: w[-i] = w[i], w[n-1+i] = w[n-1-i]
    x = np.arange(8.0)
    assert np.allclose(analysis.boxcar(x, 3), np.convolve(
        np.pad(x, 1, mode="reflect"), np.ones(3) / 3, mode="valid"))
    assert analysis.boxcar(x, 3)[0] == pytest.approx((1 + 0 + 1) / 3)      # not (0+0+1)/3
    assert analysis.boxcar(x, 3)[-1] == pytest.approx((6 + 7 + 6) / 3)
    assert np.allclose(analysis.boxcar(np.full(20, 2.5), 11), 2.5)        # a constant stays
    assert analysis.boxcar(x, 1).tolist() == x.tolist()


def test_per_trace_files_are_written_for_the_blocks_last_trace_when_flags_are_off(tmp_path):
    cfg = _cfg()
    traces = [_igor_trace(cfg, i) for i in range(1, BLOCK + 1)]
    flags = SaveFlags(bias=False, current=False, sense=False, hist=False)
    files = igor_scheme.write_block_files(tmp_path, 2, traces, cfg, flags)
    names = sorted(p.name for p in files)
    assert names == ["PullOutConductanceBlock_2.ibw", "PullOutCurrent_200.ibw",
                     "PullOutExtension_200.ibw", "PullOutVoltage_200.ibw"]
    for stem, values in (("PullOutExtension_200", traces[-1].extension_nm),
                         ("PullOutVoltage_200", traces[-1].voltage_v),
                         ("PullOutCurrent_200", traces[-1].current_a)):
        data, header, _ = _wave(tmp_path / f"{stem}.ibw")
        assert data.dtype == np.float64 and data.shape == (N,)
        assert header["bname"].split(b"\0")[0] == stem.encode()
        assert header["sfA"][0] == pytest.approx(5.0 / (N - 1))
        assert np.allclose(data, values)
    # a partial block writes no per-trace files
    files = igor_scheme.write_block_files(tmp_path / "p", 3, traces[:10], cfg, flags)
    assert [p.name for p in files] == ["PullOutConductanceBlock_3.ibw"]


def test_a_block_refuses_traces_of_different_lengths_and_more_than_100(tmp_path):
    cfg = _cfg()
    with pytest.raises(ValueError):
        igor_scheme.write_block_files(tmp_path, 1, [_igor_trace(cfg, 1), _igor_trace(cfg, 2, n=401)],
                                      cfg, SaveFlags())
    with pytest.raises(ValueError):
        igor_scheme.write_block_files(tmp_path, 1, [None] * 101, cfg, SaveFlags())
    assert igor_scheme.write_block_files(tmp_path, 1, [None, None], cfg, SaveFlags()) == []


# --------------------------------------------------------------------------
# The day writer: numbering, partial blocks, resume
# --------------------------------------------------------------------------

def test_two_sessions_of_70_and_80_traces_make_blocks_of_100_and_50(tmp_path):
    cfg = _cfg()
    root = tmp_path / "data"
    assert IgorDayWriter.scan(root / "10_22_26Merge") == (0, 0)

    first = IgorDayWriter(root, cfg, when=WHEN, note_fields={"version": "v65",
                                                           "experiment": "gold"})
    assert first.folder == root / "10_22_26Merge" and first.saved == 1
    assert not first.folder.exists()                       # created on first write
    numbers = [first.append(_igor_trace(cfg, i)) for i in range(1, 71)]
    assert numbers == list(range(1, 71)) and first.saved == 71
    assert not igor_scheme.block_file(first.folder, "conductance", 1).exists()  # not yet
    written = first.close()
    assert igor_scheme.block_file(first.folder, "conductance", 1) in written
    assert first.close() == []                             # nothing new to write
    assert IgorDayWriter.scan(first.folder) == (1, 70)
    partial = igor_scheme.read_block(first.folder, 1)
    assert partial.n_traces == 70 and partial.hist is not None
    note = igor_scheme.read_wave(igor_scheme.block_file(first.folder, "conductance", 1)).note
    assert note.startswith("pullout v65; experiment=gold; traces 1-70; written ")

    second = IgorDayWriter(root, cfg, when=WHEN + 3600)    # same day, later
    assert second.saved == 71 and second.n_pending == 70
    numbers = [second.append(_igor_trace(cfg, i)) for i in range(71, 151)]
    assert numbers == list(range(71, 151)) and second.saved == 151
    assert igor_scheme.block_file(second.folder, "conductance", 2).exists() is False
    second.flush()
    assert IgorDayWriter.scan(second.folder) == (2, 50)
    assert igor_scheme.list_blocks(second.folder) == [1, 2]

    blocks = igor_scheme.read_day_folder(second.folder, companions=True)
    assert [b.n_traces for b in blocks] == [100, 50]
    assert np.array_equal(np.concatenate([b.numbers for b in blocks]), np.arange(1, 151))
    b1, b2 = blocks
    assert b1.g0.shape == (N, 100) and b2.g0.shape == (N, 50)
    assert b1.voltage_v.shape == (N, 100) and b2.extension_nm.shape == (N, 50)
    # the refilled block kept the first session's traces and added the new ones
    for i in (1, 70, 71, 100):
        t = _igor_trace(cfg, i)
        j = i - 1
        assert np.allclose(b1.g0[:, j], t.g0, rtol=1e-6, atol=1e-12)
        assert np.allclose(b1.params[j], t.params.astype(np.float32))
        assert np.allclose(b1.current_a[:, j], t.current_a, rtol=1e-6)
    raw = _wave(igor_scheme.block_file(second.folder, "conductance", 1))[0]
    assert np.isfinite(raw).all()                          # a complete block: no NaN
    raw2 = _wave(igor_scheme.block_file(second.folder, "conductance", 2))[0]
    assert np.isnan(raw2[:, 50:]).all() and np.isfinite(raw2[:, :50]).all()
    # the complete block's histogram is /100, the partial one's /50
    assert b1.hist is not None and b2.hist is not None
    assert np.allclose(b1.hist, igor_scheme.block_histogram(list(b1.g0.T), cfg, 100).astype(np.float32),
                       rtol=1e-5)
    assert np.allclose(b2.hist, igor_scheme.block_histogram(list(b2.g0.T), cfg, 50).astype(np.float32),
                       rtol=1e-5)

    third = IgorDayWriter(root, cfg, when=WHEN + 7200)
    assert third.saved == 151 and third.current_block == 2 and third.n_pending == 50


def test_a_full_last_block_resumes_at_the_next_block(tmp_path):
    cfg = _cfg()
    w = IgorDayWriter(tmp_path, cfg, when=WHEN, flags=SaveFlags(hist=False))
    for i in range(1, BLOCK + 1):
        w.append(_igor_trace(cfg, i))
    assert w.flush() == []                                 # the block was written at 100
    assert IgorDayWriter.scan(w.folder) == (1, 100)
    again = IgorDayWriter(tmp_path, cfg, when=WHEN)
    assert again.saved == 101 and again.n_pending == 0
    assert again.append(_igor_trace(cfg, 101)) == 101
    with again:
        pass                                               # context exit flushes
    assert igor_scheme.read_block(w.folder, 2).numbers.tolist() == [101]


def test_a_changed_trace_length_starts_a_new_block_instead_of_corrupting_one(tmp_path):
    cfg = _cfg()
    w = IgorDayWriter(tmp_path, cfg, when=WHEN, flags=SaveFlags(hist=False))
    for i in range(1, 4):
        w.append(_igor_trace(cfg, i))
    assert w.append(_igor_trace(cfg, 4, n=500)) == 101     # block 1 written, block 2 starts
    w.close()
    b1, b2 = igor_scheme.read_day_folder(w.folder)
    assert b1.numbers.tolist() == [1, 2, 3] and b1.n_points == N
    assert b2.numbers.tolist() == [101] and b2.n_points == 500


def test_a_failed_block_write_keeps_the_numbering_and_the_pending_traces(tmp_path):
    """The NAS drops out as the 100th trace completes block 1: nothing may
    move. Before the fix ``saved`` advanced first, so the next flush filed
    the traces as block 2 (renumbered 101-200) and trace 1 was lost."""
    cfg = _cfg()
    w = IgorDayWriter(tmp_path, cfg, when=WHEN, flags=SaveFlags(hist=False))
    for i in range(1, BLOCK):
        w.append(_igor_trace(cfg, i))
    assert w.saved == BLOCK and w.n_pending == BLOCK - 1 and w._pending_k == 1
    with mock.patch.object(igor_scheme, "write_ibw", side_effect=OSError("NAS gone")):
        with pytest.raises(OSError):
            w.append(_igor_trace(cfg, BLOCK))
    assert w.saved == BLOCK and w.current_block == 1 and w._pending_k == 1
    assert w.n_pending == BLOCK - 1                        # the unsaved trace is not kept
    assert igor_scheme.list_blocks(w.folder) == []
    # the pending traces flush as block 1, numbered 1-99 ...
    files = w.flush()
    assert igor_scheme.block_file(w.folder, "conductance", 1) in files
    assert igor_scheme.list_blocks(w.folder) == [1]
    assert igor_scheme.read_block(w.folder, 1).numbers.tolist() == list(range(1, BLOCK))
    # ... and the retried 100th trace completes block 1 with the numbers 1-100
    assert w.append(_igor_trace(cfg, BLOCK)) == BLOCK
    assert w.saved == BLOCK + 1 and w.n_pending == 0 and w._pending_k is None
    assert w.flush() == []
    b = igor_scheme.read_block(w.folder, 1, companions=True)
    assert b.numbers.tolist() == list(range(1, BLOCK + 1))
    assert np.isfinite(b.g0).all() and b.voltage_v.shape == (N, BLOCK)
    assert igor_scheme.list_blocks(w.folder) == [1]
    assert w.append(_igor_trace(cfg, BLOCK + 1)) == BLOCK + 1 and w._pending_k == 2


def test_a_failed_write_on_a_resumed_block_leaves_the_disk_as_it_was(tmp_path):
    cfg = _cfg()
    first = IgorDayWriter(tmp_path, cfg, when=WHEN, flags=SaveFlags(hist=False))
    for i in range(1, BLOCK):
        first.append(_igor_trace(cfg, i))
    first.close()
    cond = igor_scheme.block_file(first.folder, "conductance", 1)
    before = cond.read_bytes()
    second = IgorDayWriter(tmp_path, cfg, when=WHEN + 60, flags=SaveFlags(hist=False))
    assert second.saved == BLOCK and second.n_pending == BLOCK - 1 and second._pending_k == 1
    with mock.patch.object(igor_scheme, "write_ibw", side_effect=OSError("NAS gone")):
        with pytest.raises(OSError):
            second.append(_igor_trace(cfg, BLOCK))
    assert second.saved == BLOCK and second.n_pending == BLOCK - 1
    assert second.flush() == []                            # memory == disk: nothing to write
    assert cond.read_bytes() == before
    assert second.append(_igor_trace(cfg, BLOCK)) == BLOCK
    assert igor_scheme.read_block(first.folder, 1).numbers.tolist() == list(range(1, BLOCK + 1))


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def test_read_day_folder_picks_blocks_and_trace_ranges(tmp_path):
    cfg = _cfg()
    w = IgorDayWriter(tmp_path, cfg, when=WHEN, flags=SaveFlags(hist=False))
    for i in range(1, 251):
        w.append(_igor_trace(cfg, i, with_sense=(i % 2 == 0)))
    w.close()
    folder = w.folder
    assert igor_scheme.list_blocks(folder) == [1, 2, 3]
    assert [b.n_traces for b in igor_scheme.read_day_folder(folder)] == [100, 100, 50]
    assert [b.k for b in igor_scheme.read_day_folder(folder, blocks=[3, 1])] == [1, 3]
    sel = igor_scheme.read_day_folder(folder, traces=(95, 205))
    assert [b.k for b in sel] == [1, 2, 3]
    assert np.array_equal(np.concatenate([b.numbers for b in sel]), np.arange(95, 206))
    assert sel[0].g0.shape == (N, 6) and sel[2].g0.shape == (N, 5)
    assert igor_scheme.read_day_folder(folder, blocks=[2], traces=(1, 50)) == []
    one = igor_scheme.read_day_folder(folder, traces=(150, 150), companions=True)[0]
    assert one.numbers.tolist() == [150] and one.columns.tolist() == [49]
    assert np.allclose(one.g0[:, 0], _igor_trace(cfg, 150).g0, rtol=1e-6, atol=1e-12)
    assert one.voltage_v.shape == (N, 1) and one.extension_nm.shape == (N, 1)
    assert one.voltage_lowres_v is None
    # SetScale/I: the displacement axis ends exactly at Size, inclusive
    assert one.displacement_nm.size == N and one.displacement_nm[-1] == 5.0
    # a trace without a readback has NaN in the extension block
    odd = igor_scheme.read_day_folder(folder, traces=(149, 149), companions=True)[0]
    assert np.isnan(odd.extension_nm).all()
    with pytest.raises(FileNotFoundError):
        igor_scheme.read_block(folder, 9)
    assert igor_scheme.read_day_folder(tmp_path / "nowhere") == []


def test_split_block_reads_the_legacy_nan_blank_export_and_igors_zero_rows(tmp_path):
    cfg = _cfg()
    rng = np.random.default_rng(1)
    traces = [10 ** rng.uniform(-6, 0.3, 300) for _ in range(4)]
    legacy = storage.save_igor_block(tmp_path / "PullOut_b000.ibw", cfg, traces,
                                     start_piezo_v=[4.8, 4.81, 4.79, 4.8])
    g0, params, filled = igor_scheme.split_block(storage.load_ibw(legacy))
    assert g0.shape == (300, 4) and params.shape == (4, PARAM_SLOTS) and filled.all()
    assert np.allclose(g0.T, np.array(traces), rtol=1e-6)
    assert params[0, 0] == pytest.approx(5.0) and params[2, 3] == pytest.approx(
        cfg.cal.piezo_volts_to_nm(4.79), rel=1e-5)
    # storage.load_igor_block goes through the same detection
    loaded = storage.load_igor_block(legacy)
    assert len(loaded["traces"]) == 4 and loaded["traces"][0].size == 300
    assert loaded["parameters"].shape == (4, PARAM_SLOTS)
    # Igor's own zero rows, with NaN columns for traces not taken
    igor_scheme.write_block_files(tmp_path, 1, [_igor_trace(cfg, i) for i in (1, 2)], cfg,
                                  SaveFlags(hist=False))
    block = storage.load_ibw(igor_scheme.block_file(tmp_path, "conductance", 1))
    g0, params, filled = igor_scheme.split_block(block)
    assert filled.tolist() == [True, True] + [False] * 98
    assert g0.shape == (N, BLOCK) and params[1, 10] == pytest.approx(600.0)
    loaded = storage.load_igor_block(igor_scheme.block_file(tmp_path, "conductance", 1))
    assert len(loaded["traces"]) == 2 and loaded["traces"][1].size == N
    assert loaded["parameters"].shape == (2, PARAM_SLOTS) and loaded["name"] == "PullOutConductanceBlock_1"


def test_a_bare_wave_or_a_companion_is_not_mistaken_for_a_block(tmp_path):
    cfg = _cfg()
    t = _igor_trace(cfg, 1)
    bare = storage.write_ibw(tmp_path / "bare.ibw", "bare", t.g0)
    with pytest.raises(ValueError):
        igor_scheme.split_block(storage.load_ibw(bare))
    assert not igor_scheme.has_parameter_tail(storage.load_ibw(bare))
    assert storage.load_igor_block(bare)["parameters"] is None          # taken whole
    assert storage.load_igor_block(bare)["traces"][0].size == N
    igor_scheme.write_block_files(tmp_path, 1, [t], cfg, SaveFlags())
    for kind in ("voltage", "current", "extension"):
        assert not igor_scheme.has_parameter_tail(
            storage.load_ibw(igor_scheme.block_file(tmp_path, kind, 1)))
    with pytest.raises(ValueError):
        igor_scheme.split_block(np.zeros(10))
    with pytest.raises(ValueError):
        igor_scheme.split_block(np.full((50, 3), np.nan))
    with pytest.raises(ValueError):
        igor_scheme.read_hist_wave(igor_scheme.block_file(tmp_path, "conductance", 1))


def test_read_hist_wave_takes_a_saved_loghist_as_igor_scaled_it(tmp_path):
    counts = np.zeros(HIST_POINTS, dtype=np.float32)
    counts[800] = 39369.0                                     # a sum over many traces
    path = storage.write_ibw(tmp_path / "Loghist6001_7000_06_29_25.ibw",
                             "Loghist6001_7000_06_29_25", counts, dx=HIST_DX, x0=HIST_X0)
    x, values = igor_scheme.read_hist_wave(path)
    assert x.size == 1000 and x[0] == -8.0 and x[-1] == pytest.approx(2.0)
    assert x[1] - x[0] == pytest.approx(10 / 999)
    assert values[800] == 39369.0 and x[800] == pytest.approx(-8 + 800 * 10 / 999)
    w = igor_scheme.read_wave(path)
    assert w.name == "Loghist6001_7000_06_29_25" and w.dx == pytest.approx(HIST_DX)


def test_read_wave_takes_a_version_2_wave_with_hsa_hsb_scaling(tmp_path):
    counts = np.zeros(HIST_POINTS, dtype=np.float32)
    counts[500] = 7.0
    path = _write_ibw_v2(tmp_path / "Loghist_old.ibw", "Loghist_old", counts,
                         hsA=HIST_DX, hsB=HIST_X0, note=b"old")
    assert binarywave.load(str(path))["version"] == 2
    w = igor_scheme.read_wave(path)
    assert w.dx == pytest.approx(HIST_DX) and w.x0 == -8.0
    assert w.name == "Loghist_old" and w.note == "old"
    assert w.data.shape == (HIST_POINTS,) and w.data[500] == 7.0
    x, values = igor_scheme.read_hist_wave(path)
    assert x[0] == -8.0 and x[500] == pytest.approx(-8 + 500 * 10 / 999) and values[500] == 7.0


def test_scan_and_read_block_survive_truncated_and_garbage_files(tmp_path, caplog):
    cfg = _cfg()
    w = IgorDayWriter(tmp_path, cfg, when=WHEN, flags=SaveFlags(piezo_wave=True))
    for i in range(1, 6):
        w.append(_igor_trace(cfg, i))
    w.close()
    folder = w.folder
    cond = igor_scheme.block_file(folder, "conductance", 1)
    good = cond.read_bytes()
    # a truncated last block (igor2: TypeError) is reported full, so nothing
    # is ever written over it, and the day continues after it
    cond.write_bytes(good[:len(good) // 2])
    with caplog.at_level(logging.WARNING, logger="stmlab.igor_scheme"):
        assert IgorDayWriter.scan(folder) == (1, BLOCK)
    assert cond.name in caplog.text and "TypeError" in caplog.text
    again = IgorDayWriter(tmp_path, cfg, when=WHEN)
    assert again.saved == BLOCK + 1 and again.n_pending == 0
    # garbage under a block name (igor2: ValueError), and an empty file
    igor_scheme.block_file(folder, "conductance", 2).write_bytes(b"not an igor wave\n" * 40)
    assert IgorDayWriter.scan(folder) == (2, BLOCK)
    assert IgorDayWriter(tmp_path, cfg, when=WHEN).saved == 2 * BLOCK + 1
    igor_scheme.block_file(folder, "conductance", 3).write_bytes(b"")
    assert IgorDayWriter.scan(folder) == (3, BLOCK)
    for k in (2, 3):
        igor_scheme.block_file(folder, "conductance", k).unlink()
    cond.write_bytes(good)                                 # block 1 is whole again
    # a torn companion, a garbage piezo wave and a garbage hist lose only
    # themselves; the ConductanceBlock stays authoritative
    volt = igor_scheme.block_file(folder, "voltage", 1)
    volt.write_bytes(volt.read_bytes()[:100])
    igor_scheme.block_file(folder, "piezo_wave", 1).write_bytes(b"garbage")
    igor_scheme.block_file(folder, "hist", 1).write_bytes(b"garbage")
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="stmlab.igor_scheme"):
        b = igor_scheme.read_block(folder, 1)
    assert b.n_traces == 5 and b.voltage_v is None and b.hist is None
    assert b.current_a.shape == (N, 5) and b.extension_nm.shape == (N, 5)
    assert np.allclose(b.g0[:, 0], _igor_trace(cfg, 1).g0, rtol=1e-6, atol=1e-12)
    assert volt.name in caplog.text and "PullOutConductanceBlockHist_1" in caplog.text
    # the resume reloads the block with NaN voltage rows and no piezo wave ...
    resumed = IgorDayWriter(tmp_path, cfg, when=WHEN, flags=SaveFlags(piezo_wave=True))
    assert resumed.saved == 6 and resumed.n_pending == 5 and resumed._pending_k == 1
    t = resumed._pending[0]
    assert np.isnan(t.voltage_v).all() and t.piezo_wave_v is None
    assert np.allclose(t.g0, _igor_trace(cfg, 1).g0, rtol=1e-6, atol=1e-12)
    assert np.allclose(t.current_a, _igor_trace(cfg, 1).current_a, rtol=1e-6)
    # ... and refills it in place: the lost voltage columns stay NaN, the new one is there
    resumed.append(_igor_trace(cfg, 6))
    resumed.close()
    b = igor_scheme.read_block(folder, 1)
    assert b.n_traces == 6 and b.voltage_v.shape == (N, 6) and b.hist is not None
    assert np.isnan(b.voltage_v[:, :5]).all() and np.isfinite(b.voltage_v[:, 5]).all()
    piezo = igor_scheme.read_wave(igor_scheme.block_file(folder, "piezo_wave", 1)).data
    assert piezo.shape == (N,) and piezo[0] == 0.0


# --------------------------------------------------------------------------
# The real July 2026 data on the NAS
# --------------------------------------------------------------------------

@pytest.mark.skipif(not NAS_DAY.is_dir(), reason="the NAS day folder is not mounted")
def test_the_july_2026_igor_data_reads_back():
    assert igor_scheme.parse_day_folder_name(NAS_DAY.name) == (26, 7, 16, "_")
    ks = igor_scheme.list_blocks(NAS_DAY)
    assert ks[:3] == [1, 2, 3] and ks == sorted(ks)
    b = igor_scheme.read_block(NAS_DAY, 1, companions=True)
    assert b.g0.shape == (10000, 100) and b.params.shape == (100, PARAM_SLOTS)
    assert b.numbers.tolist() == list(range(1, 101))
    assert (b.params[:, 0] == 5).all() and (b.params[:, 1] == 20).all()
    assert (b.params[:, 10] == 600).all() and (b.params[:, 2] == 0.5).all()
    assert (b.params[:, 4] == 1).all() and (b.params[:, 9] == 1).all()
    assert (b.params[:, 12] == 1e5).all() and (b.params[:, 13] == 5).all()
    assert np.allclose(b.params[:, 19], -0.00337625, rtol=1e-4)
    assert (b.params[:, [6, 7, 8, 11, 14, 15, 16, 18]] == 0).all()
    # slot 17 is Igor's DateTime of 16 July 2026, local time (float32: ~256 s resolution)
    day = time.localtime(unix_from_igor_datetime(float(b.params[0, 17])))
    assert (day.tm_year, day.tm_mon, day.tm_mday) == (2026, 7, 16)
    assert b.displacement_nm[0] == 0.0 and b.displacement_nm[-1] == 5.0
    assert b.g0[:5, 0].mean() > 10                                   # starts in contact
    assert abs(b.g0[9990:, 0]).max() < 1e-3                          # ends in tunnelling
    for arr in (b.voltage_v, b.current_a, b.extension_nm, b.voltage_lowres_v):
        assert arr is not None and arr.shape == (10000, 100)
    assert b.hist is None                                            # Hist flag was off
    assert np.allclose(b.g0[:, 0], b.current_a[:, 0] / b.voltage_v[:, 0] / G0_SIEMENS,
                       rtol=1e-3, atol=1e-6)
    # the raw file: the two rows after the trace are exactly 0, and the companions' dx
    raw, header, note = _wave(NAS_DAY / "PullOutConductanceBlock_1.ibw")
    assert raw.dtype == np.float32 and raw.shape == (10022, 100) and note == b""
    assert (raw[10000:10002, :] == 0).all() and header["sfA"][0] == 1.0
    # the header dates are local-time DateTimes: modDate is the file's mtime
    # shifted by the local UTC offset (-14400 s, EDT, on the July files)
    mtime = (NAS_DAY / "PullOutConductanceBlock_1.ibw").stat().st_mtime
    assert header["modDate"] - (mtime + IGOR_EPOCH_OFFSET) == pytest.approx(
        time.localtime(mtime).tm_gmtoff, abs=2)
    assert unix_from_igor_datetime(header["modDate"]) == pytest.approx(mtime, abs=2)
    assert _wave(NAS_DAY / "PullOutVoltageBlock_1.ibw")[1]["sfA"][0] == pytest.approx(5 / 9999)
    # plot.load([folder, "--blocks", "1-2"]) equivalent: 200 traces, numbered 1..200
    two = igor_scheme.read_day_folder(NAS_DAY, blocks=[1, 2])
    assert sum(x.n_traces for x in two) == 200
    assert np.array_equal(np.concatenate([x.numbers for x in two]), np.arange(1, 201))
    assert IgorDayWriter.scan(NAS_DAY)[1] == 100                      # the last block is full
    # the legacy reader sees the same traces
    loaded = storage.load_igor_block(NAS_DAY / "PullOutConductanceBlock_1.ibw")
    assert len(loaded["traces"]) == 100 and loaded["traces"][0].size == 10000
    assert loaded["parameters"][0, 0] == 5.0
    # Igor's block histogram recomputed from the real block: every trace ends
    # below the 5e-4 G0 floor cut, and the counts span the tunnelling region
    # (below 0.3 G0) and the contact region (above 3 G0)
    cfg = RigConfig()
    hist = igor_scheme.block_histogram(list(b.g0.T), cfg, 100)
    x = HIST_X0 + np.arange(HIST_POINTS) * HIST_DX
    assert hist.shape == (HIST_POINTS,) and hist.sum() > 0
    assert hist[x < -0.5].sum() > 0 and hist[x > 0.5].sum() > 0
    used = sum(analysis.log_histogram([g], zero_cutoff=cfg.ramp.break_g0, igor_bins=True,
                                      tail_rows=TAIL_ROWS)[1].sum() > 0 for g in b.g0.T)
    assert used == 100
