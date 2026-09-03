"""
TrackingEngine: combines CAMERA + IMU + DEPTH + CONTROLLER (+ hand/eye/body)
samples into one unified spatial state, and optionally mirrors that state
into a ``SpatialWorldModel`` as HEADSET / HAND / CONTROLLER spatial objects.

This is the Python reference fusion implementation. It intentionally uses a
simple, inspectable confidence-weighted blend rather than a full Kalman
filter so behaviour is easy to reason about and test; production XR
hardware would replace ``TrackingEngine._fuse`` with a proper EKF/UKF or a
native (Rust/C++) implementation behind the exact same public API.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from xr_os.core.events import EventBus
from xr_os.core.math3d import Quaternion, Vector3
from xr_os.core.spatial_object import SpatialObject, SpatialObjectType
from xr_os.core.world_model import SpatialWorldModel
from xr_os.tracking.types import (
    ControllerSample,
    DepthSample,
    HandSample,
    ImuSample,
    Pose,
    TrackedTarget,
    TrackingQuality,
    TrackingSource,
    VisionSample,
)

TOPIC_POSE_UPDATED = "tracking.pose.updated"

# Deterministic world-model object ids per tracked target, so repeated
# fusion updates upsert the same object instead of spawning duplicates.
_TARGET_OBJECT_ID = {
    TrackedTarget.HEAD: "tracking.head",
    TrackedTarget.LEFT_HAND: "tracking.hand.left",
    TrackedTarget.RIGHT_HAND: "tracking.hand.right",
    TrackedTarget.LEFT_CONTROLLER: "tracking.controller.left",
    TrackedTarget.RIGHT_CONTROLLER: "tracking.controller.right",
    TrackedTarget.GAZE: "tracking.gaze",
    TrackedTarget.BODY_ROOT: "tracking.body",
}

_TARGET_OBJECT_TYPE = {
    TrackedTarget.HEAD: SpatialObjectType.HEADSET,
    TrackedTarget.LEFT_HAND: SpatialObjectType.HAND,
    TrackedTarget.RIGHT_HAND: SpatialObjectType.HAND,
    TrackedTarget.LEFT_CONTROLLER: SpatialObjectType.CONTROLLER,
    TrackedTarget.RIGHT_CONTROLLER: SpatialObjectType.CONTROLLER,
    TrackedTarget.GAZE: SpatialObjectType.USER,
    TrackedTarget.BODY_ROOT: SpatialObjectType.USER,
}

# How quickly an un-refreshed sample's influence decays, in seconds.
_SOURCE_DECAY_SECONDS = 0.5
# Base fusion weight per source, before recency decay is applied. IMU never
# contributes to position (see _fuse), so its weight only competes for which
# source's orientation wins -- and real headsets trust IMU orientation over
# vision/depth for exactly this reason (higher rate, lower short-term noise).
_SOURCE_BASE_WEIGHT = {
    TrackingSource.IMU: 1.6,
    TrackingSource.VISUAL: 1.0,
    TrackingSource.DEPTH: 1.2,
    TrackingSource.CONTROLLER: 1.5,
    TrackingSource.HAND: 1.5,
    TrackingSource.EYE: 1.0,
    TrackingSource.BODY: 0.8,
}


@dataclass
class _SourceState:
    position: Vector3
    rotation: Quaternion | None
    confidence: float
    timestamp: float
    source: TrackingSource


@dataclass
class _TargetState:
    sources: dict[TrackingSource, _SourceState] = field(default_factory=dict)
    last_pose: Pose | None = None


class TrackingEngine:
    """Fuses multi-modal tracking samples into unified per-target poses."""

    def __init__(self, world_model: SpatialWorldModel | None = None, event_bus: EventBus | None = None) -> None:
        self.world_model = world_model
        self.events = event_bus or (world_model.events if world_model else EventBus())
        self._state: dict[TrackedTarget, _TargetState] = {}

    # -- ingestion ---------------------------------------------------

    def ingest_imu(self, sample: ImuSample, target: TrackedTarget = TrackedTarget.HEAD) -> Pose:
        """IMU contributes orientation (and, integrated, would contribute position deltas)."""
        rotation = Quaternion.from_tuple(sample.orientation)
        prior = self._state.get(target)
        position = prior.sources[TrackingSource.IMU].position if prior and TrackingSource.IMU in prior.sources else Vector3.zero()
        self._update_source(target, TrackingSource.IMU, position, rotation, confidence=0.7, timestamp=sample.timestamp)
        return self._fuse(target)

    def ingest_vision(self, sample: VisionSample) -> Pose:
        self._update_source(
            sample.target,
            TrackingSource.VISUAL,
            Vector3.from_tuple(sample.position),
            Quaternion.from_tuple(sample.rotation),
            sample.confidence,
            sample.timestamp,
        )
        return self._fuse(sample.target)

    def ingest_depth(self, sample: DepthSample) -> Pose:
        self._update_source(
            sample.target,
            TrackingSource.DEPTH,
            Vector3.from_tuple(sample.position),
            None,
            sample.confidence,
            sample.timestamp,
        )
        return self._fuse(sample.target)

    def ingest_controller(self, sample: ControllerSample) -> Pose:
        confidence = 0.95 if sample.is_tracking else 0.1
        self._update_source(
            sample.target,
            TrackingSource.CONTROLLER,
            Vector3.from_tuple(sample.position),
            Quaternion.from_tuple(sample.rotation),
            confidence,
            sample.timestamp,
        )
        return self._fuse(sample.target)

    def ingest_hand(self, sample: HandSample) -> Pose:
        self._update_source(
            sample.target,
            TrackingSource.HAND,
            Vector3.from_tuple(sample.wrist_position),
            Quaternion.from_tuple(sample.wrist_rotation),
            sample.confidence,
            sample.timestamp,
        )
        pose = self._fuse(sample.target)
        pose.sources = list(pose.sources)  # keep pydantic happy about mutability
        return pose

    def _update_source(
        self,
        target: TrackedTarget,
        source: TrackingSource,
        position: Vector3,
        rotation: Quaternion | None,
        confidence: float,
        timestamp: float,
    ) -> None:
        state = self._state.setdefault(target, _TargetState())
        state.sources[source] = _SourceState(position, rotation, confidence, timestamp, source)

    # -- fusion --------------------------------------------------------

    def _fuse(self, target: TrackedTarget) -> Pose:
        state = self._state.setdefault(target, _TargetState())
        # Decay is measured relative to the freshest sample's own clock, not
        # wall time: live sources already timestamp close to time.time(), and
        # this keeps fusion identical for a deterministic simulated clock.
        sample_times = [s.timestamp for s in state.sources.values()]
        now = max(sample_times) if sample_times else time.time()

        weighted_pos = Vector3.zero()
        total_weight = 0.0
        best_rotation: Quaternion | None = None
        best_rotation_weight = -1.0
        max_confidence = 0.0
        sources_used: list[TrackingSource] = []

        for source, sample in state.sources.items():
            age = max(0.0, now - sample.timestamp)
            decay = math.exp(-age / _SOURCE_DECAY_SECONDS)
            weight = _SOURCE_BASE_WEIGHT.get(source, 1.0) * sample.confidence * decay
            if weight <= 1e-6:
                continue
            # IMU alone measures orientation (and acceleration), not absolute
            # position, so it contributes rotation only -- it must not pull
            # the fused position toward whatever placeholder it was seeded with.
            if source != TrackingSource.IMU:
                weighted_pos = weighted_pos + sample.position * weight
                total_weight += weight
            max_confidence = max(max_confidence, sample.confidence * decay)
            sources_used.append(source)
            if sample.rotation is not None and weight > best_rotation_weight:
                best_rotation, best_rotation_weight = sample.rotation, weight

        if total_weight > 1e-9:
            fused_position = weighted_pos * (1.0 / total_weight)
        elif state.last_pose is not None:
            fused_position = Vector3.from_tuple(state.last_pose.position)
        else:
            fused_position = Vector3.zero()

        fused_rotation = best_rotation or (
            Quaternion.from_tuple(state.last_pose.rotation) if state.last_pose else Quaternion.identity()
        )

        linear_velocity = Vector3.zero()
        if state.last_pose is not None:
            dt = max(1e-3, now - state.last_pose.timestamp)
            linear_velocity = (fused_position - Vector3.from_tuple(state.last_pose.position)) * (1.0 / dt)

        pose = Pose(
            target=target,
            position=fused_position.as_tuple(),
            rotation=fused_rotation.normalized().as_tuple(),
            linear_velocity=linear_velocity.as_tuple(),
            confidence=min(1.0, max_confidence),
            sources=sources_used,
            timestamp=now,
        )
        state.last_pose = pose

        self.events.publish(TOPIC_POSE_UPDATED, pose)
        self._sync_world_model(pose)
        return pose

    def _sync_world_model(self, pose: Pose) -> None:
        if self.world_model is None:
            return
        object_id = _TARGET_OBJECT_ID.get(pose.target)
        object_type = _TARGET_OBJECT_TYPE.get(pose.target)
        if object_id is None or object_type is None:
            return
        existing = self.world_model.get(object_id)
        if existing is None:
            self.world_model.add(
                SpatialObject(
                    id=object_id,
                    type=object_type,
                    position=pose.position,
                    rotation=pose.rotation,
                    confidence=pose.confidence,
                    label=pose.target.value,
                )
            )
        else:
            self.world_model.update(
                object_id,
                position=pose.position,
                rotation=pose.rotation,
                confidence=pose.confidence,
            )

    # -- reads -----------------------------------------------------------

    def get_pose(self, target: TrackedTarget) -> Pose | None:
        state = self._state.get(target)
        return state.last_pose if state else None

    def quality(self, target: TrackedTarget) -> TrackingQuality:
        pose = self.get_pose(target)
        return pose.quality if pose else TrackingQuality.LOST

    def all_poses(self) -> dict[TrackedTarget, Pose]:
        return {t: s.last_pose for t, s in self._state.items() if s.last_pose is not None}
