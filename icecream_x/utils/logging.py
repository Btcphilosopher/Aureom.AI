"""Structured logging for ICECREAM-X.

Every log record carries a small set of structured fields (event, module,
and arbitrary keyword context) in addition to the human-readable message,
so simulation runs can be filtered/parsed programmatically (e.g. by a log
aggregator) as well as read on a terminal.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

_CONFIGURED = False


class StructuredFormatter(logging.Formatter):
    """Emits log records as single-line JSON with structured context."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "context", None)
        if extra:
            payload["context"] = extra
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO, *, json_output: bool = False) -> None:
    """Configure the root ``icecream_x`` logger. Safe to call multiple times."""
    global _CONFIGURED
    root = logging.getLogger("icecream_x")
    if _CONFIGURED:
        root.setLevel(level)
        return
    handler = logging.StreamHandler(stream=sys.stdout)
    if json_output:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
        )
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under the ``icecream_x`` hierarchy."""
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(f"icecream_x.{name}")


def log_context(logger: logging.Logger, level: int, message: str, **context: Any) -> None:
    """Emit a log record carrying structured keyword context."""
    logger.log(level, message, extra={"context": context})
