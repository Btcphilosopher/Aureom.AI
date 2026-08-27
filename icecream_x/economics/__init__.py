"""Economics engine: ingredient/energy/manufacturing cost and unit economics."""

from __future__ import annotations

from icecream_x.economics.energy_cost import EnergyCostResult, flat_rate_cost, scheduled_cost
from icecream_x.economics.ingredient_cost import IngredientCostBreakdown, ingredient_cost_breakdown
from icecream_x.economics.manufacturing_cost import (
    CostRates,
    ManufacturingCostResult,
    manufacturing_cost,
)
from icecream_x.economics.unit_economics import UnitEconomicsResult, unit_economics

__all__ = [
    "EnergyCostResult",
    "flat_rate_cost",
    "scheduled_cost",
    "IngredientCostBreakdown",
    "ingredient_cost_breakdown",
    "CostRates",
    "ManufacturingCostResult",
    "manufacturing_cost",
    "UnitEconomicsResult",
    "unit_economics",
]
