"""
Deterministic save/load.

Spec ref: 60 (campaign save system — "use deterministic serialization"),
62 (deterministic simulation).

Rather than a generic reflection-based dump (fragile across dataclasses
holding enums/tuples), each component type used by the vertical slice has
an explicit to_dict/from_dict pair here. This is more code up front but
survives schema changes predictably and is easy to extend per-component
as new component types are added — the honest tradeoff called out in
section 66 (clean interfaces over premature generality).
"""

from __future__ import annotations

from typing import Any, Dict

from ..ecs.core import World
from ..ecs.components import (
    ArmyComp, HeroComp, Owner, PopulationComp, ProductionComp,
    ResourceStock, SettlementComp, SettlementTier, Transform, UnitStack,
)

_COMPONENT_CODECS = {}


def _register(cls):
    def wrap(to_fn, from_fn):
        _COMPONENT_CODECS[cls.__name__] = (to_fn, from_fn)
    return wrap


_register(Transform)(
    lambda c: {"x": c.x, "y": c.y},
    lambda d: Transform(x=d["x"], y=d["y"]),
)
_register(Owner)(
    lambda c: {"faction_id": c.faction_id},
    lambda d: Owner(faction_id=d["faction_id"]),
)
_register(ResourceStock)(
    lambda c: {"amounts": dict(c.amounts)},
    lambda d: ResourceStock(amounts=dict(d["amounts"])),
)
_register(SettlementComp)(
    lambda c: {
        "name": c.name, "tier": c.tier.value, "region_id": c.region_id,
        "buildings": list(c.buildings), "garrison": c.garrison,
        "wall_health": c.wall_health, "wall_max": c.wall_max, "happiness": c.happiness,
    },
    lambda d: SettlementComp(
        name=d["name"], tier=SettlementTier(d["tier"]), region_id=d["region_id"],
        buildings=list(d["buildings"]), garrison=d["garrison"],
        wall_health=d["wall_health"], wall_max=d["wall_max"], happiness=d["happiness"],
    ),
)
_register(PopulationComp)(
    lambda c: {
        "count": c.count, "growth_rate": c.growth_rate, "housing_capacity": c.housing_capacity,
        "workers_idle": c.workers_idle, "workers_food": c.workers_food,
        "workers_industry": c.workers_industry, "soldiers": c.soldiers,
    },
    lambda d: PopulationComp(**d),
)
_register(ProductionComp)(
    lambda c: {
        "building_type": c.building_type, "output_resource": c.output_resource,
        "base_rate": c.base_rate, "settlement_id": c.settlement_id,
        "workers_assigned": c.workers_assigned,
    },
    lambda d: ProductionComp(**d),
)
_register(ArmyComp)(
    lambda c: {
        "name": c.name,
        "stacks": [{"unit_type": s.unit_type, "count": s.count, "health_fraction": s.health_fraction} for s in c.stacks],
        "supply": c.supply, "morale": c.morale, "formation": c.formation,
        "destination": list(c.destination) if c.destination else None,
        "path": [list(p) for p in c.path], "move_progress": c.move_progress,
    },
    lambda d: ArmyComp(
        name=d["name"],
        stacks=[UnitStack(unit_type=s["unit_type"], count=s["count"], health_fraction=s["health_fraction"]) for s in d["stacks"]],
        supply=d["supply"], morale=d["morale"], formation=d["formation"],
        destination=tuple(d["destination"]) if d["destination"] else None,
        path=[tuple(p) for p in d["path"]], move_progress=d["move_progress"],
    ),
)
_register(HeroComp)(
    lambda c: {
        "name": c.name, "level": c.level, "experience": c.experience,
        "faction_id": c.faction_id, "commanding_army": c.commanding_army, "skills": list(c.skills),
    },
    lambda d: HeroComp(**d),
)


def world_to_dict(world: World) -> Dict[str, Any]:
    out = {
        "next_id": world._next_id,
        "alive": sorted(world.alive),
        "kind": {str(eid): world.kind[eid] for eid in sorted(world.alive)},
        "components": {},
    }
    for type_name, store in world.components.items():
        if type_name not in _COMPONENT_CODECS:
            continue
        to_fn, _ = _COMPONENT_CODECS[type_name]
        out["components"][type_name] = {str(eid): to_fn(comp) for eid, comp in sorted(store.items())}
    return out


def world_from_dict(data: Dict[str, Any]) -> World:
    world = World()
    world._next_id = data["next_id"]
    world.alive = set(data["alive"])
    world.kind = {int(k): v for k, v in data["kind"].items()}
    world.tags = {eid: set() for eid in world.alive}
    for type_name, entries in data["components"].items():
        _, from_fn = _COMPONENT_CODECS[type_name]
        world.components[type_name] = {int(eid): from_fn(d) for eid, d in entries.items()}
    return world
