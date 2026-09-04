"""
Army movement and supply.

Spec ref: 26 (supply system), 27 (roads affect movement/supply), 70
(pathfinding — armies consume a precomputed path cell by cell).
"""

from __future__ import annotations

from typing import Callable, Optional

from ..ecs.core import World
from ..ecs.components import ArmyComp, Transform
from ..pathfinding.astar import find_path
from ..world.terrain import Grid


class MovementSystem:
    def __init__(self, world: World, grid: Grid) -> None:
        self.world = world
        self.grid = grid

    def set_destination(self, eid: int, dest: tuple, passable: Optional[Callable] = None) -> bool:
        army = self.world.require(eid, ArmyComp)
        pos = self.world.require(eid, Transform)
        path = find_path(self.grid, (pos.x, pos.y), dest, passable=passable)
        if not path:
            return False
        army.path = path[1:]  # drop current cell
        army.destination = dest
        army.move_progress = 0.0
        return True

    def tick(self, movement_speed_mult: float) -> None:
        for eid, army, pos in self.world.query(ArmyComp, Transform):
            if not army.path:
                continue
            base_speed = 3.0  # movement points/tick baseline for a mixed army
            budget = base_speed * movement_speed_mult
            army.move_progress += budget
            while army.path and army.move_progress >= self.grid.movement_cost(*army.path[0]):
                nxt = army.path.pop(0)
                cost = self.grid.movement_cost(*nxt)
                army.move_progress -= cost
                pos.x, pos.y = nxt
            if not army.path:
                army.destination = None
                army.move_progress = 0.0

            self._apply_supply(army, pos)

    def _apply_supply(self, army: ArmyComp, pos: Transform) -> None:
        """Section 26: armies far from friendly territory (here,
        approximated by being off-road) slowly lose supply; supply below
        30 begins attrition against morale and unit health."""
        on_road = self.grid.at(pos.x, pos.y).has_road
        if on_road:
            army.supply = min(100.0, army.supply + 1.0)
        else:
            army.supply = max(0.0, army.supply - 0.5)
        if army.supply < 30.0:
            army.morale = max(0.0, army.morale - 0.3)
            for stack in army.stacks:
                stack.health_fraction = max(0.1, stack.health_fraction - 0.002)
        elif army.supply >= 50.0:
            # Section 20/25: a well-supplied army out of combat slowly
            # rallies, so a rout is a temporary setback rather than a
            # permanent one.
            army.morale = min(100.0, army.morale + 0.4)
