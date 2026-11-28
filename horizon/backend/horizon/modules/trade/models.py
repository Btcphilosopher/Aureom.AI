from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base, TimestampMixin, new_id


class TradeFile(Base, TimestampMixin):
    """Dossier de commerce international — gestion documentaire uniquement.

    HORIZON n'émet ni garantie, ni crédit documentaire, ni confirmation."""

    __tablename__ = "trade_files"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"))
    reference: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(300))
    direction: Mapped[str] = mapped_column(String(10))  # IMPORT / EXPORT
    instrument_considered: Mapped[str] = mapped_column(String(200), default="")
    amount_minor: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str | None] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class TradeParty(Base, TimestampMixin):
    __tablename__ = "trade_parties"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    trade_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trade_files.id"), index=True)
    role: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    country_code: Mapped[str] = mapped_column(String(2))


class TradeDeadline(Base, TimestampMixin):
    __tablename__ = "trade_deadlines"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    trade_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trade_files.id"), index=True)
    label: Mapped[str] = mapped_column(String(200))
    due_date: Mapped[date]
    status: Mapped[str] = mapped_column(String(20), default="OPEN")


class TradeRequest(Base, TimestampMixin):
    __tablename__ = "trade_requests"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    trade_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trade_files.id"), index=True)
    kind: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    sent_at: Mapped[datetime | None]


class TradeTask(Base, TimestampMixin):
    __tablename__ = "trade_tasks"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    trade_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trade_files.id"), index=True)
    label: Mapped[str] = mapped_column(String(300))
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date | None]
    status: Mapped[str] = mapped_column(String(20), default="TODO")


class TradeDecision(Base, TimestampMixin):
    __tablename__ = "trade_decisions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    trade_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trade_files.id"), index=True)
    label: Mapped[str] = mapped_column(String(300))
    rationale: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
