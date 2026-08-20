"""
Multi-turbine dispatch: given a fleet and an available flow/head, decide how
many turbines to commit and how to split flow between them.

Running every turbine at a fraction of full load is often *less* efficient
than committing fewer machines closer to their best efficiency point (see
specification section 10). Two strategies are provided:

* ``exact=True`` -- combinatorial search over turbine commitment subsets
  (feasible for small fleets, e.g. <= 8 units) with a constrained
  continuous optimisation of the flow split within each subset. Used for
  one-off "what is the optimal dispatch here" queries.
* ``exact=False`` (default) -- a fast merit-order heuristic that commits
  turbines in order of full-load efficiency and gives each its own best
  operating point out of the remaining flow. Used inside full time-series
  simulations where the exact search would be too slow to call every
  timestep.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.optimize import minimize

from hydroflux.turbines.turbines import Turbine


@dataclass
class DispatchResult:
    turbine_flows: dict[str, float] = field(default_factory=dict)
    turbine_powers: dict[str, float] = field(default_factory=dict)
    total_power_mw: float = 0.0
    total_flow_m3s: float = 0.0
    spill_m3s: float = 0.0
    committed_turbines: list[str] = field(default_factory=list)


def _empty_result(turbines: list[Turbine], available_flow_m3s: float) -> DispatchResult:
    return DispatchResult(
        turbine_flows={t.id: 0.0 for t in turbines},
        turbine_powers={t.id: 0.0 for t in turbines},
        total_power_mw=0.0,
        total_flow_m3s=0.0,
        spill_m3s=max(available_flow_m3s, 0.0),
        committed_turbines=[],
    )


def _split_within_subset(subset: tuple[Turbine, ...], available_flow_m3s: float, head_m: float) -> Optional[tuple[dict, float]]:
    min_total = sum(t.minimum_flow_m3s for t in subset)
    if min_total > available_flow_m3s:
        return None

    x0 = np.array(
        [min(t.rated_flow_m3s, available_flow_m3s / len(subset)) for t in subset], dtype=float
    )
    x0 = np.maximum(x0, [t.minimum_flow_m3s for t in subset])
    bounds = [(t.minimum_flow_m3s, min(t.maximum_flow_m3s, available_flow_m3s)) for t in subset]

    def neg_power(x):
        return -sum(t.output_power_mw(q, head_m) for t, q in zip(subset, x))

    constraints = [{"type": "ineq", "fun": lambda x: available_flow_m3s - np.sum(x)}]
    result = minimize(neg_power, x0, method="SLSQP", bounds=bounds, constraints=constraints)
    flows = {t.id: max(float(q), 0.0) for t, q in zip(subset, result.x)}
    total_power = -float(result.fun)
    return flows, total_power


def _exact_dispatch(turbines: list[Turbine], available_flow_m3s: float, head_m: float) -> DispatchResult:
    best: Optional[tuple[dict, float]] = None
    for r in range(1, len(turbines) + 1):
        for subset in itertools.combinations(turbines, r):
            outcome = _split_within_subset(subset, available_flow_m3s, head_m)
            if outcome is None:
                continue
            flows, total_power = outcome
            if best is None or total_power > best[1]:
                best = (flows, total_power)

    if best is None:
        return _empty_result(turbines, available_flow_m3s)

    flows, total_power = best
    result = DispatchResult(
        turbine_flows={t.id: flows.get(t.id, 0.0) for t in turbines},
        turbine_powers={
            t.id: t.output_power_mw(flows.get(t.id, 0.0), head_m) if flows.get(t.id, 0.0) > 0 else 0.0
            for t in turbines
        },
    )
    result.total_flow_m3s = sum(result.turbine_flows.values())
    result.total_power_mw = sum(result.turbine_powers.values())
    result.spill_m3s = max(available_flow_m3s - result.total_flow_m3s, 0.0)
    result.committed_turbines = [tid for tid, q in result.turbine_flows.items() if q > 0]
    return result


def _greedy_dispatch(turbines: list[Turbine], available_flow_m3s: float, head_m: float) -> DispatchResult:
    # Bring the most efficient machine at full load online first.
    ordered = sorted(
        turbines,
        key=lambda t: t.output_power_mw(t.rated_flow_m3s, head_m) / max(t.rated_flow_m3s, 1e-9),
        reverse=True,
    )
    remaining = available_flow_m3s
    flows: dict[str, float] = {}
    powers: dict[str, float] = {}
    for turbine in ordered:
        flow, power = turbine.best_operating_point(remaining, head_m)
        flows[turbine.id] = flow
        powers[turbine.id] = power
        remaining -= flow

    result = DispatchResult(
        turbine_flows={t.id: flows.get(t.id, 0.0) for t in turbines},
        turbine_powers={t.id: powers.get(t.id, 0.0) for t in turbines},
    )
    result.total_flow_m3s = sum(result.turbine_flows.values())
    result.total_power_mw = sum(result.turbine_powers.values())
    result.spill_m3s = max(remaining, 0.0)
    result.committed_turbines = [tid for tid, q in result.turbine_flows.items() if q > 0]
    return result


def optimise_dispatch(
    turbines: list[Turbine],
    available_flow_m3s: float,
    head_m: float,
    exact: bool = False,
) -> DispatchResult:
    """Optimise flow allocation and unit commitment across a turbine fleet.

    Returns a :class:`DispatchResult` giving each turbine's flow, power,
    the total power/flow, spilled flow (available flow no turbine could
    usefully absorb), and which turbines were committed.
    """

    if not turbines or available_flow_m3s <= 0 or head_m <= 0:
        return _empty_result(turbines, available_flow_m3s)

    if exact and len(turbines) <= 8:
        return _exact_dispatch(turbines, available_flow_m3s, head_m)
    return _greedy_dispatch(turbines, available_flow_m3s, head_m)
