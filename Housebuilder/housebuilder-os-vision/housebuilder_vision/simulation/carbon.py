"""Indicative embodied carbon of a bill of quantities (A1-A3, A5 waste share, optional A4).

Method
------
For every resolved **material** line of the :class:`BillOfQuantities`:

1. the installed quantity is converted to mass with the material data of the library,
   by the dimension of the material's installed unit:

   * ``kg`` / ``t`` (mass): converted directly;
   * ``m3`` (volume): ``m3 x density`` (fallback: purchase-unit mass);
   * ``m2`` (area): ``m2 x layer thickness x density`` using the line's assembly layer
     (``assembly_id`` / ``layer_index``); for a bridged layer only the unbridged fraction
     ``(1 - f)`` is this material (the bridging members are measured on their own line);
     fallback when the layer has no thickness or the material no density: purchase-unit
     mass ``mass_per_purchase_unit_kg x purchase_per_installed`` (e.g. membranes, units);
   * ``nr`` / ``m`` and other count / length units: ``mass_per_purchase_unit_kg x
     purchase_per_installed`` per installed unit;

2. **A1-A3** = installed mass x the material's ``carbon_kgco2e_per_kg``;
3. **A5 waste share** = mass of the cutting + waste losses of the line x the same factor
   (the product-stage carbon of material that is bought but wasted on site);
4. **A4** (transport to site) only when a logistics plan, a factor per load-km and a
   one-way distance are all given: ``loads x distance x factor``.

Lines that cannot be converted are listed in ``unmatched`` with the reason: unresolved
quantities, materials missing from the library, materials without a carbon factor or
mass data, and **allowances without material data** (kitchens, services, piling ...) whose
carbon is therefore *not* in the totals.  Thermal-only pseudo-materials (an air cavity)
are skipped.  Plant / disposal rule lines are site operations outside A1-A3.

Boundaries
----------
Factors in the bundled library are **illustrative placeholders, not EPD or ICE values**;
the result is an indicative comparison between options, not a carbon assessment, a
whole-life carbon calculation or any certification.  Construction build-ups are
assumptions.  A5 site energy, B (use), C (end of life), D and operational energy are
excluded.  Deterministic, pure arithmetic.
"""

from __future__ import annotations

import math
from typing import Optional

from ..core.models import (
    Assembly,
    AssemblyLibrary,
    BillOfQuantities,
    CarbonLine,
    CarbonResult,
    LogisticsResult,
    MaterialSpec,
    QuantityLine,
    QuantityStatus,
)
from ..core.provenance import Basis, weakest_basis
from ..core.units import UnitError, convert, dimension, normalise_unit

__all__ = ["CARBON_CAVEATS", "installed_mass_per_unit", "embodied_carbon"]

_THERMAL_ONLY = "thermal_only"

CARBON_CAVEATS: tuple[str, ...] = (
    "Illustrative placeholder carbon factors (not EPD / ICE values): indicative comparison only, not a carbon "
    "assessment, whole-life carbon calculation or certification.",
    "Masses come from generic densities, layer thicknesses and unit masses in the assembly library.",
    "Construction build-ups are assumptions; construction is not established from images.",
    "Allowances without material data (fittings, services, piling ...) are not in the totals - see 'unmatched'.",
    "Excludes A5 site energy and plant, B (use), C (end of life), D and operational energy.",
)


def _is_placeholder(source: str) -> bool:
    s = (source or "").lower()
    return "placeholder" in s or "illustrative" in s or "fictional" in s or s in ("", "unspecified")


def _dim(unit: str) -> str:
    try:
        return dimension(unit)
    except UnitError:
        return "unknown"


def _layer_for(line: QuantityLine, asms: dict[str, Assembly]):
    if line.assembly_id is None or line.layer_index is None:
        return None
    asm = asms.get(line.assembly_id)
    if asm is None or not (0 <= line.layer_index < len(asm.layers)):
        return None
    layer = asm.layers[line.layer_index]
    return layer if layer.material_id == line.material_id else None


def installed_mass_per_unit(line: QuantityLine, material: MaterialSpec,
                            assemblies: Optional[dict[str, Assembly]] = None) -> tuple[Optional[float], str]:
    """Mass (kg) per installed unit of ``line`` and a description of the conversion.

    Returns ``(None, reason)`` when the library holds no usable mass data.  See the module
    docstring for the conversion order per unit dimension.
    """
    asms = assemblies or {}
    unit = normalise_unit(material.installed_unit)
    dim = _dim(unit)
    ppi = float(material.purchase_per_installed)
    pmass = material.mass_per_purchase_unit_kg
    purchase_kg = pmass * ppi if pmass is not None else None
    purchase_txt = (f"{material.purchase_unit} mass {pmass:g} kg × {ppi:.6g} {material.purchase_unit}/{unit}"
                    if pmass is not None else "")
    rho = material.density_kg_m3
    if dim == "mass":
        return convert(1.0, unit, "kg"), f"{unit} → kg"
    if dim == "volume":
        if rho:
            return rho * convert(1.0, unit, "m3"), f"{unit} × density {rho:g} kg/m3"
        if purchase_kg is not None:
            return purchase_kg, purchase_txt
        return None, f"no density or unit mass for {material.material_id}"
    if dim == "area":
        layer = _layer_for(line, asms)
        if layer is not None and layer.thickness_m > 0 and rho:
            f = layer.bridging.fraction if layer.bridging is not None else 0.0
            kg = convert(1.0, unit, "m2") * layer.thickness_m * rho * (1.0 - f)
            txt = f"{unit} × layer {layer.thickness_m * 1000:g} mm × density {rho:g} kg/m3"
            if f > 0:
                txt += f" × (1 − bridged fraction {f:g})"
            return kg, txt
        if purchase_kg is not None:
            return purchase_kg, purchase_txt
        if layer is None and rho:
            return None, f"no layer thickness for {material.material_id} (line has no assembly layer)"
        return None, f"no thickness/density or unit mass for {material.material_id}"
    if purchase_kg is not None:
        return purchase_kg, purchase_txt
    return None, f"no unit mass (mass_per_purchase_unit_kg) for {material.material_id} [{unit}]"


def embodied_carbon(boq: BillOfQuantities, library: AssemblyLibrary, *, logistics: Optional[LogisticsResult] = None,
                    a4_kgco2e_per_load_km: Optional[float] = None,
                    distance_km: Optional[float] = None) -> CarbonResult:
    """Indicative A1-A3 + A5-waste (+ optional A4) embodied carbon of ``boq`` (module docstring).

    ``a4_kgco2e_per_load_km`` is the transport factor per loaded vehicle-km and ``distance_km``
    the one-way delivery distance; A4 is calculated only when both are given together with a
    ``logistics`` plan (its ``total_loads``).  Raises ``ValueError`` for negative or non-finite
    A4 inputs.
    """
    for name, v in (("a4_kgco2e_per_load_km", a4_kgco2e_per_load_km), ("distance_km", distance_km)):
        if v is not None and (not math.isfinite(float(v)) or float(v) < 0):
            raise ValueError(f"{name} must be a finite, non-negative number (got {v!r})")
    mats = {m.material_id: m for m in library.materials}
    asms = {a.assembly_id: a for a in library.assemblies}
    lines: list[CarbonLine] = []
    unmatched: list[str] = []
    by_element: dict[str, float] = {}
    tot13 = tot5 = 0.0
    bases: list[Basis] = [Basis.ASSUMED]
    methods: dict[str, str] = {}
    for ln in boq.lines:
        if not ln.material_id:
            if ln.allowance_id or (ln.cost_key or "").startswith("allow:"):
                unmatched.append(f"{ln.line_id}: allowance without material data - embodied carbon not counted")
            continue
        if ln.status == QuantityStatus.UNRESOLVED or ln.installed_qty is None:
            unmatched.append(f"{ln.line_id}: quantity unresolved ({ln.material_id})")
            continue
        mat = mats.get(ln.material_id)
        if mat is None:
            unmatched.append(f"{ln.line_id}: material '{ln.material_id}' not in library")
            continue
        if mat.category == _THERMAL_ONLY:
            continue
        factor = mat.carbon_kgco2e_per_kg
        if factor is None or not math.isfinite(factor) or factor < 0:
            unmatched.append(f"{ln.line_id}: no carbon factor for material '{mat.material_id}'")
            continue
        kg_per_unit, how = installed_mass_per_unit(ln, mat, asms)
        if kg_per_unit is None:
            unmatched.append(f"{ln.line_id}: {how}")
            continue
        q = float(ln.installed_qty)
        loss = float(ln.cutting_loss_qty or 0.0) + float(ln.waste_qty or 0.0)
        mass = q * kg_per_unit
        wmass = loss * kg_per_unit
        a13 = mass * float(factor)
        a5 = wmass * float(factor)
        lb = weakest_basis(ln.basis, Basis.ASSUMED)
        bases.append(lb)
        lines.append(CarbonLine(
            quantity_line_id=ln.line_id, material_id=mat.material_id, mass_kg=mass, factor_kgco2e_per_kg=float(factor),
            a1_a3_kgco2e=a13, a5_waste_kgco2e=a5, element_code=ln.element_code,
            mass_method=f"{q:.4g} {mat.installed_unit} × {kg_per_unit:.6g} kg/{mat.installed_unit} ({how})",
            waste_mass_kg=wmass, basis=lb))
        methods.setdefault(mat.material_id, how)
        key = f"{ln.element_code} {ln.element_name}".strip()
        by_element[key] = by_element.get(key, 0.0) + a13 + a5
        tot13 += a13
        tot5 += a5
    caveats = list(CARBON_CAVEATS)
    a4 = 0.0
    a4_inputs = (logistics is not None, a4_kgco2e_per_load_km is not None, distance_km is not None)
    if all(a4_inputs):
        a4 = float(logistics.total_loads) * float(distance_km) * float(a4_kgco2e_per_load_km)  # type: ignore[union-attr,arg-type]
        boundary_a4 = (f" + A4 transport ({logistics.total_loads} loads × {distance_km:g} km × "  # type: ignore[union-attr]
                       f"{a4_kgco2e_per_load_km:g} kgCO2e/load-km, one-way)")
    else:
        boundary_a4 = ""
        if any(a4_inputs):
            caveats.append("A4 transport not calculated: it needs a logistics plan, a factor per load-km and a "
                           "distance together.")
        else:
            caveats.append("A4 transport not included (no logistics plan / transport factor / distance given).")
    gia = float(boq.geometry.gia_m2) if boq.geometry is not None else 0.0
    total = tot13 + tot5 + a4
    if gia <= 1e-9:
        caveats.append("GIA is zero or unresolved; carbon per m2 GIA not computed (reported as 0).")
    boundary = ("A1-A3 product stage on installed material mass + A5 share for material wasted on site (cutting + "
                "waste losses)" + boundary_a4 + ". Excludes A5 site energy/plant, B, C, D stages and operational "
                "energy; allowances without material data are excluded (listed as unmatched). by_element = A1-A3 + "
                "A5 waste per element code.")
    sources = sorted({mats[c.material_id].carbon_source or "unspecified" for c in lines})
    placeholder = [s for s in sources if _is_placeholder(s)]
    if not lines or placeholder == sources:
        factor_source = ("Illustrative placeholder factors from the assembly library - replace with EPD / ICE data "
                         "via an EmbodiedCarbonDataAdapter.")
    else:
        factor_source = "Carbon factors from: " + "; ".join(sources) + "."
        if placeholder:
            factor_source += " Some factors are still illustrative placeholders."
            caveats[0] = ("Some carbon factors are illustrative placeholders (not EPD / ICE values): indicative "
                          "comparison only, not a carbon assessment, whole-life carbon calculation or certification.")
        else:
            caveats[0] = ("Carbon factors come from the sources named in factor_source (applied via an adapter); "
                          "the result is still an indicative concept-stage estimate, not a carbon assessment or "
                          "certification.")
    return CarbonResult(
        boundary=boundary, total_a1_a3_kgco2e=tot13, total_a5_waste_kgco2e=tot5, a4_transport_kgco2e=a4,
        per_m2_gia_kgco2e=total / gia if gia > 1e-9 else 0.0,
        by_element=dict(sorted(by_element.items())), lines=lines, unmatched=unmatched,
        factor_source=factor_source, caveats=caveats, basis=weakest_basis(bases),
        assumptions={
            "gia_m2": gia,
            "a4_kgco2e_per_load_km": a4_kgco2e_per_load_km, "distance_km": distance_km,
            "a4_loads": logistics.total_loads if logistics is not None else None,
            "mass_conversion": "kg direct; m3 × density; m2 × layer thickness × density (× (1 − bridged fraction)), "
                               "else unit mass; nr / m × unit mass × purchase per installed",
            "a5": "cutting + waste loss mass × product-stage factor",
            "material_mass_methods": dict(sorted(methods.items())),
        },
    )
