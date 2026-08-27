"""The Project: a named collection of timelines living inside a Library Event.

Also home to (de)serialisation for the core editorial structures — the
magnetic timeline's clips, gaps, transitions, compound clips and
connections — used by ``persistence.project_store``. Attached processing
objects (effects, colour grades, transforms) are serialised best-effort as
"type name + field values" JSON, since they're intentionally duck-typed
in the timeline layer rather than being fixed, importable types.
"""
from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

import numpy as np

from finalcut_engine.core.timebase import FPS_24, FrameRate, Time, TimeRange
from finalcut_engine.timeline.clip import Clip
from finalcut_engine.timeline.compound_clip import CompoundClip
from finalcut_engine.timeline.connected_clip import ConnectedClip
from finalcut_engine.timeline.gap import Gap
from finalcut_engine.timeline.magnetic_timeline import MagneticTimeline
from finalcut_engine.timeline.roles import Role
from finalcut_engine.timeline.storyline import Storyline
from finalcut_engine.timeline.transitions import Transition, TransitionKind


@dataclass
class ProjectSettings:
    width: int = 1920
    height: int = 1080
    frame_rate: FrameRate = field(default_factory=lambda: FPS_24)


@dataclass
class Project:
    name: str
    settings: ProjectSettings = field(default_factory=ProjectSettings)
    timelines: Dict[str, MagneticTimeline] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def create_timeline(self, name: str = "Timeline") -> MagneticTimeline:
        timeline = MagneticTimeline(name=name, frame_rate=self.settings.frame_rate)
        self.timelines[timeline.id] = timeline
        return timeline


# -- serialisation ------------------------------------------------------------
def _time_to_dict(t: Time) -> dict:
    return {"value": t.value, "timescale": t.timescale}


def _time_from_dict(d: dict) -> Time:
    return Time(d["value"], d["timescale"])


def _range_to_dict(r: TimeRange) -> dict:
    return {"start": _time_to_dict(r.start), "duration": _time_to_dict(r.duration)}


def _range_from_dict(d: dict) -> TimeRange:
    return TimeRange(_time_from_dict(d["start"]), _time_from_dict(d["duration"]))


def _json_safe(value: Any) -> Any:
    """Recursively coerce an arbitrary value into something ``json.dumps`` accepts.

    Used for the duck-typed effect/colour/transform/title objects a clip can
    carry, which are intentionally *not* fixed, importable types the timeline
    layer knows about (see the module docstring) — so round-tripping their
    exact class is out of scope here; this preserves their field values for
    inspection/debugging rather than losing them to a serialisation crash.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if dataclasses.is_dataclass(value):
        return {
            "__type__": type(value).__qualname__,
            "fields": {f.name: _json_safe(getattr(value, f.name)) for f in dataclasses.fields(value)},
        }
    if callable(value):
        return {"__type__": "callable", "repr": repr(value)}
    return {"__type__": type(value).__qualname__, "repr": repr(value)}


def _processing_to_dict(obj: Any) -> Optional[dict]:
    """Best-effort serialisation for duck-typed effect/colour/transform objects."""
    if obj is None:
        return None
    return _json_safe(obj)


def _item_to_dict(item) -> dict:
    if isinstance(item, Clip):
        return {
            "type": "clip",
            "id": item.id,
            "asset_id": item.asset_id,
            "source_range": _range_to_dict(item.source_range),
            "name": item.name,
            "role": str(item.role),
            "gain_db": item.gain_db,
            "colour_grade": _processing_to_dict(item.colour_grade),
            "transform": _processing_to_dict(item.transform),
        }
    if isinstance(item, Gap):
        return {"type": "gap", "id": item.id, "duration": _time_to_dict(item.duration)}
    if isinstance(item, Transition):
        return {
            "type": "transition",
            "id": item.id,
            "duration": _time_to_dict(item.duration),
            "outgoing_item_id": item.outgoing_item_id,
            "incoming_item_id": item.incoming_item_id,
            "kind": item.kind.value,
        }
    if isinstance(item, CompoundClip):
        return {"type": "compound_clip", "id": item.id, "name": item.name, "nested": _storyline_to_dict(item.nested)}
    raise TypeError(f"don't know how to serialise timeline item of type {type(item)}")


def _item_from_dict(d: dict):
    kind = d["type"]
    if kind == "clip":
        return Clip(
            id=d["id"],
            asset_id=d["asset_id"],
            source_range=_range_from_dict(d["source_range"]),
            name=d["name"],
            role=Role.parse(d["role"]),
            gain_db=d["gain_db"],
        )
    if kind == "gap":
        return Gap(id=d["id"], _duration=_time_from_dict(d["duration"]))
    if kind == "transition":
        return Transition(
            id=d["id"],
            _duration=_time_from_dict(d["duration"]),
            outgoing_item_id=d["outgoing_item_id"],
            incoming_item_id=d["incoming_item_id"],
            kind=TransitionKind(d["kind"]),
        )
    if kind == "compound_clip":
        return CompoundClip(id=d["id"], name=d["name"], nested=_storyline_from_dict(d["nested"]))
    raise ValueError(f"unknown timeline item type {kind!r}")


def _storyline_to_dict(storyline: Storyline) -> dict:
    return {"id": storyline.id, "name": storyline.name, "items": [_item_to_dict(i) for i in storyline.items]}


def _storyline_from_dict(d: dict) -> Storyline:
    return Storyline(id=d["id"], name=d["name"], items=[_item_from_dict(i) for i in d["items"]])


def timeline_to_dict(timeline: MagneticTimeline) -> dict:
    return {
        "id": timeline.id,
        "name": timeline.name,
        "frame_rate": {"numerator": timeline.frame_rate.numerator, "denominator": timeline.frame_rate.denominator, "drop_frame": timeline.frame_rate.drop_frame},
        "primary": _storyline_to_dict(timeline.primary),
        "secondary_storylines": {sid: _storyline_to_dict(s) for sid, s in timeline.secondary_storylines.items()},
        "connected": {
            cid: {
                "id": c.id,
                "item": _item_to_dict(c.item) if isinstance(c.item, (Clip, Gap, Transition, CompoundClip)) else _storyline_to_dict(c.item),
                "item_is_storyline": isinstance(c.item, Storyline),
                "anchor_item_id": c.anchor_item_id,
                "offset": _time_to_dict(c.offset),
                "lane": c.lane,
            }
            for cid, c in timeline.connected.items()
        },
    }


def timeline_from_dict(d: dict) -> MagneticTimeline:
    fr = FrameRate(d["frame_rate"]["numerator"], d["frame_rate"]["denominator"], d["frame_rate"]["drop_frame"])
    timeline = MagneticTimeline(name=d["name"], frame_rate=fr)
    timeline.id = d["id"]
    timeline.primary = _storyline_from_dict(d["primary"])
    timeline.secondary_storylines = {sid: _storyline_from_dict(s) for sid, s in d["secondary_storylines"].items()}
    for cid, c in d["connected"].items():
        item = _storyline_from_dict(c["item"]) if c["item_is_storyline"] else _item_from_dict(c["item"])
        timeline.connected[cid] = ConnectedClip(
            id=c["id"], item=item, anchor_item_id=c["anchor_item_id"], offset=_time_from_dict(c["offset"]), lane=c["lane"]
        )
    return timeline


def project_to_dict(project: Project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "created_at": project.created_at.isoformat(),
        "settings": {
            "width": project.settings.width,
            "height": project.settings.height,
            "frame_rate": {
                "numerator": project.settings.frame_rate.numerator,
                "denominator": project.settings.frame_rate.denominator,
                "drop_frame": project.settings.frame_rate.drop_frame,
            },
        },
        "timelines": {tid: timeline_to_dict(t) for tid, t in project.timelines.items()},
    }


def project_from_dict(d: dict) -> Project:
    fr_d = d["settings"]["frame_rate"]
    settings = ProjectSettings(
        width=d["settings"]["width"], height=d["settings"]["height"], frame_rate=FrameRate(fr_d["numerator"], fr_d["denominator"], fr_d["drop_frame"])
    )
    project = Project(name=d["name"], settings=settings, id=d["id"], created_at=datetime.fromisoformat(d["created_at"]))
    project.timelines = {tid: timeline_from_dict(t) for tid, t in d["timelines"].items()}
    return project
