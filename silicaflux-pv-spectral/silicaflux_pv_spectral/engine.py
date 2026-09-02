"""
The top-level SilicaFlux optimisation entry point (SilicaFlux spec items
18, 19 and 20): ``SILICAFLUX.PV.SPECTRAL.OPTIMISE(...)``, the ``RESULT``
struct, the ``NET_ENERGY_OUTPUT`` objective, and the baseline-vs-optimised
``SIMULATION_OUTPUT`` report.

On ``NET_ENERGY_OUTPUT`` (item 19): the spec's formula --

    NET_ENERGY_OUTPUT = OPTICAL_ABSORPTION * QUANTUM_EFFICIENCY *
        CARRIER_COLLECTION * ELECTRICAL_CONVERSION
        - THERMAL_LOSS - RECOMBINATION_LOSS - REFLECTION_LOSS - DEGRADATION_COST

-- is a qualitative statement of what should matter, not a dimensionally
literal recipe: the first (multiplicative) term is exactly how
``pipeline.PipelineResult.spectral_response.p_total_w_m2`` is already
computed (optical absorption x IQE x carrier collection x electrical
conversion, at the actual cell temperature), so subtracting
thermal/recombination/reflection loss *again* on top of it would double-
count effects already inside that number. This module therefore uses
``pipeline.py``'s own accounting: ``NET_ENERGY_OUTPUT = P_TOTAL -
DEGRADATION_COST`` (the one effect genuinely outside the instantaneous
physics calculation), and reports thermal/recombination/reflection/optical
loss as a diagnostic attribution breakdown -- exactly what "WHERE IS THE
ENERGY BEING LOST?" asks for -- rather than a second, double-counted
subtraction.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .degradation import annualise_power_w_m2
from .materials import PVMaterial
from .optics import OpticalStack, default_optical_stack, optimise_front_surface
from .pipeline import PipelineResult, run_pipeline
from .spectrum import SolarSpectrum
from .constants import (
    DEFAULT_PEAK_SUN_HOURS_PER_DAY,
    DEFAULT_PROJECT_LIFETIME_YEARS,
    SPECTRAL_BANDS_NM,
    STC_TEMPERATURE_K,
)
from .spectrum import integrate_band
from .tandem import DEFAULT_TANDEM, TandemMaterial, tandem_device_operating_point, tandem_optimiser, tandem_spectral_split


# --------------------------------------------------------------------------
# RESULT (item 18)
# --------------------------------------------------------------------------
@dataclass
class SilicaFluxResult:
    total_irradiance: float
    uv_irradiance: float
    visible_irradiance: float
    nir_irradiance: float

    absorbed_uv: float
    absorbed_visible: float
    absorbed_nir: float

    uv_power: float
    visible_power: float
    nir_power: float

    optical_loss: float
    thermal_loss: float
    recombination_loss: float

    efficiency: float
    degradation_rate: float

    optimised_parameters: dict
    predicted_energy_gain: float


def _band_absorbed_power(result: PipelineResult, band: str) -> float:
    low, high = SPECTRAL_BANDS_NM[band]
    absorbed_density = result.spectral_response.optical_absorption_fraction * result.spectrum.spectral_irradiance_w_m2_nm
    return integrate_band(absorbed_density, result.spectrum.wavelength_nm, low, high)


def _optimise_single_junction_front_surface(
    spectrum: SolarSpectrum,
    material: PVMaterial,
    baseline_stack: OpticalStack,
    ambient_temperature_k: float,
    wind_speed_m_s: float,
    project_lifetime_years: float,
    peak_sun_hours_per_day: float,
) -> tuple[PipelineResult, PipelineResult, dict]:
    baseline = run_pipeline(
        spectrum, material, optical_stack=baseline_stack, ambient_temperature_k=ambient_temperature_k,
        wind_speed_m_s=wind_speed_m_s, project_lifetime_years=project_lifetime_years,
        peak_sun_hours_per_day=peak_sun_hours_per_day,
    )

    best = None
    for encapsulant_uv_blocking in (True, False):
        fs_result = optimise_front_surface(material, baseline.spectrum, encapsulant_uv_blocking=encapsulant_uv_blocking)
        stack = default_optical_stack(fs_result.ar_index, fs_result.ar_thickness_nm, encapsulant_uv_blocking)
        candidate = run_pipeline(
            spectrum, material, optical_stack=stack, ambient_temperature_k=ambient_temperature_k,
            wind_speed_m_s=wind_speed_m_s, project_lifetime_years=project_lifetime_years,
            peak_sun_hours_per_day=peak_sun_hours_per_day,
        )
        if best is None or candidate.net_energy_output_w_m2 > best[0].net_energy_output_w_m2:
            best = (candidate, stack, fs_result, encapsulant_uv_blocking)

    optimised, optimised_stack, fs_result, uv_blocking_choice = best
    optimised_parameters = {
        "ar_index": fs_result.ar_index,
        "ar_thickness_nm": fs_result.ar_thickness_nm,
        "encapsulant_uv_blocking": uv_blocking_choice,
        "texture_enabled": True,
    }
    return baseline, optimised, optimised_parameters


def optimise(
    spectrum: SolarSpectrum,
    material: PVMaterial,
    optical_stack: OpticalStack | None = None,
    temperature: float = STC_TEMPERATURE_K,
    architecture: str = "single_junction",
    wind_speed_m_s: float = 1.0,
    project_lifetime_years: float = DEFAULT_PROJECT_LIFETIME_YEARS,
    peak_sun_hours_per_day: float = DEFAULT_PEAK_SUN_HOURS_PER_DAY,
) -> SilicaFluxResult:
    """``SILICAFLUX.PV.SPECTRAL.OPTIMISE(spectrum, material, optical_stack, temperature, architecture)``."""
    if architecture == "tandem":
        return _optimise_tandem(spectrum, temperature, wind_speed_m_s)

    baseline_stack = optical_stack or default_optical_stack()
    baseline, optimised, optimised_parameters = _optimise_single_junction_front_surface(
        spectrum, material, baseline_stack, temperature, wind_speed_m_s, project_lifetime_years, peak_sun_hours_per_day
    )

    predicted_energy_gain = optimised.net_energy_output_w_m2 - baseline.net_energy_output_w_m2

    return SilicaFluxResult(
        total_irradiance=optimised.spectrum.total_irradiance_w_m2,
        uv_irradiance=optimised.spectrum.in_band("UV"),
        visible_irradiance=optimised.spectrum.in_band("VISIBLE"),
        nir_irradiance=optimised.spectrum.in_band("NIR"),
        absorbed_uv=_band_absorbed_power(optimised, "UV"),
        absorbed_visible=_band_absorbed_power(optimised, "VISIBLE"),
        absorbed_nir=_band_absorbed_power(optimised, "NIR"),
        uv_power=optimised.spectral_response.p_uv_w_m2,
        visible_power=optimised.spectral_response.p_visible_w_m2,
        nir_power=optimised.spectral_response.p_nir_w_m2,
        optical_loss=optimised.optical_loss_w_m2,
        thermal_loss=optimised.thermal_loss_w_m2,
        recombination_loss=optimised.recombination_loss_w_m2,
        efficiency=optimised.efficiency,
        degradation_rate=optimised.degradation.degradation_rate_per_year if optimised.degradation else 0.0,
        optimised_parameters=optimised_parameters,
        predicted_energy_gain=predicted_energy_gain,
    )


def _band_tandem_absorbed_power(split, wavelength_nm, spectral_irradiance_w_m2_nm, band_low: float, band_high: float) -> float:
    """
    Power (W/m^2) absorbed by *either* tandem subcell within a band (top +
    bottom, combined). Uses spectral irradiance directly rather than photon
    flux -- ``flux(lambda) * photon_energy(lambda) == irradiance(lambda)``
    by construction, so this is the power-domain equivalent of
    ``photon.photon_flux`` weighted absorption, and keeps ``absorbed_uv``
    etc. in the same W/m^2 units as the single-junction path's
    the single-junction path's ``_band_absorbed_power``.
    """
    top_absorbed = integrate_band(
        spectral_irradiance_w_m2_nm * split.top_transmission_into_absorber * split.top_absorption_fraction,
        wavelength_nm, band_low, band_high,
    )
    bottom_absorbed = integrate_band(
        spectral_irradiance_w_m2_nm * split.bottom_incident_fraction * split.bottom_absorption_fraction,
        wavelength_nm, band_low, band_high,
    )
    return top_absorbed + bottom_absorbed


def _band_tandem_power(
    split, wavelength_nm, tandem: TandemMaterial, temperature_k: float, i_mp_a_m2: float, band_low: float, band_high: float
) -> float:
    """
    Combined top+bottom electrical power contribution within a band.

    A series-connected tandem's two subcells carry the *same* device
    current I_mp -- top and bottom currents do **not** simply add (that
    would be the parallel-circuit case). Each subcell instead contributes
    ``V_subcell(I_mp) * I_mp`` to the total device power (which sums
    exactly to P_mp, since ``V_top(I_mp) + V_bottom(I_mp) == V_device``);
    that per-subcell power is then split across bands in proportion to the
    subcell's own normalised spectral current shape -- a good
    approximation as long as each subcell's relative spectral response
    does not change much between I_sc and I_mp.
    """
    from .constants import BOLTZMANN_CONSTANT_EV_K
    from .response import dark_saturation_current_density_a_m2
    from .tandem import _diode_voltage_at_current

    v_t = BOLTZMANN_CONSTANT_EV_K * temperature_k
    j0_top = dark_saturation_current_density_a_m2(tandem.top, temperature_k)
    j0_bottom = dark_saturation_current_density_a_m2(tandem.bottom, temperature_k)
    i_arr = np.array([i_mp_a_m2])

    v_top = float(_diode_voltage_at_current(i_arr, split.top.j_sc_a_m2, j0_top, tandem.top.ideality_factor, v_t)[0])
    v_bottom = float(_diode_voltage_at_current(i_arr, split.bottom.j_sc_a_m2, j0_bottom, tandem.bottom.ideality_factor, v_t)[0])

    p_top_total = v_top * i_mp_a_m2
    p_bottom_total = v_bottom * i_mp_a_m2

    top_band_fraction = (
        integrate_band(split.top.electrical_response_a_m2_nm, wavelength_nm, band_low, band_high) / split.top.j_sc_a_m2
        if split.top.j_sc_a_m2 > 0 else 0.0
    )
    bottom_band_fraction = (
        integrate_band(split.bottom.electrical_response_a_m2_nm, wavelength_nm, band_low, band_high) / split.bottom.j_sc_a_m2
        if split.bottom.j_sc_a_m2 > 0 else 0.0
    )

    return p_top_total * top_band_fraction + p_bottom_total * bottom_band_fraction


def _optimise_tandem(spectrum: SolarSpectrum, temperature: float, wind_speed_m_s: float) -> SilicaFluxResult:
    from dataclasses import replace

    from .photon import photon_flux as compute_photon_flux
    from .thermal import compute_thermal_state

    thermal_state = compute_thermal_state(temperature, spectrum.total_irradiance_w_m2, wind_speed_m_s)
    flux = compute_photon_flux(spectrum)

    baseline_split = tandem_spectral_split(DEFAULT_TANDEM, spectrum.wavelength_nm, flux, thermal_state.cell_temperature_k)
    baseline_device = tandem_device_operating_point(baseline_split, DEFAULT_TANDEM, thermal_state.cell_temperature_k)

    tandem_result = tandem_optimiser(spectrum, DEFAULT_TANDEM, thermal_state.cell_temperature_k)

    optimised_top = replace(
        DEFAULT_TANDEM.top, bandgap_eV=tandem_result.top_bandgap_eV, thickness_nm=tandem_result.top_thickness_nm
    )
    optimised_tandem = replace(DEFAULT_TANDEM, top=optimised_top)
    optimised_split = tandem_spectral_split(optimised_tandem, spectrum.wavelength_nm, flux, thermal_state.cell_temperature_k)

    device_efficiency = tandem_result.device.p_mp_w_m2 / spectrum.total_irradiance_w_m2 if spectrum.total_irradiance_w_m2 > 0 else 0.0

    optimised_parameters = {
        "architecture": "tandem",
        "top_bandgap_eV": tandem_result.top_bandgap_eV,
        "top_thickness_nm": tandem_result.top_thickness_nm,
        "current_matching_error": tandem_result.device.current_matching.current_matching_error,
    }

    predicted_energy_gain = tandem_result.device.p_mp_w_m2 - baseline_device.p_mp_w_m2

    uv_low, uv_high = SPECTRAL_BANDS_NM["UV"]
    vis_low, vis_high = SPECTRAL_BANDS_NM["VISIBLE"]
    nir_low, nir_high = SPECTRAL_BANDS_NM["NIR"]

    return SilicaFluxResult(
        total_irradiance=spectrum.total_irradiance_w_m2,
        uv_irradiance=spectrum.in_band("UV"),
        visible_irradiance=spectrum.in_band("VISIBLE"),
        nir_irradiance=spectrum.in_band("NIR"),
        absorbed_uv=_band_tandem_absorbed_power(optimised_split, spectrum.wavelength_nm, spectrum.spectral_irradiance_w_m2_nm, uv_low, uv_high),
        absorbed_visible=_band_tandem_absorbed_power(optimised_split, spectrum.wavelength_nm, spectrum.spectral_irradiance_w_m2_nm, vis_low, vis_high),
        absorbed_nir=_band_tandem_absorbed_power(optimised_split, spectrum.wavelength_nm, spectrum.spectral_irradiance_w_m2_nm, nir_low, nir_high),
        uv_power=_band_tandem_power(
            optimised_split, spectrum.wavelength_nm, optimised_tandem, thermal_state.cell_temperature_k,
            tandem_result.device.i_mp_a_m2, uv_low, uv_high,
        ),
        visible_power=_band_tandem_power(
            optimised_split, spectrum.wavelength_nm, optimised_tandem, thermal_state.cell_temperature_k,
            tandem_result.device.i_mp_a_m2, vis_low, vis_high,
        ),
        nir_power=_band_tandem_power(
            optimised_split, spectrum.wavelength_nm, optimised_tandem, thermal_state.cell_temperature_k,
            tandem_result.device.i_mp_a_m2, nir_low, nir_high,
        ),
        optical_loss=0.0,  # not decomposed for the tandem path in this version
        thermal_loss=0.0,
        recombination_loss=0.0,
        efficiency=device_efficiency,
        degradation_rate=0.0,
        optimised_parameters=optimised_parameters,
        predicted_energy_gain=predicted_energy_gain,
    )


# --------------------------------------------------------------------------
# SIMULATION OUTPUT (item 20)
# --------------------------------------------------------------------------
@dataclass
class SimulationOutput:
    BASELINE_EFFICIENCY: float
    OPTIMISED_EFFICIENCY: float
    BASELINE_UV_RESPONSE: float
    OPTIMISED_UV_RESPONSE: float
    BASELINE_UV_POWER: float
    OPTIMISED_UV_POWER: float
    ANNUAL_ENERGY_BASELINE: float
    ANNUAL_ENERGY_OPTIMISED: float
    UV_LOSS: float
    OPTICAL_LOSS: float
    THERMAL_LOSS: float
    RECOMBINATION_LOSS: float
    DEGRADATION_LOSS: float


def generate_simulation_output(
    spectrum: SolarSpectrum,
    material: PVMaterial,
    optical_stack: OpticalStack | None = None,
    temperature: float = STC_TEMPERATURE_K,
    wind_speed_m_s: float = 1.0,
    project_lifetime_years: float = DEFAULT_PROJECT_LIFETIME_YEARS,
    peak_sun_hours_per_day: float = DEFAULT_PEAK_SUN_HOURS_PER_DAY,
) -> SimulationOutput:
    """Baseline-vs-optimised machine-readable comparison report (single-junction only)."""
    baseline_stack = optical_stack or default_optical_stack()
    baseline, optimised, _params = _optimise_single_junction_front_surface(
        spectrum, material, baseline_stack, temperature, wind_speed_m_s, project_lifetime_years, peak_sun_hours_per_day
    )

    uv_low, uv_high = SPECTRAL_BANDS_NM["UV"]
    optimised_uv_loss = optimised.spectrum.in_band("UV") - optimised.spectral_response.p_uv_w_m2

    return SimulationOutput(
        BASELINE_EFFICIENCY=baseline.efficiency,
        OPTIMISED_EFFICIENCY=optimised.efficiency,
        BASELINE_UV_RESPONSE=baseline.spectral_response.uv_power_fraction,
        OPTIMISED_UV_RESPONSE=optimised.spectral_response.uv_power_fraction,
        BASELINE_UV_POWER=baseline.spectral_response.p_uv_w_m2,
        OPTIMISED_UV_POWER=optimised.spectral_response.p_uv_w_m2,
        ANNUAL_ENERGY_BASELINE=annualise_power_w_m2(baseline.net_energy_output_w_m2, peak_sun_hours_per_day),
        ANNUAL_ENERGY_OPTIMISED=annualise_power_w_m2(optimised.net_energy_output_w_m2, peak_sun_hours_per_day),
        UV_LOSS=optimised_uv_loss,
        OPTICAL_LOSS=optimised.optical_loss_w_m2,
        THERMAL_LOSS=optimised.thermal_loss_w_m2,
        RECOMBINATION_LOSS=optimised.recombination_loss_w_m2,
        DEGRADATION_LOSS=optimised.degradation.lifetime_energy_loss_w_h_m2 if optimised.degradation else 0.0,
    )


# --------------------------------------------------------------------------
# SILICAFLUX.PV.SPECTRAL.OPTIMISE dotted-namespace call syntax (item 18)
# --------------------------------------------------------------------------
class _SpectralNamespace:
    OPTIMISE = staticmethod(optimise)


class _PVNamespace:
    SPECTRAL = _SpectralNamespace()


class SILICAFLUX:
    PV = _PVNamespace()
