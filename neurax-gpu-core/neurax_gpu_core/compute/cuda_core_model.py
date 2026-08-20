"""
CUDA-core-like ALU lane model.

A ``ProcessingBlock`` groups ``warp_size`` ALU lanes behind a single warp
scheduler port -- this mirrors real SM sub-partitions (e.g. 4 partitions of
32 cores each on a 128-core SM). It is the unit that actually "executes" an
issued instruction: it retires FLOPs/INT-ops for every active lane in the
warp's execution mask and reports the (opcode-defined) result latency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .instruction_pipeline import Instruction, OpCode


def popcount(mask: int) -> int:
    return bin(mask).count("1")


@dataclass
class ExecutionResult:
    instruction: Instruction
    active_lanes: int
    flops_retired: float
    int_ops_retired: int
    result_latency_cycles: int
    is_memory: bool


@dataclass
class ProcessingBlock:
    """One SIMT execution partition of an SM."""

    block_id: int
    lane_count: int
    busy_until_cycle: int = 0

    def is_free(self, cycle: int) -> bool:
        return cycle >= self.busy_until_cycle

    def execute(self, instruction: Instruction, active_mask: int, cycle: int) -> ExecutionResult:
        active_lanes = min(popcount(active_mask), self.lane_count)
        flops = 0.0
        int_ops = 0
        if instruction.opcode in (OpCode.FP32_ADD, OpCode.FP32_MUL, OpCode.FP32_FMA,
                                    OpCode.FP16_FMA, OpCode.TENSOR_MMA, OpCode.SFU):
            flops = instruction.flops_per_lane() * active_lanes
        elif instruction.opcode in (OpCode.INT32_ADD, OpCode.INT32_MUL):
            int_ops = active_lanes

        latency = instruction.base_latency()
        # A processing block issues one instruction per cycle (throughput-1)
        # but the *lane* is only busy for a single issue slot; downstream
        # result latency is tracked by the warp, not the block.
        self.busy_until_cycle = cycle + 1
        return ExecutionResult(
            instruction=instruction,
            active_lanes=active_lanes,
            flops_retired=flops,
            int_ops_retired=int_ops,
            result_latency_cycles=latency,
            is_memory=instruction.is_memory(),
        )


@dataclass
class CudaCoreArray:
    """The full set of ALU lanes for one SM, partitioned into processing
    blocks -- one block per concurrently-scheduled warp."""

    total_cores: int
    warp_size: int

    def __post_init__(self) -> None:
        self.partitions = max(1, self.total_cores // self.warp_size)
        self.blocks: List[ProcessingBlock] = [
            ProcessingBlock(block_id=i, lane_count=self.warp_size) for i in range(self.partitions)
        ]

    def free_blocks(self, cycle: int) -> List[ProcessingBlock]:
        return [b for b in self.blocks if b.is_free(cycle)]

    def peak_flops_per_cycle(self, flops_per_fma: int = 2) -> float:
        return self.total_cores * flops_per_fma
