"""Images view: upload, evidence overlay, feature review, manual annotation, calibration, unknowns, hypotheses.

Everything shown here is pixel-space evidence or a labelled assumption: detections are OBSERVED
(capped at INFERRED for concept references), annotations are USER_CONFIRMED, scale from prior
cues is ASSUMED until a reference measurement is confirmed.  Rejecting a feature or applying
annotations re-runs the analysis; hypotheses and the twin follow (a twin with geometry edits is
not silently replaced - it is flagged as based on earlier evidence).
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from ...core.models import CONCEPT_KINDS, ImageKind, ReferenceMeasurement, ViewDirection
from ...pipeline import is_user_rejection
from .. import fmt
from .. import state as S
from ..charts import overlay_figure
from ..components import guard, html, section_title
from ..theme import BASIS_ORDER, badge, basis_legend_html, callout, esc, md_escape, tag

UPLOAD_TYPES = ["png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp"]
REF_UNITS = ("m", "mm", "cm", "ft", "in")


# =============================================================================
# Callbacks
# =============================================================================
def _cb_ingest(files: list[tuple[str, bytes, str]]) -> None:
    ws = S.get_workspace()
    uploads = []
    for name, data, fid in files:
        kind = S.KIND_LABELS.get(st.session_state.get(f"up_kind_{fid}", "Photo"), ImageKind.UNKNOWN)
        view = S.VIEW_LABELS.get(st.session_state.get(f"up_view_{fid}", "Front"), ViewDirection.UNKNOWN)
        uploads.append((name, data, kind, view))
    try:
        added, rejected = S.ingest_uploads(ws, uploads)
    except Exception as e:  # noqa: BLE001
        ws.say("error", f"Upload failed: {type(e).__name__}: {e}")
        return
    for name, why in rejected:
        ws.say("error", f"Rejected '{name}': {why}")
    if added:
        ws.say("success", f"Added {len(added)} image(s): {', '.join(added)}")
    # every attempt clears the uploader: a rejected file is reported once, not re-submitted with later uploads
    st.session_state["uploader_gen"] = st.session_state.get("uploader_gen", 0) + 1


def _cb_image_meta(image_id: str, kkey: str, vkey: str) -> None:
    ws = S.get_workspace()
    try:
        S.update_image(ws, image_id, kind=S.KIND_LABELS.get(st.session_state.get(kkey)),
                       view=S.VIEW_LABELS.get(st.session_state.get(vkey)))
    except Exception as e:  # noqa: BLE001
        ws.say("error", f"Image settings not applied: {e}")


def _cb_remove_image(image_id: str) -> None:
    ws = S.get_workspace()
    try:
        S.remove_image(ws, image_id)
    except Exception as e:  # noqa: BLE001
        ws.say("error", f"Image not removed: {e}")


def _cb_features(image_id: str, key: str, ids: list[str]) -> None:
    ws = S.get_workspace()
    edits = (st.session_state.get(key) or {}).get("edited_rows", {})
    feats = {f.feature_id: f for a in ws.project.analysis.analyses if a.image_id == image_id for f in a.features}
    for row, change in edits.items():
        if "active" not in change:
            continue
        try:
            fid = ids[int(row)]
            msg = S.set_feature_active(ws, image_id, feats[fid], bool(change["active"]))
            if msg:
                ws.say("warning", msg)
        except Exception as e:  # noqa: BLE001
            ws.say("error", f"Feature change not applied: {type(e).__name__}: {e}")


def _cb_build(hid: str) -> None:
    ws = S.get_workspace()
    try:
        S.build_twin(ws, hid)
    except Exception as e:  # noqa: BLE001
        ws.say("error", f"Twin not built from {hid}: {type(e).__name__}: {e}")


def _cb_select_hyp(hid: str) -> None:
    ws = S.get_workspace()
    ws.project.selected_hypothesis_id = hid


def _cb_proceed() -> None:
    S.get_workspace().proceed_with_assumptions = True


def _cb_clear_ref() -> None:
    ws = S.get_workspace()
    S.clear_reference(ws)
    ws.say("success", "Reference removed - scale now comes from labelled prior cues.")


def _cb_vlm(key: str) -> None:
    ws = S.get_workspace()
    S.set_vlm(ws, bool(st.session_state.get(key)))


def _cb_optional(key: str) -> None:
    ws = S.get_workspace()
    S.set_optional_adapters(ws, bool(st.session_state.get(key)))


# =============================================================================
# View
# =============================================================================
def render(ws: S.Workspace, ev: Optional[S.Evaluation]) -> None:
    p = ws.project
    if p is None:
        html(callout("Load the fictional demo (sidebar) or create a new project, then drop photos, renderings, "
                     "sketches, plans or elevation drawings here. Each image is validated, content-addressed and "
                     "kept unchanged.", title="Start", tone="info"))
        st.button("Load fictional demo", key="load_demo_empty", type="primary", on_click=_load_demo_from_view)
        return
    with guard("Concept-reference caveat"):
        _concept_banner(ws)
    with guard("Upload"):
        _upload_panel(ws)
    if not p.images:
        return
    ids = [a.image_id for a in p.images]
    labels = {a.image_id: f"{a.original_filename} · {S.kind_label(a.kind)} · {S.view_label(a.view)}" for a in p.images}
    sel_key = "img_sel"
    if st.session_state.get(sel_key) not in ids:
        st.session_state[sel_key] = p.analysis.primary_image_id if p.analysis and p.analysis.primary_image_id in ids \
            else ids[0]
    st.radio("Image", ids, key=sel_key, format_func=lambda i: labels[i], horizontal=True, label_visibility="collapsed")
    image_id = st.session_state[sel_key]
    asset = ws.image(image_id)
    analysis = p.analysis
    ia = next((a for a in analysis.analyses if a.image_id == image_id), None) if analysis else None

    left, right = st.columns([1.7, 1], gap="medium")
    with left:
        with guard("Evidence overlay"):
            _overlay(ws, asset, ia)
    with right:
        with guard("Image details"):
            _image_details(ws, asset, ia)
    # stateful (keyed) sub-tabs: e.g. the Calibration tab stays open after a reference is applied (the rerun
    # and its flash message would otherwise reset an unkeyed tab bar to the first tab)
    t1, t2, t3, t4 = st.tabs(["Evidence", "Annotate", "Calibration", "Unknowns & warnings"], key="images_subtab",
                             on_change="rerun")
    with t1:
        with guard("Evidence table"):
            _feature_table(ws, image_id, ia)
    with t2:
        with guard("Annotation editor"):
            _annotation_editor(ws, asset)
    with t3:
        with guard("Calibration"):
            _calibration_panel(ws)
    with t4:
        with guard("Unknowns and warnings"):
            _unknowns(ws)
    with guard("Hypotheses"):
        _hypotheses(ws)


def _load_demo_from_view() -> None:
    ws = S.get_workspace()
    try:
        S.load_demo(ws)
    except Exception as e:  # noqa: BLE001
        ws.say("error", f"The demo could not be loaded: {type(e).__name__}: {e}")


def _concept_banner(ws: S.Workspace) -> None:
    p = ws.project
    concept = [a for a in p.images if a.kind in CONCEPT_KINDS]
    flagged = [w for w in (p.analysis.warnings if p.analysis else []) if "Concept reference" in w
               or "concept reference" in w]
    if not concept and not flagged:
        return
    names = ", ".join(esc(a.original_filename) for a in concept) or "an uploaded image"
    html(callout(
        f"{names} {'is' if len(concept) <= 1 else 'are'} a <b>concept reference</b> (AI concept / rendering / sketch). "
        "Its geometry may be internally inconsistent: measurements from it are capped at <i>inferred</i>, never "
        "observed, and dimensions are indicative only. It does not show an existing or measured building.",
        title="AI concept / rendering caveat", tone="danger"))


def _upload_panel(ws: S.Workspace) -> None:
    p = ws.project
    with st.expander("Add images", expanded=not p.images):
        gen = st.session_state.get("uploader_gen", 0)
        files = st.file_uploader("Drag and drop photos, renderings, AI concepts, sketches, floor plans or elevations",
                                 type=UPLOAD_TYPES, accept_multiple_files=True, key=f"uploader_{gen}",
                                 help="PNG / JPEG / WebP / TIFF / BMP, at most 25 MB and 50 megapixels each. Files are "
                                      "validated and decoded safely; originals are preserved unchanged.")
        if not files:
            st.caption("Nothing is fabricated from an image: without a matching detection fixture, detector or your "
                       "annotations an upload produces warnings, not geometry.")
            return
        pending = []
        for f in files:
            fid = f"{gen}_{f.file_id}" if hasattr(f, "file_id") else f"{gen}_{f.name}_{f.size}"
            c1, c2, c3 = st.columns([2.2, 1.2, 1.2])
            c1.markdown(f"<span class='hbv-mono'>{esc(f.name)}</span> <span class='hbv-small'>· "
                        f"{f.size / 1024:,.0f} kB</span>", unsafe_allow_html=True)
            c2.selectbox("Kind", list(S.KIND_LABELS), key=f"up_kind_{fid}", label_visibility="collapsed")
            c3.selectbox("View", list(S.VIEW_LABELS), key=f"up_view_{fid}", label_visibility="collapsed")
            pending.append((f.name, f.getvalue(), fid))
        st.button(f"Validate and add {len(pending)} image(s)", key="ingest_btn", type="primary", on_click=_cb_ingest,
                  args=(pending,))


def _overlay(ws: S.Workspace, asset, ia) -> None:
    feats = list(ia.features) if ia is not None else []
    c1, c2, _ = st.columns([1.2, 1.2, 2.4])
    show_inactive = c1.toggle("Show rejected", value=False, key="ov_inactive")
    draw = c2.toggle("Draw boxes", value=False, key="ov_draw",
                     help="Box-select on the image to pre-fill an annotation row (Annotate tab).")
    try:
        uri, scale = S.image_preview(asset.sha256, asset, ws.store_dir)
    except Exception as e:  # noqa: BLE001 - show the evidence even when pixels are unavailable
        uri, scale = None, 1.0
        st.caption(f"Pixel preview unavailable ({type(e).__name__}); outlines are drawn on a blank canvas.")
    fig = overlay_figure(asset.width_px, asset.height_px, feats, preview_uri=uri, scale=scale,
                         show_inactive=show_inactive,
                         height=int(min(660, max(300, 640 * asset.height_px / max(1, asset.width_px)))) + 34)
    if draw:
        fig.update_layout(dragmode="select")
        event = st.plotly_chart(fig, key=f"ov_{asset.image_id}", on_select="rerun", selection_mode=("box",),
                                theme=None, config={"displaylogo": False, "scrollZoom": True})
        _capture_box(event, asset)
    else:
        st.plotly_chart(fig, key=f"ovs_{asset.image_id}", theme=None,
                        config={"displaylogo": False, "scrollZoom": True})
    html(basis_legend_html())
    st.caption("Outline colour and dash = evidence basis (solid observed / user-confirmed, dashed inferred, dotted "
               "assumed). Hover a shape for type, method and version, confidence, pixel uncertainty and evidence.")


def _capture_box(event: Any, asset) -> None:
    try:
        boxes = (event or {}).get("selection", {}).get("box", []) if isinstance(event, dict) else \
            list(getattr(getattr(event, "selection", None), "box", []) or [])
    except Exception:  # noqa: BLE001
        boxes = []
    if not boxes:
        return
    b = boxes[-1]
    xs, ys = b.get("x", []), b.get("y", [])
    if len(xs) < 2 or len(ys) < 2:
        return
    plan = S.is_plan_image(asset)
    row = {"type": "building_outline" if plan else "window", "x0": round(min(xs), 1), "y0": round(min(ys), 1),
           "x1": round(max(xs), 1), "y1": round(max(ys), 1), "label": "", "storey": None, "block": "main",
           "roof_form": "", "ridge": "", "gable_visible": False, "length_m": None, "axis": "", "active": True,
           "id": None}
    drafts = st.session_state.setdefault("ann_draft", {})
    rows = drafts.setdefault(asset.image_id, None)
    if rows is None:
        rows = S.annotation_rows(S.get_workspace(), asset.image_id)
    last = rows[-1] if rows else None
    if last and all(abs((last.get(k) or 0) - row[k]) < 0.5 for k in ("x0", "y0", "x1", "y1")):
        return
    rows.append(row)
    drafts[asset.image_id] = rows
    st.session_state["ann_ver"] = st.session_state.get("ann_ver", 0) + 1
    st.toast(f"Box {row['x0']:.0f},{row['y0']:.0f} - {row['x1']:.0f},{row['y1']:.0f} px added to the annotation draft "
             "(Annotate tab).")


def _image_details(ws: S.Workspace, asset, ia) -> None:
    p = ws.project
    html(f'<div style="font-weight:600">{esc(asset.original_filename)}</div>'
         f'<div class="hbv-small hbv-mono">{esc(asset.image_id)} · {asset.width_px}×{asset.height_px} px · '
         f'{asset.size_bytes / 1024:,.0f} kB · sha256 {esc(asset.sha256[:12])}…</div>')
    kk, vk = f"im_kind_{asset.image_id}", f"im_view_{asset.image_id}"
    kinds, views = list(S.KIND_LABELS), list(S.VIEW_LABELS)
    c1, c2 = st.columns(2)
    c1.selectbox("Kind", kinds, index=kinds.index(S.kind_label(asset.kind)), key=kk,
                 on_change=_cb_image_meta, args=(asset.image_id, kk, vk))
    c2.selectbox("View", views, index=views.index(S.view_label(asset.view)), key=vk,
                 on_change=_cb_image_meta, args=(asset.image_id, kk, vk))
    if asset.exif:
        st.caption("EXIF (safe subset): " + ", ".join(f"{k}={v}" for k, v in asset.exif.items())[:300])
    if ia is not None:
        n_active = sum(1 for f in ia.features if f.active)
        counts: dict[str, int] = {}
        for f in ia.features:
            if f.active:
                counts[f.basis.value] = counts.get(f.basis.value, 0) + 1
        html(f'<div class="hbv-small" style="margin:.2rem 0">{n_active} active feature(s) · '
             + " ".join(badge(b, label=f"{BASIS_LABEL_SHORT.get(b.value, b.value)} {counts[b.value]}")
                        for b in BASIS_ORDER if b.value in counts) + "</div>")
        facades = [f for f in (p.analysis.facades if p.analysis else []) if f.image_id == asset.image_id]
        if facades:
            rows = []
            for fo in facades:
                rows.append({"block": fo.block_hint, "view": fo.view.value, "storeys": fo.storeys.value,
                             "width px": fo.width_px.value, "eaves px": fo.eaves_height_px.value,
                             "ridge px": fo.ridge_height_px.value, "roof": fo.roof_form or "?",
                             "pitch (obs.)": None if fo.apparent_pitch_deg is None else fo.apparent_pitch_deg.value,
                             "openings": len(fo.openings)})
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                         column_config={k: st.column_config.NumberColumn(format="%.1f")
                                        for k in ("width px", "eaves px", "ridge px", "pitch (obs.)")})
        elif ia.features:
            st.caption("No facade measurements from this image (not an elevation-like view, or no facade box).")
        with st.expander("Adapters run on this image"):
            st.dataframe(pd.DataFrame([{"adapter": r.adapter, "version": r.version, "capability": r.capability,
                                        "status": r.status, "message": r.message[:120]} for r in ia.adapters]),
                         hide_index=True, width="stretch")
    if S.vlm_available():
        k = "vlm_toggle"
        st.toggle("Claude vision-language cross-check", value=ws.vlm_enabled, key=k, on_change=_cb_vlm, args=(k,),
                  help="Opt-in: sends the image to an external API. Output is always inferred, schema-validated, "
                       "clamped and used as a cross-check only.")
    k2 = "opt_adapters"
    st.toggle("Optional local detectors", value=ws.optional_adapters, key=k2, on_change=_cb_optional, args=(k2,),
              help="OpenCV line segments and transformers detectors / depth when installed (transformers may "
                   "download model weights). Off: bundled fixtures + NumPy line detection only.")
    st.button("Remove this image", key=f"rm_{asset.image_id}", on_click=_cb_remove_image, args=(asset.image_id,),
              type="tertiary")


BASIS_LABEL_SHORT = {"observed": "obs", "inferred": "inf", "user_confirmed": "conf", "assumed": "asm",
                     "unknown": "unk"}


def _feature_table(ws: S.Workspace, image_id: str, ia) -> None:
    if ia is None or not ia.features:
        st.info("No features on this image yet - add annotations in the Annotate tab.")
        return
    feats = list(ia.features)
    rows = []
    for f in feats:
        rejected = is_user_rejection(f)
        superseded = (not f.active) and not rejected
        rows.append({"active": f.active, "type": f.feature_type.value, "label": f.label[:60],
                     "basis": f.basis.value, "method": f"{f.method} v{f.method_version}",
                     "conf.": f.confidence, "px σ": f.pixel_uncertainty,
                     "block": str(f.attributes.get("block", "")), "storey": f.attributes.get("storey"),
                     "status": "rejected by you" if rejected else ("superseded" if superseded else "in use"),
                     "feature_id": f.feature_id})
    df = pd.DataFrame(rows)
    key = f"feat_{image_id}_{(ws.analysis_key or '')[:10]}"
    st.data_editor(df, key=key, hide_index=True, width="stretch", height=min(420, 38 + 35 * len(df)),
                   disabled=[c for c in df.columns if c != "active"],
                   column_config={
                       "active": st.column_config.CheckboxColumn("active", help="Untick to reject a detection; the "
                                                                 "analysis re-runs without it."),
                       "conf.": st.column_config.NumberColumn(format="%.2f"),
                       "px σ": st.column_config.NumberColumn(format="%.1f"),
                       "storey": st.column_config.NumberColumn(format="%d"),
                   },
                   on_change=_cb_features, args=(image_id, key, [r["feature_id"] for r in rows]))
    st.caption("Rejections and annotations are recorded as user input (with an edit record) and re-run the "
               "analysis; calibration, hypotheses and the twin follow.")


def _annotation_editor(ws: S.Workspace, asset) -> None:
    plan = S.is_plan_image(asset)
    if plan:
        st.caption("Floor plan: draw one **building_outline** box per rectangular block (block 'main', 'garage', "
                   "'extension', ...; an outline left without a block is read as the whole building and only "
                   "transfers the scale) and at least one **dimension** line along a dimensioned wall with its real "
                   "**length_m** and **axis** (width = along the frontage, depth = front to rear; optional "
                   "tolerance). The dimensions calibrate the plan; each outline then gives its block's width and "
                   "depth in metres - evidence-based depth instead of an assumption. Set **front** to 'top' on an "
                   "outline when the street side is at the top of the sheet. Pixels, origin top-left.")
    else:
        st.caption("Annotate in image pixels (origin top-left). Minimum for a facade: a facade box (block 'main'), the "
                   "ground line, the eaves line, the ridge line and the openings (window / door / garage_door) with "
                   "their **storey** (0 = ground floor; it is used as entered) and **block**. **Roof form**, **ridge** "
                   "(parallel / perpendicular to this view) and **gable visible** belong on a **roof** row: with a "
                   "visible gable the roof box is read as the gable triangle (base = box bottom, apex = top centre), "
                   "so its pitch is measured. Annotations are user-confirmed evidence and override overlapping "
                   "detections; untick 'active' to keep a row without using it. Tip: enable 'Draw boxes' above the "
                   "image and box-select to add rows.")
    drafts = st.session_state.setdefault("ann_draft", {})
    rows = drafts.get(asset.image_id)
    if rows is None:
        rows = S.annotation_rows(ws, asset.image_id)
    cols = S.PLAN_COLUMNS if plan else S.ELEVATION_COLUMNS
    df = pd.DataFrame([{c: r.get(c) for c in cols} for r in rows], columns=cols) if rows else \
        pd.DataFrame({c: pd.Series(dtype="object") for c in cols})
    for c in ("x0", "y0", "x1", "y1", "storey", "length_m", "tolerance_m", "storeys"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c, default in (("active", True), ("gable_visible", False)):
        if c in df.columns:
            df[c] = pd.Series([default if v is None or v is pd.NA or (isinstance(v, float) and v != v) else bool(v)
                               for v in df[c]], index=df.index, dtype=bool)
    types = list(S.PLAN_ANNOTATION_TYPES if plan else S.ANNOTATION_TYPES)
    config: dict[str, Any] = {
        "type": st.column_config.SelectboxColumn("type", options=types, required=True),
        "x0": st.column_config.NumberColumn("x0", format="%.1f"),
        "y0": st.column_config.NumberColumn("y0", format="%.1f"),
        "x1": st.column_config.NumberColumn("x1", format="%.1f"),
        "y1": st.column_config.NumberColumn("y1", format="%.1f"),
        "label": st.column_config.TextColumn("label", max_chars=120),
        "block": st.column_config.TextColumn("block", max_chars=30, help="e.g. main, garage, extension"),
        "active": st.column_config.CheckboxColumn("active", default=True,
                                                  help="Unticked: kept (with a 'rejected' history record) but not "
                                                       "used - it supersedes, calibrates and contributes nothing."),
        "id": None,  # stable feature id (hidden): never the row position
    }
    if plan:
        config.update({
            "length_m": st.column_config.NumberColumn("length (m)", min_value=0.0, max_value=S.MAX_PLAN_DIMENSION_M,
                                                      format="%.3f", help="Dimension rows: the real length in metres"),
            "axis": st.column_config.SelectboxColumn("axis", options=list(S.PLAN_AXES),
                                                     help="Dimension rows: width (along the frontage) or depth"),
            "tolerance_m": st.column_config.NumberColumn("± (m)", min_value=0.0, format="%.3f",
                                                         help="Dimension rows: tolerance of the dimension (default "
                                                              "0.02 m)"),
            "storeys": st.column_config.NumberColumn("storeys", min_value=1, max_value=6, step=1, format="%d",
                                                     help="Outline rows: storeys of that block, if the plan shows "
                                                          "them"),
            "front": st.column_config.SelectboxColumn("front", options=list(S.PLAN_FRONT),
                                                      help="Outline rows: edge of the sheet facing the street "
                                                           "(blank = bottom)"),
        })
    else:
        config.update({
            "storey": st.column_config.NumberColumn("storey", min_value=0, max_value=9, step=1, format="%d",
                                                    help="Openings only: 0 = ground floor"),
            "roof_form": st.column_config.SelectboxColumn("roof form", options=list(S.ROOF_FORMS),
                                                          help="Roof rows only"),
            "ridge": st.column_config.SelectboxColumn("ridge", options=list(S.RIDGE_CHOICES),
                                                      help="Roof rows only: ridge parallel or perpendicular to this "
                                                           "view (a gable facing you = perpendicular)"),
            "gable_visible": st.column_config.CheckboxColumn("gable visible", default=False,
                                                             help="Roof rows only: the gable triangle is visible "
                                                                  "(box base = eaves, apex = top centre)"),
        })
    edited = st.data_editor(
        df, key=f"ann_{asset.image_id}_{st.session_state.get('ann_ver', 0)}", num_rows="dynamic", hide_index=True,
        width="stretch", column_config=config)
    c1, c2, _ = st.columns([1, 1, 3])
    if c1.button("Apply annotations", key=f"ann_apply_{asset.image_id}", type="primary"):
        recs = edited.astype(object).where(pd.notna(edited), None).to_dict(orient="records")
        errors = S.set_annotations(ws, asset.image_id, recs)
        if errors:
            for e in errors[:8]:
                st.error(md_escape(e))
        else:
            drafts.pop(asset.image_id, None)
            st.session_state["ann_ver"] = st.session_state.get("ann_ver", 0) + 1
            ws.say("success", f"{len([r for r in recs if r.get('type')])} annotation(s) applied; analysis re-run.")
            st.rerun()
    if c2.button("Discard draft", key=f"ann_discard_{asset.image_id}"):
        drafts.pop(asset.image_id, None)
        st.session_state["ann_ver"] = st.session_state.get("ann_ver", 0) + 1
        st.rerun()


def _calibration_panel(ws: S.Workspace) -> None:
    p = ws.project
    cal = p.calibration
    if ws.calibration_error:
        st.error(md_escape(ws.calibration_error))
    if cal is None:
        st.info("No facade measurements yet, so there is no scale. Add annotations (facade box, ground / eaves "
                "lines) or an image with a detection fixture.")
        return
    tv = cal.metres_per_pixel
    lo, hi = tv.bounds()
    rel = tv.relative_spread()
    method = cal.method.replace("_", " ")
    conflict = S.reference_conflict(cal)
    if conflict is not None:
        factor, ref_v, cue_v = conflict
        html(callout(f"The reference implies <b>{ref_v * 1000:.3f} mm/px</b>, but the labelled prior cues of the same "
                     f"image imply <b>{cue_v * 1000:.3f} mm/px</b> - {factor:.1f}x apart. Wrong endpoints, the wrong "
                     "feature or the wrong unit are the usual causes. The twin is not rebuilt automatically while this "
                     "conflict stands.", title="Reference conflicts with the prior scale cues", tone="danger"))
    c1, c2 = st.columns([1.15, 1])
    with c1:
        html(f'<div class="hbv-cards" style="grid-template-columns:repeat(3,1fr)">'
             f'<div class="hbv-card hbv-card-accent"><div class="hbv-card-k">Scale ({esc(method)})</div>'
             f'<div class="hbv-card-v">{tv.value * 1000:.3f} mm/px</div>'
             f'<div style="margin-top:.25rem">{badge(tv.basis)}</div></div>'
             f'<div class="hbv-card"><div class="hbv-card-k">Range</div>'
             f'<div class="hbv-card-v">{lo * 1000:.3f}–{hi * 1000:.3f}</div><div class="hbv-card-sub">mm/px · '
             f'{esc(tv.distribution.value)}</div></div>'
             f'<div class="hbv-card"><div class="hbv-card-k">Relative spread</div>'
             f'<div class="hbv-card-v">±{(rel or 0) * 50:.1f}%</div><div class="hbv-card-sub">'
             f'carried into every scaled dimension</div></div></div>')
        if cal.cues:
            st.caption("Prior scale cues (labelled assumptions" + (", shown as a cross-check of the reference)"
                                                                   if cal.method == "reference_measurement" else ")"))
            st.dataframe(pd.DataFrame([{"cue": c.name, "pixels": c.pixels, "assumed real": c.assumed_real.label(),
                                        "implied mm/px": c.implied_m_per_px.value * 1000,
                                        "basis": c.assumed_real.basis.value} for c in cal.cues]),
                         hide_index=True, width="stretch",
                         column_config={"pixels": st.column_config.NumberColumn(format="%.1f"),
                                        "implied mm/px": st.column_config.NumberColumn(format="%.3f")})
        with st.expander("Calibration notes"):
            for n in cal.notes:
                st.markdown(f"- {md_escape(n)}")
    with c2:
        if cal.method != "reference_measurement":
            hint = next((n for n in cal.notes if "Most useful" in n), "Confirm one real dimension, e.g. the "
                        "frontage width of the main facade (corner to corner), with its tolerance.")
            if not ws.proceed_with_assumptions:
                html(callout(f"Scale comes from labelled prior cues (door / garage-door / wall heights) - an "
                             f"assumption, ±{(rel or 0) * 50:.0f}%. {esc(hint)}", title="Calibration measurement needed",
                             tone="warn"))
                st.button("Continue with labelled assumptions", key="cal_proceed", on_click=_cb_proceed,
                          help="Keep the prior-cue scale; every scaled dimension stays ASSUMED with its full range.")
            else:
                html(callout("Continuing with the prior-cue scale: scaled dimensions keep their assumption label and "
                             "range until a reference is confirmed.", title="Labelled assumptions in use",
                             tone="neutral"))
        if p.references:
            r = p.references[0]
            target = r.feature_id or (f"pixel endpoints ({r.p0[0]:.0f},{r.p0[1]:.0f})-({r.p1[0]:.0f},{r.p1[1]:.0f})"
                                      if r.p0 and r.p1 else "main front facade width")
            img = ws.image(r.image_id)
            html(callout(f"{r.real_length:g} {esc(r.unit)} ± {r.tolerance:g} {esc(r.unit)} · {esc(r.description)} · "
                         f"source: {esc(r.source)} · image: {esc(img.original_filename if img else r.image_id)} · "
                         f"target: {esc(target)}"
                         + (f" ({esc(r.feature_type)}, {r.feature_span_px:.0f} px when confirmed)"
                            if r.feature_type and r.feature_span_px else ""),
                         title="Reference in use (user-confirmed)" if not ws.calibration_error
                         else "Reference NOT in use (see the error above)",
                         tone="info" if not ws.calibration_error else "danger"))
            st.button("Remove reference", key="cal_clear", on_click=_cb_clear_ref, type="tertiary")
        _reference_form(ws)


def _ref_placeholder(asset, feat) -> str:
    """Placeholder (never a default value) for the reference description, from the chosen feature and view."""
    if feat is not None and feat.feature_type.value == "facade":
        if asset is not None and asset.view.value in ("left", "right"):
            return "e.g. measured side wall length (front to rear corner)"
        if asset is not None and asset.view.value == "rear":
            return "e.g. measured rear wall width"
        return "e.g. measured frontage width (corner to corner)"
    if feat is not None:
        return f"e.g. measured {feat.feature_type.value.replace('_', ' ')} width"
    return "what you measured, and how"


def _reference_form(ws: S.Workspace) -> None:
    """Reference measurement entry.  Nothing is pre-filled for a real project (no fictional 'survey' values);
    the image and measuring mode sit outside the form so the feature list always follows the chosen image."""
    from ...demo.build_demo import DEMO_PROJECT_ID, FRONTAGE_M, FRONTAGE_TOLERANCE_M

    p = ws.project
    analysis = p.analysis
    primary = analysis.primary_image_id if analysis else None
    img_ids = [a.image_id for a in p.images]
    if not img_ids:
        return
    demo = p.project_id == DEMO_PROJECT_ID
    st.markdown("**Confirm a reference dimension**")
    if st.session_state.get("ref_img") not in img_ids:
        st.session_state["ref_img"] = primary if primary in img_ids else img_ids[0]
    img = st.selectbox("Image", img_ids, key="ref_img",
                       format_func=lambda i: ws.image(i).original_filename if ws.image(i) else i)
    mode = st.radio("Measure", ["Feature width (box)", "Pixel endpoints"], horizontal=True, key="ref_mode")
    asset = ws.image(img)
    feats = [f for a in analysis.analyses if a.image_id == img for f in a.features
             if f.active and f.bbox is not None] if analysis else []
    feats.sort(key=lambda f: (f.feature_type.value != "facade", f.feature_id))
    by_id = {f.feature_id: f for f in feats}
    with st.form(f"ref_form_{img}", border=True):
        fid: Optional[str] = None
        xy: list[Optional[float]] = [None] * 4
        if mode.startswith("Feature"):
            if feats:
                fid = st.selectbox("Feature (its box width is the reference span)", list(by_id), key=f"ref_feat_{img}",
                                   format_func=lambda i: f"{by_id[i].feature_type.value} · {by_id[i].label[:40]} · "
                                                         f"{by_id[i].width_px():.0f} px")
            else:
                st.caption("This image has no active feature with a box - use pixel endpoints or annotate a box.")
        else:
            w, h = (asset.width_px, asset.height_px) if asset else (0, 0)
            st.caption(f"End points of the measured length in image pixels (0-{w} x 0-{h}, origin top-left).")
            cc = st.columns(4)
            for j, name in enumerate(("x0", "y0", "x1", "y1")):
                xy[j] = cc[j].number_input(f"{name} px", value=None, min_value=0.0, step=1.0, key=f"ref_{name}_{img}",
                                           placeholder="px")
        c1, c2, c3 = st.columns([1.2, 0.8, 1])
        length = c1.number_input("Real length", value=FRONTAGE_M if demo else None, min_value=0.0, step=0.01,
                                 format="%.3f", placeholder="measured", key=f"ref_len_{img}")
        unit = c2.selectbox("Unit", REF_UNITS, key=f"ref_unit_{img}")
        tol = c3.number_input("Tolerance ±", value=FRONTAGE_TOLERANCE_M if demo else None, min_value=0.0, step=0.005,
                              format="%.3f", placeholder="same unit", key=f"ref_tol_{img}",
                              help="Accuracy of your measurement, in the same unit (e.g. 0.02 m for a tape measure).")
        desc = st.text_input("Description", value="measured frontage width (corner to corner)" if demo else "",
                             max_chars=200, key=f"ref_desc_{img}",
                             placeholder=_ref_placeholder(asset, by_id.get(fid) if fid else None))
        force = st.checkbox("Use anyway if it conflicts with the prior scale cues (2x or more)", key=f"ref_force_{img}",
                            help="Only when you are sure the door / wall-height cues are wrong for this building.")
        ok = st.form_submit_button("Apply calibration", type="primary")
    if demo:
        st.caption("Demo project: the fictional survey frontage (9.60 m ± 0.02 m) is pre-filled. New projects start "
                   "empty - enter a dimension you actually measured.")
    if not ok:
        return
    problems = []
    if length is None or length <= 0:
        problems.append("enter the real length you measured")
    if tol is None:
        problems.append("enter the tolerance of your measurement")
    if not (desc or "").strip():
        problems.append("describe what was measured")
    kwargs: dict[str, Any] = {}
    if mode.startswith("Feature"):
        if not fid or fid not in by_id:
            problems.append("choose a feature of this image with a box, or use pixel endpoints")
        else:
            kwargs["feature_id"] = fid
    else:
        if any(v is None for v in xy):
            problems.append("enter all four pixel coordinates")
        else:
            x0, y0, x1, y1 = (float(v) for v in xy)  # type: ignore[arg-type]
            if asset is not None and (max(x0, x1) > asset.width_px or max(y0, y1) > asset.height_px):
                problems.append(f"the end points must lie inside the image ({asset.width_px} x {asset.height_px} px)")
            elif ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 < 20:
                problems.append("the end points must be at least 20 px apart")
            else:
                kwargs["p0"], kwargs["p1"] = (x0, y0), (x1, y1)
    if problems:
        st.error("Reference not applied: " + "; ".join(problems) + ".")
        return
    try:
        ref = ReferenceMeasurement(image_id=img, real_length=float(length), unit=unit, tolerance=float(tol),
                                   description=desc.strip()[:200], source="user (UI)", **kwargs)
    except ValidationError as e:
        st.error(f"Reference not valid: {md_escape(e.errors()[0].get('msg'))}")
        return
    err = S.set_reference(ws, ref, allow_conflict=bool(force))
    if err:
        st.error(md_escape(err))
    else:
        ws.say("success", "Calibration applied: every scaled dimension now carries the reference tolerance.")
        st.rerun()


def _unknowns(ws: S.Workspace) -> None:
    a = ws.project.analysis
    if a is None:
        st.info("Analyse an image first.")
        return
    c1, c2 = st.columns(2)
    with c1:
        html(callout("<ul>" + "".join(f"<li>{esc(u)}</li>" for u in a.unknowns) + "</ul>",
                     title=f"Unknowns carried forward ({len(a.unknowns)})", tone="neutral"))
    with c2:
        if a.warnings:
            html(callout("<ul>" + "".join(f"<li>{esc(w)}</li>" for w in a.warnings[:30]) + "</ul>",
                         title=f"Warnings ({len(a.warnings)})", tone="warn"))
        else:
            html(callout("No analysis warnings.", title="Warnings", tone="neutral"))
        if a.multiview is not None:
            mv = a.multiview
            html(callout("<ul>" + "".join(f"<li>{esc(k)}: {esc(v.label())} {badge(v.basis)}</li>"
                                         for k, v in mv.linked_measurements.items()) + "</ul>"
                         + "".join(f"<div class='hbv-small'>{esc(n)}</div>" for n in mv.notes[:4]),
                         title="Multi-view links", tone="info"))
    with st.expander("Model and adapter versions"):
        st.json(a.model_versions, expanded=False)


def _hypotheses(ws: S.Workspace) -> None:
    p = ws.project
    hyps = p.hypotheses
    section_title("Geometry hypotheses", sub="competing hidden-footprint readings of the same evidence")
    status = S.twin_status(ws)
    if status == "orphaned" and p.twin is not None:
        html(callout(f"Twin v{p.twin.version} was built from {esc(p.twin.source_hypothesis_id)}, but the images it "
                     "was measured from have been removed. It is kept as a manual model: its scale method, dimensions "
                     "and evidence links refer to evidence that is no longer in the project.",
                     title="Evidence removed - twin kept as a manual model", tone="warn"))
    if status == "stale" and p.twin is not None:
        n = S.user_geometry_edits(p.twin)
        why = (" The reference measurement conflicts with the prior scale cues, so the twin was not rebuilt "
               "automatically." if S.reference_conflict(p.calibration) is not None else "")
        html(callout(f"The evidence or calibration changed after the twin was built (twin v{p.twin.version} from "
                     f"{esc(p.twin.source_hypothesis_id)}, {n} geometry edit(s)).{why} Quantities and costs still "
                     "describe that twin. Rebuild to follow the updated hypothesis (edits are not carried over; the "
                     "assembly selection is kept).", title="Twin based on earlier evidence", tone="danger"))
        if p.selected_hypothesis_id:
            st.button(f"Rebuild twin from {p.selected_hypothesis_id}", key="rebuild_twin", on_click=_cb_build,
                      args=(p.selected_hypothesis_id,))
    if not hyps:
        st.info("No hypotheses yet: they need at least one facade observation (a facade box with ground / eaves "
                "lines) on an elevation-like view.")
        return
    system = p.settings.unit_system
    cols = st.columns(len(hyps), gap="small")
    for col, h in zip(cols, hyps):
        with col, st.container(border=True):
            current = p.twin is not None and p.twin.source_hypothesis_id == h.hypothesis_id
            head = tag("twin source", tone="gold") if current else ""
            sel = tag("selected", tone="neutral") if p.selected_hypothesis_id == h.hypothesis_id and not current else ""
            rows = []
            for b in h.blocks:
                if b.roof.form.value == "flat":
                    roof_cell = "flat"
                else:
                    roof_cell = (f"{esc(b.roof.form.value)} {esc(fmt.tv_value(b.roof.pitch_deg, system, 1))}<br>"
                                 f"{badge(b.roof.pitch_deg.basis)}")
                rows.append(
                    f"<tr><td>{esc(b.block_id)}</td>"
                    f"<td class='n'>{esc(fmt.tv_value(b.width, system))}<br>{badge(b.width.basis)}"
                    f"<div class='hbv-range'>{esc(fmt.tv_range(b.width, system).split(' · ')[0])}</div></td>"
                    f"<td class='n'>{esc(fmt.tv_value(b.depth, system))}<br>{badge(b.depth.basis)}"
                    f"<div class='hbv-range'>{esc(fmt.tv_range(b.depth, system).split(' · ')[0])}</div></td>"
                    f"<td class='n'>{int(b.storeys.value or 0)}</td>"
                    f"<td class='n'>{roof_cell}</td></tr>")
            notes = "".join(f"<li>{esc(n)}</li>" for n in h.notes[:4])
            html(f'<div class="hbv-hyp"><div style="display:flex;justify-content:space-between;align-items:center">'
                 f'<div style="font-weight:600;font-size:.9rem">{esc(h.hypothesis_id)} · {esc(h.name)}</div>'
                 f'<div>{head}{sel}</div></div>'
                 f'<div class="hbv-small" style="margin:.2rem 0">{esc(h.description)}</div>'
                 f'<div class="hbv-small">Plausibility <span class="hbv-mono">{h.plausibility:.2f}</span> '
                 f'<span title="A subjective prior weight for comparison, not a probability calibrated against data">'
                 f'(subjective prior, not a probability)</span></div>'
                 f'<div class="hbv-bar"><div style="width:{100 * h.plausibility:.0f}%"></div></div>'
                 f'<table><tr><th>block</th><th>width</th><th>depth</th><th>st.</th><th>roof</th></tr>{"".join(rows)}'
                 f'</table><div class="hbv-small" style="margin-top:.2rem">Assumption labels</div>'
                 f'<ul style="margin:.1rem 0 .2rem 1rem;padding:0">{notes}</ul>'
                 f'<div class="hbv-small">Hidden facades: rear glazing {fmt.pct(h.hidden.rear_glazing_ratio.value, 0)}, '
                 f'side glazing {fmt.pct(h.hidden.side_glazing_ratio.value, 0)} {badge(h.hidden.rear_glazing_ratio.basis)}'
                 f' · calibration: {esc(h.calibration_method.replace("_", " "))}</div></div>')
            if current and status == "ok":
                st.button("Twin built from this hypothesis", key=f"hyp_{h.hypothesis_id}", disabled=True,
                          width="stretch")
            else:
                st.button(f"Build twin from {h.hypothesis_id}", key=f"hyp_{h.hypothesis_id}", type="primary",
                          on_click=_cb_build, args=(h.hypothesis_id,), width="stretch")
    st.caption("Hypotheses are compared, never averaged. Selecting one builds an editable twin; the others remain "
               "available as build scenarios (Scenarios view).")


__all__ = ["render"]
