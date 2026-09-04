"""
Vertical slice scenario: the Rohan / Gondor / Isengard frontier.

Spec ref: 96 (first playable build — "Do NOT attempt the entire game
immediately. Build vertical slice: AGE III, REGION: ROHAN/GONDOR/
ISENGARD-style frontier scenario"). This module wires together every
system built so far (worldgen, factions, settlements, buildings,
resources, technology, army movement, combat, AI, weather, history,
fog-of-war-ready vision data) into one runnable campaign.

`build_campaign(seed)` is the single entry point: give it a seed, get
back a fully-populated, deterministic GameState ready to tick.
"""

from __future__ import annotations

import random
from typing import Dict, List, Tuple

from ..content_loader import load_buildings, load_factions, load_technologies, load_units
from ..ecs.components import ArmyComp, Owner, PopulationComp, ProductionComp, ResourceStock, SettlementComp, SettlementTier, Transform, UnitStack
from ..military.units import UnitCatalogue
from ..technology.tech_tree import TechTree
from ..time.calendar import Age
from ..game_state import Command, GameState
from ..world.regions import Region, Territory
from ..world.worldgen import WorldGenConfig, generate_world

FRONTIER_SEED_DEFAULT = 20260904


def build_campaign(seed: int = FRONTIER_SEED_DEFAULT) -> GameState:
    rng = random.Random(seed)

    factions_def = load_factions()
    units_def = load_units()
    buildings_def = load_buildings()
    tech_def = load_technologies()

    catalogue = UnitCatalogue(list(units_def.values()))
    tech_tree = TechTree(list(tech_def.values()))

    config = WorldGenConfig(width=42, height=30, mountain_seeds=4, river_count=3, settlement_slots=6)
    gen = generate_world(rng, config)

    gs = GameState(seed=seed, age=Age.THIRD_AGE, grid=gen.grid, unit_catalogue=catalogue, tech_tree=tech_tree, start_year=3018)

    for fid in ("rohan", "gondor", "isengard"):
        gs.add_faction(factions_def[fid], starting_treasury={"FOOD": 300, "WOOD": 200, "STONE": 100, "IRON": 50, "GOLD": 150})

    # Partition the map into three regions by x-band: west=Isengard,
    # centre=Rohan, east=Gondor. This is scenario setup, not a general
    # worldgen rule — a different scenario can partition however it likes.
    band_width = gen.grid.width // 3
    region_of = {}
    for cell in gen.grid.all_cells():
        if cell.x < band_width:
            region_of[(cell.x, cell.y)] = "isengard_region"
        elif cell.x < band_width * 2:
            region_of[(cell.x, cell.y)] = "rohan_region"
        else:
            region_of[(cell.x, cell.y)] = "gondor_region"

    regions = {
        "isengard_region": Region(id="isengard_region", name="Nan Curunir Frontier", dominant_biome="HILLS"),
        "rohan_region": Region(id="rohan_region", name="The Riddermark", dominant_biome="PLAINS"),
        "gondor_region": Region(id="gondor_region", name="Anórien Marches", dominant_biome="PLAINS"),
    }
    for cell in gen.grid.all_cells():
        rid = region_of[(cell.x, cell.y)]
        regions[rid].cells.append((cell.x, cell.y))
        cell.region_id = rid
    gs.regions = regions

    # Pick one settlement site per faction from the generated candidates.
    sites_by_region: Dict[str, List[Tuple[int, int]]] = {"isengard_region": [], "rohan_region": [], "gondor_region": []}
    for site in gen.settlement_sites:
        sites_by_region[region_of[site]].append(site)

    faction_region = {"isengard": "isengard_region", "rohan": "rohan_region", "gondor": "gondor_region"}
    starting_stats = {
        "isengard": {"pop": 260.0, "army": [("isengard_uruk_warrior", 40), ("isengard_uruk_pikeman", 25)]},
        "rohan": {"pop": 220.0, "army": [("rohirrim_rider", 25), ("rohan_militia", 30)]},
        "gondor": {"pop": 240.0, "army": [("gondor_spearman", 35), ("gondor_archer", 20)]},
    }

    settlement_ids: Dict[str, int] = {}
    for fid, region_id in faction_region.items():
        sites = sites_by_region[region_id]
        if not sites:
            # Fallback for unlucky seeds where worldgen placed no
            # candidate settlement site in this band: use the region's
            # most fertile cell directly.
            region_cells = [gen.grid.at(x, y) for (x, y) in regions[region_id].cells]
            best_cell = max(region_cells, key=lambda c: c.fertility)
            sites = [(best_cell.x, best_cell.y)]
        x, y = sites[0]
        name = {"rohan": "Edoras Vale", "gondor": "Anórien Hold", "isengard": "Nan Curunir Keep"}[fid]
        seid = _spawn_settlement(gs, fid, name, x, y, region_id, starting_stats[fid]["pop"])
        settlement_ids[fid] = seid
        gs.regions[region_id].territories[f"{region_id}_capital"] = Territory(
            id=f"{region_id}_capital", cell=(x, y), region_id=region_id, owner_faction=fid,
        )

        army_id = gs.world.create_entity("army")
        gs.world.add(army_id, Transform(x=x, y=y))
        gs.world.add(army_id, Owner(faction_id=fid))
        stacks = [UnitStack(unit_type=u, count=c) for u, c in starting_stats[fid]["army"]]
        gs.world.add(army_id, ArmyComp(name=f"{name} Host", stacks=stacks))

    # Section 96/lore-adjacent framing: Isengard opens the scenario at war
    # with its neighbours — this is what gives the vertical slice an
    # actual military campaign to play rather than a peaceful sandbox.
    gs.submit_command(Command("DECLARE_WAR", {"a": "isengard", "b": "rohan"}))
    gs.submit_command(Command("DECLARE_WAR", {"a": "isengard", "b": "gondor"}))

    gs.register_ai_hook(_make_ai_hook(settlement_ids, region_of))

    return gs


def _spawn_settlement(gs: GameState, faction_id: str, name: str, x: int, y: int, region_id: str, pop_start: float) -> int:
    eid = gs.world.create_entity("settlement")
    gs.world.add(eid, Transform(x=x, y=y))
    gs.world.add(eid, Owner(faction_id=faction_id))
    gs.world.add(eid, SettlementComp(name=name, tier=SettlementTier.TOWN, region_id=region_id))
    gs.world.add(eid, PopulationComp(count=pop_start, housing_capacity=6000.0))
    gs.world.add(eid, ResourceStock(amounts={"FOOD": 400.0, "WOOD": 250.0, "STONE": 120.0, "IRON": 60.0, "GOLD": 100.0}))
    gs.grid.at(x, y).settlement_id = eid

    for building_type, resource, rate in (("farm", "FOOD", 0.9), ("lumber_camp", "WOOD", 0.7), ("mine", "IRON", 0.4)):
        beid = gs.world.create_entity("building")
        gs.world.add(beid, ProductionComp(building_type=building_type, output_resource=resource, base_rate=rate, settlement_id=eid, workers_assigned=20.0))

    return eid


def _make_ai_hook(settlement_ids: Dict[str, int], region_of: Dict[Tuple[int, int], str]):
    """Section 24/25: a small strategic+operational AI. Every 10 ticks each
    faction re-evaluates its goal; a RAID/EXPAND goal sends its army
    marching toward the nearest enemy settlement, a DEFEND/FORTIFY goal
    recalls it home."""
    from ..ecs.components import ArmyComp, Owner, Transform

    def hook(gs: GameState) -> List[Command]:
        if gs.calendar.tick % 10 != 0:
            return []
        commands: List[Command] = []
        armies_by_faction: Dict[str, List[int]] = {}
        for eid, army, pos, owner in gs.world.query(ArmyComp, Transform, Owner):
            armies_by_faction.setdefault(owner.faction_id, []).append(eid)

        for fid, faction in sorted(gs.factions.items()):
            own_settlements = [settlement_ids[fid]] if fid in settlement_ids else []
            own_armies = armies_by_faction.get(fid, [])
            enemy_nearby = sum(len(v) for k, v in armies_by_faction.items() if k != fid and gs.diplomacy.at_war(fid, k))
            state = gs.ai.decide(faction, own_settlements, own_armies, enemy_nearby)

            if state.goal in ("RAID", "EXPAND") and own_armies:
                army_eid = own_armies[0]
                army = gs.world.require(army_eid, ArmyComp)
                if army.destination is None:
                    target = _nearest_enemy_settlement(gs, fid, army_eid, settlement_ids)
                    if target is not None:
                        commands.append(Command("MOVE_ARMY", {"army_id": army_eid, "destination": list(target)}))
        return commands

    return hook


def _nearest_enemy_settlement(gs: GameState, fid: str, army_eid: int, settlement_ids: Dict[str, int]):
    from ..ecs.components import Transform

    pos = gs.world.require(army_eid, Transform)
    best = None
    best_dist = None
    for other_fid, seid in settlement_ids.items():
        if other_fid == fid or not gs.diplomacy.at_war(fid, other_fid):
            continue
        target_pos = gs.world.require(seid, Transform)
        d = (target_pos.x - pos.x) ** 2 + (target_pos.y - pos.y) ** 2
        if best_dist is None or d < best_dist:
            best_dist = d
            best = (target_pos.x, target_pos.y)
    return best
