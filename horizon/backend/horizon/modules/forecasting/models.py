from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base, TimestampMixin, new_id


class ExpectedReceipt(Base, TimestampMixin):
    __tablename__ = "expected_receipts"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"))
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bank_accounts.id"))
    counterparty: Mapped[str] = mapped_column(String(200))
    reference: Mapped[str] = mapped_column(String(100))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    expected_date: Mapped[date]
    confidence: Mapped[str] = mapped_column(String(10), default="HIGH")  # HIGH / MEDIUM / LOW
    status: Mapped[str] = mapped_column(String(20), default="EXPECTED")  # EXPECTED / RECEIVED / CANCELLED
    matched_entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("journal_entries.id"))


class RecurringAssumption(Base, TimestampMixin):
    __tablename__ = "recurring_assumptions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"))
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bank_accounts.id"))
    label: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100))
    direction: Mapped[str] = mapped_column(String(3))  # IN / OUT
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    day_of_month: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date]
    end_date: Mapped[date | None]
    is_active: Mapped[bool] = mapped_column(default=True)


class RecurringRealization(Base, TimestampMixin):
    """Occurrence d'hypothèse devenue réelle : elle sort de la prévision."""

    __tablename__ = "recurring_realizations"
    __table_args__ = (UniqueConstraint("assumption_id", "occurrence_date"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    assumption_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recurring_assumptions.id"))
    occurrence_date: Mapped[date]
    realized_by_type: Mapped[str] = mapped_column(String(50))
    realized_by_id: Mapped[str] = mapped_column(String(100))


class CashflowScenario(Base, TimestampMixin):
    __tablename__ = "cashflow_scenarios"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(1000), default="")
    receipts_haircut_pct: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    receipts_delay_days: Mapped[int] = mapped_column(Integer, default=0)
    disbursements_uplift_pct: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    include_pending_approval: Mapped[bool] = mapped_column(default=True)
    include_low_confidence: Mapped[bool] = mapped_column(default=True)
    is_baseline: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class ForecastRun(Base, TimestampMixin):
    """Résultat figé et explicable d'un calcul de prévision."""

    __tablename__ = "forecast_runs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cashflow_scenarios.id"))
    horizon_days: Mapped[int]
    as_of: Mapped[date]
    method: Mapped[str] = mapped_column(String(100))
    inputs: Mapped[dict] = mapped_column(JSON)
    series: Mapped[list] = mapped_column(JSON)
    lines: Mapped[list] = mapped_column(JSON)
    excluded: Mapped[list] = mapped_column(JSON)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
