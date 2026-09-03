"""
Persistent, hierarchical spatial memory, SQLite-backed:

    HOME
    +-- LIVING ROOM
    |    +-- TV
    |    +-- SOFA
    |    +-- TABLE
    +-- OFFICE
         +-- DESK
         +-- MONITOR

Rooms are stored with a coarse geometric "fingerprint" derived from their
detected planes, so ``recognize_room`` can match a freshly-scanned space
against previously mapped ones without needing a full point-cloud registry.
"""

from __future__ import annotations

import json
import math
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from xr_os.core.math3d import Quaternion, Transform, Vector3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS places (
    id TEXT PRIMARY KEY,
    parent_id TEXT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    position TEXT NOT NULL,
    rotation TEXT NOT NULL,
    metadata TEXT NOT NULL,
    fingerprint TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY(parent_id) REFERENCES places(id)
);
CREATE INDEX IF NOT EXISTS idx_places_parent ON places(parent_id);
"""


class PlaceKind(str, Enum):
    HOME = "home"
    BUILDING = "building"
    ROOM = "room"
    ZONE = "zone"
    OBJECT = "object"


@dataclass
class Place:
    id: str
    name: str
    kind: PlaceKind
    parent_id: str | None
    position: tuple[float, float, float]
    rotation: tuple[float, float, float, float]
    metadata: dict
    fingerprint: "RoomFingerprint | None" = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def transform(self) -> Transform:
        return Transform(Vector3.from_tuple(self.position), Quaternion.from_tuple(self.rotation))


@dataclass
class RoomFingerprint:
    """A coarse, comparable geometric summary of a room, from its detected planes."""

    floor_area: float
    wall_count: int
    avg_wall_length: float
    ceiling_height: float

    def similarity(self, other: "RoomFingerprint") -> float:
        """1.0 = identical, 0.0 = nothing alike. Simple normalized inverse-distance score."""
        features_a = (self.floor_area, self.wall_count, self.avg_wall_length, self.ceiling_height)
        features_b = (other.floor_area, other.wall_count, other.avg_wall_length, other.ceiling_height)
        diffs = [abs(a - b) / max(a, b, 1e-6) for a, b in zip(features_a, features_b)]
        return max(0.0, 1.0 - (sum(diffs) / len(diffs)))

    @classmethod
    def from_spatial_map(cls, spatial_map) -> "RoomFingerprint":
        floor = spatial_map.floor()
        walls = spatial_map.walls()
        floor_area = (floor.extents[0] * floor.extents[1]) if floor else 0.0
        wall_lengths = [max(w.extents) for w in walls] or [0.0]
        ceiling_height = max((abs(p.point.y) for p in spatial_map.planes), default=2.4)
        return cls(
            floor_area=floor_area,
            wall_count=len(walls),
            avg_wall_length=sum(wall_lengths) / len(wall_lengths),
            ceiling_height=ceiling_height,
        )


def _row_to_place(row: sqlite3.Row) -> Place:
    fp_json = row["fingerprint"]
    fingerprint = RoomFingerprint(**json.loads(fp_json)) if fp_json else None
    return Place(
        id=row["id"],
        parent_id=row["parent_id"],
        name=row["name"],
        kind=PlaceKind(row["kind"]),
        position=tuple(json.loads(row["position"])),
        rotation=tuple(json.loads(row["rotation"])),
        metadata=json.loads(row["metadata"]),
        fingerprint=fingerprint,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SpatialMemory:
    """The persistent store of everywhere XR-OS has ever mapped."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- CRUD --------------------------------------------------------

    def create_place(
        self,
        name: str,
        kind: PlaceKind,
        parent_id: str | None = None,
        position: tuple[float, float, float] = (0.0, 0.0, 0.0),
        rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0),
        metadata: dict | None = None,
        fingerprint: RoomFingerprint | None = None,
    ) -> Place:
        place = Place(
            id=uuid.uuid4().hex,
            name=name,
            kind=kind,
            parent_id=parent_id,
            position=position,
            rotation=rotation,
            metadata=metadata or {},
            fingerprint=fingerprint,
        )
        self._conn.execute(
            "INSERT INTO places (id, parent_id, name, kind, position, rotation, metadata, fingerprint, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                place.id,
                place.parent_id,
                place.name,
                place.kind.value,
                json.dumps(place.position),
                json.dumps(place.rotation),
                json.dumps(place.metadata),
                json.dumps(fingerprint.__dict__) if fingerprint else None,
                place.created_at,
                place.updated_at,
            ),
        )
        self._conn.commit()
        return place

    def get(self, place_id: str) -> Place | None:
        row = self._conn.execute("SELECT * FROM places WHERE id = ?", (place_id,)).fetchone()
        return _row_to_place(row) if row else None

    def children(self, parent_id: str | None) -> list[Place]:
        if parent_id is None:
            rows = self._conn.execute("SELECT * FROM places WHERE parent_id IS NULL").fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM places WHERE parent_id = ?", (parent_id,)).fetchall()
        return [_row_to_place(r) for r in rows]

    def rooms(self) -> list[Place]:
        rows = self._conn.execute("SELECT * FROM places WHERE kind = ?", (PlaceKind.ROOM.value,)).fetchall()
        return [_row_to_place(r) for r in rows]

    def update_fingerprint(self, place_id: str, fingerprint: RoomFingerprint) -> None:
        self._conn.execute(
            "UPDATE places SET fingerprint = ?, updated_at = ? WHERE id = ?",
            (json.dumps(fingerprint.__dict__), time.time(), place_id),
        )
        self._conn.commit()

    def delete(self, place_id: str) -> None:
        for child in self.children(place_id):
            self.delete(child.id)
        self._conn.execute("DELETE FROM places WHERE id = ?", (place_id,))
        self._conn.commit()

    def tree(self, root_id: str | None = None) -> dict:
        """Nested dict view of the hierarchy, rooted at ``root_id`` (or every top-level place)."""
        if root_id is None:
            return {"name": "root", "children": [self.tree(p.id) for p in self.children(None)]}
        place = self.get(root_id)
        if place is None:
            return {}
        return {
            "id": place.id,
            "name": place.name,
            "kind": place.kind.value,
            "children": [self.tree(c.id) for c in self.children(place.id)],
        }

    # -- recognition -------------------------------------------------------

    def recognize_room(self, fingerprint: RoomFingerprint, min_similarity: float = 0.75) -> tuple[Place, float] | None:
        """Find the best-matching previously-mapped room for a freshly scanned space."""
        best: tuple[Place, float] | None = None
        for room in self.rooms():
            if room.fingerprint is None:
                continue
            score = fingerprint.similarity(room.fingerprint)
            if score >= min_similarity and (best is None or score > best[1]):
                best = (room, score)
        return best
