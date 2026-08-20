"""
Physical die floorplan.

Places SMs on a 2D grid, grouped into GPCs (Graphics Processing Clusters),
and exposes neighbour adjacency -- used by the thermal model for heat
diffusion between physically-adjacent blocks and by the visualiser to draw
the die layout / thermal heatmap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class SMPlacement:
    sm_id: int
    gpc_id: int
    x: int
    y: int
    area_mm2: float


class ChipLayout:
    def __init__(self, num_sms: int, sms_per_gpc: int, sm_area_mm2: float = 3.1):
        self.num_sms = num_sms
        self.sms_per_gpc = max(1, sms_per_gpc)
        self.num_gpcs = max(1, -(-num_sms // self.sms_per_gpc))
        self.sm_area_mm2 = sm_area_mm2

        # Roughly-square grid of GPCs, each GPC itself a small grid of SMs.
        self.gpc_cols = max(1, math.ceil(math.sqrt(self.num_gpcs)))
        self.gpc_rows = max(1, -(-self.num_gpcs // self.gpc_cols))
        self.sm_cols_per_gpc = max(1, math.ceil(math.sqrt(self.sms_per_gpc)))
        self.sm_rows_per_gpc = max(1, -(-self.sms_per_gpc // self.sm_cols_per_gpc))

        self.placements: Dict[int, SMPlacement] = {}
        self._build()

    def _build(self) -> None:
        sm_id = 0
        for gpc_id in range(self.num_gpcs):
            gpc_row = gpc_id // self.gpc_cols
            gpc_col = gpc_id % self.gpc_cols
            for local in range(self.sms_per_gpc):
                if sm_id >= self.num_sms:
                    break
                local_row = local // self.sm_cols_per_gpc
                local_col = local % self.sm_cols_per_gpc
                x = gpc_col * self.sm_cols_per_gpc + local_col
                y = gpc_row * self.sm_rows_per_gpc + local_row
                self.placements[sm_id] = SMPlacement(
                    sm_id=sm_id, gpc_id=gpc_id, x=x, y=y, area_mm2=self.sm_area_mm2,
                )
                sm_id += 1

    def neighbours(self, sm_id: int) -> List[int]:
        p = self.placements[sm_id]
        result = []
        for other in self.placements.values():
            if other.sm_id == sm_id:
                continue
            if abs(other.x - p.x) + abs(other.y - p.y) == 1:  # 4-connected
                result.append(other.sm_id)
        return result

    def grid_shape(self) -> Tuple[int, int]:
        max_x = max((p.x for p in self.placements.values()), default=0)
        max_y = max((p.y for p in self.placements.values()), default=0)
        return max_x + 1, max_y + 1

    def total_sm_area_mm2(self) -> float:
        return sum(p.area_mm2 for p in self.placements.values())
