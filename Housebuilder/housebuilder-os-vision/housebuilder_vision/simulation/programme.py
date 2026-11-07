"""Indicative construction programme: task network from the BoQ + critical path method.

Task network (finish-to-start links, working days)
--------------------------------------------------
::

    setup -> substructure -> ground_slab -> superstructure -> roof
    roof + procure_windows_doors -> windows_doors
    roof + windows_doors -> first_fix
    roof -> partitions
    first_fix + partitions -> plaster_drylining -> second_fix -> finishes -> externals_handover

* ``procure_windows_doors`` is a procurement pseudo-task (no labour) whose duration is
  the longest supplier lead time of the window / door materials, **ordered at day 0**
  (project start); it makes the lead-time constraint visible on the critical path.
  ``windows_doors.material_lead_time_days`` carries the same value.  Other materials
  are assumed ordered in time for their task (pre-start procurement); the logistics
  plan reports their order-by days.
* Quantity lines are mapped to tasks (see :func:`assign_lines_to_tasks`):
  substructure = foundation option lines; ground slab = ground-floor assembly lines
  except wet trades; superstructure = external / separating walls, upper floors,
  frame allowance (except plastering / drylining layers); roof = roof assembly lines
  except ceiling linings and ceiling insulation; windows & doors = 2.6 lines;
  partitions = partition framing; plaster / drylining = plastering & drylining layers
  of walls, ceilings and partitions, ground-floor screed and loft insulation;
  first fix = staircase allowance + ``services_first_fix_share`` (50 %) of the
  services allowances; second fix = the rest of services + fittings + internal doors;
  finishes = internal finishes allowances (floor finishes, decoration).
  ``setup`` and ``externals_handover`` have no measured work and fixed assumed durations.
* Duration (working days) = labour hours of the mapped lines x ``labour_multipliers``
  [trade] / (crew size x hours per day), minimum 1 day for a task with work (0 for a
  task without mapped work).  Trades within one task are treated as a single gang.
  ``crew_sizes`` may be keyed by task id or by trade (task id wins).
* CPM: forward pass ``ES = max(EF(pred) + lag, material_lead_time_days, 0)``, backward pass
  ``LF = min(LS(succ) - lag(succ))`` (project end for terminal tasks), total float
  ``LS - ES``; critical = zero float (tolerance 1e-6), listed in topological order.

Boundaries
----------
An **indicative task network, not a validated programme**: no weather, curing or drying
times, inspections, resource levelling, trade-stacking limits, site constraints or
supply-chain disruption are modelled, and the crew sizes and productivity (labour hours
per unit in the library) are assumptions.  Deterministic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

from ..core.models import (
    AssemblyLibrary,
    BillOfQuantities,
    ElementType,
    LayerRole,
    ProgrammeResult,
    QuantityLine,
    QuantityStatus,
    TaskSpec,
)

__all__ = [
    "TASK_DEFINITIONS",
    "PROGRAMME_CAVEATS",
    "TaskDefinition",
    "assign_lines_to_tasks",
    "material_lead_time_weeks",
    "critical_path_method",
    "build_programme",
]

_TOL = 1e-6
PROCUREMENT_TRADE = "procurement"


@dataclass(frozen=True)
class TaskDefinition:
    task_id: str
    name: str
    trade: str  # default / fallback main trade
    predecessors: tuple[str, ...]
    default_crew: float
    fixed_days: Optional[float] = None  # tasks without measured work
    procurement_for: Optional[str] = None  # pseudo-task: lead time of the materials of this task


TASK_DEFINITIONS: tuple[TaskDefinition, ...] = (
    TaskDefinition("setup", "Site set-up and enabling works", "general", (), 2, fixed_days=5.0),
    TaskDefinition("substructure", "Substructure: excavation, foundations, below-ground masonry", "groundworks",
                   ("setup",), 4),
    TaskDefinition("ground_slab", "Ground-floor slab", "groundworks", ("substructure",), 4),
    TaskDefinition("superstructure", "Superstructure: external and separating walls, frame, upper floors",
                   "bricklaying", ("ground_slab",), 4),
    TaskDefinition("roof", "Roof structure and coverings", "roofing", ("superstructure",), 3),
    TaskDefinition("procure_windows_doors", "Window and door supply lead time (ordered at day 0)",
                   PROCUREMENT_TRADE, (), 0, procurement_for="windows_doors"),
    TaskDefinition("windows_doors", "Windows and external doors", "glazing", ("roof", "procure_windows_doors"), 2),
    TaskDefinition("first_fix", "First fix services and carpentry", "plumbing", ("roof", "windows_doors"), 3),
    TaskDefinition("partitions", "Internal partitions (framing)", "carpentry", ("roof",), 2),
    TaskDefinition("plaster_drylining", "Plastering, drylining, screeds and ceiling insulation", "plastering",
                   ("first_fix", "partitions"), 3),
    TaskDefinition("second_fix", "Second fix services, carpentry and fittings", "carpentry",
                   ("plaster_drylining",), 3),
    TaskDefinition("finishes", "Finishes and decoration", "decorating", ("second_fix",), 3),
    TaskDefinition("externals_handover", "Externals, snagging and handover", "general", ("finishes",), 3,
                   fixed_days=10.0),
)

PROGRAMME_CAVEATS: tuple[str, ...] = (
    "Indicative task network from labour hours and assumed crews - not a validated programme.",
    "No weather, curing/drying times, inspections, resource levelling, site constraints or supply-chain "
    "disruption are modelled; labour productivity and crew sizes are assumptions.",
    "Window/door supply is ordered at day 0 (project start); other materials are assumed ordered in time for "
    "their task (see the logistics plan for order-by days).",
)

_WET = {"plastering", "drylining"}
_CODE_FALLBACK = {"1": "substructure", "2.1": "superstructure", "2.2": "superstructure", "2.3": "roof",
                  "2.4": "first_fix", "2.5": "superstructure", "2.6": "windows_doors", "2.7": "partitions",
                  "2.8": "superstructure", "3": "finishes", "4": "second_fix"}


# =============================================================================
# Line -> task mapping
# =============================================================================
def _line_shares(ln: QuantityLine, library: AssemblyLibrary, fdn_ids: set[str], ff_share: float,
                 asms: dict) -> tuple[list[tuple[str, float]], bool]:
    """(task shares, mapped_by_rule) for one quantity line."""
    code = ln.element_code or ""
    top = code.split(".", 1)[0]
    if ln.allowance_id:
        if top == "5":
            return [("first_fix", ff_share), ("second_fix", 1.0 - ff_share)], True
        if code == "2.7":
            return [("second_fix", 1.0)], True  # internal door sets are hung at second fix
        if code in _CODE_FALLBACK:
            return [(_CODE_FALLBACK[code], 1.0)], True
        if top in _CODE_FALLBACK:
            return [(_CODE_FALLBACK[top], 1.0)], True
        return [("superstructure", 1.0)], False
    if ln.assembly_id in fdn_ids:
        return [("substructure", 1.0)], True
    asm = asms.get(ln.assembly_id or "")
    wet = ln.trade in _WET
    if asm is not None:
        layer = asm.layers[ln.layer_index] if (ln.layer_index is not None
                                               and 0 <= ln.layer_index < len(asm.layers)) else None
        e = asm.element
        if e == ElementType.GROUND_FLOOR:
            return [("plaster_drylining" if wet else "ground_slab", 1.0)], True
        if e in (ElementType.EXTERNAL_WALL, ElementType.SEPARATING_WALL, ElementType.INTERMEDIATE_FLOOR):
            return [("plaster_drylining" if wet else "superstructure", 1.0)], True
        if e in (ElementType.PITCHED_ROOF, ElementType.FLAT_ROOF):
            ceiling_insulation = (layer is not None and layer.measure == "ceiling_area"
                                  and layer.role == LayerRole.INSULATION)
            return [("plaster_drylining" if (wet or ceiling_insulation) else "roof", 1.0)], True
        if e in (ElementType.WINDOW, ElementType.EXTERNAL_DOOR, ElementType.GARAGE_DOOR):
            return [("windows_doors", 1.0)], True
        if e == ElementType.INTERNAL_PARTITION:
            return [("plaster_drylining" if wet else "partitions", 1.0)], True
    if code in _CODE_FALLBACK:
        t = _CODE_FALLBACK[code]
        if wet and t in ("superstructure", "partitions", "roof", "ground_slab"):
            t = "plaster_drylining"
        return [(t, 1.0)], True
    if top in _CODE_FALLBACK:
        return [(_CODE_FALLBACK[top], 1.0)], True
    if top == "5":
        return [("first_fix", ff_share), ("second_fix", 1.0 - ff_share)], True
    return [("superstructure", 1.0)], False


def assign_lines_to_tasks(boq: BillOfQuantities, library: AssemblyLibrary, *, services_first_fix_share: float = 0.5,
                          warnings: Optional[list[str]] = None) -> dict[str, list[tuple[str, float]]]:
    """Map every quantity line id to ``[(task_id, share), ...]`` (shares sum to 1).

    See the module docstring for the rules.  Lines with an unrecognised element code are
    assigned to ``superstructure`` and reported in ``warnings`` (when a list is given).
    """
    if not (0.0 <= services_first_fix_share <= 1.0):
        raise ValueError("services_first_fix_share must be within [0, 1]")
    fdn_ids = {f.option_id for f in library.foundations}
    asms = {a.assembly_id: a for a in library.assemblies}
    out: dict[str, list[tuple[str, float]]] = {}
    for ln in boq.lines:
        shares, ok = _line_shares(ln, library, fdn_ids, services_first_fix_share, asms)
        out[ln.line_id] = [(t, s) for t, s in shares if s > 0]
        if not ok and warnings is not None:
            warnings.append(f"Line {ln.line_id} (element {ln.element_code!r}) has no programme mapping; assigned to "
                            "superstructure.")
    return out


def material_lead_time_weeks(material_id: str, library: AssemblyLibrary,
                             overrides: Optional[Mapping[str, float]] = None) -> Optional[float]:
    """Lead time (weeks) of a material: ``overrides[material_id]`` or the library's assumed value."""
    if overrides and material_id in overrides:
        v = float(overrides[material_id])
        if not math.isfinite(v) or v < 0:
            raise ValueError(f"lead time for '{material_id}' must be a finite, non-negative number of weeks")
        return v
    try:
        lt = library.material(material_id).lead_time_weeks
    except KeyError:
        return None
    return float(lt.value) if (lt is not None and lt.value is not None) else None


# =============================================================================
# Critical path method
# =============================================================================
def critical_path_method(tasks: Sequence[TaskSpec]) -> tuple[list[TaskSpec], float, list[str]]:
    """Forward / backward pass over ``tasks`` (finish-to-start with ``lag_days``).

    ``earliest_start = max(max(EF(pred)) + lag_days, material_lead_time_days, 0)``.
    Returns ``(scheduled_tasks, project_duration, critical_path)`` where the scheduled tasks are
    copies (input order kept) with ES / EF / LS / LF / total float / critical filled in and the
    critical path lists the zero-float tasks in topological order.  Raises ``ValueError`` for
    duplicate ids, unknown predecessors, negative durations or cycles.
    """
    ids = [t.task_id for t in tasks]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate task ids in network")
    by_id = {t.task_id: t for t in tasks}
    for t in tasks:
        if not math.isfinite(t.duration_days) or t.duration_days < 0:
            raise ValueError(f"task {t.task_id}: duration must be finite and non-negative")
        for p in t.predecessors:
            if p not in by_id:
                raise ValueError(f"task {t.task_id}: unknown predecessor '{p}'")
    succs: dict[str, list[str]] = {i: [] for i in ids}
    indeg = {i: 0 for i in ids}
    for t in tasks:
        for p in dict.fromkeys(t.predecessors):
            succs[p].append(t.task_id)
            indeg[t.task_id] += 1
    order: list[str] = []
    ready = [i for i in ids if indeg[i] == 0]
    pos = {i: k for k, i in enumerate(ids)}
    while ready:
        ready.sort(key=pos.__getitem__)
        n = ready.pop(0)
        order.append(n)
        for s in succs[n]:
            indeg[s] -= 1
            if indeg[s] == 0:
                ready.append(s)
    if len(order) != len(ids):
        raise ValueError("task network contains a cycle")
    es: dict[str, float] = {}
    ef: dict[str, float] = {}
    for i in order:
        t = by_id[i]
        start = max(0.0, float(t.material_lead_time_days))
        if t.predecessors:
            start = max(start, max(ef[p] for p in t.predecessors) + float(t.lag_days))
        es[i] = start
        ef[i] = start + float(t.duration_days)
    duration = max(ef.values(), default=0.0)
    ls: dict[str, float] = {}
    lf: dict[str, float] = {}
    for i in reversed(order):
        t = by_id[i]
        if succs[i]:
            lf[i] = min(ls[s] - float(by_id[s].lag_days) for s in succs[i])
        else:
            lf[i] = duration
        ls[i] = lf[i] - float(t.duration_days)
    out: list[TaskSpec] = []
    for t in tasks:
        i = t.task_id
        fl = ls[i] - es[i]
        if abs(fl) < _TOL:
            fl = 0.0
        out.append(t.model_copy(update={"earliest_start": es[i], "earliest_finish": ef[i], "latest_start": ls[i],
                                        "latest_finish": lf[i], "total_float": fl, "critical": fl <= _TOL}))
    crit = [i for i in order if ls[i] - es[i] <= _TOL]
    return out, duration, crit


# =============================================================================
# Programme
# =============================================================================
def _positive(name: str, v: float, upper: Optional[float] = None) -> float:
    if v is None or not math.isfinite(float(v)) or float(v) <= 0 or (upper is not None and float(v) > upper):
        raise ValueError(f"{name} must be positive" + (f" and at most {upper}" if upper is not None else "")
                         + f" (got {v!r})")
    return float(v)


def build_programme(boq: BillOfQuantities, library: AssemblyLibrary, *,
                    crew_sizes: Optional[Mapping[str, float]] = None,
                    lead_time_weeks: Optional[Mapping[str, float]] = None,
                    labour_multipliers: Optional[Mapping[str, float]] = None,
                    working_days_per_week: float = 5, hours_per_day: float = 8,
                    services_first_fix_share: float = 0.5,
                    fixed_task_days: Optional[Mapping[str, float]] = None,
                    lead_time_constrained_tasks: Iterable[str] = ("windows_doors",),
                    lead_times: Optional[Mapping[str, float]] = None) -> ProgrammeResult:
    """Indicative programme for ``boq`` (module docstring).

    ``crew_sizes``: task id or trade -> crew size (persons).  ``lead_time_weeks``: material id
    -> supplier lead time in weeks, overriding the library (used by the uncertainty
    simulator); ``lead_times`` is an accepted alias (the ARCHITECTURE §2 keyword) - pass one
    or the other.  ``labour_multipliers``: trade -> factor on labour hours (productivity
    uncertainty).  ``fixed_task_days`` overrides the assumed durations of tasks without measured
    work (``setup`` 5, ``externals_handover`` 10 working days).
    ``lead_time_constrained_tasks``: tasks whose materials are ordered at day 0 and gate the
    task start (default: windows & doors only).
    """
    if lead_times is not None:
        if lead_time_weeks is not None:
            raise ValueError("pass lead_time_weeks or its alias lead_times, not both")
        lead_time_weeks = lead_times
    wdpw = _positive("working_days_per_week", working_days_per_week, 7.0)
    hpd = _positive("hours_per_day", hours_per_day, 24.0)
    crews = dict(crew_sizes or {})
    for k, v in crews.items():
        _positive(f"crew size '{k}'", v)
    mult = dict(labour_multipliers or {})
    for k, v in mult.items():
        if v is None or not math.isfinite(float(v)) or float(v) < 0:
            raise ValueError(f"labour multiplier for '{k}' must be a finite, non-negative number")
    fixed = {d.task_id: d.fixed_days for d in TASK_DEFINITIONS if d.fixed_days is not None}
    for k, v in (fixed_task_days or {}).items():
        if v is None or not math.isfinite(float(v)) or float(v) < 0:
            raise ValueError(f"fixed duration for '{k}' must be a finite, non-negative number of days")
        fixed[k] = float(v)
    constrained = set(lead_time_constrained_tasks)
    warnings: list[str] = []
    shares = assign_lines_to_tasks(boq, library, services_first_fix_share=services_first_fix_share,
                                   warnings=warnings)

    hours: dict[str, float] = {d.task_id: 0.0 for d in TASK_DEFINITIONS}
    hours_trade_task: dict[str, dict[str, float]] = {d.task_id: {} for d in TASK_DEFINITIONS}
    task_lines: dict[str, list[str]] = {d.task_id: [] for d in TASK_DEFINITIONS}
    task_materials: dict[str, list[str]] = {d.task_id: [] for d in TASK_DEFINITIONS}
    by_trade: dict[str, float] = {}
    unresolved = 0
    for ln in boq.lines:
        alloc = shares.get(ln.line_id, [])
        if ln.status == QuantityStatus.UNRESOLVED or ln.labour_hours is None:
            unresolved += 1
        h = float(ln.labour_hours or 0.0) * float(mult.get(ln.trade, 1.0))
        for tid, s in alloc:
            if tid not in hours:
                continue
            task_lines[tid].append(ln.line_id)
            if ln.material_id and ln.material_id not in task_materials[tid]:
                task_materials[tid].append(ln.material_id)
            if h > 0:
                hours[tid] += h * s
                tt = hours_trade_task[tid]
                tt[ln.trade] = tt.get(ln.trade, 0.0) + h * s
        if h > 0 and alloc:
            by_trade[ln.trade] = by_trade.get(ln.trade, 0.0) + h
    if unresolved:
        warnings.append(f"{unresolved} quantity line(s) are unresolved or have no labour hours; their work is not in "
                        "the programme (durations may be understated).")

    specs: list[TaskSpec] = []
    lead_days: dict[str, float] = {}
    lead_notes: dict[str, str] = {}
    for tid in sorted(constrained):
        mids = task_materials.get(tid, [])
        best, best_mid = 0.0, None
        for mid in mids:
            w = material_lead_time_weeks(mid, library, lead_time_weeks)
            if w is not None and w * wdpw > best:
                best, best_mid = w * wdpw, mid
        lead_days[tid] = best
        lead_notes[tid] = (f"longest lead time {best / wdpw:g} weeks ({best_mid}) × {wdpw:g} working days/week"
                           if best_mid else "no lead-time data for this task's materials")
    for d in TASK_DEFINITIONS:
        tid = d.task_id
        if d.procurement_for is not None:
            tgt = d.procurement_for
            ld = lead_days.get(tgt, 0.0) if tgt in constrained else 0.0
            specs.append(TaskSpec(task_id=tid, name=d.name, trade=PROCUREMENT_TRADE, labour_hours=0.0, crew_size=0.0,
                                  duration_days=ld, predecessors=list(d.predecessors),
                                  notes=(lead_notes.get(tgt, "") if tgt in constrained
                                         else "not lead-time constrained") + "; no site labour"))
            continue
        h = hours[tid]
        tt = hours_trade_task[tid]
        trade = max(sorted(tt), key=lambda k: tt[k]) if tt else d.trade
        crew = float(crews.get(tid, crews.get(trade, d.default_crew)))
        if tid in fixed:
            dur = fixed[tid]
            note = f"fixed assumed duration {dur:g} working days (no measured work)"
            if h > 0:
                dur = max(dur, h / (crew * hpd))
                note += f"; {h:.1f} labour hours mapped"
        elif h > 0:
            dur = max(1.0, h / (crew * hpd))
            note = f"{h:.1f} labour hours / ({crew:g} crew × {hpd:g} h/day)" + (" (minimum 1 day)" if dur == 1.0 else "")
        else:
            dur = 0.0
            note = "no mapped work"
        if tt:
            note += "; hours by trade: " + ", ".join(f"{k} {tt[k]:.1f}" for k in sorted(tt))
        specs.append(TaskSpec(task_id=tid, name=d.name, trade=trade, labour_hours=h, crew_size=crew,
                              duration_days=dur, predecessors=list(d.predecessors),
                              material_lead_time_days=lead_days.get(tid, 0.0) if tid in constrained else 0.0,
                              line_ids=task_lines[tid], notes=note))
    scheduled, duration, crit = critical_path_method(specs)
    total_hours = sum(by_trade.values())
    assumptions: dict[str, Any] = {
        "working_days_per_week": wdpw,
        "hours_per_day": hpd,
        "crew_sizes": {t.task_id: t.crew_size for t in scheduled if t.trade != PROCUREMENT_TRADE},
        "labour_multipliers": dict(sorted(mult.items())),
        "lead_time_weeks_overrides": dict(sorted((lead_time_weeks or {}).items())),
        "lead_time_constrained_tasks": sorted(constrained),
        "lead_time_days": lead_days,
        "services_first_fix_share": services_first_fix_share,
        "fixed_task_days": fixed,
        "network": {t.task_id: list(t.predecessors) for t in scheduled},
        "basis": "assumed (crew sizes, productivities and lead times are labelled assumptions)",
    }
    return ProgrammeResult(
        tasks=scheduled, duration_days=duration, duration_weeks=duration / wdpw, working_days_per_week=wdpw,
        critical_path=crit, total_labour_hours=total_hours, labour_hours_by_trade=dict(sorted(by_trade.items())),
        caveats=list(PROGRAMME_CAVEATS), assumptions=assumptions, warnings=warnings,
    )
