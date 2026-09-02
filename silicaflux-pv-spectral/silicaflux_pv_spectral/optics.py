"""
Front-surface optics: transfer-matrix multilayer stack, the UV absorption
engine, and the front-surface reflection optimiser.

SilicaFlux spec items 6, 7 and 8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .constants import SPECTRAL_BANDS_NM
from .materials import PVMaterial, absorption_coefficient_cm, extinction_coefficient, refractive_index
from .spectrum import SolarSpectrum, integrate_band

ComplexIndexFunc = Callable[[np.ndarray], np.ndarray]


# --------------------------------------------------------------------------
# OPTICAL_STACK (item 7)
# --------------------------------------------------------------------------
@dataclass
class Layer:
    name: str
    n_func: ComplexIndexFunc   # real refractive index n(lambda_nm)
    k_func: ComplexIndexFunc   # extinction coefficient k(lambda_nm)
    thickness_nm: float


@dataclass
class OpticalStack:
    layers: list[Layer] = field(default_factory=list)
    incident_index: float = 1.0  # air


def ar_coating_layer(refractive_index_val: float = 1.38, thickness_nm: float = 100.0, name: str = "AR_COATING") -> Layer:
    """Single-layer anti-reflection coating (e.g. MgF2, n~1.38). Index/thickness are the optimiser's free parameters."""
    return Layer(
        name=name,
        n_func=lambda wl: np.full(np.shape(np.asarray(wl, dtype=float)), refractive_index_val),
        k_func=lambda wl: np.zeros(np.shape(np.asarray(wl, dtype=float))),
        thickness_nm=thickness_nm,
    )


def encapsulant_layer(
    uv_blocking: bool = True,
    thickness_nm: float = 450_000.0,
    cutoff_nm: float = 370.0,
    k_max: float = 0.05,
    name: str | None = None,
) -> Layer:
    """
    EVA-family encapsulant layer.

    Conventional EVA is formulated with a UV-stabiliser package that makes
    it strongly absorbing below ~360-380 nm -- real modules with standard
    EVA lose essentially all response in that window regardless of what the
    semiconductor underneath could do. Setting ``uv_blocking=False`` models
    a UV-transparent encapsulant (POE, or UV-transmitting EVA formulations
    increasingly used for bifacial/UV-response modules): this is one of the
    single highest-leverage, physically real levers for improving a
    module's UV response, and is exactly the kind of material choice this
    engine's optimiser is meant to surface.
    """
    n_func = lambda wl: np.full(np.shape(np.asarray(wl, dtype=float)), 1.5)
    if uv_blocking:
        def k_func(wl: np.ndarray) -> np.ndarray:
            wl = np.asarray(wl, dtype=float)
            width_nm = 8.0
            return k_max / (1.0 + np.exp((wl - cutoff_nm) / width_nm))
        default_name = "EVA_UV_BLOCKING"
    else:
        def k_func(wl: np.ndarray) -> np.ndarray:
            return np.zeros(np.shape(np.asarray(wl, dtype=float)))
        default_name = "POE_UV_TRANSPARENT"
    return Layer(name=name or default_name, n_func=n_func, k_func=k_func, thickness_nm=thickness_nm)


def default_optical_stack(
    ar_index: float = 1.38,
    ar_thickness_nm: float = 100.0,
    encapsulant_uv_blocking: bool = True,
    encapsulant_thickness_nm: float = 450_000.0,
) -> OpticalStack:
    """SUNLIGHT -> AR coating -> encapsulant -> (textured surface, handled separately) -> semiconductor."""
    return OpticalStack(
        layers=[
            ar_coating_layer(ar_index, ar_thickness_nm),
            encapsulant_layer(encapsulant_uv_blocking, encapsulant_thickness_nm),
        ]
    )


# --------------------------------------------------------------------------
# Transfer-matrix (characteristic matrix) method, normal incidence
# --------------------------------------------------------------------------
_ComplexMat = tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]  # (m00, m01, m10, m11), each complex array


def _identity_matrix(shape: tuple[int, ...]) -> _ComplexMat:
    ones = np.ones(shape, dtype=complex)
    zeros = np.zeros(shape, dtype=complex)
    return ones, zeros, zeros, ones


def _layer_characteristic_matrix(n_complex: np.ndarray, thickness_nm: float, wavelength_nm: np.ndarray) -> _ComplexMat:
    delta = 2.0 * np.pi * n_complex * thickness_nm / wavelength_nm
    cos_d, sin_d = np.cos(delta), np.sin(delta)
    m00 = cos_d
    m01 = 1j * sin_d / n_complex
    m10 = 1j * n_complex * sin_d
    m11 = cos_d
    return m00, m01, m10, m11


def _mat_mul(a: _ComplexMat, b: _ComplexMat) -> _ComplexMat:
    a00, a01, a10, a11 = a
    b00, b01, b10, b11 = b
    return (
        a00 * b00 + a01 * b10,
        a00 * b01 + a01 * b11,
        a10 * b00 + a11 * b10,
        a10 * b01 + a11 * b11,
    )


def compute_stack_optics(
    layers: list[Layer],
    semiconductor: PVMaterial,
    wavelength_nm: np.ndarray,
    texture_enabled: bool = True,
    texture_reflectance_factor: float = 0.3,
    incident_index: float = 1.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    R(lambda), T(lambda), A(lambda) for the multilayer stack terminating on
    a semi-infinite absorbing semiconductor substrate, via the standard
    characteristic-matrix (transfer-matrix) method at normal incidence.

    T is the fraction of incident power transmitted *into* the
    semiconductor at that interface (the ``OPTICAL_TRANSMISSION(lambda)``
    consumed by ``uv_absorption.py``'s Beer-Lambert absorption calculation
    within the absorber's finite thickness); A is any parasitic absorption
    within the stack itself (e.g. a UV-blocking encapsulant). R+T+A=1 by
    construction (checked in tests).

    ``texture_enabled`` applies an empirical broadband reflectance
    reduction representing pyramidal/random surface texturing's light
    trapping (real silicon texturing cuts front reflectance from ~35%
    planar to ~10-11% textured) -- full ray-tracing is out of scope here,
    so the recovered reflection is folded into T, which keeps R+T+A=1 exact.
    """
    wavelength_nm = np.asarray(wavelength_nm, dtype=float)
    shape = wavelength_nm.shape
    n_inc = complex(incident_index)

    matrix = _identity_matrix(shape)
    for layer in layers:
        n_complex = layer.n_func(wavelength_nm) - 1j * layer.k_func(wavelength_nm)
        layer_matrix = _layer_characteristic_matrix(n_complex, layer.thickness_nm, wavelength_nm)
        matrix = _mat_mul(matrix, layer_matrix)

    n_sub = refractive_index(semiconductor, wavelength_nm) - 1j * extinction_coefficient(semiconductor, wavelength_nm)
    m00, m01, m10, m11 = matrix
    b = m00 + m01 * n_sub
    c = m10 + m11 * n_sub

    r = (n_inc * b - c) / (n_inc * b + c)
    t = (2.0 * n_inc) / (n_inc * b + c)

    R = np.clip(np.abs(r) ** 2, 0.0, 1.0)
    T = np.clip((n_sub.real / n_inc.real) * np.abs(t) ** 2, 0.0, 1.0 - R)
    A = np.clip(1.0 - R - T, 0.0, 1.0)

    if texture_enabled:
        recovered = R * (1.0 - texture_reflectance_factor)
        R = R * texture_reflectance_factor
        T = T + recovered

    return R, T, A


# --------------------------------------------------------------------------
# UV absorption engine (item 6)
# --------------------------------------------------------------------------
def absorber_absorption_fraction(
    material: PVMaterial, wavelength_nm: np.ndarray, back_reflectance: float = 0.0
) -> np.ndarray:
    """
    ``A(lambda) = 1 - exp(-alpha(lambda) * thickness)``, the Beer-Lambert
    absorption fraction of light that has already entered the absorber.

    ``back_reflectance`` (0-1) optionally models a back reflector: light
    that survives the first pass gets a second chance to be absorbed after
    bouncing off the rear of the cell (a standard two-pass light-trapping
    approximation; higher-order bounces are neglected).
    """
    alpha_cm = absorption_coefficient_cm(material, wavelength_nm)
    thickness_cm = material.thickness_nm * 1e-7
    transmitted_single_pass = np.exp(-alpha_cm * thickness_cm)
    absorbed_single_pass = 1.0 - transmitted_single_pass
    if back_reflectance <= 0.0:
        return absorbed_single_pass
    absorbed_second_pass = back_reflectance * transmitted_single_pass * absorbed_single_pass
    return np.clip(absorbed_single_pass + absorbed_second_pass, 0.0, 1.0)


def absorbed_photon_flux(
    photon_flux: np.ndarray,
    atmospheric_transmission: np.ndarray,
    optical_transmission: np.ndarray,
    absorption_fraction: np.ndarray,
) -> np.ndarray:
    """``ABSORBED_UV_PHOTONS(lambda) = PHOTON_FLUX * ATMOSPHERIC_TRANSMISSION * OPTICAL_TRANSMISSION * A(lambda)``."""
    return photon_flux * atmospheric_transmission * optical_transmission * absorption_fraction


def total_absorbed_uv(
    absorbed_flux: np.ndarray, wavelength_nm: np.ndarray, low_nm: float = 280.0, high_nm: float = 400.0
) -> float:
    """``TOTAL_ABSORBED_UV = integral(ABSORBED_UV_PHOTONS(lambda), 280nm, 400nm)``, photons/(s m^2)."""
    return integrate_band(absorbed_flux, wavelength_nm, low_nm, high_nm)


# --------------------------------------------------------------------------
# Front-surface reflection optimiser (item 8)
# --------------------------------------------------------------------------
@dataclass
class FrontSurfaceOptimisationResult:
    ar_index: float
    ar_thickness_nm: float
    uv_reflection_loss_w_m2: float
    visible_reflection_loss_w_m2: float
    nir_reflection_loss_w_m2: float
    total_optical_loss_w_m2: float
    baseline_ar_index: float
    baseline_ar_thickness_nm: float
    baseline_uv_reflection_loss_w_m2: float
    baseline_visible_reflection_loss_w_m2: float
    baseline_nir_reflection_loss_w_m2: float
    baseline_total_optical_loss_w_m2: float
    uv_loss_improvement_pct: float


def _band_reflection_losses(
    ar_index: float,
    ar_thickness_nm: float,
    material: PVMaterial,
    spectrum: SolarSpectrum,
    encapsulant_uv_blocking: bool,
    texture_enabled: bool,
) -> tuple[float, float, float]:
    stack = default_optical_stack(ar_index, ar_thickness_nm, encapsulant_uv_blocking)
    R, _T, _A = compute_stack_optics(stack.layers, material, spectrum.wavelength_nm, texture_enabled)
    reflected_power = R * spectrum.spectral_irradiance_w_m2_nm
    uv_loss = integrate_band(reflected_power, spectrum.wavelength_nm, *SPECTRAL_BANDS_NM["UV"])
    vis_loss = integrate_band(reflected_power, spectrum.wavelength_nm, *SPECTRAL_BANDS_NM["VISIBLE"])
    nir_loss = integrate_band(reflected_power, spectrum.wavelength_nm, *SPECTRAL_BANDS_NM["NIR"])
    return uv_loss, vis_loss, nir_loss


def optimise_front_surface(
    material: PVMaterial,
    spectrum: SolarSpectrum,
    encapsulant_uv_blocking: bool = True,
    texture_enabled: bool = True,
    ar_index_bounds: tuple[float, float] = (1.3, 2.2),
    ar_thickness_bounds_nm: tuple[float, float] = (30.0, 150.0),
    n_index_steps: int = 19,
    n_thickness_steps: int = 25,
    uv_weight: float = 3.0,
    visible_weight: float = 1.0,
    nir_weight: float = 0.3,
    catastrophic_loss_tolerance: float = 0.15,
) -> FrontSurfaceOptimisationResult:
    """
    ``OPTIMISE_FRONT_SURFACE()`` -- deterministic grid search over AR
    coating index and thickness.

    Objective: minimise a UV-weighted sum of band reflection losses,
    subject to a hard penalty if the visible or NIR loss would exceed
    ``catastrophic_loss_tolerance`` above the baseline single-layer AR
    coating -- i.e. "do not optimise UV performance at the expense of
    catastrophic losses elsewhere" is an explicit numerical constraint,
    not just a design intention. A deterministic grid (rather than a
    gradient/stochastic optimiser) is used because the parameter space is
    small (2-D) and this guarantees reproducible results.
    """
    baseline_ar_index, baseline_ar_thickness = 1.38, 100.0
    baseline_uv, baseline_vis, baseline_nir = _band_reflection_losses(
        baseline_ar_index, baseline_ar_thickness, material, spectrum, encapsulant_uv_blocking, texture_enabled
    )
    baseline_total = baseline_uv + baseline_vis + baseline_nir

    ar_indices = np.linspace(*ar_index_bounds, n_index_steps)
    ar_thicknesses = np.linspace(*ar_thickness_bounds_nm, n_thickness_steps)

    best_objective = np.inf
    best = (baseline_ar_index, baseline_ar_thickness, baseline_uv, baseline_vis, baseline_nir)

    vis_ceiling = baseline_vis * (1.0 + catastrophic_loss_tolerance)
    nir_ceiling = baseline_nir * (1.0 + catastrophic_loss_tolerance)

    for idx in ar_indices:
        for thickness in ar_thicknesses:
            uv_l, vis_l, nir_l = _band_reflection_losses(
                float(idx), float(thickness), material, spectrum, encapsulant_uv_blocking, texture_enabled
            )
            penalty = 0.0
            if vis_l > vis_ceiling:
                penalty += 1e4 * (vis_l - vis_ceiling) ** 2
            if nir_l > nir_ceiling:
                penalty += 1e4 * (nir_l - nir_ceiling) ** 2
            objective = uv_weight * uv_l + visible_weight * vis_l + nir_weight * nir_l + penalty
            if objective < best_objective:
                best_objective = objective
                best = (float(idx), float(thickness), uv_l, vis_l, nir_l)

    best_idx, best_thickness, uv_l, vis_l, nir_l = best
    total = uv_l + vis_l + nir_l
    improvement_pct = 100.0 * (baseline_uv - uv_l) / baseline_uv if baseline_uv > 0 else 0.0

    return FrontSurfaceOptimisationResult(
        ar_index=best_idx,
        ar_thickness_nm=best_thickness,
        uv_reflection_loss_w_m2=uv_l,
        visible_reflection_loss_w_m2=vis_l,
        nir_reflection_loss_w_m2=nir_l,
        total_optical_loss_w_m2=total,
        baseline_ar_index=baseline_ar_index,
        baseline_ar_thickness_nm=baseline_ar_thickness,
        baseline_uv_reflection_loss_w_m2=baseline_uv,
        baseline_visible_reflection_loss_w_m2=baseline_vis,
        baseline_nir_reflection_loss_w_m2=baseline_nir,
        baseline_total_optical_loss_w_m2=baseline_total,
        uv_loss_improvement_pct=improvement_pct,
    )
