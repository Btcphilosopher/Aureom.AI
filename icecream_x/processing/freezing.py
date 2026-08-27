"""Freezing: the scraped-surface freezer barrel.

Simultaneously removes heat (freezing part of the water into ice),
applies intense mechanical shear (whipping air in -- see
:mod:`icecream_x.processing.aeration` -- and driving fat destabilisation),
and sets the initial ice-crystal population. This is the central,
most numerically demanding unit operation: the product passes through
its freezing point during the barrel residence time, so the
enthalpy-method timestepper (:mod:`icecream_x.core.timestep`) is used
throughout to remain stable across the phase transition.

Wall shear rate is estimated from scraper rotational speed and an assumed
scraper-to-wall clearance -- a simplified proxy standing in for a full
computational-rheology treatment of the scraped boundary layer, sufficient
to drive the (also simplified) fat-destabilisation and air-cell-size
models with a physically reasonable, monotonic shear signal.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.core.events import EventLog
from icecream_x.core.state import ProcessStage, ProductState
from icecream_x.core.timestep import enthalpy_step, time_grid
from icecream_x.equipment.freezer import ScrapedSurfaceFreezer
from icecream_x.microstructure.fat_network import (
    FatNetworkState,
    destabilisation_degree as fat_destabilisation,
    solid_fat_fraction,
)
from icecream_x.microstructure.ice_crystals import IceCrystalState, initial_crystal_state
from icecream_x.thermodynamics.enthalpy import EnthalpyTable
from icecream_x.thermodynamics.phase_equilibrium import evaluate as evaluate_thermal
from icecream_x.utils.units import celsius_to_kelvin

#: Assumed scraper-blade-to-barrel-wall clearance, m -- used only to convert
#: rotational scraper speed into an order-of-magnitude wall shear rate.
SCRAPER_CLEARANCE_M = 0.003
ICE_FRACTION_ONSET_THRESHOLD = 1e-4


@dataclass(frozen=True, slots=True)
class FreezingResult:
    final_state: ProductState
    duration_s: float
    energy_removed_j: float
    refrigeration_energy_j: float
    freezing_rate_c_per_s: float
    wall_shear_rate_1_per_s: float
    trajectory: list[ProductState]


def _wall_shear_rate_1_per_s(freezer: ScrapedSurfaceFreezer) -> float:
    import math

    angular_speed_rad_s = 2.0 * math.pi * freezer.scraper_speed_rpm / 60.0
    wall_speed_m_s = angular_speed_rad_s * (freezer.barrel_diameter_m / 2.0)
    return wall_speed_m_s / SCRAPER_CLEARANCE_M


def freeze(
    state: ProductState,
    freezer: ScrapedSurfaceFreezer,
    target_outlet_temperature_c: float,
    *,
    reference_temperature_k: float = 213.15,
    dt_s: float = 1.0,
    refrigeration_cop: float = 1.8,
    event_log: EventLog | None = None,
) -> FreezingResult:
    """Simulate transient cooling/shearing through the freezer barrel.

    ``refrigeration_cop`` is the assumed coefficient of performance of
    the refrigeration system supplying the barrel jacket, used to convert
    heat removed from the product into electrical energy consumed
    (electrical_kWh = heat_removed_kWh / COP).
    """
    comp = state.composition
    batch_mass_kg = comp.total_mass_kg
    density0 = evaluate_thermal(comp, state.temperature_k).density_kg_m3
    duration_s = freezer.residence_time_s(freezer.design_throughput_kg_s, density0)

    # The barrel's heat-transfer duty (h*A*dT) acts on whatever mass is
    # physically inside the barrel at any instant -- the "holdup" mass --
    # not on the full recipe/batch mass. In continuous flow that holdup is
    # simply barrel_volume * density, and every kg of product experiences
    # the same intensive (per-kg) thermal history during its residence
    # time regardless of how large the overall batch being processed is.
    # We therefore integrate temperature using the holdup mass, then apply
    # the resulting (intensive) enthalpy change to the full batch mass for
    # energy accounting below.
    holdup_mass_kg = freezer.barrel_volume_m3 * density0

    t_refrigerant_k = celsius_to_kelvin(freezer.refrigerant_temperature_c)
    h_coefficient = freezer.heat_transfer_coefficient_w_m2_k()
    area = freezer.heat_transfer_area_m2
    shear_rate = _wall_shear_rate_1_per_s(freezer)

    enthalpy_table = EnthalpyTable(comp, reference_temperature_k)
    grid = time_grid(duration_s, dt_s)
    trajectory: list[ProductState] = []
    t_k = state.temperature_k
    shear_exposure = state.cumulative_shear_exposure
    ice_crystals: IceCrystalState | None = state.microstructure.ice_crystals
    onset_temp_c: float | None = None
    onset_time_s: float | None = None

    for i, t_offset in enumerate(grid):
        heat_rate_w = h_coefficient * area * (t_refrigerant_k - t_k)
        step_dt = grid[i + 1] - t_offset if i + 1 < len(grid) else 0.0
        if step_dt > 0:
            result = enthalpy_step(
                comp,
                t_k,
                heat_rate_w,
                holdup_mass_kg,
                step_dt,
                reference_temperature_k,
                table=enthalpy_table,
            )
            t_k = result.temperature_k
        shear_exposure += shear_rate * step_dt

        phase = evaluate_thermal(comp, t_k).phase
        if onset_temp_c is None and phase.ice_mass_fraction > ICE_FRACTION_ONSET_THRESHOLD:
            onset_temp_c = t_k - 273.15
            onset_time_s = t_offset

        trajectory.append(
            state.evolve(
                temperature_k=t_k,
                stage=ProcessStage.FROZEN,
                cumulative_shear_exposure=shear_exposure,
                elapsed_time_s=state.elapsed_time_s + t_offset,
            )
        )
        if t_k - 273.15 <= target_outlet_temperature_c:
            break

    final_t_k = t_k
    final_time_s = trajectory[-1].elapsed_time_s - state.elapsed_time_s if trajectory else 0.0

    if onset_temp_c is not None and onset_time_s is not None and final_time_s > onset_time_s:
        freezing_rate = abs(onset_temp_c - (final_t_k - 273.15)) / max(
            final_time_s - onset_time_s, 1e-6
        )
    else:
        freezing_rate = abs(state.temperature_c - (final_t_k - 273.15)) / max(final_time_s, 1e-6)

    if ice_crystals is None and freezing_rate > 0:
        ice_crystals = initial_crystal_state(freezing_rate)

    fractions = comp.as_fractions()
    fat_state = state.microstructure.fat_network
    new_destab = fat_destabilisation(
        shear_exposure, fractions["emulsifier"], initial_degree=(fat_state.destabilisation_degree if fat_state else 0.0)
    )
    new_fat_state = FatNetworkState(
        globule_diameter_um=fat_state.globule_diameter_um if fat_state else 1.0,
        destabilisation_degree=new_destab,
        solid_fat_fraction=solid_fat_fraction(final_t_k - 273.15),
    )

    new_microstructure = (
        state.microstructure.with_ice_crystals(ice_crystals).with_fat_network(new_fat_state)
    )

    h0 = enthalpy_table.specific_enthalpy_j_kg(state.temperature_k)
    h1 = enthalpy_table.specific_enthalpy_j_kg(final_t_k)
    energy_removed_j = batch_mass_kg * (h0 - h1)  # positive: heat removed
    refrigeration_energy_j = max(energy_removed_j, 0.0) / refrigeration_cop

    final_state = state.evolve(
        temperature_k=final_t_k,
        stage=ProcessStage.FROZEN,
        microstructure=new_microstructure,
        cumulative_shear_exposure=shear_exposure,
        elapsed_time_s=state.elapsed_time_s + final_time_s,
        cumulative_energy_j=state.cumulative_energy_j + refrigeration_energy_j,
    )

    if event_log is not None:
        event_log.record(
            state.elapsed_time_s,
            ProcessStage.FROZEN.value,
            f"Frozen in {freezer.name}",
            outlet_temperature_c=round(final_t_k - 273.15, 2),
            ice_fraction_pct=round(100 * evaluate_thermal(comp, final_t_k).phase.ice_mass_fraction, 1),
            duration_s=round(final_time_s, 1),
            freezing_rate_c_per_min=round(freezing_rate * 60.0, 3),
            refrigeration_energy_kwh=round(refrigeration_energy_j / 3_600_000.0, 4),
        )

    return FreezingResult(
        final_state=final_state,
        duration_s=final_time_s,
        energy_removed_j=energy_removed_j,
        refrigeration_energy_j=refrigeration_energy_j,
        freezing_rate_c_per_s=freezing_rate,
        wall_shear_rate_1_per_s=shear_rate,
        trajectory=trajectory,
    )
