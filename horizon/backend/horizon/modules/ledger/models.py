from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from horizon.core.db import Base, TimestampMixin, new_id

GL_TYPES = ("ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE")
GL_PURPOSES = (
    "BANK",  # miroir comptable d'un compte bancaire simulé
    "OPENING_EQUITY",  # contrepartie des soldes d'ouverture
    "COUNTERPARTY_OUT",  # tiers payés (paiements sortants)
    "COUNTERPARTY_IN",  # encaissements clients
    "FX_POSITION",  # position de change, une par devise
    "BANK_FEES",
    "SUSPENSE",
)
JOURNALS = {
    "OUV": "Ouverture",
    "ENC": "Encaissements",
    "PAI": "Paiements",
    "RET": "Retours de fonds",
    "CHG": "Change",
    "FRA": "Frais bancaires",
    "COR": "Corrections et contrepassations",
}


class GlAccount(Base, TimestampMixin):
    __tablename__ = "gl_accounts"
    __table_args__ = (
        UniqueConstraint("organization_id", "code"),
        CheckConstraint(f"type IN {GL_TYPES}", name="type_valid"),
        CheckConstraint(f"purpose IN {GL_PURPOSES}", name="purpose_valid"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"))
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(20))
    purpose: Mapped[str] = mapped_column(String(30))
    currency: Mapped[str] = mapped_column(String(3))
    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bank_accounts.id"), unique=True)


class JournalEntry(Base, TimestampMixin):
    """Écriture comptabilisée. Immuable (trigger PostgreSQL) : toute correction
    passe par une contrepassation ou une écriture de correction liée."""

    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint("organization_id", "entry_number"),
        UniqueConstraint("idempotency_key"),
        UniqueConstraint("reverses_entry_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"))
    entry_number: Mapped[int] = mapped_column(BigInteger)
    journal: Mapped[str] = mapped_column(String(3))
    booking_date: Mapped[date]
    value_date: Mapped[date]
    description: Mapped[str] = mapped_column(String(500))
    reference_type: Mapped[str | None] = mapped_column(String(50))
    reference_id: Mapped[str | None] = mapped_column(String(100), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    reverses_entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("journal_entries.id"))
    corrects_entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("journal_entries.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    lines: Mapped[list["JournalLine"]] = relationship(back_populates="entry", order_by="JournalLine.line_no")


class JournalLine(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint("debit_minor >= 0 AND credit_minor >= 0", name="non_negative"),
        CheckConstraint("(debit_minor = 0) <> (credit_minor = 0)", name="one_side"),
        Index("ix_journal_lines_gl_value", "gl_account_id", "value_date"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("journal_entries.id"), index=True)
    line_no: Mapped[int]
    gl_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("gl_accounts.id"))
    currency: Mapped[str] = mapped_column(String(3))
    debit_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    credit_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    value_date: Mapped[date]
    entry: Mapped[JournalEntry] = relationship(back_populates="lines")


class Reservation(Base, TimestampMixin):
    """Montant réservé sur un compte simulé (paiement approuvé non encore réglé)."""

    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="positive"),
        CheckConstraint("status IN ('ACTIVE','CONSUMED','RELEASED')", name="status_valid"),
        Index(
            "uq_reservations_active_ref",
            "reference_type",
            "reference_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    bank_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bank_accounts.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    reference_type: Mapped[str] = mapped_column(String(50))
    reference_id: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    closed_at: Mapped[datetime | None]
    closing_reason: Mapped[str | None] = mapped_column(String(200))
