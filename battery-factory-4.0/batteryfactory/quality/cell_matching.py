"""
Cell matching engine (spec item 33): groups cells into modules to minimise
mismatch while maximising usable pack performance.

Series strings are capacity-limited by their weakest cell and resistance is
additive, so the objective is a real electrical one: minimise the spread of
capacity/resistance/voltage *within* each module.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from batteryfactory.datamodel.models import Cell, Module, next_serial


@dataclass
class MatchedModuleGroup:
    module: Module
    cells: list[Cell]
    capacity_spread_pct: float
    resistance_spread_pct: float


class CellMatchingEngine:
    def match_cells_to_modules(
        self, cells: list[Cell], cells_per_module: int, series_count: int, parallel_count: int
    ) -> list[MatchedModuleGroup]:
        usable = [c for c in cells if c.capacity_ah > 0]
        if len(usable) < cells_per_module:
            return []

        # Sort by capacity then bucket into contiguous windows: cells that
        # are electrically close end up together (a fast, effective proxy
        # for minimising within-bucket variance -- exact k-way balanced
        # partitioning is NP-hard at gigafactory volumes).
        ranked = sorted(usable, key=lambda c: (c.capacity_ah, c.internal_resistance_mohm))
        groups: list[MatchedModuleGroup] = []

        for start in range(0, len(ranked) - cells_per_module + 1, cells_per_module):
            bucket = ranked[start:start + cells_per_module]
            capacities = np.array([c.capacity_ah for c in bucket])
            resistances = np.array([c.internal_resistance_mohm for c in bucket])

            capacity_spread_pct = float((capacities.max() - capacities.min()) / capacities.mean() * 100.0)
            resistance_spread_pct = float((resistances.max() - resistances.min()) / resistances.mean() * 100.0)
            mismatch_score = capacity_spread_pct + resistance_spread_pct

            # Usable module capacity in a series string is set by the
            # weakest parallel group, not the average -- this is the real
            # electrical penalty of cell mismatch.
            module_capacity = float(capacities.min() * parallel_count)
            module_resistance = float(resistances.sum() / parallel_count * series_count)

            module = Module(
                module_id=next_serial("MOD"),
                cell_serials=[c.serial_number for c in bucket],
                series_count=series_count,
                parallel_count=parallel_count,
                capacity_ah=module_capacity,
                resistance_mohm=module_resistance,
                mismatch_score=mismatch_score,
            )
            groups.append(MatchedModuleGroup(module, bucket, capacity_spread_pct, resistance_spread_pct))

        return groups
