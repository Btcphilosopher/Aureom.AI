"""
The Spatial World Model: the single, persistent, queryable representation of
everything XR-OS currently believes exists in and around the user's space --
hardware, physical geometry, people, and virtual content alike.

Every other subsystem reads from and writes into this model rather than
keeping its own private copy of "what's out there": the tracking engine
updates the headset/hands/controllers, SLAM updates walls/floors/tables, CV
updates detected objects/people, and the scene graph/apps place virtual
content -- all as ``SpatialObject`` records in one place.
"""

from __future__ import annotations

import threading
from typing import Callable, Iterable

from pydantic import BaseModel, Field

from xr_os.core.events import EventBus
from xr_os.core.math3d import Vector3
from xr_os.core.spatial_object import SpatialObject, SpatialObjectType

# Topics published on the world model's event bus.
TOPIC_OBJECT_ADDED = "world.object.added"
TOPIC_OBJECT_UPDATED = "world.object.updated"
TOPIC_OBJECT_REMOVED = "world.object.removed"


class Zone(BaseModel):
    """A named spatial region (e.g. a room, a play-space boundary, a no-go area)."""

    id: str
    label: str
    center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    half_extents: tuple[float, float, float] = (1.0, 1.0, 1.0)
    metadata: dict = Field(default_factory=dict)

    def contains(self, point: tuple[float, float, float]) -> bool:
        cx, cy, cz = self.center
        hx, hy, hz = self.half_extents
        px, py, pz = point
        return abs(px - cx) <= hx and abs(py - cy) <= hy and abs(pz - cz) <= hz


class SpatialWorldModel:
    """Thread-safe in-memory registry of every ``SpatialObject`` XR-OS tracks."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._objects: dict[str, SpatialObject] = {}
        self._zones: dict[str, Zone] = {}
        self._lock = threading.RLock()
        self.events = event_bus or EventBus()

    # -- object CRUD -------------------------------------------------

    def add(self, obj: SpatialObject) -> SpatialObject:
        with self._lock:
            self._objects[obj.id] = obj
        self.events.publish(TOPIC_OBJECT_ADDED, obj)
        return obj

    def update(self, object_id: str, **fields) -> SpatialObject:
        with self._lock:
            obj = self._objects[object_id]
            for key, value in fields.items():
                setattr(obj, key, value)
            obj.touch()
        self.events.publish(TOPIC_OBJECT_UPDATED, obj)
        return obj

    def upsert(self, obj: SpatialObject) -> SpatialObject:
        """Add if new, otherwise replace in place and re-fire the update topic."""
        with self._lock:
            existed = obj.id in self._objects
            self._objects[obj.id] = obj
        self.events.publish(TOPIC_OBJECT_UPDATED if existed else TOPIC_OBJECT_ADDED, obj)
        return obj

    def remove(self, object_id: str) -> SpatialObject | None:
        with self._lock:
            obj = self._objects.pop(object_id, None)
        if obj is not None:
            self.events.publish(TOPIC_OBJECT_REMOVED, obj)
        return obj

    def get(self, object_id: str) -> SpatialObject | None:
        with self._lock:
            return self._objects.get(object_id)

    def all(self) -> list[SpatialObject]:
        with self._lock:
            return list(self._objects.values())

    def by_type(self, obj_type: SpatialObjectType) -> list[SpatialObject]:
        with self._lock:
            return [o for o in self._objects.values() if o.type == obj_type]

    def children_of(self, parent_id: str) -> list[SpatialObject]:
        with self._lock:
            return [o for o in self._objects.values() if o.parent_id == parent_id]

    def query(self, predicate: Callable[[SpatialObject], bool]) -> list[SpatialObject]:
        with self._lock:
            return [o for o in self._objects.values() if predicate(o)]

    def nearest(
        self, point: Vector3, obj_type: SpatialObjectType | None = None, max_distance: float | None = None
    ) -> SpatialObject | None:
        candidates = self.by_type(obj_type) if obj_type is not None else self.all()
        best: SpatialObject | None = None
        best_dist = float("inf")
        for obj in candidates:
            dist = obj.transform.position.distance_to(point)
            if dist < best_dist and (max_distance is None or dist <= max_distance):
                best, best_dist = obj, dist
        return best

    def within_radius(self, point: Vector3, radius: float, obj_type: SpatialObjectType | None = None) -> list[SpatialObject]:
        candidates = self.by_type(obj_type) if obj_type is not None else self.all()
        return [o for o in candidates if o.transform.position.distance_to(point) <= radius]

    def prune_stale(self, max_age_seconds: float, obj_type: SpatialObjectType | None = None) -> list[str]:
        """Remove objects that haven't been observed/updated recently. Returns removed IDs."""
        stale = [
            o.id
            for o in (self.by_type(obj_type) if obj_type is not None else self.all())
            if o.is_stale(max_age_seconds)
        ]
        for object_id in stale:
            self.remove(object_id)
        return stale

    # -- zones ---------------------------------------------------------

    def add_zone(self, zone: Zone) -> Zone:
        with self._lock:
            self._zones[zone.id] = zone
        return zone

    def zones(self) -> list[Zone]:
        with self._lock:
            return list(self._zones.values())

    def zones_containing(self, point: tuple[float, float, float]) -> list[Zone]:
        return [z for z in self.zones() if z.contains(point)]

    def __len__(self) -> int:
        return len(self._objects)

    def __iter__(self) -> Iterable[SpatialObject]:
        return iter(self.all())
