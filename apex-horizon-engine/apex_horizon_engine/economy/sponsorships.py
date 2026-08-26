"""
Sponsorship deals: passive income + event reward multipliers unlocked as
overall reputation tier rises. Each deal has an upkeep expectation (a
minimum discipline reputation to *keep*, not just unlock) so a
sponsorship can lapse if the player stops performing in that discipline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from apex_horizon_engine.progression.reputation import ReputationBook


@dataclass(frozen=True)
class SponsorshipDeal:
    sponsor_id: str
    display_name: str
    discipline: str
    tier_required: int
    daily_income_credits: int
    reward_multiplier: float
    upkeep_min_reputation: float


CATALOGUE: List[SponsorshipDeal] = [
    SponsorshipDeal("velocore_energy", "Velocore Energy", "street", 2, 320, 1.05, 6.0),
    SponsorshipDeal("driftline_apparel", "Driftline Apparel", "drift", 2, 260, 1.08, 6.0),
    SponsorshipDeal("terraflex_tires", "Terraflex Off-Road", "offroad", 3, 400, 1.1, 10.0),
    SponsorshipDeal("apex_petrol", "Apex Petrol Co.", "circuit", 3, 480, 1.1, 10.0),
    SponsorshipDeal("horizon_motors", "Horizon Motors Group", "endurance", 5, 900, 1.18, 18.0),
    SponsorshipDeal("neon_holo_media", "Neon Holo Media", "street", 6, 1400, 1.22, 22.0),
]


@dataclass
class SponsorshipBook:
    active_deal_ids: List[str] = field(default_factory=list)

    def available_deals(self, reputation: ReputationBook) -> List[SponsorshipDeal]:
        tier = reputation.overall_tier()
        return [d for d in CATALOGUE if tier >= d.tier_required]

    def sign(self, sponsor_id: str, reputation: ReputationBook) -> bool:
        deal = next((d for d in CATALOGUE if d.sponsor_id == sponsor_id), None)
        if deal is None or sponsor_id in self.active_deal_ids:
            return False
        if reputation.overall_tier() < deal.tier_required:
            return False
        self.active_deal_ids.append(sponsor_id)
        return True

    def check_upkeep(self, reputation: ReputationBook) -> List[str]:
        """Drop any deal whose discipline reputation has fallen below its
        upkeep requirement; returns the sponsor_ids that lapsed."""
        lapsed = []
        for sponsor_id in list(self.active_deal_ids):
            deal = next(d for d in CATALOGUE if d.sponsor_id == sponsor_id)
            if reputation.scores.get(deal.discipline, 0.0) < deal.upkeep_min_reputation:
                self.active_deal_ids.remove(sponsor_id)
                lapsed.append(sponsor_id)
        return lapsed

    def daily_income(self) -> int:
        return sum(d.daily_income_credits for d in CATALOGUE if d.sponsor_id in self.active_deal_ids)

    def reward_multiplier_for(self, discipline: str) -> float:
        mult = 1.0
        for sponsor_id in self.active_deal_ids:
            deal = next(d for d in CATALOGUE if d.sponsor_id == sponsor_id)
            if deal.discipline == discipline:
                mult *= deal.reward_multiplier
        return mult
