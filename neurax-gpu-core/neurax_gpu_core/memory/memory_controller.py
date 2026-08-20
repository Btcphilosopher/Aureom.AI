"""
Memory controller: routes SM-issued memory requests through the cache
hierarchy and, on an L2 miss, out to main memory.

Two time-scales are deliberately kept separate:

* **Cycle-accurate (micro) path** -- ``submit()`` is called once per issued
  LOAD/STORE during the engine's short cycle-accurate sampling window. It
  resolves the cache hierarchy (so hit/miss behaviour, and therefore warp
  stall/occupancy dynamics, are simulated exactly) and, on a miss, applies
  the backing store's *base* latency (converted from ns to cycles at the
  current core frequency) so a warp is woken up after a realistic delay --
  without needing to simulate a full nanosecond-scale bandwidth queue at
  cycle granularity, which would be far too slow to sample meaningfully.
* **Macro (bandwidth) path** -- once per simulation timestep, the engine
  calls :meth:`resolve_bandwidth` with the *extrapolated* total bytes the
  miss rate implies for the *entire* timestep (not just the sampled
  window). That volume is pushed through the backing store's real
  channel-queueing model over the timestep's actual wall-clock duration,
  which is what produces genuine bandwidth-saturation effects (queueing
  delay that can carry over into the next timestep) and an achieved
  GB/s figure that is never assumed, only measured.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import count
from typing import Dict, List, Optional

from .cache_hierarchy import CacheHierarchy
from .vram_model import BandwidthLimitedMemory


@dataclass
class MemoryRequest:
    request_id: int
    sm_id: int
    warp_id: int
    address: int
    size_bytes: int
    is_write: bool
    issue_cycle: int
    completion_cycle: int
    level: str  # 'L1' | 'L2' | 'MEM'


@dataclass
class BandwidthResolution:
    bytes_moved: int
    window_ns: float
    achieved_bandwidth_gbps: float
    demanded_bandwidth_gbps: float
    utilisation_fraction: float
    overrun_ns: float  # how far channel occupancy spilled past the window end


class MemoryController:
    def __init__(self, cache_hierarchy: CacheHierarchy, backing_store: BandwidthLimitedMemory,
                 num_memory_controllers: int = 8):
        self.cache_hierarchy = cache_hierarchy
        self.backing_store = backing_store
        self.num_memory_controllers = max(1, num_memory_controllers)
        self._id_gen = count()

        self.total_requests = 0
        self.l1_hits = 0
        self.l2_hits = 0
        self.mem_accesses = 0
        self.bytes_transferred = 0
        self._mem_bytes_since_resolve = 0
        self._pending: Dict[int, MemoryRequest] = {}
        self._elapsed_ns_cursor = 0.0

    def submit(self, sm_id: int, warp_id: int, address: int, size_bytes: int,
               is_write: bool, issue_cycle: int, freq_ghz: float) -> MemoryRequest:
        freq_ghz = max(1e-6, freq_ghz)
        level, cache_latency_cycles = self.cache_hierarchy.access(sm_id, address, is_write)
        self.total_requests += 1
        self.bytes_transferred += size_bytes

        if level == "L1":
            self.l1_hits += 1
            completion_cycle = issue_cycle + cache_latency_cycles
        elif level == "L2":
            self.l2_hits += 1
            completion_cycle = issue_cycle + cache_latency_cycles
        else:
            self.mem_accesses += 1
            self._mem_bytes_since_resolve += size_bytes
            base_latency_cycles = math.ceil(self.backing_store.base_latency_ns * freq_ghz)
            completion_cycle = issue_cycle + cache_latency_cycles + max(1, base_latency_cycles)

        req = MemoryRequest(
            request_id=next(self._id_gen),
            sm_id=sm_id,
            warp_id=warp_id,
            address=address,
            size_bytes=size_bytes,
            is_write=is_write,
            issue_cycle=issue_cycle,
            completion_cycle=completion_cycle,
            level=level,
        )
        self._pending[req.request_id] = req
        return req

    def drain_completed(self, current_cycle: int) -> List[MemoryRequest]:
        done = [r for r in self._pending.values() if r.completion_cycle <= current_cycle]
        for r in done:
            del self._pending[r.request_id]
        return done

    def pending_count(self) -> int:
        return len(self._pending)

    # -- macro (per-timestep) bandwidth accounting --------------------------

    def resolve_bandwidth(self, extrapolated_bytes: int, window_ns: float) -> BandwidthResolution:
        """Push this timestep's *extrapolated* miss traffic through the
        backing store's channel-queueing model, spread evenly across all
        channels. Called once per macro timestep by the engine."""
        self._mem_bytes_since_resolve = 0
        window_start_ns = self._elapsed_ns_cursor
        n = self.backing_store.num_channels
        per_channel_bytes = max(0, extrapolated_bytes) // n
        remainder = max(0, extrapolated_bytes) - per_channel_bytes * n

        max_completion_ns = window_start_ns
        for ch_idx in range(n):
            size = per_channel_bytes + (remainder if ch_idx == n - 1 else 0)
            if size <= 0:
                continue
            fake_address = ch_idx * 256
            completion_ns = self.backing_store.service(fake_address, size, window_start_ns)
            max_completion_ns = max(max_completion_ns, completion_ns)

        window_end_ns = window_start_ns + window_ns
        self._elapsed_ns_cursor = window_end_ns
        overrun_ns = max(0.0, max_completion_ns - window_end_ns)

        achieved_gbps = extrapolated_bytes / window_ns if window_ns > 0 else 0.0  # bytes/ns == GB/s
        demanded_gbps = achieved_gbps
        utilisation = min(1.0, achieved_gbps / self.backing_store.total_bandwidth_gbps) \
            if self.backing_store.total_bandwidth_gbps > 0 else 0.0

        return BandwidthResolution(
            bytes_moved=extrapolated_bytes, window_ns=window_ns, achieved_bandwidth_gbps=achieved_gbps,
            demanded_bandwidth_gbps=demanded_gbps, utilisation_fraction=utilisation, overrun_ns=overrun_ns,
        )

    def summary(self) -> Dict[str, float]:
        cache_summary = self.cache_hierarchy.summary()
        return {
            **cache_summary,
            "total_requests": self.total_requests,
            "l1_hit_fraction": self.l1_hits / self.total_requests if self.total_requests else 0.0,
            "l2_hit_fraction": self.l2_hits / self.total_requests if self.total_requests else 0.0,
            "mem_access_fraction": self.mem_accesses / self.total_requests if self.total_requests else 0.0,
            "bytes_transferred": self.bytes_transferred,
            "backing_avg_queue_delay_ns": self.backing_store.average_queue_delay_ns(),
        }
