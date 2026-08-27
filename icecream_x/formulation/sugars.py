"""Sweetener ingredients.

Freezing-point depression is a colligative property: it depends on the
*molar* concentration of dissolved solute, not its mass. A gram of
dextrose (MW 180) depresses the freezing point roughly twice as much as a
gram of a glucose-syrup oligomer (MW several hundred). Each sweetener here
therefore carries an explicit ``sugar_molecular_weight_g_per_mol`` so
:mod:`icecream_x.thermodynamics.freezing_point` can compute an effective
solute molality.

For glucose syrups, the number-average molecular weight is estimated from
Dextrose Equivalent (DE) using the common food-science approximation

    DE * Mn ~= 19000   =>   Mn ~= 19000 / DE

(DE is defined as reducing-sugar content expressed as % dextrose on a dry
basis; this relation is a standard, widely-used approximation for glucose
syrup solids, not an exact molecular-weight measurement -- real syrups are
polydisperse mixtures of saccharides, and this collapses that distribution
to a single representative molecular weight.)

See :mod:`icecream_x.formulation.fats` for a note on the provenance of the
mass-composition values used below.
"""

from __future__ import annotations

from icecream_x.formulation.ingredients import DEXTROSE_MW_G_PER_MOL, Ingredient, IngredientCategory

DE_MN_CONSTANT = 19000.0


def glucose_syrup_effective_mw(dextrose_equivalent: float) -> float:
    """Estimate the number-average molecular weight of a glucose syrup.

    See module docstring for the approximation and its limits.
    """
    if dextrose_equivalent <= 0:
        raise ValueError("dextrose_equivalent must be > 0")
    return DE_MN_CONSTANT / dextrose_equivalent


SUCROSE = Ingredient(
    name="Sucrose",
    category=IngredientCategory.SWEETENER,
    sugar_fraction=0.999,
    water_fraction=0.001,
    sugar_molecular_weight_g_per_mol=342.30,
    relative_sweetness=100.0,
    cost_per_kg=0.90,
)

DEXTROSE_MONOHYDRATE = Ingredient(
    name="Dextrose Monohydrate",
    category=IngredientCategory.SWEETENER,
    sugar_fraction=0.920,
    water_fraction=0.080,
    sugar_molecular_weight_g_per_mol=DEXTROSE_MW_G_PER_MOL,
    relative_sweetness=70.0,
    cost_per_kg=0.85,
)

FRUCTOSE = Ingredient(
    name="Fructose",
    category=IngredientCategory.SWEETENER,
    sugar_fraction=0.990,
    water_fraction=0.010,
    sugar_molecular_weight_g_per_mol=180.16,
    relative_sweetness=170.0,
    cost_per_kg=1.60,
)

GLUCOSE_SYRUP_42DE = Ingredient(
    name="Glucose Syrup (42 DE)",
    category=IngredientCategory.SWEETENER,
    sugar_fraction=0.800,
    water_fraction=0.200,
    sugar_molecular_weight_g_per_mol=glucose_syrup_effective_mw(42.0),
    relative_sweetness=40.0,
    cost_per_kg=0.70,
)

GLUCOSE_SYRUP_63DE = Ingredient(
    name="Glucose Syrup (63 DE)",
    category=IngredientCategory.SWEETENER,
    sugar_fraction=0.800,
    water_fraction=0.200,
    sugar_molecular_weight_g_per_mol=glucose_syrup_effective_mw(63.0),
    relative_sweetness=60.0,
    cost_per_kg=0.75,
)

INVERT_SUGAR_SYRUP = Ingredient(
    name="Invert Sugar Syrup (70% solids)",
    category=IngredientCategory.SWEETENER,
    sugar_fraction=0.700,
    water_fraction=0.300,
    sugar_molecular_weight_g_per_mol=180.16,
    relative_sweetness=130.0,
    cost_per_kg=1.10,
)

HONEY = Ingredient(
    name="Honey",
    category=IngredientCategory.SWEETENER,
    sugar_fraction=0.800,
    water_fraction=0.170,
    other_solids_fraction=0.030,
    sugar_molecular_weight_g_per_mol=180.16,
    relative_sweetness=110.0,
    cost_per_kg=4.50,
)

REGISTRY: dict[str, Ingredient] = {
    ing.name: ing
    for ing in [
        SUCROSE,
        DEXTROSE_MONOHYDRATE,
        FRUCTOSE,
        GLUCOSE_SYRUP_42DE,
        GLUCOSE_SYRUP_63DE,
        INVERT_SUGAR_SYRUP,
        HONEY,
    ]
}
