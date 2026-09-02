from dataclasses import replace

import numpy as np
import pytest

from silicaflux_pv_spectral.materials import SILICON
from silicaflux_pv_spectral.optics import compute_stack_optics, default_optical_stack
from silicaflux_pv_spectral.photon import photon_flux as compute_photon_flux
from silicaflux_pv_spectral.response import compute_spectral_response
from silicaflux_pv_spectral.spectral_converter import (
    SpectralConverter,
    absorption_spectrum,
    emission_spectrum_density,
    uv_conversion_gain,
)
from silicaflux_pv_spectral.spectrum import terrestrial_spectrum


@pytest.fixture(scope="module")
def wavelength_and_flux():
    spectrum = terrestrial_spectrum()
    return spectrum.wavelength_nm, compute_photon_flux(spectrum)


def test_absorption_spectrum_bounded(wavelength_and_flux):
    wl, _flux = wavelength_and_flux
    converter = SpectralConverter()
    a = absorption_spectrum(converter, wl)
    assert np.all(a >= 0.0) and np.all(a <= 1.0)
    assert a.max() == pytest.approx(converter.absorption_peak, rel=1e-6)


def test_emission_spectrum_integrates_to_one(wavelength_and_flux):
    wl, _flux = wavelength_and_flux
    converter = SpectralConverter()
    density = emission_spectrum_density(converter, wl)
    assert np.trapezoid(density, wl) == pytest.approx(1.0, rel=1e-3)


def test_conversion_gain_positive_when_native_uv_response_is_poor(wavelength_and_flux):
    wl, flux = wavelength_and_flux
    stack = default_optical_stack(encapsulant_uv_blocking=True)
    _R, T, _A = compute_stack_optics(stack.layers, SILICON, wl)
    resp = compute_spectral_response(SILICON, wl, flux, T)
    converter = SpectralConverter()

    result = uv_conversion_gain(converter, SILICON, wl, flux, T, resp.recombination_state, resp.operating_point.v_mp_v)
    assert result.uv_conversion_gain_w_m2 > 0.0
    assert result.net_positive


def test_conversion_gain_can_be_negative_when_native_uv_response_is_already_good(wavelength_and_flux):
    wl, flux = wavelength_and_flux
    stack = default_optical_stack(encapsulant_uv_blocking=False)
    _R, T, _A = compute_stack_optics(stack.layers, SILICON, wl)
    resp = compute_spectral_response(SILICON, wl, flux, T)
    converter = SpectralConverter()

    result = uv_conversion_gain(converter, SILICON, wl, flux, T, resp.recombination_state, resp.operating_point.v_mp_v)
    assert result.uv_conversion_gain_w_m2 < 0.0
    assert not result.net_positive


def test_worse_converter_parameters_reduce_the_gain(wavelength_and_flux):
    wl, flux = wavelength_and_flux
    stack = default_optical_stack(encapsulant_uv_blocking=True)
    _R, T, _A = compute_stack_optics(stack.layers, SILICON, wl)
    resp = compute_spectral_response(SILICON, wl, flux, T)

    good = SpectralConverter()
    bad = replace(good, quantum_yield=0.1, reabsorption=0.7, escape_efficiency=0.2)

    good_result = uv_conversion_gain(good, SILICON, wl, flux, T, resp.recombination_state, resp.operating_point.v_mp_v)
    bad_result = uv_conversion_gain(bad, SILICON, wl, flux, T, resp.recombination_state, resp.operating_point.v_mp_v)
    assert bad_result.uv_conversion_gain_w_m2 < good_result.uv_conversion_gain_w_m2


def test_stability_factor_scales_down_conversion(wavelength_and_flux):
    wl, flux = wavelength_and_flux
    stack = default_optical_stack(encapsulant_uv_blocking=True)
    _R, T, _A = compute_stack_optics(stack.layers, SILICON, wl)
    resp = compute_spectral_response(SILICON, wl, flux, T)

    fresh = SpectralConverter()
    degraded = replace(fresh, stability_factor=0.2)

    fresh_result = uv_conversion_gain(fresh, SILICON, wl, flux, T, resp.recombination_state, resp.operating_point.v_mp_v)
    degraded_result = uv_conversion_gain(degraded, SILICON, wl, flux, T, resp.recombination_state, resp.operating_point.v_mp_v)
    assert degraded_result.re_emitted_photons_s_m2 < fresh_result.re_emitted_photons_s_m2
