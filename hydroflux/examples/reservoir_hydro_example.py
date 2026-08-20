"""
HydroFlux example: 500 MW conventional reservoir hydro plant.

    500 MW reservoir
    4 turbines
    variable river inflow
    variable electricity price
    environmental minimum flow

Determines the optimal turbine dispatch, reservoir level strategy,
generation timing and a maintenance schedule, and reports the optimal
annual operating strategy (specification section 49).

Run with:

    python -m examples.reservoir_hydro_example
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import hydroflux
from hydroflux.core.config import (
    EconomicConfig,
    EnvironmentalConfig,
    HydroSystemConfig,
    ReservoirConfig,
    SimulationConfig,
    TurbineConfig,
)
from hydroflux.core.engine import HydroFluxEngine
from hydroflux.core.timeseries import ResourceTimeSeries, make_time_index
from hydroflux.hydrology.hydrology import synthetic_river_inflow
from hydroflux.reporting.reporting import ComparisonEngine, summarize
from hydroflux.turbines.maintenance import schedule_maintenance


def build_system() -> HydroSystemConfig:
    turbines = [
        TurbineConfig(id=f"T{i+1}", type="francis", rated_power_mw=125.0, rated_flow_m3s=130.0, minimum_flow_m3s=20.0)
        for i in range(4)
    ]
    reservoir = ReservoirConfig(
        capacity_mcm=900.0,
        dead_storage_mcm=80.0,
        minimum_level_m=200.0,
        maximum_level_m=260.0,
        initial_level_m=245.0,
        surface_area_km2=42.0,
        evaporation_mm_per_day=2.5,
        tailwater_elevation_m=150.0,
        penstock_length_m=650.0,
        penstock_diameter_m=6.5,
    )
    return HydroSystemConfig(
        name="500 MW Reservoir Hydro",
        system_type="reservoir",
        simulation=SimulationConfig(start="2025-01-01", periods=24 * 365, freq="1h", seed=42),
        turbines=turbines,
        reservoir=reservoir,
        environmental=EnvironmentalConfig(minimum_ecological_flow_m3s=15.0, maximum_flow_alteration_pct=90.0),
        economics=EconomicConfig(
            capex_total=650_000_000.0,
            opex_fixed_annual=9_000_000.0,
            opex_variable_per_mwh=1.2,
            discount_rate=0.07,
            project_lifetime_years=50,
        ),
    )


def build_resource(config: HydroSystemConfig) -> ResourceTimeSeries:
    index = make_time_index(config.simulation.start, config.simulation.periods, config.simulation.freq)
    inflow = synthetic_river_inflow(
        index,
        mean_flow_m3s=220.0,
        seasonal_amplitude_m3s=110.0,  # spring snowmelt peak, low late summer
        daily_amplitude_m3s=0.0,
        noise_std_m3s=18.0,
        seed=config.simulation.seed,
        minimum_flow_m3s=15.0,
    )
    t_hours = np.arange(len(index))
    daily_cycle = 12.0 * np.sin(2 * np.pi * (t_hours % 24) / 24.0 - np.pi / 2)
    seasonal_cycle = 8.0 * np.sin(2 * np.pi * t_hours / (24 * 365.25))
    noise = np.random.default_rng(config.simulation.seed + 1).normal(0, 4.0, len(index))
    price = pd.Series(np.clip(45.0 + daily_cycle + seasonal_cycle + noise, 5.0, None), index=index)

    return ResourceTimeSeries(index=index, inflow=inflow, price=price)


def main() -> None:
    config = build_system()
    resource = build_resource(config)

    print("Simulating baseline operating strategy (target level = initial level)...")
    baseline = hydroflux.simulate(config, resource, scenario_name="baseline")

    print("Searching for the optimal full-year reservoir operating policy (this runs a")
    print("global search over the full hourly simulation and can take a few minutes)...")
    engine = HydroFluxEngine(config)
    optimised, policy_result = engine.optimise(
        resource,
        objective="max_revenue",
        algorithm="differential_evolution",
        seed=config.simulation.seed,
        maxiter=6,
        popsize=6,
    )
    print(f"  Best policy found: {policy_result.best_parameters} (in {policy_result.n_evaluations} evaluations)")

    print()
    print(summarize(optimised))
    print()

    table = ComparisonEngine.compare({"baseline": baseline, "optimised": optimised})
    print("Baseline vs. optimised:")
    print(table.round(2).to_string())
    print()

    maintenance_windows = schedule_maintenance(
        [t.id for t in config.turbines],
        resource.index,
        resource.price,
        resource.inflow,
        duration_hours=24 * 7,
    )
    print("Recommended maintenance schedule (lowest opportunity-cost weeks):")
    for window in maintenance_windows:
        print(f"  {window.turbine_id}: {window.start.date()} for {window.duration_hours:.0f} h")


if __name__ == "__main__":
    main()
