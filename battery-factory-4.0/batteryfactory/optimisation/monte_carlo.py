"""Monte Carlo uncertainty engine (spec item 49)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np


@dataclass
class UncertainParam:
    name: str
    distribution: str   # "normal" | "lognormal" | "uniform" | "triangular"
    params: dict[str, float]

    def sample(self, rng: np.random.Generator) -> float:
        if self.distribution == "normal":
            return float(rng.normal(self.params["mean"], self.params["std"]))
        if self.distribution == "lognormal":
            return float(rng.lognormal(self.params["mean"], self.params["sigma"]))
        if self.distribution == "uniform":
            return float(rng.uniform(self.params["low"], self.params["high"]))
        if self.distribution == "triangular":
            return float(rng.triangular(self.params["left"], self.params["mode"], self.params["right"]))
        raise ValueError(f"Unknown distribution {self.distribution}")


@dataclass
class MonteCarloResult:
    n_trials: int
    samples: dict[str, np.ndarray]     # output metric -> array of trial values
    percentiles: dict[str, dict[str, float]]  # metric -> {p5, p50, p95, mean, std}


class MonteCarloEngine:
    def run(
        self,
        model_fn: Callable[[dict[str, float]], dict[str, float]],
        uncertain_params: list[UncertainParam],
        n_trials: int = 500,
        rng: np.random.Generator | None = None,
    ) -> MonteCarloResult:
        rng = rng or np.random.default_rng()
        output_samples: dict[str, list[float]] = {}

        for _ in range(n_trials):
            draw = {p.name: p.sample(rng) for p in uncertain_params}
            outputs = model_fn(draw)
            for key, val in outputs.items():
                output_samples.setdefault(key, []).append(val)

        samples = {k: np.array(v) for k, v in output_samples.items()}
        percentiles = {
            k: {
                "p5": float(np.percentile(v, 5)), "p50": float(np.percentile(v, 50)), "p95": float(np.percentile(v, 95)),
                "mean": float(np.mean(v)), "std": float(np.std(v)),
            }
            for k, v in samples.items()
        }
        return MonteCarloResult(n_trials=n_trials, samples=samples, percentiles=percentiles)
