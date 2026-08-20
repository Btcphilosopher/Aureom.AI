"""
Environmental constraints. These are modelled as hard constraints the
optimiser must respect, never as a soft penalty that can be traded away
purely because it reduces output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from hydroflux.core.config import EnvironmentalConfig


@dataclass
class EnvironmentalViolation:
    timestamp: pd.Timestamp
    constraint: str
    requested_value: float
    permitted_value: float


class EnvironmentalConstraints:
    def __init__(self, config: EnvironmentalConfig):
        self.config = config

    def _restricted_flow_cap(self, index: pd.DatetimeIndex) -> pd.Series:
        cap = pd.Series(np.inf, index=index)
        for period in self.config.restricted_periods:
            start = pd.Timestamp(period["start"])
            end = pd.Timestamp(period["end"])
            max_flow = period.get("max_flow_m3s", np.inf)
            mask = (index >= start) & (index <= end)
            cap.loc[mask] = np.minimum(cap.loc[mask], max_flow)
        return cap

    def apply(self, planned_flow_m3s: pd.Series, natural_flow_m3s: Optional[pd.Series] = None) -> tuple[pd.Series, list[EnvironmentalViolation]]:
        """Clip a planned release/diversion flow to environmental limits:
        minimum ecological flow, maximum flow alteration relative to the
        natural flow regime, and any time-bounded restricted periods
        (fish migration, spawning, etc.).

        ``maximum_flow_alteration_pct`` only makes sense once an actual
        release decision exists to check -- pass ``natural_flow_m3s=None``
        (the default) when deriving a *pre-dispatch* availability ceiling,
        and only pass the natural flow series when checking a plant's
        *actual* release against it, otherwise every regulated release from
        a storage reservoir (which is supposed to differ from
        instantaneous natural inflow -- that is what "regulation" means)
        would trivially register as a violation of itself.
        """

        index = planned_flow_m3s.index
        permitted = planned_flow_m3s.copy()
        violations: list[EnvironmentalViolation] = []

        below_min = permitted < self.config.minimum_ecological_flow_m3s
        if below_min.any():
            for ts in index[below_min]:
                violations.append(
                    EnvironmentalViolation(ts, "minimum_ecological_flow_m3s", float(planned_flow_m3s.loc[ts]), self.config.minimum_ecological_flow_m3s)
                )
        permitted = permitted.clip(lower=self.config.minimum_ecological_flow_m3s)

        if natural_flow_m3s is not None and self.config.maximum_flow_alteration_pct < 100.0:
            natural = natural_flow_m3s.reindex(index)
            max_allowed = natural * (self.config.maximum_flow_alteration_pct / 100.0)
            over = permitted > max_allowed
            if over.any():
                for ts in index[over.fillna(False)]:
                    violations.append(
                        EnvironmentalViolation(ts, "maximum_flow_alteration_pct", float(planned_flow_m3s.loc[ts]), float(max_allowed.loc[ts]))
                    )
            permitted = permitted.clip(upper=max_allowed)

        restricted_cap = self._restricted_flow_cap(index)
        over_restricted = permitted > restricted_cap
        if over_restricted.any():
            for ts in index[over_restricted]:
                violations.append(
                    EnvironmentalViolation(ts, "restricted_period", float(planned_flow_m3s.loc[ts]), float(restricted_cap.loc[ts]))
                )
        permitted = np.minimum(permitted, restricted_cap)

        return permitted, violations

    def check_reservoir_level(self, level_m: pd.Series) -> list[EnvironmentalViolation]:
        violations: list[EnvironmentalViolation] = []
        if self.config.minimum_reservoir_level_m is not None:
            below = level_m < self.config.minimum_reservoir_level_m
            for ts in level_m.index[below]:
                violations.append(EnvironmentalViolation(ts, "minimum_reservoir_level_m", float(level_m.loc[ts]), self.config.minimum_reservoir_level_m))
        if self.config.maximum_reservoir_level_m is not None:
            above = level_m > self.config.maximum_reservoir_level_m
            for ts in level_m.index[above]:
                violations.append(EnvironmentalViolation(ts, "maximum_reservoir_level_m", float(level_m.loc[ts]), self.config.maximum_reservoir_level_m))
        return violations
