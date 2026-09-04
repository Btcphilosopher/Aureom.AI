"""
Strategic Faction AI.

Spec ref: 24 (AI faction engine: PERCEPTION -> WORLD MODEL -> GOALS ->
STRATEGY -> ECONOMIC PLAN -> MILITARY PLAN -> DIPLOMACY -> EXECUTION ->
EVALUATION), 102 (AI observability — every decision is recorded on
AIDebugState so a UI/tooling layer can display it, section 102's
requirement).

This is deliberately a rule-based system, not a learned policy: it is
fast, deterministic (section 62), and — critically for section 102 —
every branch is a legible if/elif a human can read and explain. A
utility-AI or MCTS operational/tactical layer is future work (section
64: different AI tiers run at different cadences); this module is the
"strategic AI: minutes/hours" tier.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from ..ecs.core import World
from ..ecs.components import ArmyComp, PopulationComp, ResourceStock, SettlementComp, Transform
from ..world.faction import Faction


@dataclass
class AIDebugState:
    """Section 102: AI observability record, refreshed every strategic
    tick per faction."""
    faction_id: str
    goal: str = "EXPAND"
    threat_assessment: float = 0.0
    economic_priority: str = "FOOD"
    military_priority: str = "DEFEND"
    target_region: Optional[str] = None


class FactionAI:
    def __init__(self, world: World, rng: random.Random) -> None:
        self.world = world
        self.rng = rng
        self.debug_states: dict = {}

    def decide(self, faction: Faction, own_settlements: List[int], own_armies: List[int], enemy_armies_nearby: int) -> AIDebugState:
        personality = faction.definition.ai_personality
        state = AIDebugState(faction_id=faction.faction_id)

        # -- PERCEPTION / WORLD MODEL --------------------------------------
        total_pop = 0.0
        food_stock = 0.0
        for eid in own_settlements:
            pop = self.world.get(eid, PopulationComp)
            stock = self.world.get(eid, ResourceStock)
            if pop:
                total_pop += pop.count
            if stock:
                food_stock += stock.get("FOOD")

        state.threat_assessment = min(1.0, enemy_armies_nearby / 3.0)

        # -- GOALS / STRATEGY ------------------------------------------------
        if state.threat_assessment > 0.6:
            state.goal = "DEFEND"
        elif food_stock < total_pop * 0.5:
            state.goal = "TRADE"
        elif personality == "raider" and self.rng.random() < 0.3:
            state.goal = "RAID"
        elif personality == "expander" or (personality == "balanced" and self.rng.random() < 0.5):
            state.goal = "EXPAND"
        elif personality == "defender":
            state.goal = "FORTIFY"
        else:
            state.goal = "TRADE"

        state.economic_priority = "FOOD" if food_stock < total_pop * 0.8 else faction.definition.resource_priority[0] if faction.definition.resource_priority else "GOLD"
        state.military_priority = "DEFEND" if state.threat_assessment > 0.4 else "EXPAND"

        self.debug_states[faction.faction_id] = state
        return state
