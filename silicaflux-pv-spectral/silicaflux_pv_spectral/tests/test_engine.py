import pytest

from silicaflux_pv_spectral.engine import SILICAFLUX, generate_simulation_output, optimise
from silicaflux_pv_spectral.materials import SILICON
from silicaflux_pv_spectral.spectrum import terrestrial_spectrum


@pytest.fixture(scope="module")
def spectrum():
    return terrestrial_spectrum()


def test_dotted_namespace_call_matches_direct_function(spectrum):
    from_namespace = SILICAFLUX.PV.SPECTRAL.OPTIMISE(spectrum, SILICON)
    direct = optimise(spectrum, SILICON)
    assert from_namespace.efficiency == direct.efficiency
    assert from_namespace.optimised_parameters == direct.optimised_parameters


def test_optimise_improves_or_matches_baseline_efficiency(spectrum):
    result = optimise(spectrum, SILICON)
    assert result.efficiency > 0.0
    assert result.predicted_energy_gain >= 0.0


def test_optimise_result_bands_sum_to_total_irradiance_order(spectrum):
    result = optimise(spectrum, SILICON)
    assert result.uv_irradiance + result.visible_irradiance + result.nir_irradiance == pytest.approx(
        result.total_irradiance, rel=1e-6
    )


def test_optimise_absorbed_never_exceeds_incident_per_band(spectrum):
    result = optimise(spectrum, SILICON)
    assert result.absorbed_uv <= result.uv_irradiance + 1e-6
    assert result.absorbed_visible <= result.visible_irradiance + 1e-6
    assert result.absorbed_nir <= result.nir_irradiance + 1e-6


def test_optimise_prefers_uv_transparent_encapsulant(spectrum):
    result = optimise(spectrum, SILICON)
    assert result.optimised_parameters["encapsulant_uv_blocking"] is False


def test_simulation_output_optimised_beats_or_matches_baseline(spectrum):
    output = generate_simulation_output(spectrum, SILICON)
    assert output.OPTIMISED_EFFICIENCY >= output.BASELINE_EFFICIENCY
    assert output.OPTIMISED_UV_POWER >= output.BASELINE_UV_POWER
    assert output.ANNUAL_ENERGY_OPTIMISED >= output.ANNUAL_ENERGY_BASELINE


def test_simulation_output_uv_loss_is_nonnegative(spectrum):
    output = generate_simulation_output(spectrum, SILICON)
    assert output.UV_LOSS >= 0.0


def test_tandem_architecture_returns_a_result(spectrum):
    result = optimise(spectrum, SILICON, architecture="tandem")
    assert result.efficiency > 0.0
    assert result.optimised_parameters["architecture"] == "tandem"
    assert "current_matching_error" in result.optimised_parameters


def test_tandem_band_power_sums_to_device_power_within_efficiency(spectrum):
    result = optimise(spectrum, SILICON, architecture="tandem")
    band_sum = result.uv_power + result.visible_power + result.nir_power
    assert band_sum == pytest.approx(result.efficiency * result.total_irradiance, rel=1e-6)


def test_optimise_is_deterministic(spectrum):
    r1 = optimise(spectrum, SILICON)
    r2 = optimise(spectrum, SILICON)
    assert r1.efficiency == r2.efficiency
    assert r1.optimised_parameters == r2.optimised_parameters
