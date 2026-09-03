"""
Deterministic virtual hardware: a headset that walks a fixed path, hands
that follow it with a scripted pinch gesture, a synthetic room point cloud,
and a synthetic camera -- everything ``xr_os.tracking``/``xr_os.slam``/
``xr_os.vision`` need, with no real sensors involved.
"""

from __future__ import annotations

import math

import numpy as np

from xr_os.core.math3d import Quaternion, Vector3
from xr_os.slam.mapping import PointCloud
from xr_os.tracking.types import ControllerSample, HandSample, ImuSample, TrackedTarget, VisionSample


class VirtualRoom:
    """A box room: floor + 4 walls, sampled onto a deterministic grid point cloud."""

    def __init__(self, width: float = 4.0, depth: float = 4.0, height: float = 2.5) -> None:
        self.width = width
        self.depth = depth
        self.height = height

    def point_cloud(self, resolution: float = 0.1) -> PointCloud:
        points: list[tuple[float, float, float]] = []
        xs = np.arange(-self.width / 2, self.width / 2, resolution)
        zs = np.arange(-self.depth / 2, self.depth / 2, resolution)
        ys = np.arange(0.0, self.height, resolution)

        for x in xs:
            for z in zs:
                points.append((float(x), 0.0, float(z)))  # floor
                points.append((float(x), self.height, float(z)))  # ceiling
        for x in xs:
            for y in ys:
                points.append((float(x), float(y), -self.depth / 2))  # front wall
                points.append((float(x), float(y), self.depth / 2))  # back wall
        for z in zs:
            for y in ys:
                points.append((-self.width / 2, float(y), float(z)))  # left wall
                points.append((self.width / 2, float(y), float(z)))  # right wall

        return PointCloud(points=np.array(points, dtype=np.float64))


class VirtualHeadset:
    """Walks a fixed circular path deterministically as a function of simulated time."""

    def __init__(self, radius: float = 1.0, height: float = 1.6, angular_speed: float = 0.5) -> None:
        self.radius = radius
        self.height = height
        self.angular_speed = angular_speed

    def pose_at(self, t: float) -> tuple[Vector3, Quaternion]:
        angle = self.angular_speed * t
        position = Vector3(self.radius * math.cos(angle), self.height, self.radius * math.sin(angle))
        # face the center of the circle
        yaw = angle + math.pi / 2
        rotation = Quaternion.from_axis_angle(Vector3(0, 1, 0), yaw)
        return position, rotation

    def sample_imu(self, t: float) -> ImuSample:
        _, rotation = self.pose_at(t)
        angular_velocity = (0.0, self.angular_speed, 0.0)
        return ImuSample(orientation=rotation.as_tuple(), angular_velocity=angular_velocity, timestamp=t)

    def sample_vision(self, t: float) -> VisionSample:
        position, rotation = self.pose_at(t)
        return VisionSample(target=TrackedTarget.HEAD, position=position.as_tuple(), rotation=rotation.as_tuple(), confidence=0.9, timestamp=t)


class VirtualHands:
    """Hands held at a fixed offset in front of the headset, with a scripted periodic pinch."""

    def __init__(self, headset: VirtualHeadset, hand_spacing: float = 0.15, forward_offset: float = 0.3) -> None:
        self.headset = headset
        self.hand_spacing = hand_spacing
        self.forward_offset = forward_offset

    def _hand_pose(self, t: float, side: float) -> tuple[Vector3, Quaternion]:
        head_pos, head_rot = self.headset.pose_at(t)
        local_offset = Vector3(side * self.hand_spacing, -0.2, -self.forward_offset)
        world_offset = head_rot.rotate(local_offset)
        return head_pos + world_offset, head_rot

    def sample_hand(self, t: float, target: TrackedTarget) -> HandSample:
        side = -1.0 if target == TrackedTarget.LEFT_HAND else 1.0
        position, rotation = self._hand_pose(t, side)
        pinch = 1.0 if int(t * 2) % 4 == 0 else 0.0  # deterministic periodic pinch
        return HandSample(target=target, wrist_position=position.as_tuple(), wrist_rotation=rotation.as_tuple(), pinch_strength=pinch, confidence=0.85, timestamp=t)

    def sample_controller(self, t: float, target: TrackedTarget) -> ControllerSample:
        side = -1.0 if target == TrackedTarget.LEFT_CONTROLLER else 1.0
        position, rotation = self._hand_pose(t, side)
        return ControllerSample(target=target, position=position.as_tuple(), rotation=rotation.as_tuple(), timestamp=t)


class VirtualCamera:
    """A synthetic RGB camera: renders a few colored markers so vision backends have something to detect."""

    def __init__(self, width: int = 320, height: int = 240) -> None:
        self.width = width
        self.height = height

    def capture(self, t: float) -> np.ndarray:
        import cv2

        image = np.full((self.height, self.width, 3), 30, dtype=np.uint8)
        offset = int(20 * math.sin(t))
        cv2.rectangle(image, (40 + offset, 40), (90 + offset, 90), (255, 0, 0), thickness=-1)  # red marker, RGB order
        cv2.rectangle(image, (150, 100), (200, 150), (0, 255, 0), thickness=-1)  # green marker
        return image
