"""
Instruction representation and per-lane pipeline model.

An ``Instruction`` is the atomic unit issued by a warp scheduler into a
processing-block pipeline. Latencies are *base* pipeline latencies (in
cycles) for a given opcode class; actual observed latency for memory
opcodes is decided by the memory subsystem (cache hit/miss, bandwidth
contention), not fixed here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class OpCode(Enum):
    FP32_ADD = auto()
    FP32_MUL = auto()
    FP32_FMA = auto()
    FP16_FMA = auto()
    INT32_ADD = auto()
    INT32_MUL = auto()
    TENSOR_MMA = auto()      # tensor-core style matrix-multiply-accumulate
    SFU = auto()              # special function unit: rsqrt, sin, exp...
    LOAD = auto()
    STORE = auto()
    BRANCH = auto()
    BARRIER = auto()
    NOP = auto()


# Base pipeline latency in cycles for each opcode class (throughput-1/cycle
# pipelined ALUs still have a fixed result latency before a dependent
# instruction can consume the value).
BASE_LATENCY_CYCLES = {
    OpCode.FP32_ADD: 4,
    OpCode.FP32_MUL: 4,
    OpCode.FP32_FMA: 4,
    OpCode.FP16_FMA: 4,
    OpCode.INT32_ADD: 2,
    OpCode.INT32_MUL: 5,
    OpCode.TENSOR_MMA: 8,
    OpCode.SFU: 16,
    OpCode.LOAD: 0,           # resolved dynamically by the memory subsystem
    OpCode.STORE: 0,          # resolved dynamically by the memory subsystem
    OpCode.BRANCH: 1,
    OpCode.BARRIER: 1,
    OpCode.NOP: 1,
}

# FLOPs retired per lane per issue of a given opcode (0 for non-FP ops).
FLOPS_PER_LANE = {
    OpCode.FP32_ADD: 1,
    OpCode.FP32_MUL: 1,
    OpCode.FP32_FMA: 2,
    OpCode.FP16_FMA: 2,
    OpCode.TENSOR_MMA: 64,    # one MMA op fans out into many MACs
    OpCode.SFU: 1,
}

MEMORY_OPS = {OpCode.LOAD, OpCode.STORE}


@dataclass
class Instruction:
    opcode: OpCode
    warp_id: int
    pc: int
    bytes_per_lane: int = 4
    address_base: Optional[int] = None
    address_stride: int = 4
    is_divergent_branch: bool = False
    divergent_path_count: int = 1
    tensor_mma_flops_multiplier: float = 1.0

    def base_latency(self) -> int:
        return BASE_LATENCY_CYCLES[self.opcode]

    def flops_per_lane(self) -> float:
        base = FLOPS_PER_LANE.get(self.opcode, 0)
        if self.opcode == OpCode.TENSOR_MMA:
            return base * self.tensor_mma_flops_multiplier
        return base

    def is_memory(self) -> bool:
        return self.opcode in MEMORY_OPS


@dataclass
class PipelineStageConfig:
    """Describes the classic fetch/decode/issue/execute/writeback pipeline
    depth used to compute a fixed front-end latency contribution."""

    stages: int = 5

    def front_end_latency_cycles(self) -> int:
        # Fetch+decode+issue precede execute; writeback trails it.
        return max(1, self.stages - 2)
