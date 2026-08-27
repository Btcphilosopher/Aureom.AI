"""Formulation optimisation: search over ingredient masses.

Adjusts the mass of a chosen subset of a recipe's ingredient lines
(identified by ingredient name) within bounds, re-normalises the batch to
its original total mass (so the optimiser explores *mix ratios*, not just
"add more of everything"), runs the full production pipeline, and scores
the result. Uses the same bounded Nelder-Mead approach as
:mod:`icecream_x.optimisation.process_optimizer` for the same reasons
(expensive, non-smooth, simulation-based objective).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy.optimize import minimize

from icecream_x.core.engine import PipelineResult, ProcessProfile, run_production_line
from icecream_x.formulation.composition import WeighedIngredient
from icecream_x.formulation.recipe import Recipe
from icecream_x.optimisation.process_optimizer import ObjectiveFn


@dataclass(frozen=True, slots=True)
class IngredientBound:
    ingredient_name: str
    lower_bound_kg: float
    upper_bound_kg: float


@dataclass(frozen=True, slots=True)
class FormulationOptimisationResult:
    optimal_recipe: Recipe
    optimal_masses_kg: dict[str, float]
    optimal_objective_value: float
    pipeline_result: PipelineResult
    converged: bool


def _apply_masses(recipe: Recipe, bounds: list[IngredientBound], masses_kg: np.ndarray, preserve_total_mass: bool) -> Recipe:
    target_names = {b.ingredient_name for b in bounds}
    mass_by_name = {b.ingredient_name: m for b, m in zip(bounds, masses_kg)}

    new_lines = []
    for line in recipe.lines:
        if line.ingredient.name in target_names:
            new_lines.append(
                WeighedIngredient(ingredient=line.ingredient, mass_kg=float(mass_by_name[line.ingredient.name]))
            )
        else:
            new_lines.append(line)

    new_recipe = Recipe(name=recipe.name, lines=new_lines, description=recipe.description)
    if preserve_total_mass:
        new_recipe = new_recipe.scaled_to_batch_size(recipe.batch_mass_kg)
    return new_recipe


def optimise_formulation(
    base_recipe: Recipe,
    bounds: list[IngredientBound],
    objective: ObjectiveFn,
    *,
    process_profile: ProcessProfile = ProcessProfile(),
    maximise: bool = True,
    preserve_total_mass: bool = True,
    max_iterations: int = 80,
) -> FormulationOptimisationResult:
    initial_masses = {b.ingredient_name: None for b in bounds}
    for line in base_recipe.lines:
        if line.ingredient.name in initial_masses:
            initial_masses[line.ingredient.name] = line.mass_kg

    x0 = np.array(
        [
            initial_masses[b.ingredient_name]
            if initial_masses[b.ingredient_name] is not None
            else (b.lower_bound_kg + b.upper_bound_kg) / 2.0
            for b in bounds
        ]
    )
    scipy_bounds = [(b.lower_bound_kg, b.upper_bound_kg) for b in bounds]

    def scalar_objective(x: np.ndarray) -> float:
        recipe = _apply_masses(base_recipe, bounds, x, preserve_total_mass)
        try:
            result = run_production_line(recipe, process_profile)
        except Exception:
            return 1e6
        value = objective(result)
        return -value if maximise else value

    res = minimize(
        scalar_objective,
        x0,
        method="Nelder-Mead",
        bounds=scipy_bounds,
        options={"maxiter": max_iterations, "xatol": 1e-3, "fatol": 1e-3},
    )

    best_recipe = _apply_masses(base_recipe, bounds, res.x, preserve_total_mass)
    best_result = run_production_line(best_recipe, process_profile)
    best_value = objective(best_result)

    return FormulationOptimisationResult(
        optimal_recipe=best_recipe,
        optimal_masses_kg={b.ingredient_name: float(v) for b, v in zip(bounds, res.x)},
        optimal_objective_value=best_value,
        pipeline_result=best_result,
        converged=bool(res.success),
    )
