import numpy as np
import pandas as pd
import pytest

from hydroflux.core.config import TidalConfig, TidalStreamConfig
from hydroflux.core.timeseries import make_time_index
from hydroflux.tidal.barrage import TidalBarrageOptimiser
from hydroflux.tidal.stream import TidalStreamTurbine, current_velocity_series, kinetic_power, swept_area
from hydroflux.tidal.tidal import sea_level, sea_level_series
from hydroflux.tidal.wake import ArrayWakeCalculator, JensenWakeModel


def test_sea_level_is_periodic():
    period = 12.42
    t = np.array([0.0, period, 2 * period])
    levels = sea_level(t, mean_level_m=0.0, amplitude_m=3.0, period_hours=period)
    assert levels[0] == pytest.approx(levels[1], abs=1e-9)
    assert levels[1] == pytest.approx(levels[2], abs=1e-9)


def test_sea_level_bounded_by_amplitude():
    t = np.linspace(0, 100, 1000)
    levels = sea_level(t, mean_level_m=1.0, amplitude_m=4.0, period_hours=12.42)
    assert levels.max() <= 1.0 + 4.0 + 1e-9
    assert levels.min() >= 1.0 - 4.0 - 1e-9


def test_sea_level_series_reproducible():
    idx = make_time_index("2025-01-01", periods=100, freq="1h")
    config = TidalConfig(tidal_amplitude_m=3.5)
    a = sea_level_series(idx, config)
    b = sea_level_series(idx, config)
    pd.testing.assert_series_equal(a, b)


def test_barrage_generates_only_above_minimum_head():
    idx = make_time_index("2025-01-01", periods=24 * 5, freq="1h")
    config = TidalConfig(mode="two_way", tidal_amplitude_m=4.0, basin_area_km2=5.0, sluice_capacity_m3s=1000, minimum_generating_head_m=1.5)
    optimiser = TidalBarrageOptimiser(config, turbine_rated_flow_m3s=300, turbine_rated_power_mw=10)
    schedule = optimiser.optimise_schedule(idx, mode="two_way")

    generating = schedule.mode.isin(["ebb_generation", "flood_generation"])
    assert (schedule.head_m[generating].abs() >= config.minimum_generating_head_m - 1e-6).all()


def test_barrage_produces_positive_annual_energy():
    idx = make_time_index("2025-01-01", periods=24 * 14, freq="1h")
    config = TidalConfig(mode="ebb_generation", tidal_amplitude_m=4.0, basin_area_km2=8.0, sluice_capacity_m3s=1500, minimum_generating_head_m=1.0)
    optimiser = TidalBarrageOptimiser(config, turbine_rated_flow_m3s=400, turbine_rated_power_mw=20)
    schedule = optimiser.optimise_schedule(idx, mode="ebb_generation")
    assert schedule.annual_energy_mwh > 0


def test_barrage_basin_level_tracks_sea_within_range():
    idx = make_time_index("2025-01-01", periods=24 * 7, freq="1h")
    config = TidalConfig(mode="two_way", tidal_amplitude_m=4.0, basin_area_km2=8.0, sluice_capacity_m3s=3000, minimum_generating_head_m=0.5)
    optimiser = TidalBarrageOptimiser(config, turbine_rated_flow_m3s=500, turbine_rated_power_mw=25)
    schedule = optimiser.optimise_schedule(idx, mode="two_way")
    # Two-way generation with a generous sluice should keep the basin from
    # drifting far outside the tidal envelope.
    assert schedule.basin_level_m.max() <= config.tidal_amplitude_m * 1.5
    assert schedule.basin_level_m.min() >= -config.tidal_amplitude_m * 1.5


def test_swept_area_scales_with_diameter_squared():
    small = swept_area(10.0)
    large = swept_area(20.0)
    assert large == pytest.approx(small * 4, rel=1e-9)


def test_kinetic_power_scales_with_velocity_cubed():
    area = swept_area(20.0)
    p1 = kinetic_power(1.0, area)
    p2 = kinetic_power(2.0, area)
    assert p2 == pytest.approx(p1 * 8, rel=1e-9)


def test_tidal_stream_power_curve_envelope():
    config = TidalStreamConfig(rotor_diameter_m=20, rated_power_mw=1.5, cut_in_speed_ms=0.7, rated_speed_ms=2.65, cut_out_speed_ms=4.0)
    turbine = TidalStreamTurbine.from_config(config)

    assert turbine.power_curve(0.3) == 0.0  # below cut-in
    assert turbine.power_curve(3.0) == pytest.approx(config.rated_power_mw)  # at rated
    assert turbine.power_curve(5.0) == 0.0  # above cut-out
    assert 0.0 < turbine.power_curve(1.5) < config.rated_power_mw  # ramp region


def test_current_velocity_series_reproducible_and_nonnegative():
    t = np.linspace(0, 200, 500)
    v1 = current_velocity_series(t, 1.5, 1.2, 12.42)
    v2 = current_velocity_series(t, 1.5, 1.2, 12.42)
    np.testing.assert_array_equal(v1, v2)
    assert (v1 >= 0).all()


def test_wake_reduces_downstream_velocity():
    model = JensenWakeModel(wake_decay_constant=0.05)
    deficit_near = model.calculate_loss(2.0, distance_m=50, rotor_diameter_m=20)
    deficit_far = model.calculate_loss(2.0, distance_m=500, rotor_diameter_m=20)
    assert deficit_near > deficit_far > 0
    assert 0 <= deficit_near <= 1


def test_array_output_not_linear_in_turbine_count():
    config = TidalStreamConfig(rotor_diameter_m=20, rated_power_mw=1.5, cut_in_speed_ms=0.7, rated_speed_ms=2.65, cut_out_speed_ms=4.0)
    turbine = TidalStreamTurbine.from_config(config)
    calc = ArrayWakeCalculator(JensenWakeModel(wake_decay_constant=0.08), rotor_diameter_m=20)

    single = calc.array_output_mw(np.array([[0, 0]]), 2.0, turbine)
    tandem = calc.array_output_mw(np.array([[0, 0], [100, 0]]), 2.0, turbine)

    # Adding a directly-downstream turbine should not double output.
    assert tandem.sum() < single.sum() * 2
    # The downstream turbine should produce less than the upstream one.
    assert tandem[1] < tandem[0]
