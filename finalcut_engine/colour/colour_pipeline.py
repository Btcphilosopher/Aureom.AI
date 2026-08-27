"""The non-destructive colour node pipeline:

```
SOURCE -> BALANCE -> EXPOSURE -> COLOUR -> LUT -> LOOK -> OUTPUT
```

Every stage is optional and independently swappable, and nothing here ever
mutates source pixels: a :class:`ColourPipeline` is pure configuration that
the render graph re-evaluates whenever it (or an upstream node) is dirtied.

For keyframe-based colour changes, any stage may be supplied as a callable
``(Time) -> stage_instance`` instead of a fixed instance — the pipeline
resolves it at apply time. This lets ``motion.keyframes`` drive colour
parameters without colour depending on the motion module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Union

import numpy as np

from finalcut_engine.colour.exposure import apply_temperature_tint
from finalcut_engine.colour.lut import LUT3D
from finalcut_engine.core.timebase import Time
from finalcut_engine.media.metadata import ColourSpace

StageOrCallable = Union[object, Callable[[Time], object]]


def _resolve(stage: Optional[StageOrCallable], t: Time) -> Optional[object]:
    if stage is None:
        return None
    return stage(t) if callable(stage) else stage


@dataclass
class BalanceParams:
    temperature: float = 0.0
    tint: float = 0.0

    def apply(self, image: np.ndarray) -> np.ndarray:
        return apply_temperature_tint(image, self.temperature, self.tint)


@dataclass
class ColourPipeline:
    name: str = "Colour Pipeline"
    balance: Optional[StageOrCallable] = None
    exposure: Optional[StageOrCallable] = None
    colour: Optional[StageOrCallable] = None  # ColourWheel + curves ("primary" grade)
    curves: Optional[StageOrCallable] = None
    lut: Optional[LUT3D] = None
    look: Optional[LUT3D] = None  # a second, creative LUT applied after the technical one
    colour_space: ColourSpace = ColourSpace.REC709

    def apply(self, image: np.ndarray, t: Optional[Time] = None) -> np.ndarray:
        t = t if t is not None else Time.zero()
        out = image.astype(np.float64)

        balance = _resolve(self.balance, t)
        if balance is not None:
            out = balance.apply(out)

        exposure = _resolve(self.exposure, t)
        if exposure is not None:
            out = exposure.apply(out)

        colour = _resolve(self.colour, t)
        if colour is not None:
            out = colour.apply(out)

        curves = _resolve(self.curves, t)
        if curves is not None:
            out = curves.apply(out)

        if self.lut is not None:
            out = self.lut.apply(out)

        if self.look is not None:
            out = self.look.apply(out)

        return np.clip(out, 0.0, 1.0)

    def output_colour_space(self) -> ColourSpace:
        """Colour metadata is preserved through the pipeline unless a LUT changes it."""
        return self.colour_space
