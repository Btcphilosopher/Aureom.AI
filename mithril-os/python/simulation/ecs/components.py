"""
Component definitions.

Spec ref: 67 (ECS components), 09 (settlements), 12 (population),
15 (military), 16 (formations), 20 (heroes).

Every component is a plain, JSON-serializable dataclass: no methods that
mutate other entities, no references to World. Systems (in the sibling
`world`, `economy`, `population`, `military`, ... packages) are the only
code that mutates components, which keeps the simulation loop
(game_state.tick) the single place causal order is decided (section 93).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


@dataclass
class Transform:
    x: int
    y: int


@dataclass
class Owner:
    faction_id: str


@dataclass
class Health:
    current: float
    maximum: float

    @property
    def ratio(self) -> float:
        return 0.0 if self.maximum <= 0 else max(0.0, self.current / self.maximum)


@dataclass
class ResourceStock:
    amounts: Dict[str, float] = field(default_factory=dict)

    def add(self, resource: str, qty: float) -> None:
        self.amounts[resource] = self.amounts.get(resource, 0.0) + qty

    def take(self, resource: str, qty: float) -> float:
        have = self.amounts.get(resource, 0.0)
        taken = min(have, qty)
        self.amounts[resource] = have - taken
        return taken

    def get(self, resource: str) -> float:
        return self.amounts.get(resource, 0.0)


class SettlementTier(str, Enum):
    CAMP = "camp"
    VILLAGE = "village"
    TOWN = "town"
    CITY = "city"
    FORTIFIED_CITY = "fortified_city"
    CAPITAL = "capital"


@dataclass
class SettlementComp:
    name: str
    tier: SettlementTier = SettlementTier.VILLAGE
    region_id: str = ""
    buildings: List[str] = field(default_factory=list)  # building type ids, one entry per built instance
    garrison: int = 0
    wall_health: float = 0.0
    wall_max: float = 0.0
    happiness: float = 60.0


@dataclass
class PopulationComp:
    count: float
    growth_rate: float = 0.02  # per-tick fractional growth at full food/happiness
    housing_capacity: float = 200.0
    workers_idle: float = 0.0
    workers_food: float = 0.0
    workers_industry: float = 0.0
    soldiers: float = 0.0


@dataclass
class ProductionComp:
    building_type: str
    output_resource: str
    base_rate: float
    settlement_id: int  # entity id of the SettlementComp/ResourceStock this building feeds
    workers_assigned: float = 0.0


@dataclass
class UnitStack:
    unit_type: str
    count: int
    health_fraction: float = 1.0  # average condition of the stack, 0..1


@dataclass
class ArmyComp:
    name: str
    stacks: List[UnitStack] = field(default_factory=list)
    supply: float = 100.0  # 0..100, attrition below threshold
    morale: float = 70.0  # 0..100
    formation: str = "LINE"
    destination: Optional[Tuple[int, int]] = None
    path: List[Tuple[int, int]] = field(default_factory=list)
    move_progress: float = 0.0  # accumulated movement points this tick

    def total_units(self) -> int:
        return sum(s.count for s in self.stacks)


@dataclass
class HeroComp:
    name: str
    level: int = 1
    experience: float = 0.0
    faction_id: str = ""
    commanding_army: Optional[int] = None
    skills: List[str] = field(default_factory=list)


@dataclass
class RoadLink:
    """A single road segment between two adjacent grid cells."""
    quality: float = 1.0  # 0..1, degrades under disrepair


@dataclass
class HistoryTag:
    """Marks an entity as historically notable so the History Engine
    records its lifecycle events (founded, captured, destroyed...)."""
    founded_year: int
    founded_day: int
