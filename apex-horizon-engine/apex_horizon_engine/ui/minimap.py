"""
Minimap data assembly: projects nearby points of interest (active event
start, rival racers, traffic, police units, zone centers) into
player-relative coordinates within a display radius.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class MinimapMarker:
    label: str
    kind: str          # "event" | "rival" | "traffic" | "police" | "zone"
    rel_x_m: float      # relative to player, world-aligned (not rotated to heading)
    rel_y_m: float
    distance_m: float
    heading_rad: float


def build_minimap_markers(
    player_x: float, player_y: float,
    points: List[Tuple[str, str, float, float]],  # (label, kind, x, y)
    radius_m: float = 400.0,
) -> List[MinimapMarker]:
    markers = []
    for label, kind, x, y in points:
        dx, dy = x - player_x, y - player_y
        dist = math.hypot(dx, dy)
        if dist > radius_m:
            continue
        markers.append(MinimapMarker(
            label=label, kind=kind, rel_x_m=round(dx, 1), rel_y_m=round(dy, 1),
            distance_m=round(dist, 1), heading_rad=math.atan2(dy, dx),
        ))
    return sorted(markers, key=lambda m: m.distance_m)


def rotate_to_player_heading(marker: MinimapMarker, player_heading_rad: float) -> Tuple[float, float]:
    """Rotate a marker's world-relative offset into screen-relative
    (player-forward-is-up) coordinates for the on-screen minimap."""
    cos_h, sin_h = math.cos(-player_heading_rad + math.pi / 2), math.sin(-player_heading_rad + math.pi / 2)
    x, y = marker.rel_x_m, marker.rel_y_m
    return x * cos_h - y * sin_h, x * sin_h + y * cos_h
