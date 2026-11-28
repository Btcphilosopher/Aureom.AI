from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base, TimestampMixin, new_id

BENEFICIARY_STATUSES = ("PENDING_REVIEW", "ACTIVE", "SUSPENDED", "REJECTED")
MATERIAL_FIELDS = ("name", "iban", "bic", "country_code")


class Beneficiary(Base, TimestampMixin):
    __tablename__ = "beneficiaries"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING_REVIEW")
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("beneficiary_versions.id", use_alter=True))
    approved_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("beneficiary_versions.id", use_alter=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    suspended_reason: Mapped[str | None] = mapped_column(String(500))


class BeneficiaryVersion(Base, TimestampMixin):
    """Version immuable des coordonnées. Un paiement référence la version approuvée."""

    __tablename__ = "beneficiary_versions"
    __table_args__ = (UniqueConstraint("beneficiary_id", "version_no"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    beneficiary_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    version_no: Mapped[int]
    name: Mapped[str] = mapped_column(String(200))
    iban: Mapped[str] = mapped_column(String(34))
    bic: Mapped[str] = mapped_column(String(11), default="")
    country_code: Mapped[str] = mapped_column(String(2))
    address: Mapped[str] = mapped_column(String(500), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    category: Mapped[str] = mapped_column(String(100), default="Fournisseur")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    change_kind: Mapped[str] = mapped_column(String(20), default="CREATION")  # CREATION/MATERIAL/MINOR
    changed_fields: Mapped[list] = mapped_column(JSON, default=list)
    review_status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING/APPROVED/REJECTED/INHERITED
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None]
    review_comment: Mapped[str | None] = mapped_column(String(500))
    verification: Mapped[dict] = mapped_column(JSON, default=dict)
