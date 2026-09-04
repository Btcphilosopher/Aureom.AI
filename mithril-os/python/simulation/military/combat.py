"""
Real-time-abstracted combat resolution.

Spec ref: 17 (real-time battle engine), 18 (combat physics — gameplay-
level abstraction, not per-arrow ballistic simulation), 51 (battlefield
terrain modifies combat).

The vertical slice resolves battles at the STRATEGIC fidelity level
(section 46 LEVEL 0/3): two armies occupying the same cell fight in
discrete combat rounds using an attrition model (a simplified Lanchester
square law) rather than simulating individual soldier positions. This is
the seam where a future LEVEL 4/5 tactical battle renderer plugs in —
`resolve_round` takes the same terrain/weather context a tactical battle
would need (section 78: terrain continuity).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Tuple

from ..ecs.components import ArmyComp, UnitStack
from ..military.formations import modifier as formation_modifier
from ..military.units import UnitCatalogue
from ..world.terrain import DEFENCE_MODIFIER, CAVALRY_MODIFIER, TerrainType


@dataclass
class CombatResult:
    attacker_losses: Dict[str, int]
    defender_losses: Dict[str, int]
    attacker_routed: bool
    defender_routed: bool
    winner: str  # "attacker" | "defender" | "draw"


def _army_power(army: ArmyComp, catalogue: UnitCatalogue, stat: str, terrain: TerrainType, is_defender: bool) -> float:
    total = 0.0
    for stack in army.stacks:
        unit = catalogue.get(stack.unit_type)
        base = getattr(unit, stat) * stack.count * stack.health_fraction
        base *= formation_modifier(army.formation, "attack" if stat == "attack" else "defence")
        if unit.is_cavalry:
            base *= CAVALRY_MODIFIER[terrain]
        if is_defender and stat == "defence":
            base *= DEFENCE_MODIFIER[terrain]
        total += base
    morale_mult = 0.5 + (army.morale / 100.0) * 0.5
    return total * morale_mult


def resolve_round(
    attacker: ArmyComp,
    defender: ArmyComp,
    catalogue: UnitCatalogue,
    terrain: TerrainType,
    weather_ranged_accuracy_mult: float,
    rng: random.Random,
) -> CombatResult:
    """Resolves one combat round (one simulation tick of an ongoing
    battle). Losses are distributed proportionally across a side's unit
    stacks. Deterministic given `rng`."""

    atk_power = _army_power(attacker, catalogue, "attack", terrain, is_defender=False) * weather_ranged_accuracy_mult
    def_power = _army_power(defender, catalogue, "attack", terrain, is_defender=False) * weather_ranged_accuracy_mult
    atk_defence = _army_power(attacker, catalogue, "defence", terrain, is_defender=True)
    def_defence = _army_power(defender, catalogue, "defence", terrain, is_defender=True)

    # Damage each side inflicts is its attack power against the other's
    # effective defence, with a small deterministic-seeded variance so
    # repeated identical fights aren't perfectly identical (still fully
    # reproducible given the same rng state).
    def_damage_taken = max(0.0, atk_power - def_defence * 0.4) * rng.uniform(0.9, 1.1)
    atk_damage_taken = max(0.0, def_power - atk_defence * 0.4) * rng.uniform(0.9, 1.1)

    attacker_losses = _apply_losses(attacker, atk_damage_taken, catalogue)
    defender_losses = _apply_losses(defender, def_damage_taken, catalogue)

    attacker.morale = max(0.0, attacker.morale - (atk_damage_taken / max(1.0, _army_health(attacker))) * 40.0)
    defender.morale = max(0.0, defender.morale - (def_damage_taken / max(1.0, _army_health(defender))) * 40.0)

    attacker_routed = attacker.morale <= 15.0 or attacker.total_units() <= 0
    defender_routed = defender.morale <= 15.0 or defender.total_units() <= 0

    if attacker_routed and not defender_routed:
        winner = "defender"
    elif defender_routed and not attacker_routed:
        winner = "attacker"
    elif attacker_routed and defender_routed:
        winner = "draw"
    else:
        winner = "ongoing"

    return CombatResult(attacker_losses, defender_losses, attacker_routed, defender_routed, winner)


def _army_health(army: ArmyComp) -> float:
    return sum(s.count * s.health_fraction for s in army.stacks) or 1.0


def _apply_losses(army: ArmyComp, damage: float, catalogue: UnitCatalogue) -> Dict[str, int]:
    losses: Dict[str, int] = {}
    total_health = _army_health(army)
    if total_health <= 0 or damage <= 0:
        return losses
    for stack in army.stacks:
        unit = catalogue.get(stack.unit_type)
        share = (stack.count * stack.health_fraction) / total_health
        stack_damage = damage * share
        hp_per_unit = max(1.0, unit.health)
        units_lost = min(stack.count, int(stack_damage / hp_per_unit))
        if units_lost > 0:
            stack.count -= units_lost
            losses[stack.unit_type] = losses.get(stack.unit_type, 0) + units_lost
        # residual damage below one unit's worth chips away at health_fraction
        residual = stack_damage - units_lost * hp_per_unit
        if stack.count > 0:
            stack.health_fraction = max(0.05, stack.health_fraction - residual / (hp_per_unit * max(1, stack.count)))
    army.stacks = [s for s in army.stacks if s.count > 0]
    return losses
