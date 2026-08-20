"""
Modular wake-loss model for tidal-stream turbine arrays.

``WakeModel`` is an abstract base so higher-fidelity models (large-eddy
simulation surrogates, CFD-trained correction factors, etc.) can be dropped
in later without touching :class:`ArrayWakeCalculator` or the array
optimiser that consumes it. :class:`JensenWakeModel` implements the
classic Jensen/Park top-hat wake model, adapted for a tidal current
(bounded channel) rather than open-air wind flow.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


class WakeModel(ABC):
    """Interface every wake model must implement."""

    @abstractmethod
    def calculate_loss(
        self,
        upstream_velocity_ms: float,
        distance_m: float,
        rotor_diameter_m: float,
        ambient_turbulence: float = 0.1,
    ) -> float:
        """Return the fractional velocity deficit (0 = no loss, 1 = fully
        blocked) experienced by a turbine ``distance_m`` downstream of an
        upstream turbine."""

        raise NotImplementedError


@dataclass
class JensenWakeModel(WakeModel):
    """Jensen (Park) wake model: a linearly expanding wake cone with a
    top-hat velocity deficit, decaying with downstream distance and
    expanding at rate ``wake_decay_constant`` (higher ambient turbulence ->
    faster wake recovery -> a larger effective decay constant)."""

    wake_decay_constant: float = 0.05

    def wake_diameter(self, distance_m: float, rotor_diameter_m: float) -> float:
        return rotor_diameter_m + 2 * self.wake_decay_constant * distance_m

    def calculate_loss(
        self,
        upstream_velocity_ms: float,
        distance_m: float,
        rotor_diameter_m: float,
        ambient_turbulence: float = 0.1,
    ) -> float:
        if distance_m <= 0:
            return 0.0
        k = self.wake_decay_constant * (1.0 + ambient_turbulence)
        deficit = (1 - np.sqrt(max(1 - 0.593, 0.0))) * (rotor_diameter_m / (rotor_diameter_m + 2 * k * distance_m)) ** 2
        return float(np.clip(deficit, 0.0, 1.0))


def downstream_recovery(deficit: float, distance_m: float, recovery_length_scale_m: float) -> float:
    """Exponential downstream recovery of a wake deficit, for wake models
    that separate "peak deficit" from "recovery with distance" instead of
    encoding both in a single closed-form expression."""

    return deficit * np.exp(-distance_m / max(recovery_length_scale_m, 1e-6))


@dataclass
class ArrayWakeCalculator:
    """Computes effective inflow velocity at every turbine in an array,
    given turbine positions, an ambient current direction, and a
    :class:`WakeModel`. Wake deficits from multiple upstream turbines are
    combined by sum-of-squares superposition (the standard approach for
    combining independent wakes)."""

    wake_model: WakeModel
    rotor_diameter_m: float

    def effective_velocities(
        self,
        positions_m: np.ndarray,  # shape (n_turbines, 2): [along-flow, cross-flow]
        ambient_velocity_ms: float,
        ambient_turbulence: float = 0.1,
    ) -> np.ndarray:
        positions = np.asarray(positions_m, dtype=float)
        n = len(positions)
        effective = np.full(n, ambient_velocity_ms, dtype=float)

        for i in range(n):
            deficits_sq = 0.0
            for j in range(n):
                if i == j:
                    continue
                along = positions[i, 0] - positions[j, 0]
                cross = abs(positions[i, 1] - positions[j, 1])
                if along <= 0:
                    continue  # j is not upstream of i
                if cross > self.rotor_diameter_m * 1.5:
                    continue  # outside the wake cone (approximate)
                deficit = self.wake_model.calculate_loss(ambient_velocity_ms, along, self.rotor_diameter_m, ambient_turbulence)
                deficits_sq += deficit**2
            combined_deficit = np.sqrt(deficits_sq)
            effective[i] = ambient_velocity_ms * (1 - min(combined_deficit, 1.0))

        return effective

    def array_output_mw(
        self,
        positions_m: np.ndarray,
        ambient_velocity_ms: float,
        turbine,  # hydroflux.tidal.stream.TidalStreamTurbine
        ambient_turbulence: float = 0.1,
    ) -> np.ndarray:
        """Per-turbine power (MW) after wake losses. Demonstrates that
        adding turbines to an array does not increase output linearly:
        downstream machines see a reduced effective velocity and therefore
        cubically reduced available power."""

        velocities = self.effective_velocities(positions_m, ambient_velocity_ms, ambient_turbulence)
        return turbine.power_curve(velocities)
