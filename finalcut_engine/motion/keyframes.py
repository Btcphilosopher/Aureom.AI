"""Keyframes, interpolation, and easing — the base of the Motion system.

```
Keyframe -> Interpolation -> Easing -> Transform -> Render
```

A :class:`KeyframeTrack` animates a single scalar (or fixed-length vector)
value over time; :mod:`finalcut_engine.motion.animation` composes several
tracks into an animated :class:`~finalcut_engine.motion.transforms.Transform`
or effect parameter.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Sequence, Union

import numpy as np

from finalcut_engine.core.timebase import Time

Value = Union[float, Sequence[float]]


class Easing(str, Enum):
    LINEAR = "linear"
    EASE_IN = "ease_in"
    EASE_OUT = "ease_out"
    EASE_IN_OUT = "ease_in_out"
    HOLD = "hold"  # step function: snaps to this keyframe's value until the next


def _ease(t: float, easing: Easing) -> float:
    t = min(max(t, 0.0), 1.0)
    if easing == Easing.LINEAR:
        return t
    if easing == Easing.EASE_IN:
        return t * t
    if easing == Easing.EASE_OUT:
        return 1 - (1 - t) * (1 - t)
    if easing == Easing.EASE_IN_OUT:
        return t * t * (3 - 2 * t)  # smoothstep
    if easing == Easing.HOLD:
        return 0.0
    raise ValueError(f"unknown easing {easing}")


@dataclass(frozen=True)
class Keyframe:
    time: Time
    value: Value
    easing: Easing = Easing.EASE_IN_OUT  # easing applied to the segment *starting* here


@dataclass
class KeyframeTrack:
    keyframes: List[Keyframe] = field(default_factory=list)
    default: Value = 0.0

    def add(self, time: Time, value: Value, easing: Easing = Easing.EASE_IN_OUT) -> None:
        self.keyframes = [k for k in self.keyframes if k.time != time]
        self.keyframes.append(Keyframe(time, value, easing))
        self.keyframes.sort(key=lambda k: k.time.seconds())

    def remove_at(self, time: Time) -> None:
        self.keyframes = [k for k in self.keyframes if k.time != time]

    def is_animated(self) -> bool:
        return len(self.keyframes) > 0

    def value_at(self, t: Time) -> Value:
        if not self.keyframes:
            return self.default
        times = [k.time.seconds() for k in self.keyframes]
        ts = t.seconds()
        idx = bisect.bisect_right(times, ts)

        if idx == 0:
            return self.keyframes[0].value
        if idx >= len(self.keyframes):
            return self.keyframes[-1].value

        a, b = self.keyframes[idx - 1], self.keyframes[idx]
        span = b.time.seconds() - a.time.seconds()
        frac = 0.0 if span <= 0 else (ts - a.time.seconds()) / span
        eased = _ease(frac, a.easing)
        if a.easing == Easing.HOLD:
            return a.value
        return _lerp(a.value, b.value, eased)

    def as_callable(self):
        """Adapter for APIs (colour pipeline stages, effect params) expecting
        a plain ``(Time) -> value`` callable rather than a track object."""
        return self.value_at


def _lerp(a: Value, b: Value, frac: float) -> Value:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a + (b - a) * frac
    a_arr, b_arr = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    result = a_arr + (b_arr - a_arr) * frac
    return tuple(result.tolist())
