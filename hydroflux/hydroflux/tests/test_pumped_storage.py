import numpy as np
import pandas as pd
import pytest

from hydroflux.core.config import PumpConfig, PumpedStorageConfig, PumpedTurbineConfig, ReservoirConfig
from hydroflux.core.timeseries import make_time_index
from hydroflux.pumped_storage.pumped_storage import PumpedStorageOptimiser


def make_config():
    return PumpedStorageConfig(
        upper_reservoir=ReservoirConfig(name="upper", capacity_mcm=5.0, dead_storage_mcm=0.5, minimum_level_m=400, maximum_level_m=430, initial_level_m=415, surface_area_km2=0.5),
        lower_reservoir=ReservoirConfig(name="lower", capacity_mcm=5.0, dead_storage_mcm=0.5, minimum_level_m=100, maximum_level_m=120, initial_level_m=110, surface_area_km2=0.5),
        pump=PumpConfig(rated_power_mw=100.0, efficiency=0.88),
        turbine=PumpedTurbineConfig(rated_power_mw=100.0, efficiency=0.90),
    )


def make_price(idx):
    # A clean daily cycle: cheap overnight, expensive in the evening peak.
    hours = np.arange(len(idx)) % 24
    return pd.Series(np.where((hours >= 18) & (hours <= 21), 150.0, 25.0), index=idx)


def test_round_trip_efficiency_is_pump_times_turbine():
    config = make_config()
    optimiser = PumpedStorageOptimiser(config, effective_head_m=300.0)
    assert optimiser.round_trip_efficiency == pytest.approx(config.pump.efficiency * config.turbine.efficiency)


def test_threshold_schedule_pumps_low_generates_high():
    idx = make_time_index("2025-01-01", periods=24 * 3, freq="1h")
    price = make_price(idx)
    config = make_config()
    optimiser = PumpedStorageOptimiser(config, effective_head_m=300.0)

    schedule = optimiser.optimise_threshold(price, pump_threshold=30.0, generate_threshold=100.0)
    pumping_prices = price[schedule.pump_mw > 0]
    generating_prices = price[schedule.generate_mw > 0]
    if len(pumping_prices):
        assert pumping_prices.max() <= 30.0
    if len(generating_prices):
        assert generating_prices.min() >= 100.0


def test_threshold_schedule_never_exceeds_capacity():
    idx = make_time_index("2025-01-01", periods=24 * 3, freq="1h")
    price = make_price(idx)
    config = make_config()
    optimiser = PumpedStorageOptimiser(config, effective_head_m=300.0)
    schedule = optimiser.optimise_threshold(price)

    assert (schedule.pump_mw <= config.pump.rated_power_mw + 1e-6).all()
    assert (schedule.generate_mw <= config.turbine.rated_power_mw + 1e-6).all()
    assert (schedule.storage_mwh >= -1e-6).all()


def test_lp_schedule_is_at_least_as_good_as_threshold():
    idx = make_time_index("2025-01-01", periods=24 * 5, freq="1h")
    price = make_price(idx)
    config = make_config()
    optimiser = PumpedStorageOptimiser(config, effective_head_m=300.0)

    lp_schedule = optimiser.optimise_lp(price)
    threshold_schedule = optimiser.optimise_threshold(price)

    # The exact LP arbitrage solution should never earn less than the
    # simple heuristic on the same price series.
    assert lp_schedule.revenue >= threshold_schedule.revenue - 1e-6


def test_lp_schedule_respects_storage_bounds():
    idx = make_time_index("2025-01-01", periods=24 * 4, freq="1h")
    price = make_price(idx)
    config = make_config()
    optimiser = PumpedStorageOptimiser(config, effective_head_m=300.0)
    schedule = optimiser.optimise_lp(price)

    capacity = optimiser.usable_energy_capacity_mwh()
    assert (schedule.storage_mwh >= -1e-6).all()
    assert (schedule.storage_mwh <= capacity + 1e-6).all()


def test_full_arbitrage_cycle_is_profitable_when_spread_is_large():
    idx = make_time_index("2025-01-01", periods=24 * 2, freq="1h")
    price = make_price(idx)
    config = make_config()
    optimiser = PumpedStorageOptimiser(config, effective_head_m=300.0)
    schedule = optimiser.optimise_lp(price)
    assert schedule.revenue > 0
