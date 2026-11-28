"""Bénéficiaires : vérification de format, revue à quatre yeux, versions immuables, suspension."""
import pytest
from sqlalchemy import text

from horizon.core.iban import check_format, make_iban


def de_entity(api):
    return {e["name"]: e["id"] for e in api.get("katrin", "/v1/me").json()["entities"]}["Lumière Deutschland"]


def test_iban_format_check_is_not_proof_of_existence(api):
    good = make_iban("DE", "999990000077778888")
    r = api.post("claire", "/v1/beneficiaries/validate-iban", json={"iban": good}).json()
    assert r["format_valid"] and not r["account_existence_verified"] and not r["holder_name_verified"]
    assert "ne prouve ni l'existence" in r["scope"]
    assert not check_format(good[:-1] + ("0" if good[-1] != "0" else "1"))["format_valid"]
    r = api.post("katrin", "/v1/beneficiaries", json={"entity_id": de_entity(api), "name": "Kaputt GmbH",
                                                      "iban": "DE00123", "country_code": "DE"})
    assert r.status_code == 422


def test_four_eyes_review(api):
    r = api.post("katrin", "/v1/beneficiaries", json={"entity_id": de_entity(api), "name": "Neu Lieferant GmbH",
                                                      "iban": make_iban("DE", "999990000077778888"), "country_code": "DE"})
    assert r.status_code == 201
    b = r.json()
    assert b["status"] == "PENDING_REVIEW" and b["current_version"]["verification"]["name_match"]["status"] == "NOT_PERFORMED"
    api.step_up("katrin")
    r = api.post("katrin", f"/v1/beneficiaries/{b['id']}/review", json={"decision": "APPROVE"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "SEGREGATION_OF_DUTIES"
    api.step_up("sophie")
    r = api.post("sophie", f"/v1/beneficiaries/{b['id']}/review", json={"decision": "APPROVE"})
    assert r.json()["status"] == "ACTIVE"
    r = api.patch("katrin", f"/v1/beneficiaries/{b['id']}", json={"name": "Neuer Lieferant GmbH"})
    v = r.json()
    assert v["status"] == "PENDING_REVIEW" and len(v["versions"]) == 2
    assert v["versions"][0]["change_kind"] == "MATERIAL" and v["versions"][0]["changed_fields"] == ["name"]
    assert v["approved_version_id"] == v["versions"][1]["id"]  # l'ancienne version approuvée reste la référence


def test_versions_are_immutable_in_database(db):
    with pytest.raises(Exception, match="immuables"):
        db.execute(text("UPDATE beneficiary_versions SET iban = 'FR0000' WHERE version_no = 1"))
    db.rollback()
    with pytest.raises(Exception, match="interdite"):
        db.execute(text("DELETE FROM beneficiary_versions"))
    db.rollback()


def test_suspension_blocks_payments(api):
    b = api.batch([("Acier Rhône SAS", "70000.00", "x")])
    api.approve("sophie", b)
    bene = api.beneficiaries()["Acier Rhône SAS"]
    r = api.post("sophie", f"/v1/beneficiaries/{bene['id']}/suspension", json={"suspend": True, "reason": "Soupçon de fraude"})
    assert r.status_code == 200 and r.json()["status"] == "SUSPENDED"
    nb = api.get_batch(b["id"])
    assert nb["status"] == "TO_REVIEW" and nb["approvals"][0]["state"] == "INVALIDATED"
    acc = api.account("Lumière France — Compte principal")
    r = api.post("claire", "/v1/payment-batches", json={"debtor_account_id": acc["id"], "payments": [
        {"beneficiary_id": bene["id"], "amount": "10.00"}]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BENEFICIARY_NOT_USABLE"
    r = api.post("sophie", f"/v1/beneficiaries/{bene['id']}/suspension", json={"suspend": False, "reason": "Levée après contrôle"})
    assert r.json()["status"] == "ACTIVE"
