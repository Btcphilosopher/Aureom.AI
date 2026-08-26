"""
Broad/narrow-phase collision detection and impulse resolution for the
open world (vehicle-vehicle, vehicle-traffic, vehicle-scenery).

Bodies are approximated as oriented capsules projected to circles for
broad phase (cheap enough to run against hundreds of world.traffic_system
vehicles every tick) with a proper 2D impulse resolution so a collision
actually changes both bodies' velocities based on mass and closing speed,
instead of one side just stopping dead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class CircleBody:
    body_id: str
    x: float
    y: float
    radius_m: float
    mass_kg: float
    vx: float
    vy: float


@dataclass
class CollisionInfo:
    a_id: str
    b_id: str
    penetration_m: float
    normal_x: float
    normal_y: float
    impact_speed_mps: float


def detect_collision(a: CircleBody, b: CircleBody) -> Optional[CollisionInfo]:
    dx = b.x - a.x
    dy = b.y - a.y
    dist = math.hypot(dx, dy)
    min_dist = a.radius_m + b.radius_m
    if dist >= min_dist or dist < 1e-6:
        return None
    nx, ny = dx / dist, dy / dist
    rel_vx, rel_vy = b.vx - a.vx, b.vy - a.vy
    closing_speed = -(rel_vx * nx + rel_vy * ny)
    return CollisionInfo(
        a_id=a.body_id, b_id=b.body_id,
        penetration_m=min_dist - dist,
        normal_x=nx, normal_y=ny,
        impact_speed_mps=max(0.0, closing_speed),
    )


def resolve_collision(a: CircleBody, b: CircleBody, info: CollisionInfo, restitution: float = 0.25) -> None:
    """Mutates ``a`` and ``b`` velocities in place (elastic-ish impulse
    resolution) and separates overlapping bodies along the contact
    normal so they don't keep re-triggering next tick."""
    nx, ny = info.normal_x, info.normal_y
    rel_vx = b.vx - a.vx
    rel_vy = b.vy - a.vy
    vel_along_normal = rel_vx * nx + rel_vy * ny
    if vel_along_normal > 0:
        return  # already separating

    inv_mass_a = 1.0 / max(1.0, a.mass_kg)
    inv_mass_b = 1.0 / max(1.0, b.mass_kg)
    j = -(1.0 + restitution) * vel_along_normal / (inv_mass_a + inv_mass_b)
    # A packed cluster of overlapping bodies (heavy traffic, a pursuit
    # pile-up) can otherwise chain sequential-impulse pairs into an
    # unbounded velocity kick within one tick; cap the single-collision
    # delta-v to something no real bumper-to-bumper hit would exceed.
    j = max(-25000.0, min(25000.0, j))

    a.vx -= j * inv_mass_a * nx
    a.vy -= j * inv_mass_a * ny
    b.vx += j * inv_mass_b * nx
    b.vy += j * inv_mass_b * ny

    penetration = min(info.penetration_m, 2.5)
    correction = max(0.0, penetration - 0.01) / (inv_mass_a + inv_mass_b) * 0.8
    a.x -= correction * inv_mass_a * nx
    a.y -= correction * inv_mass_a * ny
    b.x += correction * inv_mass_b * nx
    b.y += correction * inv_mass_b * ny


def impulse_magnitude(a_mass_kg: float, b_mass_kg: float, impact_speed_mps: float) -> float:
    """Rough scalar impulse magnitude (N-s) handed to ``damage_model`` --
    reduced mass x closing speed, the standard two-body collision measure."""
    reduced_mass = (a_mass_kg * b_mass_kg) / max(1.0, a_mass_kg + b_mass_kg)
    return reduced_mass * impact_speed_mps


def grid_cell(x: float, y: float, cell_size_m: float = 50.0) -> tuple[int, int]:
    """Spatial hash cell for broad-phase bucketing across a large open
    world -- used by world.traffic_system to only test collisions between
    bodies sharing/adjacent cells instead of an O(n^2) sweep."""
    return int(math.floor(x / cell_size_m)), int(math.floor(y / cell_size_m))
