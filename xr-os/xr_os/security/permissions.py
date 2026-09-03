"""
Per-application permissions over sensitive spatial data.

Spatial data is treated as sensitive by default: an app only receives
camera frames, microphone audio, the spatial map, eye-tracking or
hand-tracking data it has been explicitly granted access to. Nothing here
auto-grants -- ``request`` records that an app wants a scope and leaves it
``NOT_DETERMINED`` until something (a user-facing consent UI, a test, an
admin policy) calls ``grant``/``deny``.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Callable

from xr_os.core.events import EventBus

TOPIC_PERMISSION_REQUESTED = "security.permission.requested"
TOPIC_PERMISSION_CHANGED = "security.permission.changed"


class PermissionScope(str, Enum):
    CAMERA = "camera"
    MICROPHONE = "microphone"
    SPATIAL_MAP = "spatial_map"
    EYE_TRACKING = "eye_tracking"
    HAND_TRACKING = "hand_tracking"
    LOCATION = "location"
    SPATIAL_STORAGE = "spatial_storage"


class PermissionStatus(str, Enum):
    NOT_DETERMINED = "not_determined"
    GRANTED = "granted"
    DENIED = "denied"


class PermissionDeniedError(PermissionError):
    def __init__(self, app_id: str, scope: PermissionScope, status: PermissionStatus) -> None:
        super().__init__(f"app {app_id!r} does not have {scope.value} access (status={status.value})")
        self.app_id = app_id
        self.scope = scope
        self.status = status


class PermissionManager:
    """Tracks and enforces per-app, per-scope permission grants."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.events = event_bus or EventBus()
        self._grants: dict[tuple[str, PermissionScope], PermissionStatus] = {}
        self._history: list[dict] = []

    def status(self, app_id: str, scope: PermissionScope) -> PermissionStatus:
        return self._grants.get((app_id, scope), PermissionStatus.NOT_DETERMINED)

    def request(self, app_id: str, scope: PermissionScope) -> PermissionStatus:
        """An app asks for a scope. Publishes a request event for a consent UI to react to."""
        current = self.status(app_id, scope)
        if current == PermissionStatus.NOT_DETERMINED:
            self.events.publish(TOPIC_PERMISSION_REQUESTED, {"app_id": app_id, "scope": scope})
        return current

    def grant(self, app_id: str, scope: PermissionScope) -> None:
        self._set(app_id, scope, PermissionStatus.GRANTED)

    def deny(self, app_id: str, scope: PermissionScope) -> None:
        self._set(app_id, scope, PermissionStatus.DENIED)

    def revoke(self, app_id: str, scope: PermissionScope) -> None:
        self._set(app_id, scope, PermissionStatus.NOT_DETERMINED)

    def _set(self, app_id: str, scope: PermissionScope, status: PermissionStatus) -> None:
        self._grants[(app_id, scope)] = status
        record = {"app_id": app_id, "scope": scope, "status": status, "timestamp": time.time()}
        self._history.append(record)
        self.events.publish(TOPIC_PERMISSION_CHANGED, record)

    def is_granted(self, app_id: str, scope: PermissionScope) -> bool:
        return self.status(app_id, scope) == PermissionStatus.GRANTED

    def enforce(self, app_id: str, scope: PermissionScope) -> None:
        """Raise ``PermissionDeniedError`` unless ``scope`` is granted for ``app_id``."""
        status = self.status(app_id, scope)
        if status != PermissionStatus.GRANTED:
            raise PermissionDeniedError(app_id, scope, status)

    def grants_for(self, app_id: str) -> dict[PermissionScope, PermissionStatus]:
        return {scope: status for (aid, scope), status in self._grants.items() if aid == app_id}

    def history(self) -> list[dict]:
        return list(self._history)


def require_permission(manager: PermissionManager, app_id: str, scope: PermissionScope) -> Callable:
    """Decorator: guard a function so it only runs when ``scope`` is granted to ``app_id``."""

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            manager.enforce(app_id, scope)
            return func(*args, **kwargs)

        return wrapper

    return decorator
