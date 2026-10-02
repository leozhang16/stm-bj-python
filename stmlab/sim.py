"""A fake card that behaves like a break junction.

Exposes the same ``configure``/``play`` surface as :class:`daq.DaqSession`, so
everything above the DAQ layer -- approach, trace, selection, histogram,
storage, the run loop -- can be exercised end to end on a laptop with no
hardware present.

The point is not a faithful simulation of gold. It is to produce data with the
*shape* real data has, so that the code paths which only fire on real physics
get exercised: a junction that is sometimes in contact and sometimes not, a
1 G0 plateau to put a peak where you can check it, a molecular plateau
somewhere below it, a tunnelling tail that decays into a noise floor, traces
that fail selection, and a tip that degrades until it is smashed.

It also reproduces two instrument artefacts that the acquisition code exists
to handle:

* a fixed AI/AO group delay, so ``find_alignment_edge`` has something to find
* a noise floor in the current channel, so the tunnelling tail bottoms out at
  a finite conductance instead of running to zero
"""

from __future__ import annotations

import numpy as np

from .config import G0_SIEMENS, RigConfig


class SimulatedDaqSession:
    """Drop-in replacement for :class:`daq.DaqSession`."""

    def __init__(self, cfg: RigConfig, seed: int = 0,
                 group_delay_samples: int = 37,
                 noise_v_rms: float = 1.87e-6,
                 molecule_probability: float = 0.45,
                 molecule_log_g0: float = -3.5):
        self.cfg = cfg
        self.rng = np.random.default_rng(seed)
        self.granted_rate_hz = cfg.ramp.sample_rate_hz
        self.idle_behavior = "maintain"
        self._retriggerable = True      # the fake card is an obliging one

        self.group_delay = int(group_delay_samples)
        self.noise_v_rms = float(noise_v_rms)
        self.p_molecule = float(molecule_probability)
        self.molecule_log_g0 = float(molecule_log_g0)

        # Geometry, in nm of piezo displacement. The surface sits partway up
        # the piezo's range so there is room to approach into it and to pull
        # away from it.
        self.surface_nm = 300.0
        self.piezo_nm = 0.0

        # How far the single-atom contact stretches before rupture. Real gold
        # holds for roughly one to two angstroms.
        self.gold_plateau_nm = 0.12

        # State that persists across plays, because a junction does.
        self._tail = np.zeros((2, self.group_delay))
        self._snap_nm: float | None = None
        self._snap_g0 = 1.0
        self._mol_g0: float | None = None
        self._mol_len_nm = 0.0
        self._tip_quality = 1.0

        # Piezo sense readback of the last play, like DaqSession.last_sense_v:
        # (n,) volts on a two-card config, None on a one-card one.
        self.last_sense_v: np.ndarray | None = None
        self.sense_sync = "hardware" if cfg.channels.has_piezo_sense else "none"

    # -- interface --------------------------------------------------------

    def configure(self, n_samples: int) -> None:
        return

    def close(self) -> None:
        return

    def __enter__(self) -> "SimulatedDaqSession":
        return self

    def __exit__(self, *exc) -> bool:
        self.close()
        return False

    @property
    def effective_rate_hz(self) -> float:
        return self.granted_rate_hz

    def play(self, waveform: np.ndarray, timeout_s: float = 10.0) -> np.ndarray:
        waveform = np.asarray(waveform, dtype=float)
        if waveform.ndim != 2 or waveform.shape[0] != 2:
            raise ValueError(f"waveform must be (2, n), got {waveform.shape}")

        # The card sees the command delayed: prepend the tail of the previous
        # play and keep this play's tail for the next one.
        delayed = np.concatenate([self._tail, waveform], axis=1)
        self._tail = waveform[:, waveform.shape[1] - self.group_delay:].copy() \
            if self.group_delay else np.zeros((2, 0))
        delayed = delayed[:, :waveform.shape[1]]

        piezo_v, bias_v = delayed[0], delayed[1]
        cal = self.cfg.cal

        position_nm = piezo_v * cal.piezo_nm_per_volt
        g0 = self._conductance(position_nm)

        # Commanded position is the *undelayed* last sample: this is what the
        # instrument layer's tracker believes, and it should.
        self.piezo_nm = float(waveform[0, -1] * cal.piezo_nm_per_volt)

        junction_v = cal.voltage_input_sign * bias_v
        current_a = g0 * G0_SIEMENS * junction_v
        current_v = current_a * cal.preamp_gain_v_per_a + cal.current_zero_v

        current_v += self.rng.normal(0.0, self.noise_v_rms, current_v.shape)
        voltage_v = bias_v + self.rng.normal(0.0, self.noise_v_rms * 4,
                                             bias_v.shape)

        if self.cfg.channels.has_piezo_sense:
            # The driver box's monitor output follows the command: the same
            # displacement, expressed in the sense line's own volts-per-nm,
            # seen with the same delay as the other inputs, plus a little
            # noise from the low-res card.
            sense_v = (piezo_v * cal.piezo_nm_per_volt / cal.sense_nm_per_volt
                       + cal.sense_zero_v
                       + self.rng.normal(0.0, 2e-4, piezo_v.shape))
            lim = self.cfg.channels.sense_ai_range_v
            self.last_sense_v = np.clip(sense_v, -lim, lim)
        else:
            self.last_sense_v = None

        limit = self.cfg.channels.ai_range_v
        return np.clip(np.stack([voltage_v, current_v]), -limit, limit)

    # -- physics ----------------------------------------------------------

    def _conductance(self, position_nm: np.ndarray) -> np.ndarray:
        """Conductance in G0 along a trajectory.

        Three regimes, selected per sample: metallic contact while the tip is
        past the surface; a molecular plateau for a while after it breaks, if
        a molecule bridged; then tunnelling, decaying about a decade per
        angstrom.

        The junction has memory, so a little state crosses play boundaries:
        where the last break happened, and whether a molecule caught. The
        molecule is rolled once per break, not once per sample -- a per-sample
        roll would produce white noise between the two plateaus rather than a
        plateau at one of them.
        """
        n = position_nm.size
        penetration = position_nm - self.surface_nm
        contact = penetration > 0.0

        self._condition_tip(float(penetration.max()) if n else 0.0)

        g0 = np.empty(n, dtype=float)
        if contact.any():
            # The last atom holds for a short stretch before it lets go. That
            # plateau is why the 1 G0 peak exists at all -- a contact that
            # swept smoothly through 1 G0 would put no more counts there than
            # anywhere else, and the histogram would have no ruler on it.
            plateau = self.gold_plateau_nm
            single_atom = contact & (penetration <= plateau)
            metallic = contact & (penetration > plateau)

            g0[single_atom] = 1.0 + 0.04 * self.rng.normal(
                size=int(single_atom.sum()))
            g0[metallic] = (1.0 + 4.0 * (penetration[metallic] - plateau)
                            + 0.5 * self.rng.normal(size=int(metallic.sum())))

        broken = ~contact
        if not broken.any():
            self._snap_nm = None      # still closed; next break is a new one
            return g0

        # Where was the tip when it last left contact? Within this play if it
        # broke here, otherwise whatever the previous play left behind.
        index = np.arange(n)
        last_contact = np.maximum.accumulate(np.where(contact, index, -1))

        broke_here = bool((contact[:-1] & broken[1:]).any()) if n > 1 else False
        if broke_here:
            self._roll_molecule()
        elif self._snap_nm is None:
            # Cold start, already out of contact: tunnel from the surface.
            self._snap_nm = float(self.surface_nm)
            self._mol_g0 = None

        snap = np.where(last_contact >= 0,
                        position_nm[np.maximum(last_contact, 0)],
                        self._snap_nm)
        if broke_here:
            self._snap_nm = float(snap[-1])

        stretched = np.maximum(0.0, snap[broken] - position_nm[broken])

        if self._mol_g0 is not None:
            beyond = np.maximum(0.0, stretched - self._mol_len_nm)
            g0[broken] = np.where(
                stretched < self._mol_len_nm,
                self._mol_g0 * (1.0 + 0.05 * self.rng.normal(
                    size=stretched.size)),
                self._mol_g0 * 10.0 ** (-10.0 * beyond))
        else:
            g0[broken] = self._snap_g0 * 10.0 ** (-10.0 * stretched)

        return g0

    def _roll_molecule(self) -> None:
        """Decide, once per break, whether a molecule bridged the gap."""
        self._snap_g0 = 1.0
        if self.rng.random() < self.p_molecule * self._tip_quality:
            self._mol_g0 = 10.0 ** (self.molecule_log_g0
                                    + 0.25 * self.rng.normal())
            self._mol_len_nm = abs(self.rng.normal(0.6, 0.25))
        else:
            self._mol_g0 = None
            self._mol_len_nm = 0.0

    def _condition_tip(self, max_penetration_nm: float) -> None:
        """Hard contact blunts the tip; a hard smash restores it.

        Once per play. Per sample, the tip would be ruined in a millisecond.
        """
        if max_penetration_nm > 20.0:
            self._tip_quality = 1.0
            self.surface_nm += self.rng.normal(0.0, 0.5)
        elif max_penetration_nm > 3.0:
            self._tip_quality = max(0.15, self._tip_quality - 0.01)
