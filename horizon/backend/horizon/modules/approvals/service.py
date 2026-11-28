"""Approbations : séparation des tâches, seuils, plafonds, délégations,
restrictions par compte, expiration et réauthentification.

Une approbation porte sur (lot, version). Elle n'est comptée que si :
non invalidée, non expirée, version = version courante du lot, décision APPROVE,
approbateur distinct (index unique partiel en base).
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.errors import Conflict, DomainError, Forbidden, NotFound
from horizon.core.money import convert_minor, money
from horizon.modules.approvals.models import Approval
from horizon.modules.identity.models import User
from horizon.modules.organizations.models import ApprovalPolicyRule, Delegation, RoleAssignment
from horizon.modules.organizations.permissions import ROLE_PERMISSIONS
from horizon.modules.payments.models import Payment, PaymentBatch


def select_policy(db: Session, batch: PaymentBatch) -> ApprovalPolicyRule:
    """Règle applicable : portée la plus spécifique (compte > entité > groupe),
    puis seuil le plus élevé inférieur ou égal au montant du lot."""
    rules = db.scalars(
        select(ApprovalPolicyRule).where(ApprovalPolicyRule.organization_id == batch.organization_id,
                                         ApprovalPolicyRule.is_active.is_(True))
    ).all()

    def scope_rank(r):
        if r.account_id is not None:
            return 2 if r.account_id == batch.debtor_account_id else -1
        if r.entity_id is not None:
            return 1 if r.entity_id == batch.entity_id else -1
        return 0

    candidates = [r for r in rules if scope_rank(r) >= 0]
    if not candidates:
        raise DomainError("NO_APPROVAL_POLICY", "Aucune politique d'approbation applicable", 409)
    best_scope = max(scope_rank(r) for r in candidates)

    def total_in(ccy: str) -> int:
        # Seuils exprimés dans la devise de la règle : conversion au taux daté si nécessaire.
        if ccy == batch.currency:
            return batch.total_minor
        from horizon.modules.fx.service import get_rate

        rate, _ = get_rate(db, batch.currency, ccy)
        return convert_minor(batch.total_minor, batch.currency, ccy, rate)

    scoped = [r for r in candidates if scope_rank(r) == best_scope and r.min_amount_minor <= total_in(r.currency)]
    if not scoped:
        raise DomainError("NO_APPROVAL_POLICY", "Aucune règle d'approbation pour ce montant/devise", 409)
    return max(scoped, key=lambda r: r.min_amount_minor)


def _limit_ok(limit_minor: int | None, limit_ccy: str, batch: PaymentBatch, db: Session) -> bool:
    if limit_minor is None:
        return False
    if limit_ccy == batch.currency:
        return batch.total_minor <= limit_minor
    from horizon.modules.fx.service import get_rate

    rate, _ = get_rate(db, batch.currency, limit_ccy)
    return convert_minor(batch.total_minor, batch.currency, limit_ccy, rate) <= limit_minor


def authority(db: Session, user_id: uuid.UUID, batch: PaymentBatch) -> dict | None:
    """Source du droit d'approuver ce lot (mandat ou délégation), ou None."""
    today = clock.today()
    now = clock.now()
    assignments = db.scalars(
        select(RoleAssignment).where(RoleAssignment.user_id == user_id, RoleAssignment.role == "APPROVER",
                                     RoleAssignment.organization_id == batch.organization_id,
                                     RoleAssignment.revoked_at.is_(None))
    ).all()
    for a in assignments:
        if "payment.approve" not in ROLE_PERMISSIONS[a.role]:
            continue
        if (a.valid_from and a.valid_from > today) or (a.valid_to and a.valid_to < today):
            continue
        if a.entity_id is not None and a.entity_id != batch.entity_id:
            continue
        if a.account_id is not None and a.account_id != batch.debtor_account_id:
            continue
        if _limit_ok(a.approval_limit_minor, a.limit_currency, batch, db):
            return {"type": "MANDATE", "role_assignment_id": a.id, "limit": money(a.approval_limit_minor, a.limit_currency),
                    "mandate_reference": a.mandate_reference}
    dels = db.scalars(
        select(Delegation).where(Delegation.delegate_user_id == user_id, Delegation.entity_id == batch.entity_id,
                                 Delegation.organization_id == batch.organization_id, Delegation.revoked_at.is_(None),
                                 Delegation.valid_from <= now, Delegation.valid_to >= now)
    ).all()
    for d in dels:
        # La délégation n'est valable que si le délégant dispose lui-même du droit.
        delegator_auth = authority_without_delegation(db, d.delegator_user_id, batch)
        if delegator_auth and _limit_ok(d.max_amount_minor, d.currency, batch, db):
            return {"type": "DELEGATION", "delegation_id": d.id, "delegator_user_id": d.delegator_user_id,
                    "limit": money(d.max_amount_minor, d.currency)}
    return None


def _active_delegation(db: Session, user_id, batch: PaymentBatch) -> bool:
    now = clock.now()
    return db.scalar(select(Delegation.id).where(
        Delegation.delegate_user_id == user_id, Delegation.entity_id == batch.entity_id,
        Delegation.organization_id == batch.organization_id, Delegation.revoked_at.is_(None),
        Delegation.valid_from <= now, Delegation.valid_to >= now).limit(1)) is not None


def authority_without_delegation(db: Session, user_id, batch) -> bool:
    today = clock.today()
    for a in db.scalars(select(RoleAssignment).where(RoleAssignment.user_id == user_id, RoleAssignment.role == "APPROVER",
                                                     RoleAssignment.revoked_at.is_(None))):
        if (a.valid_from and a.valid_from > today) or (a.valid_to and a.valid_to < today):
            continue
        if a.entity_id not in (None, batch.entity_id) or a.account_id not in (None, batch.debtor_account_id):
            continue
        if _limit_ok(a.approval_limit_minor, a.limit_currency, batch, db):
            return True
    return False


def valid_approvals(db: Session, batch: PaymentBatch, version: int | None = None) -> list[Approval]:
    now = clock.now()
    return db.scalars(
        select(Approval).where(
            Approval.batch_id == batch.id,
            Approval.batch_version == (version or batch.version),
            Approval.decision == "APPROVE",
            Approval.invalidated_at.is_(None),
            Approval.expires_at > now,
        )
    ).all()


def invalidate(db: Session, batch: PaymentBatch, reason: str, only_versions_below: int | None = None) -> int:
    q = select(Approval).where(Approval.batch_id == batch.id, Approval.invalidated_at.is_(None))
    if only_versions_below is not None:
        q = q.where(Approval.batch_version < only_versions_below)
    n = 0
    for a in db.scalars(q):
        a.invalidated_at = clock.now()
        a.invalidation_reason = reason
        n += 1
    db.flush()
    return n


def preparers(db: Session, batch: PaymentBatch) -> set[uuid.UUID]:
    ids = {batch.created_by}
    ids |= set(db.scalars(select(Payment.created_by).where(Payment.batch_id == batch.id)))
    return ids


def eligible_approvers(db: Session, batch: PaymentBatch) -> list[dict]:
    users = db.scalars(select(User).where(User.organization_id == batch.organization_id, User.is_active.is_(True))).all()
    excluded = preparers(db, batch)
    out = []
    for u in users:
        if u.id in excluded:
            continue
        auth = authority(db, u.id, batch)
        if auth:
            out.append({"user_id": str(u.id), "name": u.full_name, "via": auth["type"], "limit": auth["limit"]})
    return out


def decide(db: Session, principal, batch_id: uuid.UUID, decision: str, version: int, comment: str | None) -> dict:
    """Enregistre une décision ; finalise le lot si le quorum est atteint.

    Le verrou FOR UPDATE sur le lot sérialise les approbations concurrentes :
    le quorum est évalué une seule fois et les fonds réservés une seule fois.
    """
    from horizon.modules.payments import service as payments

    batch = db.get(PaymentBatch, batch_id, with_for_update=True)
    if batch is None or batch.organization_id != principal.org_id:
        raise NotFound("Lot de paiements", batch_id)
    decision = decision.upper()
    if decision not in {"APPROVE", "REJECT"}:
        raise DomainError("INVALID_DECISION", "Décision attendue : APPROVE ou REJECT", 422)
    if not principal.authz.has("payment.approve", batch.entity_id, batch.debtor_account_id) \
            and not _active_delegation(db, principal.user_id, batch):
        principal.require("payment.approve", batch.entity_id, batch.debtor_account_id)  # refus journalisé (403)
    if batch.status != "PENDING_APPROVAL":
        raise Conflict("BATCH_NOT_PENDING_APPROVAL", f"Le lot est à l'état {batch.status}", {"status": batch.status})
    if version != batch.version:
        raise Conflict("VERSION_MISMATCH",
                       "Le lot a été modifié depuis votre consultation : relisez la version courante avant de décider",
                       {"submitted_version": version, "current_version": batch.version})
    principal.require_step_up()
    if principal.user_id in preparers(db, batch):
        principal.denied("payment.approve", entity_id=batch.entity_id, action="approval.denied",
                         details={"batch_id": str(batch.id), "reason": "segregation_of_duties"})
        raise Forbidden("Séparation des tâches : le préparateur d'un lot ne peut pas l'approuver",
                        code="SEGREGATION_OF_DUTIES")
    auth = authority(db, principal.user_id, batch)
    if auth is None:
        principal.denied("payment.approve", entity_id=batch.entity_id, action="approval.denied",
                         details={"batch_id": str(batch.id), "reason": "limit_or_scope", "total": batch.total_minor})
        raise Forbidden("Plafond, périmètre de compte ou mandat insuffisant pour approuver ce lot",
                        {"total": money(batch.total_minor, batch.currency)}, code="APPROVAL_LIMIT_EXCEEDED")
    existing = db.scalar(select(Approval).where(Approval.batch_id == batch.id, Approval.batch_version == batch.version,
                                                Approval.approver_user_id == principal.user_id,
                                                Approval.invalidated_at.is_(None)))
    if existing is not None:
        raise Conflict("ALREADY_DECIDED", "Vous avez déjà statué sur cette version du lot")
    rule = db.get(ApprovalPolicyRule, batch.policy_rule_id) if batch.policy_rule_id else select_policy(db, batch)
    appr = Approval(
        organization_id=batch.organization_id, batch_id=batch.id, batch_version=batch.version,
        approver_user_id=principal.user_id, decision=decision, comment=comment,
        expires_at=clock.now() + timedelta(hours=rule.approval_validity_hours),
        step_up_at=principal.session.step_up_at,
        via_role_assignment_id=auth.get("role_assignment_id"), via_delegation_id=auth.get("delegation_id"),
    )
    db.add(appr)
    db.flush()
    principal.audit("approval.recorded", "payment_batch", batch.id, entity_id=batch.entity_id,
                    details={"decision": decision, "version": batch.version, "via": auth["type"], "comment": comment})
    if decision == "REJECT":
        payments.reject_at_approval(db, principal, batch, comment or "Refusé par l'approbateur")
        return {"batch_status": batch.status, "approvals": 0, "required": batch.required_approvals}
    count = len({a.approver_user_id for a in valid_approvals(db, batch)})
    if count >= (batch.required_approvals or rule.required_approvals):
        payments.finalize_approval(db, principal, batch)
    return {"batch_status": batch.status, "approvals": count, "required": batch.required_approvals}


def serialize(db: Session, a: Approval, current_version: int) -> dict:
    u = db.get(User, a.approver_user_id)
    now = clock.now()
    state = "VALID"
    if a.invalidated_at:
        state = "INVALIDATED"
    elif a.expires_at <= now:
        state = "EXPIRED"
    elif a.batch_version != current_version:
        state = "OTHER_VERSION"
    return {
        "id": str(a.id), "approver": u.full_name, "approver_user_id": str(u.id), "decision": a.decision,
        "batch_version": a.batch_version, "comment": a.comment, "created_at": a.created_at.isoformat(),
        "expires_at": a.expires_at.isoformat(), "state": state,
        "via": "DELEGATION" if a.via_delegation_id else "MANDATE",
        "invalidated_at": a.invalidated_at.isoformat() if a.invalidated_at else None,
        "invalidation_reason": a.invalidation_reason,
    }
