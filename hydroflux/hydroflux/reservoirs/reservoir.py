"""
Dynamic reservoir model: elevation-storage mass balance, and a water-value
engine that estimates the economic value of retaining one additional unit of
stored water via backward dynamic programming.

Mass balance:

    storage[t+1] = storage[t] + inflow[t] - release[t] - evaporation[t] - spill[t]

``storage`` is tracked in million cubic metres (mcm); water surface
elevation is derived from storage via a linear elevation-storage
relationship between (``minimum_level_m``, ``dead_storage_mcm``) and
(``maximum_level_m``, ``capacity_mcm``), which is exactly the quantity the
hydraulic head model needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

import numpy as np
import pandas as pd

from hydroflux.core.config import ReservoirConfig
from hydroflux.hydraulics.hydraulics import RHO_WATER, hydraulic_power

_MCM_PER_M3 = 1e-6


@dataclass
class ReservoirSimulationResult:
    storage_mcm: pd.Series
    level_m: pd.Series
    spill_m3s: pd.Series
    release_m3s: pd.Series


class Reservoir:
    """Wraps a :class:`ReservoirConfig` with elevation<->storage conversion
    and time-stepped mass balance."""

    def __init__(self, config: ReservoirConfig):
        self.config = config

    def level_to_storage(self, level_m: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
        c = self.config
        frac = (np.asarray(level_m, dtype=float) - c.minimum_level_m) / (c.maximum_level_m - c.minimum_level_m)
        frac = np.clip(frac, 0.0, 1.0)
        return c.dead_storage_mcm + frac * (c.capacity_mcm - c.dead_storage_mcm)

    def storage_to_level(self, storage_mcm: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
        c = self.config
        frac = (np.asarray(storage_mcm, dtype=float) - c.dead_storage_mcm) / (c.capacity_mcm - c.dead_storage_mcm)
        frac = np.clip(frac, 0.0, 1.0)
        return c.minimum_level_m + frac * (c.maximum_level_m - c.minimum_level_m)

    def simulate(
        self,
        inflow_m3s: pd.Series,
        release_m3s: pd.Series,
        evaporation_mm_per_day: Optional[pd.Series] = None,
        dt_hours: Optional[float] = None,
        initial_level_m: Optional[float] = None,
    ) -> ReservoirSimulationResult:
        """Time-step the mass balance. ``release_m3s`` is the *requested*
        release; actual release is capped so storage never falls below dead
        storage, and any excess inflow above full capacity is spilled."""

        c = self.config
        index = inflow_m3s.index
        n = len(index)
        if dt_hours is None:
            dt_hours = index.to_series().diff().median().total_seconds() / 3600.0 if n > 1 else 1.0

        inflow = inflow_m3s.reindex(index).fillna(0.0).values
        requested_release = release_m3s.reindex(index).fillna(0.0).values
        if evaporation_mm_per_day is not None:
            evap_mm = evaporation_mm_per_day.reindex(index).fillna(0.0).values
        else:
            evap_mm = np.full(n, c.evaporation_mm_per_day)

        storage = np.empty(n)
        level = np.empty(n)
        spill = np.empty(n)
        actual_release = np.empty(n)

        current_storage = self.level_to_storage(initial_level_m if initial_level_m is not None else c.initial_level_m)

        for t in range(n):
            inflow_vol = inflow[t] * dt_hours * 3600 * _MCM_PER_M3
            evap_vol = (evap_mm[t] / 1000.0) * c.surface_area_km2 * 1e6 * _MCM_PER_M3  # mm/day -> mcm/day
            evap_vol *= dt_hours / 24.0

            max_release_vol = max(current_storage - c.dead_storage_mcm + inflow_vol - evap_vol, 0.0)
            requested_vol = requested_release[t] * dt_hours * 3600 * _MCM_PER_M3
            release_vol = min(requested_vol, max_release_vol)

            balance = current_storage + inflow_vol - release_vol - evap_vol
            spill_vol = max(balance - c.capacity_mcm, 0.0)
            new_storage = np.clip(balance - spill_vol, c.dead_storage_mcm, c.capacity_mcm)

            storage[t] = new_storage
            level[t] = self.storage_to_level(new_storage)
            spill[t] = spill_vol / (dt_hours * 3600 * _MCM_PER_M3) if dt_hours > 0 else 0.0
            actual_release[t] = release_vol / (dt_hours * 3600 * _MCM_PER_M3) if dt_hours > 0 else 0.0
            current_storage = new_storage

        return ReservoirSimulationResult(
            storage_mcm=pd.Series(storage, index=index),
            level_m=pd.Series(level, index=index),
            spill_m3s=pd.Series(spill, index=index),
            release_m3s=pd.Series(actual_release, index=index),
        )


@dataclass
class WaterValueResult:
    states_mcm: np.ndarray
    value_function: np.ndarray  # shape (T, n_states), currency
    water_value_per_mcm: np.ndarray  # shape (T, n_states), currency/mcm
    index: pd.DatetimeIndex

    def water_value_at(self, t_index: int, storage_mcm: float) -> float:
        """Marginal value (currency/mcm) of stored water at a given
        timestep and storage level, via linear interpolation."""

        return float(np.interp(storage_mcm, self.states_mcm, self.water_value_per_mcm[t_index]))


class WaterValueEngine:
    """Estimates the economic value of stored water via backward dynamic
    programming: at each timestep and storage level, choose the release that
    maximises immediate revenue plus the (already-solved) value of the
    resulting future storage state.

    This lets the wider optimiser decide, at any timestep, whether to
    "generate electricity now or preserve water for a more valuable future
    period" by comparing the current price to the marginal water value.
    """

    def __init__(self, reservoir: Reservoir, turbine_efficiency: float = 0.90, n_storage_states: int = 21):
        self.reservoir = reservoir
        self.turbine_efficiency = turbine_efficiency
        self.n_storage_states = n_storage_states

    def compute(
        self,
        price: pd.Series,
        inflow_m3s: pd.Series,
        head_m: Union[float, pd.Series],
        max_release_m3s: float,
        min_release_m3s: float = 0.0,
        dt_hours: Optional[float] = None,
        n_release_choices: int = 11,
    ) -> WaterValueResult:
        c = self.reservoir.config
        index = price.index
        n_t = len(index)
        if dt_hours is None:
            dt_hours = index.to_series().diff().median().total_seconds() / 3600.0 if n_t > 1 else 1.0

        states = np.linspace(c.dead_storage_mcm, c.capacity_mcm, self.n_storage_states)
        releases = np.linspace(min_release_m3s, max_release_m3s, n_release_choices)
        release_vol = releases * dt_hours * 3600 * _MCM_PER_M3  # mcm, shape (n_release,)

        inflow = inflow_m3s.reindex(index).fillna(0.0).values
        price_v = price.reindex(index).fillna(0.0).values
        if isinstance(head_m, pd.Series):
            head_v = head_m.reindex(index).ffill().bfill().values
        else:
            head_v = np.full(n_t, float(head_m))

        value_function = np.zeros((n_t + 1, self.n_storage_states))
        v_next = np.zeros(self.n_storage_states)

        for t in range(n_t - 1, -1, -1):
            inflow_vol_t = inflow[t] * dt_hours * 3600 * _MCM_PER_M3
            next_storage_raw = states[:, None] + inflow_vol_t - release_vol[None, :]
            next_storage = np.clip(next_storage_raw, c.dead_storage_mcm, c.capacity_mcm)
            feasible = release_vol[None, :] <= (states[:, None] + inflow_vol_t - c.dead_storage_mcm)

            gen_w = hydraulic_power(releases, head_v[t], efficiency=self.turbine_efficiency, rho=RHO_WATER)
            gen_mwh = gen_w / 1e6 * dt_hours  # shape (n_release,)
            revenue = price_v[t] * gen_mwh[None, :]

            continuation = np.interp(next_storage.ravel(), states, v_next).reshape(next_storage.shape)
            total_value = np.where(feasible, revenue + continuation, -np.inf)
            best = np.max(total_value, axis=1)
            best = np.where(np.isfinite(best), best, 0.0)
            value_function[t] = best
            v_next = best

        vf = value_function[:-1]
        water_value = np.gradient(vf, states, axis=1)
        return WaterValueResult(states_mcm=states, value_function=vf, water_value_per_mcm=water_value, index=index)
