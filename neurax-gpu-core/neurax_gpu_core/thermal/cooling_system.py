"""
Cooling system model.

Converts the die-to-ambient temperature delta into a dissipated-watts
figure. Air cooling ramps a "fan curve" coefficient with temperature;
liquid and vapor-chamber solutions dissipate more linearly and with a
higher ceiling, at higher assumed cost (captured qualitatively here, tied
into cost trade-offs by the optimisation layer).
"""

from __future__ import annotations

from dataclasses import dataclass


BASE_COEFFICIENTS = {
    "air": 3.2,             # W per degree C at full fan speed
    "vapor_chamber": 4.4,
    "liquid": 6.5,
}

CAPACITY_HEADROOM = {
    "air": 1.10,
    "vapor_chamber": 1.25,
    "liquid": 1.55,
}


@dataclass
class CoolingSystem:
    cooling_type: str
    tdp_watts: float
    ambient_temp_c: float
    max_safe_temp_c: float

    def __post_init__(self) -> None:
        self.cooling_type = self.cooling_type if self.cooling_type in BASE_COEFFICIENTS else "air"
        self.base_coefficient = BASE_COEFFICIENTS[self.cooling_type]
        self.capacity_watts = self.tdp_watts * CAPACITY_HEADROOM[self.cooling_type]
        self.last_fan_speed_fraction = 0.0

    def fan_speed_fraction(self, die_temp_c: float) -> float:
        span = max(1.0, self.max_safe_temp_c - self.ambient_temp_c)
        frac = (die_temp_c - self.ambient_temp_c) / span
        return min(1.0, max(0.0, frac))

    def dissipate(self, die_temp_c: float) -> float:
        """Watts removed this instant, given the current die temperature."""
        delta = max(0.0, die_temp_c - self.ambient_temp_c)
        if self.cooling_type == "air":
            fan = 0.35 + 0.65 * self.fan_speed_fraction(die_temp_c)
            self.last_fan_speed_fraction = fan
        else:
            # Liquid / vapor chamber solutions run near-constant pump/flow rate.
            fan = 0.85 + 0.15 * self.fan_speed_fraction(die_temp_c)
            self.last_fan_speed_fraction = fan
        watts = self.base_coefficient * fan * delta
        return min(watts, self.capacity_watts)
