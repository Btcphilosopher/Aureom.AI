"""
Technology engine.

Spec ref: 14 (age-specific technology tree — "technology must alter
actual simulation variables").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class TechNode:
    tech_id: str
    name: str
    category: str
    age: str
    cost: Dict[str, float]
    prerequisites: List[str] = field(default_factory=list)
    effects: Dict[str, float] = field(default_factory=dict)  # e.g. {"armour_multiplier": 1.15}
    research_time_days: int = 10


class TechTree:
    def __init__(self, nodes: List[TechNode]) -> None:
        self.nodes: Dict[str, TechNode] = {n.tech_id: n for n in nodes}

    def available(self, researched: List[str]) -> List[TechNode]:
        done = set(researched)
        return [
            n for n in self.nodes.values()
            if n.tech_id not in done and all(p in done for p in n.prerequisites)
        ]

    def apply_effects(self, tech_id: str, modifiers: Dict[str, float]) -> Dict[str, float]:
        """Fold a researched tech's effects into a faction's modifier
        table. Multiplicative composition, e.g. two +15% armour techs
        yield 1.15 * 1.15, not a flat +30% — this is what keeps stacking
        techs from trivializing balance (section 84/85)."""
        node = self.nodes[tech_id]
        out = dict(modifiers)
        for key, value in node.effects.items():
            out[key] = out.get(key, 1.0) * value
        return out
