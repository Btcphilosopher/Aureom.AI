"""Process-condition optimisation.

Generic, black-box optimiser over any subset of
:class:`~icecream_x.core.engine.ProcessProfile` fields (including nested
equipment fields via dotted paths, e.g. ``"freezer.scraper_speed_rpm"``).
Because the objective involves running the full physical pipeline (not a
smooth closed-form function), this uses derivative-free Nelder-Mead
(bounded, via SciPy's ``bounds`` support) rather than a gradient method --
robust to the mild non-smoothness introduced by the enthalpy-method
timestepping and by discrete early-stopping conditions in
:mod:`icecream_x.processing`.

Multi-objective optimisation is supported via linear scalarisation
(:func:`pareto_front`): the same single-objective optimiser is run once
per weight combination across a set of objectives, tracing out an
approximate Pareto front. This is a standard, simple technique for
black-box multi-objective problems and is preferred here over a
population-based multi-objective algorithm (e.g. NSGA-II) purely for
implementation simplicity -- the optimiser interface is generic enough
that a population-based method could be substituted without changing
callers.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from icecream_x.core.engine import PipelineResult, ProcessProfile, run_production_line
from icecream_x.formulation.recipe import Recipe

ObjectiveFn = Callable[[PipelineResult], float]


def _get_nested(obj: object, path: str):
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def _set_nested(obj, path: str, value: float):
    """Return a copy of ``obj`` with the dotted-path attribute set to ``value``."""
    parts = path.split(".")
    if len(parts) == 1:
        return dataclasses.replace(obj, **{parts[0]: value})
    head, rest = parts[0], ".".join(parts[1:])
    child = getattr(obj, head)
    new_child = _set_nested(child, rest, value)
    return dataclasses.replace(obj, **{head: new_child})


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    path: str
    lower_bound: float
    upper_bound: float


@dataclass(frozen=True, slots=True)
class OptimisationResult:
    optimal_parameters: dict[str, float]
    optimal_profile: ProcessProfile
    optimal_objective_value: float
    pipeline_result: PipelineResult
    converged: bool
    n_evaluations: int


def optimise_process(
    recipe: Recipe,
    base_profile: ProcessProfile,
    parameters: list[ParameterSpec],
    objective: ObjectiveFn,
    *,
    maximise: bool = True,
    max_iterations: int = 100,
) -> OptimisationResult:
    x0 = np.array([_get_nested(base_profile, p.path) for p in parameters], dtype=float)
    bounds = [(p.lower_bound, p.upper_bound) for p in parameters]
    n_evals = 0

    def build_profile(x: np.ndarray) -> ProcessProfile:
        profile = base_profile
        for p, value in zip(parameters, x):
            profile = _set_nested(profile, p.path, float(value))
        return profile

    def scalar_objective(x: np.ndarray) -> float:
        nonlocal n_evals
        n_evals += 1
        profile = build_profile(x)
        try:
            result = run_production_line(recipe, profile)
        except Exception:
            return 1e6  # heavily penalise infeasible parameter combinations
        value = objective(result)
        return -value if maximise else value

    res = minimize(
        scalar_objective,
        x0,
        method="Nelder-Mead",
        bounds=bounds,
        options={"maxiter": max_iterations, "xatol": 1e-3, "fatol": 1e-3},
    )

    best_profile = build_profile(res.x)
    best_result = run_production_line(recipe, best_profile)
    best_value = objective(best_result)

    return OptimisationResult(
        optimal_parameters={p.path: float(v) for p, v in zip(parameters, res.x)},
        optimal_profile=best_profile,
        optimal_objective_value=best_value,
        pipeline_result=best_result,
        converged=bool(res.success),
        n_evaluations=n_evals,
    )


def pareto_front(
    recipe: Recipe,
    base_profile: ProcessProfile,
    parameters: list[ParameterSpec],
    objectives: list[tuple[str, ObjectiveFn, bool]],
    *,
    n_weight_samples: int = 11,
    max_iterations: int = 60,
) -> list[dict[str, float]]:
    """Approximate a Pareto front for two objectives via weighted-sum scalarisation.

    ``objectives`` is a list of ``(name, objective_fn, maximise)`` tuples.
    Currently supports exactly two objectives (the common case: e.g.
    quality vs. cost, or energy vs. throughput); weights are swept from
    (1, 0) to (0, 1).
    """
    if len(objectives) != 2:
        raise ValueError("pareto_front currently supports exactly two objectives")
    (name_a, obj_a, max_a), (name_b, obj_b, max_b) = objectives

    def normalise(value: float, maximise: bool) -> float:
        return value if maximise else -value

    front: list[dict[str, float]] = []
    for w in np.linspace(0.0, 1.0, n_weight_samples):

        def combined(result: PipelineResult, w=w) -> float:
            return w * normalise(obj_a(result), max_a) + (1 - w) * normalise(obj_b(result), max_b)

        opt = optimise_process(
            recipe, base_profile, parameters, combined, maximise=True, max_iterations=max_iterations
        )
        front.append(
            {
                "weight_a": float(w),
                name_a: obj_a(opt.pipeline_result),
                name_b: obj_b(opt.pipeline_result),
                **opt.optimal_parameters,
            }
        )
    return front
