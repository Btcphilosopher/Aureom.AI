"""
Centralised logging for APEX HORIZON ENGINE.

Every subsystem pulls its logger from :func:`get_logger` so that a single
call to :func:`setup_logging` controls verbosity engine-wide. Kept
deliberately dependency-free (stdlib ``logging`` only) so it works
identically whether the engine is driven from ``main.py``, a test, or an
embedding application.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-24s | %(message)s"
_DATEFMT = "%H:%M:%S"


def setup_logging(level: int = logging.INFO, *, stream=None) -> None:
    """Configure the root ``apex_horizon`` logger tree exactly once.

    Safe to call multiple times -- subsequent calls only adjust the level.
    """
    global _CONFIGURED
    root = logging.getLogger("apex_horizon")
    if _CONFIGURED:
        root.setLevel(level)
        return

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under the ``apex_horizon`` tree.

    Calling code does not need to call :func:`setup_logging` first --
    if nobody has configured logging yet, a sane default (INFO, stdout)
    is installed lazily so imports never spam ``No handlers could be
    found`` warnings.
    """
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(f"apex_horizon.{name}")
