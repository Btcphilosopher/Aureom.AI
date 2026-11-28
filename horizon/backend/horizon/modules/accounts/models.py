from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base, TimestampMixin, new_id

ACCOUNT_KINDS = ("SIMULATED", "EXTERNAL_READONLY")


class BankAccount(Base, TimestampMixin):
    """Compte bancaire.

    SIMULATED : solde dérivé du registre en partie double HORIZON.
    EXTERNAL_READONLY : solde observé depuis un système externe (relevé), jamais
    mélangé aux comptes simulés et jamais débité par HORIZON.
    """

    __tablename__ = "bank_accounts"
    __table_args__ = (CheckConstraint(f"kind IN {ACCOUNT_KINDS}", name="kind_valid"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    iban: Mapped[str] = mapped_column(String(34), unique=True)
    bic: Mapped[str] = mapped_column(String(11))
    currency: Mapped[str] = mapped_column(String(3))
    kind: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="OPEN")


class ExternalBalanceSnapshot(Base, TimestampMixin):
    __tablename__ = "external_balance_snapshots"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bank_accounts.id"), index=True)
    booked_minor: Mapped[int] = mapped_column(BigInteger)
    available_minor: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    source: Mapped[str] = mapped_column(String(200))
    statement_reference: Mapped[str] = mapped_column(String(100), default="")
    observed_at: Mapped[datetime]
    received_at: Mapped[datetime]
