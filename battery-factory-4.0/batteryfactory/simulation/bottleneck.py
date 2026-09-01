"""Bottleneck detection (spec item 20): a normalised score per stage."""
from __future__ import annotations

from dataclasses import dataclass

from batteryfactory.simulation.des_engine import FactorySimulationResult


@dataclass
class BottleneckScore:
    stage: str
    utilisation_pct: float
    scrap_rate_pct: float
    queue_utilisation_pct: float
    score: float  # 0..100, higher = more of a bottleneck


class BottleneckAnalyzer:
    """
    Combines utilisation, scrap and downstream-queue pressure into one
    comparable score per stage, so "the bottleneck" is a ranking, not a
    single hard-coded metric.
    """

    _BUFFER_FOR_STAGE = {
        "electrode": "assembly_in",
        "assembly": "formation_in",
        "formation": "testing_in",
        "testing": "module_in",
        "module": "pack_in",
        "pack": "warehouse",
    }

    def __init__(self, weight_utilisation: float = 0.5, weight_scrap: float = 0.3, weight_queue: float = 0.2) -> None:
        total = weight_utilisation + weight_scrap + weight_queue
        self.w_util = weight_utilisation / total
        self.w_scrap = weight_scrap / total
        self.w_queue = weight_queue / total

    def analyze(self, result: FactorySimulationResult) -> list[BottleneckScore]:
        scores: list[BottleneckScore] = []
        for stage, stats in result.stage_stats.items():
            total_hours = stats.busy_hours + stats.idle_hours
            utilisation_pct = 100.0 * stats.busy_hours / total_hours if total_hours > 0 else 0.0
            throughput = stats.completed_units + stats.scrapped_units
            scrap_rate_pct = 100.0 * stats.scrapped_units / throughput if throughput > 0 else 0.0

            buffer_name = self._BUFFER_FOR_STAGE.get(stage)
            queue_utilisation_pct = result.buffers[buffer_name].utilisation_pct if buffer_name in result.buffers else 0.0

            score = (self.w_util * utilisation_pct) + (self.w_scrap * scrap_rate_pct) + (self.w_queue * queue_utilisation_pct)
            scores.append(BottleneckScore(stage, utilisation_pct, scrap_rate_pct, queue_utilisation_pct, score))

        return sorted(scores, key=lambda s: s.score, reverse=True)

    def top_bottleneck(self, result: FactorySimulationResult) -> BottleneckScore | None:
        scores = self.analyze(result)
        return scores[0] if scores else None
