"""Aureom.AI visual language for the Streamlit UI: colours, typography, CSS and Plotly template.

Palette
-------
* Graphite surfaces ``#15171A`` (page) and ``#202328`` (cards, charts), hairlines ``#30343A``.
* Ivory ``#F3EEE4`` for text and light accents; muted ivory for secondary text.
* Restrained gold ``#B39A62`` for accents and emphasis only (active tab, primary buttons,
  P50 / critical-path / highlighted marks) - never as a data series colour.

Provenance (basis) colours
--------------------------
One colour per :class:`~housebuilder_vision.core.provenance.Basis`, used identically in every
view (badges, image overlay, 3D evidence mode, tables).  The five hues were chosen with the
dataviz palette validator against both graphite surfaces (OKLCH lightness band, chroma floor,
all-pairs CVD separation >= 9.3, normal-vision separation >= 17.3, contrast >= 3:1).  Colour is
never the only carrier of meaning: every badge prints its label, overlays add a line-dash
code per basis and every chart has a legend or a table view.

Series colours (``SERIES``) are a validated three-slot categorical set for charts that need
identity (e.g. average vs incremental cost); single-series charts use slot 1.

Typography: Inter for UI text, IBM Plex Mono for numbers (Google Fonts, imported in the injected
CSS and in ``.streamlit/config.toml``; the system sans/mono fallbacks are used offline).
"""

from __future__ import annotations

import html
from typing import Iterable, Optional

from ..core.provenance import BASIS_LABEL, Basis

# ----------------------------------------------------------------------------- core palette
GRAPHITE_BG = "#15171A"
GRAPHITE_SURFACE = "#202328"
GRAPHITE_RAISED = "#272B31"
HAIRLINE = "#30343A"
GRID = "#2A2E34"
AXIS = "#4A4F57"
IVORY = "#F3EEE4"
IVORY_MUTED = "#BDB7AB"
INK_MUTED = "#8C8F96"
GOLD = "#B39A62"
GOLD_BRIGHT = "#CDB57E"
NEUTRAL_MARK = "#59606A"

#: Validated categorical series (steel blue, terracotta, sage) - slot order is fixed.
SERIES: tuple[str, ...] = ("#4576B4", "#AB5D2B", "#4AA076")
SINGLE_SERIES = SERIES[0]
#: Diverging pair for signed quantities (negative, positive).
DIVERGING = (SERIES[0], SERIES[1])

FONT_SANS = "Inter, 'Helvetica Neue', Arial, sans-serif"
FONT_MONO = "'IBM Plex Mono', 'SFMono-Regular', Menlo, Consolas, monospace"
GOOGLE_FONTS_URL = ("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700"
                    "&family=IBM+Plex+Mono:wght@400;500&display=swap")

# ----------------------------------------------------------------------------- provenance
BASIS_COLOURS: dict[Basis, str] = {
    Basis.OBSERVED: "#009FCF",
    Basis.INFERRED: "#7260BD",
    Basis.USER_CONFIRMED: "#729F3A",
    Basis.ASSUMED: "#AD5600",
    Basis.UNKNOWN: "#CD689B",
}
#: Strongest evidence first (legend order).
BASIS_ORDER: tuple[Basis, ...] = (Basis.USER_CONFIRMED, Basis.OBSERVED, Basis.INFERRED, Basis.ASSUMED,
                                  Basis.UNKNOWN)
#: Secondary (non-colour) encoding for outlines in overlays.
BASIS_DASH: dict[Basis, str] = {
    Basis.USER_CONFIRMED: "solid",
    Basis.OBSERVED: "solid",
    Basis.INFERRED: "dash",
    Basis.ASSUMED: "dot",
    Basis.UNKNOWN: "dashdot",
}
BASIS_MEANING: dict[Basis, str] = {
    Basis.OBSERVED: "measured directly from image evidence",
    Basis.INFERRED: "derived by a rule or model from observations",
    Basis.USER_CONFIRMED: "entered or confirmed by a person",
    Basis.ASSUMED: "a labelled default you may continue with",
    Basis.UNKNOWN: "not recoverable from the evidence",
}


def as_basis(value) -> Basis:
    """Coerce a basis value / string (``"assumed"``) to :class:`Basis` (UNKNOWN when unrecognised)."""
    if isinstance(value, Basis):
        return value
    try:
        return Basis(str(value))
    except ValueError:
        return Basis.UNKNOWN


def basis_colour(value) -> str:
    return BASIS_COLOURS[as_basis(value)]


def basis_label(value) -> str:
    return BASIS_LABEL[as_basis(value)]


def hex_to_rgba(hexv: str, alpha: float) -> str:
    h = hexv.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha:.3f})"


# ----------------------------------------------------------------------------- HTML snippets
def esc(text) -> str:
    """HTML-escape untrusted text (feature labels, filenames, model output, notes)."""
    return html.escape("" if text is None else str(text), quote=True)


def badge(value, *, label: Optional[str] = None, title: Optional[str] = None) -> str:
    """Inline basis badge: coloured key + text label (colour is never the only cue)."""
    b = as_basis(value)
    text = label if label is not None else BASIS_LABEL[b]
    tip = title if title is not None else f"{BASIS_LABEL[b]}: {BASIS_MEANING[b]}"
    c = BASIS_COLOURS[b]
    return (f'<span class="hbv-badge" style="--c:{c};--cb:{hex_to_rgba(c, 0.16)}" title="{esc(tip)}">'
            f'{esc(text)}</span>')


def tag(text: str, *, tone: str = "neutral", title: str = "") -> str:
    """Small neutral / gold / warn tag (not a basis)."""
    return f'<span class="hbv-tag hbv-tag-{esc(tone)}" title="{esc(title)}">{esc(text)}</span>'


def basis_legend_html(bases: Iterable[Basis] = BASIS_ORDER) -> str:
    items = "".join(f'<span class="hbv-legend-item">{badge(b)}<span class="hbv-legend-text">'
                    f'{esc(BASIS_MEANING[b])}</span></span>' for b in bases)
    return f'<div class="hbv-legend">{items}</div>'


def callout(body_html: str, *, tone: str = "info", title: Optional[str] = None) -> str:
    """Bordered note.  ``tone``: info (gold), warn (assumption amber), danger (concept / caveat), neutral."""
    head = f'<div class="hbv-callout-title">{esc(title)}</div>' if title else ""
    return f'<div class="hbv-callout hbv-callout-{esc(tone)}">{head}<div>{body_html}</div></div>'


def card(label: str, value: str, *, sub: str = "", detail_html: str = "", accent: bool = False) -> str:
    cls = "hbv-card hbv-card-accent" if accent else "hbv-card"
    sub_html = f'<div class="hbv-card-sub">{esc(sub)}</div>' if sub else ""
    return (f'<div class="{cls}"><div class="hbv-card-k">{esc(label)}</div>'
            f'<div class="hbv-card-v">{esc(value)}</div>{sub_html}{detail_html}</div>')


# ----------------------------------------------------------------------------- CSS
CSS = f"""
@import url('{GOOGLE_FONTS_URL}');
:root {{
  --hbv-bg: {GRAPHITE_BG}; --hbv-surface: {GRAPHITE_SURFACE}; --hbv-raised: {GRAPHITE_RAISED};
  --hbv-line: {HAIRLINE}; --hbv-ivory: {IVORY}; --hbv-ivory-muted: {IVORY_MUTED}; --hbv-muted: {INK_MUTED};
  --hbv-gold: {GOLD}; --hbv-sans: {FONT_SANS}; --hbv-mono: {FONT_MONO};
}}
html, body, .stApp, [data-testid="stSidebar"], .stMarkdown, button, input, textarea, select {{
  font-family: var(--hbv-sans);
}}
.stApp {{ background: var(--hbv-bg); }}
.block-container, [data-testid="stMainBlockContainer"] {{
  padding-top: 0.9rem !important; padding-bottom: 2.5rem !important; max-width: 1560px;
}}
[data-testid="stHeader"] {{ background: transparent; height: 2.2rem; }}
h1, h2, h3, h4 {{ font-family: var(--hbv-sans); letter-spacing: -0.01em; color: var(--hbv-ivory); }}
h1 {{ font-size: 1.45rem !important; font-weight: 600 !important; }}
h2 {{ font-size: 1.15rem !important; font-weight: 600 !important; }}
h3 {{ font-size: 1.0rem !important; font-weight: 600 !important; margin-top: .4rem !important; }}
h4 {{ font-size: .9rem !important; font-weight: 600 !important; }}
p, li, label, .stMarkdown {{ font-size: 0.86rem; }}
[data-testid="stCaptionContainer"], .stCaption {{ color: var(--hbv-muted) !important; font-size: .76rem !important; }}
code, pre, .hbv-num, [data-testid="stMetricValue"], [data-testid="stMetricDelta"] {{
  font-family: var(--hbv-mono) !important;
}}
[data-testid="stMetricValue"] {{ font-size: 1.25rem !important; font-weight: 500 !important; }}
[data-testid="stMetricLabel"] p {{ font-size: .7rem !important; letter-spacing: .08em; text-transform: uppercase;
  color: var(--hbv-muted) !important; }}
/* tabs: thin gold indicator; main tabs uppercase */
[role="tablist"] {{ border-bottom: 1px solid var(--hbv-line); }}
[data-testid="stTab"] p {{ font-size: .8rem !important; font-weight: 500; color: var(--hbv-ivory-muted); }}
[data-testid="stTab"][aria-selected="true"] p {{ color: var(--hbv-ivory); }}
.react-aria-SelectionIndicator {{ background-color: var(--hbv-gold) !important; height: 2px !important; }}
.st-key-main_tab > div > [role="tablist"] [data-testid="stTab"] p,
.st-key-main_tab [role="tablist"]:first-of-type [data-testid="stTab"] p {{ font-size: .72rem !important;
  letter-spacing: .14em; text-transform: uppercase; font-weight: 600; }}
/* sidebar */
[data-testid="stSidebar"] {{ background: #1A1C20; border-right: 1px solid var(--hbv-line); }}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ padding-top: .4rem; }}
[data-testid="stSidebar"] h3 {{ font-size: .72rem !important; letter-spacing: .14em; text-transform: uppercase;
  color: var(--hbv-gold) !important; margin: .9rem 0 .2rem 0 !important; }}
/* buttons */
.stButton button, .stDownloadButton button, .stFormSubmitButton button {{ border-radius: 3px; font-size: .8rem;
  padding: .25rem .8rem; min-height: 2rem; }}
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] {{ color: #15171A; }}
[data-testid="stExpander"] details {{ border: 1px solid var(--hbv-line) !important; border-radius: 4px;
  background: transparent; }}
[data-testid="stExpander"] summary p {{ font-size: .8rem; font-weight: 500; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-color: var(--hbv-line) !important; }}
/* brand bar */
.hbv-brand {{ display:flex; align-items:baseline; gap:.75rem; margin:.1rem 0 .1rem 0; }}
.hbv-brand-mark {{ font-weight:700; letter-spacing:.32em; font-size:.68rem; color:var(--hbv-gold); }}
.hbv-brand-name {{ font-weight:600; font-size:1.18rem; color:var(--hbv-ivory); letter-spacing:-.01em; }}
.hbv-brand-sub {{ font-size:.76rem; color:var(--hbv-muted); }}
.hbv-rule {{ height:1px; background:var(--hbv-line); margin:.45rem 0 .55rem 0; }}
/* badges and tags */
.hbv-badge {{ display:inline-flex; align-items:center; gap:.35em; padding:0 .5em 0 .45em; border-radius:2px;
  border:1px solid var(--c); background:var(--cb); color:var(--hbv-ivory); font:600 .64rem/1.55 var(--hbv-sans);
  letter-spacing:.06em; text-transform:uppercase; white-space:nowrap; vertical-align:middle; }}
.hbv-badge::before {{ content:""; width:.5em; height:.5em; background:var(--c); border-radius:1px; }}
.hbv-tag {{ display:inline-block; padding:0 .45em; border-radius:2px; font:500 .66rem/1.6 var(--hbv-sans);
  letter-spacing:.05em; border:1px solid var(--hbv-line); color:var(--hbv-ivory-muted); white-space:nowrap; }}
.hbv-tag-gold {{ border-color: var(--hbv-gold); color: var(--hbv-gold); }}
.hbv-tag-warn {{ border-color: {BASIS_COLOURS[Basis.ASSUMED]}; color: #E9B489; }}
.hbv-tag-danger {{ border-color: {BASIS_COLOURS[Basis.UNKNOWN]}; color: #E8A9C7; }}
.hbv-legend {{ display:flex; flex-wrap:wrap; gap:.35rem 1rem; margin:.15rem 0 .4rem 0; }}
.hbv-legend-item {{ display:inline-flex; align-items:center; gap:.4rem; }}
.hbv-legend-text {{ font-size:.72rem; color:var(--hbv-muted); }}
/* value rows (editors) */
.hbv-val {{ display:flex; flex-wrap:wrap; align-items:center; gap:.35rem; margin:-.35rem 0 .45rem 0; min-height:1.2rem; }}
.hbv-range {{ font:400 .7rem/1.4 var(--hbv-mono); color:var(--hbv-muted); }}
/* cards */
.hbv-cards {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(190px, 1fr)); gap:.6rem; margin:.2rem 0 .6rem 0; }}
.hbv-card {{ background:var(--hbv-surface); border:1px solid var(--hbv-line); border-radius:4px; padding:.6rem .75rem .65rem .75rem; }}
.hbv-card-accent {{ border-top:2px solid var(--hbv-gold); }}
.hbv-card-k {{ font:600 .64rem/1.3 var(--hbv-sans); letter-spacing:.1em; text-transform:uppercase; color:var(--hbv-muted); }}
.hbv-card-v {{ font:500 1.15rem/1.35 var(--hbv-mono); color:var(--hbv-ivory); margin-top:.2rem; }}
.hbv-card-sub {{ font:400 .72rem/1.35 var(--hbv-mono); color:var(--hbv-ivory-muted); }}
.hbv-card-def {{ font-size:.72rem; color:var(--hbv-ivory-muted); margin-top:.35rem; line-height:1.35; }}
.hbv-card-ex {{ font-size:.68rem; color:var(--hbv-muted); margin-top:.25rem; line-height:1.3; }}
/* KPI strip */
.hbv-kpis {{ display:flex; flex-wrap:wrap; gap:0; border:1px solid var(--hbv-line); border-radius:4px;
  background:var(--hbv-surface); margin:.1rem 0 .5rem 0; }}
.hbv-kpi {{ padding:.4rem .8rem; border-right:1px solid var(--hbv-line); flex:1 1 0; min-width:118px; }}
.hbv-kpi:last-child {{ border-right:none; }}
.hbv-kpi:nth-child(2) {{ flex:1.45 1 0; }}
.hbv-kpi-k {{ font:600 .6rem/1.3 var(--hbv-sans); letter-spacing:.11em; text-transform:uppercase; color:var(--hbv-muted); }}
.hbv-kpi-v {{ font:500 .98rem/1.4 var(--hbv-mono); color:var(--hbv-ivory); }}
.hbv-kpi-d {{ font:400 .66rem/1.2 var(--hbv-mono); color:var(--hbv-gold); }}
/* callouts */
.hbv-callout {{ border:1px solid var(--hbv-line); border-left:3px solid var(--hbv-gold); background:var(--hbv-surface);
  padding:.5rem .75rem; border-radius:3px; margin:.25rem 0 .6rem 0; font-size:.8rem; color:var(--hbv-ivory); line-height:1.45; }}
.hbv-callout-title {{ font:600 .66rem/1.4 var(--hbv-sans); letter-spacing:.11em; text-transform:uppercase; margin-bottom:.15rem; color:var(--hbv-gold); }}
.hbv-callout-warn {{ border-left-color:{BASIS_COLOURS[Basis.ASSUMED]}; }}
.hbv-callout-warn .hbv-callout-title {{ color:#E9B489; }}
.hbv-callout-danger {{ border-left-color:{BASIS_COLOURS[Basis.UNKNOWN]}; background:{hex_to_rgba(BASIS_COLOURS[Basis.UNKNOWN], 0.07)}; }}
.hbv-callout-danger .hbv-callout-title {{ color:#E8A9C7; }}
.hbv-callout-neutral {{ border-left-color:var(--hbv-line); }}
.hbv-callout-neutral .hbv-callout-title {{ color:var(--hbv-ivory-muted); }}
.hbv-callout ul {{ margin:.1rem 0 0 1rem; padding:0; }}
.hbv-callout li {{ font-size:.78rem; margin:.05rem 0; }}
/* hypothesis cards */
.hbv-hyp {{ font-size:.78rem; }}
.hbv-hyp table {{ width:100%; border-collapse:collapse; margin:.3rem 0; }}
.hbv-hyp td, .hbv-hyp th {{ border-bottom:1px solid var(--hbv-line); padding:.18rem .25rem; text-align:left; font-size:.74rem; }}
.hbv-hyp th {{ color:var(--hbv-muted); font-weight:600; letter-spacing:.05em; text-transform:uppercase; font-size:.62rem; }}
.hbv-hyp td.n {{ font-family:var(--hbv-mono); }}
.hbv-bar {{ height:4px; background:var(--hbv-line); border-radius:2px; margin:.2rem 0 .1rem 0; }}
.hbv-bar > div {{ height:4px; background:var(--hbv-gold); border-radius:2px; }}
.hbv-mono {{ font-family:var(--hbv-mono); }}
.hbv-ivs {{ display:flex; flex-direction:column; gap:.1rem; }}
.hbv-iv {{ display:grid; grid-template-columns:1.6rem 1fr; gap:.5rem; padding:.4rem 0; border-bottom:1px solid var(--hbv-line); }}
.hbv-iv-rank {{ font:600 .95rem/1.2 var(--hbv-mono); color:var(--hbv-gold); text-align:right; }}
.hbv-iv-act {{ font-size:.82rem; font-weight:500; color:var(--hbv-ivory); }}
.hbv-small {{ font-size:.74rem; color:var(--hbv-ivory-muted); }}
.hbv-formula {{ font:400 .74rem/1.45 var(--hbv-mono); background:var(--hbv-bg); border:1px solid var(--hbv-line);
  padding:.45rem .6rem; border-radius:3px; white-space:pre-wrap; word-break:break-word; color:var(--hbv-ivory); }}
"""


def css_block() -> str:
    return f"<style>{CSS}</style>"


# ----------------------------------------------------------------------------- Plotly template
TEMPLATE_NAME = "aureom"


def plotly_template():
    """Thin-line technical Plotly template on graphite (registered as ``"aureom"``)."""
    import plotly.graph_objects as go
    import plotly.io as pio

    if TEMPLATE_NAME in pio.templates:
        return pio.templates[TEMPLATE_NAME]
    axis = dict(gridcolor=GRID, gridwidth=1, linecolor=AXIS, linewidth=1, showline=True, zeroline=False,
                ticks="outside", tickcolor=AXIS, ticklen=3, tickwidth=1,
                tickfont=dict(family=FONT_MONO, size=10.5, color=IVORY_MUTED),
                title=dict(font=dict(family=FONT_SANS, size=11, color=INK_MUTED), standoff=8),
                automargin=True)
    tpl = go.layout.Template(layout=dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=GRAPHITE_SURFACE,
        font=dict(family=FONT_SANS, size=11.5, color=IVORY),
        colorway=list(SERIES),
        title=dict(font=dict(family=FONT_SANS, size=12.5, color=IVORY), x=0.0, xanchor="left", y=0.98),
        xaxis=axis, yaxis=axis,
        legend=dict(bgcolor="rgba(0,0,0,0)", borderwidth=0, font=dict(size=10.5, color=IVORY_MUTED),
                    orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0.0),
        hoverlabel=dict(bgcolor=GRAPHITE_RAISED, bordercolor=GOLD,
                        font=dict(family=FONT_MONO, size=11, color=IVORY), align="left"),
        margin=dict(l=8, r=12, t=34, b=8),
        bargap=0.28,
        hovermode="closest",
    ))
    tpl.data.bar = [go.Bar(marker=dict(line=dict(width=0)))]
    tpl.data.scatter = [go.Scatter(line=dict(width=2))]
    pio.templates[TEMPLATE_NAME] = tpl
    return tpl


__all__ = [
    "AXIS", "BASIS_COLOURS", "BASIS_DASH", "BASIS_MEANING", "BASIS_ORDER", "CSS", "DIVERGING", "FONT_MONO",
    "FONT_SANS", "GOLD", "GOLD_BRIGHT", "GOOGLE_FONTS_URL", "GRAPHITE_BG", "GRAPHITE_RAISED", "GRAPHITE_SURFACE",
    "GRID", "HAIRLINE", "INK_MUTED", "IVORY", "IVORY_MUTED", "NEUTRAL_MARK", "SERIES", "SINGLE_SERIES",
    "TEMPLATE_NAME", "as_basis", "badge", "basis_colour", "basis_label", "basis_legend_html", "callout", "card",
    "css_block", "esc", "hex_to_rgba", "plotly_template", "tag",
]
