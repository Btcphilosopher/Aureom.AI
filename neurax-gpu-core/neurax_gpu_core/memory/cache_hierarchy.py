"""
Set-associative LRU cache model used for L1 (per-SM) and L2 (shared).

Only tags are tracked (no data payload) since the simulator is concerned
with hit/miss behaviour and its effect on latency and traffic, not with
data correctness. Each level exposes hit/miss counters used elsewhere to
report cache hit-rate metrics.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    writebacks: int = 0

    @property
    def accesses(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return self.hits / self.accesses if self.accesses else 0.0


class CacheLevel:
    """A single set-associative cache level with LRU replacement."""

    def __init__(self, name: str, size_kb: int, line_bytes: int, associativity: int,
                 hit_latency_cycles: int, dirty_writeback_ratio: float = 0.3):
        self.name = name
        self.size_bytes = size_kb * 1024
        self.line_bytes = max(4, line_bytes)
        self.associativity = max(1, associativity)
        self.hit_latency_cycles = hit_latency_cycles
        self.dirty_writeback_ratio = dirty_writeback_ratio

        self.num_lines = max(1, self.size_bytes // self.line_bytes)
        self.num_sets = max(1, self.num_lines // self.associativity)
        # set_index -> OrderedDict[tag] = None, ordered by recency (LRU at front)
        self._sets: Dict[int, "OrderedDict[int, None]"] = {}
        self.stats = CacheStats()

    def _decompose(self, address: int) -> Tuple[int, int]:
        line = address // self.line_bytes
        set_idx = line % self.num_sets
        tag = line // self.num_sets
        return set_idx, tag

    def access(self, address: int, is_write: bool) -> bool:
        """Return True on hit, False on miss. Always installs the line
        (miss => fill), evicting the LRU way if the set is full."""
        set_idx, tag = self._decompose(address)
        way = self._sets.setdefault(set_idx, OrderedDict())

        if tag in way:
            way.move_to_end(tag)
            self.stats.hits += 1
            return True

        self.stats.misses += 1
        if len(way) >= self.associativity:
            way.popitem(last=False)  # evict LRU
            self.stats.evictions += 1
            if is_write or self._rng_writeback():
                self.stats.writebacks += 1
        way[tag] = None
        return False

    def _rng_writeback(self) -> bool:
        # Cheap deterministic-ish proxy for "was the evicted line dirty".
        return (self.stats.evictions % 10) < int(self.dirty_writeback_ratio * 10)

    def occupancy_fraction(self) -> float:
        used_lines = sum(len(w) for w in self._sets.values())
        return used_lines / self.num_lines if self.num_lines else 0.0


class CacheHierarchy:
    """Owns one private L1 per SM plus a single shared L2."""

    def __init__(self, num_sms: int, l1_kb: int, l1_line: int, l1_assoc: int, l1_latency: int,
                 l2_kb: int, l2_line: int, l2_assoc: int, l2_latency: int):
        self.l1_caches: List[CacheLevel] = [
            CacheLevel(f"L1[{i}]", l1_kb, l1_line, l1_assoc, l1_latency) for i in range(num_sms)
        ]
        self.l2_cache = CacheLevel("L2", l2_kb, l2_line, l2_assoc, l2_latency)

    def access(self, sm_id: int, address: int, is_write: bool) -> Tuple[str, int]:
        """Walk the hierarchy L1 -> L2 -> miss (caller routes miss to VRAM/HBM).
        Returns (level_name_that_serviced_it, latency_cycles_at_that_level).
        level_name is one of 'L1', 'L2', 'MEM'.
        """
        l1 = self.l1_caches[sm_id % len(self.l1_caches)]
        if l1.access(address, is_write):
            return "L1", l1.hit_latency_cycles

        if self.l2_cache.access(address, is_write):
            return "L2", self.l2_cache.hit_latency_cycles + l1.hit_latency_cycles

        return "MEM", self.l2_cache.hit_latency_cycles + l1.hit_latency_cycles

    def aggregate_l1_stats(self) -> CacheStats:
        agg = CacheStats()
        for c in self.l1_caches:
            agg.hits += c.stats.hits
            agg.misses += c.stats.misses
            agg.evictions += c.stats.evictions
            agg.writebacks += c.stats.writebacks
        return agg

    def summary(self) -> Dict[str, float]:
        l1 = self.aggregate_l1_stats()
        return {
            "l1_hit_rate": l1.hit_rate,
            "l1_accesses": l1.accesses,
            "l2_hit_rate": self.l2_cache.stats.hit_rate,
            "l2_accesses": self.l2_cache.stats.accesses,
        }
