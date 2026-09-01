"""
Global multi-objective factory optimiser (spec item 48).

Combines maximise/minimise objectives into one weighted score and searches
a small set of decision variables (line speed multiplier, target yield,
shift pattern) by coordinate ascent -- a from-scratch, dependency-free
alternative to a full nonlinear solver, appropriate for the handful of
decision variables exposed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass
class ObjectiveWeights:
    maximise: dict[str, float]   # metric name -> weight, e.g. {"production": 1.0, "yield": 0.5}
    minimise: dict[str, float]   # metric name -> weight, e.g. {"cost": 1.0, "scrap": 0.5}


@dataclass
class DecisionVariable:
    name: str
    low: float
    high: float
    step: float


@dataclass
class OptimisationResult:
    best_point: dict[str, float]
    best_score: float
    history: list[tuple[dict[str, float], float]]


class MultiObjectiveOptimiser:
    def __init__(self, weights: ObjectiveWeights) -> None:
        self.weights = weights

    def score(self, metrics: dict[str, float], normalisers: dict[str, float]) -> float:
        s = 0.0
        for name, w in self.weights.maximise.items():
            s += w * (metrics.get(name, 0.0) / max(normalisers.get(name, 1.0), 1e-9))
        for name, w in self.weights.minimise.items():
            s -= w * (metrics.get(name, 0.0) / max(normalisers.get(name, 1.0), 1e-9))
        return s

    def optimise(
        self,
        variables: list[DecisionVariable],
        evaluate: Callable[[dict[str, float]], dict[str, float]],
        normalisers: dict[str, float],
        iterations: int = 3,
    ) -> OptimisationResult:
        """Coordinate ascent: repeatedly grid-search each variable in turn
        while holding the others at their current best value."""
        point = {v.name: (v.low + v.high) / 2.0 for v in variables}
        history: list[tuple[dict[str, float], float]] = []

        def evaluate_score(p: dict[str, float]) -> float:
            metrics = evaluate(p)
            return self.score(metrics, normalisers)

        best_score = evaluate_score(point)
        history.append((dict(point), best_score))

        for _ in range(iterations):
            improved = False
            for v in variables:
                candidates = np.arange(v.low, v.high + v.step / 2, v.step)
                best_val = point[v.name]
                for c in candidates:
                    trial = dict(point)
                    trial[v.name] = float(c)
                    s = evaluate_score(trial)
                    history.append((dict(trial), s))
                    if s > best_score:
                        best_score, best_val = s, float(c)
                        improved = True
                point[v.name] = best_val
            if not improved:
                break

        return OptimisationResult(best_point=point, best_score=best_score, history=history)
