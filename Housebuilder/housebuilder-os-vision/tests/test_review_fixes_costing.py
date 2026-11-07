"""Regression tests for the review findings on rates, the cost engine and repeat-build economics (group C).

COST-1 working-time conversion of day / week rates; COST-2 step events and the underlying marginal;
COST-3 development fee base and one-off fees; COST-4 factory steps and site logistics overlap; COST-5
order-level material pricing and re-rounding for n houses; COST-6 delivery treatment of every rate used;
COST-7 time-related site overhead and the single-house reconciliation; COST-8 honest fallback inputs in
the UI; COST-9 timber-frame variant for the illustrative off-site scenario; COST-10 escalation / regional
factor / basis / location matching; COST-11 pricing date; COST-12 unit vs cumulative-average learning.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from housebuilder_vision import pipeline as P
from housebuilder_vision.core.models import (
    AssemblyLibrary,
    BillOfQuantities,
    CostLayer,
    CostParameters,
    DeliveryTreatment,
    DiscountTier,
    FeeItem,
    GeometryMetrics,
    LearningCurve,
    LogisticsResult,
    ProductionScenario,
    QuantityLine,
    QuantityStatus,
    Rate,
    RateBook,
    RateSourceType,
    StepCost,
)
from housebuilder_vision.core.provenance import Basis
from housebuilder_vision.core.settings import ProjectSettings
from housebuilder_vision.core.units import (
    convert,
    convert_working_time_rate,
    is_working_time_pair,
    working_time_hours,
)
from housebuilder_vision.costing import (
    COST_PARAMETER_FALLBACKS,
    PRICING_DATE_WARNING,
    UNDERLYING_MARGINAL_DEFINITION,
    calculate_incremental_cost,
    comparison_table,
    component_curves,
    estimate_construction_cost,
    factory_vs_installed,
    learning_factors,
    resolve_rate,
    resolve_rate_detailed,
    single_house_reconciliation,
    site_logistics_for,
)
from housebuilder_vision.demo.build_demo import DEMO_PRICING_DATE, build_demo_project

PDATE = date(2026, 11, 1)
EFF = date(2026, 10, 1)
S = ProjectSettings(pricing_date=PDATE)


def settings(**kw) -> ProjectSettings:
    kw.setdefault("pricing_date", PDATE)
    return ProjectSettings(**kw)


def rate(rid, key, unit, value, **kw) -> Rate:
    layer = {"mat": CostLayer.MATERIALS, "allow": CostLayer.MATERIALS, "lab": CostLayer.LABOUR,
             "plant": CostLayer.PLANT, "log": CostLayer.LOGISTICS_WASTE,
             "prelim": CostLayer.PRELIMINARIES}[key.split(":")[0]]
    base = dict(rate_id=rid, cost_key=key, layer=layer, unit=unit, value=value, effective_date=EFF,
                source="FICTIONAL test rate", source_type=RateSourceType.MANUAL, location="Exampleton (fictional)",
                delivery_treatment=DeliveryTreatment.DELIVERED_INCLUDED)
    base.update(kw)
    return Rate(**base)


def metrics(**over) -> GeometryMetrics:
    vals = {}
    for name, f in GeometryMetrics.model_fields.items():
        if f.is_required():
            vals[name] = [] if name in ("blocks", "pieces", "storeys", "roofs") else 0.0
    vals.update(external_wall_gross_m2=100.0, gia_m2=80.0)
    vals.update(over)
    return GeometryMetrics(**vals)


def mline(line_id, cost_key, installed, *, ppi=1.0, pack=1.0, unit="m2", purchase_unit="board", material_id=None,
          trade="general", hours=0.0, status=QuantityStatus.DERIVED) -> QuantityLine:
    """A material line with its own per-line pack rounding (as the take-off produces it)."""
    need = installed * ppi
    packs = math.ceil(need / pack - 1e-9)
    return QuantityLine(line_id=line_id, element_code=line_id.split(".")[0], element_name="test",
                        description=f"line {line_id}", status=status, cost_key=cost_key, unit=unit,
                        installed_qty=installed, required_qty=installed, purchase_unit=purchase_unit,
                        purchase_per_installed=ppi, pack_size=pack, packs=packs, purchased_qty=packs * pack,
                        surplus_qty=packs * pack - need, material_id=material_id, trade=trade, labour_hours=hours)


def qline(line_id, cost_key, unit, qty, *, trade="general", hours=0.0, status=QuantityStatus.DERIVED) -> QuantityLine:
    return QuantityLine(line_id=line_id, element_code=line_id.split(".")[0], element_name="test",
                        description=f"line {line_id}", status=status, cost_key=cost_key, unit=unit,
                        installed_qty=qty, required_qty=qty, purchase_unit=unit, purchased_qty=qty, trade=trade,
                        labour_hours=hours)


def boq(*lines) -> BillOfQuantities:
    return BillOfQuantities(twin_id="t", twin_version=1, library_name="tiny", lines=list(lines), geometry=metrics())


BASE_RATES = [
    rate("r-gen", "lab:general", "hr", 30.0), rate("r-setup", "prelim:setup", "sum", 5000.0),
    rate("r-week", "prelim:weekly", "week", 1000.0), rate("r-load", "log:delivery_load", "load", 80.0),
    rate("r-skip", "log:skip", "nr", 300.0), rate("r-tele", "plant:telehandler", "week", 500.0),
    rate("r-scaf", "plant:scaffold", "m2_week", 2.0),
]
LOGI = LogisticsResult(batches=[], total_loads=2, total_mass_t=1.0, peak_storage_area_m2=5.0, waste_volume_m3=0.0,
                       skips=0)
PARAMS = CostParameters(fees=[], contingency_fraction=0.0, overhead_fraction=0.0, margin_fraction=0.0)


def estimate(b: BillOfQuantities, *extra: Rate, params=PARAMS, st=S, library=None, weeks=10.0):
    book = RateBook(name="t", rates=list(BASE_RATES) + list(extra))
    return estimate_construction_cost(b, book, params, settings=st, programme_weeks=weeks, logistics=LOGI,
                                      library=library or AssemblyLibrary(name="tiny", materials=[]))


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    store = tmp_path_factory.mktemp("store")
    project = build_demo_project(store)
    result = P.run_pipeline(project, store_dir=store, simulate=False, n_samples=0)
    return project, result


# =============================================================================
# COST-1 working time
# =============================================================================
def test_units_working_time_helpers_keep_calendar_convert():
    assert convert(1.0, "day", "hr") == 24.0 and convert(1.0, "week", "hr") == 168.0  # calendar is unchanged
    assert working_time_hours("day") == 8.0 and working_time_hours("week") == 40.0
    assert working_time_hours("week", hours_per_working_day=7.5, working_days_per_week=4) == 30.0
    assert convert_working_time_rate(300.0, "day", "hr") == pytest.approx(37.5)
    assert convert_working_time_rate(105.0, "day", "week") == pytest.approx(525.0)
    assert convert_working_time_rate(1200.0, "week", "hr") == pytest.approx(30.0)
    assert is_working_time_pair("day", "hr") and not is_working_time_pair("hr", "min")
    assert not is_working_time_pair("day", "m2") and not is_working_time_pair("week", "week")


def test_day_and_week_rates_of_time_based_keys_are_working_time():
    book = RateBook(name="d", rates=[rate("BL1", "lab:bricklaying", "day", 300.0),
                                     rate("TH1", "plant:telehandler", "day", 105.0),
                                     rate("EX1", "plant:excavator", "week", 1200.0),
                                     rate("PW1", "prelim:weekly", "day", 330.0),
                                     rate("SK1", "log:skip_hire", "week", 70.0)])
    rr = resolve_rate_detailed(book, "lab:bricklaying", "hr", settings=S)
    assert rr.value == pytest.approx(37.5) and rr.working_time and rr.basis == Basis.ASSUMED
    assert any("working time" in w and "8 h per working day" in w for w in rr.warnings)
    assert resolve_rate_detailed(book, "plant:telehandler", "week", settings=S).value == pytest.approx(525.0)
    assert resolve_rate_detailed(book, "plant:excavator", "hr", settings=S).value == pytest.approx(30.0)
    assert resolve_rate_detailed(book, "prelim:weekly", "week", settings=S).value == pytest.approx(1650.0)
    # the working pattern is a labelled setting
    s75 = settings(hours_per_working_day=7.5)
    assert resolve_rate_detailed(book, "lab:bricklaying", "hr", settings=s75).value == pytest.approx(40.0)
    # other cost keys keep calendar time (a skip hired per week = 7 calendar days)
    assert resolve_rate_detailed(book, "log:skip_hire", "day", settings=S).value == pytest.approx(10.0)
    # resolve_rate() surfaces the conversion in its warnings
    _, v, w = resolve_rate(book, "lab:bricklaying", "hr", settings=S)
    assert v == pytest.approx(37.5) and any(a.startswith("per day -> per hr") for a in w)


def test_engine_prices_a_day_rate_on_working_hours_with_a_warning():
    b = boq(qline("2.5.x.0", None, "nr", 0.0, trade="bricklaying", hours=20.0))
    est = estimate(b, rate("BL1", "lab:bricklaying", "day", 320.0))
    lab = next(ln for ln in est.lines if ln.cost_key == "lab:bricklaying")
    assert lab.rate_value == pytest.approx(40.0) and lab.amount == pytest.approx(800.0)
    assert lab.basis == Basis.ASSUMED and "working time" in lab.formula
    assert any("working time" in w for w in est.warnings) and est.unresolved_items == []


# =============================================================================
# COST-10 escalation, regional factor, basis, location matching
# =============================================================================
def test_firm_quotes_are_not_escalated_and_assumed_factors_weaken_the_basis():
    q = rate("Q", "mat:x", "nr", 0.72, source_type="supplier_quote", valid_until=date(2026, 12, 31))
    old = rate("O", "mat:y", "nr", 100.0, effective_date=date(2025, 11, 1))
    s = settings(annual_escalation_rate=0.10)
    rq = resolve_rate_detailed(RateBook(name="q", rates=[q]), "mat:x", "nr", settings=s)
    assert rq.value == pytest.approx(0.72) and rq.escalation_factor == 1.0 and rq.basis == Basis.USER_CONFIRMED
    assert any(a.startswith("not escalated") for a in rq.adjustments)
    ro = resolve_rate_detailed(RateBook(name="o", rates=[old]), "mat:y", "nr", settings=s)
    assert ro.value == pytest.approx(100 * 1.10 ** (365 / 365.25)) and ro.basis == Basis.ASSUMED  # manual -> assumed
    # VAT stripped at the project rate is an assumption too; a VAT rate on the quote is not
    v1 = rate("V1", "mat:v", "nr", 120.0, tax_treatment="inc_vat")
    v2 = rate("V2", "mat:w", "nr", 120.0, tax_treatment="inc_vat", vat_rate=0.2)
    book = RateBook(name="v", rates=[v1, v2])
    assert resolve_rate_detailed(book, "mat:v", "nr", settings=S).basis == Basis.ASSUMED
    assert resolve_rate_detailed(book, "mat:w", "nr", settings=S).basis == Basis.USER_CONFIRMED
    # fx alone does not weaken the basis
    e = rate("E", "mat:e", "nr", 10.0, currency="EUR")
    assert resolve_rate_detailed(RateBook(name="e", rates=[e]), "mat:e", "nr",
                                 settings=settings(fx_rates={"EUR": 0.85})).basis == Basis.USER_CONFIRMED


def test_regional_factor_location_matching_and_blank_location_quotes():
    s = settings(regional_cost_factor=1.25)
    blank_q = rate("BQ", "mat:a", "nr", 0.70, source_type="supplier_quote", location="", valid_until=date(2027, 1, 1))
    blank_m = rate("BM", "mat:b", "nr", 100.0, location="")
    lane = rate("LN", "mat:c", "nr", 100.0, location="Lane")
    local = rate("LC", "mat:d", "nr", 100.0, location="exampleton  (Fictional)")
    region = rate("RG", "mat:e", "nr", 100.0, location="England (fictional demo region)")
    book = RateBook(name="r", rates=[blank_q, blank_m, lane, local, region])
    rq = resolve_rate_detailed(book, "mat:a", "nr", settings=s)
    assert rq.value == pytest.approx(0.70) and rq.basis == Basis.USER_CONFIRMED
    assert any("no location" in w and "treated as quoted for the project site" in w for w in rq.warnings)
    rb = resolve_rate_detailed(book, "mat:b", "nr", settings=s)
    assert rb.value == pytest.approx(125.0) and rb.basis == Basis.ASSUMED
    rl = resolve_rate_detailed(book, "mat:c", "nr", settings=s)  # 'Lane' is only a substring of the site
    assert rl.value == pytest.approx(125.0) and rl.regional_factor == 1.25
    assert resolve_rate_detailed(book, "mat:d", "nr", settings=s).value == pytest.approx(100.0)
    assert resolve_rate_detailed(book, "mat:e", "nr", settings=s).value == pytest.approx(100.0)


# =============================================================================
# COST-11 pricing date
# =============================================================================
def test_pricing_date_defaults_to_today_and_the_demo_is_pinned(demo):
    assert ProjectSettings().pricing_date == date.today()
    project, result = demo
    assert DEMO_PRICING_DATE == date(2026, 11, 1)
    assert project.settings.pricing_date == DEMO_PRICING_DATE and result.estimate.pricing_date == DEMO_PRICING_DATE


def test_newer_higher_priority_rate_excluded_by_the_pricing_date_is_flagged_prominently():
    demo_rate = rate("FD-M", "mat:mortar", "m3", 138.0, source_type="fictional_demo",
                     source="FICTIONAL DEMO RATE - not market data")
    newq = rate("REALQ", "mat:mortar", "m3", 150.0, source_type="supplier_quote", effective_date=date(2026, 11, 6),
                valid_until=date(2027, 2, 1), source="Supplier quote")
    same = rate("FD-NEW", "mat:mortar", "m3", 140.0, source_type="fictional_demo", effective_date=date(2026, 11, 5),
                source="FICTIONAL DEMO RATE - not market data")
    book = RateBook(name="m", rates=[demo_rate, newq, same])
    rr = resolve_rate_detailed(book, "mat:mortar", "m3", settings=S)
    assert rr.rate.rate_id == "FD-M" and rr.excluded_newer == ("REALQ",)  # same-priority FD-NEW is not flagged
    assert rr.warnings[0].startswith(PRICING_DATE_WARNING) and "FICTIONAL" in rr.warnings[0]
    b = boq(mline("1.x.0", "mat:mortar", 1.0, unit="m3", purchase_unit="m3"))
    est = estimate(b, demo_rate, newq)
    assert est.warnings[0].startswith(PRICING_DATE_WARNING) and "REALQ for mat:mortar -> FD-M (FICTIONAL)" in \
        est.warnings[0]
    # once the pricing date reaches the quote, it is used and nothing is flagged
    rr2 = resolve_rate_detailed(book, "mat:mortar", "m3", settings=settings(pricing_date=date(2026, 11, 7)))
    assert rr2.rate.rate_id == "REALQ" and rr2.excluded_newer == ()


# =============================================================================
# COST-5 order-level materials
# =============================================================================
def test_materials_are_priced_per_order_and_allocated_to_lines():
    lines = [mline("1.a.pir.0", "mat:pir", 4.0, ppi=1 / 2.88, pack=24.0, material_id="pir"),
             mline("1.b.pir.0", "mat:pir", 4.064, ppi=1 / 2.88, pack=24.0, material_id="pir")]
    est = estimate(boq(*lines), rate("R-PIR", "mat:pir", "board", 16.5))
    mat = [ln for ln in est.lines if ln.layer == CostLayer.MATERIALS]
    need = (4.0 + 4.064) / 2.88
    assert len(mat) == 2 and {ln.quantity_line_id for ln in mat} == {"1.a.pir.0", "1.b.pir.0"}
    assert sum(ln.amount for ln in mat) == pytest.approx(24 * 16.5)  # one pack for the order (per line: two packs)
    assert sum(ln.quantity for ln in mat) == pytest.approx(24.0)
    a = next(ln for ln in mat if ln.quantity_line_id == "1.a.pir.0")
    assert a.quantity == pytest.approx(24.0 * (4.0 / 2.88) / need)
    assert "share" in a.formula and "ceil(" in a.formula and "1 packs" in a.formula
    (o,) = est.material_orders
    assert (o.cost_key, o.packs, o.purchased, o.rate_id) == ("mat:pir", 1, 24.0, "R-PIR")
    assert o.purchase_required == pytest.approx(need) and o.line_level_purchased == 48.0
    assert o.amount == pytest.approx(est.layer_totals[CostLayer.MATERIALS.value])
    assert any("per order" in n for n in est.notes)


def test_repeat_build_re_rounds_orders_for_n_houses():
    lines = [mline("1.a.pir.0", "mat:pir", 4.0, ppi=1 / 2.88, pack=24.0, material_id="pir"),
             mline("1.b.pir.0", "mat:pir", 4.064, ppi=1 / 2.88, pack=24.0, material_id="pir"),
             qline("4.allow.kitchen", "allow:kitchen", "nr", 1.0, status=QuantityStatus.ALLOWANCE)]
    est = estimate(boq(*lines), rate("R-PIR", "mat:pir", "board", 16.5), rate("K", "allow:kitchen", "nr", 5000.0))
    sc = ProductionScenario(scenario_id="s", name="s", site_establishment_per_site=0.0, site_labour_hours_per_house=0.0,
                            learning=LearningCurve(learning_rate=1.0))
    mats = component_curves(est, sc, 30)["materials_site"]
    need = (4.0 + 4.064) / 2.88
    for n in (1, 2, 8, 9, 30):
        assert mats[n - 1] == pytest.approx(math.ceil(n * need / 24 - 1e-9) * 24 * 16.5 + n * 5000.0)
    assert mats[29] < 30 * est.layer_totals[CostLayer.MATERIALS.value]  # the single-house surplus is not x n
    # a scenario value without order data stays linear in n; with orders it is re-rounded
    lin = sc.model_copy(update={"materials_per_house": 5396.0})
    assert component_curves(est, lin, 30)["materials_site"][29] == pytest.approx(30 * 5396.0)
    rr = sc.model_copy(update={"materials_per_house": 5396.0, "material_orders": est.material_orders})
    assert component_curves(est, rr, 30)["materials_site"][29] == pytest.approx(mats[29])


def test_demo_layer1_is_order_level(demo):
    _, result = demo
    est = result.estimate
    orders = est.material_orders
    assert orders and all(o.packs * o.pack_size == pytest.approx(o.purchased) for o in orders if o.pack_size > 0)
    allow = sum(ln.amount for ln in est.lines if ln.layer == CostLayer.MATERIALS and (ln.cost_key or "").startswith(
        "allow:"))
    assert est.layer_totals[CostLayer.MATERIALS.value] == pytest.approx(sum(o.amount for o in orders) + allow)
    assert sum(o.line_level_purchased * o.rate_value for o in orders) > sum(o.amount for o in orders)
    ties = next(o for o in orders if o.material_id == "wall_ties")
    assert ties.purchased == ties.packs * 250 and len(ties.line_ids) > 1
    priced = {ln.quantity_line_id for ln in est.lines if ln.layer == CostLayer.MATERIALS}
    assert set(ties.line_ids) <= priced


# =============================================================================
# COST-6 delivery treatment of every rate used
# =============================================================================
def test_delivery_treatment_applies_to_allowances_plant_and_collection():
    b = boq(qline("4.allow.kitchen", "allow:kitchen", "nr", 1.0, status=QuantityStatus.ALLOWANCE),
            qline("4.allow.staircase", "allow:staircase", "nr", 1.0, status=QuantityStatus.ALLOWANCE),
            mline("1.m.0", "mat:mortar", 1.0, unit="m3", purchase_unit="m3"),
            mline("1.s.0", "mat:sand", 1.0, unit="t", purchase_unit="t"))
    extra = [rate("K1", "allow:kitchen", "nr", 6000.0, delivery_treatment="delivery_charged_separately",
                  delivery_charge=400.0),
             rate("ST1", "allow:staircase", "nr", 1600.0, delivery_treatment="ex_works"),
             # dated after the fixture's own plant rates, so these are the ones used
             rate("SC1", "plant:scaffold", "m2_week", 2.0, delivery_treatment="delivery_charged_separately",
                  delivery_charge=600.0, effective_date=date(2026, 10, 15)),
             rate("TH1", "plant:telehandler", "week", 500.0, delivery_treatment="ex_works",
                  effective_date=date(2026, 10, 15)),
             rate("CO1", "mat:mortar", "m3", 120.0, delivery_treatment="collection"),
             rate("CO2", "mat:sand", "t", 40.0, delivery_treatment="collection", delivery_charge=55.0)]
    est = estimate(b, *extra)
    lines = {ln.line_id: ln for ln in est.lines}
    assert lines["4:log.delivery_charge.allow.kitchen"].amount == pytest.approx(400.0)
    assert lines["4:log.delivery_charge.plant.scaffold"].amount == pytest.approx(600.0)
    assert lines["4:log.delivery_charge.sand"].amount == pytest.approx(55.0)  # collection cost entered
    joined = " | ".join(est.unresolved_items)
    for key in ("allow:staircase", "plant:telehandler", "mat:mortar"):
        assert key in joined
    assert "collection" in joined and "not priced" in joined
    assert "priced once per order in layer 4" in lines["1:4.allow.kitchen"].notes
    assert "NOT priced" in lines["1:4.allow.staircase"].notes and "NOT priced" in lines["3:plant.telehandler"].notes
    assert not any(ln.line_id.startswith("4:log.delivery_charge.allow.staircase") for ln in est.lines)


# =============================================================================
# COST-12 learning models
# =============================================================================
def test_unit_and_cumulative_average_learning_models():
    unit = LearningCurve(learning_rate=0.9, floor_fraction=0.01)
    wright = unit.model_copy(update={"model": "cumulative_average"})
    assert unit.model == "unit"
    fu, fw = learning_factors(100, unit), learning_factors(100, wright)
    b = math.log2(0.9)
    assert fu[1] == pytest.approx(0.9) and fw[1] == pytest.approx(2 ** (1 + b) - 1)  # ~0.80
    for n in (25, 100):  # Wright: cumulative average of the first n units = n ** b
        assert fw[:n].sum() == pytest.approx(n ** (1 + b)) and fw[:n].mean() == pytest.approx(n ** b)
    assert fu[:25].sum() == pytest.approx(17.7, abs=0.1) and fw[:25].sum() == pytest.approx(15.3, abs=0.1)
    # the floor applies to unit hours in both models
    floored = learning_factors(100, wright.model_copy(update={"floor_fraction": 0.7}))
    assert floored.min() == pytest.approx(0.7) and np.all(floored >= 0.7)
    est = estimate(boq(qline("1.x.0", None, "nr", 0.0, hours=100.0)))
    res = calculate_incremental_cost(est, ProductionScenario(scenario_id="w", name="w", learning=wright,
                                                             site_establishment_per_site=0.0), max_n=10,
                                     comparison_ns=(1, 10))
    lc = res.assumptions["learning_curve"]
    assert lc["model_key"] == "cumulative_average" and "Wright" in lc["model"]


# =============================================================================
# COST-2 step events and underlying marginal; COST-4 factory steps
# =============================================================================
def _scen(**kw) -> ProductionScenario:
    base = dict(scenario_id="s", name="test", materials_per_house=100_000.0, site_labour_hours_per_house=1000.0,
                site_labour_rate=40.0, plant_per_house=5000.0, site_logistics_per_house=0.0,
                site_overhead_per_house=0.0, site_establishment_per_site=45_000.0, houses_per_site=25,
                learning=LearningCurve(learning_rate=1.0, floor_fraction=1.0))
    base.update(kw)
    return ProductionScenario(**base)


def _est():
    return estimate(boq(qline("1.x.0", None, "nr", 0.0, hours=10.0)))


def test_step_events_and_underlying_marginal_at_site_and_tier_steps():
    tiers = [DiscountTier(min_units=10, discount_fraction=0.05)]
    res = calculate_incremental_cost(_est(), _scen(procurement_tiers=tiers), max_n=60, comparison_ns=(1, 10, 25, 50))
    rows = {r.n: r for r in res.rows}
    # headline definition unchanged
    for n in range(1, 60):
        assert rows[n].incremental_cost == rows[n + 1].total_cost - rows[n].total_cost
    per_house = 0.95 * 100_000 + 1000 * 40.0 + 5000.0
    # house 26 starts site 2: incremental = underlying + establishment
    assert any("site 2 established for house 26" in e for e in rows[25].step_events)
    assert rows[25].underlying_marginal_cost == pytest.approx(per_house)
    assert rows[25].incremental_cost - rows[25].underlying_marginal_cost == pytest.approx(45_000.0)
    assert rows[26].step_events == [] and rows[26].incremental_cost == pytest.approx(per_house)
    # house 10 reaches the 5 % tier: every earlier house is re-priced in all-units mode
    ev = rows[9].step_events
    assert len(ev) == 1 and "0% -> 5% at 10 units" in ev[0] and "re-priced" in ev[0] and "GBP 45,000" in ev[0]
    assert rows[9].underlying_marginal_cost == pytest.approx(per_house)
    assert rows[9].incremental_cost == pytest.approx(per_house - 9 * 0.05 * 100_000)
    assert res.assumptions["underlying_marginal_definition"] == UNDERLYING_MARGINAL_DEFINITION
    assert any("n=25" in n and "n=50" in n for n in res.notes)
    table = comparison_table(res)
    assert table[2]["n"] == 25 and table[2]["step_events"] and table[2]["underlying_marginal_cost"] == pytest.approx(
        per_house)
    # development: the cascade applies to the underlying marginal too
    cp = CostParameters(fees=[FeeItem(name="BC", fraction=0.02)], contingency_fraction=0.1, overhead_fraction=0.05,
                        margin_fraction=0.08)
    dev = calculate_incremental_cost(_est(), _scen(procurement_tiers=tiers), boundary="development", max_n=30,
                                     cost_params=cp)
    k = 1.02 * 1.1 * 1.05 * 1.08
    assert dev.rows[25].underlying_marginal_cost == pytest.approx(per_house * k)


def test_factory_steps_are_inside_the_factory_gate():
    steps = [StepCost(name="Second shift", every_n_units=50, cost=55_000.0, starts_after_units=40, boundary="factory"),
             StepCost(name="Pumping station", every_n_units=30, cost=20_000.0, starts_after_units=10)]
    sc = _scen(method="offsite_panelised", factory_labour_hours_per_house=300.0, factory_labour_rate=30.0,
               step_costs=steps)
    out = factory_vs_installed(_est(), sc, max_n=60, comparison_ns=(1, 40))
    fg = {r.n: r for r in out["factory_gate"].rows}
    ins = {r.n: r for r in out["installed"].rows}
    assert fg[41].components["factory_steps"] == 55_000.0 and "step_costs" not in fg[41].components
    assert fg[40].incremental_cost - fg[39].incremental_cost == pytest.approx(55_000.0)
    assert any("Second shift (factory step)" in e for e in fg[40].step_events)
    assert not any("Pumping" in e for r in fg.values() for e in r.step_events)  # site step: installed only
    assert any("Pumping station (site step)" in e for e in ins[10].step_events)
    assert ins[41].components["factory_steps"] == 55_000.0 and ins[41].components["step_costs"] == 40_000.0
    assert fg[40].underlying_marginal_cost == pytest.approx(fg[41].incremental_cost)
    assert out["comparison"][1]["installed_step_events"]


def test_demo_offsite_factory_step_and_site_logistics(demo):
    project, result = demo
    ps = {p.scenario_id: p for p in project.production_scenarios}
    off = ps["PS-offsite"]
    assert [s.boundary for s in off.step_costs] == ["factory"]
    fg = {r.n: r for r in result.repeat_build["PS-offsite"]["factory_gate"].rows}
    assert fg[41].components["factory_steps"] == 55_000.0
    # house 41 needs factory line 2 and the second shift; the rest is the underlying marginal (+ a pack step)
    assert fg[40].incremental_cost == pytest.approx(fg[40].underlying_marginal_cost + 85_000.0 + 55_000.0, abs=500.0)
    assert any("Second factory shift" in e for e in fg[40].step_events)
    # site logistics: the factory share of material deliveries / skips is removed (other L4 items in full)
    assert off.material_orders and off.site_logistics_per_house is not None
    est = result.estimate
    assert any(ln.layer == CostLayer.LOGISTICS_WASTE for ln in est.lines)
    full = est.layer_totals[CostLayer.LOGISTICS_WASTE.value]
    assert site_logistics_for(est, 0.0) == pytest.approx(full)
    assert site_logistics_for(est, 0.35) < full
    # default for a scenario without a value uses the same split
    sc = ProductionScenario(scenario_id="x", name="x", factory_material_fraction=0.35)
    v = calculate_incremental_cost(est, sc, max_n=2, comparison_ns=(1,)).assumptions["per_house_inputs"]
    assert v["site_logistics_per_house"]["value"] == pytest.approx(site_logistics_for(est, 0.35))
    assert "0.35" in v["site_logistics_per_house"]["source"]


# =============================================================================
# COST-3 development fee base
# =============================================================================
def test_development_fees_exclude_design_capex_and_one_off_design_fee():
    assert CostParameters().fees[0].name == "Architectural & design" and not CostParameters().fees[0].recurs_per_house
    cp = CostParameters(fees=[FeeItem(name="Design", fraction=0.06, recurs_per_house=False),
                              FeeItem(name="Warranty", fraction=0.01),
                              FeeItem(name="Survey", fraction=0.02, applies_to="direct")],
                        contingency_fraction=0.0, overhead_fraction=0.0, margin_fraction=0.0)
    sc = _scen(reusable_design_cost=18_000.0, tooling_cost=10_000.0, factory_setup_cost=20_000.0,
               factory_units_per_line=40, factory_line_cost=30_000.0, site_overhead_per_house=2_000.0)
    est = _est()
    ins = calculate_incremental_cost(est, sc, max_n=50, comparison_ns=(1, 50))
    dev = calculate_incremental_cost(est, sc, boundary="development", max_n=50, comparison_ns=(1, 50), cost_params=cp)
    for n in (1, 25, 50):
        c = ins.rows[n - 1].components
        capex = 10_000.0 + 20_000.0 + c["factory_lines"]
        base = ins.rows[n - 1].total_cost - 18_000.0 - capex
        direct = base - c["site_establishment"] - c["site_overhead"]
        assert dev.rows[n - 1].components["fees"] == pytest.approx(0.01 * base + 0.02 * direct)
    assert any("covered by the reusable design cost" in n for n in dev.notes)
    treat = {f["name"]: f["treatment"] for f in dev.assumptions["fees"]}
    assert treat["Design"].startswith("one-off: covered") and treat["Warranty"].startswith("recurring")
    # without a reusable design cost the one-off fee is charged once (constant in n)
    sc0 = sc.model_copy(update={"reusable_design_cost": 0.0})
    d0 = calculate_incremental_cost(est, sc0, boundary="development", max_n=50, comparison_ns=(1,), cost_params=cp)
    i0 = calculate_incremental_cost(est, sc0, max_n=50, comparison_ns=(1,))
    one_off = 0.06 * (i0.rows[0].total_cost - 0.0 - (10_000.0 + 20_000.0 + 30_000.0))
    for n in (1, 50):
        c = i0.rows[n - 1].components
        base = i0.rows[n - 1].total_cost - 30_000.0 - c["factory_lines"]
        direct = base - c["site_establishment"] - c["site_overhead"]
        assert d0.rows[n - 1].components["fees"] == pytest.approx(one_off + 0.01 * base + 0.02 * direct)


def test_demo_development_no_longer_charges_design_per_house(demo):
    project, result = demo
    dev = {r.n: r for r in result.repeat_build["PS-site"]["development"].rows}
    ins = {r.n: r for r in result.repeat_build["PS-site"]["installed"].rows}
    recurring = sum(f.fraction for f in project.cost_parameters.fees if f.recurs_per_house)
    base = ins[100].total_cost - ins[100].components["design"]
    assert dev[100].components["fees"] == pytest.approx(recurring * base)
    assert dev[100].components["fees"] < 0.03 * ins[100].total_cost


# =============================================================================
# COST-7 site overhead and reconciliation
# =============================================================================
def test_site_overhead_defaults_from_time_related_prelims_and_reconciles():
    est = _est()  # 10 weeks x 1000 time-related prelims
    sc = ProductionScenario(scenario_id="o", name="o", site_overhead_share=0.4, site_establishment_per_site=30_000.0,
                            learning=LearningCurve(learning_rate=1.0))
    res = calculate_incremental_cost(est, sc, max_n=3, comparison_ns=(1,))
    assert res.rows[0].components["site_overhead"] == pytest.approx(0.4 * 10_000.0)
    assert res.rows[2].components["site_overhead"] == pytest.approx(3 * 0.4 * 10_000.0)
    assert "site_overhead" not in calculate_incremental_cost(est, sc, boundary="factory_gate", max_n=2,
                                                             comparison_ns=(1,)).rows[0].components
    rec = res.assumptions["single_house_reconciliation"]
    assert rec == single_house_reconciliation(est, sc)
    assert sum(r["installed_c1"] for r in rec["rows"]) == pytest.approx(rec["installed_c1"])
    assert sum(r["single_house"] for r in rec["rows"]) == pytest.approx(rec["single_house_l1_l5"])
    assert rec["installed_c1"] == pytest.approx(res.rows[0].total_cost)
    prelim = next(r for r in rec["rows"] if r["item"].startswith("Preliminaries"))
    assert prelim["single_house"] == pytest.approx(15_000.0) and prelim["installed_c1"] == pytest.approx(34_000.0)


def test_demo_reconciliation_in_results_and_report(demo):
    from housebuilder_vision.demo.run_demo import format_report

    project, result = demo
    rec = result.repeat_build["PS-site"]["installed"].assumptions["single_house_reconciliation"]
    lt = result.estimate.layer_totals
    assert rec["single_house_l1_l5"] == pytest.approx(sum(lt[layer.value] for layer in list(CostLayer)[:5]))
    rows = {r["item"]: r for r in rec["rows"]}
    assert rows["Materials (L1)"]["installed_c1"] == pytest.approx(lt[CostLayer.MATERIALS.value])
    assert result.repeat_build["PS-site"]["installed"].rows[0].components["site_overhead"] > 0
    report = format_report(project, result)
    assert "underlying" in report and "steps n->n+1" in report and "site 2 established for house 26" in report
    assert "reconciliation: single-house layers 1-5 vs installed C(1)" in report


# =============================================================================
# COST-8 / COST-9 UI state (bare mode)
# =============================================================================
@pytest.fixture(scope="module")
def demo_ws(tmp_path_factory):
    pytest.importorskip("streamlit")
    import os

    from housebuilder_vision.ui import state as UI

    old = os.environ.get("HBV_DATA_DIR")
    os.environ["HBV_DATA_DIR"] = str(tmp_path_factory.mktemp("hbv-costfix"))
    try:
        ws = UI.Workspace(store_dir=str(UI.image_store_dir()))
        UI.load_demo(ws)
        yield ws
    finally:
        if old is None:
            os.environ.pop("HBV_DATA_DIR", None)
        else:
            os.environ["HBV_DATA_DIR"] = old


def test_ui_fallback_inputs_show_the_rate_in_force_and_never_claim_a_false_effect(demo_ws):
    from housebuilder_vision.ui import state as UI
    from housebuilder_vision.ui.views.costs import _applied_message, _rates_in_force

    ws = demo_ws
    in_force = _rates_in_force(ws)
    assert set(in_force) == set(COST_PARAMETER_FALLBACKS)
    assert all(used for used, _ in in_force.values())
    assert "FD-PRELIM-weekly" in in_force["prelims_weekly_cost"][1] and "not used" in in_force["prelims_weekly_cost"][1]
    ev = UI.evaluate(ws)
    before = ws.project.cost_parameters
    err = UI.update_cost_parameters(ws, {"prelims_weekly_cost": 5000.0, "prelims_fixed_setup": 50_000.0,
                                         "cost_per_delivery_load": 500.0, "cost_per_skip": 2000.0})
    assert err is None
    level, msg = _applied_message(ws, ev, before, in_force)
    assert level == "warning" and "did not change" in msg and "prelims weekly" in msg and "no effect" in msg
    ev2 = UI.evaluate(ws)
    assert ev2.estimate.boundary("contract_sum").amount == pytest.approx(ev.estimate.boundary("contract_sum").amount)
    before2 = ws.project.cost_parameters
    UI.update_cost_parameters(ws, {"contingency_fraction": 0.15})
    level, msg = _applied_message(ws, ev2, before2, in_force)
    assert level == "success" and "contract sum" in msg and "→" in msg
    UI.update_cost_parameters(ws, {"contingency_fraction": before.contingency_fraction,
                                   **{k: getattr(before, k) for k in COST_PARAMETER_FALLBACKS}})


def test_ui_illustrative_offsite_scenario_uses_the_timber_frame_variant(demo_ws):
    from housebuilder_vision.ui import state as UI

    ws = demo_ws
    ev = UI.evaluate(ws)
    assert ws.project.twin.assemblies.external_wall == "ew_masonry_cavity"
    UI.add_example_production_scenarios(ws, ev)
    ps = {p.scenario_id: p for p in ws.project.production_scenarios}
    tf_est, label = UI.offsite_variant_estimate(ws, ev)
    assert "timber frame + brick outer leaf variant" in label
    assert ps["PS-offsite"].materials_per_house == pytest.approx(tf_est.layer_totals["1_materials"])
    assert ps["PS-offsite"].materials_per_house != pytest.approx(ev.estimate.layer_totals["1_materials"])
    assert "variant of the current house" in ps["PS-offsite"].notes
    assert ps["PS-site"].materials_per_house is None  # taken from the current estimate
    # a library without the timber-frame assembly: the label says what was used
    lib = ws.project.library
    try:
        ws.project.library = lib.model_copy(update={"assemblies": [a for a in lib.assemblies
                                                                   if a.assembly_id != "ew_timber_frame_brick"]})
        est2, label2 = UI.offsite_variant_estimate(ws, ev)
        assert est2 is ev.estimate and "not in this library" in label2
    finally:
        ws.project.library = lib
