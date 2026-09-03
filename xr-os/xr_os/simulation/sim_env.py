"""SimulatedXREnvironment: drives an ``XRServices``/``XRWorld`` purely from virtual devices, deterministically."""

from __future__ import annotations

from dataclasses import dataclass, field

from xr_os.runtime.services import XRServices
from xr_os.simulation.virtual_devices import VirtualCamera, VirtualHands, VirtualHeadset, VirtualRoom
from xr_os.slam.mapping import SlamFrame
from xr_os.tracking.types import Pose, TrackedTarget


@dataclass
class SimulatedXREnvironment:
    """
    A deterministic, headset-free XR session: a scripted virtual headset and
    hands walk a fixed path through a synthetic room, feeding the same
    ``TrackingEngine``/``SpatialMap``/``XRServices`` a real device would.
    Ideal for local development and CI.
    """

    services: XRServices = field(default_factory=XRServices)
    room: VirtualRoom = field(default_factory=VirtualRoom)
    headset: VirtualHeadset = field(default_factory=VirtualHeadset)
    camera: VirtualCamera = field(default_factory=VirtualCamera)
    time: float = 0.0
    frame_count: int = 0

    def __post_init__(self) -> None:
        self.hands = VirtualHands(self.headset)
        self._bootstrap_room()

    def _bootstrap_room(self) -> None:
        cloud = self.room.point_cloud()
        self.services.spatial_map.integrate_frame(SlamFrame(pose=Pose(target=TrackedTarget.HEAD), new_points=cloud))
        self.services.spatial_map.rebuild_planes()
        self.services.physics.sync_planes_from_spatial_map(self.services.spatial_map)

    def step(self, dt: float = 1 / 90) -> dict:
        self.time += dt
        t = self.time

        self.services.tracking.ingest_imu(self.headset.sample_imu(t))
        self.services.tracking.ingest_vision(self.headset.sample_vision(t))
        self.services.tracking.ingest_hand(self.hands.sample_hand(t, TrackedTarget.LEFT_HAND))
        self.services.tracking.ingest_hand(self.hands.sample_hand(t, TrackedTarget.RIGHT_HAND))

        head_pose = self.services.tracking.get_pose(TrackedTarget.HEAD)
        if head_pose is not None:
            self.services.audio.set_listener_pose(head_pose.transform.position, head_pose.transform.rotation)

        self.services.update(dt)
        self.frame_count += 1

        return {
            "time": t,
            "frame": self.frame_count,
            "head": self.services.tracking.get_pose(TrackedTarget.HEAD),
            "left_hand": self.services.tracking.get_pose(TrackedTarget.LEFT_HAND),
            "right_hand": self.services.tracking.get_pose(TrackedTarget.RIGHT_HAND),
        }

    def run(self, steps: int, dt: float = 1 / 90) -> list[dict]:
        return [self.step(dt) for _ in range(steps)]

    def capture_frame(self) -> "object":
        return self.camera.capture(self.time)
