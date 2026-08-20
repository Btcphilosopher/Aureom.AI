"""
Rendering workload: ray-tracing (BVH traversal + intersection) and geometry
pipeline phases.

Characterised by: the highest branch divergence of any workload here (ray
paths diverge wildly across a warp as they traverse different parts of an
acceleration structure), heavy random-access memory traffic (BVH node /
triangle fetches), and moderate compute intensity.
"""

from __future__ import annotations

from .base import Workload, WorkloadProfile

PHASES = ["geometry_pipeline", "bvh_traversal", "ray_intersection", "shading"]


class RenderingWorkload(Workload):
    def __init__(self, seed: int = 0, rays_per_thread: int = 4) -> None:
        super().__init__(seed)
        self.rays_per_thread = rays_per_thread
        self.profile = WorkloadProfile(
            name="rendering",
            compute_intensity=0.35,
            memory_intensity=0.45,
            tensor_fraction=0.0,
            divergence_probability=0.32,
            bytes_per_access=8,
            instructions_per_thread=72,
            occupancy_target_blocks_per_sm=2.0,
        )

    def phase_name(self) -> str:
        return PHASES[self._phase % len(PHASES)]

    def rays_per_second(self, kernel_time_seconds: float, threads_launched: int) -> float:
        if kernel_time_seconds <= 0:
            return 0.0
        return (threads_launched * self.rays_per_thread) / kernel_time_seconds
