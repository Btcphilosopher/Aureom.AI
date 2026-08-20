"""
Die thermal model.

Uses a lumped single-node RC model (``Q = P*dt``, ``dT = (P_in - P_out)/C``)
for the overall die temperature, driven by total package power and the
:class:`~thermal.cooling_system.CoolingSystem`'s dissipation. Per-SM
"hotspot" temperatures are then derived from each SM's share of total
power relative to the die average, smoothed by heat diffusion to
physically-adjacent SMs (via :class:`~architecture.chip_layout.ChipLayout`)
so hotspots don't jump discontinuously between timesteps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from ..architecture.chip_layout import ChipLayout
from ..utils.config import ThermalConfig
from .cooling_system import CoolingSystem


@dataclass
class ThermalState:
    die_temp_c: float
    max_sm_temp_c: float
    hottest_sm_id: int
    sm_temps_c: List[float]
    cooling_watts: float
    net_power_watts: float


class HeatModel:
    def __init__(self, config: ThermalConfig, chip_layout: ChipLayout):
        self.config = config
        self.chip_layout = chip_layout
        self.cooling_system = CoolingSystem(
            cooling_type=config.cooling_type, tdp_watts=config.tdp_watts,
            ambient_temp_c=config.ambient_temp_c, max_safe_temp_c=config.max_safe_temp_c,
        )
        self.die_temp_c = config.ambient_temp_c
        self.sm_temps_c = [config.ambient_temp_c] * chip_layout.num_sms
        self._hotspot_gain = 22.0     # max degrees a fully-loaded SM can run above die avg
        self._diffusion_rate = 0.35   # per-step blending toward neighbour average

    def step(self, sm_power_watts: List[float], total_power_watts: float, dt_seconds: float) -> ThermalState:
        cooling_watts = self.cooling_system.dissipate(self.die_temp_c)
        net_watts = total_power_watts - cooling_watts
        d_temp = (net_watts * dt_seconds) / max(1e-6, self.config.thermal_mass_j_per_c)
        self.die_temp_c = max(self.config.ambient_temp_c, self.die_temp_c + d_temp)

        avg_power = (total_power_watts / len(sm_power_watts)) if sm_power_watts else 0.0
        target_temps = []
        for p in sm_power_watts:
            if avg_power > 1e-9:
                offset = ((p - avg_power) / avg_power) * self._hotspot_gain
            else:
                offset = 0.0
            target_temps.append(self.die_temp_c + max(-self._hotspot_gain, min(self._hotspot_gain, offset)))

        # One diffusion pass: blend each SM toward its neighbours' average
        # target, so heat visibly "spreads" across the die each timestep.
        new_temps = list(target_temps)
        for sm_id in range(self.chip_layout.num_sms):
            neighbours = self.chip_layout.neighbours(sm_id)
            if not neighbours:
                blended = target_temps[sm_id]
            else:
                neighbour_avg = sum(target_temps[n] for n in neighbours) / len(neighbours)
                blended = target_temps[sm_id] * (1 - self._diffusion_rate) + neighbour_avg * self._diffusion_rate
            # Move current temp toward the blended target rather than snapping to it.
            prev = self.sm_temps_c[sm_id]
            new_temps[sm_id] = prev + (blended - prev) * 0.6
        self.sm_temps_c = new_temps

        hottest_sm_id = max(range(len(self.sm_temps_c)), key=lambda i: self.sm_temps_c[i]) if self.sm_temps_c else -1
        max_sm_temp = self.sm_temps_c[hottest_sm_id] if hottest_sm_id >= 0 else self.die_temp_c

        return ThermalState(
            die_temp_c=self.die_temp_c, max_sm_temp_c=max_sm_temp, hottest_sm_id=hottest_sm_id,
            sm_temps_c=list(self.sm_temps_c), cooling_watts=cooling_watts, net_power_watts=net_watts,
        )

    def hotspot_map(self) -> Dict[int, float]:
        return {i: t for i, t in enumerate(self.sm_temps_c)}
