"""3D mesh of a parametric twin (trimesh scene, glTF orientation, Plotly meshes).

:func:`build_mesh` returns a z-up :class:`trimesh.Scene` with one node per
element:

* ``"<block_id>/walls"`` - the block as a box from ground (z = 0) to the wall
  plate (FFL + storeys x floor-to-floor);
* ``"<block_id>/roof"`` - the convex hull of the roof's characteristic points:
  gable = triangular prism with verge overhang along the ridge and eaves
  overhang dropping ``o * tan(pitch)`` at the eaves; hip = eaves rectangle +
  ridge segment (pyramid when square); monopitch = right-triangular wedge;
  flat = 0.25 m slab (with edge overhang only when there is no parapet) plus
  parapet boxes;
* ``"opening/<opening_id>"`` - a thin box standing 0.04 m proud of the facade.

Each geometry carries ``metadata`` with ``block_id``, ``kind`` (``walls``,
``roof`` or the opening kind), ``opening_id`` / ``side`` for openings,
``colour_hex``, ``opacity``, ``basis`` and ``hidden_side_rule``.  Colours come
**only** from the twin's ``visual_finishes`` (appearance), never from the
construction assemblies; defaults are neutral ivory (walls) and graphite
(roof, openings).  Blocks not seen in any view and rule-generated openings
are drawn semi-transparent to flag them as assumptions.

Analytic checks (no overhang): wall box volume = w x d x plate; gable /
monopitch roof volume = 0.5 x span x rise x length; hip roof volume =
span x rise x (3 x length - span) / 6 - the same formulas as
``geometry.metrics`` roof void volumes.

:func:`scene_for_gltf` rotates a copy by -90 deg about X for glTF's y-up
convention; :func:`scene_to_plotly_meshes` flattens a scene into dicts for
``plotly.graph_objects.Mesh3d``; :func:`piece_outline_polylines` gives closed
rectangles for highlighting wall pieces of :class:`GeometryMetrics`.

The mesh is a visual aid at concept level, not BIM and not a measured model.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np
import trimesh

from ..core.models import (
    GLAZED_OPENINGS,
    Block,
    BuildingTwin,
    GeometryMetrics,
    Opening,
    OpeningKind,
    RoofForm,
    Side,
)

OPENING_DEPTH_M = 0.04
FLAT_SLAB_M = 0.25
PARAPET_THICKNESS_M = 0.20
DEFAULT_WALL_HEX = "#EDE6D3"  # neutral ivory
DEFAULT_ROOF_HEX = "#3C3F44"  # graphite
DEFAULT_OPENING_HEX = "#55595F"  # graphite (lighter)
HIDDEN_OPACITY = 0.55
_GLTF_ROTATION = trimesh.transformations.rotation_matrix(-math.pi / 2.0, [1.0, 0.0, 0.0])


# =============================================================================
# Helpers
# =============================================================================
def _hex_to_rgba(hexv: str, opacity: float = 1.0) -> list[int]:
    h = (hexv or "").lstrip("#")
    if len(h) != 6:
        h = DEFAULT_OPENING_HEX.lstrip("#")
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        r, g, b = (int(DEFAULT_OPENING_HEX.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return [r, g, b, int(round(255 * min(max(opacity, 0.0), 1.0)))]


def _finish_colours(twin: BuildingTwin) -> dict[str, str]:
    """First visual finish per element (appearance only)."""
    out: dict[str, str] = {}
    for vf in twin.visual_finishes:
        out.setdefault(vf.element, vf.colour_hex)
    return out


def _val(tv, default: Optional[float] = None) -> Optional[float]:
    if tv is None or tv.value is None:
        return default
    return float(tv.value)


class _B:
    """Plain numeric view of a block (None if any required value is unknown)."""

    def __init__(self, b: Block):
        self.id = b.block_id
        self.x0, self.y0 = _val(b.origin_x), _val(b.origin_y)
        self.w, self.d = _val(b.width), _val(b.depth)
        self.n = int(round(_val(b.storeys, 1)))
        self.ftf, self.ffl = _val(b.floor_to_floor), _val(b.ground_floor_level, 0.0)
        r = b.roof
        self.form = r.form
        self.pitch = 0.0 if r.form == RoofForm.FLAT else _val(r.pitch_deg)
        self.axis = r.ridge_axis
        self.eo, self.vo = _val(r.eaves_overhang_m, 0.0), _val(r.verge_overhang_m, 0.0)
        self.high = r.high_side or Side.FRONT
        self.parapet = _val(r.parapet_height_m, 0.0) or 0.0

    @property
    def ok(self) -> bool:
        return None not in (self.x0, self.y0, self.w, self.d, self.ftf, self.pitch) and self.w > 0 and self.d > 0

    @property
    def x1(self) -> float:
        return self.x0 + self.w

    @property
    def y1(self) -> float:
        return self.y0 + self.d

    @property
    def plate(self) -> float:
        return self.ffl + self.n * self.ftf


def _box(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> trimesh.Trimesh:
    m = trimesh.creation.box(extents=(x1 - x0, y1 - y0, z1 - z0))
    m.apply_translation((0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1)))
    return m


def roof_points(bp: "_B") -> np.ndarray:
    """Characteristic points of a pitched roof whose convex hull is the roof solid."""
    t = math.tan(math.radians(bp.pitch))
    x0, y0, x1, y1, plate = bp.x0, bp.y0, bp.x1, bp.y1, bp.plate
    eo, vo = bp.eo, bp.vo
    if bp.form == RoofForm.GABLE:
        if bp.axis == "x":
            rise = 0.5 * bp.d * t
            ze, zr, ym = plate - eo * t, plate + rise, 0.5 * (y0 + y1)
            xa, xb, ya, yb = x0 - vo, x1 + vo, y0 - eo, y1 + eo
            pts = [(xa, ya, ze), (xb, ya, ze), (xa, yb, ze), (xb, yb, ze), (xa, ym, zr), (xb, ym, zr)]
        else:
            rise = 0.5 * bp.w * t
            ze, zr, xm = plate - eo * t, plate + rise, 0.5 * (x0 + x1)
            xa, xb, ya, yb = x0 - eo, x1 + eo, y0 - vo, y1 + vo
            pts = [(xa, ya, ze), (xb, ya, ze), (xa, yb, ze), (xb, yb, ze), (xm, ya, zr), (xm, yb, zr)]
        return np.array(pts, dtype=float)
    if bp.form == RoofForm.HIP:
        span = min(bp.w, bp.d)
        zr, ze = plate + 0.5 * span * t, plate - eo * t
        pts = [(x0 - eo, y0 - eo, ze), (x1 + eo, y0 - eo, ze), (x0 - eo, y1 + eo, ze), (x1 + eo, y1 + eo, ze)]
        xm, ym = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
        if bp.w >= bp.d:
            pts += [(x0 + 0.5 * span, ym, zr), (x1 - 0.5 * span, ym, zr)]
        else:
            pts += [(xm, y0 + 0.5 * span, zr), (xm, y1 - 0.5 * span, zr)]
        return np.array(pts, dtype=float)
    if bp.form == RoofForm.MONOPITCH:
        high = bp.high
        along_y = high in (Side.FRONT, Side.REAR)
        span = bp.d if along_y else bp.w
        rise = span * t
        zl = plate - eo * t  # low eaves (with overhang)
        zh = plate + rise + vo * t  # high edge (with overhang)
        if along_y:
            xa, xb = x0 - vo, x1 + vo
            y_high, y_low = (y0 - vo, y1 + eo) if high == Side.FRONT else (y1 + vo, y0 - eo)
            pts = [(xa, y_low, zl), (xb, y_low, zl), (xa, y_high, zh), (xb, y_high, zh),
                   (xa, y_high, zl), (xb, y_high, zl)]
        else:
            ya, yb = y0 - vo, y1 + vo
            x_high, x_low = (x0 - vo, x1 + eo) if high == Side.LEFT else (x1 + vo, x0 - eo)
            pts = [(x_low, ya, zl), (x_low, yb, zl), (x_high, ya, zh), (x_high, yb, zh),
                   (x_high, ya, zl), (x_high, yb, zl)]
        return np.array(pts, dtype=float)
    raise ValueError("flat roofs have no pitched roof points")


def _roof_mesh(bp: "_B") -> trimesh.Trimesh:
    if bp.form == RoofForm.FLAT:
        o = 0.0 if bp.parapet > 1e-6 else bp.eo
        x0, y0, x1, y1, z = bp.x0 - o, bp.y0 - o, bp.x1 + o, bp.y1 + o, bp.plate
        corners = np.array([(x, y, zz) for x in (x0, x1) for y in (y0, y1) for zz in (z, z + FLAT_SLAB_M)])
        parts = [trimesh.convex.convex_hull(corners)]
        if bp.parapet > 1e-6:
            pt, top = PARAPET_THICKNESS_M, z + bp.parapet
            parts += [_box(bp.x0, bp.y0, z, bp.x1, bp.y0 + pt, top), _box(bp.x0, bp.y1 - pt, z, bp.x1, bp.y1, top),
                      _box(bp.x0, bp.y0 + pt, z, bp.x0 + pt, bp.y1 - pt, top),
                      _box(bp.x1 - pt, bp.y0 + pt, z, bp.x1, bp.y1 - pt, top)]
        return trimesh.util.concatenate(parts) if len(parts) > 1 else parts[0]
    return trimesh.convex.convex_hull(roof_points(bp))


def _opening_mesh(bp: "_B", o: Opening) -> Optional[trimesh.Trimesh]:
    vals = [_val(o.offset_m), _val(o.width_m), _val(o.height_m), _val(o.sill_m)]
    if any(v is None for v in vals):
        return None
    off, w, h, sill = vals
    if w <= 0 or h <= 0:
        return None
    z0 = bp.ffl + o.storey * bp.ftf + sill
    z1 = z0 + h
    T = OPENING_DEPTH_M
    if o.side == Side.FRONT:
        a = bp.x0 + off
        return _box(a, bp.y0 - T, z0, a + w, bp.y0, z1)
    if o.side == Side.REAR:
        b = bp.x1 - off
        return _box(b - w, bp.y1, z0, b, bp.y1 + T, z1)
    if o.side == Side.LEFT:
        b = bp.y1 - off
        return _box(bp.x0 - T, b - w, z0, bp.x0, b, z1)
    a = bp.y0 + off
    return _box(bp.x1, a, z0, bp.x1 + T, a + w, z1)


def _finish_for_opening(kind: OpeningKind, colours: dict[str, str]) -> str:
    if kind in GLAZED_OPENINGS:
        return colours.get("windows", DEFAULT_OPENING_HEX)
    if kind == OpeningKind.GARAGE_DOOR:
        return colours.get("garage_door", DEFAULT_OPENING_HEX)
    return colours.get("doors", DEFAULT_OPENING_HEX)


def _add(scene: trimesh.Scene, name: str, mesh: trimesh.Trimesh, hexv: str, opacity: float,
         meta: dict[str, Any]) -> None:
    mesh.visual.face_colors = _hex_to_rgba(hexv, opacity)
    mesh.metadata = {**meta, "colour_hex": hexv, "opacity": float(opacity), "name": name}
    scene.add_geometry(mesh, node_name=name, geom_name=name)


# =============================================================================
# Public API
# =============================================================================
def build_mesh(twin: BuildingTwin) -> trimesh.Scene:
    """Z-up scene with walls, roofs and openings as separate named nodes (see module docstring)."""
    scene = trimesh.Scene()
    colours = _finish_colours(twin)
    wall_hex = colours.get("walls", DEFAULT_WALL_HEX)
    roof_hex = colours.get("roof", DEFAULT_ROOF_HEX)
    warnings: list[str] = []
    bps: dict[str, _B] = {}
    for b in twin.blocks:
        bp = _B(b)
        if not bp.ok:
            warnings.append(f"Block {b.block_id} has unknown dimensions; not drawn.")
            continue
        bps[b.block_id] = bp
        seen = bool(b.visible_sides)
        op = 1.0 if seen else HIDDEN_OPACITY
        w_hex = wall_hex if seen else DEFAULT_WALL_HEX
        r_hex = roof_hex if seen else DEFAULT_ROOF_HEX
        visibility = "observed" if seen else "hidden (assumed)"
        _add(scene, f"{b.block_id}/walls", _box(bp.x0, bp.y0, 0.0, bp.x1, bp.y1, bp.plate), w_hex, op,
             {"block_id": b.block_id, "kind": "walls", "visibility": visibility,
              "basis": b.width.basis.value})
        if bp.form != RoofForm.FLAT and not (0.0 < bp.pitch < 75.0):
            warnings.append(f"Block {b.block_id} roof pitch {bp.pitch} deg outside (0, 75); roof not drawn.")
            continue
        _add(scene, f"{b.block_id}/roof", _roof_mesh(bp), r_hex, op,
             {"block_id": b.block_id, "kind": "roof", "form": bp.form.value, "visibility": visibility,
              "basis": b.roof.pitch_deg.basis.value})
    for o in twin.openings:
        bp = bps.get(o.block_id)
        if bp is None:
            continue
        m = _opening_mesh(bp, o)
        if m is None:
            warnings.append(f"Opening {o.opening_id} has unknown size/position; not drawn.")
            continue
        op = HIDDEN_OPACITY if o.hidden_side_rule else 1.0
        _add(scene, f"opening/{o.opening_id}", m, _finish_for_opening(o.kind, colours), op,
             {"block_id": o.block_id, "opening_id": o.opening_id, "kind": o.kind.value, "side": o.side.value,
              "storey": o.storey, "basis": o.width_m.basis.value, "hidden_side_rule": o.hidden_side_rule})
    scene.metadata.update({"twin_id": twin.twin_id, "twin_version": twin.version, "up_axis": "z", "units": "m",
                           "information_level": twin.information_level, "warnings": warnings,
                           "colour_source": "visual_finishes (appearance only); defaults neutral ivory/graphite"})
    return scene


def scene_for_gltf(scene: trimesh.Scene) -> trimesh.Scene:
    """Copy of a z-up scene rotated -90 deg about X for glTF (y-up)."""
    out = scene.copy()
    out.apply_transform(_GLTF_ROTATION)
    out.metadata.update({"up_axis": "y"})
    return out


def _jsonable(v: Any) -> bool:
    return v is None or isinstance(v, (str, int, float, bool))


def scene_to_plotly_meshes(scene: trimesh.Scene) -> list[dict[str, Any]]:
    """One dict per node: ``{name, x, y, z, i, j, k, color, opacity, meta}`` for ``go.Mesh3d``."""
    out: list[dict[str, Any]] = []
    for node in sorted(scene.graph.nodes_geometry):
        transform, gname = scene.graph[node]
        mesh = scene.geometry[gname]
        v = trimesh.transform_points(np.asarray(mesh.vertices, dtype=float), transform)
        f = np.asarray(mesh.faces, dtype=int)
        meta = {k: val for k, val in (mesh.metadata or {}).items() if _jsonable(val)}
        colour = meta.get("colour_hex")
        if not colour:
            fc = np.asarray(mesh.visual.face_colors)[0] if len(mesh.faces) else [128, 128, 128, 255]
            colour = "#{:02X}{:02X}{:02X}".format(int(fc[0]), int(fc[1]), int(fc[2]))
        out.append({
            "name": node, "x": v[:, 0].tolist(), "y": v[:, 1].tolist(), "z": v[:, 2].tolist(),
            "i": f[:, 0].tolist(), "j": f[:, 1].tolist(), "k": f[:, 2].tolist(),
            "color": colour, "opacity": float(meta.get("opacity", 1.0)), "meta": meta,
        })
    return out


def piece_outline_polylines(twin: BuildingTwin, metrics: GeometryMetrics, *,
                            offset_m: float = 0.03) -> list[dict[str, Any]]:
    """Closed rectangles (FFL..plate) for each wall piece, nudged ``offset_m`` outwards."""
    by = {b.block_id: _B(b) for b in twin.blocks}
    normal = {Side.FRONT: (0.0, -1.0), Side.REAR: (0.0, 1.0), Side.LEFT: (-1.0, 0.0), Side.RIGHT: (1.0, 0.0)}
    out: list[dict[str, Any]] = []
    for p in metrics.pieces:
        bp = by.get(p.block_id)
        if bp is None or not bp.ok:
            continue
        nx, ny = normal[p.side]
        x = [p.x0, p.x1, p.x1, p.x0, p.x0]
        y = [p.y0, p.y1, p.y1, p.y0, p.y0]
        z = [bp.ffl, bp.ffl, bp.plate, bp.plate, bp.ffl]
        out.append({"piece_id": p.piece_id, "block_id": p.block_id, "side": p.side.value, "exposure": p.exposure,
                    "x": [v + nx * offset_m for v in x], "y": [v + ny * offset_m for v in y], "z": z})
    return out


__all__ = ["build_mesh", "piece_outline_polylines", "roof_points", "scene_for_gltf", "scene_to_plotly_meshes",
           "DEFAULT_WALL_HEX", "DEFAULT_ROOF_HEX", "DEFAULT_OPENING_HEX"]
