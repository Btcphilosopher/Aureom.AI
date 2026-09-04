"""
Region / Province / Territory hierarchy.

Spec ref: 03 (hierarchical world model), 06 (region system), 33
(political engine).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class Territory:
    """A single grid cell promoted to a named territory once it matters
    politically (owned, contested, or garrisoned)."""
    id: str
    cell: Tuple[int, int]
    region_id: str
    owner_faction: Optional[str] = None
    settlement_id: Optional[int] = None
    loyalty: float = 100.0  # 0..100, section 33: occupation/rebellion


@dataclass
class Region:
    id: str
    name: str
    cells: List[Tuple[int, int]] = field(default_factory=list)
    dominant_biome: str = "PLAINS"
    territories: Dict[str, Territory] = field(default_factory=dict)

    def owners(self) -> Set[str]:
        return {t.owner_faction for t in self.territories.values() if t.owner_faction}

    def controlling_faction(self) -> Optional[str]:
        """The faction holding the most territories in this region, or
        None if contested/unclaimed. Section 06: every region tracks
        ownership."""
        tally: Dict[str, int] = {}
        for t in self.territories.values():
            if t.owner_faction:
                tally[t.owner_faction] = tally.get(t.owner_faction, 0) + 1
        if not tally:
            return None
        return max(tally.items(), key=lambda kv: (kv[1], kv[0]))[0]
