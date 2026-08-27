"""Model calibration against measured data.

Several models in ICECREAM-X are explicitly documented as
order-of-magnitude defaults awaiting calibration (viscosity thickening
rate constants, the freezer's scraped-surface heat-transfer-coefficient
correlation, ice-crystal nucleation/recrystallisation rate constants...).
This module provides a generic least-squares calibration routine and one
worked example (viscosity thickening constants) -- the same pattern
applies to any other tunable constant.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    fitted_parameters: dict[str, float]
    residual_rms: float
    converged: bool


def calibrate(
    model_fn: Callable[..., float],
    parameter_names: list[str],
    initial_guess: list[float],
    bounds: tuple[list[float], list[float]],
    measured_inputs: list[dict],
    measured_outputs: list[float],
) -> CalibrationResult:
    """Fit ``model_fn(**inputs, **{name: value})`` parameters to measured data.

    ``model_fn`` must accept the keys in each ``measured_inputs`` dict as
    keyword arguments, plus one keyword argument per name in
    ``parameter_names``.
    """
    measured = np.array(measured_outputs, dtype=float)

    def residuals(x: np.ndarray) -> np.ndarray:
        params = dict(zip(parameter_names, x))
        predicted = np.array([model_fn(**inputs, **params) for inputs in measured_inputs])
        return predicted - measured

    result = least_squares(residuals, x0=np.array(initial_guess, dtype=float), bounds=bounds)
    rms = float(np.sqrt(np.mean(result.fun**2)))
    return CalibrationResult(
        fitted_parameters=dict(zip(parameter_names, result.x.tolist())),
        residual_rms=rms,
        converged=bool(result.success),
    )


def calibrate_viscosity_thickening(
    measured_points: list[dict],
) -> CalibrationResult:
    """Calibrate sugar/stabiliser thickening-rate constants against viscometer data.

    Each entry of ``measured_points`` must have keys: ``temperature_k``,
    ``sugar_mass_fraction_of_serum``, ``stabiliser_mass_fraction``, and
    the target ``viscosity_pa_s`` goes in a parallel ``measured_outputs``
    list constructed by the caller (see example in
    :mod:`icecream_x.tests`).
    """
    from icecream_x.rheology.temperature_dependence import water_viscosity_pa_s

    def model(
        temperature_k: float,
        sugar_mass_fraction_of_serum: float,
        stabiliser_mass_fraction: float,
        sugar_rate: float,
        stabiliser_rate: float,
    ) -> float:
        base = water_viscosity_pa_s(temperature_k)
        sugar_factor = np.exp(min(sugar_rate * sugar_mass_fraction_of_serum, 50.0))
        stabiliser_factor = np.exp(min(stabiliser_rate * 100.0 * stabiliser_mass_fraction, 50.0))
        return base * sugar_factor * stabiliser_factor

    measured_outputs = [p.pop("viscosity_pa_s") for p in measured_points]
    return calibrate(
        model,
        parameter_names=["sugar_rate", "stabiliser_rate"],
        initial_guess=[2.2, 1.8],
        bounds=([0.0, 0.0], [10.0, 10.0]),
        measured_inputs=measured_points,
        measured_outputs=measured_outputs,
    )
