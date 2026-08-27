"""Example recipe library.

These are illustrative starting points built entirely on the public
:mod:`icecream_x.formulation` API -- nothing here is special-cased into
the engine. Add, remove, or rebalance ingredients freely; the composition
and thermodynamics engines make no assumption about what "a vanilla ice
cream" must contain.
"""

from __future__ import annotations

from icecream_x.formulation.emulsifiers import MONO_DIGLYCERIDES
from icecream_x.formulation.fats import BUTTERFAT_AMF, CREAM_40
from icecream_x.formulation.ingredients import Ingredient, IngredientCategory
from icecream_x.formulation.proteins import MILK_PROTEIN_CONCENTRATE_80, SKIM_MILK_POWDER
from icecream_x.formulation.recipe import Recipe
from icecream_x.formulation.solids import SKIM_MILK, WATER, WHOLE_MILK
from icecream_x.formulation.stabilisers import GUAR_GUM, STABILISER_EMULSIFIER_BLEND
from icecream_x.formulation.sugars import DEXTROSE_MONOHYDRATE, GLUCOSE_SYRUP_42DE, SUCROSE

COCOA_POWDER = Ingredient(
    name="Cocoa Powder (10-12% fat)",
    category=IngredientCategory.INCLUSION,
    fat_fraction=0.11,
    protein_fraction=0.20,
    other_solids_fraction=0.63,
    water_fraction=1.0 - (0.11 + 0.20 + 0.63),
    cost_per_kg=3.20,
)

STRAWBERRY_PUREE = Ingredient(
    name="Strawberry Puree",
    category=IngredientCategory.INCLUSION,
    sugar_fraction=0.06,
    other_solids_fraction=0.02,
    water_fraction=1.0 - (0.06 + 0.02),
    sugar_molecular_weight_g_per_mol=180.16,
    cost_per_kg=2.80,
)


def vanilla() -> Recipe:
    r = Recipe(name="Vanilla", description="Standard 12% fat vanilla mix.")
    r.add(WHOLE_MILK, 40).add(CREAM_40, 25).add(SKIM_MILK, 15)
    r.add(SUCROSE, 12).add(GLUCOSE_SYRUP_42DE, 5)
    r.add(STABILISER_EMULSIFIER_BLEND, 0.4)
    return r


def chocolate() -> Recipe:
    r = Recipe(name="Chocolate", description="Vanilla base with cocoa powder addition.")
    r.add(WHOLE_MILK, 38).add(CREAM_40, 23).add(SKIM_MILK, 14)
    r.add(SUCROSE, 13).add(GLUCOSE_SYRUP_42DE, 5).add(COCOA_POWDER, 5)
    r.add(STABILISER_EMULSIFIER_BLEND, 0.45)
    return r


def strawberry() -> Recipe:
    r = Recipe(name="Strawberry", description="Vanilla base with fruit puree addition.")
    r.add(WHOLE_MILK, 36).add(CREAM_40, 22).add(SKIM_MILK, 14)
    r.add(SUCROSE, 10).add(GLUCOSE_SYRUP_42DE, 4).add(STRAWBERRY_PUREE, 12)
    r.add(STABILISER_EMULSIFIER_BLEND, 0.4)
    return r


def high_fat_premium() -> Recipe:
    r = Recipe(name="High-Fat Premium", description="~16% fat super-premium formulation.")
    r.add(CREAM_40, 42).add(WHOLE_MILK, 25).add(SKIM_MILK_POWDER, 6)
    r.add(SUCROSE, 13).add(DEXTROSE_MONOHYDRATE, 3)
    r.add(STABILISER_EMULSIFIER_BLEND, 0.35).add(MONO_DIGLYCERIDES, 0.2)
    return r


def low_fat() -> Recipe:
    r = Recipe(name="Low-Fat", description="~3% fat formulation with extra MSNF for body.")
    r.add(SKIM_MILK, 62).add(CREAM_40, 8).add(SKIM_MILK_POWDER, 8)
    r.add(SUCROSE, 14).add(GLUCOSE_SYRUP_42DE, 6)
    r.add(GUAR_GUM, 0.5).add(MONO_DIGLYCERIDES, 0.2)
    return r


def high_protein() -> Recipe:
    r = Recipe(name="High-Protein", description="MPC-fortified formulation.")
    r.add(SKIM_MILK, 55).add(CREAM_40, 15).add(MILK_PROTEIN_CONCENTRATE_80, 8)
    r.add(SUCROSE, 10).add(GLUCOSE_SYRUP_42DE, 5)
    r.add(STABILISER_EMULSIFIER_BLEND, 0.4)
    return r


def industrial_standard() -> Recipe:
    r = Recipe(name="Industrial Standard", description="Cost-optimised bulk formulation.")
    r.add(SKIM_MILK, 45).add(BUTTERFAT_AMF, 10).add(SKIM_MILK_POWDER, 9)
    r.add(SUCROSE, 11).add(GLUCOSE_SYRUP_42DE, 8).add(WATER, 16.2)
    r.add(STABILISER_EMULSIFIER_BLEND, 0.5)
    return r


def artisan() -> Recipe:
    r = Recipe(name="Artisan", description="Low-overrun, egg-yolk-enriched artisan gelato base.")
    from icecream_x.formulation.emulsifiers import EGG_YOLK_LIQUID

    r.add(WHOLE_MILK, 55).add(CREAM_40, 20)
    r.add(SUCROSE, 15).add(DEXTROSE_MONOHYDRATE, 3).add(EGG_YOLK_LIQUID, 6.5)
    r.add(GUAR_GUM, 0.3)
    return r


RECIPE_LIBRARY: dict[str, Recipe] = {
    "vanilla": vanilla(),
    "chocolate": chocolate(),
    "strawberry": strawberry(),
    "high_fat_premium": high_fat_premium(),
    "low_fat": low_fat(),
    "high_protein": high_protein(),
    "industrial_standard": industrial_standard(),
    "artisan": artisan(),
}
