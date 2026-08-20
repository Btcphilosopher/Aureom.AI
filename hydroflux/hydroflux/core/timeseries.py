"""
Common time-series interface shared by every HydroFlux module.

Hydraulic, tidal and economic inputs are naturally time-indexed (flow, head,
water level, temperature, electricity price, demand).  Rather than let each
sub-package invent its own representation, everything funnels through
:class:`ResourceTimeSeries`, a thin wrapper around a set of aligned
``pandas.Series`` objects with a shared ``DatetimeIndex``.  This gives the
rest of the engine one resampling/alignment code path for 10-minute,
15-minute, 30-minute, hourly and daily resolutions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

import numpy as np
import pandas as pd

#: Resolutions HydroFlux is explicitly designed to support (pandas offset
#: aliases).  Any pandas-recognised offset works; these are the ones the
#: rest of the engine is tuned for.
SUPPORTED_FREQUENCIES = {
    "10min": "10-minute",
    "15min": "15-minute",
    "30min": "30-minute",
    "1h": "hourly",
    "1D": "daily",
}


def make_time_index(start: str | pd.Timestamp, periods: int, freq: str = "1h") -> pd.DatetimeIndex:
    """Build a ``DatetimeIndex`` for a simulation horizon."""

    return pd.date_range(start=start, periods=periods, freq=freq)


def resample_series(series: pd.Series, freq: str, method: str = "mean") -> pd.Series:
    """Resample a time series to a new frequency.

    Downsampling (e.g. hourly -> daily) aggregates with ``method``
    ("mean", "sum", "max", "min"). Upsampling (e.g. hourly -> 15min)
    linearly interpolates, which is appropriate for smoothly varying
    hydraulic quantities such as flow and head.
    """

    if series.empty:
        return series

    current_delta = series.index.to_series().diff().median()
    target_delta = pd.tseries.frequencies.to_offset(freq).delta if hasattr(
        pd.tseries.frequencies.to_offset(freq), "delta"
    ) else pd.Timedelta(pd.tseries.frequencies.to_offset(freq).nanos)

    if pd.isna(current_delta) or target_delta >= current_delta:
        agg = getattr(series.resample(freq), method)
        return agg()
    # Upsampling: reindex + interpolate.
    resampled = series.resample(freq).asfreq()
    return resampled.interpolate(method="time").bfill().ffill()


def generate_synthetic_series(
    index: pd.DatetimeIndex,
    mean: float,
    amplitude: float = 0.0,
    period_hours: float = 24.0 * 365.25,
    noise_std: float = 0.0,
    seed: Optional[int] = None,
    floor: Optional[float] = 0.0,
) -> pd.Series:
    """Generate a reproducible synthetic time series (seasonal sine + noise).

    Used for demonstration inputs and for scenario perturbation when real
    data is unavailable. Always seeded so results are reproducible.
    """

    rng = np.random.default_rng(seed)
    t_hours = (index - index[0]).total_seconds() / 3600.0
    seasonal = amplitude * np.sin(2 * np.pi * t_hours / period_hours)
    noise = rng.normal(0.0, noise_std, size=len(index)) if noise_std else 0.0
    values = mean + seasonal + noise
    if floor is not None:
        values = np.maximum(values, floor)
    return pd.Series(values, index=index)


@dataclass
class ResourceTimeSeries:
    """Aligned hydraulic/tidal/economic input data for a simulation run.

    All series share ``index``. Any field left as ``None`` is treated as
    "not provided" by downstream models (e.g. a run-of-river system has no
    ``water_level``).
    """

    index: pd.DatetimeIndex
    flow: Optional[pd.Series] = None  # m3/s
    head: Optional[pd.Series] = None  # m (static/gross head, if externally supplied)
    water_level: Optional[pd.Series] = None  # m (reservoir / sea / basin elevation)
    tailwater_level: Optional[pd.Series] = None  # m
    temperature: Optional[pd.Series] = None  # degC
    price: Optional[pd.Series] = None  # currency / MWh
    demand: Optional[pd.Series] = None  # MW
    inflow: Optional[pd.Series] = None  # m3/s, river inflow to a reservoir
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "flow",
            "head",
            "water_level",
            "tailwater_level",
            "temperature",
            "price",
            "demand",
            "inflow",
        ):
            series = getattr(self, name)
            if series is not None and not series.index.equals(self.index):
                raise ValueError(f"ResourceTimeSeries.{name} index does not match the shared index")

    @property
    def n_steps(self) -> int:
        return len(self.index)

    @property
    def dt_hours(self) -> float:
        """Median timestep length in hours (used for energy integration)."""

        if len(self.index) < 2:
            return 1.0
        delta = self.index.to_series().diff().median()
        return delta.total_seconds() / 3600.0

    def resample_to(self, freq: str) -> "ResourceTimeSeries":
        """Return a new :class:`ResourceTimeSeries` resampled to ``freq``."""

        new_index = None
        fields = {}
        for name in (
            "flow",
            "head",
            "water_level",
            "tailwater_level",
            "temperature",
            "price",
            "demand",
            "inflow",
        ):
            series = getattr(self, name)
            if series is None:
                fields[name] = None
                continue
            method = "sum" if name in ("demand",) else "mean"
            resampled = resample_series(series, freq, method=method)
            fields[name] = resampled
            new_index = resampled.index
        if new_index is None:
            new_index = pd.date_range(self.index[0], self.index[-1], freq=freq)
        return ResourceTimeSeries(index=new_index, metadata=dict(self.metadata), **fields)

    def slice(self, start=None, end=None) -> "ResourceTimeSeries":
        fields = {}
        idx = self.index
        mask = pd.Series(True, index=idx)
        if start is not None:
            mask &= idx >= pd.Timestamp(start)
        if end is not None:
            mask &= idx <= pd.Timestamp(end)
        new_index = idx[mask.values]
        for name in (
            "flow",
            "head",
            "water_level",
            "tailwater_level",
            "temperature",
            "price",
            "demand",
            "inflow",
        ):
            series = getattr(self, name)
            fields[name] = series.loc[new_index] if series is not None else None
        return ResourceTimeSeries(index=new_index, metadata=dict(self.metadata), **fields)

    def to_frame(self) -> pd.DataFrame:
        data = {}
        for name in (
            "flow",
            "head",
            "water_level",
            "tailwater_level",
            "temperature",
            "price",
            "demand",
            "inflow",
        ):
            series = getattr(self, name)
            if series is not None:
                data[name] = series
        return pd.DataFrame(data, index=self.index)

    @classmethod
    def from_frame(cls, df: pd.DataFrame, metadata: Optional[dict] = None) -> "ResourceTimeSeries":
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame must have a DatetimeIndex")
        kwargs = {name: df[name] for name in df.columns if name in cls.__dataclass_fields__}
        return cls(index=df.index, metadata=metadata or {}, **kwargs)
