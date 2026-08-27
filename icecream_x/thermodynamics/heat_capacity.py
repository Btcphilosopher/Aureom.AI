"""Component and mixture specific heat capacity.

Implements the Choi & Okos (1986) temperature-dependent polynomial
correlations for the specific heat of individual food components. These
are the standard baseline correlations used throughout food-process
engineering (see e.g. Rahman, *Food Properties Handbook*; Singh &
Heldman, *Introduction to Food Engineering*) and are explicitly an
empirical fit over -40..150 degC, not a first-principles derivation.

Mixture specific heat is estimated with the standard mass-weighted
additive rule, which assumes the components do not interact
thermodynamically (a good approximation for cp, less good for some other
properties). Stabilisers, emulsifiers, and "other solids" (cocoa, fruit
solids, fibre) are approximated using the Choi-Okos *fibre* correlation,
since minor structural/hydrocolloid carbohydrate-like components are not
separately tabulated.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.formulation.composition import Composition


def cp_water_liquid_j_kg_k(temp_c: float) -> float:
    """Choi-Okos specific heat of liquid water, J/(kg K)."""
    return 4176.2 - 9.0864e-2 * temp_c + 5.4731e-3 * temp_c**2


def cp_ice_j_kg_k(temp_c: float) -> float:
    """Choi-Okos specific heat of ice, J/(kg K). Valid for temp_c <= 0."""
    return 2062.3 + 6.0769 * temp_c


def cp_protein_j_kg_k(temp_c: float) -> float:
    return 2008.2 + 1.2089 * temp_c - 1.3129e-3 * temp_c**2


def cp_fat_j_kg_k(temp_c: float) -> float:
    return 1984.2 + 1.4733 * temp_c - 4.8008e-3 * temp_c**2


def cp_carbohydrate_j_kg_k(temp_c: float) -> float:
    return 1548.8 + 1.9625 * temp_c - 5.9399e-3 * temp_c**2


def cp_fibre_j_kg_k(temp_c: float) -> float:
    return 1845.9 + 1.8306 * temp_c - 4.6509e-3 * temp_c**2


def cp_ash_j_kg_k(temp_c: float) -> float:
    return 1092.6 + 1.8896 * temp_c - 3.6817e-3 * temp_c**2


@dataclass(frozen=True, slots=True)
class MixtureCpResult:
    cp_j_kg_k: float
    unfrozen_water_kg: float
    ice_kg: float


def mixture_specific_heat_j_kg_k(
    composition: Composition,
    temp_c: float,
    unfrozen_water_kg: float,
    ice_kg: float,
) -> float:
    """Mass-weighted mixture specific heat at a given temperature and phase split.

    ``unfrozen_water_kg`` / ``ice_kg`` should come from
    :mod:`icecream_x.thermodynamics.ice_fraction` and must sum to
    ``composition.water_kg``. This is the *sensible* (true) specific heat
    at fixed phase fraction -- it does not include the latent-heat
    contribution of ice melting/freezing as temperature changes, which is
    handled separately as the *apparent* specific heat in
    :mod:`icecream_x.thermodynamics.enthalpy`.
    """
    total = composition.total_mass_kg
    if total <= 0:
        return cp_water_liquid_j_kg_k(temp_c)

    non_fibre_other = composition.other_solids_kg + composition.stabiliser_kg + composition.emulsifier_kg

    weighted = (
        unfrozen_water_kg * cp_water_liquid_j_kg_k(temp_c)
        + ice_kg * cp_ice_j_kg_k(temp_c)
        + composition.fat_kg * cp_fat_j_kg_k(temp_c)
        + composition.protein_kg * cp_protein_j_kg_k(temp_c)
        + (composition.sugar_kg + composition.lactose_kg) * cp_carbohydrate_j_kg_k(temp_c)
        + composition.mineral_kg * cp_ash_j_kg_k(temp_c)
        + non_fibre_other * cp_fibre_j_kg_k(temp_c)
    )
    return weighted / total
