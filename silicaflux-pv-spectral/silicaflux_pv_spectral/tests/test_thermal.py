import pytest

from silicaflux_pv_spectral.constants import STC_TEMPERATURE_K
from silicaflux_pv_spectral.materials import SILICON
from silicaflux_pv_spectral.thermal import cell_temperature_k, compute_thermal_state, thermal_adjusted_material_summary


def test_cell_temperature_exceeds_ambient_under_illumination():
    t_cell = cell_temperature_k(298.15, 1000.0, wind_speed_m_s=1.0)
    assert t_cell > 298.15


def test_cell_temperature_equals_ambient_at_zero_irradiance():
    t_cell = cell_temperature_k(298.15, 0.0, wind_speed_m_s=1.0)
    assert t_cell == pytest.approx(298.15)


def test_higher_wind_speed_cools_the_cell():
    calm = cell_temperature_k(298.15, 1000.0, wind_speed_m_s=0.5)
    windy = cell_temperature_k(298.15, 1000.0, wind_speed_m_s=8.0)
    assert windy < calm


def test_cell_temperature_is_realistic_at_stc_like_conditions():
    t_cell = cell_temperature_k(298.15, 1000.0, wind_speed_m_s=1.0)
    delta_c = t_cell - 298.15
    assert 15.0 < delta_c < 60.0  # NOCT-like modules typically run 20-45 degC above ambient at full sun


def test_compute_thermal_state_matches_cell_temperature_k():
    state = compute_thermal_state(300.0, 800.0, wind_speed_m_s=2.0)
    assert state.cell_temperature_k == pytest.approx(cell_temperature_k(300.0, 800.0, wind_speed_m_s=2.0))
    assert state.delta_t_from_ambient_k == pytest.approx(state.cell_temperature_k - 300.0)


def test_bandgap_narrows_and_lifetime_shifts_away_from_stc_baseline():
    hot_summary = thermal_adjusted_material_summary(SILICON, STC_TEMPERATURE_K + 30.0)
    assert hot_summary.bandgap_shift_ev_from_stc < 0.0
    assert hot_summary.carrier_lifetime_shift_pct_from_stc != 0.0


def test_summary_at_stc_has_zero_shift():
    summary = thermal_adjusted_material_summary(SILICON, STC_TEMPERATURE_K)
    assert summary.bandgap_shift_ev_from_stc == pytest.approx(0.0, abs=1e-9)
    assert summary.carrier_lifetime_shift_pct_from_stc == pytest.approx(0.0, abs=1e-6)
