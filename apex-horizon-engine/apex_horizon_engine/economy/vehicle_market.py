"""
Vehicle marketplace: buy/sell against ``utils.config.VEHICLE_PRESETS``
with a slow supply/demand price drift per vehicle, gated by
``progression.unlock_tree``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, Optional

from apex_horizon_engine.economy.credits import CreditLedger
from apex_horizon_engine.progression.reputation import ReputationBook
from apex_horizon_engine.progression.unlock_tree import can_purchase
from apex_horizon_engine.utils.config import VEHICLE_PRESETS, VehicleSpec, get_vehicle_preset

RESALE_FRACTION = 0.62


@dataclass
class MarketListing:
    vehicle_id: str
    current_price: int


@dataclass
class VehicleMarket:
    seed: int = 0
    listings: Dict[str, MarketListing] = field(default_factory=dict)
    _rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self):
        self._rng = random.Random(self.seed)
        for spec in VEHICLE_PRESETS.values():
            self.listings[spec.vehicle_id] = MarketListing(spec.vehicle_id, spec.base_price_credits)

    def tick_prices(self, dt_days: float = 1.0) -> None:
        """Small random walk around each vehicle's base price -- keeps
        the market feeling alive without letting prices wander far from
        their design intent."""
        for vehicle_id, listing in self.listings.items():
            base = VEHICLE_PRESETS[vehicle_id].base_price_credits
            drift = self._rng.uniform(-0.015, 0.015) * dt_days
            new_price = listing.current_price * (1.0 + drift)
            # mean-revert toward base so prices don't drift unboundedly
            new_price += (base - new_price) * 0.02 * dt_days
            listing.current_price = max(int(base * 0.75), min(int(base * 1.35), int(new_price)))

    def purchase(self, vehicle_id: str, ledger: CreditLedger, reputation: ReputationBook) -> Optional[VehicleSpec]:
        spec = get_vehicle_preset(vehicle_id)
        listing = self.listings[vehicle_id]
        if not can_purchase(spec, reputation, ledger.balance):
            return None
        if not ledger.spend(listing.current_price, reason=f"purchase:{vehicle_id}"):
            return None
        return spec

    def sell(self, spec: VehicleSpec, ledger: CreditLedger) -> int:
        listing = self.listings.get(spec.vehicle_id)
        base_price = listing.current_price if listing else spec.base_price_credits
        payout = int(base_price * RESALE_FRACTION)
        ledger.earn(payout, reason=f"sell:{spec.vehicle_id}")
        return payout

    def price(self, vehicle_id: str) -> int:
        return self.listings[vehicle_id].current_price
