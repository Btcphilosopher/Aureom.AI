from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Header, Query, Response, UploadFile
from sqlalchemy import select

from horizon.api.schemas import (
    ApprovalIn,
    BatchIn,
    BatchPatch,
    BeneficiaryIn,
    BeneficiaryPatch,
    CancelIn,
    RejectionResolutionIn,
    ReviewIn,
    SuspendIn,
    VersionIn,
)
from horizon.core.context import Principal, get_principal
from horizon.core.errors import DomainError, Forbidden, NotFound
from horizon.core.iban import check_format
from horizon.core.money import money
from horizon.core.pagination import PageParams, paginate, paginate_list
from horizon.modules.approvals import service as approvals
from horizon.modules.beneficiaries import service as benes
from horizon.modules.beneficiaries.models import Beneficiary
from horizon.modules.payments import service as payments
from horizon.modules.payments import state
from horizon.modules.payments.models import Payment, PaymentBatch

router = APIRouter(prefix="/v1", tags=["Paiements"])


# ---------------------------------------------------------------- bénéficiaires

@router.get("/beneficiaries", tags=["Bénéficiaires"])
def list_beneficiaries(page: PageParams = Depends(), entity_id: uuid.UUID | None = None, status: str | None = None,
                       p: Principal = Depends(get_principal)):
    p.require_any("beneficiary.read")
    rows = p.db.scalars(select(Beneficiary).where(Beneficiary.organization_id == p.org_id).order_by(Beneficiary.created_at)).all()
    rows = [b for b in rows if p.authz.can_see_entity("beneficiary.read", b.entity_id)
            and (entity_id is None or b.entity_id == entity_id) and (status is None or b.status == status)]
    return paginate_list([benes.serialize(p.db, b) for b in rows], page)


@router.post("/beneficiaries", status_code=201, tags=["Bénéficiaires"])
def create_beneficiary(body: BeneficiaryIn, p: Principal = Depends(get_principal)):
    b = benes.create(p.db, p, body.model_dump())
    return benes.serialize(p.db, b, with_history=True)


@router.post("/beneficiaries/validate-iban", tags=["Bénéficiaires"], summary="Contrôle de format (ne prouve pas l'existence)")
def validate_iban(body: dict, p: Principal = Depends(get_principal)):
    return check_format(str(body.get("iban", "")))


@router.get("/beneficiaries/{bene_id}", tags=["Bénéficiaires"])
def get_beneficiary(bene_id: uuid.UUID, p: Principal = Depends(get_principal)):
    return benes.serialize(p.db, benes.get(p.db, p, bene_id), with_history=True)


@router.patch("/beneficiaries/{bene_id}", tags=["Bénéficiaires"], summary="Nouvelle version (revue si modification matérielle)")
def patch_beneficiary(bene_id: uuid.UUID, body: BeneficiaryPatch, p: Principal = Depends(get_principal)):
    b = benes.update(p.db, p, bene_id, body.model_dump(exclude_none=True))
    return benes.serialize(p.db, b, with_history=True)


@router.post("/beneficiaries/{bene_id}/review", tags=["Bénéficiaires"], summary="Valider/rejeter la version en revue (MFA)")
def review_beneficiary(bene_id: uuid.UUID, body: ReviewIn, p: Principal = Depends(get_principal)):
    b = benes.review(p.db, p, bene_id, body.decision == "APPROVE", body.comment)
    return benes.serialize(p.db, b, with_history=True)


@router.post("/beneficiaries/{bene_id}/suspension", tags=["Bénéficiaires"])
def suspend_beneficiary(bene_id: uuid.UUID, body: SuspendIn, p: Principal = Depends(get_principal)):
    b = benes.set_suspension(p.db, p, bene_id, body.suspend, body.reason)
    return benes.serialize(p.db, b, with_history=True)


# ------------------------------------------------------------------------ lots

def _visible_batch(p: Principal, b: PaymentBatch) -> bool:
    return p.authz.has("payment.read", b.entity_id, b.debtor_account_id)


@router.get("/payment-batches")
def list_batches(page: PageParams = Depends(), status: str | None = None, p: Principal = Depends(get_principal)):
    p.require_any("payment.read")
    rows = p.db.scalars(select(PaymentBatch).where(PaymentBatch.organization_id == p.org_id)
                        .order_by(PaymentBatch.created_at.desc())).all()
    rows = [b for b in rows if _visible_batch(p, b) and (status is None or b.status == status)]
    return paginate_list([payments.serialize_batch(p.db, b) for b in rows], page)


@router.post("/payment-batches", status_code=201, summary="Créer un virement unitaire ou un lot (Idempotency-Key recommandé)")
def create_batch(body: BatchIn, response: Response, idempotency_key: str | None = Header(default=None, max_length=200),
                 p: Principal = Depends(get_principal)):
    data = body.model_dump(mode="json")
    batch, created = payments.create_batch(p.db, p, data, idempotency_key)
    if not created:
        response.status_code = 200
        response.headers["Idempotent-Replayed"] = "true"
    return payments.serialize_batch(p.db, batch, detail=True)


@router.post("/payment-batches/import-csv", status_code=201, summary="Import CSV (iban;montant;libelle)")
async def import_csv(file: UploadFile = File(...), debtor_account_id: uuid.UUID = Form(...), label: str = Form("Import CSV"),
                     execution_date: str | None = Form(None),
                     idempotency_key: str | None = Header(default=None, max_length=200), p: Principal = Depends(get_principal)):
    content = await file.read()
    if len(content) > 1_000_000:
        raise DomainError("FILE_TOO_LARGE", "Fichier CSV limité à 1 Mo", 413)
    items, errors = payments.parse_csv(p.db, p, debtor_account_id, content)
    if errors:
        raise DomainError("CSV_INVALID", f"{len(errors)} ligne(s) invalide(s) : aucun lot créé", 422,
                          {"errors": errors, "valid_lines": len(items)})
    if not items:
        raise DomainError("EMPTY_BATCH", "Aucune ligne exploitable", 422)
    batch, _ = payments.create_batch(p.db, p, {"debtor_account_id": str(debtor_account_id), "kind": "CSV_IMPORT",
                                               "label": label, "execution_date": execution_date, "payments": items,
                                               "source_filename": file.filename}, idempotency_key)
    return payments.serialize_batch(p.db, batch, detail=True)


@router.get("/payment-batches/{batch_id}")
def get_batch(batch_id: uuid.UUID, p: Principal = Depends(get_principal)):
    return payments.serialize_batch(p.db, payments.get_batch(p.db, p, batch_id), detail=True)


@router.patch("/payment-batches/{batch_id}", summary="Modifier (toute modification matérielle invalide les approbations)")
def patch_batch(batch_id: uuid.UUID, body: BatchPatch, p: Principal = Depends(get_principal)):
    changes = body.model_dump(mode="json", exclude_none=True)
    ev = changes.pop("expected_version")
    b = payments.update_batch(p.db, p, batch_id, ev, changes)
    return payments.serialize_batch(p.db, b, detail=True)


@router.post("/payment-batches/{batch_id}/submit-for-approval")
def submit_for_approval(batch_id: uuid.UUID, body: VersionIn, p: Principal = Depends(get_principal)):
    b = payments.submit_for_approval(p.db, p, batch_id, body.expected_version)
    return payments.serialize_batch(p.db, b, detail=True)


@router.post("/payment-batches/{batch_id}/approvals", summary="Approuver/refuser une version précise (réauthentification requise)")
def approve(batch_id: uuid.UUID, body: ApprovalIn, p: Principal = Depends(get_principal)):
    res = approvals.decide(p.db, p, batch_id, body.decision, body.version, body.comment)
    b = p.db.get(PaymentBatch, batch_id)
    return {"result": res, "batch": payments.serialize_batch(p.db, b, detail=True)}


@router.post("/payment-batches/{batch_id}/cancel")
def cancel(batch_id: uuid.UUID, body: CancelIn, p: Principal = Depends(get_principal)):
    b = payments.cancel_batch(p.db, p, batch_id, body.reason)
    return payments.serialize_batch(p.db, b, detail=True)


# -------------------------------------------------------------------- paiements

@router.get("/payments")
def list_payments(page: PageParams = Depends(), status: str | None = Query(None), p: Principal = Depends(get_principal)):
    p.require_any("payment.read")
    stmt = select(Payment).where(Payment.organization_id == p.org_id).order_by(Payment.created_at.desc())
    if status:
        stmt = stmt.where(Payment.status == status)
    rows = [x for x in p.db.scalars(stmt) if p.authz.has("payment.read", x.entity_id, x.debtor_account_id)]
    return paginate_list([payments.serialize_payment(p.db, x) for x in rows], page)


@router.get("/payments/{payment_id}")
def get_payment(payment_id: uuid.UUID, p: Principal = Depends(get_principal)):
    x = p.db.get(Payment, payment_id)
    if x is None or x.organization_id != p.org_id:
        raise NotFound("Paiement", payment_id)
    if not p.authz.has("payment.read", x.entity_id, x.debtor_account_id):
        p.denied("payment.read", entity_id=x.entity_id, account_id=x.debtor_account_id)
        raise Forbidden("Permission « payment.read » requise", {"permission": "payment.read"})
    out = payments.serialize_payment(p.db, x, with_events=True)
    from horizon.modules.payments.models import PaymentReturn

    out["returns"] = [{"amount": money(r.amount_minor, r.currency), "reason_code": r.reason_code,
                       "at": r.created_at.isoformat(), "ledger_entry_id": str(r.ledger_entry_id)}
                      for r in p.db.scalars(select(PaymentReturn).where(PaymentReturn.payment_id == x.id))]
    return out


@router.post("/payments/{payment_id}/rejection-resolution", summary="Traiter un rejet (justification obligatoire)")
def resolve_rejection(payment_id: uuid.UUID, body: RejectionResolutionIn, p: Principal = Depends(get_principal)):
    x = payments.resolve_rejection(p.db, p, payment_id, body.resolution)
    return payments.serialize_payment(p.db, x, with_events=True)


@router.get("/payment-lifecycle", summary="Transitions d'état documentées")
def lifecycle():
    return state.transitions_doc()
