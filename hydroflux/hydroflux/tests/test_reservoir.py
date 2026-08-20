import numpy as np
import pandas as pd
import pytest

from hydroflux.core.config import ReservoirConfig
from hydroflux.core.timeseries import make_time_index
from hydroflux.reservoirs.reservoir import Reservoir, WaterValueEngine


def make_reservoir():
    config = ReservoirConfig(
        capacity_mcm=100.0,
        dead_storage_mcm=10.0,
        minimum_level_m=200.0,
        maximum_level_m=260.0,
        initial_level_m=230.0,
        surface_area_km2=5.0,
        evaporation_mm_per_day=0.0,
    )
    return Reservoir(config)


def test_level_storage_round_trip():
    reservoir = make_reservoir()
    for level in (200.0, 215.0, 230.0, 260.0):
        storage = reservoir.level_to_storage(level)
        back = reservoir.storage_to_level(storage)
        assert back == pytest.approx(level, abs=1e-6)


def test_level_to_storage_monotonic():
    reservoir = make_reservoir()
    levels = np.linspace(200, 260, 10)
    storages = [reservoir.level_to_storage(l) for l in levels]
    assert np.all(np.diff(storages) > 0)


def test_mass_balance_conserves_water_with_no_spill():
    reservoir = make_reservoir()
    idx = make_time_index("2025-01-01", periods=100, freq="1h")
    inflow = pd.Series(10.0, index=idx)  # small, steady inflow
    release = pd.Series(10.0, index=idx)  # matched release -> storage roughly constant

    result = reservoir.simulate(inflow, release, dt_hours=1.0)
    assert result.storage_mcm.iloc[-1] == pytest.approx(result.storage_mcm.iloc[0], abs=0.05)
    assert (result.spill_m3s == 0).all()


def test_mass_balance_never_exceeds_capacity():
    reservoir = make_reservoir()
    idx = make_time_index("2025-01-01", periods=200, freq="1h")
    inflow = pd.Series(500.0, index=idx)  # large inflow, should force spill
    release = pd.Series(50.0, index=idx)

    result = reservoir.simulate(inflow, release, dt_hours=1.0)
    assert (result.storage_mcm <= reservoir.config.capacity_mcm + 1e-6).all()
    assert result.spill_m3s.sum() > 0


def test_mass_balance_never_drops_below_dead_storage():
    reservoir = make_reservoir()
    idx = make_time_index("2025-01-01", periods=500, freq="1h")
    inflow = pd.Series(0.0, index=idx)
    release = pd.Series(1000.0, index=idx)  # far more than available

    result = reservoir.simulate(inflow, release, dt_hours=1.0)
    assert (result.storage_mcm >= reservoir.config.dead_storage_mcm - 1e-6).all()
    # Actual release should have been curtailed well below the requested rate.
    assert result.release_m3s.iloc[-1] < 1000.0


def test_water_value_higher_when_storage_scarce():
    reservoir = make_reservoir()
    idx = make_time_index("2025-01-01", periods=48, freq="1h")
    price = pd.Series(50.0, index=idx)
    inflow = pd.Series(20.0, index=idx)

    engine = WaterValueEngine(reservoir, turbine_efficiency=0.9, n_storage_states=11)
    result = engine.compute(price, inflow, head_m=50.0, max_release_m3s=100.0, n_release_choices=9)

    low_storage_value = result.water_value_at(0, reservoir.config.dead_storage_mcm + 1.0)
    high_storage_value = result.water_value_at(0, reservoir.config.capacity_mcm - 1.0)
    # Marginal value of water should not increase as storage becomes more abundant.
    assert low_storage_value >= high_storage_value - 1e-6


def test_water_value_responds_to_price():
    reservoir = make_reservoir()
    idx = make_time_index("2025-01-01", periods=24, freq="1h")
    inflow = pd.Series(20.0, index=idx)

    low_price = pd.Series(10.0, index=idx)
    high_price = pd.Series(200.0, index=idx)

    engine = WaterValueEngine(reservoir, n_storage_states=11)
    low_result = engine.compute(low_price, inflow, head_m=50.0, max_release_m3s=100.0, n_release_choices=9)
    high_result = engine.compute(high_price, inflow, head_m=50.0, max_release_m3s=100.0, n_release_choices=9)

    mid_storage = (reservoir.config.dead_storage_mcm + reservoir.config.capacity_mcm) / 2
    assert high_result.water_value_at(0, mid_storage) > low_result.water_value_at(0, mid_storage)
