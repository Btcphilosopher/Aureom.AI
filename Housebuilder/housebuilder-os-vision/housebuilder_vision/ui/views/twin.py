"""Twin view: 3D massing (visual finish / evidence basis), parameter editors with provenance, edit log.

Every edit goes through ``twin.builder.apply_twin_edit`` (validated, new version, value becomes
USER_CONFIRMED and is logged) or ``apply_construction_assemblies`` (assembly choices; appearance
never sets them) and the page re-runs: quantities and costs are recalculated immediately through
the evaluation cache keyed by ``twin_hash`` + rate book + parameters.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import pandas as pd
import streamlit as st

from ...core.models import ElementType, OpeningKind, RoofForm, Side, TwinEdit
from ...core.provenance import Basis
from .. import fmt
from .. import state as S
from ..charts import twin_figure
from ..components import guard, html, tv_number
from ..theme import badge, basis_legend_html, callout, esc, tag

REASON = "edited in the Twin view"
ASSEMBLY_ELEMENTS: tuple[tuple[str, str], ...] = (
    ("external_wall", "External walls"), ("separating_wall", "Walls between blocks"),
    ("internal_partition", "Internal partitions"), ("ground_floor", "Ground floor"),
    ("intermediate_floor", "Upper floors"), ("pitched_roof", "Pitched roofs"), ("flat_roof", "Flat roofs"),
    ("window", "Windows"), ("external_door", "External doors"), ("garage_door", "Garage doors"))


@st.cache_data(max_entries=24, show_spinner=False)
def twin_meshes(key: str, _twin) -> list[dict[str, Any]]:
    from ...twin.mesh import build_mesh, scene_to_plotly_meshes

    return scene_to_plotly_meshes(build_mesh(_twin))


def _edit(target_type: str, target_id: Optional[str], field: str) -> Callable[[Any], Optional[str]]:
    def apply(v: Any) -> Optional[str]:
        return S.edit_twin(S.get_workspace(), TwinEdit(target_type=target_type, target_id=target_id, field=field,
                                                       value=v, reason=REASON))
    return apply


def _cb_select(key: str, apply: Callable[[Any], Optional[str]]) -> None:
    ws = S.get_workspace()
    err = apply(st.session_state.get(key))
    if err:
        ws.say("error", err)


def _cb_assembly(element: str, key: str) -> None:
    ws = S.get_workspace()
    err = S.set_assembly(ws, element, st.session_state.get(key))
    if err:
        ws.say("error", err)


def _cb_rebuild() -> None:
    ws = S.get_workspace()
    try:
        S.build_twin(ws, ws.project.selected_hypothesis_id)
    except Exception as e:  # noqa: BLE001
        ws.say("error", f"Twin not rebuilt: {e}")


# =============================================================================
# View
# =============================================================================
def render(ws: S.Workspace, ev: Optional[S.Evaluation]) -> None:
    p = ws.project
    if p is None or p.twin is None:
        html(callout("No twin yet. Load the demo, or analyse an image and build a twin from a hypothesis in the "
                     "Images view.", title="Twin", tone="neutral"))
        return
    twin = p.twin
    html(callout(f"{esc(twin.information_level)} Scale: <b>{esc(twin.calibration_method.replace('_', ' '))}</b> · "
                 f"source hypothesis <b>{esc(twin.source_hypothesis_id or '-')}</b> · version {twin.version} · "
                 f"hash <span class='hbv-mono'>{esc(S.fp(twin)[:12])}</span>", title="Information level", tone="info"))
    if S.twin_status(ws) == "stale":
        html(callout("The evidence or the calibration changed after this twin was built. Results below describe this "
                     "twin; rebuild it to follow the current hypothesis.", title="Twin based on earlier evidence",
                     tone="danger"))
        st.button(f"Rebuild twin from {p.selected_hypothesis_id}", key="tw_rebuild", on_click=_cb_rebuild)
    left, right = st.columns([1.65, 1], gap="medium")
    with left:
        with guard("3D preview"):
            _viewer(ws, ev)
    with right:
        with guard("Twin summary"):
            _summary(ws, ev)
    tabs = st.tabs(["Blocks", "Roofs", "Openings", "Hidden sides", "Construction"])
    sections = [_blocks, _roofs, _openings, _hidden, _construction]
    names = ["Block editor", "Roof editor", "Openings editor", "Hidden-side assumptions", "Construction assemblies"]
    for tab, fn, name in zip(tabs, sections, names, strict=True):
        with tab:
            with guard(name):
                fn(ws, ev)
    with st.expander(f"Edit log ({len(twin.edit_log)} edit(s))"):
        with guard("Edit log"):
            _edit_log(ws, ev)


def _viewer(ws: S.Workspace, ev: Optional[S.Evaluation]) -> None:
    twin = ws.project.twin
    mode = st.segmented_control("Colour", ["Visual finish", "Evidence basis"], default="Visual finish",
                                key="tw_colour", label_visibility="collapsed") or "Visual finish"
    meshes = twin_meshes(S.fp(twin), twin)
    fig = twin_figure(meshes, twin, mode="basis" if mode == "Evidence basis" else "finish",
                      metrics=ev.boq.geometry if ev else None, height=500)
    st.plotly_chart(fig, key="tw_3d", theme=None, config={"displaylogo": False})
    if mode == "Evidence basis":
        html(basis_legend_html())
        st.caption("Walls take the basis of the block width, roofs the basis of the pitch, openings the basis of "
                   "their width. Derived quantities carry the weakest basis of all their inputs.")
    else:
        st.caption("Colours show visual appearance only (from the images) - they do not identify structure or "
                   "build-up. Semi-transparent blocks / openings are hidden from every view (assumed or rule-filled).")


def _summary(ws: S.Workspace, ev: Optional[S.Evaluation]) -> None:
    p = ws.project
    twin = p.twin
    system = p.settings.unit_system
    if ev is not None:
        g = ev.boq.geometry

        def a(v: float) -> str:
            return fmt.qty(v, "m2", system, 1)
        items = [("GEA", a(g.gea_m2)), ("GIA", a(g.gia_m2)), ("Footprint", a(g.footprint_area_m2)),
                 ("External wall (net)", a(g.external_wall_net_m2)), ("Roof surface", a(g.roof_surface_area_m2)),
                 ("Glazed openings", a(g.window_area_m2))]
        html('<div class="hbv-cards" style="grid-template-columns:repeat(3,1fr)">' + "".join(
            f'<div class="hbv-card"><div class="hbv-card-k">{esc(k)}</div><div class="hbv-card-v" '
            f'style="font-size:.98rem">{esc(v)}</div></div>' for k, v in items) + "</div>")
        st.caption(f"Wall thickness for GIA: external {g.external_wall_thickness_m * 1000:.0f} mm, between blocks "
                   f"{g.separating_wall_thickness_m * 1000:.0f} mm (from the selected assemblies).")
    rows = []
    for b in twin.blocks:
        rows.append({"block": b.block_id, "role": b.role.value, "width": fmt.tv_value(b.width, system),
                     "depth": fmt.tv_value(b.depth, system), "storeys": int(b.storeys.value or 0),
                     "roof": f"{b.roof.form.value} {fmt.tv_value(b.roof.pitch_deg, system, 1)}"
                     if b.roof.form != RoofForm.FLAT else "flat",
                     "seen": ", ".join(s.value for s in b.visible_sides) or "hidden", "heated": b.heated})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    vf = twin.visual_finishes
    if vf:
        html('<div class="hbv-small" style="margin-top:.2rem">Visual finishes (appearance only): '
             + " · ".join(f'<span style="display:inline-block;width:.7em;height:.7em;background:{esc(f.colour_hex)};'
                          f'border:1px solid #555;margin-right:.25em"></span>{esc(f.element)}: {esc(f.appearance)} '
                          f'{badge(f.basis)}' for f in vf) + "</div>")
    if twin.edit_log:
        last = twin.edit_log[-3:][::-1]
        html('<div class="hbv-small" style="margin-top:.45rem">Latest edits: ' + "; ".join(
            f'{esc(r.target)}.{esc(r.field)} {esc(_short(r.old_value))} → {esc(_short(r.new_value))}' for r in last)
             + "</div>")


def _short(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.3g}"
    s = str(v)
    return s if len(s) <= 24 else s[:22] + "…"


# =============================================================================
# Editors
# =============================================================================
def _blocks(ws: S.Workspace, ev) -> None:
    twin = ws.project.twin
    system = ws.project.settings.unit_system
    v = twin.version
    for b in twin.blocks:
        with st.container(border=True):
            html(f'<div style="display:flex;gap:.5rem;align-items:center;margin-bottom:.3rem">'
                 f'<span style="font-weight:600">{esc(b.name or b.block_id)}</span>{tag(b.role.value, tone="gold")}'
                 f'<span class="hbv-small">visible sides: {esc(", ".join(s.value for s in b.visible_sides) or "none")}'
                 f' · origin ({fmt.num(b.origin_x.value)}, {fmt.num(b.origin_y.value)}) m</span></div>')
            c = st.columns(5)
            with c[0]:
                tv_number("Width", b.width, key=f"b_{v}_{b.block_id}_w", apply=_edit("block", b.block_id, "width"),
                          system=system, min_si=0.5, max_si=200.0)
            with c[1]:
                tv_number("Depth", b.depth, key=f"b_{v}_{b.block_id}_d", apply=_edit("block", b.block_id, "depth"),
                          system=system, min_si=0.5, max_si=200.0)
            with c[2]:
                tv_number("Storeys", b.storeys, key=f"b_{v}_{b.block_id}_n", apply=_edit("block", b.block_id, "storeys"),
                          si_unit="", integer=True, min_si=1, max_si=6, nd=0)
            with c[3]:
                tv_number("Floor-to-floor", b.floor_to_floor, key=f"b_{v}_{b.block_id}_f",
                          apply=_edit("block", b.block_id, "floor_to_floor"), system=system, min_si=2.0, max_si=6.0)
            with c[4]:
                tv_number("FFL above ground", b.ground_floor_level, key=f"b_{v}_{b.block_id}_ffl",
                          apply=_edit("block", b.block_id, "ground_floor_level"), system=system, min_si=0.0,
                          max_si=3.0, step=0.01)
            k = f"b_{v}_{b.block_id}_heated"
            st.toggle("Heated (inside the thermal envelope)", value=b.heated, key=k,
                      on_change=_cb_select, args=(k, _edit("block", b.block_id, "heated")))
    st.caption("Width / depth are external dimensions. Blocks attached at the right or rear move with an edited "
               "edge so the footprint stays valid. Every edit is recorded and marks the value user-confirmed.")


def _roofs(ws: S.Workspace, ev) -> None:
    twin = ws.project.twin
    system = ws.project.settings.unit_system
    v = twin.version
    forms = [f.value for f in RoofForm]
    for b in twin.blocks:
        r = b.roof
        with st.container(border=True):
            html(f'<div style="font-weight:600;margin-bottom:.3rem">{esc(b.block_id)} roof</div>')
            c = st.columns(5)
            k = f"r_{v}_{b.block_id}_form"
            c[0].selectbox("Form", forms, index=forms.index(r.form.value), key=k, on_change=_cb_select,
                           args=(k, _edit("roof", b.block_id, "form")))
            with c[1]:
                tv_number("Pitch", r.pitch_deg, key=f"r_{v}_{b.block_id}_p", apply=_edit("roof", b.block_id, "pitch_deg"),
                          si_unit="deg", nd=1, min_si=0.0, max_si=74.9, step=0.5, disabled=r.form == RoofForm.FLAT)
            k2 = f"r_{v}_{b.block_id}_axis"
            c[2].selectbox("Ridge axis", ["x", "y"], index=0 if r.ridge_axis == "x" else 1, key=k2, on_change=_cb_select,
                           args=(k2, _edit("roof", b.block_id, "ridge_axis")),
                           format_func=lambda a: "x · parallel to frontage" if a == "x" else "y · front-to-rear",
                           disabled=r.form == RoofForm.FLAT)
            with c[3]:
                tv_number("Eaves overhang", r.eaves_overhang_m, key=f"r_{v}_{b.block_id}_eo",
                          apply=_edit("roof", b.block_id, "eaves_overhang_m"), system=system, min_si=0.0, max_si=2.0,
                          step=0.05)
            with c[4]:
                tv_number("Verge overhang", r.verge_overhang_m, key=f"r_{v}_{b.block_id}_vo",
                          apply=_edit("roof", b.block_id, "verge_overhang_m"), system=system, min_si=0.0, max_si=2.0,
                          step=0.05)
            if r.form == RoofForm.MONOPITCH:
                k3 = f"r_{v}_{b.block_id}_high"
                sides = [s.value for s in Side]
                st.selectbox("High side", sides, index=sides.index((r.high_side or Side.FRONT).value), key=k3,
                             on_change=_cb_select, args=(k3, _edit("roof", b.block_id, "high_side")))
            if r.form == RoofForm.FLAT:
                tv_number("Parapet height", r.parapet_height_m, key=f"r_{v}_{b.block_id}_par",
                          apply=_edit("roof", b.block_id, "parapet_height_m"), system=system, min_si=0.0, max_si=3.0)
    st.caption("Pitch is observed only where a gable / verge is seen in elevation; otherwise it is a prior. With an "
               "observed ridge rise, depth and pitch are coupled - confirm either one.")


_OPEN_COLS = ["opening_id", "block", "side", "kind", "storey", "offset", "width", "height", "sill", "basis", "rule"]


def _openings(ws: S.Workspace, ev) -> None:
    twin = ws.project.twin
    system = ws.project.settings.unit_system
    du = fmt.disp_unit("m", system)
    rows = []
    for o in twin.openings:
        rows.append({"opening_id": o.opening_id, "block": o.block_id, "side": o.side.value, "kind": o.kind.value,
                     "storey": o.storey, "offset": fmt.disp(o.offset_m.value, "m", system)[0],
                     "width": fmt.disp(o.width_m.value, "m", system)[0],
                     "height": fmt.disp(o.height_m.value, "m", system)[0],
                     "sill": fmt.disp(o.sill_m.value, "m", system)[0], "basis": o.width_m.basis.value,
                     "rule": o.hidden_side_rule or ""})
    df = pd.DataFrame(rows, columns=_OPEN_COLS)
    key = f"op_{twin.version}"
    ids = [r["opening_id"] for r in rows]
    blocks = [b.block_id for b in twin.blocks]
    num = lambda lab: st.column_config.NumberColumn(f"{lab} ({du})", format="%.2f", min_value=0.0)  # noqa: E731
    st.data_editor(df, key=key, num_rows="dynamic", hide_index=True, width="stretch",
                   height=min(460, 38 + 35 * (len(df) + 1)),
                   disabled=["opening_id", "basis", "rule"],
                   column_config={
                       "opening_id": st.column_config.TextColumn("id"),
                       "block": st.column_config.SelectboxColumn("block", options=blocks, required=True),
                       "side": st.column_config.SelectboxColumn("side", options=[s.value for s in Side], required=True),
                       "kind": st.column_config.SelectboxColumn("kind", options=[k.value for k in OpeningKind],
                                                                required=True),
                       "storey": st.column_config.NumberColumn("storey", min_value=0, max_value=5, step=1, format="%d"),
                       "offset": num("offset"), "width": num("width"), "height": num("height"), "sill": num("sill"),
                       "basis": st.column_config.TextColumn("basis (width)"),
                       "rule": st.column_config.TextColumn("hidden-side rule"),
                   },
                   on_change=_cb_openings, args=(key, ids, du))
    st.caption("Offset is measured along the wall from its left end as seen from outside. Rule-filled openings on "
               "hidden sides (assumed) are regenerated when geometry changes; editing, adding or deleting an opening "
               "on a hidden side fixes that side to your specification.")


def _cb_openings(key: str, ids: list[str], du: str) -> None:
    ws = S.get_workspace()
    state = st.session_state.get(key) or {}
    errs: list[str] = []
    conv = {"offset": "offset_m", "width": "width_m", "height": "height_m", "sill": "sill_m"}

    def si(v: Any) -> float:
        return fmt.to_si(float(v), du, "m")

    for idx in sorted(state.get("deleted_rows", []), reverse=True):
        oid = ids[int(idx)]
        e = S.edit_twin(ws, TwinEdit(target_type="opening", target_id=oid, field="delete", value=None, reason=REASON))
        if e:
            errs.append(e)
    deleted = {ids[int(i)] for i in state.get("deleted_rows", [])}
    for idx, change in (state.get("edited_rows") or {}).items():
        oid = ids[int(idx)]
        if oid in deleted:
            continue
        for col, val in change.items():
            if col == "block":
                errs.append(f"{oid}: to move an opening to another block, delete it and add a new row.")
                continue
            if val is None:
                continue
            field = conv.get(col, col)
            value: Any = si(val) if col in conv else (int(val) if col == "storey" else val)
            e = S.edit_twin(ws, TwinEdit(target_type="opening", target_id=oid, field=field, value=value, reason=REASON))
            if e:
                errs.append(e)
    for row in state.get("added_rows", []) or []:
        if not row.get("block") or not row.get("side") or not row.get("kind") or row.get("width") is None \
                or row.get("height") is None:
            errs.append("New opening needs block, side, kind, width and height.")
            continue
        spec = {"block_id": row["block"], "side": row["side"], "kind": row["kind"],
                "width_m": si(row["width"]), "height_m": si(row["height"]), "storey": int(row.get("storey") or 0)}
        for col in ("offset", "sill"):
            if row.get(col) is not None:
                spec[conv[col]] = si(row[col])
        e = S.edit_twin(ws, TwinEdit(target_type="opening", target_id=None, field="add", value=spec, reason=REASON))
        if e:
            errs.append(e)
    for e in errs:
        ws.say("error", e)


def _hidden(ws: S.Workspace, ev) -> None:
    twin = ws.project.twin
    h = twin.hidden
    v = twin.version
    system = ws.project.settings.unit_system
    html(callout(esc(h.notes), title="Hidden facades", tone="neutral"))
    c1, c2 = st.columns(2)
    for col, field, label, tv in ((c1, "rear_glazing_ratio", "Rear glazing ratio", h.rear_glazing_ratio),
                                  (c2, "side_glazing_ratio", "Side glazing ratio", h.side_glazing_ratio)):
        with col:
            k = f"h_{v}_{field}"
            st.slider(f"{label} (glazed fraction of hidden wall)", 0.0, 0.9, value=float(tv.value or 0.0), step=0.01,
                      key=k, on_change=_cb_select, args=(k, _edit("hidden", None, field)), format="%.2f")
            html(f'<div class="hbv-val">{badge(tv.basis)}<span class="hbv-range">{esc(fmt.tv_range(tv, system))}'
                 f'</span><span class="hbv-small">{esc(tv.note or tv.source)[:120]}</span></div>')
    c = st.columns(4)
    k = f"h_{v}_doors"
    c[0].number_input("Rear doors (patio)", value=int(h.rear_door_count), min_value=0, max_value=10, step=1, key=k,
                      on_change=_cb_select, args=(k, _edit("hidden", None, "rear_door_count")))
    du = fmt.disp_unit("m", system)
    for col, field, label in ((c[1], "typical_window_width_m", "Typical window width"),
                              (c[2], "typical_window_height_m", "Typical window height"),
                              (c[3], "typical_window_sill_m", "Typical sill height")):
        k = f"h_{v}_{field}"
        col.number_input(f"{label} ({du})", value=round(float(fmt.disp(getattr(h, field), 'm', system)[0]), 3),
                         min_value=0.0, step=0.05, format="%.2f", key=k, on_change=_cb_conv,
                         args=(k, _edit("hidden", None, field), du))
    html(f'<div class="hbv-val">{badge(Basis.ASSUMED)}<span class="hbv-range">rule parameters (assumed until '
         f'confirmed)</span></div>')
    if h.specified_sides:
        st.caption("Sides specified by a person (no longer rule-filled): " + ", ".join(h.specified_sides))
    n_rule = sum(1 for o in twin.openings if o.hidden_side_rule)
    st.caption(f"{n_rule} opening(s) currently generated by hidden-side rules. Upload a rear / side elevation to "
               "replace rules with observations.")


def _cb_conv(key: str, apply: Callable[[Any], Optional[str]], du: str) -> None:
    ws = S.get_workspace()
    v = st.session_state.get(key)
    if v is None:
        return
    err = apply(fmt.to_si(float(v), du, "m"))
    if err:
        ws.say("error", err)


def _construction(ws: S.Workspace, ev) -> None:
    p = ws.project
    twin, lib = p.twin, p.library
    sel = twin.assemblies
    html(callout("Construction assemblies are <b>hypotheses</b>: appearance does not establish structure. A brick-like "
                 "facade can be a masonry cavity wall or a timber frame with a brick outer leaf. Choices stay "
                 "<i>assumed</i> until you confirm them here; visual finishes never set them.",
                 title="Appearance does not establish structure", tone="warn"))
    try:
        from ...simulation.thermal import u_value
    except Exception:  # noqa: BLE001
        u_value = None  # type: ignore[assignment]
    cols = st.columns(2, gap="medium")
    names = {a.assembly_id: a.name for a in lib.assemblies}
    for i, (el, label) in enumerate(ASSEMBLY_ELEMENTS):
        options = [a.assembly_id for a in lib.by_element(ElementType(el))]
        cur = getattr(sel, el)
        if cur not in options:
            options = [cur, *options]
        k = f"asm_{twin.version}_{el}"
        with cols[i % 2]:
            st.selectbox(label, options, index=options.index(cur), key=k, format_func=lambda a: names.get(a, a),
                         on_change=_cb_assembly, args=(el, k), help="Appearance does not establish structure.")
            extra = ""
            try:
                asm = lib.assembly(cur)
                t_mm = asm.total_thickness_m * 1000
                parts = [f"{esc(asm.structural_system)}"]
                if t_mm > 0 and el not in ("window", "external_door", "garage_door"):
                    parts.append(f"{t_mm:.0f} mm")
                if u_value is not None:
                    try:
                        parts.append(f"U ≈ {u_value(asm, lib):.2f} W/m²K (indicative)")
                    except Exception:  # noqa: BLE001
                        pass
                extra = f'<span class="hbv-range">{" · ".join(parts)}</span>'
            except KeyError:
                extra = '<span class="hbv-range">not in library</span>'
            html(f'<div class="hbv-val">{badge(sel.basis.get(el, Basis.ASSUMED))}{extra}</div>')
    fopts = [f.option_id for f in lib.foundations]
    fnames = {f.option_id: f.name for f in lib.foundations}
    k = f"asm_{twin.version}_foundation"
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.selectbox("Foundation option", fopts, index=fopts.index(sel.foundation) if sel.foundation in fopts else 0,
                     key=k, format_func=lambda f: fnames.get(f, f), on_change=_cb_assembly, args=("foundation", k),
                     help="Indicative option for costing only - requires a site investigation and an engineer's design.")
        html(f'<div class="hbv-val">{badge(sel.basis.get("foundation", Basis.ASSUMED))}<span class="hbv-range">'
             f'indicative, for costing only; needs site investigation and engineer\'s design</span></div>')
    with c2:
        tv_number("Bathrooms (allowance driver)", twin.bathrooms, key=f"tw_{twin.version}_bath",
                  apply=_edit("twin", None, "bathrooms"), si_unit="", integer=True, min_si=0, max_si=20, nd=0)
    if sel.block_overrides:
        st.caption("Per-block overrides: " + "; ".join(f"{b}: {', '.join(f'{k}={v}' for k, v in ov.items())}"
                                                      for b, ov in sel.block_overrides.items()))


def _edit_log(ws: S.Workspace, ev) -> None:
    twin = ws.project.twin
    if not twin.edit_log:
        st.info("No edits yet - every change you make is listed here with old and new values and bases.")
        return
    rows = [{"time (UTC)": r.timestamp.strftime("%H:%M:%S"), "actor": r.actor, "target": r.target, "field": r.field,
             "old": _short(r.old_value), "new": _short(r.new_value),
             "basis": f"{r.old_basis.value if r.old_basis else '-'} → {r.new_basis.value if r.new_basis else '-'}",
             "reason": r.reason} for r in twin.edit_log[::-1]]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=min(520, 38 + 35 * len(rows)))
    st.caption(f"{len(twin.edit_log)} edit(s) on twin {twin.twin_id}; engine run records: {len(ws.project.run_log)}.")


__all__ = ["render", "twin_meshes"]
