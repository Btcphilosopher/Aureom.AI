"""
Graphical die/telemetry visualisation.

All plotting is optional -- matplotlib (and, for the timeline plot,
nothing beyond it) is imported lazily so the rest of the simulator works
fully headless. Every function returns ``None`` (and logs a warning)
instead of raising if the plotting backend isn't installed, so callers
never need their own try/except around these.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from ..utils.logging import get_logger

if TYPE_CHECKING:
    from ..architecture.chip_layout import ChipLayout
    from ..core.engine import SimulationEngine

logger = get_logger("gpu_visualizer")


def _get_matplotlib():
    try:
        import matplotlib
        matplotlib.use("Agg", force=False)
        import matplotlib.pyplot as plt
        return plt
    except ImportError:
        logger.warning("matplotlib is not installed; visualisation is disabled.")
        return None


class GPUVisualizer:
    """Namespace of die/telemetry plotting helpers, each returning a
    matplotlib Figure (or None if matplotlib is unavailable)."""

    @staticmethod
    def plot_die_layout(chip_layout: "ChipLayout", sm_values: List[float], title: str,
                         cmap: str = "inferno", value_label: str = "value"):
        plt = _get_matplotlib()
        if plt is None:
            return None

        cols, rows = chip_layout.grid_shape()
        grid = [[float("nan")] * cols for _ in range(rows)]
        for sm_id, placement in chip_layout.placements.items():
            v = sm_values[sm_id] if sm_id < len(sm_values) else float("nan")
            grid[placement.y][placement.x] = v

        fig, ax = plt.subplots(figsize=(max(4, cols * 0.5), max(3, rows * 0.5)))
        im = ax.imshow(grid, cmap=cmap, origin="upper")
        ax.set_title(title)
        ax.set_xlabel("die X")
        ax.set_ylabel("die Y")
        fig.colorbar(im, ax=ax, label=value_label)
        fig.tight_layout()
        return fig

    @staticmethod
    def plot_thermal_heatmap(engine: "SimulationEngine"):
        sm_temps = engine.heat_model.sm_temps_c
        return GPUVisualizer.plot_die_layout(
            engine.gpu.chip_layout, sm_temps, title="Die Thermal Heatmap", cmap="inferno",
            value_label="Temperature (C)",
        )

    @staticmethod
    def plot_occupancy_map(engine: "SimulationEngine"):
        occ = [sm.occupancy() for sm in engine.gpu.sms]
        return GPUVisualizer.plot_die_layout(
            engine.gpu.chip_layout, occ, title="SM Occupancy Map", cmap="viridis",
            value_label="Occupancy",
        )

    @staticmethod
    def plot_timeseries(engine: "SimulationEngine", metrics: Optional[List[str]] = None):
        plt = _get_matplotlib()
        if plt is None:
            return None
        metrics = metrics or ["tflops", "utilisation_fraction", "achieved_bandwidth_gbps",
                               "max_sm_temp_c", "total_power_watts"]
        rows = engine.metrics_log.rows()
        if not rows:
            logger.warning("No timestep history to plot.")
            return None

        timesteps = [r["timestep"] for r in rows]
        fig, axes = plt.subplots(len(metrics), 1, figsize=(10, 2.2 * len(metrics)), sharex=True)
        if len(metrics) == 1:
            axes = [axes]
        for ax, metric in zip(axes, metrics):
            values = [r.get(metric, 0.0) for r in rows]
            ax.plot(timesteps, values, linewidth=1.2)
            ax.set_ylabel(metric)
            ax.grid(alpha=0.25)
        axes[-1].set_xlabel("timestep")
        fig.suptitle(f"{engine.gpu.config.name} -- telemetry over time")
        fig.tight_layout()
        return fig

    @staticmethod
    def plot_warp_execution_timeline(engine: "SimulationEngine", window: int = 200):
        """Approximate warp-issue activity over the most recent micro-cycle
        window, sampled from the last few timesteps' occupancy history."""
        plt = _get_matplotlib()
        if plt is None:
            return None
        rows = engine.metrics_log.rows()[-window:]
        if not rows:
            return None
        fig, ax = plt.subplots(figsize=(10, 3))
        ax.plot([r["timestep"] for r in rows], [r.get("occupancy_achieved", 0.0) for r in rows],
                label="occupancy", linewidth=1.2)
        ax.plot([r["timestep"] for r in rows], [r.get("simt_efficiency", 0.0) for r in rows],
                label="SIMT efficiency", linewidth=1.2, linestyle="--")
        ax.set_ylim(0, 1.05)
        ax.set_xlabel("timestep")
        ax.set_ylabel("fraction")
        ax.set_title("Warp execution activity")
        ax.legend()
        ax.grid(alpha=0.25)
        fig.tight_layout()
        return fig
