"""
UV degradation model (SilicaFlux spec item 14).

UV dose, temperature, material stability and encapsulant stability combine
into an Arrhenius-scaled annual degradation rate; a standard linear
degradation curve (the industry-conventional "X%/year linear degradation"
warranty model) then turns that into a lifetime energy loss. This lets the
optimiser weigh ``SHORT_TERM_UV_GAIN`` (more power today, from a design
change that lets more UV reach/be absorbed by the cell) against
``LONG_TERM_UV_DEGRADATION`` (that same extra UV dose can accelerate
material/encapsulant degradation) -- the two do not automatically point the
same way.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import (
    BOLTZMANN_CONSTANT_EV_K,
    DEFAULT_PEAK_SUN_HOURS_PER_DAY,
    DEFAULT_PROJECT_LIFETIME_YEARS,
    STC_TEMPERATURE_K,
)
from .materials import PVMaterial


@dataclass
class DegradationParameters:
    activation_energy_eV: float = 0.7
    rate_prefactor_per_year: float = 4.0e-3  # degradation rate at reference UV dose & temperature
    reference_uv_irradiance_w_m2: float = 40.0  # roughly a clear-sky terrestrial UV band irradiance
    uv_intensity_exponent: float = 1.0
    reference_temperature_k: float = STC_TEMPERATURE_K


def degradation_rate_per_year(
    uv_irradiance_w_m2: float,
    temperature_k: float,
    material: PVMaterial,
    encapsulant_stability_factor: float = 1.0,
    params: DegradationParameters | None = None,
) -> float:
    """
    ``DEGRADATION_RATE`` -- fractional performance loss per year.

    Arrhenius temperature scaling relative to the reference condition,
    a (by default linear) power-law dependence on UV dose rate, and
    inversely proportional to material/encapsulant stability (a more
    UV-fragile material or a UV-transparent-but-less-stable encapsulant
    degrades faster for the same UV exposure).
    """
    params = params or DegradationParameters()
    arrhenius_factor = np.exp(
        -params.activation_energy_eV / BOLTZMANN_CONSTANT_EV_K * (1.0 / temperature_k - 1.0 / params.reference_temperature_k)
    )
    uv_ratio = max(uv_irradiance_w_m2, 0.0) / params.reference_uv_irradiance_w_m2
    dose_factor = uv_ratio**params.uv_intensity_exponent

    combined_stability = max(material.material_stability_factor * encapsulant_stability_factor, 1e-6)
    rate = params.rate_prefactor_per_year * arrhenius_factor * dose_factor / combined_stability
    return float(max(rate, 0.0))


@dataclass
class DegradationResult:
    uv_irradiance_w_m2: float
    degradation_rate_per_year: float
    annual_energy_w_h_m2_by_year: np.ndarray
    lifetime_energy_w_h_m2: float
    lifetime_energy_loss_w_h_m2: float
    end_of_life_performance_fraction: float


def evaluate_degradation(
    uv_irradiance_w_m2: float,
    temperature_k: float,
    material: PVMaterial,
    baseline_annual_energy_w_h_m2_yr: float,
    encapsulant_stability_factor: float = 1.0,
    params: DegradationParameters | None = None,
    project_lifetime_years: float = DEFAULT_PROJECT_LIFETIME_YEARS,
) -> DegradationResult:
    """Applies a standard linear degradation curve over the project lifetime and totals the lost energy."""
    rate = degradation_rate_per_year(uv_irradiance_w_m2, temperature_k, material, encapsulant_stability_factor, params)

    years = np.arange(1, int(round(project_lifetime_years)) + 1)
    performance_fraction = np.clip(1.0 - rate * years, 0.0, 1.0)
    annual_energy = baseline_annual_energy_w_h_m2_yr * performance_fraction

    lifetime_energy = float(np.sum(annual_energy))
    lifetime_no_degradation = baseline_annual_energy_w_h_m2_yr * len(years)
    lifetime_loss = lifetime_no_degradation - lifetime_energy
    end_of_life_fraction = float(performance_fraction[-1]) if len(performance_fraction) else 1.0

    return DegradationResult(
        uv_irradiance_w_m2=uv_irradiance_w_m2,
        degradation_rate_per_year=rate,
        annual_energy_w_h_m2_by_year=annual_energy,
        lifetime_energy_w_h_m2=lifetime_energy,
        lifetime_energy_loss_w_h_m2=lifetime_loss,
        end_of_life_performance_fraction=end_of_life_fraction,
    )


def annualise_power_w_m2(power_w_m2: float, peak_sun_hours_per_day: float = DEFAULT_PEAK_SUN_HOURS_PER_DAY) -> float:
    """Convert an instantaneous power density (W/m^2, at the reference irradiance the spectrum represents) to Wh/m^2/yr."""
    return power_w_m2 * peak_sun_hours_per_day * 365.0


@dataclass
class UVTradeoffResult:
    short_term_gain_w_h_m2_yr: float
    lifetime_energy_delta_w_h_m2: float
    net_lifetime_value_w_h_m2: float
    worth_it: bool


def evaluate_uv_tradeoff(baseline: DegradationResult, optimised: DegradationResult) -> UVTradeoffResult:
    """
    Compares the short-term annual energy gain of a UV-response
    improvement against its full lifetime consequence once any change in
    degradation rate (e.g. from a UV-transparent encapsulant admitting
    more UV dose) is taken into account.

    ``net_lifetime_value_w_h_m2`` is simply
    ``optimised.lifetime_energy_w_h_m2 - baseline.lifetime_energy_w_h_m2``
    -- can be negative even when the short-term gain is positive, if the
    accelerated degradation eats more energy than the extra UV response
    ever delivered.
    """
    short_term_gain = optimised.annual_energy_w_h_m2_by_year[0] - baseline.annual_energy_w_h_m2_by_year[0] if len(
        baseline.annual_energy_w_h_m2_by_year
    ) and len(optimised.annual_energy_w_h_m2_by_year) else 0.0
    lifetime_delta = optimised.lifetime_energy_w_h_m2 - baseline.lifetime_energy_w_h_m2

    return UVTradeoffResult(
        short_term_gain_w_h_m2_yr=float(short_term_gain),
        lifetime_energy_delta_w_h_m2=lifetime_delta,
        net_lifetime_value_w_h_m2=lifetime_delta,
        worth_it=lifetime_delta > 0.0,
    )
