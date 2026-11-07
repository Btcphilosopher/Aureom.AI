"""Quantity take-off: geometry measures x assembly rules -> traceable bill of quantities.

``calculate_quantities(twin, library)`` produces one :class:`QuantityLine`

* per (element instance, assembly layer) - walls / floors / roofs per block,
  windows / doors per assembly, partitions per twin;
* per substructure item of the selected :class:`FoundationOption` (trench
  excavation, oversite dig, spoil disposal, concrete, below-ground masonry,
  raft thickening, piles / ground beams and reinforcement *allowances*);
* per :class:`AllowanceRule` (labelled allowances: services, fittings, stairs,
  internal doors, finishes, decoration, structural steel).

Every line carries the measure it came from, a formula with the numbers, the
installed quantity, cutting and waste losses (kept separate), the purchase
quantity rounded to packs, trade and labour hours, the provenance basis (the
weakest of the measure's basis and the assembly-selection basis) and trace
links to geometry (piece / opening / roof / storey ids), the assembly rule,
allowances and assumptions.  When something cannot be derived the line is
``UNRESOLVED`` with the reason - numbers are never invented.

Conventions
-----------
* Line ids (stable across recalculation, ARCHITECTURE §3):
  ``<element_code>.<block_id|all>.<assembly_id>.<layer_index>``, substructure
  ``1.all.<foundation_id>.<n>`` with fixed ``n`` per item
  (0 trench excavation, 1 oversite dig, 2 disposal, 3 concrete, 4 raft extra
  thickness, 5 below-ground blockwork, 6 its mortar, 7 piles, 8 reinforcement
  allowance), allowances ``<element_code>.allow.<allowance_id>``.  Window / door
  groups use ``all``, or ``all-<element>`` when their assembly belongs to another
  element (or is not in the library), so line ids are always unique.
* Cost keys: ``mat:<material_id>`` (unit = purchase unit), ``lab:<trade>`` (hr),
  ``allow:<id>``, ``plant:excavation`` (m3 bank), ``log:spoil_disposal``
  (m3 loose).  Thermal-only layers (air cavity) have no cost key.
* Selection basis keys in ``AssemblySelection.basis``: ``"<element>"``,
  ``"<block_id>/<element>"`` for block overrides, ``"foundation"``.
* Trench centreline: the external-wall centreline perimeter is
  ``P_ext - 4 t_ext n`` (n = connected footprint parts; no enclosed
  courtyards); separating walls between blocks are added once; internal
  loadbearing walls are an allowance ``fraction x P_ext``.  All excavated spoil
  is assumed removed off site (no backfill credit) at the assumed bulking factor.
* Oversite dig = (ground-storey GIA - trench plan inside the GIA) x dig depth:
  the trench excavation is measured in full (L x W x D), so the part of the
  trenches inside the internal wall faces is left out of the oversite area and
  no volume is excavated twice.
* Windows / doors are counted from the openings deducted from wall pieces only;
  openings on separating walls, outside a wall or on a storey the block does
  not have are excluded with a warning (never priced).
* Allowances ``per_m2_gia`` use **heated** GIA (garages / unheated blocks get no
  services, doors, finishes); ``per_m2_finishable`` uses internally finished
  wall faces (heated blocks), partitions (both sides), separating-wall faces
  facing heated blocks and ceilings of heated storeys.  Separating-wall plaster
  is measured on the same faces (``internal_face_area_a`` / ``_b``).
* GIA uses the twin-wide external-wall assembly thickness; per-block wall
  overrides of a different thickness are flagged, not re-measured.

Boundaries: no reinforcement schedules, member sizes, foundation design,
concealed service layouts or compliance checks are produced.  Quantities are
concept-stage estimates from a conceptual reconstruction, not a measured survey.

Performance: with ``metrics`` precomputed, a 3-block twin takes a few
milliseconds (no deep copies; lines are built without re-validation).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Union

from ..core.models import (
    Assembly,
    AssemblyLayer,
    AssemblyLibrary,
    BillOfQuantities,
    BuildingTwin,
    ElementType,
    FoundationKind,
    FoundationOption,
    GeometryMetrics,
    LayerRole,
    MaterialSpec,
    QuantityLine,
    QuantityStatus,
    TraceLink,
)
from ..core.provenance import BASIS_LABEL, Basis, EditRecord
from ..core.settings import AssumptionLibrary
from ..core.units import UnitError, convert
from ..geometry.footprint import GeometryError
from ..geometry.metrics import CONVENTIONS as GEOMETRY_CONVENTIONS
from ..geometry.metrics import compute_metrics, params_from_twin
from .library import SUBSTRUCTURE_RULES, SubstructureRules, is_purchasable, material_cost_key
from .measures import (
    ELEMENT_CODES,
    FOUNDATION_KEY,
    SUBSTRUCTURE_CODE,
    ElementMeasures,
    Measure,
    TakeoffAssumptions,
    _weakest,
    element_measures,
    off_storey_openings,
    unknown_openings,
    unresolved_instances,
)
from .procurement import procure

__all__ = [
    "QUANTITY_CONVENTIONS",
    "SUBSTRUCTURE_LINE_INDEX",
    "wall_thicknesses",
    "apply_construction_assemblies",
    "calculate_quantities",
]

#: Fixed layer indices of substructure lines (``1.all.<foundation_id>.<index>``).
SUBSTRUCTURE_LINE_INDEX: dict[str, int] = {
    "trench_excavation": 0, "oversite_excavation": 1, "spoil_disposal": 2, "concrete": 3,
    "raft_extra_thickness": 4, "below_ground_blockwork": 5, "below_ground_mortar": 6, "piles": 7,
    "reinforcement_allowance": 8,
}

QUANTITY_CONVENTIONS: dict[str, str] = {
    "line_ids": "<element_code>.<block_id|all>.<assembly_id>.<layer_index>; substructure "
                "1.all.<foundation_id>.<n>; allowances <element_code>.allow.<allowance_id>. Stable across "
                "recalculation.",
    "element_codes": "NRM1-inspired grouping (not a claim of NRM compliance): 1 Substructure, 2.1 Frame "
                     "allowance, 2.2 Upper floors, 2.3 Roof, 2.4 Stairs, 2.5 External walls, 2.6 Windows & "
                     "external doors, 2.7 Internal walls & partitions, 2.8 Separating walls, 3 Internal "
                     "finishes, 4 Fittings, 5 Services.",
    "cost_keys": "mat:<material_id> (unit = purchase_unit), lab:<trade> (hr), allow:<allowance_id>, "
                 "plant:excavation (m3 bank), log:spoil_disposal (m3 loose), allow:piling (m), "
                 "allow:reinforcement (kg). Thermal-only layers carry no cost key.",
    "losses": "cutting_loss_qty = installed x cutting fraction and waste_qty = installed x waste fraction, "
              "added (not compounded); required = installed + cutting + waste (installed units).",
    "packaging": "purchase = required x purchase_per_installed; packs = ceil(purchase / pack_size); "
                 "purchased = packs x pack_size; surplus = purchased - purchase (purchase units).",
    "basis": "Line basis = weakest of the measure's basis (dimensions, storeys, heights, roof, openings, "
             "allowance factors) and the assembly-selection basis.",
    "status": "derived = geometry x assembly rule; allowance = labelled allowance (not measured); "
              "unresolved = could not be derived (reason given), never filled with invented numbers.",
    "openings": "Opening areas are those deducted from wall pieces (each once); grouped per (element, assembly) "
                "with instance id 'all', or 'all-<element>' when the assembly belongs to another element or is not in "
                "the library. Openings not deducted (separating wall, outside the wall, storey the block does not "
                "have) are excluded with a warning, never priced.",
    "internal_finishes": "Wall internal finishes use the FFL-to-plate zone minus openings of heated blocks; "
                         "gable infill above the ceiling and unheated blocks get no internal finish. Separating "
                         "walls are finished only on faces towards heated blocks.",
    "roof_void_wall": "A taller block's wall inside a lower neighbour's roof void stays in its external wall "
                      "quantities (conservative) and is reported as the measure lower_roof_void_area.",
    "partitions": "Internal partitions are an allowance: length per m2 heated GIA x clear storey height.",
    "substructure": "Trench length = external centreline perimeter (P - 4 t n) + separating walls + internal "
                    "loadbearing allowance (fraction x P). Oversite dig = (ground-storey GIA - trench plan inside the "
                    "GIA) x dig depth, so trench volume is not excavated twice. Spoil assumed removed off site with "
                    "bulking. Foundation options are indicative and require site investigation and engineer's design.",
    "allowances": "per_m2_gia allowances use heated GIA; per_m2_finishable uses measured finished faces.",
    "exclusions": "No reinforcement schedules, structural member sizes, foundation design, concealed service "
                  "layouts or compliance checks are produced.",
    "information_level": "Concept-stage quantities from a conceptual parametric reconstruction; not a measured "
                         "survey or a priced bill for tender.",
}

_SYSTEM_ACTORS = ("system", "scenario")
_VALID_KEYS = {e.value for e in ElementType} | {FOUNDATION_KEY}
_NEED_UNIT = {"area": "m2", "volume": "m2", "per_area": "m2", "per_length": "m", "per_item": "nr"}


# =============================================================================
# Wall thicknesses and assembly selection edits
# =============================================================================
def _assembly_for(library: AssemblyLibrary, assembly_id: str, element: ElementType) -> Assembly:
    try:
        a = library.assembly(assembly_id)
    except KeyError:
        raise ValueError(f"assembly '{assembly_id}' is not in library '{library.name}'") from None
    if a.element != element:
        raise ValueError(f"assembly '{assembly_id}' is a {a.element.value} assembly, not {element.value}")
    return a


def wall_thicknesses(twin: BuildingTwin, library: AssemblyLibrary) -> tuple[float, float]:
    """(external wall, separating wall) total thickness in m of the twin-wide selected assemblies."""
    sel = twin.assemblies
    ext = _assembly_for(library, sel.external_wall, ElementType.EXTERNAL_WALL)
    sep = _assembly_for(library, sel.separating_wall, ElementType.SEPARATING_WALL)
    return ext.total_thickness_m, sep.total_thickness_m


def apply_construction_assemblies(twin: BuildingTwin, selection_changes: dict[str, str], library: AssemblyLibrary,
                                  *, actor: str = "user", block_id: Optional[str] = None,
                                  reason: str = "") -> BuildingTwin:
    """Return a new twin with changed assembly selections (the input is never mutated).

    ``selection_changes`` maps an element value (``"external_wall"``, ``"window"`` ...) to an
    assembly id of that element, or ``"foundation"`` to a :class:`FoundationOption` id.  With
    ``block_id`` the change is a per-block override (not allowed for ``"foundation"``).

    Basis: ``USER_CONFIRMED`` unless ``actor`` starts with ``"system"`` or ``"scenario"`` (then
    ``ASSUMED`` - a scenario is a hypothesis, not a confirmation).  Each change is logged as an
    :class:`EditRecord` and the twin version is incremented once.  Raises ``ValueError`` for unknown
    elements, ids, element mismatches or unknown blocks.
    """
    if not isinstance(selection_changes, dict):
        raise ValueError("selection_changes must be a dict {element: assembly_id}")
    if block_id is not None:
        try:
            twin.block(block_id)
        except KeyError:
            raise ValueError(f"unknown block '{block_id}'") from None
    for key, aid in selection_changes.items():
        if key not in _VALID_KEYS:
            raise ValueError(f"unknown element '{key}'; expected one of {sorted(_VALID_KEYS)}")
        if not isinstance(aid, str) or not aid:
            raise ValueError(f"assembly id for '{key}' must be a non-empty string")
        if key == FOUNDATION_KEY:
            if block_id is not None:
                raise ValueError("the foundation option is selected per twin, not per block")
            try:
                library.foundation(aid)
            except KeyError:
                raise ValueError(f"foundation option '{aid}' is not in library '{library.name}'") from None
        else:
            _assembly_for(library, aid, ElementType(key))
    if not selection_changes:
        return twin.model_copy(deep=True)
    basis = Basis.ASSUMED if actor.strip().lower().startswith(_SYSTEM_ACTORS) else Basis.USER_CONFIRMED
    new = twin.model_copy(deep=True)
    sel = new.assemblies
    records: list[EditRecord] = []
    for key, aid in selection_changes.items():
        if block_id is not None:
            bkey = f"{block_id}/{key}"
            old = sel.for_element(ElementType(key), block_id)
            old_basis = sel.basis.get(bkey) if key in sel.block_overrides.get(block_id, {}) else sel.basis.get(key)
            sel.block_overrides.setdefault(block_id, {})[key] = aid
            sel.basis[bkey] = basis
            target = f"assemblies/{block_id}"
        else:
            old = getattr(sel, key)
            old_basis = sel.basis.get(key)
            setattr(sel, key, aid)
            sel.basis[key] = basis
            target = "assemblies"
        records.append(EditRecord(actor=actor, target=target, field=key, old_value=old, new_value=aid,
                                  old_basis=old_basis or Basis.ASSUMED, new_basis=basis,
                                  reason=reason or "construction assembly selection"))
    new.version = twin.version + 1
    new.edit_log.extend(records)
    return new


# =============================================================================
# Take-off
# =============================================================================
@dataclass
class _Ctx:
    twin: BuildingTwin
    library: AssemblyLibrary
    metrics: GeometryMetrics
    ta: TakeoffAssumptions
    rules: SubstructureRules
    mats: dict[str, MaterialSpec]
    asms: dict[str, Assembly]
    calib: TraceLink
    geometry_ok: bool
    warnings: list[str] = field(default_factory=list)


def _line(**kw) -> QuantityLine:
    # Inputs are produced by this module with correct types; skip re-validation for speed
    # (calculate_quantities runs inside Monte Carlo loops).
    return QuantityLine.model_construct(**kw)


def _selection_link(inst: ElementMeasures) -> TraceLink:
    ref = f"assemblies.{inst.selection_ref or inst.element_key}"
    if inst.selection_basis == Basis.USER_CONFIRMED:
        return TraceLink(kind="user_input", ref=ref, description=f"'{inst.assembly_id}' confirmed by the user")
    return TraceLink(kind="assumption", ref=ref,
                     description=f"'{inst.assembly_id}' is a {BASIS_LABEL[inst.selection_basis].lower()} "
                                 "construction choice; construction is not established from appearance")


def _geom_links(m: Measure, name: str) -> list[TraceLink]:
    return [TraceLink(kind="geometry", ref=r, description=name) for r in m.geometry_refs]


def _unresolved(*, line_id: str, code: str, ename: str, description: str, reason: str, unit: str,
                trace: list[TraceLink], refs: list[str], assembly_id: Optional[str] = None,
                layer_index: Optional[int] = None, material_id: Optional[str] = None,
                allowance_id: Optional[str] = None, measure_name: str = "", measure_unit: str = "",
                trade: str = "general", mat: Optional[MaterialSpec] = None) -> QuantityLine:
    return _line(
        line_id=line_id, element_code=code, element_name=ename, description=description,
        status=QuantityStatus.UNRESOLVED, assembly_id=assembly_id, layer_index=layer_index, material_id=material_id,
        allowance_id=allowance_id, cost_key=None, measure_name=measure_name, measure_value=None,
        measure_unit=measure_unit, formula=f"UNRESOLVED: {reason}", unit=unit, installed_qty=None,
        cutting_loss_fraction=mat.cutting_loss_fraction if mat else 0.0, cutting_loss_qty=None,
        waste_fraction=mat.waste_fraction if mat else 0.0, waste_qty=None, required_qty=None,
        purchase_unit=mat.purchase_unit if mat else "", purchase_per_installed=mat.purchase_per_installed if mat else 1.0,
        pack_size=mat.pack_size if mat else 1.0, packs=None, purchased_qty=None, surplus_qty=None, trade=trade,
        labour_hours=None, basis=Basis.UNKNOWN, trace=trace, geometry_refs=refs, notes=reason,
    )


def _installed(layer: AssemblyLayer, m: Measure, mat: MaterialSpec) -> tuple[float, str]:
    """Installed quantity (material installed units) and the formula text."""
    need = _NEED_UNIT[layer.quantity_rule]
    if m.unit != need:
        raise ValueError(f"rule '{layer.quantity_rule}' needs a {need} measure but '{layer.measure}' is {m.unit}")
    v, f, u = float(m.value), layer.factor, mat.installed_unit
    rule = layer.quantity_rule
    if rule == "area":
        q = v * f if u == "m2" else convert(v * f, "m2", u)
        return q, f"{v:.3f} m2 × {f:g} = {q:.3f} {u}"
    if rule == "volume":
        t = layer.thickness_m
        q = v * t * f if u == "m3" else convert(v * t * f, "m3", u)
        return q, f"{v:.3f} m2 × {t * 1000:g} mm ({t:g} m) × {f:g} = {q:.4f} {u}"
    q = v * f
    per = {"per_area": "m2", "per_length": "m", "per_item": "nr"}[rule]
    return q, f"{v:.3f} {per} × {f:g} {u}/{per} = {q:.3f} {u}"


def _procure_fields(q: float, mat: MaterialSpec) -> tuple[dict, str]:
    p = procure(q, mat)
    txt = (f"; + cutting {p['cutting_loss_fraction']:.0%} + waste {p['waste_fraction']:.0%} = "
           f"{p['required']:.3f} {mat.installed_unit} → {p['purchase_required']:.3f} {mat.purchase_unit} → "
           f"{p['packs']} × {mat.pack_size:g} = {p['purchased']:.3f} {mat.purchase_unit} "
           f"(surplus {p['surplus']:.3f})")
    return {
        "cutting_loss_fraction": p["cutting_loss_fraction"], "cutting_loss_qty": p["cutting_loss_qty"],
        "waste_fraction": p["waste_fraction"], "waste_qty": p["waste_qty"], "required_qty": p["required"],
        "purchase_unit": mat.purchase_unit, "purchase_per_installed": mat.purchase_per_installed,
        "pack_size": mat.pack_size, "packs": p["packs"], "purchased_qty": p["purchased"],
        "surplus_qty": p["surplus"],
    }, txt


_THERMAL_ONLY_NOTE = "Thermal-only layer: nothing purchased; carried for the thermal calculation and traceability."
_ALLOWANCE_LAYER_NOTE = "Indicative allowance (layout / member size not designed)."


def _assembly_lines(ctx: _Ctx, inst: ElementMeasures) -> list[QuantityLine]:
    element = inst.element
    assert element is not None
    code, ename = ELEMENT_CODES[element]
    where = f"block {inst.block_id}" if inst.block_id else "whole building"
    sel_link = _selection_link(inst)
    base_trace = [sel_link] + inst.trace_extra
    if inst.geometry_derived and ctx.geometry_ok:
        base_trace.append(ctx.calib)
    asm = ctx.asms.get(inst.assembly_id)
    first_refs = list(next(iter(inst.measures.values())).geometry_refs) if inst.measures else []
    if asm is None or asm.element != element:
        reason = (f"assembly '{inst.assembly_id}' not in library" if asm is None
                  else f"assembly '{inst.assembly_id}' is not a {element.value} assembly")
        return [_unresolved(line_id=f"{code}.{inst.instance_id}.{inst.assembly_id}.0", code=code, ename=ename,
                            description=f"{element.value} ({where})", reason=reason, unit="",
                            trace=base_trace, refs=first_refs, assembly_id=inst.assembly_id)]
    out: list[QuantityLine] = []
    geom_cache: dict[str, list[TraceLink]] = {}
    sel_b = inst.selection_basis
    allowance_instance = inst.status_hint == QuantityStatus.ALLOWANCE
    for i, layer in enumerate(asm.layers):
        line_id = f"{code}.{inst.instance_id}.{asm.assembly_id}.{i}"
        desc = f"{layer.name} - {asm.name} ({where})"
        rule_link = TraceLink(kind="assembly_rule", ref=f"{asm.assembly_id}[{i}]",
                              description=f"{layer.name}: {layer.quantity_rule} on {layer.measure} × {layer.factor:g}"
                                          + (f" ({layer.factor_note})" if layer.factor_note else ""))
        m = inst.measures.get(layer.measure)
        mat = ctx.mats.get(layer.material_id)
        trace = base_trace + [rule_link]
        if layer.is_allowance:
            trace.append(TraceLink(kind="assumption", ref=f"{asm.assembly_id}[{i}].factor",
                                   description=_ALLOWANCE_LAYER_NOTE))
        common = dict(line_id=line_id, code=code, ename=ename, description=desc, trace=trace,
                      assembly_id=asm.assembly_id, layer_index=i, material_id=layer.material_id,
                      measure_name=layer.measure, trade=layer.trade, mat=mat)
        if mat is None:
            out.append(_unresolved(reason=f"material '{layer.material_id}' not in library", unit="",
                                   refs=first_refs, **common))
            continue
        if m is None:
            out.append(_unresolved(reason=f"measure '{layer.measure}' is not defined for {element.value}",
                                   unit=mat.installed_unit, refs=first_refs, **common))
            continue
        if m.value is None:
            out.append(_unresolved(reason=m.formula.removeprefix("UNRESOLVED: "), unit=mat.installed_unit,
                                   refs=list(m.geometry_refs), measure_unit=m.unit, **common))
            continue
        try:
            q, ftxt = _installed(layer, m, mat)
        except (ValueError, UnitError) as e:
            out.append(_unresolved(reason=str(e), unit=mat.installed_unit, refs=list(m.geometry_refs),
                                   measure_unit=m.unit, **common))
            continue
        g = geom_cache.get(layer.measure)
        if g is None:
            g = geom_cache[layer.measure] = _geom_links(m, f"{inst.element_key} {layer.measure}")
        status = (QuantityStatus.ALLOWANCE if (layer.is_allowance or allowance_instance)
                  else QuantityStatus.DERIVED)
        basis = _weakest(m.basis, sel_b, Basis.ASSUMED if layer.is_allowance else None)
        notes = layer.factor_note
        formula = f"{layer.measure} {ftxt}"
        if is_purchasable(mat):
            pf, ptxt = _procure_fields(q, mat)
            formula += ptxt
            cost_key: Optional[str] = material_cost_key(mat.material_id)
        else:
            pf = {"cutting_loss_fraction": 0.0, "cutting_loss_qty": 0.0, "waste_fraction": 0.0, "waste_qty": 0.0,
                  "required_qty": q, "purchase_unit": mat.purchase_unit, "purchase_per_installed": 0.0,
                  "pack_size": 1.0, "packs": 0, "purchased_qty": 0.0, "surplus_qty": 0.0}
            cost_key = None
            notes = (notes + " " if notes else "") + _THERMAL_ONLY_NOTE
        if layer.is_allowance:
            notes = (notes + " " if notes else "") + _ALLOWANCE_LAYER_NOTE
        out.append(_line(
            line_id=line_id, element_code=code, element_name=ename, description=desc, status=status,
            assembly_id=asm.assembly_id, layer_index=i, material_id=mat.material_id, allowance_id=None,
            cost_key=cost_key, measure_name=layer.measure, measure_value=float(m.value), measure_unit=m.unit,
            formula=formula, unit=mat.installed_unit, installed_qty=q, trade=layer.trade,
            labour_hours=q * layer.labour_hours_per_unit, basis=basis, trace=trace + g,
            geometry_refs=list(m.geometry_refs), notes=notes, **pf,
        ))
    return out


# ------------------------------------------------------------------ substructure
def _op_line(*, line_id: str, description: str, status: QuantityStatus, assembly_id: str, layer_index: int,
             cost_key: Optional[str], unit: str, measure_name: str, measure_value: float, measure_unit: str,
             formula: str, qty: float, trade: str, hours_per_unit: float, basis: Basis, trace: list[TraceLink],
             refs: list[str], notes: str = "", material_id: Optional[str] = None,
             allowance_id: Optional[str] = None) -> QuantityLine:
    """A rule / allowance line without packaging (purchased = installed)."""
    code, ename = SUBSTRUCTURE_CODE
    return _line(
        line_id=line_id, element_code=code, element_name=ename, description=description, status=status,
        assembly_id=assembly_id, layer_index=layer_index, material_id=material_id, allowance_id=allowance_id,
        cost_key=cost_key, measure_name=measure_name, measure_value=measure_value, measure_unit=measure_unit,
        formula=formula, unit=unit, installed_qty=qty, cutting_loss_fraction=0.0, cutting_loss_qty=0.0,
        waste_fraction=0.0, waste_qty=0.0, required_qty=qty, purchase_unit=unit, purchase_per_installed=1.0,
        pack_size=1.0, packs=None, purchased_qty=qty, surplus_qty=0.0, trade=trade, labour_hours=qty * hours_per_unit,
        basis=basis, trace=trace, geometry_refs=refs, notes=notes,
    )


def _mat_line(ctx: _Ctx, *, line_id: str, description: str, status: QuantityStatus, assembly_id: str,
              layer_index: int, material_id: str, measure_name: str, measure_value: float, measure_unit: str,
              formula: str, qty: float, trade: str, hours_per_unit: float, basis: Basis, trace: list[TraceLink],
              refs: list[str], notes: str = "") -> QuantityLine:
    code, ename = SUBSTRUCTURE_CODE
    mat = ctx.mats.get(material_id)
    if mat is None:
        return _unresolved(line_id=line_id, code=code, ename=ename, description=description,
                           reason=f"material '{material_id}' not in library", unit="", trace=trace, refs=refs,
                           assembly_id=assembly_id, layer_index=layer_index, material_id=material_id,
                           measure_name=measure_name, trade=trade)
    pf, ptxt = _procure_fields(qty, mat)
    return _line(
        line_id=line_id, element_code=code, element_name=ename, description=description, status=status,
        assembly_id=assembly_id, layer_index=layer_index, material_id=material_id, allowance_id=None,
        cost_key=material_cost_key(material_id), measure_name=measure_name, measure_value=measure_value,
        measure_unit=measure_unit, formula=formula + ptxt, unit=mat.installed_unit, installed_qty=qty, trade=trade,
        labour_hours=qty * hours_per_unit, basis=basis, trace=trace, geometry_refs=refs, notes=notes, **pf,
    )


def _slab_thickness(asm: Optional[Assembly]) -> float:
    if asm is None:
        return 0.0
    return sum(layer.thickness_m for layer in asm.layers if layer.role == LayerRole.SLAB)


def _expected_substructure(kind: FoundationKind) -> list[str]:
    keys = ["trench_excavation", "oversite_excavation", "spoil_disposal", "concrete"]
    if kind == FoundationKind.RAFT:
        keys += ["raft_extra_thickness", "reinforcement_allowance"]
    else:
        keys += ["below_ground_blockwork", "below_ground_mortar"]
    if kind == FoundationKind.PILED_ALLOWANCE:
        keys += ["piles", "reinforcement_allowance"]
    return keys


_SUB_UNITS = {"trench_excavation": "m3", "oversite_excavation": "m3", "spoil_disposal": "m3", "concrete": "m3",
              "raft_extra_thickness": "m3", "below_ground_blockwork": "nr", "below_ground_mortar": "m3",
              "piles": "m", "reinforcement_allowance": "kg"}


def _substructure_lines(ctx: _Ctx, inst: ElementMeasures, gf_insts: list[ElementMeasures]) -> list[QuantityLine]:
    code, ename = SUBSTRUCTURE_CODE
    oid = inst.assembly_id
    sel_link = _selection_link(inst)
    trace0 = [sel_link] + inst.trace_extra + ([ctx.calib] if ctx.geometry_ok else [])
    ms = inst.measures
    L_m = ms.get("trench_length")
    refs = list(L_m.geometry_refs) if L_m else []
    g_links = _geom_links(L_m, "foundation trench_length") if (L_m and L_m.value is not None) else []
    trace = trace0 + g_links
    try:
        opt: FoundationOption = ctx.library.foundation(oid)
    except KeyError:
        return [_unresolved(line_id=f"{code}.all.{oid}.0", code=code, ename=ename,
                            description="Substructure", reason=f"foundation option '{oid}' not in library",
                            unit="", trace=trace0, refs=refs, assembly_id=oid, layer_index=0)]
    r, ta = ctx.rules, ctx.ta
    w, d, cd = opt.trench_width_m, opt.trench_depth_m, opt.concrete_depth_m
    sel_b = inst.selection_basis
    names = _expected_substructure(opt.kind)

    def unresolved_all(reason: str) -> list[QuantityLine]:
        return [_unresolved(line_id=f"{code}.all.{oid}.{SUBSTRUCTURE_LINE_INDEX[k]}", code=code, ename=ename,
                            description=f"{k.replace('_', ' ').capitalize()} - {opt.name}", reason=reason,
                            unit=_SUB_UNITS[k], trace=trace0, refs=refs, assembly_id=oid,
                            layer_index=SUBSTRUCTURE_LINE_INDEX[k], trade="groundworks") for k in names]

    if inst.unresolved_reason:
        return unresolved_all(inst.unresolved_reason)
    needed = [ms.get(n) for n in ("trench_length", "centreline_perimeter", "separating_wall_length",
                                  "internal_loadbearing_length", "ground_floor_area", "average_ffl")]
    missing = [m.formula.removeprefix("UNRESOLVED: ") for m in needed if m is None or m.value is None]
    dims_missing = [n for n, tv in (("trench width", w), ("trench depth", d), ("concrete depth", cd))
                    if tv.value is None]
    if missing or dims_missing:
        return unresolved_all("; ".join(missing + [f"{opt.option_id} {x} unknown" for x in dims_missing]))
    L = L_m.value
    W, D, CD = w.value, d.value, cd.value
    gfa = ms["ground_floor_area"]
    osa = ms.get("oversite_area")
    fdesc = opt.name
    idx = SUBSTRUCTURE_LINE_INDEX
    out: list[QuantityLine] = []
    ex_b = _weakest(L_m.basis, w.basis, d.basis, sel_b)
    v_trench = L * W * D
    out.append(_op_line(
        line_id=f"{code}.all.{oid}.{idx['trench_excavation']}", description=f"Trench excavation - {fdesc}",
        status=QuantityStatus.DERIVED, assembly_id=oid, layer_index=idx["trench_excavation"],
        cost_key=r.excavation_cost_key, unit="m3", measure_name="trench_length", measure_value=L, measure_unit="m",
        formula=f"trench {L:.3f} m × {W:g} m wide × {D:g} m deep = {v_trench:.3f} m3 (bank)", qty=v_trench,
        trade="groundworks", hours_per_unit=r.excavation_hours_per_m3, basis=ex_b, trace=trace, refs=refs,
        notes="Machine excavation; trench support / dewatering not quantified."))
    od = ta.oversite_dig_depth_m
    ov_link = TraceLink(kind="assumption", ref="takeoff.oversite_dig_depth_m",
                        description=f"oversite dig depth {od.label()} ({od.basis.value})")
    osa_ok = osa is not None and osa.value is not None
    v_over = osa.value * od.value if (osa_ok and od.value is not None) else None
    if v_over is None:
        why = "oversite dig depth unknown" if od.value is None else (
            osa.formula.removeprefix("UNRESOLVED: ") if osa is not None else "oversite area not measured")
        out.append(_unresolved(line_id=f"{code}.all.{oid}.{idx['oversite_excavation']}", code=code, ename=ename,
                               description=f"Oversite excavation - {fdesc}", reason=why,
                               unit="m3", trace=trace0 + [ov_link], refs=list(gfa.geometry_refs), assembly_id=oid,
                               layer_index=idx["oversite_excavation"], trade="groundworks"))
    else:
        out.append(_op_line(
            line_id=f"{code}.all.{oid}.{idx['oversite_excavation']}",
            description=f"Oversite excavation / topsoil strip under ground-floor slab, outside the trenches - {fdesc}",
            status=QuantityStatus.DERIVED, assembly_id=oid, layer_index=idx["oversite_excavation"],
            cost_key=r.excavation_cost_key, unit="m3", measure_name="oversite_area", measure_value=osa.value,
            measure_unit="m2",
            formula=f"oversite area {osa.value:.3f} m2 (ground-storey GIA {gfa.value:.3f} m2 less trench plan inside "
                    f"the GIA {gfa.value - osa.value:.3f} m2) × {od.value:g} m = {v_over:.3f} m3 (bank)",
            qty=v_over, trade="groundworks", hours_per_unit=r.oversite_hours_per_m3,
            basis=_weakest(osa.basis, od.basis, sel_b),
            trace=trace0 + [ov_link] + _geom_links(osa, "oversite_area"), refs=list(osa.geometry_refs),
            notes="Trench excavation is measured in full; the trench plan inside the GIA is excluded here "
                  "(no double count)."))
    bf = ta.spoil_bulking_factor
    bulk_link = TraceLink(kind="assumption", ref="takeoff.spoil_bulking_factor",
                          description=f"spoil bulking {bf.label()}; all spoil assumed removed off site")
    if bf.value is None or v_over is None:
        out.append(_unresolved(line_id=f"{code}.all.{oid}.{idx['spoil_disposal']}", code=code, ename=ename,
                               description=f"Spoil disposal - {fdesc}", reason="bulking factor or oversite volume "
                               "unknown", unit="m3", trace=trace0 + [bulk_link], refs=refs, assembly_id=oid,
                               layer_index=idx["spoil_disposal"], trade="groundworks"))
    else:
        v_bank = v_trench + v_over
        v_loose = v_bank * bf.value
        out.append(_op_line(
            line_id=f"{code}.all.{oid}.{idx['spoil_disposal']}",
            description=f"Load and remove excavated spoil off site (loose volume) - {fdesc}",
            status=QuantityStatus.DERIVED, assembly_id=oid, layer_index=idx["spoil_disposal"],
            cost_key=r.disposal_cost_key, unit="m3", measure_name="excavated_volume", measure_value=v_bank,
            measure_unit="m3", formula=f"({v_trench:.3f} + {v_over:.3f}) m3 bank × bulking {bf.value:g} = "
            f"{v_loose:.3f} m3 loose", qty=v_loose, trade="groundworks", hours_per_unit=r.disposal_hours_per_m3,
            basis=_weakest(ex_b, od.basis, bf.basis, osa.basis), trace=trace + [ov_link, bulk_link], refs=refs,
            notes="No reuse / backfill credited (assumption); contamination not assessed."))
    c_b = _weakest(L_m.basis, w.basis, cd.basis, sel_b)
    v_conc = L * W * CD
    piled = opt.kind == FoundationKind.PILED_ALLOWANCE
    c_status = QuantityStatus.ALLOWANCE if piled else QuantityStatus.DERIVED
    what = {FoundationKind.RAFT: "Raft thickened edges / internal thickenings",
            FoundationKind.PILED_ALLOWANCE: "Ground beams (allowance)"}.get(opt.kind, "Foundation concrete")
    out.append(_mat_line(
        ctx, line_id=f"{code}.all.{oid}.{idx['concrete']}", description=f"{what} - {fdesc}", status=c_status,
        assembly_id=oid, layer_index=idx["concrete"], material_id=opt.concrete_material_id,
        measure_name="trench_length", measure_value=L, measure_unit="m",
        formula=f"{L:.3f} m × {W:g} m × {CD:g} m = {v_conc:.3f} m3", qty=v_conc, trade="groundworks",
        hours_per_unit=r.concrete_hours_per_m3, basis=c_b, trace=trace, refs=refs,
        notes="Concrete mix / strength requires design." + (" Allowance only." if piled else "")))
    reinf_volume = 0.0
    reinf_parts: list[str] = []
    if opt.kind == FoundationKind.RAFT:
        rt = opt.raft_thickness_m
        if rt is None or rt.value is None:
            out.append(_unresolved(line_id=f"{code}.all.{oid}.{idx['raft_extra_thickness']}", code=code,
                                   ename=ename, description=f"Raft slab extra thickness - {fdesc}",
                                   reason="raft thickness unknown", unit="m3", trace=trace0, refs=refs,
                                   assembly_id=oid, layer_index=idx["raft_extra_thickness"], trade="groundworks"))
            reinf_volume = v_conc
            reinf_parts.append(f"edges {v_conc:.3f} m3")
        else:
            parts, v_extra, bases, grefs = [], 0.0, [rt.basis, sel_b], []
            slab_total = 0.0
            for gi in gf_insts:
                ea = gi.measures.get("element_area")
                if ea is None or ea.value is None:
                    continue
                st = _slab_thickness(ctx.asms.get(gi.assembly_id))
                extra = max(0.0, rt.value - st)
                v_extra += ea.value * extra
                slab_total += ea.value * max(rt.value, st)
                parts.append(f"{gi.block_id}: {ea.value:.3f} m2 × ({rt.value:g} − {st:g}) m")
                bases += [ea.basis, gi.selection_basis]
                grefs += list(ea.geometry_refs)
            out.append(_mat_line(
                ctx, line_id=f"{code}.all.{oid}.{idx['raft_extra_thickness']}",
                description=f"Raft slab thickness beyond the ground-floor slab layer - {fdesc}",
                status=QuantityStatus.DERIVED, assembly_id=oid, layer_index=idx["raft_extra_thickness"],
                material_id=opt.concrete_material_id, measure_name="ground_floor_area", measure_value=gfa.value,
                measure_unit="m2", formula=(" + ".join(parts) or "no ground floor") + f" = {v_extra:.3f} m3",
                qty=v_extra, trade="groundworks", hours_per_unit=r.concrete_hours_per_m3, basis=_weakest(bases),
                trace=trace0 + _geom_links(gfa, "ground_floor_area"), refs=grefs,
                notes="The ground-floor assembly's slab layer is taken as part of the raft (no double count)."))
            reinf_volume = v_conc + slab_total
            reinf_parts.append(f"edges {v_conc:.3f} m3 + slab {slab_total:.3f} m3")
    else:
        ffl = ms["average_ffl"]
        h = max(0.0, D - CD) + ffl.value
        Pc, Ls, Li = ms["centreline_perimeter"].value, ms["separating_wall_length"].value, \
            ms["internal_loadbearing_length"].value
        leaf_len = r.leaves_external * Pc + r.leaves_separating * Ls + r.leaves_internal * Li
        area = leaf_len * h
        b_b = _weakest(L_m.basis, d.basis, cd.basis, ffl.basis, sel_b)
        geo = (f"({r.leaves_external} × {Pc:.3f} + {r.leaves_separating} × {Ls:.3f} + {r.leaves_internal} × "
               f"{Li:.3f}) m × ({D:g} − {CD:g} + FFL {ffl.value:.3f}) m = {area:.3f} m2 leaf area")
        n_blocks = area * r.blocks_per_m2
        bstatus = QuantityStatus.ALLOWANCE if piled else QuantityStatus.DERIVED
        out.append(_mat_line(
            ctx, line_id=f"{code}.all.{oid}.{idx['below_ground_blockwork']}",
            description=f"Below-ground blockwork from foundation to DPC - {fdesc}", status=bstatus,
            assembly_id=oid, layer_index=idx["below_ground_blockwork"], material_id=r.block_material_id,
            measure_name="below_ground_masonry_area", measure_value=area, measure_unit="m2",
            formula=f"{geo} × {r.blocks_per_m2:g} nr/m2 = {n_blocks:.3f} nr", qty=n_blocks, trade="bricklaying",
            hours_per_unit=r.block_hours_per_nr, basis=b_b, trace=trace + _geom_links(ffl, "average_ffl"),
            refs=refs, notes="Two leaves under cavity / separating walls, one under internal loadbearing walls."))
        v_mortar = area * r.mortar_m3_per_m2_block
        out.append(_mat_line(
            ctx, line_id=f"{code}.all.{oid}.{idx['below_ground_mortar']}",
            description=f"Mortar to below-ground blockwork - {fdesc}", status=bstatus, assembly_id=oid,
            layer_index=idx["below_ground_mortar"], material_id=r.mortar_material_id,
            measure_name="below_ground_masonry_area", measure_value=area, measure_unit="m2",
            formula=f"{area:.3f} m2 × {r.mortar_m3_per_m2_block:g} m3/m2 = {v_mortar:.4f} m3", qty=v_mortar,
            trade="bricklaying", hours_per_unit=0.0, basis=b_b, trace=trace, refs=refs))
        if piled:
            reinf_volume = v_conc
            reinf_parts.append(f"ground beams {v_conc:.3f} m3")
    if piled:
        ppm, pl = opt.piles_per_m, opt.pile_length_m
        if ppm is None or pl is None or ppm.value is None or pl.value is None:
            out.append(_unresolved(line_id=f"{code}.all.{oid}.{idx['piles']}", code=code, ename=ename,
                                   description=f"Piles (allowance) - {fdesc}", reason="piles per metre or pile "
                                   "length unknown", unit="m", trace=trace0, refs=refs, assembly_id=oid,
                                   layer_index=idx["piles"], trade="groundworks"))
        else:
            n = int(math.ceil(L * ppm.value - 1e-9))
            qm = n * pl.value
            out.append(_op_line(
                line_id=f"{code}.all.{oid}.{idx['piles']}", description=f"Piles (allowance) - {fdesc}",
                status=QuantityStatus.ALLOWANCE, assembly_id=oid, layer_index=idx["piles"],
                cost_key=r.piling_cost_key, unit="m", measure_name="trench_length", measure_value=L, measure_unit="m",
                formula=f"ceil({L:.3f} m × {ppm.value:g}/m) = {n} piles × {pl.value:g} m = {qm:.3f} m of pile",
                qty=qm, trade="groundworks", hours_per_unit=0.0, basis=_weakest(L_m.basis, ppm.basis, pl.basis,
                                                                                sel_b, Basis.ASSUMED),
                trace=trace + [TraceLink(kind="allowance", ref=f"foundation:{oid}.piles",
                                         description="pile number and length are an allowance; pile design by a "
                                                     "specialist after ground investigation")],
                refs=refs, notes="Specialist subcontract allowance; rate assumed to include labour and plant."))
    if opt.kind in (FoundationKind.RAFT, FoundationKind.PILED_ALLOWANCE):
        ra = ta.reinforcement_allowance_kg_per_m3
        link = TraceLink(kind="allowance", ref="takeoff.reinforcement_allowance_kg_per_m3",
                         description=f"reinforcement allowance {ra.label()} - not a reinforcement design or schedule")
        if ra.value is None:
            out.append(_unresolved(line_id=f"{code}.all.{oid}.{idx['reinforcement_allowance']}", code=code,
                                   ename=ename, description=f"Reinforcement allowance - {fdesc}",
                                   reason="reinforcement allowance unknown", unit="kg", trace=trace0 + [link],
                                   refs=refs, assembly_id=oid, layer_index=idx["reinforcement_allowance"],
                                   trade="groundworks"))
        else:
            kg = reinf_volume * ra.value
            out.append(_op_line(
                line_id=f"{code}.all.{oid}.{idx['reinforcement_allowance']}",
                description=f"Reinforcement allowance (indicative; no reinforcement schedule) - {fdesc}",
                status=QuantityStatus.ALLOWANCE, assembly_id=oid, layer_index=idx["reinforcement_allowance"],
                cost_key=r.reinforcement_cost_key, unit="kg", measure_name="concrete_volume",
                measure_value=reinf_volume, measure_unit="m3",
                formula=f"({' + '.join(reinf_parts)}) × {ra.value:g} kg/m3 = {kg:.1f} kg", qty=kg,
                trade="groundworks", hours_per_unit=r.reinforcement_hours_per_kg,
                basis=_weakest(c_b, ra.basis, Basis.ASSUMED), trace=trace + [link], refs=refs,
                material_id=r.reinforcement_material_id,
                notes="Labelled allowance only; reinforcement requires an engineer's design."))
    return out


# -------------------------------------------------------------------- allowances
def _finishable_area(ctx: _Ctx, insts: list[ElementMeasures]) -> Measure:
    total, parts, bases, refs = 0.0, [], [], []
    for inst in insts:
        if inst.element == ElementType.EXTERNAL_WALL:
            m = inst.measures.get("internal_face_area")
            if m is None or m.value is None:
                return Measure(None, "m2", tuple(refs), Basis.UNKNOWN,
                               f"UNRESOLVED: internal wall faces of {inst.block_id} unresolved")
            total += m.value
            bases.append(m.basis)
            if m.value > 0:
                parts.append(f"walls {inst.block_id} {m.value:.2f}")
                refs.append(f"block:{inst.block_id}")
        elif inst.element == ElementType.INTERNAL_PARTITION:
            m = inst.measures.get("element_area")
            if m is None or m.value is None:
                return Measure(None, "m2", tuple(refs), Basis.UNKNOWN, "UNRESOLVED: partition allowance unresolved")
            total += 2.0 * m.value
            bases.append(m.basis)
            parts.append(f"partitions 2 × {m.value:.2f}")
    heated = {b.block_id: b.heated for b in ctx.twin.blocks}
    # separating-wall faces towards heated blocks: the same measures the plaster layers use
    sep, sep_bases = 0.0, []
    for inst in insts:
        if inst.element != ElementType.SEPARATING_WALL:
            continue
        for name in ("internal_face_area_a", "internal_face_area_b"):
            m = inst.measures.get(name)
            if m is None or m.value is None:
                return Measure(None, "m2", tuple(refs), Basis.UNKNOWN,
                               f"UNRESOLVED: separating wall faces of {inst.block_id} unresolved")
            sep += m.value
            sep_bases.append(m.basis)
    if sep > 0:
        total += sep
        parts.append(f"separating faces {sep:.2f}")
        bases += sep_bases
    ceil = sum(sum(bm.gia_by_storey) for bm in ctx.metrics.blocks if bm.heated)
    if ceil > 0:
        total += ceil
        parts.append(f"ceilings {ceil:.2f}")
        bases += [i.measures["element_area"].basis for i in insts
                  if i.element == ElementType.GROUND_FLOOR and i.block_id and heated.get(i.block_id)]
    refs += [f"storey:{s.storey}" for s in ctx.metrics.storeys]
    return Measure(total, "m2", tuple(refs), _weakest(bases) if bases else Basis.ASSUMED,
                   " + ".join(parts) + f" = {total:.3f} m2 finishable (walls, ceilings)")


def _gia_measure(ctx: _Ctx, heated_only: bool = True) -> Measure:
    t = ctx.twin
    blocks = [b for b in t.blocks if b.heated or not heated_only]
    bases = [tv.basis for b in blocks for tv in (b.width, b.depth, b.storeys, b.floor_to_floor)]
    if len(t.blocks) > 1:
        bases += [tv.basis for b in t.blocks for tv in (b.origin_x, b.origin_y)]
    bases.append(t.assemblies.basis.get(ElementType.EXTERNAL_WALL.value, Basis.ASSUMED))
    v = ctx.metrics.heated_gia_m2 if heated_only else ctx.metrics.gia_m2
    refs = tuple(f"block:{b.block_id}" for b in blocks) + tuple(f"storey:{s.storey}" for s in ctx.metrics.storeys)
    label = "heated GIA" if heated_only else "GIA"
    return Measure(v, "m2", refs, _weakest(bases) if blocks else Basis.ASSUMED, f"{label} = {v:.3f} m2")


def _allowance_lines(ctx: _Ctx, insts: list[ElementMeasures]) -> list[QuantityLine]:
    out: list[QuantityLine] = []
    twin = ctx.twin
    if ctx.geometry_ok:
        max_storeys: Optional[int] = max((bm.storeys for bm in ctx.metrics.blocks), default=0)
    else:
        vals = [b.storeys.value for b in twin.blocks]
        max_storeys = int(round(max(vals))) if vals and None not in vals else None
    finish: Optional[Measure] = None
    for rule in ctx.library.allowances:
        code, _, ename = rule.element.partition(" ")
        ename = ename or rule.element
        line_id = f"{code}.allow.{rule.allowance_id}"
        a_link = TraceLink(kind="allowance", ref=rule.allowance_id,
                           description=f"{rule.description}: {rule.quantity_per.label()} {rule.basis_measure}")
        trace = [a_link]
        if rule.quantity_per.basis != Basis.USER_CONFIRMED:
            trace.append(TraceLink(kind="assumption", ref=f"allowance:{rule.allowance_id}.quantity_per",
                                   description=f"{BASIS_LABEL[rule.quantity_per.basis]} allowance rate"))
        if rule.min_storeys > 1:
            if max_storeys is None:
                out.append(_unresolved(line_id=line_id, code=code, ename=ename, description=rule.description,
                                       reason="storey count unknown", unit=rule.unit, trace=trace, refs=[],
                                       allowance_id=rule.allowance_id, trade=rule.trade))
                continue
            if max_storeys < rule.min_storeys:
                continue
        bm = rule.basis_measure
        m: Optional[Measure]
        if bm == "per_dwelling":
            m = Measure(float(twin.dwellings), "dwelling", (), Basis.ASSUMED, f"{twin.dwellings} dwelling(s)")
        elif bm == "per_bathroom":
            bt = twin.bathrooms
            m = (Measure(float(bt.value), "nr", (), bt.basis, f"{bt.value:g} bathroom(s) ({bt.basis.value})")
                 if bt.value is not None else Measure(None, "nr", (), Basis.UNKNOWN, "UNRESOLVED: bathroom count unknown"))
        elif not ctx.geometry_ok:
            m = Measure(None, "m2", (), Basis.UNKNOWN, "UNRESOLVED: geometry could not be computed")
        elif bm == "per_m2_gia":
            m = _gia_measure(ctx, heated_only=True)
        elif bm == "per_m2_gea":
            m = Measure(ctx.metrics.gea_m2, "m2", tuple(f"storey:{s.storey}" for s in ctx.metrics.storeys),
                        _gia_measure(ctx, heated_only=False).basis, f"GEA = {ctx.metrics.gea_m2:.3f} m2")
        elif bm == "per_storey":
            m = Measure(float(max_storeys or 0), "storeys", tuple(f"storey:{s.storey}" for s in ctx.metrics.storeys),
                        _weakest([b.storeys.basis for b in twin.blocks]), f"{max_storeys} storeys")
        elif bm == "per_m2_finishable":
            finish = finish or _finishable_area(ctx, insts)
            m = finish
        else:  # pragma: no cover - guarded by the model Literal
            m = Measure(None, "", (), Basis.UNKNOWN, f"UNRESOLVED: unsupported basis measure '{bm}'")
        qp = rule.quantity_per
        if m.value is None or qp.value is None:
            reason = m.formula.removeprefix("UNRESOLVED: ") if m.value is None else "allowance rate unknown"
            out.append(_unresolved(line_id=line_id, code=code, ename=ename, description=rule.description,
                                   reason=reason, unit=rule.unit, trace=trace, refs=list(m.geometry_refs),
                                   allowance_id=rule.allowance_id, material_id=rule.material_id,
                                   measure_name=bm, measure_unit=m.unit, trade=rule.trade))
            continue
        q = m.value * qp.value
        out.append(_line(
            line_id=line_id, element_code=code, element_name=ename, description=rule.description,
            status=QuantityStatus.ALLOWANCE, assembly_id=None, layer_index=None, material_id=rule.material_id,
            allowance_id=rule.allowance_id, cost_key=rule.cost_key, measure_name=bm, measure_value=m.value,
            measure_unit=m.unit, formula=f"{m.formula}; × {qp.value:g} {qp.unit or rule.unit} = {q:.3f} {rule.unit}",
            unit=rule.unit, installed_qty=q, cutting_loss_fraction=0.0, cutting_loss_qty=0.0, waste_fraction=0.0,
            waste_qty=0.0, required_qty=q, purchase_unit=rule.unit, purchase_per_installed=1.0, pack_size=1.0,
            packs=None, purchased_qty=q, surplus_qty=0.0, trade=rule.trade,
            labour_hours=q * rule.labour_hours_per_unit, basis=_weakest(m.basis, qp.basis), trace=trace,
            geometry_refs=list(m.geometry_refs), notes=rule.notes or "Labelled allowance; not measured."))
    return out


# ------------------------------------------------------------------------- main
def _empty_metrics(t_ext: float, t_sep: float, reason: str) -> GeometryMetrics:
    z = 0.0
    return GeometryMetrics(
        blocks=[], pieces=[], storeys=[], roofs=[], external_wall_thickness_m=t_ext, separating_wall_thickness_m=t_sep,
        footprint_area_m2=z, ground_perimeter_m=z, gea_m2=z, gia_m2=z, heated_gia_m2=z, external_wall_gross_m2=z,
        external_wall_net_m2=z, separating_wall_area_m2=z, window_area_m2=z, door_area_m2=z, garage_door_area_m2=z,
        opening_area_m2=z, roof_plan_area_m2=z, roof_surface_area_m2=z, pitched_roof_surface_area_m2=z,
        flat_roof_area_m2=z, ground_floor_area_m2=z, intermediate_floor_area_m2=z, top_ceiling_area_m2=z,
        heated_volume_m3=z, conventions=dict(GEOMETRY_CONVENTIONS),
        warnings=[f"Geometry unresolved: {reason}"],
    )


def _code_key(code: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in code.split("."))
    except ValueError:
        return (99,)


def calculate_quantities(twin: BuildingTwin, library: AssemblyLibrary, *, metrics: Optional[GeometryMetrics] = None,
                         assumptions: Union[TakeoffAssumptions, AssumptionLibrary, None] = None,
                         rules: SubstructureRules = SUBSTRUCTURE_RULES) -> BillOfQuantities:
    """Bill of quantities for ``twin`` with ``library`` (see module docstring).

    ``metrics`` may be passed when already computed for this twin (fast path for simulation); it
    must correspond to the twin's blocks/openings and selected wall thicknesses.  ``assumptions``
    holds the labelled take-off priors (partition allowance, bulking, oversite depth,
    reinforcement allowance); an :class:`AssumptionLibrary` is accepted for the partition allowance.
    Never raises for invalid geometry: affected lines are returned ``UNRESOLVED``.
    """
    if isinstance(assumptions, AssumptionLibrary):
        ta = TakeoffAssumptions.from_assumption_library(assumptions)
    else:
        ta = assumptions or TakeoffAssumptions()
    warnings: list[str] = []
    reason: Optional[str] = None
    t_ext = t_sep = 0.0
    try:
        t_ext, t_sep = wall_thicknesses(twin, library)
    except ValueError as e:
        if metrics is None:
            reason = f"wall thickness unknown ({e})"
        else:
            warnings.append(f"Wall assembly problem: {e}")
    unknown = unknown_openings(twin)
    if metrics is None and reason is None:
        try:
            src = twin
            if unknown:
                src = twin.model_copy(update={"openings": [o for o in twin.openings if o.opening_id not in unknown]})
            blocks, openings = params_from_twin(src)
            metrics = compute_metrics(blocks, openings, t_ext, t_sep)
        except GeometryError as e:
            reason = f"geometry could not be computed: {e}"
    elif metrics is not None and reason is None and (
            abs(metrics.external_wall_thickness_m - t_ext) > 1e-6 or abs(metrics.separating_wall_thickness_m - t_sep) > 1e-6):
        warnings.append(f"Metrics were computed with wall thicknesses {metrics.external_wall_thickness_m:.4f} / "
                        f"{metrics.separating_wall_thickness_m:.4f} m but the selected assemblies are {t_ext:.4f} / "
                        f"{t_sep:.4f} m; internal areas follow the metrics supplied.")
    geometry_ok = reason is None and metrics is not None
    off = off_storey_openings(twin, {bm.block_id: bm.storeys for bm in metrics.blocks}) if geometry_ok else {}
    for oid, why in unknown.items():
        if oid not in off:  # off-storey openings are excluded altogether (warned by element_measures)
            warnings.append(f"{why}: dependent quantities are unresolved.")
    if not geometry_ok:
        metrics = _empty_metrics(t_ext, t_sep, reason or "unknown")
        warnings.append(f"Geometry unresolved - {reason}. Quantities depending on geometry are UNRESOLVED.")
    assert metrics is not None
    warnings.extend(metrics.warnings if geometry_ok else [])
    sel = twin.assemblies
    for bid, ov in sel.block_overrides.items():
        aid = ov.get(ElementType.EXTERNAL_WALL.value)
        if aid and aid in {a.assembly_id for a in library.assemblies} and abs(
                library.assembly(aid).total_thickness_m - t_ext) > 1e-6:
            warnings.append(f"Block {bid} uses external wall '{aid}' of a different thickness; internal areas use "
                            f"the twin-wide wall thickness {t_ext:.4f} m (indicative).")
    ctx = _Ctx(twin=twin, library=library, metrics=metrics, ta=ta, rules=rules,
               mats={m.material_id: m for m in library.materials},
               asms={a.assembly_id: a for a in library.assemblies},
               calib=TraceLink(kind="calibration", ref=f"calibration:{twin.calibration_method}",
                               description="dimensions scaled with this calibration method"),
               geometry_ok=geometry_ok, warnings=warnings)
    if geometry_ok:
        insts = element_measures(twin, metrics, library, assumptions=ta, unknown=unknown, warnings=warnings)
    else:
        insts = unresolved_instances(twin, library, reason or "geometry unresolved")
    gf_insts = [i for i in insts if i.element == ElementType.GROUND_FLOOR]
    lines: list[QuantityLine] = []
    for inst in insts:
        if inst.element_key == FOUNDATION_KEY:
            lines.extend(_substructure_lines(ctx, inst, gf_insts))
        else:
            lines.extend(_assembly_lines(ctx, inst))
    lines.extend(_allowance_lines(ctx, insts))
    lines.sort(key=lambda ln: _code_key(ln.element_code))
    return BillOfQuantities.model_construct(
        twin_id=twin.twin_id, twin_version=twin.version, library_name=library.name, lines=lines,
        geometry=metrics, conventions=dict(QUANTITY_CONVENTIONS), warnings=warnings,
    )
