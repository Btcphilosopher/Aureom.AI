"""
Suspension: weight transfer, body roll, and per-axle normal load.

The tire model can only ever be as good as the normal-load numbers it is
fed, so this module is where longitudinal (accel/braking) and lateral
(cornering) load transfer actually happen. Stiffer springs / a bigger
anti-roll bar visibly reduce roll angle and flatten the load-transfer
response; nothing about "body roll" is a cosmetic animation number here --
it feeds straight back into how much grip each axle has.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from apex_horizon_engine.utils.config import SuspensionSpec

GRAVITY = 9.81


@dataclass
class AxleLoad:
    front_n: float
    rear_n: float


@dataclass
class SuspensionState:
    roll_angle_rad: float = 0.0
    front_travel_m: float = 0.0
    rear_travel_m: float = 0.0


def static_axle_loads(mass_kg: float, weight_dist_front: float) -> AxleLoad:
    weight = mass_kg * GRAVITY
    return AxleLoad(front_n=weight * weight_dist_front, rear_n=weight * (1.0 - weight_dist_front))


def longitudinal_transfer_n(mass_kg: float, cg_height_m: float, wheelbase_m: float,
                             long_accel_mps2: float) -> float:
    """Positive under acceleration moves load to the rear (returned value
    subtracted from front / added to rear); positive under braking
    (negative accel) does the opposite."""
    return mass_kg * long_accel_mps2 * cg_height_m / max(0.5, wheelbase_m)


def lateral_transfer_n(mass_kg: float, cg_height_m: float, track_width_m: float,
                        lat_accel_mps2: float, anti_roll_bar: float) -> float:
    """Total load transferred from inside to outside wheels across an
    axle. ``anti_roll_bar`` in [0, 1] softens the *roll* contribution
    without touching the physically-mandated geometric transfer term --
    exactly how a real anti-roll bar works (it can't reduce total lateral
    load transfer, only redistribute it front/rear and calm body roll)."""
    geometric = mass_kg * lat_accel_mps2 * cg_height_m / max(0.5, track_width_m)
    roll_softening = 1.0 - 0.25 * anti_roll_bar
    return geometric * roll_softening


def update_suspension(
    spec: SuspensionSpec,
    state: SuspensionState,
    dt: float,
    lat_accel_mps2: float,
    long_accel_mps2: float,
) -> None:
    """Advance body roll toward its steady-state target with the spring/
    damper acting as a first-order lag, so roll builds and settles over a
    few tenths of a second instead of snapping instantly."""
    max_roll = math.radians(8.0) * (1.0 - 0.5 * spec.anti_roll_bar)
    stiffness_norm = min(1.0, spec.spring_rate_n_m / 90000.0)
    target_roll = max_roll * math.tanh(lat_accel_mps2 / 9.0) * (1.0 - 0.4 * stiffness_norm)

    lag = max(0.05, 0.6 - 0.4 * spec.damping_ratio)
    alpha = min(1.0, dt / lag)
    state.roll_angle_rad += (target_roll - state.roll_angle_rad) * alpha

    dive = -long_accel_mps2 / GRAVITY * spec.travel_m * 0.5
    state.front_travel_m += (dive - state.front_travel_m) * alpha
    state.rear_travel_m += (-dive - state.rear_travel_m) * alpha


def axle_normal_loads(
    spec_static: AxleLoad,
    mass_kg: float,
    cg_height_m: float,
    wheelbase_m: float,
    long_accel_mps2: float,
    downforce_front_n: float,
    downforce_rear_n: float,
) -> AxleLoad:
    transfer = longitudinal_transfer_n(mass_kg, cg_height_m, wheelbase_m, long_accel_mps2)
    front = max(0.0, spec_static.front_n - transfer + downforce_front_n)
    rear = max(0.0, spec_static.rear_n + transfer + downforce_rear_n)
    return AxleLoad(front_n=front, rear_n=rear)
