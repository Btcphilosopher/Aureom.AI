"""
UV spectral-conversion (down-shifting) layer (SilicaFlux spec item 11).

UV PHOTON -> SPECTRAL CONVERTER -> LOWER-ENERGY PHOTONS -> PV ABSORBER -> ELECTRICAL ENERGY

Explicitly does *not* assume a converter is a net win: every loss mechanism
(finite absorption, quantum yield < 1, self-reabsorption, escape-cone /
geometric collection efficiency, long-term stability) is applied before
comparing against the true counterfactual -- what those same UV photons
would have contributed had they hit the absorber directly, with no
converter in the path at all. ``uv_conversion_gain`` can and does come out
negative for a poor converter or a UV-transparent module that already had
decent native UV response.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import ELEMENTARY_CHARGE_C, SPECTRAL_BANDS_NM
from .materials import PVMaterial
from .recombination import RecombinationState
from .response import external_quantum_efficiency
from .spectrum import integrate_band


@dataclass
class SpectralConverter:
    name: str = "UV_DOWNSHIFTING_LAYER"
    absorption_center_nm: float = 340.0
    absorption_width_nm: float = 40.0
    absorption_peak: float = 0.85
    emission_center_nm: float = 480.0
    emission_width_nm: float = 30.0
    quantum_yield: float = 0.85
    reabsorption: float = 0.10         # fraction of emitted photons self-reabsorbed by the converter
    escape_efficiency: float = 0.80    # fraction of surviving emitted photons geometrically reaching the absorber
    stability_factor: float = 1.0      # 1.0 = fresh; degrades over service life (couples to degradation.py)


def absorption_spectrum(converter: SpectralConverter, wavelength_nm: np.ndarray) -> np.ndarray:
    """``absorption_spectrum[lambda]`` -- Gaussian absorption band, peak fraction absorbed at line centre."""
    wavelength_nm = np.asarray(wavelength_nm, dtype=float)
    shape = np.exp(-(((wavelength_nm - converter.absorption_center_nm) / converter.absorption_width_nm) ** 2))
    return np.clip(converter.absorption_peak * shape, 0.0, 1.0)


def emission_spectrum_density(converter: SpectralConverter, wavelength_nm: np.ndarray) -> np.ndarray:
    """Normalised (integrates to 1 over the given grid) Gaussian emission line shape -- a spectral probability density."""
    wavelength_nm = np.asarray(wavelength_nm, dtype=float)
    shape = np.exp(-(((wavelength_nm - converter.emission_center_nm) / converter.emission_width_nm) ** 2))
    total = np.trapezoid(shape, wavelength_nm)
    return shape / total if total > 0 else np.zeros_like(shape)


@dataclass
class UVConversionResult:
    absorbed_by_converter_photons_s_m2: float
    re_emitted_photons_s_m2: float
    direct_pass_through_power_w_m2: float
    converted_power_w_m2: float
    with_converter_total_power_w_m2: float
    without_converter_power_w_m2: float
    uv_conversion_gain_w_m2: float
    net_positive: bool


def uv_conversion_gain(
    converter: SpectralConverter,
    material: PVMaterial,
    wavelength_nm: np.ndarray,
    photon_flux: np.ndarray,
    optical_transmission: np.ndarray,
    recombination_state: RecombinationState,
    v_effective_v: float,
    band_low_nm: float = SPECTRAL_BANDS_NM["UV"][0],
    band_high_nm: float = SPECTRAL_BANDS_NM["UV"][1],
) -> UVConversionResult:
    """``UV_CONVERSION_GAIN`` -- with-converter power minus the true no-converter counterfactual."""
    eqe_native, _iqe, _abs = external_quantum_efficiency(material, wavelength_nm, optical_transmission, recombination_state)

    # --- Counterfactual: no converter, UV photons hit the absorber directly ---
    uv_mask = (wavelength_nm >= band_low_nm) & (wavelength_nm <= band_high_nm)
    direct_power_density = photon_flux * eqe_native * ELEMENTARY_CHARGE_C * v_effective_v
    without_converter_power = integrate_band(direct_power_density, wavelength_nm, band_low_nm, band_high_nm)

    # --- With converter: split incident UV flux into "absorbed by converter" and "passes through" ---
    absorption = absorption_spectrum(converter, wavelength_nm)
    uv_flux = np.where(uv_mask, photon_flux, 0.0)

    absorbed_flux = uv_flux * absorption
    pass_through_flux = uv_flux * (1.0 - absorption)

    absorbed_total = integrate_band(absorbed_flux, wavelength_nm, band_low_nm, band_high_nm)
    pass_through_power_density = pass_through_flux * eqe_native * ELEMENTARY_CHARGE_C * v_effective_v
    pass_through_power = integrate_band(pass_through_power_density, wavelength_nm, band_low_nm, band_high_nm)

    re_emitted_total = (
        absorbed_total * converter.quantum_yield * (1.0 - converter.reabsorption)
        * converter.escape_efficiency * converter.stability_factor
    )
    emission_density = emission_spectrum_density(converter, wavelength_nm)
    re_emitted_flux = re_emitted_total * emission_density

    converted_power_density = re_emitted_flux * eqe_native * ELEMENTARY_CHARGE_C * v_effective_v
    converted_power = integrate_band(converted_power_density, wavelength_nm)

    with_converter_power = pass_through_power + converted_power
    gain = with_converter_power - without_converter_power

    return UVConversionResult(
        absorbed_by_converter_photons_s_m2=absorbed_total,
        re_emitted_photons_s_m2=re_emitted_total,
        direct_pass_through_power_w_m2=pass_through_power,
        converted_power_w_m2=converted_power,
        with_converter_total_power_w_m2=with_converter_power,
        without_converter_power_w_m2=without_converter_power,
        uv_conversion_gain_w_m2=gain,
        net_positive=gain > 0.0,
    )
