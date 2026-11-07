"""Small Streamlit building blocks shared by the views (HTML snippets, guarded sections, editors).

* :func:`guard` turns any exception inside a section into an ``st.error`` naming the section and
  the error - never a raw traceback (Streamlit's control-flow exceptions derive from
  ``BaseException`` and pass through untouched).
* :func:`html` renders trusted template HTML; every interpolated value is escaped by the
  callers (``theme.esc``) because labels, filenames and notes may come from untrusted input.
* :func:`tv_number` is the standard numeric editor: a ``number_input`` in display units with the
  value's basis badge and range underneath, applying the change through a callback (immediate
  recalculation, errors reported as flash messages).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional

import streamlit as st

from ..core.provenance import TrackedValue
from . import fmt
from .state import Workspace, get_workspace
from .theme import badge, esc

log = logging.getLogger("housebuilder_vision.ui")


def html(markup: str) -> None:
    st.html(markup)


@contextmanager
def guard(context: str) -> Iterator[None]:
    """Show failures of a UI section as a contextual ``st.error`` (no traceback in the page)."""
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - the UI must stay usable; details go to the server log
        log.exception("UI section '%s' failed", context)
        msg = str(exc).strip().splitlines()[0][:400] if str(exc).strip() else ""
        st.error(f"{context} could not be shown - {type(exc).__name__}{': ' + msg if msg else ''}. "
                 "The rest of the page still works; adjust the inputs above and try again.")


def show_flash(ws: Workspace) -> None:
    """Render and clear messages queued by callbacks."""
    msgs, ws.flash = ws.flash, []
    for level, text in msgs:
        if level == "error":
            st.error(text)
        elif level == "warning":
            st.warning(text)
        else:
            st.toast(text)


def value_meta(tv: Optional[TrackedValue], system: str = "metric", *, nd: int = 2, extra: str = "") -> str:
    if tv is None:
        return f'<div class="hbv-val">{badge("unknown")}<span class="hbv-range">not set</span></div>'
    note = (tv.note or tv.source or "").strip()
    rng = fmt.tv_range(tv, system, nd)
    return (f'<div class="hbv-val" title="{esc(note)[:400]}">{badge(tv.basis)}'
            f'<span class="hbv-range">{esc(rng)}</span>{extra}</div>')


def _apply_from_widget(key: str, apply: Callable[[Any], Optional[str]], to_si: Callable[[Any], Any]) -> None:
    ws = get_workspace()
    raw = st.session_state.get(key)
    if raw is None:
        return
    try:
        err = apply(to_si(raw))
    except Exception as exc:  # noqa: BLE001 - reported to the user
        err = f"{type(exc).__name__}: {exc}"
    if err:
        ws.say("error", err)


def tv_number(label: str, tv: Optional[TrackedValue], *, key: str, apply: Callable[[float], Optional[str]],
              si_unit: str = "m", system: str = "metric", nd: int = 2, integer: bool = False,
              min_si: Optional[float] = None, max_si: Optional[float] = None, step: Optional[float] = None,
              help: Optional[str] = None, disabled: bool = False) -> None:
    """Number input in display units + basis badge/range; ``apply`` receives the SI value."""
    du = fmt.disp_unit(si_unit, system) if si_unit else si_unit
    cur = None if tv is None or tv.value is None else fmt.disp(tv.value, si_unit, system)[0] if si_unit else tv.value
    lo = None if min_si is None else (fmt.disp(min_si, si_unit, system)[0] if si_unit else min_si)
    hi = None if max_si is None else (fmt.disp(max_si, si_unit, system)[0] if si_unit else max_si)
    unit_txt = fmt.unit_label(du)
    lab = f"{label} ({unit_txt})" if unit_txt else label

    def to_si(v: Any) -> Any:
        if integer:
            return int(round(float(v)))
        return fmt.to_si(float(v), du, si_unit) if si_unit else float(v)

    if integer:
        st.number_input(lab, value=None if cur is None else int(round(cur)), min_value=None if lo is None else int(lo),
                        max_value=None if hi is None else int(hi), step=1, key=key, help=help, disabled=disabled,
                        on_change=_apply_from_widget, args=(key, apply, to_si))
    else:
        st.number_input(lab, value=None if cur is None else round(float(cur), 4),
                        min_value=None if lo is None else float(lo), max_value=None if hi is None else float(hi),
                        step=step if step is not None else (0.05 if du in ("m", "ft") else 0.5),
                        format=f"%.{nd}f", key=key, help=help, disabled=disabled,
                        on_change=_apply_from_widget, args=(key, apply, to_si))
    html(value_meta(tv, system, nd=nd))


def cards(items: list[str]) -> None:
    html(f'<div class="hbv-cards">{"".join(items)}</div>')


def section_title(text: str, *, sub: str = "") -> None:
    sub_html = f' <span class="hbv-small">{esc(sub)}</span>' if sub else ""
    html(f'<h3 style="margin:.6rem 0 .25rem 0">{esc(text)}{sub_html}</h3>')


__all__ = ["cards", "guard", "html", "section_title", "show_flash", "tv_number", "value_meta"]
