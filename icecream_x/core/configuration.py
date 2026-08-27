"""Simulation configuration.

A single, validated, serialisable object controlling numerical and
environmental parameters shared across a simulation run. Kept separate
from any one recipe/process-profile so the same configuration can drive
many different experiments (see :mod:`icecream_x.scenarios.experiments`).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from icecream_x.utils.units import celsius_to_kelvin

#: Reference temperature for enthalpy calculations: cold enough that
#: essentially all freezable water is ice for any realistic mix, so
#: enthalpy differences between any two process temperatures are well
#: defined and consistent across the whole simulation.
DEFAULT_ENTHALPY_REFERENCE_C = -60.0


class SimulationConfig(BaseModel, frozen=True):
    random_seed: int = 42
    default_timestep_s: float = 1.0
    enthalpy_reference_temperature_c: float = DEFAULT_ENTHALPY_REFERENCE_C
    ambient_temperature_c: float = 22.0
    electricity_price_per_kwh: float = 0.20
    log_every_n_steps: int = 1

    @property
    def enthalpy_reference_temperature_k(self) -> float:
        return celsius_to_kelvin(self.enthalpy_reference_temperature_c)

    @property
    def ambient_temperature_k(self) -> float:
        return celsius_to_kelvin(self.ambient_temperature_c)


DEFAULT_CONFIG = SimulationConfig()
