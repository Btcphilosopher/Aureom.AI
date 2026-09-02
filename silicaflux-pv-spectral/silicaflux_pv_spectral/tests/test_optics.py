import numpy as np
import pytest

from silicaflux_pv_spectral.materials import SILICON
from silicaflux_pv_spectral.spectrum import terrestrial_spectrum
from silicaflux_pv_spectral.optics import (
    absorbed_photon_flux,
    absorber_absorption_fraction,
    compute_stack_optics,
    default_optical_stack,
    optimise_front_surface,
    total_absorbed_uv,
)


@pytest.fixture(scope="module")
def spectrum():
    return terrestrial_spectrum()


def test_stack_energy_conservation(spectrum):
    stack = default_optical_stack()
    R, T, A = compute_stack_optics(stack.layers, SILICON, spectrum.wavelength_nm)
    assert np.allclose(R + T + A, 1.0, atol=1e-8)


def test_stack_outputs_are_bounded(spectrum):
    stack = default_optical_stack()
    R, T, A = compute_stack_optics(stack.layers, SILICON, spectrum.wavelength_nm)
    for arr in (R, T, A):
        assert np.all(arr >= -1e-12)
        assert np.all(arr <= 1.0 + 1e-12)


def test_bare_stack_no_layers_gives_fresnel_reflectance_at_normal_incidence():
    # No coatings at all: R should reduce to the bare-substrate Fresnel
    # reflectance |(N_sub - 1) / (N_sub + 1)|^2 for the complex substrate
    # index N_sub = n - ik (silicon has non-negligible k even at 600 nm).
    wl = np.array([600.0])
    R, T, A = compute_stack_optics([], SILICON, wl, texture_enabled=False)
    from silicaflux_pv_spectral.materials import extinction_coefficient, refractive_index

    n_sub = refractive_index(SILICON, wl)[0]
    k_sub = extinction_coefficient(SILICON, wl)[0]
    N_sub = complex(n_sub, -k_sub)
    expected_R = abs((N_sub - 1.0) / (N_sub + 1.0)) ** 2
    assert R[0] == pytest.approx(expected_R, rel=1e-6)


def test_uv_blocking_encapsulant_kills_uv_transmission_into_absorber(spectrum):
    blocking_stack = default_optical_stack(encapsulant_uv_blocking=True)
    transparent_stack = default_optical_stack(encapsulant_uv_blocking=False)
    uv_mask = (spectrum.wavelength_nm >= 300.0) & (spectrum.wavelength_nm <= 360.0)

    _, T_block, _ = compute_stack_optics(blocking_stack.layers, SILICON, spectrum.wavelength_nm)
    _, T_open, _ = compute_stack_optics(transparent_stack.layers, SILICON, spectrum.wavelength_nm)

    assert T_block[uv_mask].mean() < 0.1
    assert T_open[uv_mask].mean() > 0.7


def test_texturing_reduces_reflectance_without_breaking_conservation(spectrum):
    stack = default_optical_stack()
    R_textured, T_textured, A_textured = compute_stack_optics(stack.layers, SILICON, spectrum.wavelength_nm, texture_enabled=True)
    R_planar, T_planar, A_planar = compute_stack_optics(stack.layers, SILICON, spectrum.wavelength_nm, texture_enabled=False)

    visible_mask = (spectrum.wavelength_nm >= 450.0) & (spectrum.wavelength_nm <= 650.0)
    assert R_textured[visible_mask].mean() < R_planar[visible_mask].mean()
    assert np.allclose(R_textured + T_textured + A_textured, 1.0, atol=1e-8)


def test_absorber_absorption_fraction_bounded_and_monotonic_with_thickness():
    thin = SILICON
    from dataclasses import replace

    thick = replace(SILICON, thickness_nm=SILICON.thickness_nm * 5)
    wl = np.array([600.0])
    a_thin = absorber_absorption_fraction(thin, wl)[0]
    a_thick = absorber_absorption_fraction(thick, wl)[0]
    assert 0.0 <= a_thin <= 1.0
    assert 0.0 <= a_thick <= 1.0
    assert a_thick >= a_thin


def test_back_reflectance_increases_absorption():
    wl = np.array([1000.0])  # weakly-absorbed wavelength, where a back reflector should matter
    a_no_reflector = absorber_absorption_fraction(SILICON, wl, back_reflectance=0.0)[0]
    a_with_reflector = absorber_absorption_fraction(SILICON, wl, back_reflectance=0.9)[0]
    assert a_with_reflector > a_no_reflector
    assert a_with_reflector <= 1.0


def test_absorbed_photon_flux_is_product_of_its_terms():
    photon_flux = np.array([1e19, 2e19])
    atm = np.array([0.5, 0.8])
    opt = np.array([0.9, 0.95])
    absorption = np.array([0.7, 0.6])
    result = absorbed_photon_flux(photon_flux, atm, opt, absorption)
    assert np.allclose(result, photon_flux * atm * opt * absorption)


def test_total_absorbed_uv_is_nonnegative(spectrum):
    from silicaflux_pv_spectral.photon import photon_flux as compute_photon_flux
    from silicaflux_pv_spectral.spectrum import atmospheric_transmission

    stack = default_optical_stack()
    R, T, A = compute_stack_optics(stack.layers, SILICON, spectrum.wavelength_nm)
    flux = compute_photon_flux(spectrum)
    atm_t = atmospheric_transmission(spectrum.wavelength_nm)
    absorption = absorber_absorption_fraction(SILICON, spectrum.wavelength_nm)
    absorbed = absorbed_photon_flux(flux, atm_t, T, absorption)
    total = total_absorbed_uv(absorbed, spectrum.wavelength_nm)
    assert total >= 0.0


def test_front_surface_optimiser_improves_uv_without_catastrophic_visible_nir_loss(spectrum):
    result = optimise_front_surface(SILICON, spectrum, n_index_steps=7, n_thickness_steps=8)
    assert result.uv_reflection_loss_w_m2 <= result.baseline_uv_reflection_loss_w_m2
    tolerance = 1.16  # matches the optimiser's default catastrophic_loss_tolerance with slack
    assert result.visible_reflection_loss_w_m2 <= result.baseline_visible_reflection_loss_w_m2 * tolerance
    assert result.nir_reflection_loss_w_m2 <= result.baseline_nir_reflection_loss_w_m2 * tolerance


def test_front_surface_optimiser_is_deterministic(spectrum):
    r1 = optimise_front_surface(SILICON, spectrum, n_index_steps=5, n_thickness_steps=5)
    r2 = optimise_front_surface(SILICON, spectrum, n_index_steps=5, n_thickness_steps=5)
    assert r1 == r2
