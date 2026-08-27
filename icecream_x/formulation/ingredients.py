"""Ingredient property model.

Every ingredient that can go into a :class:`~icecream_x.formulation.recipe.Recipe`
is described by an :class:`Ingredient`: a typed, immutable record of its
composition and physical properties. The engine never hard-codes a
specific ingredient list -- :mod:`icecream_x.formulation.solids`,
:mod:`.sugars`, :mod:`.fats`, :mod:`.proteins`, :mod:`.stabilisers` and
:mod:`.emulsifiers` merely provide *example* ingredient databases built on
top of this model; users may construct arbitrary new ``Ingredient``
instances.

Composition fractions are all *mass fractions of the ingredient itself*
(not of the final mix) and are required to sum to 1.0 within a small
tolerance:

    water + fat + protein + lactose + sugar + mineral
        + stabiliser + emulsifier + other_solids = 1
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

# Reference molecular weights (g/mol) used for colligative freezing-point
# calculations. Sucrose and lactose are both disaccharides with formula
# C12H22O11 and share a molecular weight; monosaccharides (glucose,
# fructose, galactose) are half that.
SUCROSE_MW_G_PER_MOL = 342.30
LACTOSE_MW_G_PER_MOL = 342.30
DEXTROSE_MW_G_PER_MOL = 180.16

# Approximate pure-component densities at ~5 degC, kg/m3. Used for the
# additive-volume mix density estimate. These are representative literature
# values, not measured constants for a specific plant.
DENSITY_WATER_KG_M3 = 1000.0
DENSITY_FAT_KG_M3 = 920.0
DENSITY_PROTEIN_KG_M3 = 1400.0
DENSITY_CARBOHYDRATE_KG_M3 = 1590.0
DENSITY_MINERAL_KG_M3 = 2400.0
DENSITY_STABILISER_KG_M3 = 1600.0
DENSITY_EMULSIFIER_KG_M3 = 1000.0


class IngredientCategory(str, Enum):
    DAIRY = "dairy"
    SWEETENER = "sweetener"
    STABILISER = "stabiliser"
    EMULSIFIER = "emulsifier"
    WATER = "water"
    FLAVOUR = "flavour"
    INCLUSION = "inclusion"
    OTHER = "other"


class Ingredient(BaseModel, frozen=True):
    """A single raw material with fully-specified composition.

    All fractions are mass fractions of the ingredient (fraction of a
    kilogram of *this ingredient*, not of the mix). ``relative_sweetness``
    and ``pac_relative_to_sucrose`` are dimensionless engineering indices
    (sucrose = 100) used by the quality/sweetness and freezing-point
    engines respectively; they are optional refinements over the
    colligative (molar) freezing-point model and default to values
    consistent with the ingredient's declared molecular weight.
    """

    name: str
    category: IngredientCategory = IngredientCategory.OTHER

    water_fraction: float = Field(0.0, ge=0.0, le=1.0)
    fat_fraction: float = Field(0.0, ge=0.0, le=1.0)
    protein_fraction: float = Field(0.0, ge=0.0, le=1.0)
    lactose_fraction: float = Field(0.0, ge=0.0, le=1.0)
    sugar_fraction: float = Field(0.0, ge=0.0, le=1.0)
    mineral_fraction: float = Field(0.0, ge=0.0, le=1.0)
    stabiliser_fraction: float = Field(0.0, ge=0.0, le=1.0)
    emulsifier_fraction: float = Field(0.0, ge=0.0, le=1.0)
    other_solids_fraction: float = Field(
        0.0, ge=0.0, le=1.0, description="Cocoa solids, fruit solids, fibre, etc."
    )

    sugar_molecular_weight_g_per_mol: float = Field(
        SUCROSE_MW_G_PER_MOL,
        gt=0,
        description="Effective molecular weight of the sugar_fraction component, "
        "used for colligative freezing-point-depression estimation.",
    )
    relative_sweetness: float = Field(
        100.0, ge=0.0, description="Sweetness relative to sucrose=100 (POD-style index)."
    )

    density_override_kg_m3: float | None = Field(default=None, gt=0)
    specific_heat_override_j_kg_k: float | None = Field(default=None, gt=0)
    thermal_conductivity_override_w_m_k: float | None = Field(default=None, gt=0)

    cost_per_kg: float = Field(0.0, ge=0.0, description="Ingredient cost, currency/kg.")

    @model_validator(mode="after")
    def _check_mass_closure(self) -> "Ingredient":
        total = (
            self.water_fraction
            + self.fat_fraction
            + self.protein_fraction
            + self.lactose_fraction
            + self.sugar_fraction
            + self.mineral_fraction
            + self.stabiliser_fraction
            + self.emulsifier_fraction
            + self.other_solids_fraction
        )
        if abs(total - 1.0) > 1e-3:
            raise ValueError(
                f"Ingredient '{self.name}' composition fractions sum to {total:.6f}, "
                "expected 1.0"
            )
        return self

    @property
    def total_solids_fraction(self) -> float:
        return 1.0 - self.water_fraction

    @property
    def msnf_fraction(self) -> float:
        """Milk-solids-non-fat: protein + lactose + minerals."""
        return self.protein_fraction + self.lactose_fraction + self.mineral_fraction

    @property
    def total_sugars_fraction(self) -> float:
        """All colligatively-active sugars including lactose."""
        return self.sugar_fraction + self.lactose_fraction

    def estimated_density_kg_m3(self) -> float:
        """Additive-volume estimate of the ingredient's own density."""
        if self.density_override_kg_m3 is not None:
            return self.density_override_kg_m3
        components = [
            (self.water_fraction, DENSITY_WATER_KG_M3),
            (self.fat_fraction, DENSITY_FAT_KG_M3),
            (self.protein_fraction, DENSITY_PROTEIN_KG_M3),
            (self.lactose_fraction + self.sugar_fraction, DENSITY_CARBOHYDRATE_KG_M3),
            (self.mineral_fraction, DENSITY_MINERAL_KG_M3),
            (self.stabiliser_fraction, DENSITY_STABILISER_KG_M3),
            (self.emulsifier_fraction, DENSITY_EMULSIFIER_KG_M3),
            (self.other_solids_fraction, DENSITY_CARBOHYDRATE_KG_M3),
        ]
        inverse_density = sum(frac / rho for frac, rho in components if frac > 0)
        if inverse_density <= 0:
            return DENSITY_WATER_KG_M3
        return 1.0 / inverse_density
