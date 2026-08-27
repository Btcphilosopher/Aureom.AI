"""Track/clip-aware waveform caching, built on the core peak-extraction algorithm."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict

import numpy as np

from finalcut_engine.media.waveform import WaveformData, WaveformGenerator


@dataclass
class WaveformCache:
    """Caches generated waveforms by asset id so scrubbing/zooming never re-analyses audio."""

    generator: WaveformGenerator = field(default_factory=WaveformGenerator)
    _cache: Dict[str, WaveformData] = field(default_factory=dict)

    def get_or_generate(
        self, asset_id: str, sample_loader: Callable[[], tuple[np.ndarray, int]], pixels_per_second: int = 50
    ) -> WaveformData:
        key = f"{asset_id}:{pixels_per_second}"
        if key not in self._cache:
            samples, sample_rate = sample_loader()
            self._cache[key] = self.generator.generate(samples, sample_rate, pixels_per_second)
        return self._cache[key]

    def invalidate(self, asset_id: str) -> None:
        for key in list(self._cache):
            if key.startswith(f"{asset_id}:"):
                del self._cache[key]
