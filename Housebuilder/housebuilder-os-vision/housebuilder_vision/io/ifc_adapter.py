"""Optional IFC4 export of a parametric twin (``ifcopenshell``, imported lazily).

:func:`export_ifc` writes a *conceptual* IFC4 model of a :class:`BuildingTwin`:

* ``IfcProject`` with SI units (metre, square metre, cubic metre, radian) and a
  3D ``Model`` / ``Body`` representation context;
* ``IfcSite`` -> ``IfcBuilding`` -> ``IfcBuildingStorey`` (one storey per distinct
  floor level ``FFL + k x floor_to_floor`` over all blocks, ``Elevation`` set);
* one ``IfcWall`` per **external** wall piece of :class:`GeometryMetrics` - a
  rectangle swept along the piece from FFL to the wall plate, thickness taken from
  the selected external-wall assembly (per-block override honoured) and placed on
  the inside of the external face (the outline is traversed counter-clockwise,
  inside on the left);
* one ``IfcSlab`` (``FLOOR``) per block: the block footprint, ground-floor
  assembly thickness below FFL;
* one ``IfcRoof`` per block aggregating an ``IfcSlab`` (``ROOF``) whose body is an
  ``IfcTriangulatedFaceSet`` taken from the twin's visual mesh (``twin.mesh``);
* one ``IfcWindow`` / ``IfcDoor`` per opening, placed at the opening position as a
  thin marker panel on the external wall face (**no opening voids**);
* property set ``Pset_AureomInformationLevel`` on the building stating the
  information level, the omissions, the source twin (id / version / hash) and a
  provenance summary (counts of observed / inferred / user-confirmed / assumed /
  unknown parameters).  Elements carry ``Aureom_Provenance`` (weakest basis of the
  parameters that place them) and walls / slabs ``Aureom_Construction`` (assembly
  id and name, recorded as a construction *hypothesis*).

Boundaries and assumptions
--------------------------
The model is a conceptual reconstruction (approx. LOD 100-200).  It is not
surveyed, not a design and not for construction.  It claims no structural
adequacy, regulatory compliance or energy performance; ``LoadBearing`` and
similar properties are deliberately not set because structure is never
identified from appearance.  Everything the model does not contain is listed in
:data:`IFC_OMISSIONS` and written into the file.  ``Pset_`` is normally reserved
for buildingSMART property sets; the name ``Pset_AureomInformationLevel`` is the
contract name used by Housebuilder.OS Vision.

GlobalIds are derived deterministically (UUID5) from the twin id and element
keys (piece / opening / block ids), so elements keep their ids across twin
versions; relationships and property sets get ids from their creation order, so
re-exporting the same twin yields identical ids.  The file header timestamp
still differs between runs.  ``ifcopenshell`` is imported only inside
:func:`export_ifc`; without it :class:`AdapterUnavailable` is raised with an
install hint.
"""

from __future__ import annotations

import math
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from ..core.models import (
    GLAZED_OPENINGS,
    AssemblyLibrary,
    Block,
    BuildingTwin,
    ElementType,
    GeometryMetrics,
    Opening,
    OpeningKind,
    RoofForm,
    Side,
)
from ..core.provenance import Basis, TrackedValue, weakest_basis

try:  # share the vision module's exception type so callers can catch one class
    from ..vision.adapters import AdapterUnavailable
except Exception:  # pragma: no cover - vision package unavailable / broken at import time
    class AdapterUnavailable(RuntimeError):  # type: ignore[no-redef]
        """The adapter cannot run here (missing optional package, key or model)."""


IFC_SCHEMA = "IFC4"
IFC_INSTALL_HINT = ("IFC export needs the optional 'ifcopenshell' package: "
                    "pip install 'housebuilder-os-vision[ifc]'  (or: pip install ifcopenshell)")
IFC_INFORMATION_LEVEL = "Conceptual reconstruction (approx. LOD 100-200); not surveyed; not for construction"
INFORMATION_PSET = "Pset_AureomInformationLevel"
PROVENANCE_PSET = "Aureom_Provenance"
CONSTRUCTION_PSET = "Aureom_Construction"
#: Thickness of window / door marker panels standing proud of the external wall face (m).
OPENING_PANEL_M = 0.04
#: Ground-floor slab depth used when the selected assembly has no layer thicknesses (m).
DEFAULT_SLAB_DEPTH_M = 0.15
#: External wall thickness used when neither library nor metrics give one (m).
DEFAULT_WALL_THICKNESS_M = 0.30
_LABEL_MAX = 255
_GUID_NAMESPACE = uuid.UUID("6f0e2c9a-6d1f-5b9e-9a57-4155524f454d")  # fixed namespace for Aureom twins
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

IFC_OMISSIONS: tuple[str, ...] = (
    "No opening voids: windows and doors are thin marker panels on the external wall face; no IfcOpeningElement "
    "is created and wall solids are not cut.",
    "No internal layout: no rooms or spaces (IfcSpace), internal partitions, stairs or upper floors.",
    "No structural members or sizing: no frames, lintels, joists, rafters, trusses or foundation design; nothing is "
    "structurally verified and load-bearing status is not stated.",
    "No services (MEP) of any kind.",
    "Construction assemblies are recorded as names (construction hypotheses) in property sets, not as layered "
    "material sets; no materials are assigned.",
    "Gable / monopitch / parapet infill above the wall plate is not modelled as wall geometry (the roof envelope "
    "solid closes the volume).",
    "Separating walls between blocks, and wall portions above a lower neighbouring block, are not modelled as "
    "IfcWall.",
    "Wall junctions are not cleaned or mitred: walls overlap at external corners and leave a notch at re-entrant "
    "corners.",
    "Roofs are envelope solids triangulated from the visual mesh: no roof build-up, soffits, fascias or rainwater "
    "goods.",
    "Ground-floor slabs are the block footprint at the ground-floor assembly thickness below FFL; no foundations or "
    "substructure walls.",
    "No terrain, site boundary or georeferencing: local coordinates in metres (x along the frontage, y front to "
    "rear, z up from external ground); levels are not surveyed.",
    "No quantity sets (Qto_*), classifications, costs, schedules or energy data.",
)


class IfcExportReport(BaseModel):
    """What was written, at what information level, and what was left out."""

    model_config = ConfigDict(extra="forbid")

    path: str
    schema_identifier: str = IFC_SCHEMA
    length_unit: str = "metre"
    entity_counts: dict[str, int] = Field(default_factory=dict)
    information_level: str = IFC_INFORMATION_LEVEL
    omissions: list[str] = Field(default_factory=lambda: list(IFC_OMISSIONS))
    warnings: list[str] = Field(default_factory=list)
    #: {"id", "version", "hash"} of the exported twin.
    source_twin: dict[str, Any] = Field(default_factory=dict)
    #: Parameter counts per basis (observed / inferred / user_confirmed / assumed / unknown).
    provenance_summary: dict[str, int] = Field(default_factory=dict)
    engine_version: str = ""
    ifcopenshell_version: str = ""


# =============================================================================
# Library-free helpers (also used by io.export)
# =============================================================================
def ifc_available() -> bool:
    """True when ``ifcopenshell`` can be imported (the import is attempted)."""
    try:
        import ifcopenshell  # noqa: F401
        import ifcopenshell.api  # noqa: F401
    except Exception:
        return False
    return True


def _walk_tracked(obj: Any, out: list[TrackedValue]) -> None:
    if isinstance(obj, TrackedValue):
        out.append(obj)
        return
    if isinstance(obj, BaseModel):
        for name in type(obj).model_fields:
            if name in ("history", "edit_log", "settings"):
                continue
            _walk_tracked(getattr(obj, name), out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _walk_tracked(item, out)
    elif isinstance(obj, dict):
        for item in obj.values():
            _walk_tracked(item, out)


def provenance_counts(twin: BuildingTwin) -> dict[str, int]:
    """Counts of the twin's tracked parameters per basis, plus assembly-selection bases.

    Parameters are every :class:`TrackedValue` in blocks (incl. roofs), openings, hidden-side
    assumptions and ``bathrooms``.  Keys: ``observed``, ``inferred``, ``user_confirmed``,
    ``assumed``, ``unknown``, ``total`` and ``assembly_selection_<basis>`` (selection bases;
    a selection without a recorded basis counts as assumed).
    """
    values: list[TrackedValue] = []
    _walk_tracked([twin.blocks, twin.openings, twin.hidden, twin.bathrooms], values)
    counts = {b.value: 0 for b in (Basis.OBSERVED, Basis.INFERRED, Basis.USER_CONFIRMED, Basis.ASSUMED,
                                   Basis.UNKNOWN)}
    for tv in values:
        counts[tv.basis.value] += 1
    counts["total"] = len(values)
    sel = twin.assemblies
    keys = ["external_wall", "separating_wall", "internal_partition", "ground_floor", "intermediate_floor",
            "pitched_roof", "flat_roof", "window", "external_door", "garage_door", "foundation"]
    for b in Basis:
        counts[f"assembly_selection_{b.value}"] = 0
    for k in keys:
        counts[f"assembly_selection_{sel.basis.get(k, Basis.ASSUMED).value}"] += 1
    for bid, ov in sel.block_overrides.items():
        for k in ov:
            counts[f"assembly_selection_{sel.basis.get(f'{bid}/{k}', Basis.ASSUMED).value}"] += 1
    return counts


def provenance_text(counts: dict[str, int]) -> str:
    """One-line human summary of :func:`provenance_counts`."""
    p = "; ".join(f"{k}={counts.get(k, 0)}" for k in ("observed", "inferred", "user_confirmed", "assumed", "unknown"))
    s = "; ".join(f"{k}={counts.get(f'assembly_selection_{k}', 0)}"
                  for k in ("observed", "inferred", "user_confirmed", "assumed", "unknown")
                  if counts.get(f"assembly_selection_{k}", 0))
    return f"Parameters: {p} (total {counts.get('total', 0)}). Assembly selections: {s or 'none'}."


def _clean(text: Any, limit: Optional[int] = None) -> str:
    s = _CTRL.sub(" ", str(text if text is not None else ""))
    return s[:limit] if limit else s


def _v(tv: Optional[TrackedValue]) -> Optional[float]:
    if tv is None or tv.value is None:
        return None
    v = float(tv.value)
    return v if math.isfinite(v) else None


def _guid(twin_id: str, key: str) -> str:
    import ifcopenshell.guid

    return ifcopenshell.guid.compress(uuid.uuid5(_GUID_NAMESPACE, f"{twin_id}/{key}").hex)


# Counter-clockwise traversal of a block outline (inside on the left of the direction).
_SIDE_DIR: dict[Side, tuple[float, float]] = {
    Side.FRONT: (1.0, 0.0), Side.RIGHT: (0.0, 1.0), Side.REAR: (-1.0, 0.0), Side.LEFT: (0.0, -1.0)}


def side_frame(x0: float, y0: float, x1: float, y1: float, side: Side) -> tuple[np.ndarray, np.ndarray]:
    """(start point, unit direction) of a block side traversed counter-clockwise.

    The start is the wall's *left end as seen from outside*, i.e. the origin of
    :attr:`Opening.offset_m` (FRONT min x, RIGHT min y, REAR max x, LEFT max y).
    """
    start = {Side.FRONT: (x0, y0), Side.RIGHT: (x1, y0), Side.REAR: (x1, y1), Side.LEFT: (x0, y1)}[side]
    return np.array(start, dtype=float), np.array(_SIDE_DIR[side], dtype=float)


def _placement(origin: tuple[float, float, float], direction: tuple[float, float]) -> np.ndarray:
    """4x4 world matrix: local X = plan direction, local Y = inward (left), Z up."""
    dx, dy = direction
    m = np.eye(4)
    m[:3, 0] = (dx, dy, 0.0)
    m[:3, 1] = (-dy, dx, 0.0)
    m[:3, 2] = (0.0, 0.0, 1.0)
    m[:3, 3] = origin
    return m


# =============================================================================
# Export
# =============================================================================
class _Writer:
    """Holds the ifcopenshell file and the API modules (imported lazily)."""

    def __init__(self, twin: BuildingTwin):
        try:
            import ifcopenshell
            import ifcopenshell.api.aggregate
            import ifcopenshell.api.context
            import ifcopenshell.api.geometry
            import ifcopenshell.api.project
            import ifcopenshell.api.pset
            import ifcopenshell.api.root
            import ifcopenshell.api.spatial
            import ifcopenshell.api.unit
            import ifcopenshell.guid  # noqa: F401
        except Exception as exc:  # ImportError or a broken binary build
            raise AdapterUnavailable(f"{IFC_INSTALL_HINT} ({type(exc).__name__}: {exc})") from exc
        self.ios = ifcopenshell
        self.api = ifcopenshell.api
        self.twin = twin
        self.f = ifcopenshell.api.project.create_file(version=IFC_SCHEMA)
        self.body = None
        self.keyed: set[int] = set()

    # ---------------------------------------------------------------- basics
    def entity(self, ifc_class: str, key: str, name: str, predefined_type: Optional[str] = None):
        e = self.api.root.create_entity(self.f, ifc_class=ifc_class, predefined_type=predefined_type,
                                        name=_clean(name, _LABEL_MAX))
        e.GlobalId = _guid(self.twin.twin_id, key)
        self.keyed.add(e.id())
        return e

    def stabilise_guids(self) -> None:
        """Deterministic GlobalIds for relationships / property sets created by the API.

        Their step ids follow the (deterministic) creation order, so identical twins give identical ids.
        """
        for e in sorted(self.f.by_type("IfcRoot"), key=lambda x: x.id()):
            if e.id() not in self.keyed:
                e.GlobalId = _guid(self.twin.twin_id, f"auto/{e.is_a()}/{e.id()}")

    def text(self, value: Any):
        """IfcLabel for short strings, IfcText otherwise (IfcLabel is limited to 255 characters)."""
        s = _clean(value)
        return self.f.createIfcLabel(s) if len(s) <= _LABEL_MAX else self.f.createIfcText(s)

    def pset(self, product, name: str, props: dict[str, Any]) -> None:
        clean: dict[str, Any] = {}
        for k, v in props.items():
            if v is None:
                continue
            if isinstance(v, str):
                clean[k] = self.text(v)
            elif isinstance(v, bool):
                clean[k] = v
            elif isinstance(v, int):
                clean[k] = int(v)
            elif isinstance(v, float):
                if math.isfinite(v):
                    clean[k] = float(v)
            else:
                clean[k] = self.text(v)
        ps = self.api.pset.add_pset(self.f, product=product, name=name)
        self.api.pset.edit_pset(self.f, pset=ps, properties=clean)

    def place(self, product, matrix: Optional[np.ndarray] = None) -> None:
        self.api.geometry.edit_object_placement(self.f, product=product,
                                                matrix=np.eye(4) if matrix is None else matrix, is_si=True)

    def box_rep(self, length: float, height: float, thickness: float, offset: float = 0.0):
        return self.api.geometry.add_wall_representation(self.f, context=self.body, length=float(length),
                                                         height=float(height), thickness=float(thickness),
                                                         offset=float(offset))

    def mesh_rep(self, vertices: np.ndarray, faces: np.ndarray, closed: bool):
        pts = self.f.createIfcCartesianPointList3D([tuple(float(c) for c in v) for v in vertices])
        idx = [tuple(int(i) + 1 for i in tri) for tri in faces]
        fs = self.f.createIfcTriangulatedFaceSet(Coordinates=pts, Closed=bool(closed), CoordIndex=idx)
        return self.f.createIfcShapeRepresentation(ContextOfItems=self.body, RepresentationIdentifier="Body",
                                                   RepresentationType="Tessellation", Items=[fs])


def _assembly_name(library: Optional[AssemblyLibrary], assembly_id: str) -> tuple[str, Optional[float]]:
    if library is None:
        return assembly_id, None
    try:
        a = library.assembly(assembly_id)
    except KeyError:
        return assembly_id, None
    t = a.total_thickness_m
    return a.name, (t if t > 0 else None)


def _block_basis(b: Block) -> Basis:
    return weakest_basis(b.origin_x.basis, b.origin_y.basis, b.width.basis, b.depth.basis, b.storeys.basis,
                         b.floor_to_floor.basis, b.ground_floor_level.basis)


def _opening_basis(o: Opening) -> Basis:
    return weakest_basis(o.offset_m.basis, o.width_m.basis, o.height_m.basis, o.sill_m.basis)


_ROOF_TYPE = {RoofForm.GABLE: "GABLE_ROOF", RoofForm.HIP: "HIP_ROOF", RoofForm.FLAT: "FLAT_ROOF",
              RoofForm.MONOPITCH: "SHED_ROOF"}
_COUNTED = ("IfcProject", "IfcSite", "IfcBuilding", "IfcBuildingStorey", "IfcWall", "IfcSlab", "IfcRoof",
            "IfcWindow", "IfcDoor", "IfcPropertySet", "IfcTriangulatedFaceSet")


def _resolve_metrics(twin: BuildingTwin, metrics: Optional[GeometryMetrics],
                     library: Optional[AssemblyLibrary]) -> GeometryMetrics:
    if metrics is not None:
        return metrics
    from ..geometry.metrics import compute_geometry_metrics

    t_ext, t_sep = DEFAULT_WALL_THICKNESS_M, 0.0
    if library is not None:
        from ..quantities.takeoff import wall_thicknesses

        t_ext, t_sep = wall_thicknesses(twin, library)
    return compute_geometry_metrics(twin, t_ext, t_sep)


def export_ifc(twin: BuildingTwin, metrics: Optional[GeometryMetrics], path: Union[str, Path], *,
               library: Optional[AssemblyLibrary] = None) -> IfcExportReport:
    """Write a conceptual IFC4 model of ``twin`` to ``path`` (see module docstring).

    ``metrics`` must be the :class:`GeometryMetrics` of this twin (e.g. ``boq.geometry``); when
    ``None`` it is computed (wall thicknesses from ``library``, else 0.30 m with a warning).
    ``library`` supplies assembly names and thicknesses; without it the external wall thickness
    comes from ``metrics`` and assemblies are recorded by id.

    Raises :class:`AdapterUnavailable` (with an install hint) when ``ifcopenshell`` is missing and
    :class:`~housebuilder_vision.geometry.GeometryError` when the twin geometry is unresolved.
    The file is written atomically (temporary file in the target directory, then renamed).
    """
    w = _Writer(twin)  # raises AdapterUnavailable first, before any work
    from ..twin.builder import twin_hash
    from ..twin.mesh import build_mesh
    from .export import engine_version

    warnings: list[str] = []
    if metrics is None and library is None:
        warnings.append(f"No metrics or library supplied: walls use an assumed {DEFAULT_WALL_THICKNESS_M:.2f} m "
                        "thickness.")
    metrics = _resolve_metrics(twin, metrics, library)
    f, api = w.f, w.api
    sel = twin.assemblies
    counts = provenance_counts(twin)
    thash = twin_hash(twin)
    version = engine_version()

    # ---- project, units, contexts
    project = w.entity("IfcProject", "project", twin.name or twin.twin_id)
    project.Description = _clean(twin.information_level)
    project.Phase = "Concept"
    units = [api.unit.add_si_unit(f, unit_type=t) for t in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT",
                                                            "PLANEANGLEUNIT")]
    api.unit.assign_unit(f, units=units)
    model_ctx = api.context.add_context(f, context_type="Model")
    w.body = api.context.add_context(f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW",
                                     parent=model_ctx)

    # ---- spatial structure
    site = w.entity("IfcSite", "site", "Site (not surveyed)")
    site.Description = _clean(f"Location as entered: {twin.settings.site_location}", _LABEL_MAX)
    building = w.entity("IfcBuilding", "building", twin.name or twin.twin_id)
    building.Description = _clean(twin.information_level)
    api.aggregate.assign_object(f, products=[site], relating_object=project)
    api.aggregate.assign_object(f, products=[building], relating_object=site)
    w.place(site)
    w.place(building)

    bm = {b.block_id: b for b in metrics.blocks}
    blocks = {b.block_id: b for b in twin.blocks}
    levels: dict[float, list[str]] = {}
    for b in twin.blocks:
        m = bm.get(b.block_id)
        ftf = _v(b.floor_to_floor)
        if m is None or ftf is None:
            warnings.append(f"Block {b.block_id} has no computed metrics; not exported.")
            continue
        for k in range(m.storeys):
            levels.setdefault(round(m.ffl_m + k * ftf, 3), []).append(f"{b.block_id}:{k}")
    storeys: dict[float, Any] = {}
    for i, z in enumerate(sorted(levels)):
        st = w.entity("IfcBuildingStorey", f"storey/{z:.3f}", f"Storey {i}")
        st.LongName = _clean(f"Level {i} at {z:.3f} m above external ground (FFL + k x floor-to-floor)", _LABEL_MAX)
        st.Elevation = float(z)
        api.aggregate.assign_object(f, products=[st], relating_object=building)
        mat = np.eye(4)
        mat[2, 3] = z
        w.place(st, mat)
        storeys[z] = st

    def storey_at(block_id: str, k: int):
        b, m = blocks[block_id], bm[block_id]
        ftf = _v(b.floor_to_floor) or 0.0
        k = max(0, min(int(k), m.storeys - 1))
        return storeys[round(m.ffl_m + k * ftf, 3)]

    def contain(product, storey) -> None:
        api.spatial.assign_container(f, products=[product], relating_structure=storey)

    # ---- external walls
    n_walls = 0
    for pc in metrics.pieces:
        if pc.exposure != "external":
            continue
        if pc.block_id not in blocks or pc.block_id not in bm:
            warnings.append(f"Wall piece {pc.piece_id} references unknown block {pc.block_id}; skipped.")
            continue
        b, m = blocks[pc.block_id], bm[pc.block_id]
        p0, p1 = np.array([pc.x0, pc.y0]), np.array([pc.x1, pc.y1])
        _, d = side_frame(0, 0, 0, 0, pc.side)
        if float(np.dot(p1 - p0, d)) < 0:
            p0, p1 = p1, p0
        length = float(np.linalg.norm(p1 - p0))
        height = m.plate_height_m - m.ffl_m
        if length <= 1e-6 or height <= 1e-6:
            warnings.append(f"Wall piece {pc.piece_id} has zero length or height; skipped.")
            continue
        aid = sel.for_element(ElementType.EXTERNAL_WALL, pc.block_id)
        aname, t = _assembly_name(library, aid)
        if t is None:
            t = metrics.external_wall_thickness_m if metrics.external_wall_thickness_m > 0 else None
        if t is None:
            t = DEFAULT_WALL_THICKNESS_M
            warnings.append(f"Wall piece {pc.piece_id}: thickness unknown, {t:.2f} m assumed.")
        wall = w.entity("IfcWall", f"wall/{pc.piece_id}", f"External wall {pc.piece_id}", "NOTDEFINED")
        wall.Description = _clean(f"{pc.side.value} wall of block {pc.block_id}, {length:.3f} m long, FFL to wall "
                                  f"plate ({height:.3f} m)", _LABEL_MAX)
        contain(wall, storey_at(pc.block_id, 0))
        w.place(wall, _placement((float(p0[0]), float(p0[1]), m.ffl_m), (float(d[0]), float(d[1]))))
        api.geometry.assign_representation(f, product=wall, representation=w.box_rep(length, height, t))
        w.pset(wall, "Pset_WallCommon", {"IsExternal": True})
        w.pset(wall, PROVENANCE_PSET, {
            "PieceId": pc.piece_id, "BlockId": pc.block_id, "Side": pc.side.value,
            "GeometryBasis": _block_basis(b).value,
            "Note": "Dimensions inherit the weakest basis of the block parameters; not surveyed."})
        w.pset(wall, CONSTRUCTION_PSET, {
            "AssemblyId": aid, "AssemblyName": aname,
            "SelectionBasis": sel.basis.get(f"{pc.block_id}/external_wall",
                                            sel.basis.get("external_wall", Basis.ASSUMED)).value,
            "ThicknessM": float(t),
            "Note": "Construction hypothesis recorded by name; not identified from appearance; not a specification."})
        n_walls += 1

    # ---- ground-floor slabs
    for b in twin.blocks:
        m = bm.get(b.block_id)
        x0, y0 = _v(b.origin_x), _v(b.origin_y)
        if m is None or x0 is None or y0 is None:
            continue
        aid = sel.for_element(ElementType.GROUND_FLOOR, b.block_id)
        aname, depth = _assembly_name(library, aid)
        if depth is None:
            depth = DEFAULT_SLAB_DEPTH_M
            warnings.append(f"Ground-floor slab of {b.block_id}: thickness unknown, {depth:.2f} m assumed.")
        slab = w.entity("IfcSlab", f"slab/{b.block_id}", f"Ground floor {b.block_id}", "FLOOR")
        contain(slab, storey_at(b.block_id, 0))
        mat = np.eye(4)
        mat[:3, 3] = (x0, y0, m.ffl_m - depth)
        w.place(slab, mat)
        rep = api.geometry.add_slab_representation(
            f, context=w.body, depth=float(depth),
            polyline=[(0.0, 0.0), (m.width_m, 0.0), (m.width_m, m.depth_m), (0.0, m.depth_m)])
        api.geometry.assign_representation(f, product=slab, representation=rep)
        w.pset(slab, PROVENANCE_PSET, {"BlockId": b.block_id, "GeometryBasis": _block_basis(b).value})
        w.pset(slab, CONSTRUCTION_PSET, {
            "AssemblyId": aid, "AssemblyName": aname, "ThicknessM": float(depth),
            "SelectionBasis": sel.basis.get(f"{b.block_id}/ground_floor",
                                            sel.basis.get("ground_floor", Basis.ASSUMED)).value,
            "Note": "Construction hypothesis recorded by name; not a specification."})

    # ---- roofs (envelope solids from the visual mesh)
    scene = build_mesh(twin)
    for node in sorted(scene.graph.nodes_geometry):
        transform, gname = scene.graph[node]
        mesh = scene.geometry[gname]
        meta = mesh.metadata or {}
        if meta.get("kind") != "roof" or meta.get("block_id") not in bm:
            continue
        bid = meta["block_id"]
        b, m = blocks[bid], bm[bid]
        verts = np.asarray(mesh.vertices, dtype=float)
        verts = (np.c_[verts, np.ones(len(verts))] @ np.asarray(transform, dtype=float).T)[:, :3]
        roof = w.entity("IfcRoof", f"roof/{bid}", f"Roof {bid}", _ROOF_TYPE.get(b.roof.form, "NOTDEFINED"))
        contain(roof, storey_at(bid, m.storeys - 1))
        w.place(roof)
        rslab = w.entity("IfcSlab", f"roof/{bid}/slab", f"Roof envelope {bid}", "ROOF")
        api.aggregate.assign_object(f, products=[rslab], relating_object=roof)
        w.place(rslab)
        api.geometry.assign_representation(f, product=rslab, representation=w.mesh_rep(
            verts, np.asarray(mesh.faces, dtype=int), bool(mesh.is_watertight)))
        flat = b.roof.form == RoofForm.FLAT
        rid = sel.for_element(ElementType.FLAT_ROOF if flat else ElementType.PITCHED_ROOF, bid)
        roof_bases = [_block_basis(b), b.roof.eaves_overhang_m.basis, b.roof.verge_overhang_m.basis]
        if not flat:
            roof_bases.append(b.roof.pitch_deg.basis)
        w.pset(roof, PROVENANCE_PSET, {
            "BlockId": bid, "RoofForm": b.roof.form.value,
            "GeometryBasis": weakest_basis(roof_bases).value,
            "Note": "Roof envelope solid triangulated from the visual mesh (roof void volume, overhangs included)."})
        w.pset(roof, CONSTRUCTION_PSET, {"AssemblyId": rid, "AssemblyName": _assembly_name(library, rid)[0],
                                         "Note": "Construction hypothesis recorded by name; not a specification."})
    for wmsg in scene.metadata.get("warnings", []) or []:
        warnings.append(f"mesh: {wmsg}")

    # ---- windows and doors (placement markers, no voids)
    for o in twin.openings:
        if o.block_id not in blocks or o.block_id not in bm:
            warnings.append(f"Opening {o.opening_id} references unknown block {o.block_id}; skipped.")
            continue
        b, m = blocks[o.block_id], bm[o.block_id]
        vals = [_v(o.offset_m), _v(o.width_m), _v(o.height_m), _v(o.sill_m), _v(b.origin_x), _v(b.origin_y),
                _v(b.floor_to_floor)]
        if any(v is None for v in vals):
            warnings.append(f"Opening {o.opening_id} has unknown size or position; skipped.")
            continue
        off, ow, oh, sill, bx, by, ftf = vals  # type: ignore[misc]
        if ow <= 0 or oh <= 0:
            warnings.append(f"Opening {o.opening_id} has non-positive size; skipped.")
            continue
        if o.storey >= m.storeys:
            warnings.append(f"Opening {o.opening_id} is on storey {o.storey} but block {o.block_id} has "
                            f"{m.storeys}; placed at its level but contained in the top storey.")
        start, d = side_frame(bx, by, bx + m.width_m, by + m.depth_m, o.side)
        p = start + off * d
        z0 = m.ffl_m + o.storey * ftf + sill
        if o.kind == OpeningKind.WINDOW:
            el = w.entity("IfcWindow", f"opening/{o.opening_id}", f"Window {o.opening_id}", "WINDOW")
        elif o.kind == OpeningKind.GARAGE_DOOR:
            el = w.entity("IfcDoor", f"opening/{o.opening_id}", f"Garage door {o.opening_id}", "USERDEFINED")
            el.ObjectType = "Garage door"
        else:
            el = w.entity("IfcDoor", f"opening/{o.opening_id}",
                          f"{o.kind.value.replace('_', ' ').capitalize()} {o.opening_id}", "DOOR")
        el.OverallWidth = float(ow)
        el.OverallHeight = float(oh)
        contain(el, storey_at(o.block_id, o.storey))
        w.place(el, _placement((float(p[0]), float(p[1]), z0), (float(d[0]), float(d[1]))))
        api.geometry.assign_representation(f, product=el, representation=w.box_rep(
            ow, oh, OPENING_PANEL_M, offset=-OPENING_PANEL_M))
        common = "Pset_WindowCommon" if o.kind == OpeningKind.WINDOW else "Pset_DoorCommon"
        w.pset(el, common, {"IsExternal": True})
        w.pset(el, PROVENANCE_PSET, {
            "OpeningId": o.opening_id, "BlockId": o.block_id, "Side": o.side.value, "Storey": int(o.storey),
            "OpeningKind": o.kind.value, "Glazed": o.kind in GLAZED_OPENINGS,
            "GeometryBasis": _opening_basis(o).value, "FeatureId": o.feature_id,
            "HiddenSideRule": o.hidden_side_rule,
            "Note": ("Generated by a hidden-side rule (assumed), not observed." if o.hidden_side_rule else
                     "Placement marker on the external wall face; no opening void.")})

    # ---- information level on the building
    omissions = list(IFC_OMISSIONS)
    w.pset(building, INFORMATION_PSET, {
        "InformationLevel": IFC_INFORMATION_LEVEL,
        "Omissions": " | ".join(omissions),
        "SourceTwin": f"id={twin.twin_id}; version={twin.version}; sha256={thash}",
        "SourceTwinId": twin.twin_id,
        "SourceTwinVersion": int(twin.version),
        "SourceTwinHash": thash,
        "Provenance": provenance_text(counts),
        "ObservedParameters": counts["observed"],
        "InferredParameters": counts["inferred"],
        "UserConfirmedParameters": counts["user_confirmed"],
        "AssumedParameters": counts["assumed"],
        "UnknownParameters": counts["unknown"],
        "CalibrationMethod": twin.calibration_method,
        "SourceHypothesis": twin.source_hypothesis_id,
        "LengthUnit": "metre",
        "Disclaimer": ("No regulatory compliance, structural adequacy, energy performance or surveyed accuracy is "
                       "claimed. Construction assemblies are hypotheses recorded by name."),
        "GeneratedBy": f"Aureom Housebuilder.OS Vision {version}",
    })

    w.stabilise_guids()

    # ---- write atomically
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".ifc-", suffix=".ifc", dir=str(out.parent))
    os.close(fd)
    try:
        f.write(tmp)
        os.replace(tmp, out)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    if n_walls != sum(1 for pc in metrics.pieces if pc.exposure == "external"):
        warnings.append("Not every external wall piece could be exported as an IfcWall.")
    return IfcExportReport(
        path=str(out), entity_counts={c: len(f.by_type(c)) for c in _COUNTED}, warnings=warnings,
        source_twin={"id": twin.twin_id, "version": twin.version, "hash": thash},
        provenance_summary=counts, engine_version=version, ifcopenshell_version=str(w.ios.version),
    )


__all__ = [
    "AdapterUnavailable",
    "DEFAULT_SLAB_DEPTH_M",
    "IFC_INFORMATION_LEVEL",
    "IFC_INSTALL_HINT",
    "IFC_OMISSIONS",
    "IFC_SCHEMA",
    "INFORMATION_PSET",
    "IfcExportReport",
    "export_ifc",
    "ifc_available",
    "provenance_counts",
    "provenance_text",
    "side_frame",
]
