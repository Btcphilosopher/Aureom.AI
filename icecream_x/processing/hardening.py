"""Hardening: blast-tunnel cooling to a stable, storable temperature.

Continues the enthalpy-method cooling simulation from the freezer outlet
state down to the hardening target (typically -18 to -25 degC), using
forced-convection heat transfer against the tunnel air.

A meaningful fraction of the total ice formation happens during
hardening, not just in the freezer barrel -- at freezer outlet (~-5 degC)
a typical mix is only ~50% frozen; by -18 degC it is ~75-80% frozen (see
the worked example in :mod:`icecream_x.thermodynamics.ice_fraction`).
This continued ice growth is modelled as spherical growth of the
*existing* crystal population (crystal *number* set at nucleation in the
freezer stays fixed; each crystal simply accretes more ice), which gives
the physically sensible scaling ``d ~ ice_fraction ** (1/3)`` for a fixed
number density -- distinct from the Ostwald-ripening
(:mod:`icecream_x.microstructure.ice_crystals`) recrystallisation growth
that dominates during storage.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.core.events import EventLog
from icecream_x.core.state import ProcessStage, ProductState
from icecream_x.core.timestep import enthalpy_step, time_grid
from icecream_x.equipment.hardening_tunnel import HardeningTunnel
from icecream_x.microstructure.ice_crystals import IceCrystalState
from icecream_x.thermodynamics.enthalpy import EnthalpyTable
from icecream_x.thermodynamics.phase_equilibrium import evaluate as evaluate_thermal
from icecream_x.utils.units import celsius_to_kelvin


@dataclass(frozen=True, slots=True)
class HardeningResult:
    final_state: ProductState
    duration_s: float
    energy_removed_j: float
    refrigeration_energy_j: float
    trajectory: list[ProductState]


def harden(
    state: ProductState,
    tunnel: HardeningTunnel,
    target_temperature_c: float,
    package_half_thickness_m: float = 0.04,
    *,
    reference_temperature_k: float = 213.15,
    dt_s: float = 5.0,
    refrigeration_cop: float = 1.5,
    event_log: EventLog | None = None,
) -> HardeningResult:
    comp = state.composition
    mass = comp.total_mass_kg
    t_air_k = celsius_to_kelvin(tunnel.air_temperature_c)

    # Heat transfer area per unit mass for a slab package geometry, using
    # its own current density and the tunnel's convective coefficient
    # applied across both faces of the slab.
    density0 = evaluate_thermal(comp, state.temperature_k).density_kg_m3
    volume_m3 = mass / density0
    face_area_m2 = volume_m3 / (2.0 * package_half_thickness_m)
    total_area_m2 = 2.0 * face_area_m2

    initial_phase = evaluate_thermal(comp, state.temperature_k).phase
    ice_fraction_initial = max(initial_phase.ice_mass_fraction, 1e-6)

    enthalpy_table = EnthalpyTable(comp, reference_temperature_k)
    grid = time_grid(tunnel.transit_time_s, dt_s)
    trajectory: list[ProductState] = []
    t_k = state.temperature_k

    for i, t_offset in enumerate(grid):
        heat_rate_w = tunnel.heat_transfer_coefficient_w_m2_k * total_area_m2 * (t_air_k - t_k)
        step_dt = grid[i + 1] - t_offset if i + 1 < len(grid) else 0.0
        if step_dt > 0:
            result = enthalpy_step(
                comp, t_k, heat_rate_w, mass, step_dt, reference_temperature_k, table=enthalpy_table
            )
            t_k = result.temperature_k
        trajectory.append(
            state.evolve(
                temperature_k=t_k,
                stage=ProcessStage.HARDENED,
                elapsed_time_s=state.elapsed_time_s + t_offset,
            )
        )
        if t_k - 273.15 <= target_temperature_c:
            break

    final_time_s = trajectory[-1].elapsed_time_s - state.elapsed_time_s if trajectory else 0.0
    final_phase = evaluate_thermal(comp, t_k).phase
    ice_fraction_final = max(final_phase.ice_mass_fraction, ice_fraction_initial)

    existing_crystals = state.microstructure.ice_crystals
    if existing_crystals is not None:
        growth_ratio = (ice_fraction_final / ice_fraction_initial) ** (1.0 / 3.0)
        new_crystals = IceCrystalState(
            mean_diameter_um=existing_crystals.mean_diameter_um * growth_ratio,
            distribution_cv=existing_crystals.distribution_cv,
        )
    else:
        new_crystals = None

    new_microstructure = (
        state.microstructure.with_ice_crystals(new_crystals) if new_crystals else state.microstructure
    )

    h0 = enthalpy_table.specific_enthalpy_j_kg(state.temperature_k)
    h1 = enthalpy_table.specific_enthalpy_j_kg(t_k)
    energy_removed_j = mass * (h0 - h1)
    refrigeration_energy_j = max(energy_removed_j, 0.0) / refrigeration_cop

    final_state = state.evolve(
        temperature_k=t_k,
        stage=ProcessStage.HARDENED,
        microstructure=new_microstructure,
        elapsed_time_s=state.elapsed_time_s + final_time_s,
        cumulative_energy_j=state.cumulative_energy_j + refrigeration_energy_j,
    )

    if event_log is not None:
        event_log.record(
            state.elapsed_time_s,
            ProcessStage.HARDENED.value,
            f"Hardened in {tunnel.name}",
            final_temperature_c=round(t_k - 273.15, 2),
            ice_fraction_pct=round(100 * final_phase.ice_mass_fraction, 1),
            duration_s=round(final_time_s, 1),
            refrigeration_energy_kwh=round(refrigeration_energy_j / 3_600_000.0, 4),
        )

    return HardeningResult(
        final_state=final_state,
        duration_s=final_time_s,
        energy_removed_j=energy_removed_j,
        refrigeration_energy_j=refrigeration_energy_j,
        trajectory=trajectory,
    )
