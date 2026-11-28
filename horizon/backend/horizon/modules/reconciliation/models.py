from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base, TimestampMixin, new_id

CASE_KINDS = ("MISSING_IN_LEDGER", "MISSING_IN_STATEMENT", "AMOUNT_MISMATCH", "UNKNOWN_PAYMENT_RESULT")


class ReconciliationRun(Base, TimestampMixin):
    __tablename__ = "reconciliation_runs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bank_accounts.id"))
    statement_lines: Mapped[int] = mapped_column(default=0)
    matched: Mapped[int] = mapped_column(default=0)
    cases_opened: Mapped[int] = mapped_column(default=0)
    source: Mapped[str] = mapped_column(String(200))


class ReconciliationCase(Base, TimestampMixin):
    """Écart de rapprochement. Accuser réception ne le résout pas."""

    __tablename__ = "reconciliation_cases"
    __table_args__ = (UniqueConstraint("account_id", "kind", "external_ref"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"))
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bank_accounts.id"))
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN / ACKNOWLEDGED / RESOLVED
    external_ref: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"))
    ledger_entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("journal_entries.id"))
    statement_minor: Mapped[int | None] = mapped_column(BigInteger)
    ledger_minor: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    value_date: Mapped[date | None]
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date | None]
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None]
    resolution: Mapped[str | None] = mapped_column(String(50))
    resolution_note: Mapped[str | None] = mapped_column(String(1000))
    resolution_entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("journal_entries.id"))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None]
