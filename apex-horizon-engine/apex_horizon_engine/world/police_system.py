"""
Police pursuit system: a heat meter driven by observed infractions
(speeding through a megacity, collisions, off-road/illegal-zone driving),
which spawns and drives real pursuit vehicles once it crosses a
threshold. Heat decays only when the player evades line-of-sight/distance
for a sustained period, not on a timer alone -- so pursuits actually have
to be shaken, not waited out.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import List, Optional

from apex_horizon_engine.ai.traffic_ai import SteerTarget, follow_point_controls
from apex_horizon_engine.physics.traction_model import SurfaceCondition
from apex_horizon_engine.utils.config import get_vehicle_preset
from apex_horizon_engine.vehicles.vehicle_model import Vehicle

MAX_HEAT = 5.0
EVASION_TIME_S = 12.0
UNIT_PRESET = "ironclad_v8_muscle"


@dataclass
class PursuitUnit:
    unit_id: str
    vehicle: Vehicle
    aggression: float = 0.7


@dataclass
class PoliceSystem:
    heat: float = 0.0
    units: List[PursuitUnit] = field(default_factory=list)
    _evasion_timer_s: float = 0.0
    _next_unit_id: int = 0
    _rng: random.Random = field(default_factory=random.Random)

    def register_infraction(self, kind: str, severity: float = 1.0) -> None:
        weights = {"speeding": 0.4, "collision": 0.8, "wrong_way": 0.3, "illegal_zone": 0.6}
        self.heat = min(MAX_HEAT, self.heat + weights.get(kind, 0.3) * severity)
        self._evasion_timer_s = 0.0

    def _spawn_unit(self, near_x: float, near_y: float) -> PursuitUnit:
        vehicle = Vehicle(get_vehicle_preset(UNIT_PRESET))
        angle = self._rng.uniform(0, 2 * math.pi)
        spawn_dist = self._rng.uniform(80, 160)
        vehicle.state.x = near_x + spawn_dist * math.cos(angle)
        vehicle.state.y = near_y + spawn_dist * math.sin(angle)
        unit = PursuitUnit(f"unit_{self._next_unit_id}", vehicle, aggression=0.6 + 0.1 * self.heat)
        self._next_unit_id += 1
        return unit

    def update(self, dt: float, player_x: float, player_y: float, player_speed_mps: float,
               condition: SurfaceCondition) -> None:
        desired_units = int(self.heat)
        if desired_units > len(self.units) and self.heat >= 1.0:
            self.units.append(self._spawn_unit(player_x, player_y))

        if len(self.units) > desired_units:
            self.units = self.units[:max(0, desired_units)]

        for unit in self.units:
            ux, uy = unit.vehicle.state.x, unit.vehicle.state.y
            dist = math.hypot(player_x - ux, player_y - uy)
            target_speed = min(player_speed_mps + 6.0 * unit.aggression, 75.0)
            if dist > 1.0:
                # Chase a point trailing a fixed distance behind the
                # player rather than the player's exact coordinates --
                # aiming dead-on drives the unit straight into contact
                # and keeps it there once alongside, re-triggering a
                # collision every single tick forever.
                approach_x = (player_x - ux) / dist
                approach_y = (player_y - uy) / dist
                trail_gap_m = 9.0
                target_x = player_x - approach_x * trail_gap_m
                target_y = player_y - approach_y * trail_gap_m
            else:
                target_x, target_y = player_x, player_y
            target = SteerTarget(target_x, target_y, target_speed)
            controls = follow_point_controls(unit.vehicle.state, target, steer_gain=2.1)
            if dist < 10.0:
                # Point-blank: back off the throttle hard rather than
                # continuing to close the last few metres.
                controls.throttle *= 0.3
                controls.brake = max(controls.brake, 0.6)
            unit.vehicle.step(dt, controls, condition)

        if self.units:
            closest = min(math.hypot(player_x - u.vehicle.state.x, player_y - u.vehicle.state.y) for u in self.units)
            if closest > 220.0:
                self._evasion_timer_s += dt
            else:
                self._evasion_timer_s = 0.0
        else:
            self._evasion_timer_s += dt

        if self._evasion_timer_s >= EVASION_TIME_S and self.heat > 0:
            self.heat = max(0.0, self.heat - dt * 0.15)
            if self.heat < 0.5:
                self.units.clear()

    @property
    def wanted_stars(self) -> int:
        return min(5, math.ceil(self.heat))

    def busted(self, player_x: float, player_y: float, capture_radius_m: float = 3.0) -> bool:
        return any(
            math.hypot(player_x - u.vehicle.state.x, player_y - u.vehicle.state.y) < capture_radius_m
            for u in self.units
        )
