"""
Precise rational timebase for the FinalCut Engine.

Modelled conceptually on Core Media's ``CMTime``: every instant and duration is
stored as an integer number of ``ticks`` at a fixed ``timescale``, never as a
floating point number of seconds. Timeline arithmetic (inserts, trims, ripple
edits, transitions) therefore never accumulates rounding error, which matters
enormously once a project has thousands of edits.

Frame-accurate positions are derived from a :class:`FrameRate` via
:class:`Timecode`, including drop-frame timecode for NTSC rates (29.97/59.94).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from functools import total_ordering
from typing import Iterator

#: Highly composite default timescale (divisible by 24, 25, 30, 50, 60, 120,
#: and close NTSC rates after rounding) used unless a clip dictates otherwise.
DEFAULT_TIMESCALE = 600_600  # LCM-friendly for 24/25/30/50/60/23.976/29.97/59.94


@total_ordering
@dataclass(frozen=True)
class Time:
    """An immutable point in time or a duration, expressed in exact ticks."""

    value: int
    timescale: int = DEFAULT_TIMESCALE

    def __post_init__(self) -> None:
        if self.timescale <= 0:
            raise ValueError("timescale must be positive")

    # -- construction -----------------------------------------------------
    @classmethod
    def zero(cls, timescale: int = DEFAULT_TIMESCALE) -> "Time":
        return cls(0, timescale)

    @classmethod
    def from_seconds(cls, seconds: float, timescale: int = DEFAULT_TIMESCALE) -> "Time":
        return cls(round(seconds * timescale), timescale)

    @classmethod
    def from_frames(cls, frames: int, fps: "FrameRate") -> "Time":
        """Exact conversion from a frame count at ``fps`` to ticks."""
        ts = fps.timescale
        return cls(frames * fps.frame_duration_ticks, ts)

    # -- conversion ---------------------------------------------------------
    def seconds(self) -> float:
        return self.value / self.timescale

    def rescaled(self, timescale: int) -> "Time":
        if timescale == self.timescale:
            return self
        frac = Fraction(self.value, self.timescale) * timescale
        # Round to nearest tick, ties to even, matching CMTimeConvertScale default.
        whole = frac.numerator // frac.denominator
        remainder = Fraction(frac.numerator, frac.denominator) - whole
        if remainder * 2 >= 1:
            whole += 1
        return Time(whole, timescale)

    def to_frame_index(self, fps: "FrameRate") -> int:
        """Nearest whole frame number at ``fps`` (floor, matching NLE convention)."""
        t = self.rescaled(fps.timescale)
        return t.value // fps.frame_duration_ticks

    # -- arithmetic ---------------------------------------------------------
    def _common(self, other: "Time") -> tuple[int, int, int]:
        ts = math.lcm(self.timescale, other.timescale)
        a = self.rescaled(ts).value
        b = other.rescaled(ts).value
        return a, b, ts

    def __add__(self, other: "Time") -> "Time":
        a, b, ts = self._common(other)
        return Time(a + b, ts)

    def __sub__(self, other: "Time") -> "Time":
        a, b, ts = self._common(other)
        return Time(a - b, ts)

    def __neg__(self) -> "Time":
        return Time(-self.value, self.timescale)

    def __mul__(self, factor: int) -> "Time":
        return Time(self.value * factor, self.timescale)

    def __truediv__(self, divisor: int) -> "Time":
        return Time(round(self.value / divisor), self.timescale)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Time):
            return NotImplemented
        a, b, _ = self._common(other)
        return a == b

    def __lt__(self, other: "Time") -> bool:
        a, b, _ = self._common(other)
        return a < b

    def __hash__(self) -> int:
        # Normalise to seconds-as-fraction so equal times hash equally
        # regardless of timescale.
        return hash(Fraction(self.value, self.timescale))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Time({self.value}/{self.timescale} = {self.seconds():.6f}s)"


@dataclass(frozen=True)
class TimeRange:
    """A half-open interval ``[start, start+duration)`` on the timeline."""

    start: Time
    duration: Time

    @property
    def end(self) -> Time:
        return self.start + self.duration

    @classmethod
    def from_start_end(cls, start: Time, end: Time) -> "TimeRange":
        return cls(start, end - start)

    def is_empty(self) -> bool:
        return self.duration.value <= 0

    def contains(self, t: Time) -> bool:
        return self.start <= t < self.end

    def overlaps(self, other: "TimeRange") -> bool:
        return self.start < other.end and other.start < self.end

    def intersection(self, other: "TimeRange") -> "TimeRange | None":
        if not self.overlaps(other):
            return None
        start = max(self.start, other.start)
        end = min(self.end, other.end)
        return TimeRange.from_start_end(start, end)

    def shifted(self, delta: Time) -> "TimeRange":
        return TimeRange(self.start + delta, self.duration)

    def __repr__(self) -> str:  # pragma: no cover
        return f"TimeRange({self.start.seconds():.3f}s, +{self.duration.seconds():.3f}s)"


@dataclass(frozen=True)
class FrameRate:
    """A video frame rate expressed as an exact rational number."""

    numerator: int
    denominator: int = 1
    drop_frame: bool = False

    @property
    def fps(self) -> float:
        return self.numerator / self.denominator

    @property
    def timescale(self) -> int:
        """A timescale at which one frame is an exact integer tick count."""
        return self.numerator

    @property
    def frame_duration_ticks(self) -> int:
        return self.denominator

    def frame_duration(self) -> Time:
        return Time(self.denominator, self.numerator)

    def __repr__(self) -> str:  # pragma: no cover
        suffix = " DF" if self.drop_frame else ""
        return f"FrameRate({self.fps:.3f}fps{suffix})"


# Common broadcast/production rates.
FPS_23_976 = FrameRate(24000, 1001)
FPS_24 = FrameRate(24, 1)
FPS_25 = FrameRate(25, 1)
FPS_29_97 = FrameRate(30000, 1001, drop_frame=True)
FPS_30 = FrameRate(30, 1)
FPS_50 = FrameRate(50, 1)
FPS_59_94 = FrameRate(60000, 1001, drop_frame=True)
FPS_60 = FrameRate(60, 1)


@dataclass(frozen=True)
class Timecode:
    """SMPTE timecode, including drop-frame accounting for NTSC rates."""

    hours: int
    minutes: int
    seconds: int
    frames: int
    fps: FrameRate

    @classmethod
    def from_time(cls, t: Time, fps: FrameRate) -> "Timecode":
        frame_index = t.to_frame_index(fps)
        return cls.from_frame_index(frame_index, fps)

    @classmethod
    def from_frame_index(cls, frame_index: int, fps: FrameRate) -> "Timecode":
        nominal = round(fps.fps)  # 30 for 29.97, 60 for 59.94, else exact
        if fps.drop_frame:
            frame_index = _add_drop_frame_offset(frame_index, nominal)
        total_seconds, frames = divmod(frame_index, nominal)
        total_minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(total_minutes, 60)
        return cls(hours % 24, minutes, seconds, frames, fps)

    def to_frame_index(self) -> int:
        nominal = round(self.fps.fps)
        raw = ((self.hours * 60 + self.minutes) * 60 + self.seconds) * nominal + self.frames
        if self.fps.drop_frame:
            raw = _remove_drop_frame_offset(raw, nominal)
        return raw

    def to_time(self) -> Time:
        return Time.from_frames(self.to_frame_index(), self.fps)

    def __str__(self) -> str:
        sep = ";" if self.fps.drop_frame else ":"
        return f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}{sep}{self.frames:02d}"


def _add_drop_frame_offset(frame_index: int, nominal_fps: int) -> int:
    """Map a true elapsed frame count onto the drop-frame numbering sequence.

    Standard SMPTE drop-frame algorithm: frame numbers ``:00`` and ``:01`` are
    skipped at the start of every minute except every 10th minute.
    """
    drop_frames = 2 if nominal_fps == 30 else 4  # 29.97 -> 2, 59.94 -> 4
    frames_per_min_dropped = nominal_fps * 60 - drop_frames
    frames_per_10min_dropped = nominal_fps * 60 * 10 - drop_frames * 9

    d, m = divmod(frame_index, frames_per_10min_dropped)
    if m < drop_frames:
        return frame_index + drop_frames * 9 * d
    return frame_index + drop_frames * 9 * d + drop_frames * ((m - drop_frames) // frames_per_min_dropped)


def _remove_drop_frame_offset(frame_number: int, nominal_fps: int) -> int:
    """Inverse of :func:`_add_drop_frame_offset`."""
    drop_frames = 2 if nominal_fps == 30 else 4
    frames_per_min = nominal_fps * 60
    frames_per_10min = nominal_fps * 60 * 10

    d, m = divmod(frame_number, frames_per_10min)
    if m < drop_frames:
        return frame_number - drop_frames * 9 * d
    return frame_number - drop_frames * 9 * d - drop_frames * ((m - drop_frames) // frames_per_min)


def frame_range(rng: TimeRange, fps: FrameRate) -> Iterator[int]:
    """Yield every whole frame index covered by ``rng`` at ``fps``."""
    start = rng.start.to_frame_index(fps)
    end = rng.end.to_frame_index(fps)
    yield from range(start, end)
