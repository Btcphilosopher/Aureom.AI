"""Non-destructive angle-switch edit list for a multicam clip.

Cuts are stored as a sorted list of (offset, angle) rather than baked into
separate timeline clips, so switching angles during playback/preview never
touches the primary storyline; only committing a multicam clip's edit (a
render/export-time operation) needs to flatten it.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import List, Tuple

from finalcut_engine.core.timebase import Time


@dataclass
class AngleSwitcher:
    default_angle: str
    #: Sorted (offset, angle_name) cut points, offsets relative to clip start.
    cuts: List[Tuple[Time, str]] = field(default_factory=list)

    def switch_at(self, offset: Time, angle_name: str) -> None:
        self.cuts = [c for c in self.cuts if c[0] != offset]
        bisect.insort(self.cuts, (offset, angle_name), key=lambda c: c[0].seconds())

    def remove_cut_at(self, offset: Time) -> None:
        self.cuts = [c for c in self.cuts if c[0] != offset]

    def active_angle_at(self, offset: Time) -> str:
        active = self.default_angle
        for cut_offset, angle in self.cuts:
            if cut_offset <= offset:
                active = angle
            else:
                break
        return active

    def segments(self, total_duration: Time) -> List[Tuple[Time, Time, str]]:
        """Flatten into (start, end, angle) segments covering ``[0, total_duration)``."""
        boundaries = [Time.zero()] + [c[0] for c in self.cuts] + [total_duration]
        angles = [self.default_angle] + [c[1] for c in self.cuts]
        return [(boundaries[i], boundaries[i + 1], angles[i]) for i in range(len(angles)) if boundaries[i] < boundaries[i + 1]]
