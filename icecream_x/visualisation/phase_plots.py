"""Phase-diagram / freezing-curve plots."""

from __future__ import annotations

import plotly.graph_objects as go

from icecream_x.formulation.composition import Composition
from icecream_x.thermodynamics.ice_fraction import ice_fraction_curve


def freezing_curve(
    composition: Composition,
    temperature_range_c: tuple[float, float] = (-30.0, 5.0),
    n_points: int = 100,
    title: str = "Freezing Curve",
) -> go.Figure:
    temps_c = [
        temperature_range_c[0] + i * (temperature_range_c[1] - temperature_range_c[0]) / (n_points - 1)
        for i in range(n_points)
    ]
    temps_k = [t + 273.15 for t in temps_c]
    states = ice_fraction_curve(composition, temps_k)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=temps_c, y=[100 * s.ice_mass_fraction for s in states], mode="lines", name="Ice fraction (%)")
    )
    fig.add_trace(
        go.Scatter(
            x=temps_c,
            y=[100 * s.unfrozen_water_mass_fraction for s in states],
            mode="lines",
            name="Unfrozen water (%)",
        )
    )
    fig.update_layout(
        title=title, xaxis_title="Temperature (degC)", yaxis_title="Mass fraction of mix (%)"
    )
    return fig


def phase_composition_stacked(
    composition: Composition,
    temperature_range_c: tuple[float, float] = (-30.0, 5.0),
    n_points: int = 60,
    title: str = "Phase Composition vs. Temperature",
) -> go.Figure:
    temps_c = [
        temperature_range_c[0] + i * (temperature_range_c[1] - temperature_range_c[0]) / (n_points - 1)
        for i in range(n_points)
    ]
    temps_k = [t + 273.15 for t in temps_c]
    states = ice_fraction_curve(composition, temps_k)

    fig = go.Figure()
    series = {
        "Ice": [100 * s.ice_mass_fraction for s in states],
        "Unfrozen water": [100 * s.unfrozen_water_mass_fraction for s in states],
        "Fat": [100 * s.fat_mass_fraction for s in states],
        "Solids-non-fat": [100 * s.solids_non_fat_mass_fraction for s in states],
    }
    for name, values in series.items():
        fig.add_trace(go.Scatter(x=temps_c, y=values, mode="lines", name=name, stackgroup="one"))
    fig.update_layout(title=title, xaxis_title="Temperature (degC)", yaxis_title="Mass fraction (%)")
    return fig
