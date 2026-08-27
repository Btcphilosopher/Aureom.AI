"""Visualisation: engineering dashboard and individual chart builders (Plotly)."""

from __future__ import annotations

from icecream_x.visualisation.crystal_plots import crystal_growth_over_storage, crystal_size_comparison
from icecream_x.visualisation.dashboard import build_dashboard
from icecream_x.visualisation.phase_plots import freezing_curve, phase_composition_stacked
from icecream_x.visualisation.process_plots import formulation_comparison, process_timeline
from icecream_x.visualisation.thermal_plots import temperature_history_from_series, temperature_vs_time

__all__ = [
    "build_dashboard",
    "temperature_vs_time",
    "temperature_history_from_series",
    "freezing_curve",
    "phase_composition_stacked",
    "crystal_growth_over_storage",
    "crystal_size_comparison",
    "process_timeline",
    "formulation_comparison",
]
