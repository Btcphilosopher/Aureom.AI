"""Formulation engine: ingredients, composition, and recipes."""

from __future__ import annotations

from icecream_x.formulation import emulsifiers, fats, proteins, solids, stabilisers, sugars
from icecream_x.formulation.composition import Composition, WeighedIngredient, compose
from icecream_x.formulation.ingredients import Ingredient, IngredientCategory
from icecream_x.formulation.recipe import Recipe

#: Combined registry of every example ingredient shipped with ICECREAM-X,
#: keyed by ingredient name. Purely a convenience -- users are free to
#: construct arbitrary new :class:`Ingredient` instances outside this
#: registry.
INGREDIENT_LIBRARY: dict[str, Ingredient] = {
    **solids.REGISTRY,
    **fats.REGISTRY,
    **proteins.REGISTRY,
    **sugars.REGISTRY,
    **stabilisers.REGISTRY,
    **emulsifiers.REGISTRY,
}

__all__ = [
    "Ingredient",
    "IngredientCategory",
    "Composition",
    "WeighedIngredient",
    "compose",
    "Recipe",
    "INGREDIENT_LIBRARY",
    "solids",
    "fats",
    "proteins",
    "sugars",
    "stabilisers",
    "emulsifiers",
]
