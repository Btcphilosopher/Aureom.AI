"""Chart styling: Anglo-futurist dark theme with a CVD-validated data palette.

Surfaces and chrome use the SilicaFlux identity (near-black, gold, cyan,
Bebas Neue / DM Mono where installed).  DATA series use the validated dark
categorical palette (dataviz reference instance, re-validated on surface
#111113: all six checks pass) -- brand gold/cyan are reserved for chrome and
the single "recommended" highlight, never as series colours.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE = "#111113"
PANEL = "#17171a"
GRID = "#2a2a2e"
TEXT = "#f0efec"
TEXT2 = "#c3c2b7"
MUTED = "#8a897f"
GOLD = "#C9A84C"
CYAN = "#00E5FF"
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
NEUTRAL = "#6b6a64"

PROV_MARKER = {"THEORETICAL": "", "ANALYTICAL": "o", "PY_SIMULATION": "s", "RTL_SIMULATION": "D", "MEASURED": "*"}


def apply() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": TEXT2, "axes.titlecolor": TEXT,
        "xtick.color": MUTED, "ytick.color": MUTED, "text.color": TEXT,
        "grid.color": GRID, "grid.linewidth": 0.6, "axes.grid": True, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False,
        "font.family": ["DejaVu Sans Mono", "monospace"], "font.size": 9,
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.titlepad": 17,
        "legend.frameon": False, "legend.fontsize": 8, "lines.linewidth": 2.0,
        "lines.markersize": 7, "axes.prop_cycle": matplotlib.cycler(color=SERIES),
    })


def save(fig, path_base: str) -> list[str]:
    out = []
    for ext in ("png", "svg"):
        p = f"{path_base}.{ext}"
        fig.savefig(p, dpi=170 if ext == "png" else None, bbox_inches="tight")
        out.append(p)
    plt.close(fig)
    return out
