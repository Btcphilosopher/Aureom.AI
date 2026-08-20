"""
Tidal cycle core model: sea level, basin level, hydraulic head and
generation for tidal range (lagoon / basin / barrage) systems.

    sea_level(t) -> basin_level(t) -> head(t) -> flow(t) -> power(t)

Sea level is modelled as a harmonic constituent (the M2 semi-diurnal tide by
default, ``tidal_period_hours=12.42``); real tidal predictions loaded via
:mod:`hydroflux.data.data` can be substituted directly wherever a
``sea_level`` series is expected.
"""

from __future__ import annotations

from typing import Union

import numpy as np
import pandas as pd

from hydroflux.core.config import TidalConfig

ArrayLike = Union[float, np.ndarray]


def sea_level(
    t_hours: ArrayLike,
    mean_level_m: float,
    amplitude_m: float,
    period_hours: float,
    phase_rad: float = 0.0,
) -> ArrayLike:
    """Harmonic sea-level model: mean + amplitude * sin(2*pi*t/T + phase)."""

    t = np.asarray(t_hours, dtype=float)
    return mean_level_m + amplitude_m * np.sin(2 * np.pi * t / period_hours + phase_rad)


def sea_level_series(index: pd.DatetimeIndex, config: TidalConfig) -> pd.Series:
    t_hours = (index - index[0]).total_seconds() / 3600.0
    values = sea_level(t_hours, config.mean_sea_level_m, config.tidal_amplitude_m, config.tidal_period_hours, config.phase_rad)
    return pd.Series(values, index=index, name="sea_level_m")


def basin_area_m2(config: TidalConfig) -> float:
    return config.basin_area_km2 * 1e6


def head_from_levels(sea_level_m: ArrayLike, basin_level_m: ArrayLike) -> ArrayLike:
    """Signed hydraulic head, sea minus basin (positive = flood direction)."""

    return np.asarray(sea_level_m, dtype=float) - np.asarray(basin_level_m, dtype=float)


def flow_to_equalise(head_m: float, basin_area_m2_value: float, dt_hours: float) -> float:
    """Flow (m3/s) required to fully equalise ``head_m`` within one
    timestep given the basin's surface area -- used to cap sluice/turbine
    flow so a single step never overshoots equalisation."""

    dt_s = dt_hours * 3600.0
    return head_m * basin_area_m2_value / dt_s
