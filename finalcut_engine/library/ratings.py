"""Clip ratings: Final Cut Pro's three-state favourite / none / reject model."""
from __future__ import annotations

from enum import IntEnum
from typing import Dict


class Rating(IntEnum):
    REJECTED = -1
    UNRATED = 0
    FAVOURITE = 1


class RatingStore:
    """Maps asset (or clip range) ids to a :class:`Rating`, defaulting to UNRATED."""

    def __init__(self) -> None:
        self._ratings: Dict[str, Rating] = {}

    def set(self, subject_id: str, rating: Rating) -> None:
        if rating == Rating.UNRATED:
            self._ratings.pop(subject_id, None)
        else:
            self._ratings[subject_id] = rating

    def get(self, subject_id: str) -> Rating:
        return self._ratings.get(subject_id, Rating.UNRATED)

    def ids_with(self, rating: Rating) -> list[str]:
        return [sid for sid, r in self._ratings.items() if r == rating]
