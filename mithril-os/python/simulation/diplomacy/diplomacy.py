"""
Diplomacy engine.

Spec ref: 23 (diplomacy engine).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple


class DiplomaticStatus(str, Enum):
    PEACE = "PEACE"
    WAR = "WAR"
    ALLIANCE = "ALLIANCE"
    TRUCE = "TRUCE"
    VASSAL = "VASSAL"


@dataclass
class Relation:
    status: DiplomaticStatus = DiplomaticStatus.PEACE
    score: float = 0.0  # -100..100


class DiplomacyEngine:
    def __init__(self) -> None:
        self._relations: Dict[Tuple[str, str], Relation] = {}

    @staticmethod
    def _key(a: str, b: str) -> Tuple[str, str]:
        return (a, b) if a < b else (b, a)

    def relation(self, a: str, b: str) -> Relation:
        return self._relations.setdefault(self._key(a, b), Relation())

    def declare_war(self, a: str, b: str) -> Relation:
        rel = self.relation(a, b)
        rel.status = DiplomaticStatus.WAR
        rel.score = min(rel.score, -50.0)
        return rel

    def sign_peace(self, a: str, b: str) -> Relation:
        rel = self.relation(a, b)
        rel.status = DiplomaticStatus.PEACE
        rel.score = max(rel.score, -10.0)
        return rel

    def form_alliance(self, a: str, b: str) -> Relation:
        rel = self.relation(a, b)
        rel.status = DiplomaticStatus.ALLIANCE
        rel.score = max(rel.score, 40.0)
        return rel

    def at_war(self, a: str, b: str) -> bool:
        return self.relation(a, b).status == DiplomaticStatus.WAR

    def adjust(self, a: str, b: str, delta: float) -> Relation:
        rel = self.relation(a, b)
        rel.score = max(-100.0, min(100.0, rel.score + delta))
        return rel
