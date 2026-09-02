"""
Tandem (two-junction, series-connected) cell model (SilicaFlux spec items
12 and 13).

SUNLIGHT -> TOP CELL (preferentially absorbs higher-energy photons) ->
BOTTOM CELL (receives what the top cell didn't use) -> series-connected
two-terminal output.

A series-connected tandem's two subcells must carry the *same* current, so
its IV curve isn't just "add the two independent MPPs" -- it's built by
sweeping a shared operating current and summing each subcell's voltage at
that current (inverting each subcell's diode equation), which is the
standard, physically correct way to compute a two-terminal tandem's IV
curve and naturally penalises the whole device for current mismatch
between the subcells.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .constants import STC_TEMPERATURE_K
from .materials import PEROVSKITE_WIDEGAP, SILICON, PVMaterial
from .optics import absorber_absorption_fraction, compute_stack_optics, default_optical_stack
from .recombination import RecombinationState, carrier_lifetime
from .response import dark_saturation_current_density_a_m2, internal_quantum_efficiency
from .spectrum import SolarSpectrum, integrate_band


@dataclass
class TandemMaterial:
    top: PVMaterial
    bottom: PVMaterial
    interlayer_transmittance: float = 0.97  # tunnel-junction / recombination-layer parasitic loss


DEFAULT_TANDEM = TandemMaterial(top=PEROVSKITE_WIDEGAP, bottom=SILICON)


@dataclass
class SubcellResponse:
    eqe: np.ndarray
    iqe: np.ndarray
    electrical_response_a_m2_nm: np.ndarray
    j_sc_a_m2: float
    recombination_state: RecombinationState


def _subcell_response(
    material: PVMaterial,
    wavelength_nm: np.ndarray,
    photon_flux: np.ndarray,
    entrance_fraction: np.ndarray,
    absorption_fraction: np.ndarray,
    temperature_k: float,
) -> SubcellResponse:
    from .constants import ELEMENTARY_CHARGE_C

    recomb = carrier_lifetime(material, temperature_k=temperature_k)
    iqe = internal_quantum_efficiency(material, wavelength_nm, recomb)
    eqe = np.clip(entrance_fraction * absorption_fraction * iqe, 0.0, 1.0)
    electrical_response = photon_flux * eqe * ELEMENTARY_CHARGE_C
    j_sc = integrate_band(electrical_response, wavelength_nm)
    return SubcellResponse(eqe=eqe, iqe=iqe, electrical_response_a_m2_nm=electrical_response, j_sc_a_m2=j_sc, recombination_state=recomb)


@dataclass
class TandemSpectralSplit:
    top: SubcellResponse
    bottom: SubcellResponse
    top_transmission_into_absorber: np.ndarray
    top_absorption_fraction: np.ndarray
    bottom_incident_fraction: np.ndarray
    bottom_absorption_fraction: np.ndarray


def tandem_spectral_split(
    tandem: TandemMaterial,
    wavelength_nm: np.ndarray,
    photon_flux: np.ndarray,
    temperature_k: float = STC_TEMPERATURE_K,
    top_ar_index: float = 1.38,
    top_ar_thickness_nm: float = 100.0,
    top_encapsulant_uv_blocking: bool = False,
    bottom_back_reflectance: float = 0.9,
) -> TandemSpectralSplit:
    """
    Splits the incident spectrum between the top and bottom subcells.

    The top cell's front stack defaults to a UV-transparent encapsulant --
    tandem front sheets are, in practice, specifically chosen not to
    squander the wide-gap top cell's blue/UV response the way a
    conventional UV-blocking EVA would.
    """
    top_stack = default_optical_stack(top_ar_index, top_ar_thickness_nm, top_encapsulant_uv_blocking)
    _R_top, top_T, _A_top = compute_stack_optics(top_stack.layers, tandem.top, wavelength_nm)
    top_absorption_fraction = absorber_absorption_fraction(tandem.top, wavelength_nm)

    remaining_after_top = top_T * (1.0 - top_absorption_fraction)
    bottom_incident_fraction = remaining_after_top * tandem.interlayer_transmittance
    bottom_absorption_fraction = absorber_absorption_fraction(tandem.bottom, wavelength_nm, back_reflectance=bottom_back_reflectance)

    top_response = _subcell_response(tandem.top, wavelength_nm, photon_flux, top_T, top_absorption_fraction, temperature_k)
    bottom_response = _subcell_response(
        tandem.bottom, wavelength_nm, photon_flux, bottom_incident_fraction, bottom_absorption_fraction, temperature_k
    )

    return TandemSpectralSplit(
        top=top_response,
        bottom=bottom_response,
        top_transmission_into_absorber=top_T,
        top_absorption_fraction=top_absorption_fraction,
        bottom_incident_fraction=bottom_incident_fraction,
        bottom_absorption_fraction=bottom_absorption_fraction,
    )


@dataclass
class CurrentMatchingResult:
    i_top_a_m2: float
    i_bottom_a_m2: float
    i_matched_a_m2: float
    current_matching_error: float


def tandem_current_matching(split: TandemSpectralSplit) -> CurrentMatchingResult:
    """``I_MATCHED = MIN(I_TOP, I_BOTTOM)``; ``CURRENT_MATCHING_ERROR`` reports the relative mismatch."""
    i_top, i_bottom = split.top.j_sc_a_m2, split.bottom.j_sc_a_m2
    i_matched = min(i_top, i_bottom)
    larger = max(i_top, i_bottom)
    error = abs(i_top - i_bottom) / larger if larger > 0 else 0.0
    return CurrentMatchingResult(i_top_a_m2=i_top, i_bottom_a_m2=i_bottom, i_matched_a_m2=i_matched, current_matching_error=error)


# --------------------------------------------------------------------------
# Series-connected two-terminal IV sweep
# --------------------------------------------------------------------------
def _diode_voltage_at_current(i_a_m2: np.ndarray, j_sc_a_m2: float, j0_a_m2: float, n: float, v_t: float) -> np.ndarray:
    if j0_a_m2 <= 0.0 or j_sc_a_m2 <= 0.0:
        return np.zeros_like(i_a_m2)
    ratio = np.clip((j_sc_a_m2 - i_a_m2 + j0_a_m2) / j0_a_m2, 1e-300, None)
    return np.clip(n * v_t * np.log(ratio), 0.0, None)


@dataclass
class TandemDeviceResult:
    i_mp_a_m2: float
    v_mp_v: float
    p_mp_w_m2: float
    v_oc_v: float
    current_matching: CurrentMatchingResult


def tandem_device_operating_point(
    split: TandemSpectralSplit, tandem: TandemMaterial, temperature_k: float = STC_TEMPERATURE_K, n_points: int = 400
) -> TandemDeviceResult:
    """Series-connected tandem IV sweep: for each shared current, sum each subcell's voltage at that current, then find the MPP."""
    from .constants import BOLTZMANN_CONSTANT_EV_K

    matching = tandem_current_matching(split)
    v_t = BOLTZMANN_CONSTANT_EV_K * temperature_k

    j0_top = dark_saturation_current_density_a_m2(tandem.top, temperature_k)
    j0_bottom = dark_saturation_current_density_a_m2(tandem.bottom, temperature_k)

    i_max = matching.i_matched_a_m2
    if i_max <= 0.0:
        return TandemDeviceResult(0.0, 0.0, 0.0, 0.0, matching)

    currents = np.linspace(0.0, i_max * 0.999, n_points)
    v_top = _diode_voltage_at_current(currents, split.top.j_sc_a_m2, j0_top, tandem.top.ideality_factor, v_t)
    v_bottom = _diode_voltage_at_current(currents, split.bottom.j_sc_a_m2, j0_bottom, tandem.bottom.ideality_factor, v_t)
    v_device = v_top + v_bottom
    p_device = currents * v_device

    best_idx = int(np.argmax(p_device))
    v_oc = float(v_top[0] + v_bottom[0]) if len(v_top) else 0.0
    # Voc proper is the open-circuit (I=0) sum; recompute exactly at I=0 for accuracy.
    v_oc = float(
        _diode_voltage_at_current(np.array([0.0]), split.top.j_sc_a_m2, j0_top, tandem.top.ideality_factor, v_t)[0]
        + _diode_voltage_at_current(np.array([0.0]), split.bottom.j_sc_a_m2, j0_bottom, tandem.bottom.ideality_factor, v_t)[0]
    )

    return TandemDeviceResult(
        i_mp_a_m2=float(currents[best_idx]),
        v_mp_v=float(v_device[best_idx]),
        p_mp_w_m2=float(p_device[best_idx]),
        v_oc_v=v_oc,
        current_matching=matching,
    )


# --------------------------------------------------------------------------
# TANDEM_OPTIMISER (item 12)
# --------------------------------------------------------------------------
@dataclass
class TandemOptimisationResult:
    top_bandgap_eV: float
    top_thickness_nm: float
    device: TandemDeviceResult
    device_efficiency: float
    baseline_device: TandemDeviceResult
    baseline_device_efficiency: float
    efficiency_improvement_pct: float


def tandem_optimiser(
    spectrum: SolarSpectrum,
    base_tandem: TandemMaterial = DEFAULT_TANDEM,
    temperature_k: float = STC_TEMPERATURE_K,
    top_bandgap_range_eV: tuple[float, float] = (1.5, 2.0),
    n_bandgap_steps: int = 11,
    top_thickness_range_nm: tuple[float, float] = (200.0, 800.0),
    n_thickness_steps: int = 7,
) -> TandemOptimisationResult:
    """
    Deterministic grid search over top-cell bandgap and thickness,
    maximising total two-terminal device power while the series-connected
    IV sweep (``tandem_device_operating_point``) naturally penalises
    current mismatch between subcells.
    """
    from .photon import photon_flux as compute_photon_flux

    wavelength_nm = spectrum.wavelength_nm
    photon_flux_arr = compute_photon_flux(spectrum)

    def evaluate(top_bandgap_eV: float, top_thickness_nm: float) -> TandemDeviceResult:
        top_material = replace(base_tandem.top, bandgap_eV=top_bandgap_eV, thickness_nm=top_thickness_nm)
        tandem = replace(base_tandem, top=top_material)
        split = tandem_spectral_split(tandem, wavelength_nm, photon_flux_arr, temperature_k)
        return tandem_device_operating_point(split, tandem, temperature_k)

    baseline_device = evaluate(base_tandem.top.bandgap_eV, base_tandem.top.thickness_nm)
    baseline_efficiency = baseline_device.p_mp_w_m2 / spectrum.total_irradiance_w_m2 if spectrum.total_irradiance_w_m2 > 0 else 0.0

    bandgaps = np.linspace(*top_bandgap_range_eV, n_bandgap_steps)
    thicknesses = np.linspace(*top_thickness_range_nm, n_thickness_steps)

    best_p = -np.inf
    best = (base_tandem.top.bandgap_eV, base_tandem.top.thickness_nm, baseline_device)

    for eg in bandgaps:
        for th in thicknesses:
            device = evaluate(float(eg), float(th))
            if device.p_mp_w_m2 > best_p:
                best_p = device.p_mp_w_m2
                best = (float(eg), float(th), device)

    best_eg, best_th, best_device = best
    best_efficiency = best_device.p_mp_w_m2 / spectrum.total_irradiance_w_m2 if spectrum.total_irradiance_w_m2 > 0 else 0.0
    improvement_pct = (
        100.0 * (best_efficiency - baseline_efficiency) / baseline_efficiency if baseline_efficiency > 0 else 0.0
    )

    return TandemOptimisationResult(
        top_bandgap_eV=best_eg,
        top_thickness_nm=best_th,
        device=best_device,
        device_efficiency=best_efficiency,
        baseline_device=baseline_device,
        baseline_device_efficiency=baseline_efficiency,
        efficiency_improvement_pct=improvement_pct,
    )
