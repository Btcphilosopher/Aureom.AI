"""Thermal digital twin (spec item 35): lumped-mass heat generation & cooling."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ThermalParams:
    thermal_mass_j_per_k: float       # module/pack thermal mass (mass * specific heat)
    convective_coefficient_w_per_k: float
    coolant_temp_c: float = 25.0


@dataclass
class ThermalResult:
    heat_generated_w: float
    steady_state_temp_c: float
    temperature_trace_c: np.ndarray
    required_cooling_duty_w: float


class ThermalTwin:
    def cell_heat_generation_w(self, current_a: float, resistance_ohm: float, entropic_coefficient_w: float = 0.0) -> float:
        """Joule heating I^2R plus a (small, configurable) entropic heat term."""
        return current_a ** 2 * resistance_ohm + entropic_coefficient_w

    def simulate(self, params: ThermalParams, heat_generated_w: float, ambient_temp_c: float, duration_s: float, dt_s: float = 10.0) -> ThermalResult:
        steps = max(1, int(duration_s / dt_s))
        temp = ambient_temp_c
        trace = np.zeros(steps)
        for i in range(steps):
            cooling_w = params.convective_coefficient_w_per_k * (temp - params.coolant_temp_c)
            net_w = heat_generated_w - cooling_w
            dtemp = net_w / params.thermal_mass_j_per_k * dt_s
            temp += dtemp
            trace[i] = temp

        steady_state_temp = params.coolant_temp_c + heat_generated_w / max(params.convective_coefficient_w_per_k, 1e-6)
        required_cooling_duty = max(0.0, heat_generated_w)

        return ThermalResult(
            heat_generated_w=heat_generated_w,
            steady_state_temp_c=steady_state_temp,
            temperature_trace_c=trace,
            required_cooling_duty_w=required_cooling_duty,
        )
