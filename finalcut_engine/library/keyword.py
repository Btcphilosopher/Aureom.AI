"""Keyword tagging, including sub-clip keyword ranges (as in Final Cut Pro)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from finalcut_engine.core.timebase import Time, TimeRange


@dataclass(frozen=True)
class KeywordRange:
    """A keyword applied either to a whole asset (``range is None``) or a span of it."""

    asset_id: str
    keyword: str
    range: Optional[TimeRange] = None

    def applies_at(self, t: Time) -> bool:
        return self.range is None or self.range.contains(t)


class KeywordIndex:
    """Fast keyword -> asset lookups, and the reverse, for smart collections."""

    def __init__(self) -> None:
        self._by_keyword: Dict[str, List[KeywordRange]] = {}
        self._by_asset: Dict[str, List[KeywordRange]] = {}

    def add(self, kr: KeywordRange) -> None:
        self._by_keyword.setdefault(kr.keyword.lower(), []).append(kr)
        self._by_asset.setdefault(kr.asset_id, []).append(kr)

    def remove_keyword(self, asset_id: str, keyword: str) -> None:
        key = keyword.lower()
        self._by_keyword[key] = [kr for kr in self._by_keyword.get(key, []) if kr.asset_id != asset_id]
        self._by_asset[asset_id] = [kr for kr in self._by_asset.get(asset_id, []) if kr.keyword.lower() != key]

    def keywords_for(self, asset_id: str) -> List[str]:
        return sorted({kr.keyword for kr in self._by_asset.get(asset_id, [])})

    def assets_for_keyword(self, keyword: str) -> List[str]:
        return sorted({kr.asset_id for kr in self._by_keyword.get(keyword.lower(), [])})

    def all_keywords(self) -> List[str]:
        return sorted(self._by_keyword.keys())
