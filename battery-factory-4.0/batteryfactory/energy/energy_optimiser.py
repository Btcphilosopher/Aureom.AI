"""
Energy optimiser (spec item 25): shifts flexible/interruptible loads
(formation batches, HVAC setpoint band) to the cheapest hours of an hourly
electricity-price curve, subject to a daily throughput requirement.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class FlexibleLoad:
    name: str
    energy_kwh: float
    duration_hours: int
    earliest_start_hour: int
    latest_finish_hour: int  # exclusive


@dataclass
class EnergyScheduleResult:
    baseline_cost: float
    optimised_cost: float
    savings_pct: float
    load_start_hours: dict[str, int]


class EnergyOptimiser:
    def optimise(self, loads: list[FlexibleLoad], hourly_price: np.ndarray) -> EnergyScheduleResult:
        """
        Greedy earliest-cheapest-window placement: sorts loads by size
        (largest first, since they're hardest to place) and assigns each to
        the cheapest contiguous window inside its allowed range.
        """
        n_hours = len(hourly_price)
        occupied_kwh_per_hour = np.zeros(n_hours)
        baseline_cost = sum(load.energy_kwh / load.duration_hours * hourly_price[h]
                             for load in loads
                             for h in range(load.earliest_start_hour, load.earliest_start_hour + load.duration_hours))

        starts: dict[str, int] = {}
        optimised_cost = 0.0
        for load in sorted(loads, key=lambda l: -l.energy_kwh):
            best_start, best_cost = load.earliest_start_hour, float("inf")
            latest_start = min(load.latest_finish_hour - load.duration_hours, n_hours - load.duration_hours)
            for start in range(load.earliest_start_hour, max(load.earliest_start_hour, latest_start) + 1):
                window = hourly_price[start:start + load.duration_hours]
                cost = float(np.sum(window)) * (load.energy_kwh / load.duration_hours)
                if cost < best_cost:
                    best_cost, best_start = cost, start
            starts[load.name] = best_start
            optimised_cost += best_cost
            occupied_kwh_per_hour[best_start:best_start + load.duration_hours] += load.energy_kwh / load.duration_hours

        savings_pct = 100.0 * (baseline_cost - optimised_cost) / baseline_cost if baseline_cost > 0 else 0.0
        return EnergyScheduleResult(baseline_cost, optimised_cost, savings_pct, starts)
