"""
Spectral response and UV-to-electricity conversion (SilicaFlux spec items
9 and 10).

EQE(lambda) = optical absorption fraction * internal quantum efficiency,
where IQE folds in both the recombination model's bulk collection
efficiency (``recombination.py``) and a wavelength-resolved surface-
recombination penalty: UV photons are absorbed within tens of nanometres
of the front surface (see ``materials.absorption_coefficient_cm``'s deep-UV
boost), so a poorly-passivated front surface disproportionately kills UV
response even when the bulk material could easily use those photons.

The single-junction operating point (Voc, Vmp, fill factor) is solved
exactly from the ideal single-diode equation via the Lambert-W closed form,
using the *actual* simulated short-circuit current density -- so
temperature and material choices feed back into Voc/efficiency through
real physics (Varshni bandgap shift -> dark saturation current -> Voc),
not a hard-coded percentage.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import lambertw

from .constants import BOLTZMANN_CONSTANT_EV_K, ELEMENTARY_CHARGE_C, SPECTRAL_BANDS_NM, STC_TEMPERATURE_K
from .materials import PVMaterial, absorption_coefficient_cm, bandgap_at_temperature_eV
from .optics import absorber_absorption_fraction
from .recombination import RecombinationState, carrier_lifetime
from .spectrum import integrate_band

# Uniform illustrative dark-saturation-current prefactor (A/cm^2). Combined
# with Eg(T)/(n*Vt) via the exponential below, this lands single-junction
# Voc values for these materials' bandgaps in the realistic 0.5-1.1 V range
# at STC -- see materials.py's module docstring for the same honesty caveat.
_J00_REFERENCE_A_CM2 = 1.0e8


# --------------------------------------------------------------------------
# EQE / IQE (item 9)
# --------------------------------------------------------------------------
def surface_loss_fraction(
    material: PVMaterial, wavelength_nm: np.ndarray, recombination_state: RecombinationState
) -> np.ndarray:
    """
    Phenomenological surface-recombination penalty, built from two
    dimensionless factors:

    * ``reach_probability(lambda) = exp(-1 / (alpha(lambda) * L))`` --
      carriers are generated at a characteristic depth ``1/alpha`` from the
      front surface; comparing that depth to the material's diffusion
      length ``L`` (from ``recombination.py``) gives the probability they
      random-walk back to the surface at all before being collected or
      recombining in the bulk. Shallow generation (large alpha, i.e. UV)
      -> depth << L -> reach probability -> 1. Deep generation (small
      alpha, i.e. NIR) -> depth >> L -> reach probability -> 0.
    * ``sink_strength = (S*L/D) / (1 + S*L/D)`` -- the standard
      dimensionless Biot-like group ``S*L/D`` that determines how
      "sink-like" the surface boundary condition is (0 = perfectly
      reflecting/inert, saturating to 1 = perfect recombining sink),
      independent of wavelength.

    ``surface_loss_fraction = reach_probability * sink_strength``. This is
    a simplified stand-in for the exact (considerably more involved)
    minority-carrier diffusion boundary-value solution for EQE (e.g.
    Hovel's classic emitter-region formula), chosen because it reproduces
    the same qualitative, well-established behaviour -- UV response is
    disproportionately vulnerable to front-surface recombination, NIR
    response is not -- while staying closed-form and numerically robust.
    """
    alpha_cm = np.maximum(absorption_coefficient_cm(material, wavelength_nm), 1e-12)
    diffusion_length_cm = recombination_state.diffusion_length_cm
    reach_probability = np.exp(-1.0 / (alpha_cm * diffusion_length_cm))

    biot = material.surface_recomb_velocity_cm_s * diffusion_length_cm / material.diffusion_coefficient_cm2_s
    sink_strength = biot / (1.0 + biot)

    return reach_probability * sink_strength


def internal_quantum_efficiency(
    material: PVMaterial, wavelength_nm: np.ndarray, recombination_state: RecombinationState
) -> np.ndarray:
    """``IQE(lambda)`` = QE ceiling * bulk collection efficiency * (1 - surface loss)."""
    surface_loss = surface_loss_fraction(material, wavelength_nm, recombination_state)
    iqe = material.quantum_efficiency * recombination_state.bulk_collection_efficiency * (1.0 - surface_loss)
    return np.clip(iqe, 0.0, 1.0)


def external_quantum_efficiency(
    material: PVMaterial,
    wavelength_nm: np.ndarray,
    optical_transmission: np.ndarray,
    recombination_state: RecombinationState,
    back_reflectance: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    ``EQE(lambda) = A(lambda) * IQE(lambda)`` where ``A(lambda)`` is the
    absorption fraction of light that made it past the front-surface optics
    (``optical_transmission``, i.e. ``T(lambda)`` from ``optics.py``) and
    into the absorber.

    Returns ``(eqe, iqe, optical_absorption_fraction)``.
    """
    absorption_fraction = absorber_absorption_fraction(material, wavelength_nm, back_reflectance)
    optical_absorption_fraction = np.clip(optical_transmission * absorption_fraction, 0.0, 1.0)
    iqe = internal_quantum_efficiency(material, wavelength_nm, recombination_state)
    eqe = np.clip(optical_absorption_fraction * iqe, 0.0, 1.0)
    return eqe, iqe, optical_absorption_fraction


def electrical_response_a_m2_nm(photon_flux: np.ndarray, eqe: np.ndarray) -> np.ndarray:
    """``ELECTRICAL_RESPONSE(lambda) = PHOTON_FLUX(lambda) * EQE(lambda) * q``, A/(m^2 nm)."""
    return photon_flux * eqe * ELEMENTARY_CHARGE_C


# --------------------------------------------------------------------------
# Single-diode operating point (feeds V_EFFECTIVE, item 10)
# --------------------------------------------------------------------------
@dataclass
class OperatingPoint:
    j_sc_a_m2: float
    v_oc_v: float
    v_mp_v: float
    j_mp_a_m2: float
    p_mp_w_m2: float
    fill_factor: float


def dark_saturation_current_density_a_m2(material: PVMaterial, temperature_k: float) -> float:
    """J0(T), via Eg(T) (Varshni) driving the standard exponential dark-current temperature dependence."""
    eg_t = bandgap_at_temperature_eV(material, temperature_k)
    v_t = BOLTZMANN_CONSTANT_EV_K * temperature_k  # kT/q, in volts
    j0_a_cm2 = _J00_REFERENCE_A_CM2 * np.exp(-eg_t / (material.ideality_factor * v_t))
    return j0_a_cm2 * 1e4  # cm^-2 -> m^-2


def solve_operating_point(j_sc_a_m2: float, material: PVMaterial, temperature_k: float = STC_TEMPERATURE_K) -> OperatingPoint:
    """
    Exact ideal single-diode (R_s=0, R_sh=infinity) maximum-power-point
    solution via the Lambert-W closed form:

        I(V) = I_L - I_0*(exp(V/(n*Vt)) - 1)
        V_mp = n*Vt*(W(e*(1 + I_L/I_0)) - 1)

    (a standard textbook result for the ideal diode equation's maximum
    power point), with ``material.temperature_coefficient`` then applied as
    a secondary correction to V_mp.

    The ideal-diode-plus-Varshni-bandgap-shift treatment above already
    reproduces roughly half of a real device's temperature sensitivity (via
    Voc falling as Eg(T) shrinks and J0(T) rises); only *half* of the
    material's literature-typical ``temperature_coefficient`` (%/K) is
    applied here, as a stand-in for the remainder (fill-factor and series-
    resistance effects the ideal-diode model does not capture). This keeps
    ``temperature_coefficient`` genuinely influential -- rather than a
    decorative field -- without double-counting the whole effect twice.
    """
    j0 = dark_saturation_current_density_a_m2(material, temperature_k)
    v_t = BOLTZMANN_CONSTANT_EV_K * temperature_k
    n = material.ideality_factor

    if j_sc_a_m2 <= 0.0 or j0 <= 0.0:
        return OperatingPoint(j_sc_a_m2=max(j_sc_a_m2, 0.0), v_oc_v=0.0, v_mp_v=0.0, j_mp_a_m2=0.0, p_mp_w_m2=0.0, fill_factor=0.0)

    v_oc = n * v_t * np.log1p(j_sc_a_m2 / j0)

    w = np.real(lambertw(np.e * (1.0 + j_sc_a_m2 / j0)))
    v_mp = n * v_t * (w - 1.0)
    v_mp = float(np.clip(v_mp, 0.0, v_oc))

    residual_temp_correction = 1.0 + 0.5 * material.temperature_coefficient * (temperature_k - STC_TEMPERATURE_K)
    v_mp = float(np.clip(v_mp * max(residual_temp_correction, 0.0), 0.0, v_oc))

    j_mp = j_sc_a_m2 - j0 * (np.expm1(v_mp / (n * v_t)))
    j_mp = float(max(j_mp, 0.0))
    p_mp = v_mp * j_mp

    fill_factor = p_mp / (v_oc * j_sc_a_m2) if v_oc * j_sc_a_m2 > 0 else 0.0

    return OperatingPoint(
        j_sc_a_m2=j_sc_a_m2, v_oc_v=float(v_oc), v_mp_v=v_mp, j_mp_a_m2=j_mp, p_mp_w_m2=p_mp,
        fill_factor=float(np.clip(fill_factor, 0.0, 1.0)),
    )


def v_effective(wavelength_nm: np.ndarray, operating_point: OperatingPoint) -> np.ndarray:
    """
    ``V_EFFECTIVE(lambda)``.

    A series-connected single-junction device delivers all its harvested
    carriers into one shared terminal voltage -- there is no such thing as
    a wavelength-dependent operating voltage for a real cell. The physically
    correct way to build a *spectral* power decomposition is therefore to
    assign every wavelength interval's photocurrent the device's actual
    operating voltage (V_mp), which is exactly what is done here; the
    function is wavelength-invariant by construction; it's kept as a
    function of ``lambda`` only to match the spec's call signature and
    because a future multi-terminal/tandem architecture could return
    something wavelength-resolved instead.
    """
    return np.full_like(np.asarray(wavelength_nm, dtype=float), operating_point.v_mp_v)


# --------------------------------------------------------------------------
# UV-to-electricity conversion (item 10)
# --------------------------------------------------------------------------
def power_contribution_w_m2_nm(photon_flux: np.ndarray, eqe: np.ndarray, v_eff: np.ndarray) -> np.ndarray:
    """``POWER_CONTRIBUTION(lambda) = PHOTON_FLUX * EQE * q * V_EFFECTIVE``, W/(m^2 nm)."""
    return photon_flux * eqe * ELEMENTARY_CHARGE_C * v_eff


@dataclass
class SpectralResponseResult:
    eqe: np.ndarray
    iqe: np.ndarray
    optical_absorption_fraction: np.ndarray
    surface_loss_fraction: np.ndarray
    electrical_response_a_m2_nm: np.ndarray
    power_contribution_w_m2_nm: np.ndarray
    operating_point: OperatingPoint
    recombination_state: RecombinationState
    p_uv_w_m2: float
    p_visible_w_m2: float
    p_nir_w_m2: float
    p_total_w_m2: float
    uv_power_fraction: float


def compute_spectral_response(
    material: PVMaterial,
    wavelength_nm: np.ndarray,
    photon_flux: np.ndarray,
    optical_transmission: np.ndarray,
    temperature_k: float = STC_TEMPERATURE_K,
    delta_n_cm3: float = 1e15,
    back_reflectance: float = 0.0,
) -> SpectralResponseResult:
    """Orchestrates items 9+10: full spectral response through to P_UV/P_VISIBLE/P_NIR/P_TOTAL."""
    recomb_state = carrier_lifetime(material, delta_n_cm3=delta_n_cm3, temperature_k=temperature_k)
    eqe, iqe, optical_absorption = external_quantum_efficiency(
        material, wavelength_nm, optical_transmission, recomb_state, back_reflectance
    )
    surface_loss = surface_loss_fraction(material, wavelength_nm, recomb_state)
    electrical_response = electrical_response_a_m2_nm(photon_flux, eqe)

    j_sc_a_m2 = integrate_band(electrical_response, wavelength_nm)
    operating_point = solve_operating_point(j_sc_a_m2, material, temperature_k)
    v_eff = v_effective(wavelength_nm, operating_point)

    power_contribution = power_contribution_w_m2_nm(photon_flux, eqe, v_eff)

    p_uv = integrate_band(power_contribution, wavelength_nm, *SPECTRAL_BANDS_NM["UV"])
    p_visible = integrate_band(power_contribution, wavelength_nm, *SPECTRAL_BANDS_NM["VISIBLE"])
    p_nir = integrate_band(power_contribution, wavelength_nm, *SPECTRAL_BANDS_NM["NIR"])
    p_total = integrate_band(power_contribution, wavelength_nm)
    uv_power_fraction = p_uv / p_total if p_total > 0 else 0.0

    return SpectralResponseResult(
        eqe=eqe,
        iqe=iqe,
        optical_absorption_fraction=optical_absorption,
        surface_loss_fraction=surface_loss,
        electrical_response_a_m2_nm=electrical_response,
        power_contribution_w_m2_nm=power_contribution,
        operating_point=operating_point,
        recombination_state=recomb_state,
        p_uv_w_m2=p_uv,
        p_visible_w_m2=p_visible,
        p_nir_w_m2=p_nir,
        p_total_w_m2=p_total,
        uv_power_fraction=uv_power_fraction,
    )
