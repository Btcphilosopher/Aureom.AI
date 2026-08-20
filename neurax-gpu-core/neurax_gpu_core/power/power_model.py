"""
Power model: dynamic (CV^2f) + static (leakage) power draw, a simple
piecewise-linear DVFS voltage curve, and a TDP-regulation solver that finds
the highest clock a given workload activity level can sustain without
exceeding the configured power budget -- the power-capping half of DVFS
(the thermal-capping half lives in :mod:`thermal.throttling`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ..utils.config import PowerConfig


@dataclass
class PowerState:
    total_power_watts: float
    dynamic_power_watts: float
    static_power_watts: float
    memory_power_watts: float
    voltage_v: float
    freq_ghz: float
    sm_power_watts: List[float]


class PowerModel:
    def __init__(self, config: PowerConfig, num_sms: int, memory_power_coefficient_w: float = 55.0):
        self.config = config
        self.num_sms = num_sms
        self.memory_power_coefficient_w = memory_power_coefficient_w

        # Calibrate the dynamic-power constant from the configured spec-sheet
        # numbers: at boost clock, nominal(max) voltage and full activity,
        # dynamic power alone should consume (tdp - idle).
        denom = max(1e-9, (config.max_voltage_v ** 2) * config.boost_clock_ghz)
        self.k = max(0.0, (config.tdp_watts - config.idle_power_watts)) / denom

    def voltage_for_freq(self, freq_ghz: float) -> float:
        cfg = self.config
        if not cfg.dvfs_enabled:
            return cfg.voltage_nominal_v
        span = max(1e-9, cfg.boost_clock_ghz - cfg.base_clock_ghz)
        frac = (freq_ghz - cfg.base_clock_ghz) / span
        frac = min(1.0, max(0.0, frac))
        return cfg.min_voltage_v + frac * (cfg.max_voltage_v - cfg.min_voltage_v)

    def compute_power(self, freq_ghz: float, activity_factor: float,
                       sm_activity_fractions: List[float], bandwidth_utilisation: float) -> PowerState:
        activity_factor = min(1.0, max(0.0, activity_factor))
        voltage = self.voltage_for_freq(freq_ghz)
        dynamic = self.k * (voltage ** 2) * freq_ghz * activity_factor
        static = self.config.idle_power_watts * (voltage / max(1e-9, self.config.max_voltage_v))
        memory_power = self.memory_power_coefficient_w * min(1.0, max(0.0, bandwidth_utilisation))
        total = dynamic + static + memory_power

        n = max(1, len(sm_activity_fractions))
        weight_sum = sum(sm_activity_fractions) or 1.0
        static_share = static / n
        sm_power = [
            static_share + dynamic * (w / weight_sum) for w in (sm_activity_fractions or [1.0] * n)
        ]

        return PowerState(
            total_power_watts=total, dynamic_power_watts=dynamic, static_power_watts=static,
            memory_power_watts=memory_power, voltage_v=voltage, freq_ghz=freq_ghz, sm_power_watts=sm_power,
        )

    def max_freq_for_power_budget(self, activity_factor: float, bandwidth_utilisation: float,
                                   upper_bound_ghz: float) -> float:
        """Binary-search the highest frequency (<= upper_bound_ghz, itself
        possibly already thermally-derated) that keeps total power at or
        below the configured TDP, given the current workload activity."""
        lo, hi = self.config.base_clock_ghz * 0.3, max(self.config.base_clock_ghz * 0.3, upper_bound_ghz)
        budget = self.config.tdp_watts
        if self.compute_power(hi, activity_factor, [], bandwidth_utilisation).total_power_watts <= budget:
            return hi
        for _ in range(24):
            mid = (lo + hi) / 2
            p = self.compute_power(mid, activity_factor, [], bandwidth_utilisation).total_power_watts
            if p <= budget:
                lo = mid
            else:
                hi = mid
        return lo
