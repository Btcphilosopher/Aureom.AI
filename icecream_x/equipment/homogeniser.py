"""Homogeniser equipment definition.

Two-stage high-pressure homogenisers are standard in ice cream
manufacture: a first stage at the main pressure to break up fat globules,
and a second stage at a much lower pressure to disperse globule
clusters. Pressures are stored in Pa (SI) but are conventionally quoted
and configured in bar in the food industry -- constructors accept bar via
:meth:`Homogeniser.from_bar` for convenience.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.utils.validation import require_positive

BAR_TO_PA = 1.0e5


@dataclass(frozen=True, slots=True)
class Homogeniser:
    name: str
    first_stage_pressure_pa: float
    second_stage_pressure_pa: float = 0.0
    passes: int = 1
    motor_power_kw: float = 15.0

    def __post_init__(self) -> None:
        require_positive(self.first_stage_pressure_pa, "first_stage_pressure_pa")
        if self.passes < 1:
            raise ValueError("passes must be >= 1")

    @classmethod
    def from_bar(
        cls,
        name: str,
        first_stage_bar: float,
        second_stage_bar: float = 0.0,
        passes: int = 1,
        motor_power_kw: float = 15.0,
    ) -> "Homogeniser":
        return cls(
            name=name,
            first_stage_pressure_pa=first_stage_bar * BAR_TO_PA,
            second_stage_pressure_pa=second_stage_bar * BAR_TO_PA,
            passes=passes,
            motor_power_kw=motor_power_kw,
        )

    @property
    def total_pressure_pa(self) -> float:
        return self.first_stage_pressure_pa + self.second_stage_pressure_pa

    @property
    def total_pressure_bar(self) -> float:
        return self.total_pressure_pa / BAR_TO_PA


TWO_STAGE_DEFAULT = Homogeniser.from_bar(
    name="Two-stage homogeniser", first_stage_bar=170.0, second_stage_bar=35.0, passes=1
)

SINGLE_STAGE_ARTISAN = Homogeniser.from_bar(
    name="Single-stage homogeniser", first_stage_bar=100.0, second_stage_bar=0.0, passes=1
)
