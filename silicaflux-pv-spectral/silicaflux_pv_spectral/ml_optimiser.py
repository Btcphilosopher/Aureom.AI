"""
Machine-learning optimisation layer (SilicaFlux spec item 17).

Trains a closed-form (deterministic, no external ML framework needed --
mirroring how many small-data engineering surrogates are built) ridge-
regression model on the physics-generated parameter-sweep dataset, mapping
the spec's 12-feature vector::

    X = [wavelength, spectral_irradiance, temperature, bandgap, thickness,
         absorption, reflection, EQE, IQE, carrier_lifetime, degradation,
         optical_loss]

to the target ``P_TOTAL - DEGRADATION_COST - OPTICAL_LOSS``.

Honesty note on what this can and cannot do: most of the 12 features
(absorption, reflection, EQE, IQE, carrier_lifetime, degradation,
optical_loss) are themselves *outputs* of the physics pipeline, not free
design inputs -- computing them for a genuinely new candidate design still
requires running the real simulation. This surrogate is therefore used the
way such a model can be honestly used here: fit on the sweep's already-
physics-evaluated (X, y) pairs to (a) surface which physical levers most
strongly drive net energy (interpretable standardised coefficients), and
(b) re-rank the *already-evaluated* sweep to find the configuration the
model likes best. "The ML model must remain subordinate to physical
constraints" is implemented literally, not just asserted: the ML pick is
only ever reported if it is validated against real physics as at least as
good as the best directly-observed configuration in the sweep; otherwise
the optimiser falls back to that best observed (real, physics-simulated)
point.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .constants import ELEMENTARY_CHARGE_C
from .materials import PVMaterial
from .optics import default_optical_stack
from .parameter_sweep import SweepConfiguration
from .pipeline import PipelineResult, run_pipeline
from .spectrum import SolarSpectrum

FEATURE_NAMES: list[str] = [
    "wavelength_nm", "spectral_irradiance_w_m2_nm", "temperature_k", "bandgap_eV", "thickness_nm",
    "absorption_fraction", "reflection_fraction", "eqe", "iqe", "carrier_lifetime_ns",
    "degradation_rate_per_year", "optical_loss_fraction",
]


def _pipeline_for_configuration(
    base_material: PVMaterial,
    spectrum: SolarSpectrum,
    configuration: SweepConfiguration,
    texture_enabled: bool = True,
    encapsulant_uv_blocking: bool = False,
) -> tuple[PVMaterial, PipelineResult]:
    material = replace(
        base_material,
        bandgap_eV=configuration.bandgap_eV,
        thickness_nm=configuration.thickness_nm,
        srh_lifetime_ns=base_material.srh_lifetime_ns * configuration.lifetime_multiplier,
    )
    stack = default_optical_stack(ar_index=configuration.ar_index, encapsulant_uv_blocking=encapsulant_uv_blocking)
    result = run_pipeline(
        spectrum, material, optical_stack=stack, ambient_temperature_k=configuration.temperature_k,
        texture_enabled=texture_enabled,
    )
    return material, result


def extract_features(configuration: SweepConfiguration, result: PipelineResult) -> np.ndarray:
    wl = result.spectrum.wavelength_nm
    irr = result.spectrum.spectral_irradiance_w_m2_nm
    power_contribution = result.spectral_response.power_contribution_w_m2_nm

    total_power = float(np.trapezoid(power_contribution, wl))
    if total_power > 0:
        centroid_wavelength = float(np.trapezoid(power_contribution * wl, wl) / total_power)
    else:
        centroid_wavelength = float(np.mean(wl))
    irradiance_at_centroid = float(np.interp(centroid_wavelength, wl, irr))

    total_photon_flux = float(np.trapezoid(result.photon_flux, wl))
    avg_eqe = (
        result.spectral_response.operating_point.j_sc_a_m2 / (ELEMENTARY_CHARGE_C * total_photon_flux)
        if total_photon_flux > 0 else 0.0
    )
    avg_iqe = (
        float(np.trapezoid(result.spectral_response.iqe * result.photon_flux, wl) / total_photon_flux)
        if total_photon_flux > 0 else 0.0
    )

    absorption_fraction = result.absorbed_power_w_m2 / result.incident_power_w_m2 if result.incident_power_w_m2 > 0 else 0.0
    reflection_fraction = result.reflection_loss_w_m2 / result.incident_power_w_m2 if result.incident_power_w_m2 > 0 else 0.0
    optical_loss_fraction = result.optical_loss_w_m2 / result.incident_power_w_m2 if result.incident_power_w_m2 > 0 else 0.0
    carrier_lifetime_ns = result.spectral_response.recombination_state.tau_effective_ns
    degradation = result.degradation.degradation_rate_per_year if result.degradation else 0.0

    return np.array([
        centroid_wavelength, irradiance_at_centroid, configuration.temperature_k, configuration.bandgap_eV,
        configuration.thickness_nm, absorption_fraction, reflection_fraction, avg_eqe, avg_iqe,
        carrier_lifetime_ns, degradation, optical_loss_fraction,
    ])


def ml_target_w_m2(result: PipelineResult) -> float:
    """``P_TOTAL - DEGRADATION_COST - OPTICAL_LOSS`` -- deliberately double-penalises optical loss."""
    return result.spectral_response.p_total_w_m2 - result.degradation_cost_w_m2 - result.optical_loss_w_m2


@dataclass
class MLTrainingSet:
    feature_names: list[str]
    X: np.ndarray
    y: np.ndarray
    configurations: list[SweepConfiguration]


def build_training_set(
    base_material: PVMaterial,
    spectrum: SolarSpectrum,
    configurations: list[SweepConfiguration],
    texture_enabled: bool = True,
    encapsulant_uv_blocking: bool = False,
) -> MLTrainingSet:
    rows: list[np.ndarray] = []
    targets: list[float] = []
    for config in configurations:
        _material, result = _pipeline_for_configuration(base_material, spectrum, config, texture_enabled, encapsulant_uv_blocking)
        rows.append(extract_features(config, result))
        targets.append(ml_target_w_m2(result))
    return MLTrainingSet(
        feature_names=list(FEATURE_NAMES), X=np.vstack(rows), y=np.array(targets), configurations=list(configurations)
    )


# --------------------------------------------------------------------------
# Deterministic closed-form ridge regression surrogate
# --------------------------------------------------------------------------
class RidgeSurrogate:
    """Closed-form (normal-equation) ridge regression -- deterministic, no iterative training/randomness."""

    def __init__(self, alpha: float = 1.0):
        self.alpha = alpha
        self.mean_: np.ndarray | None = None
        self.std_: np.ndarray | None = None
        self.coef_: np.ndarray | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RidgeSurrogate":
        self.mean_ = X.mean(axis=0)
        self.std_ = X.std(axis=0)
        self.std_[self.std_ == 0] = 1.0
        x_norm = (X - self.mean_) / self.std_
        x_design = np.hstack([np.ones((x_norm.shape[0], 1)), x_norm])

        n_features = x_design.shape[1]
        penalty = np.eye(n_features) * self.alpha
        penalty[0, 0] = 0.0  # never regularise the bias term

        self.coef_ = np.linalg.solve(x_design.T @ x_design + penalty, x_design.T @ y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.coef_ is None or self.mean_ is None or self.std_ is None:
            raise RuntimeError("RidgeSurrogate.predict called before fit")
        x_norm = (X - self.mean_) / self.std_
        x_design = np.hstack([np.ones((x_norm.shape[0], 1)), x_norm])
        return x_design @ self.coef_

    def standardized_coefficients(self, feature_names: list[str]) -> dict[str, float]:
        if self.coef_ is None:
            raise RuntimeError("RidgeSurrogate.standardized_coefficients called before fit")
        return dict(zip(feature_names, self.coef_[1:].tolist()))


# --------------------------------------------------------------------------
# Top-level optimiser
# --------------------------------------------------------------------------
@dataclass
class MLOptimisationResult:
    training_set: MLTrainingSet
    feature_importance: dict[str, float]
    r_squared_training_fit: float
    predicted_best_configuration: SweepConfiguration
    predicted_best_net_energy_w_m2: float
    best_observed_configuration: SweepConfiguration
    best_observed_net_energy_w_m2: float
    ml_recommendation_accepted: bool
    recommended_configuration: SweepConfiguration
    recommended_net_energy_w_m2: float


def ml_optimise(
    base_material: PVMaterial,
    spectrum: SolarSpectrum,
    configurations: list[SweepConfiguration],
    alpha: float = 1.0,
    texture_enabled: bool = True,
    encapsulant_uv_blocking: bool = False,
) -> MLOptimisationResult:
    training_set = build_training_set(base_material, spectrum, configurations, texture_enabled, encapsulant_uv_blocking)
    surrogate = RidgeSurrogate(alpha).fit(training_set.X, training_set.y)

    predictions = surrogate.predict(training_set.X)
    residuals = training_set.y - predictions
    ss_res = float(np.sum(residuals**2))
    ss_tot = float(np.sum((training_set.y - training_set.y.mean()) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0

    ml_pick_idx = int(np.argmax(predictions))
    true_best_idx = int(np.argmax(training_set.y))

    predicted_best_config = training_set.configurations[ml_pick_idx]
    predicted_best_net_energy = float(training_set.y[ml_pick_idx])  # the *real* physics value at that config
    best_observed_config = training_set.configurations[true_best_idx]
    best_observed_net_energy = float(training_set.y[true_best_idx])

    accepted = predicted_best_net_energy >= best_observed_net_energy - 1e-9

    return MLOptimisationResult(
        training_set=training_set,
        feature_importance=surrogate.standardized_coefficients(training_set.feature_names),
        r_squared_training_fit=r_squared,
        predicted_best_configuration=predicted_best_config,
        predicted_best_net_energy_w_m2=predicted_best_net_energy,
        best_observed_configuration=best_observed_config,
        best_observed_net_energy_w_m2=best_observed_net_energy,
        ml_recommendation_accepted=accepted,
        recommended_configuration=predicted_best_config if accepted else best_observed_config,
        recommended_net_energy_w_m2=predicted_best_net_energy if accepted else best_observed_net_energy,
    )
