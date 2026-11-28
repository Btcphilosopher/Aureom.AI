"""Autorisations côté serveur, au niveau de l'entité et du compte.

Principe : permission = rôle actif (mandat) dont la portée couvre l'entité et
le compte visés. Le rôle Administration ne donne AUCUN droit d'approbation ni
de préparation de paiement : il gère les utilisateurs et les politiques.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.errors import Forbidden
from horizon.modules.organizations.models import RoleAssignment

READ = {
    "account.read",
    "transaction.read",
    "beneficiary.read",
    "payment.read",
    "forecast.read",
    "financing.read",
    "fx.read",
    "document.read",
    "trade.read",
    "reconciliation.read",
    "decision.read",
    "ledger.read",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "VIEWER": READ | {"report.export"},
    "PREPARER": READ
    | {
        "beneficiary.write",
        "payment.prepare",
        "payment.cancel",
        "forecast.write",
        "financing.prepare",
        "fx.quote",
        "document.write",
        "trade.write",
        "reconciliation.resolve",
        "decision.acknowledge",
        "report.export",
    },
    "APPROVER": READ
    | {"beneficiary.approve", "payment.approve", "payment.cancel", "fx.execute_simulated", "decision.acknowledge", "report.export"},
    "ADMIN": {"admin.users", "admin.policies", "audit.read", "decision.read", "simulator.control"},
    "AUDITOR": READ | {"audit.read", "report.export"},
}


@dataclass
class Authz:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    assignments: list[RoleAssignment] = field(default_factory=list)

    @classmethod
    def load(cls, db: Session, user_id: uuid.UUID, organization_id: uuid.UUID) -> "Authz":
        today = clock.today()
        rows = db.scalars(
            select(RoleAssignment).where(
                RoleAssignment.user_id == user_id,
                RoleAssignment.organization_id == organization_id,
                RoleAssignment.revoked_at.is_(None),
            )
        ).all()
        active = [
            r
            for r in rows
            if (r.valid_from is None or r.valid_from <= today) and (r.valid_to is None or r.valid_to >= today)
        ]
        return cls(user_id=user_id, organization_id=organization_id, assignments=active)

    def roles(self) -> set[str]:
        return {a.role for a in self.assignments}

    def permissions(self) -> set[str]:
        out: set[str] = set()
        for a in self.assignments:
            out |= ROLE_PERMISSIONS[a.role]
        return out

    def matching(self, perm: str, entity_id=None, account_id=None) -> list[RoleAssignment]:
        res = []
        for a in self.assignments:
            if perm not in ROLE_PERMISSIONS[a.role]:
                continue
            if a.entity_id is not None and entity_id is not None and a.entity_id != entity_id:
                continue
            if a.entity_id is not None and entity_id is None:
                # permission demandée au niveau groupe : un mandat d'entité ne suffit pas
                continue
            if a.account_id is not None and account_id is not None and a.account_id != account_id:
                continue
            if a.account_id is not None and account_id is None:
                continue
            res.append(a)
        return res

    def has(self, perm: str, entity_id=None, account_id=None) -> bool:
        return bool(self.matching(perm, entity_id, account_id))

    def has_any_scope(self, perm: str) -> bool:
        return any(perm in ROLE_PERMISSIONS[a.role] for a in self.assignments)

    def can_see_account(self, perm: str, entity_id, account_id) -> bool:
        return self.has(perm, entity_id, account_id)

    def can_see_entity(self, perm: str, entity_id) -> bool:
        """Visibilité d'un objet d'entité (y compris via un mandat limité à un compte)."""
        for a in self.assignments:
            if perm in ROLE_PERMISSIONS[a.role] and (a.entity_id is None or a.entity_id == entity_id):
                return True
        return False

    def require(self, perm: str, entity_id=None, account_id=None, *, audit_ctx=None) -> list[RoleAssignment]:
        m = self.matching(perm, entity_id, account_id)
        if not m:
            if audit_ctx is not None:
                audit_ctx.denied(perm, entity_id=entity_id, account_id=account_id)
            raise Forbidden(
                f"Permission « {perm} » requise sur ce périmètre",
                {"permission": perm, "entity_id": str(entity_id) if entity_id else None,
                 "account_id": str(account_id) if account_id else None},
            )
        return m

    def require_any(self, perm: str, *, audit_ctx=None) -> None:
        if not self.has_any_scope(perm):
            if audit_ctx is not None:
                audit_ctx.denied(perm)
            raise Forbidden(f"Permission « {perm} » requise", {"permission": perm})
