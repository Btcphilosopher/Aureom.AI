"""Streamlit user interface for Housebuilder.OS Vision (``streamlit run app.py``).

Five views - Images, Twin, Quantities, Costs, Scenarios - plus a sidebar for the project
(fictional demo, new project, save / load), settings and downloads.  Layout code lives in
:mod:`.views`; session state and engine orchestration (with explicit-key caching) in
:mod:`.state`; Plotly figures in :mod:`.charts`; the Aureom.AI visual language in :mod:`.theme`.

The UI adds no engineering logic: every number comes from the engine with its provenance basis,
and the UI never upgrades a basis, hides a range or prices a missing item as zero.  Importing
this package does not import Streamlit; :func:`main` does.
"""

from __future__ import annotations

__all__ = ["main"]


def main() -> None:
    """Run the Streamlit app (call from a Streamlit script, e.g. the project-root ``app.py``)."""
    from .app import main as _main

    _main()
