from __future__ import annotations

import numpy as np
import pytest

from finalcut_engine.core.timebase import Time, TimeRange
from finalcut_engine.timeline.clip import Clip


@pytest.fixture
def make_clip():
    def _make(name: str, duration_seconds: float) -> Clip:
        return Clip(asset_id=name, source_range=TimeRange(Time.zero(), Time.from_seconds(duration_seconds)), name=name)

    return _make


@pytest.fixture
def synthetic_frame_loader():
    def _loader(asset_id: str, t: Time) -> np.ndarray:
        colours = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
        base = np.array(colours.get(asset_id, (0.5, 0.5, 0.5)))
        return np.tile(base, (4, 4, 1))

    return _loader
