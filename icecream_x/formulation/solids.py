"""Base dairy liquids and water.

See :mod:`icecream_x.formulation.fats` for a note on the provenance of
these representative composition values.
"""

from __future__ import annotations

from icecream_x.formulation.ingredients import Ingredient, IngredientCategory

WATER = Ingredient(
    name="Water",
    category=IngredientCategory.WATER,
    water_fraction=1.0,
    cost_per_kg=0.001,
)

WHOLE_MILK = Ingredient(
    name="Whole Milk (3.5% fat)",
    category=IngredientCategory.DAIRY,
    fat_fraction=0.035,
    protein_fraction=0.032,
    lactose_fraction=0.047,
    mineral_fraction=0.007,
    water_fraction=1.0 - (0.035 + 0.032 + 0.047 + 0.007),
    cost_per_kg=0.55,
)

SKIM_MILK = Ingredient(
    name="Skim Milk",
    category=IngredientCategory.DAIRY,
    fat_fraction=0.001,
    protein_fraction=0.034,
    lactose_fraction=0.050,
    mineral_fraction=0.008,
    water_fraction=1.0 - (0.001 + 0.034 + 0.050 + 0.008),
    cost_per_kg=0.45,
)

CONDENSED_SKIM_MILK_30 = Ingredient(
    name="Condensed Skim Milk (~30% TS)",
    category=IngredientCategory.DAIRY,
    protein_fraction=0.105,
    lactose_fraction=0.156,
    mineral_fraction=0.024,
    water_fraction=1.0 - (0.105 + 0.156 + 0.024),
    cost_per_kg=0.90,
)

REGISTRY: dict[str, Ingredient] = {
    ing.name: ing for ing in [WATER, WHOLE_MILK, SKIM_MILK, CONDENSED_SKIM_MILK_30]
}
