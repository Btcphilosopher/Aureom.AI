"""Storage-temperature profile generation.

A :class:`TemperatureProfile` describes the *ambient* (freezer air /
truck / cabinet) temperature a stored product is exposed to over time: a
baseline setpoint plus a list of discrete excursions (door-openings,
transport handling, equipment failures). Each excursion is a simple
triangular pulse -- linear ramp from baseline up to a peak and back down
-- which is enough to distinguish "a brief excursion to -12 degC
followed by return to -20 degC" from "uninterrupted -20 degC storage", as
required, without needing a full building-thermal-model.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TemperatureExcursion:
    start_time_s: float
    duration_s: float
    peak_temperature_c: float
    label: str = ""

    def temperature_offset_c(self, t_s: float, baseline_c: float) -> float:
        """Additive temperature offset from baseline at time t_s (0 outside the excursion)."""
        elapsed = t_s - self.start_time_s
        if elapsed < 0 or elapsed > self.duration_s or self.duration_s <= 0:
            return 0.0
        half = self.duration_s / 2.0
        peak_delta = self.peak_temperature_c - baseline_c
        if elapsed <= half:
            return peak_delta * (elapsed / half)
        return peak_delta * ((self.duration_s - elapsed) / half)


@dataclass(slots=True)
class TemperatureProfile:
    baseline_temperature_c: float
    excursions: list[TemperatureExcursion] = field(default_factory=list)

    def add_excursion(
        self, start_time_s: float, duration_s: float, peak_temperature_c: float, label: str = ""
    ) -> "TemperatureProfile":
        self.excursions.append(
            TemperatureExcursion(start_time_s, duration_s, peak_temperature_c, label)
        )
        return self

    def temperature_at(self, t_s: float) -> float:
        total_offset = sum(e.temperature_offset_c(t_s, self.baseline_temperature_c) for e in self.excursions)
        return self.baseline_temperature_c + total_offset

    def active_excursion_amplitude_c(self, t_s: float) -> float:
        """Instantaneous departure from baseline (0 when no excursion active)."""
        return abs(self.temperature_at(t_s) - self.baseline_temperature_c)

    def sample(self, duration_s: float, dt_s: float) -> list[tuple[float, float]]:
        from icecream_x.core.timestep import time_grid

        return [(t, self.temperature_at(t)) for t in time_grid(duration_s, dt_s)]


def uninterrupted(baseline_temperature_c: float) -> TemperatureProfile:
    return TemperatureProfile(baseline_temperature_c=baseline_temperature_c)
