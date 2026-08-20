"""
GPU clock: combines thermal throttling and power-budget regulation into a
single effective core frequency for the *next* simulation timestep. This is
the DVFS control loop -- the thing that makes "TFLOPS" an emergent output
rather than a constant, since every downstream FLOPs figure is scaled by
whatever frequency comes out of here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..power.power_model import PowerModel
from ..thermal.throttling import ThrottleDecision, ThrottlingController
from ..utils.config import PowerConfig


@dataclass
class ClockDecision:
    freq_ghz: float
    voltage_v: float
    throttle: ThrottleDecision
    power_capped: bool


class GPUClock:
    def __init__(self, power_config: PowerConfig, throttling: ThrottlingController, power_model: PowerModel,
                 smoothing: float = 0.55):
        self.power_config = power_config
        self.throttling = throttling
        self.power_model = power_model
        self.smoothing = smoothing
        self.current_freq_ghz = power_config.boost_clock_ghz
        self.history: List[float] = []

    def decide(self, desired_activity_factor: float, max_temp_c: float,
               bandwidth_utilisation: float) -> ClockDecision:
        cfg = self.power_config
        throttle = self.throttling.evaluate(max_temp_c)
        thermal_ceiling = max(cfg.base_clock_ghz * 0.3, cfg.boost_clock_ghz * throttle.scaling_factor)

        power_capped_freq = self.power_model.max_freq_for_power_budget(
            activity_factor=desired_activity_factor, bandwidth_utilisation=bandwidth_utilisation,
            upper_bound_ghz=thermal_ceiling,
        )
        target = min(thermal_ceiling, power_capped_freq)
        target = max(cfg.base_clock_ghz * 0.3, target)

        new_freq = self.current_freq_ghz + (target - self.current_freq_ghz) * self.smoothing
        new_freq = max(cfg.base_clock_ghz * 0.3, min(cfg.boost_clock_ghz, new_freq))
        self.current_freq_ghz = new_freq
        self.history.append(new_freq)

        return ClockDecision(
            freq_ghz=new_freq, voltage_v=self.power_model.voltage_for_freq(new_freq),
            throttle=throttle, power_capped=(power_capped_freq < thermal_ceiling - 1e-6),
        )

    def average_freq_ghz(self, last_n: int = 1) -> float:
        if not self.history:
            return self.current_freq_ghz
        window = self.history[-last_n:]
        return sum(window) / len(window)
