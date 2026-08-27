"""Ageing: quiescent cold hold before freezing.

During ageing, the mix is held cold (typically 2-4 degC) for several
hours. Physically, this allows: fat to begin crystallising (some of the
"solid fat fraction" the fat-network model already computes as a
function of temperature), stabilisers/hydrocolloids to fully hydrate
(increasing serum viscosity), and milk proteins to adsorb onto the newly
homogenised fat globule surface. Full hydrocolloid/protein kinetics are
out of scope for this baseline engine; the modelled effect is a small,
time-bounded head start on fat destabilisation (representing the onset of
crystallisation-driven globule clustering before any freezer shear is
applied), capped well below what shear-driven destabilisation in the
freezer produces.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.core.events import EventLog
from icecream_x.core.state import ProcessStage, ProductState
from icecream_x.microstructure.fat_network import FatNetworkState, solid_fat_fraction
from icecream_x.thermodynamics.enthalpy import specific_enthalpy_j_kg
from icecream_x.utils.units import celsius_to_kelvin
from icecream_x.utils.validation import require_non_negative

#: Maximum destabilisation degree attributable to quiescent ageing alone
#: (shear-driven destabilisation in the freezer dominates the total).
MAX_AGEING_DESTABILISATION = 0.05
#: Time constant for the ageing destabilisation onset, seconds (~4 hours).
AGEING_TIME_CONSTANT_S = 4.0 * 3600.0


@dataclass(frozen=True, slots=True)
class AgeingResult:
    final_state: ProductState
    energy_j: float


def age(
    state: ProductState,
    ageing_temperature_c: float,
    ageing_time_s: float,
    *,
    reference_temperature_k: float = 213.15,
    event_log: EventLog | None = None,
) -> AgeingResult:
    require_non_negative(ageing_time_s, "ageing_time_s")
    comp = state.composition
    t_target_k = celsius_to_kelvin(ageing_temperature_c)

    h_start = specific_enthalpy_j_kg(comp, state.temperature_k, reference_temperature_k)
    h_target = specific_enthalpy_j_kg(comp, t_target_k, reference_temperature_k)
    cooling_energy_j = comp.total_mass_kg * (h_target - h_start)  # negative if cooling

    onset_progress = 1.0 - pow(2.718281828, -ageing_time_s / AGEING_TIME_CONSTANT_S)
    destabilisation = MAX_AGEING_DESTABILISATION * onset_progress

    existing_fat = state.microstructure.fat_network
    if existing_fat is not None:
        new_fat = FatNetworkState(
            globule_diameter_um=existing_fat.globule_diameter_um,
            destabilisation_degree=max(existing_fat.destabilisation_degree, destabilisation),
            solid_fat_fraction=solid_fat_fraction(ageing_temperature_c),
        )
        new_microstructure = state.microstructure.with_fat_network(new_fat)
    else:
        new_microstructure = state.microstructure

    final_state = state.evolve(
        temperature_k=t_target_k,
        stage=ProcessStage.AGED,
        microstructure=new_microstructure,
        elapsed_time_s=state.elapsed_time_s + ageing_time_s,
        cumulative_energy_j=state.cumulative_energy_j + max(cooling_energy_j, 0.0),
    )

    if event_log is not None:
        event_log.record(
            state.elapsed_time_s,
            ProcessStage.AGED.value,
            f"Aged {ageing_time_s / 3600.0:.1f} h at {ageing_temperature_c:.1f} degC",
            destabilisation_degree=round(destabilisation, 4),
        )

    return AgeingResult(final_state=final_state, energy_j=max(cooling_energy_j, 0.0))
