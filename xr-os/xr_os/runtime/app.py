"""
The application framework XR-OS apps are built on:

    world = XRWorld()
    panel = SpatialPanel(position=(1, 0, -2), size=(1.5, 0.8))
    world.add(panel)
    world.run()

Applications interact with the operating system only through ``XRWorld``
and the ``XRServices`` it wraps -- never by reaching into a specific
subsystem's internals directly.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Type, TypeVar

from xr_os.runtime.services import XRServices
from xr_os.scene.node import SceneNode

AppT = TypeVar("AppT", bound="XRApp")

_FRAME_STATS_WINDOW = 90


class XRWorld:
    """The top-level handle an application holds: scene content + every OS service, plus the run loop."""

    def __init__(self, services: XRServices | None = None) -> None:
        self.services = services or XRServices()
        self._apps: list["XRApp"] = []
        self._running = False
        self.frame_count = 0
        self._frame_durations: deque[float] = deque(maxlen=_FRAME_STATS_WINDOW)

    # -- content -----------------------------------------------------

    def add(self, element) -> object:
        """Mount a ``SceneNode`` or a ``SpatialUIElement``-like wrapper into the virtual world."""
        node = element.node if hasattr(element, "node") and isinstance(element.node, SceneNode) else element
        self.services.scene.add_virtual(node)
        return element

    def remove(self, element) -> None:
        node = element.node if hasattr(element, "node") and isinstance(element.node, SceneNode) else element
        if node.parent is not None:
            node.parent.remove_child(node)

    # -- apps ----------------------------------------------------------

    def load_app(self, app_cls: Type[AppT], **kwargs) -> AppT:
        app = app_cls(self, **kwargs)
        self.services.lifecycle.register(app.app_id)
        self._apps.append(app)
        self.services.lifecycle.start(app.app_id)
        app.on_start()
        return app

    def unload_app(self, app: "XRApp") -> None:
        if app in self._apps:
            app.on_stop()
            self.services.lifecycle.stop(app.app_id)
            self._apps.remove(app)

    # -- run loop --------------------------------------------------------

    def tick(self, dt: float) -> None:
        start = time.perf_counter()
        self.services.update(dt)
        for app in list(self._apps):
            if self.services.lifecycle.state_of(app.app_id).value == "running":
                app.on_update(dt)
        self.frame_count += 1
        self._frame_durations.append(time.perf_counter() - start)

    @property
    def fps(self) -> float:
        if not self._frame_durations:
            return 0.0
        avg = sum(self._frame_durations) / len(self._frame_durations)
        return 1.0 / avg if avg > 0 else 0.0

    @property
    def latency_ms(self) -> float:
        if not self._frame_durations:
            return 0.0
        return (sum(self._frame_durations) / len(self._frame_durations)) * 1000.0

    def run(self, fps: float = 90.0, max_frames: int | None = None) -> None:
        """
        Blocking run loop. Suitable for simulation/dev; a real headset would
        drive ``tick()`` from its own native frame callback instead of this
        Python loop (see xr_os/__init__.py on hard-real-time boundaries).
        """
        self._running = True
        frame_time = 1.0 / fps
        try:
            while self._running:
                start = time.perf_counter()
                self.tick(frame_time)
                if max_frames is not None and self.frame_count >= max_frames:
                    break
                elapsed = time.perf_counter() - start
                remaining = frame_time - elapsed
                if remaining > 0:
                    time.sleep(remaining)
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False


class XRApp:
    """Base class for applications built on XR-OS."""

    app_id: str = "app"

    def __init__(self, world: XRWorld) -> None:
        self.world = world
        self.services = world.services

    def on_start(self) -> None:
        """Called once when the app is loaded."""

    def on_update(self, dt: float) -> None:
        """Called every tick while the app is running."""

    def on_stop(self) -> None:
        """Called once when the app is unloaded."""
