"""
Cell thermal model (SilicaFlux spec item 15).

Cell temperature is computed from ambient temperature, irradiance and wind
speed via the Faiman (2008) heat-balance model -- a simple, widely used
(e.g. pvlib's default) energy-balance approximation:

    T_cell = T_ambient + irradiance / (U0 + U1 * wind_speed)

That temperature then genuinely propagates through the rest of the engine
rather than being a decoration: ``materials.bandgap_at_temperature_eV``
(Varshni) shifts Eg(T), which shifts the dark saturation current and hence
Voc/efficiency in ``response.solve_operating_point``, and
``recombination.carrier_lifetime`` takes the same temperature for its SRH
lifetime term. This module supplies T_cell and packages a
machine-readable summary of how those downstream quantities moved.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import STC_TEMPERATURE_K
from .materials import PVMaterial, bandgap_at_temperature_eV
from .recombination import carrier_lifetime


@dataclass
class ThermalState:
    ambient_temperature_k: float
    irradiance_w_m2: float
    wind_speed_m_s: float
    cell_temperature_k: float
    delta_t_from_ambient_k: float


def cell_temperature_k(
    ambient_temperature_k: float,
    irradiance_w_m2: float,
    wind_speed_m_s: float = 1.0,
    u0_w_m2_k: float = 25.0,
    u1_w_m2_k_per_m_s: float = 6.84,
) -> float:
    """Faiman heat-balance cell temperature."""
    denom = max(u0_w_m2_k + u1_w_m2_k_per_m_s * wind_speed_m_s, 1e-6)
    return ambient_temperature_k + max(irradiance_w_m2, 0.0) / denom


def compute_thermal_state(
    ambient_temperature_k: float,
    irradiance_w_m2: float,
    wind_speed_m_s: float = 1.0,
    u0_w_m2_k: float = 25.0,
    u1_w_m2_k_per_m_s: float = 6.84,
) -> ThermalState:
    t_cell = cell_temperature_k(ambient_temperature_k, irradiance_w_m2, wind_speed_m_s, u0_w_m2_k, u1_w_m2_k_per_m_s)
    return ThermalState(
        ambient_temperature_k=ambient_temperature_k,
        irradiance_w_m2=irradiance_w_m2,
        wind_speed_m_s=wind_speed_m_s,
        cell_temperature_k=t_cell,
        delta_t_from_ambient_k=t_cell - ambient_temperature_k,
    )


@dataclass
class ThermalAdjustedMaterialSummary:
    temperature_k: float
    bandgap_eV: float
    bandgap_shift_ev_from_stc: float
    carrier_lifetime_ns: float
    carrier_lifetime_shift_pct_from_stc: float


def thermal_adjusted_material_summary(material: PVMaterial, temperature_k: float) -> ThermalAdjustedMaterialSummary:
    """Machine-readable view of how temperature has shifted this material's bandgap and carrier lifetime."""
    eg_t = bandgap_at_temperature_eV(material, temperature_k)
    eg_stc = bandgap_at_temperature_eV(material, STC_TEMPERATURE_K)

    lifetime_t = carrier_lifetime(material, temperature_k=temperature_k).tau_effective_ns
    lifetime_stc = carrier_lifetime(material, temperature_k=STC_TEMPERATURE_K).tau_effective_ns
    lifetime_shift_pct = 100.0 * (lifetime_t - lifetime_stc) / lifetime_stc if lifetime_stc > 0 else 0.0

    return ThermalAdjustedMaterialSummary(
        temperature_k=temperature_k,
        bandgap_eV=eg_t,
        bandgap_shift_ev_from_stc=eg_t - eg_stc,
        carrier_lifetime_ns=lifetime_t,
        carrier_lifetime_shift_pct_from_stc=lifetime_shift_pct,
    )
