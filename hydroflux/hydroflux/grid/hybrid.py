"""
Hybrid energy system support: combine hydro generation with wind, solar,
battery, hydrogen or grid import/export series, and compare storage
technology options for a given price signal.

HydroFlux does not simulate wind/solar/battery physics itself -- the
specification is explicit that it should optimise the *complete system
where data is provided* -- so these components take pre-computed generation
series (or a simple battery model) and focus on the dispatch/aggregation
layer that ties them to the hydro system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class HybridComponent:
    name: str
    generation_mw: Optional[pd.Series] = None
    capacity_mw: Optional[float] = None
    cost_per_mwh: float = 0.0


@dataclass
class BatteryConfig:
    capacity_mwh: float
    power_mw: float
    round_trip_efficiency: float = 0.90


@dataclass
class HybridDispatchResult:
    total_generation_mw: pd.Series
    battery_charge_mw: pd.Series
    battery_discharge_mw: pd.Series
    battery_soc_mwh: pd.Series
    grid_export_mw: pd.Series
    revenue: float


class HybridSystem:
    def __init__(self, hydro_generation_mw: pd.Series, components: list[HybridComponent] | None = None, battery: Optional[BatteryConfig] = None):
        self.hydro_generation_mw = hydro_generation_mw
        self.components = components or []
        self.battery = battery

    def combined_generation(self) -> pd.Series:
        total = self.hydro_generation_mw.copy()
        for component in self.components:
            if component.generation_mw is not None:
                total = total.add(component.generation_mw.reindex(total.index).fillna(0.0), fill_value=0.0)
        return total

    def dispatch(self, price: pd.Series, dt_hours: float = 1.0, initial_soc_mwh: Optional[float] = None) -> HybridDispatchResult:
        """Battery dispatch via a simple price-threshold heuristic: charge
        from surplus/cheap generation, discharge when price is high."""

        gen = self.combined_generation()
        price_aligned = price.reindex(gen.index).fillna(0.0)

        if self.battery is None:
            return HybridDispatchResult(
                total_generation_mw=gen,
                battery_charge_mw=pd.Series(0.0, index=gen.index),
                battery_discharge_mw=pd.Series(0.0, index=gen.index),
                battery_soc_mwh=pd.Series(0.0, index=gen.index),
                grid_export_mw=gen,
                revenue=float((gen * price_aligned * dt_hours).sum()),
            )

        low_threshold = float(price_aligned.quantile(0.30))
        high_threshold = float(price_aligned.quantile(0.70))
        soc = self.battery.capacity_mwh / 2.0 if initial_soc_mwh is None else initial_soc_mwh

        charge = np.zeros(len(gen))
        discharge = np.zeros(len(gen))
        soc_series = np.zeros(len(gen))
        export = np.zeros(len(gen))

        for i, (p, g) in enumerate(zip(price_aligned.values, gen.values)):
            if p <= low_threshold and soc < self.battery.capacity_mwh:
                headroom = self.battery.capacity_mwh - soc
                c = min(self.battery.power_mw, headroom / (self.battery.round_trip_efficiency * dt_hours))
                soc += c * self.battery.round_trip_efficiency * dt_hours
                charge[i] = c
                export[i] = max(g - c, 0.0)
            elif p >= high_threshold and soc > 0:
                d = min(self.battery.power_mw, soc / dt_hours)
                soc -= d * dt_hours
                discharge[i] = d
                export[i] = g + d
            else:
                export[i] = g
            soc_series[i] = soc

        revenue = float(np.sum(export * price_aligned.values * dt_hours))
        return HybridDispatchResult(
            total_generation_mw=gen,
            battery_charge_mw=pd.Series(charge, index=gen.index),
            battery_discharge_mw=pd.Series(discharge, index=gen.index),
            battery_soc_mwh=pd.Series(soc_series, index=gen.index),
            grid_export_mw=pd.Series(export, index=gen.index),
            revenue=revenue,
        )


@dataclass
class StorageOption:
    name: str
    capacity_mwh: float
    power_mw: float
    round_trip_efficiency: float
    capex_per_mwh: float
    response_time_s: float = 1.0
    degradation_pct_per_year: float = 0.0


def compare_storage_options(options: list[StorageOption], price: pd.Series, dt_hours: float = 1.0) -> pd.DataFrame:
    """Compare storage technologies on the same price-arbitrage task and
    return a table ranked by simple arbitrage revenue per unit CAPEX."""

    rows = []
    for option in options:
        battery = BatteryConfig(capacity_mwh=option.capacity_mwh, power_mw=option.power_mw, round_trip_efficiency=option.round_trip_efficiency)
        system = HybridSystem(hydro_generation_mw=pd.Series(0.0, index=price.index), battery=battery)
        result = system.dispatch(price, dt_hours=dt_hours)
        capex = option.capacity_mwh * option.capex_per_mwh
        rows.append(
            {
                "name": option.name,
                "capacity_mwh": option.capacity_mwh,
                "power_mw": option.power_mw,
                "round_trip_efficiency": option.round_trip_efficiency,
                "response_time_s": option.response_time_s,
                "capex": capex,
                "arbitrage_revenue": result.revenue,
                "revenue_per_capex": result.revenue / capex if capex > 0 else np.nan,
            }
        )
    df = pd.DataFrame(rows).sort_values("revenue_per_capex", ascending=False).reset_index(drop=True)
    return df
