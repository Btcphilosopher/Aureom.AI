"""
Generic turbine engine: Kaplan, Francis, Pelton, bulb, tidal-stream and
custom turbines, all expressed through the same envelope + efficiency-curve
model so :mod:`hydroflux.turbines.dispatch` and the reservoir/tidal
optimisers never need to know which turbine family they are scheduling.

Efficiency is never assumed constant: :class:`EfficiencyCurve` maps flow
fraction (and, optionally, head fraction relative to design head) to total
turbine efficiency, giving the two-dimensional flow/head efficiency surface
requested by the specification without requiring a full multi-dimensional
lookup table when only a 1-D curve is available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

import numpy as np

from hydroflux.core.config import TurbineConfig, TurbineType
from hydroflux.hydraulics.hydraulics import electrical_power

ArrayLike = Union[float, np.ndarray]

# Generic head-derating curve: turbines lose efficiency operating away from
# their design head. head_fraction = actual_head / design_head.
_DEFAULT_HEAD_FRACTION = np.array([0.5, 0.65, 0.8, 0.9, 1.0, 1.1, 1.25, 1.4])
_DEFAULT_HEAD_DERATE = np.array([0.65, 0.80, 0.92, 0.98, 1.0, 0.99, 0.94, 0.85])

_TYPE_CURVES = {
    TurbineType.KAPLAN: (
        np.array([0.0, 0.15, 0.25, 0.4, 0.6, 0.8, 1.0, 1.1]),
        np.array([0.0, 0.55, 0.75, 0.86, 0.91, 0.93, 0.92, 0.90]),
    ),
    TurbineType.BULB: (
        np.array([0.0, 0.15, 0.25, 0.4, 0.6, 0.8, 1.0, 1.1]),
        np.array([0.0, 0.52, 0.72, 0.84, 0.90, 0.92, 0.91, 0.89]),
    ),
    TurbineType.FRANCIS: (
        np.array([0.0, 0.2, 0.35, 0.5, 0.7, 0.85, 1.0, 1.1]),
        np.array([0.0, 0.40, 0.65, 0.80, 0.89, 0.93, 0.94, 0.91]),
    ),
    TurbineType.PELTON: (
        np.array([0.0, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0, 1.1]),
        np.array([0.0, 0.70, 0.82, 0.88, 0.91, 0.92, 0.90, 0.87]),
    ),
    TurbineType.TIDAL_STREAM: (
        np.array([0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.1]),
        np.array([0.0, 0.30, 0.60, 0.80, 0.90, 0.90, 0.85]),
    ),
    TurbineType.CUSTOM: (
        np.array([0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.1]),
        np.array([0.0, 0.50, 0.75, 0.85, 0.90, 0.90, 0.88]),
    ),
}


@dataclass
class EfficiencyCurve:
    """flow -> efficiency, with an optional head -> derating factor.

    ``flow_fraction`` and ``efficiency`` define the primary 1-D curve
    (flow as a fraction of rated flow). ``head_fraction`` /
    ``head_derate`` define an optional second curve applied multiplicatively,
    which together form a lightweight flow x head efficiency surface. When
    richer multi-dimensional data is available, replace ``efficiency_at``
    with a ``scipy.interpolate.RegularGridInterpolator`` lookup -- the
    ``Turbine`` contract (``efficiency_curve.efficiency_at(flow_fraction,
    head_fraction)``) stays the same.
    """

    flow_fraction: np.ndarray
    efficiency: np.ndarray
    head_fraction: Optional[np.ndarray] = None
    head_derate: Optional[np.ndarray] = None

    def efficiency_at(self, flow_fraction: ArrayLike, head_fraction: Optional[ArrayLike] = None) -> ArrayLike:
        flow_fraction = np.clip(np.asarray(flow_fraction, dtype=float), 0.0, self.flow_fraction[-1])
        eta = np.interp(flow_fraction, self.flow_fraction, self.efficiency)
        if head_fraction is not None and self.head_fraction is not None:
            hf = np.clip(
                np.asarray(head_fraction, dtype=float),
                self.head_fraction[0],
                self.head_fraction[-1],
            )
            derate = np.interp(hf, self.head_fraction, self.head_derate)
            eta = eta * derate
        return eta


def default_efficiency_curve(turbine_type: TurbineType) -> EfficiencyCurve:
    flow_fraction, efficiency = _TYPE_CURVES.get(turbine_type, _TYPE_CURVES[TurbineType.CUSTOM])
    return EfficiencyCurve(
        flow_fraction=flow_fraction.copy(),
        efficiency=efficiency.copy(),
        head_fraction=_DEFAULT_HEAD_FRACTION.copy(),
        head_derate=_DEFAULT_HEAD_DERATE.copy(),
    )


@dataclass
class Turbine:
    id: str
    type: TurbineType
    rated_power_mw: float
    rated_flow_m3s: float
    minimum_flow_m3s: float
    maximum_flow_m3s: float
    minimum_head_m: float
    maximum_head_m: Optional[float]
    efficiency_curve: EfficiencyCurve
    generator_efficiency: float = 0.98
    transmission_efficiency: float = 0.99
    availability: float = 0.97
    design_head_m: Optional[float] = None
    maintenance_windows: list = field(default_factory=list)

    def __post_init__(self):
        if self.design_head_m is None:
            peak_eta = float(np.max(self.efficiency_curve.efficiency))
            from hydroflux.hydraulics.hydraulics import G, RHO_WATER

            self.design_head_m = (self.rated_power_mw * 1e6) / (
                RHO_WATER * G * self.rated_flow_m3s * max(peak_eta, 1e-3)
            )

    def efficiency(self, flow_m3s: ArrayLike, head_m: ArrayLike) -> ArrayLike:
        flow_fraction = np.asarray(flow_m3s, dtype=float) / self.rated_flow_m3s
        head_fraction = np.asarray(head_m, dtype=float) / self.design_head_m
        return self.efficiency_curve.efficiency_at(flow_fraction, head_fraction)

    def output_power_mw(self, flow_m3s: ArrayLike, head_m: ArrayLike) -> ArrayLike:
        """Electrical power delivered at the given flow/head, respecting the
        turbine's operating envelope. Availability (planned/forced outage) is
        applied by the dispatcher/simulation loop, not baked into this pure
        physics call.
        """

        flow = np.asarray(flow_m3s, dtype=float)
        head = np.asarray(head_m, dtype=float)
        eta = self.efficiency(flow, head)
        power_w = electrical_power(flow, head, eta, self.generator_efficiency, self.transmission_efficiency)
        power_mw = power_w / 1e6

        below_min_flow = flow < self.minimum_flow_m3s
        below_min_head = head < self.minimum_head_m
        above_max_head = np.zeros_like(head, dtype=bool) if self.maximum_head_m is None else head > self.maximum_head_m
        invalid = below_min_flow | below_min_head | above_max_head
        power_mw = np.where(invalid, 0.0, power_mw)
        return power_mw if power_mw.ndim else float(power_mw)

    def best_operating_point(self, available_flow_m3s: float, head_m: float, n_grid: int = 25) -> tuple[float, float]:
        """Find the flow within [min_flow, min(max_flow, available_flow)]
        that maximises this turbine's electrical output at the given head.

        Returns (flow_m3s, power_mw). If ``available_flow_m3s`` is below the
        minimum operable flow, or head is outside the turbine's envelope,
        returns (0.0, 0.0).

        Uses a vectorised grid search (rather than an iterative scalar
        optimiser) so it stays cheap when called once per turbine per
        timestep across a long time-series simulation -- the efficiency
        curves involved are simple piecewise-linear interpolations, so a
        ~25-point grid is already within a fraction of a percent of the
        true optimum.
        """

        upper = min(self.maximum_flow_m3s, available_flow_m3s)
        if upper < self.minimum_flow_m3s or head_m < self.minimum_head_m:
            return 0.0, 0.0
        if self.maximum_head_m is not None and head_m > self.maximum_head_m:
            return 0.0, 0.0

        candidates = np.linspace(self.minimum_flow_m3s, upper, n_grid)
        powers = self.output_power_mw(candidates, head_m)
        best_idx = int(np.argmax(powers))
        return float(candidates[best_idx]), float(powers[best_idx])


def make_turbine_from_config(config: TurbineConfig) -> Turbine:
    if config.efficiency_curve.flow_fraction and config.efficiency_curve.efficiency:
        curve = EfficiencyCurve(
            flow_fraction=np.array(config.efficiency_curve.flow_fraction, dtype=float),
            efficiency=np.array(config.efficiency_curve.efficiency, dtype=float),
            head_fraction=_DEFAULT_HEAD_FRACTION.copy(),
            head_derate=_DEFAULT_HEAD_DERATE.copy(),
        )
    else:
        curve = default_efficiency_curve(config.type)

    return Turbine(
        id=config.id,
        type=config.type,
        rated_power_mw=config.rated_power_mw,
        rated_flow_m3s=config.rated_flow_m3s,
        minimum_flow_m3s=config.minimum_flow_m3s,
        maximum_flow_m3s=config.maximum_flow_m3s,
        minimum_head_m=config.minimum_head_m,
        maximum_head_m=config.maximum_head_m,
        efficiency_curve=curve,
        generator_efficiency=config.generator_efficiency,
        transmission_efficiency=config.transmission_efficiency,
        availability=config.availability,
        maintenance_windows=list(config.maintenance_windows),
    )
