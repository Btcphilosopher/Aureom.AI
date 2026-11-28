"""Taux datés, conversions identifiées et devis de change (simulation).

* Toute conversion renvoie la référence du taux utilisé (id, date, source).
* INDICATIVE : information, jamais exécutable.
* EXECUTABLE_SIMULATED : offre ferme *du simulateur* valable 30 s ; son
  acceptation comptabilise une conversion entre deux comptes SIMULÉS.
  Aucun ordre n'est transmis à un marché ou à une banque.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.errors import Conflict, DomainError, NotFound
from horizon.core.money import convert_minor, exponent, fmt, from_minor, money, to_minor
from horizon.modules.fx.models import FxQuote, FxRate
from horizon.modules.integrations import rates as rate_adapter

EXECUTABLE_TTL_SECONDS = 30
INDICATIVE_TTL_SECONDS = 15 * 60
DEFAULT_FEE_BPS = 15  # 0,15 %, synthétique


def ensure_rates(db: Session, as_of: date) -> None:
    for obs in rate_adapter.provider.rates_for(as_of):
        exists = db.scalar(select(FxRate.id).where(FxRate.base == obs.base, FxRate.quote == obs.quote,
                                                   FxRate.as_of_date == obs.as_of, FxRate.source == obs.source))
        if exists is None:
            db.add(FxRate(base=obs.base, quote=obs.quote, rate=obs.rate, as_of_date=obs.as_of,
                          observed_at=clock.now(), source=obs.source))
    db.flush()


class RateRef(dict):
    pass


def get_rate(db: Session, from_ccy: str, to_ccy: str, on: date | None = None) -> tuple[Decimal, dict]:
    """Taux from→to le plus récent à la date ``on``. Renvoie (taux, référence)."""
    on = on or clock.today()
    if from_ccy == to_ccy:
        return Decimal(1), {"rate_id": None, "rate": "1", "as_of": on.isoformat(), "source": "Identité (même devise)",
                            "pair": f"{from_ccy}/{to_ccy}", "inverted": False}
    for base, quote, inverted in ((from_ccy, to_ccy, False), (to_ccy, from_ccy, True)):
        r = db.scalar(select(FxRate).where(FxRate.base == base, FxRate.quote == quote, FxRate.as_of_date <= on)
                      .order_by(FxRate.as_of_date.desc()).limit(1))
        if r is not None:
            rate = (Decimal(1) / Decimal(r.rate)).quantize(Decimal("0.0000000001")) if inverted else Decimal(r.rate)
            return rate, {"rate_id": str(r.id), "rate": str(rate), "as_of": r.as_of_date.isoformat(), "source": r.source,
                          "pair": f"{r.base}/{r.quote}", "inverted": inverted, "stored_rate": str(r.rate)}
    raise DomainError("RATE_UNAVAILABLE", f"Aucun taux daté disponible pour {from_ccy}/{to_ccy}", 409)


def convert(db: Session, minor: int, from_ccy: str, to_ccy: str, on: date | None = None) -> tuple[int, dict]:
    rate, ref = get_rate(db, from_ccy, to_ccy, on)
    return convert_minor(minor, from_ccy, to_ccy, rate), ref


def serialize_rate(r: FxRate) -> dict:
    return {"id": str(r.id), "pair": f"{r.base}/{r.quote}", "rate": str(r.rate), "as_of": r.as_of_date.isoformat(),
            "source": r.source, "kind": r.kind}


def create_quote(db: Session, principal, *, entity_id: uuid.UUID, base: str, quote: str, side: str, amount: str,
                 amount_currency: str, kind: str, sell_account_id=None, buy_account_id=None) -> FxQuote:
    principal.require("fx.quote", entity_id)
    side = side.upper()
    if side not in {"BUY", "SELL"}:
        raise DomainError("INVALID_SIDE", "Sens attendu : BUY ou SELL (de la devise de base)", 422)
    if kind not in {"INDICATIVE", "EXECUTABLE_SIMULATED"}:
        raise DomainError("INVALID_QUOTE_KIND", "Type de devis : INDICATIVE ou EXECUTABLE_SIMULATED", 422)
    if base == quote:
        raise DomainError("INVALID_PAIR", "Les deux devises doivent différer", 422)
    if amount_currency not in {base, quote}:
        raise DomainError("INVALID_AMOUNT_CURRENCY", "Le montant doit être exprimé dans une devise de la paire", 422)
    today = clock.today()
    ensure_rates(db, today)
    mid, ref = get_rate(db, base, quote, today)
    # Le client achète la base (BUY) : il vend la devise de cotation ; marge défavorable au client.
    spread = Decimal(DEFAULT_FEE_BPS) / Decimal(10000)
    client_rate = (mid * (1 + spread) if side == "BUY" else mid * (1 - spread)).quantize(Decimal("0.000001"))
    sell_ccy, buy_ccy = (quote, base) if side == "BUY" else (base, quote)
    amt_minor = to_minor(amount, amount_currency)
    if amt_minor <= 0:
        raise DomainError("INVALID_AMOUNT", "Montant strictement positif requis", 422)
    if amount_currency == base:
        base_minor = amt_minor
        quote_minor = convert_minor(base_minor, base, quote, client_rate)
    else:
        quote_minor = amt_minor
        base_minor = convert_minor(quote_minor, quote, base, (Decimal(1) / client_rate))
    sell_minor, buy_minor = (quote_minor, base_minor) if side == "BUY" else (base_minor, quote_minor)
    # Frais (marge) exprimés dans la devise vendue : différence avec le taux médian.
    mid_equiv = convert_minor(buy_minor, buy_ccy, sell_ccy,
                              (Decimal(1) / mid) if buy_ccy == quote else mid)
    fee_minor = max(sell_minor - mid_equiv, 0)
    ttl = EXECUTABLE_TTL_SECONDS if kind == "EXECUTABLE_SIMULATED" else INDICATIVE_TTL_SECONDS
    q = FxQuote(
        organization_id=principal.org_id, entity_id=entity_id, kind=kind, side=side, base=base, quote=quote,
        sell_currency=sell_ccy, buy_currency=buy_ccy, sell_minor=sell_minor, buy_minor=buy_minor,
        mid_rate=mid, client_rate=client_rate, fee_bps=DEFAULT_FEE_BPS, fee_minor=fee_minor, fee_currency=sell_ccy,
        rate_id=uuid.UUID(ref["rate_id"]) if ref["rate_id"] else None, source=ref["source"],
        expires_at=clock.now() + timedelta(seconds=ttl), status="OPEN",
        sell_account_id=sell_account_id, buy_account_id=buy_account_id, created_by=principal.user_id,
    )
    db.add(q)
    db.flush()
    principal.audit("fx.quote_created", "fx_quote", q.id, entity_id=entity_id,
                    details={"kind": kind, "pair": f"{base}/{quote}", "side": side})
    return q


def accept_quote(db: Session, principal, quote_id: uuid.UUID) -> FxQuote:
    from horizon.modules.accounts.models import BankAccount
    from horizon.modules.ledger import service as ledger

    q = db.get(FxQuote, quote_id, with_for_update=True)
    if q is None or q.organization_id != principal.org_id:
        raise NotFound("Devis", quote_id)
    principal.require("fx.execute_simulated", q.entity_id)
    principal.require_step_up()
    if q.kind != "EXECUTABLE_SIMULATED":
        raise Conflict("QUOTE_INDICATIVE", "Un taux indicatif n'est pas une offre exécutable")
    if q.status != "OPEN":
        raise Conflict("QUOTE_NOT_OPEN", f"Devis à l'état {q.status}")
    if q.expires_at < clock.now():
        q.status = "EXPIRED"
        db.flush()
        raise Conflict("QUOTE_EXPIRED", "Offre expirée : demandez un nouveau devis")
    sell_acc = db.get(BankAccount, q.sell_account_id) if q.sell_account_id else None
    buy_acc = db.get(BankAccount, q.buy_account_id) if q.buy_account_id else None
    if not sell_acc or not buy_acc or sell_acc.kind != "SIMULATED" or buy_acc.kind != "SIMULATED":
        raise DomainError("FX_ACCOUNTS_REQUIRED", "Deux comptes SIMULÉS (débit et crédit) sont requis", 422)
    if sell_acc.currency != q.sell_currency or buy_acc.currency != q.buy_currency:
        raise DomainError("FX_ACCOUNT_CURRENCY", "Devises des comptes incohérentes avec le devis", 422)
    if sell_acc.entity_id != q.entity_id or buy_acc.entity_id != q.entity_id:
        raise DomainError("FX_ENTITY_MISMATCH", "Les comptes doivent appartenir à l'entité du devis", 422)
    db.query(BankAccount).filter(BankAccount.id == sell_acc.id).with_for_update().one()
    available = ledger.booked_balance(db, sell_acc.id) - ledger.reserved_amount(db, sell_acc.id)
    if available < q.sell_minor:
        raise Conflict("INSUFFICIENT_FUNDS", "Solde disponible insuffisant sur le compte débité")
    pos_sell = ledger.purpose_gl(db, q.organization_id, q.entity_id, "FX_POSITION", q.sell_currency)
    pos_buy = ledger.purpose_gl(db, q.organization_id, q.entity_id, "FX_POSITION", q.buy_currency)
    lines = [
        # Devise vendue : sortie du compte bancaire vers la position de change (équilibre en sell_currency)
        ledger.Line(pos_sell.id, q.sell_currency, debit=q.sell_minor),
        ledger.Line(ledger.bank_gl(db, sell_acc.id).id, q.sell_currency, credit=q.sell_minor),
        # Devise achetée : entrée sur le compte bancaire depuis la position (équilibre en buy_currency)
        ledger.Line(ledger.bank_gl(db, buy_acc.id).id, q.buy_currency, debit=q.buy_minor),
        ledger.Line(pos_buy.id, q.buy_currency, credit=q.buy_minor),
    ]
    entry, _ = ledger.post_entry(
        db, org_id=q.organization_id, entity_id=q.entity_id, journal="CHG",
        description=f"Conversion simulée {fmt(q.sell_minor, q.sell_currency)} {q.sell_currency} → "
                    f"{fmt(q.buy_minor, q.buy_currency)} {q.buy_currency} (devis {str(q.id)[:8]})",
        lines=lines, idempotency_key=f"fx-quote:{q.id}", reference_type="fx_quote", reference_id=str(q.id),
        created_by=principal.user_id,
    )
    q.status = "ACCEPTED_SIMULATED"
    q.accepted_by = principal.user_id
    q.accepted_at = clock.now()
    q.ledger_entry_id = entry.id
    db.flush()
    principal.audit("fx.quote_accepted_simulated", "fx_quote", q.id, entity_id=q.entity_id,
                    details={"ledger_entry_id": str(entry.id)})
    return q


def serialize_quote(q: FxQuote) -> dict:
    now = clock.now()
    status = q.status
    if status == "OPEN" and q.expires_at < now:
        status = "EXPIRED"
    return {
        "id": str(q.id),
        "kind": q.kind,
        "kind_label": "Taux indicatif — non exécutable" if q.kind == "INDICATIVE" else "Offre exécutable (simulation — aucun ordre réel)",
        "pair": f"{q.base}/{q.quote}",
        "side": q.side,
        "sell": money(q.sell_minor, q.sell_currency),
        "buy": money(q.buy_minor, q.buy_currency),
        "mid_rate": str(q.mid_rate),
        "client_rate": str(q.client_rate),
        "fee_bps": q.fee_bps,
        "fee": money(q.fee_minor, q.fee_currency),
        "rate_id": str(q.rate_id) if q.rate_id else None,
        "source": q.source,
        "created_at": q.created_at.isoformat(),
        "expires_at": q.expires_at.isoformat(),
        "seconds_remaining": max(0, int((q.expires_at - now).total_seconds())),
        "status": status,
        "sell_account_id": str(q.sell_account_id) if q.sell_account_id else None,
        "buy_account_id": str(q.buy_account_id) if q.buy_account_id else None,
        "ledger_entry_id": str(q.ledger_entry_id) if q.ledger_entry_id else None,
    }
