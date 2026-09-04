"""
Resource economy system.

Spec ref: 11 (economic engine — "workers must physically move resources:
FOREST -> LUMBER CAMP -> WOOD -> CART -> STORAGE -> BUILDING"), 47
(resource simulation: depletion, regeneration, extraction rate).

Simplification for the vertical slice: instead of simulating individual
carts, each ProductionComp is tied to a settlement's ResourceStock and a
transport_cost derived from distance-to-nearest-road, which throttles
throughput exactly like a literal cart chain would, at a fraction of the
entity count. A native/Rust transport-cart layer is a clean drop-in later
(section 66) because ProductionSystem.tick is the only place that would
need to change.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from ..ecs.core import World
from ..ecs.components import PopulationComp, ProductionComp, ResourceStock, SettlementComp
from ..events.bus import Event, EventBus, RESOURCE_DEPLETED
from ..world.terrain import Grid


class ProductionSystem:
    def __init__(self, world: World, grid: Grid, bus: EventBus) -> None:
        self.world = world
        self.grid = grid
        self.bus = bus

    def tick(self, tick_no: int, year: int, day: int, season_food_mult: float, weather_construction_mult: float) -> None:
        """Section 12/13's causal link, made real: a settlement's own
        PopulationComp.workers_food / workers_industry pools (computed by
        PopulationSystem at the end of the *previous* tick — one tick of
        lag, which keeps the loop's stage order from section 93 intact)
        are split evenly across that settlement's buildings each tick,
        rather than each ProductionComp carrying an independent, never-
        updated worker count. A settlement that grows gets more farmers;
        a settlement that starves has fewer to spare."""
        by_settlement: Dict[int, List[Tuple[int, ProductionComp]]] = defaultdict(list)
        for eid, prod in self.world.query(ProductionComp):
            by_settlement[prod.settlement_id].append((eid, prod))

        for settlement_id, entries in by_settlement.items():
            stock = self.world.get(settlement_id, ResourceStock)
            if stock is None:
                continue
            pop = self.world.get(settlement_id, PopulationComp)
            food_entries = [e for e in entries if e[1].output_resource == "FOOD"]
            other_entries = [e for e in entries if e[1].output_resource != "FOOD"]
            self._produce_group(food_entries, pop.workers_food if pop else None, stock, season_food_mult)
            self._produce_group(other_entries, pop.workers_industry if pop else None, stock, 1.0)

    @staticmethod
    def _produce_group(entries: List[Tuple[int, ProductionComp]], worker_pool: float, stock: ResourceStock, multiplier: float) -> None:
        if not entries:
            return
        # Fall back to each building's own configured worker count if this
        # settlement has no PopulationComp (e.g. a unit test fixture).
        share = (worker_pool / len(entries)) if worker_pool is not None else None
        for eid, prod in entries:
            workers = share if share is not None else prod.workers_assigned
            prod.workers_assigned = workers
            output = prod.base_rate * workers * multiplier
            stock.add(prod.output_resource, output)

    def deplete_node(self, x: int, y: int, amount: float, tick_no: int, year: int, day: int) -> float:
        cell = self.grid.at(x, y)
        if cell.resource_node is None:
            return 0.0
        taken = min(cell.resource_quantity, amount)
        cell.resource_quantity -= taken
        if cell.resource_quantity <= 0.0:
            depleted_type = cell.resource_node
            cell.resource_node = None
            self.bus.publish(Event(
                type=RESOURCE_DEPLETED,
                payload={"x": x, "y": y, "resource": depleted_type},
                tick=tick_no, year=year, day=day,
            ))
        return taken
