"""
State synchronization primitives.

APEX HORIZON ENGINE runs local multiplayer/convoy sessions in-process
(genuinely deterministic, no network needed), but this module still
implements the serialize/diff/checksum machinery a real network layer
would need -- and, just as importantly, gives ``core.state_manager`` and
the test suite a way to *prove* two simulation runs from the same seed
stayed bit-for-bit in lockstep, which is exactly what
``utils.config.EngineConfig.deterministic`` promises.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict

from apex_horizon_engine.vehicles.vehicle_model import Vehicle


def serialize_vehicle_state(vehicle: Vehicle) -> Dict[str, Any]:
    s = vehicle.state
    return {
        "x": round(s.x, 4), "y": round(s.y, 4), "heading": round(s.heading_rad, 5),
        "vx": round(s.vx, 4), "vy": round(s.vy, 4), "yaw_rate": round(s.yaw_rate, 5),
        "gear": s.drivetrain.gear_index, "rpm": round(s.drivetrain.rpm, 1),
        "damage": round(s.damage.body_damage, 4),
    }


def checksum(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


@dataclass
class SnapshotDiff:
    tick: int
    changed_fields: Dict[str, Any]


class StateSyncer:
    """Keeps the last-sent snapshot per entity and emits only the fields
    that changed beyond a small epsilon -- the standard delta-compression
    trick a real network sync layer needs, exercised here so the engine's
    architecture doesn't have to change if networked multiplayer is added
    later."""

    def __init__(self, epsilon: float = 1e-4):
        self.epsilon = epsilon
        self._last: Dict[str, Dict[str, Any]] = {}

    def diff(self, entity_id: str, tick: int, current: Dict[str, Any]) -> SnapshotDiff:
        previous = self._last.get(entity_id, {})
        changed = {}
        for key, value in current.items():
            old = previous.get(key)
            if old is None or (isinstance(value, (int, float)) and isinstance(old, (int, float))
                                and abs(value - old) > self.epsilon) or (old != value and not isinstance(value, (int, float))):
                changed[key] = value
        self._last[entity_id] = current
        return SnapshotDiff(tick=tick, changed_fields=changed)

    def full_snapshot(self, entity_id: str) -> Dict[str, Any]:
        return dict(self._last.get(entity_id, {}))


def lockstep_checksum(tick: int, vehicles: Dict[str, Vehicle]) -> str:
    """Aggregate checksum across every tracked vehicle at a given tick --
    two engine instances seeded identically should produce identical
    checksums forever, which is exactly what
    ``tests/test_determinism.py`` verifies."""
    payload = {"tick": tick, "vehicles": {vid: serialize_vehicle_state(v) for vid, v in sorted(vehicles.items())}}
    return checksum(payload)
