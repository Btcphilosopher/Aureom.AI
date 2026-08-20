"""
Scenario engine: named, reproducible perturbations of a
:class:`~hydroflux.core.timeseries.ResourceTimeSeries` for planning and
climate studies, plus seeded stochastic ensemble generation for Monte Carlo
work.

Every scenario carries an explicit ``seed``; the same scenario + seed always
produces the same perturbed inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

from hydroflux.core.timeseries import ResourceTimeSeries


class ScenarioType(str, Enum):
    BASELINE = "baseline"
    HIGH_FLOW = "high_flow"
    LOW_FLOW = "low_flow"
    DROUGHT = "drought"
    FLOOD = "flood"
    HIGH_PRICE = "high_price"
    LOW_PRICE = "low_price"
    HIGH_DEMAND = "high_demand"
    LOW_DEMAND = "low_demand"
    CLIMATE_CHANGE = "climate_change"
    SEA_LEVEL_RISE = "sea_level_rise"
    TURBINE_FAILURE = "turbine_failure"
    RESERVOIR_CONSTRAINT = "reservoir_constraint"


@dataclass
class Scenario:
    name: str
    type: ScenarioType
    seed: int = 42
    flow_multiplier: float = 1.0
    price_multiplier: float = 1.0
    demand_multiplier: float = 1.0
    sea_level_rise_m: float = 0.0
    tidal_amplitude_multiplier: float = 1.0
    drought_severity: float = 0.0
    flood_severity: float = 0.0
    turbine_failure: Optional[dict] = None  # {"turbine_id":..., "start":..., "duration_hours":...}
    reservoir_min_level_offset_m: float = 0.0
    description: str = ""


def apply_scenario(resource: ResourceTimeSeries, scenario: Scenario) -> ResourceTimeSeries:
    """Return a new :class:`ResourceTimeSeries` with the scenario's
    perturbations applied. Reproducible: identical scenario -> identical
    output."""

    from hydroflux.hydrology.hydrology import drought_scenario_flow, flood_scenario_flow

    flow = resource.flow
    if flow is not None:
        flow = flow * scenario.flow_multiplier
        if scenario.drought_severity > 0:
            flow = drought_scenario_flow(flow, scenario.drought_severity)
        if scenario.flood_severity > 0:
            flow = flood_scenario_flow(flow, scenario.flood_severity)

    inflow = resource.inflow
    if inflow is not None:
        inflow = inflow * scenario.flow_multiplier
        if scenario.drought_severity > 0:
            inflow = drought_scenario_flow(inflow, scenario.drought_severity)
        if scenario.flood_severity > 0:
            inflow = flood_scenario_flow(inflow, scenario.flood_severity)

    price = resource.price * scenario.price_multiplier if resource.price is not None else None
    demand = resource.demand * scenario.demand_multiplier if resource.demand is not None else None
    water_level = resource.water_level + scenario.sea_level_rise_m if resource.water_level is not None else None

    return ResourceTimeSeries(
        index=resource.index,
        flow=flow,
        head=resource.head,
        water_level=water_level,
        tailwater_level=resource.tailwater_level,
        temperature=resource.temperature,
        price=price,
        demand=demand,
        inflow=inflow,
        metadata={**resource.metadata, "scenario": scenario.name, "seed": scenario.seed},
    )


def default_scenarios(seed: int = 42) -> list[Scenario]:
    """One representative scenario per :class:`ScenarioType`, with
    illustrative default magnitudes -- adjust for a specific study."""

    return [
        Scenario("Baseline", ScenarioType.BASELINE, seed=seed, description="Unmodified input data."),
        Scenario("High Flow", ScenarioType.HIGH_FLOW, seed=seed, flow_multiplier=1.3, description="+30% river flow."),
        Scenario("Low Flow", ScenarioType.LOW_FLOW, seed=seed, flow_multiplier=0.7, description="-30% river flow."),
        Scenario("Drought", ScenarioType.DROUGHT, seed=seed, drought_severity=0.6, description="Severe drought (peak compression)."),
        Scenario("Flood", ScenarioType.FLOOD, seed=seed, flood_severity=0.8, description="Extreme flood event."),
        Scenario("High Electricity Price", ScenarioType.HIGH_PRICE, seed=seed, price_multiplier=1.8, description="+80% electricity price."),
        Scenario("Low Electricity Price", ScenarioType.LOW_PRICE, seed=seed, price_multiplier=0.5, description="-50% electricity price."),
        Scenario("High Demand", ScenarioType.HIGH_DEMAND, seed=seed, demand_multiplier=1.4, description="+40% grid demand."),
        Scenario("Low Demand", ScenarioType.LOW_DEMAND, seed=seed, demand_multiplier=0.6, description="-40% grid demand."),
        Scenario(
            "Climate Change 2050",
            ScenarioType.CLIMATE_CHANGE,
            seed=seed,
            flow_multiplier=0.85,
            drought_severity=0.2,
            description="Reduced/altered flow regime under a mid-century climate scenario.",
        ),
        Scenario("Sea Level Rise", ScenarioType.SEA_LEVEL_RISE, seed=seed, sea_level_rise_m=0.5, tidal_amplitude_multiplier=1.05, description="+0.5 m mean sea level."),
        Scenario(
            "Turbine Failure",
            ScenarioType.TURBINE_FAILURE,
            seed=seed,
            turbine_failure={"turbine_id": "T1", "start_hour": 1000, "duration_hours": 240},
            description="Unplanned turbine outage.",
        ),
        Scenario("Reservoir Constraint", ScenarioType.RESERVOIR_CONSTRAINT, seed=seed, reservoir_min_level_offset_m=5.0, description="Tightened minimum reservoir level."),
    ]


def stochastic_flow_ensemble(
    base_flow: pd.Series,
    n_scenarios: int,
    relative_std: float = 0.15,
    seed: int = 42,
) -> list[pd.Series]:
    """Seeded ensemble of correlated (AR(1)) flow perturbations around a
    base flow series, for Monte Carlo studies."""

    rng = np.random.default_rng(seed)
    ensemble = []
    for i in range(n_scenarios):
        phi = 0.8
        noise = rng.normal(0.0, relative_std * base_flow.mean(), size=len(base_flow))
        ar_noise = np.zeros_like(noise)
        for t in range(1, len(noise)):
            ar_noise[t] = phi * ar_noise[t - 1] + noise[t]
        perturbed = np.maximum(base_flow.values + ar_noise, 0.0)
        ensemble.append(pd.Series(perturbed, index=base_flow.index, name=f"flow_scenario_{i}"))
    return ensemble


def stochastic_price_ensemble(
    base_price: pd.Series,
    n_scenarios: int,
    relative_std: float = 0.25,
    seed: int = 43,
) -> list[pd.Series]:
    rng = np.random.default_rng(seed)
    ensemble = []
    for i in range(n_scenarios):
        multiplier = np.maximum(rng.normal(1.0, relative_std, size=len(base_price)), 0.05)
        ensemble.append(pd.Series(base_price.values * multiplier, index=base_price.index, name=f"price_scenario_{i}"))
    return ensemble


def availability_dropout(index: pd.DatetimeIndex, outage_rate_per_year: float, mean_repair_hours: float, seed: int = 44) -> pd.Series:
    """Seeded forced-outage availability mask (1 = available), a simple
    Poisson-arrival / exponential-repair reliability model."""

    rng = np.random.default_rng(seed)
    hours = len(index)
    years = hours / (24 * 365.25)
    n_events = rng.poisson(outage_rate_per_year * years)
    available = np.ones(hours)
    for _ in range(n_events):
        start = rng.integers(0, hours)
        duration = int(max(rng.exponential(mean_repair_hours), 1))
        available[start : min(start + duration, hours)] = 0.0
    return pd.Series(available, index=index)
