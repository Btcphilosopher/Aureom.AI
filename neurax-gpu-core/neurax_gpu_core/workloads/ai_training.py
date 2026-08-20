"""
AI training workload: dense matrix-multiplication / tensor-core-heavy
compute with large-batch streaming reads from VRAM/HBM.

Characterised by: very high compute intensity dominated by TENSOR_MMA ops,
high sustained memory bandwidth demand (streaming activations/weights),
low branch divergence (regular, data-parallel control flow), and large
shared-memory tiles (typical of tiled GEMM kernels).
"""

from __future__ import annotations

from .base import Workload, WorkloadProfile


class AITrainingWorkload(Workload):
    def __init__(self, seed: int = 0, batch_size: int = 256, use_tensor_cores: bool = True) -> None:
        super().__init__(seed)
        self.batch_size = batch_size
        self.profile = WorkloadProfile(
            name="ai_training",
            compute_intensity=0.70,
            memory_intensity=0.30,
            tensor_fraction=0.85 if use_tensor_cores else 0.0,
            divergence_probability=0.01,
            bytes_per_access=16,
            instructions_per_thread=96,
            occupancy_target_blocks_per_sm=4.0,
        )
        self.shared_mem_bytes_per_block = 48 * 1024  # typical GEMM tile

    @staticmethod
    def samples_per_second(step_time_seconds: float, batch_size: int) -> float:
        if step_time_seconds <= 0:
            return 0.0
        return batch_size / step_time_seconds
