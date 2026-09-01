"""
Conveyor & material-flow simulation (spec item 18): buffers, queues,
bottlenecks, WIP, starvation and blocking between stages.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class Buffer:
    """A finite-capacity WIP buffer between two production stages."""

    buffer_id: str
    capacity: int
    contents: deque = field(default_factory=deque)

    starved_events: int = 0   # downstream tried to pull, buffer was empty
    blocked_events: int = 0   # upstream tried to push, buffer was full

    @property
    def wip(self) -> int:
        return len(self.contents)

    @property
    def is_full(self) -> bool:
        return self.wip >= self.capacity

    @property
    def is_empty(self) -> bool:
        return self.wip == 0

    def push(self, item) -> bool:
        if self.is_full:
            self.blocked_events += 1
            return False
        self.contents.append(item)
        return True

    def pull(self):
        if self.is_empty:
            self.starved_events += 1
            return None
        return self.contents.popleft()

    @property
    def utilisation_pct(self) -> float:
        return 100.0 * self.wip / self.capacity if self.capacity else 0.0


@dataclass
class ConveyorSegment:
    segment_id: str
    speed_m_per_min: float
    length_m: float

    @property
    def transit_time_s(self) -> float:
        return (self.length_m / max(self.speed_m_per_min, 1e-6)) * 60.0


class MaterialFlowNetwork:
    """A chain of stage -> buffer -> stage links, used by the DES engine to
    detect starvation/blocking as the simulation runs."""

    def __init__(self) -> None:
        self.buffers: dict[str, Buffer] = {}
        self.segments: dict[str, ConveyorSegment] = {}

    def add_buffer(self, buffer_id: str, capacity: int) -> Buffer:
        buf = Buffer(buffer_id=buffer_id, capacity=capacity)
        self.buffers[buffer_id] = buf
        return buf

    def add_segment(self, segment_id: str, speed_m_per_min: float, length_m: float) -> ConveyorSegment:
        seg = ConveyorSegment(segment_id=segment_id, speed_m_per_min=speed_m_per_min, length_m=length_m)
        self.segments[segment_id] = seg
        return seg

    def total_wip(self) -> int:
        return sum(b.wip for b in self.buffers.values())

    def bottleneck_buffer(self) -> Buffer | None:
        if not self.buffers:
            return None
        return max(self.buffers.values(), key=lambda b: b.utilisation_pct)
