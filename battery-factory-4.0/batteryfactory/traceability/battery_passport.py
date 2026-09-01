"""Digital battery passport (spec item 31)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from batteryfactory.config.chemistry_profiles import ChemistryProfile
from batteryfactory.traceability.genealogy import GenealogyGraph


@dataclass
class BatteryPassport:
    pack_id: str
    chemistry: str
    manufacturing_date: datetime
    factory_name: str
    material_composition_pct: dict[str, float]
    genealogy: list[str]           # every upstream batch/cell/module id
    quality_summary: dict[str, float]
    manufacturing_history: list[str]

    def to_dict(self) -> dict:
        return {
            "pack_id": self.pack_id,
            "chemistry": self.chemistry,
            "manufacturing_date": self.manufacturing_date.isoformat(),
            "factory_name": self.factory_name,
            "material_composition_pct": self.material_composition_pct,
            "genealogy": self.genealogy,
            "quality_summary": self.quality_summary,
            "manufacturing_history": self.manufacturing_history,
        }


def generate_passport(
    pack_id: str,
    factory_name: str,
    profile: ChemistryProfile,
    genealogy: GenealogyGraph,
    quality_summary: dict[str, float],
    manufacturing_history: list[str],
) -> BatteryPassport:
    return BatteryPassport(
        pack_id=pack_id,
        chemistry=profile.chemistry.value,
        manufacturing_date=datetime.utcnow(),
        factory_name=factory_name,
        material_composition_pct=profile.material_composition_pct,
        genealogy=sorted(genealogy.trace_backward(pack_id)),
        quality_summary=quality_summary,
        manufacturing_history=manufacturing_history,
    )
