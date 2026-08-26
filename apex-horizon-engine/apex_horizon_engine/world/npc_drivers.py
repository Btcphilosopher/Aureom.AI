"""
Ambient NPC drivers: the background population that makes the world feel
inhabited even when nothing is racing. Each one owns a real
``vehicles.vehicle_model.Vehicle`` (so it participates in the same
physics/collision/damage systems as the player) and a tiny patrol route
it loops around within its home zone.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import List

from apex_horizon_engine.ai.traffic_ai import SteerTarget, follow_point_controls
from apex_horizon_engine.physics.traction_model import SurfaceCondition
from apex_horizon_engine.utils.config import ZoneSpec, get_vehicle_preset
from apex_horizon_engine.vehicles.vehicle_model import Vehicle

_TRAFFIC_PRESETS = ["meridian_gt_hatch", "ironclad_v8_muscle", "outrider_rally"]


@dataclass
class NPCDriver:
    npc_id: str
    vehicle: Vehicle
    zone_id: str
    waypoints: List[tuple[float, float]]
    waypoint_index: int = 0
    speed_limit_mps: float = 22.0

    def current_target(self) -> SteerTarget:
        wx, wy = self.waypoints[self.waypoint_index]
        return SteerTarget(wx, wy, self.speed_limit_mps)

    def step(self, dt: float, condition: SurfaceCondition, obstacle_gap_m: float | None = None) -> None:
        target = self.current_target()
        dist = math.hypot(target.x - self.vehicle.state.x, target.y - self.vehicle.state.y)
        if dist < 20.0:
            self.waypoint_index = (self.waypoint_index + 1) % len(self.waypoints)
            target = self.current_target()
        controls = follow_point_controls(self.vehicle.state, target, obstacle_gap_m=obstacle_gap_m)
        self.vehicle.step(dt, controls, condition)


def _random_point_in_zone(zone: ZoneSpec, rng: random.Random) -> tuple[float, float]:
    angle = rng.uniform(0, 2 * math.pi)
    radius = rng.uniform(0.1, 0.85) * zone.radius_m
    return zone.center_xy[0] + radius * math.cos(angle), zone.center_xy[1] + radius * math.sin(angle)


def spawn_npc_driver(npc_id: str, zone: ZoneSpec, rng: random.Random, waypoint_count: int = 4) -> NPCDriver:
    preset_id = rng.choice(_TRAFFIC_PRESETS)
    vehicle = Vehicle(get_vehicle_preset(preset_id))
    waypoints = [_random_point_in_zone(zone, rng) for _ in range(waypoint_count)]
    vehicle.state.x, vehicle.state.y = waypoints[0]
    speed_limit = rng.uniform(14.0, 28.0) if zone.kind.value != "megacity" else rng.uniform(9.0, 18.0)
    return NPCDriver(npc_id=npc_id, vehicle=vehicle, zone_id=zone.zone_id,
                      waypoints=waypoints, speed_limit_mps=speed_limit)
