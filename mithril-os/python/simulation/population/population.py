"""
Population engine.

Spec ref: 12 (population engine), 13 (worker engine), 108 (historical
causality: mine depletion -> shortage -> ... -> city decline — this
system is the "population" and "economy" links in that causal chain).
"""

from __future__ import annotations

from typing import Dict

from ..ecs.core import World
from ..ecs.components import PopulationComp, ResourceStock, SettlementComp
from ..events.bus import Event, EventBus, SETTLEMENT_GREW, SETTLEMENT_STARVING

FOOD_PER_CAPITA = 0.05  # food consumed per population per tick
HAPPINESS_FOOD_WEIGHT = 0.6

TIER_THRESHOLDS = [
    ("village", 0),
    ("town", 300),
    ("city", 1200),
    ("fortified_city", 3000),
    ("capital", 6000),
]


class PopulationSystem:
    def __init__(self, world: World, bus: EventBus) -> None:
        self.world = world
        self.bus = bus

    def tick(self, tick_no: int, year: int, day: int) -> None:
        for eid, pop, stock in self.world.query(PopulationComp, ResourceStock):
            settlement = self.world.get(eid, SettlementComp)
            required_food = pop.count * FOOD_PER_CAPITA
            available = stock.get("FOOD")
            consumed = min(available, required_food)
            stock.take("FOOD", consumed)
            deficit_ratio = 0.0 if required_food <= 0 else max(0.0, (required_food - consumed) / required_food)

            if settlement is not None:
                if deficit_ratio > 0.0:
                    settlement.happiness = max(0.0, settlement.happiness - deficit_ratio * 10.0)
                    if deficit_ratio > 0.5:
                        self.bus.publish(Event(
                            type=SETTLEMENT_STARVING,
                            payload={"settlement": settlement.name, "deficit_ratio": deficit_ratio},
                            tick=tick_no, year=year, day=day,
                        ))
                else:
                    settlement.happiness = min(100.0, settlement.happiness + 0.5)

            growth_factor = pop.growth_rate
            if deficit_ratio > 0.0:
                growth_factor -= deficit_ratio * pop.growth_rate * 1.5  # starvation can go net-negative
            happiness_mult = 0.5 + (settlement.happiness / 100.0 if settlement else 0.6)
            growth = pop.count * growth_factor * happiness_mult
            pop.count = max(0.0, min(pop.housing_capacity, pop.count + growth))

            self._allocate_workers(pop)

            if settlement is not None:
                self._maybe_promote(settlement, pop, tick_no, year, day)

    def _allocate_workers(self, pop: PopulationComp) -> None:
        workforce = pop.count * 0.5  # roughly half the population works
        pop.workers_food = workforce * 0.5
        pop.workers_industry = workforce * 0.35
        pop.workers_idle = workforce * 0.15
        pop.soldiers = pop.count * 0.05  # eligible recruitment pool, not standing army

    def _maybe_promote(self, settlement: SettlementComp, pop: PopulationComp, tick_no: int, year: int, day: int) -> None:
        current_index = [i for i, (tier, _) in enumerate(TIER_THRESHOLDS) if tier == settlement.tier.value]
        idx = current_index[0] if current_index else 0
        if idx + 1 < len(TIER_THRESHOLDS):
            next_tier, threshold = TIER_THRESHOLDS[idx + 1]
            if pop.count >= threshold:
                from ..ecs.components import SettlementTier
                settlement.tier = SettlementTier(next_tier)
                self.bus.publish(Event(
                    type=SETTLEMENT_GREW,
                    payload={"settlement": settlement.name, "tier": next_tier},
                    tick=tick_no, year=year, day=day,
                ))
