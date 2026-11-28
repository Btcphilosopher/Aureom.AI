"""Exécution simulée, événements du système destinataire et résultats inconnus.

Garanties :
* revérification complète avant soumission (version, approbations, droits,
  bénéficiaire, réservation des fonds) ;
* clé d'idempotence par paiement (``submission_key``) transmise au destinataire ;
* boîte de réception d'événements dédupliquée (event_id unique) ET écritures
  comptables idempotentes (une seule écriture d'exécution par paiement) :
  un événement dupliqué ne peut pas débiter deux fois ;
* résultat inconnu → recherche de l'ordre chez le destinataire avant toute
  nouvelle soumission (avec la même clé d'idempotence).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.config import get_settings
from horizon.core.crypto import hmac_hex
from horizon.core.db import SessionLocal
from horizon.core.errors import DomainError
from horizon.modules.accounts.models import BankAccount
from horizon.modules.approvals import service as approvals
from horizon.modules.approvals.models import Approval
from horizon.modules.audit import service as audit
from horizon.modules.beneficiaries.models import Beneficiary, BeneficiaryVersion
from horizon.modules.integrations.bank_simulator import bank
from horizon.modules.integrations.gateway import GatewayRejected, GatewayTimeout
from horizon.modules.jobs import queue
from horizon.modules.ledger import service as ledger
from horizon.modules.ledger.models import Reservation
from horizon.modules.payments import state
from horizon.modules.payments.models import BankEventInbox, Payment, PaymentBatch, PaymentReturn
from horizon.modules.payments.service import (
    log_event,
    material_signature,
    payments_of,
    set_batch_status,
    set_payment_status,
)

log = logging.getLogger("horizon.execution")
gateway = bank  # adaptateur PaymentGateway (simulateur)


def _system_audit(db, org_id, action, obj_type, obj_id, entity_id=None, details=None, outcome="SUCCESS"):
    audit.record(db, organization_id=org_id, actor_user_id=None, actor_label="Système HORIZON (travailleur)",
                 action=action, object_type=obj_type, object_id=obj_id, entity_id=entity_id, details=details,
                 outcome=outcome)


# ------------------------------------------------------------ pré-contrôles

def pre_execution_checks(db: Session, batch: PaymentBatch) -> list[str]:
    problems: list[str] = []
    if batch.approved_version != batch.version:
        problems.append("Version du lot différente de la version approuvée")
    aps = db.scalars(select(Approval).where(Approval.batch_id == batch.id, Approval.batch_version == batch.version,
                                            Approval.decision == "APPROVE", Approval.invalidated_at.is_(None))).all()
    still_valid = set()
    for a in aps:
        if batch.approved_at and a.expires_at <= batch.approved_at:
            continue  # expirée avant l'atteinte du quorum
        if approvals.authority(db, a.approver_user_id, batch) is None:
            a.invalidated_at = clock.now()
            a.invalidation_reason = "Droit d'approbation retiré avant exécution"
            continue
        still_valid.add(a.approver_user_id)
    if len(still_valid) < (batch.required_approvals or 1):
        problems.append(f"Approbations valides insuffisantes ({len(still_valid)}/{batch.required_approvals})")
    for p in payments_of(db, batch):
        if p.status not in ("APPROVED", "SCHEDULED"):
            continue
        b = db.get(Beneficiary, p.beneficiary_id)
        pinned = db.get(BeneficiaryVersion, p.beneficiary_version_id)
        approved = db.get(BeneficiaryVersion, b.approved_version_id) if b.approved_version_id else None
        if b.status != "ACTIVE" or approved is None or material_signature(pinned) != material_signature(approved):
            problems.append(f"Ligne {p.line_no} : bénéficiaire modifié, suspendu ou non approuvé")
        r = db.scalar(select(Reservation).where(Reservation.reference_type == "payment",
                                                Reservation.reference_id == str(p.id), Reservation.status == "ACTIVE"))
        if r is None or r.amount_minor != p.amount_minor:
            problems.append(f"Ligne {p.line_no} : réservation de fonds absente ou incohérente")
    acc = db.get(BankAccount, batch.debtor_account_id)
    if acc.status != "OPEN":
        problems.append("Compte débité fermé")
    return problems


@queue.handler("execute_batch")
def execute_batch(db: Session, payload: dict) -> None:
    batch = db.get(PaymentBatch, uuid.UUID(payload["batch_id"]), with_for_update=True)
    if batch is None or batch.status not in ("APPROVED", "SCHEDULED"):
        db.commit()
        return
    if batch.execution_date > clock.today():
        db.commit()
        return
    problems = pre_execution_checks(db, batch)
    if problems:
        reason = "Contrôle avant exécution : " + " ; ".join(problems)
        approvals.invalidate(db, batch, reason)
        for p in payments_of(db, batch):
            if p.status in ("APPROVED", "SCHEDULED"):
                ledger.close_reservation(db, "payment", str(p.id), "RELEASED", reason)
                set_payment_status(db, batch, p, "TO_REVIEW", source="WORKER", reason=reason)
        batch.approved_version = None
        set_batch_status(db, batch, "TO_REVIEW", source="WORKER", reason=reason)
        _system_audit(db, batch.organization_id, "payment_batch.execution_blocked", "payment_batch", batch.id,
                      batch.entity_id, {"problems": problems}, outcome="FAILED")
        db.commit()
        return
    batch.processing_started_at = clock.now()
    set_batch_status(db, batch, "PROCESSING", source="WORKER", reason="Contrôles avant exécution satisfaits")
    for p in payments_of(db, batch):
        if p.status in ("APPROVED", "SCHEDULED"):
            set_payment_status(db, batch, p, "SUBMITTED", source="WORKER", reason="Transmission au système destinataire")
            p.submitted_at = clock.now()
            p.submission_attempts += 1
            queue.enqueue(db, "submit_payment", {"payment_id": str(p.id)}, f"submit_payment:{p.id}:{p.submission_attempts}",
                          organization_id=batch.organization_id)
    _system_audit(db, batch.organization_id, "payment_batch.execution_started", "payment_batch", batch.id, batch.entity_id,
                  {"version": batch.version})
    db.commit()


def _order(db: Session, p: Payment) -> dict:
    acc = db.get(BankAccount, p.debtor_account_id)
    v = db.get(BeneficiaryVersion, p.beneficiary_version_id)
    return {"submission_key": p.submission_key, "end_to_end_id": p.end_to_end_id, "debtor_iban": acc.iban,
            "creditor_iban": v.iban, "creditor_name": v.name, "amount_minor": p.amount_minor, "currency": p.currency,
            "execution_date": p.execution_date.isoformat(), "remittance_info": p.remittance_info}


def mark_unknown(db: Session, batch: PaymentBatch, p: Payment, reason: str) -> None:
    from horizon.modules.reconciliation.service import open_case

    set_payment_status(db, batch, p, "UNKNOWN", source="WORKER", reason=reason)
    p.unknown_since = clock.now()
    open_case(db, organization_id=p.organization_id, entity_id=p.entity_id, account_id=p.debtor_account_id,
              kind="UNKNOWN_PAYMENT_RESULT", external_ref=p.submission_key,
              description=f"Résultat inconnu pour {p.end_to_end_id} : recherche de l'ordre chez le destinataire en cours",
              payment_id=p.id, ledger_minor=p.amount_minor, currency=p.currency)
    queue.enqueue(db, "reconcile_unknown", {"payment_id": str(p.id)}, f"reconcile_unknown:{p.id}:{p.submission_attempts}",
                  organization_id=p.organization_id)


@queue.handler("submit_payment")
def submit_payment(db: Session, payload: dict) -> None:
    p = db.get(Payment, uuid.UUID(payload["payment_id"]), with_for_update=True)
    if p is None or p.status != "SUBMITTED" or p.technical_ack_at is not None:
        db.commit()
        return
    batch = db.get(PaymentBatch, p.batch_id)
    try:
        ack = gateway.submit(_order(db, p))
    except GatewayTimeout as exc:
        mark_unknown(db, batch, p, f"Aucune réponse exploitable du destinataire : {exc}")
        _system_audit(db, p.organization_id, "payment.result_unknown", "payment", p.id, p.entity_id, {"error": str(exc)},
                      outcome="FAILED")
        db.commit()
        return
    except GatewayRejected as rej:
        _reject(db, batch, p, rej.code, f"Rejet synchrone : {rej}")
        db.commit()
        return
    p.technical_ack_at = ack.received_at
    p.bank_reference = ack.bank_reference
    log_event(db, batch, "SUBMITTED", payment=p, from_status="SUBMITTED", source="WORKER",
              reason=f"Réception technique HTTP {ack.http_status} (ne vaut pas acceptation ni règlement)")
    queue.enqueue(db, "sim_process", {}, f"sim_process:{uuid.uuid4()}")
    db.commit()


@queue.handler("reconcile_unknown")
def reconcile_unknown(db: Session, payload: dict) -> None:
    """Recherche l'opération avant toute nouvelle soumission."""
    from horizon.modules.reconciliation.service import resolve_case_by_ref

    p = db.get(Payment, uuid.UUID(payload["payment_id"]), with_for_update=True)
    if p is None or p.status != "UNKNOWN":
        db.commit()
        return
    batch = db.get(PaymentBatch, p.batch_id)
    found = gateway.find(p.submission_key)
    if found is None:
        set_payment_status(db, batch, p, "SUBMITTED", source="RECONCILIATION",
                           reason="Recherche effectuée : ordre introuvable chez le destinataire → nouvelle soumission "
                                  "avec la même clé d'idempotence")
        p.submission_attempts += 1
        p.unknown_since = None
        queue.enqueue(db, "submit_payment", {"payment_id": str(p.id)}, f"submit_payment:{p.id}:{p.submission_attempts}",
                      organization_id=p.organization_id)
        resolve_case_by_ref(db, p.debtor_account_id, "UNKNOWN_PAYMENT_RESULT", p.submission_key, "AUTO_NOT_FOUND_RESUBMITTED",
                            "Ordre introuvable : nouvelle soumission idempotente")
        db.commit()
        return
    p.bank_reference = found.bank_reference
    p.technical_ack_at = p.technical_ack_at or clock.now()
    reason = f"Recherche effectuée : ordre retrouvé chez le destinataire (état {found.status}) — aucune nouvelle soumission"
    p.unknown_since = None
    if found.status == "RECEIVED":
        set_payment_status(db, batch, p, "SUBMITTED", source="RECONCILIATION", reason=reason)
        queue.enqueue(db, "sim_process", {}, f"sim_process:{uuid.uuid4()}")
    elif found.status == "ACCEPTED":
        set_payment_status(db, batch, p, "ACCEPTED", source="RECONCILIATION", reason=reason)
        p.accepted_at = clock.now()
        queue.enqueue(db, "sim_process", {}, f"sim_process:{uuid.uuid4()}")
    elif found.status in ("SETTLED", "RETURNED"):
        _execute(db, batch, p, reason)
    elif found.status == "REJECTED":
        _reject(db, batch, p, found.rejection_code or "MS03", reason)
    resolve_case_by_ref(db, p.debtor_account_id, "UNKNOWN_PAYMENT_RESULT", p.submission_key, "AUTO_FOUND",
                        f"Ordre retrouvé ({found.status}) — aucune double soumission")
    _system_audit(db, p.organization_id, "payment.unknown_resolved", "payment", p.id, p.entity_id,
                  {"found": found.status if found else None})
    db.commit()


@queue.handler("recover_stale_submissions")
def recover_stale_submissions(db: Session, payload: dict) -> None:
    """Reprise après interruption : paiement SOUMIS sans réception technique
    depuis plus de 5 minutes → résultat inconnu → recherche."""
    limit = clock.now() - timedelta(minutes=5)
    for p in db.scalars(select(Payment).where(Payment.status == "SUBMITTED", Payment.technical_ack_at.is_(None),
                                              Payment.submitted_at < limit).with_for_update(skip_locked=True)):
        mark_unknown(db, db.get(PaymentBatch, p.batch_id), p, "Soumission interrompue (aucune réception technique)")
    db.commit()


@queue.handler("run_scheduled")
def run_scheduled(db: Session, payload: dict) -> None:
    for b in db.scalars(select(PaymentBatch).where(PaymentBatch.status == "SCHEDULED",
                                                   PaymentBatch.execution_date <= clock.today())):
        queue.enqueue(db, "execute_batch", {"batch_id": str(b.id), "version": b.version},
                      f"execute_batch:{b.id}:{b.version}:{clock.today()}", organization_id=b.organization_id)
    db.commit()


# ------------------------------------------------------- effets métier

def refresh_batch_completion(db: Session, batch: PaymentBatch) -> None:
    ps = payments_of(db, batch)
    if batch.status == "PROCESSING" and all(p.status in state.FINAL for p in ps):
        batch.completed_at = clock.now()
        counts = {s: sum(1 for p in ps if p.status == s) for s in ("EXECUTED", "REJECTED", "CANCELLED")}
        set_batch_status(db, batch, "COMPLETED", source="WORKER",
                         reason=f"{counts['EXECUTED']} exécuté(s), {counts['REJECTED']} rejeté(s)")
        _realize_financing(db, batch)


def _realize_financing(db, batch):
    from horizon.modules.financing.models import FinancingInstallment

    inst = db.scalar(select(FinancingInstallment).where(FinancingInstallment.payment_batch_id == batch.id))
    if inst is not None and all(p.status == "EXECUTED" for p in payments_of(db, batch)):
        inst.status = "PAID"


def _realize_forecast(db, p: Payment, batch: PaymentBatch):
    from horizon.modules.forecasting.models import RecurringRealization

    for ref in {p.forecast_ref, batch.forecast_ref} - {None}:
        if ref.startswith("recurring:"):
            _, aid, d = ref.split(":")
            from datetime import date as _d

            exists = db.scalar(select(RecurringRealization).where(RecurringRealization.assumption_id == uuid.UUID(aid),
                                                                  RecurringRealization.occurrence_date == _d.fromisoformat(d)))
            if exists is None:
                db.add(RecurringRealization(assumption_id=uuid.UUID(aid), occurrence_date=_d.fromisoformat(d),
                                            realized_by_type="payment", realized_by_id=str(p.id)))


def _execute(db: Session, batch: PaymentBatch, p: Payment, reason: str) -> bool:
    """Exécuté selon confirmation : consomme la réservation et comptabilise UNE fois."""
    if p.status == "EXECUTED":
        return False
    set_payment_status(db, batch, p, "EXECUTED", source="BANK_EVENT", reason=reason)
    p.executed_at = clock.now()
    v = db.get(BeneficiaryVersion, p.beneficiary_version_id)
    cp = ledger.purpose_gl(db, p.organization_id, p.entity_id, "COUNTERPARTY_OUT", p.currency)
    bank_gl = ledger.bank_gl(db, p.debtor_account_id)
    entry, created = ledger.post_entry(
        db, org_id=p.organization_id, entity_id=p.entity_id, journal="PAI",
        description=f"{batch.reference} — {v.name} — {p.remittance_info}"[:500],
        lines=[ledger.Line(cp.id, p.currency, debit=p.amount_minor), ledger.Line(bank_gl.id, p.currency, credit=p.amount_minor)],
        idempotency_key=f"payment-execution:{p.id}", reference_type="payment", reference_id=str(p.id),
    )
    p.ledger_entry_id = entry.id
    ledger.close_reservation(db, "payment", str(p.id), "CONSUMED", "Règlement confirmé")
    _realize_forecast(db, p, batch)
    refresh_batch_completion(db, batch)
    return created


def _reject(db: Session, batch: PaymentBatch, p: Payment, code: str, reason: str) -> None:
    if p.status == "REJECTED":
        return
    set_payment_status(db, batch, p, "REJECTED", source="BANK_EVENT", reason=reason)
    p.rejected_at = clock.now()
    p.rejection_code = code
    ledger.close_reservation(db, "payment", str(p.id), "RELEASED", f"Rejet {code}")
    refresh_batch_completion(db, batch)


def verify_signature(body: bytes, signature: str | None) -> bool:
    import hmac as _h

    expected = "sha256=" + hmac_hex(get_settings().simulator_webhook_secret, body)
    return signature is not None and _h.compare_digest(expected, signature)


def ingest_bank_event(db: Session, body: bytes, signature: str | None) -> dict:
    """Point d'entrée des événements du destinataire (webhook signé)."""
    if not verify_signature(body, signature):
        audit.record_independent(organization_id=None, actor_user_id=None, actor_label="webhook",
                                 action="bank_event.signature_invalid", outcome="DENIED")
        raise DomainError("INVALID_SIGNATURE", "Signature d'événement invalide", 401)
    payload = json.loads(body)
    event_id = payload["event_id"]
    existing = db.scalar(select(BankEventInbox).where(BankEventInbox.event_id == event_id).with_for_update())
    if existing is not None:
        existing.duplicate_deliveries += 1
        db.flush()
        return {"event_id": event_id, "outcome": "DUPLICATE_IGNORED", "duplicate_deliveries": existing.duplicate_deliveries}
    inbox = BankEventInbox(event_id=event_id, event_type=payload["event_type"], payload=payload)
    db.add(inbox)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"event_id": event_id, "outcome": "DUPLICATE_IGNORED"}
    inbox.outcome = apply_event(db, payload)
    inbox.processed_at = clock.now()
    db.flush()
    return {"event_id": event_id, "outcome": inbox.outcome}


def apply_event(db: Session, ev: dict) -> str:
    et = ev["event_type"]
    if et == "INCOMING_CREDIT":
        return _incoming_credit(db, ev)
    p = db.scalar(select(Payment).where(Payment.submission_key == ev["submission_key"]).with_for_update())
    if p is None:
        return "UNMATCHED"
    batch = db.get(PaymentBatch, p.batch_id)
    if et == "PAYMENT_ACCEPTED":
        if p.status in ("SUBMITTED", "UNKNOWN"):
            set_payment_status(db, batch, p, "ACCEPTED", source="BANK_EVENT", reason="Accepté par le système destinataire")
            p.accepted_at = clock.now()
            p.bank_reference = ev.get("bank_reference")
            p.technical_ack_at = p.technical_ack_at or clock.now()
            p.unknown_since = None
            return "APPLIED"
        return "IGNORED_STALE"
    if et == "PAYMENT_SETTLED":
        if p.status in ("SUBMITTED", "ACCEPTED", "UNKNOWN"):
            _execute(db, batch, p, "Règlement confirmé par le système destinataire")
            return "APPLIED"
        return "IGNORED_ALREADY_FINAL"
    if et == "PAYMENT_REJECTED":
        if p.status in ("SUBMITTED", "ACCEPTED", "UNKNOWN"):
            _reject(db, batch, p, ev.get("reason_code", "MS03"), f"Rejeté par le système destinataire ({ev.get('reason_code')})")
            return "APPLIED"
        return "IGNORED_ALREADY_FINAL"
    if et == "PAYMENT_RETURNED":
        if p.status != "EXECUTED":
            return "IGNORED_NOT_EXECUTED"
        amt = int(ev["amount_minor"])
        cp = ledger.purpose_gl(db, p.organization_id, p.entity_id, "COUNTERPARTY_OUT", p.currency)
        entry, created = ledger.post_entry(
            db, org_id=p.organization_id, entity_id=p.entity_id, journal="RET",
            description=f"Retour de fonds {p.end_to_end_id} ({ev.get('reason_code')})",
            lines=[ledger.Line(ledger.bank_gl(db, p.debtor_account_id).id, p.currency, debit=amt),
                   ledger.Line(cp.id, p.currency, credit=amt)],
            idempotency_key=f"payment-return:{ev['event_id']}", reference_type="payment", reference_id=str(p.id),
        )
        if created:
            db.add(PaymentReturn(organization_id=p.organization_id, payment_id=p.id, amount_minor=amt, currency=p.currency,
                                 reason_code=ev.get("reason_code", ""), bank_event_id=ev["event_id"], ledger_entry_id=entry.id))
            p.returned_minor += amt
            log_event(db, batch, "EXECUTED", payment=p, from_status="EXECUTED", source="BANK_EVENT",
                      reason=f"Retour de fonds reçu ({ev.get('reason_code')})")
        return "APPLIED"
    return "UNSUPPORTED"


def _incoming_credit(db: Session, ev: dict) -> str:
    from horizon.modules.forecasting.models import ExpectedReceipt

    acc = db.scalar(select(BankAccount).where(BankAccount.iban == ev["account_iban"]))
    if acc is None or acc.kind != "SIMULATED":
        return "UNMATCHED"
    amt = int(ev["amount_minor"])
    cp = ledger.purpose_gl(db, acc.organization_id, acc.entity_id, "COUNTERPARTY_IN", acc.currency)
    entry, _ = ledger.post_entry(
        db, org_id=acc.organization_id, entity_id=acc.entity_id, journal="ENC",
        description=f"Encaissement {ev.get('payer')} — {ev.get('reference')}",
        lines=[ledger.Line(ledger.bank_gl(db, acc.id).id, acc.currency, debit=amt), ledger.Line(cp.id, acc.currency, credit=amt)],
        idempotency_key=f"incoming:{ev['event_id']}", reference_type="incoming_credit", reference_id=ev.get("bank_reference"),
    )
    # Rapprochement avec l'encaissement attendu → il sort de la prévision (pas de double comptage).
    er = db.scalar(select(ExpectedReceipt).where(ExpectedReceipt.account_id == acc.id, ExpectedReceipt.status == "EXPECTED",
                                                 ExpectedReceipt.reference == ev.get("reference")))
    if er is not None:
        er.status = "RECEIVED"
        er.matched_entry_id = entry.id
    return "APPLIED"


# ---------------------------------------------------- tâches du simulateur

@queue.handler("sim_process")
def sim_process(db: Session, payload: dict) -> None:
    """Fait avancer le système destinataire fictif puis livre ses événements."""
    bank.process_pending()
    deliver_pending_events()
    # deuxième passe : ACCEPTED → SETTLED
    bank.process_pending()
    deliver_pending_events()
    db.commit()


def deliver_pending_events() -> list[dict]:
    results = []
    for event_id, body, sig in bank.pending_events():
        with SessionLocal() as s:
            res = ingest_bank_event(s, body, sig)
            s.commit()
        bank.mark_delivered(event_id)
        results.append(res)
    return results


def redeliver(event_id: str) -> dict:
    """Redélivre un événement déjà reçu (démonstration de la déduplication)."""
    eb = bank.event_body(event_id)
    if eb is None:
        raise DomainError("NOT_FOUND", "Événement inconnu du simulateur", 404)
    with SessionLocal() as s:
        res = ingest_bank_event(s, eb[0], eb[1])
        s.commit()
    bank.mark_delivered(event_id)
    return res
