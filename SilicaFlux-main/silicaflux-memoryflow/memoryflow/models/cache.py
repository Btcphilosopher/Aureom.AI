"""CPU cache miss effects: trace-driven set-associative LRU simulation
(PY_SIMULATION) plus analytical AMAT / effective-bandwidth formulas.

Used to quantify why SilicaFlux routes dense kernels through the scratchpad
+ DMA path instead of the CPU caches: a naive ijk GEMM on a 32 KiB L1 has a
miss rate an order of magnitude above the tiled version.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Iterable, Iterator

from memoryflow.provenance import Provenance


@dataclass
class CacheStats:
    accesses: int = 0
    hits: int = 0
    misses: int = 0
    writebacks: int = 0
    line_bytes: int = 64

    @property
    def miss_rate(self) -> float:
        return self.misses / self.accesses if self.accesses else 0.0

    @property
    def dram_bytes(self) -> int:
        return (self.misses + self.writebacks) * self.line_bytes

    provenance: Provenance = Provenance.PY_SIMULATION


class SetAssocCache:
    """Write-back, write-allocate, true-LRU set-associative cache."""

    def __init__(self, size_bytes: int = 32 * 1024, line_bytes: int = 64, ways: int = 8) -> None:
        if size_bytes % (line_bytes * ways):
            raise ValueError("size must be a multiple of line*ways")
        self.line = line_bytes
        self.ways = ways
        self.nsets = size_bytes // (line_bytes * ways)
        self.sets: list[OrderedDict[int, bool]] = [OrderedDict() for _ in range(self.nsets)]
        self.stats = CacheStats(line_bytes=line_bytes)

    def access(self, addr: int, write: bool = False) -> bool:
        tag = addr // self.line
        s = self.sets[tag % self.nsets]
        self.stats.accesses += 1
        if tag in s:
            s.move_to_end(tag)
            if write:
                s[tag] = True
            self.stats.hits += 1
            return True
        self.stats.misses += 1
        if len(s) >= self.ways:
            _, dirty = s.popitem(last=False)
            if dirty:
                self.stats.writebacks += 1
        s[tag] = write
        return False

    def run(self, trace: Iterable[tuple[int, bool]]) -> CacheStats:
        for a, w in trace:
            self.access(a, w)
        return self.stats


def gemm_trace(n: int, elem: int = 4, tile: int = 0, base_a: int = 0, base_b: int = 1 << 24,
               base_c: int = 1 << 25) -> Iterator[tuple[int, bool]]:
    """Address trace of C += A*B (n x n, row-major).  tile=0 -> naive ijk."""
    if tile <= 0:
        for i in range(n):
            for j in range(n):
                for k in range(n):
                    yield base_a + (i * n + k) * elem, False
                    yield base_b + (k * n + j) * elem, False
                yield base_c + (i * n + j) * elem, True
        return
    t = tile
    for ii in range(0, n, t):
        for jj in range(0, n, t):
            for kk in range(0, n, t):
                for i in range(ii, min(ii + t, n)):
                    for k in range(kk, min(kk + t, n)):
                        yield base_a + (i * n + k) * elem, False
                        for j in range(jj, min(jj + t, n)):
                            yield base_b + (k * n + j) * elem, False
                            yield base_c + (i * n + j) * elem, True


def stream_trace(nbytes: int, elem: int = 4, streams: int = 3) -> Iterator[tuple[int, bool]]:
    """Vector add style: two reads + one write per element."""
    for i in range(0, nbytes, elem):
        yield i, False
        yield (1 << 26) + i, False
        if streams > 2:
            yield (1 << 27) + i, True


def amat(hit_cycles: float, miss_rate: float, miss_penalty: float) -> float:
    """Average memory access time (ANALYTICAL)."""
    return hit_cycles + miss_rate * miss_penalty


def cpu_effective_ops(peak_ops: float, accesses_per_op: float, miss_rate: float,
                      miss_penalty_cycles: float, clock_hz: float, mlp: float = 1.0) -> float:
    """CPU throughput with blocking cache misses overlapped ``mlp`` ways (ANALYTICAL)."""
    cycles_per_op = 1.0 / (peak_ops / clock_hz) + accesses_per_op * miss_rate * miss_penalty_cycles / mlp
    return clock_hz / cycles_per_op


def analytic_streaming_miss_rate(elem: int, line: int) -> float:
    """Compulsory-only miss rate of a unit-stride stream."""
    return elem / line
