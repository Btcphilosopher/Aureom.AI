"""Prévisions : absence de double comptage, scénarios, fourchette documentée."""
from decimal import Decimal

from tests.conftest import FR_LINES


def scenarios(api):
    return {s["code"]: s["id"] for s in api.get("claire", "/v1/cashflow-scenarios").json()["data"]}


def run(api, code="CENTRAL", horizon=30):
    r = api.post("claire", "/v1/forecasts", json={"scenario_id": scenarios(api)[code], "horizon_days": horizon})
    assert r.status_code == 201, r.text
    return r.json()


def closings(f):
    return {s["date"]: Decimal(s["closing"]["amount"]) for s in f["series"]}


def test_execution_moves_amount_from_planned_to_observed_without_double_count(api):
    b = api.batch(FR_LINES)
    api.approve("sophie", b)
    api.approve("marc", b)
    before = run(api)
    planned = [ln for ln in before["lines"] if ln["source_type"] == "payment" and ln["source_id"] in
               {p["id"] for p in b["payments"]}]
    assert sum(Decimal(ln["amount"]["amount"]) for ln in planned) == Decimal("-180000.00")
    api.run_jobs()
    after = run(api)
    assert Decimal(after["inputs"]["starting_balance"]["amount"]) == Decimal(before["inputs"]["starting_balance"]["amount"]) - 180000
    assert not [ln for ln in after["lines"] if ln["source_id"] in {p["id"] for p in b["payments"]}]
    cb, ca = closings(before), closings(after)
    assert all(cb[d] == ca[d] for d in list(cb)[1:])  # J+1 à J+30 identiques


def test_forecast_starts_from_booked_not_available(api):
    b = api.batch(FR_LINES)
    api.approve("sophie", b)
    api.approve("marc", b)  # réservé mais non comptabilisé
    f = run(api)
    assert f["inputs"]["starting_balance"]["amount"] == "24800000.00"  # réservation non déduite du départ
    assert any(ln["source_type"] == "payment" for ln in f["lines"])  # ...car comptée comme décaissement


def test_received_expected_receipt_leaves_forecast(api):
    exp = api.get("claire", "/v1/expected-receipts").json()["data"]
    target = next(e for e in exp if e["counterparty"].startswith("Hôtellerie Saint-Clair"))
    before = run(api)
    r = api.post("claire", "/v1/demo/simulator/incoming", json={"expected_receipt_id": target["id"]})
    assert r.status_code == 200 and r.json()["deliveries"][0]["outcome"] == "APPLIED"
    after = run(api)
    assert Decimal(after["inputs"]["starting_balance"]["amount"]) - Decimal(before["inputs"]["starting_balance"]["amount"]) == 1200000
    assert not [ln for ln in after["lines"] if ln["source_id"] == target["id"]]
    assert any(x.get("source_id") == target["id"] for x in after["excluded"])
    assert after["series"][-1]["closing"] == before["series"][-1]["closing"]
    exp2 = {e["id"]: e for e in api.get("claire", "/v1/expected-receipts").json()["data"]}
    assert exp2[target["id"]]["status"] == "RECEIVED"


def test_recurring_occurrence_covered_by_payment_is_not_counted_twice(api):
    rec = api.get("claire", "/v1/recurring-assumptions").json()["data"]
    rent = next(a for a in rec if a["label"] == "Loyer siège Paris")
    f = run(api)
    occ = next(ln for ln in f["lines"] if ln["source_id"].startswith(f"recurring:{rent['id']}"))
    ref = occ["source_id"]
    benes = api.beneficiaries()
    acc = api.account("Lumière France — Compte principal")
    r = api.post("claire", "/v1/payment-batches", json={"debtor_account_id": acc["id"], "label": "Loyer",
                                                        "payments": [{"beneficiary_id": benes["Cabinet Delorme Conseil"]["id"],
                                                                      "amount": "185000.00", "forecast_ref": ref}]})
    b = r.json()
    api.post("claire", f"/v1/payment-batches/{b['id']}/submit-for-approval", json={"expected_version": b["version"]})
    f2 = run(api)
    assert not [ln for ln in f2["lines"] if ln["source_id"] == ref]
    assert any(x.get("source_id") == ref and "couverte" in x["reason"] for x in f2["excluded"])
    assert sum(1 for ln in f2["lines"] if ln["source_type"] == "payment" and ln["amount"]["amount"] == "-185000.00") == 1
    # après exécution, l'occurrence est « réalisée »
    api.approve("sophie", b)
    api.approve("marc", b)
    api.run_jobs()
    f3 = run(api)
    assert any(x.get("source_id") == ref and x["reason"] == "Occurrence réalisée" for x in f3["excluded"])


def test_band_is_envelope_of_documented_scenarios(api):
    ch = api.get("claire", "/v1/forecasts/chart", params={"horizon_days": 90}).json()
    assert "enveloppe" in ch["band_method"]
    assert ch["observed"][-1]["date"] == ch["boundary_date"] == ch["forecast"][0]["date"]
    for f, b in zip(ch["forecast"], ch["band"]):
        assert Decimal(b["low"]) <= Decimal(f["value"]) <= Decimal(b["high"])
    assert any(Decimal(b["high"]) > Decimal(b["low"]) for b in ch["band"])
    p = run(api, "PRUDENT", 90)
    fav = run(api, "FAVORABLE", 90)
    assert closings(p) and closings(fav)
    last = list(closings(p))[-1]
    assert Decimal(ch["band"][-1]["low"]) == min(closings(p)[last], closings(fav)[last], Decimal(ch["forecast"][-1]["value"]))


def test_scenario_creation_and_horizon_validation(api):
    r = api.post("claire", "/v1/cashflow-scenarios", json={"code": "STRESS", "name": "Stress", "receipts_haircut_pct": 50,
                                                           "receipts_delay_days": 30})
    assert r.status_code == 201
    r = api.post("claire", "/v1/forecasts", json={"scenario_id": r.json()["id"], "horizon_days": 45})
    assert r.status_code == 422
    stress = run(api, "STRESS", 90)
    central = run(api, "CENTRAL", 90)
    assert Decimal(stress["totals"]["inflows"]["amount"]) < Decimal(central["totals"]["inflows"]["amount"])
    r = api.get("claire", f"/v1/forecasts/{stress['id']}")
    assert r.status_code == 200 and r.json()["series"] == stress["series"]
    assert api.get("lucas", f"/v1/forecasts/{stress['id']}").status_code == 404


def test_external_accounts_excluded_and_stated(api):
    f = run(api)
    assert any("externe" in x["reason"] for x in f["excluded"])
