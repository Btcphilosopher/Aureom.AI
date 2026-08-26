"""
Seamless world streaming.

There is exactly one coordinate space for the whole map -- zones are just
labelled circular regions inside it (see ``utils.config.WORLD_ZONES``).
"Streaming" here means figuring out, every tick, which zone(s) are close
enough to the player to be simulated at full detail (traffic spawns,
event generation, weather-driven audio) versus which are dormant --
never a hard cut, never a loading screen, just a radius test against
already-resident data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from apex_horizon_engine.utils.config import WORLD_ZONES, ZoneSpec


@dataclass
class StreamingReport:
    active_zone: ZoneSpec
    nearby_zones: List[ZoneSpec]
    entered_zone: Optional[ZoneSpec] = None
    exited_zone: Optional[ZoneSpec] = None
    blend_factor: float = 1.0  # 0 = fully in neighbour, 1 = fully in active zone


class WorldStreamer:
    def __init__(self, zones: Dict[str, ZoneSpec] | None = None, streaming_radius_m: float = 2500.0):
        self.zones = zones or WORLD_ZONES
        self.streaming_radius_m = streaming_radius_m
        self._current_zone_id: Optional[str] = None

    def _distance_to(self, zone: ZoneSpec, x: float, y: float) -> float:
        return math.hypot(zone.center_xy[0] - x, zone.center_xy[1] - y)

    def nearest_zone(self, x: float, y: float) -> ZoneSpec:
        return min(self.zones.values(), key=lambda z: self._distance_to(z, x, y))

    def update(self, x: float, y: float) -> StreamingReport:
        active = self.nearest_zone(x, y)
        nearby = [
            z for z in self.zones.values()
            if self._distance_to(z, x, y) <= z.radius_m + self.streaming_radius_m
        ]

        entered = exited = None
        if active.zone_id != self._current_zone_id:
            if self._current_zone_id is not None:
                exited = self.zones.get(self._current_zone_id)
            entered = active
            self._current_zone_id = active.zone_id

        # Blend factor: 1.0 deep inside the active zone, trending to 0.5
        # near its edge where a neighbouring zone is also "nearby" -- used
        # by rendering/audio to crossfade ambience instead of hard-cutting.
        dist = self._distance_to(active, x, y)
        edge_zone = max(1.0, active.radius_m)
        blend = max(0.5, 1.0 - (dist / edge_zone) * 0.5) if len(nearby) > 1 else 1.0

        return StreamingReport(active_zone=active, nearby_zones=nearby,
                                entered_zone=entered, exited_zone=exited, blend_factor=blend)

    def world_bounds(self) -> tuple[float, float, float, float]:
        """(min_x, min_y, max_x, max_y) covering every zone -- useful for
        minimap scaling and AI navigation bounds checks."""
        xs = [z.center_xy[0] - z.radius_m for z in self.zones.values()] + \
             [z.center_xy[0] + z.radius_m for z in self.zones.values()]
        ys = [z.center_xy[1] - z.radius_m for z in self.zones.values()] + \
             [z.center_xy[1] + z.radius_m for z in self.zones.values()]
        return min(xs), min(ys), max(xs), max(ys)
