"""Processing engine: mixing, pasteurisation, homogenisation, ageing, freezing, aeration, hardening."""

from __future__ import annotations

from icecream_x.processing.ageing import AgeingResult, age
from icecream_x.processing.aeration import aerate
from icecream_x.processing.freezing import FreezingResult, freeze
from icecream_x.processing.hardening import HardeningResult, harden
from icecream_x.processing.homogenisation import homogenise
from icecream_x.processing.mixing import mix
from icecream_x.processing.pasteurisation import PasteurisationResult, pasteurise

__all__ = [
    "mix",
    "pasteurise",
    "PasteurisationResult",
    "homogenise",
    "age",
    "AgeingResult",
    "freeze",
    "FreezingResult",
    "aerate",
    "harden",
    "HardeningResult",
]
