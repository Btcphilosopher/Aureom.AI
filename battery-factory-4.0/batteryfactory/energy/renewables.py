"""
Renewable energy integration and factory battery storage (spec items 26-27).

SOLAR + WIND -> FACTORY LOAD -> BATTERY STORAGE -> GRID

A simple rule-based dispatch: serve load from on-site generation first,
then from the battery, then import from the grid; charge the battery from
any generation surplus (or, if enabled, from cheap grid hours) up to its
power/energy limits. Also serves as the peak-shaving/load-shifting model
for stationary factory battery storage.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class BatteryStorageSpec:
    capacity_kwh: float
    max_charge_kw: float
    max_discharge_kw: float
    round_trip_efficiency: float = 0.90
    initial_soc_pct: float = 50.0


@dataclass
class DispatchResult:
    hours: int
    grid_import_kwh: np.ndarray
    grid_export_kwh: np.ndarray
    battery_soc_pct: np.ndarray
    self_consumption_pct: float
    peak_grid_import_kw: float
    grid_cost: float


class RenewableDispatchSimulator:
    def dispatch(
        self,
        load_kw: np.ndarray,
        solar_kw: np.ndarray,
        wind_kw: np.ndarray,
        battery: BatteryStorageSpec,
        hourly_price: np.ndarray,
        peak_shave_target_kw: float | None = None,
    ) -> DispatchResult:
        n = len(load_kw)
        soc_kwh = battery.capacity_kwh * battery.initial_soc_pct / 100.0
        grid_import = np.zeros(n)
        grid_export = np.zeros(n)
        soc_trace = np.zeros(n)
        renewable_used_kwh = 0.0
        total_load_kwh = float(np.sum(load_kw))

        for h in range(n):
            generation = solar_kw[h] + wind_kw[h]
            net_load = load_kw[h] - generation

            if net_load > 0:
                renewable_used_kwh += generation
                shave_target = peak_shave_target_kw if peak_shave_target_kw is not None else float("inf")
                discharge_needed = net_load if net_load > shave_target else 0.0 if peak_shave_target_kw is not None else net_load
                discharge_kw = min(discharge_needed if peak_shave_target_kw is not None else net_load,
                                    battery.max_discharge_kw, soc_kwh * battery.round_trip_efficiency)
                discharge_kw = max(0.0, discharge_kw)
                soc_kwh -= discharge_kw / max(battery.round_trip_efficiency, 1e-6)
                remaining = net_load - discharge_kw
                grid_import[h] = max(0.0, remaining)
            else:
                surplus = -net_load
                renewable_used_kwh += load_kw[h]
                charge_kw = min(surplus, battery.max_charge_kw, (battery.capacity_kwh - soc_kwh))
                charge_kw = max(0.0, charge_kw)
                soc_kwh += charge_kw * battery.round_trip_efficiency
                grid_export[h] = max(0.0, surplus - charge_kw)

            soc_kwh = float(np.clip(soc_kwh, 0.0, battery.capacity_kwh))
            soc_trace[h] = 100.0 * soc_kwh / battery.capacity_kwh

        self_consumption_pct = 100.0 * min(renewable_used_kwh, total_load_kwh) / total_load_kwh if total_load_kwh > 0 else 0.0
        grid_cost = float(np.sum(grid_import * hourly_price) - np.sum(grid_export * hourly_price * 0.5))

        return DispatchResult(
            hours=n,
            grid_import_kwh=grid_import,
            grid_export_kwh=grid_export,
            battery_soc_pct=soc_trace,
            self_consumption_pct=self_consumption_pct,
            peak_grid_import_kw=float(np.max(grid_import)) if n else 0.0,
            grid_cost=grid_cost,
        )
