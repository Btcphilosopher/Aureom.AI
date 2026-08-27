"""Phase-equilibrium orchestrator.

Ties together the freezing-point, ice-fraction, specific-heat and
thermal-conductivity models into a single convenience call that returns
every thermodynamic property of interest at one (composition,
temperature) point. This is the primary entry point the rest of the
engine (processing steps, the simulation loop) should use rather than
calling the individual thermodynamics submodules directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.formulation.composition import Composition
from icecream_x.thermodynamics.freezing_point import (
    FreezingPointResult,
    freezing_point_analysis,
)
from icecream_x.thermodynamics.heat_capacity import mixture_specific_heat_j_kg_k
from icecream_x.thermodynamics.ice_fraction import PhaseState, phase_state_at_temperature
from icecream_x.thermodynamics.thermal_conductivity import (
    mixture_density_kg_m3,
    mixture_thermal_conductivity_w_m_k,
)


@dataclass(frozen=True, slots=True)
class ThermalState:
    phase: PhaseState
    freezing_point: FreezingPointResult
    specific_heat_j_kg_k: float
    thermal_conductivity_w_m_k: float
    density_kg_m3: float


def evaluate(composition: Composition, temperature_k: float) -> ThermalState:
    """Evaluate the full thermodynamic state of ``composition`` at ``temperature_k``."""
    fp = freezing_point_analysis(composition)
    phase = phase_state_at_temperature(composition, temperature_k)
    temp_c = temperature_k - 273.15
    cp = mixture_specific_heat_j_kg_k(composition, temp_c, phase.unfrozen_water_kg, phase.ice_kg)
    k = mixture_thermal_conductivity_w_m_k(
        composition, temp_c, phase.unfrozen_water_kg, phase.ice_kg
    )
    rho = mixture_density_kg_m3(composition, temp_c, phase.unfrozen_water_kg, phase.ice_kg)
    return ThermalState(
        phase=phase,
        freezing_point=fp,
        specific_heat_j_kg_k=cp,
        thermal_conductivity_w_m_k=k,
        density_kg_m3=rho,
    )
