"""Factory profitability model (spec item 43)."""
from __future__ import annotations

from dataclasses import dataclass

from batteryfactory.economics.capex_opex import CapexInputs, OpexInputs


@dataclass
class FinancialResult:
    revenue: float
    cogs: float
    gross_profit: float
    gross_margin_pct: float
    ebitda: float
    ebit: float
    cash_flow: float


class FactoryFinancials:
    def compute(
        self,
        selling_price_per_kwh: float,
        annual_kwh_sold: float,
        opex: OpexInputs,
        capex: CapexInputs,
        cogs_excludes_depreciation: bool = True,
    ) -> FinancialResult:
        revenue = selling_price_per_kwh * annual_kwh_sold
        cogs = opex.materials + opex.electricity + opex.labour + opex.maintenance + opex.logistics + opex.consumables + opex.waste
        gross_profit = revenue - cogs
        gross_margin_pct = 100.0 * gross_profit / revenue if revenue > 0 else 0.0

        ebitda = gross_profit  # no separate SG&A modelled at this level of abstraction
        ebit = ebitda - capex.annual_depreciation
        # Cash flow adds back the non-cash depreciation charge.
        cash_flow = ebit + capex.annual_depreciation

        return FinancialResult(
            revenue=revenue, cogs=cogs, gross_profit=gross_profit, gross_margin_pct=gross_margin_pct,
            ebitda=ebitda, ebit=ebit, cash_flow=cash_flow,
        )

    def sensitivity(self, base_price: float, base_volume_kwh: float, opex: OpexInputs, capex: CapexInputs,
                     price_multipliers: list[float], volume_multipliers: list[float]) -> list[dict]:
        rows = []
        for pm in price_multipliers:
            for vm in volume_multipliers:
                result = self.compute(base_price * pm, base_volume_kwh * vm, opex, capex)
                rows.append({"price_multiplier": pm, "volume_multiplier": vm, "ebitda": result.ebitda, "gross_margin_pct": result.gross_margin_pct})
        return rows
