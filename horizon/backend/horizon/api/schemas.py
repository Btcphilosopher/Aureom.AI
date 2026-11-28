"""Schémas de requête (validation Pydantic). Les montants sont des chaînes décimales."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AMOUNT_RE = r"^\d{1,13}(\.\d{1,2})?$"


def _amount():
    return Field(pattern=AMOUNT_RE, description="Montant décimal positif, ex. « 480000.00 »")


def _opt_amount():
    return Field(default=None, pattern=AMOUNT_RE, description="Montant décimal positif")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginIn(Strict):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class MfaIn(Strict):
    challenge_id: uuid.UUID
    code: str = Field(pattern=r"^\d{6}$")


class StepUpIn(Strict):
    code: str = Field(pattern=r"^\d{6}$")


class BeneficiaryIn(Strict):
    entity_id: uuid.UUID
    name: str = Field(min_length=2, max_length=200)
    iban: str = Field(min_length=15, max_length=42)
    bic: str = Field(default="", max_length=11)
    country_code: str = Field(pattern=r"^[A-Za-z]{2}$")
    address: str = Field(default="", max_length=500)
    email: str = Field(default="", max_length=200)
    category: str = Field(default="Fournisseur", max_length=100)


class BeneficiaryPatch(Strict):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    iban: str | None = Field(default=None, min_length=15, max_length=42)
    bic: str | None = Field(default=None, max_length=11)
    country_code: str | None = Field(default=None, pattern=r"^[A-Za-z]{2}$")
    address: str | None = Field(default=None, max_length=500)
    email: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=100)


class ReviewIn(Strict):
    decision: Literal["APPROVE", "REJECT"]
    comment: str | None = Field(default=None, max_length=500)


class SuspendIn(Strict):
    suspend: bool
    reason: str = Field(min_length=5, max_length=500)


class PaymentLineIn(Strict):
    beneficiary_id: uuid.UUID
    amount: str = _amount()
    remittance_info: str = Field(default="", max_length=140)
    forecast_ref: str | None = Field(default=None, max_length=200)


class BatchIn(Strict):
    debtor_account_id: uuid.UUID
    kind: Literal["SINGLE", "SUPPLIER_BATCH"] | None = None
    label: str | None = Field(default=None, max_length=200)
    execution_date: date | None = None
    payments: list[PaymentLineIn] = Field(min_length=1, max_length=500)
    forecast_ref: str | None = Field(default=None, max_length=200)


class PaymentUpdate(Strict):
    payment_id: uuid.UUID
    amount: str | None = _opt_amount()
    remittance_info: str | None = Field(default=None, max_length=140)


class BatchPatch(Strict):
    expected_version: int
    label: str | None = Field(default=None, max_length=200)
    execution_date: date | None = None
    add_payments: list[PaymentLineIn] | None = None
    update_payments: list[PaymentUpdate] | None = None
    remove_payment_ids: list[uuid.UUID] | None = None


class VersionIn(Strict):
    expected_version: int


class ApprovalIn(Strict):
    decision: Literal["APPROVE", "REJECT"]
    version: int = Field(description="Version du lot examinée par l'approbateur")
    comment: str | None = Field(default=None, max_length=500)


class CancelIn(Strict):
    reason: str = Field(min_length=5, max_length=500)


class RejectionResolutionIn(Strict):
    resolution: str = Field(min_length=10, max_length=500)


class ScenarioIn(Strict):
    code: str = Field(pattern=r"^[A-Z0-9_]{2,30}$")
    name: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)
    receipts_haircut_pct: float = Field(default=0, ge=0, le=100)
    receipts_delay_days: int = Field(default=0, ge=0, le=90)
    disbursements_uplift_pct: float = Field(default=0, ge=0, le=100)
    include_pending_approval: bool = True
    include_low_confidence: bool = True


class ForecastIn(Strict):
    scenario_id: uuid.UUID
    horizon_days: Literal[7, 30, 90]


class FxQuoteIn(Strict):
    entity_id: uuid.UUID
    base: str = Field(pattern=r"^[A-Z]{3}$")
    quote: str = Field(pattern=r"^[A-Z]{3}$")
    side: Literal["BUY", "SELL"]
    amount: str = _amount()
    amount_currency: str = Field(pattern=r"^[A-Z]{3}$")
    kind: Literal["INDICATIVE", "EXECUTABLE_SIMULATED"] = "INDICATIVE"
    sell_account_id: uuid.UUID | None = None
    buy_account_id: uuid.UUID | None = None


class FinancingSimIn(Strict):
    amount: str = _amount()
    currency: str = "EUR"
    months: int = Field(ge=1, le=360)
    annual_rate_pct: float = Field(ge=0, le=30)


class FinancingRequestIn(Strict):
    entity_id: uuid.UUID
    kind: Literal["RCF", "TERM_LOAN", "SHORT_TERM"]
    amount: str = _amount()
    currency: str = "EUR"
    purpose: str = Field(min_length=10, max_length=1000)
    simulation_id: uuid.UUID | None = None


class ReconRunIn(Strict):
    account_id: uuid.UUID


class ReconAckIn(Strict):
    note: str | None = Field(default=None, max_length=500)


class ReconResolveIn(Strict):
    action: Literal["POST_ADJUSTMENT", "EXPLAINED"]
    note: str = Field(min_length=10, max_length=1000)


class AckIn(Strict):
    key: str = Field(max_length=200)
    note: str | None = Field(default=None, max_length=500)


class RoleAssignmentIn(Strict):
    user_id: uuid.UUID
    role: Literal["VIEWER", "PREPARER", "APPROVER", "ADMIN", "AUDITOR"]
    entity_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    approval_limit: str | None = _opt_amount()
    mandate_reference: str = Field(default="", max_length=200)
    valid_to: date | None = None


class DelegationIn(Strict):
    delegate_user_id: uuid.UUID
    entity_id: uuid.UUID
    max_amount: str = _amount()
    valid_days: int = Field(ge=1, le=30)
    reason: str = Field(min_length=5, max_length=500)


class PolicyRuleIn(Strict):
    name: str = Field(max_length=200)
    entity_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    min_amount: str = _amount()
    required_approvals: int = Field(ge=1, le=5)
    approval_validity_hours: int = Field(default=72, ge=1, le=720)


class TradeFileIn(Strict):
    entity_id: uuid.UUID
    title: str = Field(max_length=300)
    direction: Literal["IMPORT", "EXPORT"]
    instrument_considered: str = Field(default="", max_length=200)
    amount: str | None = _opt_amount()
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")


class TradeTaskIn(Strict):
    label: str = Field(max_length=300)
    due_date: date | None = None
    assignee_user_id: uuid.UUID | None = None


class TradeTaskPatch(Strict):
    status: Literal["TODO", "IN_PROGRESS", "DONE"]


class TradeRequestIn(Strict):
    kind: str = Field(max_length=100)
    body: str = Field(min_length=5, max_length=5000)


class TradeDecisionIn(Strict):
    label: str = Field(max_length=300)
    rationale: str = Field(min_length=5, max_length=5000)


class TradeDeadlineIn(Strict):
    label: str = Field(max_length=200)
    due_date: date


class TradePartyIn(Strict):
    role: str = Field(max_length=100)
    name: str = Field(max_length=200)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")


class FaultIn(Strict):
    kind: Literal["TIMEOUT_AFTER_RECORD", "TIMEOUT_BEFORE_RECORD"]
    match_remittance: str | None = Field(default=None, max_length=140)


class ReturnIn(Strict):
    payment_id: uuid.UUID
    amount: str | None = _opt_amount()
    reason_code: str = Field(default="MD06", pattern=r"^[A-Z0-9]{4}$")


class IncomingIn(Strict):
    expected_receipt_id: uuid.UUID


class RedeliverIn(Strict):
    event_id: str = Field(max_length=100)


class ReverseIn(Strict):
    reason: str = Field(min_length=10, max_length=500)
