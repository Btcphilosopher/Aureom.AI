"""The five views of the Streamlit UI (Images, Twin, Quantities, Costs, Scenarios) and the sidebar.

Each view module exposes ``render(ws, ev)`` taking the session :class:`~..state.Workspace` and the
current cached :class:`~..state.Evaluation` (or ``None`` when no twin exists yet).
"""

from . import costs, images, quantities, scenarios, sidebar, twin

__all__ = ["costs", "images", "quantities", "scenarios", "sidebar", "twin"]
