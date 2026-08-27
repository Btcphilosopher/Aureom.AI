"""Ice-fraction (freezing curve) model.

Given the freezing-point-depression model in
:mod:`icecream_x.thermodynamics.freezing_point`, this module computes how
much of the mix's water is frozen at any temperature below the initial
freezing point.

**Derivation.** As the mix cools below its initial freezing point
``Tf0``, ice crystallises out and the solutes concentrate in the
remaining unfrozen (serum) water. Assuming local equilibrium, the
unfrozen liquid at system temperature ``T`` must itself be exactly at its
own freezing point, i.e. its solute molality ``m(T)`` satisfies

    T = T_pure - Kf * m(T)          =>          m(T) = (T_pure - T) / Kf

Since ``m(T) = solute_moles / unfrozen_water_kg(T)`` and the total solute
moles are conserved (only water changes phase; solutes stay dissolved in
the liquid), this rearranges to a closed form:

    unfrozen_water_kg(T) = solute_moles * Kf / (T_pure - T)

with ``ice_kg(T) = total_water_kg - unfrozen_water_kg(T)``, clipped to
``[0, total_water_kg]``.

This idealised freezing curve is the same one implicit in the freezing
point model: it inherits the ideal-solution assumption and will diverge
from measured freezing curves at high solute concentration or very low
temperature (it asymptotes ``unfrozen_water -> 0`` as ``T -> -inf``,
whereas real systems reach a maximally-freeze-concentrated / glassy state
at a finite temperature -- an effect this baseline model does not
capture). It is expected to be replaced with an empirical or
activity-corrected freezing curve where precision matters; the rest of
the engine only depends on this module's function signatures.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.formulation.composition import Composition
from icecream_x.thermodynamics.freezing_point import (
    WATER_CRYOSCOPIC_CONSTANT_K_KG_PER_MOL,
    initial_freezing_point_k,
    total_colligative_solute_moles,
)


@dataclass(frozen=True, slots=True)
class PhaseState:
    """The full multi-phase breakdown of a mix at one temperature."""

    temperature_k: float
    ice_kg: float
    unfrozen_water_kg: float
    fat_kg: float
    solids_non_fat_kg: float
    total_mass_kg: float
    air_mass_kg: float = 0.0

    @property
    def temperature_c(self) -> float:
        return self.temperature_k - 273.15

    @property
    def ice_mass_fraction(self) -> float:
        return self.ice_kg / self.total_mass_kg if self.total_mass_kg > 0 else 0.0

    @property
    def unfrozen_water_mass_fraction(self) -> float:
        return self.unfrozen_water_kg / self.total_mass_kg if self.total_mass_kg > 0 else 0.0

    @property
    def fat_mass_fraction(self) -> float:
        return self.fat_kg / self.total_mass_kg if self.total_mass_kg > 0 else 0.0

    @property
    def solids_non_fat_mass_fraction(self) -> float:
        return self.solids_non_fat_kg / self.total_mass_kg if self.total_mass_kg > 0 else 0.0

    def summary(self) -> dict[str, float]:
        return {
            "temperature_c": round(self.temperature_c, 3),
            "ice_fraction_pct": round(100 * self.ice_mass_fraction, 2),
            "unfrozen_water_pct": round(100 * self.unfrozen_water_mass_fraction, 2),
            "solids_pct": round(100 * self.solids_non_fat_mass_fraction, 2),
            "fat_pct": round(100 * self.fat_mass_fraction, 2),
        }


def unfrozen_water_kg_at_temperature(
    temperature_k: float, solute_moles: float, total_water_kg: float, freezing_point_k: float
) -> float:
    """Closed-form unfrozen water mass at a given temperature. See module docstring."""
    pure_water_freeze_k = 273.15
    if temperature_k >= freezing_point_k:
        return total_water_kg
    denom = pure_water_freeze_k - temperature_k
    if denom <= 0:
        return total_water_kg
    unfrozen = solute_moles * WATER_CRYOSCOPIC_CONSTANT_K_KG_PER_MOL / denom
    return min(max(unfrozen, 0.0), total_water_kg)


def d_unfrozen_water_d_temperature(
    temperature_k: float, solute_moles: float, freezing_point_k: float
) -> float:
    """Analytic d(unfrozen_water_kg)/dT [kg/K], used for the apparent-cp latent-heat term.

    Zero above the initial freezing point (no phase change occurring).
    """
    pure_water_freeze_k = 273.15
    if temperature_k >= freezing_point_k:
        return 0.0
    denom = pure_water_freeze_k - temperature_k
    if denom <= 0:
        return 0.0
    return solute_moles * WATER_CRYOSCOPIC_CONSTANT_K_KG_PER_MOL / denom**2


def phase_state_at_temperature(composition: Composition, temperature_k: float) -> PhaseState:
    """Compute the full phase breakdown of ``composition`` at ``temperature_k``."""
    if composition.water_kg <= 0:
        unfrozen = 0.0
    else:
        tf0 = initial_freezing_point_k(composition)
        solute_moles = total_colligative_solute_moles(composition)
        unfrozen = unfrozen_water_kg_at_temperature(
            temperature_k, solute_moles, composition.water_kg, tf0
        )
    ice = composition.water_kg - unfrozen
    solids_non_fat = (
        composition.protein_kg
        + composition.lactose_kg
        + composition.sugar_kg
        + composition.mineral_kg
        + composition.stabiliser_kg
        + composition.emulsifier_kg
        + composition.other_solids_kg
    )
    return PhaseState(
        temperature_k=temperature_k,
        ice_kg=ice,
        unfrozen_water_kg=unfrozen,
        fat_kg=composition.fat_kg,
        solids_non_fat_kg=solids_non_fat,
        total_mass_kg=composition.total_mass_kg,
        air_mass_kg=composition.air_mass_kg,
    )


def ice_fraction_curve(
    composition: Composition, temperatures_k: list[float]
) -> list[PhaseState]:
    """Convenience helper: phase state across a list of temperatures (a freezing curve)."""
    return [phase_state_at_temperature(composition, t) for t in temperatures_k]
