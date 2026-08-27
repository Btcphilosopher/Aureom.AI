"""Cold-chain simulation: a sequence of storage stages.

Each :class:`ColdChainStage` represents one leg of the journey from
hardening to consumption (factory cold store -> transport -> retail
cabinet -> home freezer, or any user-defined sequence). Product core
temperature is driven toward each stage's ambient
:class:`~icecream_x.storage.temperature_history.TemperatureProfile` via a
first-order thermal lag (see
:class:`~icecream_x.storage.freezer.StorageFacility`), and the ice-crystal
population evolves via :mod:`icecream_x.storage.recrystallisation` at
every timestep -- so a stage with a brief excursion produces a measurably
different final crystal size than an uninterrupted stage of the same
average temperature, as required.

Energy accounting here is a simplified constant-hold-power draw
(``facility.refrigeration_power_kw`` for the stage duration) rather than
a detailed heat-leak/door-opening load calculation; see
:mod:`icecream_x.economics.energy_cost` for how this feeds into
manufacturing/distribution economics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from icecream_x.core.events import EventLog
from icecream_x.core.state import ProcessStage, ProductState
from icecream_x.core.timestep import time_grid
from icecream_x.storage.freezer import StorageFacility
from icecream_x.storage.recrystallisation import step_recrystallisation
from icecream_x.storage.temperature_history import TemperatureProfile, uninterrupted
from icecream_x.utils.units import celsius_to_kelvin


@dataclass(slots=True)
class ColdChainStage:
    name: str
    facility: StorageFacility
    duration_s: float
    temperature_profile: TemperatureProfile | None = None

    def profile(self) -> TemperatureProfile:
        return self.temperature_profile or uninterrupted(self.facility.setpoint_temperature_c)


@dataclass(slots=True)
class ColdChainResult:
    final_state: ProductState
    temperature_history_c: list[tuple[float, float]] = field(default_factory=list)
    ice_crystal_diameter_history_um: list[tuple[float, float]] = field(default_factory=list)
    total_energy_j: float = 0.0


def simulate_cold_chain(
    state: ProductState,
    stages: list[ColdChainStage],
    *,
    dt_s: float = 300.0,
    event_log: EventLog | None = None,
) -> ColdChainResult:
    current = state
    temp_history: list[tuple[float, float]] = []
    crystal_history: list[tuple[float, float]] = []
    total_energy_j = 0.0
    cumulative_t_s = 0.0

    for stage in stages:
        profile = stage.profile()
        tau = stage.facility.thermal_lag_time_constant_s
        product_temp_c = current.temperature_c
        grid = time_grid(stage.duration_s, dt_s)

        for i, t_offset in enumerate(grid):
            ambient_c = profile.temperature_at(t_offset)
            step_dt = grid[i + 1] - t_offset if i + 1 < len(grid) else 0.0
            if tau > 0 and step_dt > 0:
                product_temp_c = ambient_c + (product_temp_c - ambient_c) * math.exp(-step_dt / tau)
            else:
                product_temp_c = ambient_c

            cycling_amplitude = profile.active_excursion_amplitude_c(t_offset)
            new_crystals = step_recrystallisation(
                current, celsius_to_kelvin(product_temp_c), step_dt, cycling_amplitude
            )
            new_microstructure = (
                current.microstructure.with_ice_crystals(new_crystals)
                if new_crystals is not None
                else current.microstructure
            )
            current = current.evolve(
                temperature_k=celsius_to_kelvin(product_temp_c),
                stage=ProcessStage.STORED,
                microstructure=new_microstructure,
                elapsed_time_s=current.elapsed_time_s + step_dt,
            )
            temp_history.append((cumulative_t_s + t_offset, product_temp_c))
            if new_crystals is not None:
                crystal_history.append((cumulative_t_s + t_offset, new_crystals.mean_diameter_um))

        stage_energy_j = stage.facility.refrigeration_power_kw * 1000.0 * stage.duration_s
        total_energy_j += stage_energy_j
        cumulative_t_s += stage.duration_s
        current = current.evolve(cumulative_energy_j=current.cumulative_energy_j + stage_energy_j)

        if event_log is not None:
            event_log.record(
                current.elapsed_time_s,
                ProcessStage.STORED.value,
                f"Completed cold-chain stage '{stage.name}' ({stage.facility.name})",
                duration_h=round(stage.duration_s / 3600.0, 2),
                final_product_temperature_c=round(product_temp_c, 2),
            )

    return ColdChainResult(
        final_state=current,
        temperature_history_c=temp_history,
        ice_crystal_diameter_history_um=crystal_history,
        total_energy_j=total_energy_j,
    )
