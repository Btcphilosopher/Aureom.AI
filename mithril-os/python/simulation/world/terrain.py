"""
Terrain grid: the physical substrate everything else sits on.

Spec ref: 04 (map engine), 05 (procedural geography), 51 (battlefield
terrain), 78 (terrain continuity between strategic and tactical scale).

Design choice: one grid cell is a "territory-scale" tile (spec's
TERRITORY level in the WORLD > CONTINENT > REGION > PROVINCE > TERRITORY
> SETTLEMENT hierarchy from section 03). A settlement, army, or battle
occupies a cell; the same TerrainCell data that drove strategic movement
cost is what a tactical battle would inherit (section 78) — there is only
one terrain dataset, not a "strategic" copy and a disconnected "battle
arena" copy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class TerrainType(str, Enum):
    PLAINS = "PLAINS"
    HILLS = "HILLS"
    MOUNTAINS = "MOUNTAINS"
    FOREST = "FOREST"
    RIVER = "RIVER"
    WATER = "WATER"
    MARSH = "MARSH"
    DESERT = "DESERT"
    RUINS = "RUINS"


# Base movement cost in "movement points per tick required to cross".
# Roads apply a multiplicative discount on top of this (see Grid.movement_cost).
BASE_MOVEMENT_COST: Dict[TerrainType, float] = {
    TerrainType.PLAINS: 1.0,
    TerrainType.HILLS: 1.6,
    TerrainType.MOUNTAINS: 4.0,
    TerrainType.FOREST: 1.8,
    TerrainType.RIVER: 2.5,
    TerrainType.WATER: float("inf"),  # impassable without a ship/bridge
    TerrainType.MARSH: 2.2,
    TerrainType.DESERT: 1.4,
    TerrainType.RUINS: 1.3,
}

# Section 31: base vision range modifier by terrain of the *observer's* cell.
VISIBILITY_MODIFIER: Dict[TerrainType, float] = {
    TerrainType.PLAINS: 1.2,
    TerrainType.HILLS: 1.6,
    TerrainType.MOUNTAINS: 2.0,
    TerrainType.FOREST: 0.5,
    TerrainType.RIVER: 1.0,
    TerrainType.WATER: 1.3,
    TerrainType.MARSH: 0.7,
    TerrainType.DESERT: 1.4,
    TerrainType.RUINS: 1.0,
}

# Section 51: combat modifiers granted to a defender standing on this terrain.
DEFENCE_MODIFIER: Dict[TerrainType, float] = {
    TerrainType.PLAINS: 1.0,
    TerrainType.HILLS: 1.25,
    TerrainType.MOUNTAINS: 1.6,
    TerrainType.FOREST: 1.15,
    TerrainType.RIVER: 1.1,
    TerrainType.WATER: 1.0,
    TerrainType.MARSH: 0.9,
    TerrainType.DESERT: 0.95,
    TerrainType.RUINS: 1.05,
}

CAVALRY_MODIFIER: Dict[TerrainType, float] = {
    TerrainType.PLAINS: 1.3,
    TerrainType.HILLS: 0.85,
    TerrainType.MOUNTAINS: 0.4,
    TerrainType.FOREST: 0.5,
    TerrainType.RIVER: 0.6,
    TerrainType.WATER: 0.0,
    TerrainType.MARSH: 0.5,
    TerrainType.DESERT: 1.1,
    TerrainType.RUINS: 0.9,
}


@dataclass
class TerrainCell:
    x: int
    y: int
    terrain: TerrainType
    elevation: float = 0.0       # 0..1
    moisture: float = 0.0        # 0..1
    fertility: float = 0.0       # 0..1, drives farm output
    has_road: bool = False
    region_id: Optional[str] = None
    resource_node: Optional[str] = None   # resource type id, e.g. "IRON"
    resource_quantity: float = 0.0
    settlement_id: Optional[int] = None   # ECS entity id, if a settlement sits here

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["terrain"] = self.terrain.value
        return d


class Grid:
    """A width x height array of TerrainCell, plus adjacency helpers."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.cells: List[List[TerrainCell]] = [
            [TerrainCell(x, y, TerrainType.PLAINS) for y in range(height)]
            for x in range(width)
        ]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def at(self, x: int, y: int) -> TerrainCell:
        return self.cells[x][y]

    def neighbors4(self, x: int, y: int) -> List[Tuple[int, int]]:
        out = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if self.in_bounds(nx, ny):
                out.append((nx, ny))
        return out

    def neighbors8(self, x: int, y: int) -> List[Tuple[int, int]]:
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if self.in_bounds(nx, ny):
                    out.append((nx, ny))
        return out

    def movement_cost(self, x: int, y: int) -> float:
        cell = self.at(x, y)
        cost = BASE_MOVEMENT_COST[cell.terrain]
        if cell.has_road and cost != float("inf"):
            cost *= 0.35  # section 27: roads sharply cut movement cost
        return cost

    def all_cells(self):
        for col in self.cells:
            for cell in col:
                yield cell
