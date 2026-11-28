"""Approbations : séparation des tâches, quorum, plafonds, délégations, expiration,
versions, réauthentification et concurrence."""
import threading
from datetime import timedelta

from sqlalchemy import func, select

from horizon.core import clock
from horizon.core.db import SessionLocal
from horizon.modules.approvals.models import Approval
from horizon.modules.jobs.models import Job
from horizon.modules.ledger.models import Reservation
from horizon.modules.organizations.models import RoleAssignment
from tests.conftest import FR_LINES


def test_two_distinct_approvers_reach_quorum_and_reserve_funds(api):
    b = api.batch(FR_LINES)
    assert b["status"] == "PENDING_APPROVAL" and b["required_approvals"] == 2
    before = api.account("Lumière France — Compte principal")["balance"]
    r = api.approve("sophie", b)
    assert r["result"]["approvals"] == 1 and r["batch"]["status"] == "PENDING_APPROVAL"
    r = api.approve("marc", b)
    assert r["batch"]["status"] == "APPROVED"
    after = api.account("Lumière France — Compte principal")["balance"]
    assert after["booked"] == before["booked"]
    assert after["reserved"]["minor_units"] - before["reserved"]["minor_units"] == 18_000_000
    assert after["available"]["minor_units"] == after["booked"]["minor_units"] - after["reserved"]["minor_units"]


def test_preparer_cannot_approve_own_batch(api):
    # Katrin prépare ET approuve en Allemagne : elle ne peut pas approuver son propre lot.
    b = api.batch([("Immobilien Rheinpark GmbH", "60000.00", "x")], account="Lumière Deutschland", who="katrin")
    api.step_up("katrin")
    r = api.post("katrin", f"/v1/payment-batches/{b['id']}/approvals", json={"decision": "APPROVE", "version": b["version"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "SEGREGATION_OF_DUTIES"


def test_technical_admin_cannot_approve(api):
    b = api.batch(FR_LINES)
    api.step_up("julien")
    r = api.post("julien", f"/v1/payment-batches/{b['id']}/approvals", json={"decision": "APPROVE", "version": 1})
    assert r.status_code == 403
    me = api.get("julien", "/v1/me").json()
    assert "payment.approve" not in me["permissions"] and "admin.users" in me["permissions"]


def test_step_up_is_required_and_expires(api):
    b = api.batch(FR_LINES)
    r = api.post("sophie", f"/v1/payment-batches/{b['id']}/approvals", json={"decision": "APPROVE", "version": 1})
    assert r.status_code == 401 and r.json()["error"]["code"] == "STEP_UP_REQUIRED"
    api.step_up("sophie")
    clock.advance(timedelta(minutes=6))
    r = api.post("sophie", f"/v1/payment-batches/{b['id']}/approvals", json={"decision": "APPROVE", "version": 1})
    assert r.json()["error"]["code"] == "STEP_UP_REQUIRED"


def test_same_approver_counts_once(api):
    b = api.batch(FR_LINES)
    api.approve("sophie", b)
    r = api.approve("sophie", b, expect=409)
    assert r["error"]["code"] == "ALREADY_DECIDED"


def test_approval_targets_precise_version(api):
    b = api.batch(FR_LINES)
    r = api.approve("sophie", b, version=b["version"] + 1, expect=409)
    assert r["error"]["code"] == "VERSION_MISMATCH"


def test_material_change_invalidates_prior_approvals(api):
    b = api.batch(FR_LINES)
    api.approve("sophie", b)
    pid = b["payments"][0]["id"]
    r = api.patch("claire", f"/v1/payment-batches/{b['id']}",
                  json={"expected_version": b["version"], "update_payments": [{"payment_id": pid, "amount": "125000.00"}]})
    assert r.status_code == 200, r.text
    nb = r.json()
    assert nb["version"] == b["version"] + 1 and nb["status"] == "DRAFT"
    assert all(a["state"] == "INVALIDATED" for a in nb["approvals"])
    r = api.post("claire", f"/v1/payment-batches/{b['id']}/submit-for-approval", json={"expected_version": nb["version"]})
    assert r.json()["valid_approvals"] == 0
    assert api.approve("marc", b, version=b["version"], expect=409)["error"]["code"] == "VERSION_MISMATCH"
    assert api.approve("marc", nb, version=nb["version"])["result"]["approvals"] == 1


def test_stale_edit_rejected(api):
    b = api.batch(FR_LINES)
    r = api.patch("claire", f"/v1/payment-batches/{b['id']}", json={"expected_version": 99, "label": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "VERSION_MISMATCH"


def test_approval_limit_enforced(api):
    # Giulia : plafond 500 000 € ; lot italien de 600 000 € préparé par Claire.
    b = api.batch([("Consulenze Brera SpA", "600000.00", "x")], account="Lumière Italia")
    r = api.approve("giulia", b, expect=403)
    assert r["error"]["code"] == "APPROVAL_LIMIT_EXCEEDED"
    assert api.approve("sophie", b)["result"]["approvals"] == 1


def test_account_restriction_on_mandate(api):
    # Marc : consultation de toute l'entité France, mais approbation limitée au compte principal.
    usd = api.batch([("Acier Rhône SAS", "100.00", "x")], account="Lumière France — Compte USD")
    assert usd["status"] == "PENDING_APPROVAL" and usd["required_approvals"] == 1  # seuil converti au taux daté
    assert api.approve("marc", usd, expect=403)["error"]["code"] == "FORBIDDEN"
    b = api.batch(FR_LINES)
    assert api.approve("marc", b)["result"]["approvals"] == 1
    # Entité hors périmètre : lot allemand
    bd = api.batch([("Immobilien Rheinpark GmbH", "60000.00", "x")], account="Lumière Deutschland")
    assert api.approve("marc", bd, expect=403)["error"]["code"] == "FORBIDDEN"


def test_delegation_is_capped_and_counts_as_distinct_approver(api):
    ents = {e["name"]: e["id"] for e in api.get("sophie", "/v1/me").json()["entities"]}
    katrin_id = api.get("katrin", "/v1/me").json()["user"]["id"]
    api.step_up("sophie")
    r = api.post("sophie", "/v1/delegations", json={"delegate_user_id": katrin_id, "entity_id": ents["Lumière France"],
                                                    "max_amount": "6000000.00", "valid_days": 7, "reason": "Congés"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "DELEGATION_EXCEEDS_LIMIT"
    r = api.post("sophie", "/v1/delegations", json={"delegate_user_id": katrin_id, "entity_id": ents["Lumière France"],
                                                    "max_amount": "200000.00", "valid_days": 7, "reason": "Congés de Sophie"})
    assert r.status_code == 201, r.text
    b = api.batch(FR_LINES)  # 180 000
    res = api.approve("katrin", b)
    assert res["result"]["approvals"] == 1
    assert res["batch"]["approvals"][0]["via"] == "DELEGATION"
    big = api.batch([("Acier Rhône SAS", "250000.00", "x")])
    assert api.approve("katrin", big, expect=403)["error"]["code"] == "APPROVAL_LIMIT_EXCEEDED"


def test_expired_approvals_do_not_count(api):
    b = api.batch(FR_LINES)
    api.approve("sophie", b)
    clock.advance(timedelta(hours=73))
    r = api.approve("marc", b)
    assert r["result"]["approvals"] == 1 and r["batch"]["status"] == "PENDING_APPROVAL"
    states = {a["approver"]: a["state"] for a in r["batch"]["approvals"]}
    assert states["Sophie Bernard"] == "EXPIRED"


def test_insufficient_funds_blocks_final_approval(api):
    b = api.batch([("Consulenze Brera SpA", "4700000.00", "x")], account="Lumière Italia")
    api.approve("sophie", b)
    # Giulia n'a pas le plafond ; on augmente temporairement via un administrateur
    api.step_up("julien")
    gid = api.get("giulia", "/v1/me").json()["user"]["id"]
    ents = {e["name"]: e["id"] for e in api.get("julien", "/v1/me").json()["entities"]}
    r = api.post("julien", "/v1/admin/role-assignments", json={"user_id": gid, "role": "APPROVER",
                                                                "entity_id": ents["Lumière Italia"], "approval_limit": "9000000.00"})
    assert r.status_code == 201
    r = api.approve("giulia", b, expect=409)
    assert r["error"]["code"] == "INSUFFICIENT_FUNDS"
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(Approval).where(Approval.batch_id == b["id"])) == 1


def test_concurrent_approvals_finalize_exactly_once(api):
    b = api.batch(FR_LINES)
    for who in ("sophie", "marc"):
        api.step_up(who)
    results = {}
    barrier = threading.Barrier(2)

    def go(who):
        barrier.wait()
        r = api.c.post(f"/v1/payment-batches/{b['id']}/approvals", headers=api.h(who),
                       json={"decision": "APPROVE", "version": b["version"]})
        results[who] = r.status_code

    ts = [threading.Thread(target=go, args=(w,)) for w in ("sophie", "marc")]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert results == {"sophie": 200, "marc": 200}
    final = api.get_batch(b["id"])
    assert final["status"] == "APPROVED"
    with SessionLocal() as s:
        res = s.scalars(select(Reservation).where(Reservation.status == "ACTIVE",
                                                  Reservation.reference_id.in_([p["id"] for p in final["payments"]]))).all()
        assert len(res) == 2 and sum(r.amount_minor for r in res) == 18_000_000
        assert s.scalar(select(func.count()).select_from(Job).where(Job.kind == "execute_batch",
                                                                   Job.dedup_key.contains(b["id"]))) == 1


def test_concurrent_double_click_same_approver(api):
    b = api.batch(FR_LINES)
    api.step_up("sophie")
    codes = []
    barrier = threading.Barrier(2)

    def go():
        barrier.wait()
        r = api.c.post(f"/v1/payment-batches/{b['id']}/approvals", headers=api.h("sophie"),
                       json={"decision": "APPROVE", "version": b["version"]})
        codes.append(r.status_code)

    ts = [threading.Thread(target=go) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(codes) == [200, 409]
    assert api.get_batch(b["id"])["valid_approvals"] == 1


def test_rights_revoked_before_execution_block_submission(api):
    b = api.batch(FR_LINES)
    api.approve("sophie", b)
    api.approve("marc", b)
    with SessionLocal() as s:
        from horizon.modules.identity.models import User

        marc = s.scalar(select(User).where(User.email == "marc.lefevre@lumiere.example"))
        for ra in s.scalars(select(RoleAssignment).where(RoleAssignment.user_id == marc.id, RoleAssignment.role == "APPROVER")):
            ra.revoked_at = clock.now()
        s.commit()
    api.run_jobs()
    final = api.get_batch(b["id"])
    assert final["status"] == "TO_REVIEW"
    assert all(p["status"] == "TO_REVIEW" for p in final["payments"])
    assert "Contrôle avant exécution" in final["status_reason"]
    bal = api.account("Lumière France — Compte principal")["balance"]
    assert bal["reserved"]["minor_units"] == 0


def test_reject_decision_cancels_batch(api):
    b = api.batch(FR_LINES)
    api.step_up("sophie")
    r = api.post("sophie", f"/v1/payment-batches/{b['id']}/approvals",
                 json={"decision": "REJECT", "version": b["version"], "comment": "Facture non conforme"})
    assert r.status_code == 200
    assert r.json()["batch"]["status"] == "REJECTED"
    assert all(p["status"] == "CANCELLED" for p in r.json()["batch"]["payments"])
