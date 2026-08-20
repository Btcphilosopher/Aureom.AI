"""
Multi-objective composition: weighted combination of energy, revenue,
efficiency, LCOE, NPV, grid value, water security and environmental impact
into a single scalar objective the pluggable optimisation algorithms can
maximise.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ObjectiveWeights:
    """All weights are configurable; a metric with weight 0 has no effect.
    Metrics that are naturally "lower is better" (LCOE, environmental
    impact, operating cost) are subtracted, so every weight here is
    conventionally non-negative -- the sign is baked into
    :func:`composite_objective`.
    """

    energy: float = 0.0
    revenue: float = 0.0
    efficiency: float = 0.0
    lcoe: float = 0.0
    npv: float = 0.0
    grid_value: float = 0.0
    water_security: float = 0.0
    environmental_impact: float = 0.0
    operating_cost: float = 0.0

    @classmethod
    def preset(cls, name: str) -> "ObjectiveWeights":
        presets = {
            "max_energy": cls(energy=1.0),
            "max_revenue": cls(revenue=1.0),
            "min_lcoe": cls(lcoe=1.0),
            "max_npv": cls(npv=1.0),
            "max_grid_value": cls(grid_value=1.0),
            "balanced": cls(revenue=0.5, npv=0.3, environmental_impact=0.1, water_security=0.1),
        }
        if name not in presets:
            raise ValueError(f"Unknown objective preset '{name}'. Available: {list(presets)}")
        return presets[name]


def composite_objective(metrics: dict[str, float], weights: ObjectiveWeights) -> float:
    """objective = a*energy + b*revenue + c*efficiency + d*(-lcoe) + e*npv
    + f*grid_value + g*water_security - h*environmental_impact - i*operating_cost

    ``metrics`` should supply whichever of these keys are relevant; missing
    keys are treated as zero.
    """

    def m(key: str) -> float:
        return float(metrics.get(key, 0.0))

    return (
        weights.energy * m("energy")
        + weights.revenue * m("revenue")
        + weights.efficiency * m("efficiency")
        - weights.lcoe * m("lcoe")
        + weights.npv * m("npv")
        + weights.grid_value * m("grid_value")
        + weights.water_security * m("water_security")
        - weights.environmental_impact * m("environmental_impact")
        - weights.operating_cost * m("operating_cost")
    )
