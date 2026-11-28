"""Cycle de vie des paiements, exécution simulée, doublons, rejets, résultats inconnus, reprise."""
import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from horizon.core import clock
from horizon.core.db import SessionLocal
from horizon.core.errors import Conflict
from horizon.modules.integrations.bank_simulator import bank, sign
from horizon.modules.integrations.models import SimBankEvent, SimBankOrder
from horizon.modules.jobs import queue
from horizon.modules.jobs.models import Job
from horizon.modules.ledger.models import JournalEntry
from horizon.modules.payments import execution, state
from horizon.modules.payments.models import Payment
from tests.conftest import FR_LINES


def approved_batch(api, lines=FR_LINES, **kw):
    b = api.batch(lines, **kw)
    api.approve("sophie", b)
    if b["required_approvals"] > 1:
        api.approve("marc" if kw.get("account", "Lumière France").startswith("Lumière France") else "katrin", b)
    return api.get_batch(b["id"])


def test_full_lifecycle_distinguishes_receipt_acceptance_execution(api):
    b = approved_batch(api)
    queue.run_one()  # execute_batch → SOUMIS
    queue.run_one()  # submit_payment ligne 1 → réception technique
    p = api.get("claire", f"/v1/payments/{b['payments'][0]['id']}").json()
    assert p["status"] == "SUBMITTED" and p["technical_ack_at"] and p["executed_at"] is None
    bal_mid = api.account("Lumière France — Compte principal")["balance"]
    assert bal_mid["reserved"]["minor_units"] == 18_000_000  # rien n'est débité sur simple réception technique
    api.run_jobs()
    b = api.get_batch(b["id"])
    assert b["status"] == "COMPLETED"
    p = api.get("claire", f"/v1/payments/{b['payments'][0]['id']}").json()
    labels = [e["to_label"] for e in p["events"]]
    assert labels[-3:] == ["Réception technique", "Accepté par le système destinataire", "Exécuté selon confirmation"]
    bal = api.account("Lumière France — Compte principal")["balance"]
    assert bal["booked"]["minor_units"] == 12_400_000_00 - 18_000_000 and bal["reserved"]["minor_units"] == 0


def test_duplicate_event_does_not_double_debit(api):
    b = approved_batch(api)
    api.run_jobs()
    pid = b["payments"][0]["id"]
    with SessionLocal() as s:
        p = s.get(Payment, pid)
        ev = s.scalar(select(SimBankEvent).where(SimBankEvent.event_type == "PAYMENT_SETTLED",
                                                 SimBankEvent.payload["submission_key"].as_string() == p.submission_key))
        eid = ev.event_id
    booked = api.account("Lumière France — Compte principal")["balance"]["booked"]
    r1 = execution.redeliver(eid)
    r2 = execution.redeliver(eid)
    assert r1["outcome"] == r2["outcome"] == "DUPLICATE_IGNORED" and r2["duplicate_deliveries"] == 2
    # Même règlement sous un AUTRE identifiant d'événement : l'écriture idempotente protège encore.
    forged = dict(ev.payload, event_id="sim-evt-different-id")
    body = json.dumps(forged, sort_keys=True).encode()
    with SessionLocal() as s:
        res = execution.ingest_bank_event(s, body, sign(body))
        s.commit()
    assert res["outcome"] == "IGNORED_ALREADY_FINAL"
    assert api.account("Lumière France — Compte principal")["balance"]["booked"] == booked
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(JournalEntry).where(JournalEntry.reference_id == pid)) == 1


def test_invalid_webhook_signature_rejected(api):
    r = api.c.post("/v1/integrations/bank-simulator/events", content=b'{"event_id":"x","event_type":"PAYMENT_SETTLED"}',
                   headers={"X-Horizon-Signature": "sha256=deadbeef"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_SIGNATURE"


def test_partial_batch_keeps_individual_results(api):
    # Imprimerie OK, Ostwald n'est pas dans l'entité FR → on utilise un bénéficiaire FR « clôturé » créé pour le test
    from horizon.core.iban import make_iban

    ents = {e["name"]: e["id"] for e in api.get("claire", "/v1/me").json()["entities"]}
    r = api.post("claire", "/v1/beneficiaries", json={"entity_id": ents["Lumière France"], "name": "Ancien Fournisseur SA",
                                                      "iban": make_iban("FR", "99999000050000000000404"), "country_code": "FR"})
    bid = r.json()["id"]
    api.step_up("sophie")
    assert api.post("sophie", f"/v1/beneficiaries/{bid}/review", json={"decision": "APPROVE"}).status_code == 200
    b = approved_batch(api, lines=[("Acier Rhône SAS", "40000.00", "OK"), ("Ancien Fournisseur SA", "30000.00", "KO")])
    api.run_jobs()
    b = api.get_batch(b["id"])
    st = {p["beneficiary"]["name"]: (p["status"], p["rejection_code"]) for p in b["payments"]}
    assert st == {"Acier Rhône SAS": ("EXECUTED", None), "Ancien Fournisseur SA": ("REJECTED", "AC04")}
    assert b["status"] == "COMPLETED" and "1 exécuté(s), 1 rejeté(s)" in b["status_reason"]
    bal = api.account("Lumière France — Compte principal")["balance"]
    assert bal["booked"]["minor_units"] == 12_400_000_00 - 4_000_000 and bal["reserved"]["minor_units"] == 0


def _orders(key):
    with SessionLocal() as s:
        return s.scalar(select(func.count()).select_from(SimBankOrder).where(SimBankOrder.submission_key == key))


def test_unknown_result_after_record_is_searched_not_resubmitted(api):
    bank.inject_fault("TIMEOUT_AFTER_RECORD", "UNK-A")
    b = approved_batch(api, lines=[("Acier Rhône SAS", "20000.00", "UNK-A")])
    queue.run_one()
    queue.run_one()
    pid = b["payments"][0]["id"]
    p = api.get("claire", f"/v1/payments/{pid}").json()
    assert p["status"] == "UNKNOWN"
    cases = api.get("claire", "/v1/reconciliation-cases").json()["data"]
    assert any(c["kind"] == "UNKNOWN_PAYMENT_RESULT" and c["status"] == "OPEN" for c in cases)
    api.run_jobs()
    p = api.get("claire", f"/v1/payments/{pid}").json()
    assert p["status"] == "EXECUTED" and p["submission_attempts"] == 1
    assert _orders(p["submission_key"]) == 1
    assert any("ordre retrouvé" in (e["reason"] or "") for e in p["events"])
    cases = api.get("claire", "/v1/reconciliation-cases").json()["data"]
    assert all(c["status"] == "RESOLVED" for c in cases if c["kind"] == "UNKNOWN_PAYMENT_RESULT")


def test_unknown_result_before_record_resubmits_with_same_key(api):
    bank.inject_fault("TIMEOUT_BEFORE_RECORD", "UNK-B")
    b = approved_batch(api, lines=[("Acier Rhône SAS", "20000.00", "UNK-B")])
    api.run_jobs()
    p = api.get("claire", f"/v1/payments/{b['payments'][0]['id']}").json()
    assert p["status"] == "EXECUTED" and p["submission_attempts"] == 2
    assert _orders(p["submission_key"]) == 1
    assert any("introuvable" in (e["reason"] or "") for e in p["events"])


def test_interrupted_submission_is_recovered(api):
    b = approved_batch(api, lines=[("Acier Rhône SAS", "20000.00", "CRASH")])
    queue.run_one()  # execute_batch : paiement SOUMIS, tâche de soumission en file
    with SessionLocal() as s:  # le travailleur « meurt » : on supprime la tâche de soumission
        s.query(Job).filter(Job.kind == "submit_payment").delete()
        s.commit()
    clock.advance(timedelta(minutes=6))
    with SessionLocal() as s:
        queue.enqueue(s, "recover_stale_submissions", {}, "recover:test")
        s.commit()
    api.run_jobs()
    p = api.get("claire", f"/v1/payments/{b['payments'][0]['id']}").json()
    assert p["status"] == "EXECUTED" and _orders(p["submission_key"]) == 1
    assert any("interrompue" in (e["reason"] or "") for e in p["events"])


def test_expired_job_lease_is_reclaimed(api):
    with SessionLocal() as s:
        queue.enqueue(s, "run_scheduled", {}, "lease:test")
        s.commit()
        job = queue.claim(s)
        s.commit()
        assert job.status == "RUNNING"
    clock.advance(timedelta(minutes=3))  # le bail (2 min) expire : travailleur présumé mort
    assert queue.run_one() is True
    with SessionLocal() as s:
        j = s.scalar(select(Job).where(Job.dedup_key == "lease:test"))
        assert j.status == "DONE" and j.attempts == 2


def test_enqueue_is_idempotent(db):
    queue.enqueue(db, "run_scheduled", {}, "same-key")
    queue.enqueue(db, "run_scheduled", {}, "same-key")
    db.commit()
    assert db.scalar(select(func.count()).select_from(Job).where(Job.dedup_key == "same-key")) == 1


def test_cancellation_depends_on_state(api):
    b = approved_batch(api)
    r = api.post("claire", f"/v1/payment-batches/{b['id']}/cancel", json={"reason": "Doublon de facture"})
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert api.account("Lumière France — Compte principal")["balance"]["reserved"]["minor_units"] == 0
    b2 = approved_batch(api)
    api.run_jobs()
    r = api.post("claire", f"/v1/payment-batches/{b2['id']}/cancel", json={"reason": "Trop tard"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_CANCELLABLE"


def test_idempotency_key(api):
    b1 = api.batch(FR_LINES, key="k-1", submit=False)
    acc = api.account("Lumière France — Compte principal")
    benes = api.beneficiaries()
    body = {"debtor_account_id": acc["id"], "label": "Autre",
            "payments": [{"beneficiary_id": benes["Acier Rhône SAS"]["id"], "amount": "1.00"}]}
    r = api.post("claire", "/v1/payment-batches", json=body, headers={"Idempotency-Key": "k-1"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert b1["status"] == "DRAFT"


def test_external_read_only_account_cannot_be_debited(api):
    acc = api.account("Lumière France — Compte GBP")
    benes = api.beneficiaries()
    r = api.post("claire", "/v1/payment-batches", json={"debtor_account_id": acc["id"], "payments": [
        {"beneficiary_id": benes["Acier Rhône SAS"]["id"], "amount": "10.00"}]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "ACCOUNT_READ_ONLY"


def test_csv_import_all_or_nothing(api):
    benes = api.beneficiaries()
    acc = api.account("Lumière France — Compte principal")
    iban1 = benes["Acier Rhône SAS"]["current_version"]["iban"]
    iban2 = benes["Logistique Seine SARL"]["current_version"]["iban"]
    good = f"iban;montant;libelle\n{iban1};1500,50;FAC A\n{iban2};2500.00;FAC B\n".encode()
    r = api.post("claire", "/v1/payment-batches/import-csv", files={"file": ("lot.csv", good, "text/csv")},
                 data={"debtor_account_id": acc["id"], "label": "Import"})
    assert r.status_code == 201, r.text
    assert r.json()["total"]["amount"] == "4000.50" and r.json()["kind"] == "CSV_IMPORT"
    bad = f"iban;montant;libelle\n{iban1};abc;X\nFR7600000000000000000000000;10;Y\n".encode()
    r = api.post("claire", "/v1/payment-batches/import-csv", files={"file": ("lot.csv", bad, "text/csv")},
                 data={"debtor_account_id": acc["id"]})
    assert r.status_code == 422
    assert [e["code"] for e in r.json()["error"]["details"]["errors"]] == ["INVALID_AMOUNT", "UNKNOWN_BENEFICIARY"]


def test_return_of_funds_restores_balance(api):
    b = approved_batch(api)
    api.run_jobs()
    pid = b["payments"][1]["id"]
    booked = api.account("Lumière France — Compte principal")["balance"]["booked"]["minor_units"]
    r = api.post("claire", "/v1/demo/simulator/returns", json={"payment_id": pid, "reason_code": "MD06"})
    assert r.status_code == 200, r.text
    p = api.get("claire", f"/v1/payments/{pid}").json()
    assert p["returned"]["amount"] == "60000.00" and len(p["returns"]) == 1 and p["status"] == "EXECUTED"
    after = api.account("Lumière France — Compte principal")["balance"]["booked"]["minor_units"]
    assert after == booked + 6_000_000


def test_scheduled_payment_executes_on_date(api):
    future = (clock.today() + timedelta(days=3)).isoformat()
    b = approved_batch(api, execution_date=future)
    assert b["status"] == "SCHEDULED"
    api.run_jobs()
    assert api.get_batch(b["id"])["status"] == "SCHEDULED"
    clock.advance(timedelta(days=3))
    api.tokens.clear()  # les sessions (8 h) ont expiré entre-temps
    with SessionLocal() as s:
        queue.enqueue(s, "run_scheduled", {}, "scheduled:test")
        s.commit()
    api.run_jobs()
    assert api.get_batch(b["id"])["status"] == "COMPLETED"


def test_beneficiary_material_change_after_approval_invalidates(api):
    future = (clock.today() + timedelta(days=5)).isoformat()
    b = approved_batch(api, execution_date=future)
    assert b["status"] == "SCHEDULED"
    from horizon.core.iban import make_iban

    bene = api.beneficiaries()["Acier Rhône SAS"]
    r = api.patch("claire", f"/v1/beneficiaries/{bene['id']}", json={"iban": make_iban("FR", "99999000060000000012345")})
    assert r.status_code == 200 and r.json()["status"] == "PENDING_REVIEW"
    nb = api.get_batch(b["id"])
    assert nb["status"] == "TO_REVIEW"
    assert all(a["state"] == "INVALIDATED" for a in nb["approvals"])
    assert api.account("Lumière France — Compte principal")["balance"]["reserved"]["minor_units"] == 0
    # Modification mineure (courriel) : n'invalide rien
    b2 = approved_batch(api, lines=[("Logistique Seine SARL", "60000.00", "x")], execution_date=future)
    bene2 = api.beneficiaries()["Logistique Seine SARL"]
    r = api.patch("claire", f"/v1/beneficiaries/{bene2['id']}", json={"email": "compta@logistique-seine.example"})
    assert r.json()["status"] == "ACTIVE"
    assert api.get_batch(b2["id"])["status"] == "SCHEDULED"


def test_payment_keeps_pinned_beneficiary_version(api):
    b = api.batch([("Logistique Seine SARL", "60000.00", "x")], submit=False)
    pinned = b["payments"][0]["beneficiary"]["pinned_version_id"]
    bene = api.beneficiaries()["Logistique Seine SARL"]
    assert pinned == bene["approved_version_id"]
    # Transports Garnier : modification en revue → lot « À vérifier », version figée = ancienne version approuvée
    b2 = api.batch([("Transports Garnier SAS", "60000.00", "x")])
    assert b2["status"] == "TO_REVIEW"
    assert b2["validation_issues"][0]["code"] == "BENEFICIARY_CHANGE_PENDING"


def test_state_machine_rejects_illegal_transitions():
    with pytest.raises(Conflict):
        state.check_payment("EXECUTED", "CANCELLED")
    with pytest.raises(Conflict):
        state.check_payment("DRAFT", "EXECUTED")
    with pytest.raises(Conflict):
        state.check_batch("COMPLETED", "PROCESSING")
    state.check_payment("UNKNOWN", "EXECUTED")
    doc = state.transitions_doc()
    assert doc["payment"]["SUBMITTED"]["next"] == ["ACCEPTED", "EXECUTED", "REJECTED", "UNKNOWN"]
