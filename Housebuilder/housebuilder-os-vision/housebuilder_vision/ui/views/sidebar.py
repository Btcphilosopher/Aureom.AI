"""Sidebar: project (demo / new / save & load), settings, downloads; plus the page header + KPI strip."""

from __future__ import annotations

from datetime import date
from typing import Optional

import streamlit as st

from ... import __version__
from .. import fmt
from .. import state as S
from ..components import guard, html
from ..theme import badge, esc, tag

CURRENCIES = ("GBP", "EUR", "USD", "AUD", "CAD", "NZD", "CHF", "SEK", "NOK", "DKK", "PLN")


# =============================================================================
# Callbacks
# =============================================================================
def _cb_load_demo() -> None:
    ws = S.get_workspace()
    try:
        S.load_demo(ws, side_view=bool(st.session_state.get("demo_side")),
                    concept=bool(st.session_state.get("demo_concept")))
    except Exception as e:  # noqa: BLE001
        ws.say("error", f"The demo could not be loaded: {type(e).__name__}: {e}")


def _cb_new_project() -> None:
    ws = S.get_workspace()
    try:
        S.new_project(ws, st.session_state.get("np_name", ""), use_demo_rates=bool(st.session_state.get("np_rates")))
    except Exception as e:  # noqa: BLE001
        ws.say("error", f"New project failed: {type(e).__name__}: {e}")


def _cb_save() -> None:
    ws = S.get_workspace()
    try:
        ws.say("success", S.save_project(ws))
    except Exception as e:  # noqa: BLE001
        ws.say("error", f"Save failed: {type(e).__name__}: {e}")


def _cb_load_saved() -> None:
    ws = S.get_workspace()
    pid = st.session_state.get("saved_pick")
    if not pid:
        return
    try:
        ws.say("success", S.load_saved_project(ws, pid))
    except Exception as e:  # noqa: BLE001
        ws.say("error", f"Load failed: {type(e).__name__}: {e}")


def _cb_setting(field: str, key: str) -> None:
    ws = S.get_workspace()
    v = st.session_state.get(key)
    if field == "unit_system":
        v = "imperial" if str(v).lower().startswith("imperial") else "metric"
    if field == "vat_rate" and v is not None:
        v = float(v) / 100.0
    err = S.update_settings(ws, **{field: v})
    if err:
        ws.say("error", err)


def _cb_fx(cur: str, key: str) -> None:
    ws = S.get_workspace()
    fx = dict(ws.project.settings.fx_rates)
    v = st.session_state.get(key)
    if v is None or float(v) <= 0:
        fx.pop(cur, None)
    else:
        fx[cur] = float(v)
    err = S.update_settings(ws, fx_rates=fx)
    if err:
        ws.say("error", err)


def _cb_export() -> None:
    ws = S.get_workspace()
    try:
        ev = S.evaluate(ws)
        if ev is None:
            ws.say("error", "Build a twin first - there is nothing to export yet.")
            return
        out = S.export_bundle(ws, ev, st.session_state.get("export_formats") or ["json", "csv"])
        if out["manifest"].warnings:
            ws.say("warning", "Export notes: " + " | ".join(out["manifest"].warnings[:4]))
    except Exception as e:  # noqa: BLE001
        ws.say("error", f"Export failed: {type(e).__name__}: {e}")


# =============================================================================
# Sidebar
# =============================================================================
def render_sidebar(ws: S.Workspace) -> None:
    with st.sidebar:
        html('<div class="hbv-brand" style="margin-top:.2rem"><span class="hbv-brand-mark">AUREOM.AI</span></div>'
             '<div style="font-weight:600;font-size:1.02rem;margin-top:.1rem">Housebuilder.OS Vision</div>'
             f'<div class="hbv-small">Image evidence → editable twin → quantities → costs · v{esc(__version__)}</div>')
        with guard("Project panel"):
            _project_panel(ws)
        if ws.project is not None:
            with guard("Settings"):
                _settings_panel(ws)
            with guard("Downloads"):
                _downloads_panel(ws)
        html('<div class="hbv-rule"></div><div class="hbv-small">Conceptual reconstruction for concept-stage '
             'estimating. Not a survey, design, tender price or compliance check. Demo data and prices are '
             'FICTIONAL.</div>')


def _project_panel(ws: S.Workspace) -> None:
    st.markdown("### Project")
    p = ws.project
    if p is not None:
        twin = p.twin
        html(f'<div style="font-weight:600;font-size:.86rem">{esc(p.name)}</div>'
             f'<div class="hbv-small hbv-mono">{esc(p.project_id)}</div>'
             f'<div class="hbv-small">{len(p.images)} image(s) · '
             + (f'twin v{twin.version} from {esc(twin.source_hypothesis_id or "-")}' if twin else "no twin yet")
             + '</div>')
    st.button("Load fictional demo", key="load_demo", type="primary", width="stretch", on_click=_cb_load_demo,
              help="Aureom Demo House, Plot 7 - synthetic elevation, fictional survey dimension and prices.")
    st.checkbox("with the left side elevation", key="demo_side",
                help="Adds the left (gable) elevation: observed depth and pitch (multi-view).")
    st.checkbox("with an AI concept example", key="demo_concept",
                help="Adds an AI-generated concept render: flagged as a concept reference, never as observed.")
    with st.expander("New project"):
        st.text_input("Name", key="np_name", placeholder="e.g. Plot 12, Station Road")
        st.checkbox("Start with the FICTIONAL demo rate book", value=True, key="np_rates",
                    help="Fictional prices for exploration only - upload your own rate book in Costs.")
        st.button("Create project", key="np_create", on_click=_cb_new_project, width="stretch")
    with st.expander("Save / load"):
        st.button("Save project", key="save_project", on_click=_cb_save, disabled=p is None, width="stretch")
        saved = S.list_saved_projects()
        if saved:
            ids = [s.project_id for s in saved]
            labels = {s.project_id: f"{s.name} · {s.updated_at:%Y-%m-%d %H:%M}" for s in saved}
            st.selectbox("Saved projects", ids, key="saved_pick", format_func=lambda i: labels.get(i, i))
            st.button("Load selected", key="load_saved", on_click=_cb_load_saved, width="stretch")
        else:
            st.caption("No saved projects yet.")
        st.caption(f"Store: {S.data_dir() / 'housebuilder.db'} (SQLite, validated state + run log).")


def _settings_panel(ws: S.Workspace) -> None:
    p = ws.project
    s = p.settings
    pid = p.project_id
    st.markdown("### Settings")
    st.text_input("Location", value=s.site_location, key=f"set_loc_{pid}", on_change=_cb_setting,
                  args=("site_location", f"set_loc_{pid}"))
    st.text_input("Region", value=s.region, key=f"set_region_{pid}", on_change=_cb_setting,
                  args=("region", f"set_region_{pid}"))
    c1, c2 = st.columns(2)
    curs = list(CURRENCIES) if s.currency in CURRENCIES else [s.currency, *CURRENCIES]
    c1.selectbox("Currency", curs, index=curs.index(s.currency), key=f"set_cur_{pid}", on_change=_cb_setting,
                 args=("currency", f"set_cur_{pid}"))
    c2.date_input("Pricing date", value=s.pricing_date, key=f"set_date_{pid}", on_change=_cb_setting,
                  args=("pricing_date", f"set_date_{pid}"), min_value=date(2000, 1, 1), max_value=date(2100, 12, 31))
    foreign = sorted({r.currency for r in p.rate_book.rates if r.currency != s.currency})
    for cur in foreign:
        st.number_input(f"FX: 1 {cur} = ? {s.currency}", value=float(s.fx_rates[cur]) if cur in s.fx_rates else None,
                        min_value=0.0, step=0.01, format="%.4f", key=f"fx_{cur}_{pid}", on_change=_cb_fx,
                        args=(cur, f"fx_{cur}_{pid}"),
                        help="Rates in other currencies are excluded (listed as missing) until an FX rate is given.")
    st.radio("Display units", ["Metric", "Imperial"], index=0 if s.unit_system == "metric" else 1, horizontal=True,
             key=f"set_units_{pid}", on_change=_cb_setting, args=("unit_system", f"set_units_{pid}"),
             help="Display only - every calculation is SI metric.")
    st.toggle("Include VAT (layer 9)", value=s.include_vat, key=f"set_vat_{pid}", on_change=_cb_setting,
              args=("include_vat", f"set_vat_{pid}"),
              help="Adds VAT as a layer-9 line (development cost boundary). Off: all amounts net of VAT.")
    if s.include_vat:
        st.number_input("VAT rate (%)", value=round(100 * s.vat_rate, 2), min_value=0.0, max_value=50.0, step=0.5,
                        key=f"set_vat_rate_{pid}", on_change=_cb_setting, args=("vat_rate", f"set_vat_rate_{pid}"))
    with st.expander("Pricing adjustments"):
        st.number_input("Regional cost factor", value=float(s.regional_cost_factor), min_value=0.1, max_value=5.0,
                        step=0.01, key=f"set_regional_{pid}", on_change=_cb_setting, args=("regional_cost_factor", f"set_regional_{pid}"),
                        help="Applied to rates whose location differs from the project location (labelled).")
        st.number_input("Annual escalation", value=float(s.annual_escalation_rate), min_value=-0.5, max_value=1.0,
                        step=0.005, format="%.3f", key=f"set_escal_{pid}", on_change=_cb_setting,
                        args=("annual_escalation_rate", f"set_escal_{pid}"),
                        help="Applied to rates dated before the pricing date (fraction per year).")


def _downloads_panel(ws: S.Workspace) -> None:
    from ...io.ifc_adapter import ifc_available

    st.markdown("### Downloads")
    opts = ["json", "glb", "csv"] + (["ifc"] if ifc_available() else [])
    st.multiselect("Formats", opts, default=opts, key="export_formats",
                   help="JSON model state + results, GLB massing (visual only), CSV tables, IFC (conceptual, "
                        "approx. LOD 100-200; needs ifcopenshell).")
    st.button("Prepare export", key="prepare_export", on_click=_cb_export, width="stretch",
              disabled=ws.project is None or ws.project.twin is None)
    ex = ws.export
    if not ex:
        return
    ev = S.evaluate(ws)
    if ev is None or ex.get("key") != ev.key:
        st.caption("The export below was prepared before the latest edit - prepare it again for current results.")
    st.download_button("Download all (.zip)", data=ex["zip"], file_name=f"{S._slug(ws.project.project_id, 60)}.zip",
                       mime="application/zip", key="dl_zip", width="stretch", type="primary")
    for i, f in enumerate(ex["files"]):
        st.download_button(f"{f['name']}  ·  {f['size'] / 1024:,.0f} kB", data=f["data"], file_name=f["name"],
                           mime=f["mime"], key=f"dl_{i}", width="stretch", help=f.get("description") or None)
    if not ex.get("simulation_included"):
        st.caption("No current uncertainty simulation was included (run one in Costs, then prepare again).")


# =============================================================================
# Header
# =============================================================================
def render_header(ws: S.Workspace, ev: Optional[S.Evaluation]) -> None:
    p = ws.project
    sub = esc(p.name) if p is not None else "No project loaded"
    html('<div class="hbv-brand"><span class="hbv-brand-mark">AUREOM.AI</span>'
         '<span class="hbv-brand-name">Housebuilder.OS Vision</span>'
         f'<span class="hbv-brand-sub">{sub}</span></div>')
    if p is None or ev is None:
        html('<div class="hbv-rule"></div>')
        return
    k, prev = ws.cur_kpis or S.kpis(ev), ws.prev_kpis
    cur = ev.estimate.currency
    system = p.settings.unit_system

    def delta(name: str, f) -> str:
        if not prev or name not in prev:
            return ""
        d = k[name] - prev[name]
        if not fmt.is_num(d) or abs(d) < 1e-9:
            return ""
        return (f'<div class="hbv-kpi-d" title="change caused by the last edit">Δ {"+" if d > 0 else "−"}'
                f'{f(abs(d))}</div>')

    from ...core.provenance import weakest_basis
    from ...io.export import geometry_bases, is_fictional_rate

    twin = p.twin
    est = ev.estimate
    bnd = {b.key: b for b in est.boundaries}
    gia_basis = geometry_bases(twin)["gia"]

    def money_kpi(key: str, value: float) -> str:
        b = bnd.get(key)
        return ("≥ " if b is not None and b.unresolved_count else "") + fmt.money(value, cur)

    def basis_of(key: str):
        b = bnd.get(key)
        return b.basis if b is not None else None

    cons_b = basis_of("construction_incl_contingency")
    gia_v, gia_u = fmt.disp(k["gia_m2"], "m2", system)
    items = [
        ("GIA", f"{gia_v:,.1f} {fmt.unit_label(gia_u)}",
         delta("gia_m2", lambda d: f"{fmt.disp(d, 'm2', system)[0]:,.1f}"), gia_basis),
        ("Construction incl. cont.", money_kpi("construction_incl_contingency", k["construction"]),
         delta("construction", lambda d: fmt.money(d, cur)), cons_b),
        ("Contract sum", money_kpi("contract_sum", k["contract_sum"]),
         delta("contract_sum", lambda d: fmt.money(d, cur)), basis_of("contract_sum")),
        ("Cost / m² GIA", money_kpi("construction_incl_contingency", k["per_m2"]),
         delta("per_m2", lambda d: fmt.money(d, cur)), weakest_basis(cons_b, gia_basis) if cons_b else None),
        ("Programme", f"{k['programme_weeks']:.1f} wk", delta("programme_weeks", lambda d: f"{d:.1f} wk"), None),
        ("HLC", f"{k['hlc']:,.0f} W/K", delta("hlc", lambda d: f"{d:,.1f} W/K"), None),
        ("Embodied carbon", f"{k['carbon'] / 1000:,.1f} tCO₂e", delta("carbon", lambda d: f"{d / 1000:,.2f} t"), None),
    ]
    def kpi_badge(name: str, bb) -> str:
        if bb is None:
            return ""
        tip = f"{name}: weakest basis of the values it is derived from"
        return f'<div class="hbv-kpi-b">{badge(bb, title=tip)}</div>'

    body = "".join(f'<div class="hbv-kpi"><div class="hbv-kpi-k">{esc(a)}</div><div class="hbv-kpi-v">{esc(b)}</div>'
                   + kpi_badge(a, bb) + f"{c}</div>" for a, b, c, bb in items)
    status = S.twin_status(ws)
    concept = S.concept_source(ws)
    fictional = sum(1 for r in p.rate_book.rates if is_fictional_rate(r))
    scale_txt = f"scale: {twin.calibration_method.replace('_', ' ')}"
    if status == "orphaned":
        scale_txt += " (from removed evidence)"
    tags = [tag(f"twin v{twin.version} · {twin.source_hypothesis_id or 'manual'}", tone="gold"),
            tag(scale_txt, tone="neutral" if twin.calibration_method == "reference_measurement" and status != "orphaned"
                else "warn")]
    if concept == "all":
        tags.append(tag("from concept reference (indicative)", tone="danger",
                        title="Every image the twin was measured from is an AI concept / rendering / sketch: no "
                              "dimension describes an existing or measured building."))
    elif concept == "scale":
        tags.append(tag("scale from a concept reference", tone="danger",
                        title="The calibration image is an AI concept / rendering / sketch."))
    if fictional:
        tags.append(tag("FICTIONAL demo prices", tone="warn", title="Rates with source_type fictional_demo"))
    if est.unresolved_items:
        tags.append(tag(f"incomplete - {len(est.unresolved_items)} item(s) unpriced", tone="danger",
                        title="Unresolved quantities / missing rates are not priced: the cost figures are lower "
                              "bounds (Costs view)."))
    if S.reference_conflict(p.calibration) is not None:
        tags.append(tag("reference conflicts with scale cues", tone="danger"))
    if status == "stale":
        tags.append(tag("twin based on earlier evidence", tone="danger"))
    elif status == "orphaned":
        tags.append(tag("evidence removed - twin kept as a manual model", tone="warn"))
    html(f'<div class="hbv-kpis">{body}</div><div style="display:flex;gap:.35rem;flex-wrap:wrap;margin:-.15rem 0 .3rem 0">'
         + "".join(tags) + "</div>")


__all__ = ["render_header", "render_sidebar"]
