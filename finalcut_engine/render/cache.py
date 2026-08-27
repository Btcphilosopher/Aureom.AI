"""An LRU render cache keyed by content/parameter fingerprints.

Because render-graph node keys are derived from a node's own parameters *and*
its inputs' keys (see ``render_graph.py``), a cache hit/miss is entirely a
function of "did anything this frame actually depends on change" — no manual
invalidation bookkeeping is needed. Changing a colour grade changes only the
colour node's (and everything downstream of it) key; an unrelated clip's
cached frames are untouched.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Hashable, Optional


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


class RenderCache:
    def __init__(self, max_items: int = 256) -> None:
        self.max_items = max_items
        self._store: "OrderedDict[Hashable, Any]" = OrderedDict()
        self.stats = CacheStats()

    def get(self, key: Hashable) -> Optional[Any]:
        if key in self._store:
            self._store.move_to_end(key)
            self.stats.hits += 1
            return self._store[key]
        self.stats.misses += 1
        return None

    def put(self, key: Hashable, value: Any) -> None:
        self._store[key] = value
        self._store.move_to_end(key)
        while len(self._store) > self.max_items:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, key: Hashable) -> bool:
        return key in self._store
