"""
Carrier recombination model (SilicaFlux spec item 16).

Radiative, Shockley-Read-Hall (SRH), Auger and surface recombination are
combined via Matthiessen's rule into an effective carrier lifetime, which
sets the minority-carrier diffusion length and, from that, a bulk carrier
collection efficiency. ``response.py`` folds this bulk term together with
a wavelength-resolved surface-recombination penalty (carriers generated
right at the front surface -- which is exactly where UV photons are
absorbed -- are disproportionately lost to surface recombination) to build
``EQE(lambda)``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import STC_TEMPERATURE_K
from .materials import PVMaterial


@dataclass
class RecombinationState:
    tau_srh_ns: float
    tau_radiative_ns: float
    tau_auger_ns: float
    tau_surface_ns: float
    tau_effective_ns: float
    diffusion_length_cm: float
    bulk_collection_efficiency: float


def _srh_lifetime_ns(material: PVMaterial, temperature_k: float) -> float:
    """Simplified SRH lifetime temperature dependence, tau ~ (T/T_ref)^1.5 (illustrative)."""
    return material.srh_lifetime_ns * (temperature_k / STC_TEMPERATURE_K) ** 1.5


def _radiative_lifetime_ns(material: PVMaterial, delta_n_cm3: float) -> float:
    rate_per_s = material.radiative_coefficient_cm3_s * delta_n_cm3
    return 1e9 / rate_per_s if rate_per_s > 0 else np.inf


def _auger_lifetime_ns(material: PVMaterial, delta_n_cm3: float) -> float:
    rate_per_s = material.auger_coefficient_cm6_s * delta_n_cm3**2
    return 1e9 / rate_per_s if rate_per_s > 0 else np.inf


def _surface_lifetime_ns(material: PVMaterial) -> float:
    """Thin-slab, both-sided surface-recombination-limited lifetime: tau ~ thickness / (2*S)."""
    thickness_cm = material.thickness_nm * 1e-7
    return 1e9 * thickness_cm / (2.0 * material.surface_recomb_velocity_cm_s)


def carrier_lifetime(
    material: PVMaterial, delta_n_cm3: float = 1e15, temperature_k: float = STC_TEMPERATURE_K
) -> RecombinationState:
    """``CARRIER_LIFETIME`` -- Matthiessen's-rule combination of all recombination channels."""
    tau_srh = _srh_lifetime_ns(material, temperature_k)
    tau_rad = _radiative_lifetime_ns(material, delta_n_cm3)
    tau_auger = _auger_lifetime_ns(material, delta_n_cm3)
    tau_surface = _surface_lifetime_ns(material)

    inverse_sum = 1.0 / tau_srh + 1.0 / tau_rad + 1.0 / tau_auger + 1.0 / tau_surface
    tau_effective_ns = 1.0 / inverse_sum

    diffusion_length_cm = np.sqrt(material.diffusion_coefficient_cm2_s * tau_effective_ns * 1e-9)
    thickness_cm = material.thickness_nm * 1e-7
    bulk_collection_efficiency = float(np.clip(np.tanh(diffusion_length_cm / thickness_cm), 0.0, 1.0))

    return RecombinationState(
        tau_srh_ns=tau_srh,
        tau_radiative_ns=tau_rad,
        tau_auger_ns=tau_auger,
        tau_surface_ns=tau_surface,
        tau_effective_ns=tau_effective_ns,
        diffusion_length_cm=float(diffusion_length_cm),
        bulk_collection_efficiency=bulk_collection_efficiency,
    )
