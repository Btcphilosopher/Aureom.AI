"""Freezing-point-depression engine.

**Model and assumptions (read before trusting numbers to 3 decimal places):**

Ice cream mix is treated as an ideal dilute aqueous solution of the
colligatively-active solutes (sugars, lactose, and, as a rough
correction, dissolved minerals). The initial freezing point is estimated
from the van't Hoff / Raoult's-law freezing-point-depression law:

    dT_f = Kf * m

where ``Kf = 1.86 K*kg/mol`` is the cryoscopic constant of water and
``m`` is the total solute molality (mol solute per kg of *water*, not per
kg of mix).

This is the same idealisation used as the standard textbook starting
point in dairy/food science (e.g. Goff & Hartel, *Ice Cream*, 7th ed.,
ch. 3) and is known to systematically under-predict the freezing-point
depression of concentrated sugar solutions (real solutions are non-ideal
at ice-cream sugar concentrations, ~15-20% total sugars). Two explicit,
isolated assumptions are baked in, so a better model can replace either
without touching the rest of the engine:

1. **Colligative solutes** = sugars + lactose (by declared molecular
   weight) + a rough mineral contribution using an assumed effective
   molecular weight for dairy ash. Proteins, fat, stabilisers and
   emulsifiers are treated as colligatively inert (their molar
   concentration is negligible given their high molecular weight /
   insolubility).
2. **Ideal solution behaviour**: activity coefficients are taken as 1.
   A more accurate model (e.g. a Norrish-equation or UNIQUAC-based
   activity-coefficient correction, or an empirical PAC-table lookup)
   can be substituted by replacing :func:`initial_freezing_point_k` --
   the rest of the thermal engine only depends on this function's
   signature, not its internals.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.formulation.composition import Composition
from icecream_x.utils.units import celsius_to_kelvin

WATER_CRYOSCOPIC_CONSTANT_K_KG_PER_MOL = 1.86
PURE_WATER_FREEZING_POINT_K = celsius_to_kelvin(0.0)

#: Rough effective molar mass used to convert dairy mineral (ash) mass into
#: an approximate molar contribution to freezing-point depression. Dairy
#: ash is a mixture of monovalent and multivalent salts; 60 g/mol is a
#: coarse representative value (roughly between NaCl at 58.4 and KCl at
#: 74.6), documented here as an explicit simplification.
MINERAL_EFFECTIVE_MW_G_PER_MOL = 60.0


@dataclass(frozen=True, slots=True)
class FreezingPointResult:
    initial_freezing_point_k: float
    initial_freezing_point_c: float
    solute_moles: float
    molality_mol_per_kg_water: float


def _mineral_moles(composition: Composition) -> float:
    return (composition.mineral_kg * 1000.0) / MINERAL_EFFECTIVE_MW_G_PER_MOL


def total_colligative_solute_moles(composition: Composition) -> float:
    """Total moles of solute assumed to be colligatively active."""
    return composition.total_solute_moles + _mineral_moles(composition)


def initial_freezing_point_k(composition: Composition) -> float:
    """Estimate the initial freezing point of the mix, in Kelvin.

    This is the temperature at which the first ice crystal forms upon
    cooling an unfrozen mix -- see module docstring for the model and its
    assumptions.
    """
    if composition.water_kg <= 0:
        raise ValueError("Cannot compute a freezing point for a mix with no water")
    solute_moles = total_colligative_solute_moles(composition)
    molality = solute_moles / composition.water_kg
    depression = WATER_CRYOSCOPIC_CONSTANT_K_KG_PER_MOL * molality
    return PURE_WATER_FREEZING_POINT_K - depression


def freezing_point_analysis(composition: Composition) -> FreezingPointResult:
    solute_moles = total_colligative_solute_moles(composition)
    molality = solute_moles / composition.water_kg if composition.water_kg > 0 else 0.0
    tf_k = initial_freezing_point_k(composition)
    return FreezingPointResult(
        initial_freezing_point_k=tf_k,
        initial_freezing_point_c=tf_k - PURE_WATER_FREEZING_POINT_K,
        solute_moles=solute_moles,
        molality_mol_per_kg_water=molality,
    )
