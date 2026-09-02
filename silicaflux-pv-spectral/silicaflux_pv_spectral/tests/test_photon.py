import numpy as np
import pytest

from silicaflux_pv_spectral.photon import (
    photon_energy_ev,
    photon_energy_j,
    photon_flux,
    photon_flux_to_current_density_a_m2,
    total_photon_flux,
)
from silicaflux_pv_spectral.spectrum import SolarSpectrum, terrestrial_spectrum


def test_photon_energy_ev_matches_well_known_500nm_value():
    # A very commonly quoted reference point: ~500 nm photons carry ~2.48 eV.
    e = photon_energy_ev(np.array([500.0]))[0]
    assert e == pytest.approx(2.4797, abs=0.001)


def test_photon_energy_decreases_with_wavelength():
    energies = photon_energy_ev(np.array([300.0, 600.0, 1200.0]))
    assert energies[0] > energies[1] > energies[2]


def test_photon_energy_j_and_ev_are_consistent():
    from silicaflux_pv_spectral.constants import ELEMENTARY_CHARGE_C

    wl = np.array([400.0, 800.0, 1500.0])
    assert np.allclose(photon_energy_j(wl) / ELEMENTARY_CHARGE_C, photon_energy_ev(wl), rtol=1e-6)


def test_photon_flux_is_positive_and_finite():
    spectrum = terrestrial_spectrum()
    flux = photon_flux(spectrum)
    assert np.all(np.isfinite(flux))
    assert np.all(flux >= 0.0)


def test_total_photon_flux_matches_manual_trapezoid():
    spectrum = terrestrial_spectrum()
    flux = photon_flux(spectrum)
    manual = float(np.trapezoid(flux, spectrum.wavelength_nm))
    assert total_photon_flux(spectrum) == pytest.approx(manual, rel=1e-9)


def test_uv_photons_carry_fewer_flux_per_watt_than_nir():
    # Equal irradiance packed into a UV bin vs a NIR bin: UV photons carry
    # more energy each, so photon flux per unit irradiance must be lower.
    uv = SolarSpectrum(np.array([320.0]), np.array([1.0]))
    nir = SolarSpectrum(np.array([1200.0]), np.array([1.0]))
    assert photon_flux(uv)[0] < photon_flux(nir)[0]


def test_photon_flux_to_current_density_scales_linearly():
    assert photon_flux_to_current_density_a_m2(2.0) == pytest.approx(
        2.0 * photon_flux_to_current_density_a_m2(1.0)
    )
