"""Rapprochement relevé (système destinataire) ↔ registre HORIZON.

Clé de correspondance : référence bancaire / end-to-end + montant + devise.
Écarts ouverts en « cas » avec responsable et échéance. Accuser réception d'un
cas ne le résout pas : seule une action motivée (écriture de régularisation
liée ou justification) le clôt.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.errors import Conflict, DomainError, NotFound
from horizon.core.money import money
from horizon.modules.accounts.models import BankAccount
from horizon.modules.identity.models import User
from horizon.modules.integrations.bank_simulator import bank
from horizon.modules.ledger import service as ledger
from horizon.modules.ledger.models import JournalEntry, JournalLine
from horizon.modules.payments.models import Payment
from horizon.modules.reconciliation.models import ReconciliationCase, ReconciliationRun

KIND_LABELS = {
    "MISSING_IN_LEDGER": "Mouvement du relevé absent du registre",
    "MISSING_IN_STATEMENT": "Écriture du registre absente du relevé",
    "AMOUNT_MISMATCH": "Montants divergents",
    "UNKNOWN_PAYMENT_RESULT": "Résultat de paiement inconnu",
}
statement_provider = bank


def open_case(db: Session, *, organization_id, entity_id, account_id, kind, external_ref, description, payment_id=None,
              ledger_entry_id=None, statement_minor=None, ledger_minor=None, currency="EUR", value_date=None,
              owner_user_id=None) -> ReconciliationCase:
    c = db.scalar(select(ReconciliationCase).where(ReconciliationCase.account_id == account_id,
                                                   ReconciliationCase.kind == kind,
                                                   ReconciliationCase.external_ref == external_ref))
    if c is not None:
        if c.status == "RESOLVED" and kind == "UNKNOWN_PAYMENT_RESULT":
            c.status = "OPEN"
            c.resolution = c.resolved_at = c.resolved_by = None
            c.description = description
        return c
    c = ReconciliationCase(organization_id=organization_id, entity_id=entity_id, account_id=account_id, kind=kind,
                           external_ref=external_ref, description=description, payment_id=payment_id,
                           ledger_entry_id=ledger_entry_id, statement_minor=statement_minor, ledger_minor=ledger_minor,
                           currency=currency, value_date=value_date, owner_user_id=owner_user_id,
                           due_date=clock.today() + timedelta(days=2))
    db.add(c)
    db.flush()
    return c


def resolve_case_by_ref(db, account_id, kind, external_ref, resolution, note) -> None:
    c = db.scalar(select(ReconciliationCase).where(ReconciliationCase.account_id == account_id,
                                                   ReconciliationCase.kind == kind,
                                                   ReconciliationCase.external_ref == external_ref))
    if c is not None and c.status != "RESOLVED":
        c.status = "RESOLVED"
        c.resolution = resolution
        c.resolution_note = note
        c.resolved_at = clock.now()


def run(db: Session, account: BankAccount, since: date, owner_user_id=None) -> ReconciliationRun:
    lines = statement_provider.statement(account.iban, since)
    gl = ledger.bank_gl(db, account.id)
    matched = 0
    opened = 0
    seen_payment_ids = set()
    for ln in lines:
        entry = None
        if ln.kind == "PAYMENT":
            p = db.scalar(select(Payment).where(Payment.end_to_end_id == ln.end_to_end_id))
            if p is not None:
                seen_payment_ids.add(p.id)
                entry = db.get(JournalEntry, p.ledger_entry_id) if p.ledger_entry_id else None
                if entry is not None and -ln.amount_minor != p.amount_minor:
                    open_case(db, organization_id=account.organization_id, entity_id=account.entity_id,
                              account_id=account.id, kind="AMOUNT_MISMATCH", external_ref=ln.line_ref,
                              description=f"{ln.description} : relevé {ln.amount_minor} ≠ registre {-p.amount_minor}",
                              payment_id=p.id, ledger_entry_id=entry.id, statement_minor=ln.amount_minor,
                              ledger_minor=-p.amount_minor, currency=ln.currency, value_date=ln.booking_date,
                              owner_user_id=owner_user_id)
                    opened += 1
                    continue
        elif ln.kind in ("RETURN", "INCOMING"):
            entry = db.scalar(select(JournalEntry).join(JournalLine).where(
                JournalLine.gl_account_id == gl.id, JournalEntry.journal.in_(("RET", "ENC")),
                JournalEntry.description.contains(ln.end_to_end_id or ln.bank_reference or "~")))
            if entry is None and ln.kind == "INCOMING":
                entry = db.scalar(select(JournalEntry).where(JournalEntry.reference_id == ln.bank_reference))
        else:  # FEE ou autre : cherché par référence de régularisation
            entry = db.scalar(select(JournalEntry).where(JournalEntry.reference_type == "statement_line",
                                                         JournalEntry.reference_id == ln.line_ref))
        if entry is None:
            existing = db.scalar(select(ReconciliationCase).where(ReconciliationCase.account_id == account.id,
                                                                  ReconciliationCase.external_ref == ln.line_ref))
            if existing is None:
                open_case(db, organization_id=account.organization_id, entity_id=account.entity_id, account_id=account.id,
                          kind="MISSING_IN_LEDGER", external_ref=ln.line_ref,
                          description=f"{ln.description} ({ln.booking_date.isoformat()}) présent au relevé, absent du registre",
                          statement_minor=ln.amount_minor, currency=ln.currency, value_date=ln.booking_date,
                          owner_user_id=owner_user_id)
                opened += 1
        else:
            matched += 1
    # Paiements exécutés dans le registre mais absents du relevé
    for p in db.scalars(select(Payment).where(Payment.debtor_account_id == account.id, Payment.status == "EXECUTED",
                                              Payment.executed_at >= datetime.combine(since, time.min, tzinfo=timezone.utc))):
        if p.id not in seen_payment_ids:
            if db.scalar(select(ReconciliationCase).where(ReconciliationCase.account_id == account.id,
                                                          ReconciliationCase.external_ref == p.end_to_end_id)) is None:
                open_case(db, organization_id=account.organization_id, entity_id=account.entity_id, account_id=account.id,
                          kind="MISSING_IN_STATEMENT", external_ref=p.end_to_end_id,
                          description=f"Paiement {p.end_to_end_id} comptabilisé, absent du relevé", payment_id=p.id,
                          ledger_entry_id=p.ledger_entry_id, ledger_minor=-p.amount_minor, currency=p.currency,
                          owner_user_id=owner_user_id)
                opened += 1
    r = ReconciliationRun(organization_id=account.organization_id, account_id=account.id, statement_lines=len(lines),
                          matched=matched, cases_opened=opened, source=statement_provider.name)
    db.add(r)
    db.flush()
    return r


def get_case(db, principal, case_id) -> ReconciliationCase:
    c = db.get(ReconciliationCase, case_id, with_for_update=True)
    if c is None or c.organization_id != principal.org_id:
        raise NotFound("Cas de rapprochement", case_id)
    if not principal.authz.has("reconciliation.read", c.entity_id, c.account_id):
        raise NotFound("Cas de rapprochement", case_id)
    return c


def acknowledge(db, principal, case_id, note: str | None) -> ReconciliationCase:
    c = get_case(db, principal, case_id)
    principal.require("decision.acknowledge", c.entity_id, c.account_id)
    if c.status == "RESOLVED":
        raise Conflict("ALREADY_RESOLVED", "Cas déjà résolu")
    c.status = "ACKNOWLEDGED"  # la cause demeure : le cas reste ouvert
    c.acknowledged_by = principal.user_id
    c.acknowledged_at = clock.now()
    principal.audit("reconciliation.acknowledged", "reconciliation_case", c.id, entity_id=c.entity_id, details={"note": note})
    return c


def resolve(db, principal, case_id, action: str, note: str) -> ReconciliationCase:
    c = get_case(db, principal, case_id)
    principal.require("reconciliation.resolve", c.entity_id, c.account_id)
    principal.require_step_up()
    if c.status == "RESOLVED":
        raise Conflict("ALREADY_RESOLVED", "Cas déjà résolu")
    if not note or len(note.strip()) < 10:
        raise DomainError("NOTE_REQUIRED", "Justification requise (10 caractères minimum)", 422)
    if action == "POST_ADJUSTMENT":
        if c.kind != "MISSING_IN_LEDGER" or c.statement_minor is None:
            raise DomainError("ADJUSTMENT_NOT_APPLICABLE", "Régularisation possible uniquement pour un mouvement absent du registre", 422)
        acc = db.get(BankAccount, c.account_id)
        amt = abs(c.statement_minor)
        if c.statement_minor < 0:
            counter = ledger.purpose_gl(db, acc.organization_id, acc.entity_id, "BANK_FEES", acc.currency)
            lines = [ledger.Line(counter.id, acc.currency, debit=amt), ledger.Line(ledger.bank_gl(db, acc.id).id, acc.currency, credit=amt)]
        else:
            counter = ledger.purpose_gl(db, acc.organization_id, acc.entity_id, "SUSPENSE", acc.currency)
            lines = [ledger.Line(ledger.bank_gl(db, acc.id).id, acc.currency, debit=amt), ledger.Line(counter.id, acc.currency, credit=amt)]
        entry, _ = ledger.post_entry(db, org_id=acc.organization_id, entity_id=acc.entity_id, journal="FRA",
                                     description=f"Régularisation rapprochement : {c.description}"[:500], lines=lines,
                                     idempotency_key=f"reco-adjust:{c.id}", reference_type="statement_line",
                                     reference_id=c.external_ref, created_by=principal.user_id,
                                     value_date=c.value_date)
        c.resolution_entry_id = entry.id
    elif action != "EXPLAINED":
        raise DomainError("INVALID_ACTION", "Action : POST_ADJUSTMENT ou EXPLAINED", 422)
    c.status = "RESOLVED"
    c.resolution = action
    c.resolution_note = note
    c.resolved_by = principal.user_id
    c.resolved_at = clock.now()
    principal.audit("reconciliation.resolved", "reconciliation_case", c.id, entity_id=c.entity_id,
                    details={"action": action, "note": note,
                             "entry_id": str(c.resolution_entry_id) if c.resolution_entry_id else None})
    return c


def serialize(db, c: ReconciliationCase) -> dict:
    acc = db.get(BankAccount, c.account_id)

    def un(uid):
        u = db.get(User, uid) if uid else None
        return u.full_name if u else None

    return {
        "id": str(c.id), "kind": c.kind, "kind_label": KIND_LABELS[c.kind], "status": c.status,
        "status_label": {"OPEN": "Ouvert", "ACKNOWLEDGED": "Pris en compte (non résolu)", "RESOLVED": "Résolu"}[c.status],
        "account": {"id": str(acc.id), "name": acc.name}, "external_ref": c.external_ref, "description": c.description,
        "statement_amount": money(c.statement_minor, c.currency) if c.statement_minor is not None else None,
        "ledger_amount": money(c.ledger_minor, c.currency) if c.ledger_minor is not None else None,
        "payment_id": str(c.payment_id) if c.payment_id else None,
        "owner": un(c.owner_user_id), "due_date": c.due_date.isoformat() if c.due_date else None,
        "detected_at": c.created_at.isoformat(), "acknowledged_by": un(c.acknowledged_by),
        "acknowledged_at": c.acknowledged_at.isoformat() if c.acknowledged_at else None,
        "resolution": c.resolution, "resolution_note": c.resolution_note, "resolved_by": un(c.resolved_by),
        "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
        "resolution_entry_id": str(c.resolution_entry_id) if c.resolution_entry_id else None,
        "source": statement_provider.name,
    }
