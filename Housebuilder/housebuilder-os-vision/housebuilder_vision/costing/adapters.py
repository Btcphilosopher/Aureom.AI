"""Pricing adapters: pluggable sources of rates (no network access by default).

A :class:`PricingAdapter` turns a set of cost keys into a :class:`RateBook`.  The
cost engine never calls adapters itself; the application (or the user) fetches
rates, inspects them, and passes a rate book to the engine, so every price is
visible before it is used.

Bundled adapters
----------------
* :class:`ManualCSVPricingAdapter` - a CSV / JSON rate book on disk (e.g. a
  supplier's quote exported to the column layout of :data:`RATE_COLUMNS`).  It is
  the documented example of the protocol.
* :class:`FictionalDemoPricingAdapter` - the bundled demo book
  ``demo/data/fictional_rates_gbp_2026.csv``.  Every rate in it is **fictional**
  (``source_type = fictional_demo`` or a fictional supplier quote whose source text
  contains "FICTIONAL").

Writing a network adapter (not bundled)
---------------------------------------
An adapter that calls a supplier API must be opt-in: ``is_available()`` returns
False unless the user configured credentials and explicitly enabled it; it must
validate every returned record through :func:`rate_book_from_records` (treating
the response as untrusted), set ``source_type = RateSourceType.ADAPTER`` and a
``source`` naming the service and retrieval date, and import any client library
lazily inside ``fetch_rates``.  Nothing in this package makes network calls.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional, Protocol, Sequence, runtime_checkable

from ..core.models import RateBook
from ..core.settings import ProjectSettings
from .rates import RATE_COLUMNS, load_rate_book_csv, load_rate_book_json, merge_rate_books

__all__ = [
    "PricingAdapter",
    "ManualCSVPricingAdapter",
    "FictionalDemoPricingAdapter",
    "DEMO_RATES_PATH",
    "demo_rate_book",
    "fetch_rate_book",
    "RATE_COLUMNS",
]

#: Bundled fictional demo rates.
DEMO_RATES_PATH = Path(__file__).resolve().parent.parent / "demo" / "data" / "fictional_rates_gbp_2026.csv"


@runtime_checkable
class PricingAdapter(Protocol):
    """A source of rates.

    ``fetch_rates`` returns a :class:`RateBook` with rates for (a subset of) ``cost_keys``;
    keys it cannot price are simply absent (the engine then lists them as unresolved).  It must
    not raise for missing keys and must not perform network I/O unless the user enabled it.
    """

    name: str

    def is_available(self) -> bool: ...

    def fetch_rates(self, cost_keys: Iterable[str], settings: ProjectSettings) -> RateBook: ...


class ManualCSVPricingAdapter:
    """Rates from a user-supplied CSV (or JSON) rate book on disk.

    Example::

        adapter = ManualCSVPricingAdapter("quotes/example_supplier.csv", name="Example quotes")
        if adapter.is_available():
            book = adapter.fetch_rates(cost_keys(library), settings)
            estimate = estimate_construction_cost(boq, merge_rate_books(demo_rate_book(), book),
                                                  CostParameters(), settings=settings)

    The file is validated row by row (``strict`` controls whether a bad row aborts the load);
    the rates keep their own ``source_type`` / ``source`` columns.
    """

    def __init__(self, path: str | os.PathLike, *, name: Optional[str] = None, strict: bool = False) -> None:
        self.path = Path(path)
        self.name = name or f"manual:{self.path.name}"
        self.strict = strict

    def is_available(self) -> bool:
        return self.path.is_file()

    def _load(self) -> RateBook:
        if self.path.suffix.lower() == ".json":
            return load_rate_book_json(self.path, name=self.name, strict=self.strict)
        return load_rate_book_csv(self.path, name=self.name, strict=self.strict)

    def fetch_rates(self, cost_keys: Iterable[str], settings: ProjectSettings) -> RateBook:
        """Load the file and keep only rates for ``cost_keys`` (all rates when ``cost_keys`` is empty)."""
        book = self._load()
        wanted = {k.strip() for k in cost_keys}
        if not wanted:
            return book
        kept = [r for r in book.rates if r.cost_key in wanted]
        missing = sorted(wanted - {r.cost_key for r in kept})
        notes = book.notes + (f" {len(missing)} requested key(s) not in this book." if missing else "")
        return book.model_copy(update={"rates": kept, "notes": notes.strip()})


class FictionalDemoPricingAdapter(ManualCSVPricingAdapter):
    """The bundled FICTIONAL demo rates (GBP, Exampleton, effective 2026-10-01)."""

    def __init__(self) -> None:
        super().__init__(DEMO_RATES_PATH, name="Fictional demo rates GBP 2026 (FICTIONAL - not market data)",
                         strict=True)


def demo_rate_book() -> RateBook:
    """The bundled fictional demo rate book (strictly validated)."""
    return FictionalDemoPricingAdapter()._load()


def fetch_rate_book(adapters: Sequence[PricingAdapter], cost_keys: Iterable[str], settings: ProjectSettings, *,
                    name: str = "combined rates") -> RateBook:
    """Merge the books of every *available* adapter (unavailable ones are noted and skipped)."""
    keys = list(cost_keys)
    books: list[RateBook] = []
    skipped: list[str] = []
    for a in adapters:
        if a.is_available():
            books.append(a.fetch_rates(keys, settings))
        else:
            skipped.append(a.name)
    merged = merge_rate_books(*books, name=name) if books else RateBook(name=name)
    if skipped:
        msg = f"unavailable pricing adapter(s) skipped: {', '.join(skipped)}"
        merged = merged.model_copy(update={"warnings": [*merged.warnings, msg]})
    return merged
