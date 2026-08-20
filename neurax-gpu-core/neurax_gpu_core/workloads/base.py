"""
Base class for workload generators.

A workload turns a small set of high-level knobs (compute intensity, memory
intensity, divergence probability, tensor-core usage) into a concrete
:class:`~execution.kernel_dispatch.Kernel` -- an instruction-template plus
launch geometry -- sized against a specific :class:`~architecture.gpu_design.GPUDesign`
so it always launches enough blocks to meaningfully load the SM array
regardless of how big that array is.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List

from ..architecture.gpu_design import GPUDesign
from ..compute.instruction_pipeline import Instruction, OpCode
from ..execution.kernel_dispatch import Kernel


@dataclass
class WorkloadProfile:
    name: str
    compute_intensity: float       # 0..1, fraction of instructions that are ALU/tensor ops
    memory_intensity: float        # 0..1, fraction of instructions that are LOAD/STORE
    tensor_fraction: float         # 0..1, fraction of ALU ops that are TENSOR_MMA (vs FP32)
    divergence_probability: float  # 0..1, branch-divergence likelihood
    bytes_per_access: int = 4
    instructions_per_thread: int = 64
    occupancy_target_blocks_per_sm: float = 3.0


class Workload:
    """Base class; subclasses set a :class:`WorkloadProfile` in ``__init__``."""

    profile: WorkloadProfile

    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed)
        self._phase = 0

    def _build_instr_template(self, block_size: int) -> List[Instruction]:
        p = self.profile
        template: List[Instruction] = []
        n = p.instructions_per_thread
        for i in range(n):
            roll = self.rng.random()
            if roll < p.memory_intensity:
                opcode = OpCode.LOAD if self.rng.random() < 0.7 else OpCode.STORE
                instr = Instruction(
                    opcode=opcode, warp_id=-1, pc=i, bytes_per_lane=p.bytes_per_access,
                    address_base=(i * 128) % 65536, address_stride=p.bytes_per_access,
                )
            elif roll < p.memory_intensity + 0.03:
                instr = Instruction(opcode=OpCode.BRANCH, warp_id=-1, pc=i,
                                     is_divergent_branch=True)
            elif roll < p.memory_intensity + 0.05:
                instr = Instruction(opcode=OpCode.BARRIER, warp_id=-1, pc=i)
            else:
                if self.rng.random() < p.tensor_fraction:
                    instr = Instruction(opcode=OpCode.TENSOR_MMA, warp_id=-1, pc=i)
                elif self.rng.random() < 0.08:
                    instr = Instruction(opcode=OpCode.SFU, warp_id=-1, pc=i)
                else:
                    op = self.rng.choice([OpCode.FP32_ADD, OpCode.FP32_MUL, OpCode.FP32_FMA])
                    instr = Instruction(opcode=op, warp_id=-1, pc=i)
            template.append(instr)
        return template

    def _sized_grid(self, gpu: GPUDesign, block_size: int) -> int:
        """Enough blocks to load every SM to ``occupancy_target_blocks_per_sm``,
        so smaller/larger dies both see proportional pressure."""
        blocks = int(gpu.config.architecture.num_sms * self.profile.occupancy_target_blocks_per_sm)
        return max(gpu.config.architecture.num_sms, blocks)

    def generate_kernel(self, gpu: GPUDesign, block_size: int = 256,
                         shared_mem_bytes_per_block: int = 0) -> Kernel:
        self._phase += 1
        template = self._build_instr_template(block_size)
        grid = self._sized_grid(gpu, block_size)
        return Kernel(
            name=f"{self.profile.name}_k{self._phase}",
            grid_size=grid, block_size=block_size, instr_template=template,
            shared_mem_bytes_per_block=shared_mem_bytes_per_block,
            divergence_probability=self.profile.divergence_probability,
            workload_tag=self.profile.name,
        )
