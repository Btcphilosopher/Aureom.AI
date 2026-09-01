"""Raw material catalogue for a battery gigafactory (spec item 4)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from batteryfactory.datamodel.models import Material


class RawMaterialCategory(str, Enum):
    LITHIUM_COMPOUND = "lithium_compound"
    NICKEL_COMPOUND = "nickel_compound"
    MANGANESE_COMPOUND = "manganese_compound"
    COBALT_COMPOUND = "cobalt_compound"
    IRON_COMPOUND = "iron_compound"
    PHOSPHATE_COMPOUND = "phosphate_compound"
    GRAPHITE = "graphite"
    SILICON_MATERIAL = "silicon_material"
    COPPER_FOIL = "copper_foil"
    ALUMINIUM_FOIL = "aluminium_foil"
    SEPARATOR = "separator"
    ELECTROLYTE = "electrolyte"
    CASING = "casing"
    PACKAGING = "packaging"


@dataclass(frozen=True)
class MaterialSpec:
    material: Material
    category: RawMaterialCategory
    reference_unit_cost: float          # currency per unit, model assumption
    max_moisture_pct: float             # acceptance threshold
    min_purity_pct: float               # acceptance threshold


STANDARD_MATERIALS: dict[str, MaterialSpec] = {
    m.material.material_id: m
    for m in [
        MaterialSpec(Material("lithium_carbonate", "Lithium Carbonate", "cathode_precursor", "kg"), RawMaterialCategory.LITHIUM_COMPOUND, 2100.0, 0.5, 99.5),
        MaterialSpec(Material("lithium_hydroxide", "Lithium Hydroxide", "cathode_precursor", "kg"), RawMaterialCategory.LITHIUM_COMPOUND, 2300.0, 0.3, 99.5),
        MaterialSpec(Material("nickel_sulfate", "Nickel Sulfate", "cathode_precursor", "kg"), RawMaterialCategory.NICKEL_COMPOUND, 24.0, 1.0, 99.0),
        MaterialSpec(Material("manganese_sulfate", "Manganese Sulfate", "cathode_precursor", "kg"), RawMaterialCategory.MANGANESE_COMPOUND, 3.5, 1.0, 99.0),
        MaterialSpec(Material("cobalt_sulfate", "Cobalt Sulfate", "cathode_precursor", "kg"), RawMaterialCategory.COBALT_COMPOUND, 55.0, 1.0, 99.0),
        MaterialSpec(Material("iron_phosphate", "Iron Phosphate", "cathode_precursor", "kg"), RawMaterialCategory.IRON_COMPOUND, 4.5, 1.0, 98.5),
        MaterialSpec(Material("lithium_iron_phosphate", "Lithium Iron Phosphate (LFP)", "cathode_active_material", "kg"), RawMaterialCategory.PHOSPHATE_COMPOUND, 9.5, 0.3, 99.0),
        MaterialSpec(Material("graphite", "Graphite (anode active material)", "anode_active_material", "kg"), RawMaterialCategory.GRAPHITE, 8.0, 0.5, 99.5),
        MaterialSpec(Material("silicon_oxide", "Silicon Oxide (Si/C blend)", "anode_active_material", "kg"), RawMaterialCategory.SILICON_MATERIAL, 18.0, 0.3, 99.0),
        MaterialSpec(Material("copper_foil", "Copper Foil", "current_collector", "m2", density_kg_m3=8960.0), RawMaterialCategory.COPPER_FOIL, 3.2, 0.2, 99.9),
        MaterialSpec(Material("aluminium_foil", "Aluminium Foil", "current_collector", "m2", density_kg_m3=2700.0), RawMaterialCategory.ALUMINIUM_FOIL, 1.1, 0.2, 99.9),
        MaterialSpec(Material("separator", "Separator Film", "separator", "m2"), RawMaterialCategory.SEPARATOR, 0.45, 0.2, 99.9),
        MaterialSpec(Material("electrolyte", "Electrolyte", "electrolyte", "kg"), RawMaterialCategory.ELECTROLYTE, 12.0, 0.05, 99.9),
        MaterialSpec(Material("casing", "Cell Casing", "casing", "unit"), RawMaterialCategory.CASING, 0.9, 5.0, 99.0),
        MaterialSpec(Material("packaging", "Packaging", "packaging", "unit"), RawMaterialCategory.PACKAGING, 0.3, 20.0, 90.0),
    ]
}
