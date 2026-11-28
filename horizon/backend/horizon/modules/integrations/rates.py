"""Adaptateur de taux de change.

``DeterministicRateProvider`` produit des taux synthétiques reproductibles
(fonction de la date). Ce ne sont PAS des taux de marché.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

SOURCE = "Simulateur de taux HORIZON (synthétique, non contractuel)"
BASE_MIDS = {
    ("EUR", "USD"): Decimal("1.0842"),
    ("EUR", "GBP"): Decimal("0.8571"),
    ("EUR", "CHF"): Decimal("0.9412"),
    ("EUR", "JPY"): Decimal("162.35"),
    ("EUR", "SEK"): Decimal("11.2150"),
    ("EUR", "PLN"): Decimal("4.2930"),
}


@dataclass
class RateObservation:
    base: str
    quote: str
    rate: Decimal
    as_of: date
    source: str


class RateProvider(Protocol):
    def rates_for(self, as_of: date) -> list[RateObservation]: ...


class DeterministicRateProvider:
    def rates_for(self, as_of: date) -> list[RateObservation]:
        out = []
        for (b, q), mid in BASE_MIDS.items():
            h = int(hashlib.sha256(f"{b}{q}{as_of.isoformat()}".encode()).hexdigest()[:8], 16)
            # variation déterministe de ±0,4 %
            factor = Decimal(1) + (Decimal(h % 801) - Decimal(400)) / Decimal(100000)
            out.append(RateObservation(b, q, (mid * factor).quantize(Decimal("0.000001")), as_of, SOURCE))
        return out


provider: RateProvider = DeterministicRateProvider()
