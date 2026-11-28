"""Financement : contrats acceptés, utilisations, échéances, simulations et demandes.

Séparation stricte :
* FinancingSimulation : calcul indicatif, n'engage personne ;
* FinancingRequest : demande transmise pour revue humaine — AUCUN octroi automatique ;
* FinancingFacility : contrat accepté (données fictives de démonstration).
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.errors import Conflict, DomainError, NotFound
from horizon.core.money import from_minor, money, to_minor
from horizon.modules.financing.models import (
    FinancingDrawdown,
    FinancingFacility,
    FinancingInstallment,
    FinancingRequest,
    FinancingSimulation,
)
from horizon.modules.identity.models import User

KIND_LABELS = {"RCF": "Crédit renouvelable", "TERM_LOAN": "Prêt amortissable"}
INST_LABELS = {"TO_PREPARE": "À préparer", "PREPARED": "Préparée (paiement créé)", "PAID": "Payée"}


def drawn(db, fac_id) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(FinancingDrawdown.amount_minor), 0))
                         .where(FinancingDrawdown.facility_id == fac_id, FinancingDrawdown.status == "OUTSTANDING")) or 0)


def serialize_installment(db, i: FinancingInstallment) -> dict:
    fac = db.get(FinancingFacility, i.facility_id)
    u = db.get(User, i.owner_user_id) if i.owner_user_id else None
    return {"id": str(i.id), "facility_id": str(fac.id), "facility": fac.label, "facility_reference": fac.reference,
            "due_date": i.due_date.isoformat(), "principal": money(i.principal_minor, i.currency),
            "interest": money(i.interest_minor, i.currency), "total": money(i.principal_minor + i.interest_minor, i.currency),
            "status": i.status, "status_label": INST_LABELS[i.status], "owner": u.full_name if u else None,
            "payment_batch_id": str(i.payment_batch_id) if i.payment_batch_id else None,
            "days_until_due": (i.due_date - clock.today()).days}


def serialize_facility(db, f: FinancingFacility, detail=False) -> dict:
    d = drawn(db, f.id)
    out = {"id": str(f.id), "reference": f.reference, "kind": f.kind, "kind_label": KIND_LABELS.get(f.kind, f.kind),
           "label": f.label, "lender": f.lender, "status": f.status, "status_label": "Contrat accepté (fictif)",
           "entity_id": str(f.entity_id), "committed": money(f.committed_minor, f.currency), "drawn": money(d, f.currency),
           "undrawn": money(f.committed_minor - d, f.currency), "signed_date": f.signed_date.isoformat(),
           "maturity_date": f.maturity_date.isoformat(), "interest_rate_bps": f.interest_rate_bps,
           "rate_description": f.rate_description, "document_ids": f.document_ids}
    if detail:
        out["drawdowns"] = [{"id": str(x.id), "amount": money(x.amount_minor, x.currency), "date": x.drawdown_date.isoformat(),
                             "status": x.status}
                            for x in db.scalars(select(FinancingDrawdown).where(FinancingDrawdown.facility_id == f.id))]
        out["installments"] = [serialize_installment(db, i) for i in db.scalars(
            select(FinancingInstallment).where(FinancingInstallment.facility_id == f.id).order_by(FinancingInstallment.due_date))]
    return out


def prepare_installment(db: Session, principal, inst_id: uuid.UUID) -> dict:
    """Crée le paiement de remboursement (lot FINANCING) — soumis ensuite au circuit d'approbation normal."""
    from horizon.modules.payments import service as payments

    i = db.get(FinancingInstallment, inst_id, with_for_update=True)
    if i is None or i.organization_id != principal.org_id:
        raise NotFound("Échéance", inst_id)
    fac = db.get(FinancingFacility, i.facility_id)
    principal.require("financing.prepare", fac.entity_id)
    if i.status != "TO_PREPARE":
        raise Conflict("ALREADY_PREPARED", f"Échéance à l'état {i.status}")
    if fac.repayment_beneficiary_id is None or fac.repayment_account_id is None:
        raise DomainError("NO_REPAYMENT_SETUP", "Bénéficiaire ou compte de remboursement non configuré", 422)
    total = i.principal_minor + i.interest_minor
    batch, _ = payments.create_batch(db, principal, {
        "debtor_account_id": str(fac.repayment_account_id), "kind": "FINANCING",
        "label": f"Échéance {fac.label} du {i.due_date.strftime('%d/%m/%Y')}",
        "execution_date": max(i.due_date, clock.today()).isoformat(),
        "payments": [{"beneficiary_id": str(fac.repayment_beneficiary_id), "amount": str(from_minor(total, i.currency)),
                      "remittance_info": f"{fac.reference} ECHEANCE {i.due_date.isoformat()}"}],
    }, idempotency_key=f"financing-installment:{i.id}")
    i.status = "PREPARED"
    i.payment_batch_id = batch.id
    db.flush()
    principal.audit("financing.installment_prepared", "financing_installment", i.id, entity_id=fac.entity_id,
                    details={"batch": batch.reference})
    return {"installment": serialize_installment(db, i), "batch_id": str(batch.id), "batch_reference": batch.reference}


def simulate(db: Session, principal, params: dict) -> FinancingSimulation:
    principal.require_any("financing.read")
    ccy = params.get("currency", "EUR")
    amount = to_minor(params["amount"], ccy)
    months = int(params["months"])
    rate_pct = Decimal(str(params["annual_rate_pct"]))
    if amount <= 0 or not (1 <= months <= 360) or not (Decimal(0) <= rate_pct <= Decimal(30)):
        raise DomainError("INVALID_SIMULATION", "Paramètres hors bornes", 422)
    r = rate_pct / Decimal(1200)
    P = from_minor(amount, ccy)
    pay = (P / months) if r == 0 else P * r / (1 - (1 + r) ** -months)
    pay = pay.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    bal = P
    schedule = []
    total_int = Decimal(0)
    for k in range(1, months + 1):
        interest = (bal * r).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        princ = pay - interest if k < months else bal
        bal -= princ
        total_int += interest
        if k <= 12 or k == months:
            schedule.append({"month": k, "payment": str(princ + interest), "principal": str(princ), "interest": str(interest),
                             "remaining": str(bal)})
    result = {"monthly_payment": str(pay), "total_interest": str(total_int), "currency": ccy, "schedule_excerpt": schedule,
              "disclaimer": "Simulation indicative à taux fixe constant. Ne constitue ni une offre, ni une demande, ni un accord de crédit."}
    sim = FinancingSimulation(organization_id=principal.org_id, params={**params, "amount": str(from_minor(amount, ccy))},
                              result=result, created_by=principal.user_id)
    db.add(sim)
    db.flush()
    return sim


def create_request(db: Session, principal, data: dict) -> FinancingRequest:
    principal.require("financing.prepare", data["entity_id"])
    ccy = data.get("currency", "EUR")
    req = FinancingRequest(organization_id=principal.org_id, entity_id=data["entity_id"], kind=data["kind"],
                           amount_minor=to_minor(data["amount"], ccy), currency=ccy, purpose=data["purpose"],
                           simulation_id=data.get("simulation_id"), created_by=principal.user_id,
                           status="SUBMITTED_FOR_REVIEW")
    db.add(req)
    db.flush()
    principal.audit("financing.request_submitted", "financing_request", req.id, entity_id=req.entity_id,
                    details={"amount": data["amount"], "kind": data["kind"]})
    return req


def serialize_request(db, r: FinancingRequest) -> dict:
    return {"id": str(r.id), "kind": r.kind, "amount": money(r.amount_minor, r.currency), "purpose": r.purpose,
            "status": r.status, "status_label": "Transmise pour revue humaine — aucun octroi automatique",
            "created_at": r.created_at.isoformat(), "entity_id": str(r.entity_id)}
