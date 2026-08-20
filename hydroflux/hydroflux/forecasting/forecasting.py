"""
Lightweight forecasting utilities for flow, price and demand series.
Deliberately simple, transparent methods -- persistence, seasonal-naive and
exponential smoothing -- rather than a heavyweight forecasting dependency;
the interface is what matters for the rest of the engine (a forecaster that
takes a history and a horizon and returns a forecast), so a more
sophisticated model can be substituted without touching callers.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def persistence_forecast(series: pd.Series, horizon: int) -> pd.Series:
    """Naive forecast: repeat the last observed value."""

    freq = series.index.freq or pd.infer_freq(series.index)
    future_index = pd.date_range(series.index[-1], periods=horizon + 1, freq=freq)[1:]
    return pd.Series(np.full(horizon, series.iloc[-1]), index=future_index)


def seasonal_naive_forecast(series: pd.Series, horizon: int, period: int) -> pd.Series:
    """Repeat the last full seasonal cycle (e.g. period=24 for hourly data
    with a daily cycle, period=8760 for hourly data with an annual cycle)."""

    freq = series.index.freq or pd.infer_freq(series.index)
    future_index = pd.date_range(series.index[-1], periods=horizon + 1, freq=freq)[1:]
    if len(series) < period:
        values = np.full(horizon, series.iloc[-1])
    else:
        last_cycle = series.iloc[-period:].values
        reps = int(np.ceil(horizon / period))
        values = np.tile(last_cycle, reps)[:horizon]
    return pd.Series(values, index=future_index)


def exponential_smoothing_forecast(series: pd.Series, horizon: int, alpha: float = 0.3) -> pd.Series:
    """Simple exponential smoothing, projected flat from the smoothed level
    (appropriate for short-horizon operational forecasts of a
    slowly-varying quantity such as reservoir inflow)."""

    level = series.iloc[0]
    for value in series.values[1:]:
        level = alpha * value + (1 - alpha) * level
    freq = series.index.freq or pd.infer_freq(series.index)
    future_index = pd.date_range(series.index[-1], periods=horizon + 1, freq=freq)[1:]
    return pd.Series(np.full(horizon, level), index=future_index)


class SimpleForecaster:
    _METHODS = {
        "persistence": persistence_forecast,
        "exponential_smoothing": exponential_smoothing_forecast,
    }

    def forecast(self, series: pd.Series, horizon: int, method: str = "seasonal_naive", period: Optional[int] = None, **kwargs) -> pd.Series:
        if method == "seasonal_naive":
            if period is None:
                raise ValueError("seasonal_naive_forecast requires `period`")
            return seasonal_naive_forecast(series, horizon, period)
        if method not in self._METHODS:
            raise ValueError(f"Unknown forecasting method '{method}'. Available: seasonal_naive, {list(self._METHODS)}")
        return self._METHODS[method](series, horizon, **kwargs)
