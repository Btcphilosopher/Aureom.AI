"""FastAPI developer/diagnostic dashboard: tracking quality, spatial map, scene, anchors, frame timing, network."""

from __future__ import annotations

from fastapi import FastAPI

from xr_os.dashboard.cli_dashboard import snapshot
from xr_os.security.permissions import PermissionScope


def create_dashboard_app(world) -> FastAPI:
    """Build a FastAPI app exposing ``world``'s live diagnostic state."""
    app = FastAPI(title="XR-OS Dashboard")
    app.state.world = world

    @app.get("/status")
    def status() -> dict:
        return snapshot(world)

    @app.get("/tracking")
    def tracking() -> dict:
        return {target.value: pose.model_dump() for target, pose in world.services.tracking.all_poses().items()}

    @app.get("/scene")
    def scene() -> list[dict]:
        return [
            {
                "id": node.id,
                "name": node.name,
                "type": node.node_type.value,
                "visible": node.is_effectively_visible(),
                "collidable": node.collidable,
                "interactable": node.interactable,
                "position": node.world_position.as_tuple(),
                "depth": node.depth(),
            }
            for node in world.services.scene.all_nodes()
        ]

    @app.get("/anchors")
    def anchors() -> list[dict]:
        return [a.model_dump() for a in world.services.anchors.all()]

    @app.get("/permissions/{app_id}")
    def permissions(app_id: str) -> dict:
        return {scope.value: status.value for scope, status in world.services.permissions.grants_for(app_id).items()}

    @app.get("/permissions/{app_id}/{scope}")
    def permission_status(app_id: str, scope: PermissionScope) -> dict:
        return {"scope": scope.value, "status": world.services.permissions.status(app_id, scope).value}

    @app.get("/notifications")
    def notifications() -> list[dict]:
        return [{"text": n.text, "expired": n.expired} for n in world.services.notifications.active()]

    return app
