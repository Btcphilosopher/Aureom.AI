"""The ICECREAM-X engineering dashboard.

A single multi-panel Plotly figure covering the panels called for in the
spec: TEMPERATURE, ICE FRACTION, CRYSTAL SIZE, OVERRUN, VISCOSITY,
ENERGY, QUALITY. Reads directly from a
:class:`~icecream_x.core.simulation.StateLog` DataFrame (see
:func:`icecream_x.core.simulation.run_storage_simulation`), so any
timestep-logged simulation run can be visualised with one call. Panels
whose underlying column is absent from the DataFrame (e.g. viscosity,
which is not part of the default state summary) are simply left empty
rather than raising, so the dashboard degrades gracefully.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

_PANELS = [
    ("Temperature (degC)", "temperature_c"),
    ("Ice Fraction (%)", "ice_fraction_pct"),
    ("Crystal Size (um)", "microstructure.mean_ice_crystal_diameter_um"),
    ("Overrun (%)", "overrun_pct"),
    ("Viscosity (Pa s)", "viscosity_pa_s"),
    ("Cumulative Energy (kWh)", "cumulative_energy_kwh"),
    ("Quality Score", "quality_score"),
]


def build_dashboard(state_log_df: pd.DataFrame, title: str = "ICECREAM-X Dashboard") -> go.Figure:
    time_col = "timestamp_s" if "timestamp_s" in state_log_df.columns else "elapsed_time_s"
    time_h = state_log_df[time_col] / 3600.0 if time_col in state_log_df.columns else range(len(state_log_df))

    n = len(_PANELS)
    fig = make_subplots(rows=n, cols=1, shared_xaxes=True, subplot_titles=[p[0] for p in _PANELS])

    for i, (name, column) in enumerate(_PANELS, start=1):
        if column in state_log_df.columns:
            fig.add_trace(
                go.Scatter(x=time_h, y=state_log_df[column], mode="lines", name=name, showlegend=False),
                row=i,
                col=1,
            )

    fig.update_layout(title=title, height=220 * n)
    fig.update_xaxes(title_text="Time (h)", row=n, col=1)
    return fig
