"""Tracking-engine fusion tests."""

import pytest

from xr_os.core.spatial_object import SpatialObjectType
from xr_os.core.world_model import SpatialWorldModel
from xr_os.tracking.engine import TrackingEngine
from xr_os.tracking.types import ControllerSample, HandSample, ImuSample, TrackedTarget, TrackingQuality, VisionSample


def test_no_samples_means_lost():
    engine = TrackingEngine()
    assert engine.get_pose(TrackedTarget.HEAD) is None
    assert engine.quality(TrackedTarget.HEAD) == TrackingQuality.LOST


def test_vision_sample_updates_position_and_quality():
    engine = TrackingEngine()
    pose = engine.ingest_vision(VisionSample(target=TrackedTarget.HEAD, position=(1, 2, 3), confidence=0.9))
    assert pose.position == pytest.approx((1.0, 2.0, 3.0))
    assert pose.quality in (TrackingQuality.HIGH, TrackingQuality.MEDIUM)


def test_imu_contributes_rotation_but_not_position():
    engine = TrackingEngine()
    engine.ingest_vision(VisionSample(target=TrackedTarget.HEAD, position=(2, 0, 0), confidence=1.0, rotation=(0, 0, 0, 1)))
    pose = engine.ingest_imu(ImuSample(orientation=(0, 1, 0, 0)))
    # position should still reflect the vision sample, not be pulled toward IMU's placeholder origin
    assert pose.position == pytest.approx((2.0, 0.0, 0.0))
    assert pose.rotation == pytest.approx((0.0, 1.0, 0.0, 0.0))


def test_controller_sample_high_confidence_when_tracking():
    engine = TrackingEngine()
    pose = engine.ingest_controller(ControllerSample(target=TrackedTarget.RIGHT_CONTROLLER, position=(0.3, 1.2, -0.4), is_tracking=True))
    assert pose.quality == TrackingQuality.HIGH


def test_controller_sample_low_confidence_when_not_tracking():
    engine = TrackingEngine()
    pose = engine.ingest_controller(ControllerSample(target=TrackedTarget.RIGHT_CONTROLLER, position=(0, 0, 0), is_tracking=False))
    assert pose.confidence < 0.5


def test_hand_sample_updates_pose():
    engine = TrackingEngine()
    pose = engine.ingest_hand(HandSample(target=TrackedTarget.LEFT_HAND, wrist_position=(-0.2, 1.0, -0.3), pinch_strength=0.8))
    assert pose.position == pytest.approx((-0.2, 1.0, -0.3))


def test_fusion_writes_into_world_model():
    wm = SpatialWorldModel()
    engine = TrackingEngine(world_model=wm)
    engine.ingest_vision(VisionSample(target=TrackedTarget.HEAD, position=(1, 1.6, -1)))
    head_objects = wm.by_type(SpatialObjectType.HEADSET)
    assert len(head_objects) == 1
    assert head_objects[0].position == pytest.approx((1.0, 1.6, -1.0))

    # a second fusion update should upsert the same object, not create a new one
    engine.ingest_vision(VisionSample(target=TrackedTarget.HEAD, position=(2, 1.6, -1)))
    assert len(wm.by_type(SpatialObjectType.HEADSET)) == 1


def test_all_poses_reports_every_tracked_target():
    engine = TrackingEngine()
    engine.ingest_vision(VisionSample(target=TrackedTarget.HEAD, position=(0, 0, 0)))
    engine.ingest_hand(HandSample(target=TrackedTarget.LEFT_HAND, wrist_position=(0, 0, 0)))
    poses = engine.all_poses()
    assert set(poses.keys()) == {TrackedTarget.HEAD, TrackedTarget.LEFT_HAND}
