"""
GDDR-style VRAM model.

Bandwidth is tracked on a nanosecond timeline (1 GB/s == 1 byte/ns, a handy
numeric identity) using a small set of independent channels, each acting as
a simple non-preemptive server: a request occupies a channel for
``size_bytes / channel_bandwidth`` ns. Queueing on a channel is exactly what
produces bandwidth-saturation stalls -- nothing about the resulting latency
is fixed in advance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class ChannelState:
    busy_until_ns: float = 0.0
    bytes_served: int = 0
    requests_served: int = 0


class BandwidthLimitedMemory:
    """Shared base for VRAM / HBM: N parallel channels, each with its own
    bandwidth share and an independent occupancy timeline."""

    def __init__(self, total_bandwidth_gbps: float, base_latency_ns: float,
                 num_channels: int, capacity_bytes: int):
        self.total_bandwidth_gbps = total_bandwidth_gbps
        self.base_latency_ns = base_latency_ns
        self.num_channels = max(1, num_channels)
        self.capacity_bytes = capacity_bytes
        self.channel_bandwidth_bytes_per_ns = total_bandwidth_gbps / self.num_channels
        self.channels: List[ChannelState] = [ChannelState() for _ in range(self.num_channels)]
        self.total_bytes_served = 0
        self.total_requests_served = 0
        self.total_queue_delay_ns = 0.0

    def _channel_for(self, address: int) -> ChannelState:
        idx = (address // 256) % self.num_channels  # interleave at 256B granularity
        return self.channels[idx]

    def service(self, address: int, size_bytes: int, issue_time_ns: float) -> float:
        """Submit a request; returns its completion time in ns."""
        ch = self._channel_for(address)
        transfer_ns = size_bytes / max(1e-9, self.channel_bandwidth_bytes_per_ns)
        start_ns = max(issue_time_ns, ch.busy_until_ns)
        queue_delay = start_ns - issue_time_ns
        completion_ns = start_ns + transfer_ns + self.base_latency_ns
        ch.busy_until_ns = start_ns + transfer_ns
        ch.bytes_served += size_bytes
        ch.requests_served += 1

        self.total_bytes_served += size_bytes
        self.total_requests_served += 1
        self.total_queue_delay_ns += queue_delay
        return completion_ns

    def utilisation(self, window_end_ns: float, window_ns: float) -> float:
        """Fraction of channel-time busy within [window_end_ns - window_ns, window_end_ns]."""
        if window_ns <= 0:
            return 0.0
        window_start = window_end_ns - window_ns
        busy = 0.0
        for ch in self.channels:
            busy += max(0.0, min(ch.busy_until_ns, window_end_ns) - window_start)
        return min(1.0, busy / (window_ns * self.num_channels))

    def achieved_bandwidth_gbps(self, elapsed_ns: float) -> float:
        if elapsed_ns <= 0:
            return 0.0
        return self.total_bytes_served / elapsed_ns  # bytes/ns == GB/s

    def average_queue_delay_ns(self) -> float:
        if self.total_requests_served == 0:
            return 0.0
        return self.total_queue_delay_ns / self.total_requests_served


class VRAMModel(BandwidthLimitedMemory):
    """GDDR6/6X-style discrete VRAM: fewer, wider channels, higher base
    latency than on-package HBM."""

    def __init__(self, capacity_gb: float, bandwidth_gbps: float, latency_ns: float,
                 num_channels: int = 12):
        super().__init__(
            total_bandwidth_gbps=bandwidth_gbps,
            base_latency_ns=latency_ns,
            num_channels=num_channels,
            capacity_bytes=int(capacity_gb * (1024 ** 3)),
        )
        self.capacity_gb = capacity_gb
