"""
Damage accumulation and its feedback into vehicle performance.

Damage is driven entirely by collision impulses (see ``physics.collision``)
and high-speed off-road/terrain punishment -- never scripted. Once
accumulated it degrades real parameters (drag, torque, steering
authority) that ``vehicles.vehicle_model`` reads back every tick, so a
beaten-up car is measurably slower and harder to control, not just
visually dented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class DamageState:
    body_damage: float = 0.0     # 0..1, cosmetic + drag/handling penalty
    engine_damage: float = 0.0   # 0..1, torque penalty
    tire_damage: Dict[str, float] = field(default_factory=lambda: {"front": 0.0, "rear": 0.0})


IMPULSE_TO_DAMAGE = 1.0 / 45000.0   # tuned so a ~40 km/h wall hit costs ~15-20% body damage
DAMAGE_REPAIR_RATE_GARAGE = 1.0     # full repair when serviced in garage


def apply_collision_damage(state: DamageState, impulse_ns: float) -> float:
    """Apply damage from a collision impulse; returns the damage delta
    actually applied (post-clamp), useful for HUD damage-hit flashes."""
    delta = min(0.35, impulse_ns * IMPULSE_TO_DAMAGE)
    before = state.body_damage
    state.body_damage = min(1.0, state.body_damage + delta)
    if impulse_ns > 30000:
        state.engine_damage = min(1.0, state.engine_damage + delta * 0.4)
    return state.body_damage - before


def apply_offroad_wear(state: DamageState, dt: float, off_road: bool, speed_mps: float) -> None:
    if not off_road or speed_mps < 5.0:
        return
    wear = dt * 0.0006 * (speed_mps / 30.0)
    state.tire_damage["front"] = min(1.0, state.tire_damage["front"] + wear)
    state.tire_damage["rear"] = min(1.0, state.tire_damage["rear"] + wear)


def repair(state: DamageState) -> None:
    state.body_damage = 0.0
    state.engine_damage = 0.0
    state.tire_damage = {"front": 0.0, "rear": 0.0}


def drag_multiplier(state: DamageState) -> float:
    return 1.0 + state.body_damage * 0.45


def torque_multiplier(state: DamageState) -> float:
    return 1.0 - state.engine_damage * 0.55


def steering_authority_multiplier(state: DamageState) -> float:
    return 1.0 - state.body_damage * 0.25


def axle_grip_multiplier(state: DamageState, axle: str) -> float:
    return 1.0 - state.tire_damage.get(axle, 0.0) * 0.6
