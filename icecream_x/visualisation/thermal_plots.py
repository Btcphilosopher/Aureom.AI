"""Temperature / thermal-history plots."""

from __future__ import annotations

import plotly.graph_objects as go

from icecream_x.core.state import ProductState


def temperature_vs_time(trajectory: list[ProductState], title: str = "Temperature vs. Time") -> go.Figure:
    times = [s.elapsed_time_s for s in trajectory]
    temps = [s.temperature_c for s in trajectory]
    fig = go.Figure(go.Scatter(x=times, y=temps, mode="lines", name="Temperature"))
    fig.update_layout(title=title, xaxis_title="Time (s)", yaxis_title="Temperature (degC)")
    return fig


def temperature_history_from_series(
    series_s_c: list[tuple[float, float]], title: str = "Storage Temperature History"
) -> go.Figure:
    times = [t / 3600.0 for t, _ in series_s_c]
    temps = [c for _, c in series_s_c]
    fig = go.Figure(go.Scatter(x=times, y=temps, mode="lines", name="Product Temperature"))
    fig.update_layout(title=title, xaxis_title="Time (h)", yaxis_title="Temperature (degC)")
    return fig
