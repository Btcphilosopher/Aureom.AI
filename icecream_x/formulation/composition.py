"""The composition engine.

Aggregates a list of (ingredient, mass) pairs into a single
:class:`Composition` describing the absolute masses and mass fractions of
every tracked phase/component in a mix:

    total solids, water, fat, MSNF, protein, lactose, sugar,
    stabilisers, emulsifiers, other solids, air (0 before aeration)

Strict mass balance is maintained: the composition's total mass always
equals the sum of the ingredient masses that produced it (see
:func:`compose`), and every downstream process step is expected to
preserve this invariant (checked via
:func:`icecream_x.utils.validation.check_mass_balance`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from icecream_x.formulation.ingredients import LACTOSE_MW_G_PER_MOL, Ingredient
from icecream_x.utils.validation import require_non_negative


@dataclass(frozen=True, slots=True)
class Composition:
    """Absolute component masses (kg) making up a batch of product.

    ``air_mass_kg`` is a notional mass-equivalent used only for bookkeeping
    volume/density; air itself is treated as a volumetric phase (see
    :mod:`icecream_x.processing.aeration`) rather than a mass contributor to
    solids fractions.
    """

    total_mass_kg: float
    water_kg: float
    fat_kg: float
    protein_kg: float
    lactose_kg: float
    sugar_kg: float
    mineral_kg: float
    stabiliser_kg: float
    emulsifier_kg: float
    other_solids_kg: float
    air_mass_kg: float = 0.0
    sugar_moles: float = 0.0
    lactose_moles: float = 0.0

    @property
    def msnf_kg(self) -> float:
        return self.protein_kg + self.lactose_kg + self.mineral_kg

    @property
    def total_solids_kg(self) -> float:
        return self.total_mass_kg - self.water_kg

    @property
    def total_sugars_kg(self) -> float:
        return self.sugar_kg + self.lactose_kg

    @property
    def total_solute_moles(self) -> float:
        """Total moles of colligatively-active solutes (sugars + lactose)."""
        return self.sugar_moles + self.lactose_moles

    def fraction(self, component_kg: float) -> float:
        if self.total_mass_kg <= 0:
            return 0.0
        return component_kg / self.total_mass_kg

    def as_fractions(self) -> dict[str, float]:
        return {
            "water": self.fraction(self.water_kg),
            "fat": self.fraction(self.fat_kg),
            "protein": self.fraction(self.protein_kg),
            "lactose": self.fraction(self.lactose_kg),
            "sugar": self.fraction(self.sugar_kg),
            "mineral": self.fraction(self.mineral_kg),
            "stabiliser": self.fraction(self.stabiliser_kg),
            "emulsifier": self.fraction(self.emulsifier_kg),
            "other_solids": self.fraction(self.other_solids_kg),
            "msnf": self.fraction(self.msnf_kg),
            "total_solids": self.fraction(self.total_solids_kg),
        }

    def scaled(self, factor: float) -> "Composition":
        """Return a new Composition with every mass term scaled uniformly."""
        require_non_negative(factor, "scale factor")
        return Composition(
            total_mass_kg=self.total_mass_kg * factor,
            water_kg=self.water_kg * factor,
            fat_kg=self.fat_kg * factor,
            protein_kg=self.protein_kg * factor,
            lactose_kg=self.lactose_kg * factor,
            sugar_kg=self.sugar_kg * factor,
            mineral_kg=self.mineral_kg * factor,
            stabiliser_kg=self.stabiliser_kg * factor,
            emulsifier_kg=self.emulsifier_kg * factor,
            other_solids_kg=self.other_solids_kg * factor,
            air_mass_kg=self.air_mass_kg * factor,
            sugar_moles=self.sugar_moles * factor,
            lactose_moles=self.lactose_moles * factor,
        )

    def with_water_removed(self, water_removed_kg: float) -> "Composition":
        """Return a new Composition after evaporating/removing pure water.

        Used e.g. by concentration steps. Solute moles are unchanged since
        only water leaves the system.
        """
        new_water = self.water_kg - water_removed_kg
        if new_water < -1e-9:
            raise ValueError("Cannot remove more water than is present")
        new_water = max(new_water, 0.0)
        return Composition(
            total_mass_kg=self.total_mass_kg - water_removed_kg,
            water_kg=new_water,
            fat_kg=self.fat_kg,
            protein_kg=self.protein_kg,
            lactose_kg=self.lactose_kg,
            sugar_kg=self.sugar_kg,
            mineral_kg=self.mineral_kg,
            stabiliser_kg=self.stabiliser_kg,
            emulsifier_kg=self.emulsifier_kg,
            other_solids_kg=self.other_solids_kg,
            air_mass_kg=self.air_mass_kg,
            sugar_moles=self.sugar_moles,
            lactose_moles=self.lactose_moles,
        )


@dataclass(slots=True)
class WeighedIngredient:
    """An ingredient together with the mass of it used in a recipe."""

    ingredient: Ingredient
    mass_kg: float = field(metadata={"unit": "kg"})

    def __post_init__(self) -> None:
        require_non_negative(self.mass_kg, f"mass of {self.ingredient.name}")


def compose(weighed_ingredients: list[WeighedIngredient]) -> Composition:
    """Aggregate weighed ingredients into a single :class:`Composition`.

    This is a pure summation over ingredient mass fractions -- it is the
    mass-balance anchor for the whole simulation: the resulting
    ``total_mass_kg`` is defined as the sum of input ingredient masses, and
    every component mass is defined as the sum of
    ``ingredient_mass * ingredient.<component>_fraction``. No mass is
    created or destroyed here by construction.
    """
    water = fat = protein = lactose = sugar = mineral = 0.0
    stabiliser = emulsifier = other_solids = 0.0
    sugar_moles = lactose_moles = 0.0
    total_mass = 0.0

    for wi in weighed_ingredients:
        ing = wi.ingredient
        m = wi.mass_kg
        total_mass += m
        water += m * ing.water_fraction
        fat += m * ing.fat_fraction
        protein += m * ing.protein_fraction
        lactose += m * ing.lactose_fraction
        sugar += m * ing.sugar_fraction
        mineral += m * ing.mineral_fraction
        stabiliser += m * ing.stabiliser_fraction
        emulsifier += m * ing.emulsifier_fraction
        other_solids += m * ing.other_solids_fraction

        sugar_mass_kg = m * ing.sugar_fraction
        lactose_mass_kg = m * ing.lactose_fraction
        sugar_moles += (sugar_mass_kg * 1000.0) / ing.sugar_molecular_weight_g_per_mol
        lactose_moles += (lactose_mass_kg * 1000.0) / LACTOSE_MW_G_PER_MOL

    return Composition(
        total_mass_kg=total_mass,
        water_kg=water,
        fat_kg=fat,
        protein_kg=protein,
        lactose_kg=lactose,
        sugar_kg=sugar,
        mineral_kg=mineral,
        stabiliser_kg=stabiliser,
        emulsifier_kg=emulsifier,
        other_solids_kg=other_solids,
        air_mass_kg=0.0,
        sugar_moles=sugar_moles,
        lactose_moles=lactose_moles,
    )
