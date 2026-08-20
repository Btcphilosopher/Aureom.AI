"""
HydroFlux example: a two-way generating tidal barrage/basin.

    tidal basin
    variable sea level
    multiple turbines
    two-way generation
    variable electricity prices

Optimises the sluice/generation-head threshold that governs sluice
operation, generation windows and turbine dispatch, and reports annual MWh,
peak MW, capacity factor, revenue and LCOE (specification section 50).

Run with:

    python -m examples.tidal_barrage_example
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import hydroflux
from hydroflux.core.config import EconomicConfig, HydroSystemConfig, SimulationConfig, TidalConfig, TurbineConfig
from hydroflux.core.engine import HydroFluxEngine
from hydroflux.core.timeseries import ResourceTimeSeries, make_time_index
from hydroflux.reporting.reporting import ComparisonEngine, summarize


def build_system() -> HydroSystemConfig:
    turbines = [
        TurbineConfig(id=f"T{i+1}", type="bulb", rated_power_mw=30.0, rated_flow_m3s=600.0, minimum_flow_m3s=60.0)
        for i in range(10)
    ]
    tidal = TidalConfig(
        mode="two_way",
        tidal_amplitude_m=5.0,  # ~10 m spring tidal range
        tidal_period_hours=12.42,
        basin_area_km2=25.0,
        basin_volume_mcm=125.0,
        sluice_capacity_m3s=5000.0,
        minimum_generating_head_m=1.5,
    )
    return HydroSystemConfig(
        name="300 MW Tidal Barrage",
        system_type="tidal_barrage",
        simulation=SimulationConfig(start="2025-01-01", periods=24 * 365, freq="1h", seed=42),
        turbines=turbines,
        tidal=tidal,
        economics=EconomicConfig(
            capex_total=1_100_000_000.0,
            opex_fixed_annual=12_000_000.0,
            opex_variable_per_mwh=1.0,
            discount_rate=0.065,
            project_lifetime_years=100,  # barrages are long-lived civil structures
        ),
    )


def build_resource(config: HydroSystemConfig) -> ResourceTimeSeries:
    index = make_time_index(config.simulation.start, config.simulation.periods, config.simulation.freq)
    t_hours = np.arange(len(index))
    # A daily + seasonal electricity price signal (higher in winter evenings).
    daily_cycle = 15.0 * np.sin(2 * np.pi * (t_hours % 24) / 24.0 - np.pi / 2)
    seasonal_cycle = 10.0 * np.sin(2 * np.pi * t_hours / (24 * 365.25) + np.pi)
    noise = np.random.default_rng(config.simulation.seed).normal(0, 5.0, len(index))
    price = pd.Series(np.clip(50.0 + daily_cycle + seasonal_cycle + noise, 5.0, None), index=index)
    return ResourceTimeSeries(index=index, price=price)


def main() -> None:
    config = build_system()
    resource = build_resource(config)

    print("Simulating the configured (as-specified) operating threshold...")
    baseline = hydroflux.simulate(config, resource, scenario_name="baseline")

    print("Optimising the minimum generating-head threshold for maximum revenue...")
    engine = HydroFluxEngine(config)
    optimised, policy_result = engine.optimise(
        resource, objective="max_revenue", algorithm="differential_evolution", seed=config.simulation.seed, maxiter=15, popsize=10
    )
    print(f"  Best policy: {policy_result.best_parameters} (in {policy_result.n_evaluations} evaluations)")

    print()
    print(summarize(optimised))
    print()

    table = ComparisonEngine.compare({"baseline": baseline, "optimised": optimised})
    print("Baseline vs. optimised:")
    print(table.round(2).to_string())


if __name__ == "__main__":
    main()
