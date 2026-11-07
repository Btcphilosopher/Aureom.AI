"""Analytic geometry metrics for a parametric twin.

All results are closed-form functions of the block parameters (no meshing),
so they can be verified against hand calculations and evaluated quickly
inside the Monte Carlo simulator.

Conventions (also returned in ``GeometryMetrics.conventions``):

* Block width/depth are *external* dimensions (to the external wall face).
* GEA = sum of block footprints on each storey.  GIA = GEA minus wall strips:
  external walls at the external-wall assembly thickness, walls shared between
  blocks at the separating-wall thickness (each block loses half).
* External wall area is measured from finished ground-floor level to the wall
  plate, plus gable / monopitch / parapet infill above the plate.  Walls shared
  between blocks are measured once as separating walls up to the lower wall
  plate; the portion of a taller block above its neighbour is external.
* Openings are deducted once, from the wall piece that contains them.  An
  opening that falls on a separating wall is not deducted and is flagged.
* Roof surface area = roof plan area (incl. overhangs on exposed edges) /
  cos(pitch).  This is exact for roofs of uniform pitch (gable, hip,
  monopitch), including hips and valleys.  Overhang plan areas at re-entrant
  corners of roofs at the same level are allocated to one block only.  Edges of
  a taller block above a lower neighbour are roof-exposed: its eaves/verge
  overhang projects over the lower roof and is counted for the taller block.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

from ..core.models import (
    BlockMetrics,
    BuildingTwin,
    GeometryMetrics,
    GLAZED_OPENINGS,
    OpeningKind,
    RoofForm,
    RoofMetrics,
    Side,
    StoreyMetrics,
    WallPiece,
)
from .footprint import (
    TOL,
    GeometryError,
    Piece,
    Rect,
    allocate_plan_areas,
    internal_area,
    overhang_regions,
    side_pieces,
    validate_rects,
)

CONVENTIONS = {
    "dimensions": "Block width/depth are external dimensions (outside face of external walls).",
    "GEA": "Gross external area: sum of block footprints on each storey (to external wall face).",
    "GIA": "Gross internal area: GEA minus external wall strips (external wall assembly thickness) "
           "and separating walls between blocks (half thickness each side). Internal partitions are included in GIA.",
    "external_wall_area": "Measured from finished ground-floor level to wall plate, plus gable/monopitch/parapet "
                          "infill above plate. Masonry below FFL is substructure.",
    "openings": "Each opening deducted once from the wall piece containing it; openings on separating walls are not deducted.",
    "separating_walls": "Walls between blocks are counted once, up to the lower wall plate; roof-void portions are not measured.",
    "roof_area": "Sloped area = plan area incl. overhangs on roof-exposed edges / cos(pitch); exact for uniform-pitch roofs. "
                 "Valleys at block junctions are not measured as separate linear items.",
    "floors": "Ground-floor and upper-floor areas are internal (GIA) areas per storey.",
}


@dataclass
class BlockParams:
    block_id: str
    x0: float
    y0: float
    width: float
    depth: float
    storeys: int
    floor_to_floor: float
    ffl: float
    roof_form: RoofForm
    pitch_deg: float
    ridge_axis: str
    eaves_overhang: float
    verge_overhang: float
    high_side: Optional[Side] = None
    parapet: float = 0.0
    heated: bool = True

    @property
    def plate(self) -> float:
        return self.ffl + self.storeys * self.floor_to_floor

    @property
    def rect(self) -> Rect:
        return Rect(self.block_id, self.x0, self.y0, self.x0 + self.width, self.y0 + self.depth)


@dataclass
class OpeningParams:
    opening_id: str
    block_id: str
    side: Side
    kind: OpeningKind
    storey: int
    offset: float
    width: float
    height: float
    sill: float


def _req(tv, what: str) -> float:
    if tv is None or tv.value is None:
        raise GeometryError(f"{what} is unknown; supply a value or an explicit assumption")
    return float(tv.value)


def params_from_twin(twin: BuildingTwin) -> tuple[list[BlockParams], list[OpeningParams]]:
    blocks: list[BlockParams] = []
    for b in twin.blocks:
        r = b.roof
        blocks.append(BlockParams(
            block_id=b.block_id,
            x0=_req(b.origin_x, f"{b.block_id}.origin_x"),
            y0=_req(b.origin_y, f"{b.block_id}.origin_y"),
            width=_req(b.width, f"{b.block_id}.width"),
            depth=_req(b.depth, f"{b.block_id}.depth"),
            storeys=int(round(_req(b.storeys, f"{b.block_id}.storeys"))),
            floor_to_floor=_req(b.floor_to_floor, f"{b.block_id}.floor_to_floor"),
            ffl=_req(b.ground_floor_level, f"{b.block_id}.ground_floor_level"),
            roof_form=r.form,
            pitch_deg=0.0 if r.form == RoofForm.FLAT else _req(r.pitch_deg, f"{b.block_id}.roof.pitch"),
            ridge_axis=r.ridge_axis,
            eaves_overhang=_req(r.eaves_overhang_m, f"{b.block_id}.roof.eaves_overhang"),
            verge_overhang=_req(r.verge_overhang_m, f"{b.block_id}.roof.verge_overhang"),
            high_side=r.high_side,
            parapet=float(r.parapet_height_m.value) if (r.parapet_height_m and r.parapet_height_m.value) else 0.0,
            heated=b.heated,
        ))
    openings: list[OpeningParams] = []
    for o in twin.openings:
        openings.append(OpeningParams(
            opening_id=o.opening_id, block_id=o.block_id, side=o.side, kind=o.kind, storey=o.storey,
            offset=_req(o.offset_m, f"{o.opening_id}.offset"), width=_req(o.width_m, f"{o.opening_id}.width"),
            height=_req(o.height_m, f"{o.opening_id}.height"), sill=_req(o.sill_m, f"{o.opening_id}.sill"),
        ))
    return blocks, openings


# --------------------------------------------------------------------- roofs
def roof_shape(bp: BlockParams) -> tuple[float, float, float, dict[Side, float]]:
    """Return (span, length_along_ridge, rise, overhang_by_side) for a block roof."""
    w, d = bp.width, bp.depth
    t = math.tan(math.radians(bp.pitch_deg)) if bp.roof_form != RoofForm.FLAT else 0.0
    eo, vo = bp.eaves_overhang, bp.verge_overhang
    if bp.roof_form == RoofForm.GABLE:
        if bp.ridge_axis == "x":
            span, length = d, w
            ov = {Side.FRONT: eo, Side.REAR: eo, Side.LEFT: vo, Side.RIGHT: vo}
        else:
            span, length = w, d
            ov = {Side.LEFT: eo, Side.RIGHT: eo, Side.FRONT: vo, Side.REAR: vo}
        return span, length, 0.5 * span * t, ov
    if bp.roof_form == RoofForm.HIP:
        span, length = min(w, d), max(w, d)
        return span, length, 0.5 * span * t, {s: eo for s in Side}
    if bp.roof_form == RoofForm.MONOPITCH:
        high = bp.high_side or Side.FRONT
        span, length = (d, w) if high in (Side.FRONT, Side.REAR) else (w, d)
        low = {Side.FRONT: Side.REAR, Side.REAR: Side.FRONT, Side.LEFT: Side.RIGHT, Side.RIGHT: Side.LEFT}[high]
        ov = {s: vo for s in Side}
        ov[low] = eo
        return span, length, span * t, ov
    # flat
    o = 0.0 if bp.parapet > TOL else eo
    return min(w, d), max(w, d), 0.0, {s: o for s in Side}


def infill_height(bp: BlockParams, side: Side, u: float) -> float:
    """Height of wall infill above the wall plate at coordinate ``u`` along ``side``."""
    span, _, rise, _ = roof_shape(bp)
    r = bp.rect
    if bp.roof_form == RoofForm.GABLE:
        gable_sides = (Side.LEFT, Side.RIGHT) if bp.ridge_axis == "x" else (Side.FRONT, Side.REAR)
        if side not in gable_sides:
            return 0.0
        mid = 0.5 * (r.y0 + r.y1) if bp.ridge_axis == "x" else 0.5 * (r.x0 + r.x1)
        return max(0.0, rise * (1.0 - abs(u - mid) / (0.5 * span)))
    if bp.roof_form == RoofForm.MONOPITCH:
        high = bp.high_side or Side.FRONT
        if side == high:
            return rise
        if high == Side.FRONT and side in (Side.LEFT, Side.RIGHT):
            return rise * (r.y1 - u) / span
        if high == Side.REAR and side in (Side.LEFT, Side.RIGHT):
            return rise * (u - r.y0) / span
        if high == Side.LEFT and side in (Side.FRONT, Side.REAR):
            return rise * (r.x1 - u) / span
        if high == Side.RIGHT and side in (Side.FRONT, Side.REAR):
            return rise * (u - r.x0) / span
        return 0.0
    if bp.roof_form == RoofForm.FLAT:
        return bp.parapet
    return 0.0


def integrate_infill(bp: BlockParams, side: Side, a: float, b: float) -> float:
    """Exact integral of the (piecewise-linear) infill height over [a, b]."""
    if b - a <= TOL:
        return 0.0
    pts = [a, b]
    r = bp.rect
    if bp.roof_form == RoofForm.GABLE:
        mid = 0.5 * (r.y0 + r.y1) if bp.ridge_axis == "x" else 0.5 * (r.x0 + r.x1)
        if a < mid < b:
            pts.insert(1, mid)
    total = 0.0
    for u0, u1 in zip(pts[:-1], pts[1:]):
        total += 0.5 * (infill_height(bp, side, u0) + infill_height(bp, side, u1)) * (u1 - u0)
    return total


def _hip_length(span: float, overhang: float, pitch_deg: float) -> float:
    half = 0.5 * span + overhang
    return math.sqrt(2.0 * half * half + (half * math.tan(math.radians(pitch_deg))) ** 2)


def roof_exposed(piece: Piece, plates: dict[str, float]) -> bool:
    """A piece is exposed at roof level if it is external, or shared with a block whose
    wall plate is lower (the taller block's eaves/verge then project over the lower roof)."""
    if piece.external:
        return True
    return plates.get(piece.neighbour, 0.0) < plates.get(piece.rid, 0.0) - TOL


def _roof_metrics(bp: BlockParams, pieces: Sequence[Piece], plates: dict[str, float],
                  plan_area: float) -> RoofMetrics:
    span, length, rise, ov = roof_shape(bp)
    p = math.radians(bp.pitch_deg)
    cosp = math.cos(p) if bp.roof_form != RoofForm.FLAT else 1.0
    own = [pc for pc in pieces if pc.rid == bp.block_id]
    r = bp.rect

    def ext_len(side: Side) -> float:
        return sum(pc.length for pc in own if pc.side == side and roof_exposed(pc, plates))

    def ext_at(side: Side, u: float) -> bool:
        for pc in own:
            if pc.side == side and pc.a - TOL <= u <= pc.b + TOL:
                return roof_exposed(pc, plates)
        return False

    abut = 0.0
    for pc in own:
        if not pc.external and plates.get(pc.neighbour, 0.0) > bp.plate + TOL:
            abut += pc.length
    ridge = hip = eaves = verge = 0.0
    xm, ym = 0.5 * (r.x0 + r.x1), 0.5 * (r.y0 + r.y1)
    if bp.roof_form == RoofForm.GABLE:
        if bp.ridge_axis == "x":
            eaves_sides, gable_sides, mids = (Side.FRONT, Side.REAR), (Side.LEFT, Side.RIGHT), ym
        else:
            eaves_sides, gable_sides, mids = (Side.LEFT, Side.RIGHT), (Side.FRONT, Side.REAR), xm
        ridge = length + sum(bp.verge_overhang for g in gable_sides if ext_at(g, mids))
        for s in eaves_sides:
            eaves += ext_len(s)
        # eaves extend over the verge overhang at fully external corners
        eaves += sum(bp.verge_overhang for s in eaves_sides for g in gable_sides
                     if ext_at(s, _corner_u(r, s, g)) and ext_at(g, _corner_u(r, g, s)))
        for g in gable_sides:
            a0, b0 = r.side_range(g)
            for half_mid in (0.5 * (a0 + mids), 0.5 * (mids + b0)):
                if ext_at(g, half_mid):
                    verge += (0.5 * span + bp.eaves_overhang) / math.cos(p)
    elif bp.roof_form == RoofForm.HIP:
        ridge = max(0.0, length - span)
        hip = 4.0 * _hip_length(span, bp.eaves_overhang, bp.pitch_deg)
        eaves = sum(ext_len(s) for s in Side) + 8.0 * bp.eaves_overhang * _external_corner_count(r, own, plates) / 4.0
    elif bp.roof_form == RoofForm.MONOPITCH:
        high = bp.high_side or Side.FRONT
        low = {Side.FRONT: Side.REAR, Side.REAR: Side.FRONT, Side.LEFT: Side.RIGHT, Side.RIGHT: Side.LEFT}[high]
        top_ext = ext_len(high)
        ridge = top_ext  # exposed top edge (monopitch ridge)
        eaves = ext_len(low)
        for s in Side:
            if s in (high, low):
                continue
            a0, b0 = r.side_range(s)
            if ext_at(s, 0.5 * (a0 + b0)):
                verge += (span + ov[high] + ov[low]) / math.cos(p)
    else:  # flat: roof edge length
        eaves = sum(ext_len(s) for s in Side)
    plate = bp.plate
    if bp.roof_form == RoofForm.GABLE or bp.roof_form == RoofForm.MONOPITCH:
        void = 0.5 * span * rise * length
    elif bp.roof_form == RoofForm.HIP:
        void = span * rise * (3.0 * length - span) / 6.0
    else:
        void = 0.0
    return RoofMetrics(
        block_id=bp.block_id, form=bp.roof_form, pitch_deg=bp.pitch_deg, span_m=span, rise_m=rise,
        plan_area_m2=plan_area, surface_area_m2=plan_area / cosp, ridge_length_m=ridge, hip_length_m=hip,
        eaves_length_m=eaves, verge_length_m=verge, abutment_length_m=abut, wall_plate_height_m=plate,
        ridge_height_m=plate + rise, roof_void_volume_m3=void,
    )


def _corner_u(r: Rect, along: Side, of: Side) -> float:
    """Coordinate along side ``along`` at the corner it shares with side ``of``."""
    if along in (Side.LEFT, Side.RIGHT):
        return r.y0 if of == Side.FRONT else r.y1
    return r.x0 if of == Side.LEFT else r.x1


def _external_corner_count(r: Rect, own: Sequence[Piece], plates: dict[str, float]) -> int:
    from .footprint import outline_corners

    return sum(1 for v in outline_corners(r, own, lambda p: roof_exposed(p, plates)).values() if v)


# ---------------------------------------------------------------- main entry
def _opening_u(bp: BlockParams, op: OpeningParams) -> tuple[float, float]:
    """Centre coordinate along the side, and side length."""
    r = bp.rect
    c = op.offset + 0.5 * op.width
    if op.side == Side.FRONT:
        return r.x0 + c, r.width
    if op.side == Side.REAR:
        return r.x1 - c, r.width
    if op.side == Side.LEFT:
        return r.y1 - c, r.depth
    return r.y0 + c, r.depth


def compute_metrics(blocks: Sequence[BlockParams], openings: Sequence[OpeningParams],
                    external_wall_thickness: float, separating_wall_thickness: float) -> GeometryMetrics:
    """Compute all geometry metrics from plain parameters (fast path for simulation)."""
    if not blocks:
        raise GeometryError("twin has no blocks")
    warnings: list[str] = []
    rects = [b.rect for b in blocks]
    warnings += validate_rects(rects)
    by_id = {b.block_id: b for b in blocks}
    plates = {b.block_id: b.plate for b in blocks}
    ffls = {b.block_id: b.ffl for b in blocks}
    for b in blocks:
        if b.storeys < 1:
            raise GeometryError(f"block '{b.block_id}' must have at least one storey")
        if b.roof_form != RoofForm.FLAT and not (0.0 < b.pitch_deg < 75.0):
            raise GeometryError(f"block '{b.block_id}' roof pitch {b.pitch_deg:.1f} deg is outside (0, 75)")
        if b.roof_form == RoofForm.HIP and b.ridge_axis == "y" and b.width > b.depth + TOL:
            warnings.append(f"{b.block_id}: hip roof ridge follows the longer side (x).")
    pieces = side_pieces(rects)

    # ---- wall pieces (ground-level outline)
    wall_pieces: list[WallPiece] = []
    piece_index: dict[tuple[str, Side], list[int]] = {}
    for pc in pieces:
        bp = by_id[pc.rid]
        h = bp.plate - bp.ffl
        infill = integrate_infill(bp, pc.side, pc.a, pc.b)
        shared_area = 0.0
        if pc.external:
            rect_area, infill_area = pc.length * h, infill
        else:
            nb = by_id[pc.neighbour]
            rect_area = pc.length * max(0.0, bp.plate - max(nb.plate, bp.ffl))
            infill_area = infill if nb.plate < bp.plate - TOL else 0.0
            if pc.rid < pc.neighbour:
                shared_area = pc.length * max(0.0, min(bp.plate, nb.plate) - max(bp.ffl, nb.ffl))
        x0, y0, x1, y1 = pc.endpoints()
        idx = len(wall_pieces)
        wall_pieces.append(WallPiece(
            piece_id=f"{pc.rid}:{pc.side.value}:{len(piece_index.get((pc.rid, pc.side), []))}",
            block_id=pc.rid, side=pc.side, x0=x0, y0=y0, x1=x1, y1=y1, length_m=pc.length,
            exposure="external" if pc.external else "shared", neighbour_block_id=pc.neighbour,
            external_rect_area_m2=rect_area, external_infill_area_m2=infill_area, shared_area_m2=shared_area,
            external_gross_area_m2=rect_area + infill_area,
        ))
        piece_index.setdefault((pc.rid, pc.side), []).append(idx)

    # ---- openings
    win_area = door_area = garage_area = 0.0
    for op in openings:
        if op.block_id not in by_id:
            warnings.append(f"Opening {op.opening_id} references unknown block {op.block_id}; ignored.")
            continue
        bp = by_id[op.block_id]
        if op.width <= 0 or op.height <= 0:
            warnings.append(f"Opening {op.opening_id} has non-positive size; ignored.")
            continue
        u, side_len = _opening_u(bp, op)
        if op.offset < -TOL or op.offset + op.width > side_len + 1e-3:
            warnings.append(f"Opening {op.opening_id} extends beyond the {op.side.value} wall of {op.block_id}.")
        if op.storey >= bp.storeys:
            warnings.append(f"Opening {op.opening_id} is on storey {op.storey} but {op.block_id} has {bp.storeys}.")
        z0 = bp.ffl + op.storey * bp.floor_to_floor + op.sill
        z1 = z0 + op.height
        if z1 > bp.plate + infill_height(bp, op.side, u) + 1e-3:
            warnings.append(f"Opening {op.opening_id} extends above the wall/roof line.")
        target = None
        for idx in piece_index.get((op.block_id, op.side), []):
            wp = wall_pieces[idx]
            a, b = (wp.x0, wp.x1) if op.side in (Side.FRONT, Side.REAR) else (wp.y0, wp.y1)
            if min(a, b) - TOL <= u <= max(a, b) + TOL:
                target = idx
                break
        if target is None:
            warnings.append(f"Opening {op.opening_id} could not be located on a wall piece; not deducted.")
            continue
        wp = wall_pieces[target]
        if wp.exposure == "shared":
            nb = by_id[wp.neighbour_block_id]
            if z0 < nb.plate - 1e-3:
                warnings.append(f"Opening {op.opening_id} lies on a separating wall with {nb.block_id}; "
                                "treated as internal and not deducted from external wall.")
                continue
        area = op.width * op.height
        wp.opening_ids.append(op.opening_id)
        wp.opening_area_m2 += area
        wp.opening_head_length_m += op.width
        wp.opening_reveal_length_m += 2.0 * op.height
        if op.kind == OpeningKind.WINDOW:
            wp.opening_sill_length_m += op.width
        if op.kind in GLAZED_OPENINGS:
            win_area += area
        elif op.kind == OpeningKind.GARAGE_DOOR:
            garage_area += area
        else:
            door_area += area
    for wp in wall_pieces:
        if wp.opening_area_m2 > wp.external_gross_area_m2 + 1e-6:
            warnings.append(f"Openings on {wp.piece_id} exceed its external wall area; net area clamped to zero.")
        wp.external_net_area_m2 = max(0.0, wp.external_gross_area_m2 - wp.opening_area_m2)

    # ---- storeys (GEA / GIA)
    t_ext, t_sep = external_wall_thickness, separating_wall_thickness
    max_storeys = max(b.storeys for b in blocks)
    storey_metrics: list[StoreyMetrics] = []
    gia_by_block: dict[str, list[float]] = {b.block_id: [] for b in blocks}
    for k in range(max_storeys):
        present = [b for b in blocks if b.storeys > k]
        rk = [b.rect for b in present]
        pk = side_pieces(rk, _validated=True)
        gea = sum(r.area for r in rk)
        gia = 0.0
        for b, r in zip(present, rk):
            g = internal_area(r, pk, t_ext, t_sep)
            gia_by_block[b.block_id].append(g)
            gia += g
        storey_metrics.append(StoreyMetrics(
            storey=k, block_ids=[b.block_id for b in present], gea_m2=gea, gia_m2=gia,
            external_perimeter_m=sum(p.length for p in pk if p.external),
            shared_wall_length_m=0.5 * sum(p.length for p in pk if not p.external),
        ))

    # ---- roofs (plan areas partitioned exactly between blocks)
    regions, footprints = {}, {}
    for b in blocks:
        _, _, _, ov = roof_shape(b)
        regions[b.block_id] = overhang_regions(b.rect, pieces, ov, lambda p: roof_exposed(p, plates))
        r = b.rect
        footprints[b.block_id] = (r.x0, r.y0, r.x1, r.y1)
    priority = [b.block_id for b in sorted(blocks, key=lambda b: (-b.plate, b.block_id))]
    plan = allocate_plan_areas(regions, footprints, priority, plates)
    roofs = [_roof_metrics(b, pieces, plates, plan[b.block_id]) for b in blocks]

    # ---- per-block summaries
    block_metrics: list[BlockMetrics] = []
    for b in blocks:
        own = [wp for wp in wall_pieces if wp.block_id == b.block_id]
        gias = gia_by_block[b.block_id]
        block_metrics.append(BlockMetrics(
            block_id=b.block_id, width_m=b.width, depth_m=b.depth, storeys=b.storeys, ffl_m=b.ffl,
            plate_height_m=b.plate, footprint_area_m2=b.rect.area,
            external_wall_gross_m2=sum(w.external_gross_area_m2 for w in own),
            external_wall_net_m2=sum(w.external_net_area_m2 for w in own),
            opening_area_m2=sum(w.opening_area_m2 for w in own), heated=b.heated,
            gia_by_storey=gias, ceiling_area_m2=gias[-1] if gias else 0.0,
            ground_perimeter_m=sum(p.length for p in pieces if p.rid == b.block_id and p.external),
        ))

    gea = sum(s.gea_m2 for s in storey_metrics)
    gia = sum(s.gia_m2 for s in storey_metrics)
    heated_gia = sum(sum(gia_by_block[b.block_id]) for b in blocks if b.heated)
    heated_vol = sum(sum(gia_by_block[b.block_id]) * b.floor_to_floor for b in blocks if b.heated)
    pitched = [r for r in roofs if r.form != RoofForm.FLAT]
    return GeometryMetrics(
        blocks=block_metrics,
        pieces=wall_pieces,
        storeys=storey_metrics,
        roofs=roofs,
        external_wall_thickness_m=t_ext,
        separating_wall_thickness_m=t_sep,
        footprint_area_m2=storey_metrics[0].gea_m2,
        ground_perimeter_m=storey_metrics[0].external_perimeter_m,
        gea_m2=gea,
        gia_m2=gia,
        heated_gia_m2=heated_gia,
        external_wall_gross_m2=sum(w.external_gross_area_m2 for w in wall_pieces),
        external_wall_net_m2=sum(w.external_net_area_m2 for w in wall_pieces),
        separating_wall_area_m2=sum(w.shared_area_m2 for w in wall_pieces),
        window_area_m2=win_area,
        door_area_m2=door_area,
        garage_door_area_m2=garage_area,
        opening_area_m2=win_area + door_area + garage_area,
        roof_plan_area_m2=sum(r.plan_area_m2 for r in roofs),
        roof_surface_area_m2=sum(r.surface_area_m2 for r in roofs),
        pitched_roof_surface_area_m2=sum(r.surface_area_m2 for r in pitched),
        flat_roof_area_m2=sum(r.plan_area_m2 for r in roofs if r.form == RoofForm.FLAT),
        ground_floor_area_m2=storey_metrics[0].gia_m2,
        intermediate_floor_area_m2=sum(s.gia_m2 for s in storey_metrics[1:]),
        top_ceiling_area_m2=sum(bm.ceiling_area_m2 for bm in block_metrics),
        heated_volume_m3=heated_vol,
        conventions=dict(CONVENTIONS),
        warnings=warnings,
    )


def compute_geometry_metrics(twin: BuildingTwin, external_wall_thickness: float,
                             separating_wall_thickness: float) -> GeometryMetrics:
    """Geometry metrics for a twin, given wall thicknesses from the selected assemblies."""
    blocks, openings = params_from_twin(twin)
    return compute_metrics(blocks, openings, external_wall_thickness, separating_wall_thickness)
