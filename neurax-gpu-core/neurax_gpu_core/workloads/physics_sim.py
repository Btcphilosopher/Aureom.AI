"""
Physics simulation workload: particle-system integration (N-body-ish
position/velocity updates).

Characterised by: memory-bound behaviour (each thread reads and writes its
own particle state plus a handful of neighbours), light-to-moderate compute
(integration math, occasional collision branches), and low divergence
relative to rendering.
"""

from __future__ import annotations

from .base import Workload, WorkloadProfile


class PhysicsSimWorkload(Workload):
    def __init__(self, seed: int = 0, particles_per_thread: int = 1) -> None:
        super().__init__(seed)
        self.particles_per_thread = particles_per_thread
        self.profile = WorkloadProfile(
            name="physics_sim",
            compute_intensity=0.30,
            memory_intensity=0.50,
            tensor_fraction=0.0,
            divergence_probability=0.08,
            bytes_per_access=12,   # e.g. float3 position/velocity
            instructions_per_thread=40,
            occupancy_target_blocks_per_sm=3.5,
        )

    def particles_per_second(self, step_time_seconds: float, threads_launched: int) -> float:
        if step_time_seconds <= 0:
            return 0.0
        return (threads_launched * self.particles_per_thread) / step_time_seconds
