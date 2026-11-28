"""Tables du simulateur bancaire déterministe (préfixe ``sim_``).

Elles représentent l'état d'un système *externe* fictif. HORIZON n'y accède
qu'à travers l'adaptateur ``PaymentGateway`` / ``StatementProvider``.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base, TimestampMixin, new_id


class SimBankOrder(Base, TimestampMixin):
    __tablename__ = "sim_bank_orders"
    __table_args__ = (UniqueConstraint("submission_key"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    submission_key: Mapped[str] = mapped_column(String(100))
    bank_reference: Mapped[str] = mapped_column(String(100))
    end_to_end_id: Mapped[str] = mapped_column(String(35))
    debtor_iban: Mapped[str] = mapped_column(String(34))
    creditor_iban: Mapped[str] = mapped_column(String(34))
    creditor_name: Mapped[str] = mapped_column(String(200))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    requested_date: Mapped[date]
    status: Mapped[str] = mapped_column(String(20), default="RECEIVED")  # RECEIVED/ACCEPTED/SETTLED/REJECTED/RETURNED
    rejection_code: Mapped[str | None] = mapped_column(String(10))
    settled_at: Mapped[datetime | None]


class SimBankEvent(Base, TimestampMixin):
    __tablename__ = "sim_bank_events"
    __table_args__ = (UniqueConstraint("event_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(String(100))
    order_id: Mapped[uuid.UUID | None]
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)
    delivered_count: Mapped[int] = mapped_column(default=0)
    delivered_at: Mapped[datetime | None]


class SimStatementLine(Base, TimestampMixin):
    """Lignes de relevé produites par le simulateur (règlements, retours, frais)."""

    __tablename__ = "sim_statement_lines"
    __table_args__ = (UniqueConstraint("line_ref"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    line_ref: Mapped[str] = mapped_column(String(100))
    account_iban: Mapped[str] = mapped_column(String(34), index=True)
    booking_date: Mapped[date]
    amount_minor: Mapped[int] = mapped_column(BigInteger)  # signé : négatif = débit
    currency: Mapped[str] = mapped_column(String(3))
    description: Mapped[str] = mapped_column(String(300))
    end_to_end_id: Mapped[str | None] = mapped_column(String(35))
    bank_reference: Mapped[str | None] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))  # PAYMENT / RETURN / FEE


class SimFault(Base, TimestampMixin):
    """Panne injectée à usage unique (démonstration et tests)."""

    __tablename__ = "sim_faults"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(40))  # TIMEOUT_AFTER_RECORD / TIMEOUT_BEFORE_RECORD
    match_remittance: Mapped[str | None] = mapped_column(String(140))
    remaining: Mapped[int] = mapped_column(default=1)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
