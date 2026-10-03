"""Writing Igor binary waves: the block layout Igor's own procedures read."""

from __future__ import annotations

import struct

import numpy as np
import pytest

from stmlab import storage
from stmlab.config import RigConfig


def _header_words(path):
    with open(path, "rb") as fh:
        return struct.unpack("<192h", fh.read(384))


def test_ibw_headers_have_a_zero_checksum_and_the_right_sizes(tmp_path):
    data = np.arange(12, dtype=np.float32).reshape(4, 3)
    path = storage.write_ibw(tmp_path / "w.ibw", "test_wave", data, note="hi")
    words = _header_words(path)
    assert words[0] == 5                               # format version
    assert sum(words) & 0xFFFF == 0                    # Igor's checksum rule
    with open(path, "rb") as fh:
        raw = fh.read()
    version, checksum, wfm_size, formula, note_size = struct.unpack(
        "<hhlll", raw[:16])
    assert wfm_size == 320 + 12 * 4
    assert note_size == 2
    assert raw[-2:] == b"hi"
    # column-major: Igor's w[r][c] is data[r, c]
    payload = np.frombuffer(raw[384:384 + 48], dtype="<f4")
    assert np.array_equal(payload.reshape(3, 4).T, data)


def test_ibw_rejects_an_illegal_wave_name(tmp_path):
    with pytest.raises(ValueError):
        storage.write_ibw(tmp_path / "w.ibw", "1bad name", np.zeros(3))


def test_block_round_trips_through_igor2(tmp_path):
    pytest.importorskip("igor2")
    cfg = RigConfig()
    rng = np.random.default_rng(1)
    traces = [10 ** rng.uniform(-6, 0.3, 500) for _ in range(4)]
    path = storage.save_igor_block(tmp_path / "PullOut_b000.ibw", cfg, traces,
                                   start_piezo_v=[4.8, 4.81, 4.79, 4.8])
    block = storage.load_ibw(path)
    assert block.shape == (500 + 2 + storage.IGOR_PARAMETER_SLOTS, 4)
    back, params = storage.split_igor_block(block)
    assert np.allclose(back, np.array(traces), rtol=1e-6)
    assert params[0, 0] == pytest.approx(cfg.ramp.pull_length_nm)
    assert params[0, 10] == pytest.approx(cfg.ramp.bias_v * 1e3)
    assert params[2, 3] == pytest.approx(cfg.cal.piezo_volts_to_nm(4.79), rel=1e-5)
    assert np.isnan(block[500, 0]) and np.isnan(block[501, 0])   # the two blanks


def test_block_refuses_ragged_traces(tmp_path):
    cfg = RigConfig()
    with pytest.raises(ValueError):
        storage.save_igor_block(tmp_path / "x.ibw", cfg,
                                [np.zeros(10), np.zeros(11)])
