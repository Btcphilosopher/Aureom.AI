"""
Optional simplified sediment module.

Estimates sediment transport capacity (Engelund-Hansen-style total load
formula), and a basic erosion-risk index from the ratio of flow velocity to
a grain-size-dependent critical (Shields) velocity. Kept intentionally
modular and simple -- swap in a higher-fidelity sediment/morphodynamic model
by implementing the same functions without touching callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

import numpy as np
import pandas as pd

ArrayLike = Union[float, np.ndarray]

_G = 9.80665
_RHO_WATER = 1000.0
_RHO_SEDIMENT = 2650.0  # quartz sand, kg/m3


def shields_parameter(velocity_ms: ArrayLike, grain_size_m: float, depth_m: ArrayLike) -> ArrayLike:
    """Dimensionless Shields parameter estimated from a simplified
    depth-slope-friction relationship (shear velocity ~ velocity / friction
    proxy)."""

    v = np.asarray(velocity_ms, dtype=float)
    depth = np.maximum(np.asarray(depth_m, dtype=float), 0.05)
    shear_velocity = v * 0.1 / np.log(np.maximum(depth / grain_size_m, 1.01))
    tau = _RHO_WATER * shear_velocity**2
    return tau / ((_RHO_SEDIMENT - _RHO_WATER) * _G * grain_size_m)


def critical_shields_parameter(grain_size_m: float) -> float:
    """Approximate critical Shields parameter (Shields curve, coarse-grain
    asymptote ~0.06, fine-grain asymptote ~0.03)."""

    return float(np.clip(0.03 + 0.03 * np.log10(max(grain_size_m, 1e-6) / 1e-4 + 1), 0.02, 0.06))


def erosion_risk_index(velocity_ms: ArrayLike, grain_size_m: float, depth_m: ArrayLike) -> ArrayLike:
    """Ratio of the actual to critical Shields parameter; > 1 means the bed
    material is mobile (erosion risk)."""

    theta = shields_parameter(velocity_ms, grain_size_m, depth_m)
    theta_c = critical_shields_parameter(grain_size_m)
    return theta / theta_c


def sediment_transport_rate(
    velocity_ms: ArrayLike,
    depth_m: ArrayLike,
    grain_size_m: float,
    channel_width_m: float,
) -> ArrayLike:
    """Simplified Engelund-Hansen total-load sediment transport rate,
    kg/s, for a wide channel: q_s ~ 0.05 * rho_s * v^5 / (sqrt(g) * (s-1)^2 * d50 * C^3)
    with a Chezy coefficient C estimated from depth/grain size."""

    v = np.asarray(velocity_ms, dtype=float)
    depth = np.maximum(np.asarray(depth_m, dtype=float), 0.05)
    s = _RHO_SEDIMENT / _RHO_WATER
    chezy = 18 * np.log10(12 * depth / (grain_size_m if grain_size_m > 0 else 1e-4))
    chezy = np.maximum(chezy, 5.0)

    unit_transport = (
        0.05 * _RHO_SEDIMENT * np.abs(v) ** 5 / (np.sqrt(_G) * (s - 1) ** 2 * grain_size_m * chezy**3)
    )
    return unit_transport * channel_width_m


@dataclass
class SedimentSimulationResult:
    transport_rate_kgs: pd.Series
    erosion_risk_index: pd.Series


class SedimentModel:
    def __init__(self, grain_size_m: float = 0.002, channel_width_m: float = 30.0, channel_depth_m: float = 3.0):
        self.grain_size_m = grain_size_m
        self.channel_width_m = channel_width_m
        self.channel_depth_m = channel_depth_m

    def simulate(self, flow_m3s: pd.Series) -> SedimentSimulationResult:
        velocity = flow_m3s.values / (self.channel_width_m * self.channel_depth_m)
        transport = sediment_transport_rate(velocity, self.channel_depth_m, self.grain_size_m, self.channel_width_m)
        risk = erosion_risk_index(velocity, self.grain_size_m, self.channel_depth_m)
        return SedimentSimulationResult(
            transport_rate_kgs=pd.Series(transport, index=flow_m3s.index),
            erosion_risk_index=pd.Series(risk, index=flow_m3s.index),
        )
