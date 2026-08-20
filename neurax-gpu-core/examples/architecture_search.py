"""
Example: use the AI architecture optimiser to search SM count / core width /
L2 size / TDP for the best performance-per-watt on an AI-training-heavy
workload mix, then print the resulting leaderboard.

    python examples/architecture_search.py
"""

from __future__ import annotations

import os
import sys
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from neurax_gpu_core.ai.gpu_tuner import GPUTuner
from neurax_gpu_core.utils.config import get_preset
from neurax_gpu_core.workloads.ai_training import AITrainingWorkload
from neurax_gpu_core.workloads.base import Workload
from neurax_gpu_core.workloads.gaming import GamingWorkload


def workload_factory() -> List[Workload]:
    # Two AI-training instances (dominant) plus one gaming pass, to search
    # for a design that's efficient at the AI-training workload's tensor-
    # core-heavy access pattern without collapsing gaming performance.
    return [AITrainingWorkload(seed=1), AITrainingWorkload(seed=2), GamingWorkload(seed=3)]


def main() -> None:
    # Start from the smaller "efficiency" preset and use a modest evaluation
    # budget so this example finishes in well under a minute; for a more
    # rigorous search, bump eval_timesteps/eval_micro_cycles/rounds (or run
    # `python -m neurax_gpu_core.main --optimise` against a larger preset).
    base_config = get_preset("efficiency")

    tuner = GPUTuner(workload_factory=workload_factory, objective="perf_per_watt",
                      eval_timesteps=25, eval_micro_cycles=64)
    report = tuner.tune(base_config, rounds=1)

    print(f"Baseline score: {report.baseline.score:.3f} ({report.baseline.label})")
    print(f"Best score:     {report.best.score:.3f} ({report.best.label})")
    print(f"Improvement:    {report.improvement_fraction * 100:+.1f}%")
    print()
    print("Recommendations:")
    for rec in report.recommendations:
        print(f"  - {rec}")
    print()
    print("Top candidates:")
    for candidate in report.leaderboard[:5]:
        cfg = candidate.config
        print(f"  {candidate.score:8.3f}  {candidate.label:32s}  "
              f"{cfg.architecture.num_sms:4d} SMs  {cfg.compute.cuda_cores_per_sm:4d} cores/SM  "
              f"{cfg.memory.l2_cache_kb:6d}KB L2  {cfg.power.tdp_watts:6.0f}W")


if __name__ == "__main__":
    main()
