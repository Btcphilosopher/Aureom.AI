"""Stabiliser ingredients (hydrocolloids).

Stabilisers are used at very small mass fractions of the total mix
(typically 0.1-0.5%) but have an outsized effect on mix viscosity, water
binding, and ice-recrystallisation resistance during storage -- see
:mod:`icecream_x.rheology.viscosity` and
:mod:`icecream_x.storage.recrystallisation`.

See :mod:`icecream_x.formulation.fats` for a note on the provenance of
these representative composition values.
"""

from __future__ import annotations

from icecream_x.formulation.ingredients import Ingredient, IngredientCategory

GUAR_GUM = Ingredient(
    name="Guar Gum",
    category=IngredientCategory.STABILISER,
    stabiliser_fraction=0.900,
    water_fraction=0.100,
    cost_per_kg=6.00,
)

LOCUST_BEAN_GUM = Ingredient(
    name="Locust Bean Gum (LBG)",
    category=IngredientCategory.STABILISER,
    stabiliser_fraction=0.880,
    water_fraction=0.120,
    cost_per_kg=9.00,
)

CARRAGEENAN = Ingredient(
    name="Kappa Carrageenan",
    category=IngredientCategory.STABILISER,
    stabiliser_fraction=0.880,
    water_fraction=0.120,
    cost_per_kg=12.00,
)

CMC = Ingredient(
    name="Sodium Carboxymethylcellulose (CMC)",
    category=IngredientCategory.STABILISER,
    stabiliser_fraction=0.920,
    water_fraction=0.080,
    cost_per_kg=5.50,
)

XANTHAN_GUM = Ingredient(
    name="Xanthan Gum",
    category=IngredientCategory.STABILISER,
    stabiliser_fraction=0.910,
    water_fraction=0.090,
    cost_per_kg=8.50,
)

STABILISER_EMULSIFIER_BLEND = Ingredient(
    name="Commercial Stabiliser/Emulsifier Blend",
    category=IngredientCategory.STABILISER,
    stabiliser_fraction=0.700,
    emulsifier_fraction=0.200,
    water_fraction=0.100,
    cost_per_kg=7.50,
)

REGISTRY: dict[str, Ingredient] = {
    ing.name: ing
    for ing in [
        GUAR_GUM,
        LOCUST_BEAN_GUM,
        CARRAGEENAN,
        CMC,
        XANTHAN_GUM,
        STABILISER_EMULSIFIER_BLEND,
    ]
}
