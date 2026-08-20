import numpy as np
import pandas as pd
import pytest

import hydroflux
from hydroflux.core.config import (
    HydroSystemConfig,
    PumpConfig,
    PumpedStorageConfig,
    PumpedTurbineConfig,
    ReservoirConfig,
    SimulationConfig,
    TidalConfig,
    TurbineConfig,
)
from hydroflux.core.timeseries import ResourceTimeSeries, make_time_index
from hydroflux.hydrology.hydrology import synthetic_river_inflow
from hydroflux.optimisation.objectives import ObjectiveWeights


def reservoir_system():
    idx = make_time_index("2025-01-01", periods=24 * 10, freq="1h")
    flow = synthetic_river_inflow(idx, mean_flow_m3s=200, seasonal_amplitude_m3s=20, noise_std_m3s=10, seed=1, minimum_flow_m3s=20)
    price = pd.Series(30 + 20 * np.sin(np.linspace(0, 10 * np.pi, len(idx))), index=idx).clip(lower=5)
    resource = ResourceTimeSeries(index=idx, inflow=flow, price=price)

    config = HydroSystemConfig(
        name="Integration Test Reservoir",
        system_type="reservoir",
        simulation=SimulationConfig(start="2025-01-01", periods=len(idx), freq="1h", seed=42),
        turbines=[
            TurbineConfig(id="T1", type="francis", rated_power_mw=100, rated_flow_m3s=100, minimum_flow_m3s=15),
            TurbineConfig(id="T2", type="francis", rated_power_mw=100, rated_flow_m3s=100, minimum_flow_m3s=15),
        ],
        reservoir=ReservoirConfig(capacity_mcm=80, dead_storage_mcm=10, minimum_level_m=200, maximum_level_m=260, initial_level_m=245, surface_area_km2=4),
    )
    return config, resource


def test_reservoir_simulation_produces_sane_result():
    config, resource = reservoir_system()
    result = hydroflux.simulate(config, resource)

    assert result.annual_generation_mwh > 0
    assert 0.0 <= result.capacity_factor <= 1.0
    assert 0.0 <= result.average_efficiency <= 1.0
    assert result.reservoir_level_m.between(config.reservoir.minimum_level_m - 1e-3, config.reservoir.maximum_level_m + 1e-3).all()
    assert result.theoretical_potential_mwh >= result.physical_potential_mwh - 1e-6
    assert result.metadata.model_version
    assert result.metadata.configuration_hash


def test_simulation_is_deterministic():
    config, resource = reservoir_system()
    result_a = hydroflux.simulate(config, resource)
    result_b = hydroflux.simulate(config, resource)
    assert result_a.annual_generation_mwh == pytest.approx(result_b.annual_generation_mwh)
    assert result_a.metadata.configuration_hash == result_b.metadata.configuration_hash


def test_optimise_beats_or_matches_naive_baseline():
    config, resource = reservoir_system()
    baseline = hydroflux.simulate(config, resource)
    optimised = hydroflux.optimize(config, resource, objective="max_revenue", algorithm="differential_evolution")
    assert optimised.revenue >= baseline.revenue - 1e-3


def test_optimise_records_optimisation_method():
    config, resource = reservoir_system()
    result = hydroflux.optimize(config, resource, objective="max_energy")
    assert result.metadata.optimisation_method != ""
    assert "target_level_m" in result.metadata.optimisation_parameters


def test_compare_scenarios_returns_expected_shape():
    config, resource = reservoir_system()
    baseline = hydroflux.simulate(config, resource)
    optimised = hydroflux.optimize(config, resource, objective="max_revenue")
    table = hydroflux.compare({"baseline": baseline, "optimised": optimised})
    assert list(table.index) == ["baseline", "optimised"]
    assert "generation_gwh" in table.columns


def test_tidal_barrage_end_to_end():
    idx = make_time_index("2025-01-01", periods=24 * 10, freq="1h")
    price = pd.Series(30 + 40 * np.sin(np.linspace(0, 15 * np.pi, len(idx))), index=idx).clip(lower=5)
    resource = ResourceTimeSeries(index=idx, price=price)

    config = HydroSystemConfig(
        name="Integration Test Tidal Barrage",
        system_type="tidal_barrage",
        simulation=SimulationConfig(start="2025-01-01", periods=len(idx), freq="1h", seed=42),
        turbines=[TurbineConfig(id="T1", type="bulb", rated_power_mw=20, rated_flow_m3s=400, minimum_flow_m3s=40)],
        tidal=TidalConfig(mode="two_way", tidal_amplitude_m=4.0, basin_area_km2=10, sluice_capacity_m3s=2000, minimum_generating_head_m=1.0),
    )
    result = hydroflux.simulate(config, resource)
    assert result.annual_generation_mwh > 0
    assert result.revenue != 0


def test_pumped_storage_end_to_end():
    idx = make_time_index("2025-01-01", periods=24 * 5, freq="1h")
    hours = np.arange(len(idx)) % 24
    price = pd.Series(np.where((hours >= 18) & (hours <= 21), 150.0, 25.0), index=idx)
    resource = ResourceTimeSeries(index=idx, price=price)

    config = HydroSystemConfig(
        name="Integration Test Pumped Storage",
        system_type="pumped_storage",
        simulation=SimulationConfig(start="2025-01-01", periods=len(idx), freq="1h", seed=42),
        pumped_storage=PumpedStorageConfig(
            upper_reservoir=ReservoirConfig(name="upper", capacity_mcm=5, dead_storage_mcm=0.5, minimum_level_m=400, maximum_level_m=430, initial_level_m=415, surface_area_km2=0.5),
            lower_reservoir=ReservoirConfig(name="lower", capacity_mcm=5, dead_storage_mcm=0.5, minimum_level_m=100, maximum_level_m=120, initial_level_m=110, surface_area_km2=0.5),
            pump=PumpConfig(rated_power_mw=80, efficiency=0.88),
            turbine=PumpedTurbineConfig(rated_power_mw=80, efficiency=0.9),
        ),
    )
    result = hydroflux.simulate(config, resource)
    assert result.revenue > 0


def test_config_yaml_round_trip(tmp_path):
    config, _ = reservoir_system()
    path = tmp_path / "system.yaml"
    config.to_yaml(path)
    loaded = HydroSystemConfig.from_yaml(path)
    assert loaded.name == config.name
    assert len(loaded.turbines) == len(config.turbines)
    assert loaded.reservoir.capacity_mcm == config.reservoir.capacity_mcm
