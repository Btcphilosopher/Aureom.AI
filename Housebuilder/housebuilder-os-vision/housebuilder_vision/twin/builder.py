"""Parametric twin construction, user edits, hidden-side rules and hashing.

* :func:`build_parametric_twin` turns a selected :class:`GeometryHypothesis`
  into a :class:`BuildingTwin` (blocks and observed openings copied, visual
  finishes attached, assembly selection copied verbatim - visual finishes never
  set assemblies) and fills hidden facades with
  :func:`regenerate_hidden_openings`.
* :func:`apply_twin_edit` applies one validated :class:`TwinEdit` and returns a
  **new** twin (the input is never mutated) with ``version + 1``, an
  :class:`EditRecord` appended to ``edit_log`` and the edited value marked
  ``USER_CONFIRMED`` (numeric values via :meth:`TrackedValue.edited`, so the
  value's own history records the change).  When a block's width/depth
  changes, blocks attached at its right/rear edge (and blocks attached to
  those, on the same side of the old edge) move with it so composite
  footprints stay valid; blocks at its left/front keep their position.
  Geometry, opening and hidden-side edits regenerate rule-filled openings.
* :func:`regenerate_hidden_openings` drops openings created by hidden-side
  rules and re-creates them: for each *heated* block and each external side
  that is neither in ``visible_sides`` nor already specified by an observed /
  user opening, typical windows are spread evenly per storey over the
  external wall pieces (never on pieces shared with another block) so that
  glazed area ~= ratio x external rectangular wall area of that side
  (rear ratio for front/rear faces, side ratio for left/right faces), plus
  ``rear_door_count`` patio doors (1.8 x 2.1 m) on the ground floor of the
  main block's rear (or of a heated block attached behind it when the main
  rear is fully covered).  Rule openings are ``ASSUMED`` with
  ``source="hidden-side rule"`` and ``hidden_side_rule`` naming the rule.
  Unheated blocks (garages) get none.
* Editing, adding or deleting an opening on a hidden side *freezes* that side:
  it is recorded in ``hidden.specified_sides``, its current rule openings are
  kept as ordinary assumed openings (rule tag cleared, source noted) and the
  side is no longer regenerated (so a deleted rule window stays deleted).
* :func:`twin_hash` is the SHA-256 of the canonical JSON of the twin
  (``model_dump(mode="json")``, sorted keys) excluding ``edit_log`` and every
  per-value ``history`` list.

Boundaries: the twin is a conceptual parametric reconstruction; edits are
validated for geometric sanity only (positive sizes, storeys 1-6, pitch
0-75 deg for pitched roofs, glazing ratios 0-0.9) - not for buildability,
structure or compliance.  Assembly ids are validated by the quantities module.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import deque
from typing import Any, Callable, Iterable, Optional, Sequence

from ..core.models import (
    AnalysisResult,
    AssemblySelection,
    Block,
    BlockRole,
    BuildingTwin,
    GeometryHypothesis,
    Opening,
    OpeningKind,
    RoofForm,
    Side,
    TwinEdit,
    VisualFinish,
)
from ..core.provenance import Basis, EditRecord, TrackedValue, assumed, confirmed
from ..core.settings import AssumptionLibrary, ProjectSettings
from ..core.units import UnitError, convert, parse_quantity
from ..geometry.footprint import TOL, GeometryError, Piece, Rect, side_pieces, validate_rects

HIDDEN_RULE_SOURCE = "hidden-side rule"
PATIO_DOOR_SIZE = (1.80, 2.10)
EDGE_MARGIN_M = 0.40  # clear wall at piece ends and between rule openings
MAX_STOREYS = 6
MAX_RATIO = 0.9
_ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,80}$")
_SELECTION_KEYS = ("external_wall", "separating_wall", "internal_partition", "ground_floor", "intermediate_floor",
                   "pitched_roof", "flat_roof", "window", "external_door", "garage_door", "foundation")


# =============================================================================
# Visual finishes (appearance only)
# =============================================================================
#: Ordered (longest phrases first) colour words -> sRGB guess.  Appearance only.
_COLOUR_WORDS: tuple[tuple[str, str], ...] = (
    ("red-brown", "#8B4A36"), ("red brown", "#8B4A36"), ("reddish brown", "#8B4A36"),
    ("dark grey", "#4A4D53"), ("dark gray", "#4A4D53"), ("light grey", "#B6B9BD"), ("light gray", "#B6B9BD"),
    ("mid grey", "#8C8F94"), ("mid gray", "#8C8F94"), ("off-white", "#E9E4D6"), ("off white", "#E9E4D6"),
    ("anthracite", "#3A3D41"), ("charcoal", "#3F4246"), ("terracotta", "#B5653F"), ("ivory", "#ECE6D2"),
    ("cream", "#E8DDBE"), ("buff", "#D8C28E"), ("beige", "#CDBA96"), ("sand", "#D2BE94"),
    ("white", "#ECEBE5"), ("black", "#2B2C2E"), ("grey", "#8C8F94"), ("gray", "#8C8F94"),
    ("silver", "#B8BBBE"), ("slate", "#5A6068"), ("red", "#9B4A3C"), ("brown", "#7B5638"),
    ("orange", "#C2733F"), ("yellow", "#D9C27A"), ("green", "#5E7A55"), ("blue", "#4F6D8A"),
    ("oak", "#A47A4F"), ("cedar", "#A4683F"), ("timber", "#A47A4F"), ("wood", "#A47A4F"),
)
_MATERIAL_LOOK: tuple[tuple[str, str], ...] = (
    ("brick", "#9A5B45"), ("tile", "#5C5F64"), ("render", "#E6E1D3"), ("stucco", "#E6E1D3"),
    ("glass", "#7D97A8"), ("glazing", "#7D97A8"), ("stone", "#B9AE98"), ("metal", "#9EA3A8"),
)
DEFAULT_FINISH_HEX = {"walls": "#E8E2D0", "roof": "#3C3F44", "garage_door": "#5A5E66", "windows": "#5A5E66",
                      "doors": "#5A5E66", "other": "#8C8F94"}
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def colour_from_appearance(appearance: str, element: str = "other") -> str:
    """Best-effort sRGB hex guess from appearance words (purely visual)."""
    text = _CTRL.sub(" ", appearance or "").lower()[:120]
    for word, hexv in _COLOUR_WORDS:
        if re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text):
            return hexv
    for word, hexv in _MATERIAL_LOOK:
        if word in text:
            return hexv
    return DEFAULT_FINISH_HEX.get(element, DEFAULT_FINISH_HEX["other"])


def visual_finishes_from_analysis(analysis: AnalysisResult) -> list[VisualFinish]:
    """Visual finishes (appearance + colour guess) from the observed facade finishes.

    Basis ``INFERRED`` (``USER_CONFIRMED`` if the finish was confirmed).  These are
    appearance only and never select a construction assembly.
    """
    merged: dict[tuple[str, str], VisualFinish] = {}
    for fac in analysis.facades:
        for fin in fac.finishes:
            appearance = _CTRL.sub(" ", fin.appearance or "").strip()[:120]
            if not appearance:
                continue
            key = (fin.element, appearance.lower())
            if key in merged:
                vf = merged[key]
                for fid in fin.feature_ids:
                    if fid not in vf.feature_ids:
                        vf.feature_ids.append(fid)
                continue
            basis = Basis.USER_CONFIRMED if fin.basis == Basis.USER_CONFIRMED else Basis.INFERRED
            merged[key] = VisualFinish(element=fin.element, appearance=appearance,
                                       colour_hex=colour_from_appearance(appearance, fin.element), basis=basis,
                                       feature_ids=list(fin.feature_ids))
    return list(merged.values())


# =============================================================================
# Build
# =============================================================================
def _safe_twin_id(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.:\-]", "_", text)[:80]
    return s or "twin"


def build_parametric_twin(hypothesis: GeometryHypothesis, *, selection: AssemblySelection,
                          settings: Optional[ProjectSettings] = None,
                          visual_finishes: Optional[Sequence[VisualFinish]] = None,
                          twin_id: Optional[str] = None) -> BuildingTwin:
    """Twin from a hypothesis (blocks/openings copied, hidden facades rule-filled).

    Raises ``ValueError`` if the hypothesis footprint is invalid (overlaps,
    non-positive sizes) or ``twin_id`` is not a valid id.
    """
    tid = twin_id if twin_id is not None else _safe_twin_id(f"twin-{hypothesis.hypothesis_id}")
    if not _ID_RE.match(tid):
        raise ValueError(f"invalid twin_id '{tid}'")
    twin = BuildingTwin(
        twin_id=tid,
        name=f"{hypothesis.hypothesis_id}: {hypothesis.name}"[:200],
        settings=(settings or ProjectSettings()).model_copy(deep=True),
        blocks=[b.model_copy(deep=True) for b in hypothesis.blocks],
        openings=[o.model_copy(deep=True) for o in hypothesis.openings if not o.hidden_side_rule],
        hidden=hypothesis.hidden.model_copy(deep=True),
        assemblies=selection.model_copy(deep=True),
        visual_finishes=[v.model_copy(deep=True) for v in (visual_finishes or [])],
        source_hypothesis_id=hypothesis.hypothesis_id,
        calibration_method=hypothesis.calibration_method,
    )
    _check_footprint(twin)
    return regenerate_hidden_openings(twin)


def _rects(twin: BuildingTwin) -> Optional[list[Rect]]:
    rects = []
    for b in twin.blocks:
        vals = (b.origin_x.value, b.origin_y.value, b.width.value, b.depth.value)
        if any(v is None for v in vals):
            return None
        x0, y0, w, d = (float(v) for v in vals)
        rects.append(Rect(b.block_id, x0, y0, x0 + w, y0 + d))
    return rects


def _check_footprint(twin: BuildingTwin) -> None:
    rects = _rects(twin)
    if rects is None:
        return
    try:
        validate_rects(rects)
    except GeometryError as exc:
        raise ValueError(f"invalid footprint: {exc}") from exc


# =============================================================================
# Hidden-side rules
# =============================================================================
def _main_block(twin: BuildingTwin) -> Optional[Block]:
    for b in twin.blocks:
        if b.role == BlockRole.MAIN:
            return b
    return twin.blocks[0] if twin.blocks else None


def _offset_from_left_end(rect: Rect, side: Side, a: float, b: float) -> float:
    """Offset (from the wall's left end seen from outside) of the piece start [a, b]."""
    if side == Side.FRONT:
        return a - rect.x0
    if side == Side.REAR:
        return rect.x1 - b
    if side == Side.LEFT:
        return rect.y1 - b
    return a - rect.y0


def _pieces_in_wall_order(pcs: Iterable[Piece], rect: Rect) -> list[Piece]:
    return sorted(pcs, key=lambda p: _offset_from_left_end(rect, p.side, p.a, p.b))


def _row_capacity(length: float, item_w: float, fixed_widths: Sequence[float]) -> int:
    """How many items of width ``item_w`` fit beside ``fixed_widths`` with clear margins."""
    used = sum(fixed_widths) + (len(fixed_widths) + 1) * EDGE_MARGIN_M
    free = length - used
    if free < item_w:
        return 0
    return int(math.floor((free + 1e-9) / (item_w + EDGE_MARGIN_M)))


def _allocate(n: int, weights: list[float], caps: list[int]) -> list[int]:
    """Largest-remainder allocation of ``n`` items by weight, respecting capacities."""
    k = len(weights)
    alloc = [0] * k
    total_cap = sum(caps)
    n = min(n, total_cap)
    while n > 0:
        open_idx = [i for i in range(k) if alloc[i] < caps[i]]
        wsum = sum(weights[i] for i in open_idx) or float(len(open_idx))
        shares = {i: n * (weights[i] / wsum if wsum else 1.0 / len(open_idx)) for i in open_idx}
        placed = 0
        for i in open_idx:
            add = min(int(math.floor(shares[i] + 1e-9)), caps[i] - alloc[i])
            alloc[i] += add
            placed += add
        n -= placed
        if n <= 0:
            break
        rema = sorted(open_idx, key=lambda i: (-(shares[i] - math.floor(shares[i] + 1e-9)), -weights[i], i))
        for i in rema:
            if n <= 0:
                break
            if alloc[i] < caps[i]:
                alloc[i] += 1
                n -= 1
        if placed == 0 and all(alloc[i] >= caps[i] for i in open_idx):
            break
    return alloc


def _rule_tv(v: float, note: str) -> TrackedValue:
    return assumed(round(v, 4), "m", source=HIDDEN_RULE_SOURCE, note=note)


def regenerate_hidden_openings(twin: BuildingTwin) -> BuildingTwin:
    """Re-create rule-based openings on hidden facades (returns a new twin; version unchanged)."""
    new = twin.model_copy(deep=True)
    kept = [o for o in new.openings if not o.hidden_side_rule]
    new.openings = kept
    rects = _rects(new)
    if rects is None or not new.blocks:
        return new
    try:
        pieces = side_pieces(rects)
    except GeometryError:
        return new
    rect_by = {r.rid: r for r in rects}
    hidden = new.hidden
    # sides with observed / person-specified openings, as plain (block_id, side value) strings
    specified = {(o.block_id, o.side.value) for o in kept}
    specified |= {tuple(k.rsplit(":", 1)) for k in hidden.specified_sides if ":" in k}
    main = _main_block(new)

    def rule_filled(b: Block, side: Side) -> bool:
        return side not in b.visible_sides and (b.block_id, side.value) not in specified

    def ext_pieces(b: Block, side: Side) -> list[Piece]:
        return [p for p in pieces if p.rid == b.block_id and p.side == side and p.external and p.length > TOL]

    # --- which block hosts the rear patio doors
    n_doors = max(0, int(hidden.rear_door_count))
    dw, dh = PATIO_DOOR_SIZE
    door_host: Optional[Block] = None
    main_rear_open = n_doors and main is not None and main.heated and rule_filled(main, Side.REAR)
    if main_rear_open and any(_row_capacity(p.length, dw, []) >= 1 for p in ext_pieces(main, Side.REAR)):
        door_host = main
    elif main_rear_open:  # main rear fully covered: use a heated block attached behind it
        mr = rect_by[main.block_id]
        for b in new.blocks:
            r = rect_by[b.block_id]
            behind = abs(r.y0 - mr.y1) < 1e-6 and min(r.x1, mr.x1) - max(r.x0, mr.x0) > TOL
            if b is not main and b.heated and behind and rule_filled(b, Side.REAR) and \
                    any(_row_capacity(p.length, dw, []) >= 1 for p in ext_pieces(b, Side.REAR)):
                door_host = b
                break

    generated: list[Opening] = []
    for b in new.blocks:
        if not b.heated:
            continue
        r = rect_by[b.block_id]
        n_st = int(round(b.storeys.value or 1))
        ftf = float(b.floor_to_floor.value or 2.7)
        h_wall = n_st * ftf
        for side in (Side.FRONT, Side.RIGHT, Side.REAR, Side.LEFT):
            if not rule_filled(b, side):
                continue
            ext = _pieces_in_wall_order(ext_pieces(b, side), r)
            if not ext:
                continue
            area = sum(p.length for p in ext) * h_wall
            front_back = side in (Side.FRONT, Side.REAR)
            ratio_tv = hidden.rear_glazing_ratio if front_back else hidden.side_glazing_ratio
            ratio = min(max(float(ratio_tv.value or 0.0), 0.0), MAX_RATIO)
            ratio_name = "rear_glazing_ratio" if front_back else "side_glazing_ratio"
            target = ratio * area
            # rows = (piece, storey); doors on the ground-floor row of the longest piece(s)
            rows = [(p, s) for s in range(n_st) for p in ext]
            fixed: dict[int, list[float]] = {i: [] for i in range(len(rows))}
            doors_here = n_doors if (door_host is b and side == Side.REAR) else 0
            door_rows: dict[int, int] = {}
            if doors_here:
                gf = sorted((i for i, (p, s) in enumerate(rows) if s == 0), key=lambda i: (-rows[i][0].length, i))
                left = doors_here
                for i in gf:
                    while left and _row_capacity(rows[i][0].length, dw, fixed[i]) >= 1:
                        fixed[i].append(dw)
                        door_rows[i] = door_rows.get(i, 0) + 1
                        left -= 1
                doors_here -= left
            door_h = min(dh, max(0.5, ftf - 0.15))
            glazed_doors = doors_here * dw * door_h
            ww = float(hidden.typical_window_width_m)
            wh = float(hidden.typical_window_height_m)
            sill = float(hidden.typical_window_sill_m)
            if sill + wh > ftf - 0.1:
                wh = max(0.3, ftf - 0.1 - sill)
            n_win = max(0, int(round((target - glazed_doors) / (ww * wh)))) if ww * wh > 0 else 0
            caps = [_row_capacity(p.length, ww, fixed[i]) for i, (p, s) in enumerate(rows)]
            weights = [max(p.length - sum(fixed[i]), 0.0) for i, (p, s) in enumerate(rows)]
            alloc = _allocate(n_win, weights, caps)
            k = 0
            for i, (p, s) in enumerate(rows):
                items: list[tuple[str, float]] = [("window", ww)] * alloc[i]
                nd = door_rows.get(i, 0)
                if nd:
                    half = len(items) // 2
                    items = items[:half] + [("door", dw)] * nd + items[half:]
                if not items:
                    continue
                gap = (p.length - sum(w for _, w in items)) / (len(items) + 1)
                pos = _offset_from_left_end(r, side, p.a, p.b) + gap
                for kind, w in items:
                    k += 1
                    oid = f"hid:{b.block_id[:56]}:{side.value}:{k:02d}"
                    if kind == "door":
                        rule = f"rear_door_count={n_doors}"
                        generated.append(Opening(
                            opening_id=oid, block_id=b.block_id, side=side, kind=OpeningKind.PATIO_DOOR, storey=0,
                            offset_m=_rule_tv(pos, "Rear patio door placed by rule."),
                            width_m=_rule_tv(w, "Typical patio door width (assumed)."),
                            height_m=_rule_tv(door_h, "Typical patio door height (assumed)."),
                            sill_m=_rule_tv(0.0, "Door at floor level."), hidden_side_rule=rule))
                    else:
                        rule = f"{ratio_name}={ratio:.2f}"
                        generated.append(Opening(
                            opening_id=oid, block_id=b.block_id, side=side, kind=OpeningKind.WINDOW, storey=s,
                            offset_m=_rule_tv(pos, f"Spread evenly so glazing ~ {ratio:.0%} of the hidden wall."),
                            width_m=_rule_tv(w, "Typical window width (assumed)."),
                            height_m=_rule_tv(wh, "Typical window height (assumed)."),
                            sill_m=_rule_tv(sill, "Typical sill height (assumed)."), hidden_side_rule=rule))
                    pos += w + gap
    new.openings = kept + generated
    return new


# =============================================================================
# Edits
# =============================================================================
def _num(value: Any, what: str, unit: Optional[str] = "m") -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{what}: a number is required")
    if isinstance(value, (int, float)):
        v = float(value)
    elif isinstance(value, str):
        text = value.strip()[:40]
        try:
            v = float(text)
        except ValueError:
            try:
                q, u = parse_quantity(text)
                v = convert(q, u, unit) if unit else q
            except (UnitError, ValueError):
                raise ValueError(f"{what}: cannot interpret {text!r} as a number") from None
    else:
        raise ValueError(f"{what}: a number is required")
    if not math.isfinite(v):
        raise ValueError(f"{what}: value must be finite")
    return v


def _int(value: Any, what: str, lo: int, hi: int) -> int:
    v = _num(value, what, unit=None)
    if abs(v - round(v)) > 1e-9:
        raise ValueError(f"{what}: an integer is required, got {v}")
    n = int(round(v))
    if not lo <= n <= hi:
        raise ValueError(f"{what}: must be between {lo} and {hi}, got {n}")
    return n


def _bool(value: Any, what: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("true", "false", "yes", "no", "1", "0"):
        return value.strip().lower() in ("true", "yes", "1")
    raise ValueError(f"{what}: true/false required")


def _text(value: Any, what: str, limit: int = 120) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{what}: text required")
    t = _CTRL.sub(" ", value).strip()
    if not t or len(t) > limit:
        raise ValueError(f"{what}: text must be 1-{limit} characters")
    return t


def _ident(value: Any, what: str) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ValueError(f"{what}: invalid id {value!r}")
    return value


def _tol(edit: TwinEdit) -> Optional[float]:
    if edit.tolerance is None:
        return None
    t = _num(edit.tolerance, "tolerance")
    if t < 0:
        raise ValueError("tolerance must be >= 0")
    return t


def _check_range(v: float, what: str, lo: Optional[float] = None, hi: Optional[float] = None, *,
                 lo_open: bool = False, hi_open: bool = False) -> None:
    if lo is not None and (v < lo or (lo_open and v <= lo)):
        raise ValueError(f"{what}: must be {'>' if lo_open else '>='} {lo}, got {v}")
    if hi is not None and (v > hi or (hi_open and v >= hi)):
        raise ValueError(f"{what}: must be {'<' if hi_open else '<='} {hi}, got {v}")


def _edit_tv(tv: Optional[TrackedValue], v: float, edit: TwinEdit, target: str, unit: str) -> TrackedValue:
    base = tv if tv is not None else TrackedValue(value=None, unit=unit, basis=Basis.UNKNOWN)
    return base.edited(v, actor=edit.actor[:80], target=target, field=edit.field, reason=edit.reason[:500],
                       tolerance=_tol(edit))


def _shift_tv(tv: TrackedValue, delta: float, target: str, field: str, reason: str) -> TrackedValue:
    rec = EditRecord(actor="system:reflow", target=target, field=field, old_value=tv.value,
                     new_value=tv.value + delta, old_basis=tv.basis, new_basis=tv.basis, reason=reason)
    return tv.model_copy(update={
        "value": tv.value + delta,
        "low": None if tv.low is None else tv.low + delta,
        "high": None if tv.high is None else tv.high + delta,
        "history": [*tv.history, rec],
    }, deep=True)


def _touching(a: Rect, b: Rect) -> bool:
    """Rectangles share an edge segment of positive length."""
    ox = min(a.x1, b.x1) - max(a.x0, b.x0)
    oy = min(a.y1, b.y1) - max(a.y0, b.y0)
    return (abs(ox) < 1e-6 and oy > TOL) or (abs(oy) < 1e-6 and ox > TOL)


def _reflow(twin: BuildingTwin, block_id: str, field: str, old_edge: float, delta: float) -> list[str]:
    """Move blocks attached beyond the old right (width) / rear (depth) edge of ``block_id``."""
    if abs(delta) <= 1e-12:
        return []
    rects = _rects(twin)
    if rects is None:
        return []
    by = {r.rid: r for r in rects}
    # geometry of the edited block *before* the change
    r0 = by[block_id]
    if field == "width":
        r0 = Rect(r0.rid, r0.x0, r0.y0, old_edge, r0.y1)
        beyond = lambda r: r.x0 >= old_edge - 1e-6  # noqa: E731
    else:
        r0 = Rect(r0.rid, r0.x0, r0.y0, r0.x1, old_edge)
        beyond = lambda r: r.y0 >= old_edge - 1e-6  # noqa: E731
    by[block_id] = r0
    moved: list[str] = []
    seen = {block_id}
    queue = deque([block_id])
    while queue:
        cur = by[queue.popleft()]
        for r in rects:
            if r.rid in seen or not beyond(by[r.rid]):
                continue
            if _touching(cur, by[r.rid]):
                seen.add(r.rid)
                moved.append(r.rid)
                queue.append(r.rid)
    axis = "origin_x" if field == "width" else "origin_y"
    for b in twin.blocks:
        if b.block_id in moved:
            setattr(b, axis, _shift_tv(getattr(b, axis), delta, f"block:{b.block_id}", axis,
                                       f"Kept attached to '{block_id}' after its {field} changed."))
    return moved


def _wall_length(b: Block, side: Side) -> Optional[float]:
    v = b.width.value if side in (Side.FRONT, Side.REAR) else b.depth.value
    return None if v is None else float(v)


def _check_fit(twin: BuildingTwin, o: Opening) -> None:
    b = twin.block(o.block_id)
    L = _wall_length(b, o.side)
    if L is None or o.offset_m.value is None or o.width_m.value is None:
        return
    if o.offset_m.value + o.width_m.value > L + 1e-3:
        raise ValueError(f"opening {o.opening_id} ({o.offset_m.value:.2f} + {o.width_m.value:.2f} m) does not fit "
                         f"on the {o.side.value} wall of {o.block_id} ({L:.2f} m)")
    n = int(round(b.storeys.value or 1))
    if o.storey >= n:
        raise ValueError(f"opening {o.opening_id}: storey {o.storey} does not exist on {o.block_id} ({n} storeys)")


def _freeze_side(twin: BuildingTwin, block_id: str, side: Side, by: str) -> None:
    """Mark a hidden side as person-specified and keep its current rule openings as ordinary
    assumed openings (rule tag cleared), so it is no longer regenerated."""
    key = f"{block_id}:{side.value}"
    if key not in twin.hidden.specified_sides:
        twin.hidden.specified_sides.append(key)
    for o in twin.openings:
        if o.block_id == block_id and o.side == side and o.hidden_side_rule:
            note = f" Frozen from '{o.hidden_side_rule}' when {by} specified this side."
            for name in ("offset_m", "width_m", "height_m", "sill_m"):
                tv = getattr(o, name)
                setattr(o, name, tv.model_copy(update={"source": f"{HIDDEN_RULE_SOURCE} (frozen)",
                                                       "note": (tv.note + note).strip()}))
            o.hidden_side_rule = None


def _side_rule_filled(twin: BuildingTwin, block_id: str, side: Side) -> bool:
    """True for a hidden side (not seen in any view): edits there freeze the rule fill."""
    b = twin.block(block_id)
    return side not in b.visible_sides


def _edit_block(t: BuildingTwin, e: TwinEdit) -> tuple[Any, Any, bool]:
    if not e.target_id:
        raise ValueError("block edits need target_id = block id")
    try:
        b = t.block(e.target_id)
    except KeyError:
        raise ValueError(f"unknown block '{e.target_id}'") from None
    target = f"block:{b.block_id}"
    f = e.field
    if f in ("width", "depth", "origin_x", "origin_y", "floor_to_floor", "ground_floor_level"):
        v = _num(e.value, f"{target}.{f}")
        if f in ("width", "depth"):
            _check_range(v, f, 0.0, 200.0, lo_open=True)
        elif f == "floor_to_floor":
            _check_range(v, f, 0.0, 10.0, lo_open=True)
        elif f == "ground_floor_level":
            _check_range(v, f, 0.0, 3.0)
        else:
            _check_range(v, f, -1000.0, 1000.0)
        old_tv = getattr(b, f)
        old = old_tv.value
        if f in ("width", "depth") and old is not None:
            origin = b.origin_x.value if f == "width" else b.origin_y.value
            if origin is not None:
                _reflow(t, b.block_id, f, origin + old, v - old)
        setattr(b, f, _edit_tv(old_tv, v, e, target, "m"))
        return old, v, True
    if f == "storeys":
        n = _int(e.value, f"{target}.storeys", 1, MAX_STOREYS)
        old = b.storeys.value
        b.storeys = _edit_tv(b.storeys, float(n), e, target, "storeys")
        return old, n, True
    if f == "heated":
        v = _bool(e.value, f"{target}.heated")
        old, b.heated = b.heated, v
        return old, v, True
    if f == "name":
        v = _text(e.value, f"{target}.name")
        old, b.name = b.name, v
        return old, v, False
    if f == "role":
        try:
            v = BlockRole(e.value)
        except ValueError:
            raise ValueError(f"{target}.role: unknown role {e.value!r}") from None
        old, b.role = b.role.value, v
        return old, v.value, True
    raise ValueError(f"unknown block field '{f}'")


def _edit_roof(t: BuildingTwin, e: TwinEdit) -> tuple[Any, Any, bool]:
    if not e.target_id:
        raise ValueError("roof edits need target_id = block id")
    try:
        b = t.block(e.target_id)
    except KeyError:
        raise ValueError(f"unknown block '{e.target_id}'") from None
    roof = b.roof
    target = f"roof:{b.block_id}"
    f = e.field
    if f == "form":
        try:
            v = RoofForm(e.value)
        except ValueError:
            raise ValueError(f"{target}.form: unknown roof form {e.value!r}") from None
        old = roof.form.value
        roof.form = v
        if v != RoofForm.FLAT and not (roof.pitch_deg.value and 0 < roof.pitch_deg.value < 75):
            prior = AssumptionLibrary().roof_pitch_deg
            roof.pitch_deg = prior.model_copy(update={"note": "Pitch prior assumed after the roof form changed."})
        if v == RoofForm.FLAT and roof.parapet_height_m is None:
            roof.parapet_height_m = assumed(0.0, "m", note="No parapet assumed.")
        return old, v.value, True
    if f == "pitch_deg":
        v = _num(e.value, f"{target}.pitch_deg", unit="deg")
        if roof.form == RoofForm.FLAT:
            _check_range(v, "pitch_deg", 0.0, 75.0, hi_open=True)
        else:
            _check_range(v, "pitch_deg (pitched roof)", 0.0, 75.0, lo_open=True, hi_open=True)
        old = roof.pitch_deg.value
        roof.pitch_deg = _edit_tv(roof.pitch_deg, v, e, target, "deg")
        return old, v, True
    if f in ("eaves_overhang_m", "verge_overhang_m", "parapet_height_m"):
        v = _num(e.value, f"{target}.{f}")
        _check_range(v, f, 0.0, 2.0 if f != "parapet_height_m" else 3.0)
        old_tv = getattr(roof, f)
        old = old_tv.value if old_tv is not None else None
        setattr(roof, f, _edit_tv(old_tv, v, e, target, "m"))
        return old, v, True
    if f == "ridge_axis":
        if e.value not in ("x", "y"):
            raise ValueError(f"{target}.ridge_axis must be 'x' or 'y'")
        old, roof.ridge_axis = roof.ridge_axis, e.value
        return old, e.value, True
    if f == "high_side":
        try:
            v = None if e.value is None else Side(e.value)
        except ValueError:
            raise ValueError(f"{target}.high_side: unknown side {e.value!r}") from None
        old = roof.high_side.value if roof.high_side else None
        roof.high_side = v
        return old, v.value if v else None, True
    raise ValueError(f"unknown roof field '{f}'")


_ADD_KEYS = {"block_id", "side", "kind", "storey", "offset_m", "width_m", "height_m", "sill_m", "opening_id",
             "assembly_id"}


def _add_opening(t: BuildingTwin, e: TwinEdit) -> tuple[Any, Any, bool]:
    spec = e.value
    if not isinstance(spec, dict):
        raise ValueError("opening add: value must be a dict")
    extra = set(spec) - _ADD_KEYS
    if extra:
        raise ValueError(f"opening add: unknown keys {sorted(extra)}")
    for k in ("block_id", "side", "kind", "width_m", "height_m"):
        if k not in spec:
            raise ValueError(f"opening add: '{k}' is required")
    try:
        b = t.block(str(spec["block_id"]))
    except KeyError:
        raise ValueError(f"opening add: unknown block {spec['block_id']!r}") from None
    try:
        side, kind = Side(spec["side"]), OpeningKind(spec["kind"])
    except ValueError as exc:
        raise ValueError(f"opening add: {exc}") from None
    n_st = int(round(b.storeys.value or 1))
    storey = _int(spec.get("storey", 0), "opening add: storey", 0, max(0, n_st - 1))
    w = _num(spec["width_m"], "opening add: width_m")
    h = _num(spec["height_m"], "opening add: height_m")
    _check_range(w, "width_m", 0.0, 20.0, lo_open=True)
    _check_range(h, "height_m", 0.0, 20.0, lo_open=True)
    L = _wall_length(b, side) or 0.0
    off = _num(spec["offset_m"], "opening add: offset_m") if "offset_m" in spec else max(0.0, 0.5 * (L - w))
    _check_range(off, "offset_m", 0.0, 200.0)
    default_sill = 0.0 if kind in (OpeningKind.DOOR, OpeningKind.PATIO_DOOR, OpeningKind.GARAGE_DOOR,
                                   OpeningKind.BALCONY_DOOR) else float(t.hidden.typical_window_sill_m)
    sill = _num(spec["sill_m"], "opening add: sill_m") if "sill_m" in spec else default_sill
    _check_range(sill, "sill_m", 0.0, 20.0)
    used = {o.opening_id for o in t.openings}
    if spec.get("opening_id") is not None:
        oid = _ident(spec["opening_id"], "opening add: opening_id")
        if oid in used:
            raise ValueError(f"opening add: id '{oid}' already exists")
    else:
        n = 1
        while f"user:{b.block_id[:60]}:{n}" in used:
            n += 1
        oid = f"user:{b.block_id[:60]}:{n}"
    asm = spec.get("assembly_id")
    if asm is not None:
        asm = _ident(asm, "opening add: assembly_id")
    tol = _tol(e)
    src = f"user edit ({e.actor[:40]})"
    op = Opening(opening_id=oid, block_id=b.block_id, side=side, kind=kind, storey=storey,
                 offset_m=confirmed(off, "m", tolerance=tol, source=src),
                 width_m=confirmed(w, "m", tolerance=tol, source=src),
                 height_m=confirmed(h, "m", tolerance=tol, source=src),
                 sill_m=confirmed(sill, "m", tolerance=tol, source=src), assembly_id=asm)
    _check_fit(t, op)
    if _side_rule_filled(t, b.block_id, side):
        _freeze_side(t, b.block_id, side, f"adding {oid}")
    t.openings.append(op)
    return None, {"opening_id": oid, "block_id": b.block_id, "side": side.value, "kind": kind.value,
                  "storey": storey, "offset_m": off, "width_m": w, "height_m": h, "sill_m": sill}, True


def _edit_opening(t: BuildingTwin, e: TwinEdit) -> tuple[Any, Any, bool]:
    if e.field == "add":
        if e.target_id is not None:
            raise ValueError("opening add: target_id must be None")
        return _add_opening(t, e)
    if not e.target_id:
        raise ValueError("opening edits need target_id = opening id")
    idx = next((i for i, o in enumerate(t.openings) if o.opening_id == e.target_id), None)
    if idx is None:
        raise ValueError(f"unknown opening '{e.target_id}'")
    o = t.openings[idx]
    target = f"opening:{o.opening_id}"
    if o.hidden_side_rule or _side_rule_filled(t, o.block_id, o.side):
        _freeze_side(t, o.block_id, o.side, f"editing {o.opening_id}")
    f = e.field
    if f == "delete":
        removed = t.openings.pop(idx)
        return {"opening_id": removed.opening_id, "kind": removed.kind.value, "side": removed.side.value}, None, True
    if f in ("width_m", "height_m", "sill_m", "offset_m"):
        v = _num(e.value, f"{target}.{f}")
        if f in ("width_m", "height_m"):
            _check_range(v, f, 0.0, 20.0, lo_open=True)
        else:
            _check_range(v, f, 0.0, 200.0)
        old_tv = getattr(o, f)
        old = old_tv.value
        setattr(o, f, _edit_tv(old_tv, v, e, target, "m"))
        _check_fit(t, o)
        return old, v, True
    if f == "kind":
        try:
            v = OpeningKind(e.value)
        except ValueError:
            raise ValueError(f"{target}.kind: unknown kind {e.value!r}") from None
        old, o.kind = o.kind.value, v
        return old, v.value, True
    if f == "storey":
        b = t.block(o.block_id)
        n = _int(e.value, f"{target}.storey", 0, max(0, int(round(b.storeys.value or 1)) - 1))
        old, o.storey = o.storey, n
        return old, n, True
    if f == "side":
        try:
            v = Side(e.value)
        except ValueError:
            raise ValueError(f"{target}.side: unknown side {e.value!r}") from None
        old = o.side.value
        if _side_rule_filled(t, o.block_id, v):
            _freeze_side(t, o.block_id, v, f"moving {o.opening_id}")
        o.side = v
        _check_fit(t, o)
        return old, v.value, True
    if f == "assembly_id":
        v = None if e.value is None else _ident(e.value, f"{target}.assembly_id")
        old, o.assembly_id = o.assembly_id, v
        return old, v, False
    raise ValueError(f"unknown opening field '{f}'")


def _edit_hidden(t: BuildingTwin, e: TwinEdit) -> tuple[Any, Any, bool]:
    h = t.hidden
    f = e.field
    if f in ("rear_glazing_ratio", "side_glazing_ratio"):
        v = _num(e.value, f"hidden.{f}", unit=None)
        _check_range(v, f, 0.0, MAX_RATIO)
        old = getattr(h, f).value
        setattr(h, f, _edit_tv(getattr(h, f), v, e, "hidden", "fraction"))
        return old, v, True
    if f == "rear_door_count":
        n = _int(e.value, "hidden.rear_door_count", 0, 10)
        old, h.rear_door_count = h.rear_door_count, n
        return old, n, True
    if f in ("typical_window_width_m", "typical_window_height_m", "typical_window_sill_m"):
        v = _num(e.value, f"hidden.{f}")
        if f == "typical_window_sill_m":
            _check_range(v, f, 0.0, 3.0)
        else:
            _check_range(v, f, 0.0, 5.0, lo_open=True)
        old = getattr(h, f)
        setattr(h, f, v)
        return old, v, True
    raise ValueError(f"unknown hidden-side field '{f}'")


def _edit_assembly(t: BuildingTwin, e: TwinEdit) -> tuple[Any, Any, bool]:
    f = e.field
    if f not in _SELECTION_KEYS:
        raise ValueError(f"unknown assembly element '{f}'; expected one of {list(_SELECTION_KEYS)}")
    aid = _ident(e.value, f"assembly.{f}")
    sel = t.assemblies
    if e.target_id:
        try:
            t.block(e.target_id)
        except KeyError:
            raise ValueError(f"unknown block '{e.target_id}'") from None
        if f == "foundation":
            raise ValueError("the foundation option is selected per twin, not per block")
        old = sel.block_overrides.get(e.target_id, {}).get(f)
        sel.block_overrides.setdefault(e.target_id, {})[f] = aid
        sel.basis[f"{e.target_id}/{f}"] = Basis.USER_CONFIRMED
    else:
        old = getattr(sel, f)
        setattr(sel, f, aid)
        sel.basis[f] = Basis.USER_CONFIRMED
    return old, aid, False


def _edit_twin(t: BuildingTwin, e: TwinEdit) -> tuple[Any, Any, bool]:
    f = e.field
    if f == "name":
        v = _text(e.value, "twin.name", 200)
        old, t.name = t.name, v
        return old, v, False
    if f == "bathrooms":
        n = _int(e.value, "twin.bathrooms", 0, 20)
        old = t.bathrooms.value
        t.bathrooms = _edit_tv(t.bathrooms, float(n), e, "twin", "nr")
        return old, n, False
    if f == "dwellings":
        n = _int(e.value, "twin.dwellings", 1, 50)
        old, t.dwellings = t.dwellings, n
        return old, n, False
    raise ValueError(f"unknown twin field '{f}'")


_HANDLERS: dict[str, Callable[[BuildingTwin, TwinEdit], tuple[Any, Any, bool]]] = {
    "block": _edit_block, "roof": _edit_roof, "opening": _edit_opening, "hidden": _edit_hidden,
    "assembly": _edit_assembly, "twin": _edit_twin,
}


def _old_basis(twin: BuildingTwin, e: TwinEdit) -> Optional[Basis]:
    try:
        if e.target_type == "block" and e.target_id:
            tv = getattr(twin.block(e.target_id), e.field, None)
        elif e.target_type == "roof" and e.target_id:
            tv = getattr(twin.block(e.target_id).roof, e.field, None)
        elif e.target_type == "opening" and e.target_id:
            o = next((o for o in twin.openings if o.opening_id == e.target_id), None)
            tv = getattr(o, e.field, None) if o is not None else None
        elif e.target_type == "hidden":
            tv = getattr(twin.hidden, e.field, None)
        elif e.target_type == "assembly":
            key = f"{e.target_id}/{e.field}" if e.target_id else e.field
            return twin.assemblies.basis.get(key, Basis.ASSUMED)
        elif e.target_type == "twin":
            tv = getattr(twin, e.field, None)
        else:
            tv = None
    except (KeyError, AttributeError):
        return None
    return tv.basis if isinstance(tv, TrackedValue) else None


def _jsonable(v: Any) -> Any:
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return str(v)[:200]


def apply_twin_edit(twin: BuildingTwin, edit: TwinEdit) -> BuildingTwin:
    """Apply one validated user edit and return a new twin (see module docstring).

    Raises ``ValueError`` for unknown targets/fields, invalid values, or an edit
    that would make blocks overlap.
    """
    new = twin.model_copy(deep=True)
    handler = _HANDLERS.get(edit.target_type)
    if handler is None:
        raise ValueError(f"unknown edit target type '{edit.target_type}'")
    old_basis = _old_basis(twin, edit)
    old, value, regen = handler(new, edit)
    _check_footprint(new)
    if regen:
        new = regenerate_hidden_openings(new)
    target = f"{edit.target_type}:{edit.target_id}" if edit.target_id else edit.target_type
    new.edit_log.append(EditRecord(actor=edit.actor[:80], target=target, field=edit.field,
                                   old_value=_jsonable(old), new_value=_jsonable(value), old_basis=old_basis,
                                   new_basis=Basis.USER_CONFIRMED, reason=edit.reason[:500]))
    new.version = twin.version + 1
    return new


# =============================================================================
# Hash
# =============================================================================
def _strip_history(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_history(v) for k, v in obj.items() if k != "history"}
    if isinstance(obj, list):
        return [_strip_history(v) for v in obj]
    return obj


def twin_hash(twin: BuildingTwin) -> str:
    """SHA-256 of the canonical JSON of the twin, excluding ``edit_log`` and value histories."""
    data = _strip_history(twin.model_dump(mode="json", exclude={"edit_log"}))
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = [
    "DEFAULT_FINISH_HEX",
    "HIDDEN_RULE_SOURCE",
    "PATIO_DOOR_SIZE",
    "apply_twin_edit",
    "build_parametric_twin",
    "colour_from_appearance",
    "regenerate_hidden_openings",
    "twin_hash",
    "visual_finishes_from_analysis",
]
