"""
Example: run a mixed gaming/AI-training/rendering/physics workload on a
flagship-preset die, print a live dashboard every 25 timesteps, and dump a
thermal heatmap + telemetry time series if matplotlib is available.

    python examples/run_mixed_workload.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from neurax_gpu_core.core.simulation_loop import run_simulation
from neurax_gpu_core.core.engine import SimulationEngine
from neurax_gpu_core.ui.dashboard import Dashboard
from neurax_gpu_core.ui.gpu_visualizer import GPUVisualizer
from neurax_gpu_core.utils.config import get_preset
from neurax_gpu_core.workloads.ai_training import AITrainingWorkload
from neurax_gpu_core.workloads.gaming import GamingWorkload
from neurax_gpu_core.workloads.physics_sim import PhysicsSimWorkload
from neurax_gpu_core.workloads.rendering import RenderingWorkload


def main() -> None:
    config = get_preset("flagship")
    config.simulation.timesteps = 400
    config.simulation.micro_cycles_per_timestep = 256

    workloads = [
        GamingWorkload(seed=1),
        AITrainingWorkload(seed=2, batch_size=512),
        RenderingWorkload(seed=3),
        PhysicsSimWorkload(seed=4),
    ]

    engine = SimulationEngine(config, workloads)
    run_simulation(engine, log_interval=25)

    dashboard = Dashboard(engine)
    dashboard.print_summary()

    out_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(out_dir, exist_ok=True)

    fig = GPUVisualizer.plot_thermal_heatmap(engine)
    if fig is not None:
        fig.savefig(os.path.join(out_dir, "thermal_heatmap.png"), dpi=150)
        print(f"Saved thermal heatmap -> {out_dir}/thermal_heatmap.png")

    fig = GPUVisualizer.plot_timeseries(engine)
    if fig is not None:
        fig.savefig(os.path.join(out_dir, "timeseries.png"), dpi=150)
        print(f"Saved telemetry timeseries -> {out_dir}/timeseries.png")


if __name__ == "__main__":
    main()
