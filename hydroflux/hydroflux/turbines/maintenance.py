"""
Maintenance scheduling and failure-mode modelling (specification sections 28
and 29).

Maintenance is scheduled to minimise lost generation value by preferring
low-price / low-flow windows; failures are modelled as availability masks
applied to a turbine's generation, from which lost generation, lost revenue
and recovery time are computed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class MaintenanceWindow:
    turbine_id: str
    start: pd.Timestamp
    duration_hours: float

    @property
    def end(self) -> pd.Timestamp:
        return self.start + pd.Timedelta(hours=self.duration_hours)


def schedule_maintenance(
    turbine_ids: list[str],
    index: pd.DatetimeIndex,
    price: pd.Series,
    flow: pd.Series,
    duration_hours: float = 168.0,
    stagger: bool = True,
) -> list[MaintenanceWindow]:
    """Greedily place one maintenance window per turbine in the lowest
    opportunity-cost period available (lowest price x flow, i.e. lowest
    potential generation revenue), staggering turbines onto non-overlapping
    windows when requested so the whole fleet is not out simultaneously.
    """

    opportunity_cost = (price.reindex(index).fillna(price.mean()) * flow.reindex(index).fillna(flow.mean())).values
    window_steps = max(int(duration_hours / max(_median_step_hours(index), 1e-9)), 1)

    # Rolling sum of opportunity cost for every candidate start position.
    rolling = pd.Series(opportunity_cost).rolling(window_steps, min_periods=window_steps).sum()
    candidate_starts = rolling.dropna().sort_values().index.tolist()

    windows: list[MaintenanceWindow] = []
    used_ranges: list[tuple[int, int]] = []
    for turbine_id in turbine_ids:
        chosen = None
        for start_idx in candidate_starts:
            end_idx = start_idx  # rolling sum window ends at start_idx (inclusive)
            begin_idx = start_idx - window_steps + 1
            if begin_idx < 0:
                continue
            if stagger and any(not (end_idx < b or begin_idx > e) for b, e in used_ranges):
                continue
            chosen = begin_idx
            used_ranges.append((begin_idx, end_idx))
            break
        if chosen is None:
            chosen = 0
        windows.append(MaintenanceWindow(turbine_id=turbine_id, start=index[chosen], duration_hours=duration_hours))
    return windows


def _median_step_hours(index: pd.DatetimeIndex) -> float:
    if len(index) < 2:
        return 1.0
    return index.to_series().diff().median().total_seconds() / 3600.0


def simulate_failure(index: pd.DatetimeIndex, failure_start: pd.Timestamp, repair_time_hours: float) -> pd.Series:
    """Return a 0/1 availability mask over ``index`` with the turbine
    unavailable from ``failure_start`` for ``repair_time_hours``."""

    failure_end = failure_start + pd.Timedelta(hours=repair_time_hours)
    available = ~((index >= failure_start) & (index < failure_end))
    return pd.Series(available.astype(float), index=index)


@dataclass
class FailureImpact:
    lost_generation_mwh: float
    lost_revenue: float
    recovery_time_hours: float


def evaluate_failure_impact(
    generation_mw: pd.Series,
    price: pd.Series,
    availability_mask: pd.Series,
    dt_hours: float = 1.0,
) -> FailureImpact:
    """Compare generation under an availability mask to the unconstrained
    (fully available) case to quantify the cost of a failure."""

    unconstrained_mwh = generation_mw * dt_hours
    constrained_mwh = generation_mw * availability_mask.reindex(generation_mw.index).fillna(1.0) * dt_hours
    lost_mwh = float((unconstrained_mwh - constrained_mwh).clip(lower=0).sum())
    lost_revenue = float(
        ((unconstrained_mwh - constrained_mwh).clip(lower=0) * price.reindex(generation_mw.index).fillna(0)).sum()
    )
    outage_hours = float((1.0 - availability_mask.clip(0, 1)).sum() * dt_hours)
    return FailureImpact(lost_generation_mwh=lost_mwh, lost_revenue=lost_revenue, recovery_time_hours=outage_hours)
