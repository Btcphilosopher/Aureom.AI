"""A multicam clip: several synchronised camera angles edited as one clip."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict

from finalcut_engine.core.timebase import Time, TimeRange
from finalcut_engine.multicam.angle_switching import AngleSwitcher
from finalcut_engine.multicam.camera_angle import CameraAngle
from finalcut_engine.timeline.clip import Clip, TimelineItem
from finalcut_engine.timeline.roles import DEFAULT_VIDEO_ROLE, Role
from finalcut_engine.timeline.storyline import Storyline


@dataclass
class MulticamClip(TimelineItem):
    name: str
    angles: Dict[str, CameraAngle]
    switcher: AngleSwitcher
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def duration(self) -> Time:
        """The overlapping window all angles cover once synchronised."""
        if not self.angles:
            return Time.zero()
        starts = [a.sync_offset for a in self.angles.values()]
        ends = [a.sync_offset + a.source_range.duration for a in self.angles.values()]
        start, end = max(starts), min(ends)
        if end.seconds() <= start.seconds():
            return Time.zero()
        return end - start

    def switch_angle(self, offset: Time, angle_name: str) -> None:
        if angle_name not in self.angles:
            raise KeyError(f"unknown angle {angle_name!r}")
        self.switcher.switch_at(offset, angle_name)

    def flatten(self, role: Role = DEFAULT_VIDEO_ROLE) -> Storyline:
        """Bake the angle-switch edit decision list into concrete clips.

        This is what render/export actually consumes — the multicam clip's
        live angle list stays intact on the timeline (non-destructive) until
        the user explicitly commits it.
        """
        storyline = Storyline(name=f"{self.name} (flattened)")
        window_start = max(a.sync_offset for a in self.angles.values())
        for seg_start, seg_end, angle_name in self.switcher.segments(self.duration):
            angle = self.angles[angle_name]
            # Map the multicam-local segment back into the angle's own source range.
            source_start = angle.source_range.start + (window_start + seg_start - angle.sync_offset)
            source_range = TimeRange(source_start, seg_end - seg_start)
            storyline.append_clip(Clip(asset_id=angle.asset_id, source_range=source_range, name=f"{self.name}:{angle_name}", role=role))
        return storyline
