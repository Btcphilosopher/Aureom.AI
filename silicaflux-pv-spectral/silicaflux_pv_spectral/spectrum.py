"""
Solar spectrum and atmospheric transmission model.

Implements SilicaFlux spec items 1 and 3:

* ``SPECTRUM`` / ``SolarSpectrum`` -- a wavelength-indexed spectral
  irradiance array on the 280 -> 2500 nm, 1 nm grid.
* An extraterrestrial (AM0) reference spectrum, generated from Planck's law
  for a 5778 K blackbody sun and normalised to the measured solar constant
  -- not a literal blackbody claim, just a smooth, deterministic,
  physically-grounded stand-in for a tabulated AM0 reference (e.g. the
  ASTM E490 table), documented as such.
* A clear-sky atmospheric transmission model in the style of Bird &
  Hulstrom (1981) / Iqbal (1983): Rayleigh scattering, ozone
  (Hartley/Huggins/Chappuis bands), water vapour, aerosol (Angstrom
  turbidity law) and uniformly-mixed-gas (O2/CO2 band) extinction, each a
  Beer-Lambert term ``exp(-tau(lambda) * airmass)``.

This is a *simplified* clear-sky model, not a full radiative-transfer code
(SMARTS/MODTRAN-grade): band shapes are smooth analytic approximations to
the real absorber cross sections rather than tabulated line-by-line data.
It is deterministic, vectorised, and physically self-consistent -- good
enough to answer "how much does the atmosphere filter the UV before it
reaches the module", which is the point of including it at all.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import (
    BOLTZMANN_CONSTANT_J_K,
    DOBSON_UNIT_MOLECULES_CM2,
    EARTH_SUN_DISTANCE_M,
    PLANCK_CONSTANT_J_S,
    SOLAR_CONSTANT_W_M2,
    SPECTRAL_BANDS_NM,
    SPEED_OF_LIGHT_M_S,
    SUN_RADIUS_M,
    SUN_SURFACE_TEMPERATURE_K,
    wavelength_grid_nm,
)


# --------------------------------------------------------------------------
# SPECTRUM data structure (item 1)
# --------------------------------------------------------------------------
@dataclass
class SolarSpectrum:
    """One spectral-irradiance value for every wavelength interval."""

    wavelength_nm: np.ndarray
    spectral_irradiance_w_m2_nm: np.ndarray

    def __post_init__(self) -> None:
        self.wavelength_nm = np.asarray(self.wavelength_nm, dtype=float)
        self.spectral_irradiance_w_m2_nm = np.asarray(
            self.spectral_irradiance_w_m2_nm, dtype=float
        )
        if self.wavelength_nm.shape != self.spectral_irradiance_w_m2_nm.shape:
            raise ValueError(
                "wavelength_nm and spectral_irradiance_w_m2_nm must have the same shape"
            )
        if np.any(self.spectral_irradiance_w_m2_nm < 0):
            raise ValueError("spectral irradiance cannot be negative")

    @property
    def total_irradiance_w_m2(self) -> float:
        return float(np.trapezoid(self.spectral_irradiance_w_m2_nm, self.wavelength_nm))

    def band_irradiance_w_m2(self, low_nm: float, high_nm: float) -> float:
        return integrate_band(self.spectral_irradiance_w_m2_nm, self.wavelength_nm, low_nm, high_nm)

    def in_band(self, band: str) -> float:
        low, high = SPECTRAL_BANDS_NM[band]
        return self.band_irradiance_w_m2(low, high)

    def scaled(self, factor: float) -> "SolarSpectrum":
        """Return a copy scaled by a constant (e.g. to model a different irradiance level)."""
        return SolarSpectrum(self.wavelength_nm.copy(), self.spectral_irradiance_w_m2_nm * factor)


# --------------------------------------------------------------------------
# Band integration helpers
# --------------------------------------------------------------------------
def band_mask(wavelength_nm: np.ndarray, low_nm: float, high_nm: float) -> np.ndarray:
    return (wavelength_nm >= low_nm) & (wavelength_nm <= high_nm)


def integrate_band(
    y: np.ndarray, wavelength_nm: np.ndarray, low_nm: float | None = None, high_nm: float | None = None
) -> float:
    """Trapezoidal integral of ``y`` over ``wavelength_nm``, optionally restricted to [low, high]."""
    if low_nm is None and high_nm is None:
        return float(np.trapezoid(y, wavelength_nm))
    mask = band_mask(wavelength_nm, low_nm if low_nm is not None else -np.inf,
                      high_nm if high_nm is not None else np.inf)
    if mask.sum() < 2:
        return 0.0
    return float(np.trapezoid(y[mask], wavelength_nm[mask]))


# --------------------------------------------------------------------------
# Extraterrestrial (AM0) spectrum via Planck's law
# --------------------------------------------------------------------------
def blackbody_spectral_radiance_w_m3(wavelength_m: np.ndarray, temperature_k: float) -> np.ndarray:
    """Planck's law: spectral radiance of a blackbody, W / (sr m^3)."""
    h, c, kB = PLANCK_CONSTANT_J_S, SPEED_OF_LIGHT_M_S, BOLTZMANN_CONSTANT_J_K
    x = (h * c) / (wavelength_m * kB * temperature_k)
    # exp(x) overflows for very short wavelengths at solar temperatures; clip
    # the exponent so the (physically negligible) tail returns ~0 instead of NaN.
    x = np.clip(x, None, 700.0)
    numerator = 2.0 * np.pi * h * c**2
    denominator = wavelength_m**5 * np.expm1(x)
    return numerator / denominator


def extraterrestrial_spectrum(
    wavelength_nm: np.ndarray | None = None,
    temperature_k: float = SUN_SURFACE_TEMPERATURE_K,
    normalize_to_w_m2: float | None = SOLAR_CONSTANT_W_M2,
) -> SolarSpectrum:
    """
    AM0 (top-of-atmosphere) spectral irradiance at 1 AU.

    Computed from Planck's law for a blackbody at ``temperature_k``, scaled
    by the sun's solid angle as seen from Earth, then (optionally)
    renormalised so the *full-spectrum* integral matches the measured solar
    constant. The real sun is not a perfect blackbody (Fraunhofer lines,
    chromospheric effects), so this renormalisation is what keeps the total
    power realistic while retaining a smooth, physically-shaped spectrum --
    a standard simplification for synthetic AM0 spectra.
    """
    if wavelength_nm is None:
        wavelength_nm = wavelength_grid_nm()
    wavelength_m = wavelength_nm * 1e-9

    solid_angle_factor = np.pi * (SUN_RADIUS_M / EARTH_SUN_DISTANCE_M) ** 2
    radiance = blackbody_spectral_radiance_w_m3(wavelength_m, temperature_k)
    irradiance_w_m3 = radiance * solid_angle_factor
    irradiance_w_m2_nm = irradiance_w_m3 * 1e-9  # W/m^3 -> W/m^2/nm

    if normalize_to_w_m2 is not None:
        # Normalise against the *unclipped* full-spectrum blackbody power
        # (0 -> 50 micron captures effectively all of a 5778 K blackbody's
        # output) so the 280-2500 nm slice we actually keep carries the
        # correct fraction of total solar power.
        full_grid_nm = np.linspace(1.0, 50000.0, 20000)
        full_radiance = blackbody_spectral_radiance_w_m3(full_grid_nm * 1e-9, temperature_k)
        full_irradiance = full_radiance * solid_angle_factor * 1e-9
        full_total = float(np.trapezoid(full_irradiance, full_grid_nm))
        scale = normalize_to_w_m2 / full_total
        irradiance_w_m2_nm = irradiance_w_m2_nm * scale

    return SolarSpectrum(wavelength_nm, irradiance_w_m2_nm)


# --------------------------------------------------------------------------
# Atmospheric transmission (item 3)
# --------------------------------------------------------------------------
@dataclass
class AtmosphericConditions:
    """Configurable atmospheric state driving ``atmospheric_transmission``."""

    solar_zenith_deg: float = 48.19        # -> relative airmass ~= 1.5 (ASTM G173 reference)
    ozone_column_du: float = 300.0          # Dobson units, standard-atmosphere default
    precipitable_water_cm: float = 1.42     # US Standard Atmosphere default
    aerosol_optical_depth_500nm: float = 0.084  # Angstrom beta-equivalent, clear rural sky
    angstrom_exponent: float = 1.3
    pressure_ratio: float = 1.0             # local pressure / sea-level pressure (altitude proxy)
    # Fraction of Rayleigh/aerosol-*scattered* photons that still reach the
    # ground as diffuse skylight rather than being lost back to space. Pure
    # Beer-Lambert extinction treats scattering exactly like absorption
    # (photon gone); physically it isn't -- most scattered UV/blue light
    # reaches the ground as diffuse sky radiance (why the clear sky is
    # blue), and standard *global* reference spectra (e.g. AM1.5G) include
    # it. This is a simplified single-parameter stand-in for that
    # direct+diffuse split, not a rigorously retrieved atmospheric constant.
    diffuse_recovery_fraction: float = 0.75


def relative_airmass(solar_zenith_deg: float) -> float:
    """Kasten & Young (1989) relative optical airmass."""
    theta = np.radians(solar_zenith_deg)
    return 1.0 / (np.cos(theta) + 0.50572 * (96.07995 - solar_zenith_deg) ** (-1.6364))


def _rayleigh_optical_depth(wavelength_um: np.ndarray, pressure_ratio: float) -> np.ndarray:
    """Approximate Rayleigh optical depth correlation (Iqbal 1983; Bird & Hulstrom 1981)."""
    tau = 0.00864 * wavelength_um ** (-(3.916 + 0.074 * wavelength_um + 0.05 / wavelength_um))
    return tau * pressure_ratio


def _ozone_optical_depth(wavelength_nm: np.ndarray, ozone_column_du: float) -> np.ndarray:
    """
    Smooth analytic approximation to the ozone absorption cross section
    (Hartley band peak ~255 nm, Huggins tail ~300 nm, weak Chappuis band
    ~600 nm), scaled by the ozone column density.

    This is a parametric *shape* fit, not tabulated laboratory cross
    sections -- it reproduces the well-known qualitative behaviour (near
    total absorption below ~290 nm, a rapidly-opening UVB/UVA window
    above it, a weak visible dip) without embedding a large external
    dataset.
    """
    sigma_cm2 = (
        1.1e-17 * np.exp(-(((wavelength_nm - 255.0) / 16.0) ** 2))   # Hartley band
        + 7.0e-20 * np.exp(-(((wavelength_nm - 298.0) / 17.0) ** 2))  # Huggins tail
        + 5.0e-21 * np.exp(-(((wavelength_nm - 600.0) / 90.0) ** 2))  # Chappuis band
    )
    column_molecules_cm2 = ozone_column_du * DOBSON_UNIT_MOLECULES_CM2
    return sigma_cm2 * column_molecules_cm2


def _water_vapor_optical_depth(wavelength_nm: np.ndarray, precipitable_water_cm: float) -> np.ndarray:
    """Simplified (linear-in-column) approximation of the main H2O absorption bands."""
    band_shape = (
        0.15 * np.exp(-(((wavelength_nm - 940.0) / 25.0) ** 2))
        + 0.10 * np.exp(-(((wavelength_nm - 1130.0) / 35.0) ** 2))
        + 0.65 * np.exp(-(((wavelength_nm - 1380.0) / 45.0) ** 2))
        + 0.35 * np.exp(-(((wavelength_nm - 1870.0) / 55.0) ** 2))
        + 0.20 * np.exp(-(((wavelength_nm - 2500.0) / 80.0) ** 2))
    )
    return precipitable_water_cm * band_shape


def _aerosol_optical_depth(wavelength_nm: np.ndarray, aod_500nm: float, angstrom_exponent: float) -> np.ndarray:
    """Angstrom turbidity power law, anchored at the conventional 500 nm reference."""
    wavelength_um = wavelength_nm / 1000.0
    return aod_500nm * (wavelength_um / 0.5) ** (-angstrom_exponent)


def _mixed_gas_optical_depth(wavelength_nm: np.ndarray) -> np.ndarray:
    """O2 A-band (~762 nm) and a weak CO2 band (~2010 nm)."""
    return (
        0.15 * np.exp(-(((wavelength_nm - 762.0) / 3.0) ** 2))
        + 0.05 * np.exp(-(((wavelength_nm - 2010.0) / 40.0) ** 2))
    )


def atmospheric_transmission(
    wavelength_nm: np.ndarray, conditions: AtmosphericConditions | None = None
) -> np.ndarray:
    """
    ``ATMOSPHERIC_TRANSMISSION(lambda)`` -- clear-sky *global* (direct +
    diffuse) transmittance for the given wavelength grid.

    Ozone, water vapour and mixed-gas extinction are genuine absorption --
    that energy is gone, so it is applied as plain Beer-Lambert attenuation.
    Rayleigh and aerosol extinction are *scattering*: the direct beam is
    attenuated the same way, but ``diffuse_recovery_fraction`` of that
    scattered light still reaches the ground as diffuse skylight rather
    than being lost, which is what keeps the modelled UV/blue transmission
    physically realistic instead of implausibly small.

    Terrestrial PV simulation must not assume extraterrestrial UV reaches
    the module unchanged; this function is the explicit filter applied by
    ``terrestrial_spectrum`` between the AM0 reference and the module plane.
    """
    conditions = conditions or AtmosphericConditions()
    airmass = relative_airmass(conditions.solar_zenith_deg)
    wavelength_um = wavelength_nm / 1000.0

    tau_rayleigh = _rayleigh_optical_depth(wavelength_um, conditions.pressure_ratio)
    tau_aerosol = _aerosol_optical_depth(
        wavelength_nm, conditions.aerosol_optical_depth_500nm, conditions.angstrom_exponent
    )
    tau_ozone = _ozone_optical_depth(wavelength_nm, conditions.ozone_column_du)
    tau_water = _water_vapor_optical_depth(wavelength_nm, conditions.precipitable_water_cm)
    tau_mixed = _mixed_gas_optical_depth(wavelength_nm)

    transmission_absorption = np.exp(-(tau_ozone + tau_water + tau_mixed) * airmass)
    transmission_scatter_direct = np.exp(-(tau_rayleigh + tau_aerosol) * airmass)
    f = conditions.diffuse_recovery_fraction
    transmission_scatter_global = transmission_scatter_direct + f * (1.0 - transmission_scatter_direct)

    return np.clip(transmission_absorption * transmission_scatter_global, 0.0, 1.0)


def uv_available(spectrum: SolarSpectrum, conditions: AtmosphericConditions | None = None) -> np.ndarray:
    """``UV_AVAILABLE(lambda) = SOLAR_IRRADIANCE(lambda) * ATMOSPHERIC_TRANSMISSION(lambda)``."""
    transmission = atmospheric_transmission(spectrum.wavelength_nm, conditions)
    return spectrum.spectral_irradiance_w_m2_nm * transmission


def terrestrial_spectrum(
    wavelength_nm: np.ndarray | None = None,
    sun_temperature_k: float = SUN_SURFACE_TEMPERATURE_K,
    conditions: AtmosphericConditions | None = None,
) -> SolarSpectrum:
    """Convenience: extraterrestrial spectrum filtered through the atmosphere (stages 1+2)."""
    extraterrestrial = extraterrestrial_spectrum(wavelength_nm, sun_temperature_k)
    transmission = atmospheric_transmission(extraterrestrial.wavelength_nm, conditions)
    return SolarSpectrum(
        extraterrestrial.wavelength_nm,
        extraterrestrial.spectral_irradiance_w_m2_nm * transmission,
    )
