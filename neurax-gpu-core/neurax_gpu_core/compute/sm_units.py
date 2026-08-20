"""
Streaming Multiprocessor (SM) model.

An SM owns a CUDA-core array partitioned into processing blocks (one warp
scheduler per block), a register file and shared-memory budget that gate
how many warps/blocks it can host concurrently, and the resident warps
themselves. ``step()`` advances the SM by exactly one core-clock cycle:
selecting ready warps, executing ALU instructions, and turning memory
instructions into requests for the :mod:`memory.memory_controller`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..memory.memory_controller import MemoryController, MemoryRequest
from ..utils.config import ComputeConfig
from .cuda_core_model import CudaCoreArray, popcount
from .instruction_pipeline import Instruction, OpCode
from .warp_scheduler import SchedulingPolicy, Warp, WarpScheduler, WarpState


@dataclass
class SMCycleStats:
    flops: float = 0.0
    int_ops: int = 0
    issued_instructions: int = 0
    active_warps: int = 0
    resident_warps: int = 0
    memory_ops_issued: int = 0
    divergence_events: int = 0
    idle_partitions: int = 0
    finished_warp_ids: List[int] = field(default_factory=list)


class StreamingMultiprocessor:
    def __init__(self, sm_id: int, config: ComputeConfig, policy: SchedulingPolicy =
                 SchedulingPolicy.GREEDY_THEN_OLDEST):
        self.sm_id = sm_id
        self.config = config
        self.core_array = CudaCoreArray(total_cores=config.cuda_cores_per_sm, warp_size=config.warp_size)
        self.schedulers: List[WarpScheduler] = [
            WarpScheduler(scheduler_id=i, issue_width=1, policy=policy)
            for i in range(self.core_array.partitions)
        ]
        self.warps: Dict[int, Warp] = {}

        register_footprint_bytes = config.registers_per_thread * 4 * config.warp_size
        register_limited_warps = max(
            1, (config.register_file_size_kb * 1024) // max(1, register_footprint_bytes)
        )
        self.max_resident_warps = min(config.max_warps_per_sm, register_limited_warps)

        self.shared_mem_capacity_bytes = config.shared_memory_kb_per_sm * 1024
        self.shared_mem_used_bytes = 0
        self.resident_block_ids: set = set()

        self.last_stats = SMCycleStats()
        self.cumulative_flops = 0.0
        self.cumulative_int_ops = 0
        self.cumulative_cycles_active = 0
        self.cumulative_issued_instructions = 0

    # -- admission control -------------------------------------------------

    def can_accept_block(self, warps_per_block: int, shared_mem_bytes_per_block: int) -> bool:
        warp_ok = len(self.warps) + warps_per_block <= self.max_resident_warps
        mem_ok = self.shared_mem_used_bytes + shared_mem_bytes_per_block <= self.shared_mem_capacity_bytes
        block_ok = len(self.resident_block_ids) < self.config.max_blocks_per_sm
        return warp_ok and mem_ok and block_ok

    def assign_block(self, block_id: int, warps: List[Warp], shared_mem_bytes_per_block: int) -> None:
        self.resident_block_ids.add(block_id)
        self.shared_mem_used_bytes += shared_mem_bytes_per_block
        for w in warps:
            self.warps[w.warp_id] = w
            scheduler = self.schedulers[w.warp_id % len(self.schedulers)]
            scheduler.add_warp(w)

    def purge_finished_warps(self) -> List[int]:
        """Remove completed warps from schedulers and the resident set;
        returns their warp_ids so the dispatcher can retire finished blocks."""
        finished: List[int] = []
        for scheduler in self.schedulers:
            done_ids = scheduler.remove_finished()
            for wid in done_ids:
                self.warps.pop(wid, None)
                finished.append(wid)
        return finished

    def release_block(self, block_id: int, shared_mem_bytes_per_block: int) -> None:
        if block_id in self.resident_block_ids:
            self.resident_block_ids.discard(block_id)
            self.shared_mem_used_bytes = max(0, self.shared_mem_used_bytes - shared_mem_bytes_per_block)

    def is_idle(self) -> bool:
        return len(self.warps) == 0

    # -- execution -----------------------------------------------------------

    def wake_warp(self, warp_id: int, cycle: int) -> None:
        warp = self.warps.get(warp_id)
        if warp is None:
            return
        warp.outstanding_memory_ops = max(0, warp.outstanding_memory_ops - 1)
        if warp.outstanding_memory_ops == 0 and warp.state == WarpState.STALLED_MEMORY:
            warp.state = WarpState.READY
            warp.ready_at_cycle = cycle

    def step(self, cycle: int, memory_controller: MemoryController, freq_ghz: float,
              divergence_probability: float, rng: random.Random) -> SMCycleStats:
        stats = SMCycleStats(resident_warps=len(self.warps))
        active_this_cycle = set()

        for block, scheduler in zip(self.core_array.blocks, self.schedulers):
            selected = scheduler.select(cycle)
            if not selected:
                stats.idle_partitions += 1
                continue
            for warp in selected:
                instr = warp.current_instruction()
                if instr is None:
                    continue
                active_this_cycle.add(warp.warp_id)

                if instr.opcode == OpCode.BRANCH:
                    warp.apply_divergence(rng, divergence_probability)
                    stats.divergence_events += warp.divergence_events
                    warp.ready_at_cycle = cycle + instr.base_latency()
                    warp.issue_count += 1
                    warp.advance_pc()
                    stats.issued_instructions += 1
                    continue

                if instr.opcode == OpCode.BARRIER:
                    warp.ready_at_cycle = cycle + max(2, self.config.pipeline_stages)
                    warp.issue_count += 1
                    warp.advance_pc()
                    stats.issued_instructions += 1
                    continue

                if instr.is_memory():
                    active_lanes = popcount(warp.active_mask)
                    size_bytes = max(4, instr.bytes_per_lane) * max(1, active_lanes)
                    base_addr = instr.address_base if instr.address_base is not None else (
                        (warp.warp_id * 4096) + warp.pc * instr.address_stride
                    )
                    memory_controller.submit(
                        sm_id=self.sm_id, warp_id=warp.warp_id, address=base_addr,
                        size_bytes=size_bytes, is_write=(instr.opcode == OpCode.STORE),
                        issue_cycle=cycle, freq_ghz=freq_ghz,
                    )
                    warp.outstanding_memory_ops += 1
                    warp.state = WarpState.STALLED_MEMORY
                    warp.issue_count += 1
                    warp.advance_pc()
                    stats.issued_instructions += 1
                    stats.memory_ops_issued += 1
                    continue

                result = block.execute(instr, warp.active_mask, cycle)
                stats.flops += result.flops_retired
                stats.int_ops += result.int_ops_retired
                warp.ready_at_cycle = cycle + max(1, result.result_latency_cycles)
                warp.issue_count += 1
                warp.advance_pc()
                stats.issued_instructions += 1

        stats.active_warps = len(active_this_cycle)
        stats.finished_warp_ids = self.purge_finished_warps()
        self.cumulative_flops += stats.flops
        self.cumulative_int_ops += stats.int_ops
        self.cumulative_issued_instructions += stats.issued_instructions
        if stats.active_warps > 0:
            self.cumulative_cycles_active += 1
        self.last_stats = stats
        return stats

    def occupancy(self) -> float:
        if self.max_resident_warps == 0:
            return 0.0
        return len(self.warps) / self.max_resident_warps
