"""
Thin driver around :class:`~core.engine.SimulationEngine`: runs the
per-spec timestep loop for a configured number of steps, optionally
printing a live-updating text dashboard and yielding progress.
"""

from __future__ import annotations

from typing import Callable, Iterator, List, Optional

from ..utils.logging import get_logger
from .engine import SimulationEngine, TimestepResult

logger = get_logger("simulation_loop")


def run_simulation(engine: SimulationEngine, num_timesteps: Optional[int] = None,
                    on_timestep: Optional[Callable[[TimestepResult], None]] = None,
                    log_interval: int = 50) -> List[TimestepResult]:
    """Run the engine for ``num_timesteps`` (default: config.simulation.timesteps),
    optionally invoking ``on_timestep`` (e.g. a dashboard render) periodically."""
    n = num_timesteps if num_timesteps is not None else engine.config.simulation.timesteps
    results: List[TimestepResult] = []

    for i in range(n):
        result = engine.step()
        results.append(result)

        if on_timestep is not None:
            on_timestep(result)

        if log_interval and (i + 1) % log_interval == 0:
            logger.info(
                "t=%-5d kernel=%-24s TFLOPS=%6.2f util=%5.1f%% occ=%5.1f%% "
                "BW=%7.1fGB/s hit(L1/L2)=%4.1f%%/%4.1f%% clk=%5.2fGHz "
                "T=%5.1fC P=%6.1fW throttle=%s",
                result.timestep, result.active_kernel, result.tflops,
                result.utilisation_fraction * 100, result.occupancy_achieved * 100,
                result.achieved_bandwidth_gbps, result.l1_hit_rate * 100, result.l2_hit_rate * 100,
                result.freq_ghz, result.max_sm_temp_c, result.total_power_watts,
                "YES" if result.is_throttling else "no",
            )

    return results


def iter_simulation(engine: SimulationEngine, num_timesteps: Optional[int] = None) -> Iterator[TimestepResult]:
    """Generator form, useful for a UI loop that wants to render every step."""
    n = num_timesteps if num_timesteps is not None else engine.config.simulation.timesteps
    for _ in range(n):
        yield engine.step()
