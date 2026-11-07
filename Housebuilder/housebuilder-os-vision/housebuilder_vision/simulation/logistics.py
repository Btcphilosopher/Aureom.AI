"""Indicative delivery, storage and waste plan from a BoQ and a programme.

Method
------
* **Batches**: each resolved, purchasable material line is assigned to the programme task
  that uses it (:func:`~housebuilder_vision.simulation.programme.assign_lines_to_tasks`;
  a line split between tasks is delivered for the earliest of them).  Lines are batched
  per *(task, delivery category)* - one supplier delivery stream per category (masonry,
  timber, insulation, ready-mixed concrete ...) for each task.
* **Mass / volume** of a batch = purchased quantity (purchase units, after pack rounding)
  x ``mass_per_purchase_unit_kg`` / ``volume_per_purchase_unit_m3`` (each derived from the
  other with the density when only one is given; volume-unit purchases use their own
  volume).
* **Loads**: general batches ``ceil(max(mass / payload, volume / vehicle volume))`` (at least
  one load); **ready-mixed concrete** (``delivery_category = "ready_mix_concrete"``)
  ``ceil(m3 / readymix_m3_per_load)`` truck loads, delivered on the day of use, no storage.
  Each allowance line without material data (kitchen, sanitaryware, services, doors ...)
  adds ``allowance_loads_each`` load(s) with unknown mass / volume (storage not estimated).
* **Timing**: ``required_by_day`` = earliest start of the task; delivery
  ``deliver_days_before`` working days earlier (not before day 0; for a lead-time-constrained
  task - ordered at day 0 in the programme - not before its lead time); ``order_by_day`` =
  delivery day - the longest supplier lead time in the batch (weeks x working days per
  week; ``lead_time_weeks`` overrides the library).  A negative order-by day means the
  order must be placed before the programme start (reported in ``warnings``).
* **Storage**: ``volume / stack_height_m x access_factor`` m2 per batch, held from delivery to
  the end of its task (no gradual draw-down: conservative); the peak is found by sweeping
  these delivery -> consumption windows on the early-start schedule.
* **Waste**: cutting + waste losses of every material line converted to solid volume
  (volume-unit materials directly, otherwise via purchase-unit volume or mass / density),
  bulked by ``waste_bulking_factor`` -> ``waste_volume_m3`` (bulked) and
  ``skips = ceil(bulked / skip_volume_m3)``.  Excavated spoil is a separate muck-away
  item in the BoQ (``log:spoil_disposal``) and is not in the skips.

Boundaries
----------
Indicative only: supplier consolidation, vehicle types and access, crane / forklift
offloading, storage layout, traffic management and just-in-time call-offs are not
designed.  The defaults (10 t / 30 m3 rigid lorry, 6 m3 truck mixer, 1.5 m stacks, 1.3
access factor, 1.6 bulking, 6 m3 skips) are labelled assumptions.  Deterministic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Optional

from ..core.models import (
    AssemblyLibrary,
    BillOfQuantities,
    DeliveryBatch,
    LogisticsResult,
    MaterialSpec,
    ProgrammeResult,
    QuantityLine,
    QuantityStatus,
    TaskSpec,
)
from ..core.units import UnitError, convert, dimension, normalise_unit
from .programme import assign_lines_to_tasks, material_lead_time_weeks

__all__ = ["LOGISTICS_CAVEATS", "READY_MIX_CATEGORY", "purchase_mass_volume", "waste_solid_volume",
           "plan_deliveries"]

READY_MIX_CATEGORY = "ready_mix_concrete"
_THERMAL_ONLY = "thermal_only"

LOGISTICS_CAVEATS: tuple[str, ...] = (
    "Indicative delivery plan: supplier consolidation, vehicle types, site access, offloading plant, storage "
    "layout and traffic management are not designed.",
    "Vehicle payloads, stack heights, access allowance, waste bulking and skip size are labelled assumptions.",
    "Storage is held from delivery to the end of the task (no gradual draw-down) - a conservative peak.",
    "Lead times are illustrative assumptions; confirm with suppliers.",
)


def _is_volume(unit: str) -> bool:
    try:
        return dimension(unit) == "volume"
    except UnitError:
        return False


def purchase_mass_volume(material: MaterialSpec) -> tuple[Optional[float], Optional[float]]:
    """(kg, m3) per purchase unit of ``material`` (None when not derivable)."""
    m = material.mass_per_purchase_unit_kg
    v = material.volume_per_purchase_unit_m3
    rho = material.density_kg_m3
    if v is None and _is_volume(material.purchase_unit):
        v = convert(1.0, normalise_unit(material.purchase_unit), "m3")
    if m is None and v is not None and rho:
        m = v * rho
    if v is None and m is not None and rho:
        v = m / rho
    return m, v


def waste_solid_volume(line: QuantityLine, material: MaterialSpec) -> Optional[float]:
    """Solid volume (m3) of the cutting + waste losses of ``line`` (None without data)."""
    loss = float(line.cutting_loss_qty or 0.0) + float(line.waste_qty or 0.0)
    if loss <= 0:
        return 0.0
    if _is_volume(material.installed_unit):
        return convert(loss, normalise_unit(material.installed_unit), "m3")
    _, v = purchase_mass_volume(material)
    if v is None:
        return None
    return loss * float(material.purchase_per_installed) * v


@dataclass
class _Batch:
    task: TaskSpec
    category: str
    ready_mix: bool
    line_ids: list[str] = field(default_factory=list)
    material_ids: list[str] = field(default_factory=list)
    mass: float = 0.0
    volume: float = 0.0
    no_data: list[str] = field(default_factory=list)
    lead_days: float = 0.0
    lead_mid: Optional[str] = None
    allowance: Optional[str] = None


def _check(name: str, v: float, *, allow_zero: bool = False) -> float:
    if v is None or not math.isfinite(float(v)) or float(v) < 0 or (float(v) == 0 and not allow_zero):
        raise ValueError(f"{name} must be a finite {'non-negative' if allow_zero else 'positive'} number (got {v!r})")
    return float(v)


def plan_deliveries(boq: BillOfQuantities, library: AssemblyLibrary, programme: ProgrammeResult, *,
                    vehicle_payload_t: float = 10.0, vehicle_volume_m3: float = 30.0,
                    readymix_m3_per_load: float = 6.0, stack_height_m: float = 1.5, access_factor: float = 1.3,
                    deliver_days_before: float = 2, lead_time_weeks: Optional[Mapping[str, float]] = None,
                    waste_bulking_factor: float = 1.6, skip_volume_m3: float = 6.0,
                    allowance_loads_each: int = 1, services_first_fix_share: float = 0.5) -> LogisticsResult:
    """Delivery batches, loads, order-by days, storage peak, waste volume and skips (module docstring).

    ``programme`` should be the programme built from this ``boq`` (its early-start schedule
    times the deliveries); ``services_first_fix_share`` must match the one used for it.
    """
    payload_kg = _check("vehicle_payload_t", vehicle_payload_t) * 1000.0
    vvol = _check("vehicle_volume_m3", vehicle_volume_m3)
    rm = _check("readymix_m3_per_load", readymix_m3_per_load)
    stack = _check("stack_height_m", stack_height_m)
    access = _check("access_factor", access_factor)
    before = _check("deliver_days_before", deliver_days_before, allow_zero=True)
    bulking = _check("waste_bulking_factor", waste_bulking_factor)
    skip_v = _check("skip_volume_m3", skip_volume_m3)
    if int(allowance_loads_each) < 0:
        raise ValueError("allowance_loads_each must be non-negative")
    wdpw = float(programme.working_days_per_week or 5.0)
    warnings: list[str] = []
    tasks = {t.task_id: t for t in programme.tasks}
    if not tasks:
        raise ValueError("programme has no tasks")
    fallback_task = tasks.get("superstructure") or min(programme.tasks, key=lambda t: t.earliest_start)
    shares = assign_lines_to_tasks(boq, library, services_first_fix_share=services_first_fix_share)
    mats = {m.material_id: m for m in library.materials}

    batches: dict[tuple[str, str], _Batch] = {}
    allowance_batches: list[_Batch] = []
    solid_waste = 0.0
    no_waste_data: set[str] = set()
    missing_task: set[str] = set()

    def task_for(line_id: str) -> TaskSpec:
        cands = [tasks[t] for t, _ in shares.get(line_id, []) if t in tasks]
        if not cands:
            missing_task.update(t for t, _ in shares.get(line_id, []))
            return fallback_task
        return min(cands, key=lambda t: (t.earliest_start, t.task_id))

    for ln in boq.lines:
        if ln.status == QuantityStatus.UNRESOLVED:
            continue
        if not ln.material_id:
            if ln.allowance_id and allowance_loads_each > 0 and (ln.installed_qty or 0.0) > 0:
                t = task_for(ln.line_id)
                allowance_batches.append(_Batch(task=t, category="allowance_items", ready_mix=False,
                                                line_ids=[ln.line_id], allowance=ln.allowance_id))
            continue
        mat = mats.get(ln.material_id)
        if mat is None:
            warnings.append(f"Line {ln.line_id}: material '{ln.material_id}' not in library; not delivered.")
            continue
        if mat.category == _THERMAL_ONLY:
            continue
        purchased = ln.purchased_qty
        if purchased is None or purchased <= 0:
            continue
        t = task_for(ln.line_id)
        cat = mat.delivery_category or "general"
        ready = cat == READY_MIX_CATEGORY
        b = batches.get((t.task_id, cat))
        if b is None:
            b = batches[(t.task_id, cat)] = _Batch(task=t, category=cat, ready_mix=ready)
        b.line_ids.append(ln.line_id)
        if mat.material_id not in b.material_ids:
            b.material_ids.append(mat.material_id)
        m, v = purchase_mass_volume(mat)
        if m is None or v is None:
            b.no_data.append(mat.material_id)
        b.mass += float(purchased) * (m or 0.0)
        b.volume += float(purchased) * (v or 0.0)
        w = material_lead_time_weeks(mat.material_id, library, lead_time_weeks)
        if w is not None and w * wdpw > b.lead_days:
            b.lead_days, b.lead_mid = w * wdpw, mat.material_id
        wv = waste_solid_volume(ln, mat)
        if wv is None:
            no_waste_data.add(mat.material_id)
        else:
            solid_waste += wv

    out: list[DeliveryBatch] = []
    for (tid, cat), b in sorted(batches.items(), key=lambda kv: (kv[1].task.earliest_start, kv[0])):
        t = b.task
        if b.ready_mix:
            loads = int(math.ceil(b.volume / rm - 1e-9)) if b.volume > 0 else 1
            delivery = t.earliest_start
            storage = 0.0
            desc = f"{t.name}: ready-mixed concrete {b.volume:.2f} m3 in {loads} truck load(s) of {rm:g} m3"
        else:
            need = max(b.mass / payload_kg, b.volume / vvol)
            loads = max(1, int(math.ceil(need - 1e-9)))
            delivery = max(0.0, t.earliest_start - before)
            if t.material_lead_time_days > 0:
                # Lead-time-constrained task: ordered at day 0, so it cannot arrive before its lead time.
                delivery = min(t.earliest_start, max(delivery, b.lead_days))
            storage = b.volume / stack * access
            desc = (f"{t.name}: {cat} - {b.mass / 1000:.2f} t, {b.volume:.2f} m3 in {loads} load(s) "
                    f"(payload {payload_kg / 1000:g} t / {vvol:g} m3)")
        if b.no_data:
            warnings.append(f"Batch {tid}:{cat}: no mass/volume data for {', '.join(sorted(set(b.no_data)))}; "
                            "loads and storage may be understated.")
        order_by = delivery - b.lead_days
        if order_by < 0:
            warnings.append(f"Batch {tid}:{cat}: order {(-order_by):.1f} working days before the programme start "
                            f"(lead time {b.lead_days / wdpw:g} weeks, {b.lead_mid}).")
        out.append(DeliveryBatch(
            batch_id=f"{tid}:{cat}", task_id=tid, description=desc, material_ids=sorted(b.material_ids),
            mass_kg=b.mass, volume_m3=b.volume, loads=loads, required_by_day=t.earliest_start, order_by_day=order_by,
            storage_area_m2=storage, delivery_category=cat, line_ids=b.line_ids, lead_time_days=b.lead_days,
            delivery_day=delivery, consumed_by_day=t.earliest_finish, ready_mix=b.ready_mix))
    for b in sorted(allowance_batches, key=lambda x: (x.task.earliest_start, x.allowance or "")):
        t = b.task
        delivery = max(0.0, t.earliest_start - before)
        out.append(DeliveryBatch(
            batch_id=f"{t.task_id}:allowance:{b.allowance}", task_id=t.task_id,
            description=f"{t.name}: allowance items '{b.allowance}' - {allowance_loads_each} load(s) assumed; mass, "
                        "volume and storage not estimated",
            material_ids=[], mass_kg=0.0, volume_m3=0.0, loads=int(allowance_loads_each),
            required_by_day=t.earliest_start, order_by_day=delivery, storage_area_m2=0.0,
            delivery_category="allowance_items", line_ids=b.line_ids, delivery_day=delivery,
            consumed_by_day=t.earliest_finish))
    if allowance_batches:
        warnings.append(f"{len(allowance_batches)} allowance item(s) without material data counted as "
                        f"{allowance_loads_each} load(s) each; their storage is not estimated.")
    if missing_task:
        warnings.append(f"Task(s) {', '.join(sorted(missing_task))} not in the programme; their materials are "
                        f"delivered for '{fallback_task.task_id}'.")
    if no_waste_data:
        warnings.append("Waste volume not estimated for material(s) without volume/mass data: "
                        + ", ".join(sorted(no_waste_data)))

    # ---- peak storage: sweep delivery -> consumption windows (removals before additions at equal times)
    events: list[tuple[float, int, float]] = []
    for d in out:
        if d.storage_area_m2 > 0 and d.consumed_by_day > d.delivery_day:
            events.append((d.delivery_day, 1, d.storage_area_m2))
            events.append((d.consumed_by_day, 0, -d.storage_area_m2))
    events.sort()
    cur = peak = 0.0
    peak_day = 0.0
    for day, _, delta in events:
        cur += delta
        if cur > peak + 1e-12:
            peak, peak_day = cur, day
    bulked = solid_waste * bulking
    skips = int(math.ceil(bulked / skip_v - 1e-9)) if bulked > 0 else 0
    return LogisticsResult(
        batches=out, total_loads=sum(d.loads for d in out), total_mass_t=sum(d.mass_kg for d in out) / 1000.0,
        peak_storage_area_m2=peak, waste_volume_m3=bulked, skips=skips,
        assumptions={
            "vehicle_payload_t": vehicle_payload_t, "vehicle_volume_m3": vvol, "readymix_m3_per_load": rm,
            "stack_height_m": stack, "access_factor": access, "deliver_days_before": before,
            "waste_bulking_factor": bulking, "skip_volume_m3": skip_v, "allowance_loads_each": allowance_loads_each,
            "working_days_per_week": wdpw, "lead_time_weeks_overrides": dict(sorted((lead_time_weeks or {}).items())),
            "waste_solid_volume_m3": solid_waste, "peak_storage_day": peak_day,
            "batching": "per (programme task, delivery category); purchased quantities after pack rounding",
            "schedule": "early-start dates of the programme",
            "basis": "assumed (vehicle, storage and waste parameters are labelled assumptions)",
        },
        caveats=list(LOGISTICS_CAVEATS), warnings=warnings,
    )
