"""Profiling infrastructure and automatic bottleneck detection (spec section 24)."""
from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional

from finalcut_engine.render.cache import RenderCache


@dataclass
class PerformanceWarning:
    stage: str
    fraction_of_frame_time: float
    suggestion: str

    def __str__(self) -> str:
        return (
            "PERFORMANCE WARNING\n\n"
            f"{self.stage}:\n"
            f"{self.fraction_of_frame_time * 100:.0f}% of frame render time\n\n"
            f"Suggested optimisation:\n{self.suggestion}"
        )


_SUGGESTIONS = {
    "colour": "Enable GPU colour pipeline.",
    "effects": "Enable GPU effect processing or reduce active filters.",
    "decode": "Switch to proxy media for editing.",
    "transform": "Enable GPU-accelerated transform/warp.",
    "audio": "Reduce active audio plugins or freeze processed tracks.",
}


@dataclass
class PerformanceMonitor:
    """Accumulates named timing samples per rendered frame and reports both
    live counters and, on request, an automatic bottleneck diagnosis.
    """

    dropped_frames: int = 0
    frames_rendered: int = 0
    _stage_totals: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _frame_totals: List[float] = field(default_factory=list)
    _playback_timestamps: List[float] = field(default_factory=list)

    @contextmanager
    def measure(self, stage: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self._stage_totals[stage] += time.perf_counter() - start

    def record_frame_complete(self) -> None:
        self.frames_rendered += 1
        self._playback_timestamps.append(time.perf_counter())
        total = sum(self._stage_totals.values())
        self._frame_totals.append(total)
        self._stage_totals.clear()

    def record_dropped_frame(self) -> None:
        self.dropped_frames += 1

    def playback_fps(self, window: int = 30) -> float:
        recent = self._playback_timestamps[-window:]
        if len(recent) < 2:
            return 0.0
        return (len(recent) - 1) / (recent[-1] - recent[0]) if recent[-1] != recent[0] else 0.0

    def average_frame_time_by_stage(self, window: int = 30) -> Dict[str, float]:
        # Simple accumulation across the whole session; a real implementation
        # would keep a ring buffer of per-frame stage breakdowns.
        return dict(self._stage_totals)

    def cache_hit_rate(self, cache: RenderCache) -> float:
        return cache.stats.hit_rate

    def diagnose(self, last_frame_stage_times: Dict[str, float], threshold: float = 0.3) -> Optional[PerformanceWarning]:
        """Given one frame's per-stage timings, flag whichever stage dominated."""
        total = sum(last_frame_stage_times.values())
        if total <= 0:
            return None
        stage, elapsed = max(last_frame_stage_times.items(), key=lambda kv: kv[1])
        fraction = elapsed / total
        if fraction < threshold:
            return None
        suggestion = _SUGGESTIONS.get(stage, f"Investigate the '{stage}' stage — it dominates frame time.")
        return PerformanceWarning(stage=stage, fraction_of_frame_time=fraction, suggestion=suggestion)
