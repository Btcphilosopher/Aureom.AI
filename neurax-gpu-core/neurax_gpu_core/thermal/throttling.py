"""
Thermal throttling controller: a simplified DVFS response curve mapping the
hottest point on the die to a clock-scaling factor. This is the mechanism
that couples the thermal system back into performance -- a hot chip really
does run its next timestep's cycles more slowly here, exactly as in
silicon.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..utils.config import ThermalConfig


@dataclass
class ThrottleDecision:
    scaling_factor: float
    is_throttling: bool
    is_critical: bool
    max_temp_c: float


class ThrottlingController:
    MIN_SCALE_AT_THROTTLE = 0.92
    MIN_SCALE_AT_CRITICAL = 0.45

    def __init__(self, config: ThermalConfig):
        self.config = config
        self.throttle_events = 0
        self.throttled_timesteps = 0
        self.critical_timesteps = 0
        self._was_throttling = False

    def evaluate(self, max_temp_c: float) -> ThrottleDecision:
        cfg = self.config
        if max_temp_c < cfg.throttle_temp_c:
            scale = 1.0
            throttling = False
            critical = False
        elif max_temp_c < cfg.critical_temp_c:
            span = max(1e-6, cfg.critical_temp_c - cfg.throttle_temp_c)
            frac = (max_temp_c - cfg.throttle_temp_c) / span
            scale = self.MIN_SCALE_AT_THROTTLE - frac * (self.MIN_SCALE_AT_THROTTLE - self.MIN_SCALE_AT_CRITICAL)
            throttling = True
            critical = False
        else:
            scale = self.MIN_SCALE_AT_CRITICAL
            throttling = True
            critical = True

        if throttling:
            self.throttled_timesteps += 1
            if not self._was_throttling:
                self.throttle_events += 1
        if critical:
            self.critical_timesteps += 1
        self._was_throttling = throttling

        return ThrottleDecision(
            scaling_factor=max(0.0, min(1.0, scale)), is_throttling=throttling,
            is_critical=critical, max_temp_c=max_temp_c,
        )
