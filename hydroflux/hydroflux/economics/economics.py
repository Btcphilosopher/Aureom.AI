"""
Economic engine: CAPEX/OPEX build-up, LCOE, NPV, IRR, ROI and payback
period, driven by a configurable discount rate, inflation, project
lifetime, financing and degradation assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from scipy.optimize import brentq

from hydroflux.core.config import EconomicConfig


def npv(cashflows: Sequence[float], discount_rate: float) -> float:
    """Net present value of a cashflow series, cashflows[0] at t=0."""

    flows = np.asarray(cashflows, dtype=float)
    years = np.arange(len(flows))
    return float(np.sum(flows / (1 + discount_rate) ** years))


def irr(cashflows: Sequence[float], bracket: tuple[float, float] = (-0.99, 5.0)) -> Optional[float]:
    """Internal rate of return: the discount rate at which NPV = 0, found
    via root-finding (no ``numpy_financial`` dependency)."""

    flows = np.asarray(cashflows, dtype=float)
    if np.all(flows >= 0) or np.all(flows <= 0):
        return None  # no sign change -> IRR undefined

    def f(rate):
        return npv(flows, rate)

    try:
        lo, hi = bracket
        f_lo, f_hi = f(lo), f(hi)
        if f_lo * f_hi > 0:
            return None
        return float(brentq(f, lo, hi))
    except (ValueError, RuntimeError):
        return None


def payback_period(cashflows: Sequence[float]) -> Optional[float]:
    """Simple (undiscounted) payback period in years, with linear
    interpolation within the year the cumulative cashflow turns positive."""

    cumulative = np.cumsum(cashflows)
    positive = np.where(cumulative >= 0)[0]
    if len(positive) == 0:
        return None
    idx = positive[0]
    if idx == 0:
        return 0.0
    prev_cumulative = cumulative[idx - 1]
    step = cumulative[idx] - prev_cumulative
    frac = (-prev_cumulative / step) if step != 0 else 0.0
    return float(idx - 1 + frac)


def lcoe(capex: float, opex_by_year: Sequence[float], generation_mwh_by_year: Sequence[float], discount_rate: float) -> float:
    """Levelised cost of energy: discounted lifetime cost / discounted
    lifetime generation, currency per MWh. ``capex`` is incurred at t=0;
    ``opex_by_year``/``generation_mwh_by_year`` start at year 1."""

    opex = np.asarray(opex_by_year, dtype=float)
    generation = np.asarray(generation_mwh_by_year, dtype=float)
    years = np.arange(1, len(opex) + 1)
    discount = 1.0 / (1 + discount_rate) ** years

    discounted_cost = capex + float(np.sum(opex * discount))
    discounted_generation = float(np.sum(generation * discount))
    if discounted_generation <= 0:
        return float("inf")
    return discounted_cost / discounted_generation


@dataclass
class EconomicResult:
    capex: float
    opex_by_year: np.ndarray
    revenue_by_year: np.ndarray
    generation_by_year_mwh: np.ndarray
    cashflows: np.ndarray
    lcoe_value: float
    npv_value: float
    irr_value: Optional[float]
    roi: float
    payback_years: Optional[float]


class EconomicEngine:
    def __init__(self, assumptions: EconomicConfig):
        self.assumptions = assumptions

    def evaluate(
        self,
        annual_generation_mwh: float,
        annual_price: float,
        opex_variable_per_mwh: Optional[float] = None,
    ) -> EconomicResult:
        """Evaluate project economics assuming a representative constant
        annual generation/price (post-degradation), replicated across the
        project lifetime with configured degradation and inflation."""

        a = self.assumptions
        n_years = a.project_lifetime_years
        years = np.arange(1, n_years + 1)

        degradation = (1 - a.degradation_rate_annual) ** (years - 1)
        generation_by_year = annual_generation_mwh * degradation

        inflation = (1 + a.inflation_rate) ** (years - 1)
        opex_var = opex_variable_per_mwh if opex_variable_per_mwh is not None else a.opex_variable_per_mwh
        opex_by_year = (a.opex_fixed_annual + opex_var * generation_by_year) * inflation

        revenue_by_year = annual_price * generation_by_year * inflation

        capex = a.capex_total
        cashflows = np.concatenate([[-capex], revenue_by_year - opex_by_year])
        if a.replacement_cost and a.replacement_year and 1 <= a.replacement_year <= n_years:
            cashflows[a.replacement_year] -= a.replacement_cost
        cashflows[-1] -= a.decommissioning_cost

        lcoe_value = lcoe(capex, opex_by_year, generation_by_year, a.discount_rate)
        npv_value = npv(cashflows, a.discount_rate)
        irr_value = irr(cashflows)
        total_revenue = float(np.sum(revenue_by_year))
        roi = (total_revenue - float(np.sum(opex_by_year)) - capex) / capex if capex > 0 else float("nan")
        payback = payback_period(cashflows)

        return EconomicResult(
            capex=capex,
            opex_by_year=opex_by_year,
            revenue_by_year=revenue_by_year,
            generation_by_year_mwh=generation_by_year,
            cashflows=cashflows,
            lcoe_value=lcoe_value,
            npv_value=npv_value,
            irr_value=irr_value,
            roi=roi,
            payback_years=payback,
        )

    def evaluate_from_series(self, generation_mwh_by_year: Sequence[float], revenue_by_year: Sequence[float]) -> EconomicResult:
        """Evaluate economics from explicit per-year generation/revenue
        series (e.g. built from a multi-year simulation with real annual
        variation) instead of a single representative year."""

        a = self.assumptions
        generation = np.asarray(generation_mwh_by_year, dtype=float)
        revenue = np.asarray(revenue_by_year, dtype=float)
        n_years = len(generation)
        years = np.arange(1, n_years + 1)
        inflation = (1 + a.inflation_rate) ** (years - 1)
        opex_by_year = (a.opex_fixed_annual + a.opex_variable_per_mwh * generation) * inflation

        capex = a.capex_total
        cashflows = np.concatenate([[-capex], revenue - opex_by_year])
        cashflows[-1] -= a.decommissioning_cost

        lcoe_value = lcoe(capex, opex_by_year, generation, a.discount_rate)
        npv_value = npv(cashflows, a.discount_rate)
        irr_value = irr(cashflows)
        roi = (float(np.sum(revenue)) - float(np.sum(opex_by_year)) - capex) / capex if capex > 0 else float("nan")
        payback = payback_period(cashflows)

        return EconomicResult(
            capex=capex,
            opex_by_year=opex_by_year,
            revenue_by_year=revenue,
            generation_by_year_mwh=generation,
            cashflows=cashflows,
            lcoe_value=lcoe_value,
            npv_value=npv_value,
            irr_value=irr_value,
            roi=roi,
            payback_years=payback,
        )
