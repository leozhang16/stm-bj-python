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
  a finite conductance instead of running to zero. The built-in noise is far
  below a real card's; ``sim.ai_noise_v_rms`` in the config puts the card's
  own number on every input, and the floors where the rig has them
* the second output of a two-channel current amplifier, when the config
  reads one (``channels.current_channels = 2``): the same junction current
  through a higher gain, railed for as long as the junction is closed and
  carrying on below channel 1's noise floor once it opens
* the series resistor between the bias output and the junction
  (``keithley.series_resistance_ohm``) and the card's 1 Mohm input: in
  contact the current is capped at bias / R_series and the junction voltage
  on ai0 collapses to a few mV, exactly as on the rig, so the record looks
  like Igor's HighRes window and contact is found by the threshold, not by
  a railed amplifier
"""

from __future__ import annotations

import numpy as np

from .config import G0_SIEMENS, RigConfig


class SimulatedDaqSession:
    """Drop-in replacement for :class:`daq.DaqSession`."""

    def __init__(self, cfg: RigConfig, seed: int = 0,
                 group_delay_samples: int = 37,
                 noise_v_rms: float | None = None,
                 molecule_probability: float = 0.45,
                 molecule_log_g0: float = -3.5):
        self.cfg = cfg
        self.rng = np.random.default_rng(seed)
        # Channel 2's noise has a generator of its own, so that reading the
        # second output does not move a single sample of the first: channel
        # 1 is the same, sample for sample, with one channel read or two.
        self.rng2 = np.random.default_rng([int(seed), 2])
        self.granted_rate_hz = cfg.ramp.sample_rate_hz
        # DaqSession.last_play_seconds is how long the card took over the
        # last play by the PC's clock. A simulated play takes no real time,
        # so there is nothing to report: None, always.
        self.last_play_seconds: float | None = None
        self.last_read_seconds: float | None = None
        # Which way round this amplifier's two outputs are, fixed here for
        # the session: what sim.amplifier_output_sign says, or, when that is
        # None, the way round the config says the real amplifier is
        # (cal.current_sign) -- so a rig's config simulates right, and
        # un-ticking "flip the sign" later shows a wrong sign.
        sim = getattr(cfg, "sim", None)

        def way_round(value, channel: int) -> float:
            if value is None:
                return cfg.cal.sign_of(channel)
            return -1.0 if value < 0 else 1.0
        self.amplifier_output_sign = way_round(
            getattr(sim, "amplifier_output_sign", None), 1)
        self.amplifier_output_sign_2 = way_round(
            getattr(sim, "amplifier_output_sign_2", None), 2)
        self.idle_behavior = "maintain"
        self.ai_terminal_set: list[str] = []      # every live switch, for tests
        self.current_channels_set: list[int] = []
        self._retriggerable = True      # the fake card is an obliging one

        self.group_delay = int(group_delay_samples)
        # Input noise, volts rms per sample. Three sources, in this order:
        # the argument; the config's ``sim.ai_noise_v_rms``, a card's own
        # number, which every input then gets alike; the built-in 1.87 uV
        # on the current input with four times that on the junction
        # voltage, which is what every simulated run had before the config
        # could say, and still has when it does not.
        # ``voltage_noise_factor`` is the junction-voltage input's noise in
        # units of ``noise_v_rms``.
        card = getattr(getattr(cfg, "sim", None), "ai_noise_v_rms", None)
        if noise_v_rms is not None:
            self.noise_v_rms = float(noise_v_rms)
            self.voltage_noise_factor = 4.0
        elif card is not None:
            self.noise_v_rms = float(card)
            self.voltage_noise_factor = 1.0
        else:
            self.noise_v_rms = 1.87e-6
            self.voltage_noise_factor = 4.0
        # The card's input impedance on ai0: with the junction open it forms
        # a divider with the series resistor, which is why a 100 mV bias
        # reads about 90 mV on the rig.
        self.ai_input_ohm = 1.0e6
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

        # Channel 2 of a two-channel amplifier over the last play, like
        # DaqSession.last_current2_v: (n,) volts, None while it is not read.
        self.last_current2_v: np.ndarray | None = None
        # Its noise: the thermal noise of its own feedback resistor over
        # this bandwidth, the floor a transimpedance stage cannot get under
        # (0.4 pA rms at 1e9 V/A; a tenfold gain lowers it by sqrt(10)).
        self.channel2_bandwidth_hz = 1.0e4

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

    def set_ai_terminal(self, name: str) -> None:
        from .config import AI_TERMINALS
        if str(name).lower() not in AI_TERMINALS:
            raise ValueError(f"terminal mode {name!r} is not one of {sorted(AI_TERMINALS)}")
        self.cfg.channels.ai_terminal = str(name).lower()
        if self.cfg.channels.sense_in_record:
            self.cfg.channels.sense_terminal = self.cfg.channels.ai_terminal
        self.ai_terminal_set.append(self.cfg.channels.ai_terminal)

    def ai_terminal_modes(self) -> list[str]:
        return ["default", "rse", "nrse", "diff"]

    def set_current_channels(self, n: int) -> None:
        n = int(n)
        if n not in (1, 2):
            raise ValueError(f"current channels: 1 or 2, not {n}")
        if n == 2 and not self.cfg.channels.ai_current_2:
            raise ValueError("two current channels need channels.ai_current_2 "
                             "in the config: the input channel 2 is wired to")
        self.cfg.channels.current_channels = n
        self.current_channels_set.append(n)
        if n == 1:
            self.last_current2_v = None

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

        # The loop: bias output, series resistor, the junction (in parallel
        # with the card's input impedance on ai0), the amplifier at virtual
        # ground. The node between resistor and junction is what ai0 reads.
        g = g0 * G0_SIEMENS                              # siemens
        rs = max(0.0, self.cfg.keithley.series_resistance_ohm)
        zin = self.ai_input_ohm
        with np.errstate(divide="ignore", invalid="ignore"):
            r_j = np.where(g > 0, 1.0 / np.maximum(g, 1e-30), np.inf)
            r_par = np.where(np.isinf(r_j), zin, r_j * zin / (r_j + zin))
        node_v = bias_v * r_par / (rs + r_par)          # as the bias row sees it
        junction_v = cal.voltage_input_sign * node_v
        current_a = junction_v * g                       # through the junction
        # The Keithley's current suppress, when a simulated amplifier is
        # attached and has it switched on: a set current subtracted at the
        # input before the gain, which is what Find suppress sweeps.
        k = getattr(self, "keithley", None)
        if k is not None and getattr(k, "suppress_on", False):
            current_a = current_a - k.suppress_ua * 1e-6
        # Which way round the simulated amplifier's outputs are (set when
        # the session was made: see __init__).
        out_sign, out_sign_2 = self.amplifier_output_sign, self.amplifier_output_sign_2
        current_v = out_sign * current_a * cal.preamp_gain_v_per_a + cal.current_zero_v

        current_v += self.rng.normal(0.0, self.noise_v_rms, current_v.shape)
        voltage_v = node_v + self.rng.normal(
            0.0, self.noise_v_rms * self.voltage_noise_factor, bias_v.shape)

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

        if self.cfg.channels.two_current_channels:
            # The amplifier's other output: the same current through
            # channel 2's gain, on channel 2's offset, with the thermal
            # noise of channel 2's feedback resistor, and clipped where the
            # card's range ends -- which is where it sits for as long as
            # the junction is closed.
            gain2 = cal.preamp_gain_2_v_per_a
            k_t = 1.380649e-23 * 295.0
            noise2_a = np.sqrt(4.0 * k_t * self.channel2_bandwidth_hz / gain2)
            current2_v = (out_sign_2 * current_a * gain2 + cal.current_zero_2_v
                          + self.rng2.normal(0.0, noise2_a * gain2, current_a.shape)
                          + self.rng2.normal(0.0, self.noise_v_rms, current_a.shape))
            self.last_current2_v = np.clip(current2_v, -limit, limit)
        else:
            self.last_current2_v = None

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
            # Deeper in, the neck is a few atoms across and loses them one at
            # a time as it is pulled: integer-ish steps every 0.125 nm with a
            # slight slope within each, 5 % noise. A pull that starts 0.5 nm
            # in shows 4, 3, 2, 1 G0 on the way out, as Igor's traces do.
            x = 8.0 * (penetration[metallic] - plateau)
            g0[metallic] = (1.0 + np.floor(x) + 0.3 * (x - np.floor(x))
                            + 0.05 * self.rng.normal(size=int(metallic.sum())))

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

    def move_surface(self, delta_nm: float) -> None:
        """The coarse actuator: the sample moves, the piezo does not. The
        junction's memory of where it last broke is a place on the sample,
        so it moves with it -- otherwise a sample backed off by 150 nm
        would still read as a 1 G0 contact."""
        self.surface_nm += delta_nm
        if self._snap_nm is not None:
            self._snap_nm += delta_nm

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
