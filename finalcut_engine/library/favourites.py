"""Convenience API over :class:`RatingStore` for favourite/reject workflows."""
from __future__ import annotations

from dataclasses import dataclass

from finalcut_engine.library.ratings import Rating, RatingStore


@dataclass
class FavouritesManager:
    ratings: RatingStore

    def mark_favourite(self, subject_id: str) -> None:
        self.ratings.set(subject_id, Rating.FAVOURITE)

    def mark_rejected(self, subject_id: str) -> None:
        self.ratings.set(subject_id, Rating.REJECTED)

    def clear_rating(self, subject_id: str) -> None:
        self.ratings.set(subject_id, Rating.UNRATED)

    def toggle_favourite(self, subject_id: str) -> bool:
        is_fav = self.ratings.get(subject_id) == Rating.FAVOURITE
        self.ratings.set(subject_id, Rating.UNRATED if is_fav else Rating.FAVOURITE)
        return not is_fav

    def is_favourite(self, subject_id: str) -> bool:
        return self.ratings.get(subject_id) == Rating.FAVOURITE

    def is_rejected(self, subject_id: str) -> bool:
        return self.ratings.get(subject_id) == Rating.REJECTED

    def favourites(self) -> list[str]:
        return self.ratings.ids_with(Rating.FAVOURITE)

    def rejected(self) -> list[str]:
        return self.ratings.ids_with(Rating.REJECTED)
