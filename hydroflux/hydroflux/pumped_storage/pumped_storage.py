"""
Pumped-storage optimiser: decide generate / pump / hold at every timestep to
maximise arbitrage value, subject to the upper reservoir's usable energy
capacity and pump/turbine ratings.

Storage is tracked in generation-equivalent MWh (the energy the stored
water would yield if released through the turbine at the assumed effective
head), so 1 MWh of stored energy always costs
``1 / (pump_efficiency * turbine_efficiency)`` MWh of pumping electricity to
create -- i.e. round-trip efficiency falls straight out of the pump and
turbine efficiencies already on the configuration, exactly as requested by
the specification's

    35 GBP/MWh -> pump
    180 GBP/MWh -> generate

example. Two solvers are provided:

* :meth:`PumpedStorageOptimiser.optimise_lp` -- an exact linear program
  (``scipy.optimize.linprog``, HiGHS) built with a sparse tridiagonal-style
  constraint matrix so it scales to a full year of hourly data.
* :meth:`PumpedStorageOptimiser.optimise_threshold` -- a simple,
  configurable price-threshold heuristic (pump below a low-price threshold,
  generate above a high-price threshold) for quick studies or as a
  transparent baseline to compare the LP result against.

``optimise`` picks the LP by default and falls back to the threshold
heuristic automatically above ``lp_max_horizon`` steps, where the dense
sparse-but-still-sizeable LP stops being the fastest option for a
demonstration-scale engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import linprog

from hydroflux.core.config import PumpedStorageConfig
from hydroflux.hydraulics.hydraulics import G, RHO_WATER


@dataclass
class PumpedStorageSchedule:
    generate_mw: pd.Series
    pump_mw: pd.Series
    storage_mwh: pd.Series
    revenue: float
    round_trip_efficiency: float
    method: str


class PumpedStorageOptimiser:
    def __init__(self, config: PumpedStorageConfig, effective_head_m: float, turbine_efficiency: Optional[float] = None):
        self.config = config
        self.effective_head_m = effective_head_m
        self.turbine_efficiency = turbine_efficiency if turbine_efficiency is not None else config.turbine.efficiency
        self.round_trip_efficiency = config.pump.efficiency * self.turbine_efficiency

    def usable_energy_capacity_mwh(self) -> float:
        usable_mcm = self.config.upper_reservoir.capacity_mcm - self.config.upper_reservoir.dead_storage_mcm
        volume_m3 = usable_mcm * 1e6
        energy_j = RHO_WATER * G * volume_m3 * self.effective_head_m * self.turbine_efficiency
        return energy_j / 3.6e9

    def optimise_threshold(
        self,
        price: pd.Series,
        pump_threshold: Optional[float] = None,
        generate_threshold: Optional[float] = None,
        dt_hours: Optional[float] = None,
        initial_storage_mwh: Optional[float] = None,
    ) -> PumpedStorageSchedule:
        index = price.index
        n = len(index)
        if dt_hours is None:
            dt_hours = index.to_series().diff().median().total_seconds() / 3600.0 if n > 1 else 1.0

        if pump_threshold is None:
            pump_threshold = float(np.quantile(price.values, 0.30))
        if generate_threshold is None:
            generate_threshold = float(np.quantile(price.values, 0.70))

        capacity = self.usable_energy_capacity_mwh()
        storage = capacity / 2.0 if initial_storage_mwh is None else initial_storage_mwh
        pump_capacity = self.config.pump.rated_power_mw

        generate = np.zeros(n)
        pump = np.zeros(n)
        storage_series = np.zeros(n)

        for t in range(n):
            p = price.iloc[t]
            if p <= pump_threshold and storage < capacity:
                headroom_mwh = capacity - storage
                pump_mw = min(pump_capacity, headroom_mwh / (self.round_trip_efficiency * dt_hours))
                storage += pump_mw * self.round_trip_efficiency * dt_hours
                pump[t] = pump_mw
            elif p >= generate_threshold and storage > 0:
                available_mwh = storage
                gen_mw = min(available_mwh / dt_hours, self.config.turbine.rated_power_mw)
                storage -= gen_mw * dt_hours
                generate[t] = gen_mw
            storage_series[t] = storage

        revenue = float(np.sum(price.values * generate * dt_hours - price.values * pump * dt_hours))
        return PumpedStorageSchedule(
            generate_mw=pd.Series(generate, index=index),
            pump_mw=pd.Series(pump, index=index),
            storage_mwh=pd.Series(storage_series, index=index),
            revenue=revenue,
            round_trip_efficiency=self.round_trip_efficiency,
            method="threshold",
        )

    def optimise_lp(
        self,
        price: pd.Series,
        dt_hours: Optional[float] = None,
        initial_storage_mwh: Optional[float] = None,
        turbine_capacity_mw: Optional[float] = None,
    ) -> PumpedStorageSchedule:
        index = price.index
        n = len(index)
        if dt_hours is None:
            dt_hours = index.to_series().diff().median().total_seconds() / 3600.0 if n > 1 else 1.0

        capacity = self.usable_energy_capacity_mwh()
        storage0 = capacity / 2.0 if initial_storage_mwh is None else initial_storage_mwh
        pump_cap = self.config.pump.rated_power_mw
        gen_cap = turbine_capacity_mw if turbine_capacity_mw is not None else self.config.turbine.rated_power_mw
        eff = self.round_trip_efficiency

        # Variable layout: [pump_1..T | generate_1..T | storage_1..T]
        n_vars = 3 * n
        rows = np.concatenate([np.arange(n), np.arange(1, n), np.arange(n), np.arange(n)])
        cols = np.concatenate(
            [
                2 * n + np.arange(n),  # s_t
                2 * n + np.arange(n - 1),  # s_{t-1} for t=2..T
                np.arange(n),  # pump_t
                n + np.arange(n),  # generate_t
            ]
        )
        data = np.concatenate(
            [
                np.ones(n),
                -np.ones(n - 1),
                np.full(n, -eff * dt_hours),
                np.full(n, dt_hours),
            ]
        )
        A_eq = sparse.csr_matrix((data, (rows, cols)), shape=(n, n_vars))
        b_eq = np.zeros(n)
        b_eq[0] = storage0

        lb = np.concatenate([np.zeros(n), np.zeros(n), np.zeros(n)])
        ub = np.concatenate([np.full(n, pump_cap), np.full(n, gen_cap), np.full(n, capacity)])
        bounds = list(zip(lb.tolist(), ub.tolist()))

        price_v = price.reindex(index).fillna(0.0).values
        c = np.concatenate([price_v * dt_hours, -price_v * dt_hours, np.zeros(n)])

        result = linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
        if not result.success:
            # Degenerate/infeasible edge case (e.g. zero-length horizon): fall back to no-op schedule.
            zeros = pd.Series(np.zeros(n), index=index)
            return PumpedStorageSchedule(zeros, zeros, pd.Series(np.full(n, storage0), index=index), 0.0, eff, "linear_programming")

        x = result.x
        pump = x[:n]
        generate = x[n : 2 * n]
        storage = x[2 * n : 3 * n]
        revenue = float(np.sum(price_v * generate * dt_hours - price_v * pump * dt_hours))

        return PumpedStorageSchedule(
            generate_mw=pd.Series(generate, index=index),
            pump_mw=pd.Series(pump, index=index),
            storage_mwh=pd.Series(storage, index=index),
            revenue=revenue,
            round_trip_efficiency=eff,
            method="linear_programming",
        )

    def optimise(
        self,
        price: pd.Series,
        method: str = "auto",
        lp_max_horizon: int = 2000,
        **kwargs,
    ) -> PumpedStorageSchedule:
        if method == "auto":
            method = "linear_programming" if len(price) <= lp_max_horizon else "threshold"
        if method == "linear_programming":
            return self.optimise_lp(price, **kwargs)
        return self.optimise_threshold(price, **kwargs)
