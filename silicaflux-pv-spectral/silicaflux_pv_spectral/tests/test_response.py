import numpy as np
import pytest

from silicaflux_pv_spectral.materials import SILICON
from silicaflux_pv_spectral.optics import compute_stack_optics, default_optical_stack
from silicaflux_pv_spectral.photon import photon_flux as compute_photon_flux
from silicaflux_pv_spectral.response import (
    compute_spectral_response,
    dark_saturation_current_density_a_m2,
    solve_operating_point,
    surface_loss_fraction,
)
from silicaflux_pv_spectral.spectrum import terrestrial_spectrum


@pytest.fixture(scope="module")
def baseline_response():
    spectrum = terrestrial_spectrum()
    flux = compute_photon_flux(spectrum)
    stack = default_optical_stack()
    _R, T, _A = compute_stack_optics(stack.layers, SILICON, spectrum.wavelength_nm)
    result = compute_spectral_response(SILICON, spectrum.wavelength_nm, flux, T)
    return spectrum, result


def test_eqe_and_iqe_are_bounded(baseline_response):
    _spectrum, result = baseline_response
    assert np.all(result.eqe >= 0.0) and np.all(result.eqe <= 1.0)
    assert np.all(result.iqe >= 0.0) and np.all(result.iqe <= 1.0)


def test_eqe_never_exceeds_iqe_or_optical_absorption(baseline_response):
    _spectrum, result = baseline_response
    assert np.all(result.eqe <= result.iqe + 1e-9)
    assert np.all(result.eqe <= result.optical_absorption_fraction + 1e-9)


def test_surface_loss_fraction_worse_in_uv_than_nir_for_poorly_passivated_cell():
    from dataclasses import replace

    from silicaflux_pv_spectral.recombination import carrier_lifetime

    poorly_passivated = replace(SILICON, surface_recomb_velocity_cm_s=1.0e6)
    state = carrier_lifetime(poorly_passivated)
    wl = np.array([300.0, 1200.0])
    loss = surface_loss_fraction(poorly_passivated, wl, state)
    assert loss[0] > loss[1]  # UV (heavily absorbed near-surface) suffers more


def test_surface_loss_fraction_improves_with_better_passivation():
    from dataclasses import replace

    from silicaflux_pv_spectral.recombination import carrier_lifetime

    good = replace(SILICON, surface_recomb_velocity_cm_s=10.0)
    bad = replace(SILICON, surface_recomb_velocity_cm_s=1.0e6)
    wl = np.array([320.0])
    loss_good = surface_loss_fraction(good, wl, carrier_lifetime(good))
    loss_bad = surface_loss_fraction(bad, wl, carrier_lifetime(bad))
    assert loss_good[0] < loss_bad[0]


def test_power_bands_sum_to_total(baseline_response):
    _spectrum, result = baseline_response
    assert result.p_uv_w_m2 + result.p_visible_w_m2 + result.p_nir_w_m2 == pytest.approx(
        result.p_total_w_m2, rel=1e-6
    )


def test_uv_power_fraction_is_small_but_positive_with_uv_blocking_encapsulant(baseline_response):
    _spectrum, result = baseline_response
    assert 0.0 < result.uv_power_fraction < 0.05


def test_uv_transparent_encapsulant_meaningfully_increases_uv_power():
    spectrum = terrestrial_spectrum()
    flux = compute_photon_flux(spectrum)

    blocking_stack = default_optical_stack(encapsulant_uv_blocking=True)
    _R1, T1, _A1 = compute_stack_optics(blocking_stack.layers, SILICON, spectrum.wavelength_nm)
    blocking_result = compute_spectral_response(SILICON, spectrum.wavelength_nm, flux, T1)

    open_stack = default_optical_stack(encapsulant_uv_blocking=False)
    _R2, T2, _A2 = compute_stack_optics(open_stack.layers, SILICON, spectrum.wavelength_nm)
    open_result = compute_spectral_response(SILICON, spectrum.wavelength_nm, flux, T2)

    assert open_result.p_uv_w_m2 > 5.0 * blocking_result.p_uv_w_m2
    assert open_result.operating_point.p_mp_w_m2 > blocking_result.operating_point.p_mp_w_m2


def test_operating_point_zero_current_gives_zero_power():
    op = solve_operating_point(0.0, SILICON)
    assert op.v_oc_v == 0.0
    assert op.p_mp_w_m2 == 0.0


def test_operating_point_voc_increases_with_current():
    low = solve_operating_point(50.0, SILICON)
    high = solve_operating_point(500.0, SILICON)
    assert high.v_oc_v > low.v_oc_v
    assert 0.0 <= low.fill_factor <= 1.0
    assert 0.0 <= high.fill_factor <= 1.0


def test_operating_point_vmp_between_zero_and_voc():
    op = solve_operating_point(300.0, SILICON)
    assert 0.0 <= op.v_mp_v <= op.v_oc_v


def test_dark_saturation_current_increases_with_temperature():
    j0_cold = dark_saturation_current_density_a_m2(SILICON, 280.0)
    j0_hot = dark_saturation_current_density_a_m2(SILICON, 340.0)
    assert j0_hot > j0_cold


def test_higher_temperature_reduces_voc_all_else_equal():
    j_sc = 300.0
    op_cold = solve_operating_point(j_sc, SILICON, temperature_k=280.0)
    op_hot = solve_operating_point(j_sc, SILICON, temperature_k=340.0)
    assert op_hot.v_oc_v < op_cold.v_oc_v


def test_v_effective_is_wavelength_invariant(baseline_response):
    spectrum, result = baseline_response
    from silicaflux_pv_spectral.response import v_effective

    v_eff = v_effective(spectrum.wavelength_nm, result.operating_point)
    assert np.all(v_eff == result.operating_point.v_mp_v)
