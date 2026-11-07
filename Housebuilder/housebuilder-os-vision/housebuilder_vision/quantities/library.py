"""Default assembly library: materials, construction build-ups, foundations, allowances.

Information level
-----------------
Everything here is **generic and illustrative**:

* build-ups are indicative comparison assemblies, **not specifications or
  designs**; nothing implies regulatory compliance, certified thermal
  performance or structural adequacy;
* thermal conductivities, densities, masses and pack sizes are typical-order
  illustrative values for concept-stage modelling;
* carbon factors (``carbon_kgco2e_per_kg``) are **illustrative placeholders,
  not EPD or ICE values** (``carbon_source = "illustrative placeholder"``);
  replace them through a data adapter before any reporting;
* lead times are assumed ranges (``TrackedValue`` with basis ``ASSUMED``);
* the library holds **no prices**.  Prices live in rate books, and the bundled
  demo rates are explicitly fictional.

Ids are the contract used by other modules: assemblies ``ew_masonry_cavity``,
``ew_timber_frame_brick``, ``ew_timber_frame_clad``, ``sw_masonry_separating``,
``ip_timber_stud``, ``gf_concrete_slab``, ``if_timber_joist``, ``pr_tiled_cold``,
``fr_warm_deck``, ``win_upvc_dg``, ``win_alu_tg``, ``door_composite``,
``gdoor_steel_sectional``; foundations ``fdn_trench_fill``, ``fdn_strip``,
``fdn_deep_trench_fill``, ``fdn_raft``, ``fdn_piled_allowance``.

Cost keys emitted by the take-off (see :func:`cost_keys`)
--------------------------------------------------------
* ``mat:<material_id>`` per material, unit = the material's ``purchase_unit``
  (thermal-only pseudo-materials such as ``air_cavity_50`` get no cost key);
* ``lab:<trade>`` (unit ``hr``) for labour hours on every line;
* ``allow:<allowance_id>`` for :class:`AllowanceRule` lines (unit = rule unit);
* substructure operations are *rule lines* without a material:
  ``plant:excavation`` (m3 bank volume, trenches and oversite dig) and
  ``log:spoil_disposal`` (m3 loose volume after bulking, removed off site);
* foundation allowances ``allow:piling`` (m of pile, specialist subcontract,
  labour included in the rate) and ``allow:reinforcement`` (kg, indicative
  allowance, never a reinforcement schedule).

Units: installed quantities are SI (m, m2, m3, kg, nr); purchase units are
product units (pack contents are expressed in purchase units, e.g. PIR is
bought as boards in packs of 6 boards).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..core.models import (
    AllowanceRule,
    Assembly,
    AssemblyLayer,
    AssemblyLibrary,
    AssemblySelection,
    ElementType,
    FoundationKind,
    FoundationOption,
    LayerBridging,
    LayerRole,
    MaterialSpec,
)
from ..core.provenance import Basis, Distribution, TrackedValue, assumed
from ..core.units import UnitError, dimension, is_known_unit
from .measures import FOUNDATION_KEY, MEASURE_UNITS, MEASURES

__all__ = [
    "LIBRARY_SOURCE",
    "LIBRARY_INFORMATION",
    "THERMAL_ONLY_CATEGORY",
    "TRADES",
    "SubstructureRules",
    "SUBSTRUCTURE_RULES",
    "default_library",
    "default_selection",
    "validate_library",
    "cost_keys",
    "material_cost_key",
    "labour_cost_key",
    "is_purchasable",
]

LIBRARY_SOURCE = "aureom-generic-library-v1 (illustrative)"
LIBRARY_INFORMATION = (
    "Generic indicative build-ups with illustrative thermal, mass and carbon data for concept-stage "
    "comparison. NOT specifications, NOT designs, NOT EPD/ICE values; no compliance, certified "
    "performance or structural adequacy is implied.")
THERMAL_ONLY_CATEGORY = "thermal_only"
CARBON_SOURCE = "illustrative placeholder"

#: Trade names used for ``lab:<trade>`` cost keys (ARCHITECTURE §3).
TRADES: tuple[str, ...] = ("groundworks", "bricklaying", "carpentry", "roofing", "glazing", "drylining",
                           "plastering", "electrical", "plumbing", "decorating", "general")


def material_cost_key(material_id: str) -> str:
    return f"mat:{material_id}"


def labour_cost_key(trade: str) -> str:
    return f"lab:{trade}"


def is_purchasable(material: MaterialSpec) -> bool:
    """False for thermal-only pseudo-materials (e.g. an air cavity) that are never bought."""
    return material.category != THERMAL_ONLY_CATEGORY


@dataclass(frozen=True)
class SubstructureRules:
    """Fixed rule data for substructure lines (illustrative; editable by passing a copy).

    Excavation and disposal are *rule lines* (no material) priced via ``plant:excavation`` and
    ``log:spoil_disposal``.  Labour hours are per installed unit.
    """

    excavation_cost_key: str = "plant:excavation"
    disposal_cost_key: str = "log:spoil_disposal"
    piling_cost_key: str = "allow:piling"
    reinforcement_cost_key: str = "allow:reinforcement"
    reinforcement_material_id: str = "reinforcement_steel"
    block_material_id: str = "dense_concrete_block_100"
    mortar_material_id: str = "mortar"
    blocks_per_m2: float = 9.88  # 440x215 blocks with 10 mm joints
    mortar_m3_per_m2_block: float = 0.009
    #: Leaves of below-ground masonry per wall type (cavity walls: 2; internal loadbearing: 1).
    leaves_external: int = 2
    leaves_separating: int = 2
    leaves_internal: int = 1
    excavation_hours_per_m3: float = 0.35
    oversite_hours_per_m3: float = 0.20
    disposal_hours_per_m3: float = 0.05
    concrete_hours_per_m3: float = 0.60
    block_hours_per_nr: float = 0.06
    reinforcement_hours_per_kg: float = 0.02


SUBSTRUCTURE_RULES = SubstructureRules()


# =============================================================================
# Materials
# =============================================================================
def _lead(mode: float, low: float, high: float, note: str = "") -> TrackedValue:
    return assumed(mode, "week", low=low, high=high, source=LIBRARY_SOURCE,
                   note=note or "Illustrative supplier lead time; confirm with suppliers.")


def _m(material_id: str, name: str, category: str, installed_unit: str, purchase_unit: str, *,
       ppi: float = 1.0, pack: float = 1.0, pack_desc: str = "", cut: float = 0.0, waste: float = 0.0,
       density: Optional[float] = None, k: Optional[float] = None, mass: Optional[float] = None,
       vol: Optional[float] = None, carbon: Optional[float] = None, lead: Optional[TrackedValue] = None,
       delivery: str = "general", notes: str = "") -> MaterialSpec:
    return MaterialSpec(
        material_id=material_id, name=name, category=category, installed_unit=installed_unit,
        purchase_unit=purchase_unit, purchase_per_installed=ppi, pack_size=pack, pack_description=pack_desc,
        cutting_loss_fraction=cut, waste_fraction=waste, density_kg_m3=density, conductivity_w_mk=k,
        mass_per_purchase_unit_kg=mass, volume_per_purchase_unit_m3=vol, carbon_kgco2e_per_kg=carbon,
        carbon_source=CARBON_SOURCE, lead_time_weeks=lead, delivery_category=delivery,
        notes=(notes + " " if notes else "") + "Illustrative data; not a product specification.",
    )


def _materials() -> list[MaterialSpec]:
    return [
        # ------------------------------------------------------------ masonry
        _m("facing_brick", "Facing brick 215x102.5x65 (generic clay)", "masonry", "nr", "nr", pack=500,
           pack_desc="pack of 500 bricks", cut=0.03, waste=0.05, density=1900, k=0.77, mass=2.5, vol=0.00143,
           carbon=0.22, lead=_lead(4, 2, 8), delivery="masonry"),
        _m("mortar", "General-purpose masonry mortar (site / silo)", "mortar", "m3", "m3", pack=0.1,
           pack_desc="ordered in 0.1 m3 increments", waste=0.10, density=1800, k=0.94, mass=1800, vol=1.0,
           carbon=0.16, lead=_lead(1, 0.5, 2), delivery="bulk_aggregate"),
        _m("dense_concrete_block_100", "Dense concrete block 440x215x100", "masonry", "nr", "nr", pack=72,
           pack_desc="pallet of 72 blocks", cut=0.05, waste=0.03, density=2000, k=1.13, mass=18.9, vol=0.00946,
           carbon=0.08, lead=_lead(2, 1, 4), delivery="masonry"),
        _m("aerated_concrete_block_100", "Aerated (aircrete) block 440x215x100", "masonry", "nr", "nr",
           pack=100, pack_desc="pack of 100 blocks", cut=0.05, waste=0.03, density=600, k=0.15, mass=5.7,
           vol=0.00946, carbon=0.30, lead=_lead(2, 1, 6), delivery="masonry"),
        _m("wall_ties", "Stainless cavity wall tie (generic)", "fixings", "nr", "nr", pack=250,
           pack_desc="box of 250 ties", waste=0.05, mass=0.04, vol=0.00005, carbon=6.0,
           lead=_lead(1, 0.5, 2), delivery="general"),
        _m("steel_lintel", "Galvanised steel cavity lintel (generic, type not selected)", "steel", "m", "m",
           pack=0.15, pack_desc="standard lengths in 150 mm increments (bought per opening; aggregate "
           "rounding here is indicative)", k=50.0, mass=8.0, vol=0.01, carbon=2.0, lead=_lead(2, 1, 4),
           delivery="steel", notes="Lintel type and load capacity require design; quantity only."),
        _m("cavity_closer", "Insulated cavity closer 2.4 m length", "fixings", "m", "length", ppi=1 / 2.4,
           pack_desc="2.4 m lengths", cut=0.05, waste=0.05, mass=1.0, vol=0.03, carbon=3.0,
           lead=_lead(1, 0.5, 3), delivery="general"),
        # ------------------------------------------------- concrete & ground
        _m("concrete_c25", "Ready-mixed concrete C25/30 (generic)", "concrete", "m3", "m3", pack=0.25,
           pack_desc="ordered in 0.25 m3 increments", waste=0.05, density=2400, k=1.65, mass=2400, vol=1.0,
           carbon=0.10, lead=_lead(1, 0.5, 2), delivery="ready_mix_concrete"),
        _m("hardcore_type1", "Type 1 sub-base (compacted)", "aggregate", "m3", "tonne", ppi=2.1, pack=1.0,
           pack_desc="ordered by the whole tonne; 2.1 t per compacted m3", waste=0.05, density=2100, mass=1000,
           vol=0.56, carbon=0.005, lead=_lead(1, 0.5, 2), delivery="bulk_aggregate"),
        _m("sand_blinding", "Sand blinding", "aggregate", "m3", "tonne", ppi=1.6, pack=0.85,
           pack_desc="bulk bags of 0.85 t; 1.6 t per m3", waste=0.10, density=1600, mass=1000, vol=0.63,
           carbon=0.005, lead=_lead(1, 0.5, 2), delivery="bulk_aggregate"),
        _m("screed_sand_cement", "Sand-cement floor screed", "concrete", "m3", "m3", pack=0.1,
           pack_desc="ordered in 0.1 m3 increments", waste=0.05, density=2000, k=1.4, mass=2000, vol=1.0,
           carbon=0.13, lead=_lead(1, 0.5, 2), delivery="ready_mix_concrete"),
        _m("dpm_1200g", "Polyethylene damp-proof membrane 1200 gauge", "membrane", "m2", "roll", ppi=0.01,
           pack_desc="roll 4 m x 25 m = 100 m2", cut=0.10, waste=0.05, mass=28, vol=0.06, carbon=2.5,
           lead=_lead(1, 0.5, 2), delivery="general", notes="Cutting allowance covers laps and upstands."),
        _m("reinforcement_steel", "Reinforcement steel (allowance only)", "steel", "kg", "kg", waste=0.03,
           density=7850, k=50.0, mass=1.0, vol=0.000127, carbon=1.2, lead=_lead(2, 1, 3), delivery="steel",
           notes="Used only by labelled reinforcement allowances; no reinforcement schedule is computed."),
        # ------------------------------------------------------- insulation
        _m("pir_100", "PIR insulation board 100 mm (2400x1200)", "insulation", "m2", "board", ppi=1 / 2.88,
           pack=6, pack_desc="pack of 6 boards (2.88 m2 each = 17.28 m2)", cut=0.05, waste=0.03, density=32,
           k=0.022, mass=9.2, vol=0.288, carbon=3.4, lead=_lead(2, 1, 6), delivery="insulation"),
        _m("pir_25", "PIR insulation board 25 mm (2400x1200)", "insulation", "m2", "board", ppi=1 / 2.88,
           pack=24, pack_desc="pack of 24 boards (2.88 m2 each)", cut=0.10, waste=0.05, density=32, k=0.022,
           mass=2.3, vol=0.072, carbon=3.4, lead=_lead(2, 1, 6), delivery="insulation"),
        _m("mineral_wool_100_cavity", "Mineral wool full-fill cavity batt 100 mm", "insulation", "m2", "pack",
           ppi=1 / 4.37, pack_desc="pack of batts covering 4.37 m2", cut=0.03, waste=0.03, density=30, k=0.037,
           mass=13.1, vol=0.40, carbon=1.2, lead=_lead(2, 1, 4), delivery="insulation"),
        _m("mineral_wool_140_stud", "Mineral wool slab 140 mm for 140 mm studs", "insulation", "m2", "pack",
           ppi=1 / 4.10, pack_desc="pack of slabs covering 4.10 m2", cut=0.05, waste=0.03, density=18,
           k=0.036, mass=10.3, vol=0.30, carbon=1.3, lead=_lead(2, 1, 4), delivery="insulation"),
        _m("mineral_wool_300_loft", "Mineral wool loft roll, 300 mm total depth", "insulation", "m2", "roll",
           ppi=1 / 3.2, pack_desc="roll-equivalent covering 3.2 m2 at 300 mm (100 mm between ties + 200 mm "
           "over)", cut=0.03, waste=0.03, density=10, k=0.044, mass=9.6, vol=0.25, carbon=1.3,
           lead=_lead(1, 0.5, 3), delivery="insulation"),
        _m("air_cavity_50", "Unventilated air cavity 50 mm (thermal only)", THERMAL_ONLY_CATEGORY, "m2", "m2",
           density=1.2, k=0.05 / 0.18, carbon=0.0, delivery="none",
           notes="Pseudo-material for the thermal calculation: equivalent conductivity = 0.05 m / "
                 "R 0.18 m2K/W. Nothing is purchased."),
        # ------------------------------------------------- timber & sheets
        _m("timber_stud_140x38", "Structural timber C24 140x38 (studs, plates)", "timber", "m", "length",
           ppi=1 / 4.8, pack_desc="4.8 m lengths", cut=0.10, waste=0.05, density=470, k=0.13, mass=12.0,
           vol=0.0255, carbon=0.40, lead=_lead(2, 1, 4), delivery="timber"),
        _m("timber_stud_89x38", "Timber CLS 89x38 (partition studs)", "timber", "m", "length", ppi=1 / 4.8,
           pack_desc="4.8 m lengths", cut=0.10, waste=0.05, density=470, k=0.13, mass=7.6, vol=0.0162,
           carbon=0.40, lead=_lead(1, 0.5, 3), delivery="timber"),
        _m("timber_batten_25x50", "Treated timber batten 25x50", "timber", "m", "length", ppi=1 / 4.8,
           pack_desc="4.8 m lengths", cut=0.10, waste=0.05, density=470, k=0.13, mass=2.8, vol=0.006,
           carbon=0.40, lead=_lead(1, 0.5, 3), delivery="timber"),
        _m("timber_joist_c24", "Timber joist C24 (generic section; not sized)", "timber", "m", "length",
           ppi=1 / 4.8, pack_desc="4.8 m lengths", cut=0.08, waste=0.05, density=470, k=0.13, mass=20.7,
           vol=0.044, carbon=0.40, lead=_lead(2, 1, 4), delivery="timber",
           notes="Generic section for quantity only; member sizing not performed."),
        _m("floor_joist_i", "Engineered timber I-joist (generic; depth not designed)", "timber", "m", "m",
           pack=1.0, pack_desc="cut to length; ordered by the metre", cut=0.05, waste=0.03, k=0.13, mass=3.5,
           vol=0.05, carbon=0.60, lead=_lead(3, 2, 4), delivery="timber",
           notes="Joist depth, spacing and layout require manufacturer's / engineer's design."),
        _m("trussed_rafter", "Trussed rafter (manufacturer-designed, generic)", "timber", "nr", "nr", mass=45,
           vol=0.25, k=0.13, carbon=0.40, lead=_lead(4, 3, 5), delivery="timber_frame",
           notes="Count only; truss design, bracing and girders are by the truss manufacturer."),
        _m("fascia_soffit_timber", "Timber fascia and soffit board set", "timber", "m", "length", ppi=1 / 4.8,
           pack_desc="4.8 m lengths", cut=0.10, waste=0.05, density=470, mass=12.0, vol=0.03, carbon=0.40,
           lead=_lead(1, 0.5, 3), delivery="timber"),
        _m("larch_cladding", "Larch cladding boards 20 mm", "timber", "m2", "m2", ppi=1.15,
           pack_desc="board face area; 1.15 m2 of boards per m2 of wall (laps)", cut=0.10, waste=0.05,
           density=550, k=0.13, mass=11.0, vol=0.02, carbon=0.30, lead=_lead(4, 2, 8), delivery="timber"),
        _m("osb_9", "OSB/3 sheathing 9 mm (2440x1220)", "sheet", "m2", "sheet", ppi=1 / 2.977,
           pack_desc="2.977 m2 sheets", cut=0.08, waste=0.03, density=600, k=0.13, mass=16.1, vol=0.027,
           carbon=0.45, lead=_lead(1, 0.5, 3), delivery="sheet_materials"),
        _m("osb_18", "OSB/3 deck 18 mm (2440x1220)", "sheet", "m2", "sheet", ppi=1 / 2.977,
           pack_desc="2.977 m2 sheets", cut=0.08, waste=0.03, density=600, k=0.13, mass=32.2, vol=0.054,
           carbon=0.45, lead=_lead(1, 0.5, 3), delivery="sheet_materials"),
        _m("chipboard_22", "Chipboard flooring P5 22 mm T&G (2400x600)", "sheet", "m2", "sheet",
           ppi=1 / 1.44, pack_desc="1.44 m2 sheets", cut=0.05, waste=0.03, density=650, k=0.13, mass=20.6,
           vol=0.032, carbon=0.50, lead=_lead(1, 0.5, 3), delivery="sheet_materials"),
        _m("plasterboard_12_5", "Gypsum plasterboard 12.5 mm (2400x1200)", "sheet", "m2", "sheet",
           ppi=1 / 2.88, pack_desc="2.88 m2 sheets", cut=0.08, waste=0.05, density=700, k=0.21, mass=25.2,
           vol=0.036, carbon=0.39, lead=_lead(1, 0.5, 2), delivery="sheet_materials"),
        _m("plaster_hardwall_undercoat", "Gypsum undercoat plaster 11 mm", "plaster", "m2", "bag", ppi=1 / 2.6,
           pack_desc="25 kg bag covering ~2.6 m2 at 11 mm", waste=0.10, density=1100, k=0.40, mass=25,
           vol=0.025, carbon=0.13, lead=_lead(1, 0.5, 2), delivery="general"),
        _m("skim_plaster", "Gypsum finish (skim) plaster 2 mm", "plaster", "m2", "bag", ppi=0.1,
           pack_desc="25 kg bag covering ~10 m2 at 2 mm", waste=0.10, density=1100, k=0.40, mass=25,
           vol=0.025, carbon=0.13, lead=_lead(1, 0.5, 2), delivery="general"),
        # -------------------------------------------------------- membranes
        _m("breather_membrane", "Breather membrane (walls)", "membrane", "m2", "roll", ppi=1 / 50,
           pack_desc="50 m2 rolls", cut=0.10, waste=0.03, mass=6.5, vol=0.05, carbon=2.5,
           lead=_lead(1, 0.5, 2), delivery="general"),
        _m("vcl_polythene", "Polythene vapour control layer", "membrane", "m2", "roll", ppi=1 / 50,
           pack_desc="50 m2 rolls", cut=0.10, waste=0.05, mass=6.0, vol=0.04, carbon=2.3,
           lead=_lead(1, 0.5, 2), delivery="general"),
        # ---------------------------------------------------------- roofing
        _m("roof_tile_concrete", "Interlocking concrete roof tile", "roofing", "nr", "nr", pack=240,
           pack_desc="pallet of 240 tiles", cut=0.03, waste=0.03, density=2100, mass=4.4, vol=0.0035,
           carbon=0.15, lead=_lead(3, 2, 6), delivery="roofing"),
        _m("ridge_tile", "Concrete ridge / hip tile (450 mm cover)", "roofing", "nr", "nr", cut=0.05,
           waste=0.03, mass=5.0, vol=0.006, carbon=0.15, lead=_lead(3, 2, 6), delivery="roofing"),
        _m("roof_underlay", "Breathable roof underlay", "membrane", "m2", "roll", ppi=1 / 50,
           pack_desc="50 m2 rolls", cut=0.15, waste=0.03, mass=7.5, vol=0.05, carbon=2.5,
           lead=_lead(1, 0.5, 2), delivery="roofing", notes="Cutting allowance covers laps."),
        _m("dry_verge_unit", "Dry verge unit", "roofing", "nr", "nr", waste=0.03, mass=0.6, vol=0.004,
           carbon=3.0, lead=_lead(2, 1, 4), delivery="roofing"),
        _m("lead_flashing_code4", "Lead flashing code 4 (300 mm girth)", "roofing", "m", "roll", ppi=1 / 6,
           pack_desc="6 m rolls", cut=0.10, waste=0.05, density=11340, mass=36.7, vol=0.01, carbon=1.7,
           lead=_lead(1, 0.5, 2), delivery="roofing"),
        _m("single_ply_membrane", "Single-ply roof membrane", "roofing", "m2", "roll", ppi=1 / 30,
           pack_desc="30 m2 rolls", cut=0.10, waste=0.05, mass=45, vol=0.08, carbon=3.0,
           lead=_lead(2, 1, 4), delivery="roofing", notes="Cutting allowance covers laps and upstands."),
        # ------------------------------------------------------------ steel
        _m("steel_beam", "Structural steel sections (allowance only)", "steel", "kg", "kg", waste=0.02,
           density=7850, k=50.0, mass=1.0, vol=0.000127, carbon=1.5, lead=_lead(3, 2, 4), delivery="steel",
           notes="Used by the structural steel allowance; no member sizing performed."),
        # -------------------------------------------------- windows & doors
        _m("window_upvc_dg", "uPVC double-glazed window unit (per m2 of unit)", "windows_doors", "m2", "m2",
           pack=0.01, pack_desc="made to measure; no pack rounding (0.01 m2 resolution)", mass=30, vol=0.12,
           carbon=3.0, lead=_lead(8, 6, 10), delivery="windows_doors"),
        _m("window_alu_tg", "Aluminium triple-glazed window unit (per m2 of unit)", "windows_doors", "m2",
           "m2", pack=0.01, pack_desc="made to measure; no pack rounding (0.01 m2 resolution)", mass=40,
           vol=0.12, carbon=6.0, lead=_lead(10, 8, 14), delivery="windows_doors"),
        _m("door_composite", "Composite external door set", "windows_doors", "nr", "nr", mass=65, vol=0.25,
           carbon=3.0, lead=_lead(6, 4, 8), delivery="windows_doors"),
        _m("garage_door_sectional", "Steel sectional garage door", "windows_doors", "nr", "nr", mass=85,
           vol=0.6, carbon=2.5, lead=_lead(4, 3, 6), delivery="windows_doors"),
    ]


# =============================================================================
# Assemblies
# =============================================================================
def _l(name: str, material_id: str, role: LayerRole, thickness: float = 0.0, *, rule: str = "area",
       measure: str = "element_area", factor: float = 1.0, note: str = "", hours: float = 0.0,
       trade: str = "general", thermal: Optional[bool] = None, bridging: Optional[LayerBridging] = None,
       allowance: bool = False) -> AssemblyLayer:
    return AssemblyLayer(name=name, material_id=material_id, role=role, thickness_m=thickness,
                         quantity_rule=rule, measure=measure, factor=factor, factor_note=note,
                         bridging=bridging, in_thermal_calc=(thickness > 0) if thermal is None else thermal,
                         labour_hours_per_unit=hours, trade=trade, is_allowance=allowance)


_BRICKS_PER_M2 = 60.0
_BLOCKS_PER_M2 = SUBSTRUCTURE_RULES.blocks_per_m2
_INFO = "Generic indicative build-up for comparison; not a specification or design."


def _brick_layers() -> list[AssemblyLayer]:
    R, T = LayerRole, "bricklaying"
    return [
        _l("Facing brick outer leaf 102.5 mm", "facing_brick", R.EXTERNAL_FINISH, 0.1025, rule="per_area",
           factor=_BRICKS_PER_M2, note="215x65 bricks with 10 mm joints ≈ 59.3/m2, taken as 60/m2",
           hours=0.022, trade=T),
        _l("Mortar to brickwork", "mortar", R.FIXINGS, rule="per_area", factor=0.022,
           note="≈ 0.022 m3 mortar per m2 of half-brick wall", trade=T),
    ]


def _lintel_layers(trade: str = "bricklaying", note: str = "") -> list[AssemblyLayer]:
    R = LayerRole
    n = "Quantity only - lintel type and load capacity are not selected (requires design)." + (
        f" {note}" if note else "")
    return [
        _l("Steel lintels over openings (clear span)", "steel_lintel", R.STRUCTURE, rule="per_length",
           measure="opening_head_length", factor=1.0, note=n, hours=0.5, trade=trade),
        _l("Steel lintel end bearings (2 x 150 mm per opening)", "steel_lintel", R.STRUCTURE, rule="per_item",
           measure="opening_count", factor=0.30, note="0.30 m extra lintel length per opening", hours=0.5,
           trade=trade),
    ]


def _closer_layers(trade: str) -> list[AssemblyLayer]:
    R = LayerRole
    return [
        _l("Cavity closers at reveals", "cavity_closer", R.FIXINGS, rule="per_length",
           measure="opening_reveal_length", factor=1.0, hours=0.05, trade=trade),
        _l("Cavity closers at sills", "cavity_closer", R.FIXINGS, rule="per_length",
           measure="opening_sill_length", factor=1.0, hours=0.05, trade=trade),
    ]


def _tf_core_layers(stud_note: str) -> list[AssemblyLayer]:
    R = LayerRole
    return [
        _l("Breather membrane", "breather_membrane", R.MEMBRANE, hours=0.03, trade="carpentry"),
        _l("OSB/3 sheathing 9 mm", "osb_9", R.SHEATHING, 0.009, hours=0.08, trade="carpentry"),
        _l("Timber studs 140x38 @ 600 crs incl. plates and noggings", "timber_stud_140x38", R.STRUCTURE,
           rule="per_area", factor=2.6, note=stud_note, hours=0.06, trade="carpentry", thermal=False),
        _l("Mineral wool between studs 140 mm", "mineral_wool_140_stud", R.INSULATION, 0.14, hours=0.08,
           trade="carpentry", bridging=LayerBridging(material_id="timber_stud_140x38", fraction=0.15)),
    ]


def _tf_lining_layers() -> list[AssemblyLayer]:
    R = LayerRole
    return [
        _l("Vapour control layer", "vcl_polythene", R.MEMBRANE, measure="internal_face_area", hours=0.03,
           trade="drylining"),
        _l("Plasterboard 12.5 mm, taped and jointed", "plasterboard_12_5", R.INTERNAL_FINISH, 0.0125,
           measure="internal_face_area", hours=0.35, trade="drylining"),
    ]


_SEP_FACE_A = "Side A = face towards the block the wall is measured on; finished only if that block is heated."
_SEP_FACE_B = "Side B = face towards the neighbouring block(s); finished only towards heated blocks."

_STUD_NOTE = ("Studs @ 600 crs ≈ 1.67 m/m2 plus head/sole plates, noggings and opening framing ≈ 2.6 m/m2 "
              "(generic; frame not designed)")


def _assemblies() -> list[Assembly]:
    R, E = LayerRole, ElementType
    out: list[Assembly] = []

    # ------------------------------------------------------- external walls
    out.append(Assembly(
        assembly_id="ew_masonry_cavity", name="Masonry cavity wall (brick / full-fill mineral wool / aircrete "
        "block / plaster)", element=E.EXTERNAL_WALL, structural_system="masonry cavity wall, loadbearing inner leaf",
        information_level=_INFO,
        description="Facing brick outer leaf, 100 mm cavity fully filled with mineral wool batts, 100 mm "
                    "aircrete inner leaf, two-coat gypsum plaster.",
        layers=[
            *_brick_layers(),
            _l("Full-fill mineral wool cavity batts 100 mm", "mineral_wool_100_cavity", R.INSULATION, 0.10,
               hours=0.10, trade="bricklaying"),
            _l("Aircrete block inner leaf 100 mm", "aerated_concrete_block_100", R.STRUCTURE, 0.10,
               rule="per_area", factor=_BLOCKS_PER_M2, note="440x215 blocks with 10 mm joints = 9.88/m2",
               hours=0.045, trade="bricklaying"),
            _l("Mortar to blockwork", "mortar", R.FIXINGS, rule="per_area",
               factor=SUBSTRUCTURE_RULES.mortar_m3_per_m2_block, note="≈ 0.009 m3 mortar per m2 of 100 mm "
               "blockwork", trade="bricklaying"),
            _l("Wall ties (general field)", "wall_ties", R.FIXINGS, rule="per_area", factor=2.5,
               note="900 mm horizontal x 450 mm vertical ≈ 2.5/m2", hours=0.01, trade="bricklaying"),
            _l("Additional wall ties at reveals", "wall_ties", R.FIXINGS, rule="per_length",
               measure="opening_reveal_length", factor=3.33, note="at 300 mm vertical centres", hours=0.01,
               trade="bricklaying"),
            *_lintel_layers(),
            *_closer_layers("bricklaying"),
            _l("Gypsum undercoat plaster 11 mm", "plaster_hardwall_undercoat", R.INTERNAL_FINISH, 0.011,
               measure="internal_face_area", hours=0.30, trade="plastering"),
            _l("Finish (skim) plaster 2 mm", "skim_plaster", R.INTERNAL_FINISH, 0.002,
               measure="internal_face_area", hours=0.20, trade="plastering"),
        ]))
    out.append(Assembly(
        assembly_id="ew_timber_frame_brick", name="Timber frame with brick outer leaf", element=E.EXTERNAL_WALL,
        structural_system="timber frame (loadbearing studs); brick outer leaf is cladding",
        information_level=_INFO,
        description="Facing brick outer leaf, 50 mm cavity, breather membrane, 9 mm OSB sheathing, 140 mm "
                    "studs with mineral wool, VCL, 12.5 mm plasterboard. Looks like brick from outside.",
        layers=[
            *_brick_layers(),
            _l("Cavity 50 mm (thermal only)", "air_cavity_50", R.CAVITY, 0.05,
               note="Unventilated cavity, R = 0.18 m2K/W; nothing purchased"),
            _l("Timber-frame wall ties", "wall_ties", R.FIXINGS, rule="per_area", factor=4.4,
               note="600 mm horizontal (at studs) x 375 mm vertical ≈ 4.4/m2", hours=0.01, trade="bricklaying"),
            _l("Additional wall ties at reveals", "wall_ties", R.FIXINGS, rule="per_length",
               measure="opening_reveal_length", factor=3.33, note="at 300 mm vertical centres", hours=0.01,
               trade="bricklaying"),
            *_tf_core_layers(_STUD_NOTE),
            *_lintel_layers(note="Outer-leaf lintels only; frame headers are within the stud allowance."),
            *_closer_layers("carpentry"),
            *_tf_lining_layers(),
        ]))
    out.append(Assembly(
        assembly_id="ew_timber_frame_clad", name="Timber frame with ventilated timber cladding",
        element=E.EXTERNAL_WALL, structural_system="timber frame (loadbearing studs)", information_level=_INFO,
        rse=0.13,
        description="Larch boards on 25x50 battens (ventilated cavity), breather membrane, 9 mm OSB, 140 mm "
                    "studs with mineral wool, VCL, 12.5 mm plasterboard. Rse = 0.13 because layers outside the "
                    "ventilated cavity are excluded from the thermal calculation.",
        layers=[
            _l("Larch cladding boards 20 mm", "larch_cladding", R.CLADDING, 0.020, hours=0.6, trade="carpentry",
               thermal=False),
            _l("Vertical battens 25x50 @ 600 crs (ventilated cavity)", "timber_batten_25x50", R.BATTENS, 0.025,
               rule="per_area", factor=1.8, note="1.67 m/m2 at 600 crs plus extra at openings and corners",
               hours=0.05, trade="carpentry", thermal=False),
            *_tf_core_layers(_STUD_NOTE),
            _l("Cladding trims at reveals and sills", "timber_batten_25x50", R.FIXINGS, rule="per_length",
               measure="opening_reveal_length", factor=1.0, hours=0.15, trade="carpentry"),
            *_tf_lining_layers(),
        ]))

    # --------------------------------------------------- separating wall
    out.append(Assembly(
        assembly_id="sw_masonry_separating", name="Masonry cavity wall between blocks", element=E.SEPARATING_WALL,
        structural_system="masonry cavity wall", information_level=_INFO,
        description="Plaster, 100 mm dense block, 100 mm mineral wool, 100 mm dense block, plaster. Generic "
                    "wall between blocks of the building; any fire / acoustic separation requires design. "
                    "Plaster is measured only on faces towards heated blocks (side A faces the block the wall "
                    "is measured on, side B its neighbour); a face towards an unheated block such as a garage "
                    "gets no internal finish, as for external walls.",
        layers=[
            _l("Gypsum plaster side A (undercoat 11 mm)", "plaster_hardwall_undercoat", R.INTERNAL_FINISH, 0.011,
               measure="internal_face_area_a", note=_SEP_FACE_A, hours=0.30, trade="plastering"),
            _l("Finish (skim) plaster side A", "skim_plaster", R.INTERNAL_FINISH, 0.002,
               measure="internal_face_area_a", note=_SEP_FACE_A, hours=0.20, trade="plastering"),
            _l("Dense block leaf A 100 mm", "dense_concrete_block_100", R.STRUCTURE, 0.10, rule="per_area",
               factor=_BLOCKS_PER_M2, hours=0.06, trade="bricklaying"),
            _l("Mineral wool cavity batts 100 mm", "mineral_wool_100_cavity", R.INSULATION, 0.10, hours=0.10,
               trade="bricklaying"),
            _l("Dense block leaf B 100 mm", "dense_concrete_block_100", R.STRUCTURE, 0.10, rule="per_area",
               factor=_BLOCKS_PER_M2, hours=0.06, trade="bricklaying"),
            _l("Mortar to blockwork (two leaves)", "mortar", R.FIXINGS, rule="per_area",
               factor=2 * SUBSTRUCTURE_RULES.mortar_m3_per_m2_block, trade="bricklaying"),
            _l("Wall ties", "wall_ties", R.FIXINGS, rule="per_area", factor=2.5, hours=0.01, trade="bricklaying"),
            _l("Gypsum plaster side B (undercoat 11 mm)", "plaster_hardwall_undercoat", R.INTERNAL_FINISH, 0.011,
               measure="internal_face_area_b", note=_SEP_FACE_B, hours=0.30, trade="plastering"),
            _l("Finish (skim) plaster side B", "skim_plaster", R.INTERNAL_FINISH, 0.002,
               measure="internal_face_area_b", note=_SEP_FACE_B, hours=0.20, trade="plastering"),
        ]))

    # --------------------------------------------------------- partitions
    out.append(Assembly(
        assembly_id="ip_timber_stud", name="Timber stud partition, plasterboard both sides",
        element=E.INTERNAL_PARTITION, structural_system="non-loadbearing timber stud (assumed)",
        information_level=_INFO,
        description="89x38 studs @ 600 crs with 12.5 mm plasterboard each side, taped and jointed. Quantities "
                    "are an allowance: no internal layout is observed.",
        layers=[
            _l("Plasterboard 12.5 mm side A", "plasterboard_12_5", R.INTERNAL_FINISH, 0.0125, hours=0.35,
               trade="drylining"),
            _l("Timber studs 89x38 @ 600 crs incl. plates and noggings", "timber_stud_89x38", R.STRUCTURE, 0.089,
               rule="per_area", factor=2.6, note="generic stud allowance per m2 of partition", hours=0.05,
               trade="carpentry", thermal=False),
            _l("Plasterboard 12.5 mm side B", "plasterboard_12_5", R.INTERNAL_FINISH, 0.0125, hours=0.35,
               trade="drylining"),
        ]))

    # ------------------------------------------------------------- floors
    out.append(Assembly(
        assembly_id="gf_concrete_slab", name="Ground-bearing concrete slab with PIR below slab",
        element=E.GROUND_FLOOR, structural_system="ground-bearing slab (assumed; requires design)",
        information_level=_INFO, rsi=0.17, rse=0.04,
        description="150 mm Type 1, 25 mm sand blinding, DPM, 100 mm PIR, 100 mm C25 slab, 65 mm screed, 25 mm "
                    "PIR perimeter upstand. Any reinforcement / anti-crack mesh is not quantified (design).",
        notes="Ground-floor heat loss should use a ground-contact method (e.g. ISO 13370), not layers alone.",
        layers=[
            _l("Type 1 sub-base 150 mm compacted", "hardcore_type1", R.STRUCTURE, 0.15, rule="volume",
               hours=0.5, trade="groundworks", thermal=False),
            _l("Sand blinding 25 mm", "sand_blinding", R.STRUCTURE, 0.025, rule="volume", hours=0.5,
               trade="groundworks", thermal=False),
            _l("Damp-proof membrane 1200 gauge", "dpm_1200g", R.MEMBRANE, hours=0.03, trade="groundworks"),
            _l("PIR insulation 100 mm below slab", "pir_100", R.INSULATION, 0.10, hours=0.06,
               trade="groundworks"),
            _l("Concrete slab C25 100 mm", "concrete_c25", R.SLAB, 0.10, rule="volume", hours=1.2,
               trade="groundworks"),
            _l("Sand-cement screed 65 mm", "screed_sand_cement", R.SCREED, 0.065, rule="volume", hours=2.3,
               trade="plastering"),
            _l("PIR perimeter edge upstand 25 mm", "pir_25", R.INSULATION, rule="per_length", measure="perimeter",
               factor=0.165, note="upstand depth = slab 100 + screed 65 mm → 0.165 m2 per m of perimeter "
               "(external-face perimeter; slight overestimate accepted)", hours=0.05, trade="groundworks",
               thermal=False),
        ]))
    out.append(Assembly(
        assembly_id="if_timber_joist", name="Timber I-joist intermediate floor", element=E.INTERMEDIATE_FLOOR,
        structural_system="engineered timber joists (layout and depth not designed)", information_level=_INFO,
        rsi=0.10, rse=0.10,
        description="22 mm chipboard on I-joists (assumed 220 mm zone) with 12.5 mm plasterboard ceiling below.",
        layers=[
            _l("Chipboard flooring P5 22 mm", "chipboard_22", R.INTERNAL_FINISH, 0.022, hours=0.25,
               trade="carpentry"),
            _l("Engineered I-joists @ 400 crs incl. rim and trimmers (220 mm zone, not designed)", "floor_joist_i",
               R.STRUCTURE, 0.22, rule="per_area", factor=2.8, note="2.5 m/m2 at 400 crs plus rim board and "
               "trimmers; indicative allowance, joist layout and size require design", hours=0.12,
               trade="carpentry", thermal=False, allowance=True),
            _l("Plasterboard ceiling 12.5 mm, taped and jointed", "plasterboard_12_5", R.INTERNAL_FINISH, 0.0125,
               hours=0.40, trade="drylining"),
        ]))

    # -------------------------------------------------------------- roofs
    out.append(Assembly(
        assembly_id="pr_tiled_cold", name="Pitched cold roof, concrete tiles on trussed rafters",
        element=E.PITCHED_ROOF, structural_system="trussed rafters (manufacturer-designed)",
        information_level=_INFO, rsi=0.10, rse=0.04,
        description="Interlocking concrete tiles, battens, breathable underlay, trussed rafters @ 600 crs; "
                    "ventilated loft with 300 mm mineral wool on the ceiling, VCL and plasterboard ceiling.",
        notes="Thermal layers are the ceiling layers (cold roof). Truss count is per run along the ridge "
              "direction at 600 mm centres; bracing, straps and girder trusses are not quantified.",
        layers=[
            _l("Interlocking concrete tiles", "roof_tile_concrete", R.ROOF_COVERING, rule="per_area",
               factor=9.7, note="≈ 9.7 tiles/m2 at ~340 mm gauge (generic)", hours=0.036, trade="roofing"),
            _l("Tiling battens 25x50", "timber_batten_25x50", R.BATTENS, rule="per_area", factor=3.0,
               note="≈ 2.9 m/m2 at ~340 mm gauge plus eaves/ridge extras", hours=0.02, trade="roofing"),
            _l("Breathable roof underlay", "roof_underlay", R.MEMBRANE, hours=0.03, trade="roofing"),
            _l("Trussed rafters @ 600 crs", "trussed_rafter", R.STRUCTURE, rule="per_length",
               measure="truss_run_length", factor=1 / 0.6, note="1 truss per 0.6 m of run along the ridge "
               "direction (indicative count, not a truss layout)", hours=1.5, trade="carpentry"),
            _l("Ridge tiles", "ridge_tile", R.ROOF_COVERING, rule="per_length", measure="ridge_length",
               factor=1 / 0.45, note="450 mm cover", hours=0.22, trade="roofing"),
            _l("Hip tiles (ridge-type)", "ridge_tile", R.ROOF_COVERING, rule="per_length", measure="hip_length",
               factor=1 / 0.45, note="450 mm cover", hours=0.30, trade="roofing"),
            _l("Fascia and soffit", "fascia_soffit_timber", R.EXTERNAL_FINISH, rule="per_length",
               measure="eaves_length", factor=1.0, hours=0.5, trade="carpentry"),
            _l("Dry verge units", "dry_verge_unit", R.ROOF_COVERING, rule="per_length", measure="verge_length",
               factor=1 / 0.34, note="one unit per tile course (~340 mm)", hours=0.08, trade="roofing"),
            _l("Abutment flashing", "lead_flashing_code4", R.ROOF_COVERING, rule="per_length",
               measure="abutment_length", factor=1.0, hours=0.6, trade="roofing"),
            _l("Loft insulation 300 mm (100 between ties + 200 over)", "mineral_wool_300_loft", R.INSULATION, 0.30,
               measure="ceiling_area", note="ceiling-tie bridging of the lower layer neglected (simplification)",
               hours=0.06, trade="general"),
            _l("Vapour control layer at ceiling", "vcl_polythene", R.MEMBRANE, measure="ceiling_area", hours=0.03,
               trade="drylining"),
            _l("Plasterboard ceiling 12.5 mm, taped and jointed", "plasterboard_12_5", R.INTERNAL_FINISH, 0.0125,
               measure="ceiling_area", hours=0.40, trade="drylining"),
        ]))
    out.append(Assembly(
        assembly_id="fr_warm_deck", name="Flat warm-deck roof, single ply on PIR on OSB deck",
        element=E.FLAT_ROOF, structural_system="timber joists (layout and size not designed)",
        information_level=_INFO, rsi=0.10, rse=0.04,
        description="Single-ply membrane, 100 mm PIR, VCL, 18 mm OSB deck on timber joists, plasterboard ceiling.",
        notes="Insulation thickness is illustrative, not designed for a target U-value. Falls not modelled.",
        layers=[
            _l("Single-ply membrane", "single_ply_membrane", R.ROOF_COVERING, hours=0.25, trade="roofing"),
            _l("PIR insulation 100 mm (warm deck)", "pir_100", R.INSULATION, 0.10, hours=0.08, trade="roofing"),
            _l("Vapour control layer", "vcl_polythene", R.MEMBRANE, hours=0.03, trade="roofing"),
            _l("OSB/3 deck 18 mm", "osb_18", R.SHEATHING, 0.018, hours=0.10, trade="carpentry"),
            _l("Flat roof joists @ 400 crs (generic C24, not designed)", "timber_joist_c24", R.STRUCTURE, 0.195,
               rule="per_area", factor=2.6, note="2.5 m/m2 at 400 crs plus trimmers; indicative allowance, "
               "member size requires design", hours=0.10, trade="carpentry", thermal=False, allowance=True),
            _l("Plasterboard ceiling 12.5 mm, taped and jointed", "plasterboard_12_5", R.INTERNAL_FINISH, 0.0125,
               measure="ceiling_area", hours=0.40, trade="drylining"),
            _l("Roof edge trim / fascia", "fascia_soffit_timber", R.EXTERNAL_FINISH, rule="per_length",
               measure="eaves_length", factor=1.0, hours=0.4, trade="roofing"),
            _l("Abutment upstand flashing", "lead_flashing_code4", R.ROOF_COVERING, rule="per_length",
               measure="abutment_length", factor=1.0, hours=0.6, trade="roofing"),
        ]))

    # ---------------------------------------------------- windows & doors
    out.append(Assembly(
        assembly_id="win_upvc_dg", name="uPVC double-glazed windows", element=E.WINDOW, u_value_override=1.4,
        structural_system="n/a (unit)", information_level=_INFO,
        description="Per m2 of window unit; assumed whole-window U-value 1.4 W/m2K (not a declared product value).",
        layers=[_l("uPVC double-glazed window units", "window_upvc_dg", R.UNIT, hours=1.2, trade="glazing",
                   thermal=False)]))
    out.append(Assembly(
        assembly_id="win_alu_tg", name="Aluminium triple-glazed windows", element=E.WINDOW, u_value_override=1.2,
        structural_system="n/a (unit)", information_level=_INFO,
        description="Per m2 of window unit; assumed whole-window U-value 1.2 W/m2K (not a declared product value).",
        layers=[_l("Aluminium triple-glazed window units", "window_alu_tg", R.UNIT, hours=1.4, trade="glazing",
                   thermal=False)]))
    out.append(Assembly(
        assembly_id="door_composite", name="Composite external door set", element=E.EXTERNAL_DOOR,
        u_value_override=1.4, structural_system="n/a (unit)", information_level=_INFO,
        description="Per item; assumed U-value 1.4 W/m2K.",
        layers=[_l("Composite external door set", "door_composite", R.UNIT, rule="per_item",
                   measure="opening_count", hours=4.0, trade="carpentry", thermal=False)]))
    out.append(Assembly(
        assembly_id="gdoor_steel_sectional", name="Steel sectional garage door", element=E.GARAGE_DOOR,
        u_value_override=3.0, structural_system="n/a (unit)", information_level=_INFO,
        description="Per item; assumed U-value 3.0 W/m2K.",
        layers=[_l("Steel sectional garage door", "garage_door_sectional", R.UNIT, rule="per_item",
                   measure="opening_count", hours=8.0, trade="general", thermal=False)]))
    return out


# =============================================================================
# Foundations
# =============================================================================
_FDN_NOTE = "Indicative option for costing only - requires site investigation and engineer's design."


def _a(v: float, unit: str, lo: float, hi: float, note: str = "") -> TrackedValue:
    return assumed(v, unit, low=lo, high=hi, source=LIBRARY_SOURCE, note=note)


def _foundations() -> list[FoundationOption]:
    frac = lambda: _a(0.20, "fraction", 0.10, 0.35, "internal loadbearing wall length / external perimeter")  # noqa: E731
    return [
        FoundationOption(
            option_id="fdn_trench_fill", name="Trench-fill concrete foundation", kind=FoundationKind.TRENCH_FILL,
            trench_width_m=_a(0.60, "m", 0.45, 0.75), trench_depth_m=_a(1.0, "m", 0.9, 1.2),
            concrete_depth_m=_a(0.85, "m", 0.75, 1.05), internal_loadbearing_fraction=frac(),
            suitable_ground=["good_clay_or_gravel"],
            notes=f"{_FDN_NOTE} Concrete to within ~150 mm of ground; masonry from there to DPC."),
        FoundationOption(
            option_id="fdn_strip", name="Strip foundation with substructure blockwork", kind=FoundationKind.STRIP,
            trench_width_m=_a(0.60, "m", 0.45, 0.75), trench_depth_m=_a(1.0, "m", 0.9, 1.2),
            concrete_depth_m=_a(0.25, "m", 0.225, 0.30), internal_loadbearing_fraction=frac(),
            suitable_ground=["good_clay_or_gravel"],
            notes=f"{_FDN_NOTE} Blockwork from top of strip to DPC; any cavity fill below DPC not quantified."),
        FoundationOption(
            option_id="fdn_deep_trench_fill", name="Deep trench-fill foundation (variable made ground)",
            kind=FoundationKind.TRENCH_FILL, trench_width_m=_a(0.60, "m", 0.45, 0.75),
            trench_depth_m=_a(1.5, "m", 1.2, 2.0), concrete_depth_m=_a(1.35, "m", 1.05, 1.85),
            internal_loadbearing_fraction=frac(), suitable_ground=["variable_made_ground"],
            notes=f"{_FDN_NOTE} Depth is an assumption for variable made ground; trench support not quantified."),
        FoundationOption(
            option_id="fdn_raft", name="Reinforced raft with thickened edges", kind=FoundationKind.RAFT,
            trench_width_m=_a(0.60, "m", 0.45, 0.80, "thickened edge width"),
            trench_depth_m=_a(0.45, "m", 0.35, 0.60, "thickened edge depth"),
            concrete_depth_m=_a(0.45, "m", 0.35, 0.60, "thickened edge concrete depth"),
            raft_thickness_m=_a(0.25, "m", 0.20, 0.30), internal_loadbearing_fraction=frac(),
            suitable_ground=["poor_soft_ground", "variable_made_ground"],
            notes=f"{_FDN_NOTE} The ground-floor assembly's slab is taken as part of the raft; only the extra "
                  "raft thickness is added. Reinforcement is a labelled allowance only (no schedule)."),
        FoundationOption(
            option_id="fdn_piled_allowance", name="Piles and ground beams (allowance)",
            kind=FoundationKind.PILED_ALLOWANCE, trench_width_m=_a(0.45, "m", 0.35, 0.60, "ground beam width"),
            trench_depth_m=_a(0.60, "m", 0.45, 0.75, "ground beam depth"),
            concrete_depth_m=_a(0.60, "m", 0.45, 0.75, "ground beam concrete depth"),
            piles_per_m=_a(0.40, "nr/m", 0.30, 0.60, "piles per metre of loadbearing wall"),
            pile_length_m=_a(12.0, "m", 8.0, 18.0), internal_loadbearing_fraction=frac(),
            suitable_ground=["poor_soft_ground"],
            notes=f"{_FDN_NOTE} Allowance only: pile type, number, length and capacity require ground "
                  "investigation and a piling designer."),
    ]


# =============================================================================
# Allowances
# =============================================================================
def _allowances() -> list[AllowanceRule]:
    A = AllowanceRule
    fixed = lambda v, unit, note="": TrackedValue(value=v, unit=unit, basis=Basis.ASSUMED,  # noqa: E731
                                                  distribution=Distribution.FIXED, source=LIBRARY_SOURCE, note=note)
    return [
        A(allowance_id="structural_steel", element="2.1 Frame allowance",
          description="Structural steel / beam allowance - indicative allowance; no member sizing performed",
          cost_key="allow:structural_steel", unit="kg", basis_measure="per_m2_gia",
          quantity_per=_a(3.0, "kg/m2", 0.0, 8.0), trade="general", labour_hours_per_unit=0.02,
          material_id="steel_beam"),
        A(allowance_id="staircase", element="2.4 Stairs", description="Timber staircase per dwelling (allowance)",
          cost_key="allow:staircase", unit="nr", basis_measure="per_dwelling", quantity_per=fixed(1.0, "nr"),
          trade="carpentry", labour_hours_per_unit=14.0, min_storeys=2),
        A(allowance_id="internal_doors", element="2.7 Internal walls & partitions",
          description="Internal door sets (allowance per m2 GIA; no layout observed)", cost_key="allow:internal_doors",
          unit="nr", basis_measure="per_m2_gia", quantity_per=_a(0.08, "nr/m2", 0.06, 0.10),
          trade="carpentry", labour_hours_per_unit=2.5),
        A(allowance_id="floor_finishes", element="3 Internal finishes",
          description="Floor finishes (allowance per m2 GIA)", cost_key="allow:floor_finishes", unit="m2",
          basis_measure="per_m2_gia", quantity_per=_a(0.95, "m2/m2", 0.85, 1.0), trade="general",
          labour_hours_per_unit=0.30),
        A(allowance_id="decoration", element="3 Internal finishes",
          description="Decoration of finished walls and ceilings (allowance per m2 of finishable area)",
          cost_key="allow:decoration", unit="m2", basis_measure="per_m2_finishable",
          quantity_per=fixed(1.0, "m2/m2"), trade="decorating", labour_hours_per_unit=0.15),
        A(allowance_id="kitchen", element="4 Fittings", description="Kitchen fit-out per dwelling (allowance)",
          cost_key="allow:kitchen", unit="nr", basis_measure="per_dwelling", quantity_per=fixed(1.0, "nr"),
          trade="carpentry", labour_hours_per_unit=40.0),
        A(allowance_id="sanitaryware", element="5 Services",
          description="Sanitaryware per bathroom (allowance)", cost_key="allow:sanitaryware", unit="nr",
          basis_measure="per_bathroom", quantity_per=fixed(1.0, "nr"), trade="plumbing",
          labour_hours_per_unit=14.0),
        A(allowance_id="plumbing_heating", element="5 Services",
          description="Plumbing and heating system per dwelling - system type not determined (allowance)",
          cost_key="allow:plumbing_heating", unit="nr", basis_measure="per_dwelling",
          quantity_per=fixed(1.0, "nr"), trade="plumbing", labour_hours_per_unit=110.0,
          notes="Heating system type (boiler / heat pump) is not determined from images."),
        A(allowance_id="electrical_installation", element="5 Services",
          description="Electrical installation (allowance per m2 GIA; no layout designed)",
          cost_key="allow:electrical_installation", unit="m2", basis_measure="per_m2_gia",
          quantity_per=fixed(1.0, "m2/m2"), trade="electrical", labour_hours_per_unit=1.0),
    ]


# =============================================================================
# Public API
# =============================================================================
def default_library() -> AssemblyLibrary:
    """The bundled generic, illustrative library (see module docstring for its information level)."""
    return AssemblyLibrary(name="Aureom generic assemblies (illustrative)", version="1",
                           materials=_materials(), assemblies=_assemblies(), foundations=_foundations(),
                           allowances=_allowances())


_DEFAULTS = {
    "external_wall": "ew_masonry_cavity",
    "separating_wall": "sw_masonry_separating",
    "internal_partition": "ip_timber_stud",
    "ground_floor": "gf_concrete_slab",
    "intermediate_floor": "if_timber_joist",
    "pitched_roof": "pr_tiled_cold",
    "flat_roof": "fr_warm_deck",
    "window": "win_upvc_dg",
    "external_door": "door_composite",
    "garage_door": "gdoor_steel_sectional",
    FOUNDATION_KEY: "fdn_trench_fill",
}


def default_selection(library: Optional[AssemblyLibrary] = None) -> AssemblySelection:
    """Default construction hypothesis (masonry cavity, trench fill, tiled cold roof, ...).

    Every choice has basis ``ASSUMED``: construction is never established from appearance.
    Raises ``ValueError`` if ``library`` lacks one of the default ids.
    """
    lib = library or default_library()
    asm_ids = {a.assembly_id: a for a in lib.assemblies}
    fdn_ids = {f.option_id for f in lib.foundations}
    for key, aid in _DEFAULTS.items():
        if key == FOUNDATION_KEY:
            if aid not in fdn_ids:
                raise ValueError(f"default foundation option '{aid}' not in library '{lib.name}'")
        elif aid not in asm_ids or asm_ids[aid].element.value != key:
            raise ValueError(f"default {key} assembly '{aid}' not in library '{lib.name}'")
    return AssemblySelection(**_DEFAULTS, basis={k: Basis.ASSUMED for k in _DEFAULTS})


def _dim(unit: str) -> Optional[str]:
    try:
        return dimension(unit)
    except UnitError:
        return None


def validate_library(library: AssemblyLibrary) -> list[str]:
    """Static consistency checks; returns a list of problems (empty = consistent)."""
    problems: list[str] = []
    for kind, ids in (("material", [m.material_id for m in library.materials]),
                      ("assembly", [a.assembly_id for a in library.assemblies]),
                      ("foundation", [f.option_id for f in library.foundations]),
                      ("allowance", [a.allowance_id for a in library.allowances])):
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            problems.append(f"duplicate {kind} ids: {sorted(dup)}")
    mats = {m.material_id: m for m in library.materials}
    for m in library.materials:
        for u in (m.installed_unit, m.purchase_unit):
            if not is_known_unit(u):
                problems.append(f"material {m.material_id}: unknown unit '{u}'")
        if is_purchasable(m) and m.mass_per_purchase_unit_kg is None and m.density_kg_m3 is None:
            problems.append(f"material {m.material_id}: no mass data for logistics/carbon")
    rule_dims = {"area": "area", "volume": "volume"}
    for a in library.assemblies:
        allowed = MEASURES.get(a.element, set())
        for i, layer in enumerate(a.layers):
            where = f"assembly {a.assembly_id}[{i}] '{layer.name}'"
            mat = mats.get(layer.material_id)
            if mat is None:
                problems.append(f"{where}: unknown material '{layer.material_id}'")
                continue
            if layer.bridging and layer.bridging.material_id not in mats:
                problems.append(f"{where}: unknown bridging material '{layer.bridging.material_id}'")
            if layer.measure not in allowed:
                problems.append(f"{where}: measure '{layer.measure}' not available for {a.element.value}")
                continue
            mu = MEASURE_UNITS[layer.measure]
            need = {"area": "m2", "volume": "m2", "per_area": "m2", "per_length": "m", "per_item": "nr"}[
                layer.quantity_rule]
            if mu != need:
                problems.append(f"{where}: rule '{layer.quantity_rule}' needs a {need} measure, got '{mu}'")
            if layer.quantity_rule in rule_dims and _dim(mat.installed_unit) != rule_dims[layer.quantity_rule]:
                problems.append(f"{where}: rule '{layer.quantity_rule}' but material installed unit "
                                f"'{mat.installed_unit}'")
            if layer.quantity_rule == "volume" and layer.thickness_m <= 0:
                problems.append(f"{where}: volume rule needs a positive thickness")
            if layer.in_thermal_calc and layer.thickness_m > 0 and not mat.conductivity_w_mk:
                problems.append(f"{where}: in thermal calc but material has no conductivity")
            if layer.trade not in TRADES:
                problems.append(f"{where}: trade '{layer.trade}' not in {TRADES}")
    for f in library.foundations:
        if f.concrete_material_id not in mats:
            problems.append(f"foundation {f.option_id}: unknown concrete material '{f.concrete_material_id}'")
        for name in ("trench_width_m", "trench_depth_m", "concrete_depth_m"):
            tv = getattr(f, name)
            if tv.value is not None and tv.value < 0:
                problems.append(f"foundation {f.option_id}: negative {name}")
        if (f.trench_depth_m.value is not None and f.concrete_depth_m.value is not None
                and f.concrete_depth_m.value > f.trench_depth_m.value + 1e-9):
            problems.append(f"foundation {f.option_id}: concrete deeper than trench")
        if f.kind == FoundationKind.PILED_ALLOWANCE and (f.piles_per_m is None or f.pile_length_m is None):
            problems.append(f"foundation {f.option_id}: piled option needs piles_per_m and pile_length_m")
        if f.kind == FoundationKind.RAFT and f.raft_thickness_m is None:
            problems.append(f"foundation {f.option_id}: raft option needs raft_thickness_m")
    for r in library.allowances:
        if not r.cost_key.startswith("allow:"):
            problems.append(f"allowance {r.allowance_id}: cost key should start with 'allow:'")
        if not r.element.split(" ", 1)[0].replace(".", "").isdigit():
            problems.append(f"allowance {r.allowance_id}: element '{r.element}' should start with a code")
        if r.material_id and r.material_id not in mats:
            problems.append(f"allowance {r.allowance_id}: unknown material '{r.material_id}'")
        if r.trade not in TRADES:
            problems.append(f"allowance {r.allowance_id}: trade '{r.trade}' not in {TRADES}")
    sr = SUBSTRUCTURE_RULES
    for mid in (sr.block_material_id, sr.mortar_material_id, sr.reinforcement_material_id):
        if mid not in mats:
            problems.append(f"substructure rules: unknown material '{mid}'")
    return problems


def cost_keys(library: AssemblyLibrary, rules: SubstructureRules = SUBSTRUCTURE_RULES) -> dict[str, str]:
    """Every cost key the take-off can emit for this library -> its unit (for rate books)."""
    mats = {m.material_id: m for m in library.materials}
    used: set[str] = {layer.material_id for a in library.assemblies for layer in a.layers}
    used |= {f.concrete_material_id for f in library.foundations}
    used |= {rules.block_material_id, rules.mortar_material_id}
    out: dict[str, str] = {}
    for mid in sorted(used):
        m = mats.get(mid)
        if m is not None and is_purchasable(m):
            out[material_cost_key(mid)] = m.purchase_unit
    trades = {layer.trade for a in library.assemblies for layer in a.layers} | {
        r.trade for r in library.allowances} | {"groundworks", "bricklaying"}
    for t in sorted(trades):
        out[labour_cost_key(t)] = "hr"
    for r in library.allowances:
        out[r.cost_key] = r.unit
    out[rules.excavation_cost_key] = "m3"
    out[rules.disposal_cost_key] = "m3"
    kinds = {f.kind for f in library.foundations}
    if FoundationKind.PILED_ALLOWANCE in kinds:
        out[rules.piling_cost_key] = "m"
    if kinds & {FoundationKind.PILED_ALLOWANCE, FoundationKind.RAFT}:
        out[rules.reinforcement_cost_key] = "kg"
    return dict(sorted(out.items()))
