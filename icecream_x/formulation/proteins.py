"""Powdered milk-solids and purified milk-protein ingredients.

See :mod:`icecream_x.formulation.fats` for a note on the provenance of
these representative composition values.
"""

from __future__ import annotations

from icecream_x.formulation.ingredients import Ingredient, IngredientCategory

SKIM_MILK_POWDER = Ingredient(
    name="Skim Milk Powder (SMP)",
    category=IngredientCategory.DAIRY,
    protein_fraction=0.350,
    lactose_fraction=0.520,
    mineral_fraction=0.080,
    water_fraction=1.0 - (0.350 + 0.520 + 0.080),
    cost_per_kg=3.20,
)

WHOLE_MILK_POWDER = Ingredient(
    name="Whole Milk Powder (WMP)",
    category=IngredientCategory.DAIRY,
    fat_fraction=0.260,
    protein_fraction=0.260,
    lactose_fraction=0.380,
    mineral_fraction=0.060,
    water_fraction=1.0 - (0.260 + 0.260 + 0.380 + 0.060),
    cost_per_kg=3.80,
)

MILK_PROTEIN_CONCENTRATE_80 = Ingredient(
    name="Milk Protein Concentrate (MPC80)",
    category=IngredientCategory.DAIRY,
    protein_fraction=0.800,
    lactose_fraction=0.060,
    mineral_fraction=0.060,
    water_fraction=1.0 - (0.800 + 0.060 + 0.060),
    cost_per_kg=9.50,
)

WHEY_PROTEIN_CONCENTRATE_80 = Ingredient(
    name="Whey Protein Concentrate (WPC80)",
    category=IngredientCategory.DAIRY,
    protein_fraction=0.800,
    lactose_fraction=0.070,
    mineral_fraction=0.060,
    water_fraction=1.0 - (0.800 + 0.070 + 0.060),
    cost_per_kg=8.50,
)

SODIUM_CASEINATE = Ingredient(
    name="Sodium Caseinate",
    category=IngredientCategory.DAIRY,
    protein_fraction=0.880,
    mineral_fraction=0.040,
    water_fraction=1.0 - (0.880 + 0.040),
    cost_per_kg=7.00,
)

REGISTRY: dict[str, Ingredient] = {
    ing.name: ing
    for ing in [
        SKIM_MILK_POWDER,
        WHOLE_MILK_POWDER,
        MILK_PROTEIN_CONCENTRATE_80,
        WHEY_PROTEIN_CONCENTRATE_80,
        SODIUM_CASEINATE,
    ]
}
