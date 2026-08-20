"""
GPUTuner: the top-level AI optimisation entry point.

Drives :class:`~optimisation.architecture_optimizer.ArchitectureOptimizer`
across a design space (SM count vs power, cache sizes, TDP), fits a cheap
:class:`~ai.workload_predictor.PerformancePredictor` surrogate over the
resulting samples so the trade-off surface can be inspected without paying
for another simulation, and produces a short, human-readable set of
recommendations for the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List

from ..optimisation.architecture_optimizer import ArchitectureOptimizer, CandidateResult
from ..utils.config import GPUConfig
from ..utils.logging import get_logger
from ..workloads.base import Workload
from .workload_predictor import PerformancePredictor

logger = get_logger("gpu_tuner")


@dataclass
class TuningReport:
    best: CandidateResult
    baseline: CandidateResult
    improvement_fraction: float
    recommendations: List[str]
    predictor_r2: float
    predictor_backend: str
    leaderboard: List[CandidateResult]


def _feature_vector(cfg: GPUConfig) -> List[float]:
    return [
        float(cfg.architecture.num_sms),
        float(cfg.compute.cuda_cores_per_sm),
        float(cfg.memory.l2_cache_kb),
        float(cfg.power.tdp_watts),
    ]


class GPUTuner:
    def __init__(self, workload_factory: Callable[[], List[Workload]], objective: str = "perf_per_watt",
                 eval_timesteps: int = 30, eval_micro_cycles: int = 96):
        self.workload_factory = workload_factory
        self.objective = objective
        self.optimizer = ArchitectureOptimizer(
            workload_factory=workload_factory, objective=objective,
            eval_timesteps=eval_timesteps, eval_micro_cycles=eval_micro_cycles,
        )
        self.predictor = PerformancePredictor()

    def tune(self, base_config: GPUConfig, rounds: int = 2) -> TuningReport:
        logger.info("Starting architecture search (objective=%s, rounds=%d)...", self.objective, rounds)
        best = self.optimizer.search(base_config, rounds=rounds)
        baseline = self.optimizer.history[0]

        fit_report = None
        if len(self.optimizer.history) >= 3:
            X = [_feature_vector(r.config) for r in self.optimizer.history]
            y = [r.score for r in self.optimizer.history]
            fit_report = self.predictor.fit(X, y)

        improvement = (
            (best.score - baseline.score) / abs(baseline.score) if baseline.score not in (0.0,) else 0.0
        )

        recommendations = self._build_recommendations(baseline, best)

        return TuningReport(
            best=best, baseline=baseline, improvement_fraction=improvement,
            recommendations=recommendations,
            predictor_r2=fit_report.train_r2 if fit_report else 0.0,
            predictor_backend=fit_report.backend if fit_report else "untrained",
            leaderboard=self.optimizer.leaderboard(),
        )

    def _build_recommendations(self, baseline: CandidateResult, best: CandidateResult) -> List[str]:
        recs: List[str] = []
        base_cfg, best_cfg = baseline.config, best.config

        if best_cfg.architecture.num_sms != base_cfg.architecture.num_sms:
            direction = "increasing" if best_cfg.architecture.num_sms > base_cfg.architecture.num_sms else "reducing"
            recs.append(
                f"{direction.capitalize()} SM count from {base_cfg.architecture.num_sms} to "
                f"{best_cfg.architecture.num_sms} improved the '{self.objective}' objective."
            )
        if best_cfg.compute.cuda_cores_per_sm != base_cfg.compute.cuda_cores_per_sm:
            recs.append(
                f"CUDA cores/SM changed from {base_cfg.compute.cuda_cores_per_sm} to "
                f"{best_cfg.compute.cuda_cores_per_sm} -- wider SMs trade area/power for throughput."
            )
        if best_cfg.memory.l2_cache_kb != base_cfg.memory.l2_cache_kb:
            recs.append(
                f"L2 cache resized from {base_cfg.memory.l2_cache_kb}KB to {best_cfg.memory.l2_cache_kb}KB "
                f"based on observed hit-rate/bandwidth pressure."
            )
        if best_cfg.power.tdp_watts != base_cfg.power.tdp_watts:
            recs.append(
                f"TDP target moved from {base_cfg.power.tdp_watts:.0f}W to {best_cfg.power.tdp_watts:.0f}W."
            )
        if best.throttle_events > 0:
            recs.append(
                f"Best candidate still throttled {best.throttle_events} time(s) during evaluation -- "
                f"consider a stronger cooling solution before committing to this configuration."
            )
        if not recs:
            recs.append("Baseline architecture was already at (or near) a local optimum for this objective.")
        return recs
