"""Streamlit page: sidebar, header with live KPIs, and five lazily rendered tabs.

Tabs use state tracking (``on_change="rerun"``), so only the open tab runs - heavy views do no
work while hidden.  The deterministic evaluation (quantities -> programme / logistics / carbon /
heat loss -> cost) is computed once per run through the cache keyed by ``twin_hash`` + rate book
+ parameters, so every edit immediately updates the header KPIs and all views.
"""

from __future__ import annotations

import logging

import streamlit as st

from . import state as S
from .components import guard, html, show_flash
from .theme import css_block
from .views import costs, images, quantities, scenarios, sidebar, twin

TABS = ("Images", "Twin", "Quantities", "Costs", "Scenarios")
TAB_KEY = "main_tab"
_RENDER = {"Images": images.render, "Twin": twin.render, "Quantities": quantities.render, "Costs": costs.render,
           "Scenarios": scenarios.render}


def main() -> None:
    st.set_page_config(page_title="Housebuilder.OS Vision · Aureom.AI", page_icon=":material/home_work:",
                       layout="wide", initial_sidebar_state="expanded")
    logging.getLogger("housebuilder_vision").setLevel(logging.INFO)
    html(css_block())
    ws = S.get_workspace()
    sidebar.render_sidebar(ws)
    ev = None
    if ws.project is not None and ws.project.twin is not None:
        with guard("Quantities and cost recalculation"):
            ev = S.evaluate(ws)
    sidebar.render_header(ws, ev)
    show_flash(ws)
    tabs = st.tabs(list(TABS), key=TAB_KEY, on_change="rerun")
    for name, tab in zip(TABS, tabs):
        if tab.open is False:
            continue
        with tab:
            with guard(f"{name} view"):
                _RENDER[name](ws, ev)
    show_flash(ws)


__all__ = ["TABS", "TAB_KEY", "main"]
