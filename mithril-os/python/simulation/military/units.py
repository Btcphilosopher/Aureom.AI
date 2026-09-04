"""
Unit definitions.

Spec ref: 15 (military engine).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class UnitDefinition:
    unit_id: str
    name: str
    category: str  # INFANTRY, ARCHERS, SPEARMEN, CAVALRY, ELITE_INFANTRY, SCOUTS, SIEGE, NAVAL, MONSTROUS, SPECIAL
    health: float
    armour: float
    attack: float
    defence: float
    speed: float          # movement points per tick
    attack_range: float    # 0 = melee
    accuracy: float        # 0..1, relevant for ranged units
    morale: float
    upkeep: Dict[str, float] = field(default_factory=dict)
    recruit_cost: Dict[str, float] = field(default_factory=dict)
    recruit_time_days: int = 3
    is_cavalry: bool = False


class UnitCatalogue:
    def __init__(self, definitions: List[UnitDefinition]) -> None:
        self.definitions: Dict[str, UnitDefinition] = {d.unit_id: d for d in definitions}

    def get(self, unit_id: str) -> UnitDefinition:
        return self.definitions[unit_id]
