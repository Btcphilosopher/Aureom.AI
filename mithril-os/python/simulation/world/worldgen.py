"""
Procedural geography generator.

Spec ref: 05 (procedural Middle-earth — "do not generate random geography
without structure; use geographical logic").

Pipeline, each stage consuming the previous stage's output rather than
independent noise layers, so the result has causal structure instead of
looking like colored static:

  1. Elevation  — a handful of mountain "seed" peaks, smoothed by
     repeated neighbour-averaging (cheap diffusion, no numpy required).
  2. Mountains/Hills/Plains classification from elevation thresholds.
  3. Rivers — traced by steepest-descent from each mountain peak down to
     the lowest neighbour until reaching the map edge or an existing
     water cell, raising moisture along the way.
  4. Forest placement — biased toward high-moisture, low-elevation cells
     (i.e. near rivers), per section 05's "rivers influence agriculture,
     forests influence wood/wildlife/concealment".
  5. Fertility — plains near rivers get high fertility (agriculture),
     driving where farms/settlements are viable.
  6. Resource nodes — ore/stone in mountains and hills, wood implicit in
     forest tiles, gold as a rare deposit near mountains.
  7. Settlement anchor points — chosen where fertility and defensibility
     (elevation) both score well and cells are spaced apart, then
     connected by roads via straight-ish least-cost paths.

Fully deterministic: the only randomness source is the `random.Random`
instance passed in, seeded by the caller (GameState.rng), per section 62.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .terrain import Grid, TerrainCell, TerrainType


@dataclass
class WorldGenConfig:
    width: int = 40
    height: int = 30
    mountain_seeds: int = 5
    diffusion_passes: int = 6
    river_count: int = 4
    mountain_threshold: float = 0.72
    hill_threshold: float = 0.52
    forest_moisture_threshold: float = 0.35
    settlement_slots: int = 6
    min_settlement_spacing: int = 6


@dataclass
class WorldGenResult:
    grid: Grid
    settlement_sites: List[Tuple[int, int]] = field(default_factory=list)
    river_cells: List[Tuple[int, int]] = field(default_factory=list)
    mountain_peaks: List[Tuple[int, int]] = field(default_factory=list)


def generate_world(rng: random.Random, config: Optional[WorldGenConfig] = None) -> WorldGenResult:
    cfg = config or WorldGenConfig()
    grid = Grid(cfg.width, cfg.height)

    elevation = _generate_elevation(rng, cfg)
    peaks = _pick_peaks(elevation, cfg, rng)

    for x in range(cfg.width):
        for y in range(cfg.height):
            cell = grid.at(x, y)
            cell.elevation = elevation[x][y]
            if cell.elevation >= cfg.mountain_threshold:
                cell.terrain = TerrainType.MOUNTAINS
            elif cell.elevation >= cfg.hill_threshold:
                cell.terrain = TerrainType.HILLS
            else:
                cell.terrain = TerrainType.PLAINS

    river_cells = _trace_rivers(grid, elevation, peaks, cfg, rng)
    _apply_moisture(grid, river_cells, cfg)
    _place_forests(grid, cfg, rng)
    _assign_fertility(grid)
    _place_resources(grid, rng)

    sites = _choose_settlement_sites(grid, cfg, rng)
    _connect_roads(grid, sites)

    return WorldGenResult(grid=grid, settlement_sites=sites, river_cells=river_cells, mountain_peaks=peaks)


# ---------------------------------------------------------------------------
# elevation


def _generate_elevation(rng: random.Random, cfg: WorldGenConfig) -> List[List[float]]:
    w, h = cfg.width, cfg.height
    elevation = [[rng.random() * 0.15 for _ in range(h)] for _ in range(w)]

    seeds = []
    for _ in range(cfg.mountain_seeds):
        sx, sy = rng.randrange(w), rng.randrange(h)
        seeds.append((sx, sy))
        elevation[sx][sy] = 1.0

    # Radial falloff from each seed, then smooth via diffusion — this is
    # what gives mountains contiguous ranges instead of isolated spikes.
    for sx, sy in seeds:
        radius = rng.uniform(4.0, 8.0)
        for x in range(w):
            for y in range(h):
                dist = ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5
                if dist <= radius:
                    contribution = max(0.0, 1.0 - dist / radius)
                    elevation[x][y] = max(elevation[x][y], contribution)

    for _ in range(cfg.diffusion_passes):
        new_elev = [row[:] for row in elevation]
        for x in range(w):
            for y in range(h):
                neighbours = []
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < w and 0 <= ny < h:
                            neighbours.append(elevation[nx][ny])
                new_elev[x][y] = sum(neighbours) / len(neighbours)
        elevation = new_elev

    return elevation


def _pick_peaks(elevation: List[List[float]], cfg: WorldGenConfig, rng: random.Random) -> List[Tuple[int, int]]:
    flat = [(elevation[x][y], x, y) for x in range(cfg.width) for y in range(cfg.height)]
    flat.sort(reverse=True)
    peaks: List[Tuple[int, int]] = []
    for _, x, y in flat:
        if len(peaks) >= cfg.river_count:
            break
        if all((x - px) ** 2 + (y - py) ** 2 > 25 for px, py in peaks):
            peaks.append((x, y))
    return peaks


# ---------------------------------------------------------------------------
# rivers


def _trace_rivers(
    grid: Grid,
    elevation: List[List[float]],
    peaks: List[Tuple[int, int]],
    cfg: WorldGenConfig,
    rng: random.Random,
) -> List[Tuple[int, int]]:
    river_cells: List[Tuple[int, int]] = []
    for px, py in peaks:
        x, y = px, py
        visited = set()
        for _ in range(cfg.width + cfg.height):  # generous step budget
            visited.add((x, y))
            neighbours = grid.neighbors8(x, y)
            # steepest descent: move to the lowest-elevation neighbour not
            # already part of this river.
            candidates = [(elevation[nx][ny], nx, ny) for nx, ny in neighbours if (nx, ny) not in visited]
            if not candidates:
                break
            candidates.sort()
            _, nx, ny = candidates[0]
            if elevation[nx][ny] >= elevation[x][y] and grid.at(x, y).terrain != TerrainType.MOUNTAINS:
                break  # reached a local basin; stop before flowing uphill
            x, y = nx, ny
            cell = grid.at(x, y)
            if cell.terrain != TerrainType.MOUNTAINS:
                cell.terrain = TerrainType.RIVER
            river_cells.append((x, y))
            if x == 0 or y == 0 or x == cfg.width - 1 or y == cfg.height - 1:
                break
    return river_cells


def _apply_moisture(grid: Grid, river_cells: List[Tuple[int, int]], cfg: WorldGenConfig) -> None:
    for (rx, ry) in river_cells:
        for x in range(max(0, rx - 3), min(cfg.width, rx + 4)):
            for y in range(max(0, ry - 3), min(cfg.height, ry + 4)):
                dist = ((x - rx) ** 2 + (y - ry) ** 2) ** 0.5
                if dist <= 3:
                    cell = grid.at(x, y)
                    cell.moisture = min(1.0, cell.moisture + max(0.0, 1.0 - dist / 3.0) * 0.6)


# ---------------------------------------------------------------------------
# forests / fertility / resources


def _place_forests(grid: Grid, cfg: WorldGenConfig, rng: random.Random) -> None:
    for cell in grid.all_cells():
        if cell.terrain != TerrainType.PLAINS:
            continue
        chance = cell.moisture
        if chance >= cfg.forest_moisture_threshold and rng.random() < chance * 0.7:
            cell.terrain = TerrainType.FOREST


def _assign_fertility(grid: Grid) -> None:
    for cell in grid.all_cells():
        if cell.terrain == TerrainType.PLAINS:
            cell.fertility = min(1.0, 0.3 + cell.moisture * 0.7)
        elif cell.terrain == TerrainType.FOREST:
            cell.fertility = min(1.0, 0.15 + cell.moisture * 0.3)
        else:
            cell.fertility = 0.0


def _place_resources(grid: Grid, rng: random.Random) -> None:
    for cell in grid.all_cells():
        if cell.terrain == TerrainType.MOUNTAINS:
            if rng.random() < 0.35:
                cell.resource_node = "IRON"
                cell.resource_quantity = rng.uniform(400, 1200)
            elif rng.random() < 0.10:
                cell.resource_node = "GOLD"
                cell.resource_quantity = rng.uniform(150, 400)
            else:
                cell.resource_node = "STONE"
                cell.resource_quantity = rng.uniform(500, 1500)
        elif cell.terrain == TerrainType.HILLS and rng.random() < 0.25:
            cell.resource_node = "STONE"
            cell.resource_quantity = rng.uniform(300, 800)
        elif cell.terrain == TerrainType.FOREST:
            cell.resource_node = "WOOD"
            cell.resource_quantity = rng.uniform(600, 1600)


# ---------------------------------------------------------------------------
# settlement placement / roads


def _choose_settlement_sites(grid: Grid, cfg: WorldGenConfig, rng: random.Random) -> List[Tuple[int, int]]:
    scored: List[Tuple[float, int, int]] = []
    for cell in grid.all_cells():
        if cell.terrain not in (TerrainType.PLAINS, TerrainType.HILLS):
            continue
        # Favor high fertility (agriculture) with a touch of elevation
        # (defensibility) — section 05: geography must generate strategic
        # consequences, not just pretty noise.
        score = cell.fertility * 1.5 + cell.elevation * 0.3
        scored.append((score, cell.x, cell.y))
    scored.sort(reverse=True)

    sites: List[Tuple[int, int]] = []
    for _, x, y in scored:
        if len(sites) >= cfg.settlement_slots:
            break
        if all(abs(x - sx) + abs(y - sy) >= cfg.min_settlement_spacing for sx, sy in sites):
            sites.append((x, y))
    return sites


def _connect_roads(grid: Grid, sites: List[Tuple[int, int]]) -> None:
    """Greedy minimum-spanning-tree-ish road network: connect each site to
    its nearest already-connected neighbour with a straight-line-ish path
    that prefers low movement cost (section 27: roads are infrastructure,
    not decoration)."""
    if len(sites) < 2:
        return
    connected = [sites[0]]
    remaining = sites[1:]
    while remaining:
        best = None
        best_dist = None
        for s in remaining:
            for c in connected:
                d = (s[0] - c[0]) ** 2 + (s[1] - c[1]) ** 2
                if best_dist is None or d < best_dist:
                    best_dist = d
                    best = (s, c)
        s, c = best
        _lay_road(grid, s, c)
        connected.append(s)
        remaining.remove(s)


def _lay_road(grid: Grid, a: Tuple[int, int], b: Tuple[int, int]) -> None:
    x, y = a
    bx, by = b
    while (x, y) != (bx, by):
        cell = grid.at(x, y)
        if cell.terrain != TerrainType.WATER:
            cell.has_road = True
        if x != bx:
            x += 1 if bx > x else -1
        elif y != by:
            y += 1 if by > y else -1
    grid.at(bx, by).has_road = True
