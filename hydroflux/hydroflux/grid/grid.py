"""
Grid-interaction model: objectives beyond raw MWh, curtailment, and a grid
"value" score that rewards generation coincident with high demand/price
rather than generation volume alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd


class GridObjective(str, Enum):
    MAX_ENERGY = "max_energy"
    MAX_REVENUE = "max_revenue"
    MIN_LCOE = "min_lcoe"
    MAX_NPV = "max_npv"
    MAX_GRID_VALUE = "max_grid_value"


@dataclass
class CurtailmentResult:
    delivered_mw: pd.Series
    curtailed_mw: pd.Series
    curtailment_pct: float


def curtailment(generation_mw: pd.Series, grid_capacity_mw: Optional[float]) -> CurtailmentResult:
    """Cap generation at the grid export capacity; anything above is
    curtailed rather than exported."""

    if grid_capacity_mw is None:
        zeros = pd.Series(0.0, index=generation_mw.index)
        return CurtailmentResult(delivered_mw=generation_mw, curtailed_mw=zeros, curtailment_pct=0.0)

    delivered = generation_mw.clip(upper=grid_capacity_mw)
    curtailed = (generation_mw - delivered).clip(lower=0.0)
    total_gen = generation_mw.sum()
    pct = float(100.0 * curtailed.sum() / total_gen) if total_gen > 0 else 0.0
    return CurtailmentResult(delivered_mw=delivered, curtailed_mw=curtailed, curtailment_pct=pct)


def grid_value_score(
    generation_mw: pd.Series,
    price: Optional[pd.Series] = None,
    demand_mw: Optional[pd.Series] = None,
    peak_demand_weight: float = 0.0,
) -> float:
    """A composite "grid value" score: revenue-weighted generation, with an
    optional bonus for generation coincident with system peak demand
    (a simple proxy for capacity/flexibility value beyond pure energy
    revenue)."""

    score = 0.0
    if price is not None:
        score += float((generation_mw * price.reindex(generation_mw.index).fillna(0.0)).sum())
    else:
        score += float(generation_mw.sum())

    if demand_mw is not None and peak_demand_weight > 0:
        demand_aligned = demand_mw.reindex(generation_mw.index).fillna(0.0)
        peak = demand_aligned.max()
        if peak > 0:
            coincidence = (generation_mw * demand_aligned / peak).sum()
            score += peak_demand_weight * float(coincidence)

    return score


def balancing_requirement(generation_mw: pd.Series, demand_mw: pd.Series) -> pd.Series:
    """Net imbalance the grid must otherwise balance: demand minus
    generation (positive = shortfall, negative = surplus/export)."""

    return demand_mw.reindex(generation_mw.index).fillna(0.0) - generation_mw
