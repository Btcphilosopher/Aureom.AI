import numpy as np
import pandas as pd
import pytest

from hydroflux.core.timeseries import ResourceTimeSeries, make_time_index
from hydroflux.hydrology.hydrology import synthetic_river_inflow
from hydroflux.scenarios.scenarios import (
    Scenario,
    ScenarioType,
    apply_scenario,
    availability_dropout,
    default_scenarios,
    stochastic_flow_ensemble,
    stochastic_price_ensemble,
)


def make_resource(seed=1):
    idx = make_time_index("2025-01-01", periods=24 * 10, freq="1h")
    flow = synthetic_river_inflow(idx, mean_flow_m3s=100, seasonal_amplitude_m3s=10, noise_std_m3s=5, seed=seed)
    price = pd.Series(np.linspace(20, 60, len(idx)), index=idx)
    return ResourceTimeSeries(index=idx, flow=flow, price=price)


def test_synthetic_flow_is_reproducible():
    idx = make_time_index("2025-01-01", periods=200, freq="1h")
    a = synthetic_river_inflow(idx, mean_flow_m3s=100, seasonal_amplitude_m3s=10, noise_std_m3s=5, seed=99)
    b = synthetic_river_inflow(idx, mean_flow_m3s=100, seasonal_amplitude_m3s=10, noise_std_m3s=5, seed=99)
    pd.testing.assert_series_equal(a, b)


def test_synthetic_flow_differs_with_different_seed():
    idx = make_time_index("2025-01-01", periods=200, freq="1h")
    a = synthetic_river_inflow(idx, mean_flow_m3s=100, seasonal_amplitude_m3s=10, noise_std_m3s=5, seed=1)
    b = synthetic_river_inflow(idx, mean_flow_m3s=100, seasonal_amplitude_m3s=10, noise_std_m3s=5, seed=2)
    assert not a.equals(b)


def test_drought_scenario_reduces_mean_flow():
    resource = make_resource()
    scenario = Scenario("drought", ScenarioType.DROUGHT, drought_severity=0.5)
    perturbed = apply_scenario(resource, scenario)
    assert perturbed.flow.mean() < resource.flow.mean()


def test_flood_scenario_increases_peak_flow():
    resource = make_resource()
    scenario = Scenario("flood", ScenarioType.FLOOD, flood_severity=0.5)
    perturbed = apply_scenario(resource, scenario)
    assert perturbed.flow.max() > resource.flow.max()


def test_high_price_scenario_scales_price():
    resource = make_resource()
    scenario = Scenario("high price", ScenarioType.HIGH_PRICE, price_multiplier=1.5)
    perturbed = apply_scenario(resource, scenario)
    pd.testing.assert_series_equal(perturbed.price, resource.price * 1.5)


def test_scenario_application_reproducible():
    resource = make_resource()
    scenario = Scenario("drought", ScenarioType.DROUGHT, seed=7, drought_severity=0.4)
    a = apply_scenario(resource, scenario)
    b = apply_scenario(resource, scenario)
    pd.testing.assert_series_equal(a.flow, b.flow)


def test_default_scenarios_cover_every_type():
    scenarios = default_scenarios()
    types_covered = {s.type for s in scenarios}
    assert types_covered == set(ScenarioType)


def test_stochastic_flow_ensemble_reproducible():
    idx = make_time_index("2025-01-01", periods=200, freq="1h")
    base = pd.Series(100.0, index=idx)
    ensemble_a = stochastic_flow_ensemble(base, n_scenarios=5, seed=11)
    ensemble_b = stochastic_flow_ensemble(base, n_scenarios=5, seed=11)
    for a, b in zip(ensemble_a, ensemble_b):
        pd.testing.assert_series_equal(a, b)


def test_stochastic_flow_ensemble_nonnegative():
    idx = make_time_index("2025-01-01", periods=200, freq="1h")
    base = pd.Series(10.0, index=idx)
    ensemble = stochastic_flow_ensemble(base, n_scenarios=3, relative_std=0.8, seed=1)
    for series in ensemble:
        assert (series >= 0).all()


def test_stochastic_price_ensemble_reproducible():
    idx = make_time_index("2025-01-01", periods=100, freq="1h")
    base = pd.Series(40.0, index=idx)
    a = stochastic_price_ensemble(base, n_scenarios=4, seed=5)
    b = stochastic_price_ensemble(base, n_scenarios=4, seed=5)
    for x, y in zip(a, b):
        pd.testing.assert_series_equal(x, y)


def test_availability_dropout_reproducible_and_bounded():
    idx = make_time_index("2025-01-01", periods=24 * 60, freq="1h")
    a = availability_dropout(idx, outage_rate_per_year=5, mean_repair_hours=20, seed=3)
    b = availability_dropout(idx, outage_rate_per_year=5, mean_repair_hours=20, seed=3)
    pd.testing.assert_series_equal(a, b)
    assert set(a.unique()).issubset({0.0, 1.0})
