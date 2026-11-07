"""Uncertainty simulation of ONE coherent house: sampled inputs -> geometry -> quantities -> cost.

:func:`simulate_uncertainty` propagates the labelled uncertainty carried by a
:class:`~housebuilder_vision.core.models.BuildingTwin` (and by the rate book, the
library and a few explicit commercial assumptions) through the same engine
chain the deterministic estimate uses::

    sampled parameters -> compute_metrics (fast path) -> calculate_quantities
    -> labour productivity -> build_programme -> plan_deliveries
    -> estimate_construction_cost (programme weeks drive time-related prelims)

Every sample is **one coherent house**: one twin, one hypothesis, one assembly
set, one foundation option, one rate book draw.  Nothing is averaged across
hypotheses or construction assemblies; alternatives are compared with
:func:`housebuilder_vision.simulation.scenarios.compare_build_scenarios` (and
their spread is ranked with
:func:`housebuilder_vision.simulation.scenarios.combined_information_value`).
Every interval is therefore conditional on the twin's hypothesis and assembly
selection, which ``SimulationResult.interval_type`` states.

Uncertain inputs (:class:`UncertainInput`) and their groups
-----------------------------------------------------------
Inputs are discovered, never invented:

``scale``
    Every uncertain twin value whose ``correlation_group`` starts with
    ``"scale:"`` (dimensions converted from pixels of the same image) plus the
    calibration's ``metres_per_pixel`` when a calibration is passed.  Values in
    the same correlation group are sampled **comonotonically** (one latent draw
    per group, rho = 1).  Evidence-derived values without a correlation group
    (observed pitch, opening offsets) and every ``USER_CONFIRMED`` value with a
    tolerance (the person's own measurement, even when an edit kept the image's
    correlation group) are measurement errors in the same group but with their
    own independent draw.
``hidden_geometry``
    ``ASSUMED`` geometric values (hidden depths, roof pitch priors, overhangs,
    FFL, extension sizes), the hidden-facade glazing ratios, the assumed number
    of bathrooms and the partition-length allowance (internal layout).
    Independent (rho = 0).  Identical copies of one ``ASSUMED`` prior (same
    field, value, range and distribution - e.g. the FFL of every block, also the
    "assumed equal to the main block's FFL" copy of a hidden extension) are one
    shared input.
``unit_prices``
    One multiplier per non-labour rate actually used by the base estimate,
    ``triangular(1 + uncertainty_low, 1, 1 + uncertainty_high)`` from the rate.
``labour_rates``
    The same for every ``lab:<trade>`` rate used.
``labour_productivity``
    One hours multiplier per trade with labour, ``triangular(0.85, 1.0, 1.30)``
    (:data:`PRODUCTIVITY_MULTIPLIER`, a labelled assumption).
``waste``
    One multiplier per material category on the materials' ``waste_fraction``,
    ``triangular(0.6, 1.0, 1.8)`` (:data:`WASTE_MULTIPLIER`, assumption; cutting
    losses are geometric and kept).
``ground``
    A discrete ground class from ``config.ground_classes`` mapped to a
    foundation option: a class the selected option lists in its
    ``suitable_ground`` keeps the selected option; otherwise
    :data:`GROUND_FOUNDATIONS` (good -> the selected option, variable made
    ground -> deep trench fill, poor/soft ground -> piled allowance), else the
    first library option listing the class.  Skipped when the foundation
    selection is user-confirmed or fixed by a build scenario
    (``fixed_foundation``).
``lead_time``
    Supplier lead time (weeks) of the window / door / garage-door materials in
    the bill of quantities, from the material's ``lead_time_weeks`` range;
    windows & doors gate the programme, so this reaches the time-related
    preliminaries.

Only groups listed in ``config.include_groups`` are sampled; everything else
stays at its base value.  Held fixed (and stated in the notes): storey counts
(a topology change is a different hypothesis), the hypothesis and the assembly
selection, library allowance quantities, the substructure take-off priors and
all commercial fractions (fees, contingency, overhead, margin).

Coherence rules applied in every sample
---------------------------------------
* **Attached blocks stay attached.**  The base footprint is analysed once with
  ``twin.builder.footprint_attachments`` (the same attachment tree the twin
  editor reflows with): every block touching an already placed block keeps
  that contact and its alignment (front/rear or left/right flush, otherwise
  the base offset).  Their origins are derived, not sampled.
* **Depth-pitch coupling.**  A pitched block whose roof stores an observed rise
  (``RoofSpec.observed_rise_m``, see ``twin.builder.block_coupling``) keeps
  ``rise = k x span x tan(pitch)`` in every sample (k = 1/2 for gable / hip,
  1 for monopitch; span = the dimension the roof spans).  Each sample starts
  from the *stored* observed rise (scaled by the sampled ``metres_per_pixel``
  of its correlation group unless the rise is user-confirmed), never from the
  rise recomputed from an edited depth or pitch.  The sampled side is the one
  that is fixed by evidence: a user-confirmed / observed span is sampled and
  the pitch derived; a user-confirmed / observed pitch is sampled (or held,
  when fixed) and the span derived ``span = rise / (k tan(pitch))`` exactly -
  that pitch is never re-derived; with neither fixed, an image-derived span is
  sampled, otherwise the pitch prior, and the span derived from the prior is
  clipped to the span range (the pitch then re-derived so the relation stays
  exact).  A hip spans its shorter side: its coupled span is capped at the
  other plan dimension in every sample (the pitch re-derived; with a fixed
  pitch the cap is counted in the notes).  Not coupled: both fixed (sampled
  independently, stated in the notes) or a twin whose roof does not reproduce
  its observed rise (``twin.builder.coupling_warnings``).  Twins without a
  stored rise (saved before it existed) fall back to the rise of their current
  geometry for gables with ridge ``x`` / hips whose depth or pitch carries
  image evidence.
* **Wall plate - FFL coupling.**  A block with an observed wall-plate height
  (``Block.observed_eaves_m``) whose floor-to-floor is not user-confirmed /
  observed derives ``floor_to_floor = (plate x image scale - FFL) / storeys``
  per sample (the hypotheses fold the FFL range into the floor-to-floor, so
  sampling both would count the FFL twice), and every observed opening sill
  measured from the ground line is ``bottom x image scale - FFL - storey x
  floor-to-floor``.  The plate stays on the eaves seen in the image; a higher
  FFL means shorter storeys and lower sills.
* **Hidden-facade openings follow their rule, storey by storey.**  Rule-generated
  windows keep their count; the widths of each storey's rule windows scale so
  their glazed area tracks ``ratio x that storey's exposed wall area - the rule
  doors on that storey`` relative to the base (a wall shared in plan with a
  lower neighbour is exposed above the neighbour's wall plate, as in
  ``geometry.metrics``), and their positions scale with the wall length.
* Ground classes switch the foundation option of the twin (pre-built once per
  option with ``apply_construction_assemblies``; basis ASSUMED).

Sampling
--------
Every input and every group factor has its own random stream,
``PCG64(SeedSequence([seed, SHA-256(stable key)]))`` keyed by the input's target
(e.g. ``rate:<id>``, ``block:main.depth``): ``config.method == "lhs"`` draws a
Latin hypercube column from it (one point per stratum, strata in random order -
the same construction as ``scipy.stats.qmc.LatinHypercube``), ``"mc"`` plain
uniforms.  Build scenarios simulated with the same seed therefore share the
draws of every input they have in common (common random numbers), and their
samples are paired.  Dependence is a Gaussian copula: each input's latent
normal is ``x_i = a_g F_g + sqrt(1 - a_g^2) e_i`` with ``a_g = sqrt(rho_g)``
(one-factor model, :data:`GROUP_RHO`); group factors ``F`` (canonical order) are
correlated with ``config.group_correlations`` (Cholesky, repaired to the nearest
positive semi-definite correlation matrix when needed; the notes report the
correlations in force).  Latents map to marginals with ``scipy.stats``: uniform,
triangular, PERT (beta, lambda = 4), normal and lognormal with low/high read as
P5/P95.  Fully reproducible for a given seed.

Outputs
-------
:class:`DistributionSummary` for the cost boundaries, areas, concrete, labour
hours, programme weeks and every block's width / depth; samples (cost boundaries,
GIA, programme weeks, block dimensions and the ground class index); Spearman rank
correlation of every input with construction cost; first-order variance shares
by quantile binning (``Var(E[Y | bin]) / Var(Y)``, 10-20 equal-count bins,
small-sample bias corrected).  For a group the binned index is built from its
independent latent sources - each common factor once plus the own latent of
every member without a factor - used as is when there is one, else combined by
their correlation with the output (a linear projection, exact for independent
inputs with additive effects) and corrected for the in-sample bias of the
estimated weights; the ground class for ``ground``.  For a group with rho < 1
only the common factor is credited (a lower bound).  ``information_value`` ranks
groups by variance share with the action that would resolve them
(:func:`input_action` of the group's dominant input: e.g. the rear elevation
for an assumed rear glazing ratio, a second measured dimension once a
reference measurement sets the scale, a better measurement of a user-confirmed
value), a bootstrap standard error of the share, the ranks it could take
(``rank_range`` / ``tied_with``) and the P10-P90 width it accounts for
(``W x (1 - sqrt(1 - share))``: the expected narrowing if the group were
resolved, under a normal approximation).  Shares can sum to more than one when
groups are correlated.

Boundaries
----------
Intervals are **assumed scenario uncertainty**: they propagate labelled
engineering assumptions; they are not statistically calibrated against outturn
costs and are not confidence intervals.  Bundled demo prices are fictional.
"""

from __future__ import annotations

import copy
import hashlib
import math
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence, Union

import numpy as np
from scipy import stats

from ..core.models import (
    AssemblyLibrary,
    Block,
    BuildingTwin,
    CostParameters,
    DistributionSummary,
    ElementType,
    Opening,
    RateBook,
    RoofForm,
    ScaleCalibration,
    SensitivityItem,
    Side,
    SimulationConfig,
    SimulationResult,
    UncertainInput,
)
from ..core.provenance import Basis, Distribution, TrackedValue
from ..core.settings import AssumptionLibrary, ProjectSettings
from ..costing.engine import estimate_construction_cost
from ..costing.rates import rate_basis
from ..geometry.footprint import GeometryError, side_pieces
from ..geometry.metrics import BlockParams, OpeningParams, compute_metrics, params_from_twin, roof_shape
from ..quantities.measures import TakeoffAssumptions, unknown_openings
from ..quantities.takeoff import apply_construction_assemblies, calculate_quantities, wall_thicknesses
from ..twin.builder import (
    EAVES_TOL_M,
    FTF_PLAUSIBLE_M,
    BlockAttachment,
    attached_origin,
    block_coupling,
    footprint_attachments,
)
from .logistics import plan_deliveries
from .programme import build_programme

__all__ = [
    "GROUPS",
    "GROUP_RHO",
    "RESOLVING_ACTIONS",
    "SCALE_ACTION_CALIBRATED",
    "BOOTSTRAP_REPS",
    "GROUND_FOUNDATIONS",
    "PRODUCTIVITY_MULTIPLIER",
    "WASTE_MULTIPLIER",
    "COST_METRIC",
    "OUTPUT_METRICS",
    "INTERVAL_TYPE",
    "simulate_uncertainty",
    "discover_inputs",
    "input_action",
    "summarize",
    "binned_variance_share",
]

#: Input groups in reporting order.
GROUPS: tuple[str, ...] = ("scale", "hidden_geometry", "unit_prices", "labour_rates", "labour_productivity",
                           "waste", "ground", "lead_time")

#: Within-group rank-correlation of the one-factor Gaussian copula (rho_g; loading a_g = sqrt(rho_g)).
#: ``scale`` applies within one correlation group (one image); different images are independent.
#: ``lead_time`` (common supply-chain conditions) is an assumption added here; ``ground`` has one input.
GROUP_RHO: dict[str, float] = {
    "scale": 1.0,
    "unit_prices": 0.5,
    "labour_rates": 0.7,
    "labour_productivity": 0.6,
    "waste": 0.5,
    "hidden_geometry": 0.0,
    "lead_time": 0.5,
    "ground": 1.0,
}

#: The default action that would resolve (most of) each group's uncertainty.  ``information_value`` and
#: ``sensitivity`` refine it per input (:func:`input_action`): e.g. the hidden-geometry entry names the
#: rear elevation when the assumed rear glazing ratio dominates, the scale entry asks for a second measured
#: dimension once a reference measurement is in force, and a user-confirmed value asks for a better
#: measurement of that value.
RESOLVING_ACTIONS: dict[str, str] = {
    "scale": "Confirm a reference dimension such as the measured frontage",
    # what the engine can use for a hidden plan depth: a scale-linked side (left/right) elevation
    # (vision.multiview), a FLOOR_PLAN image with a BUILDING_OUTLINE per block and a DIMENSION carrying
    # length_m (twin.calibration.plan_evidence), or a depth entered in the twin editor (user-confirmed)
    "hidden_geometry": ("Confirm the hidden plan depth: upload a side elevation, or a floor plan with the building "
                        "outline and one measured dimension, or enter the measured depth"),
    "ground": "Commission a site/ground investigation",
    "unit_prices": "Obtain supplier quotations",
    "labour_rates": "Agree contractor labour rates",
    "labour_productivity": "Agree a contractor programme / productivity data",
    "lead_time": "Confirm window/door lead times with suppliers",
    "waste": "Confirm waste management plan",
}

#: Ground class -> foundation option id (``None`` = the twin's selected option), used for a class the
#: selected option does not list in its ``suitable_ground`` (a class it lists keeps the selected option).
#: Classes not listed here are matched to the first library option whose ``suitable_ground`` names them.
GROUND_FOUNDATIONS: dict[str, Optional[str]] = {
    "good_clay_or_gravel": None,
    "variable_made_ground": "fdn_deep_trench_fill",
    "poor_soft_ground": "fdn_piled_allowance",
}

#: Scale action once a measured reference (or a dimensioned plan) already sets the scale: the remaining
#: spread is perspective and pixel error, which another independent measurement narrows.
SCALE_ACTION_CALIBRATED = ("Add a second measured dimension (e.g. the eaves height or the overall depth) or a "
                           "less oblique photo")
#: Input-specific actions within ``hidden_geometry`` (matched on the input's target; first match wins).
_HIDDEN_ACTIONS: tuple[tuple[str, str], ...] = (
    ("hidden.rear_glazing_ratio", "Upload a rear elevation (rear openings are rule-filled from an assumed glazing "
                                  "ratio)"),
    ("hidden.side_glazing_ratio", "Upload the side elevations (side openings are rule-filled from an assumed "
                                  "glazing ratio)"),
    (".ground_floor_level", "Measure the finished floor level above external ground on site (FFL is an assumed "
                            "prior)"),
    ("roof.eaves_overhang_m", "Measure the eaves overhang (or annotate it in a measured elevation)"),
    ("roof.verge_overhang_m", "Measure the verge overhang (or annotate it in a measured elevation)"),
    ("roof.parapet_height_m", "Measure the parapet height"),
    (".floor_to_floor", "Confirm a reference dimension so the eaves height gives the storey height, or measure "
                        "the floor-to-floor height"),
    ("twin.bathrooms", "Confirm the number of bathrooms (internal layout not observed)"),
    ("assumptions.partition_length_per_m2_gia", "Confirm the internal layout with the designer (partition length "
                                                "is an assumed allowance)"),
    ("opening:", "Measure the openings on site or annotate them in a measured elevation"),
)
#: Bootstrap resamples for the standard error of each group's variance share.
BOOTSTRAP_REPS = 60
#: A group's action names its dominant input only when the group has at least this share of the variance
#: and that input at least this fraction of the group's share (else the group default).
_LEAD_MIN_SHARE = 0.01
_LEAD_FRACTION = 0.4

#: Labour productivity: hours multiplier per trade, triangular(low, mode, high) - labelled assumption.
PRODUCTIVITY_MULTIPLIER: tuple[float, float, float] = (0.85, 1.0, 1.30)
#: Multiplier on material waste fractions per material category, triangular(low, mode, high) - assumption.
WASTE_MULTIPLIER: tuple[float, float, float] = (0.6, 1.0, 1.8)

COST_METRIC = "construction_incl_contingency"
#: (metric, unit) of the summarised outputs; "CUR" is replaced by the project currency.
OUTPUT_METRICS: tuple[tuple[str, str], ...] = (
    ("construction_incl_contingency", "CUR"),
    ("contract_sum", "CUR"),
    ("gia_m2", "m2"),
    ("external_wall_net_m2", "m2"),
    ("roof_surface_m2", "m2"),
    ("concrete_m3", "m3"),
    ("labour_hours", "hr"),
    ("programme_weeks", "week"),
)
_SAMPLE_KEYS = ("construction_incl_contingency", "contract_sum", "gia_m2", "programme_weeks")

INTERVAL_TYPE = (
    "Assumed scenario uncertainty: P-values propagate labelled engineering assumptions and assumed ranges "
    "(geometry evidence and priors, rate ranges, productivity, waste, ground classes, lead times) through one "
    "coherent house per sample. They are not statistically calibrated against outturn costs and are not "
    "confidence intervals. Each interval is conditional on one geometry hypothesis and one assembly selection: "
    "alternatives are separate build scenarios, never sampled or averaged into one house."
)

_Z95 = float(stats.norm.ppf(0.95))
_EVIDENCE = (Basis.OBSERVED, Basis.INFERRED, Basis.USER_CONFIRMED)
_PITCH_LIMITS = (1.0, 74.0)
_MIN_DIM = 1e-3
_RATIO_MAX = 0.9
_WINDOW_ELEMENTS = {ElementType.WINDOW, ElementType.EXTERNAL_DOOR, ElementType.GARAGE_DOOR}

# (BlockParams attribute, path inside Block, label)
_BLOCK_FIELDS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("x0", ("origin_x",), "origin_x"),
    ("y0", ("origin_y",), "origin_y"),
    ("width", ("width",), "width"),
    ("depth", ("depth",), "depth"),
    ("floor_to_floor", ("floor_to_floor",), "floor_to_floor"),
    ("ffl", ("ground_floor_level",), "ground_floor_level"),
    ("pitch_deg", ("roof", "pitch_deg"), "roof.pitch_deg"),
    ("eaves_overhang", ("roof", "eaves_overhang_m"), "roof.eaves_overhang_m"),
    ("verge_overhang", ("roof", "verge_overhang_m"), "roof.verge_overhang_m"),
    ("parapet", ("roof", "parapet_height_m"), "roof.parapet_height_m"),
)
_OPENING_FIELDS: tuple[tuple[str, str], ...] = (("offset", "offset_m"), ("width", "width_m"),
                                                 ("height", "height_m"), ("sill", "sill_m"))


# =============================================================================
# Marginals
# =============================================================================
Ppf = Callable[[np.ndarray], np.ndarray]


def _marginal(distribution: str, low: Optional[float], mode: Optional[float],
              high: Optional[float]) -> Optional[Ppf]:
    """Inverse CDF of a labelled distribution, or ``None`` when there is no spread.

    ``triangular``/``pert`` use (low, mode, high); ``uniform`` (low, high); ``normal`` mean = mode
    with low/high as P5/P95; ``lognormal`` median = mode with low/high as P5/P95.
    """
    if mode is None or low is None or high is None:
        return None
    lo, hi, m = float(low), float(high), float(mode)
    if not (math.isfinite(lo) and math.isfinite(hi) and math.isfinite(m)) or hi - lo <= 1e-12:
        return None
    m = min(max(m, lo), hi)
    d = distribution.value if isinstance(distribution, Distribution) else str(distribution)
    if d == "fixed":
        return None
    if d == "uniform":
        rv = stats.uniform(loc=lo, scale=hi - lo)
    elif d == "pert":
        a = 1.0 + 4.0 * (m - lo) / (hi - lo)
        b = 1.0 + 4.0 * (hi - m) / (hi - lo)
        rv = stats.beta(a, b, loc=lo, scale=hi - lo)
    elif d == "normal":
        rv = stats.norm(loc=m, scale=(hi - lo) / (2.0 * _Z95))
    elif d == "lognormal" and lo > 0 and m > 0:
        rv = stats.lognorm(s=math.log(hi / lo) / (2.0 * _Z95), scale=m)
    elif d == "lognormal":
        rv = stats.norm(loc=m, scale=(hi - lo) / (2.0 * _Z95))
    else:  # triangular (default)
        rv = stats.triang(c=(m - lo) / (hi - lo), loc=lo, scale=hi - lo)
    return rv.ppf


def _tv_marginal(tv: Optional[TrackedValue]) -> Optional[Ppf]:
    if tv is None or tv.value is None or not tv.is_uncertain:
        return None
    return _marginal(tv.distribution, tv.low, tv.value, tv.high)


def _discrete_ppf(probs: Sequence[float]) -> Ppf:
    cum = np.cumsum(np.asarray(probs, dtype=float))
    cum = cum / cum[-1]

    def ppf(u: np.ndarray) -> np.ndarray:
        return np.minimum(np.searchsorted(cum, u, side="right"), len(cum) - 1).astype(float)

    return ppf


# =============================================================================
# Per-sample state and drivers
# =============================================================================
@dataclass
class _Sample:
    """Parameter values of one sampled house (only what differs from the base)."""

    block: dict[tuple[int, str], float] = field(default_factory=dict)
    opening: dict[tuple[int, str], float] = field(default_factory=dict)
    ratios: dict[str, float] = field(default_factory=dict)
    scale_ratio: dict[str, float] = field(default_factory=dict)
    bathrooms: Optional[float] = None
    partition: Optional[float] = None
    rate_mult: dict[str, float] = field(default_factory=dict)
    productivity: dict[str, float] = field(default_factory=dict)
    waste: dict[str, float] = field(default_factory=dict)
    ground: Optional[int] = None
    lead_time: dict[str, float] = field(default_factory=dict)


@dataclass
class _Driver:
    spec: UncertainInput
    ppf: Ppf
    apply: Callable[[float, _Sample], None]
    factor: Optional[str] = None
    loading: float = 0.0
    clip: tuple[float, float] = (-math.inf, math.inf)
    integer: bool = False
    #: ground driver only: class names in sampling order
    classes: list[str] = field(default_factory=list)


#: Attachment of a block to its parent (shared with the twin editor's reflow).
_Attach = BlockAttachment


@dataclass
class _Coupling:
    block: int
    mode: str  # pitch_primary (pitch sampled, span derived) | depth_primary (span sampled, pitch derived)
    k: float
    base_rise: float
    depth_lo: float  # span range (the span is the depth unless ``span == "width"``)
    depth_hi: float
    group: Optional[str]
    span: str = "depth"  # BlockParams attribute the roof spans: "depth" | "width"
    stored: bool = True  # base_rise is the stored observed rise (False: legacy twin, rise of the geometry)
    #: pitch_primary with a USER_CONFIRMED / OBSERVED pitch: the pitch is never re-derived (the span follows)
    pitch_fixed: bool = False
    #: hip roof: the span is the shorter side, so it is capped at the other plan dimension in every sample
    hip: bool = False

    @property
    def other(self) -> str:
        return "width" if self.span == "depth" else "depth"


@dataclass
class _EavesLink:
    """Floor-to-floor derived from the observed wall-plate height: ``ftf = (plate x scale - FFL) / storeys``."""

    block: int
    plate0: float  # base wall plate above ground (= the observed eaves, within EAVES_TOL_M)
    group: Optional[str]  # image scale group of the observed eaves (None: user-confirmed, held)
    storeys: int


@dataclass
class _SillLink:
    """Sill of an observed opening derived from its observed bottom above ground: ``z x scale - FFL - s x ftf``."""

    opening: int
    block: int
    storey: int
    z0: float  # base opening bottom above external ground
    group: Optional[str]


@dataclass
class _RuleSide:
    block: int
    side: Side
    ratio_key: str
    windows: list[int]
    doors: list[int]
    door_area: float
    base_target: float  # whole side: ratio x exposed wall area (all storeys) - rule doors
    base_side_len: float
    #: storey -> (rule windows on that storey, rule door area on that storey, base target of that storey)
    storeys: dict[int, tuple[list[int], float, float]] = field(default_factory=dict)


def _round(v: Optional[float], nd: int = 6) -> Optional[float]:
    return None if v is None else round(float(v), nd)


def _tv_key(field_label: str, tv: TrackedValue) -> tuple:
    """Merge key of identical value copies (one shared input).

    An ``ASSUMED`` value without a correlation group is identified by its field, value, range and
    distribution only: copies of one stated prior (e.g. the FFL copied to every block, also when a
    hypothesis re-labels the copy "assumed equal to the main block's FFL") are one assumption, whatever
    their source / note text.  Evidence-derived values also keep their source and note.
    """
    core = (field_label, tv.basis.value, _round(tv.value), _round(tv.low), _round(tv.high), tv.distribution.value,
            tv.unit)
    if tv.basis == Basis.ASSUMED and not tv.correlation_group:
        return core
    return core + (tv.correlation_group or "", tv.source, tv.note)


def _tv_group(tv: TrackedValue) -> Optional[str]:
    if tv.correlation_group and tv.correlation_group.startswith("scale:"):
        return "scale"
    if tv.basis == Basis.ASSUMED:
        return "hidden_geometry"
    if tv.basis in _EVIDENCE:
        return "scale"
    return None


def _get_path(block: Block, path: tuple[str, ...]) -> Optional[TrackedValue]:
    obj: Any = block
    for p in path:
        obj = getattr(obj, p, None)
        if obj is None:
            return None
    return obj


def _short(text: str, n: int = 160) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


_CALIBRATED_METHODS = ("reference_measurement", "dimensioned_plan")


def input_action(spec: UncertainInput, calibration_method: Optional[str] = None) -> str:
    """The action that would resolve one input's uncertainty (refines :data:`RESOLVING_ACTIONS`).

    * ``scale``: a ``USER_CONFIRMED`` value asks for a more precise measurement of that value (its tolerance
      is the person's own measurement error); otherwise, with a measured reference / dimensioned plan in
      force (``calibration_method``), a second measured dimension or a less oblique photo
      (:data:`SCALE_ACTION_CALIBRATED`), else the group default (confirm a reference dimension).
    * ``hidden_geometry``: rear / side glazing ratio -> the rear / side elevations; FFL, overhangs,
      bathrooms, partitions, assumed openings -> their own measurement; hidden depths, pitch priors and
      extension sizes -> the group default (a side elevation, a dimensioned floor plan or the measured depth -
      the evidence the engine can use for a hidden plan depth).
    * other groups: the group default.
    """
    g = spec.group
    if g == "scale":
        if spec.basis == Basis.USER_CONFIRMED and not spec.target.startswith("calibration."):
            name = spec.name.split(" (+", 1)[0]
            tol = ""
            if spec.low is not None and spec.high is not None and spec.high > spec.low:
                tol = f", currently +/-{0.5 * (spec.high - spec.low):.3g} {spec.unit}".rstrip()
            return f"Measure {name} more precisely (user-confirmed value{tol})"
        if calibration_method in _CALIBRATED_METHODS:
            return SCALE_ACTION_CALIBRATED
        return RESOLVING_ACTIONS["scale"]
    if g == "hidden_geometry":
        target = spec.target.split("; ")[0]
        for pattern, action in _HIDDEN_ACTIONS:
            if pattern in target:
                return action
        return RESOLVING_ACTIONS["hidden_geometry"]
    return RESOLVING_ACTIONS.get(g, "")


# =============================================================================
# The house model (base state + one-sample evaluation)
# =============================================================================
class _HouseModel:
    """Precomputed base state of the twin; ``evaluate`` builds and prices one sampled house."""

    def __init__(self, twin: BuildingTwin, library: AssemblyLibrary, rate_book: RateBook,
                 cost_params: CostParameters, settings: ProjectSettings, *,
                 takeoff: TakeoffAssumptions, crew_sizes: Optional[Mapping[str, float]],
                 fixed_foundation: Optional[str] = None) -> None:
        #: who fixed the foundation option (e.g. "build scenario S1"): ground classes are then not sampled
        self.fixed_foundation = fixed_foundation
        unknown = unknown_openings(twin)
        #: openings whose size / position is unknown are left out of the sampled geometry (their quantities
        #: stay UNRESOLVED in the deterministic bill of quantities)
        self.excluded_openings = sorted(unknown)
        if unknown:
            twin = twin.model_copy(update={"openings": [o for o in twin.openings if o.opening_id not in unknown]})
        self.twin = twin
        self.library = library
        self.book = rate_book
        self.cp = cost_params
        self.settings = settings
        self.ta = takeoff
        self.crew_sizes = dict(crew_sizes) if crew_sizes else None
        try:
            self.base_bp, self.base_op = params_from_twin(twin)
        except GeometryError as exc:
            raise ValueError(f"twin geometry is incomplete; cannot simulate ({exc})") from exc
        self.t_ext, self.t_sep = wall_thicknesses(twin, library)
        self.block_index = {b.block_id: i for i, b in enumerate(twin.blocks)}
        self.root = next((i for i, b in enumerate(twin.blocks) if b.role.value == "main"), 0)
        self.attachments, self.detached = self._attachments()
        self.coupling_notes: list[str] = []
        self.couplings = self._couplings()
        self.eaves_links = self._eaves_links()
        self.sill_links = self._sill_links()
        self.rule_sides = self._rule_sides()
        #: samples in which a hip with a fixed pitch could not keep its observed rise (span capped)
        self.rise_misses = 0
        self.concrete_ids = {m.material_id for m in library.materials
                             if m.category == "concrete" and "screed" not in m.material_id}
        self.foundation_twins: dict[str, BuildingTwin] = {twin.assemblies.foundation: twin}
        self.ground_options: list[str] = []
        self.geometry_fallbacks = 0

    # ------------------------------------------------------------ footprint analysis
    def _attachments(self) -> tuple[list[_Attach], set[int]]:
        return footprint_attachments([b.rect for b in self.base_bp], self.root, tol=1e-4)

    def _couplings(self) -> dict[int, _Coupling]:
        out: dict[int, _Coupling] = {}
        fixed = (Basis.OBSERVED, Basis.USER_CONFIRMED)
        for i, (b, bp) in enumerate(zip(self.twin.blocks, self.base_bp)):
            rise_tv = b.roof.observed_rise_m
            if rise_tv is not None and rise_tv.value is not None:
                c = block_coupling(b)
                if c is None:
                    continue
                if not c.consistent:
                    self.coupling_notes.append(
                        f"{b.block_id}: depth/pitch not coupled - the roof does not reproduce its observed rise "
                        f"(residual {c.residual_m:+.3f} m); {c.span_field} and pitch are sampled independently.")
                    continue
                span_fixed, pitch_fixed = c.span.basis in fixed, c.pitch.basis in fixed
                if span_fixed and pitch_fixed:
                    self.coupling_notes.append(
                        f"{b.block_id}: {c.span_field} and pitch are both {c.span.basis.value}/"
                        f"{c.pitch.basis.value}; sampled independently within their ranges (the observed rise "
                        "is not enforced).")
                    continue
                if span_fixed:
                    mode = "depth_primary"
                elif pitch_fixed:
                    mode = "pitch_primary"
                else:
                    mode = "depth_primary" if c.span.basis in _EVIDENCE else "pitch_primary"
                lo, hi = c.span.bounds()
                span_v = float(getattr(bp, c.span_field))
                group = None if rise_tv.basis == Basis.USER_CONFIRMED else rise_tv.correlation_group
                out[i] = _Coupling(block=i, mode=mode, k=1.0 / c.factor, base_rise=float(rise_tv.value),
                                   depth_lo=float(lo if lo is not None else span_v),
                                   depth_hi=float(hi if hi is not None else span_v), group=group, span=c.span_field,
                                   pitch_fixed=mode == "pitch_primary" and pitch_fixed,
                                   hip=bp.roof_form == RoofForm.HIP)
                continue
            # legacy twins (no stored rise): the rise of the current geometry, depth spans only
            if bp.roof_form == RoofForm.GABLE and bp.ridge_axis == "x":
                k = 0.5
            elif bp.roof_form == RoofForm.HIP and bp.depth <= bp.width:
                k = 0.5
            else:
                continue
            if Side.FRONT not in b.visible_sides:
                continue
            p_tv, d_tv = b.roof.pitch_deg, b.depth
            depth_ev = d_tv.basis in _EVIDENCE
            pitch_ev = p_tv.basis in fixed
            if depth_ev and pitch_ev:
                continue
            if not (d_tv.evidence_ids or p_tv.evidence_ids):
                continue  # no observed rise links them (depth from a ratio prior, pitch from the prior)
            mode = "depth_primary" if depth_ev else "pitch_primary"
            _, _, rise, _ = roof_shape(bp)
            lo, hi = d_tv.bounds()
            out[i] = _Coupling(block=i, mode=mode, k=k, base_rise=rise,
                               depth_lo=float(lo if lo is not None else bp.depth),
                               depth_hi=float(hi if hi is not None else bp.depth),
                               group=d_tv.correlation_group or p_tv.correlation_group, stored=False,
                               pitch_fixed=mode == "pitch_primary" and pitch_ev,
                               hip=bp.roof_form == RoofForm.HIP)
        return out

    def _eaves_links(self) -> dict[int, _EavesLink]:
        """Blocks whose floor-to-floor is derived from the observed eaves height in every sample.

        The hypotheses set ``ftf = (observed eaves - assumed FFL) / storeys`` (the FFL range folded into the
        ftf range).  Sampling the FFL and the ftf independently would count the FFL twice and lose the
        offset between substructure and wall height, so per sample ``ftf = (plate x image scale - FFL) /
        storeys``: the wall plate stays on the eaves seen in the image.  Not linked (stated in the notes):
        a ``USER_CONFIRMED`` / ``OBSERVED`` floor-to-floor, or a twin whose plate no longer matches the
        observed eaves (``twin.builder.coupling_warnings``).
        """
        out: dict[int, _EavesLink] = {}
        fixed = (Basis.OBSERVED, Basis.USER_CONFIRMED)
        for i, (b, bp) in enumerate(zip(self.twin.blocks, self.base_bp)):
            e = b.observed_eaves_m
            if e is None or e.value is None or bp.storeys < 1:
                continue
            if b.floor_to_floor.basis in fixed:
                self.coupling_notes.append(
                    f"{b.block_id}: floor-to-floor is {b.floor_to_floor.basis.value}; it is not derived from the "
                    "observed eaves (FFL and floor-to-floor sampled independently).")
                continue
            if abs(bp.plate - float(e.value)) > EAVES_TOL_M:
                self.coupling_notes.append(
                    f"{b.block_id}: wall plate {bp.plate:.2f} m does not match the observed eaves {e.value:.2f} m; "
                    "floor-to-floor not derived from it (sampled independently).")
                continue
            group = None if e.basis == Basis.USER_CONFIRMED else e.correlation_group
            out[i] = _EavesLink(block=i, plate0=float(bp.plate), group=group, storeys=int(bp.storeys))
        return out

    def _sill_links(self) -> list[_SillLink]:
        """Observed openings whose sill is derived per sample from their bottom above ground.

        A sill measured from the ground line (``opening bottom - FFL - storey x ftf``, correlation group of
        the image) keeps its observed bottom ``z`` (scaled by the image scale) in every sample, so a higher
        sampled FFL / floor-to-floor lowers the sill instead of moving the opening.  User-confirmed /
        observed sills and openings at floor level (sill 0, e.g. doors) are not linked.
        """
        out: list[_SillLink] = []
        fixed = (Basis.OBSERVED, Basis.USER_CONFIRMED)
        for k, (o, op) in enumerate(zip(self.twin.openings, self.base_op)):
            tv = o.sill_m
            if o.hidden_side_rule or o.block_id not in self.block_index or tv.basis in fixed:
                continue
            if not (tv.correlation_group or "").startswith("scale:") or op.sill <= 1e-6:
                continue
            bi = self.block_index[o.block_id]
            bp = self.base_bp[bi]
            out.append(_SillLink(opening=k, block=bi, storey=int(op.storey),
                                 z0=float(op.sill + bp.ffl + op.storey * bp.floor_to_floor), group=tv.correlation_group))
        return out

    def _storey_exposure(self, bps: Sequence[BlockParams]) -> dict[tuple[int, Side], list[float]]:
        """Exposed (external) wall area of each block side per storey band.

        A piece shared in plan with a neighbour is exposed above the neighbour's wall plate (the wall of a
        two-storey block above a single-storey extension is external), as in ``geometry.metrics``.
        """
        pcs = side_pieces([b.rect for b in bps])
        idx = {b.block_id: i for i, b in enumerate(bps)}
        out: dict[tuple[int, Side], list[float]] = {}
        for p in pcs:
            i = idx[p.rid]
            bp = bps[i]
            n = max(int(bp.storeys), 0)
            areas = out.setdefault((i, p.side), [0.0] * n)
            nb_plate = None if p.external else bps[idx[p.neighbour]].plate
            for s in range(n):
                lo = bp.ffl + s * bp.floor_to_floor
                hi = lo + bp.floor_to_floor
                h = hi - lo if nb_plate is None else max(0.0, hi - max(lo, nb_plate))
                areas[s] += p.length * h
        return out

    def _rule_sides(self) -> list[_RuleSide]:
        groups: "OrderedDict[tuple[int, Side], dict]" = OrderedDict()
        for k, o in enumerate(self.twin.openings):
            rule = o.hidden_side_rule or ""
            if not rule or o.block_id not in self.block_index:
                continue
            bi = self.block_index[o.block_id]
            g = groups.setdefault((bi, o.side), {"windows": [], "doors": [], "ratio": None})
            if rule.startswith("rear_glazing_ratio") or rule.startswith("side_glazing_ratio"):
                g["windows"].append(k)
                g["ratio"] = rule.split("=", 1)[0]
            else:
                g["doors"].append(k)
        if not groups:
            return []
        try:
            exposure = self._storey_exposure(self.base_bp)
        except GeometryError:
            return []
        out: list[_RuleSide] = []
        for (bi, side), g in groups.items():
            if not g["windows"] or g["ratio"] is None:
                continue
            bp = self.base_bp[bi]
            ratio = float(getattr(self.twin.hidden, g["ratio"]).value or 0.0)
            areas = exposure.get((bi, side), [])
            door_by_storey: dict[int, float] = {}
            for k in g["doors"]:
                o = self.base_op[k]
                door_by_storey[o.storey] = door_by_storey.get(o.storey, 0.0) + o.width * o.height
            door_area = sum(door_by_storey.values())
            target = ratio * sum(areas) - door_area
            per: dict[int, tuple[list[int], float, float]] = {}
            for s in sorted({self.base_op[k].storey for k in g["windows"]}):
                wins = [k for k in g["windows"] if self.base_op[k].storey == s]
                a_s = areas[s] if 0 <= s < len(areas) else 0.0
                per[s] = (wins, door_by_storey.get(s, 0.0), ratio * a_s - door_by_storey.get(s, 0.0))
            if target <= 1e-9 and all(t <= 1e-9 for _, _, t in per.values()):
                continue
            full = bp.width if side in (Side.FRONT, Side.REAR) else bp.depth
            out.append(_RuleSide(bi, side, g["ratio"], g["windows"], g["doors"], door_area, target, full, per))
        return out

    # ------------------------------------------------------------ foundations
    def foundation_twin(self, option_id: str) -> BuildingTwin:
        t = self.foundation_twins.get(option_id)
        if t is None:
            t = apply_construction_assemblies(self.twin, {"foundation": option_id}, self.library,
                                              actor="system:uncertainty-simulation",
                                              reason="ground-class sample (uncertainty simulation; assumed)")
            self.foundation_twins[option_id] = t
        return t

    # ------------------------------------------------------------ one sample
    def _geometry(self, s: _Sample) -> tuple[list[BlockParams], list[OpeningParams]]:
        bps = [copy.copy(b) for b in self.base_bp]
        for (bi, attr), v in s.block.items():
            setattr(bps[bi], attr, v)
        # floor-to-floor from the observed wall plate (scaled with the image) and the sampled FFL
        for e in self.eaves_links.values():
            bp = bps[e.block]
            plate = e.plate0 * s.scale_ratio.get(e.group or "", 1.0)
            bp.floor_to_floor = min(max((plate - bp.ffl) / e.storeys, FTF_PLAUSIBLE_M[0]), FTF_PLAUSIBLE_M[1])
        for c in self.couplings.values():
            bp = bps[c.block]
            rise = c.base_rise * s.scale_ratio.get(c.group or "", 1.0)
            # a hip spans its shorter side: the coupled span never exceeds the other plan dimension (a front
            # view of the hip's ridge band implies it), otherwise the roof would span the other side
            cap = getattr(bp, c.other) if c.hip else math.inf
            if c.mode == "pitch_primary":
                t = math.tan(math.radians(min(max(bp.pitch_deg, _PITCH_LIMITS[0]), _PITCH_LIMITS[1])))
                span = rise / (c.k * t)
                if c.pitch_fixed:
                    # a user-confirmed / observed pitch is never re-derived: the span follows the rise exactly
                    if span > cap:
                        self.rise_misses += 1
                    setattr(bp, c.span, max(min(span, cap), _MIN_DIM))
                    continue
                setattr(bp, c.span, min(max(span, c.depth_lo), c.depth_hi, cap))
            elif getattr(bp, c.span) > cap:
                setattr(bp, c.span, cap)
            span = max(getattr(bp, c.span), _MIN_DIM)
            bp.pitch_deg = min(max(math.degrees(math.atan(rise / (c.k * span))), _PITCH_LIMITS[0]), _PITCH_LIMITS[1])
        for a in self.attachments:
            b, n = bps[a.child], bps[a.parent]
            b.x0, b.y0 = attached_origin(a, (n.x0, n.y0, n.width, n.depth), b.width, b.depth)
        ops = [copy.copy(o) for o in self.base_op]
        for (oi, attr), v in s.opening.items():
            setattr(ops[oi], attr, v)
        for sl in self.sill_links:
            bp = bps[sl.block]
            z = sl.z0 * s.scale_ratio.get(sl.group or "", 1.0)
            ops[sl.opening].sill = max(0.0, z - bp.ffl - sl.storey * bp.floor_to_floor)
        if self.rule_sides:
            exposure = self._storey_exposure(bps)  # raises GeometryError on overlap
            for rs in self.rule_sides:
                bp = bps[rs.block]
                ratio = s.ratios.get(rs.ratio_key, float(getattr(self.twin.hidden, rs.ratio_key).value or 0.0))
                areas = exposure.get((rs.block, rs.side), [])
                f_side = (max(0.0, ratio * sum(areas) - rs.door_area) / rs.base_target
                          if rs.base_target > 1e-9 else 1.0)
                full = bp.width if rs.side in (Side.FRONT, Side.REAR) else bp.depth
                lf = full / rs.base_side_len if rs.base_side_len > 0 else 1.0
                for st, (wins, door_s, t0) in rs.storeys.items():
                    # each storey's rule glazing tracks ratio x that storey's exposed wall - its rule doors
                    if t0 > 1e-9:
                        a_s = areas[st] if 0 <= st < len(areas) else 0.0
                        f = max(0.0, ratio * a_s - door_s) / t0
                    else:
                        f = f_side
                    for k in wins:
                        o, o0 = ops[k], self.base_op[k]
                        centre = (o0.offset + 0.5 * o0.width) * lf
                        o.width = o0.width * f
                        o.offset = centre - 0.5 * o.width
                for k in rs.doors:
                    o, o0 = ops[k], self.base_op[k]
                    o.offset = (o0.offset + 0.5 * o0.width) * lf - 0.5 * o0.width
        return bps, ops

    def _twin_copy(self, template: BuildingTwin, bps: Sequence[BlockParams], ops: Sequence[OpeningParams],
                   s: _Sample) -> BuildingTwin:
        blocks: list[Block] = []
        for b, bp, b0 in zip(template.blocks, bps, self.base_bp):
            upd: dict[str, Any] = {}
            roof_upd: dict[str, Any] = {}
            for attr, path, _ in _BLOCK_FIELDS:
                v = getattr(bp, attr)
                if v == getattr(b0, attr):
                    continue
                tv = _get_path(b, path)
                if tv is None:
                    continue
                new = tv.model_copy(update={"value": float(v)})
                if path[0] == "roof":
                    roof_upd[path[1]] = new
                else:
                    upd[path[0]] = new
            if roof_upd:
                upd["roof"] = b.roof.model_copy(update=roof_upd)
            blocks.append(b.model_copy(update=upd) if upd else b)
        openings: list[Opening] = []
        for o, op, o0 in zip(template.openings, ops, self.base_op):
            upd = {}
            for attr, name in _OPENING_FIELDS:
                v = getattr(op, attr)
                if v != getattr(o0, attr):
                    upd[name] = getattr(o, name).model_copy(update={"value": float(v)})
            openings.append(o.model_copy(update=upd) if upd else o)
        upd_t: dict[str, Any] = {"blocks": blocks, "openings": openings}
        if s.bathrooms is not None:
            upd_t["bathrooms"] = template.bathrooms.model_copy(update={"value": float(s.bathrooms)})
        return template.model_copy(update=upd_t)

    def evaluate(self, s: _Sample, *, keep: bool = False) -> dict[str, Any]:
        """Build, measure, schedule and price one sampled house; returns its outputs.

        ``keep`` adds the sample's bill of quantities and estimate (``_boq`` / ``_estimate``).
        """
        try:
            bps, ops = self._geometry(s)
            metrics = compute_metrics(bps, ops, self.t_ext, self.t_sep)
        except GeometryError:
            # keep the sampled non-geometric values; fall back to the base footprint for this sample
            self.geometry_fallbacks += 1
            s = copy.copy(s)
            s.block, s.opening, s.ratios, s.scale_ratio = {}, {}, {}, {}
            bps, ops = self._geometry(s)
            metrics = compute_metrics(bps, ops, self.t_ext, self.t_sep)
        option = self.ground_options[s.ground] if s.ground is not None and self.ground_options else \
            self.twin.assemblies.foundation
        template = self.foundation_twin(option)
        twin_s = self._twin_copy(template, bps, ops, s)
        lib = self.library
        if s.waste:
            mats = []
            for m in lib.materials:
                f = s.waste.get(m.category)
                mats.append(m.model_copy(update={"waste_fraction": min(0.95, m.waste_fraction * f)})
                            if f is not None and m.waste_fraction > 0 else m)
            lib = lib.model_copy(update={"materials": mats})
        ta = self.ta
        if s.partition is not None:
            ta = ta.model_copy(update={"partition_length_per_m2_gia": ta.partition_length_per_m2_gia.model_copy(
                update={"value": float(s.partition)})})
        boq = calculate_quantities(twin_s, lib, metrics=metrics, assumptions=ta)
        labour = 0.0
        concrete = 0.0
        for ln in boq.lines:  # lines are fresh objects of this sample's bill: safe to scale in place
            if ln.labour_hours:
                f = s.productivity.get(ln.trade)
                if f is not None:
                    ln.labour_hours = ln.labour_hours * f
                labour += ln.labour_hours
            if ln.material_id in self.concrete_ids and ln.installed_qty:
                concrete += ln.installed_qty
        lt = dict(s.lead_time) or None
        prog = build_programme(boq, lib, crew_sizes=self.crew_sizes, lead_time_weeks=lt)
        logi = plan_deliveries(boq, lib, prog, lead_time_weeks=lt, waste_bulking_factor=self.cp.waste_bulking_factor,
                               skip_volume_m3=self.cp.skip_volume_m3)
        book = self.book
        if s.rate_mult:
            book = book.model_copy(update={"rates": [
                r.model_copy(update={"value": r.value * s.rate_mult[r.rate_id]}) if r.rate_id in s.rate_mult else r
                for r in book.rates]})
        est = estimate_construction_cost(boq, book, self.cp, settings=self.settings,
                                         programme_weeks=prog.duration_weeks, logistics=logi, library=lib)
        bnd = {b.key: b.amount for b in est.boundaries}
        out = {
            "construction_incl_contingency": bnd.get("construction_incl_contingency", math.nan),
            "contract_sum": bnd.get("contract_sum", math.nan),
            "gia_m2": metrics.gia_m2,
            "external_wall_net_m2": metrics.external_wall_net_m2,
            "roof_surface_m2": metrics.roof_surface_area_m2,
            "concrete_m3": concrete,
            "labour_hours": labour,
            "programme_weeks": prog.duration_weeks,
            "unresolved": len(est.unresolved_items),
            "foundation": option,
        }
        for bp in bps:
            out[f"{bp.block_id}.width_m"] = bp.width
            out[f"{bp.block_id}.depth_m"] = bp.depth
        if keep:
            out["_estimate"] = est
            out["_boq"] = boq
        return out


# =============================================================================
# Input discovery
# =============================================================================
def _geometry_drivers(model: _HouseModel, calibration: Optional[ScaleCalibration],
                      notes: list[str]) -> list[_Driver]:
    twin = model.twin
    merged: "OrderedDict[tuple, dict]" = OrderedDict()

    def add(key: tuple, tv: TrackedValue, name: str, target: str, description: str, setter: Callable,
            clip: tuple[float, float], integer: bool = False) -> None:
        g = merged.get(key)
        if g is None:
            merged[key] = {"tv": tv, "names": [name], "targets": [target], "desc": description,
                           "setters": [setter], "clip": clip, "integer": integer}
        else:
            g["names"].append(name)
            g["targets"].append(target)
            g["setters"].append(setter)

    derived: list[str] = []
    for bi, b in enumerate(twin.blocks):
        bp = model.base_bp[bi]
        coupling = model.couplings.get(bi)
        attached = bi == model.root or any(a.child == bi for a in model.attachments)
        for attr, path, label in _BLOCK_FIELDS:
            tv = _get_path(b, path)
            if tv is None or _tv_marginal(tv) is None:
                continue
            if attr in ("x0", "y0") and attached:
                derived.append(f"{b.block_id}.{label}")
                continue
            if attr == "pitch_deg" and bp.roof_form == RoofForm.FLAT:
                continue
            if attr == "verge_overhang" and bp.roof_form in (RoofForm.FLAT, RoofForm.HIP):
                continue
            if attr == "parapet" and bp.roof_form != RoofForm.FLAT:
                continue
            if coupling is not None and ((coupling.mode == "pitch_primary" and attr == coupling.span)
                                         or (coupling.mode == "depth_primary" and attr == "pitch_deg")):
                derived.append(f"{b.block_id}.{label}")
                continue
            if attr == "floor_to_floor" and bi in model.eaves_links:
                derived.append(f"{b.block_id}.{label}")
                continue
            desc = _short(tv.note or tv.source)
            if coupling is not None and attr in (coupling.span, "pitch_deg"):
                other = coupling.span if attr == "pitch_deg" else "roof pitch"
                desc = (f"{other} derived from the observed rise (rise = {coupling.k:g} x {coupling.span} x "
                        "tan(pitch)). " + desc)
            lo = 0.0 if attr in ("eaves_overhang", "verge_overhang", "parapet", "ffl") else _MIN_DIM
            clip = (_PITCH_LIMITS[0], _PITCH_LIMITS[1]) if attr == "pitch_deg" else (
                (-math.inf, math.inf) if attr in ("x0", "y0") else (lo, math.inf))
            key = (_tv_key(label, tv),) if not tv.correlation_group else (_tv_key(label, tv), b.block_id)

            def setter(v: float, s: _Sample, _bi: int = bi, _attr: str = attr) -> None:
                s.block[(_bi, _attr)] = v

            add(key, tv, f"{b.block_id}.{label}", f"block:{b.block_id}.{'.'.join(path)}", desc, setter, clip)
    sill_linked = {sl.opening for sl in model.sill_links}
    for oi, o in enumerate(twin.openings):
        if o.hidden_side_rule:
            continue
        for attr, name in _OPENING_FIELDS:
            tv = getattr(o, name)
            if _tv_marginal(tv) is None:
                continue
            if attr == "sill" and oi in sill_linked:
                derived.append(f"{o.opening_id}.{name}")
                continue

            def setter(v: float, s: _Sample, _oi: int = oi, _attr: str = attr) -> None:
                s.opening[(_oi, _attr)] = v

            clip = (-math.inf, math.inf) if attr == "offset" else (0.0 if attr == "sill" else _MIN_DIM, math.inf)
            add((_tv_key(name, tv), o.opening_id), tv, f"{o.opening_id}.{name}", f"opening:{o.opening_id}.{name}",
                _short(tv.note or tv.source), setter, clip)
    ratio_keys = {rs.ratio_key for rs in model.rule_sides}
    for rk in ("rear_glazing_ratio", "side_glazing_ratio"):
        tv = getattr(twin.hidden, rk)
        if rk not in ratio_keys or _tv_marginal(tv) is None:
            continue

        def setter(v: float, s: _Sample, _rk: str = rk) -> None:
            s.ratios[_rk] = v

        add((_tv_key(rk, tv),), tv, f"hidden.{rk}", f"hidden.{rk}",
            "Rule-generated openings on hidden facades scale with this ratio. " + _short(tv.note or tv.source),
            setter, (0.0, _RATIO_MAX))
    if _tv_marginal(twin.bathrooms) is not None and any(
            a.basis_measure == "per_bathroom" for a in model.library.allowances):
        def set_bath(v: float, s: _Sample) -> None:
            s.bathrooms = v

        add(("bathrooms",), twin.bathrooms, "twin.bathrooms", "twin.bathrooms",
            "Number of bathrooms (internal layout hidden; drives per-bathroom allowances), rounded to whole rooms.",
            set_bath, (1.0, math.inf), integer=True)
    ptv = model.ta.partition_length_per_m2_gia
    if _tv_marginal(ptv) is not None:
        def set_part(v: float, s: _Sample) -> None:
            s.partition = v

        add(("partition",), ptv, "takeoff.partition_length_per_m2_gia", "assumptions.partition_length_per_m2_gia",
            "Internal partition length per m2 GIA (no internal layout observed). " + _short(ptv.note), set_part,
            (0.0, math.inf))
    if calibration is not None and _tv_marginal(calibration.metres_per_pixel) is not None:
        mpp = calibration.metres_per_pixel
        grp = mpp.correlation_group or f"scale:{calibration.image_id}"
        base = float(mpp.value)

        def set_mpp(v: float, s: _Sample, _g: str = grp, _b: float = base) -> None:
            s.scale_ratio[_g] = v / _b

        tv = mpp if mpp.correlation_group else mpp.model_copy(update={"correlation_group": grp})
        add(("mpp",), tv, f"calibration.metres_per_pixel[{calibration.image_id}]", "calibration.metres_per_pixel",
            f"Image scale ({calibration.method}); drives the observed roof rises of coupled blocks. "
            + _short(mpp.note), set_mpp, (1e-9, math.inf))
    elif model.couplings or model.eaves_links or model.sill_links:
        notes.append("No calibration passed: the observed roof rises, wall plates and opening bottoms of coupled "
                     "blocks are held at their base values (scale uncertainty then reaches them only through the "
                     "sampled pitch and FFL).")
    notes.extend(model.coupling_notes)
    if derived:
        notes.append("Derived per sample (not sampled): " + ", ".join(sorted(set(derived)))
                     + " - attached blocks keep their contact and alignment; coupled depth/pitch follow the "
                     "observed roof rise; floor-to-floor = (observed wall plate x image scale - FFL) / storeys and "
                     "observed sills = (opening bottom x image scale) - FFL - storey x floor-to-floor, so the "
                     "sampled FFL is not counted twice.")

    drivers: list[_Driver] = []
    for key, g in merged.items():
        tv: TrackedValue = g["tv"]
        group = "scale" if key == ("mpp",) else _tv_group(tv)
        if group is None:
            continue
        setters = g["setters"]

        def apply(v: float, s: _Sample, _setters=tuple(setters)) -> None:
            for fn in _setters:
                fn(v, s)

        names = g["names"]
        name = names[0] if len(names) == 1 else f"{names[0]} (+{len(names) - 1} shared)"
        desc = g["desc"]
        if len(names) > 1:
            desc = f"One shared assumption applied to {', '.join(names)}. " + desc
        # a user-confirmed value is the person's own measurement: its tolerance is an independent error, even
        # when the edited value still carries the image's correlation group (it no longer moves with the scale)
        independent = tv.basis == Basis.USER_CONFIRMED and key != ("mpp",)
        if independent and tv.correlation_group:
            desc = "User-confirmed: its tolerance is sampled as an independent measurement error. " + desc
        spec = UncertainInput(name=name, group=group, target="; ".join(g["targets"])[:500],
                              distribution=tv.distribution.value, low=tv.low, mode=tv.value, high=tv.high,
                              unit=tv.unit, basis=tv.basis, description=_short(desc, 400))
        drivers.append(_Driver(spec=spec, ppf=_tv_marginal(tv), apply=apply, clip=g["clip"], integer=g["integer"],
                               factor=(tv.correlation_group if group == "scale" and tv.correlation_group
                                       and not independent else None)))
    return drivers


def _ground_driver(model: _HouseModel, config: SimulationConfig, notes: list[str]) -> Optional[_Driver]:
    """Discrete ground-class input (sets ``model.ground_options``), or ``None``."""
    if "ground" not in config.include_groups:
        return None
    sel = model.twin.assemblies
    if model.fixed_foundation:
        notes.append(f"Ground classes not sampled: the foundation option '{sel.foundation}' is fixed by "
                     f"{model.fixed_foundation}; the interval is conditional on that foundation.")
        return None
    if sel.basis.get("foundation") == Basis.USER_CONFIRMED:
        notes.append(f"Ground classes not sampled: the foundation option is user-confirmed ('{sel.foundation}').")
        return None
    fids = {f.option_id for f in model.library.foundations}
    try:
        suits = set(model.library.foundation(sel.foundation).suitable_ground)
    except KeyError:
        suits = set()
    classes: list[str] = []
    probs: list[float] = []
    options: list[str] = []
    for cls, p in config.ground_classes.items():
        if p is None or not math.isfinite(float(p)) or float(p) <= 0:
            continue
        if cls in suits:  # the selected option already suits this class: keep it
            opt = sel.foundation
        elif cls in GROUND_FOUNDATIONS:
            opt = GROUND_FOUNDATIONS[cls] or sel.foundation
        else:
            opt = next((f.option_id for f in model.library.foundations if cls in f.suitable_ground), None)
            if opt is None:
                notes.append(f"Ground class '{cls}' matches no foundation option; the selected option is used.")
                opt = sel.foundation
        if opt not in fids:
            notes.append(f"Foundation option '{opt}' for ground class '{cls}' is not in the library; the selected "
                         "option is used.")
            opt = sel.foundation
        classes.append(cls)
        probs.append(float(p))
        options.append(opt)
    if len(classes) < 2:
        return None
    model.ground_options = options
    for opt in dict.fromkeys(options):
        model.foundation_twin(opt)

    def apply(v: float, s: _Sample) -> None:
        s.ground = int(v)

    total = sum(probs)
    desc = "; ".join(f"{c} (p={p / total:.2f}) -> {o}" for c, p, o in zip(classes, probs, options))
    spec = UncertainInput(name="ground class", group="ground", target="assemblies.foundation",
                          distribution="discrete", low=0.0, mode=0.0, high=float(len(classes) - 1), unit="class",
                          basis=Basis.ASSUMED,
                          description=_short("Ground conditions are not visible; assumed class probabilities select "
                                             "the foundation option: " + desc, 400))
    return _Driver(spec=spec, ppf=_discrete_ppf(probs), apply=apply, factor="ground", integer=True,
                   classes=list(classes))


def _commercial_drivers(model: _HouseModel, base: dict[str, Any], config: SimulationConfig,
                        notes: list[str]) -> list[_Driver]:
    drivers: list[_Driver] = []
    ground = _ground_driver(model, config, notes)
    # the bills and estimates of every foundation option the ground classes can select
    runs = [base]
    for k, opt in enumerate(model.ground_options):
        if opt != model.twin.assemblies.foundation and opt not in model.ground_options[:k]:
            runs.append(model.evaluate(_Sample(ground=k), keep=True))
    boq = base["_boq"]
    rates = {r.rate_id: r for r in model.book.rates}
    used: "OrderedDict[str, Any]" = OrderedDict()
    for run in runs:
        for ln in run["_estimate"].lines:
            if ln.rate_id and ln.rate_id in rates and ln.rate_id not in used:
                used[ln.rate_id] = rates[ln.rate_id]
    for rid, r in used.items():
        lo, hi = 1.0 + float(r.uncertainty_low), 1.0 + float(r.uncertainty_high)
        lo = max(lo, 0.0)
        ppf = _marginal("triangular", lo, 1.0, hi)
        if ppf is None:
            continue
        group = "labour_rates" if r.cost_key.startswith("lab:") else "unit_prices"

        def apply(v: float, s: _Sample, _rid: str = rid) -> None:
            s.rate_mult[_rid] = v

        label = "labour rate" if group == "labour_rates" else "unit price"
        spec = UncertainInput(
            name=f"{label}: {r.cost_key}", group=group, target=f"rate:{rid}", distribution="triangular", low=lo,
            mode=1.0, high=hi, unit="multiplier", basis=rate_basis(r),
            description=_short(f"Multiplier on rate {rid} ({r.value:g} {r.currency}/{r.unit}, {r.source_type.value}); "
                               f"range from the rate's uncertainty {r.uncertainty_low:+.0%}/{r.uncertainty_high:+.0%}.",
                               300))
        drivers.append(_Driver(spec=spec, ppf=ppf, apply=apply, factor=group, clip=(0.0, math.inf)))
    all_lines = [ln for run in runs for ln in run["_boq"].lines]
    trades = sorted({ln.trade for ln in all_lines if ln.labour_hours})
    plo, pm, phi = PRODUCTIVITY_MULTIPLIER
    for tr in trades:
        def apply(v: float, s: _Sample, _tr: str = tr) -> None:
            s.productivity[_tr] = v

        spec = UncertainInput(name=f"productivity: {tr}", group="labour_productivity", target=f"productivity:{tr}",
                              distribution="triangular", low=plo, mode=pm, high=phi, unit="multiplier",
                              basis=Basis.ASSUMED,
                              description=f"Multiplier on {tr} labour hours (assumed range; library hours are "
                                          "illustrative, not contractor data).")
        drivers.append(_Driver(spec=spec, ppf=_marginal("triangular", plo, pm, phi), apply=apply,
                               factor="labour_productivity", clip=(0.0, math.inf)))
    mats = {m.material_id: m for m in model.library.materials}
    cats = sorted({mats[ln.material_id].category for ln in all_lines
                   if ln.material_id in mats and mats[ln.material_id].waste_fraction > 0 and ln.cost_key})
    wlo, wm, whi = WASTE_MULTIPLIER
    for cat in cats:
        def apply(v: float, s: _Sample, _c: str = cat) -> None:
            s.waste[_c] = v

        spec = UncertainInput(name=f"waste: {cat}", group="waste", target=f"waste:{cat}", distribution="triangular",
                              low=wlo, mode=wm, high=whi, unit="multiplier", basis=Basis.ASSUMED,
                              description=f"Multiplier on the waste fraction of '{cat}' materials (assumed range; "
                                          "cutting losses unchanged).")
        drivers.append(_Driver(spec=spec, ppf=_marginal("triangular", wlo, wm, whi), apply=apply, factor="waste",
                               clip=(0.0, math.inf)))
    if ground is not None:
        drivers.append(ground)
    # lead times of window / door materials
    asms = {a.assembly_id: a for a in model.library.assemblies}
    lt_mats: list[str] = []
    for ln in boq.lines:
        a = asms.get(ln.assembly_id or "")
        if a is not None and a.element in _WINDOW_ELEMENTS and ln.material_id and ln.material_id not in lt_mats:
            lt_mats.append(ln.material_id)
    for mid in lt_mats:
        tv = mats[mid].lead_time_weeks if mid in mats else None
        ppf = _tv_marginal(tv)
        if ppf is None:
            continue

        def apply(v: float, s: _Sample, _m: str = mid) -> None:
            s.lead_time[_m] = v

        spec = UncertainInput(name=f"lead time: {mid}", group="lead_time", target=f"lead_time:{mid}",
                              distribution=tv.distribution.value, low=tv.low, mode=tv.value, high=tv.high, unit="week",
                              basis=tv.basis,
                              description="Supplier lead time; windows & doors are ordered at day 0 and gate their "
                                          "installation task in the programme. " + _short(tv.note))
        drivers.append(_Driver(spec=spec, ppf=ppf, apply=apply, factor="lead_time", clip=(0.0, math.inf)))
    return drivers


def discover_inputs(twin: BuildingTwin, library: AssemblyLibrary, rate_book: RateBook,
                    cost_params: CostParameters, settings: ProjectSettings, *,
                    config: Optional[SimulationConfig] = None, calibration: Optional[ScaleCalibration] = None,
                    assumptions: Union[AssumptionLibrary, TakeoffAssumptions, None] = None,
                    fixed_foundation: Optional[str] = None) -> list[UncertainInput]:
    """The uncertain inputs :func:`simulate_uncertainty` would sample (no sampling done)."""
    cfg = config or SimulationConfig()
    model = _HouseModel(twin, library, rate_book, cost_params, settings, takeoff=_takeoff(assumptions),
                        crew_sizes=None, fixed_foundation=fixed_foundation)
    notes: list[str] = []
    drivers = _all_drivers(model, cfg, calibration, notes)[0]
    return [d.spec for d in drivers]


def _takeoff(assumptions: Union[AssumptionLibrary, TakeoffAssumptions, None]) -> TakeoffAssumptions:
    if isinstance(assumptions, AssumptionLibrary):
        return TakeoffAssumptions.from_assumption_library(assumptions)
    return assumptions or TakeoffAssumptions()


def _base_run(model: _HouseModel) -> dict[str, Any]:
    return model.evaluate(_Sample(), keep=True)


def _all_drivers(model: _HouseModel, cfg: SimulationConfig, calibration: Optional[ScaleCalibration],
                 notes: list[str]) -> tuple[list[_Driver], dict[str, Any]]:
    base = _base_run(model)
    drivers = _geometry_drivers(model, calibration, notes) + _commercial_drivers(model, base, cfg, notes)
    include = set(cfg.include_groups)
    unknown = sorted(include - set(GROUPS))
    if unknown:
        notes.append(f"Unknown groups in include_groups ignored: {', '.join(unknown)}.")
    skipped = sorted({d.spec.group for d in drivers if d.spec.group not in include})
    if skipped:
        notes.append(f"Groups held at base values (not in include_groups): {', '.join(skipped)}.")
    return [d for d in drivers if d.spec.group in include], base


# =============================================================================
# Sampling
# =============================================================================
def _nearest_correlation(c: np.ndarray) -> tuple[np.ndarray, bool]:
    c = 0.5 * (c + c.T)
    w, v = np.linalg.eigh(c)
    if w.min() > 1e-10:
        return c, False
    w = np.clip(w, 1e-8, None)
    c2 = (v * w) @ v.T
    d = np.sqrt(np.diag(c2))
    c2 = c2 / np.outer(d, d)
    np.fill_diagonal(c2, 1.0)
    return c2, True


def _stream(seed: int, key: str) -> np.random.Generator:
    """The random stream of one input (or group factor): PCG64 seeded from ``(seed, SHA-256(key))``.

    Keyed by the input's stable target (e.g. ``rate:<id>``, ``block:main.depth``) rather than its column
    position, so an input shared by two build scenarios gets identical draws in both (common random
    numbers) even when the scenarios have different input sets.  ``hashlib`` (not ``hash()``) keeps it
    reproducible across processes.
    """
    h = hashlib.sha256(key.encode("utf-8")).digest()
    words = [int.from_bytes(h[i:i + 4], "little") for i in range(0, 16, 4)]
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([int(seed) % (1 << 64), *words])))


def _uniform_column(rng: np.random.Generator, n: int, method: str) -> np.ndarray:
    """One column of uniforms: a Latin hypercube stratification (``lhs``) or plain Monte Carlo (``mc``)."""
    if method == "lhs":  # one point per stratum [i/n, (i+1)/n), strata in random order (= scipy's LHS column)
        return (rng.permutation(n) + rng.random(n)) / n
    return rng.random(n)


def _stream_keys(drivers: Sequence[_Driver]) -> list[str]:
    """Stable, unique stream key of every driver (its primary target; repeats get a ``#k`` suffix)."""
    seen: dict[str, int] = {}
    out = []
    for d in drivers:
        base = "input:" + (d.spec.target.split("; ")[0] or d.spec.name)
        seen[base] = seen.get(base, 0) + 1
        out.append(base if seen[base] == 1 else f"{base}#{seen[base]}")
    return out


def _latents(drivers: Sequence[_Driver], cfg: SimulationConfig, notes: list[str]
             ) -> tuple[np.ndarray, np.ndarray, list[str], np.ndarray]:
    """Correlated latent normals X (n x D), factor values F (n x K), factor keys, factor correlation.

    Common random numbers: every input and every group factor draws from its own stream keyed by a
    stable name (:func:`_stream`), so build scenarios simulated with the same seed share the draws of
    every input they have in common; paired scenario differences are then much less noisy than the
    marginal P-values.  Factors are ordered canonically (``GROUPS`` order, then key) so the Cholesky
    mixing of a shared factor does not depend on which other inputs a scenario has.
    """
    n = cfg.n_samples
    factors: list[str] = []
    for d in drivers:
        g = d.spec.group
        if d.factor is None:
            d.loading = 0.0
            continue
        rho = GROUP_RHO.get(g, 0.0)
        d.loading = math.sqrt(max(0.0, min(1.0, rho)))
        if d.loading == 0.0:
            d.factor = None
            continue
        if d.factor not in factors:
            factors.append(d.factor)
    group_of = {f: (f.split(":", 1)[0] if f.startswith("scale:") else f) for f in factors}
    gpos = {g: i for i, g in enumerate(GROUPS)}
    factors.sort(key=lambda f: (gpos.get(group_of[f], len(GROUPS)), f))
    k = len(factors)
    c = np.eye(k)
    requested: list[tuple[str, float, tuple[int, int]]] = []
    for key, val in (cfg.group_correlations or {}).items():
        parts = [p.strip() for p in str(key).split("|")]
        if len(parts) != 2 or not all(p in GROUPS for p in parts) or val is None or not math.isfinite(float(val)):
            notes.append(f"Group correlation '{key}' ignored (expected 'group_a|group_b' with known groups).")
            continue
        v = max(-0.99, min(0.99, float(val)))
        first: Optional[tuple[int, int]] = None
        for i, fi in enumerate(factors):
            for j, fj in enumerate(factors):
                if i != j and {group_of[fi], group_of[fj]} == set(parts) and group_of[fi] != group_of[fj]:
                    c[i, j] = v
                    first = first or (i, j)
        if first is not None:
            requested.append((f"{parts[0]}|{parts[1]}", v, first))
        else:
            notes.append(f"Group correlation '{key}' has no effect (a group is absent or has no common factor).")
    c, repaired = _nearest_correlation(c) if k else (c, False)
    if repaired:
        notes.append("Between-group correlation matrix was not positive definite and was repaired to the nearest "
                     "valid correlation matrix (eigenvalue clipping).")
    if requested:
        # the correlations in force are those of the (possibly repaired) matrix
        parts_txt = []
        for name, v, (i, j) in requested:
            eff = float(c[i, j])
            parts_txt.append(f"{name}={eff:+.2f}" if abs(eff - v) < 5e-3 else f"{name}={eff:+.2f} (requested {v:+.2f})")
        notes.append("Between-group factor correlations in force: " + ", ".join(parts_txt) + ".")
    keys = [f"factor:{fk}" for fk in factors] + _stream_keys(drivers)
    u = np.empty((n, len(keys)))
    for col, key in enumerate(keys):
        u[:, col] = _uniform_column(_stream(cfg.seed, key), n, cfg.method)
    z = stats.norm.ppf(np.clip(u, 1e-12, 1 - 1e-12))
    f = z[:, :k] @ np.linalg.cholesky(c).T if k else np.zeros((n, 0))
    e = z[:, k:]
    x = np.empty((n, len(drivers)))
    fidx = {key: i for i, key in enumerate(factors)}
    for j, d in enumerate(drivers):
        if d.factor is not None and d.loading > 0:
            a = d.loading
            x[:, j] = a * f[:, fidx[d.factor]] + math.sqrt(max(0.0, 1.0 - a * a)) * e[:, j]
        else:
            x[:, j] = e[:, j]
    return x, f, factors, c


# =============================================================================
# Statistics
# =============================================================================
def summarize(metric: str, unit: str, values: Sequence[float]) -> DistributionSummary:
    """Distribution summary (mean, std, P5..P95, min, max) of ``values`` (NaNs ignored)."""
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        a = np.array([math.nan])
    q = np.quantile(a, [0.05, 0.10, 0.50, 0.80, 0.90, 0.95])
    return DistributionSummary(metric=metric, unit=unit, mean=float(a.mean()),
                               std=float(a.std(ddof=1)) if a.size > 1 and np.ptp(a) > 0 else 0.0,
                               p5=float(q[0]), p10=float(q[1]),
                               p50=float(q[2]), p80=float(q[3]), p90=float(q[4]), p95=float(q[5]),
                               min=float(a.min()), max=float(a.max()))


def _bins_for(n: int) -> int:
    return int(min(20, max(10, round(math.sqrt(n) / 2.0))))


def binned_variance_share(index: np.ndarray, y: np.ndarray, *, bins: Optional[int] = None,
                          categorical: bool = False) -> float:
    """First-order variance share ``Var(E[Y | bin(index)]) / Var(Y)`` by equal-count quantile bins.

    The between-bin sum of squares is bias-corrected (``SS_b - (k - 1) MS_w``) so an irrelevant
    input scores about zero; the result is clipped to [0, 1].  ``categorical`` uses the index values
    as classes (e.g. ground classes).
    """
    y = np.asarray(y, dtype=float)
    n = y.size
    if n < 4:
        return 0.0
    total = float(((y - y.mean()) ** 2).sum())
    if total <= 0 or not math.isfinite(total):
        return 0.0
    if categorical:
        _, labels = np.unique(np.asarray(index), return_inverse=True)
    else:
        b = bins or _bins_for(n)
        order = np.argsort(np.asarray(index, dtype=float), kind="stable")
        labels = np.empty(n, dtype=int)
        labels[order] = (np.arange(n) * b) // n
    k = int(labels.max()) + 1
    counts = np.bincount(labels, minlength=k).astype(float)
    sums = np.bincount(labels, weights=y, minlength=k)
    mask = counts > 0
    means = sums[mask] / counts[mask]
    ss_b = float((counts[mask] * (means - y.mean()) ** 2).sum())
    kk = int(mask.sum())
    ss_w = max(total - ss_b, 0.0)
    ms_w = ss_w / max(n - kk, 1)
    share = (ss_b - (kk - 1) * ms_w) / total
    return float(min(1.0, max(0.0, share)))


def _ranks(a: np.ndarray) -> np.ndarray:
    return stats.rankdata(a)


def _spearman(x: np.ndarray, ry: np.ndarray) -> float:
    rx = _ranks(x)
    sx, sy = rx.std(), ry.std()
    if sx <= 0 or sy <= 0:
        return 0.0
    return float(np.mean((rx - rx.mean()) * (ry - ry.mean())) / (sx * sy))


def _group_index(members: Sequence[int], drivers: Sequence[_Driver], x: np.ndarray, f: np.ndarray,
                 fidx: Mapping[str, int], y: np.ndarray) -> tuple[np.ndarray, int, str]:
    """The binned index of one group: ``(index, number of regressors, estimator description)``.

    The regressors are the group's independent latent sources: each common factor once (its members'
    shared draw) plus the own latent of every member without a factor (independent measurement errors
    such as a user-confirmed tolerance, or the members of an rho = 0 group).  One regressor is used as is;
    several are combined by their correlation with the output (for independent regressors this is the
    least-squares linear projection).  For a group with rho < 1 only the common factor is credited (each
    member's idiosyncratic part is not): the share is then a lower bound.
    """
    regs: list[np.ndarray] = []
    seen: set[str] = set()
    n_factor = n_indep = 0
    for j in members:
        d = drivers[j]
        if d.factor is not None and d.loading > 0:
            if d.factor not in seen:
                seen.add(d.factor)
                regs.append(f[:, fidx[d.factor]])
                n_factor += 1
        else:
            regs.append(x[:, j])
            n_indep += 1
    if len(regs) == 1:
        return regs[0], 1, "group latent factor" if n_factor else "the group's only input latent"
    r = np.column_stack(regs)
    yc = y - y.mean()
    w = np.array([float(np.corrcoef(r[:, i], yc)[0, 1]) if np.std(r[:, i]) > 0 and np.std(yc) > 0 else 0.0
                  for i in range(r.shape[1])])
    parts = []
    if n_factor:
        parts.append(f"{n_factor} common factor(s)")
    if n_indep:
        parts.append(f"{n_indep} independent input latent(s)")
    return r @ np.nan_to_num(w), len(regs), "correlation-weighted sum of " + " and ".join(parts)


def _adjusted_share(index: np.ndarray, y: np.ndarray, p: int, *, bins: int, categorical: bool) -> float:
    """Binned share of ``index``, less the in-sample bias ``(p - 1)(1 - share) / n`` of ``p`` estimated weights."""
    s = binned_variance_share(index, y, bins=bins, categorical=categorical)
    if p > 1:
        s -= (p - 1) * (1.0 - s) / max(len(y), 1)
    return float(min(1.0, max(0.0, s)))


def _information_value(drivers: Sequence[_Driver], x: np.ndarray, f: np.ndarray, factor_keys: Sequence[str],
                       values: np.ndarray, y: np.ndarray, sens: Sequence[SensitivityItem],
                       action_of: Mapping[str, str], *, bins: int, width: float, currency: str, seed: int,
                       calibration_method: Optional[str]) -> list[dict[str, Any]]:
    """Groups ranked by variance share, with the action that would resolve them and its uncertainty.

    Each entry: ``group``, ``resolving_action`` (the action of the group's dominant input,
    :func:`input_action`), ``group_action`` (the group default), ``variance_share`` and its bootstrap
    standard error ``variance_share_se`` (:data:`BOOTSTRAP_REPS` resamples of the rows, index held),
    ``rank`` plus ``rank_range`` / ``tied_with`` (groups whose share is not distinguishable at about
    2 standard errors of the difference - the ranking can swap between seeds), the P10-P90 width and the
    width the group accounts for, ``n_inputs``, ``top_inputs`` and the estimator used.
    """
    n = y.size
    fidx = {k: i for i, k in enumerate(factor_keys)}
    rng = _stream(seed, "bootstrap:information_value")
    rows = [rng.integers(0, n, n) for _ in range(BOOTSTRAP_REPS)] if n >= 20 else []
    info: list[dict[str, Any]] = []
    for g in GROUPS:
        members = [j for j, d in enumerate(drivers) if d.spec.group == g]
        if not members:
            continue
        categorical = g == "ground"
        if categorical:
            index, p, how = values[:, members[0]], 1, "ground class"
        else:
            index, p, how = _group_index(members, drivers, x, f, fidx, y)
        share = _adjusted_share(index, y, p, bins=bins, categorical=categorical)
        boots = [_adjusted_share(index[r], y[r], p, bins=bins, categorical=categorical) for r in rows]
        se = float(np.std(boots, ddof=1)) if len(boots) > 1 else math.nan
        ranked = [it for it in sens if it.group == g]
        top = [it.input_name for it in ranked][:3]
        default = (SCALE_ACTION_CALIBRATED if g == "scale" and calibration_method in _CALIBRATED_METHODS
                   else RESOLVING_ACTIONS.get(g, ""))
        if g == "hidden_geometry":
            # every hidden input has its own evidence (depth / pitch -> side elevation or plan, rear glazing ->
            # rear elevation, FFL -> site measurement ...): name the one of the strongest input
            lead = ranked[0] if ranked else None
        else:
            # scale: the dominant input (e.g. a user-confirmed measurement) names the action only when the
            # group clearly matters (above 1 % and 2 standard errors) and that input carries most of it;
            # otherwise the calibration-aware default
            clear = share >= max(_LEAD_MIN_SHARE, 2.0 * (se if math.isfinite(se) else 0.0))
            lead = (ranked[0] if ranked and clear and ranked[0].variance_share >= _LEAD_FRACTION * share
                    else None)
        action = action_of.get(lead.input_name, default) if lead is not None else default
        others = list(dict.fromkeys(action_of.get(it.input_name, default) for it in ranked[:3]
                                    if it.variance_share >= _LEAD_MIN_SHARE)) if share >= _LEAD_MIN_SHARE else []
        info.append({
            "group": g,
            "resolving_action": action,
            "group_action": RESOLVING_ACTIONS.get(g, ""),
            "other_actions": [a for a in others if a != action],
            "variance_share": share,
            "variance_share_se": se,
            "p10_p90_width": width,
            "p10_p90_width_accounted": width * (1.0 - math.sqrt(max(0.0, 1.0 - share))),
            "currency": currency,
            "n_inputs": len(members),
            "top_inputs": top,
            "estimator": how,
            "kind": "within_scenario",
        })
    info.sort(key=lambda r: (-r["variance_share"], r["group"]))
    for rank, r in enumerate(info, 1):
        r["rank"] = rank
    for r in info:
        tied = []
        above = below = 0
        for o in info:
            if o is r:
                continue
            se2 = (r["variance_share_se"] or 0.0) ** 2 + (o["variance_share_se"] or 0.0) ** 2
            band = 2.0 * math.sqrt(se2) if math.isfinite(se2) else 0.0
            diff = o["variance_share"] - r["variance_share"]
            if abs(diff) <= band:
                tied.append(o["group"])
            elif diff > 0:
                above += 1
            else:
                below += 1
        r["tied_with"] = tied
        r["rank_range"] = [above + 1, len(info) - below]
    return info


# =============================================================================
# Public entry point
# =============================================================================
def simulate_uncertainty(twin: BuildingTwin, library: AssemblyLibrary, rate_book: RateBook,
                         cost_params: CostParameters, settings: ProjectSettings, *,
                         config: Optional[SimulationConfig] = None,
                         calibration: Optional[ScaleCalibration] = None,
                         assumptions: Union[AssumptionLibrary, TakeoffAssumptions, None] = None,
                         scenario_id: Optional[str] = None,
                         crew_sizes: Optional[Mapping[str, float]] = None,
                         fixed_foundation: Optional[str] = None) -> SimulationResult:
    """Sample one coherent house ``config.n_samples`` times and summarise cost / quantity uncertainty.

    ``calibration`` (recommended) lets the image scale drive the observed roof rises, wall plates and
    opening bottoms of coupled blocks and selects the scale group's resolving action; ``assumptions``
    supplies the partition-length allowance (an :class:`AssumptionLibrary` or
    :class:`TakeoffAssumptions`); ``crew_sizes`` is passed to the programme.  ``fixed_foundation`` names
    who fixed the foundation option (e.g. ``"build scenario S1"``): the ground classes are then not
    sampled and every sample keeps the twin's foundation.  Raises ``ValueError`` when the twin's geometry
    is incomplete.  Deterministic for a given ``config.seed``.  See the module docstring for method and
    boundaries.
    """
    t0 = time.perf_counter()
    cfg = config if config is not None else SimulationConfig()
    notes: list[str] = []
    model = _HouseModel(twin, library, rate_book, cost_params, settings, takeoff=_takeoff(assumptions),
                        crew_sizes=crew_sizes, fixed_foundation=fixed_foundation)
    drivers, base = _all_drivers(model, cfg, calibration, notes)
    n = cfg.n_samples
    x, f, factor_keys, _ = _latents(drivers, cfg, notes)
    u = stats.norm.cdf(x)
    values = np.empty_like(u)
    for j, d in enumerate(drivers):
        v = np.asarray(d.ppf(np.clip(u[:, j], 1e-12, 1 - 1e-12)), dtype=float)
        v = np.clip(v, d.clip[0], d.clip[1])
        if d.integer and d.spec.group != "ground":
            v = np.round(v)
        values[:, j] = v

    outputs: list[dict[str, Any]] = []
    for i in range(n):
        s = _Sample()
        for j, d in enumerate(drivers):
            d.apply(float(values[i, j]), s)
        outputs.append(model.evaluate(s))

    cur = settings.currency
    y = np.array([o[COST_METRIC] for o in outputs], dtype=float)
    metrics = [summarize(m, cur if unit == "CUR" else unit, [o[m] for o in outputs]) for m, unit in OUTPUT_METRICS]
    samples = {k: [float(o[k]) for o in outputs] for k in _SAMPLE_KEYS}
    for b in twin.blocks:
        for dim in ("width_m", "depth_m"):
            key = f"{b.block_id}.{dim}"
            metrics.append(summarize(key, "m", [o[key] for o in outputs]))
            samples[key] = [float(o[key]) for o in outputs]

    # ---------------------------------------------------------------- sensitivity
    ry = _ranks(y)
    bins = _bins_for(n)
    cal_method = calibration.method if calibration is not None else None
    sens: list[SensitivityItem] = []
    action_of: dict[str, str] = {}
    for j, d in enumerate(drivers):
        rho = _spearman(values[:, j], ry)
        share = binned_variance_share(values[:, j] if d.spec.group == "ground" else x[:, j], y, bins=bins,
                                      categorical=d.spec.group == "ground")
        action_of[d.spec.name] = input_action(d.spec, cal_method)
        sens.append(SensitivityItem(input_name=d.spec.name, group=d.spec.group, spearman_rho=rho,
                                    variance_share=share, resolving_action=action_of[d.spec.name]))
    sens.sort(key=lambda it: (-it.variance_share, -abs(it.spearman_rho), it.input_name))

    q10, q90 = np.quantile(y, [0.10, 0.90]) if n else (math.nan, math.nan)
    width = float(q90 - q10)
    info = _information_value(drivers, x, f, factor_keys, values, y, sens, action_of, bins=bins, width=width,
                              currency=cur, seed=cfg.seed, calibration_method=cal_method)

    conditional: dict[str, DistributionSummary] = {}
    ground_driver = next((j for j, d in enumerate(drivers) if d.spec.group == "ground"), None)
    if ground_driver is not None:
        classes = drivers[ground_driver].classes
        cls_idx = values[:, ground_driver].astype(int)
        samples["ground_class"] = [float(v) for v in cls_idx]
        for k, cls in enumerate(classes):
            sel = y[cls_idx == k]
            if sel.size >= 2:
                conditional[cls] = summarize(f"{COST_METRIC} | ground={cls} ({model.ground_options[k]})", cur, sel)

    # ---------------------------------------------------------------- notes
    elapsed = time.perf_counter() - t0
    sel = twin.assemblies
    notes[:0] = [
        f"One coherent house per sample: twin '{twin.twin_id}' v{twin.version} (hypothesis "
        f"{twin.source_hypothesis_id or 'n/a'}; external wall '{sel.external_wall}', foundation '{sel.foundation}'). "
        "No averaging across hypotheses or construction assemblies - compare those with compare_build_scenarios.",
        f"Sampling: {'Latin hypercube' if cfg.method == 'lhs' else 'Monte Carlo'} with one PCG64 stream per input "
        f"(common random numbers across scenarios with the same seed), n={n}, seed={cfg.seed}; {len(drivers)} "
        f"inputs in {len({d.spec.group for d in drivers})} groups.",
        "Gaussian copula, one-factor model per group with rho = "
        + ", ".join(f"{g} {GROUP_RHO[g]:.1f}" for g in GROUPS)
        + " (scale: comonotonic within one image's correlation group).",
        "Per sample: geometry (fast path) -> quantities -> productivity -> programme -> logistics -> cost with "
        "programme weeks driving time-related preliminaries.",
        f"Deterministic base (all inputs at their mode, selected foundation): {cur} {base[COST_METRIC]:,.0f} "
        f"construction incl. contingency.",
        "Held fixed: storey counts, the hypothesis and assembly selection, library allowance quantities, take-off "
        "substructure priors and commercial fractions (fees, contingency, overhead, margin).",
        f"Variance shares: quantile binning with {bins} bins, bias-corrected; group shares may sum to more than "
        "one when groups are correlated. P10-P90 width accounted = W x (1 - sqrt(1 - share)) (normal approx.). "
        f"Each group share has a bootstrap standard error ({BOOTSTRAP_REPS} resamples); groups listed in "
        "'tied_with' are not distinguishable at this sample size and may swap ranks with another seed.",
        "Per-input Spearman rho and shares include effects transmitted through correlated inputs (shared group "
        "factors), so each input of a correlated group (e.g. unit prices) shows part of the group's effect; rank "
        "evidence by group (information_value).",
        f"Runtime {elapsed:.1f} s.",
    ]
    if model.excluded_openings:
        notes.append(f"{len(model.excluded_openings)} opening(s) with unknown size or position are excluded from the "
                     f"sampled geometry: {', '.join(model.excluded_openings[:6])}.")
    if model.geometry_fallbacks:
        notes.append(f"{model.geometry_fallbacks} sample(s) produced an invalid footprint and used the base footprint "
                     "geometry (other sampled values kept).")
    if model.rise_misses:
        notes.append(f"{model.rise_misses} sample(s): a hip roof with a fixed (user-confirmed / observed) pitch would "
                     "have needed a span longer than its other plan side; the span was capped and the pitch kept, so "
                     "the observed roof rise is not reproduced there.")
    unresolved = sum(1 for o in outputs if o["unresolved"])
    if unresolved:
        notes.append(f"{unresolved} sample(s) had unresolved cost items (missing rates or quantities); their totals "
                     "exclude those items.")
    if base["unresolved"]:
        notes.append(f"The base estimate has {base['unresolved']} unresolved item(s); totals exclude them.")
    if any(d.spec.group == "unit_prices" for d in drivers) and any(
            r.source_type.value == "fictional_demo" for r in rate_book.rates):
        notes.append("Rate book contains FICTIONAL demo prices; cost distributions illustrate the method only.")
    fdn_txt = (f"foundation '{sel.foundation}' (fixed by {fixed_foundation})" if fixed_foundation
               else f"foundation '{sel.foundation}' or the ground-class options" if ground_driver is not None
               else f"foundation '{sel.foundation}'")
    interval = (f"{INTERVAL_TYPE} This one: conditional on geometry hypothesis "
                f"{twin.source_hypothesis_id or 'n/a'} (twin '{twin.twin_id}' v{twin.version}) and the selected "
                f"assemblies (external wall '{sel.external_wall}', {fdn_txt}).")
    return SimulationResult(scenario_id=scenario_id or twin.twin_id, config=cfg, n_samples=n, metrics=metrics,
                            samples=samples, inputs=[d.spec for d in drivers], sensitivity=sens,
                            information_value=info, conditional_on_ground=conditional, interval_type=interval,
                            notes=notes)
