#!/usr/bin/env python3
"""Electrochemical gating and cyclic voltammetry.

Igor equivalent: ``EChem_Module.ipf`` in its entirety. Three things lived in
that file and all three are here as subcommands:

    gate     WriteToCounterElectrode          :88   -- set the DC gate
    cv       CVcurveHighRes / CVcurveLowRes   :106 / :234
    traces   the gate + StartMeasurement, which is what the module was FOR

``traces`` is the actual experiment. The other two are the instrument
controls it is built out of, exposed separately because you will want to set
a gate and walk away, or take a voltammogram to see whether the cell is
behaving, without acquiring anything.

The physics: in an electrochemical STM junction the tip and substrate sit in
electrolyte, and a counter electrode holds the solution at a controlled
potential. Shifting that potential moves the molecular levels relative to the
Fermi energy of the electrodes -- a gate. Conductance measured as a function
of gate voltage is the electrochemical analogue of a transistor transfer
curve, and a redox-active molecule can show a conductance peak where a level
crosses resonance.

Igor saved the gate voltage with every trace as ParameterWave[18]. Here it
travels inside ``cfg.echem.gate_mv``, which is written into every data file,
so a file always knows the gate it was taken at.

TWO CARDS. The counter electrode is on the low-res card's ao1
(Setup1_STMBJ.ipf:11). This rig currently has one card, so ``gate`` and
``cv --kind lowres`` need ``channels.low_res_device`` set in the config and
will refuse otherwise. ``cv --kind highres`` drives the junction-bias output
on the card you have.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import logging
import signal
import threading
import time

from stmlab import approach, calibrate, echem, storage, trace
from stmlab.config import ConfigError, RigConfig, validate
from stmlab.echem import EChemError
from stmlab.instrument import Rig
from stmlab.safety import RigState, SafeSession, SafetyViolation

log = logging.getLogger("echem")

PKG_ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------
# gate
# --------------------------------------------------------------------------

def cmd_gate(cfg: RigConfig, mv: float, hold_s: float | None) -> int:
    """Set the counter electrode and either exit or hold it.

    Igor's task stayed open for the life of the running experiment. A CLI
    process cannot do that, so there are two honest options and both are
    offered: ``--hold`` keeps the process (and the task) alive for a stated
    number of seconds, or the default releases the channel WITHOUT zeroing
    it, leaving the card's AO holding the last value written. The second is
    the one that matches Igor's behaviour from the operator's point of view;
    it is also the one that leaves a voltage on an electrode with no process
    watching it, which is why it says so out loud.
    """
    ce = echem.make_counter_electrode(cfg)
    ce.on()
    try:
        ce.set_mv(mv)
        if hold_s is not None:
            log.info("holding the gate at %+.1f mV for %.0f s "
                     "(Ctrl-C to release early)", mv, hold_s)
            try:
                time.sleep(hold_s)
            except KeyboardInterrupt:
                log.warning("interrupted; releasing the gate")
            ce.off(zero=True)
            log.info("gate returned to 0 mV")
        else:
            ce.off(zero=False)
            log.warning("gate LEFT AT %+.1f mV -- the card holds its output "
                        "after this process exits. Run with --mv 0 to clear "
                        "it.", mv)
    except Exception:
        ce.off(zero=True)
        raise
    return 0

# --------------------------------------------------------------------------
# cv
# --------------------------------------------------------------------------

def cmd_cv(cfg: RigConfig, kind: str, cycles: int, out: Path,
           plot: bool) -> int:
    ec = cfg.echem
    log.info("CV (%s): 0 -> %+.2f V -> %+.2f V at %.0f mV/s, "
             "%d cycle(s), sampled at %.0f Hz",
             kind, ec.peak_one_v, ec.peak_two_v, ec.scan_rate_mv_per_s,
             cycles, ec.cv_rate_hz)

    if kind == "highres":
        log.warning("the high-res CV drives dev1/ao1 -- the JUNCTION BIAS "
                    "output. The tip is the working electrode. Make sure no "
                    "junction is engaged: retract before running this.")

    result = echem.run_cv(cfg, kind=kind, cycles=cycles)
    storage.save_cv_cycles(out, cfg, result, kind=kind)

    # A voltammogram's headline numbers, so the terminal says something
    # useful without opening the file.
    for c in result:
        i_a = cfg.cal.volts_to_amps(c.tip_current_v)
        kept = i_a[c.keep]
        log.info("  cycle %d: %+.3e to %+.3e A over %d kept samples "
                 "(%d masked)", c.cycle, kept.min(), kept.max(),
                 int(c.keep.sum()), int((~c.keep).sum()))

    if plot:
        _plot_cv(cfg, result, out.with_suffix(".png"))
    return 0

def _plot_cv(cfg: RigConfig, cycles: list, path: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        log.warning("matplotlib not installed; skipping the plot")
        return

    fig, ax = plt.subplots(figsize=(6, 5))
    for c in cycles:
        i_ua = cfg.cal.volts_to_amps(c.tip_current_v) * 1e6
        ax.plot(c.applied_v[c.keep], i_ua[c.keep], lw=.9,
                label=f"cycle {c.cycle}")
    ax.set_xlabel("applied potential (V)")
    ax.set_ylabel("cell current (uA)")
    ax.set_title(f"Cyclic voltammogram, {cfg.echem.scan_rate_mv_per_s:.0f} mV/s")
    ax.axhline(0, color="grey", lw=.6)
    ax.grid(alpha=.3)
    if len(cycles) > 1:
        ax.legend(fontsize=8)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    log.info("wrote %s", path)

# --------------------------------------------------------------------------
# traces -- the experiment the module exists for
# --------------------------------------------------------------------------

def cmd_traces(cfg: RigConfig, gates_mv: list[float], n_traces: int,
               out_dir: Path, do_calibrate: bool, settle_s: float) -> int:
    """Break-junction traces at one or more gate potentials.

    One file per gate. The gate is written into ``cfg.echem.gate_mv`` before
    the writer opens, so it lands in that file's ``config_json`` -- the same
    slot Igor used for ParameterWave[18], but attached to the whole session
    rather than repeated per trace.

    Settling matters here in a way it does not for a dry junction: after
    changing the counter-electrode potential the double layer takes time to
    re-equilibrate, and traces taken during that are at an unknown gate.
    ``--settle`` is that wait, and it defaults to 5 s rather than 0.
    """
    stop = threading.Event()

    def on_signal(signum, frame):
        del signum, frame
        if stop.is_set():
            log.warning("second interrupt; exiting now")
            sys.exit(130)
        log.warning("interrupt: finishing the current gate, then stopping")
        stop.set()

    signal.signal(signal.SIGINT, on_signal)

    for warning in validate(cfg):
        log.warning("config: %s", warning)

    log.info("gated break junctions: %d gate(s) %s mV, %d trace(s) each",
             len(gates_mv), gates_mv, n_traces)

    results: list[tuple[float, dict, Path]] = []

    with SafeSession(cfg):
        with Rig(cfg) as rig:
            ce = echem.make_counter_electrode(cfg)
            ce.on()
            try:
                if do_calibrate:
                    calibrate.session_calibration(rig)
                rig.set_bias(cfg.ramp.bias_v)

                for gate_mv in gates_mv:
                    if stop.is_set():
                        break

                    ce.set_mv(gate_mv)          # also sets cfg.echem.gate_mv
                    log.info("settling %.1f s at %+.1f mV", settle_s, gate_mv)
                    time.sleep(settle_s)

                    # Re-measure the preamp zero at every gate. The gate
                    # shifts the electrochemical leakage through the cell,
                    # so the "zero current" of one gate is not the zero of
                    # the next -- an uncorrected offset here puts a false
                    # floor under that gate's histogram only, which reads as
                    # gate-dependent physics.
                    if do_calibrate:
                        cfg.cal.current_zero_v = calibrate.measure_zero(rig)

                    if approach.recover_headroom(rig) is not RigState.ENGAGED:
                        log.error("could not engage at %+.1f mV", gate_mv)
                        break

                    path = out_dir / f"gate_{gate_mv:+.0f}mV.h5"
                    with storage.SessionWriter(path, cfg) as writer:
                        writer._h5.attrs["gate_mv"] = gate_mv
                        stats = trace.trace_loop(
                            rig, n=n_traces, on_trace=writer.append,
                            stop_flag=stop)
                        stats["gate_mv"] = gate_mv
                        writer.write_summary(stats)

                    results.append((gate_mv, stats, path))
                    log.info("gate %+.1f mV: %d accepted / %d attempts -> %s",
                             gate_mv, stats["accepted"], stats["attempts"],
                             path.name)

                rig.withdraw()
            finally:
                ce.off(zero=True)               # never leave a cell gated
                log.info("counter electrode returned to 0 mV")

    if not results:
        return 1
    log.info("done: %d gate(s)", len(results))
    for gate_mv, stats, _ in results:
        log.info("  %+8.1f mV: %4d accepted / %4d attempts",
                 gate_mv, stats["accepted"], stats["attempts"])
    return 0

# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Electrochemical gating and cyclic voltammetry "
                    "(Igor: EChem_Module.ipf).")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path,
                        help="rig config JSON; defaults are used if omitted")
    common.add_argument("-v", "--verbose", action="store_true")
    common.add_argument("--simulate", action="store_true",
                        help="run against the simulated cell, no hardware")

    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("gate", parents=[common],
                       help="set the counter-electrode DC potential")
    g.add_argument("--mv", type=float, required=True,
                   help="gate potential in millivolts (Igor entered mV too)")
    g.add_argument("--hold", type=float, default=None, metavar="SECONDS",
                   help="hold the gate for this long, then return to 0 mV. "
                        "Without it the channel is released still holding "
                        "the value, as Igor's did.")

    c = sub.add_parser("cv", parents=[common], help="cyclic voltammetry")
    c.add_argument("--kind", choices=("highres", "lowres"), default="highres",
                   help="highres drives dev1/ao1 (tip as working electrode); "
                        "lowres drives the counter electrode on the second "
                        "card (default: highres)")
    c.add_argument("--cycles", type=int, default=None,
                   help="number of cycles (default: echem.cycles)")
    c.add_argument("-o", "--out", type=Path, default=None,
                   help="output .h5 (default: data/cv_<timestamp>.h5)")
    c.add_argument("--plot", action="store_true",
                   help="also write a PNG of the voltammogram")

    t = sub.add_parser("traces", parents=[common],
                       help="break-junction traces at one or more gates")
    t.add_argument("--gate-mv", type=float, nargs="+", required=True,
                   metavar="MV",
                   help="one or more gate potentials, e.g. --gate-mv -200 0 200")
    t.add_argument("-n", "--traces", type=int, default=100,
                   help="accepted traces per gate (default 100)")
    t.add_argument("-o", "--out-dir", type=Path, default=None,
                   help="output directory (default: data/echem_<timestamp>/)")
    t.add_argument("--settle", type=float, default=5.0,
                   help="seconds to wait after changing the gate before "
                        "acquiring (default 5)")
    t.add_argument("--no-calibrate", action="store_true",
                   help="skip the session zero and per-gate zero")
    return p

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S")

    cfg = RigConfig.from_json(args.config) if args.config else RigConfig()
    if args.simulate:
        cfg.simulate = True

    stamp = time.strftime("%Y%m%d_%H%M%S")
    try:
        if args.command == "gate":
            return cmd_gate(cfg, args.mv, args.hold)
        if args.command == "cv":
            out = args.out or PKG_ROOT / "data" / f"cv_{stamp}.h5"
            cycles = args.cycles if args.cycles is not None \
                else cfg.echem.cycles
            return cmd_cv(cfg, args.kind, cycles, out, args.plot)
        out_dir = args.out_dir or PKG_ROOT / "data" / f"echem_{stamp}"
        return cmd_traces(cfg, list(args.gate_mv), args.traces, out_dir,
                          not args.no_calibrate, args.settle)
    except (ConfigError, SafetyViolation, EChemError) as exc:
        log.error("%s", exc)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
