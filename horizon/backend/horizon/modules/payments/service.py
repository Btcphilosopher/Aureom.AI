"""Préparation, validation, approbation et annulation des lots de paiements."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.errors import Conflict, DomainError, Forbidden, NotFound
from horizon.core.iban import normalize
from horizon.core.money import fmt, money, to_minor
from horizon.modules.accounts.models import BankAccount
from horizon.modules.approvals import service as approvals
from horizon.modules.approvals.models import Approval
from horizon.modules.beneficiaries.models import MATERIAL_FIELDS, Beneficiary, BeneficiaryVersion
from horizon.modules.identity.models import User
from horizon.modules.jobs import queue
from horizon.modules.ledger import service as ledger
from horizon.modules.organizations.models import LegalEntity
from horizon.modules.payments import state
from horizon.modules.payments.models import Payment, PaymentBatch, PaymentEvent

KINDS = {"SINGLE": "Virement unitaire", "SUPPLIER_BATCH": "Lot fournisseurs", "CSV_IMPORT": "Import CSV",
         "FINANCING": "Remboursement de financement"}


# ----------------------------------------------------------------- utilitaires

def log_event(db: Session, batch: PaymentBatch, to_status: str, *, payment: Payment | None = None,
              from_status: str | None = None, actor: uuid.UUID | None = None, source: str = "USER",
              reason: str | None = None) -> None:
    db.add(PaymentEvent(organization_id=batch.organization_id, batch_id=batch.id,
                        payment_id=payment.id if payment else None, from_status=from_status, to_status=to_status,
                        actor_user_id=actor, source=source, reason=reason, batch_version=batch.version))


def set_batch_status(db, batch: PaymentBatch, to: str, *, actor=None, source="USER", reason=None) -> None:
    if batch.status == to:
        return
    state.check_batch(batch.status, to)
    frm = batch.status
    batch.status = to
    batch.status_reason = reason
    log_event(db, batch, to, from_status=frm, actor=actor, source=source, reason=reason)


def set_payment_status(db, batch: PaymentBatch, p: Payment, to: str, *, actor=None, source="USER", reason=None) -> None:
    if p.status == to:
        return
    state.check_payment(p.status, to)
    frm = p.status
    p.status = to
    p.status_reason = reason
    log_event(db, batch, to, payment=p, from_status=frm, actor=actor, source=source, reason=reason)


def payments_of(db: Session, batch: PaymentBatch) -> list[Payment]:
    return db.scalars(select(Payment).where(Payment.batch_id == batch.id).order_by(Payment.line_no)).all()


def get_batch(db: Session, principal, batch_id: uuid.UUID, *, lock: bool = False) -> PaymentBatch:
    b = db.get(PaymentBatch, batch_id, with_for_update=lock)
    if b is None or b.organization_id != principal.org_id:
        raise NotFound("Lot de paiements", batch_id)
    if not principal.authz.has("payment.read", b.entity_id, b.debtor_account_id):
        principal.denied("payment.read", entity_id=b.entity_id, account_id=b.debtor_account_id)
        raise Forbidden("Permission « payment.read » requise sur ce compte", {"permission": "payment.read"})
    return b


def _fingerprint(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def _next_reference(db: Session) -> str:
    n = db.scalar(text("SELECT nextval('payment_batch_reference_seq')"))
    return f"LOT-{clock.today().year}-{n:05d}"


def _debtor_account(db: Session, principal, account_id) -> BankAccount:
    acc = db.get(BankAccount, account_id)
    if acc is None or acc.organization_id != principal.org_id:
        raise NotFound("Compte", account_id)
    if acc.kind != "SIMULATED":
        raise DomainError("ACCOUNT_READ_ONLY", "Compte externe en lecture seule : aucun paiement ne peut en être émis", 422)
    if acc.status != "OPEN":
        raise DomainError("ACCOUNT_CLOSED", "Compte non ouvert", 422)
    return acc


def _pinned_version(db: Session, b: Beneficiary) -> BeneficiaryVersion:
    """Version à figer : l'approuvée si elle existe, sinon la courante (lot ira « À vérifier »)."""
    vid = b.approved_version_id or b.current_version_id
    return db.get(BeneficiaryVersion, vid)


def _build_payment(db, principal, batch: PaymentBatch, acc: BankAccount, line_no: int, item: dict) -> Payment:
    bid = item["beneficiary_id"]
    b = db.get(Beneficiary, uuid.UUID(str(bid)))
    if b is None or b.organization_id != principal.org_id:
        raise NotFound("Bénéficiaire", bid)
    if b.entity_id != acc.entity_id:
        raise DomainError("BENEFICIARY_ENTITY_MISMATCH",
                          "Le bénéficiaire appartient à une autre entité que le compte débité", 422,
                          {"line": line_no})
    if b.status in ("REJECTED", "SUSPENDED"):
        raise DomainError("BENEFICIARY_NOT_USABLE", f"Bénéficiaire {b.status.lower()}", 422, {"line": line_no})
    amount = to_minor(item["amount"], acc.currency)
    if amount <= 0:
        raise DomainError("INVALID_AMOUNT", "Montant strictement positif requis", 422, {"line": line_no})
    v = _pinned_version(db, b)
    pid = uuid.uuid4()
    return Payment(
        id=pid, organization_id=principal.org_id, entity_id=acc.entity_id, batch_id=batch.id, line_no=line_no,
        debtor_account_id=acc.id, beneficiary_id=b.id, beneficiary_version_id=v.id, amount_minor=amount,
        currency=acc.currency, execution_date=batch.execution_date,
        remittance_info=(item.get("remittance_info") or "")[:140],
        end_to_end_id=f"HZN{batch.reference.replace('LOT-', '').replace('-', '')}{line_no:04d}",
        status="DRAFT", submission_key=f"hzn-{pid}", created_by=principal.user_id,
        forecast_ref=item.get("forecast_ref"),
    )


def _recompute_totals(db, batch: PaymentBatch) -> None:
    ps = [p for p in payments_of(db, batch) if p.status != "CANCELLED"]
    batch.total_minor = sum(p.amount_minor for p in ps)
    batch.payment_count = len(ps)


# --------------------------------------------------------------- préparation

def create_batch(db: Session, principal, data: dict, idempotency_key: str | None) -> tuple[PaymentBatch, bool]:
    acc = _debtor_account(db, principal, data["debtor_account_id"])
    principal.require("payment.prepare", acc.entity_id, acc.id)
    fp = _fingerprint(data)
    if idempotency_key:
        prior = db.scalar(select(PaymentBatch).where(PaymentBatch.organization_id == principal.org_id,
                                                     PaymentBatch.idempotency_key == idempotency_key))
        if prior is not None:
            if prior.request_fingerprint != fp:
                raise Conflict("IDEMPOTENCY_KEY_REUSED", "Clé d'idempotence déjà utilisée pour une requête différente")
            return prior, False
    items = data.get("payments") or []
    if not items:
        raise DomainError("EMPTY_BATCH", "Un lot doit contenir au moins un paiement", 422)
    kind = data.get("kind") or ("SUPPLIER_BATCH" if len(items) > 1 else "SINGLE")
    if kind not in KINDS:
        raise DomainError("INVALID_KIND", "Type de lot inconnu", 422)
    if kind == "SINGLE" and len(items) != 1:
        raise DomainError("SINGLE_EXPECTS_ONE", "Un virement unitaire contient exactement un paiement", 422)
    exec_date = data.get("execution_date") or clock.today()
    if isinstance(exec_date, str):
        exec_date = date.fromisoformat(exec_date)
    if exec_date < clock.today():
        raise DomainError("EXECUTION_DATE_PAST", "La date d'exécution ne peut pas être passée", 422)
    batch = PaymentBatch(
        organization_id=principal.org_id, entity_id=acc.entity_id, debtor_account_id=acc.id,
        reference=_next_reference(db), kind=kind, label=data.get("label") or KINDS[kind], status="DRAFT", version=1,
        currency=acc.currency, execution_date=exec_date, idempotency_key=idempotency_key, request_fingerprint=fp,
        source_filename=data.get("source_filename"), created_by=principal.user_id, forecast_ref=data.get("forecast_ref"),
    )
    db.add(batch)
    db.flush()
    for i, item in enumerate(items, start=1):
        db.add(_build_payment(db, principal, batch, acc, i, item))
    db.flush()
    _recompute_totals(db, batch)
    log_event(db, batch, "DRAFT", actor=principal.user_id, reason="Création")
    db.flush()
    principal.audit("payment_batch.created", "payment_batch", batch.id, entity_id=batch.entity_id,
                    details={"reference": batch.reference, "kind": kind, "count": batch.payment_count,
                             "total": fmt(batch.total_minor, batch.currency)})
    return batch, True


def parse_csv(db: Session, principal, account_id, content: bytes) -> tuple[list[dict], list[dict]]:
    """Colonnes : iban;montant;libelle (séparateur ; ou ,). Correspondance par IBAN
    avec un bénéficiaire de l'entité. Aucune création implicite de bénéficiaire."""
    acc = _debtor_account(db, principal, account_id)
    text_ = content.decode("utf-8-sig")
    dialect = csv.Sniffer().sniff(text_.splitlines()[0], delimiters=";,")
    reader = csv.DictReader(io.StringIO(text_), dialect=dialect)
    benes = db.scalars(select(Beneficiary).where(Beneficiary.entity_id == acc.entity_id)).all()
    by_iban = {}
    for b in benes:
        v = db.get(BeneficiaryVersion, b.approved_version_id or b.current_version_id)
        by_iban[v.iban] = b
    items, errors = [], []
    for n, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        iban = normalize(row.get("iban", ""))
        amount = row.get("montant") or row.get("amount")
        label = row.get("libelle") or row.get("libellé") or row.get("remittance_info") or ""
        b = by_iban.get(iban)
        if not iban or b is None:
            errors.append({"line": n, "code": "UNKNOWN_BENEFICIARY",
                           "message": "IBAN sans bénéficiaire enregistré pour cette entité (créez-le et faites-le valider)"})
            continue
        try:
            if to_minor((amount or "").replace(",", "."), acc.currency) <= 0:
                raise ValueError
        except Exception:  # noqa: BLE001
            errors.append({"line": n, "code": "INVALID_AMOUNT", "message": f"Montant invalide : {amount!r}"})
            continue
        items.append({"beneficiary_id": str(b.id), "amount": amount.replace(",", "."), "remittance_info": label})
    return items, errors


def update_batch(db: Session, principal, batch_id: uuid.UUID, expected_version: int, changes: dict) -> PaymentBatch:
    batch = get_batch(db, principal, batch_id, lock=True)
    principal.require("payment.prepare", batch.entity_id, batch.debtor_account_id)
    if batch.status not in state.EDITABLE_BATCH:
        raise Conflict("BATCH_NOT_EDITABLE", f"Lot non modifiable à l'état {batch.status}")
    if expected_version != batch.version:
        raise Conflict("VERSION_MISMATCH", "Version obsolète", {"current_version": batch.version})
    acc = db.get(BankAccount, batch.debtor_account_id)
    material = False
    if "label" in changes and changes["label"]:
        batch.label = changes["label"]
    if changes.get("execution_date"):
        d = date.fromisoformat(str(changes["execution_date"]))
        if d < clock.today():
            raise DomainError("EXECUTION_DATE_PAST", "Date passée", 422)
        if d != batch.execution_date:
            batch.execution_date = d
            for p in payments_of(db, batch):
                p.execution_date = d
            material = True
    for upd in changes.get("update_payments") or []:
        p = db.get(Payment, uuid.UUID(upd["payment_id"]))
        if p is None or p.batch_id != batch.id:
            raise NotFound("Paiement", upd.get("payment_id"))
        if "amount" in upd:
            amt = to_minor(upd["amount"], p.currency)
            if amt <= 0:
                raise DomainError("INVALID_AMOUNT", "Montant strictement positif requis", 422)
            if amt != p.amount_minor:
                p.amount_minor = amt
                material = True
        if "remittance_info" in upd:
            p.remittance_info = upd["remittance_info"][:140]
            material = True
    for rid in changes.get("remove_payment_ids") or []:
        p = db.get(Payment, uuid.UUID(rid))
        if p is None or p.batch_id != batch.id:
            raise NotFound("Paiement", rid)
        p.status = "CANCELLED"
        p.status_reason = "Retiré du lot avant exécution"
        log_event(db, batch, "CANCELLED", payment=p, actor=principal.user_id, reason="Retiré du lot")
        material = True
    add = changes.get("add_payments") or []
    if add:
        start = max([p.line_no for p in payments_of(db, batch)] or [0])
        for i, item in enumerate(add, start=start + 1):
            db.add(_build_payment(db, principal, batch, acc, i, item))
        material = True
    db.flush()
    if material:
        _material_change(db, principal, batch, "Modification matérielle du lot")
    _recompute_totals(db, batch)
    if batch.payment_count == 0:
        raise DomainError("EMPTY_BATCH", "Un lot doit contenir au moins un paiement", 422)
    principal.audit("payment_batch.updated", "payment_batch", batch.id, entity_id=batch.entity_id,
                    details={"material": material, "version": batch.version, "changes": list(changes.keys())})
    return batch


def _material_change(db, principal, batch: PaymentBatch, reason: str) -> None:
    """Toute modification matérielle : nouvelle version, approbations invalidées,
    réservations libérées, retour en brouillon (nouvelle soumission requise)."""
    batch.version += 1
    batch.approved_version = None
    approvals.invalidate(db, batch, f"{reason} (version {batch.version})")
    for p in payments_of(db, batch):
        if p.status in ("APPROVED", "SCHEDULED"):
            ledger.close_reservation(db, "payment", str(p.id), "RELEASED", reason)
        if p.status in ("TO_REVIEW", "PENDING_APPROVAL", "APPROVED", "SCHEDULED"):
            set_payment_status(db, batch, p, "DRAFT", actor=principal.user_id, reason=reason)
    if batch.status != "DRAFT":
        set_batch_status(db, batch, "DRAFT", actor=principal.user_id, reason=reason)


# ---------------------------------------------------------------- soumission

def validate_batch(db: Session, batch: PaymentBatch) -> list[dict]:
    issues = []
    acc = db.get(BankAccount, batch.debtor_account_id)
    if acc.kind != "SIMULATED" or acc.status != "OPEN":
        issues.append({"code": "ACCOUNT_NOT_USABLE", "blocking": True, "message": "Compte débité inutilisable"})
    if batch.execution_date < clock.today():
        issues.append({"code": "EXECUTION_DATE_PAST", "blocking": True, "message": "Date d'exécution passée"})
    for p in payments_of(db, batch):
        if p.status == "CANCELLED":
            continue
        b = db.get(Beneficiary, p.beneficiary_id)
        cur = db.get(BeneficiaryVersion, b.current_version_id)
        if cur.review_status == "PENDING" and b.approved_version_id is not None and b.status != "SUSPENDED":
            issues.append({"code": "BENEFICIARY_CHANGE_PENDING", "blocking": True, "line": p.line_no,
                           "payment_id": str(p.id), "beneficiary_id": str(b.id),
                           "message": f"Modification de « {cur.name} » en attente de revue"})
            continue
        if b.status != "ACTIVE" or b.approved_version_id is None:
            issues.append({"code": "BENEFICIARY_NOT_APPROVED", "blocking": True, "line": p.line_no,
                           "payment_id": str(p.id), "beneficiary_id": str(b.id),
                           "message": f"Bénéficiaire « {cur.name} » : {b.status} — revue requise"})
            continue
    available = ledger.booked_balance(db, acc.id) - ledger.reserved_amount(db, acc.id)
    if available < batch.total_minor:
        issues.append({"code": "FUNDS_INSUFFICIENT_INDICATIVE", "blocking": False,
                       "message": f"Disponible indicatif {fmt(available, acc.currency)} < total du lot ; "
                                  "les fonds seront revérifiés à l'approbation finale et avant exécution"})
    return issues


def _repin_to_approved(db, batch: PaymentBatch) -> bool:
    changed = False
    for p in payments_of(db, batch):
        if p.status == "CANCELLED":
            continue
        b = db.get(Beneficiary, p.beneficiary_id)
        if b.approved_version_id and p.beneficiary_version_id != b.approved_version_id:
            p.beneficiary_version_id = b.approved_version_id
            changed = True
    return changed


def submit_for_approval(db: Session, principal, batch_id: uuid.UUID, expected_version: int) -> PaymentBatch:
    batch = get_batch(db, principal, batch_id, lock=True)
    principal.require("payment.prepare", batch.entity_id, batch.debtor_account_id)
    if batch.status not in ("DRAFT", "TO_REVIEW"):
        raise Conflict("INVALID_TRANSITION", f"Soumission impossible depuis l'état {batch.status}")
    if expected_version != batch.version:
        raise Conflict("VERSION_MISMATCH", "Version obsolète", {"current_version": batch.version})
    if _repin_to_approved(db, batch):
        batch.version += 1  # la version figée du bénéficiaire fait partie du contenu approuvé
    issues = validate_batch(db, batch)
    batch.validation_issues = issues
    blocking = [i for i in issues if i["blocking"]]
    target = "TO_REVIEW" if blocking else "PENDING_APPROVAL"
    if not blocking:
        rule = approvals.select_policy(db, batch)
        batch.policy_rule_id = rule.id
        batch.required_approvals = rule.required_approvals
        batch.submitted_for_approval_at = clock.now()
    reason = "; ".join(i["message"] for i in blocking) if blocking else None
    for p in payments_of(db, batch):
        if p.status in ("DRAFT", "TO_REVIEW"):
            set_payment_status(db, batch, p, target, actor=principal.user_id, reason=reason)
    set_batch_status(db, batch, target, actor=principal.user_id, reason=reason)
    db.flush()
    principal.audit("payment_batch.submitted_for_approval", "payment_batch", batch.id, entity_id=batch.entity_id,
                    details={"version": batch.version, "status": target, "issues": issues,
                             "required_approvals": batch.required_approvals})
    return batch


# ---------------------------------------------------------------- approbation

def finalize_approval(db: Session, principal, batch: PaymentBatch) -> None:
    """Quorum atteint : réservation des fonds (verrou du compte), puis
    Approuvé → Planifié (date future) ou mise en file d'exécution."""
    acc = db.get(BankAccount, batch.debtor_account_id, with_for_update=True)
    available = ledger.booked_balance(db, acc.id) - ledger.reserved_amount(db, acc.id)
    if available < batch.total_minor:
        raise Conflict("INSUFFICIENT_FUNDS",
                       "Fonds disponibles insuffisants pour réserver le lot : approbation non enregistrée",
                       {"available": money(available, acc.currency), "required": money(batch.total_minor, acc.currency)})
    ps = [p for p in payments_of(db, batch) if p.status == "PENDING_APPROVAL"]
    for p in ps:
        ledger.reserve(db, batch.organization_id, acc.id, p.amount_minor, p.currency, "payment", str(p.id))
    batch.approved_version = batch.version
    batch.approved_at = clock.now()
    for p in ps:
        set_payment_status(db, batch, p, "APPROVED", actor=principal.user_id, source="USER", reason="Quorum atteint")
    set_batch_status(db, batch, "APPROVED", actor=principal.user_id, reason="Quorum d'approbation atteint")
    if batch.execution_date > clock.today():
        for p in ps:
            set_payment_status(db, batch, p, "SCHEDULED", source="WORKER", reason=f"Exécution prévue le {batch.execution_date}")
        set_batch_status(db, batch, "SCHEDULED", source="WORKER", reason=f"Exécution prévue le {batch.execution_date}")
    else:
        queue.enqueue(db, "execute_batch", {"batch_id": str(batch.id), "version": batch.version},
                      f"execute_batch:{batch.id}:{batch.version}", organization_id=batch.organization_id)
    db.flush()
    principal.audit("payment_batch.approved", "payment_batch", batch.id, entity_id=batch.entity_id,
                    details={"version": batch.version, "reserved": fmt(batch.total_minor, batch.currency),
                             "status": batch.status})


def reject_at_approval(db: Session, principal, batch: PaymentBatch, reason: str) -> None:
    for p in payments_of(db, batch):
        if p.status not in state.FINAL:
            set_payment_status(db, batch, p, "CANCELLED", actor=principal.user_id, reason=f"Refusé à l'approbation : {reason}")
    set_batch_status(db, batch, "REJECTED", actor=principal.user_id, reason=reason)
    db.flush()


def cancel_batch(db: Session, principal, batch_id: uuid.UUID, reason: str) -> PaymentBatch:
    batch = get_batch(db, principal, batch_id, lock=True)
    principal.require("payment.cancel", batch.entity_id, batch.debtor_account_id)
    if batch.status not in state.CANCELLABLE:
        raise Conflict("NOT_CANCELLABLE",
                       f"Annulation impossible à l'état {batch.status} : le lot a été transmis au système destinataire "
                       "(un rappel de fonds serait nécessaire — fonction reportée)", {"status": batch.status})
    for p in payments_of(db, batch):
        if p.status in state.FINAL:
            continue
        ledger.close_reservation(db, "payment", str(p.id), "RELEASED", f"Annulation : {reason}")
        set_payment_status(db, batch, p, "CANCELLED", actor=principal.user_id, reason=reason)
    approvals.invalidate(db, batch, f"Lot annulé : {reason}")
    set_batch_status(db, batch, "CANCELLED", actor=principal.user_id, reason=reason)
    db.flush()
    principal.audit("payment_batch.cancelled", "payment_batch", batch.id, entity_id=batch.entity_id,
                    details={"reason": reason})
    return batch


# ------------------------------------------- effets des changements de bénéficiaire

def on_beneficiary_material_change(db: Session, principal, b: Beneficiary, reason: str) -> list[str]:
    affected = []
    ps = db.scalars(select(Payment).where(Payment.beneficiary_id == b.id,
                                          Payment.status.in_(("PENDING_APPROVAL", "APPROVED", "SCHEDULED")))).all()
    for batch_id in {p.batch_id for p in ps}:
        batch = db.get(PaymentBatch, batch_id, with_for_update=True)
        n = approvals.invalidate(db, batch, reason)
        for p in payments_of(db, batch):
            if p.status in ("APPROVED", "SCHEDULED"):
                ledger.close_reservation(db, "payment", str(p.id), "RELEASED", reason)
            if p.status in ("PENDING_APPROVAL", "APPROVED", "SCHEDULED"):
                set_payment_status(db, batch, p, "TO_REVIEW", actor=principal.user_id, reason=reason)
        batch.approved_version = None
        set_batch_status(db, batch, "TO_REVIEW", actor=principal.user_id, reason=reason)
        affected.append(batch.reference)
        principal.audit("payment_batch.approvals_invalidated", "payment_batch", batch.id, entity_id=batch.entity_id,
                        details={"reason": reason, "invalidated": n})
    db.flush()
    return affected


def repin_minor_version(db: Session, b: Beneficiary, v: BeneficiaryVersion) -> None:
    for p in db.scalars(select(Payment).where(Payment.beneficiary_id == b.id, Payment.status.in_(("DRAFT", "TO_REVIEW")))):
        p.beneficiary_version_id = v.id


def repin_after_beneficiary_approval(db: Session, b: Beneficiary, v: BeneficiaryVersion) -> None:
    """Après validation d'une nouvelle version, les lots en préparation sont
    repointés (nouvelle version de lot) ; ils doivent être re-soumis."""
    for p in db.scalars(select(Payment).where(Payment.beneficiary_id == b.id, Payment.status.in_(("DRAFT", "TO_REVIEW")))):
        if p.beneficiary_version_id != v.id:
            p.beneficiary_version_id = v.id
            batch = db.get(PaymentBatch, p.batch_id)
            batch.version += 1
    db.flush()


def material_signature(v: BeneficiaryVersion) -> tuple:
    return tuple(getattr(v, f) for f in MATERIAL_FIELDS)


# ------------------------------------------------------------------ rejets

def resolve_rejection(db: Session, principal, payment_id: uuid.UUID, resolution: str) -> Payment:
    p = db.get(Payment, payment_id, with_for_update=True)
    if p is None or p.organization_id != principal.org_id:
        raise NotFound("Paiement", payment_id)
    principal.require("payment.prepare", p.entity_id, p.debtor_account_id)
    if p.status != "REJECTED":
        raise Conflict("NOT_REJECTED", "Seul un paiement rejeté peut faire l'objet d'un traitement de rejet")
    if p.rejection_resolved_at:
        raise Conflict("ALREADY_RESOLVED", "Rejet déjà traité")
    if not resolution or len(resolution.strip()) < 10:
        raise DomainError("RESOLUTION_REQUIRED", "Justification du traitement requise (10 caractères minimum)", 422)
    p.rejection_resolution = resolution.strip()
    p.rejection_resolved_by = principal.user_id
    p.rejection_resolved_at = clock.now()
    db.flush()
    principal.audit("payment.rejection_resolved", "payment", p.id, entity_id=p.entity_id, details={"resolution": resolution})
    return p


# -------------------------------------------------------------- sérialisation

REJECTION_CODES = {
    "AC04": "Compte du bénéficiaire clôturé",
    "AC01": "Numéro de compte incorrect",
    "AM02": "Montant non autorisé",
    "AG01": "Opération interdite sur ce compte",
    "MS03": "Motif non précisé par le destinataire",
}


def _uname(db, uid):
    u = db.get(User, uid) if uid else None
    return u.full_name if u else None


def serialize_payment(db: Session, p: Payment, with_events: bool = False) -> dict:
    v = db.get(BeneficiaryVersion, p.beneficiary_version_id)
    b = db.get(Beneficiary, p.beneficiary_id)
    batch = db.get(PaymentBatch, p.batch_id)
    out = {
        "id": str(p.id), "batch_id": str(p.batch_id), "batch_reference": batch.reference, "batch_label": batch.label,
        "line_no": p.line_no, "entity_id": str(p.entity_id),
        "entity_name": db.get(LegalEntity, p.entity_id).name,
        "debtor_account_id": str(p.debtor_account_id),
        "beneficiary": {"id": str(b.id), "status": b.status, "pinned_version_id": str(v.id),
                        "pinned_version_no": v.version_no, "name": v.name, "iban": v.iban, "bic": v.bic,
                        "pinned_is_current_approved": b.approved_version_id == v.id},
        "amount": money(p.amount_minor, p.currency), "execution_date": p.execution_date.isoformat(),
        "remittance_info": p.remittance_info, "end_to_end_id": p.end_to_end_id,
        "status": p.status, "status_label": state.PAYMENT_LABELS[p.status], "status_reason": p.status_reason,
        "submission_key": p.submission_key, "submission_attempts": p.submission_attempts,
        "bank_reference": p.bank_reference,
        "technical_ack_at": p.technical_ack_at.isoformat() if p.technical_ack_at else None,
        "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
        "accepted_at": p.accepted_at.isoformat() if p.accepted_at else None,
        "executed_at": p.executed_at.isoformat() if p.executed_at else None,
        "rejected_at": p.rejected_at.isoformat() if p.rejected_at else None,
        "rejection_code": p.rejection_code,
        "rejection_label": REJECTION_CODES.get(p.rejection_code or "", p.rejection_code),
        "rejection_resolution": p.rejection_resolution,
        "rejection_resolved_by": _uname(db, p.rejection_resolved_by),
        "unknown_since": p.unknown_since.isoformat() if p.unknown_since else None,
        "ledger_entry_id": str(p.ledger_entry_id) if p.ledger_entry_id else None,
        "returned": money(p.returned_minor, p.currency) if p.returned_minor else None,
        "created_by": _uname(db, p.created_by), "created_at": p.created_at.isoformat(),
        "settlement_note": "« Exécuté » n'est affiché qu'après confirmation de règlement du système destinataire ; "
                           "la réception technique seule ne le prouve pas.",
    }
    if with_events:
        evs = db.scalars(select(PaymentEvent).where(PaymentEvent.payment_id == p.id).order_by(PaymentEvent.created_at)).all()
        out["events"] = [serialize_event(db, e) for e in evs]
    return out


def serialize_event(db, e: PaymentEvent) -> dict:
    label = state.PAYMENT_LABELS.get(e.to_status) or state.BATCH_LABELS.get(e.to_status)
    if e.from_status == e.to_status == "SUBMITTED":
        label = "Réception technique"
    elif e.from_status == e.to_status == "EXECUTED":
        label = "Retour de fonds"
    return {"at": e.created_at.isoformat(), "from": e.from_status, "to": e.to_status, "to_label": label,
            "actor": _uname(db, e.actor_user_id), "source": e.source, "reason": e.reason,
            "batch_version": e.batch_version, "payment_id": str(e.payment_id) if e.payment_id else None}


def serialize_batch(db: Session, batch: PaymentBatch, detail: bool = False) -> dict:
    ps = payments_of(db, batch)
    counts: dict[str, int] = {}
    for p in ps:
        counts[p.status] = counts.get(p.status, 0) + 1
    valid = approvals.valid_approvals(db, batch) if batch.status == "PENDING_APPROVAL" else []
    acc = db.get(BankAccount, batch.debtor_account_id)
    out = {
        "id": str(batch.id), "reference": batch.reference, "kind": batch.kind, "kind_label": KINDS[batch.kind],
        "label": batch.label, "status": batch.status, "status_label": state.BATCH_LABELS[batch.status],
        "status_reason": batch.status_reason, "version": batch.version, "approved_version": batch.approved_version,
        "entity": {"id": str(batch.entity_id), "name": db.get(LegalEntity, batch.entity_id).name},
        "debtor_account": {"id": str(acc.id), "name": acc.name, "iban": acc.iban},
        "total": money(batch.total_minor, batch.currency), "payment_count": batch.payment_count,
        "execution_date": batch.execution_date.isoformat(), "required_approvals": batch.required_approvals,
        "valid_approvals": len({a.approver_user_id for a in valid}),
        "created_by": _uname(db, batch.created_by), "created_by_id": str(batch.created_by),
        "created_at": batch.created_at.isoformat(),
        "approved_at": batch.approved_at.isoformat() if batch.approved_at else None,
        "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
        "status_counts": counts, "validation_issues": batch.validation_issues,
        "source_filename": batch.source_filename,
    }
    if detail:
        out["payments"] = [serialize_payment(db, p) for p in ps]
        aps = db.scalars(select(Approval).where(Approval.batch_id == batch.id).order_by(Approval.created_at)).all()
        out["approvals"] = [approvals.serialize(db, a, batch.version) for a in aps]
        if batch.status == "PENDING_APPROVAL":
            out["eligible_approvers"] = approvals.eligible_approvers(db, batch)
        evs = db.scalars(select(PaymentEvent).where(PaymentEvent.batch_id == batch.id, PaymentEvent.payment_id.is_(None))
                         .order_by(PaymentEvent.created_at)).all()
        out["events"] = [serialize_event(db, e) for e in evs]
        out["transitions"] = sorted(state.BATCH_TRANSITIONS[batch.status])
    return out
