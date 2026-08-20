"""
Text-mode engineering dashboard.

Renders a dense, NVIDIA/AMD-internal-tooling-style status block from a
:class:`~core.engine.SimulationEngine`'s live/most-recent state, and
exposes a pandas-DataFrame view of the full run history for downstream
analysis or plotting. Falls back gracefully (prints via the logger instead
of crashing) when pandas isn't installed, since it's an optional dependency
per the project's tech requirements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from ..utils.logging import get_logger

if TYPE_CHECKING:
    from ..core.engine import SimulationEngine, TimestepResult

logger = get_logger("dashboard")

_BAR_WIDTH = 24


def _bar(fraction: float, width: int = _BAR_WIDTH) -> str:
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    return "[" + "#" * filled + "-" * (width - filled) + f"] {fraction * 100:5.1f}%"


class Dashboard:
    def __init__(self, engine: "SimulationEngine"):
        self.engine = engine

    def render_frame(self, result: Optional["TimestepResult"] = None) -> str:
        r = result or (self.engine.history[-1] if self.engine.history else None)
        if r is None:
            return "(no simulation data yet)"

        gpu = self.engine.gpu
        lines = [
            "=" * 78,
            f" NEURAX GPU CORE  |  {gpu.config.name}  |  t={r.timestep}  |  kernel={r.active_kernel}",
            "=" * 78,
            f" Clock        {r.freq_ghz:6.2f} GHz @ {r.voltage_v:5.3f} V"
            f"{'   [THROTTLING]' if r.is_throttling else ''}"
            f"{'   [POWER-CAPPED]' if r.is_power_capped else ''}",
            f" Throughput   {r.tflops:8.2f} TFLOPS   {r.gips:8.2f} GIPS   IPC/SM={r.ipc_per_sm:5.2f}",
            f" Utilisation  {_bar(r.utilisation_fraction)}",
            f" Occupancy    {_bar(r.occupancy_achieved)}  (theoretical ceiling {r.occupancy_theoretical * 100:4.1f}%)",
            f" SIMT eff.    {_bar(r.simt_efficiency)}",
            f" Bandwidth    {r.achieved_bandwidth_gbps:8.1f} GB/s   " + _bar(r.bandwidth_utilisation),
            f" Cache        L1 hit {r.l1_hit_rate * 100:5.1f}%   L2 hit {r.l2_hit_rate * 100:5.1f}%",
            f" Power        {r.total_power_watts:7.1f} W   ({r.gflops_per_watt:6.1f} GFLOPS/W)",
            f" Thermal      die {r.die_temp_c:5.1f}C   hotspot {r.max_sm_temp_c:5.1f}C"
            f"   (throttle limit {gpu.config.thermal.throttle_temp_c:.0f}C)",
            f" Dispatch     queue depth = {r.queue_depth} blocks waiting",
            "-" * 78,
        ]
        return "\n".join(lines)

    def render_summary(self) -> str:
        s = self.engine.summary()
        if not s:
            return "(no simulation data yet)"
        lat = s.get("kernel_latency", {})
        lines = [
            "=" * 78,
            f" RUN SUMMARY  |  {self.engine.gpu.config.name}  |  {s['timesteps_run']} timesteps",
            "=" * 78,
            f" Avg TFLOPS         {s['avg_tflops']:8.2f}    Peak TFLOPS   {s['peak_tflops']:8.2f}",
            f" Avg Utilisation    {s['avg_utilisation'] * 100:7.1f}%",
            f" Avg Bandwidth      {s['avg_bandwidth_gbps']:8.1f} GB/s",
            f" Avg Occupancy      {s['avg_occupancy'] * 100:7.1f}%",
            f" Avg Power          {s['avg_power_watts']:8.1f} W",
            f" Avg Efficiency     {s['avg_gflops_per_watt']:8.1f} GFLOPS/W",
            f" Max Die Temp       {s['max_die_temp_c']:8.1f} C",
            f" Throttle Events    {s['throttle_events']}",
            f" Kernel Latency     mean={lat.get('mean_ms', 0):.3f}ms  p95={lat.get('p95_ms', 0):.3f}ms  "
            f"max={lat.get('max_ms', 0):.3f}ms  (n={lat.get('count', 0)})",
            "=" * 78,
        ]
        return "\n".join(lines)

    def render_recommendations(self) -> str:
        lines = [" AI OPTIMISATION RECOMMENDATIONS", "-" * 78]
        sched_recs = self.engine.scheduling_optimizer.recommendations[-5:]
        mem_recs = self.engine.memory_optimizer.recommendations[-5:]
        if not sched_recs and not mem_recs:
            lines.append(" (none yet -- run more timesteps)")
        for rec in sched_recs:
            tag = "APPLIED" if rec.applied else "advisory"
            lines.append(f" [scheduling/{tag}] t={rec.timestep}: {rec.reason}")
        for rec in mem_recs:
            lines.append(f" [memory/{rec.severity}] t={rec.timestep}: {rec.message}")
        return "\n".join(lines)

    def to_dataframe(self):
        return self.engine.metrics_log.to_dataframe()

    def print_frame(self, result: Optional["TimestepResult"] = None) -> None:
        print(self.render_frame(result))

    def print_summary(self) -> None:
        print(self.render_summary())
        print(self.render_recommendations())
