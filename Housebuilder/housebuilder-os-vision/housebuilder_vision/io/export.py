"""Project export: JSON model state, glTF (GLB) massing, CSV tables and optional IFC.

:func:`export_project` writes a self-describing folder::

    project.json          complete model state (Project.model_dump_json) - the source of truth
    results.json          optional result objects (BoQ, cost estimate, simulation, repeat-build,
                          scenario comparison) + engine versions, source-image sha256s, twin hash,
                          seed and a provenance note, so results can be reproduced
    twin.glb              visual massing (walls / roofs / openings as named nodes, y-up)
    quantities.csv        one row per BoQ line, every field (basis / status / trace flattened)
    costs.csv             one row per cost line (+ rate source type and FICTIONAL labels)
    cost_boundaries.csv   cumulative cost boundaries
    repeat_build.csv      C(n), average and incremental cost rows (when supplied)
    simulation_summary.csv / scenario_comparison.csv   (when supplied)
    twin.ifc              conceptual IFC4 model (only when ifcopenshell is installed)
    README.txt            information level, provenance and pricing notes, file list
    manifest.json         ExportManifest: every file with format, sha256, size and description

Rules and boundaries
--------------------
* File names are fixed constants; nothing from the project (ids, names, filenames
  of uploaded images) is used to build a path, and every target is checked to
  resolve inside ``out_dir`` (no traversal, no writing through symlinks).  Writes
  are atomic (temporary file + rename).
* CSV cells are protected against formula injection: string cells starting with
  ``= + - @``, tab or carriage return get a leading apostrophe; numbers are
  written unchanged.
* The GLB is visual geometry only (not BIM, not measured).  The IFC file is a
  conceptual reconstruction (approx. LOD 100-200) with its omissions declared.
* Prices are only as good as the rate book; rates whose source is the bundled
  demo data are labelled FICTIONAL in every table and note.
* Missing optional dependencies never fail an export: a missing ``ifcopenshell``
  becomes a manifest warning.
* When ``boq`` is not supplied but the project has a twin, the bill of quantities
  is computed at export time from ``project.twin`` and the library (recorded as
  ``boq_source``).  No cost estimate or simulation is ever computed here.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence, Union

from pydantic import BaseModel, ConfigDict, Field

from ..core.models import (
    COST_LAYER_NAMES,
    SCHEMA_VERSION,
    AssemblyLibrary,
    BillOfQuantities,
    BuildingTwin,
    CostEstimate,
    CostLine,
    GeometryMetrics,
    Project,
    QuantityLine,
    Rate,
    RateBook,
    RateSourceType,
    RepeatBuildResult,
    ScenarioComparison,
    ScenarioOutcome,
    SimulationResult,
)
from ..core.provenance import BASIS_LABEL, Basis, utcnow, weakest_basis
from .ifc_adapter import IFC_INSTALL_HINT, AdapterUnavailable, IfcExportReport, provenance_counts

ENGINE_NAME = "Aureom Housebuilder.OS Vision"
DISTRIBUTION_NAME = "housebuilder-os-vision"
FORMATS: tuple[str, ...] = ("json", "glb", "csv", "ifc")
#: Leading characters that make spreadsheet applications evaluate a cell.
CSV_INJECTION_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r")
FICTIONAL_LABEL = "FICTIONAL demo rate - not a market price"

EXPORT_INFORMATION_LEVEL = (
    "Conceptual parametric reconstruction from images and labelled assumptions (approx. LOD 100-200). "
    "Not a measured survey, not a design, not construction-ready BIM. No regulatory compliance, structural "
    "adequacy, certified energy performance or surveyed accuracy is claimed."
)
PROVENANCE_NOTE = (
    "Every parameter carries a basis: observed (measured from image evidence), inferred (derived by a rule or "
    "model from observations), user_confirmed (entered or confirmed by a person), assumed (labelled default the "
    "user may replace) or unknown (not recoverable; dependent quantities are unresolved, never invented). Derived "
    "quantities and costs take the weakest basis of their inputs. Visual finishes describe appearance only and "
    "never establish structure, insulation, foundations or services; construction assemblies are hypotheses."
)
GLB_NOTICE = (
    "Visual geometry only: conceptual massing of the parametric twin for viewing. Not BIM, not a measured model, "
    "not for construction. Colours come from visual finishes (appearance), not from construction assemblies. "
    "Semi-transparent elements are hidden/assumed. Units metres, glTF y-up."
)

_DEFAULT_TWIN_LEVEL = BuildingTwin.model_fields["information_level"].default
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,99}$")


# =============================================================================
# Versions and hashing
# =============================================================================
def _dist_version(name: str) -> Optional[str]:
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover
        return None
    try:
        return version(name)
    except PackageNotFoundError:
        return None
    except Exception:  # pragma: no cover - corrupt metadata
        return None


def engine_version() -> str:
    """Engine version: installed distribution metadata, else the source tree's pyproject, else 'unknown'."""
    v = _dist_version(DISTRIBUTION_NAME)
    if v:
        return v
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    m = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    return f"{m.group(1)}+source" if m else "unknown"


def engine_versions() -> dict[str, str]:
    """Versions that affect results (engine, model schema, Python and key libraries; no imports done)."""
    out = {"engine": f"{ENGINE_NAME} {engine_version()}", "model_schema": SCHEMA_VERSION,
           "python": sys.version.split()[0]}
    for dist in ("pydantic", "numpy", "scipy", "pandas", "trimesh", "ifcopenshell"):
        v = _dist_version(dist)
        if v:
            out[dist] = v
    return out


def _finite(obj: Any) -> Any:
    """Replace non-finite floats with None (strict JSON)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite(v) for v in obj]
    return obj


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def canonical_json(obj: Any) -> str:
    """Canonical JSON (sorted keys, compact, non-finite floats as null) of models / plain data."""
    return json.dumps(_finite(_jsonable(obj)), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def sha256_hex(data: Union[bytes, str]) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def canonical_sha256(obj: Any) -> str:
    """SHA-256 of :func:`canonical_json` - stable fingerprint of inputs / outputs for run logs."""
    return sha256_hex(canonical_json(obj))


# =============================================================================
# CSV
# =============================================================================
def sanitize_cell(value: Any) -> Any:
    """CSV cell value with formula-injection protection.

    ``None`` -> empty; numbers (int / float) are returned unchanged; booleans as ``true`` /
    ``false``; enums by value; any other value as a string, prefixed with ``'`` when it starts
    with ``= + - @``, tab or carriage return.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, Enum):
        value = value.value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    s = str(value)
    if s.startswith(CSV_INJECTION_PREFIXES):
        s = "'" + s
    return s


def csv_bytes(columns: Sequence[str], rows: Iterable[dict[str, Any]]) -> bytes:
    """UTF-8 CSV (header + rows, excel dialect) with every cell passed through :func:`sanitize_cell`."""
    buf = io.StringIO()
    wr = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    wr.writerow([sanitize_cell(c) for c in columns])
    for row in rows:
        wr.writerow([sanitize_cell(row.get(c)) for c in columns])
    return buf.getvalue().encode("utf-8")


def _trace_text(line: QuantityLine) -> str:
    return " | ".join(f"{t.kind}:{t.ref}" + (f" ({t.description})" if t.description else "") for t in line.trace)


def quantity_rows(boq: BillOfQuantities) -> tuple[list[str], list[dict[str, Any]]]:
    """Columns and rows for ``quantities.csv``: every :class:`QuantityLine` field, flattened."""
    fields = list(QuantityLine.model_fields)
    extra = ["basis_label", "trace_kinds", "twin_id", "twin_version", "library_name"]
    cols = fields + extra
    rows: list[dict[str, Any]] = []
    for ln in boq.lines:
        row: dict[str, Any] = {}
        for name in fields:
            v = getattr(ln, name)
            if name == "trace":
                v = _trace_text(ln)
            elif name == "geometry_refs":
                v = "; ".join(v)
            row[name] = v
        row["basis_label"] = BASIS_LABEL.get(ln.basis, str(ln.basis))
        row["trace_kinds"] = "; ".join(sorted({t.kind for t in ln.trace}))
        row["twin_id"], row["twin_version"], row["library_name"] = boq.twin_id, boq.twin_version, boq.library_name
        rows.append(row)
    return cols, rows


def is_fictional_rate(rate: Rate) -> bool:
    """True for bundled demonstration rates (source type or source/supplier text says fictional)."""
    return (rate.source_type == RateSourceType.FICTIONAL_DEMO or "fictional" in rate.source.lower()
            or "fictional" in rate.supplier.lower())


def _estimate_uses_fictional(estimate: CostEstimate, rates: dict[str, Rate]) -> bool:
    if any(ln.rate_id in rates and is_fictional_rate(rates[ln.rate_id]) for ln in estimate.lines if ln.rate_id):
        return True
    text = " ".join([estimate.rate_book_name, *estimate.warnings]).lower()
    return "fictional" in text


def cost_rows(estimate: CostEstimate, rate_book: Optional[RateBook] = None) -> tuple[list[str], list[dict[str, Any]]]:
    """Columns and rows for ``costs.csv`` (one per :class:`CostLine`).

    Adds ``layer_name``, ``rate_source_type`` / ``rate_source`` (looked up by ``rate_id`` in
    ``rate_book``) and ``price_label`` (``FICTIONAL ...`` for demo rates).
    """
    rates = {r.rate_id: r for r in (rate_book.rates if rate_book else [])}
    fields = list(CostLine.model_fields)  # additive CostLine fields are exported automatically
    cols = fields[:2] + ["layer_name"] + fields[2:] + ["basis_label", "rate_source_type", "rate_source",
                                                       "price_label"]
    any_fictional = _estimate_uses_fictional(estimate, rates)
    rows: list[dict[str, Any]] = []
    for ln in estimate.lines:
        row = {n: getattr(ln, n) for n in fields}
        row["layer_name"] = COST_LAYER_NAMES.get(ln.layer, str(ln.layer))
        row["basis_label"] = BASIS_LABEL.get(ln.basis, str(ln.basis))
        r = rates.get(ln.rate_id) if ln.rate_id else None
        if r is not None:
            row["rate_source_type"], row["rate_source"] = r.source_type.value, r.source
            row["price_label"] = FICTIONAL_LABEL if is_fictional_rate(r) else ""
        elif ln.rate_id:
            row["rate_source_type"] = "unknown (rate not in exported rate book)"
            row["price_label"] = ("Rate source not verifiable; estimate uses FICTIONAL demo rates"
                                  if any_fictional else "Rate source not verifiable")
        else:
            row["price_label"] = ("Derived from other lines that include FICTIONAL demo rates" if any_fictional
                                  else "")
        rows.append(row)
    return cols, rows


def boundary_rows(estimate: CostEstimate, rate_book: Optional[RateBook] = None
                  ) -> tuple[list[str], list[dict[str, Any]]]:
    """Columns and rows for ``cost_boundaries.csv`` (one per :class:`CostBoundary`).

    ``basis`` is the weakest basis of the cost lines summed in the boundary; ``unresolved_items`` counts the
    unresolved items in its layers and ``completeness`` says ``INCOMPLETE - lower bound`` when there are any.
    """
    rates = {r.rate_id: r for r in (rate_book.rates if rate_book else [])}
    label = ("Includes FICTIONAL demo rates - not market prices"
             if _estimate_uses_fictional(estimate, rates) else "")
    cols = ["key", "name", "layers", "amount", "currency", "per_m2_gia", "gia_m2", "basis", "basis_label",
            "unresolved_items", "completeness", "definition", "excludes", "pricing_date", "location",
            "rate_book_name", "price_label"]
    rows = []
    for b in estimate.boundaries:
        rows.append({
            "key": b.key, "name": b.name, "layers": "; ".join(layer.value for layer in b.layers),
            "amount": b.amount, "currency": estimate.currency,
            "per_m2_gia": (b.amount / estimate.gia_m2) if estimate.gia_m2 > 0 else None,
            "gia_m2": estimate.gia_m2, "basis": b.basis.value, "basis_label": BASIS_LABEL.get(b.basis, str(b.basis)),
            "unresolved_items": b.unresolved_count,
            "completeness": (f"INCOMPLETE - lower bound ({b.unresolved_count} unresolved item(s) not priced)"
                             if b.unresolved_count else "complete"),
            "definition": b.definition, "excludes": b.excludes,
            "pricing_date": estimate.pricing_date.isoformat(), "location": estimate.location,
            "rate_book_name": estimate.rate_book_name, "price_label": label,
        })
    return cols, rows


def rate_book_rows(book: RateBook) -> tuple[list[str], list[dict[str, Any]]]:
    """Columns (= ``Rate`` fields) and rows of a rate book for CSV download / export.

    Use with :func:`csv_bytes`, which applies the formula-injection guard: supplier text fields
    (description, source, supplier, notes, quote reference) are untrusted and stored verbatim.
    """
    from ..costing.rates import RATE_COLUMNS

    cols = list(RATE_COLUMNS)
    return cols, [r.model_dump(mode="json") for r in book.rates]


def geometry_bases(twin: BuildingTwin) -> dict[str, Basis]:
    """Weakest basis of the twin values each geometry summary depends on (derived values take the weakest basis).

    ``plan`` (footprint, GEA): block widths, depths, positions and storeys; ``gia``: plan + the external-wall
    assembly selection (wall thickness); ``walls`` (gross external / separating wall): plan + storey heights
    and FFL + roof pitches (gable infill); ``openings``: opening sizes; ``net_walls``: walls + openings;
    ``roof``: plan + pitches and overhangs; ``volume``: plan + storey heights.
    """
    plan: list[Basis] = []
    heights: list[Basis] = []
    roof: list[Basis] = []
    for b in twin.blocks:
        plan += [b.width.basis, b.depth.basis, b.origin_x.basis, b.origin_y.basis, b.storeys.basis]
        heights += [b.floor_to_floor.basis, b.ground_floor_level.basis]
        r = b.roof
        roof += [r.eaves_overhang_m.basis, r.verge_overhang_m.basis]
        if r.form.value != "flat":
            roof.append(r.pitch_deg.basis)
        elif r.parapet_height_m is not None:
            roof.append(r.parapet_height_m.basis)
    ops = [x for o in twin.openings for x in (o.width_m.basis, o.height_m.basis)]
    sel = twin.assemblies
    wall_sel = weakest_basis([sel.basis.get("external_wall", Basis.ASSUMED)]
                             + [sel.basis.get(f"{bid}/external_wall", Basis.ASSUMED)
                                for bid, ov in sel.block_overrides.items() if "external_wall" in ov])
    walls = weakest_basis(plan, heights, roof)
    return {"plan": weakest_basis(plan), "gia": weakest_basis(plan, [wall_sel]), "walls": walls,
            "openings": weakest_basis(ops) if ops else Basis.UNKNOWN, "net_walls": weakest_basis([walls], ops),
            "roof": weakest_basis(plan, roof), "volume": weakest_basis(plan, heights, [wall_sel])}


#: (metric, GeometryMetrics field, unit, basis group of :func:`geometry_bases`, definition)
GEOMETRY_SUMMARY: tuple[tuple[str, str, str, str, str], ...] = (
    ("Footprint (ground-floor GEA)", "footprint_area_m2", "m2", "plan", "Ground-level footprint to external faces."),
    ("GEA", "gea_m2", "m2", "plan", "Gross external area: block footprints per storey."),
    ("GIA", "gia_m2", "m2", "gia",
     "Gross internal area: GEA minus external wall strips and half of each wall shared between blocks."),
    ("Heated GIA", "heated_gia_m2", "m2", "gia", "GIA of heated blocks (per-m2 allowances use it)."),
    ("Ground perimeter", "ground_perimeter_m", "m", "plan", "External perimeter at ground level."),
    ("External wall - gross", "external_wall_gross_m2", "m2", "walls",
     "FFL to wall plate plus gable / monopitch / parapet infill, before opening deductions."),
    ("Windows and glazed doors", "window_area_m2", "m2", "openings",
     "Glazed openings (windows, patio / balcony doors)."),
    ("External doors", "door_area_m2", "m2", "openings", "Opaque external doors."),
    ("Garage doors", "garage_door_area_m2", "m2", "openings", "Garage doors."),
    ("Openings - total", "opening_area_m2", "m2", "openings", "All openings deducted from external walls (once each)."),
    ("External wall - net", "external_wall_net_m2", "m2", "net_walls", "Gross external wall minus openings."),
    ("Separating walls", "separating_wall_area_m2", "m2", "walls",
     "Walls shared between blocks, counted once up to the lower plate."),
    ("Roof - plan area", "roof_plan_area_m2", "m2", "roof", "Plan area including external overhangs."),
    ("Roof - surface area", "roof_surface_area_m2", "m2", "roof", "Plan area / cos(pitch) (flat roofs: plan area)."),
    ("Roof - pitched surface", "pitched_roof_surface_area_m2", "m2", "roof", "Surface of pitched roofs."),
    ("Roof - flat area", "flat_roof_area_m2", "m2", "roof", "Area of flat roofs."),
    ("Ground floor (internal)", "ground_floor_area_m2", "m2", "gia", "GIA of storey 0 (slab measured internally)."),
    ("Upper floors (internal)", "intermediate_floor_area_m2", "m2", "gia", "GIA of upper storeys."),
    ("Top ceilings (internal)", "top_ceiling_area_m2", "m2", "gia", "Internal area under roofs (insulated ceiling)."),
    ("Heated volume", "heated_volume_m3", "m3", "volume", "Internal volume of heated blocks."),
)


def geometry_rows(metrics: GeometryMetrics, twin: Optional[BuildingTwin] = None
                  ) -> tuple[list[str], list[dict[str, Any]]]:
    """Columns and rows for ``geometry_summary.csv``: gross / net wall, glazing, door, roof and floor areas.

    Each row carries the weakest basis of the twin values it depends on (:func:`geometry_bases`; ``unknown``
    without a twin) and its definition.
    """
    bases = geometry_bases(twin) if twin is not None else {}
    cols = ["metric", "field", "value", "unit", "basis", "basis_label", "definition", "external_wall_thickness_m",
            "twin_id", "twin_version"]
    rows = []
    for name, field_name, unit, group, definition in GEOMETRY_SUMMARY:
        b = bases.get(group, Basis.UNKNOWN)
        rows.append({"metric": name, "field": field_name, "value": float(getattr(metrics, field_name)), "unit": unit,
                     "basis": b.value, "basis_label": BASIS_LABEL.get(b, str(b)), "definition": definition,
                     "external_wall_thickness_m": metrics.external_wall_thickness_m,
                     "twin_id": twin.twin_id if twin is not None else None,
                     "twin_version": twin.version if twin is not None else None})
    return cols, rows


def repeat_rows(results: Sequence[RepeatBuildResult]) -> tuple[list[str], list[dict[str, Any]]]:
    comps: list[str] = []
    for r in results:
        for row in r.rows:
            comps += [c for c in row.components if c not in comps]
    cols = ["scenario_id", "boundary", "currency", "n", "total_cost", "average_cost", "incremental_cost",
            "is_comparison_n"] + [f"component:{c}" for c in comps]
    rows = []
    for r in results:
        cmp = set(r.comparison_ns)
        for row in r.rows:
            d = {"scenario_id": r.scenario_id, "boundary": r.boundary, "currency": r.currency, "n": row.n,
                 "total_cost": row.total_cost, "average_cost": row.average_cost,
                 "incremental_cost": row.incremental_cost, "is_comparison_n": row.n in cmp}
            d.update({f"component:{k}": v for k, v in row.components.items()})
            rows.append(d)
    return cols, rows


def simulation_rows(sim: SimulationResult) -> tuple[list[str], list[dict[str, Any]]]:
    cols = ["scenario_id", "metric", "unit", "mean", "std", "p5", "p10", "p50", "p80", "p90", "p95", "min", "max",
            "n_samples", "seed", "method", "interval_type"]
    rows = []
    for m in sim.metrics:
        d = m.model_dump()
        d.update({"scenario_id": sim.scenario_id, "n_samples": sim.n_samples, "seed": sim.config.seed,
                  "method": sim.config.method, "interval_type": sim.interval_type})
        rows.append(d)
    return cols, rows


#: Basis of every scenario outcome's cost: it includes the assumed contingency layer and the scenario's
#: assembly overrides are applied as assumptions (actor ``scenario``), so it is never stronger than ASSUMED.
SCENARIO_COST_BASIS = Basis.ASSUMED


def comparison_rows(cmp: ScenarioComparison) -> tuple[list[str], list[dict[str, Any]]]:
    fields = list(ScenarioOutcome.model_fields)
    cols = fields + ([] if "basis" in fields else ["basis"])
    rows = []
    for o in cmp.outcomes:
        d = {n: getattr(o, n) for n in fields}
        if "key_assumptions" in d:
            d["key_assumptions"] = "; ".join(d["key_assumptions"])
        d.setdefault("basis", SCENARIO_COST_BASIS.value)
        rows.append(d)
    return cols, rows


# =============================================================================
# Manifest
# =============================================================================
class ExportedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: str
    #: POSIX path relative to the export directory.
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    description: str = ""


class ExportManifest(BaseModel):
    """Index of an export folder (written as ``manifest.json``, which is not listed in ``files``)."""

    model_config = ConfigDict(extra="forbid")

    manifest_version: int = 1
    project_id: str
    project_name: str
    created_at: datetime = Field(default_factory=utcnow)
    engine: dict[str, str] = Field(default_factory=dict)
    formats: list[str] = Field(default_factory=list)
    files: list[ExportedFile] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    information_level: str = EXPORT_INFORMATION_LEVEL
    #: {"id", "version", "hash"} of the exported twin (None when the project has no twin).
    twin: Optional[dict[str, Any]] = None
    #: Source images identified by content hash (originals are preserved by the ingest module).
    source_images: list[dict[str, Any]] = Field(default_factory=list)
    ifc: Optional[IfcExportReport] = None

    def file(self, path: str) -> ExportedFile:
        for f in self.files:
            if f.path == path:
                return f
        raise KeyError(path)

    def by_format(self, fmt: str) -> list[ExportedFile]:
        return [f for f in self.files if f.format == fmt]

    def verify(self, out_dir: Union[str, Path]) -> list[str]:
        """Re-hash every listed file; returns a list of problems (empty = all files intact)."""
        base = Path(out_dir)
        problems: list[str] = []
        for f in self.files:
            p = base / f.path
            try:
                data = p.read_bytes()
            except OSError as e:
                problems.append(f"{f.path}: cannot read ({e.strerror})")
                continue
            if len(data) != f.size_bytes:
                problems.append(f"{f.path}: size {len(data)} != {f.size_bytes}")
            if sha256_hex(data) != f.sha256:
                problems.append(f"{f.path}: sha256 mismatch")
        return problems


class _Out:
    """Validated, atomic writes inside one export directory."""

    def __init__(self, out_dir: Union[str, Path]):
        base = Path(out_dir)
        base.mkdir(parents=True, exist_ok=True)
        self.base = base
        self.root = base.resolve()
        self.files: list[ExportedFile] = []

    def target(self, name: str) -> Path:
        if not _SAFE_NAME.match(name) or ".." in name:
            raise ValueError(f"unsafe export file name {name!r}")
        p = self.base / name
        if p.is_symlink():
            raise ValueError(f"refusing to write through symlink {name!r}")
        if p.resolve().parent != self.root:
            raise ValueError(f"export path {name!r} escapes the export directory")
        return p

    def write(self, name: str, data: bytes, fmt: str, description: str, *, record: bool = True) -> Optional[
            ExportedFile]:
        p = self.target(name)
        fd, tmp = tempfile.mkstemp(prefix=".export-", dir=str(self.root))
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, p)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        if not record:
            return None
        ef = ExportedFile(format=fmt, path=name, sha256=sha256_hex(data), size_bytes=len(data),
                          description=description)
        self.files.append(ef)
        return ef

    def record_existing(self, name: str, fmt: str, description: str) -> ExportedFile:
        data = self.target(name).read_bytes()
        ef = ExportedFile(format=fmt, path=name, sha256=sha256_hex(data), size_bytes=len(data),
                          description=description)
        self.files.append(ef)
        return ef


# =============================================================================
# Export
# =============================================================================
def _formats(formats: Union[str, Sequence[str]]) -> list[str]:
    seq = [formats] if isinstance(formats, str) else list(formats)
    out: list[str] = []
    for f in seq:
        key = str(f).strip().lower()
        if key not in FORMATS:
            raise ValueError(f"unknown export format {f!r}; expected any of {FORMATS}")
        if key not in out:
            out.append(key)
    return out


def _library(project: Project, library: Optional[AssemblyLibrary], notes: list[str]) -> AssemblyLibrary:
    if library is not None:
        return library
    if project.library.assemblies:
        return project.library
    from ..quantities.library import default_library

    notes.append("Project library is empty; the bundled illustrative assembly library was used for wall "
                 "thicknesses and quantities.")
    return default_library()


def _metrics_for(twin: BuildingTwin, boq: Optional[BillOfQuantities], lib: AssemblyLibrary) -> GeometryMetrics:
    if boq is not None and boq.twin_id == twin.twin_id and boq.twin_version == twin.version and boq.geometry.pieces:
        return boq.geometry
    from ..geometry.metrics import compute_geometry_metrics
    from ..quantities.takeoff import wall_thicknesses

    t_ext, t_sep = wall_thicknesses(twin, lib)
    return compute_geometry_metrics(twin, t_ext, t_sep)


def _image_refs(project: Project) -> list[dict[str, Any]]:
    return [{"image_id": im.image_id, "sha256": im.sha256, "filename": im.original_filename,
             "media_type": im.media_type, "kind": im.kind.value, "view": im.view.value,
             "size_bytes": im.size_bytes, "width_px": im.width_px, "height_px": im.height_px}
            for im in project.images]


def _json_bytes(obj: Any) -> bytes:
    return (json.dumps(_finite(_jsonable(obj)), indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def concept_reference_warning(project: Project) -> Optional[str]:
    """Warning when every image with facade measurements (else every image) is a concept reference."""
    from ..core.models import CONCEPT_KINDS

    if not project.images:
        return None
    kinds = {a.image_id: a.kind for a in project.images}
    flagged = set(getattr(project.analysis, "concept_image_ids", None) or []) if project.analysis else set()
    fac = {f.image_id for f in (project.analysis.facades if project.analysis else [])} & set(kinds)
    pool = fac or set(kinds)
    if all(kinds[i] in CONCEPT_KINDS or i in flagged for i in pool):
        return ("Concept reference only: every image the twin was measured from is an AI concept / rendering / "
                "sketch. The geometry, quantities and costs are indicative for a concept and do not describe an "
                "existing or measured building.")
    return None


def _readme(manifest: ExportManifest, fictional: bool) -> bytes:
    lines = [
        f"{ENGINE_NAME} export - {manifest.project_name} ({manifest.project_id})",
        f"Created {manifest.created_at.isoformat()} with {manifest.engine.get('engine', '')}",
        "",
        "INFORMATION LEVEL",
        manifest.information_level,
        "",
        "PROVENANCE",
        PROVENANCE_NOTE,
        "",
    ]
    if fictional:
        lines += ["PRICES", "Cost figures use FICTIONAL demonstration rates. They are not market prices, quotes or "
                  "tender figures.", ""]
    lines += ["3D MODEL", GLB_NOTICE, ""]
    if manifest.ifc is not None:
        lines += ["IFC", manifest.ifc.information_level, "Omissions:"] + [f"  - {o}" for o in manifest.ifc.omissions]
        lines.append("")
    if manifest.source_images:
        lines.append("SOURCE IMAGES (by sha256)")
        lines += [f"  {im['sha256']}  {im['image_id']}" for im in manifest.source_images]
        lines.append("")
    if manifest.warnings:
        lines.append("WARNINGS")
        lines += [f"  - {w}" for w in manifest.warnings]
        lines.append("")
    lines.append("FILES (sha256 in manifest.json)")
    lines += [f"  {f.path:<24} {f.format:<5} {f.description}" for f in manifest.files]
    lines.append("")
    text = "\n".join(re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", ln) for ln in lines)
    return text.encode("utf-8")


def export_project(project: Project, out_dir: Union[str, Path], *, boq: Optional[BillOfQuantities] = None,
                   estimate: Optional[CostEstimate] = None, simulation: Optional[SimulationResult] = None,
                   repeat: Union[RepeatBuildResult, Sequence[RepeatBuildResult], None] = None,
                   comparison: Optional[ScenarioComparison] = None,
                   formats: Union[str, Sequence[str]] = FORMATS,
                   library: Optional[AssemblyLibrary] = None,
                   rate_book: Optional[RateBook] = None) -> ExportManifest:
    """Export ``project`` (and optional results) into ``out_dir`` (see module docstring).

    ``formats`` is any subset of ``("json", "glb", "csv", "ifc")``; unknown names raise
    ``ValueError``.  ``library`` (default: the project's library, else the bundled one) gives wall
    thicknesses / assembly names; ``rate_book`` (default ``project.rate_book``) is used to label
    each cost line's rate source.  Returns the :class:`ExportManifest`, also written as
    ``manifest.json``.  Missing inputs (no twin, no estimate, no ifcopenshell) become warnings.
    """
    if not isinstance(project, Project):
        raise TypeError("project must be a housebuilder_vision Project")
    fmts = _formats(formats)
    out = _Out(out_dir)
    warnings: list[str] = []
    notes: list[str] = []
    twin = project.twin
    repeats: list[RepeatBuildResult] = ([repeat] if isinstance(repeat, RepeatBuildResult)
                                        else list(repeat or []))
    book = rate_book if rate_book is not None else project.rate_book
    rates = {r.rate_id: r for r in book.rates}
    lib = _library(project, library, notes) if twin is not None else (library or project.library)

    thash: Optional[str] = None
    if twin is not None:
        from ..twin.builder import twin_hash

        thash = twin_hash(twin)
    manifest = ExportManifest(
        project_id=project.project_id, project_name=project.name, engine=engine_versions(), formats=fmts,
        twin=({"id": twin.twin_id, "version": twin.version, "hash": thash} if twin is not None else None),
        source_images=[{k: im[k] for k in ("image_id", "sha256", "filename")} for im in _image_refs(project)],
        information_level=(f"{EXPORT_INFORMATION_LEVEL} Twin: {twin.information_level}"
                           if twin is not None and twin.information_level != _DEFAULT_TWIN_LEVEL
                           else EXPORT_INFORMATION_LEVEL),
    )

    # ---- bill of quantities (supplied or computed) and geometry
    boq_source = "supplied by caller" if boq is not None else None
    if boq is None and twin is not None and ("csv" in fmts or "json" in fmts):
        from ..quantities.takeoff import calculate_quantities

        boq = calculate_quantities(twin, lib, assumptions=project.assumptions)
        boq_source = "computed at export from project.twin and the assembly library"
        notes.append("Bill of quantities computed at export time from the project twin (none supplied).")
    if boq is not None and twin is not None and (boq.twin_id != twin.twin_id or boq.twin_version != twin.version):
        warnings.append(f"Bill of quantities is for twin {boq.twin_id} v{boq.twin_version} but the project twin is "
                        f"{twin.twin_id} v{twin.version}; exported as supplied.")
    fictional = bool(estimate is not None and _estimate_uses_fictional(estimate, rates))
    if fictional:
        notes.append("Cost estimate uses FICTIONAL demonstration rates - not market prices.")
    concept = concept_reference_warning(project)
    if concept:
        warnings.append(concept)
    if estimate is not None:
        incomplete = [b for b in estimate.boundaries if b.unresolved_count]
        if incomplete:
            warnings.append(f"Cost estimate is INCOMPLETE: {len(estimate.unresolved_items)} unresolved item(s) are not "
                            "priced, so the boundary amounts are lower bounds (see cost_boundaries.csv).")

    metrics: Optional[GeometryMetrics] = None
    if twin is not None and ("ifc" in fmts):
        try:
            metrics = _metrics_for(twin, boq, lib)
        except ValueError as e:  # GeometryError / unknown assembly
            warnings.append(f"IFC not written: geometry could not be computed ({e}).")

    # ---- JSON
    if "json" in fmts:
        project_bytes = (project.model_dump_json(indent=2) + "\n").encode("utf-8")
        out.write("project.json", project_bytes, "json",
                  "Complete model state (Project.model_dump_json); reload with Project.model_validate_json.")
        counts = provenance_counts(twin) if twin is not None else {}
        results = {
            "format": "housebuilder-vision-results",
            "format_version": 1,
            "engine": manifest.engine,
            "exported_at": manifest.created_at.isoformat(),
            "project": {"project_id": project.project_id, "name": project.name,
                        "schema_version": project.schema_version, "updated_at": project.updated_at.isoformat()},
            "project_json_sha256": sha256_hex(project_bytes),
            "project_state_sha256": canonical_sha256(project),
            "twin": None if twin is None else {
                "twin_id": twin.twin_id, "version": twin.version, "hash": thash,
                "calibration_method": twin.calibration_method, "source_hypothesis_id": twin.source_hypothesis_id,
                "information_level": twin.information_level},
            "source_images": _image_refs(project),
            "seeds": {"project_simulation_config": project.simulation_config.seed,
                      "simulation_result": simulation.config.seed if simulation is not None else None},
            "information_level": manifest.information_level,
            "provenance": {"note": PROVENANCE_NOTE, "parameter_counts": counts,
                           "basis_labels": {b.value: BASIS_LABEL[b] for b in Basis}},
            "pricing": {"rate_book": book.name, "uses_fictional_rates": fictional,
                        "note": ("Prices include FICTIONAL demonstration rates - not market prices." if fictional
                                 else "Prices are only as reliable as the rate book used.")},
            "geometry_notice": GLB_NOTICE,
            "results": {
                "bill_of_quantities": boq, "boq_source": boq_source, "cost_estimate": estimate,
                "simulation": simulation, "repeat_build": repeats, "scenario_comparison": comparison,
            },
            "reproduce": ("Reload project.json with Project.model_validate_json, match source images by sha256, "
                          "and re-run the engine functions with the recorded seeds and engine versions."),
        }
        out.write("results.json", _json_bytes(results), "json",
                  "Result objects (BoQ, costs, simulation, repeat-build, comparison) with engine versions, image "
                  "sha256s, twin hash, seeds and provenance note.")

    # ---- GLB
    if "glb" in fmts:
        if twin is None:
            warnings.append("GLB not written: the project has no twin.")
        else:
            from ..twin.mesh import build_mesh, scene_for_gltf

            scene = scene_for_gltf(build_mesh(twin))
            warnings += [f"mesh: {w}" for w in scene.metadata.get("warnings", []) or []]
            scene.metadata.update({"notice": GLB_NOTICE, "twin_hash": thash, "engine": manifest.engine["engine"],
                                   "project_id": project.project_id})
            if not scene.geometry:
                warnings.append("GLB not written: the twin has no drawable geometry.")
            else:
                data = scene.export(file_type="glb")
                out.write("twin.glb", data, "glb", "Visual geometry only (glTF 2.0 binary, y-up, metres): walls, "
                          "roofs and openings as named nodes. Not BIM, not measured, not for construction.")

    # ---- CSV
    if "csv" in fmts:
        if boq is not None:
            out.write("quantities.csv", csv_bytes(*quantity_rows(boq)), "csv",
                      "Bill of quantities: one row per line with every field (status, basis, trace flattened).")
        else:
            warnings.append("quantities.csv not written: no bill of quantities (project has no twin).")
        if estimate is not None:
            out.write("costs.csv", csv_bytes(*cost_rows(estimate, book)), "csv",
                      "Cost lines by layer with rate source type" + ("; FICTIONAL demo rates labelled."
                                                                     if fictional else "."))
            out.write("cost_boundaries.csv", csv_bytes(*boundary_rows(estimate, book)), "csv",
                      "Cumulative cost boundaries with basis, completeness, definitions and exclusions.")
        else:
            warnings.append("costs.csv / cost_boundaries.csv not written: no cost estimate supplied.")
        if boq is not None:
            out.write("geometry_summary.csv", csv_bytes(*geometry_rows(boq.geometry, twin)), "csv",
                      "Geometry summary: gross / net external wall, glazing, door, garage-door, separating-wall, roof "
                      "and floor areas with the basis of the values they depend on.")
        if repeats:
            out.write("repeat_build.csv", csv_bytes(*repeat_rows(repeats)), "csv",
                      "Repeat-build economics: total C(n), average C(n)/n and incremental cost per n.")
        if simulation is not None:
            out.write("simulation_summary.csv", csv_bytes(*simulation_rows(simulation)), "csv",
                      "Uncertainty simulation percentiles (assumed scenario ranges, not calibrated).")
        if comparison is not None:
            out.write("scenario_comparison.csv", csv_bytes(*comparison_rows(comparison)), "csv",
                      "Build scenario comparison outcomes.")

    # ---- IFC
    if "ifc" in fmts:
        if twin is None:
            warnings.append("IFC not written: the project has no twin.")
        elif metrics is not None:
            from .ifc_adapter import export_ifc

            target = out.target("twin.ifc")
            try:
                report = export_ifc(twin, metrics, target, library=lib)
            except AdapterUnavailable as e:
                warnings.append(f"IFC not written: {e}" if "ifcopenshell" in str(e) else
                                f"IFC not written: {IFC_INSTALL_HINT} ({e})")
            except ValueError as e:  # GeometryError and invalid inputs
                warnings.append(f"IFC not written: {e}")
            else:
                report.path = "twin.ifc"
                manifest.ifc = report
                warnings += [f"ifc: {w}" for w in report.warnings]
                out.record_existing("twin.ifc", "ifc", f"{report.information_level}. IFC4, metres; omissions "
                                    "listed in Pset_AureomInformationLevel and the manifest.")

    manifest.warnings = warnings
    manifest.notes = notes
    manifest.files = list(out.files)
    out.write("README.txt", _readme(manifest, fictional), "txt",
              "Plain-text summary: information level, provenance, pricing and file list.")
    manifest.files = list(out.files)
    out.write("manifest.json", (manifest.model_dump_json(indent=2) + "\n").encode("utf-8"), "json", "",
              record=False)
    return manifest


__all__ = [
    "CSV_INJECTION_PREFIXES",
    "EXPORT_INFORMATION_LEVEL",
    "FICTIONAL_LABEL",
    "FORMATS",
    "GLB_NOTICE",
    "PROVENANCE_NOTE",
    "ExportManifest",
    "ExportedFile",
    "GEOMETRY_SUMMARY",
    "SCENARIO_COST_BASIS",
    "boundary_rows",
    "concept_reference_warning",
    "geometry_bases",
    "geometry_rows",
    "rate_book_rows",
    "canonical_json",
    "canonical_sha256",
    "cost_rows",
    "csv_bytes",
    "engine_version",
    "engine_versions",
    "export_project",
    "is_fictional_rate",
    "quantity_rows",
    "sanitize_cell",
    "sha256_hex",
]
