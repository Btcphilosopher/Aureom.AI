"""Plotly figure builders for the UI (pure functions: model objects in, ``go.Figure`` out).

Conventions: the ``"aureom"`` template (:func:`..theme.plotly_template`) - graphite surface,
hairline grid, Inter labels, IBM Plex Mono ticks; one axis per chart (separate panels instead of
dual axes); basis colours from :data:`..theme.BASIS_COLOURS` everywhere, always with a legend
and a dash code; gold only for emphasis (P50, critical path, highlighted geometry, final totals).
Every figure states its boundary / assumption in the view caption that accompanies it.

All text placed in hover labels that may come from untrusted sources (feature labels, evidence,
filenames) is HTML-escaped.
"""

from __future__ import annotations

import math
import textwrap
from typing import Any, Iterable, Optional, Sequence

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..core.models import (
    COST_LAYER_NAMES,
    BuildingTwin,
    CarbonResult,
    CostEstimate,
    CostLayer,
    DetectedFeature,
    GeometryMetrics,
    HeatLossResult,
    ProgrammeResult,
    RepeatBuildResult,
    ScenarioOutcome,
    SensitivityItem,
)
from .fmt import money, money_short
from .theme import (
    BASIS_COLOURS,
    BASIS_DASH,
    BASIS_ORDER,
    DIVERGING,
    GOLD,
    GRAPHITE_RAISED,
    GRAPHITE_SURFACE,
    GRID,
    INK_MUTED,
    IVORY,
    IVORY_MUTED,
    NEUTRAL_MARK,
    SERIES,
    SINGLE_SERIES,
    TEMPLATE_NAME,
    as_basis,
    basis_label,
    esc,
    hex_to_rgba,
    plotly_template,
)

plotly_template()
EDGE_COLOUR = "#121315"


def _wrap(text: str, width: int = 64, max_lines: int = 5) -> str:
    lines = textwrap.wrap(esc(text), width=width)[:max_lines]
    return "<br>".join(lines)


def _base(fig: go.Figure, *, height: int, title: str = "", **layout: Any) -> go.Figure:
    fig.update_layout(template=TEMPLATE_NAME, height=height, title=dict(text=esc(title)) if title else None,
                      **layout)
    return fig


# =============================================================================
# Image evidence overlay
# =============================================================================
def _feature_path(f: DetectedFeature) -> Optional[tuple[list[float], list[float], bool]]:
    if f.polygon:
        xs = [p[0] for p in f.polygon] + [f.polygon[0][0]]
        ys = [p[1] for p in f.polygon] + [f.polygon[0][1]]
        return xs, ys, True
    if f.bbox:
        x0, y0, x1, y1 = f.bbox
        return [x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], True
    if f.line:
        x0, y0, x1, y1 = f.line
        t = np.linspace(0.0, 1.0, 9)
        return list(x0 + (x1 - x0) * t), list(y0 + (y1 - y0) * t), False
    return None


def feature_hover(f: DetectedFeature) -> str:
    b = as_basis(f.basis)
    conf = "n/a" if f.confidence is None else f"{f.confidence:.2f}"
    attrs = ", ".join(f"{esc(k)}={esc(v)}" for k, v in sorted(f.attributes.items()) if k != "source_image")
    parts = [f"<b>{esc(f.feature_type.value.replace('_', ' '))}</b>  {esc(f.label)[:80]}",
             f"basis: {basis_label(b)}" + ("" if f.active else "  (inactive)"),
             f"method: {esc(f.method)} v{esc(f.method_version)}",
             f"confidence: {conf} · pixel uncertainty ±{f.pixel_uncertainty:.1f} px (1σ)"]
    if attrs:
        parts.append(f"attributes: {attrs[:120]}")
    if f.evidence:
        parts.append(_wrap(f.evidence))
    parts.append(f"<span style='color:{INK_MUTED}'>{esc(f.feature_id)}</span>")
    return "<br>".join(parts)


_BIG_FEATURES = ("facade", "roof", "finish_region", "building_outline", "garage", "extension")


def _hover_points(f: DetectedFeature, width_px: int, height_px: int) -> list[tuple[float, float]]:
    """Points that carry a feature's hover text (fills only show the trace name in plotly).

    Openings and other small boxes: centre and corners; big shapes (facade, roof, finish regions, outlines):
    corners and edge midpoints plus the centre; lines: five points along the line.  A box covering most of
    the image (e.g. an 'other: image metadata' box) gets its corners only, so it never captures the hover of
    the windows and doors inside it.
    """
    if f.line is not None:
        x0, y0, x1, y1 = f.line
        return [(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t) for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
    if f.polygon:
        pts = [(float(x), float(y)) for x, y in f.polygon]
        cx, cy = sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)
        return pts + [(cx, cy)]
    if f.bbox is None:
        return []
    x0, y0, x1, y1 = f.bbox
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    centre = (0.5 * (x0 + x1), 0.5 * (y0 + y1))
    if (x1 - x0) * (y1 - y0) > 0.5 * max(1, width_px) * max(1, height_px) \
            and f.feature_type.value not in _BIG_FEATURES:
        return corners
    if f.feature_type.value in _BIG_FEATURES:
        mids = [(centre[0], y0), (x1, centre[1]), (centre[0], y1), (x0, centre[1])]
        return corners + mids + [centre]
    return corners + [centre]


def overlay_figure(width_px: int, height_px: int, features: Sequence[DetectedFeature], *,
                   preview_uri: Optional[str] = None, scale: float = 1.0, show_inactive: bool = False,
                   selected_id: Optional[str] = None, height: int = 560) -> go.Figure:
    """Image with every feature outlined in its basis colour + dash; hover gives the evidence.

    Outlines (and their faint fills) never take the hover; every feature instead has invisible hover
    points (:func:`_hover_points`) in one trace drawn on top, so windows and doors inside a facade, roof or
    image-wide box show their own type, method and version, confidence, pixel uncertainty and evidence.
    Big shapes are drawn first and openings on top.
    """
    fig = go.Figure()
    if preview_uri:
        fig.add_trace(go.Image(source=preview_uri, x0=0, y0=0, dx=1.0 / scale, dy=1.0 / scale, hoverinfo="skip",
                               name="image"))
    seen: set[str] = set()
    order = {b: i for i, b in enumerate(BASIS_ORDER)}
    feats = sorted(features, key=lambda f: (f.active, f.feature_type.value not in _BIG_FEATURES))
    hx: list[float] = []
    hy: list[float] = []
    ht: list[str] = []
    for f in feats:
        if not f.active and not show_inactive:
            continue
        path = _feature_path(f)
        if path is None:
            continue
        xs, ys, closed = path
        b = as_basis(f.basis)
        col = BASIS_COLOURS[b] if f.active else NEUTRAL_MARK
        group = b.value if f.active else "inactive"
        name = basis_label(b) if f.active else "Inactive (rejected / superseded)"
        sel = f.feature_id == selected_id
        big = f.feature_type.value in _BIG_FEATURES
        fill_alpha = 0.0 if not closed else (0.05 if big else 0.13)
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines", name=name, legendgroup=group, showlegend=group not in seen,
            legendrank=order.get(b, 9) if f.active else 99,
            line=dict(color=GOLD if sel else col, width=3.0 if sel else (1.3 if big else 1.8),
                      dash="dot" if not f.active else BASIS_DASH[b]),
            fill="toself" if closed else None, fillcolor=hex_to_rgba(col, fill_alpha) if closed else None,
            hoverinfo="skip", opacity=0.75 if not f.active else 1.0))
        seen.add(group)
        text = feature_hover(f)
        for x, y in _hover_points(f, width_px, height_px):
            hx.append(float(x))
            hy.append(float(y))
            ht.append(text)
    if hx:
        fig.add_trace(go.Scatter(x=hx, y=hy, mode="markers", name="evidence details", showlegend=False,
                                 marker=dict(size=16, color="rgba(0,0,0,0)"), hovertext=ht,
                                 hovertemplate="%{hovertext}<extra></extra>"))
    fig.update_xaxes(visible=False, range=[0, width_px], constrain="domain")
    fig.update_yaxes(visible=False, range=[height_px, 0], scaleanchor="x", scaleratio=1, constrain="domain")
    _base(fig, height=height, margin=dict(l=0, r=0, t=26, b=0), plot_bgcolor=GRAPHITE_SURFACE,
          legend=dict(orientation="h", y=1.0, yanchor="bottom", x=0, title=dict(text="Evidence basis ")),
          dragmode="pan", hovermode="closest", hoverdistance=24, hoverlabel=dict(align="left"))
    return fig


# =============================================================================
# 3D twin
# =============================================================================
def _feature_edges(m: dict[str, Any]) -> tuple[list[Optional[float]], list[Optional[float]], list[Optional[float]]]:
    """Crease edges of a mesh (angle between faces > ~1 deg) as None-separated polylines."""
    import trimesh

    v = np.column_stack([m["x"], m["y"], m["z"]])
    f = np.column_stack([m["i"], m["j"], m["k"]])
    if len(f) == 0:
        return [], [], []
    tm = trimesh.Trimesh(vertices=v, faces=f, process=True)
    edges = tm.face_adjacency_edges[tm.face_adjacency_angles > 0.02]
    xs: list[Optional[float]] = []
    ys: list[Optional[float]] = []
    zs: list[Optional[float]] = []
    for a, b in edges:
        pa, pb = tm.vertices[a], tm.vertices[b]
        xs += [pa[0], pb[0], None]
        ys += [pa[1], pb[1], None]
        zs += [pa[2], pb[2], None]
    return xs, ys, zs


def resolve_refs(twin: BuildingTwin, metrics: Optional[GeometryMetrics], refs: Iterable[str]
                 ) -> dict[str, set]:
    """Group geometry refs of a quantity line into node names, wall pieces and storeys."""
    opening_ids = {o.opening_id for o in twin.openings}
    piece_ids = {p.piece_id for p in metrics.pieces} if metrics is not None else set()
    out: dict[str, set] = {"nodes": set(), "pieces": set(), "storeys": set(), "other": set()}
    for r in refs:
        if r in opening_ids:
            out["nodes"].add(f"opening/{r}")
        elif r in piece_ids:
            out["pieces"].add(r)
        elif r.startswith("block:"):
            bid = r.split(":", 1)[1]
            out["nodes"] |= {f"{bid}/walls", f"{bid}/roof"}
        elif r.startswith("roof:"):
            out["nodes"].add(f"{r.split(':', 1)[1]}/roof")
        elif r.startswith("storey:"):
            try:
                out["storeys"].add(int(r.split(":", 1)[1]))
            except ValueError:
                out["other"].add(r)
        else:
            out["other"].add(r)
    return out


def twin_figure(meshes: Sequence[dict[str, Any]], twin: BuildingTwin, *, mode: str = "finish",
                highlight: Optional[dict[str, set]] = None, metrics: Optional[GeometryMetrics] = None,
                height: int = 520, show_edges: bool = True) -> go.Figure:
    """3D massing: ``mode`` "finish" (visual appearance colours) or "basis" (evidence colours).

    ``highlight`` (from :func:`resolve_refs`) greys everything except the referenced nodes,
    outlines referenced wall pieces and draws referenced storey floor planes, in gold.
    """
    from ..twin.mesh import piece_outline_polylines

    fig = go.Figure()
    hl = highlight if highlight and any(highlight.get(k) for k in ("nodes", "pieces", "storeys")) else None
    seen: set[str] = set()
    xs_all, ys_all = [], []
    ex: list[Optional[float]] = []
    ey: list[Optional[float]] = []
    ez: list[Optional[float]] = []
    for m in meshes:
        meta = m.get("meta", {})
        b = as_basis(meta.get("basis", "unknown"))
        name = m["name"]
        xs_all += [min(m["x"]), max(m["x"])]
        ys_all += [min(m["y"]), max(m["y"])]
        opacity = float(m.get("opacity", 1.0))
        showlegend = False
        legend_name = name
        if hl is not None:
            on = name in hl["nodes"]
            colour = GOLD if on else "#3A3E44"
            opacity = 0.9 if on else 0.16
        elif mode == "basis":
            colour = BASIS_COLOURS[b]
            legend_name = basis_label(b)
            showlegend = b.value not in seen
            seen.add(b.value)
        else:
            colour = m["color"]
        kind = meta.get("kind", "")
        hover = (f"<b>{esc(name)}</b><br>kind: {esc(kind)}<br>basis: {basis_label(b)}"
                 + (f"<br>{esc(meta.get('visibility'))}" if meta.get("visibility") else "")
                 + (f"<br>rule: {esc(meta.get('hidden_side_rule'))}" if meta.get("hidden_side_rule") else ""))
        fig.add_trace(go.Mesh3d(
            x=m["x"], y=m["y"], z=m["z"], i=m["i"], j=m["j"], k=m["k"], color=colour, opacity=opacity,
            flatshading=True, name=legend_name, legendgroup=b.value if mode == "basis" else None,
            showlegend=showlegend, hovertext=hover, hoverinfo="text",
            lighting=dict(ambient=0.62, diffuse=0.75, specular=0.05, roughness=0.95, fresnel=0.05),
            lightposition=dict(x=-1200, y=-2200, z=3000)))
        if show_edges and (hl is None or name in hl["nodes"]):
            try:
                a, bb, c = _feature_edges(m)
                ex += a
                ey += bb
                ez += c
            except Exception:  # noqa: BLE001 - edges are decoration only
                pass
    if ex:
        fig.add_trace(go.Scatter3d(x=ex, y=ey, z=ez, mode="lines", line=dict(color=EDGE_COLOUR, width=2),
                                   hoverinfo="skip", showlegend=False, name="edges"))
    if hl is not None and metrics is not None:
        lx: list[Optional[float]] = []
        ly: list[Optional[float]] = []
        lz: list[Optional[float]] = []
        for poly in piece_outline_polylines(twin, metrics, offset_m=0.08):
            if poly["piece_id"] in hl["pieces"]:
                lx += poly["x"] + [None]
                ly += poly["y"] + [None]
                lz += poly["z"] + [None]
        for k in sorted(hl["storeys"]):
            for blk in twin.blocks:
                n = int(round(blk.storeys.value or 1))
                if k >= n or None in (blk.origin_x.value, blk.origin_y.value, blk.width.value, blk.depth.value):
                    continue
                z = float(blk.ground_floor_level.value or 0.0) + k * float(blk.floor_to_floor.value or 0.0)
                x0, y0 = blk.origin_x.value, blk.origin_y.value
                x1, y1 = x0 + blk.width.value, y0 + blk.depth.value
                lx += [x0, x1, x1, x0, x0, None]
                ly += [y0, y0, y1, y1, y0, None]
                lz += [z, z, z, z, z, None]
        if lx:
            fig.add_trace(go.Scatter3d(x=lx, y=ly, z=lz, mode="lines", line=dict(color=GOLD, width=7),
                                       name="referenced geometry", hoverinfo="skip", showlegend=True))
    if hl is not None:
        fig.add_trace(go.Scatter3d(x=[None], y=[None], z=[None], mode="markers",
                                   marker=dict(size=8, color=GOLD, symbol="square"), name="referenced by line"))
    # ground plate for context
    if xs_all:
        x0, x1 = min(xs_all) - 2.0, max(xs_all) + 2.0
        y0, y1 = min(ys_all) - 2.0, max(ys_all) + 2.0
        fig.add_trace(go.Mesh3d(x=[x0, x1, x1, x0], y=[y0, y0, y1, y1], z=[-0.02] * 4, i=[0, 0], j=[1, 2],
                                k=[2, 3], color=GRAPHITE_RAISED, opacity=1.0, hoverinfo="skip", showlegend=False,
                                name="ground"))
    axis = dict(showbackground=False, gridcolor=GRID, zerolinecolor=GRID, linecolor="#4A4F57", showspikes=False,
                tickfont=dict(size=9, color=INK_MUTED), title=dict(font=dict(size=10, color=INK_MUTED)))
    _base(fig, height=height, margin=dict(l=0, r=0, t=8, b=0),
          legend=dict(orientation="h", y=0.99, yanchor="top", x=0.01, bgcolor="rgba(21,23,26,0.6)"),
          scene=dict(aspectmode="data", bgcolor="rgba(0,0,0,0)",
                     xaxis=dict(axis, title=dict(text="x frontage (m)")),
                     yaxis=dict(axis, title=dict(text="y depth (m)")),
                     zaxis=dict(axis, title=dict(text="z (m)")),
                     camera=dict(eye=dict(x=-0.88, y=-1.45, z=0.62), up=dict(x=0, y=0, z=1),
                                 center=dict(x=0, y=0, z=-0.04))),
          uirevision=twin.twin_id)
    return fig


# =============================================================================
# Costs
# =============================================================================
_TOTAL_AFTER = {
    CostLayer.LOGISTICS_WASTE: ("direct_works", "Σ Direct works"),
    CostLayer.FEES_ALLOWANCES: ("construction_before_contingency", "Σ Before contingency"),
    CostLayer.CONTINGENCY: ("construction_incl_contingency", "Σ Incl. contingency"),
    CostLayer.OVERHEAD_MARGIN: ("contract_sum", "Σ Contract sum"),
}
_LAYER_SHORT = {
    CostLayer.MATERIALS: "1 Materials", CostLayer.LABOUR: "2 Labour", CostLayer.PLANT: "3 Plant",
    CostLayer.LOGISTICS_WASTE: "4 Logistics", CostLayer.PRELIMINARIES: "5 Prelims",
    CostLayer.FEES_ALLOWANCES: "6 Fees", CostLayer.CONTINGENCY: "7 Contingency",
    CostLayer.OVERHEAD_MARGIN: "8 OH & margin", CostLayer.LAND_FINANCE_TAX_SALES: "9 Land / finance / tax",
}


def layer_waterfall(est: CostEstimate, *, height: int = 360) -> go.Figure:
    """Layers 1-9 as floating steps; the cumulative boundaries as subtotal bars (final total in gold).

    Built from plain bars (not ``go.Waterfall``) so subtotals can stay neutral while only the final
    boundary carries the gold emphasis.  One axis, one currency.
    """
    keys = {b.key for b in est.boundaries}
    xs: list[str] = []
    base: list[float] = []
    h: list[float] = []
    colours: list[str] = []
    hover: list[str] = []
    run = 0.0
    final_key = "total_development_cost" if "total_development_cost" in keys else "contract_sum"
    for layer in CostLayer:
        v = float(est.layer_totals.get(layer.value, 0.0))
        if layer == CostLayer.LAND_FINANCE_TAX_SALES and v == 0.0:
            continue
        xs.append(_LAYER_SHORT[layer])
        base.append(run if v >= 0 else run + v)
        h.append(abs(v))
        colours.append(SINGLE_SERIES if v >= 0 else SERIES[1])
        hover.append(f"{esc(COST_LAYER_NAMES[layer])}<br>{money(v, est.currency)}")
        run += v
        tot = _TOTAL_AFTER.get(layer)
        if tot and tot[0] in keys:
            amt = est.boundary(tot[0]).amount
            xs.append(tot[1])
            base.append(0.0)
            h.append(amt)
            colours.append(GOLD if tot[0] == final_key else "#6B665C")
            hover.append(f"{esc(est.boundary(tot[0]).name)}<br>{money(amt, est.currency)}")
            run = amt
    if "total_development_cost" in keys:
        amt = est.boundary("total_development_cost").amount
        xs.append("Σ Development cost")
        base.append(0.0)
        h.append(amt)
        colours.append(GOLD)
        hover.append(f"Total development cost<br>{money(amt, est.currency)}")
    fig = go.Figure(go.Bar(
        x=xs, y=h, base=base, marker=dict(color=colours, line=dict(width=0)),
        text=[money_short(v, est.currency) for v in h], textposition="outside", cliponaxis=False,
        textfont=dict(size=9.5, color=IVORY_MUTED, family="IBM Plex Mono"), hovertext=hover, hoverinfo="text"))
    # thin connectors between consecutive bar tops
    for i in range(len(xs) - 1):
        top = base[i] + h[i]
        fig.add_shape(type="line", x0=i + 0.36, x1=i + 0.64, y0=top, y1=top, xref="x", yref="y",
                      line=dict(color="#4A4F57", width=1))
    fig.update_yaxes(title=dict(text=f"{est.currency}, net of VAT"), rangemode="tozero",
                     range=[0, max(b + v for b, v in zip(base, h)) * 1.1 if h else 1])
    fig.update_xaxes(tickangle=-35, tickfont=dict(size=9.5, family="Inter", color=IVORY_MUTED), showgrid=False)
    return _base(fig, height=height, showlegend=False, margin=dict(l=8, r=12, t=18, b=8), bargap=0.38)


def histogram_cdf(samples: Sequence[float], *, p10: float, p50: float, p90: float, deterministic: Optional[float],
                  currency: str, metric_label: str = "Construction cost incl. contingency",
                  height: int = 400) -> go.Figure:
    x = np.asarray([v for v in samples if v is not None and math.isfinite(v)], dtype=float)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.6, 0.4], vertical_spacing=0.05)
    fig.add_trace(go.Histogram(x=x, nbinsx=min(40, max(10, int(len(x) ** 0.5) * 2)), name="samples",
                               marker=dict(color=SINGLE_SERIES, line=dict(color=GRAPHITE_SURFACE, width=1)),
                               hovertemplate="%{x}<br>%{y} samples<extra></extra>", showlegend=False), row=1, col=1)
    xs = np.sort(x)
    cdf = np.arange(1, len(xs) + 1) / max(1, len(xs))
    fig.add_trace(go.Scatter(x=xs, y=cdf, mode="lines", line=dict(color=IVORY_MUTED, width=1.6), name="CDF",
                             showlegend=False, hovertemplate="%{x:,.0f}<br>P(cost ≤ x) = %{y:.0%}<extra></extra>"),
                  row=2, col=1)
    marks = [("P10", p10, IVORY_MUTED, "dash"), ("P50", p50, GOLD, "solid"), ("P90", p90, IVORY_MUTED, "dash")]
    for lab, v, col, dash in marks:
        fig.add_vline(x=v, line=dict(color=col, width=1.4, dash=dash), row="all", col=1)
        fig.add_annotation(x=v, y=1.0, yref="y domain", xref="x", text=f"{lab} {money_short(v, currency)}",
                           showarrow=False, yanchor="bottom", font=dict(size=10, color=col, family="IBM Plex Mono"),
                           row=1, col=1)
    if deterministic is not None and math.isfinite(deterministic):
        fig.add_vline(x=deterministic, line=dict(color=SERIES[1], width=1.4, dash="dot"), row="all", col=1)
        fig.add_annotation(x=deterministic, y=0.02, yref="y2 domain", xref="x2", text="deterministic estimate",
                           showarrow=False, xanchor="left", yanchor="bottom", font=dict(size=9.5, color="#D9A07E"),
                           row=2, col=1)
    fig.update_yaxes(title=dict(text="samples"), row=1, col=1)
    fig.update_yaxes(title=dict(text="cumulative"), tickformat=".0%", range=[0, 1.02], row=2, col=1)
    fig.update_xaxes(title=dict(text=f"{esc(metric_label)} ({currency})"), row=2, col=1)
    return _base(fig, height=height, showlegend=False, margin=dict(l=8, r=12, t=30, b=8), bargap=0.06)


def tornado(items: Sequence[SensitivityItem], *, top: int = 12, height: int = 380) -> go.Figure:
    rows = sorted(items, key=lambda s: abs(s.spearman_rho), reverse=True)[:top][::-1]
    names = [esc(s.input_name)[:46] for s in rows]
    fig = go.Figure(go.Bar(
        x=[s.spearman_rho for s in rows], y=names, orientation="h",
        marker=dict(color=[DIVERGING[1] if s.spearman_rho >= 0 else DIVERGING[0] for s in rows], line=dict(width=0)),
        text=[f"{s.variance_share:.0%}" for s in rows], textposition="outside", cliponaxis=False,
        textfont=dict(size=9.5, color=IVORY_MUTED),
        customdata=[[esc(s.group), esc(s.resolving_action)] for s in rows],
        hovertemplate="<b>%{y}</b><br>Spearman ρ %{x:.2f}<br>variance share %{text}<br>group %{customdata[0]}"
                      "<br>resolve: %{customdata[1]}<extra></extra>"))
    fig.add_vline(x=0, line=dict(color="#4A4F57", width=1))
    fig.update_xaxes(range=[-1.05, 1.05], title=dict(text="Spearman rank correlation with cost (label: variance share)"))
    fig.update_yaxes(tickfont=dict(size=9.5, family="Inter"))
    return _base(fig, height=height, showlegend=False, margin=dict(l=8, r=40, t=18, b=8))


# =============================================================================
# Repeat build
# =============================================================================
def repeat_chart(results: dict[str, RepeatBuildResult], *, height: int = 380) -> go.Figure:
    """Average C(n)/n and incremental C(n+1) - C(n) per boundary (one panel per boundary, own y-axis)."""
    titles = {"factory_gate": "Factory-gate boundary", "installed": "Installed boundary",
              "development": "Development boundary"}
    keys = [k for k in ("factory_gate", "installed", "development") if k in results]
    fig = make_subplots(rows=1, cols=len(keys), subplot_titles=[titles[k] for k in keys], horizontal_spacing=0.08)
    for c, k in enumerate(keys, start=1):
        r = results[k]
        n = [row.n for row in r.rows]
        avg = [row.average_cost for row in r.rows]
        inc = [row.incremental_cost for row in r.rows]
        marks = set(r.comparison_ns)
        for label, ys, col, width in (("Average cost C(n)/n", avg, SERIES[0], 2.2),
                                      ("Incremental cost C(n+1) − C(n)", inc, SERIES[1], 1.3)):
            fig.add_trace(go.Scatter(x=n, y=ys, mode="lines", name=label, legendgroup=label, showlegend=c == 1,
                                     line=dict(color=col, width=width),
                                     hovertemplate=f"n=%{{x}}<br>{label}: %{{y:,.0f}} {r.currency}<extra></extra>"),
                          row=1, col=c)
            mx = [x for x in n if x in marks]
            my = [ys[x - 1] for x in mx]
            fig.add_trace(go.Scatter(x=mx, y=my, mode="markers", showlegend=False, legendgroup=label,
                                     marker=dict(size=8, color=col, line=dict(color=GRAPHITE_SURFACE, width=2)),
                                     hovertemplate=f"n=%{{x}}<br>{label}: %{{y:,.0f}} {r.currency}<extra></extra>"),
                          row=1, col=c)
        if all(abs(v) < 1e-9 for v in avg + inc):
            fig.add_annotation(text="no costs inside this boundary<br>(e.g. no factory in a site-built route)",
                               xref=f"x{c if c > 1 else ''} domain", yref=f"y{c if c > 1 else ''} domain", x=0.5,
                               y=0.55, showarrow=False, font=dict(size=10.5, color=INK_MUTED))
        fig.update_xaxes(title=dict(text="houses built (n)"), row=1, col=c, tickvals=sorted(marks))
        fig.update_yaxes(title=dict(text=f"{r.currency} per house") if c == 1 else None, row=1, col=c,
                         rangemode="tozero")
    for a in fig.layout.annotations:
        if a.text in titles.values():
            a.font = dict(size=11, color=IVORY_MUTED)
    return _base(fig, height=height, margin=dict(l=8, r=12, t=70, b=8),
                 legend=dict(orientation="h", y=1.16, yanchor="bottom", x=0.0))


# =============================================================================
# Programme, carbon, heat loss
# =============================================================================
def gantt(prog: ProgrammeResult, *, height: Optional[int] = None) -> go.Figure:
    tasks = sorted(prog.tasks, key=lambda t: (t.earliest_start, t.earliest_finish))
    names = [esc(t.name)[:52] for t in tasks]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=names, x=[max(t.duration_days, 0.15) for t in tasks], base=[t.earliest_start for t in tasks],
        orientation="h", marker=dict(color=[GOLD if t.critical else SINGLE_SERIES for t in tasks], line=dict(width=0)),
        customdata=[[esc(t.trade), t.labour_hours, t.crew_size, t.total_float, "critical" if t.critical else "float"]
                    for t in tasks],
        hovertemplate="<b>%{y}</b><br>start day %{base:.1f} · duration %{x:.1f} d<br>trade %{customdata[0]} · "
                      "%{customdata[1]:.0f} labour h · crew %{customdata[2]:.0f}<br>total float %{customdata[3]:.1f} d "
                      "(%{customdata[4]})<extra></extra>", name="tasks", showlegend=False))
    fx, fy = [], []
    for t, nm in zip(tasks, names):
        if t.total_float > 0.05:
            fx += [t.earliest_finish, t.latest_finish, None]
            fy += [nm, nm, None]
    if fx:
        fig.add_trace(go.Scatter(x=fx, y=fy, mode="lines", line=dict(color=INK_MUTED, width=1.2),
                                 name="total float", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(symbol="square", size=10, color=GOLD),
                             name="critical path"))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers",
                             marker=dict(symbol="square", size=10, color=SINGLE_SERIES), name="non-critical task"))
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=10, family="Inter"))
    fig.update_xaxes(title=dict(text=f"working days ({prog.working_days_per_week:g}-day weeks)"), rangemode="tozero")
    return _base(fig, height=height or max(260, 26 * len(tasks) + 80), barmode="overlay",
                 margin=dict(l=8, r=12, t=30, b=8))


def hbar(labels: Sequence[str], values: Sequence[float], *, unit: str, height: Optional[int] = None,
         text_fmt: str = "{:,.0f}", colour: str = SINGLE_SERIES) -> go.Figure:
    pairs = sorted(zip(labels, values), key=lambda p: p[1])
    fig = go.Figure(go.Bar(
        y=[esc(p[0]) for p in pairs], x=[p[1] for p in pairs], orientation="h",
        marker=dict(color=colour, line=dict(width=0)), text=[text_fmt.format(p[1]) for p in pairs],
        textposition="outside", cliponaxis=False, textfont=dict(size=9.5, color=IVORY_MUTED),
        hovertemplate=f"%{{y}}<br>%{{x:,.1f}} {esc(unit)}<extra></extra>"))
    fig.update_xaxes(title=dict(text=esc(unit)), rangemode="tozero")
    fig.update_yaxes(tickfont=dict(size=10, family="Inter"))
    return _base(fig, height=height or max(220, 30 * len(pairs) + 70), showlegend=False,
                 margin=dict(l=8, r=48, t=14, b=8), bargap=0.45)


def carbon_chart(carbon: CarbonResult) -> go.Figure:
    labels = list(carbon.by_element)
    vals = [v / 1000.0 for v in carbon.by_element.values()]
    return hbar(labels, vals, unit="tCO2e (A1-A3 + A5 waste, illustrative factors)", text_fmt="{:,.2f}")


def heat_loss_chart(heat: HeatLossResult) -> go.Figure:
    labels = [e.element.replace("_", " ") for e in heat.elements] + ["thermal bridging (y-value)", "ventilation"]
    vals = [e.ua_w_k for e in heat.elements] + [heat.thermal_bridging_w_k, heat.ventilation_w_k]
    return hbar(labels, vals, unit="W/K (simplified steady-state)", text_fmt="{:,.1f}")


# =============================================================================
# Scenario small multiples
# =============================================================================
SCENARIO_METRICS: tuple[tuple[str, str, float, str], ...] = (
    ("Construction cost", "construction_cost", 1.0, "CUR"),
    ("Cost per m² GIA", "cost_per_m2_gia", 1.0, "CUR/m²"),
    ("GIA", "gia_m2", 1.0, "m²"),
    ("External wall thickness", "external_wall_thickness_m", 1000.0, "mm"),
    ("Embodied carbon", "embodied_carbon_kgco2e", 0.001, "tCO2e"),
    ("Heat-loss coefficient", "heat_loss_coefficient_w_k", 1.0, "W/K"),
    ("Programme", "programme_weeks", 1.0, "weeks"),
    ("Labour", "labour_hours", 1.0, "h"),
)


def scenario_interval_traces(outs: Sequence[ScenarioOutcome], ids: Sequence[str], currency: str) -> list[go.Scatter]:
    """P10-P90 interval segments and P50 markers of the simulated construction cost, one row per scenario.

    Drawn as their own traces (not as error bars around the deterministic bar): the deterministic estimate
    uses modal values and may lie below P10, which error bars cannot show (negative half-widths).
    """
    rows = [(i, o) for i, o in zip(ids, outs) if o.cost_p10 is not None and o.cost_p90 is not None]
    if not rows:
        return []
    xs: list[Optional[float]] = []
    ys: list[Optional[str]] = []
    for i, o in rows:
        lo, hi = sorted((float(o.cost_p10), float(o.cost_p90)))
        xs += [lo, hi, None]
        ys += [i, i, None]
    seg = go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=IVORY_MUTED, width=1.6), showlegend=False,
                     hoverinfo="skip", name="P10-P90")
    p50 = [(i, o) for i, o in rows if o.cost_p50 is not None]
    mk = go.Scatter(
        x=[float(o.cost_p50) for _, o in p50], y=[i for i, _ in p50], mode="markers", showlegend=False,
        name="P50", marker=dict(symbol="diamond", size=7, color=GOLD, line=dict(width=0)),
        customdata=[[float(o.cost_p10), float(o.cost_p90), float(o.construction_cost)] for _, o in p50],
        hovertemplate=(f"P50 %{{x:,.0f}} {esc(currency)}<br>P10-P90 %{{customdata[0]:,.0f}} - "
                       f"%{{customdata[1]:,.0f}}<br>deterministic %{{customdata[2]:,.0f}}<extra></extra>"))
    return [seg, mk]


def scenario_multiples(outcomes: Sequence[ScenarioOutcome], currency: str, *, height: int = 430) -> go.Figure:
    titles = [f"{t} ({u.replace('CUR', currency)})" for t, _, _, u in SCENARIO_METRICS]
    fig = make_subplots(rows=2, cols=4, subplot_titles=titles, shared_yaxes=True, horizontal_spacing=0.035,
                        vertical_spacing=0.2)
    ids = [esc(o.scenario_id) for o in outcomes][::-1]
    outs = list(outcomes)[::-1]
    for idx, (_t, attr, k, unit) in enumerate(SCENARIO_METRICS):
        r, c = idx // 4 + 1, idx % 4 + 1
        vals = [float(getattr(o, attr)) * k for o in outs]
        fmt = "{:,.0f}" if max(abs(v) for v in vals or [0]) >= 100 else "{:,.1f}"
        fig.add_trace(go.Bar(
            y=ids, x=vals, orientation="h", marker=dict(color=SINGLE_SERIES, line=dict(width=0)),
            text=[fmt.format(v) for v in vals], textposition="inside", insidetextanchor="end",
            textfont=dict(size=9.5, color=IVORY, family="IBM Plex Mono"), showlegend=False,
            customdata=[esc(o.name) for o in outs],
            hovertemplate="%{customdata}<br>deterministic %{x:,.2f} " + esc(unit.replace("CUR", currency))
                          + "<extra></extra>"),
            row=r, col=c)
        if attr == "construction_cost":
            for tr in scenario_interval_traces(outs, ids, currency):
                fig.add_trace(tr, row=r, col=c)
        fig.update_xaxes(rangemode="tozero", showticklabels=False, showgrid=False, row=r, col=c)
    for a in fig.layout.annotations:
        a.font = dict(size=10.5, color=IVORY_MUTED)
    fig.update_yaxes(tickfont=dict(size=10.5, family="IBM Plex Mono"))
    return _base(fig, height=height, showlegend=False, margin=dict(l=8, r=8, t=34, b=8), bargap=0.5)


__all__ = ["SCENARIO_METRICS", "carbon_chart", "feature_hover", "gantt", "hbar", "heat_loss_chart",
           "histogram_cdf", "layer_waterfall", "overlay_figure", "repeat_chart", "resolve_refs",
           "scenario_interval_traces", "scenario_multiples", "tornado", "twin_figure"]
