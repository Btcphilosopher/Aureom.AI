"""
Example: define a new workload type by subclassing Workload with a custom
WorkloadProfile, and run it through the engine like any built-in workload.

    python examples/custom_workload.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from neurax_gpu_core.core.engine import SimulationEngine
from neurax_gpu_core.ui.dashboard import Dashboard
from neurax_gpu_core.utils.config import get_preset
from neurax_gpu_core.workloads.base import Workload, WorkloadProfile


class VideoEncodeWorkload(Workload):
    """A hypothetical video-encode compute workload: moderate compute
    (DCT/motion-estimation-style math), fairly high memory traffic
    (streaming frame buffers), and low divergence (regular block processing)."""

    def __init__(self, seed: int = 0, resolution: str = "4k") -> None:
        super().__init__(seed)
        scale = {"1080p": 0.5, "4k": 1.0, "8k": 2.2}.get(resolution, 1.0)
        self.profile = WorkloadProfile(
            name="video_encode",
            compute_intensity=0.40,
            memory_intensity=0.48,
            tensor_fraction=0.0,
            divergence_probability=0.05,
            bytes_per_access=8,
            instructions_per_thread=int(56 * scale),
            occupancy_target_blocks_per_sm=3.0,
        )


def main() -> None:
    config = get_preset("efficiency")
    config.simulation.timesteps = 200

    engine = SimulationEngine(config, [VideoEncodeWorkload(seed=1, resolution="4k")])
    engine.run(config.simulation.timesteps)

    Dashboard(engine).print_summary()


if __name__ == "__main__":
    main()
