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
:func:`housebuilder_vision.simulation.scenarios.compare_build_scenarios`.

Uncertain inputs (:class:`UncertainInput`) and their groups
-----------------------------------------------------------
Inputs are discovered, never invented:

``scale``
    Every uncertain twin value whose ``correlation_group`` starts with
    ``"scale:"`` (dimensions converted from pixels of the same image) plus the
    calibration's ``metres_per_pixel`` when a calibration is passed.  Values in
    the same correlation group are sampled **comonotonically** (one latent draw
    per group, rho = 1).  Evidence-derived values without a correlation group
    (user-confirmed frontage tolerance, observed pitch, opening offsets) are
    measurement errors in the same group but with their own independent draw.
``hidden_geometry``
    ``ASSUMED`` geometric values (hidden depths, roof pitch priors, overhangs,
    FFL, extension sizes), the hidden-facade glazing ratios, the assumed number
    of bathrooms and the partition-length allowance (internal layout).
    Independent (rho = 0).
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
    foundation option (:data:`GROUND_FOUNDATIONS`: good -> the selected option,
    variable made ground -> deep trench fill, poor/soft ground -> piled
    allowance).  Skipped when the foundation selection is user-confirmed.
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
* **Attached blocks stay attached.**  The base footprint is analysed once: every
  block touching an already placed block keeps that contact and its alignment
  (front/rear or left/right flush, otherwise the base offset).  Their origins
  are derived, not sampled.
* **Depth-pitch coupling.**  When a block's roof span runs along its depth
  (gable with ridge parallel to the frontage, or hip) and the front elevation
  shows its roof rise (the depth or pitch carries image evidence), the rise is
  an observation: ``rise = k x depth x tan(pitch)`` (k = 1/2).  If the depth is
  assumed, the pitch prior is sampled and the depth derived
  ``depth = rise / (k tan(pitch))`` (clipped to the depth range); if the depth
  is evidence-derived, it is sampled and the pitch derived.  The rise scales
  with the sampled ``metres_per_pixel`` of its correlation group.
* **Hidden-facade openings follow their rule.**  Rule-generated windows keep
  their count; their widths scale so the glazed area tracks
  ``ratio x hidden wall area - rule doors`` relative to the base, and their
  positions scale with the wall length.
* Ground classes switch the foundation option of the twin (pre-built once per
  option with ``apply_construction_assemblies``; basis ASSUMED).

Sampling
--------
``config.method == "lhs"``: ``scipy.stats.qmc.LatinHypercube`` on the
independent normal drivers (seeded); ``"mc"``: ``numpy`` ``Generator(PCG64(seed))``.
Dependence is a Gaussian copula: each input's latent normal is
``x_i = a_g F_g + sqrt(1 - a_g^2) e_i`` with ``a_g = sqrt(rho_g)`` (one-factor
model, :data:`GROUP_RHO`); group factors ``F`` are correlated with
``config.group_correlations`` (Cholesky, repaired to the nearest positive
semi-definite correlation matrix when needed).  Latents map to marginals with
``scipy.stats``: uniform, triangular, PERT (beta, lambda = 4), normal and
lognormal with low/high read as P5/P95.  Fully reproducible for a given seed.

Outputs
-------
:class:`DistributionSummary` for the cost boundaries, areas, concrete, labour
hours, programme weeks and every block's width / depth; samples (cost boundaries,
GIA, programme weeks, block dimensions and the ground class index); Spearman rank
correlation of every input with construction cost; first-order variance shares
by quantile binning (``Var(E[Y | bin]) / Var(Y)``, 10-20 equal-count bins,
small-sample bias corrected).  For a group the binned index is its latent
factor when the group has one common factor, the ground class for ``ground``,
and otherwise the correlation-weighted sum of its inputs' latents (a linear
projection, exact for independent inputs with additive effects).
``information_value`` ranks groups by variance share with the action that
would resolve them and the P10-P90 width they account for
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
import math
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence, Union

import numpy as np
from scipy import stats
from scipy.stats import qmc

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
from .logistics import plan_deliveries
from .programme import build_programme

__all__ = [
    "GROUPS",
    "GROUP_RHO",
    "RESOLVING_ACTIONS",
    "GROUND_FOUNDATIONS",
    "PRODUCTIVITY_MULTIPLIER",
    "WASTE_MULTIPLIER",
    "COST_METRIC",
    "OUTPUT_METRICS",
    "INTERVAL_TYPE",
    "simulate_uncertainty",
    "discover_inputs",
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

#: The action that would resolve (most of) each group's uncertainty.
RESOLVING_ACTIONS: dict[str, str] = {
    "scale": "Confirm a reference dimension such as the measured frontage",
    "hidden_geometry": "Upload a side/rear elevation or a dimensioned floor plan",
    "ground": "Commission a site/ground investigation",
    "unit_prices": "Obtain supplier quotations",
    "labour_rates": "Agree contractor labour rates",
    "labour_productivity": "Agree a contractor programme / productivity data",
    "lead_time": "Confirm window/door lead times with suppliers",
    "waste": "Confirm waste management plan",
}

#: Ground class -> foundation option id (``None`` = the twin's selected option).  Classes not listed
#: here are matched to the first library option whose ``suitable_ground`` names them.
GROUND_FOUNDATIONS: dict[str, Optional[str]] = {
    "good_clay_or_gravel": None,
    "variable_made_ground": "fdn_deep_trench_fill",
    "poor_soft_ground": "fdn_piled_allowance",
}

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
    "confidence intervals."
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


@dataclass
class _Attach:
    child: int
    parent: int
    relation: str  # right_of | left_of | behind | in_front
    align: str  # front | rear | left | right | offset
    delta: float


@dataclass
class _Coupling:
    block: int
    mode: str  # pitch_primary | depth_primary
    k: float
    base_rise: float
    depth_lo: float
    depth_hi: float
    group: Optional[str]


@dataclass
class _RuleSide:
    block: int
    side: Side
    ratio_key: str
    windows: list[int]
    doors: list[int]
    door_area: float
    base_target: float
    base_side_len: float


def _round(v: Optional[float], nd: int = 6) -> Optional[float]:
    return None if v is None else round(float(v), nd)


def _tv_key(field_label: str, tv: TrackedValue) -> tuple:
    return (field_label, tv.basis.value, _round(tv.value), _round(tv.low), _round(tv.high), tv.distribution.value,
            tv.correlation_group or "", tv.source, tv.note)


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


# =============================================================================
# The house model (base state + one-sample evaluation)
# =============================================================================
class _HouseModel:
    """Precomputed base state of the twin; ``evaluate`` builds and prices one sampled house."""

    def __init__(self, twin: BuildingTwin, library: AssemblyLibrary, rate_book: RateBook,
                 cost_params: CostParameters, settings: ProjectSettings, *,
                 takeoff: TakeoffAssumptions, crew_sizes: Optional[Mapping[str, float]]) -> None:
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
        self.couplings = self._couplings()
        self.rule_sides = self._rule_sides()
        self.concrete_ids = {m.material_id for m in library.materials
                             if m.category == "concrete" and "screed" not in m.material_id}
        self.foundation_twins: dict[str, BuildingTwin] = {twin.assemblies.foundation: twin}
        self.ground_options: list[str] = []
        self.geometry_fallbacks = 0

    # ------------------------------------------------------------ footprint analysis
    def _attachments(self) -> tuple[list[_Attach], set[int]]:
        bps = self.base_bp
        tol = 1e-4
        placed = [self.root]
        out: list[_Attach] = []
        remaining = [i for i in range(len(bps)) if i != self.root]
        progress = True
        while remaining and progress:
            progress = False
            for i in list(remaining):
                b = bps[i].rect
                for j in placed:
                    n = bps[j].rect
                    ov_y = min(b.y1, n.y1) - max(b.y0, n.y0)
                    ov_x = min(b.x1, n.x1) - max(b.x0, n.x0)
                    rel = None
                    if ov_y > tol and abs(b.x0 - n.x1) < tol:
                        rel = "right_of"
                    elif ov_y > tol and abs(b.x1 - n.x0) < tol:
                        rel = "left_of"
                    elif ov_x > tol and abs(b.y0 - n.y1) < tol:
                        rel = "behind"
                    elif ov_x > tol and abs(b.y1 - n.y0) < tol:
                        rel = "in_front"
                    if rel is None:
                        continue
                    if rel in ("right_of", "left_of"):
                        if abs(b.y0 - n.y0) < tol:
                            align, delta = "front", 0.0
                        elif abs(b.y1 - n.y1) < tol:
                            align, delta = "rear", 0.0
                        else:
                            align, delta = "offset", b.y0 - n.y0
                    else:
                        if abs(b.x0 - n.x0) < tol:
                            align, delta = "left", 0.0
                        elif abs(b.x1 - n.x1) < tol:
                            align, delta = "right", 0.0
                        else:
                            align, delta = "offset", b.x0 - n.x0
                    out.append(_Attach(i, j, rel, align, delta))
                    placed.append(i)
                    remaining.remove(i)
                    progress = True
                    break
        return out, set(remaining)

    def _couplings(self) -> dict[int, _Coupling]:
        out: dict[int, _Coupling] = {}
        for i, (b, bp) in enumerate(zip(self.twin.blocks, self.base_bp)):
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
            pitch_ev = p_tv.basis in (Basis.OBSERVED, Basis.USER_CONFIRMED)
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
                               group=d_tv.correlation_group or p_tv.correlation_group)
        return out

    def _ext_side_lengths(self, bps: Sequence[BlockParams]) -> dict[tuple[int, Side], float]:
        rects = [b.rect for b in bps]
        pcs = side_pieces(rects)
        idx = {b.block_id: i for i, b in enumerate(bps)}
        out: dict[tuple[int, Side], float] = {}
        for p in pcs:
            if p.external:
                key = (idx[p.rid], p.side)
                out[key] = out.get(key, 0.0) + p.length
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
            lengths = self._ext_side_lengths(self.base_bp)
        except GeometryError:
            return []
        out: list[_RuleSide] = []
        for (bi, side), g in groups.items():
            if not g["windows"] or g["ratio"] is None:
                continue
            bp = self.base_bp[bi]
            ratio = float(getattr(self.twin.hidden, g["ratio"]).value or 0.0)
            door_area = sum(self.base_op[k].width * self.base_op[k].height for k in g["doors"])
            h = bp.storeys * bp.floor_to_floor
            target = ratio * lengths.get((bi, side), 0.0) * h - door_area
            if target <= 1e-9:
                continue
            full = bp.width if side in (Side.FRONT, Side.REAR) else bp.depth
            out.append(_RuleSide(bi, side, g["ratio"], g["windows"], g["doors"], door_area, target, full))
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
        for c in self.couplings.values():
            bp = bps[c.block]
            rise = c.base_rise * s.scale_ratio.get(c.group or "", 1.0)
            if c.mode == "pitch_primary":
                t = math.tan(math.radians(min(max(bp.pitch_deg, _PITCH_LIMITS[0]), _PITCH_LIMITS[1])))
                depth = rise / (c.k * t)
                bp.depth = min(max(depth, c.depth_lo), c.depth_hi)
            bp.pitch_deg = min(max(math.degrees(math.atan(rise / (c.k * max(bp.depth, _MIN_DIM)))),
                                   _PITCH_LIMITS[0]), _PITCH_LIMITS[1])
        for a in self.attachments:
            b, n = bps[a.child], bps[a.parent]
            if a.relation == "right_of":
                b.x0 = n.x0 + n.width
            elif a.relation == "left_of":
                b.x0 = n.x0 - b.width
            elif a.relation == "behind":
                b.y0 = n.y0 + n.depth
            else:
                b.y0 = n.y0 - b.depth
            if a.relation in ("right_of", "left_of"):
                b.y0 = n.y0 if a.align == "front" else (n.y0 + n.depth - b.depth if a.align == "rear"
                                                         else n.y0 + a.delta)
            else:
                b.x0 = n.x0 if a.align == "left" else (n.x0 + n.width - b.width if a.align == "right"
                                                       else n.x0 + a.delta)
        ops = [copy.copy(o) for o in self.base_op]
        for (oi, attr), v in s.opening.items():
            setattr(ops[oi], attr, v)
        if self.rule_sides:
            lengths = self._ext_side_lengths(bps)  # raises GeometryError on overlap
            for rs in self.rule_sides:
                bp = bps[rs.block]
                ratio = s.ratios.get(rs.ratio_key, float(getattr(self.twin.hidden, rs.ratio_key).value or 0.0))
                target = ratio * lengths.get((rs.block, rs.side), 0.0) * bp.storeys * bp.floor_to_floor - rs.door_area
                f = max(0.0, target) / rs.base_target
                full = bp.width if rs.side in (Side.FRONT, Side.REAR) else bp.depth
                lf = full / rs.base_side_len if rs.base_side_len > 0 else 1.0
                for k in rs.windows:
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
            if coupling is not None and ((coupling.mode == "pitch_primary" and attr == "depth")
                                         or (coupling.mode == "depth_primary" and attr == "pitch_deg")):
                derived.append(f"{b.block_id}.{label}")
                continue
            desc = _short(tv.note or tv.source)
            if coupling is not None and attr in ("depth", "pitch_deg"):
                other = "depth" if attr == "pitch_deg" else "roof pitch"
                desc = (f"{other} derived from the observed rise (rise = {coupling.k:g} x depth x tan(pitch)). "
                        + desc)
            lo = 0.0 if attr in ("eaves_overhang", "verge_overhang", "parapet", "ffl") else _MIN_DIM
            clip = (_PITCH_LIMITS[0], _PITCH_LIMITS[1]) if attr == "pitch_deg" else (
                (-math.inf, math.inf) if attr in ("x0", "y0") else (lo, math.inf))
            key = (_tv_key(label, tv),) if not tv.correlation_group else (_tv_key(label, tv), b.block_id)

            def setter(v: float, s: _Sample, _bi: int = bi, _attr: str = attr) -> None:
                s.block[(_bi, _attr)] = v

            add(key, tv, f"{b.block_id}.{label}", f"block:{b.block_id}.{'.'.join(path)}", desc, setter, clip)
    for oi, o in enumerate(twin.openings):
        if o.hidden_side_rule:
            continue
        for attr, name in _OPENING_FIELDS:
            tv = getattr(o, name)
            if _tv_marginal(tv) is None:
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
    elif model.couplings:
        notes.append("No calibration passed: the observed roof rise of depth-pitch coupled blocks is held at its "
                     "base value (scale uncertainty then reaches depth only through the sampled pitch).")
    if derived:
        notes.append("Derived per sample (not sampled): " + ", ".join(sorted(set(derived)))
                     + " - attached blocks keep their contact and alignment; coupled depth/pitch follow the "
                     "observed roof rise.")

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
        spec = UncertainInput(name=name, group=group, target="; ".join(g["targets"])[:500],
                              distribution=tv.distribution.value, low=tv.low, mode=tv.value, high=tv.high,
                              unit=tv.unit, basis=tv.basis, description=_short(desc, 400))
        drivers.append(_Driver(spec=spec, ppf=_tv_marginal(tv), apply=apply, clip=g["clip"], integer=g["integer"],
                               factor=(tv.correlation_group if group == "scale" and tv.correlation_group
                                       else None)))
    return drivers


def _ground_driver(model: _HouseModel, config: SimulationConfig, notes: list[str]) -> Optional[_Driver]:
    """Discrete ground-class input (sets ``model.ground_options``), or ``None``."""
    if "ground" not in config.include_groups:
        return None
    sel = model.twin.assemblies
    if sel.basis.get("foundation") == Basis.USER_CONFIRMED:
        notes.append(f"Ground classes not sampled: the foundation option is user-confirmed ('{sel.foundation}').")
        return None
    fids = {f.option_id for f in model.library.foundations}
    classes: list[str] = []
    probs: list[float] = []
    options: list[str] = []
    for cls, p in config.ground_classes.items():
        if p is None or not math.isfinite(float(p)) or float(p) <= 0:
            continue
        if cls in GROUND_FOUNDATIONS:
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
                    assumptions: Union[AssumptionLibrary, TakeoffAssumptions, None] = None) -> list[UncertainInput]:
    """The uncertain inputs :func:`simulate_uncertainty` would sample (no sampling done)."""
    cfg = config or SimulationConfig()
    model = _HouseModel(twin, library, rate_book, cost_params, settings, takeoff=_takeoff(assumptions),
                        crew_sizes=None)
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


def _uniforms(n: int, d: int, cfg: SimulationConfig) -> np.ndarray:
    if d == 0:
        return np.zeros((n, 0))
    if cfg.method == "lhs":
        try:
            sampler = qmc.LatinHypercube(d=d, rng=np.random.Generator(np.random.PCG64(cfg.seed)))
        except TypeError:  # older SciPy: ``seed`` keyword
            sampler = qmc.LatinHypercube(d=d, seed=np.random.Generator(np.random.PCG64(cfg.seed)))
        return sampler.random(n)
    return np.random.Generator(np.random.PCG64(cfg.seed)).random((n, d))


def _latents(drivers: Sequence[_Driver], cfg: SimulationConfig, notes: list[str]
             ) -> tuple[np.ndarray, np.ndarray, list[str], np.ndarray]:
    """Correlated latent normals X (n x D), factor values F (n x K), factor keys, factor correlation."""
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
    k = len(factors)
    group_of = {f: (f.split(":", 1)[0] if f.startswith("scale:") else f) for f in factors}
    c = np.eye(k)
    used_pairs: list[str] = []
    for key, val in (cfg.group_correlations or {}).items():
        parts = [p.strip() for p in str(key).split("|")]
        if len(parts) != 2 or not all(p in GROUPS for p in parts) or val is None or not math.isfinite(float(val)):
            notes.append(f"Group correlation '{key}' ignored (expected 'group_a|group_b' with known groups).")
            continue
        v = max(-0.99, min(0.99, float(val)))
        hit = False
        for i, fi in enumerate(factors):
            for j, fj in enumerate(factors):
                if i != j and {group_of[fi], group_of[fj]} == set(parts) and group_of[fi] != group_of[fj]:
                    c[i, j] = v
                    hit = True
        if hit:
            used_pairs.append(f"{parts[0]}|{parts[1]}={v:+.2f}")
        else:
            notes.append(f"Group correlation '{key}' has no effect (a group is absent or has no common factor).")
    c, repaired = _nearest_correlation(c) if k else (c, False)
    if repaired:
        notes.append("Between-group correlation matrix was not positive definite and was repaired to the nearest "
                     "valid correlation matrix (eigenvalue clipping).")
    if used_pairs:
        notes.append("Between-group factor correlations: " + ", ".join(used_pairs) + ".")
    dim = k + len(drivers)
    u = _uniforms(n, dim, cfg)
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


# =============================================================================
# Public entry point
# =============================================================================
def simulate_uncertainty(twin: BuildingTwin, library: AssemblyLibrary, rate_book: RateBook,
                         cost_params: CostParameters, settings: ProjectSettings, *,
                         config: Optional[SimulationConfig] = None,
                         calibration: Optional[ScaleCalibration] = None,
                         assumptions: Union[AssumptionLibrary, TakeoffAssumptions, None] = None,
                         scenario_id: Optional[str] = None,
                         crew_sizes: Optional[Mapping[str, float]] = None) -> SimulationResult:
    """Sample one coherent house ``config.n_samples`` times and summarise cost / quantity uncertainty.

    ``calibration`` (recommended) lets the image scale drive the observed roof rises of
    depth-pitch coupled blocks; ``assumptions`` supplies the partition-length allowance (an
    :class:`AssumptionLibrary` or :class:`TakeoffAssumptions`); ``crew_sizes`` is passed to the
    programme.  Raises ``ValueError`` when the twin's geometry is incomplete.  Deterministic for a
    given ``config.seed``.  See the module docstring for method and boundaries.
    """
    t0 = time.perf_counter()
    cfg = config if config is not None else SimulationConfig()
    notes: list[str] = []
    model = _HouseModel(twin, library, rate_book, cost_params, settings, takeoff=_takeoff(assumptions),
                        crew_sizes=crew_sizes)
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
    sens: list[SensitivityItem] = []
    for j, d in enumerate(drivers):
        rho = _spearman(values[:, j], ry)
        share = binned_variance_share(values[:, j] if d.spec.group == "ground" else x[:, j], y, bins=bins,
                                      categorical=d.spec.group == "ground")
        sens.append(SensitivityItem(input_name=d.spec.name, group=d.spec.group, spearman_rho=rho,
                                    variance_share=share, resolving_action=RESOLVING_ACTIONS.get(d.spec.group, "")))
    sens.sort(key=lambda it: (-it.variance_share, -abs(it.spearman_rho), it.input_name))

    q10, q90 = np.quantile(y, [0.10, 0.90]) if n else (math.nan, math.nan)
    width = float(q90 - q10)
    info: list[dict[str, Any]] = []
    fidx = {k: i for i, k in enumerate(factor_keys)}
    for g in GROUPS:
        members = [j for j, d in enumerate(drivers) if d.spec.group == g]
        if not members:
            continue
        mfactors = {drivers[j].factor for j in members if drivers[j].factor is not None and drivers[j].loading > 0}
        if g == "ground":
            share = binned_variance_share(values[:, members[0]], y, categorical=True)
            how = "ground class"
        elif len(mfactors) == 1:
            share = binned_variance_share(f[:, fidx[mfactors.pop()]], y, bins=bins)
            how = "group latent factor"
        else:
            yc = y - y.mean()
            w = np.array([float(np.corrcoef(x[:, j], yc)[0, 1]) if np.std(x[:, j]) > 0 and np.std(yc) > 0 else 0.0
                          for j in members])
            index = x[:, members] @ np.nan_to_num(w)
            share = binned_variance_share(index, y, bins=bins)
            how = "correlation-weighted sum of the group's latents"
        top = [it.input_name for it in sens if it.group == g][:3]
        info.append({
            "group": g,
            "resolving_action": RESOLVING_ACTIONS.get(g, ""),
            "variance_share": share,
            "p10_p90_width": width,
            "p10_p90_width_accounted": width * (1.0 - math.sqrt(max(0.0, 1.0 - share))),
            "currency": cur,
            "n_inputs": len(members),
            "top_inputs": top,
            "estimator": how,
        })
    info.sort(key=lambda r: (-r["variance_share"], r["group"]))
    for rank, r in enumerate(info, 1):
        r["rank"] = rank

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
        f"Sampling: {'Latin hypercube (scipy.stats.qmc)' if cfg.method == 'lhs' else 'Monte Carlo (PCG64)'}, "
        f"n={n}, seed={cfg.seed}; {len(drivers)} inputs in {len({d.spec.group for d in drivers})} groups.",
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
        "one when groups are correlated. P10-P90 width accounted = W x (1 - sqrt(1 - share)) (normal approx.).",
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
    unresolved = sum(1 for o in outputs if o["unresolved"])
    if unresolved:
        notes.append(f"{unresolved} sample(s) had unresolved cost items (missing rates or quantities); their totals "
                     "exclude those items.")
    if base["unresolved"]:
        notes.append(f"The base estimate has {base['unresolved']} unresolved item(s); totals exclude them.")
    if any(d.spec.group == "unit_prices" for d in drivers) and any(
            r.source_type.value == "fictional_demo" for r in rate_book.rates):
        notes.append("Rate book contains FICTIONAL demo prices; cost distributions illustrate the method only.")
    return SimulationResult(scenario_id=scenario_id or twin.twin_id, config=cfg, n_samples=n, metrics=metrics,
                            samples=samples, inputs=[d.spec for d in drivers], sensitivity=sens,
                            information_value=info, conditional_on_ground=conditional, interval_type=INTERVAL_TYPE,
                            notes=notes)
