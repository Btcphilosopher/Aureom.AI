"""3D audio: sources placed at spatial coordinates, mixed relative to a moving listener."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from enum import Enum

from xr_os.core.math3d import Quaternion, Vector3


class AttenuationModel(str, Enum):
    LINEAR = "linear"
    INVERSE = "inverse"
    EXPONENTIAL = "exponential"


@dataclass
class AudioSource:
    """A sound placed at a point (or attached to a moving object) in the world."""

    sound_id: str
    position: Vector3 = field(default_factory=Vector3.zero)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    gain: float = 1.0
    min_distance: float = 1.0
    max_distance: float = 20.0
    attenuation: AttenuationModel = AttenuationModel.INVERSE
    loop: bool = False
    playing: bool = True
    attached_node_id: str | None = None  # if set, position tracks this scene node each update


@dataclass
class Listener:
    """The ears: a position + orientation (forward/up define the stereo field)."""

    position: Vector3 = field(default_factory=Vector3.zero)
    rotation: Quaternion = field(default_factory=Quaternion.identity)

    @property
    def forward(self) -> Vector3:
        return self.rotation.rotate(Vector3(0, 0, -1))

    @property
    def right(self) -> Vector3:
        return self.rotation.rotate(Vector3(1, 0, 0))


@dataclass
class RoomAcoustics:
    """Simple per-zone room-effect parameters (reverb send + occlusion strength)."""

    reverb_wet: float = 0.15
    occlusion_attenuation_db: float = -12.0


@dataclass
class AudioMix:
    """The computed per-frame mix parameters for one source, ready for an audio backend."""

    source_id: str
    gain: float  # linear 0..1, after distance + occlusion + room effects
    pan: float  # -1 (full left) .. +1 (full right)
    distance: float
    occluded: bool
    reverb_wet: float


def _attenuate(distance: float, min_d: float, max_d: float, model: AttenuationModel) -> float:
    if distance <= min_d:
        return 1.0
    if distance >= max_d:
        return 0.0
    span = max(1e-6, max_d - min_d)
    t = (distance - min_d) / span
    if model == AttenuationModel.LINEAR:
        return 1.0 - t
    if model == AttenuationModel.EXPONENTIAL:
        return (1.0 - t) ** 2
    # INVERSE, matching real-world 1/r falloff normalized to [min_d, max_d]
    return min_d / distance


class SpatialAudioEngine:
    """Owns sources + the listener, and computes the per-frame spatial mix."""

    def __init__(self, scene_graph=None, room_acoustics: RoomAcoustics | None = None) -> None:
        self.scene_graph = scene_graph
        self.listener = Listener()
        self.room_acoustics = room_acoustics or RoomAcoustics()
        self._sources: dict[str, AudioSource] = {}

    def add_source(self, source: AudioSource) -> AudioSource:
        self._sources[source.id] = source
        return source

    def remove_source(self, source_id: str) -> None:
        self._sources.pop(source_id, None)

    def source_count(self) -> int:
        return len(self._sources)

    def set_listener_pose(self, position: Vector3, rotation: Quaternion) -> None:
        self.listener = Listener(position, rotation)

    def _is_occluded(self, source: AudioSource) -> bool:
        """Line-of-sight check: any collidable scene node between listener and source occludes."""
        if self.scene_graph is None:
            return False
        origin = self.listener.position
        to_source = source.position - origin
        distance = to_source.length()
        if distance < 1e-6:
            return False
        direction = to_source * (1.0 / distance)
        hit = self.scene_graph.raycast(origin, direction, max_distance=distance - 0.05)
        return hit is not None and hit.node.collidable

    def update(self) -> list[AudioMix]:
        """Sync attached sources to their scene node, then compute a mix for every playing source."""
        mixes: list[AudioMix] = []
        for source in self._sources.values():
            if source.attached_node_id and self.scene_graph is not None:
                node = self.scene_graph.find(source.attached_node_id)
                if node is not None:
                    source.position = node.world_position
            if not source.playing:
                continue
            distance = self.listener.position.distance_to(source.position)
            attenuated = _attenuate(distance, source.min_distance, source.max_distance, source.attenuation)
            occluded = self._is_occluded(source)
            occlusion_gain = _db_to_linear(self.room_acoustics.occlusion_attenuation_db) if occluded else 1.0

            to_source = (source.position - self.listener.position).normalized()
            pan = max(-1.0, min(1.0, to_source.dot(self.listener.right)))

            gain = max(0.0, min(1.0, source.gain * attenuated * occlusion_gain))
            mixes.append(
                AudioMix(
                    source_id=source.id,
                    gain=gain,
                    pan=pan,
                    distance=distance,
                    occluded=occluded,
                    reverb_wet=self.room_acoustics.reverb_wet,
                )
            )
        return mixes


def _db_to_linear(db: float) -> float:
    return 10 ** (db / 20.0)
