"""Application runtime tests: XRWorld, XRApp lifecycle, and OS-style services."""

import pytest

from xr_os.runtime.app import XRApp, XRWorld
from xr_os.runtime.services import AppLifecycleState
from xr_os.ui.elements import Button3D, SpatialPanel


def test_world_add_mounts_ui_element_into_virtual_world():
    world = XRWorld()
    panel = SpatialPanel(position=(1, 0, -2), size=(1.5, 0.8))
    world.add(panel)
    assert panel.node.parent is world.services.scene.virtual_world


def test_world_add_accepts_a_bare_scene_node():
    from xr_os.scene.nodes import ModelNode

    world = XRWorld()
    node = ModelNode("cube")
    world.add(node)
    assert node.parent is world.services.scene.virtual_world


def test_world_remove_detaches_element():
    world = XRWorld()
    panel = SpatialPanel()
    world.add(panel)
    world.remove(panel)
    assert panel.node.parent is None


def test_button_click_fires_callback_through_panel():
    world = XRWorld()
    panel = SpatialPanel()
    world.add(panel)
    clicks = []
    button = panel.add(Button3D("Go", on_click=lambda b: clicks.append(b.label)))
    button.click()
    assert clicks == ["Go"]


class _CountingApp(XRApp):
    app_id = "counting_app"

    def on_start(self):
        self.started = True
        self.ticks = 0

    def on_update(self, dt):
        self.ticks += 1

    def on_stop(self):
        self.stopped = True


def test_load_app_calls_on_start_and_registers_lifecycle():
    world = XRWorld()
    app = world.load_app(_CountingApp)
    assert app.started
    assert world.services.lifecycle.state_of("counting_app") == AppLifecycleState.RUNNING


def test_tick_advances_running_apps():
    world = XRWorld()
    app = world.load_app(_CountingApp)
    world.tick(1 / 90)
    world.tick(1 / 90)
    assert app.ticks == 2


def test_paused_app_does_not_tick():
    world = XRWorld()
    app = world.load_app(_CountingApp)
    world.services.lifecycle.pause("counting_app")
    world.tick(1 / 90)
    assert app.ticks == 0


def test_unload_app_calls_on_stop():
    world = XRWorld()
    app = world.load_app(_CountingApp)
    world.unload_app(app)
    assert app.stopped
    assert world.services.lifecycle.state_of("counting_app") == AppLifecycleState.STOPPED


def test_run_stops_after_max_frames():
    world = XRWorld()
    world.load_app(_CountingApp)
    world.run(fps=1000, max_frames=5)
    assert world.frame_count == 5


def test_fps_and_latency_are_tracked_after_ticks():
    world = XRWorld()
    world.tick(1 / 90)
    world.tick(1 / 90)
    assert world.fps > 0
    assert world.latency_ms >= 0


def test_notification_service_expires_notifications():
    world = XRWorld()
    note = world.services.notifications.post("hello", duration_seconds=0.0)
    active = world.services.notifications.update()
    assert note not in active


def test_profile_service_tracks_active_user():
    world = XRWorld()
    world.services.profiles.create("u1", "Alice")
    world.services.profiles.create("u2", "Bob")
    assert world.services.profiles.active().user_id == "u1"
    world.services.profiles.set_active("u2")
    assert world.services.profiles.active().display_name == "Bob"
