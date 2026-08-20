"""
Throughput metrics: TFLOPS, IPC and utilisation, all derived from measured
per-cycle activity -- never assumed. ``ThroughputTracker`` accumulates raw
counters (flops, int ops, issued instructions, elapsed cycles/seconds) fed
to it by the engine and turns them into reportable rates on demand.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ThroughputSample:
    tflops: float
    gips: float                 # giga integer-ops/sec
    ipc_per_sm: float
    utilisation_fraction: float


class ThroughputTracker:
    def __init__(self) -> None:
        self.cumulative_flops = 0.0
        self.cumulative_int_ops = 0
        self.cumulative_issued = 0
        self.cumulative_cycles = 0
        self.cumulative_seconds = 0.0

    def update(self, flops: float, int_ops: int, issued_instructions: int,
               cycles_elapsed: int, seconds_elapsed: float) -> None:
        self.cumulative_flops += flops
        self.cumulative_int_ops += int_ops
        self.cumulative_issued += issued_instructions
        self.cumulative_cycles += cycles_elapsed
        self.cumulative_seconds += seconds_elapsed

    def instantaneous(self, flops: float, int_ops: int, issued_instructions: int,
                       cycles_elapsed: int, seconds_elapsed: float, num_sms: int,
                       peak_flops: float) -> ThroughputSample:
        tflops = (flops / seconds_elapsed / 1e12) if seconds_elapsed > 0 else 0.0
        gips = (int_ops / seconds_elapsed / 1e9) if seconds_elapsed > 0 else 0.0
        ipc = (issued_instructions / cycles_elapsed / max(1, num_sms)) if cycles_elapsed > 0 else 0.0
        util = (flops / seconds_elapsed) / peak_flops if peak_flops > 0 and seconds_elapsed > 0 else 0.0
        return ThroughputSample(
            tflops=tflops, gips=gips, ipc_per_sm=ipc, utilisation_fraction=min(1.0, util),
        )

    def average_tflops(self) -> float:
        if self.cumulative_seconds <= 0:
            return 0.0
        return self.cumulative_flops / self.cumulative_seconds / 1e12
