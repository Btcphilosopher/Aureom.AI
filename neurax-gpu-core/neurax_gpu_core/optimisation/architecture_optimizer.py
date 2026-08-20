"""
Cross-run architecture optimiser.

Unlike the runtime scheduling/memory optimisers, SM count, cache sizes and
power/thermal envelopes cannot be changed inside a running die -- they are
what get respun into the *next* chip. This optimiser therefore works at the
level of whole simulation runs: it perturbs a few architectural knobs on a
copy of the base :class:`~utils.config.GPUConfig`, runs a short simulation
of each candidate, scores it against an objective, and keeps the best --
a coordinate-ascent / local search over the design space driven entirely by
simulated (not assumed) outcomes.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..utils.config import GPUConfig
from ..workloads.base import Workload


@dataclass
class CandidateResult:
    config: GPUConfig
    score: float
    avg_tflops: float
    avg_power_watts: float
    avg_gflops_per_watt: float
    silicon_cost_index: float
    max_die_temp_c: float
    throttle_events: int
    label: str


Objective = Callable[[Dict], float]


def objective_perf_per_watt(summary: Dict, cost_index: float) -> float:
    return summary.get("avg_gflops_per_watt", 0.0)


def objective_perf_per_dollar(summary: Dict, cost_index: float) -> float:
    if cost_index <= 0 or cost_index == float("inf"):
        return 0.0
    return summary.get("avg_tflops", 0.0) / cost_index


def objective_raw_throughput(summary: Dict, cost_index: float) -> float:
    return summary.get("avg_tflops", 0.0)


OBJECTIVES = {
    "perf_per_watt": objective_perf_per_watt,
    "perf_per_dollar": objective_perf_per_dollar,
    "raw_throughput": objective_raw_throughput,
}


# Knob perturbations tried at each step: (config_path, candidate_multipliers)
_KNOBS: List[Tuple[str, str, List[float]]] = [
    ("architecture", "num_sms", [0.75, 1.0, 1.25, 1.5]),
    ("compute", "cuda_cores_per_sm", [0.5, 1.0, 2.0]),
    ("memory", "l2_cache_kb", [0.5, 1.0, 2.0]),
    ("power", "tdp_watts", [0.7, 1.0, 1.3]),
]


def _apply_multiplier(config: GPUConfig, section: str, field_name: str, multiplier: float) -> GPUConfig:
    cfg = copy.deepcopy(config)
    section_obj = getattr(cfg, section)
    current = getattr(section_obj, field_name)
    new_value = current * multiplier
    if isinstance(current, int):
        new_value = max(1, int(round(new_value)))
    setattr(section_obj, field_name, new_value)
    if section == "power":
        cfg.thermal.tdp_watts = cfg.power.tdp_watts
    return cfg


class ArchitectureOptimizer:
    def __init__(self, workload_factory: Callable[[], List[Workload]], objective: str = "perf_per_watt",
                 eval_timesteps: int = 30, eval_micro_cycles: int = 96):
        if objective not in OBJECTIVES:
            raise KeyError(f"Unknown objective '{objective}'. Available: {sorted(OBJECTIVES)}")
        self.workload_factory = workload_factory
        self.objective_fn = OBJECTIVES[objective]
        self.objective_name = objective
        self.eval_timesteps = eval_timesteps
        self.eval_micro_cycles = eval_micro_cycles
        self.history: List[CandidateResult] = []

    def _evaluate(self, config: GPUConfig, label: str) -> CandidateResult:
        # Imported locally to avoid a core <-> optimisation import cycle at
        # module load time (core.engine does not import this module, but
        # keeping the dependency one-directional and lazy is good hygiene).
        from ..core.engine import SimulationEngine
        from ..silicon.transistor_cost import TransistorCostModel

        run_config = copy.deepcopy(config)
        run_config.simulation.timesteps = self.eval_timesteps
        run_config.simulation.micro_cycles_per_timestep = self.eval_micro_cycles
        run_config.simulation.enable_ai_optimisation = False

        engine = SimulationEngine(run_config, self.workload_factory())
        engine.run(self.eval_timesteps)
        summary = engine.summary()

        cost_index = TransistorCostModel(run_config).silicon_cost_index()
        score = self.objective_fn(summary, cost_index)

        result = CandidateResult(
            config=run_config, score=score, avg_tflops=summary.get("avg_tflops", 0.0),
            avg_power_watts=summary.get("avg_power_watts", 0.0),
            avg_gflops_per_watt=summary.get("avg_gflops_per_watt", 0.0),
            silicon_cost_index=cost_index, max_die_temp_c=summary.get("max_die_temp_c", 0.0),
            throttle_events=summary.get("throttle_events", 0), label=label,
        )
        self.history.append(result)
        return result

    def search(self, base_config: GPUConfig, rounds: int = 2) -> CandidateResult:
        """Coordinate-ascent local search: for each knob in turn, try a few
        multipliers and keep whichever improves the objective, repeating for
        ``rounds`` full passes over the knob list."""
        best = self._evaluate(base_config, label="baseline")
        current_config = best.config

        for round_idx in range(rounds):
            for section, field_name, multipliers in _KNOBS:
                for mult in multipliers:
                    if mult == 1.0:
                        continue
                    candidate_cfg = _apply_multiplier(current_config, section, field_name, mult)
                    label = f"round{round_idx}:{section}.{field_name}x{mult}"
                    try:
                        candidate = self._evaluate(candidate_cfg, label)
                    except Exception:
                        continue
                    if candidate.score > best.score:
                        best = candidate
                        current_config = candidate.config

        return best

    def leaderboard(self, top_n: int = 10) -> List[CandidateResult]:
        return sorted(self.history, key=lambda r: r.score, reverse=True)[:top_n]
