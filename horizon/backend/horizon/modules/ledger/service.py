"""Registre en partie double des comptes simulés.

Règles :
* une écriture comporte au moins deux lignes, chacune au débit OU au crédit ;
* pour chaque devise, Σ débits = Σ crédits (vérifié ici ET par un trigger
  PostgreSQL différé) — une opération de change s'équilibre donc devise par
  devise via les comptes « Position de change » ;
* les écritures sont immuables : correction = contrepassation liée
  (reverses_entry_id) et éventuellement nouvelle écriture (corrects_entry_id) ;
* idempotency_key unique : rejouer une comptabilisation ne double jamais
  l'effet (protection contre les événements dupliqués).

Solde d'un compte bancaire simulé (miroir ACTIF) = Σ débits − Σ crédits.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.errors import Conflict, DomainError, NotFound
from horizon.modules.ledger.models import GlAccount, JournalEntry, JournalLine, Reservation

PURPOSE_META = {
    "BANK": ("ASSET", "512"),
    "OPENING_EQUITY": ("EQUITY", "101"),
    "COUNTERPARTY_OUT": ("LIABILITY", "401"),
    "COUNTERPARTY_IN": ("ASSET", "411"),
    "FX_POSITION": ("ASSET", "476"),
    "BANK_FEES": ("EXPENSE", "627"),
    "SUSPENSE": ("ASSET", "471"),
}
PURPOSE_NAMES = {
    "OPENING_EQUITY": "Contrepartie des soldes d'ouverture",
    "COUNTERPARTY_OUT": "Tiers – paiements émis",
    "COUNTERPARTY_IN": "Tiers – encaissements reçus",
    "FX_POSITION": "Position de change",
    "BANK_FEES": "Frais bancaires",
    "SUSPENSE": "Compte d'attente",
}


@dataclass
class Line:
    gl_account_id: uuid.UUID
    currency: str
    debit: int = 0
    credit: int = 0


def bank_gl(db: Session, bank_account_id: uuid.UUID) -> GlAccount:
    gl = db.scalar(select(GlAccount).where(GlAccount.bank_account_id == bank_account_id))
    if gl is None:
        raise DomainError("NO_LEDGER_ACCOUNT", "Compte sans registre simulé (compte externe en lecture seule ?)", 409)
    return gl


def purpose_gl(db: Session, org_id: uuid.UUID, entity_id: uuid.UUID, purpose: str, currency: str) -> GlAccount:
    gl = db.scalar(
        select(GlAccount).where(
            GlAccount.organization_id == org_id,
            GlAccount.entity_id == entity_id,
            GlAccount.purpose == purpose,
            GlAccount.currency == currency,
        )
    )
    if gl is None:
        typ, prefix = PURPOSE_META[purpose]
        n = db.scalar(select(func.count()).select_from(GlAccount).where(GlAccount.organization_id == org_id)) or 0
        gl = GlAccount(
            organization_id=org_id,
            entity_id=entity_id,
            code=f"{prefix}{n + 1:04d}-{currency}",
            name=f"{PURPOSE_NAMES[purpose]} ({currency})",
            type=typ,
            purpose=purpose,
            currency=currency,
        )
        db.add(gl)
        db.flush()
    return gl


def post_entry(
    db: Session,
    *,
    org_id: uuid.UUID,
    entity_id: uuid.UUID,
    journal: str,
    description: str,
    lines: list[Line],
    idempotency_key: str,
    value_date: date | None = None,
    booking_date: date | None = None,
    reference_type: str | None = None,
    reference_id: str | None = None,
    created_by: uuid.UUID | None = None,
    reverses_entry_id: uuid.UUID | None = None,
    corrects_entry_id: uuid.UUID | None = None,
) -> tuple[JournalEntry, bool]:
    """Comptabilise une écriture équilibrée. Retourne (écriture, créée?)."""
    existing = db.scalar(select(JournalEntry).where(JournalEntry.idempotency_key == idempotency_key))
    if existing is not None:
        return existing, False
    if len(lines) < 2:
        raise DomainError("ENTRY_TOO_SHORT", "Une écriture exige au moins deux lignes", 422)
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    gl_ids = {ln.gl_account_id for ln in lines}
    gls = {g.id: g for g in db.scalars(select(GlAccount).where(GlAccount.id.in_(gl_ids)))}
    for ln in lines:
        if (ln.debit < 0 or ln.credit < 0) or ((ln.debit == 0) == (ln.credit == 0)):
            raise DomainError("INVALID_LINE", "Chaque ligne est soit au débit soit au crédit, montant positif", 422)
        gl = gls.get(ln.gl_account_id)
        if gl is None or gl.organization_id != org_id:
            raise DomainError("INVALID_GL_ACCOUNT", "Compte comptable inconnu pour cette organisation", 422)
        if gl.currency != ln.currency:
            raise DomainError("CURRENCY_MISMATCH", f"Le compte {gl.code} est tenu en {gl.currency}", 422)
        totals[ln.currency][0] += ln.debit
        totals[ln.currency][1] += ln.credit
    unbalanced = {c: t for c, t in totals.items() if t[0] != t[1]}
    if unbalanced:
        raise DomainError("ENTRY_UNBALANCED", "Écriture déséquilibrée", 422,
                          {c: {"debit": t[0], "credit": t[1]} for c, t in unbalanced.items()})
    today = clock.today()
    vd = value_date or today
    entry = JournalEntry(
        organization_id=org_id,
        entity_id=entity_id,
        entry_number=db.scalar(text("SELECT nextval('journal_entry_number_seq')")),
        journal=journal,
        booking_date=booking_date or today,
        value_date=vd,
        description=description,
        reference_type=reference_type,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
        reverses_entry_id=reverses_entry_id,
        corrects_entry_id=corrects_entry_id,
        created_by=created_by,
    )
    db.add(entry)
    db.flush()
    for i, ln in enumerate(lines, start=1):
        db.add(JournalLine(entry_id=entry.id, line_no=i, gl_account_id=ln.gl_account_id, currency=ln.currency,
                           debit_minor=ln.debit, credit_minor=ln.credit, value_date=vd))
    db.flush()
    return entry, True


def reverse_entry(db: Session, entry_id: uuid.UUID, reason: str, user_id: uuid.UUID | None) -> JournalEntry:
    orig = db.get(JournalEntry, entry_id)
    if orig is None:
        raise NotFound("Écriture", entry_id)
    if orig.reverses_entry_id is not None:
        raise Conflict("CANNOT_REVERSE_REVERSAL", "Une contrepassation ne se contrepasse pas ; passez une nouvelle écriture")
    already = db.scalar(select(JournalEntry).where(JournalEntry.reverses_entry_id == orig.id))
    if already is not None:
        raise Conflict("ALREADY_REVERSED", "Écriture déjà contrepassée", {"reversal_entry_id": str(already.id)})
    lines = [Line(ln.gl_account_id, ln.currency, debit=ln.credit_minor, credit=ln.debit_minor) for ln in orig.lines]
    entry, _ = post_entry(
        db,
        org_id=orig.organization_id,
        entity_id=orig.entity_id,
        journal="COR",
        description=f"Contrepassation de l'écriture n°{orig.entry_number} — {reason}",
        lines=lines,
        idempotency_key=f"reversal:{orig.id}",
        reference_type="journal_entry",
        reference_id=str(orig.id),
        created_by=user_id,
        reverses_entry_id=orig.id,
    )
    return entry


def booked_balance(db: Session, bank_account_id: uuid.UUID, as_of: date | None = None) -> int:
    gl = bank_gl(db, bank_account_id)
    q = select(func.coalesce(func.sum(JournalLine.debit_minor - JournalLine.credit_minor), 0)).where(
        JournalLine.gl_account_id == gl.id
    )
    if as_of is not None:
        q = q.where(JournalLine.value_date <= as_of)
    return int(db.scalar(q) or 0)


def reserved_amount(db: Session, bank_account_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(Reservation.amount_minor), 0)).where(
                Reservation.bank_account_id == bank_account_id, Reservation.status == "ACTIVE"
            )
        )
        or 0
    )


def daily_balances(db: Session, bank_account_id: uuid.UUID, start: date, end: date) -> list[tuple[date, int]]:
    """Solde comptabilisé de clôture, jour par jour (date de valeur)."""
    from datetime import timedelta

    gl = bank_gl(db, bank_account_id)
    opening = booked_balance(db, bank_account_id, start - timedelta(days=1))
    rows = db.execute(
        select(JournalLine.value_date, func.sum(JournalLine.debit_minor - JournalLine.credit_minor))
        .where(JournalLine.gl_account_id == gl.id, JournalLine.value_date >= start, JournalLine.value_date <= end)
        .group_by(JournalLine.value_date)
    ).all()
    delta = {d: int(v) for d, v in rows}
    out, bal, d = [], opening, start
    while d <= end:
        bal += delta.get(d, 0)
        out.append((d, bal))
        d += timedelta(days=1)
    return out


def reserve(db: Session, org_id, bank_account_id, amount_minor: int, currency: str, ref_type: str, ref_id: str) -> Reservation:
    r = Reservation(organization_id=org_id, bank_account_id=bank_account_id, amount_minor=amount_minor,
                    currency=currency, reference_type=ref_type, reference_id=ref_id, status="ACTIVE")
    db.add(r)
    db.flush()
    return r


def close_reservation(db: Session, ref_type: str, ref_id: str, status: str, reason: str) -> Reservation | None:
    r = db.scalar(
        select(Reservation)
        .where(Reservation.reference_type == ref_type, Reservation.reference_id == ref_id, Reservation.status == "ACTIVE")
        .with_for_update()
    )
    if r is not None:
        r.status = status
        r.closed_at = clock.now()
        r.closing_reason = reason
        db.flush()
    return r


def trial_balance(db: Session, org_id: uuid.UUID) -> list[dict]:
    rows = db.execute(
        select(GlAccount, func.coalesce(func.sum(JournalLine.debit_minor), 0), func.coalesce(func.sum(JournalLine.credit_minor), 0))
        .outerjoin(JournalLine, JournalLine.gl_account_id == GlAccount.id)
        .where(GlAccount.organization_id == org_id)
        .group_by(GlAccount.id)
        .order_by(GlAccount.code)
    ).all()
    return [
        {"gl_account_id": str(g.id), "code": g.code, "name": g.name, "type": g.type, "currency": g.currency,
         "debit_minor": int(d), "credit_minor": int(c), "balance_minor": int(d) - int(c)}
        for g, d, c in rows
    ]


def serialize_entry(e: JournalEntry, gl_names: dict | None = None) -> dict:
    from horizon.core.money import fmt

    return {
        "id": str(e.id),
        "entry_number": e.entry_number,
        "journal": e.journal,
        "booking_date": e.booking_date.isoformat(),
        "value_date": e.value_date.isoformat(),
        "description": e.description,
        "reference_type": e.reference_type,
        "reference_id": e.reference_id,
        "reverses_entry_id": str(e.reverses_entry_id) if e.reverses_entry_id else None,
        "corrects_entry_id": str(e.corrects_entry_id) if e.corrects_entry_id else None,
        "lines": [
            {
                "gl_account_id": str(ln.gl_account_id),
                "gl_account": (gl_names or {}).get(ln.gl_account_id),
                "currency": ln.currency,
                "debit": fmt(ln.debit_minor, ln.currency) if ln.debit_minor else None,
                "credit": fmt(ln.credit_minor, ln.currency) if ln.credit_minor else None,
            }
            for ln in e.lines
        ],
    }
