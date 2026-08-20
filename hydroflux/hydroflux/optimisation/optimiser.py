"""
Generic policy-parameter optimiser: given a parametrised operating policy
(e.g. a reservoir target level, pumped-storage price thresholds, a tidal
generating-head threshold), search for the parameter values that maximise a
composite objective evaluated by running a full simulation for each
candidate.

This is deliberately a *policy search*, not a full time-step-by-time-step
mixed-integer unit-commitment solve over an entire year -- that is
computationally infeasible for an interactive research/planning tool and,
in practice, is how real hydro/pumped-storage scheduling is often
approached (parametrised release/threshold policies tuned against a
simulator or against a water-value function). See
:mod:`hydroflux.core.engine` for how this plugs into the full
INPUT -> ... -> OPTIMAL CONFIGURATION pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import numpy as np

from hydroflux.optimisation.algorithms import OptResult, get_algorithm
from hydroflux.optimisation.objectives import ObjectiveWeights, composite_objective


@dataclass
class PolicyOptimisationResult:
    best_parameters: dict[str, float]
    best_objective: float
    best_metrics: dict[str, float]
    algorithm: str
    n_evaluations: int
    history: list[float] = field(default_factory=list)


def optimise_policy(
    parameter_names: Sequence[str],
    parameter_bounds: Sequence[tuple[float, float]],
    evaluate_fn: Callable[[dict[str, float]], dict[str, float]],
    weights: ObjectiveWeights,
    algorithm: str = "differential_evolution",
    seed: Optional[int] = None,
    **algorithm_kwargs,
) -> PolicyOptimisationResult:
    """Search ``parameter_bounds`` for the parameter vector maximising the
    composite objective. ``evaluate_fn(params_dict) -> metrics_dict`` should
    run the relevant simulation and return whichever metrics
    :func:`composite_objective` needs (energy, revenue, lcoe, npv, ...).
    """

    algo = get_algorithm(algorithm, **algorithm_kwargs)
    cache: dict[tuple, dict[str, float]] = {}

    def objective(x: np.ndarray) -> float:
        params = dict(zip(parameter_names, x))
        key = tuple(np.round(x, 6))
        metrics = cache.get(key)
        if metrics is None:
            metrics = evaluate_fn(params)
            cache[key] = metrics
        return composite_objective(metrics, weights)

    result: OptResult = algo.optimise(objective, list(parameter_bounds), seed=seed, maximize=True)
    best_params = dict(zip(parameter_names, result.best_x))
    best_metrics = cache.get(tuple(np.round(result.best_x, 6)), evaluate_fn(best_params))

    return PolicyOptimisationResult(
        best_parameters=best_params,
        best_objective=result.best_value,
        best_metrics=best_metrics,
        algorithm=result.method,
        n_evaluations=result.n_evaluations,
        history=result.history,
    )
