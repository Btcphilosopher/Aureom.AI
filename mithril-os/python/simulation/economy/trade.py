"""
Trade engine (vertical-slice scope).

Spec ref: 32 (trade engine), 49 (resource market: P = f(supply, demand,
distance, scarcity, security)).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class TradeRoute:
    route_id: str
    origin_settlement: int
    destination_settlement: int
    resource: str
    volume: float
    active: bool = True
    security: float = 1.0  # 0..1, reduced by raiding/war along the route


class Market:
    """A single shared price table. Section 49's formula, kept simple:
    price rises with demand/supply pressure and falls with security."""

    BASE_PRICES = {
        "FOOD": 1.0, "WOOD": 1.2, "STONE": 1.5, "IRON": 3.0, "GOLD": 8.0,
    }

    def __init__(self) -> None:
        self.supply: Dict[str, float] = {}
        self.demand: Dict[str, float] = {}

    def record_supply(self, resource: str, qty: float) -> None:
        self.supply[resource] = self.supply.get(resource, 0.0) + qty

    def record_demand(self, resource: str, qty: float) -> None:
        self.demand[resource] = self.demand.get(resource, 0.0) + qty

    def price(self, resource: str, distance: float = 0.0, security: float = 1.0) -> float:
        base = self.BASE_PRICES.get(resource, 1.0)
        s = max(1.0, self.supply.get(resource, 1.0))
        d = max(1.0, self.demand.get(resource, 1.0))
        pressure = d / s
        distance_cost = 1.0 + distance * 0.01
        security_cost = 1.0 + (1.0 - security) * 0.5
        return base * pressure * distance_cost * security_cost

    def reset_tick(self) -> None:
        self.supply.clear()
        self.demand.clear()


class TradeEngine:
    def __init__(self) -> None:
        self.routes: List[TradeRoute] = []
        self.market = Market()

    def establish_route(self, route: TradeRoute) -> None:
        self.routes.append(route)

    def block_routes_through(self, settlement_id: int) -> None:
        for r in self.routes:
            if settlement_id in (r.origin_settlement, r.destination_settlement):
                r.active = False

    def tick(self) -> List[TradeRoute]:
        active = [r for r in self.routes if r.active]
        for r in active:
            self.market.record_supply(r.resource, r.volume * r.security)
            self.market.record_demand(r.resource, r.volume)
        return active
