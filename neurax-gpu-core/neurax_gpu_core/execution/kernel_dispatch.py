"""
GPU kernel launch and dispatch across the SM array.

Models the piece of real GPU hardware ("GigaThread"/"Global Scheduler"-like
front end) that hands out thread blocks (CTAs) to SMs with free residency
budget, and queues blocks when every SM is full -- this queueing is exactly
what produces "compute queue contention" under high occupancy pressure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from typing import Dict, List, Optional

from ..compute.instruction_pipeline import Instruction
from ..compute.sm_units import SMCycleStats, StreamingMultiprocessor
from .thread_model import ThreadBlock


@dataclass
class Kernel:
    name: str
    grid_size: int                    # number of thread blocks
    block_size: int                   # threads per block
    instr_template: List[Instruction]
    shared_mem_bytes_per_block: int = 0
    divergence_probability: float = 0.05
    workload_tag: str = "generic"


@dataclass
class KernelRun:
    run_id: int
    kernel: Kernel
    launch_cycle: int
    total_blocks: int
    warp_size: int
    blocks_completed: int = 0
    completion_cycle: Optional[int] = None
    total_warps_launched: int = 0
    warps_completed: int = 0

    @property
    def is_complete(self) -> bool:
        return self.blocks_completed >= self.total_blocks

    def latency_cycles(self) -> Optional[int]:
        if self.completion_cycle is None:
            return None
        return self.completion_cycle - self.launch_cycle


@dataclass
class _TrackedBlock:
    block: ThreadBlock
    run: KernelRun
    remaining_warps: int
    sm_id: Optional[int] = None


class KernelDispatcher:
    def __init__(self, sms: List[StreamingMultiprocessor], warp_size: int):
        self.sms = sms
        self.warp_size = warp_size
        self._run_id_gen = count()
        self._block_id_gen = count()
        self._warp_id_gen = count()

        self.pending_blocks: List[_TrackedBlock] = []
        self.active_blocks: Dict[int, _TrackedBlock] = {}      # block_id -> tracked
        self.warp_to_block: Dict[int, int] = {}                # global warp_id -> block_id
        self.runs: Dict[int, KernelRun] = {}
        self._sm_cursor = 0

    def launch(self, kernel: Kernel, launch_cycle: int) -> KernelRun:
        run = KernelRun(
            run_id=next(self._run_id_gen), kernel=kernel, launch_cycle=launch_cycle,
            total_blocks=kernel.grid_size, warp_size=self.warp_size,
        )
        self.runs[run.run_id] = run
        for i in range(kernel.grid_size):
            block_id = next(self._block_id_gen)
            warps_per_block = max(1, -(-kernel.block_size // self.warp_size))
            warp_id_base = self._reserve_warp_ids(warps_per_block)
            block = ThreadBlock(
                block_id=block_id, kernel_name=kernel.name, global_block_index=i,
                threads_per_block=kernel.block_size, warp_size=self.warp_size,
                shared_mem_bytes=kernel.shared_mem_bytes_per_block, warp_id_base=warp_id_base,
            )
            tracked = _TrackedBlock(block=block, run=run, remaining_warps=warps_per_block)
            self.pending_blocks.append(tracked)
            run.total_warps_launched += warps_per_block
        return run

    def _reserve_warp_ids(self, n: int) -> int:
        base = next(self._warp_id_gen)
        for _ in range(n - 1):
            next(self._warp_id_gen)
        return base

    def queue_depth(self) -> int:
        return len(self.pending_blocks)

    def try_dispatch(self, cycle: int) -> int:
        """Assign as many queued blocks as current SM residency allows.
        Returns the number of blocks dispatched this call."""
        dispatched = 0
        still_pending: List[_TrackedBlock] = []
        for tracked in self.pending_blocks:
            kernel = tracked.run.kernel
            warps_per_block = tracked.remaining_warps
            placed = False
            for _ in range(len(self.sms)):
                sm = self.sms[self._sm_cursor]
                self._sm_cursor = (self._sm_cursor + 1) % len(self.sms)
                if sm.can_accept_block(warps_per_block, kernel.shared_mem_bytes_per_block):
                    warps = tracked.block.build_warps(kernel.instr_template, sm.sm_id, cycle)
                    for w in warps:
                        w.warp_id = w.warp_id  # already globally unique
                    sm.assign_block(tracked.block.block_id, warps, kernel.shared_mem_bytes_per_block)
                    tracked.sm_id = sm.sm_id
                    self.active_blocks[tracked.block.block_id] = tracked
                    for w in warps:
                        self.warp_to_block[w.warp_id] = tracked.block.block_id
                    placed = True
                    dispatched += 1
                    break
            if not placed:
                still_pending.append(tracked)
        self.pending_blocks = still_pending
        return dispatched

    def on_sm_stats(self, sm: StreamingMultiprocessor, stats: SMCycleStats, cycle: int) -> None:
        for warp_id in stats.finished_warp_ids:
            block_id = self.warp_to_block.pop(warp_id, None)
            if block_id is None or block_id not in self.active_blocks:
                continue
            tracked = self.active_blocks[block_id]
            tracked.remaining_warps -= 1
            tracked.run.warps_completed += 1
            if tracked.remaining_warps <= 0:
                sm.release_block(block_id, tracked.run.kernel.shared_mem_bytes_per_block)
                del self.active_blocks[block_id]
                tracked.run.blocks_completed += 1
                if tracked.run.is_complete and tracked.run.completion_cycle is None:
                    tracked.run.completion_cycle = cycle

    def step(self, cycle: int) -> None:
        self.try_dispatch(cycle)

    def active_run_count(self) -> int:
        return sum(1 for r in self.runs.values() if not r.is_complete)
