"""
PV absorber material model (SilicaFlux spec items 4 and 5).

``PVMaterial`` carries everything downstream modules need: an absorption
coefficient model (Tauc-relation band edge + Urbach tail + a deep-UV
interband-transition boost, since this engine specifically cares about the
UV response), a Cauchy-dispersion refractive index, and the recombination /
diode parameters used by ``recombination.py``, ``response.py`` and
``thermal.py``.

Honesty note: the per-material numbers below are illustrative,
physically-motivated defaults representative of literature-typical orders
of magnitude for each material family. They are *not* fitted to any one
measured device or datasheet, and should be recalibrated against measured
data (absorption spectra, EQE, dark I-V) before being used for real
device-level predictions. What is guaranteed to be physically consistent
is the *model form* connecting them (Tauc relations, Varshni shift, Beer-
Lambert absorption, Matthiessen recombination, the diode equation) -- swap
in measured constants and the whole engine's outputs update accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from .constants import HC_EV_NM

AbsorptionKind = Literal["direct", "indirect"]


@dataclass
class PVMaterial:
    material_name: str

    # --- band structure / optical absorption (items 4, 5, 6) ---
    bandgap_eV: float
    absorption_kind: AbsorptionKind
    absorption_prefactor: float          # cm^-1 eV^-1/2 (direct) or cm^-1 eV^-2 (indirect)
    urbach_energy_eV: float              # sub-gap exponential-tail width
    uv_interband_onset_eV: float         # where deep-UV (E1/E2-like) transitions switch on
    uv_interband_max_cm: float = 1.0e6   # asymptotic UV absorption coefficient, cm^-1

    # --- optical dispersion ---
    refractive_index_n0: float = 3.0     # Cauchy n0
    refractive_index_b_um2: float = 0.03  # Cauchy B coefficient, micron^2

    # --- device geometry / baseline quantum efficiency ceiling ---
    thickness_nm: float = 1000.0
    quantum_efficiency: float = 0.95     # best-case internal QE ceiling (item 4's "quantum_efficiency")
    temperature_coefficient: float = -0.004  # fractional efficiency change per K (secondary correction)

    # --- recombination / transport (feeds recombination.py, response.py) ---
    surface_recomb_velocity_cm_s: float = 200.0
    diffusion_coefficient_cm2_s: float = 10.0
    srh_lifetime_ns: float = 1000.0
    radiative_coefficient_cm3_s: float = 1.0e-10
    auger_coefficient_cm6_s: float = 1.0e-30
    ideality_factor: float = 1.2

    # --- Varshni bandgap-temperature shift (item 15) ---
    varshni_alpha_ev_k: float = 4.73e-4
    varshni_beta_k: float = 636.0

    # --- UV/thermal degradation stability (item 14) ---
    material_stability_factor: float = 1.0  # 1.0 = reference stability, lower = more UV-fragile

    def __post_init__(self) -> None:
        if self.bandgap_eV <= 0:
            raise ValueError("bandgap_eV must be positive")
        if self.thickness_nm <= 0:
            raise ValueError("thickness_nm must be positive")


# --------------------------------------------------------------------------
# Absorption coefficient model
# --------------------------------------------------------------------------
def absorption_coefficient_cm(material: PVMaterial, wavelength_nm: np.ndarray) -> np.ndarray:
    """
    ``ABSORPTION_COEFFICIENT(lambda)`` in cm^-1.

    Above the band edge: Tauc relation (direct: sqrt(E-Eg); indirect:
    (E-Eg)^2). Below the band edge: an Urbach exponential tail, continuous
    with the band-edge value at E = Eg. A logistic "deep-UV boost" is added
    on top, representing the higher-energy interband transitions that push
    the absorption coefficient of essentially all semiconductors up toward
    ~1e5-1e6 cm^-1 in the UV regardless of the fundamental gap's character
    -- the dominant reason real cells absorb UV photons within tens of
    nanometres of the front surface.
    """
    wavelength_nm = np.asarray(wavelength_nm, dtype=float)
    e_eV = HC_EV_NM / wavelength_nm
    eg = material.bandgap_eV
    delta_e = e_eV - eg

    if material.absorption_kind == "direct":
        alpha_edge_above = material.absorption_prefactor * np.sqrt(np.clip(delta_e, 0.0, None))
    else:
        alpha_edge_above = material.absorption_prefactor * np.clip(delta_e, 0.0, None) ** 2

    alpha_at_gap = 1e-6  # cm^-1, effectively zero but keeps the Urbach tail well-defined at E=Eg
    alpha_urbach = alpha_at_gap * np.exp(delta_e / material.urbach_energy_eV)

    alpha_band = np.where(delta_e >= 0.0, np.maximum(alpha_edge_above, alpha_at_gap), alpha_urbach)

    # Width chosen so this term's tail decays much faster than the ~1e6 cm^-1
    # amplitude would otherwise let it contaminate near-band-edge/NIR values
    # (a naive 0.3 eV logistic width leaves a tail worth hundreds of cm^-1
    # even an eV below onset, which would swamp the true edge absorption).
    uv_boost_width_eV = 0.12
    logistic = 1.0 / (1.0 + np.exp(-(e_eV - material.uv_interband_onset_eV) / uv_boost_width_eV))
    alpha_uv_boost = material.uv_interband_max_cm * logistic

    return np.maximum(alpha_band, alpha_uv_boost)


def refractive_index(material: PVMaterial, wavelength_nm: np.ndarray) -> np.ndarray:
    """Cauchy dispersion: ``n(lambda) = n0 + B / lambda_um^2``, clipped to a sane physical range."""
    wavelength_um = np.asarray(wavelength_nm, dtype=float) / 1000.0
    n = material.refractive_index_n0 + material.refractive_index_b_um2 / wavelength_um**2
    return np.clip(n, 1.0, 6.0)


def extinction_coefficient(material: PVMaterial, wavelength_nm: np.ndarray) -> np.ndarray:
    """``k(lambda) = alpha(lambda) * lambda / (4*pi)``, the standard alpha<->k relation (consistent units, cm)."""
    alpha_cm = absorption_coefficient_cm(material, wavelength_nm)
    wavelength_cm = np.asarray(wavelength_nm, dtype=float) * 1e-7
    return alpha_cm * wavelength_cm / (4.0 * np.pi)


# --------------------------------------------------------------------------
# Bandgap filter (item 5)
# --------------------------------------------------------------------------
def photon_can_generate_carrier(photon_energy_eV: np.ndarray, bandgap_eV: float) -> np.ndarray:
    return np.asarray(photon_energy_eV) >= bandgap_eV


def lambda_cutoff_nm(bandgap_eV: float) -> float:
    return HC_EV_NM / bandgap_eV


# --------------------------------------------------------------------------
# Varshni bandgap-vs-temperature shift (feeds thermal.py)
# --------------------------------------------------------------------------
def bandgap_at_temperature_eV(material: PVMaterial, temperature_k: float) -> float:
    """``Eg(T) = Eg(0) - alpha*T^2/(T+beta)``, the standard Varshni (1967) relation."""
    eg0 = material.bandgap_eV
    alpha, beta = material.varshni_alpha_ev_k, material.varshni_beta_k
    # bandgap_eV is treated as the room-temperature (STC, 298.15 K) value, so
    # back out Eg(0) once and reuse it for any T.
    from .constants import STC_TEMPERATURE_K

    eg_at_0 = eg0 + alpha * STC_TEMPERATURE_K**2 / (STC_TEMPERATURE_K + beta)
    return eg_at_0 - alpha * temperature_k**2 / (temperature_k + beta)


# --------------------------------------------------------------------------
# Material library (item 4)
# --------------------------------------------------------------------------
SILICON = PVMaterial(
    material_name="SILICON",
    bandgap_eV=1.12,
    absorption_kind="indirect",
    absorption_prefactor=4000.0,
    urbach_energy_eV=0.05,
    uv_interband_onset_eV=3.4,
    refractive_index_n0=3.6,
    refractive_index_b_um2=0.03,
    thickness_nm=180_000.0,
    quantum_efficiency=0.97,
    temperature_coefficient=-0.0045,
    surface_recomb_velocity_cm_s=100.0,
    diffusion_coefficient_cm2_s=27.0,
    srh_lifetime_ns=100_000.0,
    radiative_coefficient_cm3_s=4.73e-15,
    auger_coefficient_cm6_s=1.0e-30,
    ideality_factor=1.1,
    varshni_alpha_ev_k=4.73e-4,
    varshni_beta_k=636.0,
    material_stability_factor=1.2,
)

PEROVSKITE = PVMaterial(
    material_name="PEROVSKITE",
    bandgap_eV=1.6,
    absorption_kind="direct",
    absorption_prefactor=3.0e4,
    urbach_energy_eV=0.015,
    uv_interband_onset_eV=3.5,
    refractive_index_n0=2.5,
    refractive_index_b_um2=0.02,
    thickness_nm=500.0,
    quantum_efficiency=0.95,
    temperature_coefficient=-0.0025,
    surface_recomb_velocity_cm_s=1000.0,
    diffusion_coefficient_cm2_s=1.0,
    srh_lifetime_ns=200.0,
    radiative_coefficient_cm3_s=1.0e-10,
    auger_coefficient_cm6_s=1.0e-29,
    ideality_factor=1.5,
    varshni_alpha_ev_k=5.0e-4,
    varshni_beta_k=300.0,
    material_stability_factor=0.5,  # perovskites are notably UV/moisture fragile
)

# Wide-gap perovskite variant used as the default tandem top cell.
PEROVSKITE_WIDEGAP = PVMaterial(
    material_name="PEROVSKITE_WIDEGAP",
    bandgap_eV=1.68,
    absorption_kind="direct",
    absorption_prefactor=3.0e4,
    urbach_energy_eV=0.018,
    uv_interband_onset_eV=3.6,
    refractive_index_n0=2.4,
    refractive_index_b_um2=0.02,
    thickness_nm=400.0,
    quantum_efficiency=0.93,
    temperature_coefficient=-0.0025,
    surface_recomb_velocity_cm_s=1200.0,
    diffusion_coefficient_cm2_s=0.8,
    srh_lifetime_ns=150.0,
    radiative_coefficient_cm3_s=1.0e-10,
    auger_coefficient_cm6_s=1.0e-29,
    ideality_factor=1.5,
    varshni_alpha_ev_k=5.0e-4,
    varshni_beta_k=300.0,
    material_stability_factor=0.45,
)

GALLIUM_ARSENIDE = PVMaterial(
    material_name="GALLIUM_ARSENIDE",
    bandgap_eV=1.42,
    absorption_kind="direct",
    absorption_prefactor=5.0e4,
    urbach_energy_eV=0.008,
    uv_interband_onset_eV=3.0,
    refractive_index_n0=3.3,
    refractive_index_b_um2=0.06,
    thickness_nm=2000.0,
    quantum_efficiency=0.98,
    temperature_coefficient=-0.0020,
    surface_recomb_velocity_cm_s=10.0,
    diffusion_coefficient_cm2_s=25.0,
    srh_lifetime_ns=1000.0,
    radiative_coefficient_cm3_s=7.2e-10,
    auger_coefficient_cm6_s=1.0e-30,
    ideality_factor=1.0,
    varshni_alpha_ev_k=5.41e-4,
    varshni_beta_k=204.0,
    material_stability_factor=1.1,
)

CADMIUM_TELLURIDE = PVMaterial(
    material_name="CADMIUM_TELLURIDE",
    bandgap_eV=1.5,
    absorption_kind="direct",
    absorption_prefactor=4.0e4,
    urbach_energy_eV=0.012,
    uv_interband_onset_eV=3.6,
    refractive_index_n0=2.7,
    refractive_index_b_um2=0.05,
    thickness_nm=3000.0,
    quantum_efficiency=0.90,
    temperature_coefficient=-0.0025,
    surface_recomb_velocity_cm_s=200.0,
    diffusion_coefficient_cm2_s=4.0,
    srh_lifetime_ns=20.0,
    radiative_coefficient_cm3_s=1.0e-10,
    auger_coefficient_cm6_s=1.0e-29,
    ideality_factor=1.4,
    varshni_alpha_ev_k=4.5e-4,
    varshni_beta_k=280.0,
    material_stability_factor=0.9,
)

CIGS = PVMaterial(
    material_name="CIGS",
    bandgap_eV=1.15,
    absorption_kind="direct",
    absorption_prefactor=3.0e4,
    urbach_energy_eV=0.02,
    uv_interband_onset_eV=3.3,
    refractive_index_n0=2.6,
    refractive_index_b_um2=0.04,
    thickness_nm=2000.0,
    quantum_efficiency=0.92,
    temperature_coefficient=-0.0036,
    surface_recomb_velocity_cm_s=500.0,
    diffusion_coefficient_cm2_s=2.0,
    srh_lifetime_ns=30.0,
    radiative_coefficient_cm3_s=1.0e-10,
    auger_coefficient_cm6_s=1.0e-29,
    ideality_factor=1.3,
    varshni_alpha_ev_k=4.5e-4,
    varshni_beta_k=280.0,
    material_stability_factor=0.85,
)

MATERIAL_LIBRARY: dict[str, PVMaterial] = {
    "SILICON": SILICON,
    "PEROVSKITE": PEROVSKITE,
    "PEROVSKITE_WIDEGAP": PEROVSKITE_WIDEGAP,
    "GALLIUM_ARSENIDE": GALLIUM_ARSENIDE,
    "CADMIUM_TELLURIDE": CADMIUM_TELLURIDE,
    "CIGS": CIGS,
    # "TANDEM" is not a single-junction PVMaterial -- see tandem.py's
    # TandemMaterial and DEFAULT_TANDEM, which pairs PEROVSKITE_WIDEGAP
    # (top) with SILICON (bottom).
}
