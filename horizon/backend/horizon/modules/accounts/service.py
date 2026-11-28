"""Soldes explicables.

Règle documentée du solde disponible (comptes SIMULÉS) :
    disponible = solde comptabilisé (registre) − montants réservés actifs
Les réservations naissent à l'approbation finale d'un paiement et disparaissent
à son exécution (consommées) ou à son rejet/annulation (libérées). Les
opérations « en attente » (soumises mais non confirmées) sont donc déjà
couvertes par une réservation : elles sont listées, jamais soustraites deux fois.

Comptes EXTERNES en lecture seule : solde observé tel que transmis par la
source, avec heure d'observation et fraîcheur. Jamais additionnés aux comptes
simulés dans l'indicateur de liquidité.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.config import get_settings
from horizon.core.money import money
from horizon.modules.accounts.models import BankAccount, ExternalBalanceSnapshot
from horizon.modules.ledger import service as ledger
from horizon.modules.organizations.models import LegalEntity

PENDING_STATUSES = ("SUBMITTED", "ACCEPTED", "UNKNOWN")


def visible_accounts(db: Session, principal, perm: str = "account.read") -> list[BankAccount]:
    accs = db.scalars(
        select(BankAccount).where(BankAccount.organization_id == principal.org_id).order_by(BankAccount.name)
    ).all()
    return [a for a in accs if principal.authz.can_see_account(perm, a.entity_id, a.id)]


def latest_snapshot(db: Session, account_id) -> ExternalBalanceSnapshot | None:
    return db.scalar(
        select(ExternalBalanceSnapshot)
        .where(ExternalBalanceSnapshot.account_id == account_id)
        .order_by(ExternalBalanceSnapshot.observed_at.desc())
        .limit(1)
    )


def freshness(observed_at) -> dict:
    age = clock.now() - observed_at
    stale_after = timedelta(hours=get_settings().external_data_stale_hours)
    hours = round(age.total_seconds() / 3600, 1)
    return {"age_hours": hours, "stale": age > stale_after, "stale_after_hours": get_settings().external_data_stale_hours}


def balance_view(db: Session, acc: BankAccount) -> dict:
    from horizon.modules.payments.models import Payment

    now = clock.now()
    if acc.kind == "SIMULATED":
        booked = ledger.booked_balance(db, acc.id)
        reserved = ledger.reserved_amount(db, acc.id)
        pend = db.scalars(
            select(Payment).where(Payment.debtor_account_id == acc.id, Payment.status.in_(PENDING_STATUSES))
        ).all()
        return {
            "kind": "SIMULATED",
            "booked": money(booked, acc.currency),
            "reserved": money(reserved, acc.currency),
            "available": money(booked - reserved, acc.currency),
            "available_rule": "Disponible = comptabilisé − réservations actives (paiements approuvés non réglés)",
            "pending_operations": {
                "count": len(pend),
                "outgoing": money(sum(p.amount_minor for p in pend), acc.currency),
                "note": "Déjà couvertes par les réservations : non soustraites une seconde fois",
            },
            "source": "Registre HORIZON en partie double (simulé)",
            "observed_at": now.isoformat(),
            "freshness": {"age_hours": 0.0, "stale": False, "label": "Temps réel (registre)"},
        }
    snap = latest_snapshot(db, acc.id)
    if snap is None:
        return {"kind": "EXTERNAL_READONLY", "booked": None, "available": None, "reserved": None,
                "source": acc.provider, "observed_at": None, "freshness": {"stale": True, "age_hours": None},
                "note": "Aucun relevé reçu"}
    fr = freshness(snap.observed_at)
    return {
        "kind": "EXTERNAL_READONLY",
        "booked": money(snap.booked_minor, snap.currency),
        "available": money(snap.available_minor, snap.currency) if snap.available_minor is not None else None,
        "reserved": None,
        "available_rule": "Solde disponible tel que déclaré par la source externe (non recalculé par HORIZON)",
        "source": snap.source,
        "statement_reference": snap.statement_reference,
        "observed_at": snap.observed_at.isoformat(),
        "received_at": snap.received_at.isoformat(),
        "freshness": {**fr, "label": ("Données périmées" if fr["stale"] else "À jour")},
    }


def serialize_account(db: Session, acc: BankAccount, with_balance: bool = True) -> dict:
    ent = db.get(LegalEntity, acc.entity_id)
    out = {
        "id": str(acc.id),
        "name": acc.name,
        "entity": {"id": str(ent.id), "name": ent.name, "country_code": ent.country_code, "country_name": ent.country_name},
        "iban": acc.iban,
        "bic": acc.bic,
        "currency": acc.currency,
        "kind": acc.kind,
        "kind_label": "Compte simulé (registre HORIZON)" if acc.kind == "SIMULATED" else "Compte externe — lecture seule",
        "provider": acc.provider,
        "status": acc.status,
    }
    if with_balance:
        out["balance"] = balance_view(db, acc)
    return out


def consolidate(db: Session, principal, accounts: list[BankAccount] | None = None) -> dict:
    """Consolidation en devise de base avec taux identifiés et datés.

    Deux agrégats distincts : comptes simulés (disponible) et estimation
    consolidée incluant les soldes externes observés.
    """
    from horizon.modules.fx import service as fx

    base = get_settings().base_currency
    accounts = accounts if accounts is not None else visible_accounts(db, principal)
    simulated, external = [], []
    sim_total = 0
    ext_total = 0
    for acc in accounts:
        bv = balance_view(db, acc)
        if acc.kind == "SIMULATED":
            avail = bv["available"]["minor_units"]
            conv, ref = fx.convert(db, avail, acc.currency, base)
            sim_total += conv
            simulated.append({"account_id": str(acc.id), "account": acc.name, "currency": acc.currency,
                              "booked": bv["booked"], "reserved": bv["reserved"], "available": bv["available"],
                              "available_in_base": money(conv, base), "rate": ref})
        else:
            if bv.get("available") is None and bv.get("booked") is None:
                external.append({"account_id": str(acc.id), "account": acc.name, "missing": True})
                continue
            src = bv["available"] or bv["booked"]
            conv, ref = fx.convert(db, src["minor_units"], acc.currency, base)
            ext_total += conv
            external.append({"account_id": str(acc.id), "account": acc.name, "currency": acc.currency,
                             "observed": src, "observed_in_base": money(conv, base), "rate": ref,
                             "observed_at": bv["observed_at"], "source": bv["source"], "freshness": bv["freshness"]})
    return {
        "base_currency": base,
        "simulated_available": money(sim_total, base),
        "simulated_components": simulated,
        "external_observed": money(ext_total, base),
        "external_components": external,
        "consolidated_estimate": money(sim_total + ext_total, base),
        "method": "Chaque solde est converti individuellement au dernier taux daté disponible ; "
                  "aucune addition de montants de devises différentes.",
        "warnings": [
            f"{e['account']} : données périmées ({e['freshness']['age_hours']} h)"
            for e in external if not e.get("missing") and e["freshness"]["stale"]
        ],
    }
