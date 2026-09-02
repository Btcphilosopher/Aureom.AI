"""
The full SilicaFlux computational pipeline (SilicaFlux spec item 24):

    SOLAR SPECTRUM -> ATMOSPHERIC MODEL -> PHOTON ENERGY -> OPTICAL STACK ->
    UV ABSORPTION -> VISIBLE ABSORPTION -> NIR ABSORPTION -> QUANTUM
    EFFICIENCY -> CARRIER GENERATION -> RECOMBINATION -> CARRIER COLLECTION
    -> ELECTRICAL CONVERSION -> THERMAL MODEL -> DEGRADATION MODEL

One clarification versus the diagram's literal top-to-bottom order: cell
temperature is resolved *before* the optical/electrical stages here,
because later stages (the diode equation's dark saturation current via
Varshni-shifted Eg(T), the recombination model's SRH lifetime) need T_cell
as an input, not an afterthought -- the diagram expresses a logical/
informational dependency, not a strict evaluation order. Machine learning
and the top-level SilicaFlux optimiser (items 17/18) are *not* pipeline
stages that run on every call -- they are search processes built on top of
repeated evaluations of this same pipeline function, kept as separate
modules (``ml_optimiser.py``, ``engine.py``) for modularity.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import DEFAULT_PEAK_SUN_HOURS_PER_DAY, DEFAULT_PROJECT_LIFETIME_YEARS, STC_TEMPERATURE_K
from .degradation import DegradationParameters, DegradationResult, annualise_power_w_m2, evaluate_degradation
from .materials import PVMaterial
from .optics import OpticalStack, compute_stack_optics, default_optical_stack
from .photon import photon_flux as compute_photon_flux
from .response import SpectralResponseResult, compute_spectral_response
from .spectrum import AtmosphericConditions, SolarSpectrum, atmospheric_transmission
from .thermal import ThermalState, compute_thermal_state


@dataclass
class PipelineResult:
    spectrum: SolarSpectrum
    atmospheric_transmission: np.ndarray
    photon_flux: np.ndarray
    optical_stack: OpticalStack
    reflection: np.ndarray
    optical_transmission: np.ndarray
    stack_parasitic_absorption: np.ndarray
    thermal_state: ThermalState
    spectral_response: SpectralResponseResult
    degradation: DegradationResult | None

    incident_power_w_m2: float
    absorbed_power_w_m2: float
    reflection_loss_w_m2: float
    parasitic_stack_loss_w_m2: float
    optical_loss_w_m2: float
    recombination_loss_w_m2: float
    thermal_loss_w_m2: float
    degradation_cost_w_m2: float

    net_energy_output_w_m2: float
    efficiency: float


def run_pipeline(
    spectrum: SolarSpectrum,
    material: PVMaterial,
    optical_stack: OpticalStack | None = None,
    ambient_temperature_k: float = STC_TEMPERATURE_K,
    wind_speed_m_s: float = 1.0,
    texture_enabled: bool = True,
    back_reflectance: float = 0.0,
    apply_atmosphere: bool = False,
    atmospheric_conditions: AtmosphericConditions | None = None,
    delta_n_cm3: float = 1e15,
    compute_degradation: bool = True,
    degradation_params: DegradationParameters | None = None,
    encapsulant_stability_factor: float = 1.0,
    project_lifetime_years: float = DEFAULT_PROJECT_LIFETIME_YEARS,
    peak_sun_hours_per_day: float = DEFAULT_PEAK_SUN_HOURS_PER_DAY,
) -> PipelineResult:
    """
    Runs the full stage chain and returns every intermediate quantity.

    ``spectrum`` is treated as the spectrum arriving at the module plane
    (i.e. already terrestrial) unless ``apply_atmosphere=True``, in which
    case it is treated as extraterrestrial (AM0) and the atmospheric model
    is applied here.
    """
    # --- Stage 1+2: solar spectrum, atmospheric model ---
    if apply_atmosphere:
        transmission = atmospheric_transmission(spectrum.wavelength_nm, atmospheric_conditions)
        working_spectrum = SolarSpectrum(spectrum.wavelength_nm, spectrum.spectral_irradiance_w_m2_nm * transmission)
    else:
        transmission = np.ones_like(spectrum.wavelength_nm)
        working_spectrum = spectrum

    incident_power = working_spectrum.total_irradiance_w_m2

    # --- Thermal model (resolved early -- see module docstring) ---
    thermal_state = compute_thermal_state(ambient_temperature_k, incident_power, wind_speed_m_s)
    t_cell = thermal_state.cell_temperature_k

    # --- Stage 3: photon energy / flux ---
    photon_flux_arr = compute_photon_flux(working_spectrum)

    # --- Stage 4: optical stack (front-surface R/T/A) ---
    stack = optical_stack or default_optical_stack()
    reflection, transmission_into_absorber, parasitic_absorption = compute_stack_optics(
        stack.layers, material, working_spectrum.wavelength_nm, texture_enabled=texture_enabled
    )

    # --- Stages 5-11: UV/visible/NIR absorption, QE, carrier generation,
    #     recombination, collection, electrical conversion ---
    spectral_response = compute_spectral_response(
        material,
        working_spectrum.wavelength_nm,
        photon_flux_arr,
        transmission_into_absorber,
        temperature_k=t_cell,
        delta_n_cm3=delta_n_cm3,
        back_reflectance=back_reflectance,
    )

    # --- Loss accounting ---
    reflection_loss = float(np.trapezoid(reflection * working_spectrum.spectral_irradiance_w_m2_nm, working_spectrum.wavelength_nm))
    parasitic_loss = float(
        np.trapezoid(parasitic_absorption * working_spectrum.spectral_irradiance_w_m2_nm, working_spectrum.wavelength_nm)
    )
    absorbed_power = float(
        np.trapezoid(
            spectral_response.optical_absorption_fraction * working_spectrum.spectral_irradiance_w_m2_nm,
            working_spectrum.wavelength_nm,
        )
    )
    optical_loss = max(incident_power - absorbed_power, 0.0)

    # Recombination loss: power lost purely to IQE < 1, holding optics and
    # operating voltage fixed (i.e. what P_total would be if internal
    # collection were perfect).
    from .constants import ELEMENTARY_CHARGE_C

    ideal_iqe_power_density = (
        photon_flux_arr * spectral_response.optical_absorption_fraction * ELEMENTARY_CHARGE_C
        * spectral_response.operating_point.v_mp_v
    )
    ideal_iqe_power = float(np.trapezoid(ideal_iqe_power_density, working_spectrum.wavelength_nm))
    recombination_loss = max(ideal_iqe_power - spectral_response.p_total_w_m2, 0.0)

    # Thermal loss: same stack/spectrum, re-evaluated at STC temperature,
    # compared against the actual (T_cell) result already computed above.
    # Positive = efficiency given up to running hotter than STC; can be
    # negative if the cell happens to be running cooler than STC.
    stc_response = compute_spectral_response(
        material, working_spectrum.wavelength_nm, photon_flux_arr, transmission_into_absorber,
        temperature_k=STC_TEMPERATURE_K, delta_n_cm3=delta_n_cm3, back_reflectance=back_reflectance,
    )
    thermal_loss = stc_response.p_total_w_m2 - spectral_response.p_total_w_m2

    # --- Degradation model ---
    degradation_result: DegradationResult | None = None
    degradation_cost = 0.0
    if compute_degradation:
        uv_irradiance = working_spectrum.in_band("UV")
        baseline_annual_energy = annualise_power_w_m2(spectral_response.p_total_w_m2, peak_sun_hours_per_day)
        degradation_result = evaluate_degradation(
            uv_irradiance, t_cell, material, baseline_annual_energy,
            encapsulant_stability_factor, degradation_params, project_lifetime_years,
        )
        degradation_cost = spectral_response.p_total_w_m2 * degradation_result.degradation_rate_per_year

    net_energy_output = spectral_response.p_total_w_m2 - degradation_cost
    efficiency = spectral_response.p_total_w_m2 / incident_power if incident_power > 0 else 0.0

    return PipelineResult(
        spectrum=working_spectrum,
        atmospheric_transmission=transmission,
        photon_flux=photon_flux_arr,
        optical_stack=stack,
        reflection=reflection,
        optical_transmission=transmission_into_absorber,
        stack_parasitic_absorption=parasitic_absorption,
        thermal_state=thermal_state,
        spectral_response=spectral_response,
        degradation=degradation_result,
        incident_power_w_m2=incident_power,
        absorbed_power_w_m2=absorbed_power,
        reflection_loss_w_m2=reflection_loss,
        parasitic_stack_loss_w_m2=parasitic_loss,
        optical_loss_w_m2=optical_loss,
        recombination_loss_w_m2=recombination_loss,
        thermal_loss_w_m2=thermal_loss,
        degradation_cost_w_m2=degradation_cost,
        net_energy_output_w_m2=net_energy_output,
        efficiency=efficiency,
    )
