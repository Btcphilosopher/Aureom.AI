"""Ties keyframe tracks to concrete animatable objects (transforms, effect params).

This is the glue the diagram in the module docstring of ``keyframes.py``
describes: Keyframe -> Interpolation -> Easing -> Transform -> Render.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from finalcut_engine.core.timebase import Time
from finalcut_engine.motion.keyframes import KeyframeTrack
from finalcut_engine.motion.transforms import Transform


@dataclass
class AnimatedTransform:
    """A :class:`Transform` whose fields are each independently keyframeable.

    Any field left with an empty track keeps :attr:`base`'s static value.
    """

    base: Transform = field(default_factory=Transform)
    position_x: KeyframeTrack = field(default_factory=KeyframeTrack)
    position_y: KeyframeTrack = field(default_factory=KeyframeTrack)
    scale_x: KeyframeTrack = field(default_factory=KeyframeTrack)
    scale_y: KeyframeTrack = field(default_factory=KeyframeTrack)
    rotation: KeyframeTrack = field(default_factory=KeyframeTrack)

    def __post_init__(self) -> None:
        self.position_x.default = self.base.position[0]
        self.position_y.default = self.base.position[1]
        self.scale_x.default = self.base.scale[0]
        self.scale_y.default = self.base.scale[1]
        self.rotation.default = self.base.rotation_degrees

    def at(self, t: Time) -> Transform:
        return Transform(
            position=(float(self.position_x.value_at(t)), float(self.position_y.value_at(t))),
            scale=(float(self.scale_x.value_at(t)), float(self.scale_y.value_at(t))),
            rotation_degrees=float(self.rotation.value_at(t)),
            anchor=self.base.anchor,
            crop=self.base.crop,
        )

    def as_callable(self):
        return self.at


@dataclass
class AnimatedParameters:
    """A generic bag of named keyframe tracks, e.g. for driving an Effect's params."""

    tracks: Dict[str, KeyframeTrack] = field(default_factory=dict)

    def track(self, name: str, default: float = 0.0) -> KeyframeTrack:
        if name not in self.tracks:
            self.tracks[name] = KeyframeTrack(default=default)
        return self.tracks[name]

    def values_at(self, t: Time) -> Dict[str, float]:
        return {name: track.value_at(t) for name, track in self.tracks.items()}
