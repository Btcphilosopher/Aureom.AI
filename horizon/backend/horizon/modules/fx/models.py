from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base, TimestampMixin, new_id


class FxRate(Base, TimestampMixin):
    """Taux indicatif identifié et daté (unités de quote pour 1 base)."""

    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("base", "quote", "as_of_date", "source"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    base: Mapped[str] = mapped_column(String(3))
    quote: Mapped[str] = mapped_column(String(3))
    rate: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    as_of_date: Mapped[date]
    observed_at: Mapped[datetime]
    source: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="INDICATIVE")


class FxQuote(Base, TimestampMixin):
    """Devis de change. INDICATIVE : information seule. EXECUTABLE_SIMULATED :
    offre ferme du simulateur, acceptable avant expiration — aucun ordre réel."""

    __tablename__ = "fx_quotes"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"))
    kind: Mapped[str] = mapped_column(String(30))
    side: Mapped[str] = mapped_column(String(4))  # BUY / SELL (de la devise de base de la paire)
    base: Mapped[str] = mapped_column(String(3))
    quote: Mapped[str] = mapped_column(String(3))
    sell_currency: Mapped[str] = mapped_column(String(3))
    buy_currency: Mapped[str] = mapped_column(String(3))
    sell_minor: Mapped[int] = mapped_column(BigInteger)
    buy_minor: Mapped[int] = mapped_column(BigInteger)
    mid_rate: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    client_rate: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    fee_bps: Mapped[int]
    fee_minor: Mapped[int] = mapped_column(BigInteger)
    fee_currency: Mapped[str] = mapped_column(String(3))
    rate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fx_rates.id"))
    source: Mapped[str] = mapped_column(String(200))
    expires_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    sell_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bank_accounts.id"))
    buy_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bank_accounts.id"))
    ledger_entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("journal_entries.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    accepted_at: Mapped[datetime | None]
