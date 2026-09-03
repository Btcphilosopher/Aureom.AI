"""
Terminal diagnostic dashboard:

    XR-OS
    TRACKING       o GOOD
    SPATIAL MAP    o ACTIVE
    HANDS          o TRACKING
    ...
    POSITION X 1.24 Y 1.67 Z -0.82
    FPS            90
    LATENCY        8 ms
"""

from __future__ import annotations

from xr_os.tracking.types import TrackedTarget, TrackingQuality


def snapshot(world) -> dict:
    """Build the plain-dict status snapshot both the CLI and HTTP dashboards render."""
    services = world.services
    head_pose = services.tracking.get_pose(TrackedTarget.HEAD)
    hands_tracking = any(
        services.tracking.get_pose(t) is not None
        for t in (TrackedTarget.LEFT_HAND, TrackedTarget.RIGHT_HAND)
    )
    return {
        "tracking_quality": (head_pose.quality if head_pose else TrackingQuality.LOST).value,
        "spatial_map_active": services.spatial_map.frame_count > 0,
        "spatial_map_points": len(services.spatial_map.cloud),
        "spatial_map_planes": len(services.spatial_map.planes),
        "hands_tracking": hands_tracking,
        "eyes_tracking": services.tracking.get_pose(TrackedTarget.GAZE) is not None,
        "audio_active": services.audio.source_count() > 0,
        "haptics_bound": services.haptics.bound_body_count() > 0,
        "scene_object_count": len(services.scene.all_nodes()),
        "input_event_count": services.input.total_events,
        "position": head_pose.position if head_pose else (0.0, 0.0, 0.0),
        "fps": round(world.fps, 1),
        "latency_ms": round(world.latency_ms, 2),
        "mode": services.modes.mode.value,
        "running_apps": services.lifecycle.running_apps(),
    }


def _bullet(active: bool) -> str:
    return "●" if active else "○"  # ● / ○


def render_dashboard(world):
    """Return a ``rich`` renderable (a Panel) for the current world state."""
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    data = snapshot(world)

    status = Table.grid(padding=(0, 2))
    status.add_column(justify="left")
    status.add_column(justify="left")

    def row(label: str, active: bool, text: str) -> None:
        color = "green" if active else "red"
        status.add_row(label, Text(f"{_bullet(active)} {text}", style=color))

    row("TRACKING", data["tracking_quality"] in ("high", "medium"), data["tracking_quality"].upper())
    row("SPATIAL MAP", data["spatial_map_active"], "ACTIVE" if data["spatial_map_active"] else "INACTIVE")
    row("HANDS", data["hands_tracking"], "TRACKING" if data["hands_tracking"] else "LOST")
    row("EYES", data["eyes_tracking"], "TRACKING" if data["eyes_tracking"] else "N/A")
    row("AUDIO", data["audio_active"], "ACTIVE" if data["audio_active"] else "IDLE")
    row("HAPTICS", data["haptics_bound"], "READY" if data["haptics_bound"] else "IDLE")

    x, y, z = data["position"]
    status.add_row("", "")
    status.add_row("POSITION", f"X {x:.2f}  Y {y:.2f}  Z {z:.2f}")
    status.add_row("MODE", data["mode"].upper())
    status.add_row("SCENE OBJECTS", str(data["scene_object_count"]))
    status.add_row("INPUT EVENTS", str(data["input_event_count"]))
    status.add_row("", "")
    status.add_row("FPS", str(data["fps"]))
    status.add_row("LATENCY", f"{data['latency_ms']} ms")

    return Panel(status, title="XR-OS", border_style="cyan")


def print_dashboard(world) -> None:
    from rich.console import Console

    Console().print(render_dashboard(world))
