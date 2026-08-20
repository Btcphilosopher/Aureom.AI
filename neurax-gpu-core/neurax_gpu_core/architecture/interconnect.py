"""
On-die interconnect (crossbar / ring / mesh) between SMs, the L2 cache and
the memory controllers.

The backing-store bandwidth queueing in :mod:`memory.vram_model` already
captures off-chip saturation; this module captures the *on-chip* fabric's
own finite bandwidth, reporting a congestion metric used for bottleneck
detection and as a small extra scheduling-stall contribution.
"""

from __future__ import annotations

from dataclasses import dataclass


TOPOLOGY_EFFICIENCY = {
    "crossbar": 1.00,   # full bisection bandwidth, most area-expensive
    "mesh": 0.80,
    "ring": 0.65,
}


@dataclass
class Interconnect:
    bandwidth_gbps: float
    topology: str = "crossbar"
    num_ports: int = 8

    def __post_init__(self) -> None:
        eff = TOPOLOGY_EFFICIENCY.get(self.topology, 0.75)
        self.effective_bandwidth_gbps = self.bandwidth_gbps * eff
        self._bytes_this_window = 0

    def record_traffic(self, bytes_moved: int) -> None:
        self._bytes_this_window += bytes_moved

    def congestion_fraction(self, window_ns: float) -> float:
        if window_ns <= 0:
            return 0.0
        capacity_bytes = self.effective_bandwidth_gbps * window_ns  # GB/s == bytes/ns
        if capacity_bytes <= 0:
            return 0.0
        return min(1.0, self._bytes_this_window / capacity_bytes)

    def reset_window(self) -> None:
        self._bytes_this_window = 0

    def stall_penalty_cycles(self, window_ns: float) -> int:
        """A small extra scheduling penalty once the fabric is saturated,
        representing arbitration/backpressure overhead."""
        congestion = self.congestion_fraction(window_ns)
        if congestion < 0.85:
            return 0
        return int((congestion - 0.85) * 40)  # up to ~6 cycles at full saturation
