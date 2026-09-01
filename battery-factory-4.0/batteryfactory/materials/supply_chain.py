"""
Supply-chain digital twin (spec item 5): supplier models with capacity,
lead time, reliability, price, MOQ, location and quality distribution, plus
disruption simulation (delay, shortage, price shock, transport disruption,
quality failure).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class DisruptionType(str, Enum):
    NONE = "none"
    SUPPLIER_DELAY = "supplier_delay"
    MATERIAL_SHORTAGE = "material_shortage"
    PRICE_SHOCK = "price_shock"
    TRANSPORT_DISRUPTION = "transport_disruption"
    QUALITY_FAILURE = "quality_failure"


@dataclass
class Supplier:
    supplier_id: str
    name: str
    material_id: str
    location: str
    monthly_capacity: float
    lead_time_days_mean: float
    lead_time_days_std: float
    reliability: float           # P(on-time, no disruption) in [0,1]
    price_per_unit: float
    minimum_order_quantity: float
    quality_mean_pct: float      # mean purity, say
    quality_std_pct: float
    disruption_probability: float  # baseline chance of *any* disruption per order


@dataclass
class OrderOutcome:
    supplier_id: str
    ordered_quantity: float
    delivered_quantity: float
    actual_lead_time_days: float
    actual_price_per_unit: float
    actual_purity_pct: float
    disruption: DisruptionType


class SupplyChainSimulator:
    def __init__(self, rng: np.random.Generator | None = None) -> None:
        self.rng = rng or np.random.default_rng()

    def place_order(self, supplier: Supplier, quantity: float) -> OrderOutcome:
        quantity = max(quantity, supplier.minimum_order_quantity)
        disrupted = self.rng.random() > supplier.reliability or self.rng.random() < supplier.disruption_probability
        disruption = DisruptionType.NONE
        delivered = quantity
        lead_time = max(0.0, self.rng.normal(supplier.lead_time_days_mean, supplier.lead_time_days_std))
        price = supplier.price_per_unit
        purity = float(np.clip(self.rng.normal(supplier.quality_mean_pct, supplier.quality_std_pct), 0.0, 100.0))

        if disrupted:
            disruption = DisruptionType(
                self.rng.choice(
                    [d.value for d in DisruptionType if d != DisruptionType.NONE],
                    p=[0.30, 0.25, 0.20, 0.15, 0.10],
                )
            )
            if disruption is DisruptionType.SUPPLIER_DELAY:
                lead_time *= self.rng.uniform(1.5, 3.0)
            elif disruption is DisruptionType.MATERIAL_SHORTAGE:
                delivered = quantity * self.rng.uniform(0.3, 0.8)
            elif disruption is DisruptionType.PRICE_SHOCK:
                price *= self.rng.uniform(1.15, 1.6)
            elif disruption is DisruptionType.TRANSPORT_DISRUPTION:
                lead_time *= self.rng.uniform(1.3, 2.2)
            elif disruption is DisruptionType.QUALITY_FAILURE:
                purity = float(np.clip(purity - self.rng.uniform(2.0, 8.0), 0.0, 100.0))

        return OrderOutcome(
            supplier_id=supplier.supplier_id,
            ordered_quantity=quantity,
            delivered_quantity=delivered,
            actual_lead_time_days=lead_time,
            actual_price_per_unit=price,
            actual_purity_pct=purity,
            disruption=disruption,
        )
