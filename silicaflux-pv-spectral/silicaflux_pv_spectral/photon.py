"""
Photon engine (SilicaFlux spec item 2).

Converts spectral irradiance into photon energy and photon flux, the
currency every downstream stage (absorption, EQE, carrier generation)
actually works in.
"""

from __future__ import annotations

import numpy as np

from .constants import (
    ELEMENTARY_CHARGE_C,
    HC_EV_NM,
    PLANCK_CONSTANT_J_S,
    SPEED_OF_LIGHT_M_S,
)
from .spectrum import SolarSpectrum, integrate_band


def photon_energy_j(wavelength_nm: np.ndarray) -> np.ndarray:
    """``E_PHOTON(lambda) = h*c/lambda``, in Joules."""
    wavelength_m = np.asarray(wavelength_nm, dtype=float) * 1e-9
    return PLANCK_CONSTANT_J_S * SPEED_OF_LIGHT_M_S / wavelength_m


def photon_energy_ev(wavelength_nm: np.ndarray) -> np.ndarray:
    """Photon energy in eV, using the exact spec constant ``HC_EV_NM``."""
    return HC_EV_NM / np.asarray(wavelength_nm, dtype=float)


def photon_flux(spectrum: SolarSpectrum) -> np.ndarray:
    """
    ``PHOTON_FLUX(lambda) = spectral_irradiance(lambda) / E_PHOTON(lambda)``

    Returns photons / (s m^2 nm) -- a photon-count spectral density on the
    same wavelength grid as the input spectrum.
    """
    e_photon_j = photon_energy_j(spectrum.wavelength_nm)
    return spectrum.spectral_irradiance_w_m2_nm / e_photon_j


def total_photon_flux(spectrum: SolarSpectrum, low_nm: float | None = None, high_nm: float | None = None) -> float:
    """``TOTAL_PHOTON_FLUX = integral(PHOTON_FLUX(lambda), lambda_min, lambda_max)``, photons/(s m^2)."""
    flux = photon_flux(spectrum)
    return integrate_band(flux, spectrum.wavelength_nm, low_nm, high_nm)


def photon_flux_to_current_density_a_m2(flux_photons_s_m2: float) -> float:
    """Convert an integrated photon flux into the short-circuit current density it implies at unit EQE."""
    return flux_photons_s_m2 * ELEMENTARY_CHARGE_C
