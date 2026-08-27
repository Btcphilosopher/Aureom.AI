"""Manual and rule-based ("smart") collections over a library's media assets."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, List

if TYPE_CHECKING:  # pragma: no cover - avoids a library <-> collection import cycle
    from finalcut_engine.library.library import Library
    from finalcut_engine.media.asset import MediaAsset


@dataclass
class Collection:
    """A manually curated, ordered set of assets."""

    name: str
    asset_ids: List[str] = field(default_factory=list)

    def add(self, asset_id: str) -> None:
        if asset_id not in self.asset_ids:
            self.asset_ids.append(asset_id)

    def remove(self, asset_id: str) -> None:
        if asset_id in self.asset_ids:
            self.asset_ids.remove(asset_id)


#: A rule is (library, asset) -> bool.
SmartRule = Callable[["Library", "MediaAsset"], bool]


@dataclass
class SmartCollection:
    """A saved search: recomputed on demand against the current library state."""

    name: str
    rules: List[SmartRule] = field(default_factory=list)
    match_all: bool = True  # AND vs OR across rules

    def matches(self, library: "Library", asset: "MediaAsset") -> bool:
        if not self.rules:
            return True
        results = (rule(library, asset) for rule in self.rules)
        return all(results) if self.match_all else any(results)

    def evaluate(self, library: "Library") -> List["MediaAsset"]:
        return [a for a in library.all_assets() if self.matches(library, a)]


# -- reusable rule factories --------------------------------------------------
def rule_keyword(keyword: str) -> SmartRule:
    key = keyword.lower()
    return lambda library, asset: key in {k.lower() for k in library.keywords.keywords_for(asset.id)}


def rule_rating(rating) -> SmartRule:
    return lambda library, asset: library.ratings.get(asset.id) == rating


def rule_text(query: str) -> SmartRule:
    q = query.lower()
    return lambda library, asset: q in asset.searchable_text()


def rule_video_only() -> SmartRule:
    return lambda library, asset: asset.metadata.is_video


def rule_min_duration(seconds: float) -> SmartRule:
    return lambda library, asset: asset.metadata.duration_seconds >= seconds
