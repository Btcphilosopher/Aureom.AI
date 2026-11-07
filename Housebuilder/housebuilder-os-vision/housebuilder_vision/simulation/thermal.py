"""Simplified steady-state thermal calculations: U-values, ground floors and heat loss.

What this module does
---------------------
* :func:`u_value` - thermal transmittance of a plane assembly in the style of the
  BS EN ISO 6946 *combined method*:

  - each thermal layer contributes ``R = d / lambda`` (thickness / conductivity);
  - a layer with a repeating thermal bridge (``AssemblyLayer.bridging``, e.g. timber
    studs in mineral wool) is handled with the upper / lower bound pair:
    *upper bound* ``R'`` = parallel heat-flow paths through the **whole** assembly
    (``1/R' = sum_s f_s / R_s`` over sections; with several bridged layers the
    section fractions are taken as independent products - an approximation of the
    real section geometry); *lower bound* ``R''`` = series layers in which each
    bridged layer has the area-weighted equivalent conductivity
    ``lambda'' = (1 - f) lambda_insulation + f lambda_bridge``; and
    ``R_T = (R' + R'') / 2``, ``U = 1 / R_T``;
  - layers on the outside of a **ventilated** air layer (a ``CAVITY`` / ``BATTENS``
    layer that is not in the thermal calculation, or whose name says "ventilated")
    are ignored together with that air layer, and the external surface resistance
    is replaced by the internal one (``Rse = Rsi``), as ISO 6946 prescribes for
    well-ventilated air layers.  For a cold pitched roof this means the ventilated
    loft and everything above it are ignored; ISO 6946's additional roof-space
    resistance is conservatively not credited;
  - unventilated cavities enter as pseudo-materials with an equivalent
    conductivity (the bundled ``air_cavity_50`` has R = 0.18 m2K/W);
  - window / door units with ``Assembly.u_value_override`` use that declared /
    assumed value and their layers are ignored.

  Not included: ISO 6946 Annex F corrections (air gaps, mechanical fasteners such
  as wall ties, inverted roofs), tapered layers, and non-plane elements.

* :func:`ground_floor_u` - ISO 13370 simplified method for a slab on ground:
  characteristic dimension ``B' = A / (0.5 P)``, total equivalent thickness
  ``d_t = w + lambda (Rsi + Rf + Rse)`` and

  ``U = 2 lambda ln(pi B'/d_t + 1) / (pi B' + d_t)`` for ``d_t < B'`` (uninsulated /
  moderately insulated), else ``U = lambda / (0.457 B' + d_t)`` (well insulated).
  ``Rf`` is the resistance of the floor construction from the assembly's thermal
  layers (surface resistances excluded).  Edge insulation is not credited.

* :func:`heat_loss` - fabric + ventilation heat-loss coefficient of the **heated
  blocks** of a twin (unheated blocks such as garages are outside the envelope):

  - external walls (per heated block, per block assembly override): wall area from
    finished floor level to wall plate minus openings (gable / monopitch infill above
    the plate is in the roof void, outside the heated envelope);
  - windows, external doors and garage doors on heated blocks (opening areas, grouped
    by the assembly that applies to each opening);
  - roofs: pitched (cold) roofs use the roof assembly U-value on the insulated ceiling
    area (internal area of the top storey); flat roofs use the roof plan area inside
    the external wall line (block footprint; overhangs are outside the envelope);
  - ground floor: ISO 13370 on the heated ground-floor internal area with the heated
    exposed perimeter (external walls plus walls to unheated blocks, measured on the
    external face - slightly conservative); one common ``B'`` for the whole heated
    floor, applied per ground-floor assembly;
  - walls between heated and unheated blocks: separating-wall area x U (with
    ``Rse = Rsi``, both faces internal) x temperature factor ``b``;
  - thermal bridging: ``y x`` total exposed element area (SAP-style y-value);
  - ventilation: ``0.33 n V`` with ``V`` the heated internal volume (GIA x
    floor-to-floor) and ``n`` air changes per hour;
  - ``HLC`` = fabric + bridging + ventilation (W/K); peak load = ``HLC x dT`` at the
    project design temperatures; annual space heat = ``HLC x HDD x 24 / 1000`` kWh
    (no solar / internal gains, no system efficiency); ``HLP = HLC / heated GIA``.

Boundaries
----------
This is a **simplified steady-state indicative calculation, not SAP, SBEM or PHPP**,
and it makes **no claim of Building Regulations (Part L) or any other compliance**,
nor of certified energy performance.  The construction build-ups are assumptions
(construction is never established from appearance), and material conductivities in
the bundled library are illustrative.  Results are for comparing options at concept
stage only.  All arithmetic is deterministic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import product
from typing import Any, Optional, Union

from ..core.models import (
    Assembly,
    AssemblyLayer,
    AssemblyLibrary,
    BuildingTwin,
    ElementType,
    GeometryMetrics,
    HeatLossElement,
    HeatLossResult,
    LayerRole,
    RoofForm,
)
from ..core.provenance import Basis, weakest_basis
from ..core.settings import ProjectSettings
from ..geometry.metrics import compute_geometry_metrics
from ..quantities.measures import opening_element, selection_basis
from ..quantities.takeoff import wall_thicknesses

__all__ = [
    "ThermalDataError",
    "THERMAL_CAVEATS",
    "is_ventilated_layer",
    "u_value",
    "ground_floor_u",
    "heat_loss",
]

#: Ventilation heat capacity of air used in ``0.33 n V`` (Wh/m3K).
AIR_HEAT_CAPACITY_WH_M3K = 0.33
#: Safety limit on the number of independently bridged layers (2**n sections).
_MAX_BRIDGED_LAYERS = 8

THERMAL_CAVEATS: tuple[str, ...] = (
    "Simplified steady-state calculation; not SAP, SBEM or PHPP. No Building Regulations (Part L) or other "
    "compliance claim and no certified energy performance is implied.",
    "Construction build-ups are assumptions (construction is not established from images); conductivities "
    "are illustrative generic values, not declared product data.",
    "ISO 6946 combined method without Annex F corrections (air gaps, wall-tie fasteners); ventilated layers "
    "and everything outside them are ignored with Rse = Rsi.",
    "Ground floor by the ISO 13370 simplified slab-on-ground method; edge insulation is not credited.",
    "Thermal bridging is a single y-value on the exposed area; ventilation uses an assumed air-change rate; "
    "annual heat demand uses degree-days without solar/internal gains or heating-system efficiency.",
)


class ThermalDataError(ValueError):
    """Raised when an assembly lacks the data needed for a U-value (no conductivity, no thermal layers)."""


# =============================================================================
# U-values (ISO 6946-style)
# =============================================================================
def is_ventilated_layer(layer: AssemblyLayer) -> bool:
    """True when ``layer`` is a ventilated air layer (cavity / batten zone).

    A ``CAVITY`` or ``BATTENS`` layer counts as ventilated when it is excluded from the
    thermal calculation (``in_thermal_calc=False``) or when its name / factor note says
    "ventilated" (and not "unventilated").
    """
    if layer.role not in (LayerRole.CAVITY, LayerRole.BATTENS):
        return False
    text = f"{layer.name} {layer.factor_note}".lower()
    if "unventilated" in text or "non-ventilated" in text:
        return False
    return (not layer.in_thermal_calc) or ("ventilated" in text)


@dataclass(frozen=True)
class _TLayer:
    index: int
    name: str
    material_id: str
    thickness: float
    conductivity: float
    bridge_material_id: Optional[str] = None
    bridge_conductivity: Optional[float] = None
    bridge_fraction: float = 0.0

    @property
    def r_unbridged(self) -> float:
        return self.thickness / self.conductivity

    @property
    def r_bridge(self) -> Optional[float]:
        if self.bridge_conductivity is None:
            return None
        return self.thickness / self.bridge_conductivity

    @property
    def r_equivalent(self) -> float:
        """Lower-bound layer resistance with the area-weighted equivalent conductivity."""
        if self.bridge_fraction <= 0 or self.bridge_conductivity is None:
            return self.r_unbridged
        lam = (1.0 - self.bridge_fraction) * self.conductivity + self.bridge_fraction * self.bridge_conductivity
        return self.thickness / lam


def _resolve_assembly(assembly: Union[Assembly, str], library: AssemblyLibrary) -> Assembly:
    if isinstance(assembly, Assembly):
        return assembly
    try:
        return library.assembly(str(assembly))
    except KeyError:
        raise ThermalDataError(f"assembly '{assembly}' is not in library '{library.name}'") from None


def _conductivity(library: AssemblyLibrary, material_id: str, where: str) -> float:
    try:
        mat = library.material(material_id)
    except KeyError:
        raise ThermalDataError(f"{where}: material '{material_id}' is not in library '{library.name}'") from None
    k = mat.conductivity_w_mk
    if k is None or not math.isfinite(k) or k <= 0:
        raise ThermalDataError(f"{where}: material '{material_id}' has no thermal conductivity")
    return float(k)


def u_value(assembly: Union[Assembly, str], library: AssemblyLibrary, *, return_detail: bool = False,
            rse_override: Optional[float] = None) -> Union[float, tuple[float, dict[str, Any]]]:
    """U-value (W/m2K) of ``assembly`` by the ISO 6946-style combined method (module docstring).

    ``assembly`` may be an :class:`Assembly` or an assembly id in ``library``.
    ``rse_override`` replaces the external surface resistance (e.g. ``Rsi`` for an element
    facing an unheated internal space).  With ``return_detail=True`` returns ``(U, detail)``
    where ``detail`` lists every layer with its resistance, the upper / lower bounds, the
    total resistance and the ISO 6946 maximum relative error estimate.

    Raises :class:`ThermalDataError` when a thermal layer has no conductivity or the
    assembly has neither thermal layers nor a ``u_value_override``.
    """
    asm = _resolve_assembly(assembly, library)
    if asm.u_value_override is not None:
        u = float(asm.u_value_override)
        if not math.isfinite(u) or u <= 0:
            raise ThermalDataError(f"assembly '{asm.assembly_id}': invalid u_value_override {u!r}")
        detail = {
            "assembly_id": asm.assembly_id, "method": "u_value_override",
            "note": "Declared / assumed whole-unit U-value; layers ignored for the thermal calculation.",
            "u_value": u, "layers": [], "r_total": 1.0 / u,
        }
        return (u, detail) if return_detail else u

    vent_idx = max((i for i, layer in enumerate(asm.layers) if is_ventilated_layer(layer)), default=None)
    rsi = float(asm.rsi)
    rse = float(asm.rse) if vent_idx is None else rsi
    if rse_override is not None:
        if not math.isfinite(rse_override) or rse_override < 0:
            raise ThermalDataError(f"invalid rse_override {rse_override!r}")
        rse = float(rse_override)
    layer_rows: list[dict[str, Any]] = []
    tlayers: list[_TLayer] = []
    for i, layer in enumerate(asm.layers):
        row: dict[str, Any] = {"index": i, "name": layer.name, "material_id": layer.material_id,
                               "thickness_m": layer.thickness_m, "role": layer.role.value}
        if vent_idx is not None and i <= vent_idx:
            row.update(included=False, reason=("ventilated air layer" if i == vent_idx
                                               else "outside a ventilated air layer"))
            layer_rows.append(row)
            continue
        if not layer.in_thermal_calc or layer.thickness_m <= 0:
            row.update(included=False, reason="not in thermal calculation" if not layer.in_thermal_calc
                       else "zero thickness")
            layer_rows.append(row)
            continue
        where = f"assembly '{asm.assembly_id}' layer {i} '{layer.name}'"
        k = _conductivity(library, layer.material_id, where)
        bmid, bk, bf = None, None, 0.0
        if layer.bridging is not None and layer.bridging.fraction > 0:
            bmid = layer.bridging.material_id
            bk = _conductivity(library, bmid, f"{where} bridging")
            bf = float(layer.bridging.fraction)
        tl = _TLayer(i, layer.name, layer.material_id, float(layer.thickness_m), k, bmid, bk, bf)
        tlayers.append(tl)
        row.update(included=True, conductivity_w_mk=k, r_m2k_w=tl.r_unbridged)
        if bmid is not None:
            row["bridging"] = {"material_id": bmid, "conductivity_w_mk": bk, "fraction": bf,
                               "r_bridge_m2k_w": tl.r_bridge, "r_equivalent_m2k_w": tl.r_equivalent}
        layer_rows.append(row)
    if not tlayers:
        raise ThermalDataError(f"assembly '{asm.assembly_id}' has no thermal layers and no u_value_override")

    bridged = [t for t in tlayers if t.bridge_fraction > 0]
    if len(bridged) > _MAX_BRIDGED_LAYERS:
        raise ThermalDataError(f"assembly '{asm.assembly_id}' has more than {_MAX_BRIDGED_LAYERS} bridged layers")
    base = rsi + rse + sum(t.r_unbridged for t in tlayers if t.bridge_fraction <= 0)
    sections: list[dict[str, Any]] = []
    inv = 0.0
    for combo in product((False, True), repeat=len(bridged)):
        frac = 1.0
        r = base
        for t, is_bridge in zip(bridged, combo):
            frac *= t.bridge_fraction if is_bridge else (1.0 - t.bridge_fraction)
            r += t.r_bridge if is_bridge else t.r_unbridged  # type: ignore[operator]
        if frac <= 0:
            continue
        inv += frac / r
        sections.append({"fraction": frac, "r_total_m2k_w": r,
                         "bridged_layers": [t.index for t, b in zip(bridged, combo) if b]})
    r_upper = 1.0 / inv
    r_lower = rsi + rse + sum(t.r_equivalent for t in tlayers)
    r_total = 0.5 * (r_upper + r_lower)
    u = 1.0 / r_total
    if not return_detail:
        return u
    detail = {
        "assembly_id": asm.assembly_id,
        "method": "ISO 6946-style combined method" if bridged else "ISO 6946-style series layers",
        "rsi": rsi, "rse": rse,
        "rse_note": ("Rse = Rsi: layers outside the ventilated air layer are ignored" if vent_idx is not None
                     else ("Rse overridden" if rse_override is not None else "assembly Rse")),
        "ventilated_layer_index": vent_idx,
        "layers": layer_rows,
        "sections": sections,
        "r_upper_m2k_w": r_upper, "r_lower_m2k_w": r_lower, "r_total": r_total,
        "relative_error_estimate": (r_upper - r_lower) / (2.0 * r_total),
        "u_value": u,
        "not_included": "ISO 6946 Annex F corrections (air gaps, mechanical fasteners) are not applied.",
    }
    return u, detail


# =============================================================================
# Ground floors (ISO 13370 simplified)
# =============================================================================
def ground_floor_u(assembly: Union[Assembly, str], library: AssemblyLibrary, area: float, exposed_perimeter: float,
                   *, lambda_ground: float = 2.0, wall_thickness_m: float = 0.3,
                   return_detail: bool = False) -> Union[float, tuple[float, dict[str, Any]]]:
    """ISO 13370 simplified U-value (W/m2K) of a slab-on-ground floor (module docstring).

    ``area`` is the floor area (m2), ``exposed_perimeter`` the perimeter exposed to the
    outside or to unheated spaces (m), ``lambda_ground`` the ground conductivity (W/mK;
    2.0 = clay/silt default), ``wall_thickness_m`` the full external wall thickness ``w``.
    A floor without exposed perimeter has ``B' -> infinity`` and ``U -> 0``.  An assembly
    with ``u_value_override`` returns that value.
    """
    for name, v in (("area", area), ("exposed_perimeter", exposed_perimeter), ("lambda_ground", lambda_ground),
                    ("wall_thickness_m", wall_thickness_m)):
        if v is None or not math.isfinite(float(v)):
            raise ValueError(f"{name} must be a finite number (got {v!r})")
    if area <= 0:
        raise ValueError(f"floor area must be positive (got {area!r})")
    if exposed_perimeter < 0 or wall_thickness_m < 0:
        raise ValueError("exposed perimeter and wall thickness must be non-negative")
    if lambda_ground <= 0:
        raise ValueError("ground conductivity must be positive")
    asm = _resolve_assembly(assembly, library)
    if asm.u_value_override is not None:
        u = float(asm.u_value_override)
        d = {"assembly_id": asm.assembly_id, "method": "u_value_override", "u_value": u}
        return (u, d) if return_detail else u
    _, ud = u_value(asm, library, return_detail=True)
    rsi, rse = float(ud["rsi"]), float(ud["rse"])
    rf = float(ud["r_total"]) - rsi - rse
    d_t = wall_thickness_m + lambda_ground * (rsi + rf + rse)
    if exposed_perimeter <= 1e-9:
        b_dash = math.inf
        u = 0.0
        branch = "no exposed perimeter (B' -> infinity, U -> 0)"
    else:
        b_dash = area / (0.5 * exposed_perimeter)
        if d_t < b_dash:
            u = 2.0 * lambda_ground * math.log(math.pi * b_dash / d_t + 1.0) / (math.pi * b_dash + d_t)
            branch = "d_t < B': U = 2λ ln(πB'/d_t + 1) / (πB' + d_t)"
        else:
            u = lambda_ground / (0.457 * b_dash + d_t)
            branch = "d_t >= B': U = λ / (0.457 B' + d_t)"
    if not return_detail:
        return u
    return u, {
        "assembly_id": asm.assembly_id, "method": "ISO 13370 simplified slab on ground", "area_m2": area,
        "exposed_perimeter_m": exposed_perimeter, "characteristic_dimension_m": b_dash,
        "lambda_ground_w_mk": lambda_ground, "wall_thickness_m": wall_thickness_m, "rsi": rsi, "rse": rse,
        "r_floor_m2k_w": rf, "total_equivalent_thickness_m": d_t, "branch": branch, "u_value": u,
        "not_included": "Edge insulation (ISO 13370 Annex B) and periodic effects are not included.",
    }


# =============================================================================
# Heat loss
# =============================================================================
@dataclass
class _Acc:
    element: str
    assembly_id: Optional[str]
    area: float
    u: float
    b: float
    bases: list[Basis]
    notes: str = ""


def _block_bases(twin: BuildingTwin, block_id: str) -> list[Basis]:
    try:
        b = twin.block(block_id)
    except KeyError:
        return [Basis.UNKNOWN]
    return [tv.basis for tv in (b.width, b.depth, b.storeys, b.floor_to_floor, b.ground_floor_level)]


def heat_loss(twin: BuildingTwin, metrics: Optional[GeometryMetrics], library: AssemblyLibrary,
              settings: Optional[ProjectSettings] = None, *, thermal_bridging_y: float = 0.15,
              air_change_rate: float = 0.5, unheated_space_b_factor: float = 0.5,
              lambda_ground: float = 2.0) -> HeatLossResult:
    """Simplified steady-state heat-loss coefficient of the heated part of ``twin`` (module docstring).

    ``metrics`` must be the :class:`GeometryMetrics` of this twin (``None`` computes them with
    the selected wall thicknesses); ``settings`` defaults to ``twin.settings`` and supplies the
    design temperatures and heating degree-days.  ``thermal_bridging_y`` (W/m2K),
    ``air_change_rate`` (1/h), ``unheated_space_b_factor`` (0..1) and ``lambda_ground`` (W/mK)
    are labelled assumptions recorded in ``assumptions``.  Elements whose U-value cannot be
    computed are excluded and listed in ``warnings`` (heat loss is then underestimated).
    """
    settings = settings or twin.settings
    for name, v, lo, hi in (("thermal_bridging_y", thermal_bridging_y, 0.0, 1.0),
                            ("air_change_rate", air_change_rate, 0.0, 20.0),
                            ("unheated_space_b_factor", unheated_space_b_factor, 0.0, 1.0),
                            ("lambda_ground", lambda_ground, 1e-6, 10.0)):
        if v is None or not math.isfinite(float(v)) or not (lo <= float(v) <= hi):
            raise ValueError(f"{name} must be within [{lo}, {hi}] (got {v!r})")
    if metrics is None:
        t_ext, t_sep = wall_thicknesses(twin, library)
        metrics = compute_geometry_metrics(twin, t_ext, t_sep)

    sel = twin.assemblies
    heated = {b.block_id: bool(b.heated) for b in twin.blocks}
    bms = {bm.block_id: bm for bm in metrics.blocks}
    roofs = {r.block_id: r for r in metrics.roofs}
    ops = {o.opening_id: o for o in twin.openings}
    warnings: list[str] = []
    u_cache: dict[tuple[str, Optional[float]], Optional[float]] = {}

    def u_of(aid: str, rse: Optional[float] = None) -> Optional[float]:
        key = (aid, rse)
        if key not in u_cache:
            try:
                u_cache[key] = float(u_value(aid, library, rse_override=rse))  # type: ignore[arg-type]
            except ThermalDataError as e:
                warnings.append(f"{e}; element excluded from heat loss (heat loss underestimated).")
                u_cache[key] = None
        return u_cache[key]

    def sel_b(element: ElementType, block_id: Optional[str]) -> Basis:
        return selection_basis(sel, element.value, block_id)[0]

    accs: list[_Acc] = []
    heated_ids = [b.block_id for b in twin.blocks if b.heated and b.block_id in bms]

    # ---- external walls (FFL to plate minus openings) per heated block
    for bid in heated_ids:
        pcs = [p for p in metrics.pieces if p.block_id == bid]
        area = sum(max(0.0, p.external_rect_area_m2 - p.opening_area_m2) for p in pcs)
        if area <= 1e-9:
            continue
        aid = sel.for_element(ElementType.EXTERNAL_WALL, bid)
        u = u_of(aid)
        if u is None:
            continue
        accs.append(_Acc(f"external_wall:{bid}", aid, area, u, 1.0,
                         _block_bases(twin, bid) + [sel_b(ElementType.EXTERNAL_WALL, bid)],
                         "FFL-to-plate wall area minus openings; infill above the plate is in the roof void"))

    # ---- openings on heated blocks (as deducted from wall pieces)
    groups: dict[tuple[str, str], _Acc] = {}
    for p in metrics.pieces:
        if not heated.get(p.block_id, False):
            continue
        for oid in p.opening_ids:
            o = ops.get(oid)
            if o is None or o.width_m.value is None or o.height_m.value is None:
                continue
            et = opening_element(o.kind)
            if o.assembly_id:
                aid = o.assembly_id
                ob = sel.basis.get(f"opening/{o.opening_id}", Basis.ASSUMED)
            else:
                aid = sel.for_element(et, o.block_id)
                ob = sel_b(et, o.block_id)
            area = float(o.width_m.value) * float(o.height_m.value)
            key = (et.value, aid)
            g = groups.get(key)
            if g is None:
                u = u_of(aid)
                if u is None:
                    continue
                g = groups[key] = _Acc(et.value, aid, 0.0, u, 1.0, [], "opening areas on heated blocks")
            g.area += area
            g.bases += [o.width_m.basis, o.height_m.basis, ob]
    accs.extend(groups[k] for k in sorted(groups))

    # ---- roofs
    for bid in heated_ids:
        r = roofs.get(bid)
        bm = bms[bid]
        if r is None:
            continue
        if r.form == RoofForm.FLAT:
            et, area, note = ElementType.FLAT_ROOF, bm.footprint_area_m2, "flat roof plan area inside the wall line"
        else:
            et, area, note = ElementType.PITCHED_ROOF, bm.ceiling_area_m2, "cold roof: insulated ceiling area"
        if area <= 1e-9:
            continue
        aid = sel.for_element(et, bid)
        u = u_of(aid)
        if u is None:
            continue
        rb = twin.block(bid).roof
        bases = _block_bases(twin, bid) + [sel_b(et, bid)]
        if r.form != RoofForm.FLAT:
            bases.append(rb.pitch_deg.basis)
        accs.append(_Acc(f"{et.value}:{bid}", aid, area, u, 1.0, bases, note))

    # ---- ground floor (ISO 13370, common B' for the heated floor)
    gf_area_total = 0.0
    gf_groups: dict[str, list[str]] = {}
    for bid in heated_ids:
        g0 = bms[bid].gia_by_storey[0] if bms[bid].gia_by_storey else 0.0
        if g0 <= 0:
            continue
        gf_area_total += g0
        gf_groups.setdefault(sel.for_element(ElementType.GROUND_FLOOR, bid), []).append(bid)
    exposed_p = 0.0
    for p in metrics.pieces:
        if not heated.get(p.block_id, False):
            continue
        if p.exposure == "external" or not heated.get(p.neighbour_block_id or "", False):
            exposed_p += p.length_m
    b_dash: Optional[float] = None
    if gf_area_total > 0:
        b_dash = gf_area_total / (0.5 * exposed_p) if exposed_p > 1e-9 else math.inf
        for aid in sorted(gf_groups):
            bids = gf_groups[aid]
            area = sum(bms[b].gia_by_storey[0] for b in bids)
            try:
                u = float(ground_floor_u(aid, library, gf_area_total, exposed_p, lambda_ground=lambda_ground,
                                         wall_thickness_m=metrics.external_wall_thickness_m))  # type: ignore[arg-type]
            except (ThermalDataError, ValueError) as e:
                warnings.append(f"ground floor '{aid}': {e}; excluded from heat loss (heat loss underestimated).")
                continue
            bases = [x for b in bids for x in _block_bases(twin, b)] + [sel_b(ElementType.GROUND_FLOOR, b)
                                                                         for b in bids]
            accs.append(_Acc("ground_floor", aid, area, u, 1.0, bases,
                             f"ISO 13370 on heated ground floor {gf_area_total:.2f} m2, exposed perimeter "
                             f"{exposed_p:.2f} m (blocks {', '.join(bids)})"))

    # ---- walls between heated and unheated blocks
    sep_groups: dict[tuple[str, str, str], _Acc] = {}
    for p in metrics.pieces:
        if p.shared_area_m2 <= 1e-9 or not p.neighbour_block_id:
            continue
        ha, hn = heated.get(p.block_id, False), heated.get(p.neighbour_block_id, False)
        if ha == hn:
            continue
        hb, ub = (p.block_id, p.neighbour_block_id) if ha else (p.neighbour_block_id, p.block_id)
        aid = sel.for_element(ElementType.SEPARATING_WALL, hb)
        try:
            rsi = library.assembly(aid).rsi
        except KeyError:
            warnings.append(f"separating wall assembly '{aid}' not in library; wall to unheated space excluded.")
            continue
        u = u_of(aid, rsi)
        if u is None:
            continue
        key = (hb, ub, aid)
        g = sep_groups.get(key)
        if g is None:
            g = sep_groups[key] = _Acc(f"wall_to_unheated:{hb}|{ub}", aid, 0.0, u, unheated_space_b_factor,
                                       _block_bases(twin, hb) + _block_bases(twin, ub)
                                       + [sel_b(ElementType.SEPARATING_WALL, hb)],
                                       f"separating wall to unheated block {ub}; Rse = Rsi; b = "
                                       f"{unheated_space_b_factor:g}")
        g.area += p.shared_area_m2
    accs.extend(sep_groups[k] for k in sorted(sep_groups))

    # ---- totals
    elements = [HeatLossElement(element=a.element, assembly_id=a.assembly_id, area_m2=a.area, u_value=a.u,
                                ua_w_k=a.u * a.area * a.b, b_factor=a.b,
                                basis=weakest_basis(Basis.ASSUMED, a.bases), notes=a.notes)
                for a in accs]
    fabric = sum(e.ua_w_k for e in elements)
    exposed_area = sum(e.area_m2 for e in elements)
    bridging = thermal_bridging_y * exposed_area
    volume = metrics.heated_volume_m3
    vent = AIR_HEAT_CAPACITY_WH_M3K * air_change_rate * volume
    hlc = fabric + bridging + vent
    dt = float(settings.internal_design_temp_c) - float(settings.external_design_temp_c)
    gia = metrics.heated_gia_m2
    if not heated_ids:
        warnings.append("Twin has no heated blocks; heat loss is zero.")
    basis = weakest_basis(Basis.ASSUMED, [e.basis for e in elements])
    assumptions: dict[str, Any] = {
        "thermal_bridging_y_w_m2k": thermal_bridging_y,
        "air_change_rate_ach": air_change_rate,
        "unheated_space_b_factor": unheated_space_b_factor,
        "lambda_ground_w_mk": lambda_ground,
        "internal_design_temp_c": settings.internal_design_temp_c,
        "external_design_temp_c": settings.external_design_temp_c,
        "heating_degree_days_kday": settings.heating_degree_days,
        "heated_blocks": heated_ids,
        "heated_gia_m2": gia,
        "heated_volume_m3": volume,
        "exposed_area_m2": exposed_area,
        "ground_floor_exposed_perimeter_m": exposed_p,
        "ground_floor_characteristic_dimension_m": b_dash,
        "external_wall_thickness_m": metrics.external_wall_thickness_m,
        "conventions": {
            "walls": "external wall area FFL to wall plate minus openings, heated blocks only",
            "roofs": "pitched cold roof: ceiling (top-storey internal) area; flat roof: footprint inside wall line",
            "ground_floor": "ISO 13370 simplified; heated ground-floor GIA; exposed perimeter on external faces "
                            "including walls to unheated blocks",
            "unheated": "walls to unheated blocks: U (Rse = Rsi) x area x b; unheated blocks outside the envelope",
            "bridging": "y-value x total exposed element area",
            "ventilation": "0.33 x n x heated volume (GIA x floor-to-floor)",
            "annual": "HLC x heating degree-days x 24 / 1000 (no gains, no system efficiency)",
        },
        "basis_note": "All inputs above are labelled assumptions (ASSUMED) unless confirmed by a person.",
    }
    return HeatLossResult(
        elements=elements, fabric_ua_w_k=fabric, thermal_bridging_w_k=bridging, ventilation_w_k=vent,
        heat_loss_coefficient_w_k=hlc, design_delta_t_k=dt, peak_heat_load_kw=hlc * dt / 1000.0,
        annual_space_heat_kwh=hlc * float(settings.heating_degree_days) * 24.0 / 1000.0,
        hlp_w_m2k=hlc / gia if gia > 1e-9 else 0.0, assumptions=assumptions, caveats=list(THERMAL_CAVEATS),
        basis=basis, warnings=warnings,
    )
