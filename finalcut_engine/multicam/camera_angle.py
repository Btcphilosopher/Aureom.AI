"""A single camera (or audio recorder) feed inside a multicam clip."""
from __future__ import annotations

from dataclasses import dataclass

from finalcut_engine.core.timebase import Time, TimeRange


@dataclass
class CameraAngle:
    name: str  # e.g. "Camera A"
    asset_id: str
    sync_offset: Time  # this angle's start, relative to the group's earliest angle
    source_range: TimeRange  # the portion of the source asset available for this angle

    def range_in_group_time(self) -> TimeRange:
        return TimeRange(self.sync_offset, self.source_range.duration)
