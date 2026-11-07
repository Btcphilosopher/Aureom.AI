"""Scenarios view: build-scenario comparison, repeat-build economics, programme / logistics, carbon / heat loss.

Each build scenario is one coherent house (hypothesis + assembly overrides + foundation + price
level); results are compared side by side and never averaged.  Repeat-build curves show average
C(n)/n, incremental C(n+1) - C(n) and the underlying marginal cost (without capacity steps, pack
rounding steps and all-units tier re-pricing) for the factory-gate and installed boundaries; the
table lists the steps / tier crossings between n and n+1 and the single house is reconciled with
the installed C(1).  Every
chart carries its assumptions / boundary caption: the programme is an indicative critical path,
carbon uses illustrative placeholder factors, heat loss is a simplified steady-state calculation
(not SAP / SBEM / PHPP) - none of them is a compliance or performance claim.
"""

from __future__ import annotations

import math
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ...core.models import DiscountTier, LearningCurve, ProductionScenario, StepCost
from .. import fmt
from .. import state as S
from ..charts import carbon_chart, gantt, heat_loss_chart, repeat_chart, scenario_multiples
from ..components import cards, guard, html, section_title
from ..theme import IVORY_MUTED, callout, card, esc


def render(ws: S.Workspace, ev: Optional[S.Evaluation]) -> None:
    p = ws.project
    if p is None or p.twin is None or ev is None:
        html(callout("Build a twin first - scenarios are evaluated from it.", title="Scenarios", tone="neutral"))
        return
    t1, t2, t3, t4 = st.tabs(["Build scenarios", "Repeat build", "Programme & logistics", "Carbon & heat loss"],
                             key="scenarios_subtab", on_change="rerun")
    with t1:
        with guard("Build-scenario comparison"):
            _build_scenarios(ws, ev)
    with t2:
        with guard("Repeat-build economics"):
            _repeat(ws, ev)
    with t3:
        with guard("Programme and logistics"):
            _programme(ws, ev)
    with t4:
        with guard("Carbon and heat loss"):
            _carbon_heat(ws, ev)


# =============================================================================
# Build scenarios
# =============================================================================
def _cb_add_build() -> None:
    ws = S.get_workspace()
    n = S.add_example_build_scenarios(ws)
    ws.say("success" if n else "warning", f"{n} example build scenario(s) added." if n else
           "No example scenario fits this project's hypotheses / library.")


def _build_scenarios(ws: S.Workspace, ev: S.Evaluation) -> None:
    p = ws.project
    if not p.build_scenarios:
        html(callout("No build scenarios on this project. Example scenarios compare masonry cavity, timber frame + "
                     "brick and timber frame + cladding on the available hypotheses.", title="Build scenarios",
                     tone="neutral"))
        st.button("Add example build scenarios", key="sc_add", on_click=_cb_add_build)
        return
    c1, c2, c3 = st.columns([1.2, 1, 2.5])
    simulate = c1.toggle("Include P10 / P90", value=False, key="sc_sim",
                         help="Runs a small uncertainty simulation per scenario (slower).")
    n = c2.number_input("Samples / scenario", value=60, min_value=20, max_value=1000, step=20, key="sc_n",
                        disabled=not simulate)
    with st.spinner("Evaluating scenarios…"):
        comp = S.compare_scenarios(ws, simulate=simulate, n=int(n))
    cur = ev.estimate.currency
    outs = comp.outcomes
    rows = []
    for o in outs:
        rows.append({"scenario": o.scenario_id, "name": o.name, "hypothesis": o.hypothesis_id,
                     "wall (mm)": 1000 * o.external_wall_thickness_m, "GIA (m²)": o.gia_m2,
                     f"construction ({cur})": o.construction_cost, f"per m² ({cur})": o.cost_per_m2_gia,
                     f"contract sum ({cur})": o.contract_sum, "labour h": o.labour_hours,
                     "programme (wk)": o.programme_weeks, "carbon (tCO₂e)": o.embodied_carbon_kgco2e / 1000,
                     "HLC (W/K)": o.heat_loss_coefficient_w_k, "peak load (kW)": o.peak_heat_load_kw,
                     "P10": o.cost_p10, "P50": o.cost_p50, "P90": o.cost_p90})
    df = pd.DataFrame(rows)
    money_cols = [f"construction ({cur})", f"per m² ({cur})", f"contract sum ({cur})", "P10", "P50", "P90"]
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={**{c: st.column_config.NumberColumn(format="%,.0f") for c in money_cols},
                                "wall (mm)": st.column_config.NumberColumn(format="%.0f"),
                                "GIA (m²)": st.column_config.NumberColumn(format="%.1f"),
                                "labour h": st.column_config.NumberColumn(format="%,.0f"),
                                "programme (wk)": st.column_config.NumberColumn(format="%.1f"),
                                "carbon (tCO₂e)": st.column_config.NumberColumn(format="%.1f"),
                                "HLC (W/K)": st.column_config.NumberColumn(format="%.0f"),
                                "peak load (kW)": st.column_config.NumberColumn(format="%.2f"),
                                "name": st.column_config.TextColumn(width="medium")})
    st.plotly_chart(scenario_multiples(outs, cur, height=420), key="sc_multi", theme=None,
                    config={"displaylogo": False})
    st.caption("Each scenario is one coherent house (one hypothesis, one assembly set); results are compared, never "
               "averaged. Hypothesis plausibility is a subjective prior. On the cost panel (when P10 / P90 are "
               "included) the line is the P10-P90 range of assumed scenario uncertainty and the gold diamond its P50; "
               "the bar is the deterministic estimate, which uses the modal (most likely) value of every input and "
               "can sit near or even below P10 when the input ranges are skewed upwards.")
    with guard("Questions that choose between scenarios"):
        _scenario_spreads(comp, cur)
    with st.expander("Key assumptions per scenario"):
        for o in outs:
            st.markdown(f"**{esc(o.scenario_id)} · {esc(o.name)}**")
            for a in o.key_assumptions:
                st.markdown(f"- {esc(a)}")
        for nn in comp.notes:
            st.caption(nn)


def _scenario_spreads(comp, cur: str) -> None:
    """Hypothesis / construction / foundation / price-level spreads between scenarios and what resolves them.

    These questions are kept as separate scenarios (never sampled into one house), so they never appear in
    the simulation's "what to resolve next"; ``simulation.scenarios.scenario_spread_entries`` reports them.
    """
    try:
        from ...simulation.scenarios import scenario_spread_entries
    except ImportError:  # older engine without the helper
        return
    entries = scenario_spread_entries(comp, currency=cur)
    if not entries:
        return
    section_title("Questions that choose between scenarios", sub="cost spread between scenarios that differ only "
                                                                 "in that respect")
    items = []
    for i, e in enumerate(entries, 1):
        lo, hi = e["low"], e["high"]
        items.append(f'<div class="hbv-iv"><div class="hbv-iv-rank">{i}</div><div>'
                     f'<div class="hbv-iv-act">{esc(e["resolving_action"])}</div>'
                     f'<div class="hbv-small">{esc(e["label"])} · spread of the {esc(e["measure"])} '
                     f'<span class="hbv-mono">{esc(fmt.money(e["spread"], cur))}</span></div>'
                     f'<div class="hbv-range">{esc(lo["scenario_id"])} {esc(fmt.money(lo["cost"], cur))} '
                     f'({esc(lo["alternative"])}) → {esc(hi["scenario_id"])} {esc(fmt.money(hi["cost"], cur))} '
                     f'({esc(hi["alternative"])})</div></div></div>')
    html('<div class="hbv-ivs">' + "".join(items) + "</div>")
    st.caption("A spread between alternatives says which house is being priced; it is not a share of one house's "
               "sampled variance, so it is listed here rather than in the simulation's ranking.")


# =============================================================================
# Repeat build
# =============================================================================
def _cb_add_ps() -> None:
    ws = S.get_workspace()
    ev = S.evaluate(ws)
    if ev is not None:
        source = S.add_example_production_scenarios(ws, ev)
        ws.say("success", "Illustrative (FICTIONAL) production scenarios added: site-built (current house) and "
                          f"off-site panelised (per-house values from {source}).")


def _repeat(ws: S.Workspace, ev: S.Evaluation) -> None:
    p = ws.project
    if not p.production_scenarios:
        html(callout("No production scenario on this project. Add the illustrative site-built vs off-site panelised "
                     "pair (fictional, labelled assumptions) to explore repeat-build economics.",
                     title="Repeat build", tone="neutral"))
        st.button("Add illustrative production scenarios", key="ps_add", on_click=_cb_add_ps)
        return
    ids = [s.scenario_id for s in p.production_scenarios]
    names = {s.scenario_id: s.name for s in p.production_scenarios}
    sid = st.segmented_control("Production scenario", ids, default=ids[0], key="ps_sel",
                               format_func=lambda i: names.get(i, i)) or ids[0]
    ps = next(s for s in p.production_scenarios if s.scenario_id == sid)
    left, right = st.columns([1.15, 2], gap="medium")
    with left:
        _ps_editor(ws, ps)
    res = S.repeat_results(ws, ev, ps)
    cur = res["installed"].currency
    with right:
        fig = repeat_chart(res, height=360)
        _add_underlying(fig, res)
        st.plotly_chart(fig, key="ps_chart", theme=None, config={"displaylogo": False})
        rows = []
        fg = {r.n: r for r in res["factory_gate"].rows}
        ins = {r.n: r for r in res["installed"].rows}
        for n in res["installed"].comparison_ns:
            a, b = fg.get(n), ins.get(n)
            if a is None or b is None:
                continue
            rows.append({"n": n, "FG average": a.average_cost, "FG incremental": a.incremental_cost,
                         "FG underlying": a.underlying_marginal_cost,
                         "installed average": b.average_cost, "installed incremental": b.incremental_cost,
                         "installed underlying": b.underlying_marginal_cost, "installed C(n)": b.total_cost,
                         "factory share": a.total_cost / b.total_cost if b.total_cost else None,
                         "steps between n and n+1": "; ".join(b.step_events) or "-"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={**{c: st.column_config.NumberColumn(c, format="%,.0f")
                                       for c in ("FG average", "FG incremental", "FG underlying", "installed average",
                                                 "installed incremental", "installed underlying", "installed C(n)")},
                                    "n": st.column_config.NumberColumn(format="%d"),
                                    "factory share": st.column_config.NumberColumn(format="percent"),
                                    "steps between n and n+1": st.column_config.TextColumn(width="large")})
        st.caption(f"Amounts in {cur} per house (C(n) in total). FG = factory gate; factory share = factory-gate "
                   "C(n) / installed C(n). Incremental = C(n+1) − C(n) exactly: when house n+1 starts a new site, "
                   "factory line or capacity step, or reaches a procurement tier, it contains that step (listed in the "
                   "last column). Underlying = the cost of house n+1 without capacity steps, pack-rounding steps and "
                   "all-units tier re-pricing (dotted lines in the chart).")
    html(callout(
        "<b>Average cost</b> = C(n) / n spreads one-off and step costs (design, tooling, factory set-up and lines, site "
        "establishment, capacity steps) over n houses. <b>Incremental cost</b> = C(n+1) − C(n) is the cost of one more "
        "house: it only contains a step cost when a threshold is crossed, and all-units procurement tiers can make it "
        "drop sharply. <b>Underlying marginal</b>: "
        f"{esc(res['installed'].assumptions.get('underlying_marginal_definition', ''))}<br>"
        f"<b>Factory gate:</b> {esc(res['factory_gate'].boundary_definition)}<br>"
        f"<b>Installed:</b> {esc(res['installed'].boundary_definition)}", title="Definitions and boundaries",
        tone="info"))
    _reconciliation(res["installed"])
    with st.expander("Model notes and per-house inputs"):
        for n in res["installed"].notes:
            st.markdown(f"- {esc(n)}")
        inputs = res["installed"].assumptions.get("per_house_inputs", {})
        if inputs:
            st.dataframe(pd.DataFrame([{"input": k, "value": v.get("value"), "source": v.get("source")}
                                       for k, v in inputs.items()]), hide_index=True, width="stretch")
        st.caption(esc(ps.notes))
    if len(p.production_scenarios) > 1:
        section_title("Production scenarios side by side", sub="installed boundary, average cost per house")
        crow = []
        for s in p.production_scenarios:
            r = S.repeat_results(ws, ev, s, ("installed",))["installed"]
            by = {x.n: x for x in r.rows}
            crow.append({"scenario": s.name, **{f"n={n}": by[n].average_cost for n in r.comparison_ns if n in by}})
        st.dataframe(pd.DataFrame(crow), hide_index=True, width="stretch",
                     column_config={c: st.column_config.NumberColumn(f"{c} ({cur})", format="%,.0f")
                                    for c in crow[0] if c != "scenario"})


def _add_underlying(fig: go.Figure, res: dict) -> None:
    """Dotted underlying-marginal line per boundary panel of :func:`charts.repeat_chart`."""
    keys = [k for k in ("factory_gate", "installed", "development") if k in res]
    for c, k in enumerate(keys, start=1):
        r = res[k]
        ys = [row.underlying_marginal_cost for row in r.rows]
        if all(y is None or abs(y) < 1e-9 for y in ys):
            continue
        label = "Underlying marginal (no steps / re-pricing)"
        fig.add_trace(go.Scatter(x=[row.n for row in r.rows], y=ys, mode="lines", name=label, legendgroup=label,
                                 showlegend=c == 1, line=dict(color=IVORY_MUTED, width=1.4, dash="dot"),
                                 hovertemplate=f"n=%{{x}}<br>{label}: %{{y:,.0f}} {r.currency}<extra></extra>"),
                      row=1, col=c)


def _reconciliation(res) -> None:
    """Single-house layers 1-5 next to the installed C(1) components."""
    rec = res.assumptions.get("single_house_reconciliation")
    if not rec:
        return
    cur = res.currency
    with st.expander(f"Single house vs installed C(1): {fmt.money(rec['single_house_l1_l5'], cur)} (layers 1-5) → "
                     f"{fmt.money(rec['installed_c1'], cur)}"):
        rows = [{"item": r["item"], "single house": r["single_house"], "installed C(1)": r["installed_c1"],
                 "difference": r["difference"], "note": r["note"]} for r in rec["rows"]]
        rows.append({"item": "Total", "single house": rec["single_house_l1_l5"], "installed C(1)": rec["installed_c1"],
                     "difference": rec["difference"], "note": ""})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={k: st.column_config.NumberColumn(f"{k} ({cur})", format="%,.0f")
                                    for k in ("single house", "installed C(1)", "difference")})
        st.caption(rec["note"] + " The single-house preliminaries become site establishment per started site plus a "
                   "time-related site overhead share per house; compare averages C(n)/n with installed C(1).")


def _ps_editor(ws: S.Workspace, ps: ProductionScenario) -> None:
    with st.form(f"ps_form_{ps.scenario_id}", border=True):
        st.markdown("**Key assumptions** <span class='hbv-small'>(labelled, not calibrated)</span>",
                    unsafe_allow_html=True)
        c = st.columns(3)
        models = ["unit", "cumulative_average"]
        lm = c[0].selectbox("Learning model", models, index=models.index(ps.learning.model),
                            format_func=lambda m: "Unit (Crawford-style)" if m == "unit" else
                            "Cumulative average (Wright)",
                            help="Unit (Crawford-style): each house's hours fall by (1 − rate) per doubling of "
                                 "output. Cumulative average (Wright): the average hours of the first n houses fall by "
                                 "(1 − rate) per doubling - faster learning for the same rate. Use the model your "
                                 "benchmark rate was quoted for.")
        lr = c[1].number_input("Learning rate", value=float(ps.learning.learning_rate), min_value=0.51, max_value=1.0,
                               step=0.01, format="%.2f", help="Hours (unit model) or average hours (Wright) fall by "
                                                              "(1 − rate) per doubling of output.")
        fl = c[2].number_input("Learning floor", value=float(ps.learning.floor_fraction), min_value=0.05,
                               max_value=1.0, step=0.05, format="%.2f",
                               help="A house's hours never fall below floor × h1 (both models).")
        c = st.columns(3)
        hps = c[0].number_input("Houses per site", value=int(ps.houses_per_site), min_value=1, max_value=10000, step=1)
        est = c[1].number_input("Site establishment / site", value=float(ps.site_establishment_per_site), min_value=0.0,
                                step=1000.0)
        ovs = c[2].number_input("Site overhead share", value=float(ps.site_overhead_share), min_value=0.0,
                                max_value=1.0, step=0.05, format="%.2f",
                                disabled=ps.site_overhead_per_house is not None,
                                help="Share of the single-house time-related preliminaries (supervision, welfare "
                                     "hire) each house carries when built concurrently on a shared site (assumed). "
                                     + ("This scenario fixes its site overhead per house, so the share is not used."
                                        if ps.site_overhead_per_house is not None else ""))
        tiers = pd.DataFrame([{"min units": t.min_units, "discount %": 100 * t.discount_fraction}
                              for t in ps.procurement_tiers], columns=["min units", "discount %"])
        st.caption("Procurement discount tiers")
        tiers_ed = st.data_editor(tiers, key=f"ps_tiers_{ps.scenario_id}", num_rows="dynamic", hide_index=True,
                                  width="stretch",
                                  column_config={"min units": st.column_config.NumberColumn(min_value=1, step=1,
                                                                                            format="%d"),
                                                 "discount %": st.column_config.NumberColumn(min_value=0.0,
                                                                                             max_value=99.0,
                                                                                             format="%.1f")})
        steps = pd.DataFrame([{"name": s.name, "every n": s.every_n_units, "cost": s.cost, "after": s.starts_after_units,
                               "boundary": s.boundary} for s in ps.step_costs],
                             columns=["name", "every n", "cost", "after", "boundary"])
        st.caption("Capacity step costs (factory steps count at the factory gate; site steps only when installed)")
        steps_ed = st.data_editor(steps, key=f"ps_steps_{ps.scenario_id}", num_rows="dynamic", hide_index=True,
                                  width="stretch",
                                  column_config={"every n": st.column_config.NumberColumn(min_value=1, step=1,
                                                                                          format="%d"),
                                                 "after": st.column_config.NumberColumn(min_value=0, step=1,
                                                                                        format="%d"),
                                                 "cost": st.column_config.NumberColumn(format="%,.0f"),
                                                 "boundary": st.column_config.SelectboxColumn(
                                                     options=["site", "factory"], required=True)})
        ok = st.form_submit_button("Apply assumptions", type="primary")
    if ok:
        try:
            tiers_l = [DiscountTier(min_units=int(r["min units"]), discount_fraction=float(r["discount %"]) / 100.0)
                       for r in tiers_ed.to_dict(orient="records")
                       if _ok(r.get("min units")) and _ok(r.get("discount %"))]
            steps_l = [StepCost(name=str(r["name"])[:120], every_n_units=int(r["every n"]), cost=float(r["cost"]),
                                starts_after_units=int(r["after"] if _ok(r.get("after")) else 0),
                                boundary="factory" if r.get("boundary") == "factory" else "site",
                                note="edited in the UI (assumption)")
                       for r in steps_ed.to_dict(orient="records")
                       if r.get("name") and _ok(r.get("every n")) and _ok(r.get("cost"))]
            new = ProductionScenario.model_validate({
                **ps.model_dump(), "learning": LearningCurve.model_validate(
                    {**ps.learning.model_dump(), "learning_rate": lr, "floor_fraction": fl, "model": lm}).model_dump(),
                "houses_per_site": int(hps), "site_establishment_per_site": float(est),
                "site_overhead_share": float(ovs),
                "procurement_tiers": [t.model_dump() for t in tiers_l], "step_costs": [s.model_dump() for s in steps_l]})
        except Exception as e:  # noqa: BLE001 - validation message shown to the user
            st.error(f"Assumptions not applied: {e}")
            return
        S.update_production_scenario(ws, new)
        S.get_workspace().say("success", f"{ps.scenario_id}: assumptions applied - curves recalculated.")
        st.rerun()


def _ok(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


# =============================================================================
# Programme, logistics, carbon, heat loss
# =============================================================================
def _programme(ws: S.Workspace, ev: S.Evaluation) -> None:
    prog, logi = ev.programme, ev.logistics
    cards([card("Programme", f"{prog.duration_weeks:.1f} weeks", sub=f"{prog.duration_days:.0f} working days",
                accent=True),
           card("Labour", f"{prog.total_labour_hours:,.0f} h", sub=f"{len(prog.labour_hours_by_trade)} trades"),
           card("Deliveries", f"{logi.total_loads} loads", sub=f"{logi.total_mass_t:,.1f} t"),
           card("Peak storage", f"{logi.peak_storage_area_m2:,.0f} m²", sub="held to end of task (conservative)"),
           card("Waste", f"{logi.skips} skips", sub=f"{logi.waste_volume_m3:,.1f} m³ loose")])
    section_title("Programme", sub=prog.method)
    st.plotly_chart(gantt(prog), key="pg_gantt", theme=None, config={"displaylogo": False})
    crews = prog.assumptions.get("crew_sizes", {})
    st.caption(" · ".join(prog.caveats) + (" Crew sizes (assumed): " + ", ".join(f"{k} {v:g}" for k, v in crews.items())
                                          if crews else ""))
    section_title("Deliveries", sub="indicative batches per task and delivery category")
    rows = [{"batch": b.batch_id, "task": b.task_id, "category": b.delivery_category, "loads": b.loads,
             "mass (t)": b.mass_kg / 1000, "volume (m³)": b.volume_m3, "order by (day)": b.order_by_day,
             "deliver (day)": b.delivery_day, "needed by (day)": b.required_by_day,
             "storage (m²)": b.storage_area_m2, "lead time (d)": b.lead_time_days,
             "ready-mix": b.ready_mix, "description": b.description} for b in logi.batches]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=min(420, 38 + 35 * len(rows)),
                 column_config={k: st.column_config.NumberColumn(format="%.1f")
                                for k in ("mass (t)", "volume (m³)", "order by (day)", "deliver (day)",
                                          "needed by (day)", "storage (m²)", "lead time (d)")})
    st.caption(" ".join(logi.caveats) + " Negative order-by days mean ordering before site start.")


def _carbon_heat(ws: S.Workspace, ev: S.Evaluation) -> None:
    carbon, heat = ev.carbon, ev.heat_loss
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        section_title("Embodied carbon by element", sub="illustrative factors")
        cards([card("A1-A3 + A5 waste", f"{carbon.total_kgco2e / 1000:,.1f} tCO₂e",
                    sub=f"{carbon.per_m2_gia_kgco2e:,.0f} kgCO₂e / m² GIA", accent=True)])
        st.plotly_chart(carbon_chart(carbon), key="cb_chart", theme=None, config={"displaylogo": False})
        st.caption(f"Boundary: {carbon.boundary} {carbon.factor_source}")
        with st.expander(f"Caveats and unmatched items ({len(carbon.unmatched)})"):
            for c in carbon.caveats + carbon.unmatched:
                st.markdown(f"- {esc(c)}")
    with c2:
        section_title("Heat-loss breakdown", sub="simplified steady state")
        cards([card("Heat-loss coefficient", f"{heat.heat_loss_coefficient_w_k:,.0f} W/K",
                    sub=f"HLP {heat.hlp_w_m2k:.2f} W/m²K", accent=True),
               card("Peak load", f"{heat.peak_heat_load_kw:,.1f} kW", sub=f"ΔT {heat.design_delta_t_k:.0f} K"),
               card("Space heat (indicative)", f"{heat.annual_space_heat_kwh:,.0f} kWh/yr", sub="degree-day, no gains")])
        st.plotly_chart(heat_loss_chart(heat), key="hl_chart", theme=None, config={"displaylogo": False})
        a = heat.assumptions
        st.caption(f"{heat.method} Assumed: thermal bridging y = {a.get('thermal_bridging_y_w_m2k')} W/m²K, "
                   f"{a.get('air_change_rate_ach')} ach, design {a.get('internal_design_temp_c')} / "
                   f"{a.get('external_design_temp_c')} °C. Construction build-ups are assumptions.")
        with st.expander("Caveats"):
            for c in heat.caveats + heat.warnings:
                st.markdown(f"- {esc(c)}")


__all__ = ["render"]
