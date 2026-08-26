"""
Steering "brain" for background traffic and generic NPC path-following.

Deliberately simple (proportional steering toward a target point, speed
governed by a target + following-distance rule) -- this is the low end of
the AI stack; ``ai.racer_ai`` builds genuine racing-line and overtaking
behaviour on top of the same primitives for event opponents.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from apex_horizon_engine.vehicles.vehicle_model import VehicleControls, VehicleState


@dataclass
class SteerTarget:
    x: float
    y: float
    speed_limit_mps: float


def heading_error_to_point(state: VehicleState, target_x: float, target_y: float) -> float:
    dx = target_x - state.x
    dy = target_y - state.y
    desired_heading = math.atan2(dy, dx)
    error = desired_heading - state.heading_rad
    # wrap to [-pi, pi]
    return (error + math.pi) % (2 * math.pi) - math.pi


def follow_point_controls(
    state: VehicleState,
    target: SteerTarget,
    steer_gain: float = 1.6,
    lead_distance_ahead_m: float = 0.0,
    obstacle_gap_m: Optional[float] = None,
) -> VehicleControls:
    """Return throttle/brake/steer that chases ``target`` while respecting
    its speed limit and (optionally) backing off for a vehicle ahead."""
    heading_err = heading_error_to_point(state, target.x, target.y)
    steer = max(-1.0, min(1.0, heading_err * steer_gain))

    speed = state.speed_mps
    speed_error = target.speed_limit_mps - speed

    throttle = 0.0
    brake = 0.0
    if obstacle_gap_m is not None and obstacle_gap_m < 12.0:
        brake = min(1.0, (12.0 - obstacle_gap_m) / 12.0)
    elif speed_error > 0.5:
        throttle = min(1.0, speed_error / 4.0)
    elif speed_error < -1.0:
        brake = min(0.8, -speed_error / 6.0)

    # Ease off the throttle in a hard turn -- traffic doesn't try to
    # power through a corner at full send.
    throttle *= max(0.25, 1.0 - abs(steer) * 0.6)

    return VehicleControls(throttle=throttle, brake=brake, steering=steer)
