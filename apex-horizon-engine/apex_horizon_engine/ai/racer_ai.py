"""
Racing AI for event rivals: waypoint/racing-line following with skill-
and aggression-driven cornering, overtaking, and rivalry tracking.

Nothing here is a scripted outcome -- every rival drives the same
``vehicles.vehicle_model.Vehicle`` physics the player does, fed by
controls this module computes fresh each tick from the live race state
(gap to the car ahead, corner geometry, its own skill/aggression/mistake
roll). Two AI racers with identical specs but different ``skill`` values
will simply, honestly, drive differently.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from apex_horizon_engine.vehicles.vehicle_model import Vehicle, VehicleControls, VehicleState


@dataclass
class RaceWaypoint:
    x: float
    y: float
    corner_sharpness: float = 0.0  # 0 = straight, 1 = hairpin


def build_lap_route(center_x: float, center_y: float, radius_m: float, waypoint_count: int,
                     rng: random.Random, irregularity: float = 0.35) -> List[RaceWaypoint]:
    """Procedurally lay out a closed-loop route -- an irregular polygon
    around a centre point, standing in for an actual road spline. Corner
    sharpness at each waypoint is derived from the actual turn angle
    between neighbouring points, so the AI's braking behaviour reacts to
    genuine route geometry rather than tagged metadata."""
    raw: List[Tuple[float, float]] = []
    for i in range(waypoint_count):
        angle = 2 * math.pi * i / waypoint_count
        r = radius_m * (1.0 + rng.uniform(-irregularity, irregularity))
        raw.append((center_x + r * math.cos(angle), center_y + r * math.sin(angle)))

    waypoints: List[RaceWaypoint] = []
    n = len(raw)
    for i in range(n):
        prev_p, cur_p, next_p = raw[(i - 1) % n], raw[i], raw[(i + 1) % n]
        v1 = math.atan2(cur_p[1] - prev_p[1], cur_p[0] - prev_p[0])
        v2 = math.atan2(next_p[1] - cur_p[1], next_p[0] - cur_p[0])
        turn = abs((v2 - v1 + math.pi) % (2 * math.pi) - math.pi)
        sharpness = min(1.0, turn / math.radians(90))
        waypoints.append(RaceWaypoint(cur_p[0], cur_p[1], sharpness))
    return waypoints


@dataclass
class RivalryState:
    grudge: float = 0.0       # rises on contact / being overtaken by the player
    respect: float = 0.5      # rises when the player races clean and fast


@dataclass
class RacerAI:
    racer_id: str
    vehicle: Vehicle
    route: List[RaceWaypoint]
    skill: float = 0.6          # 0..1 -- higher = later braking, tighter line, fewer mistakes
    aggression: float = 0.5     # 0..1 -- higher = more willing to trade paint overtaking
    archetype: str = "balanced"  # "drift_focused" | "highway_aggressive" | "technical" | "balanced"
    waypoint_index: int = 0
    laps_completed: int = 0
    rivalry: RivalryState = field(default_factory=RivalryState)
    _rng: random.Random = field(default_factory=random.Random)
    _mistake_cooldown_s: float = 0.0

    def _lookahead_speed_mps(self, sharpness: float) -> float:
        base_max = 46.0
        skill_bonus = self.skill * 8.0
        corner_penalty = sharpness * (30.0 - self.skill * 12.0)
        return max(8.0, base_max + skill_bonus - corner_penalty)

    def step(self, dt: float, condition, rival_positions: Optional[List[Tuple[float, float]]] = None) -> VehicleControls:
        state = self.vehicle.state
        wp = self.route[self.waypoint_index]
        dist = math.hypot(wp.x - state.x, wp.y - state.y)
        if dist < 18.0:
            self.waypoint_index += 1
            if self.waypoint_index >= len(self.route):
                self.waypoint_index = 0
                self.laps_completed += 1
            wp = self.route[self.waypoint_index]

        next_wp = self.route[(self.waypoint_index + 1) % len(self.route)]
        heading_err = self._heading_error(state, wp.x, wp.y)
        steer = max(-1.0, min(1.0, heading_err * (1.7 + 0.4 * self.aggression)))

        target_speed = self._lookahead_speed_mps(wp.corner_sharpness)
        # Look one waypoint further to start braking before the apex, not at it.
        if next_wp.corner_sharpness > wp.corner_sharpness and dist < 45.0:
            target_speed = min(target_speed, self._lookahead_speed_mps(next_wp.corner_sharpness) + 6.0)

        speed_error = target_speed - state.speed_mps
        throttle = min(1.0, max(0.0, speed_error / 5.0))
        brake = min(1.0, max(0.0, -speed_error / 8.0))
        throttle *= max(0.3, 1.0 - abs(steer) * (0.5 - 0.2 * self.skill))

        # Occasional unforced error -- lower skill means more frequent,
        # more severe throttle lifts. This is what keeps a field of AI
        # racers from being deterministic laser-line clones.
        self._mistake_cooldown_s -= dt
        if self._mistake_cooldown_s <= 0:
            mistake_chance = (1.0 - self.skill) * 0.02
            if self._rng.random() < mistake_chance:
                throttle *= 0.4
                self._mistake_cooldown_s = self._rng.uniform(0.4, 1.2)
            else:
                self._mistake_cooldown_s = 0.25

        # Overtaking: nudge the racing line toward a gap if a rival is
        # close ahead and this AI is aggressive enough to contest it.
        if rival_positions:
            for rx, ry in rival_positions:
                gap = math.hypot(rx - state.x, ry - state.y)
                ahead = self._heading_error(state, rx, ry)
                if gap < 14.0 and abs(ahead) < math.radians(25) and self.aggression > 0.4:
                    side = 1.0 if ahead >= 0 else -1.0
                    steer = max(-1.0, min(1.0, steer - side * 0.25 * self.aggression))
                    throttle = min(1.0, throttle + 0.1 * self.aggression)

        return VehicleControls(throttle=throttle, brake=brake, steering=steer)

    @staticmethod
    def _heading_error(state: VehicleState, target_x: float, target_y: float) -> float:
        desired = math.atan2(target_y - state.y, target_x - state.x)
        return (desired - state.heading_rad + math.pi) % (2 * math.pi) - math.pi

    def register_contact_with_player(self, impulse_ns: float) -> None:
        self.rivalry.grudge = min(1.0, self.rivalry.grudge + impulse_ns / 60000.0)
        self.aggression = min(1.0, self.aggression + 0.02)

    def register_overtaken_by_player(self, clean: bool) -> None:
        if clean:
            self.rivalry.respect = min(1.0, self.rivalry.respect + 0.03)
        else:
            self.rivalry.grudge = min(1.0, self.rivalry.grudge + 0.08)
