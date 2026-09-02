import pytest

from silicaflux_pv_spectral.materials import SILICON
from silicaflux_pv_spectral.optics import default_optical_stack
from silicaflux_pv_spectral.pipeline import run_pipeline
from silicaflux_pv_spectral.spectrum import terrestrial_spectrum


@pytest.fixture(scope="module")
def spectrum():
    return terrestrial_spectrum()


def test_pipeline_runs_end_to_end(spectrum):
    result = run_pipeline(spectrum, SILICON)
    assert result.spectral_response.p_total_w_m2 > 0.0
    assert 0.0 < result.efficiency < 1.0


def test_optical_loss_accounting_identity(spectrum):
    result = run_pipeline(spectrum, SILICON)
    assert result.optical_loss_w_m2 == pytest.approx(
        result.incident_power_w_m2 - result.absorbed_power_w_m2, rel=1e-6
    )
    assert result.optical_loss_w_m2 >= result.reflection_loss_w_m2 + result.parasitic_stack_loss_w_m2 - 1e-6


def test_all_loss_terms_are_nonnegative_except_thermal(spectrum):
    result = run_pipeline(spectrum, SILICON)
    assert result.reflection_loss_w_m2 >= 0.0
    assert result.parasitic_stack_loss_w_m2 >= 0.0
    assert result.optical_loss_w_m2 >= 0.0
    assert result.recombination_loss_w_m2 >= 0.0
    assert result.degradation_cost_w_m2 >= 0.0
    # thermal_loss may be negative if the cell runs cooler than STC, but not here (hot ambient case)


def test_net_energy_output_below_p_total_when_degradation_active(spectrum):
    result = run_pipeline(spectrum, SILICON, compute_degradation=True)
    assert result.net_energy_output_w_m2 <= result.spectral_response.p_total_w_m2


def test_disabling_degradation_makes_net_energy_output_equal_p_total(spectrum):
    result = run_pipeline(spectrum, SILICON, compute_degradation=False)
    assert result.degradation is None
    assert result.net_energy_output_w_m2 == pytest.approx(result.spectral_response.p_total_w_m2)


def test_higher_wind_speed_cools_cell_and_improves_efficiency(spectrum):
    calm = run_pipeline(spectrum, SILICON, wind_speed_m_s=0.5)
    windy = run_pipeline(spectrum, SILICON, wind_speed_m_s=10.0)
    assert windy.thermal_state.cell_temperature_k < calm.thermal_state.cell_temperature_k
    assert windy.efficiency >= calm.efficiency


def test_apply_atmosphere_flag_reduces_irradiance(spectrum):
    from silicaflux_pv_spectral.spectrum import extraterrestrial_spectrum

    et = extraterrestrial_spectrum()
    with_atm = run_pipeline(et, SILICON, apply_atmosphere=True)
    without_atm = run_pipeline(et, SILICON, apply_atmosphere=False)
    assert with_atm.incident_power_w_m2 < without_atm.incident_power_w_m2


def test_uv_transparent_encapsulant_improves_pipeline_efficiency(spectrum):
    blocking = run_pipeline(spectrum, SILICON, optical_stack=default_optical_stack(encapsulant_uv_blocking=True))
    transparent = run_pipeline(spectrum, SILICON, optical_stack=default_optical_stack(encapsulant_uv_blocking=False))
    assert transparent.efficiency > blocking.efficiency


def test_pipeline_is_deterministic(spectrum):
    r1 = run_pipeline(spectrum, SILICON)
    r2 = run_pipeline(spectrum, SILICON)
    assert r1.efficiency == r2.efficiency
    assert r1.spectral_response.p_total_w_m2 == r2.spectral_response.p_total_w_m2
