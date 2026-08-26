"""
Festival crowd simulation: per-event crowd density and "hype" energy that
rises with exciting moments (drift score gains, close overtakes, race
finishes) and decays otherwise. Feeds ``audio.radio_system`` (DJ
commentary triggers) and ``rendering`` atmosphere without owning any
presentation logic itself.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CrowdState:
    density: float = 0.4     # 0..1, how packed the venue is
    energy: float = 0.2      # 0..1, current hype level
    peak_energy_today: float = 0.0

    def pulse(self, magnitude: float) -> None:
        """A discrete exciting moment (overtake, big drift bank, photo
        finish) -- kicks energy up sharply, capped at 1.0."""
        self.energy = min(1.0, self.energy + magnitude)
        self.peak_energy_today = max(self.peak_energy_today, self.energy)

    def update(self, dt: float, nearby_action_intensity: float, festival_tier: int) -> None:
        """``nearby_action_intensity`` in [0, 1] -- a continuous read of
        "how much is happening right now" (speed, drift angle, proximity
        of a close race) supplied by the caller each tick."""
        target_density = min(1.0, 0.25 + festival_tier * 0.12)
        self.density += (target_density - self.density) * min(1.0, dt * 0.05)

        decay = 0.06 * dt
        gain = nearby_action_intensity * self.density * 0.8 * dt
        self.energy = max(0.0, min(1.0, self.energy + gain - decay))
        self.peak_energy_today = max(self.peak_energy_today, self.energy)

    @property
    def cheer_intensity(self) -> float:
        """0..1 composite used directly by audio/rendering -- crowd noise
        volume, fireworks trigger threshold, hologram display brightness."""
        return self.energy * (0.4 + 0.6 * self.density)

    def reset_daily_peak(self) -> None:
        self.peak_energy_today = 0.0
