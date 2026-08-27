"""Cross-cutting validation helpers used throughout ICECREAM-X.

These are deliberately simple, dependency-free numeric guards. Pydantic
handles structural/type validation on data models (see
``formulation.ingredients`` and ``core.configuration``); this module
handles physical-plausibility and mass/energy-balance checks that apply
across module boundaries.
"""

from __future__ import annotations

import math

MASS_BALANCE_TOLERANCE_KG = 1e-9
FRACTION_TOLERANCE = 1e-6


class ValidationError(ValueError):
    """Raised when a physical or numerical invariant is violated."""


def require_fraction(value: float, name: str, *, allow_zero: bool = True) -> float:
    """Validate that ``value`` is a fraction in [0, 1] (or (0, 1] if not allow_zero)."""
    if math.isnan(value) or math.isinf(value):
        raise ValidationError(f"{name} is not finite: {value}")
    lower = 0.0 if allow_zero else FRACTION_TOLERANCE
    if value < lower - FRACTION_TOLERANCE or value > 1.0 + FRACTION_TOLERANCE:
        raise ValidationError(f"{name} must be a fraction in [0, 1], got {value}")
    return min(max(value, 0.0), 1.0)


def require_non_negative(value: float, name: str) -> float:
    if math.isnan(value) or math.isinf(value):
        raise ValidationError(f"{name} is not finite: {value}")
    if value < -1e-9:
        raise ValidationError(f"{name} must be >= 0, got {value}")
    return max(value, 0.0)


def require_positive(value: float, name: str) -> float:
    if math.isnan(value) or math.isinf(value) or value <= 0:
        raise ValidationError(f"{name} must be > 0, got {value}")
    return value


def require_sums_to_one(fractions: dict[str, float], *, tolerance: float = 1e-3) -> None:
    """Validate that a dict of mass fractions sums to ~1.0."""
    total = sum(fractions.values())
    if abs(total - 1.0) > tolerance:
        raise ValidationError(
            f"Fractions do not sum to 1.0 (got {total:.6f}): {fractions}"
        )


def check_mass_balance(
    input_mass_kg: float,
    output_mass_kg: float,
    known_losses_kg: float = 0.0,
    *,
    tolerance_kg: float = MASS_BALANCE_TOLERANCE_KG,
    context: str = "process",
) -> None:
    """Enforce INPUT MASS = OUTPUT MASS + KNOWN LOSSES for every process step."""
    residual = input_mass_kg - (output_mass_kg + known_losses_kg)
    # Use a relative tolerance for larger batches, absolute for small ones.
    scale = max(abs(input_mass_kg), 1e-6)
    rel_tolerance = max(tolerance_kg, 1e-9 * scale)
    if abs(residual) > rel_tolerance:
        raise ValidationError(
            f"Mass balance violated in {context}: input={input_mass_kg:.9f} kg, "
            f"output={output_mass_kg:.9f} kg, losses={known_losses_kg:.9f} kg, "
            f"residual={residual:.9f} kg"
        )
