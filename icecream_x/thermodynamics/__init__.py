"""Thermodynamics engine: freezing point, ice fraction, enthalpy, heat transfer properties."""

from __future__ import annotations

from icecream_x.thermodynamics.enthalpy import (
    apparent_specific_heat_j_kg_k,
    enthalpy_state,
    specific_enthalpy_j_kg,
    temperature_from_enthalpy_k,
)
from icecream_x.thermodynamics.freezing_point import freezing_point_analysis, initial_freezing_point_k
from icecream_x.thermodynamics.ice_fraction import PhaseState, phase_state_at_temperature
from icecream_x.thermodynamics.phase_equilibrium import ThermalState, evaluate

__all__ = [
    "apparent_specific_heat_j_kg_k",
    "enthalpy_state",
    "specific_enthalpy_j_kg",
    "temperature_from_enthalpy_k",
    "freezing_point_analysis",
    "initial_freezing_point_k",
    "PhaseState",
    "phase_state_at_temperature",
    "ThermalState",
    "evaluate",
]
