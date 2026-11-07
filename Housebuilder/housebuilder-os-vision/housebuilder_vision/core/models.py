"""Validated data models (the shared contract between all engine modules).

Coordinate conventions
----------------------
Plan coordinates are metres.  ``x`` runs along the visible frontage (left to
right as seen from the front), ``y`` runs from the front facade towards the
rear, ``z`` is up with ``z = 0`` at external ground level.

Block sides: FRONT is the face at ``y = origin_y`` (facing -y), REAR at
``y = origin_y + depth`` (facing +y), LEFT at ``x = origin_x`` (facing -x),
RIGHT at ``x = origin_x + width`` (facing +x).

Opening ``offset_m`` is measured along the wall from the wall's left end *as
seen by a person standing outside facing that wall*:
FRONT -> from min x; REAR -> from max x; LEFT -> from max y; RIGHT -> from min y.

Heights: finished ground-floor level (FFL) is ``ground_floor_level`` above
ground; the wall plate (eaves) is ``FFL + storeys * floor_to_floor``.
Superstructure external wall areas are measured from FFL to wall plate (plus
gable/monopitch infill above the plate).  Masonry below FFL is substructure.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .provenance import Basis, EditRecord, TrackedValue, utcnow
from .settings import AssumptionLibrary, ProjectSettings

SCHEMA_VERSION = "1.0.0"
_ID_PATTERN = r"^[A-Za-z0-9_.:\-]{1,80}$"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


# =============================================================================
# Images and image interpretation
# =============================================================================
class ImageKind(str, Enum):
    PHOTOGRAPH = "photograph"
    RENDERING = "architectural_rendering"
    AI_CONCEPT = "ai_generated_concept"
    SKETCH = "sketch"
    FLOOR_PLAN = "floor_plan"
    ELEVATION_DRAWING = "elevation_drawing"
    UNKNOWN = "unknown"


#: Kinds whose geometry may be internally inconsistent (concept references).
CONCEPT_KINDS = {ImageKind.AI_CONCEPT, ImageKind.RENDERING, ImageKind.SKETCH}


class ViewDirection(str, Enum):
    FRONT = "front"
    REAR = "rear"
    LEFT = "left"
    RIGHT = "right"
    FRONT_LEFT_OBLIQUE = "front_left_oblique"
    FRONT_RIGHT_OBLIQUE = "front_right_oblique"
    PLAN = "plan"
    AERIAL = "aerial"
    UNKNOWN = "unknown"


class ImageAsset(_Model):
    """A validated, content-addressed source image (originals are preserved)."""

    image_id: str = Field(pattern=_ID_PATTERN)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    original_filename: str
    media_type: str
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    size_bytes: int = Field(ge=0)
    kind: ImageKind = ImageKind.UNKNOWN
    view: ViewDirection = ViewDirection.UNKNOWN
    stored_path: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=utcnow)
    exif: dict[str, str] = Field(default_factory=dict)
    notes: str = ""

    @property
    def is_concept_reference(self) -> bool:
        return self.kind in CONCEPT_KINDS


class FeatureType(str, Enum):
    BUILDING_OUTLINE = "building_outline"
    FACADE = "facade"
    ROOF = "roof"
    WALL = "wall"
    WINDOW = "window"
    DOOR = "door"
    GARAGE_DOOR = "garage_door"
    BALCONY = "balcony"
    STOREY_LINE = "storey_line"
    EAVES_LINE = "eaves_line"
    RIDGE_LINE = "ridge_line"
    GROUND_LINE = "ground_line"
    CHIMNEY = "chimney"
    GARAGE = "garage"
    EXTENSION = "extension"
    FINISH_REGION = "finish_region"
    LINE_SEGMENT = "line_segment"
    DIMENSION = "dimension"
    ROOM = "room"
    OTHER = "other"


class DetectedFeature(_Model):
    """One piece of image evidence with coordinates, method and uncertainty."""

    feature_id: str = Field(pattern=_ID_PATTERN)
    image_id: str
    feature_type: FeatureType
    label: str = ""
    bbox: Optional[tuple[float, float, float, float]] = None  # x0, y0, x1, y1 (px)
    polygon: Optional[list[tuple[float, float]]] = None  # px
    line: Optional[tuple[float, float, float, float]] = None  # x0, y0, x1, y1 (px)
    basis: Basis = Basis.OBSERVED
    method: str = "unknown"
    method_version: str = "0"
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    pixel_uncertainty: float = Field(default=3.0, ge=0.0)
    #: Free attributes, e.g. {"roof_form": "gable", "appearance": "brick-like", "storey": 1}
    attributes: dict[str, Any] = Field(default_factory=dict)
    evidence: str = ""
    active: bool = True
    history: list[EditRecord] = Field(default_factory=list)

    @field_validator("bbox")
    @classmethod
    def _bbox_ok(cls, v):
        if v is not None and (v[2] < v[0] or v[3] < v[1]):
            raise ValueError("bbox must be (x0, y0, x1, y1) with x1>=x0 and y1>=y0")
        return v

    def width_px(self) -> Optional[float]:
        if self.bbox:
            return self.bbox[2] - self.bbox[0]
        if self.line:
            return abs(self.line[2] - self.line[0])
        return None

    def height_px(self) -> Optional[float]:
        if self.bbox:
            return self.bbox[3] - self.bbox[1]
        if self.line:
            return abs(self.line[3] - self.line[1])
        return None


class VanishingPoint(_Model):
    x: Optional[float] = None
    y: Optional[float] = None
    direction: Literal["horizontal_a", "horizontal_b", "vertical"]
    finite: bool = True
    support: int = 0  # number of supporting line segments


class PerspectiveEstimate(_Model):
    method: str
    method_version: str = "0"
    vanishing_points: list[VanishingPoint] = Field(default_factory=list)
    horizon_y: Optional[float] = None
    vertical_tilt_deg: Optional[float] = None
    #: Angle between the principal facade and the image plane (0 = fronto-parallel).
    facade_obliqueness_deg: Optional[float] = None
    is_near_fronto_parallel: Optional[bool] = None
    #: Fractional dimension uncertainty attributable to perspective.
    foreshortening_uncertainty: float = 0.05
    notes: list[str] = Field(default_factory=list)


class DepthEstimate(_Model):
    method: str
    method_version: str = "0"
    available: bool = False
    #: Relative depth extent of the building region (dimensionless, model-specific).
    relative_depth_range: Optional[tuple[float, float]] = None
    notes: list[str] = Field(default_factory=list)


class VLMExtraction(_Model):
    """Structured output of a vision-language model.  Always INFERRED, untrusted."""

    method: str
    model_id: str
    storeys: Optional[int] = Field(default=None, ge=1, le=10)
    roof_form: Optional[str] = None
    has_garage: Optional[bool] = None
    has_balcony: Optional[bool] = None
    has_extension: Optional[bool] = None
    likely_external_finishes: list[str] = Field(default_factory=list)
    window_count_visible: Optional[int] = Field(default=None, ge=0, le=500)
    door_count_visible: Optional[int] = Field(default=None, ge=0, le=100)
    image_appears_ai_generated: Optional[bool] = None
    geometry_inconsistencies: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    raw_response_sha256: Optional[str] = None


class AdapterRun(_Model):
    adapter: str
    version: str = "0"
    capability: str
    status: Literal["ok", "unavailable", "skipped", "error"]
    message: str = ""
    duration_ms: Optional[float] = None


class ImageAnalysis(_Model):
    image_id: str
    features: list[DetectedFeature] = Field(default_factory=list)
    perspective: Optional[PerspectiveEstimate] = None
    depth: Optional[DepthEstimate] = None
    vlm: Optional[VLMExtraction] = None
    adapters: list[AdapterRun] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ObservedOpening(_Model):
    feature_id: str
    kind: Literal["window", "door", "garage_door", "patio_door", "balcony_door"]
    bbox_px: tuple[float, float, float, float]
    storey_index: Optional[int] = None
    #: Which visible block (in hypothesis terms) the opening belongs to.
    block_hint: Optional[str] = None


class ObservedFinish(_Model):
    element: Literal["walls", "roof", "garage_door", "windows", "doors", "other"]
    appearance: str  # e.g. "red brick-like", "dark grey tile-like"
    basis: Basis = Basis.INFERRED
    feature_ids: list[str] = Field(default_factory=list)
    caveat: str = "Appearance only - does not establish the structural material or build-up."


class FacadeObservation(_Model):
    """Pixel-space summary of one elevation-like view.

    ``block_hint`` groups measurements per visible volume (e.g. "main", "garage").
    All lengths are pixels; conversion to metres happens in calibration.
    """

    image_id: str
    view: ViewDirection
    block_hint: str = "main"
    storeys: TrackedValue
    width_px: TrackedValue
    eaves_height_px: TrackedValue  # ground line to wall plate
    ridge_height_px: TrackedValue  # ground line to ridge (or roof top)
    ground_y_px: Optional[float] = None
    left_x_px: Optional[float] = None
    roof_form: Optional[str] = None
    roof_form_basis: Basis = Basis.UNKNOWN
    #: Pitch observed directly only when a gable/verge is seen in elevation.
    apparent_pitch_deg: Optional[TrackedValue] = None
    ridge_axis_hint: Optional[Literal["parallel_to_view", "perpendicular_to_view"]] = None
    openings: list[ObservedOpening] = Field(default_factory=list)
    finishes: list[ObservedFinish] = Field(default_factory=list)
    feature_ids: list[str] = Field(default_factory=list)


class MultiViewResult(_Model):
    method: str
    method_version: str = "0"
    image_ids: list[str]
    #: e.g. {"main.depth_px_in_side_view": TrackedValue, ...}
    linked_measurements: dict[str, TrackedValue] = Field(default_factory=dict)
    #: scale ratio between images derived from shared features: {"img_b": factor relative to primary}
    relative_scales: dict[str, TrackedValue] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class AnalysisResult(_Model):
    images: list[ImageAsset]
    analyses: list[ImageAnalysis]
    facades: list[FacadeObservation] = Field(default_factory=list)
    multiview: Optional[MultiViewResult] = None
    primary_image_id: Optional[str] = None
    #: Items that cannot be established from appearance and are carried as unknowns.
    unknowns: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)

    def all_features(self) -> list[DetectedFeature]:
        return [f for a in self.analyses for f in a.features if f.active]


# =============================================================================
# Scale calibration and geometry hypotheses
# =============================================================================
class ReferenceMeasurement(_Model):
    image_id: str
    feature_id: Optional[str] = None
    #: Pixel endpoints; if omitted the feature's bbox width is used.
    p0: Optional[tuple[float, float]] = None
    p1: Optional[tuple[float, float]] = None
    real_length: float = Field(gt=0)
    unit: str = "m"
    description: str = ""
    source: str = "user"
    #: Measurement tolerance of the real length, in ``unit``.
    tolerance: float = 0.02


class ScaleCue(_Model):
    name: str
    feature_id: Optional[str] = None
    pixels: float
    assumed_real: TrackedValue
    implied_m_per_px: TrackedValue


class ScaleCalibration(_Model):
    image_id: str
    method: Literal["reference_measurement", "prior_cues", "dimensioned_plan", "none"]
    metres_per_pixel: TrackedValue
    reference: Optional[ReferenceMeasurement] = None
    cues: list[ScaleCue] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Side(str, Enum):
    FRONT = "front"
    REAR = "rear"
    LEFT = "left"
    RIGHT = "right"


class RoofForm(str, Enum):
    GABLE = "gable"
    HIP = "hip"
    FLAT = "flat"
    MONOPITCH = "monopitch"


class BlockRole(str, Enum):
    MAIN = "main"
    WING = "wing"
    EXTENSION = "extension"
    GARAGE = "garage"


class RoofSpec(_Model):
    form: RoofForm = RoofForm.GABLE
    pitch_deg: TrackedValue
    #: Ridge parallel to plan x ("x") or plan y ("y").  Ignored for flat roofs.
    ridge_axis: Literal["x", "y"] = "x"
    eaves_overhang_m: TrackedValue
    verge_overhang_m: TrackedValue
    #: Monopitch only: which side is high.
    high_side: Optional[Side] = None
    #: Flat roof only: parapet height above wall plate (0 = none).
    parapet_height_m: Optional[TrackedValue] = None


class Block(_Model):
    """A rectangular building volume.  Footprints are unions of blocks."""

    block_id: str = Field(pattern=_ID_PATTERN)
    name: str = ""
    role: BlockRole = BlockRole.MAIN
    origin_x: TrackedValue
    origin_y: TrackedValue
    width: TrackedValue  # extent along x (external face to external face)
    depth: TrackedValue  # extent along y
    storeys: TrackedValue  # unit "storeys"
    floor_to_floor: TrackedValue
    ground_floor_level: TrackedValue
    roof: RoofSpec
    heated: bool = True
    visible_sides: list[Side] = Field(default_factory=list)
    notes: str = ""


class OpeningKind(str, Enum):
    WINDOW = "window"
    DOOR = "door"
    PATIO_DOOR = "patio_door"
    GARAGE_DOOR = "garage_door"
    BALCONY_DOOR = "balcony_door"


GLAZED_OPENINGS = {OpeningKind.WINDOW, OpeningKind.PATIO_DOOR, OpeningKind.BALCONY_DOOR}


class Opening(_Model):
    opening_id: str = Field(pattern=_ID_PATTERN)
    block_id: str
    side: Side
    kind: OpeningKind
    storey: int = Field(default=0, ge=0)
    offset_m: TrackedValue  # from wall's left end as seen from outside (to opening's left edge)
    width_m: TrackedValue
    height_m: TrackedValue
    sill_m: TrackedValue  # above the storey's floor level
    feature_id: Optional[str] = None
    #: Set when generated by a hidden-side rule rather than observed.
    hidden_side_rule: Optional[str] = None
    assembly_id: Optional[str] = None  # override of the default window/door assembly


class HiddenSideAssumptions(_Model):
    rear_glazing_ratio: TrackedValue
    side_glazing_ratio: TrackedValue
    rear_door_count: int = 1
    typical_window_width_m: float = 1.2
    typical_window_height_m: float = 1.2
    typical_window_sill_m: float = 0.9
    notes: str = "Hidden facades are filled by rule; replace with observed openings when evidence exists."
    #: (additive) Block sides ``"<block_id>:<side>"`` whose openings a person has specified
    #: (added / edited / deleted); hidden-side rules no longer fill them.
    specified_sides: list[str] = Field(default_factory=list)


class GeometryHypothesis(_Model):
    hypothesis_id: str = Field(pattern=_ID_PATTERN)
    name: str
    description: str = ""
    #: Subjective prior weight (not a probability calibrated against data).
    plausibility: float = Field(default=0.5, ge=0.0, le=1.0)
    blocks: list[Block]
    openings: list[Opening] = Field(default_factory=list)
    hidden: HiddenSideAssumptions
    evidence_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    calibration_method: str = "none"


# =============================================================================
# Materials and construction assemblies
# =============================================================================
class ElementType(str, Enum):
    EXTERNAL_WALL = "external_wall"
    SEPARATING_WALL = "separating_wall"  # wall shared between blocks
    INTERNAL_PARTITION = "internal_partition"
    GROUND_FLOOR = "ground_floor"
    INTERMEDIATE_FLOOR = "intermediate_floor"
    PITCHED_ROOF = "pitched_roof"
    FLAT_ROOF = "flat_roof"
    WINDOW = "window"
    EXTERNAL_DOOR = "external_door"
    GARAGE_DOOR = "garage_door"


class LayerRole(str, Enum):
    EXTERNAL_FINISH = "external_finish"
    CLADDING = "cladding"
    CAVITY = "cavity"
    INSULATION = "insulation"
    STRUCTURE = "structure"
    SHEATHING = "sheathing"
    MEMBRANE = "membrane"
    BATTENS = "battens"
    SERVICE_VOID = "service_void"
    INTERNAL_FINISH = "internal_finish"
    ROOF_COVERING = "roof_covering"
    SCREED = "screed"
    SLAB = "slab"
    FIXINGS = "fixings"
    UNIT = "unit"  # whole window / door units


class MaterialSpec(_Model):
    material_id: str = Field(pattern=_ID_PATTERN)
    name: str
    category: str = ""
    #: Unit in which the material is measured when installed (m2, m3, m, nr, kg).
    installed_unit: str
    #: Unit in which it is bought (sheet, pack, m3, nr, ...).
    purchase_unit: str
    #: purchase units per installed unit (e.g. 1/2.88 sheets per m2 of 2.88 m2 boards).
    purchase_per_installed: float = Field(default=1.0, gt=0)
    #: Packaging increment in purchase units (e.g. pack of 500 bricks -> 500).
    pack_size: float = Field(default=1.0, gt=0)
    pack_description: str = ""
    cutting_loss_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    waste_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    density_kg_m3: Optional[float] = None
    conductivity_w_mk: Optional[float] = None
    #: Mass of one purchase unit (kg) for logistics/carbon where density is not meaningful.
    mass_per_purchase_unit_kg: Optional[float] = None
    #: Bulk volume of one purchase unit (m3) for storage / vehicle loading.
    volume_per_purchase_unit_m3: Optional[float] = None
    #: Illustrative A1-A3 factor (kgCO2e per kg).  Not a certified EPD value.
    carbon_kgco2e_per_kg: Optional[float] = None
    carbon_source: str = "illustrative placeholder"
    lead_time_weeks: Optional[TrackedValue] = None
    delivery_category: str = "general"
    notes: str = ""


class LayerBridging(_Model):
    """Repeating thermal bridge within a layer (e.g. timber studs in insulation)."""

    material_id: str
    fraction: float = Field(ge=0.0, le=1.0)


class AssemblyLayer(_Model):
    name: str
    material_id: str
    role: LayerRole
    thickness_m: float = Field(default=0.0, ge=0.0)
    #: How the installed quantity is derived from the element measure:
    #:   "area"     installed (m2)  = element_area * factor
    #:   "volume"   installed (m3)  = element_area * thickness * factor
    #:   "per_area" installed (unit)= element_area * factor   (factor = count/lm/kg per m2)
    #:   "per_length" installed     = element_length * factor (e.g. lintels per m of opening)
    #:   "per_item" installed (nr)  = element_count * factor
    quantity_rule: Literal["area", "volume", "per_area", "per_length", "per_item"] = "area"
    #: Which geometric measure of the element the rule applies to.  See
    #: ``housebuilder_vision.quantities.measures.MEASURES`` for the allowed names per
    #: element, e.g. "element_area" (net wall / floor / roof area), "ceiling_area",
    #: "roof_plan", "ridge_length", "eaves_length", "verge_length", "hip_length",
    #: "opening_head_length", "opening_reveal_length", "opening_sill_length",
    #: "opening_count", "perimeter".
    measure: str = "element_area"
    factor: float = Field(default=1.0, ge=0.0)
    factor_note: str = ""
    bridging: Optional[LayerBridging] = None
    in_thermal_calc: bool = True
    #: Labour hours per installed unit of this layer, and trade.
    labour_hours_per_unit: float = Field(default=0.0, ge=0.0)
    trade: str = "general"
    #: Indicative allowance rather than a measured layer (e.g. structural timber kg/m2).
    is_allowance: bool = False


class Assembly(_Model):
    assembly_id: str = Field(pattern=_ID_PATTERN)
    name: str
    element: ElementType
    structural_system: str = "unspecified"
    layers: list[AssemblyLayer] = Field(default_factory=list)
    description: str = ""
    information_level: str = "Generic indicative build-up for comparison; not a specification or design."
    rsi: float = 0.13
    rse: float = 0.04
    #: Declared/assumed U-value for units (windows/doors); layers ignored for U.
    u_value_override: Optional[float] = None
    #: For WINDOW/EXTERNAL_DOOR/GARAGE_DOOR: whether layers are per m2 of opening or per item.
    notes: str = ""

    @property
    def total_thickness_m(self) -> float:
        return float(sum(l.thickness_m for l in self.layers))


class FoundationKind(str, Enum):
    STRIP = "strip"
    TRENCH_FILL = "trench_fill"
    RAFT = "raft"
    PILED_ALLOWANCE = "piled_allowance"


class FoundationOption(_Model):
    option_id: str = Field(pattern=_ID_PATTERN)
    name: str
    kind: FoundationKind
    trench_width_m: TrackedValue
    trench_depth_m: TrackedValue
    #: Concrete fill depth in the trench (trench fill = most of trench depth).
    concrete_depth_m: TrackedValue
    #: Raft slab thickness / thickened edge (raft only).
    raft_thickness_m: Optional[TrackedValue] = None
    #: Piled: indicative piles per metre of loadbearing wall (allowance only).
    piles_per_m: Optional[TrackedValue] = None
    pile_length_m: Optional[TrackedValue] = None
    #: Internal loadbearing wall length as a fraction of external perimeter (allowance).
    internal_loadbearing_fraction: TrackedValue
    suitable_ground: list[str] = Field(default_factory=list)
    concrete_material_id: str = "concrete_c25"
    notes: str = "Indicative option for costing only. Requires site investigation and engineer's design."


class AllowanceRule(_Model):
    """A labelled allowance for something the model cannot measure."""

    allowance_id: str = Field(pattern=_ID_PATTERN)
    element: str  # e.g. "5 Services"
    description: str
    cost_key: str
    unit: str
    #: ``per_m2_finishable`` (additive): m2 of internally finished wall + ceiling surface
    #: measured by the quantity take-off (used e.g. for decoration).
    basis_measure: Literal["per_dwelling", "per_m2_gia", "per_m2_gea", "per_storey", "per_bathroom",
                           "per_m2_finishable"]
    quantity_per: TrackedValue
    trade: str = "services"
    labour_hours_per_unit: float = 0.0
    notes: str = ""
    #: Optional material the allowance quantity is made of (e.g. structural steel in kg),
    #: so carbon / logistics can use it.  Costing still uses ``cost_key`` (``allow:...``).
    material_id: Optional[str] = None
    #: Apply only when the twin's tallest block has at least this many storeys (e.g. stairs: 2).
    min_storeys: int = Field(default=1, ge=1)


class AssemblyLibrary(_Model):
    name: str = "Aureom generic assemblies (illustrative)"
    version: str = "1"
    materials: list[MaterialSpec] = Field(default_factory=list)
    assemblies: list[Assembly] = Field(default_factory=list)
    foundations: list[FoundationOption] = Field(default_factory=list)
    allowances: list[AllowanceRule] = Field(default_factory=list)

    def material(self, material_id: str) -> MaterialSpec:
        for m in self.materials:
            if m.material_id == material_id:
                return m
        raise KeyError(f"unknown material '{material_id}'")

    def assembly(self, assembly_id: str) -> Assembly:
        for a in self.assemblies:
            if a.assembly_id == assembly_id:
                return a
        raise KeyError(f"unknown assembly '{assembly_id}'")

    def foundation(self, option_id: str) -> FoundationOption:
        for f in self.foundations:
            if f.option_id == option_id:
                return f
        raise KeyError(f"unknown foundation option '{option_id}'")

    def by_element(self, element: ElementType) -> list[Assembly]:
        return [a for a in self.assemblies if a.element == element]


class AssemblySelection(_Model):
    """Which assembly is used for each element (construction hypothesis).

    Selections are assumptions until the user confirms them; visual finishes
    never set them automatically.
    """

    external_wall: str
    separating_wall: str
    internal_partition: str
    ground_floor: str
    intermediate_floor: str
    pitched_roof: str
    flat_roof: str
    window: str
    external_door: str
    garage_door: str
    foundation: str
    #: Per-block overrides: {block_id: {element_value: assembly_id}}
    block_overrides: dict[str, dict[str, str]] = Field(default_factory=dict)
    basis: dict[str, Basis] = Field(default_factory=dict)

    def for_element(self, element: ElementType, block_id: Optional[str] = None) -> str:
        if block_id and block_id in self.block_overrides:
            ov = self.block_overrides[block_id].get(element.value)
            if ov:
                return ov
        return getattr(self, element.value)


class VisualFinish(_Model):
    """What the surface *looks like* in the images.  Kept separate from assemblies."""

    element: Literal["walls", "roof", "garage_door", "windows", "doors", "other"]
    appearance: str
    colour_hex: str = "#C8C2B4"
    basis: Basis = Basis.INFERRED
    feature_ids: list[str] = Field(default_factory=list)
    caveat: str = "Visual appearance only; does not establish structure or build-up."


class BuildingTwin(_Model):
    twin_id: str = Field(pattern=_ID_PATTERN)
    name: str = "Untitled twin"
    version: int = 1
    schema_version: str = SCHEMA_VERSION
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    blocks: list[Block]
    openings: list[Opening] = Field(default_factory=list)
    hidden: HiddenSideAssumptions
    assemblies: AssemblySelection
    visual_finishes: list[VisualFinish] = Field(default_factory=list)
    dwellings: int = 1
    bathrooms: TrackedValue = Field(default_factory=lambda: TrackedValue(
        value=2, unit="nr", basis=Basis.ASSUMED, low=1, high=3, source="aureom-uk-defaults-v1"))
    source_hypothesis_id: Optional[str] = None
    calibration_method: str = "none"
    edit_log: list[EditRecord] = Field(default_factory=list)
    information_level: str = (
        "Conceptual parametric reconstruction from images and labelled assumptions. "
        "Not a measured survey, not a design, not construction-ready BIM."
    )

    def block(self, block_id: str) -> Block:
        for b in self.blocks:
            if b.block_id == block_id:
                return b
        raise KeyError(f"unknown block '{block_id}'")


class TwinEdit(_Model):
    """A single user edit applied to a twin (drives immediate recalculation)."""

    target_type: Literal["block", "roof", "opening", "hidden", "assembly", "twin"]
    target_id: Optional[str] = None
    field: str
    value: Any
    tolerance: Optional[float] = None
    reason: str = ""
    actor: str = "user"


# =============================================================================
# Computed geometry (not persisted as source of truth)
# =============================================================================
class WallPiece(_Model):
    piece_id: str
    block_id: str
    side: Side
    #: Plan endpoints of the piece on the block outline (m).
    x0: float
    y0: float
    x1: float
    y1: float
    length_m: float
    exposure: Literal["external", "shared"]
    neighbour_block_id: Optional[str] = None
    #: External wall area of this piece in the rectangular zone FFL..plate (m2).
    external_rect_area_m2: float = 0.0
    #: External area of gable / monopitch infill above the plate (m2).
    external_infill_area_m2: float = 0.0
    #: Separating (shared) wall area counted on this piece (only on the piece
    #: owned by the lexicographically smaller block id, so it is counted once).
    shared_area_m2: float = 0.0
    opening_ids: list[str] = Field(default_factory=list)
    opening_area_m2: float = 0.0
    #: Opening perimeter (m) for reveals / lintels / sills.
    opening_head_length_m: float = 0.0
    opening_reveal_length_m: float = 0.0
    opening_sill_length_m: float = 0.0
    external_gross_area_m2: float = 0.0
    external_net_area_m2: float = 0.0


class StoreyMetrics(_Model):
    storey: int
    block_ids: list[str]
    gea_m2: float
    gia_m2: float
    external_perimeter_m: float
    shared_wall_length_m: float


class RoofMetrics(_Model):
    block_id: str
    form: RoofForm
    pitch_deg: float
    span_m: float  # wall-plate span perpendicular to ridge (or slope direction)
    rise_m: float
    plan_area_m2: float  # incl. overhangs on external edges
    surface_area_m2: float  # true sloped area
    ridge_length_m: float
    hip_length_m: float
    eaves_length_m: float
    verge_length_m: float
    abutment_length_m: float
    wall_plate_height_m: float
    ridge_height_m: float
    roof_void_volume_m3: float


class BlockMetrics(_Model):
    block_id: str
    width_m: float
    depth_m: float
    storeys: int
    ffl_m: float
    plate_height_m: float
    footprint_area_m2: float
    external_wall_gross_m2: float
    external_wall_net_m2: float
    opening_area_m2: float
    heated: bool
    #: Internal (GIA-style) area of this block on each storey it has.
    gia_by_storey: list[float] = Field(default_factory=list)
    #: Internal area of the block's top storey = insulated ceiling plane under its roof.
    ceiling_area_m2: float = 0.0
    #: External perimeter of this block at ground level (m).
    ground_perimeter_m: float = 0.0


class GeometryMetrics(_Model):
    blocks: list[BlockMetrics]
    pieces: list[WallPiece]
    storeys: list[StoreyMetrics]
    roofs: list[RoofMetrics]
    external_wall_thickness_m: float
    separating_wall_thickness_m: float
    footprint_area_m2: float  # ground-level GEA footprint
    ground_perimeter_m: float  # external perimeter at ground level
    gea_m2: float
    gia_m2: float
    heated_gia_m2: float
    external_wall_gross_m2: float
    external_wall_net_m2: float
    separating_wall_area_m2: float
    window_area_m2: float  # glazed openings (windows, patio/balcony doors)
    door_area_m2: float  # opaque external doors
    garage_door_area_m2: float
    opening_area_m2: float
    roof_plan_area_m2: float
    roof_surface_area_m2: float
    pitched_roof_surface_area_m2: float
    flat_roof_area_m2: float
    ground_floor_area_m2: float  # GIA of storey 0 (slab measured internally)
    intermediate_floor_area_m2: float  # GIA of upper storeys
    top_ceiling_area_m2: float  # internal area under roofs (insulated ceiling plane)
    heated_volume_m3: float
    conventions: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


# =============================================================================
# Quantities
# =============================================================================
class QuantityStatus(str, Enum):
    DERIVED = "derived"  # measured from geometry x assembly rule
    ALLOWANCE = "allowance"  # labelled allowance (not measured)
    UNRESOLVED = "unresolved"  # cannot be derived; left open


class TraceLink(_Model):
    kind: Literal["geometry", "assembly_rule", "allowance", "user_input", "calibration", "evidence", "assumption"]
    ref: str
    description: str = ""


class QuantityLine(_Model):
    line_id: str
    element_code: str  # e.g. "2.5"
    element_name: str  # e.g. "External walls"
    description: str
    status: QuantityStatus
    assembly_id: Optional[str] = None
    layer_index: Optional[int] = None
    material_id: Optional[str] = None
    allowance_id: Optional[str] = None
    cost_key: Optional[str] = None
    #: What the quantity was measured from, e.g. "net external wall area".
    measure_name: str = ""
    measure_value: Optional[float] = None
    measure_unit: str = ""
    formula: str = ""
    # --- installed (net, measured) quantity
    unit: str
    installed_qty: Optional[float] = None
    # --- losses, kept separate
    cutting_loss_fraction: float = 0.0
    cutting_loss_qty: Optional[float] = None
    waste_fraction: float = 0.0
    waste_qty: Optional[float] = None
    required_qty: Optional[float] = None  # installed + cutting + waste (installed units)
    # --- purchase
    purchase_unit: str = ""
    purchase_per_installed: float = 1.0
    pack_size: float = 1.0
    packs: Optional[int] = None
    purchased_qty: Optional[float] = None  # purchase units = packs * pack_size
    surplus_qty: Optional[float] = None  # purchased - required (purchase units)
    # --- labour
    trade: str = "general"
    labour_hours: Optional[float] = None
    # --- provenance
    basis: Basis = Basis.ASSUMED
    trace: list[TraceLink] = Field(default_factory=list)
    geometry_refs: list[str] = Field(default_factory=list)
    notes: str = ""


class BillOfQuantities(_Model):
    twin_id: str
    twin_version: int
    library_name: str
    lines: list[QuantityLine]
    geometry: GeometryMetrics
    conventions: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)

    def line(self, line_id: str) -> QuantityLine:
        for l in self.lines:
            if l.line_id == line_id:
                return l
        raise KeyError(line_id)

    @property
    def unresolved(self) -> list[QuantityLine]:
        return [l for l in self.lines if l.status == QuantityStatus.UNRESOLVED]


# =============================================================================
# Rates and costs
# =============================================================================
class CostLayer(str, Enum):
    MATERIALS = "1_materials"
    LABOUR = "2_labour"
    PLANT = "3_plant"
    LOGISTICS_WASTE = "4_logistics_waste"
    PRELIMINARIES = "5_preliminaries"
    FEES_ALLOWANCES = "6_fees_allowances"
    CONTINGENCY = "7_contingency"
    OVERHEAD_MARGIN = "8_overhead_margin"
    LAND_FINANCE_TAX_SALES = "9_land_finance_tax_sales"


COST_LAYER_NAMES: dict[CostLayer, str] = {
    CostLayer.MATERIALS: "Purchased materials",
    CostLayer.LABOUR: "Direct installation labour",
    CostLayer.PLANT: "Plant and equipment",
    CostLayer.LOGISTICS_WASTE: "Logistics and waste handling",
    CostLayer.PRELIMINARIES: "Site preliminaries",
    CostLayer.FEES_ALLOWANCES: "Professional fees and allowances",
    CostLayer.CONTINGENCY: "Risk contingency",
    CostLayer.OVERHEAD_MARGIN: "Contractor overhead and margin",
    CostLayer.LAND_FINANCE_TAX_SALES: "Land, finance, taxes and sales costs",
}


class TaxTreatment(str, Enum):
    EX_VAT = "ex_vat"
    INC_VAT = "inc_vat"
    ZERO_RATED = "zero_rated"
    EXEMPT = "exempt"
    UNKNOWN = "unknown"


class DeliveryTreatment(str, Enum):
    DELIVERED_INCLUDED = "delivered_included"
    EX_WORKS = "ex_works"
    DELIVERY_CHARGED_SEPARATELY = "delivery_charged_separately"
    COLLECTION = "collection"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class RateSourceType(str, Enum):
    FICTIONAL_DEMO = "fictional_demo"
    SUPPLIER_QUOTE = "supplier_quote"
    PRICE_LIST = "price_list"
    MANUAL = "manual"
    ADAPTER = "adapter"


#: Resolution priority (higher wins) when several rates match a cost key.
RATE_SOURCE_PRIORITY: dict[RateSourceType, int] = {
    RateSourceType.SUPPLIER_QUOTE: 5,
    RateSourceType.MANUAL: 4,
    RateSourceType.PRICE_LIST: 3,
    RateSourceType.ADAPTER: 2,
    RateSourceType.FICTIONAL_DEMO: 1,
}


class Rate(_Model):
    rate_id: str = Field(pattern=_ID_PATTERN)
    cost_key: str
    description: str = ""
    layer: CostLayer
    unit: str
    currency: str = "GBP"
    value: float = Field(ge=0.0)
    location: str = ""
    effective_date: date
    source: str
    source_type: RateSourceType
    supplier: str = ""
    tax_treatment: TaxTreatment = TaxTreatment.EX_VAT
    vat_rate: Optional[float] = None  # needed to strip VAT from INC_VAT rates
    delivery_treatment: DeliveryTreatment = DeliveryTreatment.UNKNOWN
    delivery_charge: Optional[float] = None  # per order, same currency
    #: Fractional uncertainty, e.g. low=-0.10, high=+0.15 (assumed unless quoted).
    uncertainty_low: float = -0.10
    uncertainty_high: float = 0.10
    quote_reference: str = ""
    valid_until: Optional[date] = None
    notes: str = ""


class RateBook(_Model):
    name: str
    rates: list[Rate] = Field(default_factory=list)
    notes: str = ""
    #: Load-time validation messages (skipped rows, clamped values) - additive, costing module.
    warnings: list[str] = Field(default_factory=list)


class FeeItem(_Model):
    name: str
    fraction: float = Field(ge=0.0, le=1.0)
    #: Boundary the fraction applies to, e.g. "direct" (layers 1-4) or "construction" (1-5).
    applies_to: Literal["direct", "construction"] = "construction"
    basis: Basis = Basis.ASSUMED
    note: str = ""


class CostParameters(_Model):
    """Project-level commercial assumptions (all labelled, all editable)."""

    prelims_weekly_cost: float = 1800.0
    prelims_fixed_setup: float = 6500.0
    #: Programme length used for time-related prelims when no sequence is supplied.
    default_programme_weeks: float = 26.0
    #: Logistics: cost per delivery load and per skip of waste.
    cost_per_delivery_load: float = 95.0
    skip_volume_m3: float = 6.0
    cost_per_skip: float = 290.0
    waste_bulking_factor: float = 1.6  # loose waste volume / solid volume
    fees: list[FeeItem] = Field(default_factory=lambda: [
        FeeItem(name="Architectural & design", fraction=0.06, applies_to="construction",
                note="Fictional demo assumption."),
        FeeItem(name="Structural engineer (indicative)", fraction=0.015, applies_to="construction",
                note="Fictional demo assumption."),
        FeeItem(name="Building control & warranty allowance", fraction=0.012, applies_to="construction",
                note="Fictional demo assumption."),
    ])
    contingency_fraction: float = 0.12
    contingency_basis: str = "Concept-stage design risk allowance (assumed)."
    overhead_fraction: float = 0.06
    margin_fraction: float = 0.08
    # --- layer 9 items (only when entered)
    land_cost: Optional[float] = None
    finance_rate_annual: Optional[float] = None
    finance_months: Optional[float] = None
    taxes: dict[str, float] = Field(default_factory=dict)  # name -> amount (e.g. stamp duty entered by user)
    sales_cost_fraction: Optional[float] = None  # of sales value
    sales_value: Optional[float] = None  # GDV, reported separately; never a cost
    notes: str = "All commercial parameters are editable assumptions."


class CostLine(_Model):
    line_id: str
    layer: CostLayer
    description: str
    cost_key: Optional[str] = None
    quantity: Optional[float] = None
    unit: str = ""
    rate_value: Optional[float] = None
    rate_id: Optional[str] = None
    currency: str = "GBP"
    amount: float = 0.0
    quantity_line_id: Optional[str] = None
    basis: Basis = Basis.ASSUMED
    formula: str = ""
    uncertainty_low: float = 0.0
    uncertainty_high: float = 0.0
    notes: str = ""


class CostBoundary(_Model):
    key: str
    name: str
    layers: list[CostLayer]
    amount: float
    definition: str
    excludes: str = ""


class CostEstimate(_Model):
    currency: str
    pricing_date: date
    location: str
    rate_book_name: str
    lines: list[CostLine]
    layer_totals: dict[str, float]
    boundaries: list[CostBoundary]
    gia_m2: float
    unresolved_items: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    #: Reported separately from cost; never included in a cost boundary.
    sales_value: Optional[float] = None
    programme_weeks: Optional[float] = None
    created_at: datetime = Field(default_factory=utcnow)
    #: Pricing conventions and rule assumptions used (additive, costing module).
    conventions: dict[str, str] = Field(default_factory=dict)
    #: Informational notes that are not problems (e.g. order-level rounding saving) - additive.
    notes: list[str] = Field(default_factory=list)

    def boundary(self, key: str) -> CostBoundary:
        for b in self.boundaries:
            if b.key == key:
                return b
        raise KeyError(key)


# =============================================================================
# Repeat-build economics
# =============================================================================
class LearningCurve(_Model):
    """Wright learning curve: hours(i) = h1 * i ** log2(rate), floored."""

    learning_rate: float = Field(default=0.92, gt=0.5, le=1.0)
    floor_fraction: float = Field(default=0.70, gt=0.0, le=1.0)
    applies_to: list[Literal["site_labour", "factory_labour"]] = Field(
        default_factory=lambda: ["site_labour", "factory_labour"])
    basis: Basis = Basis.ASSUMED
    note: str = "Assumed learning rate; not calibrated against Aureom outturn data."


class DiscountTier(_Model):
    min_units: int = Field(ge=1)
    discount_fraction: float = Field(ge=0.0, lt=1.0)


class StepCost(_Model):
    """A capacity threshold: ``cost`` is incurred once per started block of ``every_n_units``."""

    name: str
    every_n_units: int = Field(ge=1)
    cost: float
    starts_after_units: int = 0
    note: str = ""


class ProductionScenario(_Model):
    scenario_id: str = Field(pattern=_ID_PATTERN)
    name: str
    method: Literal["site_built", "offsite_panelised", "volumetric"] = "site_built"
    # one-off / reusable
    reusable_design_cost: float = 0.0
    tooling_cost: float = 0.0
    factory_setup_cost: float = 0.0
    # factory capacity
    factory_units_per_line: Optional[int] = None
    factory_line_cost: float = 0.0
    # per-house cost components (base values for house #1, before learning/discounts)
    materials_per_house: Optional[float] = None  # taken from estimate if None
    site_labour_hours_per_house: Optional[float] = None
    site_labour_rate: float = 38.0
    factory_labour_hours_per_house: float = 0.0
    factory_labour_rate: float = 30.0
    factory_overhead_per_house: float = 0.0
    plant_per_house: Optional[float] = None
    transport_loads_per_house: float = 0.0
    transport_cost_per_load: float = 0.0
    site_works_per_house: float = 0.0
    # sites and infrastructure
    houses_per_site: int = 25
    site_establishment_per_site: float = 45000.0
    infrastructure_per_plot: float = 0.0
    step_costs: list[StepCost] = Field(default_factory=list)
    # procurement and learning
    procurement_tiers: list[DiscountTier] = Field(default_factory=list)
    learning: LearningCurve = Field(default_factory=LearningCurve)
    #: Per-unit escalation applied beyond a threshold (e.g. scarce labour) - costs can rise.
    labour_scarcity_threshold_units: Optional[int] = None
    labour_scarcity_premium: float = 0.0
    notes: str = ""
    # --- additive (costing module) ------------------------------------------------
    #: Share of materials procured and consumed in the factory (counted at the factory gate).
    #: None -> assumed default by method (site_built 0, offsite_panelised 0.35, volumetric 0.70).
    factory_material_fraction: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    #: How procurement tiers apply: "all_units" (the tier reached by n discounts every unit) or
    #: "incremental" (each unit gets the tier in force when it is bought).
    discount_mode: Literal["all_units", "incremental"] = "all_units"
    #: Site logistics & waste per house (deliveries, skips, disposal); None -> estimate layer 4.
    site_logistics_per_house: Optional[float] = None


class RepeatBuildRow(_Model):
    n: int
    total_cost: float  # C(n)
    average_cost: float  # C(n)/n
    incremental_cost: float  # C(n+1) - C(n): cost of the next house
    components: dict[str, float] = Field(default_factory=dict)  # breakdown of C(n)


class RepeatBuildResult(_Model):
    scenario_id: str
    boundary: Literal["factory_gate", "installed", "development"]
    boundary_definition: str
    currency: str
    rows: list[RepeatBuildRow]
    comparison_ns: list[int]
    assumptions: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


# =============================================================================
# Uncertainty simulation
# =============================================================================
class UncertainInput(_Model):
    name: str
    group: str  # e.g. "scale", "hidden_geometry", "unit_prices", "labour_productivity", "waste", "ground", "lead_time"
    target: str  # dotted path or engine key
    distribution: str
    low: Optional[float] = None
    mode: Optional[float] = None
    high: Optional[float] = None
    unit: str = ""
    basis: Basis = Basis.ASSUMED
    description: str = ""


class SimulationConfig(_Model):
    n_samples: int = Field(default=1000, ge=20, le=200000)
    seed: int = 20261107
    method: Literal["lhs", "mc"] = "lhs"
    #: Rank correlation between groups, e.g. {"unit_prices|labour_productivity": 0.3}
    group_correlations: dict[str, float] = Field(default_factory=lambda: {"unit_prices|labour_rates": 0.4})
    include_groups: list[str] = Field(default_factory=lambda: [
        "scale", "hidden_geometry", "unit_prices", "labour_rates", "labour_productivity",
        "waste", "ground", "lead_time"])
    #: Ground-condition classes and probabilities (site investigation would resolve).
    ground_classes: dict[str, float] = Field(default_factory=lambda: {
        "good_clay_or_gravel": 0.6, "variable_made_ground": 0.3, "poor_soft_ground": 0.1})


class DistributionSummary(_Model):
    metric: str
    unit: str
    mean: float
    std: float
    p5: float
    p10: float
    p50: float
    p80: float
    p90: float
    p95: float
    min: float
    max: float


class SensitivityItem(_Model):
    input_name: str
    group: str
    spearman_rho: float
    variance_share: float  # first-order share of output variance (binned estimate)
    resolving_action: str = ""


class SimulationResult(_Model):
    scenario_id: str
    config: SimulationConfig
    n_samples: int
    metrics: list[DistributionSummary]
    #: Sampled totals for charts (construction cost boundary), length n_samples.
    samples: dict[str, list[float]] = Field(default_factory=dict)
    inputs: list[UncertainInput] = Field(default_factory=list)
    sensitivity: list[SensitivityItem] = Field(default_factory=list)
    #: Ranked list of missing inputs that would most reduce uncertainty.
    information_value: list[dict[str, Any]] = Field(default_factory=list)
    conditional_on_ground: dict[str, DistributionSummary] = Field(default_factory=dict)
    interval_type: str = (
        "Assumed scenario uncertainty: ranges are labelled engineering assumptions, "
        "not statistically calibrated against outturn costs."
    )
    notes: list[str] = Field(default_factory=list)


# =============================================================================
# Digital simulations
# =============================================================================
class CarbonLine(_Model):
    quantity_line_id: str
    material_id: str
    mass_kg: float
    factor_kgco2e_per_kg: float
    a1_a3_kgco2e: float
    a5_waste_kgco2e: float
    # --- additive (simulation module) -------------------------------------------
    #: Element code of the quantity line (e.g. "2.5").
    element_code: str = ""
    #: How the installed quantity was converted to mass (e.g. "m3 x density 2400 kg/m3").
    mass_method: str = ""
    #: Mass of cutting + waste losses (kg) that the A5 waste share is computed on.
    waste_mass_kg: float = 0.0
    #: Provenance of the line (weakest of the quantity line basis and the assumed factor).
    basis: Basis = Basis.ASSUMED


class CarbonResult(_Model):
    boundary: str = "A1-A3 product stage (+A5 material waste share). Excludes B, C, D stages and operational energy."
    total_a1_a3_kgco2e: float
    total_a5_waste_kgco2e: float
    a4_transport_kgco2e: float = 0.0
    per_m2_gia_kgco2e: float
    by_element: dict[str, float]
    lines: list[CarbonLine]
    unmatched: list[str] = Field(default_factory=list)
    factor_source: str = "Illustrative placeholder factors - replace with EPD / ICE data via adapter."
    caveats: list[str] = Field(default_factory=list)
    # --- additive (simulation module) -------------------------------------------
    #: Provenance of the totals (assumed at best: factors and assemblies are assumptions).
    basis: Basis = Basis.ASSUMED
    #: Labelled inputs and conventions used (A4 inputs, mass conversion rules, GIA).
    assumptions: dict[str, Any] = Field(default_factory=dict)

    @property
    def total_kgco2e(self) -> float:
        """A1-A3 + A5 waste share + A4 (when calculated)."""
        return self.total_a1_a3_kgco2e + self.total_a5_waste_kgco2e + self.a4_transport_kgco2e


class HeatLossElement(_Model):
    element: str
    assembly_id: Optional[str]
    area_m2: float
    u_value: float
    ua_w_k: float
    # --- additive (simulation module) -------------------------------------------
    #: Temperature factor b applied (1 = to outside air / ground; < 1 = to an unheated space);
    #: ``ua_w_k = u_value * area_m2 * b_factor``.
    b_factor: float = 1.0
    #: Provenance (construction assemblies and conductivities are assumptions unless confirmed).
    basis: Basis = Basis.ASSUMED
    notes: str = ""


class HeatLossResult(_Model):
    method: str = "Simplified steady-state fabric + ventilation heat loss (not SAP/SBEM/PHPP)."
    elements: list[HeatLossElement]
    fabric_ua_w_k: float
    thermal_bridging_w_k: float
    ventilation_w_k: float
    heat_loss_coefficient_w_k: float
    design_delta_t_k: float
    peak_heat_load_kw: float
    annual_space_heat_kwh: float
    hlp_w_m2k: float  # heat loss parameter per m2 floor
    assumptions: dict[str, Any] = Field(default_factory=dict)
    caveats: list[str] = Field(default_factory=list)
    # --- additive (simulation module) -------------------------------------------
    basis: Basis = Basis.ASSUMED
    #: Elements excluded or approximated (e.g. missing conductivity data).
    warnings: list[str] = Field(default_factory=list)


class TaskSpec(_Model):
    task_id: str
    name: str
    trade: str
    labour_hours: float
    crew_size: float
    duration_days: float
    predecessors: list[str] = Field(default_factory=list)
    lag_days: float = 0.0
    material_lead_time_days: float = 0.0
    earliest_start: float = 0.0
    earliest_finish: float = 0.0
    latest_start: float = 0.0
    latest_finish: float = 0.0
    total_float: float = 0.0
    critical: bool = False
    # --- additive (simulation module) -------------------------------------------
    #: Quantity line ids whose labour (and materials) are assigned to this task.
    line_ids: list[str] = Field(default_factory=list)
    notes: str = ""


class ProgrammeResult(_Model):
    method: str = "Critical path on an indicative task network (not a validated programme)."
    tasks: list[TaskSpec]
    duration_days: float
    duration_weeks: float
    working_days_per_week: float = 5.0
    critical_path: list[str]
    total_labour_hours: float
    labour_hours_by_trade: dict[str, float]
    caveats: list[str] = Field(default_factory=list)
    # --- additive (simulation module) -------------------------------------------
    assumptions: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    def task(self, task_id: str) -> TaskSpec:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        raise KeyError(task_id)


class DeliveryBatch(_Model):
    batch_id: str
    task_id: str
    description: str
    material_ids: list[str]
    mass_kg: float
    volume_m3: float
    loads: int
    required_by_day: float
    order_by_day: float
    storage_area_m2: float
    # --- additive (simulation module) -------------------------------------------
    delivery_category: str = ""
    line_ids: list[str] = Field(default_factory=list)
    #: Longest supplier lead time of the batch (working days).
    lead_time_days: float = 0.0
    #: Planned delivery day and the day the batch is used up (end of its task).
    delivery_day: float = 0.0
    consumed_by_day: float = 0.0
    #: Ready-mixed concrete: loads by truck volume, delivered on the day of use, no storage.
    ready_mix: bool = False


class LogisticsResult(_Model):
    batches: list[DeliveryBatch]
    total_loads: int
    total_mass_t: float
    peak_storage_area_m2: float
    waste_volume_m3: float
    skips: int
    assumptions: dict[str, Any] = Field(default_factory=dict)
    caveats: list[str] = Field(default_factory=list)
    # --- additive (simulation module) -------------------------------------------
    warnings: list[str] = Field(default_factory=list)


# =============================================================================
# Scenarios and project
# =============================================================================
class BuildScenario(_Model):
    scenario_id: str = Field(pattern=_ID_PATTERN)
    name: str
    description: str = ""
    hypothesis_id: Optional[str] = None
    #: Element -> assembly id overrides applied to the base twin.
    assembly_overrides: dict[str, str] = Field(default_factory=dict)
    foundation_option: Optional[str] = None
    production_scenario_id: Optional[str] = None
    rate_multiplier: float = 1.0


class ScenarioOutcome(_Model):
    scenario_id: str
    name: str
    hypothesis_id: Optional[str]
    gia_m2: float
    external_wall_thickness_m: float
    construction_cost: float  # boundary "construction_incl_contingency"
    contract_sum: float
    cost_per_m2_gia: float
    labour_hours: float
    programme_weeks: float
    embodied_carbon_kgco2e: float
    heat_loss_coefficient_w_k: float
    peak_heat_load_kw: float
    cost_p10: Optional[float] = None
    cost_p50: Optional[float] = None
    cost_p90: Optional[float] = None
    key_assumptions: list[str] = Field(default_factory=list)


class ScenarioComparison(_Model):
    outcomes: list[ScenarioOutcome]
    notes: list[str] = Field(default_factory=list)


class RunRecord(_Model):
    """Reproducibility log entry for an engine function call."""

    function: str
    timestamp: datetime = Field(default_factory=utcnow)
    inputs_sha256: str = ""
    outputs_sha256: str = ""
    seed: Optional[int] = None
    versions: dict[str, str] = Field(default_factory=dict)
    note: str = ""


class Project(_Model):
    project_id: str = Field(pattern=_ID_PATTERN)
    name: str
    schema_version: str = SCHEMA_VERSION
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    assumptions: AssumptionLibrary = Field(default_factory=AssumptionLibrary)
    images: list[ImageAsset] = Field(default_factory=list)
    analysis: Optional[AnalysisResult] = None
    references: list[ReferenceMeasurement] = Field(default_factory=list)
    calibration: Optional[ScaleCalibration] = None
    hypotheses: list[GeometryHypothesis] = Field(default_factory=list)
    selected_hypothesis_id: Optional[str] = None
    twin: Optional[BuildingTwin] = None
    library: AssemblyLibrary = Field(default_factory=AssemblyLibrary)
    rate_book: RateBook = Field(default_factory=lambda: RateBook(name="empty"))
    cost_parameters: CostParameters = Field(default_factory=CostParameters)
    production_scenarios: list[ProductionScenario] = Field(default_factory=list)
    build_scenarios: list[BuildScenario] = Field(default_factory=list)
    simulation_config: SimulationConfig = Field(default_factory=SimulationConfig)
    run_log: list[RunRecord] = Field(default_factory=list)
    notes: str = ""
