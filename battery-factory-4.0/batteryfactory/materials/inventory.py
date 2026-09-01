"""
Material inventory tracking (spec item 4): batches, supplier, cost, quality,
lead time, moisture, purity, availability -- with FIFO consumption so
electrode batches can be traced back to the raw-material batches they
consumed (feeds ``traceability.genealogy``).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from batteryfactory.datamodel.models import Batch, next_serial
from batteryfactory.materials.material_types import STANDARD_MATERIALS


def compute_quality_score(moisture_pct: float, purity_pct: float, max_moisture_pct: float, min_purity_pct: float) -> float:
    """0..1 acceptance score: 1.0 = comfortably within spec, 0.0 = at/over the reject edge."""
    moisture_margin = max(0.0, (max_moisture_pct - moisture_pct) / max(max_moisture_pct, 1e-9))
    purity_margin = max(0.0, (purity_pct - min_purity_pct) / max(100.0 - min_purity_pct, 1e-9))
    return max(0.0, min(1.0, 0.5 * moisture_margin + 0.5 * purity_margin))


@dataclass
class ConsumptionRecord:
    batch_id: str
    quantity_consumed: float


class InventoryLedger:
    """Per-material FIFO ledger of raw-material batches."""

    def __init__(self) -> None:
        self._queues: dict[str, deque[Batch]] = {}
        self.rejected_batches: list[Batch] = []
        self.all_received: list[Batch] = []

    def receive_batch(
        self,
        material_id: str,
        supplier_id: str,
        quantity: float,
        cost_per_unit: float,
        moisture_pct: float,
        purity_pct: float,
        lead_time_days: float,
        received_at: datetime | None = None,
    ) -> Batch:
        spec = STANDARD_MATERIALS.get(material_id)
        max_moisture = spec.max_moisture_pct if spec else 5.0
        min_purity = spec.min_purity_pct if spec else 95.0
        quality_score = compute_quality_score(moisture_pct, purity_pct, max_moisture, min_purity)
        batch = Batch(
            batch_id=next_serial("MATB"),
            material_id=material_id,
            supplier_id=supplier_id,
            quantity=quantity,
            unit=spec.material.unit if spec else "kg",
            cost_per_unit=cost_per_unit,
            received_at=received_at or datetime.utcnow(),
            moisture_pct=moisture_pct,
            purity_pct=purity_pct,
            lead_time_days=lead_time_days,
            quality_score=quality_score,
        )
        self.all_received.append(batch)
        if moisture_pct > max_moisture or purity_pct < min_purity:
            self.rejected_batches.append(batch)
            return batch  # rejected at goods-in inspection: never enters the usable queue
        self._queues.setdefault(material_id, deque()).append(batch)
        return batch

    def stock_level(self, material_id: str) -> float:
        return sum(b.quantity for b in self._queues.get(material_id, ()))

    def weighted_average_cost(self, material_id: str) -> float:
        batches = self._queues.get(material_id, ())
        total_qty = sum(b.quantity for b in batches)
        if total_qty <= 0:
            return 0.0
        return sum(b.quantity * b.cost_per_unit for b in batches) / total_qty

    def consume(self, material_id: str, quantity: float) -> tuple[list[ConsumptionRecord], float]:
        """FIFO consumption. Returns (records, quantity_actually_consumed)."""
        queue = self._queues.get(material_id, deque())
        remaining = quantity
        records: list[ConsumptionRecord] = []
        while remaining > 1e-9 and queue:
            batch = queue[0]
            take = min(batch.quantity, remaining)
            batch.quantity -= take
            remaining -= take
            records.append(ConsumptionRecord(batch.batch_id, take))
            if batch.quantity <= 1e-9:
                queue.popleft()
        return records, quantity - remaining

    def availability_ratio(self, material_id: str, required_quantity: float) -> float:
        if required_quantity <= 0:
            return 1.0
        return min(1.0, self.stock_level(material_id) / required_quantity)
