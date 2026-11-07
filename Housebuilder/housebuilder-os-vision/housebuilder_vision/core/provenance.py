"""Provenance primitives used throughout Housebuilder.OS Vision.

Every number that drives geometry, quantities or cost is wrapped in a
:class:`TrackedValue` that records *how we know it*:

``observed``        measured directly from image evidence (pixels, detections).
``inferred``        derived by a rule or model from observations (e.g. storey
                    count from window rows, metres from pixels via scale).
``user_confirmed``  entered or confirmed by a person; the strongest basis.
``assumed``         a labelled default the user may continue with (UK priors,
                    hidden-side rules, assembly choices).
``unknown``         not recoverable from the available evidence.

Derived results inherit the *weakest* basis of their inputs (see
:func:`weakest_basis`), so a quantity that depends on an assumed depth is shown
as assumption-dependent even if other inputs were confirmed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Basis(str, Enum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    USER_CONFIRMED = "user_confirmed"
    ASSUMED = "assumed"
    UNKNOWN = "unknown"


#: Ordering used when combining bases: lower rank = weaker evidence.
BASIS_RANK: dict[Basis, int] = {
    Basis.UNKNOWN: 0,
    Basis.ASSUMED: 1,
    Basis.INFERRED: 2,
    Basis.OBSERVED: 3,
    Basis.USER_CONFIRMED: 4,
}

BASIS_LABEL: dict[Basis, str] = {
    Basis.OBSERVED: "Observed",
    Basis.INFERRED: "Inferred",
    Basis.USER_CONFIRMED: "User-confirmed",
    Basis.ASSUMED: "Assumption",
    Basis.UNKNOWN: "Unknown",
}


def weakest_basis(*bases: Basis | Iterable[Basis]) -> Basis:
    """Return the weakest basis among the inputs (UNKNOWN if none given)."""
    flat: list[Basis] = []
    for b in bases:
        if isinstance(b, Basis):
            flat.append(b)
        elif b is None:
            continue
        else:
            flat.extend(x for x in b if x is not None)
    if not flat:
        return Basis.UNKNOWN
    return min(flat, key=lambda x: BASIS_RANK[x])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Distribution(str, Enum):
    """How ``low``/``value``/``high`` are interpreted by the simulator.

    FIXED       no uncertainty (low/high ignored).
    UNIFORM     uniform on [low, high].
    TRIANGULAR  triangular(low, mode=value, high).
    PERT        Beta-PERT(low, mode=value, high).
    NORMAL      normal with mean=value; low/high are the P5/P95 bounds.
    LOGNORMAL   lognormal with median=value; low/high are the P5/P95 bounds.
    """

    FIXED = "fixed"
    UNIFORM = "uniform"
    TRIANGULAR = "triangular"
    PERT = "pert"
    NORMAL = "normal"
    LOGNORMAL = "lognormal"


class EditRecord(BaseModel):
    """One change to a value, feature or model element (audit trail)."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime = Field(default_factory=utcnow)
    actor: str = "user"
    target: str = ""
    field: str = ""
    old_value: Any = None
    new_value: Any = None
    old_basis: Optional[Basis] = None
    new_basis: Optional[Basis] = None
    reason: str = ""


class TrackedValue(BaseModel):
    """A number with unit, uncertainty range and provenance.

    ``value`` is the best estimate (mode).  ``None`` means unknown, in which
    case ``basis`` must be ``UNKNOWN`` and downstream code must either use a
    labelled allowance or leave the dependent quantity unresolved.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=False)

    value: Optional[float] = None
    unit: str = ""
    basis: Basis = Basis.ASSUMED
    low: Optional[float] = None
    high: Optional[float] = None
    distribution: Distribution = Distribution.TRIANGULAR
    #: Values sharing a correlation group are sampled with a common driver
    #: (e.g. every dimension scaled from the same image shares "scale:img_x").
    correlation_group: Optional[str] = None
    source: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    note: str = ""
    history: list[EditRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "TrackedValue":
        if self.value is None:
            if self.basis not in (Basis.UNKNOWN,):
                # A value without a number is by definition unknown.
                object.__setattr__(self, "basis", Basis.UNKNOWN)
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError(f"low ({self.low}) > high ({self.high})")
        if self.value is not None:
            if self.low is not None and self.value < self.low - 1e-9:
                raise ValueError(f"value {self.value} below low {self.low}")
            if self.high is not None and self.value > self.high + 1e-9:
                raise ValueError(f"value {self.value} above high {self.high}")
        return self

    # ------------------------------------------------------------------ helpers
    @property
    def is_known(self) -> bool:
        return self.value is not None

    @property
    def is_uncertain(self) -> bool:
        return (
            self.distribution != Distribution.FIXED
            and self.low is not None
            and self.high is not None
            and self.high > self.low
        )

    def v(self, default: Optional[float] = None) -> Optional[float]:
        """Best estimate, or ``default`` when unknown."""
        return self.value if self.value is not None else default

    def bounds(self) -> tuple[Optional[float], Optional[float]]:
        if self.distribution == Distribution.FIXED:
            return self.value, self.value
        lo = self.low if self.low is not None else self.value
        hi = self.high if self.high is not None else self.value
        return lo, hi

    def relative_spread(self) -> Optional[float]:
        """(high-low)/value, or None if not computable."""
        lo, hi = self.bounds()
        if self.value in (None, 0) or lo is None or hi is None:
            return None
        return (hi - lo) / abs(self.value)

    def edited(
        self,
        new_value: Optional[float],
        *,
        actor: str = "user",
        target: str = "",
        field: str = "value",
        reason: str = "",
        basis: Basis = Basis.USER_CONFIRMED,
        tolerance: Optional[float] = None,
        low: Optional[float] = None,
        high: Optional[float] = None,
    ) -> "TrackedValue":
        """Return a copy with a new value and an appended :class:`EditRecord`.

        By default the edit is treated as a user confirmation: the range
        collapses to ``value ± tolerance`` (or to the point value).
        """
        if new_value is None:
            lo = hi = None
            basis = Basis.UNKNOWN
        elif low is not None or high is not None:
            lo = low if low is not None else new_value
            hi = high if high is not None else new_value
        elif tolerance:
            lo, hi = new_value - abs(tolerance), new_value + abs(tolerance)
        else:
            lo = hi = None
        rec = EditRecord(
            actor=actor,
            target=target,
            field=field,
            old_value=self.value,
            new_value=new_value,
            old_basis=self.basis,
            new_basis=basis,
            reason=reason,
        )
        dist = self.distribution if (lo is not None and hi is not None and hi > lo) else Distribution.FIXED
        return self.model_copy(
            update={
                "value": new_value,
                "low": lo,
                "high": hi,
                "basis": basis,
                "distribution": dist,
                "history": [*self.history, rec],
            },
            deep=True,
        )

    def label(self, fmt: str = "{:.2f}") -> str:
        if self.value is None:
            return f"unknown {self.unit}".strip()
        s = fmt.format(self.value)
        if self.is_uncertain:
            s += f" ({fmt.format(self.low)}–{fmt.format(self.high)})"
        return f"{s} {self.unit}".strip()


# ----------------------------------------------------------------- factories
def observed(value: float, unit: str, *, low: float | None = None, high: float | None = None,
             source: str = "", evidence_ids: Iterable[str] = (), note: str = "",
             distribution: Distribution = Distribution.TRIANGULAR,
             correlation_group: str | None = None) -> TrackedValue:
    return TrackedValue(value=value, unit=unit, basis=Basis.OBSERVED, low=low, high=high,
                        source=source, evidence_ids=list(evidence_ids), note=note,
                        distribution=distribution if low is not None else Distribution.FIXED,
                        correlation_group=correlation_group)


def inferred(value: float, unit: str, *, low: float | None = None, high: float | None = None,
             source: str = "", evidence_ids: Iterable[str] = (), note: str = "",
             distribution: Distribution = Distribution.TRIANGULAR,
             correlation_group: str | None = None) -> TrackedValue:
    return TrackedValue(value=value, unit=unit, basis=Basis.INFERRED, low=low, high=high,
                        source=source, evidence_ids=list(evidence_ids), note=note,
                        distribution=distribution if low is not None else Distribution.FIXED,
                        correlation_group=correlation_group)


def assumed(value: float, unit: str, *, low: float | None = None, high: float | None = None,
            source: str = "", note: str = "", distribution: Distribution = Distribution.TRIANGULAR,
            correlation_group: str | None = None) -> TrackedValue:
    return TrackedValue(value=value, unit=unit, basis=Basis.ASSUMED, low=low, high=high,
                        source=source, note=note,
                        distribution=distribution if low is not None else Distribution.FIXED,
                        correlation_group=correlation_group)


def confirmed(value: float, unit: str, *, tolerance: float | None = None, source: str = "user",
              note: str = "") -> TrackedValue:
    lo = hi = None
    dist = Distribution.FIXED
    if tolerance:
        lo, hi, dist = value - abs(tolerance), value + abs(tolerance), Distribution.UNIFORM
    return TrackedValue(value=value, unit=unit, basis=Basis.USER_CONFIRMED, low=lo, high=hi,
                        source=source, note=note, distribution=dist)


def unknown(unit: str, note: str = "", source: str = "") -> TrackedValue:
    return TrackedValue(value=None, unit=unit, basis=Basis.UNKNOWN, note=note, source=source,
                        distribution=Distribution.FIXED)
