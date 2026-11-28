from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from horizon.api.schemas import ReverseIn
from horizon.core import clock
from horizon.core.context import Principal, get_principal
from horizon.core.errors import Forbidden, NotFound
from horizon.core.money import money
from horizon.core.pagination import PageParams, paginate, paginate_list
from horizon.modules.accounts import service as accounts
from horizon.modules.accounts.models import BankAccount, ExternalBalanceSnapshot
from horizon.modules.ledger import service as ledger
from horizon.modules.ledger.models import GlAccount, JournalEntry, JournalLine
from horizon.modules.overview import service as overview

router = APIRouter(prefix="/v1", tags=["Comptes et registre"])


@router.get("/overview", tags=["Vue d'ensemble"], summary="Indicateurs calculés et leurs justifications")
def get_overview(p: Principal = Depends(get_principal)):
    return overview.overview(p.db, p)


@router.get("/accounts")
def list_accounts(page: PageParams = Depends(), p: Principal = Depends(get_principal)):
    p.require_any("account.read")
    accs = accounts.visible_accounts(p.db, p)
    return paginate_list([accounts.serialize_account(p.db, a) for a in accs], page)


@router.get("/consolidation", summary="Consolidation multidevise avec taux datés")
def consolidation(p: Principal = Depends(get_principal)):
    p.require_any("account.read")
    return accounts.consolidate(p.db, p)


def _account(p: Principal, account_id: uuid.UUID, perm="account.read") -> BankAccount:
    acc = p.db.get(BankAccount, account_id)
    if acc is None or acc.organization_id != p.org_id:
        raise NotFound("Compte", account_id)
    if not p.authz.can_see_account(perm, acc.entity_id, acc.id):
        p.denied(perm, entity_id=acc.entity_id, account_id=acc.id)
        raise Forbidden(f"Permission « {perm} » requise sur ce compte", {"permission": perm})
    return acc


@router.get("/accounts/{account_id}")
def get_account(account_id: uuid.UUID, p: Principal = Depends(get_principal)):
    acc = _account(p, account_id)
    out = accounts.serialize_account(p.db, acc)
    if acc.kind == "EXTERNAL_READONLY":
        snaps = p.db.scalars(select(ExternalBalanceSnapshot).where(ExternalBalanceSnapshot.account_id == acc.id)
                             .order_by(ExternalBalanceSnapshot.observed_at.desc()).limit(10)).all()
        out["snapshots"] = [{"observed_at": s.observed_at.isoformat(), "booked": money(s.booked_minor, s.currency),
                             "source": s.source, "statement_reference": s.statement_reference} for s in snaps]
    return out


@router.get("/accounts/{account_id}/transactions", summary="Écritures du registre affectant le compte")
def account_transactions(account_id: uuid.UUID, page: PageParams = Depends(), p: Principal = Depends(get_principal)):
    acc = _account(p, account_id, "transaction.read")
    if acc.kind != "SIMULATED":
        return {"data": [], "page": {"limit": page.limit, "total": 0, "next_cursor": None},
                "note": "Compte externe en lecture seule : seuls les soldes observés sont disponibles."}
    gl = ledger.bank_gl(p.db, acc.id)
    stmt = (select(JournalLine).where(JournalLine.gl_account_id == gl.id)
            .order_by(JournalLine.value_date.desc(), JournalLine.id.desc()))

    def ser(ln: JournalLine):
        e = p.db.get(JournalEntry, ln.entry_id)
        signed = ln.debit_minor - ln.credit_minor
        return {"entry_id": str(e.id), "entry_number": e.entry_number, "journal": e.journal,
                "booking_date": e.booking_date.isoformat(), "value_date": ln.value_date.isoformat(),
                "description": e.description, "amount": money(signed, ln.currency),
                "direction": "CREDIT" if signed > 0 else "DEBIT", "reference_type": e.reference_type,
                "reference_id": e.reference_id, "reverses_entry_id": str(e.reverses_entry_id) if e.reverses_entry_id else None}
    return paginate(p.db, stmt, page, ser)


@router.get("/accounts/{account_id}/balance-history")
def balance_history(account_id: uuid.UUID, days: int = Query(30, ge=1, le=365), p: Principal = Depends(get_principal)):
    acc = _account(p, account_id)
    if acc.kind != "SIMULATED":
        return {"data": []}
    today = clock.today()
    return {"data": [{"date": d.isoformat(), "booked": money(v, acc.currency)}
                     for d, v in ledger.daily_balances(p.db, acc.id, today - timedelta(days=days), today)]}


@router.get("/ledger/entries", summary="Journal général")
def ledger_entries(page: PageParams = Depends(), journal: str | None = None, p: Principal = Depends(get_principal)):
    p.require_any("ledger.read")
    stmt = select(JournalEntry).where(JournalEntry.organization_id == p.org_id).order_by(JournalEntry.entry_number.desc())
    if journal:
        stmt = stmt.where(JournalEntry.journal == journal)
    from horizon.modules.organizations.models import LegalEntity

    ents = [e.id for e in p.db.scalars(select(LegalEntity).where(LegalEntity.organization_id == p.org_id))
            if p.authz.can_see_entity("ledger.read", e.id)]
    stmt = stmt.where(JournalEntry.entity_id.in_(ents))
    names = {g.id: f"{g.code} {g.name}" for g in p.db.scalars(select(GlAccount).where(GlAccount.organization_id == p.org_id))}
    return paginate(p.db, stmt, page, lambda e: ledger.serialize_entry(e, names))


@router.get("/ledger/trial-balance", summary="Balance générale (contrôle d'équilibre par devise)")
def trial_balance(p: Principal = Depends(get_principal)):
    p.require_any("ledger.read")
    rows = ledger.trial_balance(p.db, p.org_id)
    by_ccy: dict[str, list[int]] = {}
    for r in rows:
        t = by_ccy.setdefault(r["currency"], [0, 0])
        t[0] += r["debit_minor"]
        t[1] += r["credit_minor"]
    return {"accounts": rows, "totals_by_currency": {c: {"debit": money(d, c), "credit": money(cr, c), "balanced": d == cr}
                                                      for c, (d, cr) in by_ccy.items()}}


@router.post("/ledger/entries/{entry_id}/reverse", summary="Contrepassation liée (les écritures sont immuables)")
def reverse(entry_id: uuid.UUID, body: ReverseIn, p: Principal = Depends(get_principal)):
    e = p.db.get(JournalEntry, entry_id)
    if e is None or e.organization_id != p.org_id:
        raise NotFound("Écriture", entry_id)
    p.require("reconciliation.resolve", e.entity_id)
    p.require_step_up()
    rev = ledger.reverse_entry(p.db, entry_id, body.reason, p.user_id)
    p.audit("ledger.entry_reversed", "journal_entry", e.id, entity_id=e.entity_id,
            details={"reversal_entry_id": str(rev.id), "reason": body.reason})
    return ledger.serialize_entry(rev)
