"""Bundled FICTIONAL demonstration: "Aureom Demo House, Plot 7".

* ``data/`` - synthetic front / left elevations, detection fixtures, a concept-render
  example and the fictional rate book (``fictional_rates_gbp_2026.csv``).
* :mod:`.make_demo_assets` - deterministic generator of the synthetic images and fixtures.
* :mod:`.build_demo` - :func:`build_demo_project` / :func:`build_uncalibrated_demo_project`.
* :mod:`.run_demo` - ``python -m housebuilder_vision.demo.run_demo`` (full pipeline, report, exports).

Everything here is fictional: the house, the survey dimension, prices and production
economics.  Names below are imported lazily so ``import housebuilder_vision.demo`` stays light.
"""

from __future__ import annotations

from typing import Any

_LAZY = {
    "build_demo_project": "build_demo",
    "build_uncalibrated_demo_project": "build_demo",
    "demo_build_scenarios": "build_demo",
    "demo_production_scenarios_for": "build_demo",
    "DATA_DIR": "build_demo",
    "main": "run_demo",
}

__all__ = sorted(_LAZY)


def __getattr__(name: str) -> Any:
    mod = _LAZY.get(name)
    if mod is None:
        raise AttributeError(f"module 'housebuilder_vision.demo' has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(f"{__name__}.{mod}"), name)
    globals()[name] = value
    return value
