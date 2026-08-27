"""The generic timestep simulation loop.

The spec calls for an explicit state-transition loop:

    for timestep in simulation:
        update_environment()
        update_formulation_state()
        update_temperature()
        calculate_phase_state()
        calculate_ice_fraction()
        update_viscosity()
        update_microstructure()
        update_air_cells()
        update_energy_balance()
        update_equipment()
        update_storage_history()
        update_quality()
        log_state()

Each *processing* step (mixing, pasteurisation, homogenisation, ageing,
freezing, hardening -- :mod:`icecream_x.processing`) already implements
this pattern internally with a numerical method suited to its own
physics (see each module's docstring), because each is a genuinely
different boundary-value problem (a controlled ramp, a convective
barrel, a slab in a blast tunnel...) and gains little from being forced
through one generic interface.

:class:`Simulation` is where this loop is implemented *literally and
generically*, and it is used for the phase of the product's life that is
naturally open-ended and timestep-driven rather than a fixed unit
operation: cold storage and distribution. It composes
:mod:`icecream_x.storage.cold_chain` for the temperature/microstructure
physics and adds the two steps that module doesn't itself compute --
``update_quality`` (:mod:`icecream_x.analytics.quality`) and
``log_state`` -- producing a full :class:`StateLog` time series suitable
for plotting (:mod:`icecream_x.visualisation`) or DataFrame export.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from icecream_x.analytics.quality import QualityWeights, quality_score
from icecream_x.core.events import EventLog
from icecream_x.core.state import ProcessStage, ProductState
from icecream_x.core.timestep import time_grid
from icecream_x.storage.freezer import StorageFacility
from icecream_x.storage.recrystallisation import step_recrystallisation
from icecream_x.storage.temperature_history import TemperatureProfile, uninterrupted
from icecream_x.utils.units import celsius_to_kelvin


@dataclass(slots=True)
class StateLog:
    """A time series of state summaries + quality scores, one row per logged step."""

    records: list[dict] = field(default_factory=list)

    def append(self, timestamp_s: float, state: ProductState, quality_overall: float) -> None:
        row = {"timestamp_s": timestamp_s, "quality_score": quality_overall}
        row.update(state.summary())
        self.records.append(row)

    def to_dataframe(self):
        import pandas as pd

        return pd.DataFrame.from_records(self.records)


@dataclass(slots=True)
class SimulationResult:
    final_state: ProductState
    state_log: StateLog
    event_log: EventLog


def run_storage_simulation(
    initial_state: ProductState,
    facility: StorageFacility,
    duration_s: float,
    *,
    temperature_profile: TemperatureProfile | None = None,
    dt_s: float = 900.0,
    quality_weights: QualityWeights = QualityWeights(),
    log_every_n_steps: int = 1,
    event_log: EventLog | None = None,
) -> SimulationResult:
    """Run the explicit per-timestep simulation loop over a storage period."""
    log = event_log if event_log is not None else EventLog()
    profile = temperature_profile or uninterrupted(facility.setpoint_temperature_c)
    state_log = StateLog()

    state = initial_state
    product_temp_c = state.temperature_c
    tau = facility.thermal_lag_time_constant_s
    grid = time_grid(duration_s, dt_s)

    for i, t_offset in enumerate(grid):
        # update_environment(): ambient temperature at this instant.
        ambient_c = profile.temperature_at(t_offset)
        cycling_amplitude = profile.active_excursion_amplitude_c(t_offset)

        step_dt = grid[i + 1] - t_offset if i + 1 < len(grid) else 0.0

        # update_formulation_state(): composition is conserved in storage
        # (no ingredient addition/removal); nothing to do, but kept as an
        # explicit no-op step for symmetry with the spec's loop and as the
        # extension point for e.g. modelling moisture migration.
        composition = state.composition

        # update_temperature(): first-order thermal lag toward ambient.
        if tau > 0 and step_dt > 0:
            product_temp_c = ambient_c + (product_temp_c - ambient_c) * math.exp(-step_dt / tau)
        else:
            product_temp_c = ambient_c
        temperature_k = celsius_to_kelvin(product_temp_c)

        # calculate_phase_state() / calculate_ice_fraction(): evaluated
        # lazily via ProductState.thermal_state() below and inside the
        # quality/microstructure steps; no separate mutation needed since
        # ProductState derives phase state on demand from (composition, T).

        # update_viscosity(): likewise derived on demand via
        # ProductState.rheology_state() -- nothing to store here.

        # update_microstructure() / update_air_cells(): ice-crystal
        # recrystallisation responds to temperature and cycling; air-cell
        # population is assumed structurally frozen in place during
        # storage (no further whipping occurs) so is carried forward
        # unchanged.
        new_crystals = step_recrystallisation(state, temperature_k, step_dt, cycling_amplitude)
        microstructure = (
            state.microstructure.with_ice_crystals(new_crystals)
            if new_crystals is not None
            else state.microstructure
        )

        # update_energy_balance(): constant-hold refrigeration draw.
        energy_j = state.cumulative_energy_j + facility.refrigeration_power_kw * 1000.0 * step_dt

        # update_equipment(): storage facility has no dynamic equipment
        # state to evolve in this simplified model (a detailed model could
        # track e.g. defrost cycles or compressor duty here).

        state = state.evolve(
            composition=composition,
            temperature_k=temperature_k,
            stage=ProcessStage.STORED,
            microstructure=microstructure,
            elapsed_time_s=state.elapsed_time_s + step_dt,
            cumulative_energy_j=energy_j,
        )

        # update_storage_history(): handled by the caller/EventLog; a
        # periodic milestone event is emitted below.

        # update_quality() + log_state():
        if i % max(log_every_n_steps, 1) == 0 or i == len(grid) - 1:
            q = quality_score(state, quality_weights)
            state_log.append(t_offset, state, q.overall_score)

        if cycling_amplitude > 0.5:
            log.record(
                state.elapsed_time_s,
                ProcessStage.STORED.value,
                "Temperature excursion active",
                ambient_c=round(ambient_c, 2),
                product_c=round(product_temp_c, 2),
            )

    return SimulationResult(final_state=state, state_log=state_log, event_log=log)
