"""
Statistical quality engine (spec item 15): distributions, Cp/Cpk, defect
rate and first-pass yield, driven by a user-adjustable process-variability
multiplier.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


def mean_std(values: np.ndarray) -> tuple[float, float]:
    return float(np.mean(values)), float(np.std(values, ddof=1)) if len(values) > 1 else 0.0


def cp(usl: float, lsl: float, std: float) -> float:
    if std <= 0:
        return float("inf")
    return (usl - lsl) / (6.0 * std)


def cpk(usl: float, lsl: float, mean: float, std: float) -> float:
    if std <= 0:
        return float("inf")
    return min((usl - mean) / (3.0 * std), (mean - lsl) / (3.0 * std))


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def defect_rate_ppm(mean: float, std: float, usl: float | None, lsl: float | None) -> float:
    if std <= 0:
        return 0.0
    p_below = _normal_cdf((lsl - mean) / std) if lsl is not None else 0.0
    p_above = 1.0 - _normal_cdf((usl - mean) / std) if usl is not None else 0.0
    return (p_below + p_above) * 1_000_000.0


def first_pass_yield(pass_count: int, total_count: int) -> float:
    if total_count == 0:
        return 0.0
    return 100.0 * pass_count / total_count


@dataclass
class ProcessCapability:
    metric: str
    mean: float
    std: float
    usl: float | None
    lsl: float | None
    cp: float
    cpk: float
    defect_rate_ppm: float


class QualityDistributionGenerator:
    """
    Generates correlated capacity / resistance / voltage / weight / thickness
    samples for a batch of cells, given a process-variability multiplier the
    user can turn up or down to see the resulting quality distributions and
    Cp/Cpk shift in real time.
    """

    _BASE_STD = {
        "capacity_ah": 0.015,     # fraction of nominal
        "resistance_mohm": 0.08,  # fraction of nominal
        "voltage_v": 0.01,
        "weight_g": 0.02,
        "thickness_um": 0.03,
    }
    # negative capacity/resistance correlation is physically real: thicker,
    # more resistive cells tend to carry slightly less usable capacity.
    _CORR = np.array([
        [1.00, -0.35, 0.10, 0.25, 0.15],
        [-0.35, 1.00, -0.05, 0.10, 0.20],
        [0.10, -0.05, 1.00, 0.05, 0.00],
        [0.25, 0.10, 0.05, 1.00, 0.30],
        [0.15, 0.20, 0.00, 0.30, 1.00],
    ])
    _METRICS = ["capacity_ah", "resistance_mohm", "voltage_v", "weight_g", "thickness_um"]

    def __init__(self, rng: np.random.Generator | None = None) -> None:
        self.rng = rng or np.random.default_rng()

    def generate(self, nominal: dict[str, float], n: int, variability_multiplier: float = 1.0) -> dict[str, np.ndarray]:
        stds = np.array([nominal[m] * self._BASE_STD[m] * variability_multiplier for m in self._METRICS])
        cov = np.outer(stds, stds) * self._CORR
        means = np.array([nominal[m] for m in self._METRICS])
        samples = self.rng.multivariate_normal(means, cov, size=n)
        return {m: samples[:, i] for i, m in enumerate(self._METRICS)}

    def capability(self, metric: str, samples: np.ndarray, usl: float | None, lsl: float | None) -> ProcessCapability:
        mean, std = mean_std(samples)
        return ProcessCapability(
            metric=metric, mean=mean, std=std, usl=usl, lsl=lsl,
            cp=cp(usl, lsl, std) if (usl is not None and lsl is not None) else float("nan"),
            cpk=cpk(usl, lsl, mean, std) if (usl is not None and lsl is not None) else float("nan"),
            defect_rate_ppm=defect_rate_ppm(mean, std, usl, lsl),
        )
