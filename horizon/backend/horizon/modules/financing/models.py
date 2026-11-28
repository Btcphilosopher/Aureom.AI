from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base, TimestampMixin, new_id


class FinancingFacility(Base, TimestampMixin):
    """Contrat accepté (fictif). Distinct des simulations et des demandes."""

    __tablename__ = "financing_facilities"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"))
    reference: Mapped[str] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(30))  # RCF / TERM_LOAN
    label: Mapped[str] = mapped_column(String(200))
    lender: Mapped[str] = mapped_column(String(200))
    committed_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    signed_date: Mapped[date]
    maturity_date: Mapped[date]
    interest_rate_bps: Mapped[int] = mapped_column(Integer)
    rate_description: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="CONTRACT_ACTIVE")
    repayment_beneficiary_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("beneficiaries.id"))
    repayment_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bank_accounts.id"))
    document_ids: Mapped[list] = mapped_column(JSON, default=list)


class FinancingDrawdown(Base, TimestampMixin):
    __tablename__ = "financing_drawdowns"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    facility_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("financing_facilities.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    drawdown_date: Mapped[date]
    status: Mapped[str] = mapped_column(String(20), default="OUTSTANDING")  # OUTSTANDING / REPAID


class FinancingInstallment(Base, TimestampMixin):
    __tablename__ = "financing_installments"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    facility_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("financing_facilities.id"), index=True)
    due_date: Mapped[date]
    principal_minor: Mapped[int] = mapped_column(BigInteger)
    interest_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20), default="TO_PREPARE")  # TO_PREPARE / PREPARED / PAID
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    payment_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payment_batches.id"))


class FinancingSimulation(Base, TimestampMixin):
    """Calcul indicatif. N'engage personne et ne constitue pas une demande."""

    __tablename__ = "financing_simulations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    params: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class FinancingRequest(Base, TimestampMixin):
    """Demande transmise pour revue humaine. Aucun octroi automatique."""

    __tablename__ = "financing_requests"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"))
    kind: Mapped[str] = mapped_column(String(30))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    purpose: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(30), default="SUBMITTED_FOR_REVIEW")
    simulation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("financing_simulations.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
