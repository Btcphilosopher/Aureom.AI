"""
Calibration engine: standard goodness-of-fit metrics (RMSE, MAE, MAPE, R^2)
between observed and simulated series, and parameter calibration against
observations via global optimisation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np
from scipy.optimize import differential_evolution


def rmse(observed: np.ndarray, simulated: np.ndarray) -> float:
    obs, sim = np.asarray(observed, dtype=float), np.asarray(simulated, dtype=float)
    return float(np.sqrt(np.mean((obs - sim) ** 2)))


def mae(observed: np.ndarray, simulated: np.ndarray) -> float:
    obs, sim = np.asarray(observed, dtype=float), np.asarray(simulated, dtype=float)
    return float(np.mean(np.abs(obs - sim)))


def mape(observed: np.ndarray, simulated: np.ndarray) -> float:
    obs, sim = np.asarray(observed, dtype=float), np.asarray(simulated, dtype=float)
    mask = obs != 0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((obs[mask] - sim[mask]) / obs[mask])) * 100.0)


def r_squared(observed: np.ndarray, simulated: np.ndarray) -> float:
    obs, sim = np.asarray(observed, dtype=float), np.asarray(simulated, dtype=float)
    ss_res = np.sum((obs - sim) ** 2)
    ss_tot = np.sum((obs - np.mean(obs)) ** 2)
    if ss_tot == 0:
        return float("nan")
    return float(1 - ss_res / ss_tot)


@dataclass
class CalibrationMetrics:
    rmse: float
    mae: float
    mape: float
    r2: float


def evaluate_calibration(observed: np.ndarray, simulated: np.ndarray) -> CalibrationMetrics:
    return CalibrationMetrics(
        rmse=rmse(observed, simulated),
        mae=mae(observed, simulated),
        mape=mape(observed, simulated),
        r2=r_squared(observed, simulated),
    )


@dataclass
class CalibrationResult:
    best_parameters: dict[str, float]
    metrics: CalibrationMetrics


def calibrate_parameters(
    model_fn: Callable[..., np.ndarray],
    observed: np.ndarray,
    param_names: Sequence[str],
    param_bounds: Sequence[tuple[float, float]],
    seed: int = 42,
    maxiter: int = 60,
) -> CalibrationResult:
    """Calibrate ``model_fn(**params) -> simulated_array`` against
    ``observed`` by minimising RMSE with differential evolution (global,
    derivative-free -- appropriate for hydrological/hydraulic models whose
    RMSE surface is rarely convex)."""

    def objective(x):
        params = dict(zip(param_names, x))
        simulated = model_fn(**params)
        return rmse(observed, simulated)

    result = differential_evolution(objective, bounds=list(param_bounds), seed=seed, maxiter=maxiter, polish=True)
    best_params = dict(zip(param_names, result.x))
    simulated = model_fn(**best_params)
    return CalibrationResult(best_parameters=best_params, metrics=evaluate_calibration(observed, simulated))
