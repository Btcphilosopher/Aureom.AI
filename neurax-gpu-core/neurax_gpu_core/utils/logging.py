"""
Logging utilities for NEURAX GPU CORE.

Provides a standard Python logger (``get_logger``) plus a lightweight
``MetricsLog`` used to accumulate per-timestep telemetry across every
subsystem so the dashboard / visualiser / tests can consume a single
tidy structure (a list of dict rows, trivially convertible to a
pandas DataFrame) instead of poking into engine internals.
"""

from __future__ import annotations

import logging
import sys
from collections import defaultdict
from typing import Any, Dict, List

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        logging.getLogger("neurax").setLevel(level)
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)-28s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root = logging.getLogger("neurax")
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(f"neurax.{name}")


class MetricsLog:
    """Accumulates one row of metrics per simulation timestep.

    Any subsystem can call ``record(timestep, **fields)`` repeatedly for the
    same timestep -- fields are merged into that row's dict, so different
    subsystems can each contribute their own columns without needing to
    know about each other.
    """

    def __init__(self) -> None:
        self._rows: Dict[int, Dict[str, Any]] = defaultdict(dict)
        self._order: List[int] = []

    def record(self, timestep: int, **fields: Any) -> None:
        if timestep not in self._rows:
            self._order.append(timestep)
        self._rows[timestep]["timestep"] = timestep
        self._rows[timestep].update(fields)

    def rows(self) -> List[Dict[str, Any]]:
        return [self._rows[t] for t in self._order]

    def latest(self) -> Dict[str, Any]:
        if not self._order:
            return {}
        return self._rows[self._order[-1]]

    def column(self, name: str) -> List[Any]:
        return [self._rows[t].get(name) for t in self._order]

    def to_dataframe(self):
        try:
            import pandas as pd
        except ImportError as exc:  # pragma: no cover
            raise ImportError("pandas is required for MetricsLog.to_dataframe()") from exc
        return pd.DataFrame(self.rows())

    def __len__(self) -> int:
        return len(self._order)
