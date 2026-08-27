"""Analytics engine: quality index, energy, production throughput, Monte Carlo statistics."""

from __future__ import annotations

from icecream_x.analytics.energy import EnergyBreakdown, energy_breakdown
from icecream_x.analytics.production import ProductionRateResult, production_rate
from icecream_x.analytics.quality import DEFAULT_WEIGHTS, QualityResult, QualityWeights, quality_score
from icecream_x.analytics.statistics import MonteCarloResult, PercentileSummary, run_monte_carlo

__all__ = [
    "EnergyBreakdown",
    "energy_breakdown",
    "ProductionRateResult",
    "production_rate",
    "QualityResult",
    "QualityWeights",
    "DEFAULT_WEIGHTS",
    "quality_score",
    "MonteCarloResult",
    "PercentileSummary",
    "run_monte_carlo",
]
