"""Mixing: turn a Recipe into the initial ProductState.

This is the entry point of the simulation chain: FORMULATION -> MIXING.
No thermal or structural transformation happens here beyond bringing the
ingredients to a uniform temperature and composition -- homogenisation,
pasteurisation etc. are separate, explicit steps.
"""

from __future__ import annotations

from icecream_x.core.state import ProcessStage, ProductState
from icecream_x.formulation.recipe import Recipe
from icecream_x.utils.units import celsius_to_kelvin


def mix(recipe: Recipe, mix_temperature_c: float = 4.0) -> ProductState:
    """Combine a recipe's ingredients into a uniform, well-mixed ProductState."""
    composition = recipe.composition()
    return ProductState(
        composition=composition,
        temperature_k=celsius_to_kelvin(mix_temperature_c),
        stage=ProcessStage.MIXED,
    )
