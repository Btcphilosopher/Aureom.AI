"""
Physical constants and spectral-grid / band definitions for the SilicaFlux
PV spectral engine.

All constants are 2019-redefinition SI exact values (``h``, ``c``, ``q``,
``k_B`` are defining constants of the SI and therefore have no uncertainty).
Everything downstream in this package is derived from these -- nothing is
independently re-fitted per module, so a single source of truth keeps the
whole engine numerically self-consistent.
"""

from __future__ import annotations

import numpy as np

# --------------------------------------------------------------------------
# Fundamental physical constants (SI)
# --------------------------------------------------------------------------
PLANCK_CONSTANT_J_S: float = 6.62607015e-34          # h  [J s]      (exact)
SPEED_OF_LIGHT_M_S: float = 2.99792458e8              # c  [m/s]      (exact)
ELEMENTARY_CHARGE_C: float = 1.602176634e-19          # q  [C]        (exact)
BOLTZMANN_CONSTANT_J_K: float = 1.380649e-23          # k_B [J/K]     (exact)
BOLTZMANN_CONSTANT_EV_K: float = BOLTZMANN_CONSTANT_J_K / ELEMENTARY_CHARGE_C  # ~8.617333e-5 eV/K

# hc/q expressed directly in eV*nm -- the standard photon-energy conversion
# constant. h*c/q * 1e9 evaluates to 1239.84198433... eV*nm; the literal
# value below matches the constant quoted in the SilicaFlux spec (item 5)
# to the precision given there.
HC_EV_NM: float = 1239.841984

# Convenience: recompute the same quantity from first principles so a test
# can assert the two never drift apart.
_HC_EV_NM_DERIVED: float = (
    PLANCK_CONSTANT_J_S * SPEED_OF_LIGHT_M_S / ELEMENTARY_CHARGE_C * 1e9
)

# --------------------------------------------------------------------------
# Sun / atmosphere reference values
# --------------------------------------------------------------------------
SUN_SURFACE_TEMPERATURE_K: float = 5778.0
SUN_RADIUS_M: float = 6.957e8
EARTH_SUN_DISTANCE_M: float = 1.496e11
SOLAR_CONSTANT_W_M2: float = 1361.0          # AM0, total-spectrum TOA irradiance
DOBSON_UNIT_MOLECULES_CM2: float = 2.6867e16  # 1 DU, standard atmospheric-chemistry conversion

# STC (Standard Test Conditions) reference used throughout the electrical
# and thermal models as the "25 degC" baseline operating point.
STC_TEMPERATURE_K: float = 298.15
STC_IRRADIANCE_W_M2: float = 1000.0

# Default reference exposure lifetime used by the degradation model (item 14)
# and annual-energy figures, matching the PV industry's standard 25-year
# warranty horizon.
DEFAULT_PROJECT_LIFETIME_YEARS: float = 25.0

# Standard "peak sun hours" equivalent used to translate an instantaneous
# W/m^2 result into an annual kWh/m^2/yr figure (typical mid-latitude
# average; callers may override).
DEFAULT_PEAK_SUN_HOURS_PER_DAY: float = 4.5

# --------------------------------------------------------------------------
# Wavelength grid (item 1)
# --------------------------------------------------------------------------
LAMBDA_MIN_NM: float = 280.0
LAMBDA_MAX_NM: float = 2500.0
DELTA_LAMBDA_NM: float = 1.0


def wavelength_grid_nm(
    lambda_min_nm: float = LAMBDA_MIN_NM,
    lambda_max_nm: float = LAMBDA_MAX_NM,
    delta_lambda_nm: float = DELTA_LAMBDA_NM,
) -> np.ndarray:
    """Return the default 1 nm-resolution wavelength grid, 280 -> 2500 nm inclusive."""
    n_steps = int(round((lambda_max_nm - lambda_min_nm) / delta_lambda_nm)) + 1
    return lambda_min_nm + np.arange(n_steps) * delta_lambda_nm


# --------------------------------------------------------------------------
# Spectral bands (item 3). Each entry is (low_nm, high_nm], boundaries
# configurable by constructing a new dict if a caller wants a different
# band convention -- these are the SilicaFlux defaults.
# --------------------------------------------------------------------------
SPECTRAL_BANDS_NM: dict[str, tuple[float, float]] = {
    "UVC": (100.0, 280.0),
    "UVB": (280.0, 315.0),
    "UVA": (315.0, 400.0),
    "UV": (280.0, 400.0),        # UVB + UVA -- the terrestrially-relevant UV window
    "VISIBLE": (400.0, 700.0),
    "NIR": (700.0, 2500.0),
}
