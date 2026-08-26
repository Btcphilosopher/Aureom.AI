"""
Traffic population manager: keeps a bounded, streaming-radius-scoped set
of ``world.npc_drivers.NPCDriver`` instances alive around the player,
matching each zone's ``traffic_density`` from ``utils.config``, and runs
broad-phase collision against them every tick.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from apex_horizon_engine.physics.collision import CircleBody, detect_collision, impulse_magnitude, resolve_collision
from apex_horizon_engine.physics.damage_model import apply_collision_damage
from apex_horizon_engine.physics.traction_model import SurfaceCondition
from apex_horizon_engine.utils.config import ZoneSpec
from apex_horizon_engine.utils.logging import get_logger
from apex_horizon_engine.world.npc_drivers import NPCDriver, spawn_npc_driver

logger = get_logger("world.traffic")

MAX_ACTIVE_TRAFFIC = 24
VEHICLE_COLLISION_RADIUS_M = 1.6


@dataclass
class TrafficSystem:
    zones: Dict[str, ZoneSpec]
    seed: int = 0
    active: List[NPCDriver] = field(default_factory=list)
    _next_id: int = 0
    _rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self):
        self._rng = random.Random(self.seed)

    def _target_population(self, zone: ZoneSpec, streaming_radius_m: float) -> int:
        area_km2 = math.pi * (min(zone.radius_m, streaming_radius_m) / 1000.0) ** 2
        return min(MAX_ACTIVE_TRAFFIC, max(0, round(zone.traffic_density * area_km2 * 0.15)))

    def update_population(self, active_zone: ZoneSpec, streaming_radius_m: float) -> None:
        target = self._target_population(active_zone, streaming_radius_m)
        current_in_zone = [n for n in self.active if n.zone_id == active_zone.zone_id]

        while len(current_in_zone) < target and len(self.active) < MAX_ACTIVE_TRAFFIC:
            npc = spawn_npc_driver(f"npc_{self._next_id}", active_zone, self._rng)
            self._next_id += 1
            self.active.append(npc)
            current_in_zone.append(npc)

        # Despawn NPCs far outside every zone's streaming range (cheap:
        # only drop from zones no longer active to keep this O(active)).
        self.active = [n for n in self.active
                       if n.zone_id == active_zone.zone_id or len(self.active) <= MAX_ACTIVE_TRAFFIC // 2]

    def step(self, dt: float, condition_by_zone: Dict[str, SurfaceCondition],
             extra_obstacles: Optional[List[tuple]] = None) -> None:
        """``extra_obstacles`` is an optional list of (x, y) points --
        typically just the player -- included in the proactive braking
        check below, so ambient traffic actually slows for the player's
        car instead of only reacting to a collision after the fact."""
        obstacles = list(extra_obstacles or [])
        positions = [(n.vehicle.state.x, n.vehicle.state.y) for n in self.active]
        for i, npc in enumerate(self.active):
            condition = condition_by_zone.get(npc.zone_id, SurfaceCondition(base_grip=1.0))
            nearest_gap = None
            for j, (ox, oy) in enumerate(positions + obstacles):
                if j == i:
                    continue
                d = math.hypot(ox - npc.vehicle.state.x, oy - npc.vehicle.state.y)
                if nearest_gap is None or d < nearest_gap:
                    nearest_gap = d
            npc.step(dt, condition, obstacle_gap_m=nearest_gap)
        self._resolve_traffic_collisions()

    def _resolve_traffic_collisions(self) -> None:
        bodies = [
            CircleBody(n.npc_id, n.vehicle.state.x, n.vehicle.state.y, VEHICLE_COLLISION_RADIUS_M,
                       n.vehicle.spec.mass_kg, n.vehicle.state.vx, n.vehicle.state.vy)
            for n in self.active
        ]
        by_id = {n.npc_id: n for n in self.active}
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                info = detect_collision(bodies[i], bodies[j])
                if info is None:
                    continue
                resolve_collision(bodies[i], bodies[j], info)
                impulse = impulse_magnitude(bodies[i].mass_kg, bodies[j].mass_kg, info.impact_speed_mps)
                for body in (bodies[i], bodies[j]):
                    npc = by_id[body.body_id]
                    apply_collision_damage(npc.vehicle.state.damage, impulse)
                    npc.vehicle.state.x, npc.vehicle.state.y = body.x, body.y
                    npc.vehicle.state.vx, npc.vehicle.state.vy = body.vx, body.vy
                    # Resync wheel spin to the post-impact body speed --
                    # see core.engine._resolve_player_traffic_collision
                    # for why this matters.
                    w = body.vx / npc.vehicle.wheel_radius_m
                    npc.vehicle.state.w_front = w
                    npc.vehicle.state.w_rear = w

    def check_player_collision(self, player_x: float, player_y: float, player_radius_m: float = 1.7) -> Optional[NPCDriver]:
        for npc in self.active:
            dist = math.hypot(npc.vehicle.state.x - player_x, npc.vehicle.state.y - player_y)
            if dist < player_radius_m + VEHICLE_COLLISION_RADIUS_M:
                return npc
        return None
