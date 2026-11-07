"""Tests for rate books, rate resolution, the nine-layer cost engine and repeat-build economics.

Arithmetic is checked by hand on a tiny bill of quantities; the bundled FICTIONAL demo rates are
checked for coverage of every cost key the take-off can emit on a hand-built two-storey twin.
"""

from __future__ import annotations

import io
import json
import math
import time
from datetime import date

import pytest

from housebuilder_vision.core.models import (
    BillOfQuantities,
    Block,
    BlockRole,
    BuildingTwin,
    CostLayer,
    CostParameters,
    DeliveryTreatment,
    DiscountTier,
    FeeItem,
    GeometryMetrics,
    HiddenSideAssumptions,
    LearningCurve,
    LogisticsResult,
    MaterialSpec,
    Opening,
    OpeningKind,
    ProductionScenario,
    QuantityLine,
    QuantityStatus,
    Rate,
    RateBook,
    RateSourceType,
    RoofForm,
    RoofSpec,
    Side,
    StepCost,
    AssemblyLibrary,
)
from housebuilder_vision.core.provenance import Basis, TrackedValue, assumed
from housebuilder_vision.core.settings import ProjectSettings
from housebuilder_vision.costing import (
    BOUNDARY_KEYS,
    DEMO_RATES_PATH,
    FictionalDemoPricingAdapter,
    ManualCSVPricingAdapter,
    PricingAdapter,
    RATE_COLUMNS,
    RULE_COST_KEYS,
    RateBookError,
    calculate_incremental_cost,
    component_curves,
    demo_production_scenarios,
    demo_rate_book,
    estimate_construction_cost,
    factory_vs_installed,
    fetch_rate_book,
    learning_factors,
    load_rate_book_csv,
    load_rate_book_json,
    merge_rate_books,
    rate_book_to_dataframe,
    resolve_rate,
    resolve_rate_detailed,
    total_cost_curve,
)
from housebuilder_vision.costing.rates import MAX_FILE_BYTES, MAX_ROWS
from housebuilder_vision.quantities import (
    apply_construction_assemblies,
    calculate_quantities,
    cost_keys,
    default_library,
    default_selection,
)

LIB = default_library()
PRICING_DATE = date(2026, 11, 1)  # pinned: ProjectSettings() defaults to today (COST-11)
SETTINGS = ProjectSettings(pricing_date=PRICING_DATE)  # GBP
EFF = date(2026, 10, 1)


def settings(**kw) -> ProjectSettings:
    """Project settings with the pinned test pricing date unless one is given."""
    kw.setdefault("pricing_date", PRICING_DATE)
    return ProjectSettings(**kw)


# =============================================================================
# helpers
# =============================================================================
def rate(rid, key, unit, value, **kw) -> Rate:
    layer = {"mat": CostLayer.MATERIALS, "allow": CostLayer.MATERIALS, "lab": CostLayer.LABOUR,
             "plant": CostLayer.PLANT, "log": CostLayer.LOGISTICS_WASTE,
             "prelim": CostLayer.PRELIMINARIES}[key.split(":")[0]]
    base = dict(rate_id=rid, cost_key=key, layer=layer, unit=unit, value=value, effective_date=EFF,
                source="FICTIONAL test rate", source_type=RateSourceType.FICTIONAL_DEMO,
                location="Exampleton (fictional)", uncertainty_low=-0.1, uncertainty_high=0.15)
    base.update(kw)
    return Rate(**base)


def tiny_book(*extra: Rate, drop: tuple[str, ...] = ()) -> RateBook:
    rates = [
        rate("r-brick", "mat:brick", "nr", 0.80, delivery_treatment=DeliveryTreatment.DELIVERED_INCLUDED),
        rate("r-bl", "lab:bricklaying", "hr", 40.0, uncertainty_low=-0.08, uncertainty_high=0.20),
        rate("r-gw", "lab:groundworks", "hr", 30.0),
        rate("r-cp", "lab:carpentry", "hr", 35.0),
        rate("r-exc", "plant:excavation", "m3", 10.0),
        rate("r-spoil", "log:spoil_disposal", "m3", 40.0),
        rate("r-kit", "allow:kitchen", "nr", 5000.0),
        rate("r-dump", "plant:dumper", "week", 150.0),
        rate("r-scaf", "plant:scaffold", "m2_week", 2.0),
        rate("r-tele", "plant:telehandler", "week", 500.0),
        rate("r-load", "log:delivery_load", "load", 80.0),
        rate("r-skip", "log:skip", "nr", 300.0),
        rate("r-setup", "prelim:setup", "sum", 5000.0),
        rate("r-week", "prelim:weekly", "week", 1000.0),
    ]
    rates = [r for r in rates if r.cost_key not in drop] + list(extra)
    return RateBook(name="tiny", rates=rates)


def metrics(**over) -> GeometryMetrics:
    vals = {}
    for name, f in GeometryMetrics.model_fields.items():
        if f.is_required():
            vals[name] = [] if name in ("blocks", "pieces", "storeys", "roofs") else 0.0
    vals.update(external_wall_gross_m2=100.0, gia_m2=80.0)
    vals.update(over)
    return GeometryMetrics(**vals)


def qline(line_id, cost_key, unit, qty, *, trade="general", hours=0.0, status=QuantityStatus.DERIVED,
          material_id=None, cutting=0.0, waste=0.0, basis=Basis.ASSUMED) -> QuantityLine:
    return QuantityLine(line_id=line_id, element_code=line_id.split(".")[0], element_name="test",
                        description=f"test line {line_id}", status=status, cost_key=cost_key, unit=unit,
                        installed_qty=qty, required_qty=qty, purchase_unit=unit, purchased_qty=qty,
                        cutting_loss_qty=cutting, waste_qty=waste, trade=trade, labour_hours=hours,
                        material_id=material_id, basis=basis)


def tiny_boq(*, unresolved: bool = False) -> BillOfQuantities:
    lines = [
        qline("2.5.B1.ew.0", "mat:brick", "nr", 1000.0, trade="bricklaying", hours=20.0, material_id="brick",
              cutting=27.0, waste=45.0),
        qline("1.all.fdn.0", "plant:excavation", "m3", 10.0, trade="groundworks", hours=3.5),
        qline("1.all.fdn.2", "log:spoil_disposal", "m3", 13.0, trade="groundworks", hours=0.0),
        qline("4.allow.kitchen", "allow:kitchen", "nr", 1.0, trade="carpentry", hours=40.0,
              status=QuantityStatus.ALLOWANCE),
    ]
    if unresolved:
        lines.append(QuantityLine(line_id="2.3.B1.pr.0", element_code="2.3", element_name="Roof",
                                  description="roof tiles", status=QuantityStatus.UNRESOLVED, unit="nr",
                                  notes="pitch unknown", formula="UNRESOLVED: pitch unknown", basis=Basis.UNKNOWN))
    return BillOfQuantities(twin_id="t", twin_version=1, library_name="tiny", lines=lines, geometry=metrics())


TINY_LIB = AssemblyLibrary(name="tiny", materials=[
    MaterialSpec(material_id="brick", name="brick", installed_unit="nr", purchase_unit="nr", pack_size=1.0,
                 mass_per_purchase_unit_kg=2.5, volume_per_purchase_unit_m3=0.002)])

TINY_PARAMS = CostParameters(
    fees=[FeeItem(name="Design", fraction=0.05, applies_to="construction"),
          FeeItem(name="Survey", fraction=0.01, applies_to="direct")],
    contingency_fraction=0.10, overhead_fraction=0.05, margin_fraction=0.08, skip_volume_m3=6.0,
    waste_bulking_factor=1.6)

LOGI = LogisticsResult(batches=[], total_loads=3, total_mass_t=2.5, peak_storage_area_m2=10.0, waste_volume_m3=0.1,
                       skips=1)


def tiny_estimate(params=TINY_PARAMS, settings=SETTINGS, book=None, **kw):
    return estimate_construction_cost(kw.pop("boq", tiny_boq()), book or tiny_book(), params, settings=settings,
                                      programme_weeks=kw.pop("programme_weeks", 10.0),
                                      logistics=kw.pop("logistics", LOGI), library=TINY_LIB, **kw)


# --- hand-built twin (the twin builder is a separate module) -------------------
def tv(v, unit="m", basis=Basis.USER_CONFIRMED):
    return TrackedValue(value=v, unit=unit, basis=basis)


def blk(bid, x0, y0, w, d, storeys=2, form=RoofForm.GABLE, pitch=35.0, axis="x", eo=0.3, vo=0.2, heated=True,
        role=BlockRole.MAIN):
    return Block(block_id=bid, role=role, origin_x=tv(x0), origin_y=tv(y0), width=tv(w), depth=tv(d),
                 storeys=tv(storeys, "storeys"), floor_to_floor=tv(2.7), ground_floor_level=tv(0.15),
                 roof=RoofSpec(form=form, pitch_deg=tv(pitch, "deg"), ridge_axis=axis, eaves_overhang_m=tv(eo),
                               verge_overhang_m=tv(vo)), heated=heated)


def op(oid, bid, side, kind, storey, off, w, h, sill):
    return Opening(opening_id=oid, block_id=bid, side=side, kind=kind, storey=storey, offset_m=tv(off),
                   width_m=tv(w), height_m=tv(h), sill_m=tv(sill))


def two_storey_twin() -> BuildingTwin:
    blocks = [
        blk("main", 0, 0, 9.6, 8.4),
        blk("garage", 9.6, 0, 3.2, 6.0, storeys=1, pitch=30.0, axis="y", heated=False, role=BlockRole.GARAGE),
        blk("ext", 0, 8.4, 4.8, 3.6, storeys=1, form=RoofForm.FLAT, pitch=0.0, eo=0.15, vo=0.15,
            role=BlockRole.EXTENSION),
    ]
    ops = [
        op("W1", "main", Side.FRONT, OpeningKind.WINDOW, 0, 1.0, 1.8, 1.2, 0.9),
        op("D1", "main", Side.FRONT, OpeningKind.DOOR, 0, 4.3, 1.0, 2.1, 0.0),
        op("W2", "main", Side.FRONT, OpeningKind.WINDOW, 0, 6.8, 1.8, 1.2, 0.9),
        op("W3", "main", Side.FRONT, OpeningKind.WINDOW, 1, 1.3, 1.2, 1.2, 0.9),
        op("W4", "main", Side.FRONT, OpeningKind.WINDOW, 1, 4.2, 1.2, 1.2, 0.9),
        op("W5", "main", Side.REAR, OpeningKind.PATIO_DOOR, 0, 5.5, 2.4, 2.1, 0.0),
        op("G1", "garage", Side.FRONT, OpeningKind.GARAGE_DOOR, 0, 0.4, 2.4, 2.13, 0.0),
    ]
    return BuildingTwin(twin_id="t_cost", blocks=blocks, openings=ops,
                        hidden=HiddenSideAssumptions(rear_glazing_ratio=assumed(0.2, "fraction"),
                                                     side_glazing_ratio=assumed(0.04, "fraction")),
                        assemblies=default_selection(LIB))


# =============================================================================
# Rate books: loading and validation
# =============================================================================
def test_demo_csv_loads_strictly_and_is_fictional():
    book = load_rate_book_csv(DEMO_RATES_PATH, name="demo", strict=True)
    assert book.warnings == []
    assert len(book.rates) >= 70
    for r in book.rates:
        assert r.currency == "GBP"
        assert r.location == "Exampleton (fictional)"
        assert r.effective_date == date(2026, 10, 1)
        assert "FICTIONAL DEMO RATE - not market data" in r.source
        assert r.uncertainty_low < 0 < r.uncertainty_high
        assert r.delivery_treatment != DeliveryTreatment.UNKNOWN
    types = [r.source_type for r in book.rates]
    assert types.count(RateSourceType.SUPPLIER_QUOTE) == 3
    assert all(t in (RateSourceType.FICTIONAL_DEMO, RateSourceType.SUPPLIER_QUOTE) for t in types)
    quotes = [r for r in book.rates if r.source_type == RateSourceType.SUPPLIER_QUOTE]
    assert all(q.supplier == "Example Supplies Ltd (fictional)" and q.quote_reference and q.valid_until
               for q in quotes)
    assert any(q.valid_until < date(2026, 11, 1) for q in quotes)  # one expired quote
    inc = [r for r in book.rates if r.tax_treatment.value == "inc_vat"]
    assert len(inc) == 1 and inc[0].vat_rate == pytest.approx(0.20)
    assert all(r.tax_treatment.value in ("ex_vat", "inc_vat") for r in book.rates)
    # labour and materials uncertainty bands as specified
    lab = [r for r in book.rates if r.cost_key.startswith("lab:")]
    assert {(r.uncertainty_low, r.uncertainty_high) for r in lab} == {(-0.08, 0.20)}
    mat = [r for r in book.rates if r.source_type == RateSourceType.FICTIONAL_DEMO and r.cost_key.startswith("mat:")]
    assert {(r.uncertainty_low, r.uncertainty_high) for r in mat} == {(-0.10, 0.15)}
    # adapter and helper give the same book
    assert len(demo_rate_book().rates) == len(book.rates)


def test_demo_csv_covers_every_takeoff_cost_key_and_rule_key():
    book = demo_rate_book()
    have = {r.cost_key for r in book.rates}
    assert set(cost_keys(LIB)) <= have
    assert set(RULE_COST_KEYS) <= have
    # each takeoff key resolves in its takeoff unit (purchase unit for materials)
    for key, unit in cost_keys(LIB).items():
        r, v, _ = resolve_rate(book, key, unit, settings=SETTINGS)
        assert r is not None and v > 0, key


CSV_HEADER = ",".join(RATE_COLUMNS)


def _csv(rows: list[dict]) -> str:
    out = [CSV_HEADER]
    for row in rows:
        out.append(",".join(str(row.get(c, "")) for c in RATE_COLUMNS))
    return "\n".join(out) + "\n"


GOOD_ROW = dict(rate_id="a1", cost_key="mat:brick", layer="1_materials", unit="nr", currency="gbp", value="0.8",
                effective_date="2026-10-01", source="FICTIONAL test", source_type="fictional_demo")


def test_csv_invalid_rows_are_warned_or_raise_in_strict_mode():
    rows = [GOOD_ROW,
            dict(GOOD_ROW, rate_id="a2", value="-1"),  # negative
            dict(GOOD_ROW, rate_id="a3", effective_date="not-a-date"),
            dict(GOOD_ROW, rate_id="a4", value="nan"),
            dict(GOOD_ROW, rate_id="a1"),  # duplicate id
            dict(GOOD_ROW, rate_id="a5", uncertainty_low="0.3", uncertainty_high="9")]  # clamped
    text = "  " + _csv(rows).replace("mat:brick,", " mat:brick ,", 1)  # whitespace is stripped
    book = load_rate_book_csv(io.StringIO(text.strip() + "\n"), name="t")
    assert [r.rate_id for r in book.rates] == ["a1", "a5"]
    assert book.rates[0].currency == "GBP" and book.rates[0].cost_key == "mat:brick"
    joined = " | ".join(book.warnings)
    for row_no in (3, 4, 5, 6):  # header is line 1
        assert f"row {row_no}" in joined
    assert "clamped" in joined
    assert book.rates[1].uncertainty_low == 0.0 and book.rates[1].uncertainty_high == 5.0
    with pytest.raises(RateBookError) as ei:
        load_rate_book_csv(io.StringIO(_csv(rows)), name="t", strict=True)
    assert "row 3" in str(ei.value) and "row 6" in str(ei.value)


def test_csv_limits_and_structure_errors():
    with pytest.raises(RateBookError):
        load_rate_book_csv(io.BytesIO(b"x" * (MAX_FILE_BYTES + 1)), name="big")
    many = CSV_HEADER + "\n" + "\n".join(
        f"r{i},mat:x,,1_materials,nr,GBP,1,,2026-10-01,F,fictional_demo" + "," * 10 for i in range(MAX_ROWS + 1))
    with pytest.raises(RateBookError, match="rows"):
        load_rate_book_csv(io.StringIO(many), name="many")
    with pytest.raises(RateBookError, match="missing required column"):
        load_rate_book_csv(io.StringIO("rate_id,value\na,1\n"), name="cols")
    with pytest.raises(RateBookError):
        load_rate_book_csv(io.StringIO(""), name="empty")
    with pytest.raises(RateBookError):
        load_rate_book_csv("/nonexistent/rates.csv")
    # unknown columns are ignored with a warning, formulas are kept as inert text
    text = _csv([dict(GOOD_ROW, notes="=HYPERLINK(1)")]).replace(CSV_HEADER, CSV_HEADER + ",extra", 1)
    book = load_rate_book_csv(io.StringIO(text), name="x")
    assert len(book.rates) == 1 and book.rates[0].notes == "=HYPERLINK(1)"
    assert any("extra" in w for w in book.warnings)


def test_json_loader_merge_and_dataframe(tmp_path):
    payload = {"name": "json book", "rates": [dict(GOOD_ROW), dict(GOOD_ROW, rate_id="b2", value="x")]}
    p = tmp_path / "rates.json"
    p.write_text(json.dumps(payload))
    book = load_rate_book_json(p)
    assert book.name == "json book" and len(book.rates) == 1 and any("row 2" in w for w in book.warnings)
    with pytest.raises(RateBookError):
        load_rate_book_json(p, strict=True)
    listed = load_rate_book_json(io.StringIO(json.dumps([GOOD_ROW])), name="list")
    assert listed.rates[0].rate_id == "a1"
    with pytest.raises(RateBookError):
        load_rate_book_json(io.StringIO("{not json"), name="bad")
    newer = RateBook(name="override", rates=[rate("a1", "mat:brick", "nr", 0.9)])
    merged = merge_rate_books(book, newer)
    assert len(merged.rates) == 1 and merged.rates[0].value == 0.9
    assert any("replaces" in w for w in merged.warnings)
    df = rate_book_to_dataframe(merged)
    assert list(df.columns) == list(RATE_COLUMNS) and df.loc[0, "layer"] == "1_materials"


# =============================================================================
# Rate resolution
# =============================================================================
def test_vat_stripping_with_and_without_rate_vat():
    book = RateBook(name="v", rates=[rate("v1", "mat:door", "nr", 120.0, tax_treatment="inc_vat", vat_rate=0.20),
                                     rate("v2", "mat:gate", "nr", 125.0, tax_treatment="inc_vat")])
    r, v, w = resolve_rate(book, "mat:door", "nr", settings=SETTINGS)
    # resolve_rate() lists every adjustment it applied (COST-1); no other warning here
    assert r.rate_id == "v1" and v == pytest.approx(100.0) and w == ["VAT stripped ÷1.2"]
    s = settings(vat_rate=0.25)
    r, v, w = resolve_rate(book, "mat:gate", "nr", settings=s)
    assert v == pytest.approx(100.0) and any("project VAT rate" in x for x in w)
    # the demo door is entered inc. VAT: 1386 / 1.2
    r, v, _ = resolve_rate(demo_rate_book(), "mat:door_composite", "nr", settings=SETTINGS)
    assert v == pytest.approx(1155.0)


def test_per_tonne_to_per_kg_and_incompatible_units():
    book = RateBook(name="u", rates=[rate("u1", "allow:steel", "t", 1200.0), rate("u2", "mat:agg", "tonne", 30.0)])
    r, v, _ = resolve_rate(book, "allow:steel", "kg", settings=SETTINGS)
    assert r.rate_id == "u1" and v == pytest.approx(1.2)
    _, v2, _ = resolve_rate(book, "mat:agg", "kg", settings=SETTINGS)
    assert v2 == pytest.approx(0.03)
    rd = resolve_rate_detailed(book, "allow:steel", "kg", settings=SETTINGS)
    assert rd.unit_factor == pytest.approx(1e-3) and any("per t -> per kg" in a for a in rd.adjustments)
    r, v, w = resolve_rate(book, "allow:steel", "m2", settings=SETTINGS)
    assert r is None and math.isnan(v) and any("not convertible" in x for x in w)
    r, v, w = resolve_rate(book, "mat:unknown", "nr", settings=SETTINGS)
    assert r is None and math.isnan(v) and any("no rate" in x for x in w)


def test_fx_conversion_and_missing_fx():
    book = RateBook(name="fx", rates=[rate("e1", "mat:x", "nr", 100.0, currency="EUR")])
    r, v, w = resolve_rate(book, "mat:x", "nr", settings=settings(fx_rates={"EUR": 0.85}))
    assert r.rate_id == "e1" and v == pytest.approx(85.0) and any("fx EUR->GBP" in x for x in w)
    r, v, w = resolve_rate(book, "mat:x", "nr", settings=SETTINGS)
    assert r is None and any("no fx rate" in x for x in w)


def test_expired_quote_is_deprioritised_and_priority_order():
    valid_q = rate("q1", "mat:x", "nr", 0.90, source_type="supplier_quote", supplier="Example Supplies Ltd (fictional)",
                   quote_reference="Q1", valid_until=date(2026, 12, 31))
    expired_q = rate("q2", "mat:x", "nr", 0.70, source_type="supplier_quote", quote_reference="Q2",
                     valid_until=date(2026, 10, 15))
    demo = rate("d1", "mat:x", "nr", 1.00)
    manual = rate("m1", "mat:x", "nr", 0.95, source_type="manual")
    # supplier quote (priority 5) beats manual (4) beats fictional (1)
    r, _, _ = resolve_rate(RateBook(name="a", rates=[demo, manual, valid_q]), "mat:x", "nr", settings=SETTINGS)
    assert r.rate_id == "q1"
    r, _, _ = resolve_rate(RateBook(name="b", rates=[demo, manual]), "mat:x", "nr", settings=SETTINGS)
    assert r.rate_id == "m1"
    # an expired quote ranks below any valid rate, with a warning
    r, v, w = resolve_rate(RateBook(name="c", rates=[expired_q, demo]), "mat:x", "nr", settings=SETTINGS)
    assert r.rate_id == "d1" and v == 1.0 and any("expired" in x and "q2" in x for x in w)
    # only an expired quote: used, flagged, provenance downgraded
    rd = resolve_rate_detailed(RateBook(name="d", rates=[expired_q]), "mat:x", "nr", settings=SETTINGS)
    assert rd.rate.rate_id == "q2" and rd.expired and rd.basis == Basis.ASSUMED
    assert any("using expired" in x for x in rd.warnings)
    assert resolve_rate_detailed(RateBook(name="e", rates=[valid_q]), "mat:x", "nr",
                                 settings=SETTINGS).basis == Basis.USER_CONFIRMED
    # same source type: most recent effective date wins
    older = rate("o1", "mat:x", "nr", 1.10, effective_date=date(2025, 6, 1))
    r, _, _ = resolve_rate(RateBook(name="f", rates=[older, demo]), "mat:x", "nr", settings=SETTINGS)
    assert r.rate_id == "d1"
    # demo book: expired fictional tile quote loses to the demo rate
    r, v, w = resolve_rate(demo_rate_book(), "mat:roof_tile_concrete", "nr", settings=SETTINGS)
    assert r.source_type == RateSourceType.FICTIONAL_DEMO and any("EXQ-2026-0398" in x for x in w)


def test_future_dated_rates_are_excluded():
    future = rate("f1", "mat:x", "nr", 0.5, effective_date=date(2027, 1, 1), source_type="supplier_quote")
    current = rate("c1", "mat:x", "nr", 1.0)
    r, v, w = resolve_rate(RateBook(name="a", rates=[future, current]), "mat:x", "nr", settings=SETTINGS)
    assert r.rate_id == "c1" and v == 1.0 and any("f1" in x and "excluded" in x for x in w)
    r, v, w = resolve_rate(RateBook(name="b", rates=[future]), "mat:x", "nr", settings=SETTINGS)
    assert r is None and math.isnan(v)
    # ... but valid once the pricing date passes its effective date
    r, _, _ = resolve_rate(RateBook(name="c", rates=[future]), "mat:x", "nr",
                           settings=ProjectSettings(pricing_date=date(2027, 2, 1)))
    assert r.rate_id == "f1"


def test_escalation_and_regional_factor_are_labelled():
    old = rate("o1", "mat:x", "nr", 100.0, effective_date=date(2025, 11, 1), location="Elsewhere (fictional)")
    book = RateBook(name="esc", rates=[old])
    s = settings(annual_escalation_rate=0.05)
    r, v, w = resolve_rate(book, "mat:x", "nr", settings=s)
    assert v == pytest.approx(100.0 * 1.05 ** (365 / 365.25))
    assert any("escalation" in x for x in w)
    s2 = settings(regional_cost_factor=1.10)
    _, v2, w2 = resolve_rate(book, "mat:x", "nr", settings=s2)
    assert v2 == pytest.approx(110.0) and any("regional factor" in x for x in w2)
    local = RateBook(name="loc", rates=[rate("l1", "mat:x", "nr", 100.0)])  # Exampleton = project location
    _, v3, _ = resolve_rate(local, "mat:x", "nr", settings=s2)
    assert v3 == pytest.approx(100.0)


def test_rate_index_is_cached_and_tracks_changes():
    from housebuilder_vision.costing import rate_index

    book = tiny_book()
    assert rate_index(book) is rate_index(book)
    book.rates.append(rate("new", "mat:new", "nr", 1.0))
    idx = rate_index(book)
    assert "mat:new" in idx.cost_keys()


# =============================================================================
# Cost engine: hand-checked arithmetic on a tiny BoQ
# =============================================================================
def _hand_layers():
    L1 = 1000 * 0.80 + 1 * 5000.0
    L2 = 20 * 40.0 + 3.5 * 30.0 + 40 * 35.0
    scaffold = 100.0 * 1.15 * (0.40 * 10.0) * 2.0
    L3 = 10 * 10.0 + 1 * 150.0 + scaffold + math.ceil(0.35 * 10) * 500.0
    skips = math.ceil((27 + 45) * 0.002 * 1.6 / 6.0)
    L4 = 13 * 40.0 + 3 * 80.0 + skips * 300.0
    L5 = 5000.0 + 10 * 1000.0
    direct = L1 + L2 + L3 + L4
    L6 = 0.05 * (direct + L5) + 0.01 * direct
    L7 = 0.10 * (direct + L5 + L6)
    b8 = direct + L5 + L6 + L7
    oh = 0.05 * b8
    L8 = oh + 0.08 * (b8 + oh)
    return dict(L1=L1, L2=L2, L3=L3, L4=L4, L5=L5, L6=L6, L7=L7, L8=L8, skips=skips)


def test_tiny_boq_layers_by_hand():
    est = tiny_estimate()
    h = _hand_layers()
    lt = est.layer_totals
    assert lt[CostLayer.MATERIALS.value] == pytest.approx(h["L1"])
    assert lt[CostLayer.LABOUR.value] == pytest.approx(h["L2"])
    assert lt[CostLayer.PLANT.value] == pytest.approx(h["L3"])
    assert lt[CostLayer.LOGISTICS_WASTE.value] == pytest.approx(h["L4"])
    assert lt[CostLayer.PRELIMINARIES.value] == pytest.approx(h["L5"])
    assert lt[CostLayer.FEES_ALLOWANCES.value] == pytest.approx(h["L6"])
    assert lt[CostLayer.CONTINGENCY.value] == pytest.approx(h["L7"])
    assert lt[CostLayer.OVERHEAD_MARGIN.value] == pytest.approx(h["L8"])
    assert lt[CostLayer.LAND_FINANCE_TAX_SALES.value] == 0.0
    assert set(lt) == {layer.value for layer in CostLayer}
    assert est.unresolved_items == []
    assert est.programme_weeks == 10.0 and est.gia_m2 == 80.0 and est.currency == "GBP"
    lines = {ln.line_id: ln for ln in est.lines}
    assert lines["3:plant.scaffold"].quantity == pytest.approx(460.0)
    assert lines["3:plant.telehandler"].quantity == 4.0
    assert lines["4:log.skips"].quantity == h["skips"] == 1
    assert lines["4:log.delivery_loads"].quantity == 3.0  # from the logistics plan
    # layer totals equal the sum of their lines
    for layer in CostLayer:
        assert lt[layer.value] == pytest.approx(sum(ln.amount for ln in est.lines if ln.layer == layer))


def test_boundaries_are_cumulative_and_defined():
    est = tiny_estimate()
    h = _hand_layers()
    keys = [b.key for b in est.boundaries]
    assert keys == list(BOUNDARY_KEYS[:-1])  # no layer-9 items entered -> no development boundary
    b = {x.key: x.amount for x in est.boundaries}
    assert b["materials"] == pytest.approx(h["L1"])
    assert b["direct_works"] == pytest.approx(h["L1"] + h["L2"] + h["L3"] + h["L4"])
    assert b["construction_before_contingency"] == pytest.approx(b["direct_works"] + h["L5"] + h["L6"])
    assert b["construction_incl_contingency"] == pytest.approx(b["construction_before_contingency"] + h["L7"])
    assert b["contract_sum"] == pytest.approx(b["construction_incl_contingency"] + h["L8"])
    amounts = [x.amount for x in est.boundaries]
    assert amounts == sorted(amounts)
    for x in est.boundaries:
        assert x.definition and x.excludes
        assert x.amount == pytest.approx(sum(est.layer_totals[layer.value] for layer in x.layers))
    with pytest.raises(KeyError):
        est.boundary("total_development_cost")


def test_cost_lines_link_quantities_rates_and_provenance():
    est = tiny_estimate()
    lines = {ln.line_id: ln for ln in est.lines}
    brick = lines["1:2.5.B1.ew.0"]
    assert brick.quantity_line_id == "2.5.B1.ew.0" and brick.rate_id == "r-brick" and brick.amount == pytest.approx(800)
    assert (brick.uncertainty_low, brick.uncertainty_high) == (-0.1, 0.15)
    assert "1000.000 nr" in brick.formula and brick.basis == Basis.ASSUMED
    lab = lines["2:2.5.B1.ew.0"]
    assert lab.cost_key == "lab:bricklaying" and lab.quantity == 20.0 and lab.amount == pytest.approx(800)
    assert (lab.uncertainty_low, lab.uncertainty_high) == (-0.08, 0.20)
    assert lines["1:4.allow.kitchen"].layer == CostLayer.MATERIALS
    assert lines["3:1.all.fdn.0"].layer == CostLayer.PLANT
    assert lines["4:1.all.fdn.2"].layer == CostLayer.LOGISTICS_WASTE
    # basis: a user-confirmed quantity priced with a valid quote stays user-confirmed
    boq = tiny_boq()
    boq.lines[0] = boq.lines[0].model_copy(update={"basis": Basis.USER_CONFIRMED})
    quote = rate("q-brick", "mat:brick", "nr", 0.75, source_type="supplier_quote", valid_until=date(2027, 1, 1))
    est2 = tiny_estimate(boq=boq, book=tiny_book(quote))
    ln = {x.line_id: x for x in est2.lines}["1:2.5.B1.ew.0"]
    assert ln.rate_id == "q-brick" and ln.basis == Basis.USER_CONFIRMED and ln.amount == pytest.approx(750)


def test_fee_bases_contingency_and_ohp():
    est = tiny_estimate()
    h = _hand_layers()
    lines = {ln.line_id: ln for ln in est.lines}
    direct = h["L1"] + h["L2"] + h["L3"] + h["L4"]
    assert lines["6:fee.0.design"].amount == pytest.approx(0.05 * (direct + h["L5"]))
    assert lines["6:fee.1.survey"].amount == pytest.approx(0.01 * direct)
    b7 = direct + h["L5"] + h["L6"]
    assert lines["7:contingency"].amount == pytest.approx(0.10 * b7)
    assert lines["8:overhead"].amount == pytest.approx(0.05 * (b7 + h["L7"]))
    assert lines["8:margin"].amount == pytest.approx(
        0.08 * (b7 + h["L7"] + lines["8:overhead"].amount))


def test_layer9_land_finance_taxes_vat_sales_and_sales_value_excluded():
    p = TINY_PARAMS.model_copy(update=dict(land_cost=100_000.0, finance_rate_annual=0.08, finance_months=12.0,
                                           taxes={"Stamp duty (entered)": 2000.0}, sales_value=500_000.0,
                                           sales_cost_fraction=0.02))
    s = settings(include_vat=True, vat_rate=0.20)
    est = tiny_estimate(params=p, settings=s)
    contract = est.boundary("contract_sum").amount
    lines = {ln.line_id: ln for ln in est.lines}
    assert lines["9:land"].amount == 100_000.0
    assert lines["9:finance"].amount == pytest.approx(0.08 * 12 / 12 * (100_000 + 0.5 * contract))
    assert lines["9:vat"].amount == pytest.approx(0.20 * contract)
    assert "check applicable treatment" in lines["9:vat"].description
    assert lines["9:sales_costs"].amount == pytest.approx(0.02 * 500_000)
    tdc = est.boundary("total_development_cost")
    expected = contract + 100_000 + lines["9:finance"].amount + 2000 + 0.2 * contract + 10_000
    assert tdc.amount == pytest.approx(expected)
    assert est.sales_value == 500_000.0
    # the sales value is never inside a boundary
    for b in est.boundaries:
        assert b.amount == pytest.approx(sum(est.layer_totals[layer.value] for layer in b.layers))
    assert all(ln.amount != 500_000.0 for ln in est.lines)
    assert "Sales value" in tdc.excludes
    # VAT is not added unless settings.include_vat
    est_novat = tiny_estimate(params=p)
    assert "9:vat" not in {ln.line_id for ln in est_novat.lines}


def test_layer9_incomplete_inputs_are_unresolved():
    p = TINY_PARAMS.model_copy(update=dict(finance_rate_annual=0.07, sales_cost_fraction=0.02))
    est = tiny_estimate(params=p)
    assert any("finance" in u for u in est.unresolved_items)
    assert any("sales costs" in u for u in est.unresolved_items)
    assert "total_development_cost" not in {b.key for b in est.boundaries}


def test_missing_rate_and_unresolved_quantity_are_listed_not_zeroed():
    est = tiny_estimate(boq=tiny_boq(unresolved=True), book=tiny_book(drop=("lab:carpentry", "plant:dumper")))
    joined = " | ".join(est.unresolved_items)
    assert "2.3.B1.pr.0" in joined and "pitch unknown" in joined
    assert "missing rate lab:carpentry per hr" in joined and "4.allow.kitchen" in joined
    assert "missing rate plant:dumper" in joined
    ids = {ln.line_id for ln in est.lines}
    assert "2:4.allow.kitchen" not in ids and "1:4.allow.kitchen" in ids
    assert all(not ln.line_id.endswith("2.3.B1.pr.0") for ln in est.lines)
    assert all(math.isfinite(ln.amount) for ln in est.lines)
    h = _hand_layers()
    assert est.layer_totals[CostLayer.LABOUR.value] == pytest.approx(h["L2"] - 40 * 35.0)


def test_delivery_charges_loads_estimate_and_param_fallbacks():
    dcs = rate("q-brick", "mat:brick", "nr", 0.75, source_type="supplier_quote", valid_until=date(2027, 1, 1),
               delivery_treatment="delivery_charged_separately", delivery_charge=85.0)
    est = tiny_estimate(book=tiny_book(dcs), logistics=None)
    lines = {ln.line_id: ln for ln in est.lines}
    assert lines["4:log.delivery_charge.brick"].amount == pytest.approx(85.0)
    # no logistics plan: one load per material order (2.5 t of bricks) + one per allowance item
    assert lines["4:log.delivery_loads"].quantity == 2.0
    nocharge = dcs.model_copy(update={"delivery_charge": None})
    est2 = tiny_estimate(book=tiny_book(nocharge))
    assert any("no delivery_charge" in u for u in est2.unresolved_items)
    # log / prelim rates missing -> CostParameters values, labelled
    est3 = tiny_estimate(book=tiny_book(drop=("log:skip", "log:delivery_load", "prelim:setup", "prelim:weekly")))
    l3 = {ln.line_id: ln for ln in est3.lines}
    assert l3["4:log.skips"].amount == pytest.approx(TINY_PARAMS.cost_per_skip)
    assert l3["4:log.delivery_loads"].amount == pytest.approx(3 * TINY_PARAMS.cost_per_delivery_load)
    assert l3["5:prelim.weekly"].amount == pytest.approx(10 * TINY_PARAMS.prelims_weekly_cost)
    assert "CostParameters" in l3["5:prelim.setup"].formula


def test_default_programme_is_flagged_and_excavator_fallback():
    est = tiny_estimate(programme_weeks=None)
    assert est.programme_weeks == TINY_PARAMS.default_programme_weeks
    assert any("Programme length assumed" in w for w in est.warnings)
    book = tiny_book(rate("r-ex-hr", "plant:excavator", "hr", 50.0), drop=("plant:excavation",))
    est2 = tiny_estimate(book=book)
    ln = {x.line_id: x for x in est2.lines}["3:1.all.fdn.0"]
    assert ln.cost_key == "plant:excavator" and ln.quantity == pytest.approx(1.0)  # 10 m3 x 0.10 hr/m3
    assert ln.amount == pytest.approx(50.0) and est2.unresolved_items == []


# =============================================================================
# Demo rates on a hand-built two-storey twin
# =============================================================================
@pytest.mark.parametrize("changes", [
    {},
    {"external_wall": "ew_timber_frame_brick"},
    {"external_wall": "ew_timber_frame_clad", "window": "win_alu_tg", "foundation": "fdn_raft"},
    {"foundation": "fdn_piled_allowance"},
    {"foundation": "fdn_strip"},
])
def test_demo_rates_price_every_line_of_a_two_storey_twin(changes):
    twin = two_storey_twin()
    if changes:
        twin = apply_construction_assemblies(twin, changes, LIB, actor="scenario")
    boq = calculate_quantities(twin, LIB)
    assert boq.unresolved == []
    est = estimate_construction_cost(boq, demo_rate_book(), CostParameters(), settings=SETTINGS, library=LIB)
    assert not [u for u in est.unresolved_items if "missing rate" in u]
    assert est.unresolved_items == []
    priced_qlines = {ln.quantity_line_id for ln in est.lines if ln.quantity_line_id}
    for ql in boq.lines:
        if ql.cost_key and (ql.purchased_qty or 0) > 0:
            assert ql.line_id in priced_qlines
    assert any("FICTIONAL" in w for w in est.warnings)
    c = est.boundary("contract_sum").amount / est.gia_m2
    assert 800 < c < 6000  # plausible order of magnitude for fictional rates (GBP/m2 GIA)
    # brick quote (delivery charged separately) and the expired tile quote are reflected
    uses_brick = any(ql.cost_key == "mat:facing_brick" and (ql.purchased_qty or 0) > 0 for ql in boq.lines)
    assert uses_brick == any(ln.line_id == "4:log.delivery_charge.facing_brick" for ln in est.lines)
    assert any("EXQ-2026-0398" in w for w in est.warnings)
    door = next(ln for ln in est.lines if ln.cost_key == "mat:door_composite")
    assert door.rate_value == pytest.approx(1155.0) and "VAT stripped" in door.formula


def test_engine_performance_under_20ms():
    boq = calculate_quantities(two_storey_twin(), LIB)
    book = demo_rate_book()
    params = CostParameters()
    estimate_construction_cost(boq, book, params, settings=SETTINGS, library=LIB)  # warm-up
    best = math.inf
    for _ in range(5):
        t0 = time.perf_counter()
        est = estimate_construction_cost(boq, book, params, settings=SETTINGS, library=LIB)
        best = min(best, time.perf_counter() - t0)
    assert len(boq.lines) >= 120 and len(est.lines) >= 150
    assert best < 0.020


# =============================================================================
# Adapters
# =============================================================================
def test_pricing_adapters(tmp_path):
    demo = FictionalDemoPricingAdapter()
    assert isinstance(demo, PricingAdapter) and demo.is_available()
    sub = demo.fetch_rates(["mat:facing_brick", "lab:bricklaying"], SETTINGS)
    assert {r.cost_key for r in sub.rates} == {"mat:facing_brick", "lab:bricklaying"}
    p = tmp_path / "quote.csv"
    p.write_text(_csv([dict(GOOD_ROW, rate_id="mq1", cost_key="mat:facing_brick", source_type="manual", value="0.7")]))
    manual = ManualCSVPricingAdapter(p, name="manual quotes")
    missing = ManualCSVPricingAdapter(tmp_path / "nope.csv")
    assert manual.is_available() and not missing.is_available()
    book = fetch_rate_book([demo, manual, missing], ["mat:facing_brick"], SETTINGS)
    assert any("unavailable" in w for w in book.warnings)
    r, v, _ = resolve_rate(book, "mat:facing_brick", "nr", settings=SETTINGS)
    assert r.rate_id == "EXQ-2026-0412-brick"  # valid supplier quote outranks the manual rate
    assert v == pytest.approx(0.72)


# =============================================================================
# Repeat-build economics
# =============================================================================
def _base_estimate():
    return tiny_estimate()


def _scen(**kw) -> ProductionScenario:
    base = dict(scenario_id="s", name="test", materials_per_house=100_000.0, site_labour_hours_per_house=1000.0,
                site_labour_rate=40.0, plant_per_house=5000.0, site_logistics_per_house=0.0,
                site_establishment_per_site=0.0, learning=LearningCurve(learning_rate=1.0, floor_fraction=1.0))
    base.update(kw)
    return ProductionScenario(**base)


def test_incremental_equals_difference_and_differs_from_average():
    sc = _scen(reusable_design_cost=50_000.0, tooling_cost=20_000.0, houses_per_site=25,
               site_establishment_per_site=40_000.0, learning=LearningCurve(learning_rate=0.9, floor_fraction=0.7))
    res = calculate_incremental_cost(_base_estimate(), sc, max_n=60, comparison_ns=(1, 10, 25, 50))
    rows = res.rows
    assert [r.n for r in rows] == list(range(1, 61))
    for a, b in zip(rows[:-1], rows[1:], strict=True):
        assert a.incremental_cost == b.total_cost - a.total_cost
        assert a.average_cost == a.total_cost / a.n
    c61 = total_cost_curve(_base_estimate(), sc, max_n=61)
    assert rows[-1].incremental_cost == pytest.approx(c61[-1] - c61[-2])
    assert rows[9].average_cost != pytest.approx(rows[9].incremental_cost)
    assert rows[9].average_cost > rows[9].incremental_cost  # one-off costs spread in the average
    for r in rows:
        assert sum(r.components.values()) == pytest.approx(r.total_cost)
    assert not any("max_n raised" in n for n in res.notes)
    raised = calculate_incremental_cost(_base_estimate(), sc, max_n=60)  # default comparison up to 100
    assert raised.comparison_ns == [1, 10, 25, 50, 100] and len(raised.rows) == 100
    assert any("max_n raised" in n for n in raised.notes)
    a = res.assumptions
    # the default model is the unit-time (Crawford-style) curve, not Wright's cumulative average (COST-12)
    assert a["learning_curve"]["learning_rate"] == 0.9 and a["learning_curve"]["model_key"] == "unit"
    assert "Crawford" in a["learning_curve"]["model"] and "Wright" not in a["learning_curve"]["model"]
    assert "boundary_definition" in a and a["steps"] and "per_house_inputs" in a


def test_learning_lowers_labour_per_house_down_to_floor():
    sc = _scen(learning=LearningCurve(learning_rate=0.9, floor_fraction=0.7, applies_to=["site_labour"]))
    curves = component_curves(_base_estimate(), sc, 200)
    lab = curves["site_labour"]
    per_house = [lab[0]] + [lab[i] - lab[i - 1] for i in range(1, len(lab))]
    assert per_house[0] == pytest.approx(1000 * 40.0)
    assert per_house[1] == pytest.approx(1000 * 40.0 * 0.9)  # one doubling
    assert per_house[3] == pytest.approx(1000 * 40.0 * 0.81)  # two doublings
    assert all(b <= a + 1e-9 for a, b in zip(per_house[:-1], per_house[1:], strict=True))
    assert per_house[-1] == pytest.approx(1000 * 40.0 * 0.7)  # floor reached
    f = learning_factors(8, sc.learning)
    assert f[7] == pytest.approx(0.729)


def test_step_costs_jump_at_capacity_thresholds():
    sc = _scen(factory_units_per_line=20, factory_line_cost=50_000.0, houses_per_site=25,
               site_establishment_per_site=30_000.0,
               step_costs=[StepCost(name="pumping station", every_n_units=30, cost=20_000.0, starts_after_units=10)])
    rows = calculate_incremental_cost(_base_estimate(), sc, max_n=60).rows
    inc = {r.n: r.incremental_cost for r in rows}
    base = inc[5]
    assert inc[19] == pytest.approx(base)
    assert inc[20] - base == pytest.approx(50_000.0)  # house 21 needs a second factory line
    assert inc[25] - base == pytest.approx(30_000.0)  # house 26 starts a second site
    assert inc[10] - base == pytest.approx(20_000.0)  # first step block starts with house 11
    assert inc[40] - base == pytest.approx(50_000.0 + 20_000.0)  # line 3 + second step block
    c = {r.n: r for r in rows}
    assert c[1].components["factory_lines"] == 50_000.0 and c[21].components["factory_lines"] == 100_000.0


def test_discount_tier_crossing_all_units_vs_incremental():
    tiers = [DiscountTier(min_units=10, discount_fraction=0.05)]
    M = 100_000.0
    au = component_curves(_base_estimate(), _scen(procurement_tiers=tiers), 12)["materials_site"]
    assert au[8] == pytest.approx(9 * M)
    assert au[9] == pytest.approx(10 * M * 0.95)
    assert au[9] - au[8] == pytest.approx(0.5 * M)  # all-units re-pricing at the crossing
    assert au[10] - au[9] == pytest.approx(0.95 * M)
    inc = component_curves(_base_estimate(), _scen(procurement_tiers=tiers, discount_mode="incremental"),
                           12)["materials_site"]
    assert inc[9] - inc[8] == pytest.approx(0.95 * M)
    assert inc[8] - inc[7] == pytest.approx(M)
    res = calculate_incremental_cost(_base_estimate(), _scen(procurement_tiers=tiers), max_n=12)
    assert res.assumptions["discount_mode"] == "all_units"
    assert res.rows[8].incremental_cost < res.rows[7].incremental_cost


def test_labour_scarcity_premium_raises_incremental_cost_beyond_threshold():
    sc = _scen(labour_scarcity_threshold_units=50, labour_scarcity_premium=0.10)
    rows = {r.n: r for r in calculate_incremental_cost(_base_estimate(), sc, max_n=60).rows}
    assert rows[50].incremental_cost - rows[49].incremental_cost == pytest.approx(0.10 * 1000 * 40.0)
    assert rows[55].incremental_cost == pytest.approx(rows[50].incremental_cost)
    no_prem = {r.n: r for r in calculate_incremental_cost(_base_estimate(), _scen(), max_n=60).rows}
    assert rows[49].incremental_cost == pytest.approx(no_prem[49].incremental_cost)
    assert rows[50].incremental_cost > no_prem[50].incremental_cost


def test_factory_gate_incremental_below_installed_and_boundaries():
    sc = _scen(method="offsite_panelised", factory_labour_hours_per_house=300.0, factory_labour_rate=30.0,
               factory_overhead_per_house=1000.0, tooling_cost=40_000.0, factory_setup_cost=100_000.0,
               transport_loads_per_house=3, transport_cost_per_load=600.0)
    out = factory_vs_installed(_base_estimate(), sc, max_n=100)
    fg, ins = out["factory_gate"], out["installed"]
    assert fg.boundary == "factory_gate" and ins.boundary == "installed"
    for a, b in zip(fg.rows, ins.rows, strict=True):
        assert a.incremental_cost < b.incremental_cost
        assert a.total_cost < b.total_cost
    assert fg.rows[0].components["materials_factory"] == pytest.approx(0.35 * 100_000)  # method default share
    assert ins.assumptions["per_house_inputs"]["factory_material_fraction"]["source"].startswith("assumed")
    assert [r["n"] for r in out["comparison"]] == [1, 10, 25, 50, 100]
    assert 0 < out["comparison"][0]["factory_share_of_installed"] < 1
    # development = installed + fees on the fee base (installed - design - factory capex; COST-3), then
    # contingency, overhead and margin in cascade.  The one-off design fee is charged once here because the
    # scenario has no reusable design cost.
    cp = CostParameters()
    dev = calculate_incremental_cost(_base_estimate(), sc, boundary="development", max_n=10, cost_params=cp)
    capex = 40_000.0 + 100_000.0
    i1, i5 = ins.rows[0].total_cost, ins.rows[4].total_cost
    fees = sum(x.fraction * ((i5 if x.recurs_per_house else i1) - capex) for x in cp.fees)
    k = (1 + cp.contingency_fraction) * (1 + cp.overhead_fraction) * (1 + cp.margin_fraction)
    assert dev.rows[4].total_cost == pytest.approx((i5 + fees) * k)
    assert dev.rows[4].components["fees"] == pytest.approx(fees)
    with pytest.raises(ValueError):
        calculate_incremental_cost(_base_estimate(), sc, boundary="gross")


def test_scenario_defaults_come_from_the_single_house_estimate():
    est = _base_estimate()
    sc = ProductionScenario(scenario_id="d", name="defaults", site_establishment_per_site=0.0,
                            learning=LearningCurve(learning_rate=1.0))
    res = calculate_incremental_cost(est, sc, max_n=2)
    row1 = res.rows[0]
    hours = sum(ln.quantity for ln in est.lines if ln.layer == CostLayer.LABOUR)
    assert hours == pytest.approx(63.5)
    assert row1.components["materials_site"] == pytest.approx(est.layer_totals["1_materials"])
    assert row1.components["site_labour"] == pytest.approx(hours * sc.site_labour_rate)  # scenario rate
    assert row1.components["plant"] == pytest.approx(est.layer_totals["3_plant"])
    assert row1.components["site_logistics"] == pytest.approx(est.layer_totals["4_logistics_waste"])
    inputs = res.assumptions["per_house_inputs"]
    assert inputs["materials_per_house"]["source"].startswith("single-house estimate")
    assert inputs["estimate_blended_labour_rate"]["value"] == pytest.approx(est.layer_totals["2_labour"] / hours)
    assert any("blended labour rate" in n for n in res.notes)
    # results survive a JSON save / load of the scenario unchanged
    reloaded = ProductionScenario.model_validate_json(sc.model_dump_json())
    assert calculate_incremental_cost(est, reloaded, max_n=2).rows == res.rows


def test_demo_production_scenarios_run():
    boq = calculate_quantities(two_storey_twin(), LIB)
    est = estimate_construction_cost(boq, demo_rate_book(), CostParameters(), settings=SETTINGS, library=LIB)
    site, panel = demo_production_scenarios(est)
    for sc in (site, panel):
        res = calculate_incremental_cost(est, sc)
        by_n = {r.n: r for r in res.rows}
        assert by_n[100].average_cost < by_n[1].average_cost
        assert all(math.isfinite(r.total_cost) for r in res.rows)
    out = factory_vs_installed(est, panel)
    assert all(a["factory_gate_incremental"] < a["installed_incremental"] for a in out["comparison"])
