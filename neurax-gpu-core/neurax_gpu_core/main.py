"""
NEURAX GPU CORE -- command-line entry point.

Examples
--------
Run a mixed workload simulation on the mainstream preset::

    python -m neurax_gpu_core.main --preset mainstream --timesteps 300

Run the AI architecture optimiser (SM count / cache / TDP search)::

    python -m neurax_gpu_core.main --optimise --objective perf_per_watt

Export the full per-timestep telemetry to CSV::

    python -m neurax_gpu_core.main --timesteps 500 --csv out.csv
"""

from __future__ import annotations

import argparse
import sys
from typing import List

from .ai.gpu_tuner import GPUTuner
from .core.engine import SimulationEngine
from .core.simulation_loop import run_simulation
from .utils.config import GPUConfig, PRESETS, get_preset
from .utils.logging import get_logger, setup_logging
from .workloads.ai_training import AITrainingWorkload
from .workloads.base import Workload
from .workloads.gaming import GamingWorkload
from .workloads.physics_sim import PhysicsSimWorkload
from .workloads.rendering import RenderingWorkload

logger = get_logger("main")

WORKLOAD_FACTORIES = {
    "gaming": lambda seed: GamingWorkload(seed=seed),
    "ai_training": lambda seed: AITrainingWorkload(seed=seed),
    "rendering": lambda seed: RenderingWorkload(seed=seed),
    "physics_sim": lambda seed: PhysicsSimWorkload(seed=seed),
}


def build_workloads(names: List[str], seed: int = 0) -> List[Workload]:
    workloads = []
    for i, name in enumerate(names):
        if name not in WORKLOAD_FACTORIES:
            raise KeyError(f"Unknown workload '{name}'. Available: {sorted(WORKLOAD_FACTORIES)}")
        workloads.append(WORKLOAD_FACTORIES[name](seed + i))
    return workloads


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="NEURAX GPU CORE simulation platform")
    p.add_argument("--preset", choices=sorted(PRESETS), default="mainstream",
                    help="Base GPU architecture preset.")
    p.add_argument("--num-sms", type=int, default=None, help="Override SM count.")
    p.add_argument("--tdp", type=float, default=None, help="Override TDP (watts).")
    p.add_argument("--timesteps", type=int, default=300, help="Number of macro timesteps to simulate.")
    p.add_argument("--micro-cycles", type=int, default=256, help="Cycle-accurate sample window per timestep.")
    p.add_argument("--workloads", nargs="+", default=["gaming", "ai_training", "rendering", "physics_sim"],
                    choices=sorted(WORKLOAD_FACTORIES), help="Workloads to cycle through.")
    p.add_argument("--seed", type=int, default=42, help="Random seed.")
    p.add_argument("--log-interval", type=int, default=25, help="Timesteps between dashboard log lines.")
    p.add_argument("--csv", default=None, help="Write full per-timestep telemetry to this CSV path.")
    p.add_argument("--plot-dir", default=None, help="Directory to save matplotlib summary plots into.")
    p.add_argument("--optimise", action="store_true", help="Run the AI architecture optimiser instead of a plain simulation.")
    p.add_argument("--objective", choices=["perf_per_watt", "perf_per_dollar", "raw_throughput"],
                    default="perf_per_watt", help="Objective for --optimise.")
    p.add_argument("--rounds", type=int, default=2, help="Search rounds for --optimise.")
    p.add_argument("--quiet", action="store_true", help="Suppress per-interval log lines.")
    return p.parse_args(argv)


def build_config(args: argparse.Namespace) -> GPUConfig:
    config = get_preset(args.preset)
    if args.num_sms is not None:
        config.architecture.num_sms = args.num_sms
    if args.tdp is not None:
        config.power.tdp_watts = args.tdp
        config.thermal.tdp_watts = args.tdp
    config.simulation.timesteps = args.timesteps
    config.simulation.micro_cycles_per_timestep = args.micro_cycles
    config.simulation.random_seed = args.seed
    return config


def cmd_simulate(args: argparse.Namespace) -> int:
    config = build_config(args)
    workloads = build_workloads(args.workloads, seed=args.seed)

    logger.info("Building %s: %d SMs, %d CUDA cores/SM, %.0fW TDP, %s",
                config.name, config.architecture.num_sms, config.compute.cuda_cores_per_sm,
                config.power.tdp_watts, "HBM" if config.memory.use_hbm else "GDDR/VRAM")

    engine = SimulationEngine(config, workloads)

    from .ui.dashboard import Dashboard
    dashboard = Dashboard(engine)

    run_simulation(engine, num_timesteps=args.timesteps,
                    log_interval=0 if args.quiet else args.log_interval)

    dashboard.print_summary()

    if args.csv:
        df = dashboard.to_dataframe()
        df.to_csv(args.csv, index=False)
        logger.info("Wrote telemetry CSV to %s (%d rows)", args.csv, len(df))

    if args.plot_dir:
        _save_plots(engine, args.plot_dir)

    return 0


def cmd_optimise(args: argparse.Namespace) -> int:
    config = build_config(args)
    workload_names = args.workloads

    def factory() -> List[Workload]:
        return build_workloads(workload_names, seed=args.seed)

    tuner = GPUTuner(workload_factory=factory, objective=args.objective,
                      eval_timesteps=min(args.timesteps, 40), eval_micro_cycles=min(args.micro_cycles, 96))
    report = tuner.tune(config, rounds=args.rounds)

    print("=" * 78)
    print(f" ARCHITECTURE OPTIMISATION RESULT  (objective={args.objective})")
    print("=" * 78)
    print(f" Baseline score : {report.baseline.score:.4f}  ({report.baseline.label})")
    print(f" Best score     : {report.best.score:.4f}  ({report.best.label})")
    print(f" Improvement    : {report.improvement_fraction * 100:+.1f}%")
    print(f" Best config    : {report.best.config.architecture.num_sms} SMs, "
          f"{report.best.config.compute.cuda_cores_per_sm} cores/SM, "
          f"{report.best.config.memory.l2_cache_kb}KB L2, {report.best.config.power.tdp_watts:.0f}W TDP")
    print(f" Predictor      : {report.predictor_backend} (train R^2={report.predictor_r2:.3f})")
    print("-" * 78)
    print(" Recommendations:")
    for rec in report.recommendations:
        print(f"  - {rec}")
    print("=" * 78)
    return 0


def _save_plots(engine: SimulationEngine, plot_dir: str) -> None:
    import os
    from .ui.gpu_visualizer import GPUVisualizer

    os.makedirs(plot_dir, exist_ok=True)
    figures = {
        "timeseries.png": GPUVisualizer.plot_timeseries(engine),
        "thermal_heatmap.png": GPUVisualizer.plot_thermal_heatmap(engine),
        "occupancy_map.png": GPUVisualizer.plot_occupancy_map(engine),
        "warp_timeline.png": GPUVisualizer.plot_warp_execution_timeline(engine),
    }
    for filename, fig in figures.items():
        if fig is None:
            continue
        path = os.path.join(plot_dir, filename)
        fig.savefig(path, dpi=140)
        logger.info("Saved plot: %s", path)


def main(argv: List[str] = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    setup_logging("WARNING" if args.quiet else "INFO")
    if args.optimise:
        return cmd_optimise(args)
    return cmd_simulate(args)


if __name__ == "__main__":
    raise SystemExit(main())
