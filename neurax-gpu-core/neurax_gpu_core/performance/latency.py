"""
Per-kernel latency tracking.

Consumes completed :class:`~execution.kernel_dispatch.KernelRun` objects and
converts their cycle-domain latency into wall-clock time using the clock
frequency history recorded during the run (so a kernel that straddles a
thermal-throttling event is timed correctly rather than at a single
snapshot frequency).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class KernelLatencyRecord:
    run_id: int
    kernel_name: str
    workload_tag: str
    latency_cycles: int
    latency_seconds: float
    launch_cycle: int
    completion_cycle: int


class LatencyTracker:
    def __init__(self) -> None:
        self.records: List[KernelLatencyRecord] = []
        self._seen_run_ids: set = set()

    def record_completion(self, run, avg_ghz_over_run: float) -> None:
        if run.run_id in self._seen_run_ids or run.completion_cycle is None:
            return
        self._seen_run_ids.add(run.run_id)
        latency_cycles = run.latency_cycles() or 0
        latency_seconds = latency_cycles / (avg_ghz_over_run * 1e9) if avg_ghz_over_run > 0 else 0.0
        self.records.append(KernelLatencyRecord(
            run_id=run.run_id, kernel_name=run.kernel.name, workload_tag=run.kernel.workload_tag,
            latency_cycles=latency_cycles, latency_seconds=latency_seconds,
            launch_cycle=run.launch_cycle, completion_cycle=run.completion_cycle,
        ))

    def stats(self) -> Dict[str, float]:
        if not self.records:
            return {"count": 0, "mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
        latencies_ms = sorted(r.latency_seconds * 1000.0 for r in self.records)
        return {
            "count": len(latencies_ms),
            "mean_ms": statistics.fmean(latencies_ms),
            "p50_ms": latencies_ms[int(0.50 * (len(latencies_ms) - 1))],
            "p95_ms": latencies_ms[int(0.95 * (len(latencies_ms) - 1))],
            "max_ms": latencies_ms[-1],
        }

    def by_workload(self) -> Dict[str, Dict[str, float]]:
        tags = {r.workload_tag for r in self.records}
        out = {}
        for tag in tags:
            vals = sorted(r.latency_seconds * 1000.0 for r in self.records if r.workload_tag == tag)
            out[tag] = {
                "count": len(vals),
                "mean_ms": statistics.fmean(vals) if vals else 0.0,
                "max_ms": vals[-1] if vals else 0.0,
            }
        return out
