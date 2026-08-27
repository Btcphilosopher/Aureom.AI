"""Process-timeline and formulation-comparison plots."""

from __future__ import annotations

import plotly.graph_objects as go

from icecream_x.core.engine import PipelineResult


def process_timeline(pipeline_result: PipelineResult, title: str = "Process Timeline") -> go.Figure:
    summaries = pipeline_result.stage_summaries()
    stages = [s["stage"] for s in summaries]
    temps = [s["temperature_c"] for s in summaries]
    fig = go.Figure(go.Scatter(x=stages, y=temps, mode="lines+markers", name="Temperature"))
    fig.update_layout(title=title, xaxis_title="Process stage", yaxis_title="Temperature (degC)")
    return fig


def formulation_comparison(recipes_summary: dict[str, dict[str, float]], metric: str, title: str | None = None) -> go.Figure:
    """Bar chart comparing one metric (e.g. 'cost_per_kg', 'quality_score') across recipes."""
    names = list(recipes_summary.keys())
    values = [recipes_summary[name].get(metric, 0.0) for name in names]
    fig = go.Figure(go.Bar(x=names, y=values))
    fig.update_layout(title=title or f"Formulation Comparison: {metric}", xaxis_title="Recipe", yaxis_title=metric)
    return fig
