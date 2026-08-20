"""
Hydrological flow model: time-series river inflow, synthetic generation,
resampling and simple scenario perturbation (drought / flood).

Real observed/forecast flow data should be loaded through
:mod:`hydroflux.data.data` and wrapped in a
:class:`hydroflux.core.timeseries.ResourceTimeSeries`; the helpers here are
for generating reproducible synthetic inputs (demonstrations, Monte Carlo
ensembles, sensitivity studies) and for basic scenario transforms.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from hydroflux.core.timeseries import generate_synthetic_series


def synthetic_river_inflow(
    index: pd.DatetimeIndex,
    mean_flow_m3s: float,
    seasonal_amplitude_m3s: float = 0.0,
    daily_amplitude_m3s: float = 0.0,
    noise_std_m3s: float = 0.0,
    seed: Optional[int] = None,
    minimum_flow_m3s: float = 0.0,
) -> pd.Series:
    """A reproducible synthetic river inflow series with an annual seasonal
    cycle, an optional diurnal component (snowmelt/glacial rivers) and
    autocorrelated-looking noise via an AR(1) filter."""

    rng = np.random.default_rng(seed)
    t_hours = (index - index[0]).total_seconds() / 3600.0
    annual = seasonal_amplitude_m3s * np.sin(2 * np.pi * t_hours / (24 * 365.25) - np.pi / 2)
    diurnal = daily_amplitude_m3s * np.sin(2 * np.pi * t_hours / 24.0)

    white_noise = rng.normal(0.0, noise_std_m3s, size=len(index))
    phi = 0.85
    noise = np.zeros_like(white_noise)
    for i in range(1, len(noise)):
        noise[i] = phi * noise[i - 1] + white_noise[i]

    flow = mean_flow_m3s + annual + diurnal + noise
    flow = np.maximum(flow, minimum_flow_m3s)
    return pd.Series(flow, index=index, name="flow_m3s")


def flow_duration_curve(flow: pd.Series) -> pd.DataFrame:
    """Return the flow-duration curve: exceedance probability vs flow."""

    sorted_flow = np.sort(flow.values)[::-1]
    rank = np.arange(1, len(sorted_flow) + 1)
    exceedance_pct = 100.0 * rank / (len(sorted_flow) + 1)
    return pd.DataFrame({"exceedance_pct": exceedance_pct, "flow_m3s": sorted_flow})


def apply_flow_duration_scaling(flow: pd.Series, multiplier: float, minimum_flow_m3s: float = 0.0) -> pd.Series:
    """Scale a flow series uniformly (e.g. for high-flow / low-flow
    scenarios) while respecting a floor."""

    return np.maximum(flow * multiplier, minimum_flow_m3s)


def drought_scenario_flow(flow: pd.Series, severity: float = 0.5, minimum_flow_m3s: float = 0.0) -> pd.Series:
    """Apply a drought scenario: flow scaled down, low flows compressed
    further than high flows (droughts disproportionately remove peaks)."""

    median = np.median(flow.values)
    scaled = median + (flow - median) * (1 - severity) * 0.5
    scaled = scaled * (1 - severity * 0.5)
    return np.maximum(scaled, minimum_flow_m3s)


def flood_scenario_flow(flow: pd.Series, severity: float = 0.5) -> pd.Series:
    """Apply a flood scenario: peaks amplified more than base flow."""

    median = np.median(flow.values)
    amplified = median + (flow - median) * (1 + severity * 2)
    return np.maximum(amplified, 0.0)
