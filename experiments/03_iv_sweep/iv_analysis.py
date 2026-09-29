#!/usr/bin/env python3
"""Cut stored IV traces back into I-V curves.

The acquisition (run_experiment.py, Igor's CreateInputs IV branch,
Functions_STMBJ.ipf:1497-1537) stores whole records in raw volts: initial
pull, cap, sweep, cap, final pull, all in one trace. This module cuts the
``iv_ramp`` window back out and converts it to physics::

    V_junction = cfg.cal.voltage_input_sign * voltage_v[a:b]   # volts
    I          = cfg.cal.volts_to_amps(current_v[a:b])         # amps

where ``(a, b)`` comes from the ``segments`` map the runner stored in the
file's summary stats, and the sweep is split into its four quarter-sweeps
using the ``quarters`` boundaries Igor computed as BiasIndex1..4
(Functions_STMBJ.ipf:1521-1524) -- or, for a file without a summary, by the
sign of dV/dt of the measured junction voltage.

Igor itself had no IV analysis in the acquisition procedures -- sweeps were
inspected by hand in graph windows -- so the dI/dV here (smoothed gradient
ratio, masked at the turning points) is new, not a translation.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import json
import logging
from dataclasses import dataclass, field

import numpy as np

from stmlab import analysis, storage
from stmlab.config import G0_SIEMENS

log = logging.getLogger("iv_analysis")


@dataclass
class IVSweep:
    """One trace's sweep window, in physical units.

    ``quarters`` maps quarter names to (start, stop) indices into
    ``v_junction``/``i_amps``. With ``positive_first`` False the junction
    voltage runs 0 -> +max (q1), +max -> 0 (q2), 0 -> -max (q3),
    -max -> 0 (q4); with it True the polarities swap.
    """
    index: int
    v_junction: np.ndarray            # volts, sign-corrected
    i_amps: np.ndarray                # amps, zero-corrected
    quarters: dict[str, tuple[int, int]] = field(default_factory=dict)
    didv_v: np.ndarray | None = None  # voltage axis for didv_s
    didv_s: np.ndarray | None = None  # dI/dV in siemens (NaN at turnarounds)

    def quarter(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        a, b = self.quarters[name]
        return self.v_junction[a:b], self.i_amps[a:b]


# --------------------------------------------------------------------------
# Locating the sweep inside a stored trace
# --------------------------------------------------------------------------

def run_stats(session: storage.Session) -> dict:
    """The summary dict the runner passed to ``write_summary``, or {}.

    ``storage.Session`` has no public accessor for the file attributes, so
    this reads the underlying h5py handle directly.
    """
    raw = session._h5.attrs.get("run_stats_json")
    return json.loads(raw) if raw else {}


def iv_window(session: storage.Session
              ) -> tuple[tuple[int, int], tuple[int, int, int, int] | None]:
    """((a, b), quarters) of the sweep, in trace-sample indices.

    Prefers the summary stats written by run_experiment.py (keys "segments"
    and "quarters"); falls back to the "segments_json" attribute alone. The
    stored quarter boundaries (b1, b2, b3, b4) satisfy b1 == a and b4 == b:
    Igor's BiasIndex1..4 (Functions_STMBJ.ipf:1521-1524) in the same index
    space as the segments. Returns quarters=None if only segments exist.
    """
    stats = run_stats(session)
    segments = stats.get("segments")
    if segments is None:
        raw = session._h5.attrs.get("segments_json")
        if raw is None:
            raise KeyError(
                f"{session.path} carries neither run-summary segments nor a "
                f"segments_json attribute; was it written by "
                f"experiments/03_iv_sweep/run_experiment.py?")
        segments = json.loads(raw)
    if "iv_ramp" not in segments:
        raise KeyError(f"{session.path} has segments {sorted(segments)} but "
                       f"no 'iv_ramp'; not an IV session file")
    a, b = (int(x) for x in segments["iv_ramp"])
    quarters = stats.get("quarters")
    if quarters is not None:
        quarters = tuple(int(x) for x in quarters)
    return (a, b), quarters


def _quarters_from_dvdt(v: np.ndarray) -> tuple[int, int, int]:
    """(t1, mid, t2) split points from the measured voltage alone.

    The triangle has exactly one apex of each sign: the first apex ends q1,
    the zero crossing between the apexes splits the long middle flank into
    q2/q3, and the second apex starts q4. Equivalent to splitting where the
    sign of dV/dt flips, but immune to noise between samples.
    """
    v_s = analysis.boxcar(v, 25)
    i_max, i_min = int(np.argmax(v_s)), int(np.argmin(v_s))
    t1, t2 = sorted((i_max, i_min))
    if t1 == t2 or t1 < 1 or t2 > v.size - 1:
        raise ValueError("measured voltage has no triangular sweep; cannot "
                         "split quarters by dV/dt")
    mid = t1 + int(np.argmin(np.abs(v_s[t1:t2])))
    return t1, mid, t2


def split_quarters(v: np.ndarray,
                   quarters_abs: tuple[int, int, int, int] | None = None
                   ) -> dict[str, tuple[int, int]]:
    """Quarter-sweep boundaries, relative to the cut (V, I) arrays.

    ``quarters_abs`` is the stored (b1, b2, b3, b4), with b1 the window
    start; the middle +max -> -max flank (b2, b3) is split at its midpoint,
    where the applied bias crosses zero (the ramp is linear, Igor line 1530).
    Without stored quarters the split points come from the sign structure of
    the measured V itself.
    """
    n = v.size
    if quarters_abs is not None:
        b1, b2, b3, _b4 = quarters_abs
        t1, t2 = b2 - b1, b3 - b1
        mid = (t1 + t2) // 2
    else:
        t1, mid, t2 = _quarters_from_dvdt(v)
    return {"q1": (0, t1), "q2": (t1, mid), "q3": (mid, t2), "q4": (t2, n)}


# --------------------------------------------------------------------------
# Physics
# --------------------------------------------------------------------------

def differential_conductance(v: np.ndarray, i: np.ndarray,
                             smooth_pts: int = 25
                             ) -> tuple[np.ndarray, np.ndarray]:
    """(V, dI/dV) sample by sample, dI/dV in siemens.

    Both arrays are boxcar-smoothed first (Igor's Smooth/B), then the
    gradients are ratioed. Where the sweep turns around |dV| per sample
    collapses and the ratio is meaningless, so those samples are NaN --
    plot with a line and they leave a clean gap at each apex.
    """
    v_s = analysis.boxcar(np.asarray(v, float), smooth_pts)
    i_s = analysis.boxcar(np.asarray(i, float), smooth_pts)
    dv = np.gradient(v_s)
    di = np.gradient(i_s)
    floor = 0.2 * np.median(np.abs(dv))
    with np.errstate(divide="ignore", invalid="ignore"):
        didv = np.where(np.abs(dv) > floor, di / dv, np.nan)
    return v_s, didv


def extract(session: storage.Session, index: int,
            smooth_pts: int = 25) -> IVSweep:
    """The (V, I) sweep and dI/dV of one stored trace.

    This is the function the task promises: given a ``storage.Session`` and
    a trace index, cut the iv_ramp window, convert with the file's own
    calibration, split the quarter sweeps, and attach dI/dV vs V.
    """
    (a, b), quarters_abs = iv_window(session)
    cfg = session.cfg
    voltage_v, current_v = session.raw(index)

    v = cfg.cal.voltage_input_sign * np.asarray(voltage_v[a:b], float)
    i = cfg.cal.volts_to_amps(np.asarray(current_v[a:b], float))

    try:
        quarters = split_quarters(v, quarters_abs)
    except ValueError as exc:
        log.warning("trace %d: %s -- returning the sweep unsplit", index, exc)
        quarters = {"all": (0, v.size)}

    didv_v, didv_s = differential_conductance(v, i, smooth_pts)
    return IVSweep(index=index, v_junction=v, i_amps=i, quarters=quarters,
                   didv_v=didv_v, didv_s=didv_s)


# --------------------------------------------------------------------------
# Quick look from the command line
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        description="Inspect IV sweeps stored by run_experiment.py.")
    p.add_argument("path", type=Path, help="session .h5 file")
    p.add_argument("index", type=int, nargs="?", default=0,
                   help="trace index (default 0)")
    p.add_argument("--plot", action="store_true",
                   help="show I-V and dI/dV (needs matplotlib)")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    with storage.Session(args.path) as session:
        sweep = extract(session, args.index)
        print(f"{args.path.name} trace {sweep.index}: "
              f"{sweep.v_junction.size} samples, "
              f"V in [{sweep.v_junction.min():+.3f}, "
              f"{sweep.v_junction.max():+.3f}] V, "
              f"peak |I| {np.max(np.abs(sweep.i_amps)) * 1e9:.2f} nA")
        for name, (qa, qb) in sweep.quarters.items():
            vq = sweep.v_junction[qa:qb]
            g = np.nanmedian(sweep.didv_s[qa:qb]) / G0_SIEMENS
            print(f"  {name}: {qb - qa:6d} samples, "
                  f"V {vq[0]:+.3f} -> {vq[-1]:+.3f} V, "
                  f"median dI/dV {g:.3e} G0")

        if args.plot:
            try:
                import matplotlib.pyplot as plt
            except Exception as exc:
                print(f"matplotlib unavailable: {exc}")
                return 1
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4))
            ax1.plot(sweep.v_junction, sweep.i_amps * 1e9, lw=0.8)
            ax1.set_xlabel("junction voltage (V)")
            ax1.set_ylabel("current (nA)")
            ax2.plot(sweep.didv_v, sweep.didv_s / G0_SIEMENS, lw=0.8)
            ax2.set_xlabel("junction voltage (V)")
            ax2.set_ylabel("dI/dV (G0)")
            fig.suptitle(f"{args.path.name} trace {sweep.index}")
            fig.tight_layout()
            plt.show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
