"""Emulsifier ingredients.

Emulsifiers displace milk protein from the fat-globule surface during
homogenisation, promoting the controlled partial coalescence of fat that
builds a stable air-cell/fat network during freezing -- see
:mod:`icecream_x.processing.homogenisation` and
:mod:`icecream_x.microstructure.fat_network`.

See :mod:`icecream_x.formulation.fats` for a note on the provenance of
these representative composition values.
"""

from __future__ import annotations

from icecream_x.formulation.ingredients import Ingredient, IngredientCategory

MONO_DIGLYCERIDES = Ingredient(
    name="Mono- and Diglycerides",
    category=IngredientCategory.EMULSIFIER,
    emulsifier_fraction=0.950,
    water_fraction=0.050,
    cost_per_kg=4.50,
)

POLYSORBATE_80 = Ingredient(
    name="Polysorbate 80",
    category=IngredientCategory.EMULSIFIER,
    emulsifier_fraction=0.980,
    water_fraction=0.020,
    cost_per_kg=7.00,
)

LECITHIN = Ingredient(
    name="Soy Lecithin",
    category=IngredientCategory.EMULSIFIER,
    emulsifier_fraction=0.970,
    fat_fraction=0.030,
    cost_per_kg=3.50,
)

EGG_YOLK_LIQUID = Ingredient(
    name="Liquid Egg Yolk",
    category=IngredientCategory.EMULSIFIER,
    fat_fraction=0.310,
    protein_fraction=0.160,
    emulsifier_fraction=0.020,
    mineral_fraction=0.010,
    water_fraction=1.0 - (0.310 + 0.160 + 0.020 + 0.010),
    cost_per_kg=5.00,
)

REGISTRY: dict[str, Ingredient] = {
    ing.name: ing for ing in [MONO_DIGLYCERIDES, POLYSORBATE_80, LECITHIN, EGG_YOLK_LIQUID]
}
