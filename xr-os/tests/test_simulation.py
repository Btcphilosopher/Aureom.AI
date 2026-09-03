"""Simulation-mode tests: the OS runs headless, deterministically, for CI."""

import numpy as np
import pytest

from xr_os.runtime.services import XRServices
from xr_os.simulation.sim_env import SimulatedXREnvironment
from xr_os.simulation.virtual_devices import VirtualRoom
from xr_os.tracking.types import TrackedTarget


def test_virtual_room_generates_a_point_cloud_with_planes():
    room = VirtualRoom(width=4, depth=4, height=2.5)
    cloud = room.point_cloud(resolution=0.2)
    assert len(cloud) > 0
    lower, upper = cloud.bounds()
    assert lower.y == pytest.approx(0.0, abs=1e-6)
    assert upper.y == pytest.approx(2.5, abs=1e-6)


def test_sim_env_bootstraps_planes_from_room():
    env = SimulatedXREnvironment()
    assert len(env.services.spatial_map.planes) > 0
    assert len(env.services.physics.planes) == len(env.services.spatial_map.planes)


def test_sim_env_step_produces_tracked_head_pose():
    env = SimulatedXREnvironment()
    frame = env.step(1 / 90)
    assert frame["head"] is not None
    assert frame["head"].target == TrackedTarget.HEAD


def test_sim_env_is_deterministic_across_independent_runs():
    env_a = SimulatedXREnvironment()
    env_b = SimulatedXREnvironment()
    results_a = env_a.run(steps=90)
    results_b = env_b.run(steps=90)
    assert results_a[-1]["head"].position == results_b[-1]["head"].position
    assert results_a[-1]["left_hand"].position == results_b[-1]["left_hand"].position


def test_sim_env_head_follows_circular_path():
    env = SimulatedXREnvironment()
    env.run(steps=90)  # 1 second at 90Hz
    head = env.services.tracking.get_pose(TrackedTarget.HEAD)
    # after walking part of the circle, the head should have left its start position
    assert head.position != (0.0, 0.0, 0.0)
    # radius stays constant in the XZ plane
    x, y, z = head.position
    assert (x**2 + z**2) ** 0.5 == pytest.approx(env.headset.radius, abs=1e-2)


def test_sim_env_camera_produces_frame_vision_can_detect():
    from xr_os.vision.cv_backends import ColorBlobDetector

    env = SimulatedXREnvironment()
    frame = env.capture_frame()
    assert isinstance(frame, np.ndarray)
    detections = ColorBlobDetector().detect(frame)
    labels = {d.label for d in detections}
    assert "red" in labels
    assert "green" in labels


def test_sim_env_shares_services_with_an_xr_world():
    from xr_os.runtime.app import XRWorld

    world = XRWorld()
    env = SimulatedXREnvironment(services=world.services)
    env.run(steps=30)
    world.tick(1 / 90)
    assert world.services.spatial_map.frame_count == 1  # only the room bootstrap frame
    assert world.services.tracking.get_pose(TrackedTarget.HEAD) is not None
