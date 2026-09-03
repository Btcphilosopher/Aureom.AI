"""Dashboard tests: the FastAPI diagnostic API and the snapshot it shares with the CLI renderer."""

import pytest
from fastapi.testclient import TestClient

from xr_os.dashboard.api import create_dashboard_app
from xr_os.dashboard.cli_dashboard import snapshot
from xr_os.runtime.app import XRWorld
from xr_os.scene.nodes import ModelNode
from xr_os.simulation.sim_env import SimulatedXREnvironment


@pytest.fixture
def world() -> XRWorld:
    w = XRWorld()
    env = SimulatedXREnvironment(services=w.services)
    env.run(steps=30)
    w.tick(1 / 90)
    return w


def test_snapshot_reports_tracking_and_scene_state(world: XRWorld):
    data = snapshot(world)
    assert data["tracking_quality"] in ("lost", "low", "medium", "high")
    assert data["spatial_map_active"] is True
    assert data["scene_object_count"] >= 0
    assert "fps" in data and "latency_ms" in data


def test_status_endpoint_matches_snapshot(world: XRWorld):
    client = TestClient(create_dashboard_app(world))
    response = client.get("/status")
    assert response.status_code == 200
    assert response.json()["mode"] == "mr"


def test_scene_endpoint_lists_mounted_nodes(world: XRWorld):
    world.add(ModelNode("demo_cube"))
    client = TestClient(create_dashboard_app(world))
    response = client.get("/scene")
    names = [n["name"] for n in response.json()]
    assert "demo_cube" in names


def test_anchors_endpoint_reflects_created_anchors(world: XRWorld):
    from xr_os.core.math3d import Vector3

    world.services.anchors.create_local_anchor(Vector3(1, 0, 0), label="test-anchor")
    client = TestClient(create_dashboard_app(world))
    response = client.get("/anchors")
    labels = [a["label"] for a in response.json()]
    assert "test-anchor" in labels


def test_permissions_endpoint_reports_grants(world: XRWorld):
    from xr_os.security.permissions import PermissionScope

    world.services.permissions.grant("my_app", PermissionScope.CAMERA)
    client = TestClient(create_dashboard_app(world))
    response = client.get("/permissions/my_app")
    assert response.json()["camera"] == "granted"


def test_notifications_endpoint_lists_active_notifications(world: XRWorld):
    world.services.notifications.post("Welcome!", duration_seconds=30.0)
    client = TestClient(create_dashboard_app(world))
    response = client.get("/notifications")
    assert any(n["text"] == "Welcome!" for n in response.json())
