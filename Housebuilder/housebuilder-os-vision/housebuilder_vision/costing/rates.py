"""Rate books: loading, validation, merging and rate resolution.

A :class:`~housebuilder_vision.core.models.RateBook` is a list of
:class:`~housebuilder_vision.core.models.Rate` records keyed by *cost key*
(``mat:<material_id>``, ``lab:<trade>``, ``plant:<item>``, ``allow:<id>``,
``log:<item>``, ``prelim:<item>``; see ARCHITECTURE §3).

Loading (untrusted input)
-------------------------
:func:`load_rate_book_csv` / :func:`load_rate_book_json` treat files as
untrusted: at most :data:`MAX_FILE_BYTES` (5 MB) and :data:`MAX_ROWS`
(20 000) rows, CSV read by pandas with ``dtype=str`` (nothing is evaluated),
every cell stripped and length-capped, every row validated into a ``Rate``.
Invalid rows are skipped and reported in ``RateBook.warnings`` with their row
number; ``strict=True`` raises :class:`RateBookError` listing every bad row
instead.  Uncertainty fractions are clamped to ``[-1, 0]`` / ``[0, 5]`` with a
warning; non-finite numbers are rejected.

Resolution
----------
:func:`resolve_rate` picks one rate for ``(cost_key, unit)`` at
``settings.pricing_date`` and returns its *net* value per requested unit:

1. candidates = rates with that cost key (index built once per book);
2. excluded (with a warning): future-dated rates (``effective_date >
   pricing_date``), rates in a currency with no ``settings.fx_rates`` entry,
   rates whose unit cannot be converted to the requested unit;
3. ranking: quotes still valid on the pricing date before expired quotes
   (``valid_until < pricing_date`` -> deprioritised, warned), then
   :data:`~housebuilder_vision.core.models.RATE_SOURCE_PRIORITY`, then the most
   recent ``effective_date``, then book order;
4. net value = value
   ``÷ (1 + vat_rate)`` for ``INC_VAT`` rates (falls back to
   ``settings.vat_rate`` with a warning when the rate carries none)
   ``× fx`` (``settings.fx_rates[currency]``)
   ``× unit conversion`` (:func:`~housebuilder_vision.core.units.convert_rate`,
   dimension-checked; count units only match themselves).  For time-based cost keys
   (:data:`TIME_BASED_COST_KEY_PREFIXES`: ``lab:``, ``plant:``, ``prelim:``) a ``day`` /
   ``week`` is *working* time - ``settings.hours_per_working_day`` hours /
   ``settings.working_days_per_week`` days
   (:func:`~housebuilder_vision.core.units.convert_working_time_rate`), never 24 h / 7 days;
   the conversion is warned and labelled as an assumption.  Other keys use calendar time.
   ``× (1 + settings.annual_escalation_rate) ** years`` for rates dated before
   the pricing date (years = days / 365.25) - except rates whose ``valid_until`` covers the
   pricing date (a firm quote / price list is not escalated)
   ``× settings.regional_cost_factor`` when it differs from 1 and the rate is not local:
   a rate is local when its normalised location (lower case, punctuation removed) *equals*
   the project's site location, its region or one comma-separated part of either (e.g.
   ``"Exampleton (fictional)"`` matches ``"Plot 7, Fictional Lane, Exampleton
   (fictional)"``; ``"Lane"`` does not).  A supplier quote without a location is treated as
   quoted for the project site (warned); any other rate without a location is adjusted.
   Every factor is labelled.

Provenance: ``ResolvedRate.basis`` is the rate's basis (:data:`RATE_SOURCE_BASIS`; expired
quotes ASSUMED), weakened to ASSUMED when an assumed factor changed the value (escalation,
regional factor, VAT stripped at the project rate, working-time conversion).

Pricing date: a rate dated after the pricing date is excluded; when it outranks the rate that
is used instead (e.g. a new supplier quote excluded and a FICTIONAL demo rate used), the
warning starts with :data:`PRICING_DATE_WARNING` and ``ResolvedRate.excluded_newer`` names it.

No rate -> ``(None, nan, warnings)``: the value is NaN on purpose so a missing
price can never be silently treated as zero.

Boundaries: rates are inputs supplied by the user or by adapters.  The bundled
demo book is **fictional** (``source_type = fictional_demo``, source text
contains "FICTIONAL"); nothing here presents prices as market data.
"""

from __future__ import annotations

import io
import json
import math
import os
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import IO, Any, Iterable, Optional, Union

import pandas as pd
from pydantic import ValidationError

from ..core.models import (
    RATE_SOURCE_PRIORITY,
    CostLayer,
    DeliveryTreatment,
    Rate,
    RateBook,
    RateSourceType,
    TaxTreatment,
)
from ..core.provenance import Basis, weakest_basis
from ..core.settings import ProjectSettings
from ..core.units import UnitError, convert_rate, convert_working_time_rate, is_working_time_pair, normalise_unit

__all__ = [
    "MAX_FILE_BYTES",
    "MAX_ROWS",
    "MAX_CELL_CHARS",
    "RATE_COLUMNS",
    "KNOWN_COST_KEY_PREFIXES",
    "TIME_BASED_COST_KEY_PREFIXES",
    "PRICING_DATE_WARNING",
    "RATE_SOURCE_BASIS",
    "RateBookError",
    "RateIndex",
    "ResolvedRate",
    "rate_index",
    "load_rate_book_csv",
    "load_rate_book_json",
    "rate_book_from_records",
    "resolve_rate",
    "resolve_rate_detailed",
    "merge_rate_books",
    "rate_book_to_dataframe",
    "rate_basis",
    "cost_key_layer",
]

#: Maximum size of a rate-book file / buffer (bytes).
MAX_FILE_BYTES = 5 * 1024 * 1024
#: Maximum number of data rows.
MAX_ROWS = 20_000
#: Maximum characters in any one cell.
MAX_CELL_CHARS = 2_000
#: CSV / JSON columns = ``Rate`` fields, in model order.
RATE_COLUMNS: tuple[str, ...] = tuple(Rate.model_fields)
_REQUIRED_COLUMNS = ("rate_id", "cost_key", "layer", "unit", "value", "effective_date", "source", "source_type")
_FLOAT_FIELDS = ("value", "vat_rate", "delivery_charge", "uncertainty_low", "uncertainty_high")
_OPTIONAL_EMPTY_IS_NONE = ("vat_rate", "delivery_charge", "valid_until")
KNOWN_COST_KEY_PREFIXES = ("mat", "lab", "plant", "allow", "log", "prelim")
#: Cost keys priced per unit of time: their ``day`` / ``week`` units are working time (see module docstring).
TIME_BASED_COST_KEY_PREFIXES = ("lab", "plant", "prelim")
#: Start of the warning raised when a higher-priority rate is excluded only because it is dated after the
#: pricing date and a lower-priority rate is used instead (the estimate and the UI show it prominently).
PRICING_DATE_WARNING = "PRICING DATE"

#: Provenance of a rate by source type (expired quotes are downgraded to ASSUMED).
RATE_SOURCE_BASIS: dict[RateSourceType, Basis] = {
    RateSourceType.SUPPLIER_QUOTE: Basis.USER_CONFIRMED,
    RateSourceType.MANUAL: Basis.USER_CONFIRMED,
    RateSourceType.PRICE_LIST: Basis.INFERRED,
    RateSourceType.ADAPTER: Basis.INFERRED,
    RateSourceType.FICTIONAL_DEMO: Basis.ASSUMED,
}

_PREFIX_LAYER: dict[str, CostLayer] = {
    "mat": CostLayer.MATERIALS,
    "allow": CostLayer.MATERIALS,
    "lab": CostLayer.LABOUR,
    "plant": CostLayer.PLANT,
    "log": CostLayer.LOGISTICS_WASTE,
    "prelim": CostLayer.PRELIMINARIES,
}

PathOrBuffer = Union[str, os.PathLike, IO[str], IO[bytes]]


class RateBookError(ValueError):
    """Raised for unreadable / oversized rate books, or invalid rows in strict mode."""


# =============================================================================
# Small helpers
# =============================================================================
def cost_key_layer(cost_key: str) -> Optional[CostLayer]:
    """Default cost layer for a cost key prefix (``mat:``/``allow:`` -> 1, ``lab:`` -> 2 ...)."""
    prefix, _, _ = (cost_key or "").partition(":")
    return _PREFIX_LAYER.get(prefix)


def rate_basis(rate: Rate, *, expired: bool = False) -> Basis:
    """Provenance basis of a rate (see :data:`RATE_SOURCE_BASIS`)."""
    if expired:
        return Basis.ASSUMED
    return RATE_SOURCE_BASIS.get(rate.source_type, Basis.ASSUMED)


def _unit_key(unit: str) -> str:
    try:
        return normalise_unit(unit)
    except UnitError:
        return (unit or "").strip()


def _read_limited(path_or_buffer: PathOrBuffer) -> bytes:
    """Read at most MAX_FILE_BYTES (+1 to detect overflow) from a path or buffer."""
    if isinstance(path_or_buffer, (str, os.PathLike)):
        p = Path(path_or_buffer)
        if not p.is_file():
            raise RateBookError(f"rate book file not found: {p}")
        size = p.stat().st_size
        if size > MAX_FILE_BYTES:
            raise RateBookError(f"rate book is {size} bytes; the limit is {MAX_FILE_BYTES} bytes")
        with p.open("rb") as fh:
            data = fh.read(MAX_FILE_BYTES + 1)
    elif hasattr(path_or_buffer, "read"):
        data = path_or_buffer.read(MAX_FILE_BYTES + 1)
        if isinstance(data, str):
            data = data.encode("utf-8")
    else:
        raise RateBookError("expected a file path or a readable buffer")
    if len(data) > MAX_FILE_BYTES:
        raise RateBookError(f"rate book exceeds the {MAX_FILE_BYTES} byte limit")
    return data


def _layer_value(text: str) -> str:
    """Accept a CostLayer value ("1_materials"), name ("MATERIALS") or short name ("materials")."""
    t = text.strip()
    for layer in CostLayer:
        if t == layer.value or t.upper() == layer.name or t.lower() == layer.value.split("_", 1)[1]:
            return layer.value
    return t


def _clean_record(raw: dict[str, Any], row_no: int, warnings: list[str]) -> dict[str, Any]:
    """Strip / type-check one raw record (strings from CSV, JSON scalars) before model validation.

    Raises ``ValueError`` with a human-readable reason for an invalid row.
    """
    rec: dict[str, Any] = {}
    for key, val in raw.items():
        if key not in Rate.model_fields:
            continue  # unknown columns are reported once by the caller
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        if isinstance(val, (dict, list, tuple, set)):
            raise ValueError(f"field '{key}' must be a scalar")
        s = val.strip() if isinstance(val, str) else val
        if isinstance(s, str):
            if len(s) > MAX_CELL_CHARS:
                raise ValueError(f"field '{key}' exceeds {MAX_CELL_CHARS} characters")
            if s == "":
                continue  # empty -> model default (or None for optional fields)
        rec[key] = s
    for key in _FLOAT_FIELDS:
        if key in rec:
            try:
                f = float(rec[key])
            except (TypeError, ValueError):
                raise ValueError(f"field '{key}' is not a number: {rec[key]!r}") from None
            if not math.isfinite(f):
                raise ValueError(f"field '{key}' must be finite")
            rec[key] = f
    if "layer" in rec and isinstance(rec["layer"], str):
        rec["layer"] = _layer_value(rec["layer"])
    if "currency" in rec and isinstance(rec["currency"], str):
        cur = rec["currency"].upper()
        if not (len(cur) == 3 and cur.isalpha()):
            raise ValueError(f"currency must be a 3-letter code, got {rec['currency']!r}")
        rec["currency"] = cur
    for key in ("source_type", "tax_treatment", "delivery_treatment"):
        if key in rec and isinstance(rec[key], str):
            rec[key] = rec[key].lower()
    if "cost_key" in rec:
        ck = str(rec["cost_key"])
        if ":" not in ck or len(ck) > 120 or any(c.isspace() for c in ck):
            raise ValueError(f"cost_key {ck!r} must look like '<prefix>:<item>' without spaces")
        if ck.split(":", 1)[0] not in KNOWN_COST_KEY_PREFIXES:
            warnings.append(f"row {row_no}: cost key prefix of '{ck}' is not one of {KNOWN_COST_KEY_PREFIXES}")
    lo, hi = rec.get("uncertainty_low"), rec.get("uncertainty_high")
    if lo is not None and not (-1.0 <= lo <= 0.0):
        new = min(0.0, max(-1.0, lo))
        warnings.append(f"row {row_no}: uncertainty_low {lo:g} clamped to {new:g} (allowed -1..0)")
        rec["uncertainty_low"] = new
    if hi is not None and not (0.0 <= hi <= 5.0):
        new = min(5.0, max(0.0, hi))
        warnings.append(f"row {row_no}: uncertainty_high {hi:g} clamped to {new:g} (allowed 0..5)")
        rec["uncertainty_high"] = new
    vr = rec.get("vat_rate")
    if vr is not None and not (0.0 <= vr < 1.0):
        raise ValueError(f"vat_rate {vr:g} must be in [0, 1)")
    dc = rec.get("delivery_charge")
    if dc is not None and dc < 0:
        raise ValueError("delivery_charge must be >= 0")
    return rec


def _validation_reason(e: ValidationError) -> str:
    parts = []
    for err in e.errors()[:4]:
        loc = ".".join(str(x) for x in err.get("loc", ())) or "row"
        parts.append(f"{loc}: {err.get('msg', 'invalid')}")
    return "; ".join(parts)


def rate_book_from_records(records: Iterable[dict[str, Any]], *, name: str, strict: bool = False,
                           notes: str = "", first_row_number: int = 1) -> RateBook:
    """Validate raw records into a :class:`RateBook` (shared by the CSV / JSON loaders).

    Invalid rows are skipped with a warning naming the row number (``strict=True`` raises
    :class:`RateBookError` listing all of them).  Duplicate ``rate_id`` values keep the first
    occurrence.
    """
    rates: list[Rate] = []
    warnings: list[str] = []
    errors: list[str] = []
    seen: set[str] = set()
    unknown_cols: set[str] = set()
    for i, raw in enumerate(records):
        row_no = first_row_number + i
        if i >= MAX_ROWS:
            raise RateBookError(f"rate book has more than {MAX_ROWS} rows")
        if not isinstance(raw, dict):
            errors.append(f"row {row_no}: not a record")
            continue
        unknown_cols |= {str(k) for k in raw if k not in Rate.model_fields}
        try:
            rec = _clean_record(raw, row_no, warnings)
            rate = Rate.model_validate(rec)
        except ValidationError as e:
            errors.append(f"row {row_no}: {_validation_reason(e)}")
            continue
        except ValueError as e:
            errors.append(f"row {row_no}: {e}")
            continue
        if rate.rate_id in seen:
            errors.append(f"row {row_no}: duplicate rate_id '{rate.rate_id}' (first occurrence kept)")
            continue
        seen.add(rate.rate_id)
        rates.append(rate)
    if unknown_cols:
        warnings.insert(0, f"ignored unknown column(s): {', '.join(sorted(unknown_cols))}")
    if errors and strict:
        raise RateBookError(f"{len(errors)} invalid row(s) in rate book '{name}': " + " | ".join(errors))
    warnings.extend(f"skipped invalid {e}" for e in errors)
    if not rates:
        warnings.append(f"rate book '{name}' contains no valid rates")
    return RateBook(name=name, rates=rates, notes=notes, warnings=warnings)


# =============================================================================
# Loaders
# =============================================================================
def load_rate_book_csv(path_or_buffer: PathOrBuffer, *, name: Optional[str] = None,
                       strict: bool = False) -> RateBook:
    """Load a rate book from CSV (columns = ``Rate`` fields; header row required).

    ``path_or_buffer`` is a path or a text / binary buffer (UTF-8, optional BOM).  Size and row
    limits, cell stripping and per-row validation as described in the module docstring.
    ``name`` defaults to the file stem (or ``"uploaded rate book"`` for buffers).
    """
    data = _read_limited(path_or_buffer)
    if name is None:
        name = Path(path_or_buffer).stem if isinstance(path_or_buffer, (str, os.PathLike)) else "uploaded rate book"
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise RateBookError(f"rate book is not valid UTF-8 text: {e}") from None
    if not text.strip():
        raise RateBookError("rate book is empty")
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, na_filter=False,
                         skipinitialspace=True, comment=None, nrows=MAX_ROWS + 1)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as e:
        raise RateBookError(f"could not parse rate book CSV: {e}") from None
    if len(df) > MAX_ROWS:
        raise RateBookError(f"rate book has more than {MAX_ROWS} rows")
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in _REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise RateBookError(f"rate book CSV is missing required column(s): {', '.join(missing)}")
    records = df.to_dict(orient="records")
    # header is line 1, so the first data row is line 2 of the file
    return rate_book_from_records(records, name=name, strict=strict, first_row_number=2,
                                  notes=f"Loaded from CSV ({len(records)} rows).")


def load_rate_book_json(path_or_buffer: PathOrBuffer, *, name: Optional[str] = None,
                        strict: bool = False) -> RateBook:
    """Load a rate book from JSON: either ``{"name": ..., "rates": [...], "notes": ...}`` or a list of rates.

    Same limits and per-row validation as :func:`load_rate_book_csv` (row numbers are 1-based list
    positions).
    """
    data = _read_limited(path_or_buffer)
    try:
        obj = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise RateBookError(f"could not parse rate book JSON: {e}") from None
    notes = ""
    if isinstance(obj, dict):
        rows = obj.get("rates")
        if name is None and isinstance(obj.get("name"), str):
            name = obj["name"].strip()[:200]
        if isinstance(obj.get("notes"), str):
            notes = obj["notes"][:MAX_CELL_CHARS]
    else:
        rows = obj
    if not isinstance(rows, list):
        raise RateBookError("rate book JSON must be a list of rates or an object with a 'rates' list")
    if len(rows) > MAX_ROWS:
        raise RateBookError(f"rate book has more than {MAX_ROWS} rows")
    if name is None:
        name = Path(path_or_buffer).stem if isinstance(path_or_buffer, (str, os.PathLike)) else "uploaded rate book"
    return rate_book_from_records(rows, name=name, strict=strict, notes=notes or "Loaded from JSON.")


def merge_rate_books(*books: RateBook, name: Optional[str] = None) -> RateBook:
    """Concatenate rate books.  A later book's rate with an existing ``rate_id`` replaces it (warned).

    Rates for the same cost key from different books all remain; :func:`resolve_rate` chooses
    between them by validity, source priority and date.
    """
    by_id: "OrderedDict[str, Rate]" = OrderedDict()
    warnings: list[str] = []
    for b in books:
        warnings.extend(f"[{b.name}] {w}" for w in b.warnings)
        for r in b.rates:
            if r.rate_id in by_id:
                warnings.append(f"rate_id '{r.rate_id}' from '{b.name}' replaces an earlier rate with the same id")
                del by_id[r.rate_id]
            by_id[r.rate_id] = r
    return RateBook(name=name or " + ".join(b.name for b in books) or "merged",
                    rates=list(by_id.values()),
                    notes="Merged from: " + ", ".join(b.name for b in books), warnings=warnings)


def rate_book_to_dataframe(book: RateBook) -> pd.DataFrame:
    """One row per rate, columns = :data:`RATE_COLUMNS` (enums as values, dates ISO strings)."""
    rows = [r.model_dump(mode="json") for r in book.rates]
    return pd.DataFrame(rows, columns=list(RATE_COLUMNS))


# =============================================================================
# Index and resolution
# =============================================================================
class RateIndex:
    """Rates grouped by cost key (built once per book; immutable snapshot)."""

    __slots__ = ("book_name", "by_key", "n_rates", "_order")

    def __init__(self, book: RateBook) -> None:
        self.book_name = book.name
        self.n_rates = len(book.rates)
        by_key: dict[str, list[Rate]] = {}
        order: dict[str, int] = {}
        for i, r in enumerate(book.rates):
            by_key.setdefault(r.cost_key.strip(), []).append(r)
            order[r.rate_id] = i
        self.by_key = by_key
        self._order = order

    def candidates(self, cost_key: str) -> list[Rate]:
        return self.by_key.get(cost_key.strip(), [])

    def position(self, rate: Rate) -> int:
        return self._order.get(rate.rate_id, 0)

    def cost_keys(self) -> set[str]:
        return set(self.by_key)


_INDEX_CACHE: "OrderedDict[int, tuple[Any, tuple[int, ...], RateIndex]]" = OrderedDict()
_INDEX_CACHE_SIZE = 16


def rate_index(book: Union[RateBook, RateIndex]) -> RateIndex:
    """Index for ``book`` (cached per book object; rebuilt if its rate list changed)."""
    if isinstance(book, RateIndex):
        return book
    key = id(book)
    fp = tuple(id(r) for r in book.rates)
    hit = _INDEX_CACHE.get(key)
    if hit is not None and hit[0]() is book and hit[1] == fp:
        _INDEX_CACHE.move_to_end(key)
        return hit[2]
    import weakref

    idx = RateIndex(book)
    _INDEX_CACHE[key] = (weakref.ref(book), fp, idx)
    _INDEX_CACHE.move_to_end(key)
    while len(_INDEX_CACHE) > _INDEX_CACHE_SIZE:
        _INDEX_CACHE.popitem(last=False)
    return idx


@dataclass(frozen=True)
class ResolvedRate:
    """Outcome of resolving one ``(cost_key, unit)`` (see :func:`resolve_rate_detailed`)."""

    cost_key: str
    unit: str
    rate: Optional[Rate]
    #: Net value per requested unit in ``settings.currency`` (NaN when no rate).
    value: float
    #: Problems / exclusions worth showing to the user.
    warnings: tuple[str, ...] = ()
    #: Labelled adjustments applied to the chosen rate (VAT strip, fx, unit, escalation, region).
    adjustments: tuple[str, ...] = ()
    #: Product of the non-unit factors (VAT strip x fx x escalation x regional); applies to
    #: per-order amounts such as ``delivery_charge``.
    money_factor: float = 1.0
    unit_factor: float = 1.0
    escalation_factor: float = 1.0
    regional_factor: float = 1.0
    expired: bool = False
    basis: Basis = Basis.UNKNOWN
    #: True when a day / week rate of a time-based key was converted as working time (assumption).
    working_time: bool = False
    #: Rate ids that outrank the chosen rate but were excluded only because they are dated after the
    #: pricing date (see :data:`PRICING_DATE_WARNING`).
    excluded_newer: tuple[str, ...] = ()

    @property
    def found(self) -> bool:
        return self.rate is not None


_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def _norm_location(text: str) -> str:
    """Lower case, punctuation removed, whitespace collapsed: "Exampleton (fictional)" -> "exampleton fictional"."""
    return " ".join(_NON_ALNUM.sub(" ", (text or "").lower()).split())


def _local_names(settings: ProjectSettings) -> set[str]:
    """Normalised names that count as the project location: site location, region and their comma parts."""
    names: set[str] = set()
    for text in (settings.site_location, settings.region):
        names.add(_norm_location(text))
        names.update(_norm_location(part) for part in (text or "").split(","))
    names.discard("")
    return names


def _location_is_local(rate: Rate, settings: ProjectSettings) -> bool:
    """Normalised token equality with the site location, region or one of their comma-separated parts."""
    loc = _norm_location(rate.location)
    return bool(loc) and loc in _local_names(settings)


def _is_fictional(rate: Rate) -> bool:
    return (rate.source_type == RateSourceType.FICTIONAL_DEMO or "fictional" in rate.source.lower()
            or "fictional" in rate.supplier.lower())


def resolve_rate_detailed(book: Union[RateBook, RateIndex], cost_key: str, unit: str, *,
                          settings: ProjectSettings) -> ResolvedRate:
    """Choose a rate for ``(cost_key, unit)`` and compute its net value (see module docstring)."""
    idx = rate_index(book)
    cands = idx.candidates(cost_key)
    if not cands:
        return ResolvedRate(cost_key, unit, None, math.nan,
                            (f"no rate for '{cost_key}' in rate book '{idx.book_name}'",))
    pdate: date = settings.pricing_date
    req_unit = _unit_key(unit)
    time_based = cost_key.split(":", 1)[0].strip() in TIME_BASED_COST_KEY_PREFIXES
    hpd, dpw = settings.hours_per_working_day, settings.working_days_per_week
    warnings: list[str] = []
    excluded: list[str] = []
    future: list[Rate] = []
    usable: list[tuple[tuple, Rate, float, float, bool, bool]] = []
    for r in cands:
        if r.effective_date > pdate:
            warnings.append(f"rate '{r.rate_id}' for '{cost_key}' is effective from {r.effective_date.isoformat()}, "
                            f"after the pricing date {pdate.isoformat()}; excluded")
            future.append(r)
            continue
        if r.currency == settings.currency:
            fx = 1.0
        elif r.currency in settings.fx_rates and settings.fx_rates[r.currency] > 0:
            fx = float(settings.fx_rates[r.currency])
        else:
            warnings.append(f"rate '{r.rate_id}' for '{cost_key}' is in {r.currency} and no fx rate to "
                            f"{settings.currency} is set; excluded")
            continue
        r_unit = _unit_key(r.unit)
        working = False
        if r_unit == req_unit:
            uf = 1.0
        elif time_based and is_working_time_pair(r_unit, req_unit):
            uf = convert_working_time_rate(1.0, r_unit, req_unit, hours_per_working_day=hpd,
                                           working_days_per_week=dpw)
            working = True
        else:
            try:
                uf = convert_rate(1.0, r_unit, req_unit)
            except UnitError as e:
                excluded.append(f"rate '{r.rate_id}' is per '{r.unit}', not convertible to '{unit}' ({e})")
                continue
        expired = r.valid_until is not None and r.valid_until < pdate
        rank = (0 if expired else 1, RATE_SOURCE_PRIORITY.get(r.source_type, 0), r.effective_date.toordinal(),
                -idx.position(r))
        usable.append((rank, r, fx, uf, expired, working))
    if not usable:
        return ResolvedRate(cost_key, unit, None, math.nan,
                            tuple(warnings + excluded + [f"no usable rate for '{cost_key}' per '{unit}'"]))
    usable.sort(key=lambda t: t[0], reverse=True)
    _, rate, fx, uf, expired, working = usable[0]
    for _, other, _, _, other_expired, _ in usable[1:]:
        if other_expired and other.source_type == RateSourceType.SUPPLIER_QUOTE:
            warnings.append(f"quote '{other.rate_id}' for '{cost_key}' expired on {other.valid_until.isoformat()} "
                            f"(before {pdate.isoformat()}); deprioritised in favour of '{rate.rate_id}'")
    if expired:
        warnings.append(f"using expired rate '{rate.rate_id}' for '{cost_key}' (valid until "
                        f"{rate.valid_until.isoformat()}, pricing date {pdate.isoformat()}); re-quote")
    # ---- newer rates excluded only by the pricing date that outrank the rate used (COST-11)
    prio = RATE_SOURCE_PRIORITY.get(rate.source_type, 0)
    newer = [f for f in future if RATE_SOURCE_PRIORITY.get(f.source_type, 0) > prio
             or (expired and RATE_SOURCE_PRIORITY.get(f.source_type, 0) == prio)]
    for f in newer:
        used_label = f"{rate.source_type.value} rate '{rate.rate_id}'" + (" (FICTIONAL demo data)"
                                                                         if _is_fictional(rate) else "")
        warnings.insert(0, f"{PRICING_DATE_WARNING}: rate '{f.rate_id}' ({f.source_type.value}, effective "
                           f"{f.effective_date.isoformat()}) for '{cost_key}' is dated after the pricing date "
                           f"{pdate.isoformat()} and was excluded; the lower-priority {used_label} was used instead. "
                           f"Move the pricing date to {f.effective_date.isoformat()} or later if the newer rate "
                           "should apply.")
    adjustments: list[str] = []
    assumed_factor = False
    v = float(rate.value)
    money = 1.0
    if rate.tax_treatment == TaxTreatment.INC_VAT:
        vr = rate.vat_rate
        if vr is None:
            vr = settings.vat_rate
            assumed_factor = True
            warnings.append(f"rate '{rate.rate_id}' is VAT-inclusive without a vat_rate; stripped at the project "
                            f"VAT rate {vr:.0%} (assumption)")
            adjustments.append(f"VAT stripped ÷{1.0 + vr:g} at the project VAT rate (assumption)")
        else:
            adjustments.append(f"VAT stripped ÷{1.0 + vr:g}")
        money /= (1.0 + vr)
    elif rate.tax_treatment == TaxTreatment.UNKNOWN:
        warnings.append(f"rate '{rate.rate_id}' has unknown tax treatment; used as entered (assumed net of VAT)")
    if fx != 1.0:
        money *= fx
        adjustments.append(f"fx {rate.currency}->{settings.currency} ×{fx:g}")
    if working:
        assumed_factor = True
        adjustments.append(f"per {rate.unit} -> per {unit} ×{uf:g} (working time: {hpd:g} h per working day, "
                           f"{dpw:g} working days per week; assumption)")
        warnings.append(f"rate '{rate.rate_id}' for '{cost_key}' is per {rate.unit}: converted to per {unit} as "
                        f"working time ({hpd:g} h per working day, {dpw:g} working days per week - "
                        "ProjectSettings.hours_per_working_day / working_days_per_week; assumption), not calendar "
                        "time")
    elif uf != 1.0:
        adjustments.append(f"per {rate.unit} -> per {unit} ×{uf:g}")
    esc = 1.0
    e = settings.annual_escalation_rate
    days = (pdate - rate.effective_date).days
    firm = rate.valid_until is not None and rate.valid_until >= pdate
    if e and days > 0:
        if firm:
            adjustments.append(f"not escalated: valid until {rate.valid_until.isoformat()} (firm price on the "
                               f"pricing date {pdate.isoformat()})")
        else:
            years = days / 365.25
            esc = (1.0 + e) ** years
            money *= esc
            assumed_factor = True
            adjustments.append(f"escalation {e:+.1%}/yr × {years:.2f} yr = ×{esc:.4f} (assumption)")
    reg = 1.0
    rf = settings.regional_cost_factor
    if rf != 1.0:
        if not rate.location.strip() and rate.source_type == RateSourceType.SUPPLIER_QUOTE:
            warnings.append(f"supplier quote '{rate.rate_id}' for '{cost_key}' has no location; treated as quoted "
                            f"for the project site (regional factor ×{rf:g} not applied; assumption) - add the "
                            "quote's location to confirm")
        elif not _location_is_local(rate, settings):
            reg = rf
            money *= reg
            assumed_factor = True
            adjustments.append(f"regional factor ×{rf:g} (rate location '{rate.location or 'unspecified'}' "
                               "differs from the project location; assumption)")
    v = v * money * uf
    basis = rate_basis(rate, expired=expired)
    if assumed_factor:
        basis = weakest_basis(basis, Basis.ASSUMED)
    return ResolvedRate(cost_key=cost_key, unit=unit, rate=rate, value=v, warnings=tuple(warnings),
                        adjustments=tuple(adjustments), money_factor=money, unit_factor=uf, escalation_factor=esc,
                        regional_factor=reg, expired=expired, basis=basis, working_time=working,
                        excluded_newer=tuple(f.rate_id for f in newer))


def resolve_rate(book: Union[RateBook, RateIndex], cost_key: str, unit: str, *,
                 settings: ProjectSettings) -> tuple[Optional[Rate], float, list[str]]:
    """``(rate, net value per unit, warnings)`` for ``cost_key`` priced per ``unit``.

    The net value is converted to the requested unit and ``settings.currency``, VAT-exclusive,
    escalated to the pricing date and regionally adjusted.  The warnings list the resolution
    warnings followed by *every* adjustment applied (VAT strip, fx, unit / working-time conversion,
    escalation, regional factor), each labelled.  ``rate`` is ``None`` and the value NaN when
    nothing usable exists.
    """
    rr = resolve_rate_detailed(book, cost_key, unit, settings=settings)
    out = list(rr.warnings)
    out.extend(a for a in rr.adjustments if a not in out)
    return rr.rate, rr.value, out


def __getattr__(name: str) -> Any:
    # ARCHITECTURE §2 lists ``PricingAdapter`` under costing/rates.py; it lives in .adapters.
    if name == "PricingAdapter":
        from .adapters import PricingAdapter

        return PricingAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def delivery_note(rate: Rate) -> Optional[str]:
    """Short label of how delivery is treated by a rate (None when included / not applicable)."""
    t = rate.delivery_treatment
    if t in (DeliveryTreatment.DELIVERED_INCLUDED, DeliveryTreatment.NOT_APPLICABLE):
        return None
    return t.value.replace("_", " ")
