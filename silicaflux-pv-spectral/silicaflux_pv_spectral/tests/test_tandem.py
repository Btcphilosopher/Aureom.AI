import pytest

from silicaflux_pv_spectral.photon import photon_flux as compute_photon_flux
from silicaflux_pv_spectral.spectrum import terrestrial_spectrum
from silicaflux_pv_spectral.tandem import (
    DEFAULT_TANDEM,
    tandem_current_matching,
    tandem_device_operating_point,
    tandem_optimiser,
    tandem_spectral_split,
)


@pytest.fixture(scope="module")
def split():
    spectrum = terrestrial_spectrum()
    flux = compute_photon_flux(spectrum)
    return tandem_spectral_split(DEFAULT_TANDEM, spectrum.wavelength_nm, flux)


def test_both_subcells_generate_positive_current(split):
    assert split.top.j_sc_a_m2 > 0.0
    assert split.bottom.j_sc_a_m2 > 0.0


def test_bottom_incident_fraction_never_exceeds_top_transmission(split):
    assert (split.bottom_incident_fraction <= split.top_transmission_into_absorber + 1e-9).all()


def test_current_matching_is_the_minimum_of_the_two_subcells(split):
    result = tandem_current_matching(split)
    assert result.i_matched_a_m2 == pytest.approx(min(result.i_top_a_m2, result.i_bottom_a_m2))
    assert 0.0 <= result.current_matching_error <= 1.0


def test_device_power_cannot_exceed_matched_current_times_open_circuit_voltage(split):
    device = tandem_device_operating_point(split, DEFAULT_TANDEM)
    assert device.p_mp_w_m2 <= device.i_mp_a_m2 * device.v_oc_v + 1e-6
    assert device.i_mp_a_m2 <= device.current_matching.i_matched_a_m2 + 1e-6


def test_device_voc_exceeds_either_subcell_alone():
    # Series-connected tandem Voc should exceed a lone subcell's Voc (voltages add).
    from silicaflux_pv_spectral.response import solve_operating_point

    spectrum = terrestrial_spectrum()
    flux = compute_photon_flux(spectrum)
    split_result = tandem_spectral_split(DEFAULT_TANDEM, spectrum.wavelength_nm, flux)
    device = tandem_device_operating_point(split_result, DEFAULT_TANDEM)

    top_alone = solve_operating_point(split_result.top.j_sc_a_m2, DEFAULT_TANDEM.top)
    assert device.v_oc_v > top_alone.v_oc_v


def test_tandem_optimiser_improves_efficiency_over_baseline():
    spectrum = terrestrial_spectrum()
    result = tandem_optimiser(spectrum, n_bandgap_steps=5, n_thickness_steps=4)
    assert result.device_efficiency >= result.baseline_device_efficiency
    assert result.device.p_mp_w_m2 >= result.baseline_device.p_mp_w_m2


def test_tandem_optimiser_is_deterministic():
    spectrum = terrestrial_spectrum()
    r1 = tandem_optimiser(spectrum, n_bandgap_steps=4, n_thickness_steps=3)
    r2 = tandem_optimiser(spectrum, n_bandgap_steps=4, n_thickness_steps=3)
    assert r1 == r2


def test_tandem_optimiser_stays_within_requested_bandgap_bounds():
    spectrum = terrestrial_spectrum()
    bounds = (1.55, 1.9)
    result = tandem_optimiser(spectrum, top_bandgap_range_eV=bounds, n_bandgap_steps=5, n_thickness_steps=3)
    assert bounds[0] <= result.top_bandgap_eV <= bounds[1]
