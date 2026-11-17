"""Diagnostics shared by the loader, validator and emitters.

Every validation problem carries a stable machine-readable code (``E_*``) so
tests, CI and editors can match on it instead of on message text.  The
validator collects *all* problems before giving up; a definition is usable
only when no error was reported.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    where: str = ""

    def __str__(self) -> str:
        loc = f" [{self.where}]" if self.where else ""
        return f"{self.code}{loc}: {self.message}"


class RegDefError(Exception):
    """Raised when a definition is invalid.  ``diagnostics`` lists every problem."""

    def __init__(self, diagnostics: List[Diagnostic]):
        self.diagnostics = list(diagnostics)
        super().__init__("\n".join(str(d) for d in self.diagnostics))

    @property
    def codes(self) -> List[str]:
        return [d.code for d in self.diagnostics]


class Collector:
    """Accumulates diagnostics; ``raise_if_any`` converts them to an exception."""

    def __init__(self) -> None:
        self.items: List[Diagnostic] = []

    def add(self, code: str, message: str, where: str = "") -> None:
        self.items.append(Diagnostic(code, message, where))

    def raise_if_any(self) -> None:
        if self.items:
            raise RegDefError(self.items)

    def __bool__(self) -> bool:  # truthy when problems exist
        return bool(self.items)
