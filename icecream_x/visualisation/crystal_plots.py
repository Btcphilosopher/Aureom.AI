"""Ice-crystal growth plots."""

from __future__ import annotations

import plotly.graph_objects as go


def crystal_growth_over_storage(
    diameter_history_um: list[tuple[float, float]], title: str = "Ice-Crystal Growth During Storage"
) -> go.Figure:
    days = [t / 86400.0 for t, _ in diameter_history_um]
    diameters = [d for _, d in diameter_history_um]
    fig = go.Figure(go.Scatter(x=days, y=diameters, mode="lines", name="Mean crystal diameter"))
    fig.update_layout(title=title, xaxis_title="Time (days)", yaxis_title="Mean ice-crystal diameter (um)")
    return fig


def crystal_size_comparison(scenarios: dict[str, float], title: str = "Crystal Size Comparison") -> go.Figure:
    fig = go.Figure(go.Bar(x=list(scenarios.keys()), y=list(scenarios.values())))
    fig.update_layout(title=title, xaxis_title="Scenario", yaxis_title="Mean ice-crystal diameter (um)")
    return fig
