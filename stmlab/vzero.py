"""The Voltage_Offset workflow: find the bias that nulls the current.

Igor equivalents:

    measure_offset      OffsetVoltage       Functions_STMBJ.ipf:920
    _ensure_contact     HighResContact      Functions_STMBJ.ipf:1045
    VzeroTracker        SaveOffset          Functions_STMBJ.ipf:993

An amplifier chain has an input offset: at a commanded bias of exactly zero,
a small current still flows. Igor measured the *applied bias that makes the
current zero* (Vzero) by holding the tip in contact, stepping the bias
through +/-5 mV in ten steps, fitting current against bias, and reading the
line's zero crossing. The result fed back into the applied bias --
``-(TipBias + Vzero)/1000`` in CreateInputs (Functions_STMBJ.ipf:1611) --
and, in the high-bias-hold mode, could *become* the hold bias.

The periodic version (SaveOffset) re-measured every ``G_VzeroFrequency = 50``
accepted traces and kept the history, which is what ``VzeroTracker`` does.
The history matters: a drifting Vzero is an early warning that the amplifier
or the junction chemistry is drifting, and Igor plotted it (the Izero graph)
for exactly that reason.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from .config import RigConfig, VzeroConfig
from .safety import SafetyViolation

log = logging.getLogger(__name__)


@dataclass
class VzeroResult:
    """One offset measurement. Currents in amps, biases in the units named."""
    vzero_mv: float               # applied bias that nulls the current
    izero_a: float                # current at zero applied bias (intercept)
    bias_mv: np.ndarray           # the sweep points
    current_a: np.ndarray
    voltage_v: np.ndarray         # measured junction voltage at each point
    timestamp: float = field(default_factory=time.time)


def _ensure_contact(rig, step_in_nm: float = 2.0,
                    contact_bias_v: float = 0.100) -> None:
    """Igor's HighResContact: step in +2 nm at 100 mV until above threshold.

    Refuses at the piezo ceiling rather than looping forever -- Igor's loop
    had no exit on the extended side.
    """
    cfg: RigConfig = rig.cfg
    rig.set_bias(contact_bias_v)
    while not rig.in_contact():
        if rig.piezo_v >= cfg.limits.piezo_ao_max_v:
            raise SafetyViolation(
                "vzero: piezo at the ceiling with no contact; run the "
                "coarse approach before measuring the offset")
        rig.piezo_step_nm(step_in_nm)


def measure_offset(rig, vz: VzeroConfig | None = None) -> VzeroResult:
    """Sweep the bias through +/-interval_mv in contact and fit I(V).

    Igor swept ``2 * G_NumPoints`` values from -interval to +interval
    (Functions_STMBJ.ipf:950-952), re-checking contact before every point,
    settling 50 ms after each bias change, then fitted a line:
    Izero is the current at zero applied bias and Vzero = -Izero/slope is
    the bias that nulls it. The original bias is restored afterwards.
    """
    cfg: RigConfig = rig.cfg
    vz = vz or cfg.vzero
    original_bias = cfg.ramp.bias_v

    n = 2 * vz.n_points
    increment = abs(vz.interval_mv) / vz.n_points
    bias_mv = -abs(vz.interval_mv) + increment * np.arange(n)   # Igor :951

    current_a = np.empty(n)
    voltage_v = np.empty(n)
    M, C = cfg.channels, cfg.cal

    for i, b in enumerate(bias_mv):
        _ensure_contact(rig)
        rig.set_bias(b / 1000.0)
        time.sleep(vz.settle_s)
        record = rig.hold(n_samples=5000)      # Igor read 5000 samples
        keep = record.shape[1] - cfg.ramp.settle_discard
        current_a[i] = C.volts_to_amps(
            float(np.mean(record[M.ROW_CURRENT, -keep:])))
        voltage_v[i] = C.voltage_input_sign * \
            float(np.mean(record[M.ROW_VOLTAGE, -keep:]))

    rig.set_bias(original_bias)                # Igor :980

    slope, izero = np.polyfit(bias_mv, current_a, 1)   # amps per mV, amps
    if slope == 0:
        raise RuntimeError("vzero: flat I(V) -- no contact, or a railed "
                           "preamp at every point")
    vzero_mv = -izero / slope

    log.info("Vzero = %+.3f mV (Izero = %+.3e A)", vzero_mv, izero)
    return VzeroResult(vzero_mv=float(vzero_mv), izero_a=float(izero),
                       bias_mv=bias_mv, current_a=current_a,
                       voltage_v=voltage_v)


class VzeroTracker:
    """Re-measure the offset every N accepted traces, keeping the history.

    Igor's SaveOffset, minus the globals. Wire ``maybe_measure`` into a trace
    loop's ``on_trace`` callback (or call it manually between traces), then
    pass ``tracker.offset_v`` to ``trace.single_trace(bias_offset_v=...)`` so
    the applied bias carries the correction, exactly as Igor's CreateInputs
    refresh after every accepted trace did (Functions_STMBJ.ipf:1653).
    """

    def __init__(self, cfg: RigConfig):
        self.cfg = cfg
        self.history: list[VzeroResult] = []

    @property
    def current(self) -> VzeroResult | None:
        return self.history[-1] if self.history else None

    @property
    def offset_v(self) -> float:
        """The correction to add to the applied bias, in volts."""
        return self.current.vzero_mv / 1000.0 if self.history else 0.0

    def maybe_measure(self, rig, trace_number: int) -> VzeroResult | None:
        every = self.cfg.vzero.every_n_traces
        if every <= 0 or trace_number == 0 or trace_number % every:
            return None
        result = measure_offset(rig, self.cfg.vzero)
        self.history.append(result)
        return result

    def as_arrays(self) -> dict[str, np.ndarray]:
        """History as flat arrays, ready for an HDF5 attribute or dataset."""
        return {
            "vzero_mv": np.array([r.vzero_mv for r in self.history]),
            "izero_a": np.array([r.izero_a for r in self.history]),
            "timestamp": np.array([r.timestamp for r in self.history]),
        }
