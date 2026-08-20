"""
Gaming workload: rasterization, texture fetch and frame-buffer write phases.

Characterised by: high memory intensity (texture sampling is essentially
random-access read traffic), meaningful branch divergence (per-pixel
discard/blend logic), low tensor-core use, and a request for "frames" whose
duration in simulated seconds becomes an emergent FPS figure once the
kernel actually finishes -- never assumed up front.
"""

from __future__ import annotations

from .base import Workload, WorkloadProfile

PHASES = ["rasterization", "texture_fetch", "frame_buffer_write"]


class GamingWorkload(Workload):
    def __init__(self, seed: int = 0, resolution_scale: float = 1.0) -> None:
        super().__init__(seed)
        self.resolution_scale = resolution_scale
        self.profile = WorkloadProfile(
            name="gaming",
            compute_intensity=0.45,
            memory_intensity=0.42,
            tensor_fraction=0.0,
            divergence_probability=0.18,
            bytes_per_access=8,
            instructions_per_thread=int(48 * resolution_scale),
            occupancy_target_blocks_per_sm=2.5,
        )

    def phase_name(self) -> str:
        return PHASES[self._phase % len(PHASES)]

    @staticmethod
    def fps_from_frame_time(frame_time_seconds: float) -> float:
        if frame_time_seconds <= 0:
            return 0.0
        return 1.0 / frame_time_seconds
