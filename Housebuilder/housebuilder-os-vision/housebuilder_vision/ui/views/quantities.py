"""Quantities view: traceable bill of quantities with filters, line trace + 3D highlight, allowances,
unresolved items, measurement conventions and GEA / GIA by storey.

Installed quantities, cutting loss, waste, pack rounding and surplus are kept separate exactly as
the take-off reports them; display units follow the unit setting (count units never convert).
Selecting a line shows its formula, measure and trace links and highlights the geometry it was
measured from (wall pieces, blocks, roofs, openings, storeys) - quantity-to-model traceability.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from ...core.models import QuantityLine, QuantityStatus
from ...core.provenance import Basis
from .. import fmt
from .. import state as S
from ..charts import resolve_refs, twin_figure
from ..components import guard, html, section_title
from ..theme import BASIS_COLOURS, badge, callout, esc, hex_to_rgba, tag
from .twin import twin_meshes


def _disp_qty(v, unit: str, system: str) -> tuple[Optional[float], str]:
    if v is None:
        return None, unit
    return fmt.disp(v, unit, system)


def _rows(lines: list[QuantityLine], system: str) -> pd.DataFrame:
    out = []
    for ln in lines:
        inst, u = _disp_qty(ln.installed_qty, ln.unit, system)
        req, _ = _disp_qty(ln.required_qty, ln.unit, system)
        out.append({
            "line_id": ln.line_id, "element": f"{ln.element_code} {ln.element_name}", "description": ln.description,
            "status": ln.status.value, "installed": inst, "unit": fmt.unit_label(u),
            "cutting %": 100 * ln.cutting_loss_fraction, "waste %": 100 * ln.waste_fraction, "required": req,
            "purchase unit": ln.purchase_unit, "packs": ln.packs, "purchased": ln.purchased_qty,
            "surplus": ln.surplus_qty, "labour h": ln.labour_hours, "trade": ln.trade, "basis": ln.basis.value})
    return pd.DataFrame(out)


def _style_basis(df: pd.DataFrame):
    """Tint the basis column with the basis colour (the cell text names the basis, so colour is not alone)."""
    valid = {b.value: b for b in Basis}

    def colour(v: str) -> str:
        b = valid.get(v)
        return f"background-color: {hex_to_rgba(BASIS_COLOURS[b], 0.24)}; color: #F3EEE4" if b else ""
    return df.style.map(colour, subset=["basis"])


NUM_COLS = {
    "installed": st.column_config.NumberColumn(format="%.2f"),
    "cutting %": st.column_config.NumberColumn(format="%.0f"),
    "waste %": st.column_config.NumberColumn(format="%.0f"),
    "required": st.column_config.NumberColumn(format="%.2f"),
    "packs": st.column_config.NumberColumn(format="%d"),
    "purchased": st.column_config.NumberColumn(format="%.2f"),
    "surplus": st.column_config.NumberColumn(format="%.2f"),
    "labour h": st.column_config.NumberColumn(format="%.1f"),
    "description": st.column_config.TextColumn(width="medium"),
    "line_id": st.column_config.TextColumn("line id"),
}


def render(ws: S.Workspace, ev: Optional[S.Evaluation]) -> None:
    p = ws.project
    if p is None or p.twin is None or ev is None:
        html(callout("Build a twin first (Images view) - quantities are measured from it.", title="Quantities",
                     tone="neutral"))
        return
    boq = ev.boq
    system = p.settings.unit_system
    n = {s: sum(1 for ln in boq.lines if ln.status == s) for s in QuantityStatus}
    html(f'<div style="display:flex;gap:.4rem;flex-wrap:wrap;margin:.1rem 0 .4rem 0">'
         f'{tag(f"{len(boq.lines)} lines")}{tag(f"{n[QuantityStatus.DERIVED]} derived")}'
         f'{tag(f"{n[QuantityStatus.ALLOWANCE]} allowances", tone="warn")}'
         f'{tag(f"{n[QuantityStatus.UNRESOLVED]} unresolved", tone="danger" if n[QuantityStatus.UNRESOLVED] else "neutral")}'
         f'{tag(f"twin v{boq.twin_version}", tone="gold")}{tag(boq.library_name)}</div>')
    with guard("Bill of quantities"):
        _boq_table(ws, ev, system)
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        with guard("Allowances"):
            _allowances(boq, system)
    with c2:
        with guard("Unresolved items"):
            _unresolved(boq, ev)
    with guard("Areas by storey"):
        _areas(ev, system)
    with st.expander("Measurement conventions"):
        conv = {**boq.geometry.conventions, **boq.conventions}
        st.dataframe(pd.DataFrame([{"topic": k.replace("_", " "), "convention": v} for k, v in conv.items()]),
                     hide_index=True, width="stretch",
                     column_config={"convention": st.column_config.TextColumn(width="large")})
    if boq.warnings:
        with st.expander(f"Take-off warnings ({len(boq.warnings)})"):
            for w in boq.warnings:
                st.markdown(f"- {esc(w)}")


def _boq_table(ws: S.Workspace, ev: S.Evaluation, system: str) -> None:
    boq = ev.boq
    elements = sorted({f"{ln.element_code} {ln.element_name}" for ln in boq.lines},
                      key=lambda s: [int(x) if x.isdigit() else x for x in s.split(" ")[0].split(".")])
    c1, c2, c3, c4 = st.columns([2.2, 1.2, 1.4, 1.6])
    el = c1.multiselect("Element", elements, key="q_el", placeholder="All elements")
    stt = c2.multiselect("Status", [s.value for s in QuantityStatus], key="q_status", placeholder="All")
    bs = c3.multiselect("Basis", ["user_confirmed", "observed", "inferred", "assumed", "unknown"], key="q_basis",
                        placeholder="All")
    q = c4.text_input("Search", key="q_text", placeholder="description, material, trade…")
    lines = [ln for ln in boq.lines
             if (not el or f"{ln.element_code} {ln.element_name}" in el)
             and (not stt or ln.status.value in stt) and (not bs or ln.basis.value in bs)
             and (not q or q.lower() in f"{ln.description} {ln.material_id} {ln.trade} {ln.line_id}".lower())]
    df = _rows(lines, system)
    if df.empty:
        st.info("No lines match the filters.")
        return
    event = st.dataframe(_style_basis(df), key="boq_table", hide_index=True, width="stretch",
                         height=min(390, 40 + 35 * len(df)),
                         on_select="rerun", selection_mode="single-row", column_config=NUM_COLS,
                         column_order=["element", "description", "status", "installed", "unit", "cutting %",
                                       "waste %", "required", "purchase unit", "packs", "purchased", "surplus",
                                       "labour h", "trade", "basis", "line_id"])
    st.caption(f"{len(df)} of {len(boq.lines)} lines. Select a row to trace it. Installed = net measured quantity; "
               "cutting and waste losses are kept separate; purchased = packs × pack size (purchase units); "
               "surplus = purchased − required.")
    rows = list(getattr(getattr(event, "selection", None), "rows", []) or []) if event is not None else []
    sel_id = df.iloc[rows[0]]["line_id"] if rows and rows[0] < len(df) else None
    _trace_panel(ws, ev, sel_id, system)


def _trace_panel(ws: S.Workspace, ev: S.Evaluation, line_id: Optional[str], system: str) -> None:
    p = ws.project
    left, right = st.columns([1, 1.15], gap="medium")
    meshes = twin_meshes(S.fp(p.twin), p.twin)
    if line_id is None:
        with left:
            section_title("Trace", sub="quantity-to-model traceability")
            html(callout("Select a BoQ line above to see its formula, measure and trace links; the geometry it was "
                         "measured from (wall pieces, blocks, roofs, openings, storeys) is highlighted in gold.",
                         title="No line selected", tone="neutral"))
        with right:
            st.plotly_chart(twin_figure(meshes, p.twin, metrics=ev.boq.geometry, height=340), key="q_3d_idle",
                            theme=None, config={"displaylogo": False})
        return
    ln = ev.boq.line(line_id)
    mv, mu = _disp_qty(ln.measure_value, ln.measure_unit, system)
    with left:
        section_title("Trace", sub="quantity-to-model traceability")
        html(f'<div style="display:flex;gap:.4rem;align-items:center;flex-wrap:wrap">{badge(ln.basis)}'
             f'{tag(ln.status.value, tone="warn" if ln.status != QuantityStatus.DERIVED else "neutral")}'
             f'<span class="hbv-small hbv-mono">{esc(ln.line_id)}</span></div>'
             f'<div style="font-weight:600;margin:.25rem 0">{esc(ln.description)}</div>'
             f'<div class="hbv-small">Measure: <b>{esc(ln.measure_name or "-")}</b> = '
             f'<span class="hbv-mono">{esc(fmt.num(mv, 3))} {esc(fmt.unit_label(mu))}</span> · trade '
             f'{esc(ln.trade)} · {esc(fmt.num(ln.labour_hours, 1))} labour h · cost key '
             f'<span class="hbv-mono">{esc(ln.cost_key or "-")}</span></div>'
             f'<div class="hbv-formula" style="margin-top:.35rem">{esc(ln.formula or "no formula recorded")}</div>')
        if ln.notes:
            st.caption(ln.notes)
        if ln.trace:
            st.dataframe(pd.DataFrame([{"kind": t.kind, "ref": t.ref, "description": t.description}
                                       for t in ln.trace]),
                         hide_index=True, width="stretch", height=min(250, 38 + 35 * len(ln.trace)),
                         column_config={"description": st.column_config.TextColumn(width="large")})
    hl = resolve_refs(p.twin, ev.boq.geometry, ln.geometry_refs)
    with right:
        st.plotly_chart(twin_figure(meshes, p.twin, highlight=hl, metrics=ev.boq.geometry, height=360),
                        key="q_3d", theme=None, config={"displaylogo": False})
        refs = ", ".join(ln.geometry_refs) or "none (allowance / non-geometric)"
        st.caption(f"Highlighted in gold: {refs}" + (f" · not drawable: {', '.join(sorted(hl['other']))}"
                                                     if hl["other"] else ""))


def _allowances(boq, system: str) -> None:
    section_title("Allowances", sub="labelled, not measured")
    lines = [ln for ln in boq.lines if ln.status == QuantityStatus.ALLOWANCE]
    if not lines:
        st.caption("No allowance lines.")
        return
    df = pd.DataFrame([{"element": f"{ln.element_code} {ln.element_name}", "description": ln.description,
                        "quantity": ln.installed_qty, "unit": ln.unit, "basis": ln.basis.value,
                        "rule": ln.formula[:120]} for ln in lines])
    st.dataframe(_style_basis(df), hide_index=True, width="stretch", height=min(360, 38 + 35 * len(df)),
                 column_config={"quantity": st.column_config.NumberColumn(format="%.2f")})


def _unresolved(boq, ev: S.Evaluation) -> None:
    section_title("Unresolved items", sub="never priced as zero")
    lines = boq.unresolved
    items = list(ev.estimate.unresolved_items)
    if not lines and not items:
        html(callout("Every quantity was derived or allowed for, and every cost item found a rate.",
                     title="Nothing unresolved", tone="neutral"))
        return
    if lines:
        st.dataframe(pd.DataFrame([{"line": ln.line_id, "description": ln.description, "reason": ln.notes}
                                   for ln in lines]), hide_index=True, width="stretch")
    if items:
        html(callout("<ul>" + "".join(f"<li>{esc(i)}</li>" for i in items[:40]) + "</ul>",
                     title=f"Cost items without a usable rate ({len(items)})", tone="danger"))


def _areas(ev: S.Evaluation, system: str) -> None:
    g = ev.boq.geometry
    section_title("GEA / GIA by storey", sub="GEA to external face; GIA net of external walls and half of shared walls")
    rows = [{"storey": s.storey, "blocks": ", ".join(s.block_ids), "GEA": fmt.disp(s.gea_m2, "m2", system)[0],
             "GIA": fmt.disp(s.gia_m2, "m2", system)[0],
             "external perimeter": fmt.disp(s.external_perimeter_m, "m", system)[0]} for s in g.storeys]
    rows.append({"storey": float("nan"), "blocks": "total", "GEA": fmt.disp(g.gea_m2, "m2", system)[0],
                 "GIA": fmt.disp(g.gia_m2, "m2", system)[0], "external perimeter": float("nan")})
    au, lu = fmt.unit_label(fmt.disp_unit("m2", system)), fmt.unit_label(fmt.disp_unit("m", system))
    c1, c2 = st.columns([1, 1.2], gap="medium")
    c1.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={"GEA": st.column_config.NumberColumn(f"GEA ({au})", format="%.2f"),
                                "GIA": st.column_config.NumberColumn(f"GIA ({au})", format="%.2f"),
                                "external perimeter": st.column_config.NumberColumn(f"ext. perimeter ({lu})",
                                                                                    format="%.2f"),
                                "storey": st.column_config.NumberColumn(format="%d")})
    brow = [{"block": b.block_id, "storeys": b.storeys, "footprint": fmt.disp(b.footprint_area_m2, "m2", system)[0],
             "GIA by storey": " / ".join(f"{fmt.disp(x, 'm2', system)[0]:.1f}" for x in b.gia_by_storey),
             "ext. wall net": fmt.disp(b.external_wall_net_m2, "m2", system)[0],
             "openings": fmt.disp(b.opening_area_m2, "m2", system)[0], "heated": b.heated} for b in g.blocks]
    c2.dataframe(pd.DataFrame(brow), hide_index=True, width="stretch",
                 column_config={k: st.column_config.NumberColumn(f"{k} ({au})", format="%.2f")
                                for k in ("footprint", "ext. wall net", "openings")})


__all__ = ["render"]
