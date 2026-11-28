"""Vue d'ensemble : chaque indicateur est calculé depuis les données et
accompagné de sa justification (formule, composantes, sources, exclusions)."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.config import get_settings
from horizon.core.money import money
from horizon.modules.accounts.service import consolidate, visible_accounts
from horizon.modules.decisions import service as decisions
from horizon.modules.forecasting.models import ExpectedReceipt
from horizon.modules.fx import service as fx
from horizon.modules.payments.models import Payment, PaymentBatch
from horizon.modules.payments.service import serialize_payment


def kpis(db: Session, principal) -> dict:
    base = get_settings().base_currency
    today = clock.today()
    accounts = visible_accounts(db, principal)
    cons = consolidate(db, principal, accounts)

    # 2. Paiements à approuver
    pend_batches = [b for b in db.scalars(select(PaymentBatch).where(PaymentBatch.organization_id == principal.org_id,
                                                                    PaymentBatch.status == "PENDING_APPROVAL"))
                    if principal.authz.has("payment.read", b.entity_id, b.debtor_account_id)]
    pend_components, pend_total, pend_count = [], 0, 0
    for b in pend_batches:
        conv, ref = fx.convert(db, b.total_minor, b.currency, base)
        pend_total += conv
        pend_count += b.payment_count
        pend_components.append({"batch_id": str(b.id), "reference": b.reference, "label": b.label,
                                "payment_count": b.payment_count, "total": money(b.total_minor, b.currency),
                                "total_in_base": money(conv, base), "rate": ref})

    # 3. Encaissements attendus 7 jours
    acc_ids = {a.id for a in accounts if a.kind == "SIMULATED"}
    rec_components, rec_total = [], 0
    for r in db.scalars(select(ExpectedReceipt).where(ExpectedReceipt.organization_id == principal.org_id,
                                                      ExpectedReceipt.status == "EXPECTED",
                                                      ExpectedReceipt.expected_date >= today,
                                                      ExpectedReceipt.expected_date <= today + timedelta(days=7))
                        .order_by(ExpectedReceipt.expected_date)):
        if r.account_id not in acc_ids:
            continue
        conv, ref = fx.convert(db, r.amount_minor, r.currency, base)
        rec_total += conv
        rec_components.append({"id": str(r.id), "counterparty": r.counterparty, "reference": r.reference,
                               "expected_date": r.expected_date.isoformat(), "confidence": r.confidence,
                               "amount": money(r.amount_minor, r.currency), "amount_in_base": money(conv, base), "rate": ref})

    # 4. Alertes
    items = decisions.items(db, principal)
    alerts = [i for i in items if i["is_alert"]]

    return {
        "as_of": clock.now().isoformat(),
        "base_currency": base,
        "kpis": [
            {
                "key": "available_liquidity", "label": "Liquidités disponibles",
                "value": cons["simulated_available"],
                "explain": {
                    "formula": "Σ (solde comptabilisé − réservations actives) des comptes SIMULÉS, chaque solde converti "
                               "en EUR au dernier taux daté",
                    "components": cons["simulated_components"],
                    "excluded": [{"account": e["account"], "reason": "Compte externe en lecture seule : présenté à part",
                                  "observed_in_base": e.get("observed_in_base"), "freshness": e.get("freshness")}
                                 for e in cons["external_components"]],
                    "consolidated_estimate_including_external": cons["consolidated_estimate"],
                    "warnings": cons["warnings"],
                    "sources": ["Registre HORIZON en partie double (simulé)", "Taux : simulateur de taux synthétique"],
                },
            },
            {
                "key": "payments_to_approve", "label": "Paiements à approuver",
                "value": {"count": pend_count, "total": money(pend_total, base)},
                "explain": {"formula": "Paiements des lots à l'état « En attente d'approbation » visibles par vous",
                            "components": pend_components, "sources": ["Module Paiements"]},
            },
            {
                "key": "expected_receipts_7d", "label": "Encaissements attendus", "sublabel": "7 prochains jours",
                "value": money(rec_total, base),
                "explain": {"formula": f"Σ encaissements attendus (état EXPECTED) datés du {today.isoformat()} au "
                                       f"{(today + timedelta(days=7)).isoformat()}, comptes simulés",
                            "components": rec_components,
                            "note": "Un encaissement rapproché d'un crédit réel passe à « reçu » et sort de cet indicateur.",
                            "sources": ["Module Prévisions — encaissements attendus"]},
            },
            {
                "key": "alerts", "label": "Alertes à examiner", "value": {"count": len(alerts)},
                "explain": {"formula": "Éléments du centre de décisions hors approbations courantes : bénéficiaires en revue, "
                                       "rejets non traités, écarts de rapprochement, résultats inconnus, données périmées, "
                                       "échéances de financement à 30 jours",
                            "components": [{"key": i["key"], "title": i["title"], "subtitle": i["subtitle"],
                                            "source": i["source"], "owner": i["owner"], "due_date": i["due_date"],
                                            "state": i["state"]} for i in alerts],
                            "sources": ["Centre de décisions"]},
            },
        ],
    }


def overview(db: Session, principal) -> dict:
    from horizon.modules.accounts.service import serialize_account

    data = kpis(db, principal)
    accounts = visible_accounts(db, principal)
    data["accounts"] = [serialize_account(db, a) for a in accounts]
    data["decisions"] = decisions.items(db, principal)[:6]
    recent = db.scalars(select(Payment).where(Payment.organization_id == principal.org_id)
                        .order_by(Payment.created_at.desc()).limit(40)).all()
    data["recent_payments"] = [serialize_payment(db, p) for p in recent
                               if principal.authz.has("payment.read", p.entity_id, p.debtor_account_id)][:8]
    data["environment"] = {"label": "ENVIRONNEMENT DE DÉMONSTRATION",
                           "notice": "Concept indépendant · Données synthétiques · Aucun service bancaire réel"}
    return data
