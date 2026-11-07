"""Element measures: the geometric quantities that assembly rules are applied to.

For every *element instance* of a twin this module returns named measures
(e.g. ``element_area``, ``ridge_length``) with value, unit, geometry
references, provenance basis and a human-readable formula.  Assembly layers
then turn a measure into an installed quantity (see ``takeoff``).

Element instances
-----------------
* external / separating walls, ground / intermediate floors, pitched / flat
  roofs: one instance **per block** (``instance_id = block_id``);
* windows / external doors / garage doors: one instance **per (element,
  assembly)** - openings are grouped by the assembly that applies to them
  (``Opening.assembly_id`` override, else the block / twin selection).
  ``instance_id = "all"`` when the assembly belongs to that opening element in
  the library, otherwise ``"all-<element>"`` (e.g. a door overridden with a
  window assembly, or an assembly id missing from the library), so every line
  id stays unique and does not depend on which other groups exist;
* internal partitions and foundations: one instance **per twin** (``"all"``).

Conventions and boundaries
--------------------------
* All values come from :class:`~housebuilder_vision.core.models.GeometryMetrics`
  (computed once for the twin; openings are deducted there exactly once).
  Opening areas per assembly are taken from the wall pieces the openings were
  deducted from, split pro rata to nominal twin sizes when a piece mixes
  assemblies, so window/door areas always reconcile with wall deductions.
  Windows / doors are counted from **deducted openings only**: an opening that
  metrics did not deduct (on a separating wall, outside the wall, or on a
  storey the block does not have) is excluded with a warning, never priced.
  ``metrics`` must have been computed from this twin's blocks and openings.
* ``internal_face_area`` of an external wall = rectangular zone (FFL to wall
  plate) minus openings, for **heated blocks only**; gable / monopitch infill
  above the plate is in the roof void and gets no internal finish.  Unheated
  blocks (garages) are assumed to have no internal wall finish and no finished /
  insulated ceiling (``ceiling_area = 0``) - select another assembly or mark
  the block heated to change this.
* ``lower_roof_void_area`` of an external wall = the part of the block's wall
  inside a lower neighbour's roof void (above the lower wall plate, under its
  roof line; see :func:`~housebuilder_vision.geometry.metrics.roof_void_wall_areas`).
  It is **included** in ``gross_area`` / ``element_area`` (conservative: the
  wall is still built and faced) and reported separately for review.
* Separating walls: ``internal_face_area_a`` is the face towards the block the
  wall is measured on (the lexicographically smaller block id), and
  ``internal_face_area_b`` the face towards its neighbour; a face is finished
  only when the block it faces is heated (same rule as external walls), so the
  wall between a house and an unheated garage is finished on the house side
  only.
* ``truss_run_length`` (pitched roofs) = footprint area / span, i.e. the
  wall-to-wall run along the ridge direction (gable: ridge length less verge
  overhangs; hip: full length, hip-end framing approximated by an equivalent
  count).  Truss counts derived from it are indicative, not a truss layout.
* Internal partitions are an **allowance**: no internal layout is observed.
  ``element_area = partition length allowance (m per m2 GIA) x heated GIA x
  clear storey height`` where clear height = floor-to-floor minus the selected
  intermediate-floor zone.  Garages / unheated blocks get no partitions.
* Foundations: ``trench_length = external ground perimeter at the wall
  centreline (P - 4 t n, n = connected footprint parts, no enclosed courtyards
  assumed) + separating-wall length (counted once) + internal loadbearing
  allowance (fraction x external perimeter)``.  T-junction overlaps are ignored.
  ``oversite_area`` = ground-storey GIA minus the trench plan inside it, so the
  top of the trenches is not excavated twice: external trench beyond the inner
  wall face (``max(t, (t + W) / 2)`` strip from the external face), separating
  trench beyond each wall face (``max(t_sep, W) / 2`` each side) and the whole
  internal loadbearing trench (``W x internal length``) are excluded.
* Basis of each measure = weakest basis of the TrackedValues it depends on
  (block dimensions, storeys, heights, roof pitch / overhangs, neighbour
  positions for blocks that share walls, openings, the external-wall assembly
  selection where wall thickness changes internal areas, allowance factors).

Nothing here sizes structural members, designs foundations or lays out
services; measures are concept-stage geometry, not a measured survey.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, NamedTuple, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..core.models import (
    AssemblyLibrary,
    AssemblySelection,
    Block,
    BlockMetrics,
    BuildingTwin,
    ElementType,
    GeometryMetrics,
    Opening,
    OpeningKind,
    QuantityStatus,
    RoofForm,
    RoofMetrics,
    TraceLink,
    WallPiece,
)
from ..core.provenance import BASIS_RANK, Basis, TrackedValue, assumed
from ..core.settings import ASSUMPTION_SOURCE, AssumptionLibrary
from ..geometry.footprint import GeometryError
from ..geometry.metrics import block_params_from_twin, ground_internal_area, roof_void_wall_areas

__all__ = [
    "FOUNDATION_KEY",
    "MEASURES",
    "FOUNDATION_MEASURES",
    "MEASURE_UNITS",
    "ELEMENT_CODES",
    "SUBSTRUCTURE_CODE",
    "OPENING_ELEMENT",
    "TakeoffAssumptions",
    "Measure",
    "ElementMeasures",
    "element_measures",
    "unresolved_instances",
    "selection_basis",
    "opening_element",
    "opening_instance_id",
    "off_storey_openings",
    "unknown_openings",
]

#: Key used for the foundation choice in ``AssemblySelection`` / instance lists.
FOUNDATION_KEY = "foundation"

#: Unit of every named measure.
MEASURE_UNITS: dict[str, str] = {
    "element_area": "m2",
    "gross_area": "m2",
    "internal_face_area": "m2",
    "internal_face_area_a": "m2",
    "internal_face_area_b": "m2",
    "lower_roof_void_area": "m2",
    "opening_head_length": "m",
    "opening_reveal_length": "m",
    "opening_sill_length": "m",
    "opening_count": "nr",
    "opening_perimeter": "m",
    "length": "m",
    "perimeter": "m",
    "partition_length": "m",
    "roof_plan": "m2",
    "ceiling_area": "m2",
    "ridge_length": "m",
    "hip_length": "m",
    "eaves_length": "m",
    "verge_length": "m",
    "abutment_length": "m",
    "truss_run_length": "m",
    # foundation (per twin)
    "ground_perimeter": "m",
    "centreline_perimeter": "m",
    "separating_wall_length": "m",
    "internal_loadbearing_length": "m",
    "trench_length": "m",
    "footprint_area": "m2",
    "ground_floor_area": "m2",
    "oversite_area": "m2",
    "average_ffl": "m",
}

#: Measures available to assembly layers, per element type (the contract for ``AssemblyLayer.measure``).
MEASURES: dict[ElementType, set[str]] = {
    ElementType.EXTERNAL_WALL: {"element_area", "gross_area", "internal_face_area", "opening_head_length",
                                "opening_reveal_length", "opening_sill_length", "opening_count",
                                "lower_roof_void_area"},
    ElementType.SEPARATING_WALL: {"element_area", "length", "internal_face_area_a", "internal_face_area_b"},
    ElementType.INTERNAL_PARTITION: {"element_area", "partition_length"},
    ElementType.GROUND_FLOOR: {"element_area", "perimeter"},
    ElementType.INTERMEDIATE_FLOOR: {"element_area"},
    ElementType.PITCHED_ROOF: {"element_area", "roof_plan", "ceiling_area", "ridge_length", "hip_length",
                               "eaves_length", "verge_length", "abutment_length", "truss_run_length"},
    ElementType.FLAT_ROOF: {"element_area", "roof_plan", "ceiling_area", "eaves_length", "abutment_length"},
    ElementType.WINDOW: {"element_area", "opening_count", "opening_perimeter"},
    ElementType.EXTERNAL_DOOR: {"element_area", "opening_count", "opening_perimeter"},
    ElementType.GARAGE_DOOR: {"element_area", "opening_count", "opening_perimeter"},
}

#: Measures of the per-twin foundation instance (used by the substructure take-off).
FOUNDATION_MEASURES: set[str] = {"ground_perimeter", "centreline_perimeter", "separating_wall_length",
                                 "internal_loadbearing_length", "trench_length", "footprint_area",
                                 "ground_floor_area", "oversite_area", "average_ffl"}

#: NRM1-inspired element code and name per element type (not a claim of NRM compliance).
ELEMENT_CODES: dict[ElementType, tuple[str, str]] = {
    ElementType.GROUND_FLOOR: ("1", "Substructure"),
    ElementType.INTERMEDIATE_FLOOR: ("2.2", "Upper floors"),
    ElementType.PITCHED_ROOF: ("2.3", "Roof"),
    ElementType.FLAT_ROOF: ("2.3", "Roof"),
    ElementType.EXTERNAL_WALL: ("2.5", "External walls"),
    ElementType.WINDOW: ("2.6", "Windows & external doors"),
    ElementType.EXTERNAL_DOOR: ("2.6", "Windows & external doors"),
    ElementType.GARAGE_DOOR: ("2.6", "Windows & external doors"),
    ElementType.INTERNAL_PARTITION: ("2.7", "Internal walls & partitions"),
    ElementType.SEPARATING_WALL: ("2.8", "Separating walls"),
}
SUBSTRUCTURE_CODE: tuple[str, str] = ("1", "Substructure")

#: Which element (and hence which assembly selection) an opening kind belongs to.
OPENING_ELEMENT: dict[OpeningKind, ElementType] = {
    OpeningKind.WINDOW: ElementType.WINDOW,
    OpeningKind.PATIO_DOOR: ElementType.WINDOW,
    OpeningKind.BALCONY_DOOR: ElementType.WINDOW,
    OpeningKind.DOOR: ElementType.EXTERNAL_DOOR,
    OpeningKind.GARAGE_DOOR: ElementType.GARAGE_DOOR,
}

_OPENING_ELEMENTS = (ElementType.WINDOW, ElementType.EXTERNAL_DOOR, ElementType.GARAGE_DOOR)


def opening_element(kind: OpeningKind) -> ElementType:
    """Element type whose assembly applies to an opening of this kind (glazed doors -> window)."""
    return OPENING_ELEMENT[kind]


def opening_instance_id(element: ElementType, assembly_id: str, library: AssemblyLibrary) -> str:
    """Instance id of an opening group: ``"all"`` when ``assembly_id`` is a library assembly of
    ``element``, else ``"all-<element>"`` (wrong-element override or unknown id).

    All opening elements share element code 2.6, so two groups with the same assembly id (e.g.
    the windows and a door overridden with a window assembly) would otherwise get the same line
    id.  The rule depends only on (element, assembly, library), so ids are stable.
    """
    try:
        ok = library.assembly(assembly_id).element == element
    except KeyError:
        ok = False
    return "all" if ok else f"all-{element.value}"


def off_storey_openings(twin: BuildingTwin, storeys: dict[str, int]) -> dict[str, str]:
    """Openings on a storey their block does not have: ``{opening_id: reason}``.

    ``storeys`` maps block ids to storey counts (e.g. from ``GeometryMetrics.blocks``).  Such
    openings are not deducted from walls by the geometry metrics and are excluded from
    window / door quantities.
    """
    return {o.opening_id: f"opening {o.opening_id} is on storey {o.storey} but block {o.block_id} has "
                          f"{storeys[o.block_id]} storey(s) (numbered from 0)"
            for o in twin.openings if o.block_id in storeys and o.storey >= storeys[o.block_id]}


class TakeoffAssumptions(BaseModel):
    """Labelled take-off assumptions (all ``ASSUMED`` priors; editable / sampleable)."""

    model_config = ConfigDict(extra="forbid")

    partition_length_per_m2_gia: TrackedValue = Field(
        default_factory=lambda: AssumptionLibrary().partition_length_per_m2_gia)
    spoil_bulking_factor: TrackedValue = Field(default_factory=lambda: assumed(
        1.25, "ratio", low=1.10, high=1.40, source=ASSUMPTION_SOURCE,
        note="Loose / bank volume of excavated spoil (indicative; depends on ground)."))
    oversite_dig_depth_m: TrackedValue = Field(default_factory=lambda: assumed(
        0.25, "m", low=0.15, high=0.40, source=ASSUMPTION_SOURCE,
        note="Topsoil strip / reduced-level dig under the ground-floor slab (indicative)."))
    reinforcement_allowance_kg_per_m3: TrackedValue = Field(default_factory=lambda: assumed(
        60.0, "kg/m3", low=40.0, high=100.0, source=ASSUMPTION_SOURCE,
        note="Indicative reinforcement allowance per m3 of raft / ground-beam concrete. "
             "Not a reinforcement design or schedule; requires engineer's design."))

    @classmethod
    def from_assumption_library(cls, lib: AssumptionLibrary) -> "TakeoffAssumptions":
        return cls(partition_length_per_m2_gia=lib.partition_length_per_m2_gia)


class Measure(NamedTuple):
    """One named measure of an element instance.  ``value is None`` means unresolved
    (``formula`` then starts with ``"UNRESOLVED:"`` and states the reason)."""

    value: Optional[float]
    unit: str
    geometry_refs: tuple[str, ...]
    basis: Basis
    formula: str


@dataclass
class ElementMeasures:
    """Measures of one element instance plus what is needed to apply its assembly."""

    element_key: str  # ElementType value, or "foundation"
    element: Optional[ElementType]  # None for the foundation instance
    instance_id: str  # block id, or "all"
    block_id: Optional[str]
    assembly_id: str  # assembly id, or foundation option id
    measures: dict[str, Measure]
    selection_basis: Basis = Basis.ASSUMED
    selection_ref: str = ""  # key into AssemblySelection.basis
    status_hint: QuantityStatus = QuantityStatus.DERIVED
    unresolved_reason: Optional[str] = None
    trace_extra: list[TraceLink] = field(default_factory=list)
    #: True when the measures come from scaled dimensions (adds a calibration trace link).
    geometry_derived: bool = True


# --------------------------------------------------------------------- helpers
def _bases(*tvs: Optional[TrackedValue]) -> list[Basis]:
    return [tv.basis for tv in tvs if tv is not None]


def _weakest(*groups: Optional[Iterable[Basis] | Basis]) -> Basis:
    """Weakest basis over the given bases / iterables (None entries ignored)."""
    best: Optional[Basis] = None
    rank = 99
    for g in groups:
        if g is None:
            continue
        items = (g,) if isinstance(g, Basis) else g
        for b in items:
            if b is None:
                continue
            r = BASIS_RANK[b]
            if r < rank:
                best, rank = b, r
    return best if best is not None else Basis.UNKNOWN


def selection_basis(sel: AssemblySelection, element_key: str, block_id: Optional[str] = None) -> tuple[Basis, str]:
    """Basis of the assembly choice for an element (and block), and its key in ``sel.basis``.

    Keys: ``"<element>"`` for twin-wide choices, ``"<block_id>/<element>"`` for block
    overrides (``"/"`` cannot occur in ids), ``"foundation"``.  Missing keys are ASSUMED.
    """
    if block_id and element_key in sel.block_overrides.get(block_id, {}):
        key = f"{block_id}/{element_key}"
        return sel.basis.get(key, Basis.ASSUMED), key
    return sel.basis.get(element_key, Basis.ASSUMED), element_key


def unknown_openings(twin: BuildingTwin) -> dict[str, str]:
    """Openings whose size / position is unknown: ``{opening_id: reason}``."""
    out: dict[str, str] = {}
    for o in twin.openings:
        missing = [n for n, tv in (("offset", o.offset_m), ("width", o.width_m), ("height", o.height_m),
                                   ("sill", o.sill_m)) if tv is None or tv.value is None]
        if missing:
            out[o.opening_id] = f"opening {o.opening_id} {'/'.join(missing)} unknown"
    return out


def _unresolved_measures(names: Iterable[str], refs: tuple[str, ...], reason: str) -> dict[str, Measure]:
    return {n: Measure(None, MEASURE_UNITS.get(n, ""), refs, Basis.UNKNOWN, f"UNRESOLVED: {reason}")
            for n in sorted(names)}


def _f(v: float) -> str:
    return f"{v:.3f}"


@dataclass
class _BlockCtx:
    block: Block
    bm: BlockMetrics
    roof: Optional[RoofMetrics]
    pieces: list[WallPiece]
    plan: Basis
    height: Basis
    pitch: Optional[Basis]
    overhang: Basis
    adj: Optional[Basis]
    infill: Optional[Basis]


def _block_contexts(twin: BuildingTwin, metrics: GeometryMetrics) -> list[_BlockCtx]:
    bms = {bm.block_id: bm for bm in metrics.blocks}
    roofs = {r.block_id: r for r in metrics.roofs}
    pieces_by: dict[str, list[WallPiece]] = {}
    for p in metrics.pieces:
        pieces_by.setdefault(p.block_id, []).append(p)
    by_id = {b.block_id: b for b in twin.blocks}
    out: list[_BlockCtx] = []
    for b in twin.blocks:
        bm = bms.get(b.block_id)
        if bm is None:
            continue
        pcs = pieces_by.get(b.block_id, [])
        nbs = {p.neighbour_block_id for p in pcs if p.neighbour_block_id}
        adj = None
        if nbs:
            tvs: list[Optional[TrackedValue]] = [b.origin_x, b.origin_y, b.ground_floor_level]
            for nid in sorted(nbs):
                n = by_id.get(nid)
                if n is not None:
                    tvs += [n.origin_x, n.origin_y, n.width, n.depth, n.storeys, n.floor_to_floor,
                            n.ground_floor_level]
            adj = _weakest(_bases(*tvs))
        r = b.roof
        pitch = None if r.form == RoofForm.FLAT else r.pitch_deg.basis
        infill = pitch if r.form != RoofForm.FLAT else (r.parapet_height_m.basis if r.parapet_height_m else None)
        out.append(_BlockCtx(
            block=b, bm=bm, roof=roofs.get(b.block_id), pieces=pcs,
            plan=_weakest(_bases(b.width, b.depth)),
            height=_weakest(_bases(b.storeys, b.floor_to_floor)),
            pitch=pitch,
            overhang=_weakest(_bases(r.eaves_overhang_m, r.verge_overhang_m, r.parapet_height_m)),
            adj=adj, infill=infill,
        ))
    return out


# ------------------------------------------------------------------ main entry
def element_measures(twin: BuildingTwin, metrics: GeometryMetrics, library: AssemblyLibrary, *,
                     assumptions: Optional[TakeoffAssumptions] = None,
                     unknown: Optional[dict[str, str]] = None,
                     warnings: Optional[list[str]] = None) -> list[ElementMeasures]:
    """Measures for every element instance of ``twin`` (see module docstring).

    ``unknown`` maps opening ids whose dimensions are unknown to a reason (default:
    computed from the twin); measures depending on them are left unresolved.
    ``warnings`` (optional list) receives non-fatal notes.
    """
    ta = assumptions or TakeoffAssumptions()
    unknown = unknown_openings(twin) if unknown is None else unknown
    warn = warnings if warnings is not None else []
    sel = twin.assemblies
    ctxs = _block_contexts(twin, metrics)
    ctx_by_id = {c.block.block_id: c for c in ctxs}
    out: list[ElementMeasures] = []
    ext_sel_basis, _ = selection_basis(sel, ElementType.EXTERNAL_WALL.value)
    sep_sel_basis, _ = selection_basis(sel, ElementType.SEPARATING_WALL.value)
    # openings on a storey their block does not have are never deducted or counted (not even as
    # unresolved): they cannot exist in the wall, whatever their size
    off_storey = off_storey_openings(twin, {bm.block_id: bm.storeys for bm in metrics.blocks})
    unknown = {k: v for k, v in unknown.items() if k not in off_storey}
    try:  # taller-wall areas inside lower roof voids (reported, still counted as external wall)
        void_by_piece = roof_void_wall_areas(block_params_from_twin(twin))
    except GeometryError:
        void_by_piece = {}

    unknown_by_block: dict[str, list[str]] = {}
    ops_by_id = {o.opening_id: o for o in twin.openings}
    for oid in unknown:
        o = ops_by_id.get(oid)
        if o is not None:
            unknown_by_block.setdefault(o.block_id, []).append(unknown[oid])

    def inst(element: ElementType, c: _BlockCtx, measures: dict[str, Measure], **kw) -> ElementMeasures:
        bid = c.block.block_id
        sb, sref = selection_basis(sel, element.value, bid)
        return ElementMeasures(element_key=element.value, element=element, instance_id=bid, block_id=bid,
                               assembly_id=sel.for_element(element, bid), measures=measures,
                               selection_basis=sb, selection_ref=sref, **kw)

    # internal areas depend on the wall thicknesses of the selected assemblies
    gia_sel = {c.block.block_id: _weakest(ext_sel_basis, sep_sel_basis if c.adj is not None else None)
               for c in ctxs}

    # ---------------------------------------------------------- external walls
    for c in ctxs:
        bid = c.block.block_id
        pcs = [p for p in c.pieces if p.external_gross_area_m2 > 1e-9]
        if not pcs:
            continue
        refs = tuple(p.piece_id for p in pcs)
        oids = tuple(oid for p in pcs for oid in p.opening_ids)
        gross = sum(p.external_gross_area_m2 for p in pcs)
        infill = sum(p.external_infill_area_m2 for p in pcs)
        op_area = sum(p.opening_area_m2 for p in pcs)
        net = sum(p.external_net_area_m2 for p in pcs)
        g_basis = _weakest(c.plan, c.height, c.infill if infill > 1e-9 else None, c.adj)
        op_basis = _weakest(*[_bases(ops_by_id[o].width_m, ops_by_id[o].height_m) for o in oids if o in ops_by_id])
        n_basis = _weakest(g_basis, op_basis if oids else None)
        refs_n = refs + oids
        void_pcs = [p for p in pcs if p.piece_id in void_by_piece]
        void = sum(void_by_piece[p.piece_id] for p in void_pcs)
        void_note = (f"; incl. {_f(void)} m2 inside a lower neighbour's roof void (kept as external wall, "
                     "conservative)" if void > 1e-9 else "")
        m: dict[str, Measure] = {
            "gross_area": Measure(gross, "m2", refs, g_basis,
                                  f"Σ pieces (FFL to plate {_f(gross - infill)} + gable/infill {_f(infill)}) "
                                  f"= {_f(gross)} m2{void_note}"),
        }
        if void_pcs:
            low = sorted({p.neighbour_block_id or "" for p in void_pcs})
            v_basis = _weakest(g_basis, *[ctx_by_id[n].pitch for n in low if n in ctx_by_id])
            m["lower_roof_void_area"] = Measure(
                void, "m2", tuple(p.piece_id for p in void_pcs), v_basis,
                f"wall inside the roof void of lower block(s) {', '.join(low)} (above their wall plate, under "
                f"their roof line) = {_f(void)} m2; included in gross and net external wall area (conservative)")
        else:
            m["lower_roof_void_area"] = Measure(0.0, "m2", refs, g_basis,
                                                "no wall inside a lower neighbour's roof void = 0 m2")
        bad = unknown_by_block.get(bid)
        net_names = ("element_area", "internal_face_area", "opening_head_length", "opening_reveal_length",
                     "opening_sill_length", "opening_count")
        if bad:
            m.update(_unresolved_measures(net_names, refs_n, "; ".join(bad) + " - net wall area and opening "
                                          "measures cannot be completed"))
        else:
            m["element_area"] = Measure(net, "m2", refs_n, n_basis,
                                        f"gross {_f(gross)} m2 − openings {_f(op_area)} m2 = {_f(net)} m2 "
                                        f"(each opening deducted once, per piece){void_note}")
            if c.block.heated:
                rect_net = sum(max(0.0, p.external_rect_area_m2 - p.opening_area_m2) for p in pcs)
                rect = sum(p.external_rect_area_m2 for p in pcs)
                m["internal_face_area"] = Measure(
                    rect_net, "m2", refs_n, n_basis,
                    f"FFL-to-plate zone {_f(rect)} m2 − openings {_f(op_area)} m2 = {_f(rect_net)} m2 "
                    f"(gable/infill {_f(infill)} m2 above plate excluded)")
            else:
                m["internal_face_area"] = Measure(0.0, "m2", refs, c.plan,
                                                  "unheated block: no internal wall finish assumed = 0 m2")
            head = sum(p.opening_head_length_m for p in pcs)
            rev = sum(p.opening_reveal_length_m for p in pcs)
            sill = sum(p.opening_sill_length_m for p in pcs)
            ob = _weakest(op_basis) if oids else c.plan
            m["opening_head_length"] = Measure(head, "m", oids or refs, ob, f"Σ opening widths = {_f(head)} m")
            m["opening_reveal_length"] = Measure(rev, "m", oids or refs, ob,
                                                 f"Σ 2 × opening heights = {_f(rev)} m")
            m["opening_sill_length"] = Measure(sill, "m", oids or refs, ob,
                                               f"Σ window widths = {_f(sill)} m")
            m["opening_count"] = Measure(float(len(oids)), "nr", oids or refs, ob,
                                         f"{len(oids)} openings deducted from this block's walls")
        out.append(inst(ElementType.EXTERNAL_WALL, c, m))

    # -------------------------------------------------------- separating walls
    heated = {b.block_id: b.heated for b in twin.blocks}
    for c in ctxs:
        pcs = [p for p in c.pieces if p.shared_area_m2 > 1e-9]
        if not pcs:
            continue
        bid = c.block.block_id
        refs = tuple(p.piece_id for p in pcs)
        area = sum(p.shared_area_m2 for p in pcs)
        length = sum(p.length_m for p in pcs)
        b = _weakest(c.plan, c.height, c.adj)
        nbs = ", ".join(sorted({p.neighbour_block_id or "" for p in pcs}))
        # each face is finished only towards a heated block (unheated blocks get no internal finish)
        face_a = area if c.block.heated else 0.0
        hot_nbs = sorted({p.neighbour_block_id for p in pcs if heated.get(p.neighbour_block_id or "", False)})
        face_b = sum(p.shared_area_m2 for p in pcs if heated.get(p.neighbour_block_id or "", False))
        out.append(inst(ElementType.SEPARATING_WALL, c, {
            "element_area": Measure(area, "m2", refs, b,
                                    f"Σ shared length × height to lower plate = {_f(area)} m2 "
                                    f"(with {nbs}; counted once on block {bid})"),
            "length": Measure(length, "m", refs, b, f"Σ shared piece lengths = {_f(length)} m"),
            "internal_face_area_a": Measure(
                face_a, "m2", refs, b,
                f"side A faces {bid}: {_f(area)} m2" if c.block.heated
                else f"side A faces {bid} (unheated: no internal finish assumed) = 0 m2"),
            "internal_face_area_b": Measure(
                face_b, "m2", refs, b,
                f"side B faces heated neighbour(s) {', '.join(hot_nbs)}: {_f(face_b)} m2" if hot_nbs
                else f"side B faces {nbs} (unheated: no internal finish assumed) = 0 m2"),
        }))

    # ----------------------------------------------------------- ground floors
    for c in ctxs:
        bid = c.block.block_id
        g0 = c.bm.gia_by_storey[0] if c.bm.gia_by_storey else 0.0
        refs = (f"block:{bid}", "storey:0")
        b = _weakest(c.plan, c.adj, gia_sel[bid])
        out.append(inst(ElementType.GROUND_FLOOR, c, {
            "element_area": Measure(g0, "m2", refs, b, f"ground-storey internal area of {bid} = {_f(g0)} m2"),
            "perimeter": Measure(c.bm.ground_perimeter_m, "m", refs, _weakest(c.plan, c.adj),
                                 f"exposed ground perimeter of {bid} (external face) = "
                                 f"{_f(c.bm.ground_perimeter_m)} m"),
        }))

    # ----------------------------------------------------- intermediate floors
    for c in ctxs:
        bid = c.block.block_id
        upper = c.bm.gia_by_storey[1:]
        if not upper:
            continue
        a = sum(upper)
        refs = (f"block:{bid}",) + tuple(f"storey:{k}" for k in range(1, len(upper) + 1))
        out.append(inst(ElementType.INTERMEDIATE_FLOOR, c, {
            "element_area": Measure(a, "m2", refs, _weakest(c.plan, c.height, c.adj, gia_sel[bid]),
                                    f"Σ internal area of storeys 1..{len(upper)} of {bid} = {_f(a)} m2"),
        }))

    # ------------------------------------------------------------------ roofs
    for c in ctxs:
        r = c.roof
        if r is None:
            continue
        bid = c.block.block_id
        rr = (f"roof:{bid}",)
        top = max(0, c.bm.storeys - 1)
        cref = (f"block:{bid}", f"storey:{top}")
        plan_b = _weakest(c.plan, c.overhang, c.adj)
        slope_b = _weakest(plan_b, c.pitch)
        if c.block.heated:
            ceil = Measure(c.bm.ceiling_area_m2, "m2", cref, _weakest(c.plan, c.adj, gia_sel[bid]),
                           f"internal area of top storey {top} of {bid} = {_f(c.bm.ceiling_area_m2)} m2")
        else:
            ceil = Measure(0.0, "m2", cref, c.plan, "unheated block: no insulated/finished ceiling assumed = 0 m2")
        if r.form == RoofForm.FLAT:
            out.append(inst(ElementType.FLAT_ROOF, c, {
                "element_area": Measure(r.plan_area_m2, "m2", rr, plan_b,
                                        f"flat roof plan area incl. external overhangs = {_f(r.plan_area_m2)} m2"),
                "roof_plan": Measure(r.plan_area_m2, "m2", rr, plan_b, f"roof plan area = {_f(r.plan_area_m2)} m2"),
                "ceiling_area": ceil,
                "eaves_length": Measure(r.eaves_length_m, "m", rr, plan_b,
                                        f"external roof edge length = {_f(r.eaves_length_m)} m"),
                "abutment_length": Measure(r.abutment_length_m, "m", rr, plan_b,
                                           f"abutment with taller blocks = {_f(r.abutment_length_m)} m"),
            }))
            continue
        run = c.bm.footprint_area_m2 / r.span_m if r.span_m > 1e-9 else 0.0
        out.append(inst(ElementType.PITCHED_ROOF, c, {
            "element_area": Measure(r.surface_area_m2, "m2", rr, slope_b,
                                    f"plan {_f(r.plan_area_m2)} m2 / cos({r.pitch_deg:.1f}°) = "
                                    f"{_f(r.surface_area_m2)} m2"),
            "roof_plan": Measure(r.plan_area_m2, "m2", rr, plan_b,
                                 f"roof plan area incl. external overhangs = {_f(r.plan_area_m2)} m2"),
            "ceiling_area": ceil,
            "ridge_length": Measure(r.ridge_length_m, "m", rr, plan_b, f"ridge length = {_f(r.ridge_length_m)} m"),
            "hip_length": Measure(r.hip_length_m, "m", rr, slope_b, f"hip length = {_f(r.hip_length_m)} m"),
            "eaves_length": Measure(r.eaves_length_m, "m", rr, plan_b, f"eaves length = {_f(r.eaves_length_m)} m"),
            "verge_length": Measure(r.verge_length_m, "m", rr, slope_b, f"verge length = {_f(r.verge_length_m)} m"),
            "abutment_length": Measure(r.abutment_length_m, "m", rr, plan_b,
                                       f"abutment with taller blocks = {_f(r.abutment_length_m)} m"),
            "truss_run_length": Measure(run, "m", rr, c.plan,
                                        f"footprint {_f(c.bm.footprint_area_m2)} m2 / span {_f(r.span_m)} m "
                                        f"= {_f(run)} m run along ridge direction"),
        }))

    # --------------------------------------------------------------- openings
    # metrics already flags (by id) the openings it could not deduct; avoid repeating that warning
    flagged = {oid for oid in off_storey if any(f"Opening {oid} " in w for w in metrics.warnings)}
    out.extend(_opening_instances(twin, ctxs, ops_by_id, unknown, warn, library, off_storey, flagged))

    # ------------------------------------------------------------- partitions
    part = _partition_instance(twin, ctxs, library, ta, gia_sel)
    if part is not None:
        out.append(part)

    # ------------------------------------------------------------- foundation
    out.append(_foundation_instance(twin, metrics, library, ctxs, ext_sel_basis, sep_sel_basis))
    return out


def _opening_instances(twin: BuildingTwin, ctxs: list[_BlockCtx], ops_by_id: dict[str, Opening],
                       unknown: dict[str, str], warn: list[str], library: AssemblyLibrary,
                       off_storey: dict[str, str], flagged: set[str]) -> list[ElementMeasures]:
    """Window / door instances counted from the openings deducted from wall pieces (see module doc)."""
    sel = twin.assemblies

    def assembly_of(o: Opening) -> tuple[ElementType, str, Basis, str]:
        et = OPENING_ELEMENT[o.kind]
        if o.assembly_id:
            key = f"opening/{o.opening_id}"
            return et, o.assembly_id, sel.basis.get(key, Basis.ASSUMED), key
        b, key = selection_basis(sel, et.value, o.block_id)
        return et, sel.for_element(et, o.block_id), b, key

    groups: dict[tuple[ElementType, str], dict] = {}

    def group(et: ElementType, aid: str) -> dict:
        g = groups.get((et, aid))
        if g is None:
            g = groups[(et, aid)] = {"area": 0.0, "count": 0, "perim": 0.0, "ids": [], "bases": [],
                                     "sel": [], "sel_refs": [], "unknown": [], "evidence": [], "rules": set()}
        return g

    located: set[str] = set()
    for c in ctxs:
        for p in c.pieces:
            if not p.opening_ids:
                continue
            ops = [ops_by_id.get(oid) for oid in p.opening_ids]
            nominal_a = []
            nominal_p = []
            for o in ops:
                w = o.width_m.value if o is not None else None
                h = o.height_m.value if o is not None else None
                nominal_a.append(w * h if (w is not None and h is not None) else None)
                nominal_p.append(2.0 * (w + h) if (w is not None and h is not None) else None)
            n = len(ops)
            sa = sum(a for a in nominal_a if a is not None) if None not in nominal_a else None
            sp = sum(x for x in nominal_p if x is not None) if None not in nominal_p else None
            piece_perim = 2.0 * p.opening_head_length_m + p.opening_reveal_length_m
            for k, (oid, o) in enumerate(zip(p.opening_ids, ops)):
                if o is None:
                    warn.append(f"Opening {oid} on {p.piece_id} not found in twin; excluded from window/door "
                                "quantities.")
                    continue
                located.add(oid)
                et, aid, sb, sref = assembly_of(o)
                g = group(et, aid)
                share_a = (nominal_a[k] / sa) if sa else 1.0 / n
                share_p = (nominal_p[k] / sp) if sp else 1.0 / n
                g["area"] += p.opening_area_m2 * share_a
                g["perim"] += piece_perim * share_p
                g["count"] += 1
                g["ids"].append(oid)
                g["bases"] += _bases(o.width_m, o.height_m)
                g["sel"].append(sb)
                g["sel_refs"].append(sref)
                if o.feature_id:
                    g["evidence"].append(o.feature_id)
                if o.hidden_side_rule:
                    g["rules"].add(o.hidden_side_rule)
    for o in twin.openings:
        if o.opening_id in located:
            continue
        if o.opening_id in off_storey:
            if o.opening_id not in flagged:
                why = off_storey[o.opening_id]
                warn.append(f"{why[:1].upper()}{why[1:]}: not deducted from any wall and excluded from "
                            "window/door quantities - move it to an existing storey or delete it.")
            continue
        if o.opening_id in unknown:
            et, aid, sb, sref = assembly_of(o)
            g = group(et, aid)
            g["unknown"].append(unknown[o.opening_id])
            g["ids"].append(o.opening_id)
            g["sel"].append(sb)
            g["sel_refs"].append(sref)
        else:
            warn.append(f"Opening {o.opening_id} is not located on an external wall piece (e.g. on a separating "
                        "wall or outside the wall); excluded from window/door quantities.")

    out: list[ElementMeasures] = []
    order = {e: i for i, e in enumerate(_OPENING_ELEMENTS)}
    for (et, aid), g in sorted(groups.items(), key=lambda kv: (order[kv[0][0]], kv[0][1])):
        refs = tuple(g["ids"])
        extra: list[TraceLink] = [TraceLink(kind="evidence", ref=fid, description="observed opening detection")
                                  for fid in g["evidence"]]
        extra += [TraceLink(kind="assumption", ref=f"hidden_side_rule:{rule}",
                            description="opening generated by a hidden-facade rule, not observed")
                  for rule in sorted(g["rules"])]
        sel_refs = sorted(set(g["sel_refs"]))
        em = ElementMeasures(element_key=et.value, element=et, instance_id=opening_instance_id(et, aid, library),
                             block_id=None, assembly_id=aid,
                             measures={}, selection_basis=_weakest(g["sel"]),
                             selection_ref=sel_refs[0] if len(sel_refs) == 1 else ",".join(sel_refs),
                             trace_extra=extra)
        if g["unknown"]:
            em.measures = _unresolved_measures(MEASURES[et], refs, "; ".join(g["unknown"]))
            em.unresolved_reason = "; ".join(g["unknown"])
        else:
            b = _weakest(g["bases"])
            em.measures = {
                "element_area": Measure(g["area"], "m2", refs, b,
                                        f"Σ {g['count']} opening areas (as deducted from walls) = {_f(g['area'])} m2"),
                "opening_count": Measure(float(g["count"]), "nr", refs, b, f"{g['count']} openings"),
                "opening_perimeter": Measure(g["perim"], "m", refs, b,
                                             f"Σ 2 × (width + height) = {_f(g['perim'])} m"),
            }
        out.append(em)
    return out


def _partition_instance(twin: BuildingTwin, ctxs: list[_BlockCtx], library: AssemblyLibrary,
                        ta: TakeoffAssumptions, gia_sel: dict[str, Basis]) -> Optional[ElementMeasures]:
    sel = twin.assemblies
    et = ElementType.INTERNAL_PARTITION
    heated = [c for c in ctxs if c.block.heated]
    if not heated:
        return None
    sb, sref = selection_basis(sel, et.value)
    lpm = ta.partition_length_per_m2_gia
    link = TraceLink(kind="assumption", ref="partition_length_per_m2_gia",
                     description=f"Partition allowance {lpm.label()} per m2 GIA ({lpm.basis.value}); "
                                 "no internal layout is observed")
    refs = tuple(f"block:{c.block.block_id}" for c in heated) + tuple(
        f"storey:{k}" for k in range(max(c.bm.storeys for c in heated)))
    em = ElementMeasures(element_key=et.value, element=et, instance_id="all", block_id=None,
                         assembly_id=sel.for_element(et), measures={}, selection_basis=sb, selection_ref=sref,
                         status_hint=QuantityStatus.ALLOWANCE, trace_extra=[link])
    if lpm.value is None:
        em.unresolved_reason = "partition length allowance unknown"
        em.measures = _unresolved_measures(MEASURES[et], refs, em.unresolved_reason)
        return em
    area = length = 0.0
    parts = []
    bases: list[Basis] = [lpm.basis]
    for c in heated:
        bid = c.block.block_id
        try:
            zone = library.assembly(sel.for_element(ElementType.INTERMEDIATE_FLOOR, bid)).total_thickness_m
        except KeyError:
            em.unresolved_reason = f"intermediate floor assembly for {bid} not in library (clear height unknown)"
            em.measures = _unresolved_measures(MEASURES[et], refs, em.unresolved_reason)
            return em
        ftf = (c.bm.plate_height_m - c.bm.ffl_m) / c.bm.storeys if c.bm.storeys else 0.0
        clear = ftf - zone
        if clear <= 0:
            em.unresolved_reason = f"clear storey height of {bid} is not positive ({ftf:.3f} − {zone:.3f} m)"
            em.measures = _unresolved_measures(MEASURES[et], refs, em.unresolved_reason)
            return em
        gia = sum(c.bm.gia_by_storey)
        lb = gia * lpm.value
        length += lb
        area += lb * clear
        parts.append(f"{bid}: {_f(gia)} m2 × {lpm.value:g} m/m2 × {clear:.3f} m")
        bases += [c.plan, c.height, gia_sel[bid]]
        if c.adj is not None:
            bases.append(c.adj)
    b = _weakest(bases)
    em.measures = {
        "element_area": Measure(area, "m2", refs, b, " + ".join(parts) + f" = {_f(area)} m2 (allowance)"),
        "partition_length": Measure(length, "m", refs, b,
                                    f"heated GIA × {lpm.value:g} m/m2 = {_f(length)} m (allowance)"),
    }
    return em


def _components(blocks: list[str], pieces: list[WallPiece]) -> int:
    parent = {b: b for b in blocks}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in pieces:
        if p.neighbour_block_id and p.neighbour_block_id in parent and p.block_id in parent:
            ra, rb = find(p.block_id), find(p.neighbour_block_id)
            if ra != rb:
                parent[ra] = rb
    return len({find(b) for b in blocks})


def _foundation_instance(twin: BuildingTwin, metrics: GeometryMetrics, library: AssemblyLibrary,
                         ctxs: list[_BlockCtx], ext_sel_basis: Basis, sep_sel_basis: Basis) -> ElementMeasures:
    sel = twin.assemblies
    opt_id = sel.foundation
    sb, sref = selection_basis(sel, FOUNDATION_KEY)
    refs = tuple(p.piece_id for p in metrics.pieces if p.exposure == "external") + tuple(
        p.piece_id for p in metrics.pieces if p.shared_area_m2 > 1e-9)
    em = ElementMeasures(element_key=FOUNDATION_KEY, element=None, instance_id="all", block_id=None,
                         assembly_id=opt_id, measures={}, selection_basis=sb, selection_ref=sref)
    try:
        opt = library.foundation(opt_id)
    except KeyError:
        em.unresolved_reason = f"foundation option '{opt_id}' not in library"
        em.measures = _unresolved_measures(FOUNDATION_MEASURES, refs, em.unresolved_reason)
        return em
    f = opt.internal_loadbearing_fraction
    multi = len(ctxs) > 1
    plan_b = _weakest(*[[c.plan] + ([c.adj] if (multi and c.adj is not None) else []) for c in ctxs])
    if multi:
        plan_b = _weakest(plan_b, *[_bases(c.block.origin_x, c.block.origin_y) for c in ctxs])
    P = metrics.ground_perimeter_m
    t = metrics.external_wall_thickness_m
    n = _components([c.block.block_id for c in ctxs], metrics.pieces)
    Pc = max(0.0, P - 4.0 * t * n)
    Lsep = metrics.storeys[0].shared_wall_length_m if metrics.storeys else 0.0
    cl_b = _weakest(plan_b, ext_sel_basis)
    tot_p = sum(c.bm.ground_perimeter_m for c in ctxs)
    ffl = (sum(c.bm.ground_perimeter_m * c.bm.ffl_m for c in ctxs) / tot_p) if tot_p > 0 else (
        ctxs[0].bm.ffl_m if ctxs else 0.0)
    ffl_b = _weakest(*[_bases(c.block.ground_floor_level) for c in ctxs])
    m: dict[str, Measure] = {
        "ground_perimeter": Measure(P, "m", refs, plan_b, f"external ground perimeter = {_f(P)} m"),
        "centreline_perimeter": Measure(Pc, "m", refs, cl_b,
                                        f"{_f(P)} m − 4 × {t:.4f} m × {n} part(s) = {_f(Pc)} m at wall centreline"),
        "separating_wall_length": Measure(Lsep, "m", refs, plan_b,
                                          f"walls between blocks (counted once) = {_f(Lsep)} m"),
        "footprint_area": Measure(metrics.footprint_area_m2, "m2", refs, plan_b,
                                  f"ground footprint GEA = {_f(metrics.footprint_area_m2)} m2"),
        "ground_floor_area": Measure(metrics.ground_floor_area_m2, "m2", ("storey:0",), cl_b,
                                     f"ground-storey internal area = {_f(metrics.ground_floor_area_m2)} m2"),
        "average_ffl": Measure(ffl, "m", tuple(f"block:{c.block.block_id}" for c in ctxs), ffl_b,
                               f"perimeter-weighted finished floor level above ground = {ffl:.3f} m"),
    }
    if f.value is None:
        reason = f"internal loadbearing fraction of '{opt_id}' unknown"
        m.update(_unresolved_measures(("internal_loadbearing_length", "trench_length", "oversite_area"), refs,
                                      reason))
    else:
        Lint = f.value * P
        L = Pc + Lsep + Lint
        m["internal_loadbearing_length"] = Measure(Lint, "m", refs, _weakest(plan_b, f.basis),
                                                   f"{f.value:g} × {_f(P)} m = {_f(Lint)} m (allowance)")
        m["trench_length"] = Measure(L, "m", refs, _weakest(cl_b, f.basis),
                                     f"centreline {_f(Pc)} + separating {_f(Lsep)} + internal {_f(Lint)} "
                                     f"= {_f(L)} m")
        W = opt.trench_width_m
        if W.value is None:
            m.update(_unresolved_measures(("oversite_area",), refs, f"trench width of '{opt_id}' unknown"))
        else:
            # oversite dig = ground-storey GIA less the trench plan inside it (trenches are measured
            # in full by the trench excavation, so their top is not dug twice)
            w = W.value
            t_sep = metrics.separating_wall_thickness_m
            e_ext, e_sep = max(t, 0.5 * (t + w)), max(0.5 * t_sep, 0.5 * w)
            gfa = metrics.ground_floor_area_m2
            a_walls = ground_internal_area(metrics, e_ext, e_sep)
            a_int = w * Lint
            oa = max(0.0, a_walls - a_int)
            ob = _weakest(cl_b, W.basis, f.basis, sep_sel_basis if Lsep > 1e-9 else None)
            m["oversite_area"] = Measure(
                oa, "m2", refs + ("storey:0",), ob,
                f"ground-storey GIA {_f(gfa)} m2 − trench plan inside the GIA {_f(gfa - oa)} m2 (external trench "
                f"{_f(e_ext - t)} m beyond the inner wall face, separating trench {_f(e_sep - 0.5 * t_sep)} m beyond "
                f"each wall face, internal trench {w:g} m × {_f(Lint)} m) = {_f(oa)} m2; trench volumes are "
                "measured separately (no double count)")
    em.measures = m
    em.trace_extra = [
        TraceLink(kind="assumption", ref=f"foundation:{opt_id}",
                  description=f"{opt.name}: {opt.notes}"),
        TraceLink(kind="assumption", ref=f"foundation:{opt_id}.internal_loadbearing_fraction",
                  description=f"Internal loadbearing wall length allowance {f.label()} of external perimeter"),
    ]
    return em


def unresolved_instances(twin: BuildingTwin, library: AssemblyLibrary, reason: str) -> list[ElementMeasures]:
    """Element instances with every measure unresolved (used when geometry cannot be computed).

    Instances are enumerated from the twin itself so the bill still lists what is needed,
    with stable line ids, instead of inventing numbers.
    """
    sel = twin.assemblies
    out: list[ElementMeasures] = []

    def add(element: ElementType, instance_id: str, block_id: Optional[str], assembly_id: str,
            refs: tuple[str, ...], status: QuantityStatus = QuantityStatus.DERIVED) -> None:
        sb, sref = selection_basis(sel, element.value, block_id)
        out.append(ElementMeasures(element_key=element.value, element=element, instance_id=instance_id,
                                   block_id=block_id, assembly_id=assembly_id,
                                   measures=_unresolved_measures(MEASURES[element], refs, reason),
                                   selection_basis=sb, selection_ref=sref, status_hint=status,
                                   unresolved_reason=reason))

    for b in twin.blocks:
        bid = b.block_id
        refs = (f"block:{bid}",)
        add(ElementType.EXTERNAL_WALL, bid, bid, sel.for_element(ElementType.EXTERNAL_WALL, bid), refs)
        add(ElementType.GROUND_FLOOR, bid, bid, sel.for_element(ElementType.GROUND_FLOOR, bid), refs)
        if b.storeys.value is None or round(b.storeys.value) > 1:
            add(ElementType.INTERMEDIATE_FLOOR, bid, bid, sel.for_element(ElementType.INTERMEDIATE_FLOOR, bid), refs)
        rf = ElementType.FLAT_ROOF if b.roof.form == RoofForm.FLAT else ElementType.PITCHED_ROOF
        add(rf, bid, bid, sel.for_element(rf, bid), (f"roof:{bid}",))
    if len(twin.blocks) > 1:
        add(ElementType.SEPARATING_WALL, "all", None, sel.separating_wall,
            tuple(f"block:{b.block_id}" for b in twin.blocks))
    seen: set[tuple[ElementType, str]] = set()
    for o in twin.openings:
        et = OPENING_ELEMENT[o.kind]
        aid = o.assembly_id or sel.for_element(et, o.block_id)
        if (et, aid) in seen:
            continue
        seen.add((et, aid))
        ids = tuple(x.opening_id for x in twin.openings
                    if OPENING_ELEMENT[x.kind] == et and (x.assembly_id or sel.for_element(et, x.block_id)) == aid)
        add(et, opening_instance_id(et, aid, library), None, aid, ids)
    if any(b.heated for b in twin.blocks):
        add(ElementType.INTERNAL_PARTITION, "all", None, sel.internal_partition,
            tuple(f"block:{b.block_id}" for b in twin.blocks if b.heated), QuantityStatus.ALLOWANCE)
    sb, sref = selection_basis(sel, FOUNDATION_KEY)
    out.append(ElementMeasures(element_key=FOUNDATION_KEY, element=None, instance_id="all", block_id=None,
                               assembly_id=sel.foundation,
                               measures=_unresolved_measures(FOUNDATION_MEASURES,
                                                             tuple(f"block:{b.block_id}" for b in twin.blocks),
                                                             reason),
                               selection_basis=sb, selection_ref=sref, unresolved_reason=reason))
    return out
