"""Costs view: boundary cards, layer waterfall, cost lines with rate provenance, rate book (upload +
inline editing), commercial parameters and the uncertainty simulation.

Boundaries are cumulative layer sums shown with their definitions and exclusions; sales value
(GDV) is reported separately and never inside a cost.  Missing rates are listed as unresolved,
never priced as zero.  Rates whose source is the bundled demo are labelled FICTIONAL.  The
uncertainty result states its interval type: assumed scenario uncertainty, not a calibrated
confidence interval.
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from ...core.models import COST_LAYER_NAMES, CostLayer
from .. import fmt
from .. import state as S
from ..charts import histogram_cdf, layer_waterfall, tornado
from ..components import cards, guard, html, section_title
from ..theme import callout, card, esc

METRIC_LABELS = {"construction_incl_contingency": "Construction incl. contingency", "contract_sum": "Contract sum",
                 "gia_m2": "GIA", "external_wall_net_m2": "External wall (net)", "roof_surface_m2": "Roof surface",
                 "concrete_m3": "Concrete", "labour_hours": "Labour", "programme_weeks": "Programme"}
GROUP_LABELS = {"scale": "Scale (image calibration)", "hidden_geometry": "Hidden geometry",
                "unit_prices": "Unit prices", "labour_rates": "Labour rates",
                "labour_productivity": "Labour productivity", "waste": "Waste", "ground": "Ground conditions",
                "lead_time": "Lead times"}


def render(ws: S.Workspace, ev: Optional[S.Evaluation]) -> None:
    p = ws.project
    if p is None or p.twin is None or ev is None:
        html(callout("Build a twin first - costs are priced from its bill of quantities.", title="Costs",
                     tone="neutral"))
        return
    est = ev.estimate
    with guard("Pricing notice"):
        _pricing_notice(ws, ev)
    with guard("Cost boundaries"):
        _boundary_cards(ws, ev)
    left, right = st.columns([1.55, 1], gap="medium")
    with left:
        with guard("Layer breakdown"):
            section_title("Cost layers", sub="nine layers; Σ bars are the cumulative boundaries")
            st.plotly_chart(layer_waterfall(est, height=360), key="c_waterfall", theme=None,
                            config={"displaylogo": False})
    with right:
        with guard("Layer table"):
            _layer_table(est)
    t1, t2, t3, t4 = st.tabs(["Uncertainty", "Cost lines & rate provenance", "Rate book", "Commercial parameters"])
    with t1:
        with guard("Uncertainty simulation"):
            _uncertainty(ws, ev)
    with t2:
        with guard("Cost lines"):
            _cost_lines(ws, ev)
    with t3:
        with guard("Rate book"):
            _rate_book(ws)
    with t4:
        with guard("Commercial parameters"):
            _commercial(ws, ev)


def _pricing_notice(ws: S.Workspace, ev: S.Evaluation) -> None:
    p = ws.project
    est = ev.estimate
    used = {ln.rate_id for ln in est.lines if ln.rate_id}
    rates = {r.rate_id: r for r in p.rate_book.rates}
    from ...io.export import is_fictional_rate

    fict = sum(1 for rid in used if rid in rates and is_fictional_rate(rates[rid]))
    parts = []
    if fict:
        parts.append(f"<b>{fict} of {len(used)} rates used are FICTIONAL demo data</b> - not market prices. Upload "
                     "supplier quotes or your own price list in the Rate book tab.")
    parts.append(f"Rate book <b>{esc(est.rate_book_name)}</b> · pricing date {est.pricing_date:%d %b %Y} · "
                 f"{esc(est.location)} · {esc(est.currency)} · "
                 + ("VAT added as a layer-9 line" if p.settings.include_vat else "all amounts net of VAT"))
    html(callout(" ".join(parts), title="Pricing basis", tone="warn" if fict else "info"))
    from ...costing.rates import PRICING_DATE_WARNING

    excluded = [w for w in est.warnings if w.startswith(PRICING_DATE_WARNING) and "newer, higher-priority" in w]
    if excluded:
        html(callout(esc(excluded[0].split(":", 1)[1].strip()) + " Change the pricing date in the sidebar settings.",
                     title="Newer rates excluded by the pricing date", tone="danger"))


def _boundary_cards(ws: S.Workspace, ev: S.Evaluation) -> None:
    est = ev.estimate
    cur = est.currency
    items = []
    final = "total_development_cost" if any(b.key == "total_development_cost" for b in est.boundaries) else "contract_sum"
    for b in est.boundaries:
        per = b.amount / est.gia_m2 if est.gia_m2 > 0 else float("nan")
        detail = (f'<div class="hbv-card-def">{esc(b.definition)}</div>'
                  f'<div class="hbv-card-ex"><b>Excludes:</b> {esc(b.excludes or "-")}</div>')
        items.append(card(b.name, fmt.money(b.amount, cur), sub=f"{fmt.money(per, cur)} / m² GIA",
                          detail_html=detail, accent=b.key in ("construction_incl_contingency", final)))
    if est.sales_value is not None:
        items.append(card("Sales value (GDV)", fmt.money(est.sales_value, cur), sub="reported separately",
                          detail_html='<div class="hbv-card-def">Gross development value entered as an assumption. '
                                      'It is never included in any cost boundary.</div>'))
    cards(items)


def _layer_table(est) -> None:
    cs = next((b.amount for b in est.boundaries if b.key == "contract_sum"), None)
    rows = []
    for layer in CostLayer:
        v = float(est.layer_totals.get(layer.value, 0.0))
        rows.append({"layer": f"{layer.value.split('_')[0]} {COST_LAYER_NAMES[layer]}", "amount": v,
                     "% of contract sum": (v / cs) if cs else None})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=36 + 35 * len(rows),
                 column_config={"layer": st.column_config.TextColumn(width="medium"),
                                "amount": st.column_config.NumberColumn(f"{est.currency}", format="%,.0f",
                                                                        width="small"),
                                "% of contract sum": st.column_config.NumberColumn("% of CS", format="percent",
                                                                                   width="small")})
    notes = list(est.notes) + list(est.warnings)
    if notes:
        with st.expander(f"Estimate notes and warnings ({len(notes)})"):
            for n in notes:
                st.markdown(f"- {esc(n)}")
    if est.unresolved_items:
        html(callout("<ul>" + "".join(f"<li>{esc(i)}</li>" for i in est.unresolved_items[:30]) + "</ul>",
                     title=f"Unresolved ({len(est.unresolved_items)}) - not priced as zero", tone="danger"))


# =============================================================================
# Cost lines
# =============================================================================
def _cost_lines(ws: S.Workspace, ev: S.Evaluation) -> None:
    p = ws.project
    est = ev.estimate
    from ...io.export import is_fictional_rate

    rates = {r.rate_id: r for r in p.rate_book.rates}
    layers = [lay.value for lay in CostLayer]
    c1, c2 = st.columns([2, 1.5])
    sel = c1.multiselect("Layer", layers, key="cl_layer", format_func=lambda v: f"{v[0]} {COST_LAYER_NAMES[CostLayer(v)]}",
                         placeholder="All layers")
    q = c2.text_input("Search", key="cl_q", placeholder="description, cost key, supplier…")
    rows = []
    for ln in est.lines:
        if sel and ln.layer.value not in sel:
            continue
        r = rates.get(ln.rate_id or "")
        text = f"{ln.description} {ln.cost_key} {ln.rate_id} {(r.supplier if r else '')}".lower()
        if q and q.lower() not in text:
            continue
        rows.append({
            "layer": ln.layer.value[0], "description": ln.description, "quantity": ln.quantity, "unit": ln.unit,
            "rate": ln.rate_value, "amount": ln.amount, "basis": ln.basis.value, "cost key": ln.cost_key or "",
            "rate id": ln.rate_id or "",
            "source": ("FICTIONAL · " if r and is_fictional_rate(r) and "FICTIONAL" not in r.source else "")
                      + (r.source if r else ""),
            "source type": r.source_type.value if r else "", "supplier": r.supplier if r else "",
            "rate date": r.effective_date.isoformat() if r else "", "location": r.location if r else "",
            "tax": r.tax_treatment.value if r else "", "delivery": r.delivery_treatment.value if r else "",
            "valid until": r.valid_until.isoformat() if r and r.valid_until else "",
            "uncertainty": f"{ln.uncertainty_low:+.0%} / {ln.uncertainty_high:+.0%}",
            "formula": ln.formula})
    if not rows:
        st.info("No cost lines match.")
        return
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, width="stretch", height=440,
                 column_config={"quantity": st.column_config.NumberColumn(format="%.2f"),
                                "rate": st.column_config.NumberColumn(format="%.2f"),
                                "amount": st.column_config.NumberColumn(f"amount ({est.currency})", format="%,.0f"),
                                "description": st.column_config.TextColumn(width="medium"),
                                "formula": st.column_config.TextColumn(width="large")})
    st.caption(f"{len(rows)} of {len(est.lines)} cost lines · amounts net of VAT, after unit / currency / escalation / "
               "regional conversions listed in each formula. Uncertainty = the rate's assumed range (used by the "
               "simulation).")


# =============================================================================
# Rate book
# =============================================================================
def _rate_book(ws: S.Workspace) -> None:
    from ...costing.rates import (RATE_COLUMNS, RateBookError, load_rate_book_csv, load_rate_book_json,
                                  merge_rate_books, rate_book_from_records, rate_book_to_dataframe)

    p = ws.project
    book = p.rate_book
    c1, c2 = st.columns([1.3, 1], gap="medium")
    with c1:
        html(f'<div style="font-weight:600">{esc(book.name)}</div><div class="hbv-small">{len(book.rates)} rate(s) · '
             f'{esc(book.notes)[:200]}</div>')
        if book.warnings:
            with st.expander(f"Load warnings ({len(book.warnings)})"):
                for w in book.warnings[:60]:
                    st.markdown(f"- {esc(w)}")
    with c2:
        gen = st.session_state.get("rb_gen", 0)
        up = st.file_uploader("Upload a rate book (CSV or JSON, columns = Rate fields)", type=["csv", "json"],
                              key=f"rb_up_{gen}", help="Validated row by row (≤ 5 MB, ≤ 20 000 rows); invalid rows "
                                                       "are skipped with a reason. Nothing is evaluated.")
        if up is not None:
            name = Path(up.name).stem[:80] or "uploaded rate book"
            try:
                data = io.BytesIO(up.getvalue())
                newb = load_rate_book_json(data, name=name) if up.name.lower().endswith(".json") \
                    else load_rate_book_csv(data, name=name)
            except RateBookError as e:
                st.error(f"Rate book rejected: {e}")
                newb = None
            if newb is not None:
                st.caption(f"Parsed {len(newb.rates)} valid rate(s) from '{esc(up.name)}'.")
                for w in newb.warnings[:12]:
                    st.warning(w)
                b1, b2 = st.columns(2)
                if b1.button("Replace rate book", key="rb_replace", disabled=not newb.rates):
                    S.replace_rate_book(ws, newb)
                    st.session_state["rb_gen"] = gen + 1
                    ws.say("success", f"Rate book replaced by '{newb.name}' ({len(newb.rates)} rates).")
                    st.rerun()
                if b2.button("Merge (adds / replaces by rate_id)", key="rb_merge", disabled=not newb.rates):
                    S.replace_rate_book(ws, merge_rate_books(book, newb, name=f"{book.name} + {newb.name}"))
                    st.session_state["rb_gen"] = gen + 1
                    ws.say("success", f"Merged {len(newb.rates)} rate(s); supplier quotes outrank manual, price-list, "
                                      "adapter and demo rates for the same cost key.")
                    st.rerun()
    df = rate_book_to_dataframe(book)
    for c in ("effective_date", "valid_until"):
        df[c] = df[c].astype("string")
    with st.form("rb_edit", border=False):
        edited = st.data_editor(
            df, key=f"rb_editor_{S.fp(book)[:10]}", num_rows="dynamic", hide_index=True, width="stretch", height=380,
            column_config={
                "value": st.column_config.NumberColumn(format="%.4f", min_value=0.0),
                "uncertainty_low": st.column_config.NumberColumn(format="%.2f", min_value=-1.0, max_value=0.0),
                "uncertainty_high": st.column_config.NumberColumn(format="%.2f", min_value=0.0, max_value=5.0),
                "layer": st.column_config.SelectboxColumn(options=[lay.value for lay in CostLayer]),
                "source_type": st.column_config.SelectboxColumn(
                    options=["fictional_demo", "supplier_quote", "price_list", "manual", "adapter"]),
                "tax_treatment": st.column_config.SelectboxColumn(
                    options=["ex_vat", "inc_vat", "zero_rated", "exempt", "unknown"]),
                "delivery_treatment": st.column_config.SelectboxColumn(
                    options=["delivered_included", "ex_works", "delivery_charged_separately", "collection",
                             "not_applicable", "unknown"]),
                "effective_date": st.column_config.TextColumn(help="YYYY-MM-DD"),
                "valid_until": st.column_config.TextColumn(help="YYYY-MM-DD (quotes)"),
            })
        ok = st.form_submit_button("Apply rate edits", type="primary")
    st.caption("Edit values, ranges, sources or validity inline. A rate you edit should carry an honest source "
               "type (e.g. 'manual' or 'supplier_quote' with a quote reference) - the demo rows stay FICTIONAL.")
    if ok:
        recs = []
        for r in edited.to_dict(orient="records"):
            rec = {}
            for k in RATE_COLUMNS:
                v = r.get(k)
                rec[k] = "" if v is None or (isinstance(v, float) and math.isnan(v)) or (v is pd.NA) else str(v)
            recs.append(rec)
        newb = rate_book_from_records(recs, name=book.name, notes=book.notes + " Edited in the UI.")
        if not newb.rates:
            st.error("No valid rates after editing - the rate book was not changed.")
        else:
            S.replace_rate_book(ws, newb)
            msg = f"Rate book updated ({len(newb.rates)} rates)."
            if newb.warnings:
                msg += " " + " | ".join(newb.warnings[:5])
            ws.say("warning" if newb.warnings else "success", msg)
            st.rerun()
    st.download_button("Download rate book (CSV)", data=df.to_csv(index=False).encode("utf-8"),
                       file_name="rate_book.csv", mime="text/csv", key="rb_dl")


# =============================================================================
# Commercial parameters
# =============================================================================
_FALLBACK_LABELS = {"prelims_weekly_cost": "prelims weekly", "prelims_fixed_setup": "prelims set-up",
                   "cost_per_delivery_load": "cost per delivery load", "cost_per_skip": "cost per skip"}


def _rates_in_force(ws: S.Workspace) -> dict[str, tuple[bool, str]]:
    """For each CostParameters fallback field: (rate book rate in force?, short text of what the engine uses)."""
    from ...costing.engine import COST_PARAMETER_FALLBACKS
    from ...costing.rates import resolve_rate_detailed

    p = ws.project
    cur = p.settings.currency
    out: dict[str, tuple[bool, str]] = {}
    for name, (ck, unit) in COST_PARAMETER_FALLBACKS.items():
        rr = resolve_rate_detailed(p.rate_book, ck, unit, settings=p.settings)
        if rr.found:
            out[name] = (True, f"rate {rr.rate.rate_id} = {cur} {rr.value:,.2f}/{unit} ({ck}) is in force - this "
                               "fallback is not used")
        else:
            out[name] = (False, f"no usable {ck} rate in the rate book - this fallback IS used")
    return out


def _commercial(ws: S.Workspace, ev: S.Evaluation) -> None:
    cp = ws.project.cost_parameters
    cur = ws.project.settings.currency
    in_force = _rates_in_force(ws)

    def fb_help(name: str) -> str:
        text = in_force[name][1]
        return f"Fallback, used only when the rate book has no prelim: / log: rate for it. Now: {text}."

    def fb_label(name: str, base: str) -> str:
        return base + (" · fallback (rate in force)" if in_force[name][0] else " · fallback (IN USE)")

    with st.form("cp_form", border=False):
        st.markdown("**Preliminaries and logistics**")
        c = st.columns(4)
        weekly = c[0].number_input(fb_label("prelims_weekly_cost", f"Prelims weekly ({cur})"),
                                   value=float(cp.prelims_weekly_cost), min_value=0.0, step=50.0,
                                   help=fb_help("prelims_weekly_cost"))
        setup = c[1].number_input(fb_label("prelims_fixed_setup", f"Prelims set-up ({cur})"),
                                  value=float(cp.prelims_fixed_setup), min_value=0.0, step=100.0,
                                  help=fb_help("prelims_fixed_setup"))
        weeks = c[2].number_input("Default programme (weeks)", value=float(cp.default_programme_weeks), min_value=1.0,
                                  step=1.0, help="Used only when no programme is supplied (the UI supplies one).")
        load = c[3].number_input(fb_label("cost_per_delivery_load", f"Cost per delivery load ({cur})"),
                                 value=float(cp.cost_per_delivery_load), min_value=0.0, step=5.0,
                                 help=fb_help("cost_per_delivery_load"))
        c = st.columns(4)
        skipv = c[0].number_input("Skip volume (m³)", value=float(cp.skip_volume_m3), min_value=0.5, step=0.5)
        skipc = c[1].number_input(fb_label("cost_per_skip", f"Cost per skip ({cur})"), value=float(cp.cost_per_skip),
                                  min_value=0.0, step=10.0, help=fb_help("cost_per_skip"))
        bulk = c[2].number_input("Waste bulking factor", value=float(cp.waste_bulking_factor), min_value=1.0,
                                 max_value=3.0, step=0.1)
        st.caption("Prelims weekly / set-up, cost per delivery load and cost per skip are **fallbacks**: the engine "
                   "uses the rate book's prelim:weekly, prelim:setup, log:delivery_load and log:skip rates when they "
                   "exist. In force now - "
                   + "; ".join(f"{_FALLBACK_LABELS[k]}: {t}" for k, (_, t) in in_force.items()) + ". To change "
                   "those amounts, edit the rates in the Rate book tab.")
        st.markdown("**Fees (fractions of a boundary)**")
        fees_df = pd.DataFrame([{"name": f.name, "percent": 100 * f.fraction, "applies_to": f.applies_to,
                                 "recurs per house": bool(f.recurs_per_house), "note": f.note} for f in cp.fees],
                               columns=["name", "percent", "applies_to", "recurs per house", "note"])
        fees_ed = st.data_editor(fees_df, key="cp_fees", num_rows="dynamic", hide_index=True, width="stretch",
                                 column_config={"percent": st.column_config.NumberColumn("percent (%)", min_value=0.0,
                                                                                         max_value=100.0, format="%.2f"),
                                                "applies_to": st.column_config.SelectboxColumn(
                                                    options=["direct", "construction"], required=True),
                                                "recurs per house": st.column_config.CheckboxColumn(
                                                    help="Repeat build only: unticked = one-off (design-stage) fee, "
                                                         "covered by the scenario's reusable design cost when it "
                                                         "has one. The single-house estimate charges every fee.")})
        st.markdown("**Risk, overhead and margin**")
        c = st.columns(3)
        cont = c[0].number_input("Contingency (%)", value=100 * cp.contingency_fraction, min_value=0.0, max_value=100.0,
                                 step=0.5)
        oh = c[1].number_input("Overhead (%)", value=100 * cp.overhead_fraction, min_value=0.0, max_value=100.0, step=0.5)
        mg = c[2].number_input("Margin (%)", value=100 * cp.margin_fraction, min_value=0.0, max_value=100.0, step=0.5)
        cont_basis = st.text_input("Contingency basis", value=cp.contingency_basis, max_chars=300)
        st.markdown("**Land, finance, taxes and sales (layer 9 - only items you enter)**")
        c = st.columns(4)
        land = c[0].number_input(f"Land ({cur})", value=cp.land_cost, min_value=0.0, step=1000.0, placeholder="none")
        fin_r = c[1].number_input("Finance rate (% p.a.)", value=None if cp.finance_rate_annual is None
                                  else 100 * cp.finance_rate_annual, min_value=0.0, max_value=100.0, step=0.25,
                                  placeholder="none")
        fin_m = c[2].number_input("Finance period (months)", value=cp.finance_months, min_value=0.0, step=1.0,
                                  placeholder="none")
        sales_f = c[3].number_input("Sales costs (% of GDV)", value=None if cp.sales_cost_fraction is None
                                    else 100 * cp.sales_cost_fraction, min_value=0.0, max_value=100.0, step=0.25,
                                    placeholder="none")
        c = st.columns([1, 2])
        gdv = c[0].number_input(f"Sales value / GDV ({cur})", value=cp.sales_value, min_value=0.0, step=5000.0,
                                placeholder="none", help="Reported separately as GDV - never part of any cost.")
        tax_df = pd.DataFrame([{"tax": k, "amount": v} for k, v in cp.taxes.items()], columns=["tax", "amount"])
        with c[1]:
            tax_ed = st.data_editor(tax_df, key="cp_taxes", num_rows="dynamic", hide_index=True, width="stretch",
                                    column_config={"amount": st.column_config.NumberColumn(f"amount ({cur})",
                                                                                           min_value=0.0)})
        ok = st.form_submit_button("Apply commercial parameters", type="primary")
    st.caption("All commercial parameters are labelled assumptions. Fees, contingency, overhead and margin cascade "
               "as described in the boundary definitions; sales value (GDV) is shown separately.")
    if ok:
        fees = []
        for r in fees_ed.to_dict(orient="records"):
            if not r.get("name") or r.get("percent") is None or (isinstance(r["percent"], float) and math.isnan(r["percent"])):
                continue
            rec = r.get("recurs per house")
            fees.append({"name": str(r["name"])[:120], "fraction": float(r["percent"]) / 100.0,
                         "applies_to": r.get("applies_to") or "construction", "note": str(r.get("note") or "")[:300],
                         "recurs_per_house": True if rec is None or rec is pd.NA else bool(rec)})
        taxes = {}
        for r in tax_ed.to_dict(orient="records"):
            if r.get("tax") and r.get("amount") is not None and not (isinstance(r["amount"], float) and math.isnan(r["amount"])):
                taxes[str(r["tax"])[:80]] = float(r["amount"])
        data = {"prelims_weekly_cost": weekly, "prelims_fixed_setup": setup, "default_programme_weeks": weeks,
                "cost_per_delivery_load": load, "skip_volume_m3": skipv, "cost_per_skip": skipc,
                "waste_bulking_factor": bulk, "fees": fees, "contingency_fraction": cont / 100.0,
                "contingency_basis": cont_basis, "overhead_fraction": oh / 100.0, "margin_fraction": mg / 100.0,
                "land_cost": land, "finance_rate_annual": None if fin_r is None else fin_r / 100.0,
                "finance_months": fin_m, "taxes": taxes, "sales_cost_fraction": None if sales_f is None else sales_f / 100.0,
                "sales_value": gdv}
        before = cp
        err = S.update_cost_parameters(ws, data)
        if err:
            st.error(err)
        else:
            ws.say(*_applied_message(ws, ev, before, in_force))
            st.rerun()


def _applied_message(ws: S.Workspace, ev: S.Evaluation, before, in_force: dict[str, tuple[bool, str]]
                     ) -> tuple[str, str]:
    """Flash message that reports what actually changed (never claims an effect that did not happen)."""
    after = ws.project.cost_parameters
    cur = ws.project.settings.currency
    shadowed = [_FALLBACK_LABELS[k] for k, (used_rate, _) in in_force.items()
                if used_rate and getattr(before, k) != getattr(after, k)]
    note = (f" Changed fallback(s) {', '.join(shadowed)} have no effect: the rate book's prelim: / log: rates are "
            "in force (edit them in the Rate book tab)." if shadowed else "")
    if after == before:
        return "info", "No commercial parameter changed."
    new_ev = S.evaluate(ws)
    old_cs = ev.estimate.boundary("contract_sum").amount
    new_cs = new_ev.estimate.boundary("contract_sum").amount if new_ev is not None else old_cs
    if abs(new_cs - old_cs) < 0.005 and new_ev is not None and \
            new_ev.estimate.layer_totals == ev.estimate.layer_totals:
        return "warning", "Commercial parameters saved - the single-house estimate did not change." + note
    return "success", (f"Commercial parameters applied - contract sum {fmt.money(old_cs, cur)} → "
                       f"{fmt.money(new_cs, cur)}." + note)


# =============================================================================
# Uncertainty
# =============================================================================
def _uncertainty(ws: S.Workspace, ev: S.Evaluation) -> None:
    from ...simulation.uncertainty import GROUPS, INTERVAL_TYPE

    p = ws.project
    cfg = p.simulation_config
    with st.form("sim_form", border=True):
        c = st.columns([1, 1, 1, 3])
        n = c[0].number_input("Samples", value=int(min(cfg.n_samples, 300)), min_value=20, max_value=5000, step=50,
                              help="Each sample re-computes geometry → quantities → programme → logistics → cost for "
                                   "one coherent house. ~500+ for stable rankings.")
        seed = c[1].number_input("Seed", value=int(cfg.seed), min_value=0, max_value=2 ** 31 - 1, step=1)
        method = c[2].selectbox("Sampling", ["lhs", "mc"], index=0 if cfg.method == "lhs" else 1,
                                format_func=lambda m: "Latin hypercube" if m == "lhs" else "Monte Carlo")
        groups = c[3].multiselect("Uncertainty groups", list(GROUPS),
                                  default=[g for g in cfg.include_groups if g in GROUPS],
                                  format_func=lambda g: GROUP_LABELS.get(g, g))
        run = st.form_submit_button("Run simulation", type="primary")
    if run:
        if not groups:
            st.error("Choose at least one uncertainty group.")
        else:
            with st.spinner(f"Simulating {int(n)} coherent houses…"):
                try:
                    S.run_simulation(ws, n_samples=int(n), seed=int(seed), groups=groups, method=method)
                except Exception as e:  # noqa: BLE001
                    st.error(f"Simulation failed: {type(e).__name__}: {e}")
    sim = ws.simulation
    if sim is None:
        html(callout("Run a simulation to see P10 / P50 / P90, the drivers of the spread and which missing evidence "
                     "would reduce it most. " + esc(INTERVAL_TYPE), title="Uncertainty", tone="neutral"))
        return
    if not S.simulation_is_current(ws):
        html(callout("The twin, rates or parameters changed after this simulation - the results below describe the "
                     "earlier inputs. Run it again for the current model.", title="Simulation out of date",
                     tone="danger"))
    est = ev.estimate
    cur = est.currency
    by = {m.metric: m for m in sim.metrics}
    m = by.get("construction_incl_contingency")
    cs = by.get("contract_sum")
    det = est.boundary("construction_incl_contingency").amount
    if m is not None:
        width = m.p90 - m.p10
        cards([
            card("P10 · construction incl. contingency", fmt.money(m.p10, cur), sub="10% of samples below"),
            card("P50 (median)", fmt.money(m.p50, cur), sub=f"deterministic {fmt.money(det, cur)}", accent=True),
            card("P90", fmt.money(m.p90, cur), sub=f"P10–P90 width {fmt.money(width, cur)} ({width / m.p50:.0%})"),
            card("Contract sum P50", fmt.money(cs.p50, cur) if cs else "–",
                 sub=f"P10 {fmt.money_short(cs.p10, cur)} · P90 {fmt.money_short(cs.p90, cur)}" if cs else ""),
            card("Samples", f"{sim.n_samples:,}", sub=f"{sim.config.method.upper()} · seed {sim.config.seed}"),
        ])
        samples = sim.samples.get("construction_incl_contingency", [])
        c1, c2 = st.columns([1.45, 1], gap="medium")
        with c1:
            st.plotly_chart(histogram_cdf(samples, p10=m.p10, p50=m.p50, p90=m.p90, deterministic=det, currency=cur,
                                          height=400), key="u_hist", theme=None, config={"displaylogo": False})
        with c2:
            section_title("What to resolve next", sub="ranked by share of the cost spread")
            iv = sim.information_value
            if iv:
                items = []
                for i in iv:
                    share = i.get("variance_share") or 0.0
                    items.append(
                        f'<div class="hbv-iv"><div class="hbv-iv-rank">{esc(i.get("rank"))}</div><div>'
                        f'<div class="hbv-iv-act">{esc(i.get("resolving_action"))}</div>'
                        f'<div class="hbv-small">{esc(GROUP_LABELS.get(i.get("group"), i.get("group")))} · '
                        f'<span class="hbv-mono">{share:.0%}</span> of variance · P10–P90 accounted '
                        f'<span class="hbv-mono">{esc(fmt.money(i.get("p10_p90_width_accounted"), cur))}</span>'
                        f'</div><div class="hbv-bar"><div style="width:{min(100.0, 100 * share):.0f}%"></div></div>'
                        f'<div class="hbv-range">{esc(", ".join(i.get("top_inputs", [])[:3]))}</div></div></div>')
                html('<div class="hbv-ivs">' + "".join(items) + "</div>")
                st.caption("Variance share = first-order (binned) share of the cost variance per group; groups can "
                           "overlap, so shares need not sum to 100%. Rankings stabilise from ~500 samples.")
    c1, c2 = st.columns([1, 1], gap="medium")
    with c1:
        section_title("Sensitivity", sub="tornado of the strongest inputs")
        if sim.sensitivity:
            st.plotly_chart(tornado(sim.sensitivity, top=12, height=400), key="u_tornado", theme=None,
                            config={"displaylogo": False})
            st.caption("Bars: Spearman rank correlation with construction cost (terracotta raises, steel lowers cost); "
                       "labels: first-order variance share. Per-input values include effects shared through group "
                       "factors - use the group ranking for decisions.")
    with c2:
        section_title("Quantiles", sub="all simulated metrics")
        qrows = []
        for s in sim.metrics:
            unit = s.unit.replace("CUR", cur)
            qrows.append({"metric": METRIC_LABELS.get(s.metric, s.metric.replace("_", " ")), "unit": unit,
                          "P10": s.p10, "P50": s.p50, "P90": s.p90, "mean": s.mean})
        st.dataframe(pd.DataFrame(qrows), hide_index=True, width="stretch", height=38 + 35 * len(qrows),
                     column_config={k: st.column_config.NumberColumn(format="%,.2f")
                                    for k in ("mean", "P10", "P50", "P90")})
        if sim.conditional_on_ground:
            section_title("Conditional on ground class", sub="site investigation resolves this")
            probs = sim.config.ground_classes
            grows = [{"ground class": k.replace("_", " "), "assumed probability": probs.get(k),
                      "P10": v.p10, "P50": v.p50, "P90": v.p90, "mean": v.mean}
                     for k, v in sim.conditional_on_ground.items()]
            st.dataframe(pd.DataFrame(grows), hide_index=True, width="stretch",
                         column_config={"assumed probability": st.column_config.NumberColumn(format="percent"),
                                        **{k: st.column_config.NumberColumn(f"{k} ({cur})", format="%,.0f")
                                           for k in ("P10", "P50", "P90", "mean")}})
    html(callout(esc(sim.interval_type), title="Interval type", tone="info"))
    with st.expander(f"Sampled inputs ({len(sim.inputs)}) and simulation notes"):
        st.dataframe(pd.DataFrame([{"input": i.name, "group": i.group, "distribution": i.distribution, "low": i.low,
                                    "mode": i.mode, "high": i.high, "unit": i.unit, "basis": i.basis.value,
                                    "description": i.description} for i in sim.inputs]),
                     hide_index=True, width="stretch", height=300)
        for n in sim.notes:
            st.markdown(f"- {esc(n)}")


__all__ = ["render"]
