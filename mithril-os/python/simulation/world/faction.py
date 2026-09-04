"""
FactionDefinition and runtime Faction state.

Spec ref: 07 (faction engine), 08 (species/culture engine), 48 (faction
economic models).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class FactionDefinition:
    """Static, data-driven identity loaded from content/factions/*.yaml
    (section 103: do not hard-code faction bonuses)."""
    faction_id: str
    name: str
    culture: str
    species: str
    government: str
    economic_model: str  # e.g. "mining_metallurgy", "forestry_craft", "agriculture_trade", "raiding"
    resource_priority: List[str] = field(default_factory=list)
    unit_cost_modifiers: Dict[str, float] = field(default_factory=dict)
    production_modifiers: Dict[str, float] = field(default_factory=dict)
    starting_technologies: List[str] = field(default_factory=list)
    ai_personality: str = "balanced"  # expander / defender / raider / trader / balanced


@dataclass
class Faction:
    """Runtime state for a faction within a running campaign."""
    definition: FactionDefinition
    capital_settlement: Optional[int] = None  # ECS entity id
    territories: List[str] = field(default_factory=list)  # Territory ids
    treasury: Dict[str, float] = field(default_factory=dict)
    researched_technologies: List[str] = field(default_factory=list)
    tech_modifiers: Dict[str, float] = field(default_factory=dict)
    at_war_with: List[str] = field(default_factory=list)
    allied_with: List[str] = field(default_factory=list)
    is_alive: bool = True

    @property
    def faction_id(self) -> str:
        return self.definition.faction_id

    def modifier(self, key: str) -> float:
        base = self.definition.production_modifiers.get(key, 1.0)
        tech = self.tech_modifiers.get(key, 1.0)
        return base * tech
