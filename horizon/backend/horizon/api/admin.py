from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from horizon.api.schemas import DelegationIn, FaultIn, IncomingIn, PolicyRuleIn, RedeliverIn, ReturnIn, RoleAssignmentIn
from horizon.core import clock
from horizon.core.config import get_settings
from horizon.core.context import Principal, get_principal
from horizon.core.db import get_db
from horizon.core.errors import Conflict, DomainError, Forbidden, NotFound
from horizon.core.money import money, to_minor
from horizon.core.pagination import PageParams, paginate
from horizon.modules.audit import service as audit
from horizon.modules.audit.models import AuditEvent
from horizon.modules.forecasting.models import ExpectedReceipt
from horizon.modules.identity.models import User
from horizon.modules.integrations.bank_simulator import bank
from horizon.modules.integrations.models import SimBankEvent
from horizon.modules.jobs import queue
from horizon.modules.jobs.models import Job
from horizon.modules.organizations.models import ROLE_LABELS, ApprovalPolicyRule, Delegation, LegalEntity, RoleAssignment
from horizon.modules.payments import execution
from horizon.modules.payments.models import BankEventInbox, Payment
from horizon.modules.reports import service as reports

router = APIRouter(prefix="/v1", tags=["Administration et audit"])


def _ent_name(db, eid):
    return db.get(LegalEntity, eid).name if eid else "Toutes les entités"


@router.get("/admin/users")
def users(p: Principal = Depends(get_principal)):
    p.require_any("admin.users")
    out = []
    for u in p.db.scalars(select(User).where(User.organization_id == p.org_id).order_by(User.full_name)):
        ras = p.db.scalars(select(RoleAssignment).where(RoleAssignment.user_id == u.id)).all()
        out.append({"id": str(u.id), "full_name": u.full_name, "email": u.email, "title": u.title, "active": u.is_active,
                    "mfa": "TOTP", "roles": [_ser_ra(p.db, a) for a in ras]})
    return {"data": out}


def _ser_ra(db, a: RoleAssignment) -> dict:
    return {"id": str(a.id), "role": a.role, "role_label": ROLE_LABELS[a.role], "entity": _ent_name(db, a.entity_id),
            "entity_id": str(a.entity_id) if a.entity_id else None, "account_id": str(a.account_id) if a.account_id else None,
            "approval_limit": money(a.approval_limit_minor, a.limit_currency) if a.approval_limit_minor else None,
            "mandate_reference": a.mandate_reference, "valid_to": a.valid_to.isoformat() if a.valid_to else None,
            "revoked_at": a.revoked_at.isoformat() if a.revoked_at else None}


@router.post("/admin/role-assignments", status_code=201)
def grant(body: RoleAssignmentIn, p: Principal = Depends(get_principal)):
    p.require_any("admin.users")
    p.require_step_up()
    u = p.db.get(User, body.user_id)
    if u is None or u.organization_id != p.org_id:
        raise NotFound("Utilisateur", body.user_id)
    if body.user_id == p.user_id:
        raise Forbidden("Un administrateur ne peut pas s'attribuer de rôle à lui-même", code="SELF_GRANT_FORBIDDEN")
    if body.role == "APPROVER" and not body.approval_limit:
        raise DomainError("LIMIT_REQUIRED", "Un plafond est obligatoire pour le rôle Approbation", 422)
    a = RoleAssignment(organization_id=p.org_id, user_id=u.id, role=body.role, entity_id=body.entity_id,
                       account_id=body.account_id,
                       approval_limit_minor=to_minor(body.approval_limit, "EUR") if body.approval_limit else None,
                       mandate_reference=body.mandate_reference, valid_from=clock.today(), valid_to=body.valid_to,
                       granted_by=p.user_id)
    p.db.add(a)
    p.db.flush()
    p.audit("admin.role_granted", "role_assignment", a.id, entity_id=body.entity_id,
            details={"user": u.email, "role": body.role, "limit": body.approval_limit})
    return _ser_ra(p.db, a)


@router.post("/admin/role-assignments/{ra_id}/revoke")
def revoke(ra_id: uuid.UUID, p: Principal = Depends(get_principal)):
    p.require_any("admin.users")
    p.require_step_up()
    a = p.db.get(RoleAssignment, ra_id)
    if a is None or a.organization_id != p.org_id:
        raise NotFound("Mandat", ra_id)
    if a.revoked_at:
        raise Conflict("ALREADY_REVOKED", "Mandat déjà révoqué")
    a.revoked_at = clock.now()
    a.revoked_by = p.user_id
    p.audit("admin.role_revoked", "role_assignment", a.id, entity_id=a.entity_id, details={"role": a.role})
    return _ser_ra(p.db, a)


@router.get("/admin/approval-policies")
def policies(p: Principal = Depends(get_principal)):
    if not (p.authz.has_any_scope("admin.policies") or p.authz.has_any_scope("payment.read")):
        raise Forbidden()
    rows = p.db.scalars(select(ApprovalPolicyRule).where(ApprovalPolicyRule.organization_id == p.org_id)
                        .order_by(ApprovalPolicyRule.min_amount_minor)).all()
    return {"data": [{"id": str(r.id), "name": r.name, "scope": ("Compte" if r.account_id else "Entité" if r.entity_id else "Groupe"),
                      "entity": _ent_name(p.db, r.entity_id), "account_id": str(r.account_id) if r.account_id else None,
                      "min_amount": money(r.min_amount_minor, r.currency), "required_approvals": r.required_approvals,
                      "approval_validity_hours": r.approval_validity_hours, "active": r.is_active} for r in rows]}


@router.post("/admin/approval-policies", status_code=201)
def add_policy(body: PolicyRuleIn, p: Principal = Depends(get_principal)):
    p.require_any("admin.policies")
    p.require_step_up()
    r = ApprovalPolicyRule(organization_id=p.org_id, name=body.name, entity_id=body.entity_id, account_id=body.account_id,
                           min_amount_minor=to_minor(body.min_amount, "EUR"), required_approvals=body.required_approvals,
                           approval_validity_hours=body.approval_validity_hours, created_by=p.user_id)
    p.db.add(r)
    p.db.flush()
    p.audit("admin.policy_added", "approval_policy_rule", r.id, details=body.model_dump(mode="json"))
    return {"id": str(r.id)}


@router.get("/delegations")
def delegations(p: Principal = Depends(get_principal)):
    p.require_any("payment.read") if not p.authz.has_any_scope("admin.users") else None
    rows = p.db.scalars(select(Delegation).where(Delegation.organization_id == p.org_id)).all()
    now = clock.now()
    return {"data": [{"id": str(d.id), "delegator": p.db.get(User, d.delegator_user_id).full_name,
                      "delegate": p.db.get(User, d.delegate_user_id).full_name, "entity": _ent_name(p.db, d.entity_id),
                      "max_amount": money(d.max_amount_minor, d.currency), "valid_from": d.valid_from.isoformat(),
                      "valid_to": d.valid_to.isoformat(), "reason": d.reason,
                      "active": d.revoked_at is None and d.valid_from <= now <= d.valid_to} for d in rows]}


@router.post("/delegations", status_code=201, summary="Déléguer son droit d'approbation (plafonné, temporaire)")
def delegate(body: DelegationIn, p: Principal = Depends(get_principal)):
    p.require("payment.approve", body.entity_id)
    p.require_step_up()
    if body.delegate_user_id == p.user_id:
        raise DomainError("SELF_DELEGATION", "Délégation à soi-même impossible", 422)
    mine = [a for a in p.authz.matching("payment.approve", body.entity_id) if a.role == "APPROVER"]
    max_minor = to_minor(body.max_amount, "EUR")
    if not any((a.approval_limit_minor or 0) >= max_minor for a in mine):
        raise Forbidden("Le plafond délégué dépasse votre propre plafond", code="DELEGATION_EXCEEDS_LIMIT")
    now = clock.now()
    d = Delegation(organization_id=p.org_id, delegator_user_id=p.user_id, delegate_user_id=body.delegate_user_id,
                   entity_id=body.entity_id, max_amount_minor=max_minor, valid_from=now,
                   valid_to=now + timedelta(days=body.valid_days), reason=body.reason, created_by=p.user_id)
    p.db.add(d)
    p.db.flush()
    p.audit("approval.delegated", "delegation", d.id, entity_id=body.entity_id, details=body.model_dump(mode="json"))
    return {"id": str(d.id)}


@router.post("/delegations/{delegation_id}/revoke")
def revoke_delegation(delegation_id: uuid.UUID, p: Principal = Depends(get_principal)):
    d = p.db.get(Delegation, delegation_id)
    if d is None or d.organization_id != p.org_id:
        raise NotFound("Délégation", delegation_id)
    if d.delegator_user_id != p.user_id and not p.authz.has_any_scope("admin.users"):
        raise Forbidden()
    d.revoked_at = clock.now()
    p.audit("approval.delegation_revoked", "delegation", d.id, entity_id=d.entity_id)
    return {"revoked": True}


# ------------------------------------------------------------------------ audit

@router.get("/audit-events")
def audit_events(page: PageParams = Depends(), action: str | None = None, object_id: str | None = None,
                 p: Principal = Depends(get_principal)):
    p.require_any("audit.read")
    stmt = select(AuditEvent).where(AuditEvent.organization_id == p.org_id).order_by(AuditEvent.id.desc())
    if action:
        stmt = stmt.where(AuditEvent.action.startswith(action))
    if object_id:
        stmt = stmt.where(AuditEvent.object_id == object_id)
    res = paginate(p.db, stmt, page, audit.serialize)
    p.audit("audit.read", "audit_events", None, details={"action_filter": action, "object_id": object_id})
    return res


@router.get("/audit-events/verify", summary="Vérifier l'intégrité de la chaîne d'audit")
def verify(p: Principal = Depends(get_principal)):
    p.require_any("audit.read")
    return audit.verify_chain(p.db, p.org_id)


@router.post("/reports/treasury-export", summary="Rapport + piste d'audit (ZIP avec manifeste SHA-256)")
def export(p: Principal = Depends(get_principal)):
    data, name, rec = reports.treasury_export(p.db, p)
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "X-Report-SHA256": rec.sha256,
                             "Cache-Control": "no-store"})


# ------------------------------------------------- intégration : webhook signé

@router.post("/integrations/bank-simulator/events", tags=["Intégrations"], summary="Webhook signé du simulateur bancaire")
async def bank_events(request: Request, x_horizon_signature: str | None = Header(default=None), db: Session = Depends(get_db)):
    body = await request.body()
    return execution.ingest_bank_event(db, body, x_horizon_signature)


# --------------------------------------------- contrôles de démonstration

def _demo(p: Principal):
    if not get_settings().demo_controls:
        raise DomainError("DEMO_CONTROLS_DISABLED", "Contrôles de démonstration désactivés", 404)


@router.post("/demo/run-jobs", tags=["Démonstration"], summary="Traiter la file de tâches (sans travailleur)")
def run_jobs(p: Principal = Depends(get_principal)):
    _demo(p)
    p.db.commit()
    n = queue.drain()
    return {"processed": n}


@router.get("/demo/jobs", tags=["Démonstration"])
def jobs(p: Principal = Depends(get_principal)):
    _demo(p)
    rows = p.db.scalars(select(Job).order_by(Job.created_at.desc()).limit(50)).all()
    return {"data": [queue.serialize(j) for j in rows]}


@router.post("/demo/simulator/faults", tags=["Démonstration"], summary="Injecter une panne (résultat inconnu)")
def fault(body: FaultIn, p: Principal = Depends(get_principal)):
    _demo(p)
    p.require_any("payment.prepare") if not p.authz.has_any_scope("simulator.control") else None
    fid = bank.inject_fault(body.kind, body.match_remittance)
    p.audit("demo.fault_injected", "sim_fault", fid, details=body.model_dump())
    return {"fault_id": fid}


@router.get("/demo/simulator/events", tags=["Démonstration"])
def sim_events(p: Principal = Depends(get_principal)):
    _demo(p)
    rows = p.db.scalars(select(SimBankEvent).order_by(SimBankEvent.created_at.desc()).limit(50)).all()
    inbox = {i.event_id: i for i in p.db.scalars(select(BankEventInbox))}
    return {"data": [{"event_id": e.event_id, "type": e.event_type, "delivered_count": e.delivered_count,
                      "inbox_outcome": inbox[e.event_id].outcome if e.event_id in inbox else None,
                      "duplicate_deliveries": inbox[e.event_id].duplicate_deliveries if e.event_id in inbox else 0,
                      "submission_key": e.payload.get("submission_key"), "at": e.created_at.isoformat()} for e in rows]}


@router.post("/demo/simulator/redeliver", tags=["Démonstration"], summary="Redélivrer un événement (doublon)")
def redeliver(body: RedeliverIn, p: Principal = Depends(get_principal)):
    _demo(p)
    p.db.commit()
    res = execution.redeliver(body.event_id)
    p.audit("demo.event_redelivered", "bank_event", body.event_id, details=res)
    return res


@router.post("/demo/simulator/returns", tags=["Démonstration"], summary="Simuler un retour de fonds")
def sim_return(body: ReturnIn, p: Principal = Depends(get_principal)):
    _demo(p)
    pay = p.db.get(Payment, body.payment_id)
    if pay is None or pay.organization_id != p.org_id:
        raise NotFound("Paiement", body.payment_id)
    try:
        eid = bank.simulate_return(pay.submission_key, to_minor(body.amount, pay.currency) if body.amount else None, body.reason_code)
    except ValueError as exc:
        raise Conflict("RETURN_NOT_POSSIBLE", str(exc)) from exc
    p.db.commit()
    res = execution.deliver_pending_events()
    return {"event_id": eid, "deliveries": res}


@router.post("/demo/simulator/incoming", tags=["Démonstration"], summary="Simuler la réception d'un encaissement attendu")
def sim_incoming(body: IncomingIn, p: Principal = Depends(get_principal)):
    _demo(p)
    from horizon.modules.accounts.models import BankAccount

    er = p.db.get(ExpectedReceipt, body.expected_receipt_id)
    if er is None or er.organization_id != p.org_id:
        raise NotFound("Encaissement attendu", body.expected_receipt_id)
    acc = p.db.get(BankAccount, er.account_id)
    eid = bank.simulate_incoming(acc.iban, er.amount_minor, er.currency, er.reference, er.counterparty)
    p.db.commit()
    return {"event_id": eid, "deliveries": execution.deliver_pending_events()}
