"""Example fat-source ingredients.

Composition values below are representative typical figures consistent
with standard dairy-science references (e.g. Goff & Hartel, *Ice Cream*,
7th ed.), not a certificate of analysis for any specific supplier batch.
Replace with supplier CoA data for production use -- these exist to make
the formulation engine usable out of the box and to serve as scenario
defaults.
"""

from __future__ import annotations

from icecream_x.formulation.ingredients import Ingredient, IngredientCategory

CREAM_40 = Ingredient(
    name="Cream (40% fat)",
    category=IngredientCategory.DAIRY,
    fat_fraction=0.400,
    protein_fraction=0.021,
    lactose_fraction=0.031,
    mineral_fraction=0.005,
    water_fraction=1.0 - (0.400 + 0.021 + 0.031 + 0.005),
    cost_per_kg=4.20,
)

CREAM_35 = Ingredient(
    name="Cream (35% fat)",
    category=IngredientCategory.DAIRY,
    fat_fraction=0.350,
    protein_fraction=0.023,
    lactose_fraction=0.033,
    mineral_fraction=0.005,
    water_fraction=1.0 - (0.350 + 0.023 + 0.033 + 0.005),
    cost_per_kg=3.80,
)

BUTTERFAT_AMF = Ingredient(
    name="Anhydrous Milk Fat (AMF / butterfat)",
    category=IngredientCategory.DAIRY,
    fat_fraction=0.998,
    water_fraction=0.002,
    cost_per_kg=6.50,
)

BUTTER_UNSALTED = Ingredient(
    name="Unsalted Butter",
    category=IngredientCategory.DAIRY,
    fat_fraction=0.800,
    water_fraction=0.180,
    mineral_fraction=0.020,
    cost_per_kg=5.50,
)

COCOA_BUTTER = Ingredient(
    name="Cocoa Butter",
    category=IngredientCategory.OTHER,
    fat_fraction=1.000,
    cost_per_kg=8.00,
)

VEGETABLE_FAT_COCONUT = Ingredient(
    name="Coconut Oil (non-dairy fat)",
    category=IngredientCategory.OTHER,
    fat_fraction=1.000,
    cost_per_kg=2.50,
)

REGISTRY: dict[str, Ingredient] = {
    ing.name: ing
    for ing in [
        CREAM_40,
        CREAM_35,
        BUTTERFAT_AMF,
        BUTTER_UNSALTED,
        COCOA_BUTTER,
        VEGETABLE_FAT_COCONUT,
    ]
}
