from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base, TimestampMixin, new_id


class PaymentBatch(Base, TimestampMixin):
    """Lot de paiements (un virement unitaire est un lot de type SINGLE).

    ``version`` est incrémentée à chaque modification matérielle ; les
    approbations portent sur une version précise.
    """

    __tablename__ = "payment_batches"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key"),
        UniqueConstraint("organization_id", "reference"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"), index=True)
    debtor_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bank_accounts.id"), index=True)
    reference: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(20))  # SINGLE / SUPPLIER_BATCH / CSV_IMPORT / FINANCING
    label: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    status_reason: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(default=1)
    approved_version: Mapped[int | None]
    total_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3))
    payment_count: Mapped[int] = mapped_column(default=0)
    execution_date: Mapped[date]
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    request_fingerprint: Mapped[str | None] = mapped_column(String(64))
    source_filename: Mapped[str | None] = mapped_column(String(300))
    required_approvals: Mapped[int | None]
    policy_rule_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("approval_policy_rules.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    submitted_for_approval_at: Mapped[datetime | None]
    approved_at: Mapped[datetime | None]
    processing_started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    validation_issues: Mapped[list] = mapped_column(JSON, default=list)
    forecast_ref: Mapped[str | None] = mapped_column(String(200))


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="positive"),
        UniqueConstraint("end_to_end_id"),
        UniqueConstraint("submission_key"),
        Index("ix_payments_status", "organization_id", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"))
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payment_batches.id"), index=True)
    line_no: Mapped[int]
    debtor_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bank_accounts.id"))
    beneficiary_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    # Version du bénéficiaire figée au moment de la préparation (doit être approuvée).
    beneficiary_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("beneficiary_versions.id"))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    execution_date: Mapped[date]
    remittance_info: Mapped[str] = mapped_column(String(140), default="")
    end_to_end_id: Mapped[str] = mapped_column(String(35))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    status_reason: Mapped[str | None] = mapped_column(String(500))
    submission_key: Mapped[str] = mapped_column(String(100))
    submission_attempts: Mapped[int] = mapped_column(default=0)
    bank_reference: Mapped[str | None] = mapped_column(String(100))
    technical_ack_at: Mapped[datetime | None]
    submitted_at: Mapped[datetime | None]
    accepted_at: Mapped[datetime | None]
    executed_at: Mapped[datetime | None]
    rejected_at: Mapped[datetime | None]
    rejection_code: Mapped[str | None] = mapped_column(String(10))
    unknown_since: Mapped[datetime | None]
    ledger_entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("journal_entries.id"))
    returned_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    forecast_ref: Mapped[str | None] = mapped_column(String(200))
    # Traitement d'un rejet : cause traitée (remplacement ou clôture motivée).
    rejection_resolution: Mapped[str | None] = mapped_column(String(500))
    rejection_resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    rejection_resolved_at: Mapped[datetime | None]


class PaymentEvent(Base, TimestampMixin):
    """Historique des transitions d'état (lot ou paiement)."""

    __tablename__ = "payment_events"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payment_batches.id"), index=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(50))  # USER / WORKER / BANK_EVENT / RECONCILIATION
    reason: Mapped[str | None] = mapped_column(String(500))
    batch_version: Mapped[int | None]


class BankEventInbox(Base, TimestampMixin):
    """Boîte de réception des événements du système destinataire (idempotente)."""

    __tablename__ = "bank_event_inbox"
    __table_args__ = (UniqueConstraint("event_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)
    processed_at: Mapped[datetime | None]
    outcome: Mapped[str] = mapped_column(String(30), default="RECEIVED")
    duplicate_deliveries: Mapped[int] = mapped_column(default=0)
    note: Mapped[str | None] = mapped_column(Text)


class PaymentReturn(Base, TimestampMixin):
    __tablename__ = "payment_returns"
    __table_args__ = (UniqueConstraint("bank_event_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    reason_code: Mapped[str] = mapped_column(String(10))
    bank_event_id: Mapped[str] = mapped_column(String(100))
    ledger_entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("journal_entries.id"))
