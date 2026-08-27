"""Homogenisation: fat globule size reduction and emulsion formation."""

from __future__ import annotations

from icecream_x.core.events import EventLog
from icecream_x.core.state import ProcessStage, ProductState
from icecream_x.equipment.homogeniser import Homogeniser
from icecream_x.microstructure.fat_network import (
    FatNetworkState,
    homogenised_globule_diameter_um,
    solid_fat_fraction,
)
from icecream_x.utils.validation import require_positive


def homogenise(
    state: ProductState,
    homogeniser: Homogeniser,
    *,
    mass_flow_kg_s: float,
    event_log: EventLog | None = None,
) -> ProductState:
    require_positive(mass_flow_kg_s, "mass_flow_kg_s")
    diameter_um = homogenised_globule_diameter_um(homogeniser)
    fat_state = FatNetworkState(
        globule_diameter_um=diameter_um,
        destabilisation_degree=0.0,
        solid_fat_fraction=solid_fat_fraction(state.temperature_c),
    )
    new_microstructure = state.microstructure.with_fat_network(fat_state)

    process_time_s = state.composition.total_mass_kg / mass_flow_kg_s
    energy_j = homogeniser.motor_power_kw * 1000.0 * process_time_s

    new_state = state.evolve(
        stage=ProcessStage.HOMOGENISED,
        microstructure=new_microstructure,
        elapsed_time_s=state.elapsed_time_s + process_time_s,
        cumulative_energy_j=state.cumulative_energy_j + energy_j,
    )

    if event_log is not None:
        event_log.record(
            state.elapsed_time_s,
            ProcessStage.HOMOGENISED.value,
            f"Homogenised via {homogeniser.name} at {homogeniser.total_pressure_bar:.0f} bar",
            globule_diameter_um=round(diameter_um, 3),
            passes=homogeniser.passes,
            energy_kwh=round(energy_j / 3_600_000.0, 4),
        )
    return new_state
