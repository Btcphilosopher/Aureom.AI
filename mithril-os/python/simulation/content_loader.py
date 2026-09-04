"""
Data-driven content loader.

Spec ref: 81 (modding engine), 103 (data-driven content — "do not
hard-code unit stats, building costs, technology, faction bonuses").

Loads YAML definitions from mithril-os/content/ into the typed
dataclasses the simulation systems consume. This is the seam a modder
(or the future scenario/campaign editors, sections 82-83) would target:
add a YAML file, no engine code changes required.
"""

from __future__ import annotations

import os
from typing import Dict, List

import yaml

from .military.units import UnitDefinition
from .settlements.buildings import BuildingDefinition
from .technology.tech_tree import TechNode
from .world.faction import FactionDefinition

CONTENT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "content"))


def _load_yaml_dir(subdir: str) -> List[dict]:
    path = os.path.join(CONTENT_ROOT, subdir)
    out = []
    if not os.path.isdir(path):
        return out
    for fname in sorted(os.listdir(path)):
        if not (fname.endswith(".yaml") or fname.endswith(".yml")):
            continue
        with open(os.path.join(path, fname), "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if isinstance(data, list):
                out.extend(data)
            elif data is not None:
                out.append(data)
    return out


def load_factions() -> Dict[str, FactionDefinition]:
    return {d["faction_id"]: FactionDefinition(**d) for d in _load_yaml_dir("factions")}


def load_units() -> Dict[str, UnitDefinition]:
    return {d["unit_id"]: UnitDefinition(**d) for d in _load_yaml_dir("units")}


def load_buildings() -> Dict[str, BuildingDefinition]:
    return {d["building_id"]: BuildingDefinition(**d) for d in _load_yaml_dir("buildings")}


def load_technologies() -> Dict[str, TechNode]:
    return {d["tech_id"]: TechNode(**d) for d in _load_yaml_dir("technologies")}
