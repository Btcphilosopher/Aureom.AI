"""Ingredient cost breakdown.

Deliberately separate from the physical engine: nothing here feeds back
into thermodynamics/processing, only into
:mod:`icecream_x.economics.manufacturing_cost` and
:mod:`icecream_x.economics.unit_economics`.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.formulation.recipe import Recipe


@dataclass(frozen=True, slots=True)
class IngredientCostBreakdown:
    total_cost: float
    cost_per_kg_batch: float
    line_items: list[dict[str, float | str]]


def ingredient_cost_breakdown(recipe: Recipe) -> IngredientCostBreakdown:
    total_mass = recipe.batch_mass_kg
    line_items = []
    total_cost = 0.0
    for line in recipe.lines:
        cost = line.mass_kg * line.ingredient.cost_per_kg
        total_cost += cost
        line_items.append(
            {
                "ingredient": line.ingredient.name,
                "mass_kg": line.mass_kg,
                "unit_cost_per_kg": line.ingredient.cost_per_kg,
                "cost": cost,
                "cost_share_pct": 0.0,  # filled below once total is known
            }
        )
    for item in line_items:
        item["cost_share_pct"] = 100.0 * item["cost"] / total_cost if total_cost > 0 else 0.0

    return IngredientCostBreakdown(
        total_cost=total_cost,
        cost_per_kg_batch=total_cost / total_mass if total_mass > 0 else 0.0,
        line_items=line_items,
    )
