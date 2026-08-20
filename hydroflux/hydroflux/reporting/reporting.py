"""
Reporting: the standard result objects every HydroFlux run returns, a
human-readable summary formatter, a scenario-comparison table, sensitivity
analysis and a Monte Carlo uncertainty engine.

Every :class:`SimulationResult` carries a :class:`ReproducibilityRecord` so
any result can be traced back to the exact model version, scenario,
configuration, input data, random seed and optimisation method that
produced it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence

import numpy as np
import pandas as pd

from hydroflux._version import __version__ as MODEL_VERSION


@dataclass
class ReproducibilityRecord:
    model_version: str = MODEL_VERSION
    scenario: str = "baseline"
    configuration_hash: str = ""
    input_data_hash: str = ""
    random_seed: Optional[int] = None
    optimisation_method: str = ""
    optimisation_parameters: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def hash_dict(data: dict) -> str:
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def hash_series(series: Optional[pd.Series]) -> str:
    if series is None:
        return ""
    return hashlib.sha256(np.asarray(series.values).tobytes()).hexdigest()[:16]


@dataclass
class SimulationResult:
    """Standard output of a HydroFlux simulation or optimisation run --
    section 36's checklist made concrete."""

    system_name: str
    generation_mw: pd.Series
    reservoir_level_m: Optional[pd.Series] = None
    spill_m3s: Optional[pd.Series] = None
    curtailment_mw: Optional[pd.Series] = None
    turbine_dispatch: Optional[pd.DataFrame] = None

    annual_generation_mwh: float = 0.0
    peak_generation_mw: float = 0.0
    capacity_factor: float = 0.0
    average_efficiency: float = 0.0
    water_utilisation_pct: float = 100.0
    spillage_pct: float = 0.0
    curtailment_pct: float = 0.0

    revenue: float = 0.0
    capex: float = 0.0
    opex: float = 0.0
    lcoe: float = 0.0
    npv: float = 0.0
    irr: Optional[float] = None

    environmental_metrics: dict = field(default_factory=dict)
    constraint_violations: list = field(default_factory=list)

    theoretical_potential_mwh: Optional[float] = None
    physical_potential_mwh: Optional[float] = None
    available_generation_mwh: Optional[float] = None
    environmentally_permitted_mwh: Optional[float] = None

    metadata: ReproducibilityRecord = field(default_factory=ReproducibilityRecord)

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in asdict(self).items() if not isinstance(v, (pd.Series, pd.DataFrame))}
        return d

    def to_json(self, path: str) -> None:
        from pathlib import Path

        Path(path).write_text(json.dumps(self.to_dict(), indent=2, default=str))

    def to_csv(self, path: str) -> None:
        frame = pd.DataFrame({"generation_mw": self.generation_mw})
        if self.reservoir_level_m is not None:
            frame["reservoir_level_m"] = self.reservoir_level_m
        if self.spill_m3s is not None:
            frame["spill_m3s"] = self.spill_m3s
        if self.curtailment_mw is not None:
            frame["curtailment_mw"] = self.curtailment_mw
        frame.to_csv(path, index_label="timestamp")


def summarize(result: SimulationResult) -> str:
    lines = [
        "HYDROFLUX OPTIMISATION" if result.metadata.optimisation_method else "HYDROFLUX SIMULATION",
        "System:",
        f"  {result.system_name}",
        "",
        "Annual Generation:",
        f"  {result.annual_generation_mwh / 1000:.2f} GWh",
        "Peak Generation:",
        f"  {result.peak_generation_mw:.1f} MW",
        "Capacity Factor:",
        f"  {result.capacity_factor * 100:.1f}%",
        "Average Efficiency:",
        f"  {result.average_efficiency * 100:.1f}%",
        "Water Utilisation:",
        f"  {result.water_utilisation_pct:.1f}%",
        "Spillage:",
        f"  {result.spillage_pct:.1f}%",
        "Curtailment:",
        f"  {result.curtailment_pct:.1f}%",
        "",
        "Annual Revenue:",
        f"  {result.revenue:,.0f}",
        "LCOE:",
        f"  {result.lcoe:.2f} /MWh",
        "NPV:",
        f"  {result.npv / 1e6:,.1f} million",
    ]
    if result.irr is not None:
        lines += ["IRR:", f"  {result.irr * 100:.1f}%"]
    if result.constraint_violations:
        lines += ["", f"Constraint violations: {len(result.constraint_violations)}"]
    return "\n".join(lines)


class ComparisonEngine:
    """Compare multiple named :class:`SimulationResult` objects side by
    side (specification section 37)."""

    @staticmethod
    def compare(results: dict[str, SimulationResult]) -> pd.DataFrame:
        rows = []
        for name, result in results.items():
            rows.append(
                {
                    "scenario": name,
                    "generation_gwh": result.annual_generation_mwh / 1000,
                    "capacity_factor_pct": result.capacity_factor * 100,
                    "average_efficiency_pct": result.average_efficiency * 100,
                    "revenue": result.revenue,
                    "lcoe": result.lcoe,
                    "npv": result.npv,
                    "spillage_pct": result.spillage_pct,
                    "curtailment_pct": result.curtailment_pct,
                }
            )
        return pd.DataFrame(rows).set_index("scenario")


def sensitivity_analysis(
    evaluate_fn: Callable[[dict[str, float]], float],
    base_params: dict[str, float],
    variables: Sequence[str],
    deltas: Sequence[float] = (0.05, 0.10, 0.20),
) -> pd.DataFrame:
    """For each variable in ``base_params``, perturb it by +/-``deltas`` and
    record the resulting change in ``evaluate_fn``'s scalar output. Returns
    a table ranked by the largest absolute effect on the objective
    (specification section 38)."""

    base_value = evaluate_fn(base_params)
    rows = []
    for var in variables:
        if var not in base_params:
            continue
        max_abs_effect = 0.0
        for delta in deltas:
            for sign in (+1, -1):
                perturbed = dict(base_params)
                perturbed[var] = base_params[var] * (1 + sign * delta)
                value = evaluate_fn(perturbed)
                pct_change = 100.0 * (value - base_value) / base_value if base_value != 0 else np.nan
                rows.append(
                    {
                        "variable": var,
                        "delta_pct": sign * delta * 100,
                        "objective_value": value,
                        "objective_change_pct": pct_change,
                    }
                )
                max_abs_effect = max(max_abs_effect, abs(pct_change) if not np.isnan(pct_change) else 0.0)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    ranking = df.groupby("variable")["objective_change_pct"].apply(lambda s: s.abs().max()).sort_values(ascending=False)
    df["variable"] = pd.Categorical(df["variable"], categories=ranking.index, ordered=True)
    return df.sort_values(["variable", "delta_pct"]).reset_index(drop=True)


@dataclass
class MonteCarloResult:
    samples: pd.DataFrame
    percentiles: dict[str, dict[str, float]]  # {metric: {"P10":..., "P50":..., "P90":...}}


class MonteCarloEngine:
    """Runs ``evaluate_fn`` over many sampled scenarios and reports
    distributions (P10/P50/P90) for each returned metric (specification
    section 39)."""

    def run(
        self,
        evaluate_fn: Callable[[int], dict[str, float]],
        n_scenarios: int = 1000,
        seed: int = 42,
    ) -> MonteCarloResult:
        rng = np.random.default_rng(seed)
        seeds = rng.integers(0, 2**31 - 1, size=n_scenarios)
        rows = [evaluate_fn(int(s)) for s in seeds]
        df = pd.DataFrame(rows)

        percentiles: dict[str, dict[str, float]] = {}
        for col in df.columns:
            percentiles[col] = {
                "P10": float(np.percentile(df[col], 10)),
                "P50": float(np.percentile(df[col], 50)),
                "P90": float(np.percentile(df[col], 90)),
                "mean": float(df[col].mean()),
                "std": float(df[col].std()),
            }
        return MonteCarloResult(samples=df, percentiles=percentiles)
