import pytest

from icecream_x.formulation.fats import CREAM_40
from icecream_x.formulation.ingredients import Ingredient
from icecream_x.formulation.recipe import Recipe
from icecream_x.formulation.solids import SKIM_MILK, WATER, WHOLE_MILK
from icecream_x.formulation.stabilisers import STABILISER_EMULSIFIER_BLEND
from icecream_x.formulation.sugars import GLUCOSE_SYRUP_42DE, SUCROSE
from icecream_x.utils.validation import ValidationError


def _vanilla_recipe() -> Recipe:
    r = Recipe(name="vanilla")
    r.add(WHOLE_MILK, 40).add(CREAM_40, 25).add(SKIM_MILK, 15)
    r.add(SUCROSE, 12).add(GLUCOSE_SYRUP_42DE, 5).add(STABILISER_EMULSIFIER_BLEND, 0.4)
    return r


def test_ingredient_composition_must_sum_to_one():
    with pytest.raises(Exception):
        Ingredient(name="broken", water_fraction=0.5, fat_fraction=0.6)


def test_recipe_mass_balance():
    recipe = _vanilla_recipe()
    comp = recipe.composition()
    assert comp.total_mass_kg == pytest.approx(recipe.batch_mass_kg)

    component_sum = (
        comp.water_kg
        + comp.fat_kg
        + comp.protein_kg
        + comp.lactose_kg
        + comp.sugar_kg
        + comp.mineral_kg
        + comp.stabiliser_kg
        + comp.emulsifier_kg
        + comp.other_solids_kg
    )
    assert component_sum == pytest.approx(comp.total_mass_kg, rel=1e-9)


def test_composition_fractions_sum_to_one():
    comp = _vanilla_recipe().composition()
    fractions = comp.as_fractions()
    non_derived = ["water", "fat", "protein", "lactose", "sugar", "mineral", "stabiliser", "emulsifier", "other_solids"]
    assert sum(fractions[k] for k in non_derived) == pytest.approx(1.0, rel=1e-9)


def test_recipe_scaling_preserves_ratios():
    recipe = _vanilla_recipe()
    scaled = recipe.scaled_to_batch_size(1000.0)
    assert scaled.batch_mass_kg == pytest.approx(1000.0)

    original_fractions = recipe.composition().as_fractions()
    scaled_fractions = scaled.composition().as_fractions()
    for key in original_fractions:
        assert scaled_fractions[key] == pytest.approx(original_fractions[key], abs=1e-9)


def test_pure_water_ingredient_is_all_water():
    assert WATER.water_fraction == 1.0
    assert WATER.total_solids_fraction == 0.0


def test_empty_recipe_raises():
    with pytest.raises(ValueError):
        Recipe(name="empty").composition()
