"""Memory budget tracking for caches and buffers.

Apple Silicon's unified memory architecture means there is one shared pool
rather than separate CPU/GPU heaps — so this tracks one overall budget rather
than modelling a discrete-GPU-style split, and eviction callbacks are how
callers (the render cache, proxy cache) respond to pressure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict

import numpy as np


def size_of(array: np.ndarray) -> int:
    return int(array.nbytes)


@dataclass
class MemoryManager:
    budget_bytes: int
    _usage: Dict[str, int] = field(default_factory=dict)
    _eviction_callbacks: list[Callable[[str], None]] = field(default_factory=list)

    def register(self, key: str, size_bytes: int) -> None:
        self._usage[key] = size_bytes
        self._maybe_evict()

    def release(self, key: str) -> None:
        self._usage.pop(key, None)

    def total_usage(self) -> int:
        return sum(self._usage.values())

    def pressure(self) -> float:
        """Fraction of budget consumed, in [0, +inf); > 1 means over budget."""
        return self.total_usage() / self.budget_bytes if self.budget_bytes else 0.0

    def on_eviction_needed(self, callback: Callable[[str], None]) -> None:
        self._eviction_callbacks.append(callback)

    def _maybe_evict(self) -> None:
        # Evict oldest-registered entries (insertion order) until back under budget.
        while self.total_usage() > self.budget_bytes and self._usage:
            oldest_key = next(iter(self._usage))
            self.release(oldest_key)
            for cb in self._eviction_callbacks:
                cb(oldest_key)
