"""
HBM (High Bandwidth Memory) stack model.

HBM trades VRAM's few-wide-channel design for many narrow, independent
channels spread across stacked dies on an interposer: much higher aggregate
bandwidth and lower latency, at lower per-stack capacity. Reuses the same
bandwidth-queueing mechanics as :mod:`vram_model` via the shared base class.
"""

from __future__ import annotations

from .vram_model import BandwidthLimitedMemory


class HBMModel(BandwidthLimitedMemory):
    def __init__(self, stacks: int, channels_per_stack: int, bandwidth_per_stack_gbps: float,
                 latency_ns: float, capacity_per_stack_gb: float = 4.0):
        total_bandwidth = stacks * bandwidth_per_stack_gbps
        total_channels = max(1, stacks * channels_per_stack)
        super().__init__(
            total_bandwidth_gbps=total_bandwidth,
            base_latency_ns=latency_ns,
            num_channels=total_channels,
            capacity_bytes=int(stacks * capacity_per_stack_gb * (1024 ** 3)),
        )
        self.stacks = stacks
        self.channels_per_stack = channels_per_stack
        self.capacity_gb = stacks * capacity_per_stack_gb
