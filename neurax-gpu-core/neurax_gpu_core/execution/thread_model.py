"""
Thread / thread-block (CTA) grouping.

A GPU kernel launch describes a grid of thread blocks, each containing some
number of threads. This module turns that abstract launch geometry into
concrete :class:`~compute.warp_scheduler.Warp` objects (grouping threads
into ``warp_size``-wide SIMT groups), instantiated from a kernel's
instruction template.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import List

from ..compute.instruction_pipeline import Instruction
from ..compute.warp_scheduler import Warp


@dataclass
class ThreadBlock:
    block_id: int
    kernel_name: str
    global_block_index: int
    threads_per_block: int
    warp_size: int
    shared_mem_bytes: int
    warp_id_base: int

    def build_warps(self, instr_template: List[Instruction], sm_id: int, created_cycle: int) -> List[Warp]:
        n_warps = max(1, -(-self.threads_per_block // self.warp_size))  # ceil div
        warps: List[Warp] = []
        for local_idx in range(n_warps):
            warp_id = self.warp_id_base + local_idx
            # Give each warp its own copy of the instruction stream with
            # addresses offset so different warps touch different memory --
            # this is what produces realistic (non-degenerate) cache behaviour.
            instrs = []
            addr_offset = (self.global_block_index * self.threads_per_block + local_idx * self.warp_size) * 4
            for instr in instr_template:
                new_instr = copy.copy(instr)
                if new_instr.address_base is not None:
                    new_instr.address_base = new_instr.address_base + addr_offset
                new_instr.warp_id = warp_id
                instrs.append(new_instr)
            warps.append(Warp(
                warp_id=warp_id, sm_id=sm_id, block_id=self.block_id,
                warp_size=self.warp_size, instructions=instrs, created_cycle=created_cycle,
            ))
        return warps
