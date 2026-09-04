"""
Terrain- and road-aware A* pathfinding.

Spec ref: 70 (pathfinding), 71 (flow fields — noted as future work for
mass-army movement; a single army in the vertical slice uses A* directly).
"""

from __future__ import annotations

import heapq
from typing import Callable, List, Optional, Tuple

from ..world.terrain import Grid

Coord = Tuple[int, int]


def heuristic(a: Coord, b: Coord) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def find_path(
    grid: Grid,
    start: Coord,
    goal: Coord,
    passable: Optional[Callable[[Coord], bool]] = None,
) -> List[Coord]:
    """Returns a list of coordinates from start to goal inclusive, or an
    empty list if unreachable. `passable` lets callers exclude enemy
    territory / blocked routes (section 70) without touching the grid."""
    if start == goal:
        return [start]

    def is_passable(c: Coord) -> bool:
        if grid.movement_cost(*c) == float("inf"):
            return False
        if passable is not None and not passable(c):
            return False
        return True

    open_heap: List[Tuple[float, int, Coord]] = []
    counter = 0
    heapq.heappush(open_heap, (0.0, counter, start))
    came_from = {}
    g_score = {start: 0.0}
    visited = set()

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current in visited:
            continue
        visited.add(current)
        if current == goal:
            return _reconstruct(came_from, current)

        for nxt in grid.neighbors4(*current):
            if not is_passable(nxt):
                continue
            step_cost = grid.movement_cost(*nxt)
            tentative = g_score[current] + step_cost
            if tentative < g_score.get(nxt, float("inf")):
                g_score[nxt] = tentative
                came_from[nxt] = current
                priority = tentative + heuristic(nxt, goal)
                counter += 1
                heapq.heappush(open_heap, (priority, counter, nxt))

    return []


def _reconstruct(came_from: dict, current: Coord) -> List[Coord]:
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def path_cost(grid: Grid, path: List[Coord]) -> float:
    return sum(grid.movement_cost(*c) for c in path[1:])
