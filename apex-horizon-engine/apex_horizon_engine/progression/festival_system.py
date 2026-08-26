"""
Festival influence: as the player's overall reputation grows, their
"festival" expands its footprint into more zones, raising festival tier
(which ``ai.crowd_simulation`` and event rewards both read) and unlocking
zone-level festival hubs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from apex_horizon_engine.progression.reputation import ReputationBook
from apex_horizon_engine.utils.config import WORLD_ZONES

INFLUENCE_PER_ZONE_TIER = 60.0


@dataclass
class FestivalSystem:
    zone_influence: Dict[str, float] = field(default_factory=lambda: {z: 0.0 for z in WORLD_ZONES})

    def award_influence(self, zone_id: str, amount: float) -> None:
        if zone_id not in self.zone_influence:
            self.zone_influence[zone_id] = 0.0
        self.zone_influence[zone_id] += amount

    def zone_tier(self, zone_id: str) -> int:
        return min(5, 1 + int(self.zone_influence.get(zone_id, 0.0) // INFLUENCE_PER_ZONE_TIER))

    def global_tier(self, reputation: ReputationBook) -> int:
        """Overall festival scale is a blend of raw reputation (skill
        recognised) and total influence spread (footprint), so a
        one-discipline specialist and a globe-trotting generalist reach
        the top tier by different but equally valid paths."""
        rep_component = reputation.overall_tier()
        spread_component = 1 + int(sum(1 for v in self.zone_influence.values() if v > INFLUENCE_PER_ZONE_TIER))
        return min(10, max(rep_component, spread_component))

    def expanded_zones(self) -> Dict[str, int]:
        return {z: self.zone_tier(z) for z in self.zone_influence if self.zone_tier(z) > 1}
