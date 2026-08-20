"""
Hydraulic physics engine.

Core relationship (never treated as delivered electrical power on its own):

    P_hydraulic = rho * g * Q * H

Delivered *electrical* power additionally applies turbine, generator and
transmission efficiency, each of which is itself a function of operating
conditions elsewhere in the engine (see :mod:`hydroflux.turbines.turbines`):

    P_electrical = P_hydraulic * eta_turbine * eta_generator * eta_transmission

This module also implements the dynamic net-head model:

    net_head = gross_head - penstock_losses - intake_losses - tailwater_effects
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

import numpy as np

ArrayLike = Union[float, np.ndarray]

#: Standard gravitational acceleration, m/s^2
G = 9.80665

#: Fresh water density, kg/m^3 (varies slightly with temperature; treated as
#: constant here -- a temperature-dependent density model can be substituted
#: without touching the rest of the engine).
RHO_WATER = 1000.0

#: Typical seawater density, kg/m^3 (tidal systems).
RHO_SEAWATER = 1025.0


def theoretical_power(flow_m3s: ArrayLike, head_m: ArrayLike, rho: float = RHO_WATER) -> ArrayLike:
    """Theoretical (100% efficient) hydraulic power, in watts.

    This is the *theoretical potential* -- see
    :class:`hydroflux.core.engine.GenerationPotential`. It is never reported
    as deliverable electrical output on its own.
    """

    flow = np.asarray(flow_m3s, dtype=float)
    head = np.maximum(np.asarray(head_m, dtype=float), 0.0)
    return rho * G * flow * head


def hydraulic_power(flow_m3s: ArrayLike, head_m: ArrayLike, efficiency: ArrayLike = 1.0, rho: float = RHO_WATER) -> ArrayLike:
    """Hydraulic power delivered to the turbine shaft, P = rho g Q H eta."""

    return theoretical_power(flow_m3s, head_m, rho=rho) * np.asarray(efficiency, dtype=float)


def electrical_power(
    flow_m3s: ArrayLike,
    head_m: ArrayLike,
    turbine_efficiency: ArrayLike,
    generator_efficiency: float = 0.98,
    transmission_efficiency: float = 0.99,
    rho: float = RHO_WATER,
) -> ArrayLike:
    """Net electrical power delivered to the grid connection point, in watts.

    This chains turbine -> generator -> transmission efficiency onto the
    hydraulic power so theoretical hydraulic power is never conflated with
    delivered electrical power.
    """

    p_hyd = hydraulic_power(flow_m3s, head_m, efficiency=turbine_efficiency, rho=rho)
    return p_hyd * generator_efficiency * transmission_efficiency


def penstock_loss(
    flow_m3s: ArrayLike,
    length_m: float,
    diameter_m: float,
    friction_factor: float = 0.015,
    minor_loss_coefficient: float = 0.0,
) -> ArrayLike:
    """Darcy-Weisbach head loss through a penstock/pipe, in metres.

    h_f = f * (L / D) * v^2 / (2g), plus optional minor (fittings/bends)
    losses h_m = K * v^2 / (2g).
    """

    flow = np.asarray(flow_m3s, dtype=float)
    area = np.pi * (diameter_m / 2.0) ** 2
    velocity = flow / area
    velocity_head = velocity**2 / (2 * G)
    friction_loss = friction_factor * (length_m / diameter_m) * velocity_head
    minor_loss = minor_loss_coefficient * velocity_head
    return friction_loss + minor_loss


def intake_loss(flow_m3s: ArrayLike, area_m2: float, loss_coefficient: float = 0.15) -> ArrayLike:
    """Intake/trash-rack head loss, K * v^2 / (2g)."""

    flow = np.asarray(flow_m3s, dtype=float)
    velocity = flow / area_m2
    return loss_coefficient * velocity**2 / (2 * G)


def channel_loss(flow_m3s: ArrayLike, length_m: float, width_m: float, manning_n: float = 0.025, slope: float = 0.0005) -> ArrayLike:
    """Simplified open-channel friction loss using Manning's equation for a
    wide rectangular channel (hydraulic radius approx = depth)."""

    flow = np.asarray(flow_m3s, dtype=float)
    depth = np.maximum(flow / (width_m * np.sqrt(max(slope, 1e-6)) / manning_n) ** (3 / 5), 0.1)
    hydraulic_radius = (width_m * depth) / (width_m + 2 * depth)
    velocity = flow / (width_m * depth)
    friction_slope = (manning_n * velocity) ** 2 / hydraulic_radius ** (4 / 3)
    return friction_slope * length_m


def net_head(
    gross_head_m: ArrayLike,
    penstock_losses_m: ArrayLike = 0.0,
    intake_losses_m: ArrayLike = 0.0,
    tailwater_effect_m: ArrayLike = 0.0,
) -> ArrayLike:
    """net_head = gross_head - penstock_losses - intake_losses - tailwater_effects.

    Never negative (a turbine cannot operate below zero head).
    """

    h = (
        np.asarray(gross_head_m, dtype=float)
        - np.asarray(penstock_losses_m, dtype=float)
        - np.asarray(intake_losses_m, dtype=float)
        - np.asarray(tailwater_effect_m, dtype=float)
    )
    return np.maximum(h, 0.0)


@dataclass
class HeadModel:
    """Dynamic head calculation for a conventional/run-of-river hydro plant.

    Computes net head as operating conditions change: reservoir elevation
    (via a storage-elevation relationship), tailwater elevation (which can
    itself vary with downstream flow / drawdown), and hydraulic losses
    through the penstock and intake.
    """

    penstock_length_m: float
    penstock_diameter_m: float
    penstock_friction_factor: float = 0.015
    intake_area_m2: Optional[float] = None
    intake_loss_coefficient: float = 0.15
    tailwater_rating_curve: Optional[callable] = None  # flow_m3s -> tailwater elevation_m

    def __post_init__(self):
        if self.intake_area_m2 is None:
            self.intake_area_m2 = np.pi * (self.penstock_diameter_m / 2.0) ** 2 * 3.0

    def gross_head(self, reservoir_elevation_m: ArrayLike, tailwater_elevation_m: ArrayLike) -> ArrayLike:
        return np.asarray(reservoir_elevation_m, dtype=float) - np.asarray(tailwater_elevation_m, dtype=float)

    def tailwater_elevation(self, flow_m3s: ArrayLike, default_elevation_m: float) -> ArrayLike:
        if self.tailwater_rating_curve is not None:
            return self.tailwater_rating_curve(np.asarray(flow_m3s, dtype=float))
        # Simple monotonic drawdown-free default: tailwater rises slightly
        # with flow (backwater effect), ~0.02 m per (m3/s) above a nominal
        # base flow of 50 m3/s, capped at +3 m.
        flow = np.asarray(flow_m3s, dtype=float)
        rise = np.clip(0.02 * (flow - 50.0), 0.0, 3.0)
        return default_elevation_m + rise

    def net_head(self, flow_m3s: ArrayLike, reservoir_elevation_m: ArrayLike, tailwater_elevation_m: ArrayLike) -> ArrayLike:
        gross = self.gross_head(reservoir_elevation_m, tailwater_elevation_m)
        p_loss = penstock_loss(flow_m3s, self.penstock_length_m, self.penstock_diameter_m, self.penstock_friction_factor)
        i_loss = intake_loss(flow_m3s, self.intake_area_m2, self.intake_loss_coefficient)
        return net_head(gross, p_loss, i_loss, 0.0)
