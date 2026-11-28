"""Simulateur bancaire déterministe (système destinataire FICTIF).

Comportement reproductible :
* IBAN créancier se terminant par « 0404 » → rejet AC04 (compte clôturé) ;
* montant > 10 000 000 → rejet AM02 ;
* sinon : ACCEPTED puis SETTLED (règlement), avec ligne de relevé.
* Pannes injectables à usage unique :
  - TIMEOUT_AFTER_RECORD : l'ordre est enregistré mais la réponse est perdue ;
  - TIMEOUT_BEFORE_RECORD : rien n'est enregistré, la réponse est perdue.
* Les événements sont signés (HMAC-SHA256) et peuvent être redélivrés
  (démonstration de la déduplication).

Le simulateur utilise ses propres sessions : ses enregistrements survivent
même si la transaction appelante échoue — comme un vrai système externe.
"""
from __future__ import annotations

import json
import uuid
from datetime import date

from sqlalchemy import select

from horizon.core import clock
from horizon.core.config import get_settings
from horizon.core.crypto import hmac_hex
from horizon.core.db import SessionLocal
from horizon.modules.integrations.gateway import GatewayRejected, GatewayTimeout, OrderStatus, StatementLine, SubmitAck
from horizon.modules.integrations.models import SimBankEvent, SimBankOrder, SimFault, SimStatementLine

NAME = "Simulateur bancaire HORIZON (fictif)"
CLOSED_SUFFIX = "0404"  # règle déterministe documentée : compte du bénéficiaire « clôturé »


def is_closed(iban: str) -> bool:
    return iban.endswith(CLOSED_SUFFIX)


def _event(s, order: SimBankOrder | None, etype: str, payload: dict) -> SimBankEvent:
    ev = SimBankEvent(event_id=f"sim-evt-{uuid.uuid4()}", order_id=order.id if order else None, event_type=etype,
                      payload={"event_type": etype, **payload})
    ev.payload["event_id"] = ev.event_id
    ev.payload["emitted_at"] = clock.now().isoformat()
    s.add(ev)
    s.flush()
    return ev


def _take_fault(s, remittance: str) -> SimFault | None:
    for f in s.scalars(select(SimFault).where(SimFault.remaining > 0).order_by(SimFault.created_at).with_for_update()):
        if f.match_remittance is None or f.match_remittance.lower() in (remittance or "").lower():
            f.remaining -= 1
            return f
    return None


class SimulatedBank:
    name = NAME

    # --- PaymentGateway ------------------------------------------------------
    def submit(self, order: dict) -> SubmitAck:
        with SessionLocal() as s:
            fault = _take_fault(s, order.get("remittance_info", ""))
            if fault is not None and fault.kind == "TIMEOUT_BEFORE_RECORD":
                s.commit()
                raise GatewayTimeout("Délai dépassé (simulé) avant enregistrement")
            existing = s.scalar(select(SimBankOrder).where(SimBankOrder.submission_key == order["submission_key"]))
            if existing is None:
                if not order["creditor_iban"][:2].isalpha():
                    s.commit()
                    raise GatewayRejected("AC01", "Format de compte invalide")
                existing = SimBankOrder(
                    submission_key=order["submission_key"], bank_reference=f"SIMREF-{uuid.uuid4().hex[:12].upper()}",
                    end_to_end_id=order["end_to_end_id"], debtor_iban=order["debtor_iban"],
                    creditor_iban=order["creditor_iban"], creditor_name=order["creditor_name"],
                    amount_minor=order["amount_minor"], currency=order["currency"],
                    requested_date=date.fromisoformat(order["execution_date"]), status="RECEIVED",
                )
                s.add(existing)
                s.flush()
            # Idempotence : une nouvelle soumission de la même clé renvoie le même ordre.
            ack = SubmitAck(bank_reference=existing.bank_reference, received_at=clock.now())
            s.commit()
            if fault is not None and fault.kind == "TIMEOUT_AFTER_RECORD":
                raise GatewayTimeout("Délai dépassé (simulé) après enregistrement de l'ordre")
            return ack

    def find(self, submission_key: str) -> OrderStatus | None:
        with SessionLocal() as s:
            o = s.scalar(select(SimBankOrder).where(SimBankOrder.submission_key == submission_key))
            if o is None:
                return None
            return OrderStatus(o.submission_key, o.bank_reference, o.status, o.rejection_code)

    # --- traitement interne du « système destinataire » -----------------------
    def process_pending(self) -> int:
        n = 0
        with SessionLocal() as s:
            for o in s.scalars(select(SimBankOrder).where(SimBankOrder.status.in_(("RECEIVED", "ACCEPTED")))
                               .with_for_update(skip_locked=True)):
                base = {"submission_key": o.submission_key, "bank_reference": o.bank_reference,
                        "end_to_end_id": o.end_to_end_id, "amount_minor": o.amount_minor, "currency": o.currency}
                if o.status == "RECEIVED":
                    if is_closed(o.creditor_iban) or o.amount_minor > 10_000_000_00:
                        o.status = "REJECTED"
                        o.rejection_code = "AC04" if is_closed(o.creditor_iban) else "AM02"
                        _event(s, o, "PAYMENT_REJECTED", {**base, "reason_code": o.rejection_code})
                    else:
                        o.status = "ACCEPTED"
                        _event(s, o, "PAYMENT_ACCEPTED", base)
                    n += 1
                elif o.status == "ACCEPTED":
                    o.status = "SETTLED"
                    o.settled_at = clock.now()
                    s.add(SimStatementLine(line_ref=f"STL-{o.bank_reference}", account_iban=o.debtor_iban,
                                           booking_date=clock.today(), amount_minor=-o.amount_minor, currency=o.currency,
                                           description=f"Virement émis {o.creditor_name}", end_to_end_id=o.end_to_end_id,
                                           bank_reference=o.bank_reference, kind="PAYMENT"))
                    _event(s, o, "PAYMENT_SETTLED", {**base, "settlement_date": clock.today().isoformat()})
                    n += 1
            s.commit()
        return n

    def pending_events(self) -> list[tuple[str, bytes, str]]:
        """Événements non encore livrés : (event_id, corps, signature)."""
        out = []
        with SessionLocal() as s:
            for ev in s.scalars(select(SimBankEvent).where(SimBankEvent.delivered_count == 0).order_by(SimBankEvent.created_at)):
                body = json.dumps(ev.payload, sort_keys=True).encode()
                out.append((ev.event_id, body, sign(body)))
        return out

    def mark_delivered(self, event_id: str) -> None:
        with SessionLocal() as s:
            ev = s.scalar(select(SimBankEvent).where(SimBankEvent.event_id == event_id))
            ev.delivered_count += 1
            ev.delivered_at = clock.now()
            s.commit()

    def event_body(self, event_id: str) -> tuple[bytes, str] | None:
        with SessionLocal() as s:
            ev = s.scalar(select(SimBankEvent).where(SimBankEvent.event_id == event_id))
            if ev is None:
                return None
            body = json.dumps(ev.payload, sort_keys=True).encode()
            return body, sign(body)

    # --- démonstration --------------------------------------------------------
    def inject_fault(self, kind: str, match_remittance: str | None = None, count: int = 1) -> str:
        assert kind in ("TIMEOUT_AFTER_RECORD", "TIMEOUT_BEFORE_RECORD")
        with SessionLocal() as s:
            f = SimFault(kind=kind, match_remittance=match_remittance, remaining=count)
            s.add(f)
            s.commit()
            return str(f.id)

    def simulate_return(self, submission_key: str, amount_minor: int | None, reason_code: str = "MD06") -> str:
        with SessionLocal() as s:
            o = s.scalar(select(SimBankOrder).where(SimBankOrder.submission_key == submission_key).with_for_update())
            if o is None or o.status != "SETTLED":
                raise ValueError("Seul un ordre réglé peut faire l'objet d'un retour")
            amt = amount_minor or o.amount_minor
            o.status = "RETURNED"
            ev = _event(s, o, "PAYMENT_RETURNED", {"submission_key": o.submission_key, "bank_reference": o.bank_reference,
                                                   "end_to_end_id": o.end_to_end_id, "amount_minor": amt,
                                                   "currency": o.currency, "reason_code": reason_code})
            s.add(SimStatementLine(line_ref=f"RET-{ev.event_id}", account_iban=o.debtor_iban, booking_date=clock.today(),
                                   amount_minor=amt, currency=o.currency, description=f"Retour de fonds {o.creditor_name}",
                                   end_to_end_id=o.end_to_end_id, bank_reference=o.bank_reference, kind="RETURN"))
            s.commit()
            return ev.event_id

    def simulate_incoming(self, iban: str, amount_minor: int, currency: str, reference: str, payer: str) -> str:
        with SessionLocal() as s:
            ref = f"INC-{uuid.uuid4().hex[:10].upper()}"
            ev = _event(s, None, "INCOMING_CREDIT", {"account_iban": iban, "amount_minor": amount_minor, "currency": currency,
                                                     "reference": reference, "payer": payer, "bank_reference": ref})
            s.add(SimStatementLine(line_ref=f"INC-{ev.event_id}", account_iban=iban, booking_date=clock.today(),
                                   amount_minor=amount_minor, currency=currency, description=f"Virement reçu {payer} {reference}",
                                   end_to_end_id=None, bank_reference=ref, kind="INCOMING"))
            s.commit()
            return ev.event_id

    def add_fee_line(self, iban: str, amount_minor: int, currency: str, label: str, line_ref: str) -> None:
        with SessionLocal() as s:
            if s.scalar(select(SimStatementLine).where(SimStatementLine.line_ref == line_ref)) is None:
                s.add(SimStatementLine(line_ref=line_ref, account_iban=iban, booking_date=clock.today(),
                                       amount_minor=-amount_minor, currency=currency, description=label,
                                       end_to_end_id=None, bank_reference=line_ref, kind="FEE"))
                s.commit()

    # --- StatementProvider ------------------------------------------------------
    def statement(self, iban: str, since: date) -> list[StatementLine]:
        with SessionLocal() as s:
            rows = s.scalars(select(SimStatementLine).where(SimStatementLine.account_iban == iban,
                                                            SimStatementLine.booking_date >= since)
                             .order_by(SimStatementLine.created_at)).all()
            return [StatementLine(r.line_ref, r.booking_date, r.amount_minor, r.currency, r.description,
                                  r.end_to_end_id, r.bank_reference, r.kind) for r in rows]


def sign(body: bytes) -> str:
    return "sha256=" + hmac_hex(get_settings().simulator_webhook_secret, body)


bank = SimulatedBank()
