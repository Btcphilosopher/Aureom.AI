"""
Cycle-level orchestration: ties the SM array, kernel dispatcher and memory
controller together into a single ``run_cycle()`` step. This is the inner
loop that :mod:`core.engine` drives repeatedly during each macro timestep's
cycle-accurate sampling window.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List

from ..compute.sm_units import StreamingMultiprocessor
from ..memory.memory_controller import MemoryController
from .kernel_dispatch import KernelDispatcher


@dataclass
class AggregateCycleStats:
    flops: float = 0.0
    int_ops: int = 0
    issued_instructions: int = 0
    active_warps: int = 0
    resident_warps: int = 0
    memory_ops_issued: int = 0
    divergence_events: int = 0
    idle_partitions: int = 0
    total_partitions: int = 0
    memory_completions: int = 0


class WarpExecutionEngine:
    def __init__(self, sms: List[StreamingMultiprocessor], dispatcher: KernelDispatcher,
                 memory_controller: MemoryController, rng: random.Random):
        self.sms = sms
        self.dispatcher = dispatcher
        self.memory_controller = memory_controller
        self.rng = rng

    def run_cycle(self, cycle: int, freq_ghz: float, divergence_probability: float) -> AggregateCycleStats:
        self.dispatcher.step(cycle)

        agg = AggregateCycleStats()
        for sm in self.sms:
            stats = sm.step(cycle, self.memory_controller, freq_ghz, divergence_probability, self.rng)
            self.dispatcher.on_sm_stats(sm, stats, cycle)

            agg.flops += stats.flops
            agg.int_ops += stats.int_ops
            agg.issued_instructions += stats.issued_instructions
            agg.active_warps += stats.active_warps
            agg.resident_warps += stats.resident_warps
            agg.memory_ops_issued += stats.memory_ops_issued
            agg.divergence_events += stats.divergence_events
            agg.idle_partitions += stats.idle_partitions
            agg.total_partitions += len(sm.core_array.blocks)

        completed = self.memory_controller.drain_completed(cycle)
        for req in completed:
            self.sms[req.sm_id].wake_warp(req.warp_id, cycle)
        agg.memory_completions = len(completed)
        return agg

    def per_sm_occupancy(self) -> List[float]:
        return [sm.occupancy() for sm in self.sms]

    def all_work_drained(self) -> bool:
        return (
            self.dispatcher.queue_depth() == 0
            and all(sm.is_idle() for sm in self.sms)
            and self.memory_controller.pending_count() == 0
        )
