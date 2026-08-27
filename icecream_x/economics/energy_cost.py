"""Energy cost, supporting a time-varying electricity price.

Electricity price can be a flat rate or a callable ``price(t_s) ->
currency/kWh`` (e.g. a time-of-use tariff), so overnight production runs
can be priced against off-peak rates.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

PriceSchedule = Callable[[float], float] | float


def _price_at(schedule: PriceSchedule, t_s: float) -> float:
    if callable(schedule):
        return schedule(t_s)
    return schedule


@dataclass(frozen=True, slots=True)
class EnergyCostResult:
    total_energy_kwh: float
    total_cost: float
    average_price_per_kwh: float


def flat_rate_cost(total_energy_j: float, price_per_kwh: float) -> EnergyCostResult:
    kwh = total_energy_j / 3_600_000.0
    cost = kwh * price_per_kwh
    return EnergyCostResult(total_energy_kwh=kwh, total_cost=cost, average_price_per_kwh=price_per_kwh)


def scheduled_cost(
    energy_time_series_j: list[tuple[float, float]], price_schedule: PriceSchedule
) -> EnergyCostResult:
    """Cost of a series of (timestamp_s, energy_added_j) increments against a price schedule."""
    total_kwh = 0.0
    total_cost = 0.0
    for t_s, energy_j in energy_time_series_j:
        kwh = energy_j / 3_600_000.0
        total_kwh += kwh
        total_cost += kwh * _price_at(price_schedule, t_s)
    avg_price = total_cost / total_kwh if total_kwh > 0 else 0.0
    return EnergyCostResult(total_energy_kwh=total_kwh, total_cost=total_cost, average_price_per_kwh=avg_price)
