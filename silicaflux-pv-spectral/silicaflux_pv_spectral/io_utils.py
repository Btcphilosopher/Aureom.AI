"""
Machine-readable data export helpers (SilicaFlux spec items 20, 25:
"machine-readable data" throughout).

Recursively converts dataclasses, numpy arrays/scalars, dicts, lists and
tuples into plain JSON-serialisable Python structures (via ``json.dumps``),
so any result object in this package -- ``PipelineResult``,
``SilicaFluxResult``, sweep tables, graph data -- can be serialised without
each module hand-writing its own exporter.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import numpy as np


def to_jsonable(value: Any) -> Any:
    """Recursively convert ``value`` into plain JSON-serialisable Python types."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, np.ndarray):
        return [to_jsonable(v) for v in value.tolist()]
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    if callable(value):
        # e.g. an optics.Layer's n_func/k_func -- a wavelength -> index closure,
        # not itself data. Represent it by name rather than failing to serialise.
        return f"<function:{getattr(value, '__name__', repr(value))}>"
    return value


def to_json(value: Any, indent: int | None = 2) -> str:
    """Serialise any dataclass/array-bearing result object to a JSON string."""
    return json.dumps(to_jsonable(value), indent=indent)


def write_json(value: Any, path: str, indent: int | None = 2) -> None:
    with open(path, "w") as f:
        f.write(to_json(value, indent=indent))
