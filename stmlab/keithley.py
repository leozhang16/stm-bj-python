"""Keithley 428 current amplifier over GPIB.

Igor equivalents:

    Keithley428.open            SetUpGPIB_Keithley()      SetUpGPIB_Keithley.ipf:9
    zero_check / zero_correct   ZeroCheckProc/ZeroCorrectProc  Controls_STMBJ.ipf:262,277
    set_gain                    SetGain                   Controls_STMBJ.ipf:290
    set_suppress_ua / enable    SetCurrentSuppress, CurrentSuppressCheckProc
    bias_enable / set_bias_mv   KeithleyBias, KeithleyBiasVolt  SetUpGPIB_Keithley.ipf:67,95
    filter / filter_rise_time   KeithleyFilter(RiseTime)  SetUpGPIB_Keithley.ipf:37,48
    find_suppress               TestVirtualGround         Functions_STMBJ.ipf:1097

The 428 speaks a terse command language where ``X`` executes the buffer:
``C1X`` zero-check on, ``C0X`` off, ``C2X`` zero-correct, ``P1/P0`` filter,
``T<n>`` rise time, ``H6R<g>X`` gain 10^g V/A, ``H8S<amps>,0X`` suppress
value, ``N1/N0`` suppress on/off, ``B1/B0`` internal bias source on/off,
``V<mV>E-3X`` bias value. Igor's init string ``C1P0B0N0X`` is zero-check on,
filter off, bias off, suppress off -- the amplifier wakes up inert.

GPIB access uses pyvisa (address 22, as Igor's ``ibdev={0,22,...}``).
``SimulatedKeithley`` has the same surface and just records state, so every
experiment script runs on a laptop.

Two things Igor kept in globals that live here as derived values:

    conversion_ua_per_v = 10**(6 - gain)       (G_CurrentVoltConversion)
    suppress from const = const * 10**(3 - gain)  (G_CurrentSuppress)

When the Keithley sources the bias (``B1X``), the junction voltage is no
longer measured at ai0 and the conductance needs the series-resistance
correction -- Igor's formula from GenerateTrace:390:

    G/G0 = (1 / (V_bias/I - R_series)) / G0

available here as :func:`series_corrected_conductance`.
"""

from __future__ import annotations

import logging
import time

import numpy as np

from .config import G0_SIEMENS, KeithleyConfig, RigConfig

log = logging.getLogger(__name__)


def series_corrected_conductance(current_a, bias_v: float,
                                 series_resistance_ohm: float):
    """Igor: PullOutConductance = (1/((TipBias*1e-3/I) - SeriesResistance))/K_G0.

    Used when the Keithley sources the bias, so the measured quantity is the
    total two-terminal current and the series resistance must be subtracted
    from the apparent resistance before inverting.
    """
    current_a = np.asarray(current_a, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        apparent_r = bias_v / current_a
        return (1.0 / (apparent_r - series_resistance_ohm)) / G0_SIEMENS


class KeithleyError(RuntimeError):
    pass


class Keithley428:
    """The real amplifier. Requires pyvisa and an NI GPIB interface."""

    def __init__(self, cfg: KeithleyConfig):
        self.cfg = cfg
        self._inst = None
        self.gain_exponent = cfg.gain_exponent
        self.suppress_ua = 0.0
        self.bias_enabled = False

    # -- lifecycle --------------------------------------------------------

    def open(self) -> "Keithley428":
        import pyvisa
        rm = pyvisa.ResourceManager()
        self._inst = rm.open_resource(self.cfg.resource)
        self._inst.timeout = 5000
        self.write("C1P0B0N0X")          # Igor's init: safe, inert state
        log.info("Keithley 428 at %s: zero-check on, filter/bias/suppress "
                 "off", self.cfg.resource)
        return self

    def close(self) -> None:
        if self._inst is not None:
            try:
                self.write("C1B0N0X")    # leave it inert
            except Exception:
                pass
            self._inst.close()
            self._inst = None

    def __enter__(self) -> "Keithley428":
        return self.open()

    def __exit__(self, *exc) -> bool:
        self.close()
        return False

    def write(self, command: str) -> None:
        if self._inst is None:
            raise KeithleyError("Keithley is not open")
        self._inst.write(command)

    # -- controls ---------------------------------------------------------

    def zero_check(self, on: bool) -> None:
        self.write("C1X" if on else "C0X")

    def zero_correct(self) -> None:
        self.write("C2X")

    def filter(self, on: bool) -> None:
        self.write("P1X" if on else "P0X")

    def filter_rise_time_us(self, t_us: float) -> None:
        """Igor's KeithleyFilterRiseTime. The 428 encodes rise time as T0-T9;
        Igor's formula recovers the code from the microsecond value. (Igor's
        range check used ``||`` where it meant ``&&`` -- fixed here.)"""
        if not 10 <= t_us <= 300000:
            raise ValueError(f"rise time {t_us} us out of range 10..300000")
        if round(t_us / 3) * 3 == t_us:
            code = np.log10((t_us / 30) ** 2) + 1
        elif round(t_us / 10) * 10 == t_us:
            code = np.log10((t_us / 10) ** 2)
        else:
            raise ValueError("rise time must be a 428 step "
                             "(10, 30, 100, 300 ... us)")
        self.write(f"T{int(round(code))}X")

    def set_gain(self, exponent: int) -> float:
        """Program the transimpedance gain to 10^exponent V/A.

        Igor's SetGain also recomputed the derived conversion and suppress
        (Controls_STMBJ.ipf:304-310); returned here is the conversion in
        uA per volt, and the suppress is re-sent at its rescaled value.
        """
        self.gain_exponent = int(exponent)
        conversion_ua_per_v = 10.0 ** (6 - self.gain_exponent)
        suppress_ua = self.cfg.suppress_const * 10.0 ** (3 - self.gain_exponent)
        self.write(f"H6R{self.gain_exponent}X")
        self.set_suppress_ua(suppress_ua)
        log.info("gain set to 1e%d V/A (%.3g uA/V)", self.gain_exponent,
                 conversion_ua_per_v)
        return conversion_ua_per_v

    def suppress_enable(self, on: bool) -> None:
        self.write("N1X" if on else "N0X")

    def set_suppress_ua(self, ua: float) -> None:
        self.suppress_ua = float(ua)
        self.write(f"H8S{ua / 1e6:.6g},0X")   # the 428 wants amps

    def bias_enable(self, on: bool) -> None:
        self.bias_enabled = bool(on)
        self.write("B1X" if on else "B0X")

    def set_bias_mv(self, mv: float) -> None:
        """Igor quantised to 5 mV before sending (SetTipBiasVoltage)."""
        mv = 5.0 * round(mv / 5.0)
        self.write(f"V{mv:g}E-3X")
        log.info("Keithley internal bias set to %g mV", mv)


class SimulatedKeithley(Keithley428):
    """Same surface, no GPIB. Records every command for inspection."""

    def __init__(self, cfg: KeithleyConfig):
        super().__init__(cfg)
        self.commands: list[str] = []

    def open(self) -> "SimulatedKeithley":
        self.write("C1P0B0N0X")
        return self

    def close(self) -> None:
        return

    def write(self, command: str) -> None:
        self.commands.append(command)
        log.debug("simulated Keithley <- %s", command)


def make_keithley(cfg: RigConfig):
    return SimulatedKeithley(cfg.keithley) if cfg.simulate \
        else Keithley428(cfg.keithley)


# --------------------------------------------------------------------------
# Virtual-ground calibration
# --------------------------------------------------------------------------

def find_suppress(rig, keithley: Keithley428,
                  n_points: int = 21,
                  settle_s: float = 0.083,
                  read_samples: int = 2000) -> tuple[float, np.ndarray,
                                                     np.ndarray]:
    """Find the suppress current that nulls the measured output at zero bias.

    Igor's TestVirtualGround (Functions_STMBJ.ipf:1097): sweep the suppress
    from -1 to +1 uA in 21 steps, wait for the amplifier to settle after each
    (Igor: ``sleep/T 5`` -- the "SPIKE problem" comment at :1123), read 2000
    samples of the output, then fit a line through the middle points and set
    the suppress to the zero crossing. Igor's FindSuppress button zeroed the
    applied bias first and restored it after (Controls_STMBJ.ipf:479); do the
    same around this call.

    Returns ``(new_suppress_ua, suppress_values_ua, mean_output_v)``.
    """
    sweep = np.linspace(-1.0, 1.0, n_points)
    readings = np.empty(n_points)

    for k, s in enumerate(sweep):
        keithley.set_suppress_ua(float(s))
        time.sleep(settle_s)
        record = rig.hold(bias_v=0.0, n_samples=read_samples)
        readings[k] = float(np.mean(record[rig.cfg.channels.ROW_CURRENT]))

    # Igor excluded the endpoints from the fit (amplifier settling).
    slope, intercept = np.polyfit(sweep[1:-1], readings[1:-1], 1)
    if slope == 0:
        raise KeithleyError("suppress sweep produced a flat response; is the "
                            "amplifier connected and out of zero-check?")
    new_suppress = -intercept / slope
    keithley.set_suppress_ua(float(new_suppress))
    log.info("new current suppress: %.4f uA", new_suppress)
    return float(new_suppress), sweep, readings
