from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base, TimestampMixin, new_id

ROLES = ("VIEWER", "PREPARER", "APPROVER", "ADMIN", "AUDITOR")
ROLE_LABELS = {
    "VIEWER": "Consultation",
    "PREPARER": "Préparation",
    "APPROVER": "Approbation",
    "ADMIN": "Administration",
    "AUDITOR": "Audit",
}


class Organization(Base, TimestampMixin):
    """Groupe (locataire). Toutes les données métier portent organization_id."""

    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    base_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    is_demo: Mapped[bool] = mapped_column(default=True)


class LegalEntity(Base, TimestampMixin):
    __tablename__ = "legal_entities"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    country_code: Mapped[str] = mapped_column(String(2))
    country_name: Mapped[str] = mapped_column(String(100))
    registration_number: Mapped[str] = mapped_column(String(100), default="")
    lei: Mapped[str] = mapped_column(String(40), default="")


class RoleAssignment(Base, TimestampMixin):
    """Mandat : rôle d'un utilisateur, limité à une entité et éventuellement à un compte."""

    __tablename__ = "role_assignments"
    __table_args__ = (CheckConstraint(f"role IN {ROLES}", name="role_valid"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("legal_entities.id"))
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bank_accounts.id"))
    # Plafond par lot/paiement pour le rôle Approbation (unités mineures de limit_currency).
    approval_limit_minor: Mapped[int | None] = mapped_column(BigInteger)
    limit_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    mandate_reference: Mapped[str] = mapped_column(String(200), default="")
    valid_from: Mapped[date | None]
    valid_to: Mapped[date | None]
    granted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None]
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Delegation(Base, TimestampMixin):
    """Délégation temporaire du droit d'approbation, plafonnée."""

    __tablename__ = "delegations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    delegator_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    delegate_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"))
    max_amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    valid_from: Mapped[datetime]
    valid_to: Mapped[datetime]
    reason: Mapped[str] = mapped_column(String(500), default="")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None]


class ApprovalPolicyRule(Base, TimestampMixin):
    """Règle d'approbation : à partir de min_amount, N approbateurs distincts.

    Portée la plus spécifique gagnante : compte > entité > groupe.
    """

    __tablename__ = "approval_policy_rules"
    __table_args__ = (CheckConstraint("required_approvals >= 1", name="required_positive"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("legal_entities.id"))
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bank_accounts.id"))
    min_amount_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    required_approvals: Mapped[int] = mapped_column(Integer)
    approval_validity_hours: Mapped[int] = mapped_column(Integer, default=72)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
