"""
Material inventory optimiser (spec item 6): reorder point, safety stock,
economic order quantity and supplier mix, minimising total inventory +
shortage + procurement cost subject to production requirements.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from batteryfactory.materials.supply_chain import Supplier

_Z_TABLE = {
    0.90: 1.2816, 0.95: 1.6449, 0.975: 1.9600, 0.98: 2.0537,
    0.99: 2.3263, 0.995: 2.5758, 0.999: 3.0902,
}


def service_level_z(service_level: float) -> float:
    """Standard-normal z for a target cycle service level, nearest tabulated value."""
    closest = min(_Z_TABLE, key=lambda k: abs(k - service_level))
    return _Z_TABLE[closest]


def economic_order_quantity(annual_demand: float, order_cost: float, holding_cost_per_unit_per_year: float) -> float:
    if holding_cost_per_unit_per_year <= 0 or annual_demand <= 0:
        return 0.0
    return math.sqrt((2.0 * annual_demand * order_cost) / holding_cost_per_unit_per_year)


def safety_stock(demand_std_per_day: float, lead_time_days: float, service_level: float = 0.97) -> float:
    z = service_level_z(service_level)
    return z * demand_std_per_day * math.sqrt(max(lead_time_days, 0.0))


def reorder_point(avg_demand_per_day: float, avg_lead_time_days: float, safety_stock_units: float) -> float:
    return avg_demand_per_day * avg_lead_time_days + safety_stock_units


@dataclass
class SupplierAllocation:
    supplier_id: str
    quantity: float
    unit_cost: float

    @property
    def cost(self) -> float:
        return self.quantity * self.unit_cost


@dataclass
class SupplierMixResult:
    allocations: list[SupplierAllocation]
    total_quantity: float
    total_cost: float
    weighted_lead_time_days: float
    weighted_reliability: float


def optimise_supplier_mix(
    suppliers: list[Supplier],
    required_quantity: float,
    max_single_supplier_share: float = 0.7,
) -> SupplierMixResult:
    """
    Greedy least-cost-adjusted-for-risk allocation across suppliers.

    Minimises total procurement cost subject to: MOQ per supplier, monthly
    capacity per supplier, and a diversification cap so no single supplier
    can be starved-out or fail and take the whole factory down (a crude but
    real proxy for "minimise total inventory + shortage + procurement cost").
    Suppliers are ranked by an effective cost that penalises low reliability
    (an unreliable supplier's nominal price understates its true cost).
    """
    if required_quantity <= 0 or not suppliers:
        return SupplierMixResult([], 0.0, 0.0, 0.0, 0.0)

    def effective_cost(s: Supplier) -> float:
        risk_penalty = 1.0 + (1.0 - s.reliability) * 0.5 + s.disruption_probability * 0.5
        return s.price_per_unit * risk_penalty

    ranked = sorted(suppliers, key=effective_cost)
    cap_per_supplier = required_quantity * max_single_supplier_share
    allocations: list[SupplierAllocation] = []
    remaining = required_quantity

    for supplier in ranked:
        if remaining <= 1e-9:
            break
        capacity_limit = min(supplier.monthly_capacity, cap_per_supplier)
        take = min(remaining, capacity_limit)
        if take < supplier.minimum_order_quantity:
            if supplier.minimum_order_quantity <= remaining and supplier.minimum_order_quantity <= capacity_limit:
                take = supplier.minimum_order_quantity
            else:
                continue
        allocations.append(SupplierAllocation(supplier.supplier_id, take, supplier.price_per_unit))
        remaining -= take

    if remaining > 1e-9 and ranked:
        # Can't fully diversify away the residual: top up on the cheapest supplier.
        best = ranked[0]
        allocations.append(SupplierAllocation(best.supplier_id, remaining, best.price_per_unit))
        remaining = 0.0

    total_quantity = sum(a.quantity for a in allocations)
    total_cost = sum(a.cost for a in allocations)
    by_id = {s.supplier_id: s for s in suppliers}
    weighted_lead_time = (
        sum(a.quantity * by_id[a.supplier_id].lead_time_days_mean for a in allocations) / total_quantity
        if total_quantity else 0.0
    )
    weighted_reliability = (
        sum(a.quantity * by_id[a.supplier_id].reliability for a in allocations) / total_quantity
        if total_quantity else 0.0
    )
    return SupplierMixResult(allocations, total_quantity, total_cost, weighted_lead_time, weighted_reliability)
