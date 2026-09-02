"""
Spectral graph engine (SilicaFlux spec item 21).

Produces machine-readable (JSON-serialisable) series for the seven
required graphs, each spanning 280 -> 2500 nm with UV/VISIBLE/NIR band
boundaries attached as metadata for highlighting. Rendering to actual
image files is optional and degrades gracefully if matplotlib is not
installed (mirroring the rest of this package's "no hard dependency on
plotting libraries" stance).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import SPECTRAL_BANDS_NM
from .pipeline import PipelineResult

GRAPH_NAMES = [
    "SPECTRAL_IRRADIANCE_GRAPH", "ABSORPTION_GRAPH", "EQE_GRAPH", "IQE_GRAPH",
    "REFLECTION_GRAPH", "TRANSMISSION_GRAPH", "POWER_CONTRIBUTION_GRAPH",
]


@dataclass
class GraphSeries:
    name: str
    x_label: str
    y_label: str
    wavelength_nm: np.ndarray
    values: np.ndarray
    bands: dict[str, tuple[float, float]]


def build_graph_data(result: PipelineResult) -> dict[str, GraphSeries]:
    wl = result.spectrum.wavelength_nm
    bands = {k: v for k, v in SPECTRAL_BANDS_NM.items() if k in ("UV", "VISIBLE", "NIR")}

    return {
        "SPECTRAL_IRRADIANCE_GRAPH": GraphSeries(
            "SPECTRAL_IRRADIANCE_GRAPH", "wavelength_nm", "spectral_irradiance_w_m2_nm",
            wl, result.spectrum.spectral_irradiance_w_m2_nm, bands,
        ),
        "ABSORPTION_GRAPH": GraphSeries(
            "ABSORPTION_GRAPH", "wavelength_nm", "absorption_fraction",
            wl, result.spectral_response.optical_absorption_fraction, bands,
        ),
        "EQE_GRAPH": GraphSeries("EQE_GRAPH", "wavelength_nm", "eqe", wl, result.spectral_response.eqe, bands),
        "IQE_GRAPH": GraphSeries("IQE_GRAPH", "wavelength_nm", "iqe", wl, result.spectral_response.iqe, bands),
        "REFLECTION_GRAPH": GraphSeries("REFLECTION_GRAPH", "wavelength_nm", "reflection_fraction", wl, result.reflection, bands),
        "TRANSMISSION_GRAPH": GraphSeries(
            "TRANSMISSION_GRAPH", "wavelength_nm", "transmission_fraction", wl, result.optical_transmission, bands
        ),
        "POWER_CONTRIBUTION_GRAPH": GraphSeries(
            "POWER_CONTRIBUTION_GRAPH", "wavelength_nm", "power_contribution_w_m2_nm",
            wl, result.spectral_response.power_contribution_w_m2_nm, bands,
        ),
    }


def render_graphs_matplotlib(graph_data: dict[str, GraphSeries], out_dir: str) -> list[str]:
    """
    Optional PNG rendering with UV/VISIBLE/NIR bands shaded. Returns the
    list of file paths written; returns an empty list (rather than raising)
    if matplotlib is not installed.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []

    import os

    os.makedirs(out_dir, exist_ok=True)
    band_colors = {"UV": "#8e5cf7", "VISIBLE": "#f7d65c", "NIR": "#c0392b"}

    written = []
    for name, series in graph_data.items():
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for band_name, (low, high) in series.bands.items():
            ax.axvspan(low, high, color=band_colors.get(band_name, "#888888"), alpha=0.12, label=band_name)
        ax.plot(series.wavelength_nm, series.values, color="#1f77b4", linewidth=1.2)
        ax.set_xlabel(series.x_label)
        ax.set_ylabel(series.y_label)
        ax.set_title(name)
        ax.set_xlim(series.wavelength_nm.min(), series.wavelength_nm.max())
        ax.legend(loc="upper right", fontsize=8)
        fig.tight_layout()

        path = os.path.join(out_dir, f"{name.lower()}.png")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        written.append(path)

    return written
