"""Monte Carlo uncertainty analysis.

Generic driver: given a callable that runs one full simulation from a
seeded :class:`numpy.random.Generator` and returns a flat dict of scalar
outputs, runs it ``n_samples`` times and reports P10/P50/P90 (plus
mean/std) for every output key. Reproducible for a fixed
``random_seed`` (uses NumPy's PCG64 generator via
``numpy.random.default_rng``, not the global numpy random state).

Used by :mod:`icecream_x.scenarios.experiments` to propagate uncertainty
in ingredient composition, ambient temperature, freezer performance,
heat-transfer coefficients, storage temperature, processing time, and
measurement error through to outputs like crystal size, energy
consumption, melting time, manufacturing cost, and quality score.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class PercentileSummary:
    p10: float
    p50: float
    p90: float
    mean: float
    std: float


@dataclass(frozen=True, slots=True)
class MonteCarloResult:
    n_samples: int
    samples: dict[str, np.ndarray]
    summary: dict[str, PercentileSummary]

    def summary_table(self) -> list[dict[str, float | str]]:
        return [
            {
                "output": key,
                "p10": s.p10,
                "p50": s.p50,
                "p90": s.p90,
                "mean": s.mean,
                "std": s.std,
            }
            for key, s in self.summary.items()
        ]


def summarise(values: np.ndarray) -> PercentileSummary:
    return PercentileSummary(
        p10=float(np.percentile(values, 10)),
        p50=float(np.percentile(values, 50)),
        p90=float(np.percentile(values, 90)),
        mean=float(np.mean(values)),
        std=float(np.std(values)),
    )


def run_monte_carlo(
    run_once: Callable[[np.random.Generator], dict[str, float]],
    n_samples: int,
    random_seed: int = 42,
) -> MonteCarloResult:
    rng = np.random.default_rng(random_seed)
    collected: dict[str, list[float]] = {}

    for _ in range(n_samples):
        outputs = run_once(rng)
        for key, value in outputs.items():
            collected.setdefault(key, []).append(value)

    samples = {key: np.array(values) for key, values in collected.items()}
    summary = {key: summarise(values) for key, values in samples.items()}
    return MonteCarloResult(n_samples=n_samples, samples=samples, summary=summary)
