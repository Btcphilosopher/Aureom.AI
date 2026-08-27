"""Routes render-graph work between CPU and GPU compute backends.

A real scheduler on Apple Silicon would weigh queue depth on each engine
(Metal command queue occupancy vs. CPU thread pool load) before dispatching;
this prototype models the same decision with a simple heuristic — cheap,
small operations stay on the CPU (dispatch overhead would dominate), larger
ones prefer the GPU backend when one is available.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from finalcut_engine.render.gpu import CPUBackend, ComputeBackend, SharedBuffer, select_backend


@dataclass
class GPUScheduler:
    gpu_backend: ComputeBackend = field(default_factory=select_backend)
    cpu_backend: ComputeBackend = field(default_factory=CPUBackend)
    #: Below this many pixels, dispatch overhead isn't worth leaving the CPU.
    gpu_pixel_threshold: int = 512 * 512

    def backend_for(self, frame_shape: tuple[int, ...]) -> ComputeBackend:
        pixel_count = frame_shape[0] * frame_shape[1] if len(frame_shape) >= 2 else 0
        if pixel_count >= self.gpu_pixel_threshold and self.gpu_backend.is_available():
            return self.gpu_backend
        return self.cpu_backend

    def run(self, op: Callable[[np.ndarray], np.ndarray], frame: np.ndarray) -> np.ndarray:
        backend = self.backend_for(frame.shape)
        try:
            result = backend.run(op, SharedBuffer(data=frame))
        except NotImplementedError:
            # The GPU backend documented its own unavailability (see gpu.py);
            # fall back rather than crash the render.
            result = self.cpu_backend.run(op, SharedBuffer(data=frame))
        return result.data
