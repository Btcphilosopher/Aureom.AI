"""
Tidal barrage / lagoon / basin operating-schedule optimiser.

Implements the four operating modes from the specification as explicit,
inspectable rules rather than a black box, simulated step-by-step because
basin level is a genuine state variable (this step's decision affects the
head available next step):

* ``ebb_generation`` -- sluice open to fill the basin toward sea level on
  the flood tide, hold near high water, then generate on the ebb once head
  exceeds the minimum generating head.
* ``flood_generation`` -- mirror image: generate while the tide floods
  (sea > basin + min head), then sluice the basin back down on the ebb.
* ``two_way`` -- generate in whichever direction currently has enough head,
  sluice freely below the threshold so the basin keeps tracking sea level
  for the next half-cycle.
* ``pump_assisted`` -- as ``two_way``/``ebb_generation``, plus optional
  pumping (using the turbines as pumps) near slack water when electricity
  is cheap, to raise the head available for the next generating half-cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from hydroflux.core.config import TidalConfig, TurbineType
from hydroflux.hydraulics.hydraulics import RHO_SEAWATER
from hydroflux.tidal.tidal import basin_area_m2, flow_to_equalise, sea_level_series
from hydroflux.turbines.turbines import Turbine, default_efficiency_curve

_PUMP_EFFICIENCY_DEFAULT = 0.85


@dataclass
class TidalBarrageSchedule:
    sea_level_m: pd.Series
    basin_level_m: pd.Series
    head_m: pd.Series
    flow_m3s: pd.Series  # positive = sea -> basin
    power_mw: pd.Series
    pumped_energy_mwh: pd.Series
    mode: pd.Series  # per-step operating mode label
    annual_energy_mwh: float
    revenue: float


class TidalBarrageOptimiser:
    def __init__(
        self,
        tidal_config: TidalConfig,
        turbine_rated_flow_m3s: float,
        turbine_rated_power_mw: float,
        sluice_capacity_m3s: float | None = None,
        pump_fraction: float = 0.15,
        pump_efficiency: float = _PUMP_EFFICIENCY_DEFAULT,
    ):
        self.config = tidal_config
        self.turbine = Turbine(
            id="barrage_turbines",
            type=TurbineType.BULB,
            rated_power_mw=turbine_rated_power_mw,
            rated_flow_m3s=turbine_rated_flow_m3s,
            minimum_flow_m3s=turbine_rated_flow_m3s * 0.1,
            maximum_flow_m3s=turbine_rated_flow_m3s,
            minimum_head_m=tidal_config.minimum_generating_head_m,
            maximum_head_m=None,
            efficiency_curve=default_efficiency_curve(TurbineType.BULB),
            design_head_m=max(tidal_config.tidal_amplitude_m, tidal_config.minimum_generating_head_m * 2),
        )
        self.sluice_capacity_m3s = sluice_capacity_m3s or tidal_config.sluice_capacity_m3s
        self.pump_fraction = pump_fraction
        self.pump_efficiency = pump_efficiency

    def _step(self, mode: str, sea: float, basin: float, dt_hours: float, low_price: bool) -> tuple[float, float, float, str]:
        """Return (flow_m3s, power_mw, pumped_energy_mwh, label) for one step."""

        area = basin_area_m2(self.config)
        min_head = self.config.minimum_generating_head_m
        ebb_head = basin - sea  # basin higher -> generate basin -> sea
        flood_head = sea - basin  # sea higher -> generate sea -> basin

        def capped(head, capacity):
            return float(np.sign(head)) * min(capacity, abs(flow_to_equalise(head, area, dt_hours)))

        flow = 0.0
        power = 0.0
        pumped_mwh = 0.0
        label = "hold"

        if mode in ("ebb_generation", "pump_assisted") and ebb_head >= min_head:
            magnitude = min(self.turbine.maximum_flow_m3s, abs(flow_to_equalise(ebb_head, area, dt_hours)))
            flow = -magnitude
            power = self.turbine.output_power_mw(magnitude, ebb_head)
            label = "ebb_generation"
        elif mode == "flood_generation" and flood_head >= min_head:
            magnitude = min(self.turbine.maximum_flow_m3s, abs(flow_to_equalise(flood_head, area, dt_hours)))
            flow = magnitude
            power = self.turbine.output_power_mw(magnitude, flood_head)
            label = "flood_generation"
        elif mode == "two_way":
            if ebb_head >= min_head:
                magnitude = min(self.turbine.maximum_flow_m3s, abs(flow_to_equalise(ebb_head, area, dt_hours)))
                flow = -magnitude
                power = self.turbine.output_power_mw(magnitude, ebb_head)
                label = "ebb_generation"
            elif flood_head >= min_head:
                magnitude = min(self.turbine.maximum_flow_m3s, abs(flow_to_equalise(flood_head, area, dt_hours)))
                flow = magnitude
                power = self.turbine.output_power_mw(magnitude, flood_head)
                label = "flood_generation"

        if label == "hold":
            if mode == "ebb_generation" and sea > basin:
                # Flood tide: sluice the basin up toward sea level to prepare for ebb generation.
                flow = capped(sea - basin, self.sluice_capacity_m3s)
                label = "sluice_fill"
            elif mode == "flood_generation" and basin > sea:
                flow = capped(sea - basin, self.sluice_capacity_m3s)
                label = "sluice_empty"
            elif mode == "two_way":
                flow = capped(sea - basin, self.sluice_capacity_m3s)
                label = "sluice"
            elif mode == "pump_assisted" and low_price and abs(ebb_head) < min_head:
                pump_capacity = self.turbine.maximum_flow_m3s * self.pump_fraction
                # Pump toward building ebb-generation head (basin above sea).
                magnitude = min(pump_capacity, abs(flow_to_equalise(min_head - ebb_head, area, dt_hours)))
                flow = magnitude  # sea -> basin, raises basin level
                from hydroflux.hydraulics.hydraulics import G

                pumped_mwh = (RHO_SEAWATER * G * magnitude * abs(flood_head if flood_head > 0 else min_head) / self.pump_efficiency) / 1e6 * dt_hours
                label = "pump"

        return flow, power, pumped_mwh, label

    def optimise_schedule(
        self,
        index: pd.DatetimeIndex,
        mode: str | None = None,
        price: pd.Series | None = None,
        low_price_quantile: float = 0.25,
    ) -> TidalBarrageSchedule:
        mode = mode or self.config.mode
        sea = sea_level_series(index, self.config)
        n = len(index)
        dt_hours = index.to_series().diff().median().total_seconds() / 3600.0 if n > 1 else 1.0

        low_threshold = float(price.quantile(low_price_quantile)) if price is not None else None

        basin_level = np.empty(n)
        head = np.empty(n)
        flow = np.empty(n)
        power = np.empty(n)
        pumped = np.empty(n)
        labels: list[str] = []

        current_basin = self.config.initial_basin_level_m
        for t in range(n):
            low_price = price is not None and price.iloc[t] <= low_threshold
            sea_t = float(sea.iloc[t])
            f, p, pmwh, label = self._step(mode, sea_t, current_basin, dt_hours, low_price)
            # Record the head that actually drove this step's decision (sea
            # and basin level *before* this step's flow updates the basin),
            # not the post-update level -- otherwise a generating step could
            # be reported against a head that no longer reflects why it
            # generated.
            head[t] = sea_t - current_basin
            area = basin_area_m2(self.config)
            current_basin = current_basin + f * dt_hours * 3600.0 / area
            basin_level[t] = current_basin
            flow[t] = f
            power[t] = p
            pumped[t] = pmwh
            labels.append(label)

        power_series = pd.Series(power, index=index)
        pumped_series = pd.Series(pumped, index=index)
        annual_energy = float(power_series.sum() * dt_hours)
        if price is not None:
            revenue = float((power_series * dt_hours * price.reindex(index).fillna(0.0)).sum() - (pumped_series * price.reindex(index).fillna(0.0)).sum())
        else:
            revenue = 0.0

        return TidalBarrageSchedule(
            sea_level_m=sea,
            basin_level_m=pd.Series(basin_level, index=index),
            head_m=pd.Series(head, index=index),
            flow_m3s=pd.Series(flow, index=index),
            power_mw=power_series,
            pumped_energy_mwh=pumped_series,
            mode=pd.Series(labels, index=index),
            annual_energy_mwh=annual_energy,
            revenue=revenue,
        )
