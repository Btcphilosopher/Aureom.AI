"""Input engine tests: device-agnostic dispatch and scene-graph hit resolution."""

from xr_os.core.math3d import Transform, Vector3
from xr_os.input.devices import ControllerDevice, HandDevice, VoiceDevice
from xr_os.input.engine import InputEngine
from xr_os.input.events import InputEventType
from xr_os.scene.nodes import ModelNode
from xr_os.ui.elements import Button3D


def test_point_event_resolves_via_raycast(scene_graph):
    target = ModelNode("target", local_transform=Transform(Vector3(0, 0, -2)))
    scene_graph.add_virtual(target)
    engine = InputEngine(scene_graph)
    controller = engine.register(ControllerDevice("right_controller"))
    controller.emit_point((0, 0, 0), (0, 0, -1))

    results = engine.update()
    assert len(results) == 1
    assert results[0].event.type == InputEventType.POINT
    assert results[0].target_node_id == target.id


def test_pinch_event_resolves_via_proximity_and_dispatches(scene_graph):
    button = Button3D("ok", position=(0, 0, -1))
    scene_graph.add_virtual(button.node)
    clicked = []
    button.node.on_interact(lambda n, e, p: clicked.append(e))

    engine = InputEngine(scene_graph)
    hand = engine.register(HandDevice("right_hand"))
    hand.emit_pinch((0, 0, -1), strength=1.0)
    engine.update()

    assert clicked == ["pinch"]


def test_events_with_no_scene_graph_are_still_published():
    engine = InputEngine(scene_graph=None)
    seen = []
    engine.events.subscribe("input.event", lambda e: seen.append(e))
    voice = engine.register(VoiceDevice("voice"))
    voice.emit_speak("open menu")
    results = engine.update()
    assert len(seen) == 1
    assert results[0].target_node_id is None
    assert seen[0].text == "open menu"


def test_total_event_count_increments():
    engine = InputEngine()
    controller = engine.register(ControllerDevice("left_controller"))
    controller.emit_move((0, 0, 0))
    controller.emit_click((0, 0, 0))
    engine.update()
    assert engine.total_events == 2


def test_device_agnostic_apps_do_not_see_device_kind_in_dispatch(scene_graph):
    """Two different physical devices producing the same logical event type (CLICK)
    should both resolve and dispatch identically -- apps only see the event type."""
    button = Button3D("ok", position=(0, 0, -1))
    scene_graph.add_virtual(button.node)
    dispatched_types = []
    button.node.on_interact(lambda n, e, p: dispatched_types.append(e))

    engine = InputEngine(scene_graph)
    controller = engine.register(ControllerDevice("right_controller"))
    hand = engine.register(HandDevice("left_hand"))
    controller.emit_click((0, 0, -1))
    hand.emit_grab((0, 0, -1))
    engine.update()

    assert dispatched_types == ["click", "grab"]
