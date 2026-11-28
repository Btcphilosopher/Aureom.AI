"""Rapprochement, centre de décisions, audit chaîné, export et contrat d'API."""
import io
import json
import zipfile

import psycopg
import pytest
from sqlalchemy import text

from horizon.core.db import SessionLocal
from horizon.modules.audit import service as audit
from tests.conftest import URL


def fr_account(api):
    return api.account("Lumière France — Compte principal")


def test_reconciliation_detects_fee_and_ack_does_not_resolve(api):
    acc = fr_account(api)
    run = api.post("claire", "/v1/reconciliation/runs", json={"account_id": acc["id"]}).json()
    assert run["cases_opened"] == 1
    case = api.get("claire", "/v1/reconciliation-cases").json()["data"][0]
    assert case["kind"] == "MISSING_IN_LEDGER" and case["statement_amount"]["amount"] == "-35.00"
    assert case["owner"] == "Claire Martin" and case["due_date"]
    r = api.post("claire", f"/v1/reconciliation-cases/{case['id']}/acknowledge", json={"note": "Vu"})
    assert r.json()["status"] == "ACKNOWLEDGED"
    items = api.get("claire", "/v1/decisions").json()["data"]
    assert any(i["source"]["object_id"] == case["id"] for i in items)  # toujours présent
    r = api.post("claire", f"/v1/reconciliation-cases/{case['id']}/resolve",
                 json={"action": "POST_ADJUSTMENT", "note": "Frais conformes à la grille"})
    assert r.status_code == 401  # réauthentification
    api.step_up("claire")
    r = api.post("claire", f"/v1/reconciliation-cases/{case['id']}/resolve",
                 json={"action": "POST_ADJUSTMENT", "note": "Frais conformes à la grille"})
    assert r.status_code == 200 and r.json()["status"] == "RESOLVED" and r.json()["resolution_entry_id"]
    assert fr_account(api)["balance"]["booked"]["amount"] == "12399965.00"
    run2 = api.post("claire", "/v1/reconciliation/runs", json={"account_id": acc["id"]}).json()
    assert run2["cases_opened"] == 0 and run2["matched"] == 1  # la régularisation liée rapproche la ligne


def test_decision_items_have_source_owner_due_state(api):
    items = api.get("claire", "/v1/decisions").json()["data"]
    assert {i["kind"] for i in items} >= {"BATCH_APPROVAL", "BENEFICIARY_REVIEW", "FINANCING_DEADLINE", "STALE_DATA"}
    for i in items:
        assert i["source"]["module"] and i["owner"] and i["due_date"] and i["state"]
    stale = next(i for i in items if i["kind"] == "STALE_DATA")
    r = api.post("claire", "/v1/decisions/acknowledge", json={"key": stale["key"], "note": "Relance faite"})
    assert r.json()["resolved"] is False
    again = next(i for i in api.get("claire", "/v1/decisions").json()["data"] if i["key"] == stale["key"])
    assert again["acknowledgements"][0]["by"] == "Claire Martin" and again["state"] == "Relevé attendu"


def test_overview_kpis_are_computed_and_explained(api):
    ov = api.get("claire", "/v1/overview").json()
    k = {x["key"]: x for x in ov["kpis"]}
    assert k["available_liquidity"]["value"]["amount"] == "24800000.00"
    comps = k["available_liquidity"]["explain"]["components"]
    assert sum(float(c["available_in_base"]["amount"]) for c in comps) == 24_800_000.0
    assert k["available_liquidity"]["explain"]["excluded"][0]["reason"].startswith("Compte externe")
    assert k["payments_to_approve"]["value"]["count"] == 5
    assert k["expected_receipts_7d"]["value"]["amount"] == "3600000.00"
    assert len(k["expected_receipts_7d"]["explain"]["components"]) == 4
    assert k["alerts"]["value"]["count"] == 3


def test_audit_chain_is_append_only_and_tamper_evident(api, db):
    api.batch([("Acier Rhône SAS", "10.00", "x")])
    org_id = db.execute(text("SELECT id FROM organizations WHERE name = 'Groupe Lumière'")).scalar()
    assert audit.verify_chain(db, org_id)["valid"]
    with pytest.raises(Exception, match="immuable"):
        db.execute(text("UPDATE audit_events SET action = 'x' WHERE id = (SELECT min(id) FROM audit_events)"))
    db.rollback()
    # Un super-utilisateur qui désactive le trigger pour altérer l'historique est détecté par la chaîne.
    try:
        su = psycopg.connect(host=URL.host, port=URL.port, user="postgres", dbname=URL.database, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("connexion super-utilisateur indisponible")
    with su:
        su.execute("ALTER TABLE audit_events DISABLE TRIGGER audit_events_append_only")
        su.execute("UPDATE audit_events SET details = '{\"falsifié\": true}' WHERE id = "
                   "(SELECT min(id) + 3 FROM audit_events WHERE organization_id = %s)", (org_id,))
        su.execute("ALTER TABLE audit_events ENABLE TRIGGER audit_events_append_only")
    with SessionLocal() as s:
        res = audit.verify_chain(s, org_id)
    assert res["valid"] is False and res["broken_at_event_id"]


def test_export_contains_report_and_verifiable_audit_trail(api):
    api.post("claire", "/v1/reconciliation/runs", json={"account_id": fr_account(api)["id"]})
    r = api.post("ines", "/v1/reports/treasury-export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert set(z.namelist()) == {"rapport.csv", "piste_audit.csv", "manifeste.json"}
    m = json.loads(z.read("manifeste.json"))
    import hashlib

    for name, sha in m["files"].items():
        assert hashlib.sha256(z.read(name)).hexdigest() == sha
    assert m["audit_chain"]["valid"] and m["environment"] == "DÉMONSTRATION"
    report = z.read("rapport.csv").decode("utf-8-sig")
    assert "DÉMONSTRATION" in report and "24800000.00" in report
    events = api.get("ines", "/v1/audit-events", params={"action": "report.exported"}).json()["data"]
    assert events and events[0]["details"]["sha256"] == r.headers["x-report-sha256"]
    assert api.post("julien", "/v1/reports/treasury-export").status_code == 403


def test_structured_errors_pagination_and_versioning(api):
    r = api.get("claire", "/v1/payment-batches/00000000-0000-0000-0000-000000000000")
    body = r.json()
    assert r.status_code == 404 and set(body["error"]) == {"code", "message", "details", "request_id"}
    assert r.headers["x-request-id"] == body["error"]["request_id"]
    r = api.post("claire", "/v1/payment-batches", json={"debtor_account_id": "x", "payments": []})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR" and r.json()["error"]["details"]
    r = api.post("claire", "/v1/payment-batches", json={"debtor_account_id": fr_account(api)["id"], "unexpected": 1,
                                                        "payments": [{"beneficiary_id": fr_account(api)["id"], "amount": "1.001"}]})
    assert r.status_code == 422  # champs inconnus et précision refusés
    p1 = api.get("claire", "/v1/accounts", params={"limit": 2}).json()
    assert len(p1["data"]) == 2 and p1["page"]["total"] == 5 and p1["page"]["next_cursor"]
    p2 = api.get("claire", "/v1/accounts", params={"limit": 2, "cursor": p1["page"]["next_cursor"]}).json()
    assert {a["id"] for a in p1["data"]}.isdisjoint({a["id"] for a in p2["data"]})
    assert api.get("claire", "/v1/accounts", params={"cursor": "%%%"}).json()["error"]["code"] == "INVALID_CURSOR"
    assert api.get("claire", "/v1/accounts", params={"limit": 500}).status_code == 422
    r = api.get("claire", "/v1/me", headers={"Horizon-API-Version": "1999-01-01"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "UNSUPPORTED_API_VERSION"
    r = api.get("claire", "/v1/me")
    assert r.headers["horizon-api-version"] == "2026-11-01" and r.headers["x-horizon-environment"] == "demonstration"


def test_openapi_exposes_required_endpoints(api):
    paths = api.c.get("/openapi.json").json()["paths"]
    required = [("get", "/v1/overview"), ("get", "/v1/accounts"), ("get", "/v1/accounts/{account_id}/transactions"),
                ("post", "/v1/beneficiaries"), ("post", "/v1/payment-batches"),
                ("post", "/v1/payment-batches/{batch_id}/submit-for-approval"),
                ("post", "/v1/payment-batches/{batch_id}/approvals"), ("get", "/v1/payments/{payment_id}"),
                ("post", "/v1/cashflow-scenarios"), ("get", "/v1/forecasts/{forecast_id}"), ("post", "/v1/fx-quotes"),
                ("get", "/v1/reconciliation-cases"), ("get", "/v1/audit-events")]
    for method, path in required:
        assert method in paths[path], f"{method.upper()} {path}"
