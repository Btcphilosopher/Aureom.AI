import pytest

from silicaflux_pv_spectral.materials import SILICON
from silicaflux_pv_spectral.parameter_sweep import SweepConfiguration, evaluate_configuration, parameter_sweep
from silicaflux_pv_spectral.spectrum import terrestrial_spectrum


@pytest.fixture(scope="module")
def spectrum():
    return terrestrial_spectrum()


def test_single_configuration_evaluates(spectrum):
    config = SweepConfiguration(
        bandgap_eV=SILICON.bandgap_eV, thickness_nm=SILICON.thickness_nm, ar_index=1.38,
        lifetime_multiplier=1.0, temperature_k=298.15, uv_conversion_efficiency=0.0,
    )
    result = evaluate_configuration(SILICON, spectrum, config)
    assert result.total_efficiency > 0.0
    assert 0.0 <= result.uv_response <= 1.0
    assert result.degradation_rate_per_year >= 0.0


def test_sweep_is_ranked_descending_by_net_energy(spectrum):
    results = parameter_sweep(
        SILICON, spectrum,
        bandgap_values=[1.0, 1.12], thickness_values=[SILICON.thickness_nm],
        ar_index_values=[1.38], lifetime_multiplier_values=[1.0],
        temperature_values=[298.15], uv_conversion_efficiency_values=[0.0],
    )
    net_energies = [r.net_energy_output_w_m2 for r in results]
    assert net_energies == sorted(net_energies, reverse=True)


def test_sweep_ranks_are_sequential_starting_at_one(spectrum):
    results = parameter_sweep(
        SILICON, spectrum,
        bandgap_values=[1.0, 1.12], thickness_values=[SILICON.thickness_nm],
        ar_index_values=[1.38], lifetime_multiplier_values=[1.0],
        temperature_values=[298.15], uv_conversion_efficiency_values=[0.0],
    )
    assert [r.rank for r in results] == list(range(1, len(results) + 1))


def test_sweep_covers_the_full_cartesian_product_when_under_the_cap(spectrum):
    results = parameter_sweep(
        SILICON, spectrum,
        bandgap_values=[1.0, 1.12], thickness_values=[SILICON.thickness_nm, SILICON.thickness_nm * 2],
        ar_index_values=[1.38], lifetime_multiplier_values=[1.0],
        temperature_values=[298.15], uv_conversion_efficiency_values=[0.0],
    )
    assert len(results) == 2 * 2


def test_sweep_respects_max_configs_cap_via_deterministic_downsampling(spectrum):
    results = parameter_sweep(
        SILICON, spectrum,
        bandgap_values=[1.0, 1.05, 1.1, 1.15], thickness_values=[SILICON.thickness_nm, SILICON.thickness_nm * 2],
        ar_index_values=[1.3, 1.6], lifetime_multiplier_values=[0.5, 1.0],
        temperature_values=[290.0, 300.0], uv_conversion_efficiency_values=[0.0, 0.5],
        max_configs=10,
    )
    assert len(results) <= 10


def test_sweep_is_deterministic(spectrum):
    kwargs = dict(
        bandgap_values=[1.0, 1.12], thickness_values=[SILICON.thickness_nm],
        ar_index_values=[1.38, 1.6], lifetime_multiplier_values=[1.0],
        temperature_values=[298.15], uv_conversion_efficiency_values=[0.0],
    )
    r1 = parameter_sweep(SILICON, spectrum, **kwargs)
    r2 = parameter_sweep(SILICON, spectrum, **kwargs)
    assert [r.net_energy_output_w_m2 for r in r1] == [r.net_energy_output_w_m2 for r in r2]


def test_uv_conversion_efficiency_option_changes_net_energy(spectrum):
    base_kwargs = dict(
        bandgap_values=[SILICON.bandgap_eV], thickness_values=[SILICON.thickness_nm],
        ar_index_values=[1.38], lifetime_multiplier_values=[1.0], temperature_values=[298.15],
    )
    no_converter = parameter_sweep(SILICON, spectrum, uv_conversion_efficiency_values=[0.0], **base_kwargs)
    with_converter = parameter_sweep(SILICON, spectrum, uv_conversion_efficiency_values=[0.9], **base_kwargs)
    assert no_converter[0].net_energy_output_w_m2 != with_converter[0].net_energy_output_w_m2
