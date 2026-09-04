"""
Building definitions and construction.

Spec ref: 10 (building engine), 40/41 (city construction, procedural
buildings — the visual/procedural-mesh side is deferred to the rendering
layer; this module owns the simulation-relevant facts: cost, output,
garrison capacity, upkeep).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BuildingDefinition:
    building_id: str
    name: str
    category: str  # e.g. "economy", "military", "civic", "defence"
    cost: Dict[str, float]
    construction_time_days: int
    produces: Optional[str] = None       # resource id this building generates, if any
    base_output: float = 0.0
    garrison_capacity: int = 0
    wall_bonus: float = 0.0
    required_tier: str = "village"        # minimum settlement tier to build
    upkeep: Dict[str, float] = field(default_factory=dict)


@dataclass
class ConstructionOrder:
    building_id: str
    settlement_id: int
    days_remaining: int
    location: Optional[tuple] = None


class ConstructionSystem:
    def __init__(self) -> None:
        self.orders: List[ConstructionOrder] = []

    def queue(self, order: ConstructionOrder) -> None:
        self.orders.append(order)

    def tick(self, construction_speed_mult: float = 1.0) -> List[ConstructionOrder]:
        completed = []
        remaining = []
        for order in self.orders:
            order.days_remaining -= 1 * construction_speed_mult
            if order.days_remaining <= 0:
                completed.append(order)
            else:
                remaining.append(order)
        self.orders = remaining
        return completed
