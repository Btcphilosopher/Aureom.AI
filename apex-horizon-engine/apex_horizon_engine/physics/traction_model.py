"""
Traction resolution: combines a tire compound + per-wheel runtime state +
axle normal load + surface condition into actual forces.

This is the seam between "generic physics" and "this specific car" -- it
owns surface-grip modelling (wet/dry/sand/gravel) so that weather and
terrain type are the *only* things that can change how much grip is on
the table before the tire model's slip curve takes over.
"""

from __future__ import annotations

from dataclasses import dataclass

from apex_horizon_engine.utils.config import TireCompound
from apex_horizon_engine.vehicles.tire_model import WheelTireState, compute_tire_forces


@dataclass
class SurfaceCondition:
    base_grip: float        # zone baseline, e.g. 1.0 tarmac, 0.82 sand (from ZoneSpec)
    wetness: float = 0.0    # 0 = bone dry, 1 = standing water
    off_road: bool = False
    surface_temp_c: float = 22.0


def surface_grip_multiplier(condition: SurfaceCondition) -> float:
    """Non-linear wetness penalty: the first bit of rain costs relatively
    little (damp but still mostly grippy), while standing water costs a
    lot -- aquaplaning territory. Off-road surfaces get a flat additional
    penalty on top since tires here aren't designed for loose grit."""
    wet_penalty = 1.0 - (0.18 * condition.wetness + 0.55 * (condition.wetness ** 2))
    offroad_penalty = 0.72 if condition.off_road else 1.0
    cold_track_penalty = 1.0 - max(0.0, (10.0 - condition.surface_temp_c)) * 0.004
    return max(0.15, condition.base_grip * wet_penalty * offroad_penalty * cold_track_penalty)


def resolve_axle_forces(
    compound: TireCompound,
    wheel_state: WheelTireState,
    normal_load_n: float,
    slip_ratio: float,
    slip_angle_deg: float,
    condition: SurfaceCondition,
) -> tuple[float, float, float]:
    """Return ``(Fx_n, Fy_n, slip_severity)`` in the wheel's own frame."""
    grip_mult = surface_grip_multiplier(condition)
    return compute_tire_forces(compound, wheel_state, normal_load_n, slip_ratio, slip_angle_deg, grip_mult)


def rolling_resistance_force_n(total_normal_load_n: float, crr: float = 0.013) -> float:
    return crr * total_normal_load_n
