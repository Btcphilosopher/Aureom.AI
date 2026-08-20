"""
Tidal stream (underwater current turbine) model.

Kinetic power available in a tidal current:

    P_available = 0.5 * rho * A * v^3

A turbine only extracts a fraction of this (the power coefficient, Cp,
capped by the Betz limit of ~0.593 for an idealised rotor) between cut-in
and rated speed, holds rated power between rated and cut-out speed, and
produces nothing outside [cut_in, cut_out].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

import numpy as np

from hydroflux.core.config import TidalStreamConfig
from hydroflux.hydraulics.hydraulics import RHO_SEAWATER

ArrayLike = Union[float, np.ndarray]


def swept_area(rotor_diameter_m: float) -> float:
    return np.pi * (rotor_diameter_m / 2.0) ** 2


def kinetic_power(velocity_ms: ArrayLike, area_m2: float, rho: float = RHO_SEAWATER) -> ArrayLike:
    """Total kinetic power flux through the rotor swept area, watts."""

    v = np.asarray(velocity_ms, dtype=float)
    return 0.5 * rho * area_m2 * np.abs(v) ** 3


@dataclass
class TidalStreamTurbine:
    rotor_diameter_m: float
    rated_power_mw: float
    cut_in_speed_ms: float
    rated_speed_ms: float
    cut_out_speed_ms: float
    power_coefficient: float = 0.42
    drivetrain_efficiency: float = 0.93
    seawater_density_kgm3: float = RHO_SEAWATER

    @property
    def area_m2(self) -> float:
        return swept_area(self.rotor_diameter_m)

    def power_curve(self, velocity_ms: ArrayLike) -> ArrayLike:
        """Electrical power output, MW, as a function of current speed."""

        v = np.abs(np.asarray(velocity_ms, dtype=float))
        p_available = kinetic_power(v, self.area_m2, self.seawater_density_kgm3)
        p_extracted = p_available * self.power_coefficient * self.drivetrain_efficiency / 1e6  # MW

        rated_speed_power = self.rated_power_mw
        power = np.where(v < self.cut_in_speed_ms, 0.0, p_extracted)
        power = np.where(v >= self.rated_speed_ms, rated_speed_power, power)
        power = np.where(v >= self.cut_out_speed_ms, 0.0, power)
        power = np.minimum(power, rated_speed_power)
        return power if power.ndim else float(power)

    @classmethod
    def from_config(cls, config: TidalStreamConfig) -> "TidalStreamTurbine":
        return cls(
            rotor_diameter_m=config.rotor_diameter_m,
            rated_power_mw=config.rated_power_mw,
            cut_in_speed_ms=config.cut_in_speed_ms,
            rated_speed_ms=config.rated_speed_ms,
            cut_out_speed_ms=config.cut_out_speed_ms,
            power_coefficient=config.power_coefficient,
            drivetrain_efficiency=config.drivetrain_efficiency,
            seawater_density_kgm3=config.seawater_density_kgm3,
        )


def current_velocity_series(t_hours: ArrayLike, mean_speed_ms: float, amplitude_ms: float, period_hours: float, phase_rad: float = 0.0) -> ArrayLike:
    """Simplified tidal-stream current speed model: |harmonic|, since flood
    and ebb currents both produce usable (bidirectional or bidirectionally
    rectified) flow through the rotor."""

    t = np.asarray(t_hours, dtype=float)
    return np.abs(mean_speed_ms + amplitude_ms * np.sin(2 * np.pi * t / period_hours + phase_rad))
