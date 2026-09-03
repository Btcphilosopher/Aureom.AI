"""
OS-style services: the same spatial-mapping, tracking, audio, input,
haptics, scene, notification, permission, profile, lifecycle and storage
subsystems used throughout XR-OS, wired together and exposed as one
service locator (``XRServices``) that applications and the dashboard read
from.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from xr_os.anchors.anchor_engine import SpatialAnchorEngine
from xr_os.audio.spatial_audio import SpatialAudioEngine
from xr_os.core.events import EventBus
from xr_os.core.world_model import SpatialWorldModel
from xr_os.haptics.haptics import HapticEngine
from xr_os.input.engine import InputEngine
from xr_os.memory.spatial_memory import SpatialMemory
from xr_os.modes.xr_mode import XRMode, XRModeManager
from xr_os.physics.engine import XRPhysicsEngine
from xr_os.scene.graph import XRSceneGraph
from xr_os.security.permissions import PermissionManager
from xr_os.security.storage import EncryptedStorage
from xr_os.slam.mapping import SpatialMap
from xr_os.tracking.engine import TrackingEngine
from xr_os.ui.elements import Notification

TOPIC_NOTIFICATION_POSTED = "notifications.posted"


class UserProfile(BaseModel):
    user_id: str
    display_name: str
    preferences: dict = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)


class ProfileService:
    """The active user profile plus any other known profiles (e.g. for a shared device)."""

    def __init__(self) -> None:
        self._profiles: dict[str, UserProfile] = {}
        self.active_user_id: str | None = None

    def create(self, user_id: str, display_name: str, preferences: dict | None = None) -> UserProfile:
        profile = UserProfile(user_id=user_id, display_name=display_name, preferences=preferences or {})
        self._profiles[user_id] = profile
        if self.active_user_id is None:
            self.active_user_id = user_id
        return profile

    def get(self, user_id: str) -> UserProfile | None:
        return self._profiles.get(user_id)

    def active(self) -> UserProfile | None:
        return self._profiles.get(self.active_user_id) if self.active_user_id else None

    def set_active(self, user_id: str) -> None:
        if user_id not in self._profiles:
            raise KeyError(user_id)
        self.active_user_id = user_id

    def all(self) -> list[UserProfile]:
        return list(self._profiles.values())


class NotificationService:
    """Posts transient spatial notifications and prunes them once expired."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.events = event_bus or EventBus()
        self._active: list[Notification] = []

    def post(self, text: str, duration_seconds: float = 3.0) -> Notification:
        notification = Notification(text, duration_seconds=duration_seconds)
        self._active.append(notification)
        self.events.publish(TOPIC_NOTIFICATION_POSTED, notification)
        return notification

    def update(self) -> list[Notification]:
        self._active = [n for n in self._active if not n.expired]
        return self._active

    def active(self) -> list[Notification]:
        return list(self._active)


class AppLifecycleState(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    BACKGROUND = "background"


class LifecycleService:
    """Tracks which applications are registered and their run state."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.events = event_bus or EventBus()
        self._state: dict[str, AppLifecycleState] = {}

    def register(self, app_id: str) -> None:
        self._state.setdefault(app_id, AppLifecycleState.STOPPED)

    def start(self, app_id: str) -> None:
        self._transition(app_id, AppLifecycleState.RUNNING)

    def pause(self, app_id: str) -> None:
        self._transition(app_id, AppLifecycleState.PAUSED)

    def background(self, app_id: str) -> None:
        self._transition(app_id, AppLifecycleState.BACKGROUND)

    def stop(self, app_id: str) -> None:
        self._transition(app_id, AppLifecycleState.STOPPED)

    def _transition(self, app_id: str, state: AppLifecycleState) -> None:
        self._state[app_id] = state
        self.events.publish("runtime.lifecycle.changed", {"app_id": app_id, "state": state})

    def state_of(self, app_id: str) -> AppLifecycleState:
        return self._state.get(app_id, AppLifecycleState.STOPPED)

    def running_apps(self) -> list[str]:
        return [aid for aid, s in self._state.items() if s == AppLifecycleState.RUNNING]


@dataclass
class XRServices:
    """
    The service locator every XR-OS application and the dashboard read
    from: one instance per running session, all subsystems pre-wired to
    share the same event bus and world model.
    """

    world_model: SpatialWorldModel = field(default_factory=SpatialWorldModel)
    events: EventBus = field(init=False)
    scene: XRSceneGraph = field(init=False)
    tracking: TrackingEngine = field(init=False)
    spatial_map: SpatialMap = field(default_factory=SpatialMap)
    anchors: SpatialAnchorEngine = field(init=False)
    modes: XRModeManager = field(init=False)
    audio: SpatialAudioEngine = field(init=False)
    input: InputEngine = field(init=False)
    haptics: HapticEngine = field(init=False)
    physics: XRPhysicsEngine = field(default_factory=XRPhysicsEngine)
    memory: SpatialMemory = field(default_factory=SpatialMemory)
    permissions: PermissionManager = field(init=False)
    notifications: NotificationService = field(init=False)
    profiles: ProfileService = field(default_factory=ProfileService)
    lifecycle: LifecycleService = field(init=False)
    storage: EncryptedStorage | None = None
    storage_dir: str | Path | None = None

    def __post_init__(self) -> None:
        self.events = self.world_model.events
        self.scene = XRSceneGraph(self.world_model)
        self.tracking = TrackingEngine(self.world_model, self.events)
        self.anchors = SpatialAnchorEngine(self.world_model)
        self.modes = XRModeManager(XRMode.MR, self.events)
        self.audio = SpatialAudioEngine(self.scene)
        self.input = InputEngine(self.scene, self.events)
        self.haptics = HapticEngine(self.events)
        self.permissions = PermissionManager(self.events)
        self.notifications = NotificationService(self.events)
        self.lifecycle = LifecycleService(self.events)
        if self.storage is None and self.storage_dir is not None:
            self.storage = EncryptedStorage(self.storage_dir)

    def update(self, dt: float = 1 / 90) -> None:
        """Advance every per-frame subsystem by one tick."""
        self.scene.sync_from_world_model()
        contacts = self.physics.step(dt)
        self.haptics.handle_collisions(contacts)
        self.input.update()
        self.audio.update()
        self.notifications.update()
