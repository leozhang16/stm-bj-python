"""Lateral X piezo, for walking the tip across a monolayer.

Igor equivalents (NanoPZ_Actuator_Functions_STM.ipf):

    XPiezo.setup       SetupXPiezo        :25
    XPiezo.move_nm     MoveXPiezo         :47
    XPiezo.zero        MoveXPiezoToZero   :70
    XPiezo.stop        StopXPiezo         :93

The X piezo hangs off the low-res card's ao0 (``dev2/ao0``,
Setup1_STMBJ.ipf:40) at ``K_XPiezoScale = 522 nm/V`` -- almost an order of
magnitude coarser than the Z piezo's 62 nm/V, because lateral moves between
measurement sites are hundreds of nanometres.

Like the Z piezo, it is open loop: position is the running sum of commanded
moves, tracked here exactly as Igor tracked ``G_XPiezoPosition``. There is no
interlock tied to it -- a lateral move with the tip *in contact* drags the
tip across the surface, so the lateral experiment withdraws (coarse steps
apart) before every move; see ``experiments/07_lateral_monolayer``.
"""

from __future__ import annotations

import logging

from .config import RigConfig, XPiezoConfig

log = logging.getLogger(__name__)


class XPiezoError(RuntimeError):
    pass


class XPiezo:
    """DC control of the lateral piezo, with tracked absolute position."""

    def __init__(self, cfg: RigConfig):
        self.cfg = cfg
        self.xcfg: XPiezoConfig = cfg.xpiezo
        self.position_nm = 0.0
        self._task = None

    # -- lifecycle --------------------------------------------------------

    def setup(self) -> "XPiezo":
        """Create the output channel and drive it to 0 V (Igor SetupXPiezo)."""
        device = self.cfg.channels.low_res_device
        if device is None:
            raise XPiezoError(
                "no low-res device configured (channels.low_res_device is "
                "None); the X piezo lives on the second card")
        import nidaqmx
        self._task = nidaqmx.Task("stmlab_xpiezo")
        self._task.ao_channels.add_ao_voltage_chan(
            f"{device}/{self.xcfg.channel}",
            min_val=self.xcfg.min_v, max_val=self.xcfg.max_v)
        self._write(0.0)
        self.position_nm = 0.0
        return self

    def stop(self) -> None:
        """Zero the output and release the channel (Igor StopXPiezo)."""
        if self._task is not None:
            try:
                self._write(0.0)
            finally:
                self._task.close()
                self._task = None
        self.position_nm = 0.0

    def __enter__(self) -> "XPiezo":
        return self.setup()

    def __exit__(self, *exc) -> bool:
        self.stop()
        return False

    # -- motion -----------------------------------------------------------

    def _write(self, volts: float) -> None:
        self._task.write(volts, auto_start=True)

    @property
    def voltage(self) -> float:
        return self.position_nm / self.xcfg.nm_per_volt

    def move_nm(self, delta_nm: float) -> float:
        """Relative lateral move. Igor: MoveXPiezo(XDistance).

        Refuses a move that would leave the channel's range -- Igor did not
        check, and 12,200 accumulated 200 nm steps (the LateralEXPT campaign)
        is 4.7 V of a 10 V range, so the headroom is real but finite.
        """
        target_nm = self.position_nm + delta_nm
        volts = target_nm / self.xcfg.nm_per_volt
        if not self.xcfg.min_v <= volts <= self.xcfg.max_v:
            raise XPiezoError(
                f"lateral move to {target_nm:.0f} nm needs {volts:.3f} V, "
                f"outside [{self.xcfg.min_v}, {self.xcfg.max_v}] V. Re-centre "
                f"the sample or zero the X piezo.")
        self._write(volts)
        self.position_nm = target_nm
        log.info("X piezo at %.0f nm (%.3f V)", target_nm, volts)
        return target_nm

    def zero(self) -> None:
        """Return to 0 (Igor MoveXPiezoToZero)."""
        self._write(0.0)
        self.position_nm = 0.0


class SimulatedXPiezo(XPiezo):
    """Same surface, no card. Tracks position only."""

    def setup(self) -> "SimulatedXPiezo":
        self.position_nm = 0.0
        return self

    def stop(self) -> None:
        self.position_nm = 0.0

    def _write(self, volts: float) -> None:
        log.debug("simulated X piezo <- %.4f V", volts)


def make_xpiezo(cfg: RigConfig) -> XPiezo:
    return SimulatedXPiezo(cfg) if cfg.simulate else XPiezo(cfg)
