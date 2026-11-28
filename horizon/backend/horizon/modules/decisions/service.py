"""Centre de décisions : éléments calculés depuis leurs sources.

Chaque élément indique source, responsable, échéance et état. L'accusé de
réception est tracé mais ne modifie jamais l'état de la cause : l'élément
disparaît uniquement quand la cause est traitée dans son module d'origine.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.errors import DomainError
from horizon.core.money import money
from horizon.modules.accounts.models import BankAccount
from horizon.modules.accounts.service import freshness, latest_snapshot, visible_accounts
from horizon.modules.approvals import service as approvals
from horizon.modules.beneficiaries.models import Beneficiary, BeneficiaryVersion
from horizon.modules.decisions.models import DecisionAcknowledgement
from horizon.modules.financing.models import FinancingFacility, FinancingInstallment
from horizon.modules.identity.models import User
from horizon.modules.payments.models import Payment, PaymentBatch
from horizon.modules.reconciliation.models import ReconciliationCase
from horizon.modules.reconciliation.service import KIND_LABELS

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
KIND_ORDER = {"PAYMENT_REJECTED": 0, "UNKNOWN_PAYMENT_RESULT": 1, "BATCH_APPROVAL": 2, "BENEFICIARY_REVIEW": 3,
              "FINANCING_DEADLINE": 4, "MISSING_IN_LEDGER": 5, "MISSING_IN_STATEMENT": 5, "AMOUNT_MISMATCH": 5,
              "STALE_DATA": 6}


def _uname(db, uid):
    u = db.get(User, uid) if uid else None
    return u.full_name if u else None


def items(db: Session, principal) -> list[dict]:
    a = principal.authz
    out: list[dict] = []
    today = clock.today()

    # 1. Lots en attente d'approbation
    for b in db.scalars(select(PaymentBatch).where(PaymentBatch.organization_id == principal.org_id,
                                                   PaymentBatch.status == "PENDING_APPROVAL")):
        if not a.has("payment.read", b.entity_id, b.debtor_account_id):
            continue
        valid = len({x.approver_user_id for x in approvals.valid_approvals(db, b)})
        req = b.required_approvals or 1
        elig = approvals.eligible_approvers(db, b)
        out.append({
            "key": f"batch-approval:{b.id}:{b.version}", "kind": "BATCH_APPROVAL", "severity": "warning", "is_alert": False,
            "title": b.label, "subtitle": f"{money(b.total_minor, b.currency)['amount']} {b.currency} · "
                                          f"{req - valid} validation{'s' if req - valid > 1 else ''} requise{'s' if req - valid > 1 else ''}",
            "amount": money(b.total_minor, b.currency), "source": {"module": "Paiements", "object_type": "payment_batch",
                                                                   "object_id": str(b.id), "reference": b.reference},
            "owner": ", ".join(e["name"] for e in elig) or "Aucun approbateur éligible",
            "due_date": b.execution_date.isoformat(), "state": f"{valid}/{req} validations",
            "action": {"label": "Examiner", "href": f"/paiements/lots/{b.id}"},
        })
    # 2. Bénéficiaires créés ou modifiés en attente de revue
    for bene in db.scalars(select(Beneficiary).where(Beneficiary.organization_id == principal.org_id)):
        v = db.get(BeneficiaryVersion, bene.current_version_id)
        if v.review_status != "PENDING" or not a.can_see_entity("beneficiary.read", bene.entity_id):
            continue
        modified = v.version_no > 1
        out.append({
            "key": f"beneficiary-review:{bene.id}:{v.version_no}", "kind": "BENEFICIARY_REVIEW", "severity": "warning",
            "is_alert": True, "title": "Bénéficiaire modifié" if modified else "Nouveau bénéficiaire",
            "subtitle": f"{v.name} — contrôle complémentaire requis" + (f" ({', '.join(v.changed_fields)})" if modified else ""),
            "source": {"module": "Paiements › Bénéficiaires", "object_type": "beneficiary", "object_id": str(bene.id)},
            "owner": "Approbateurs de l'entité", "due_date": (v.created_at.date() + timedelta(days=2)).isoformat(),
            "state": "En revue", "action": {"label": "Vérifier", "href": f"/paiements/beneficiaires/{bene.id}"},
        })
    # 3. Échéances de financement à préparer (30 jours)
    for inst in db.scalars(select(FinancingInstallment).where(FinancingInstallment.organization_id == principal.org_id,
                                                              FinancingInstallment.status == "TO_PREPARE",
                                                              FinancingInstallment.due_date <= today + timedelta(days=30))):
        fac = db.get(FinancingFacility, inst.facility_id)
        if not a.can_see_entity("financing.read", fac.entity_id):
            continue
        out.append({
            "key": f"financing-installment:{inst.id}", "kind": "FINANCING_DEADLINE",
            "severity": "critical" if inst.due_date <= today + timedelta(days=5) else "warning", "is_alert": True,
            "title": "Échéance de financement",
            "subtitle": f"{inst.due_date.strftime('%d/%m/%Y')} · À préparer · {fac.label}",
            "amount": money(inst.principal_minor + inst.interest_minor, inst.currency),
            "source": {"module": "Financement", "object_type": "financing_installment", "object_id": str(inst.id)},
            "owner": _uname(db, inst.owner_user_id) or "Trésorerie", "due_date": inst.due_date.isoformat(),
            "state": "À préparer", "action": {"label": "Consulter", "href": f"/financement?echeance={inst.id}"},
        })
    # 4. Paiements rejetés non traités
    for p in db.scalars(select(Payment).where(Payment.organization_id == principal.org_id, Payment.status == "REJECTED",
                                              Payment.rejection_resolved_at.is_(None))):
        if not a.has("payment.read", p.entity_id, p.debtor_account_id):
            continue
        b = db.get(PaymentBatch, p.batch_id)
        v = db.get(BeneficiaryVersion, p.beneficiary_version_id)
        out.append({
            "key": f"payment-rejected:{p.id}", "kind": "PAYMENT_REJECTED", "severity": "critical", "is_alert": True,
            "title": "Paiement rejeté", "subtitle": f"{v.name} · {money(p.amount_minor, p.currency)['amount']} {p.currency} · motif {p.rejection_code}",
            "amount": money(p.amount_minor, p.currency),
            "source": {"module": "Paiements", "object_type": "payment", "object_id": str(p.id), "reference": b.reference},
            "owner": _uname(db, p.created_by), "due_date": (p.rejected_at.date() + timedelta(days=1)).isoformat() if p.rejected_at else None,
            "state": "Rejet à traiter", "action": {"label": "Traiter", "href": f"/paiements/{p.id}"},
        })
    # 5. Résultats inconnus et écarts de rapprochement
    for c in db.scalars(select(ReconciliationCase).where(ReconciliationCase.organization_id == principal.org_id,
                                                         ReconciliationCase.status != "RESOLVED")):
        if not a.has("reconciliation.read", c.entity_id, c.account_id):
            continue
        acc = db.get(BankAccount, c.account_id)
        out.append({
            "key": f"reconciliation:{c.id}", "kind": c.kind, "severity": "critical" if c.kind == "UNKNOWN_PAYMENT_RESULT" else "warning",
            "is_alert": True, "title": KIND_LABELS[c.kind], "subtitle": f"{acc.name} · {c.description}"[:160],
            "source": {"module": "Rapprochement", "object_type": "reconciliation_case", "object_id": str(c.id)},
            "owner": _uname(db, c.owner_user_id) or "Trésorerie", "due_date": c.due_date.isoformat() if c.due_date else None,
            "state": {"OPEN": "Ouvert", "ACKNOWLEDGED": "Pris en compte — cause non résolue"}[c.status],
            "action": {"label": "Analyser", "href": f"/tresorerie/rapprochement?cas={c.id}"},
        })
    # 6. Données externes périmées
    for acc in visible_accounts(db, principal):
        if acc.kind != "EXTERNAL_READONLY":
            continue
        snap = latest_snapshot(db, acc.id)
        fr = freshness(snap.observed_at) if snap else {"stale": True, "age_hours": None}
        if fr["stale"]:
            out.append({
                "key": f"stale-data:{acc.id}:{snap.id if snap else 'none'}", "kind": "STALE_DATA", "severity": "warning",
                "is_alert": True, "title": "Données périmées",
                "subtitle": f"{acc.name} · dernier relevé il y a {fr['age_hours']} h" if snap else f"{acc.name} · aucun relevé",
                "source": {"module": "Comptes", "object_type": "bank_account", "object_id": str(acc.id), "provider": acc.provider},
                "owner": "Administration (intégrations)",
                "due_date": clock.today().isoformat(), "state": "Relevé attendu",
                "action": {"label": "Consulter", "href": f"/comptes/{acc.id}"},
            })
    acks: dict[str, list] = {}
    for ack in db.scalars(select(DecisionAcknowledgement).where(DecisionAcknowledgement.organization_id == principal.org_id)):
        acks.setdefault(ack.item_key, []).append({"by": _uname(db, ack.user_id), "at": ack.created_at.isoformat(), "note": ack.note})
    for it in out:
        it["acknowledgements"] = acks.get(it["key"], [])
    out.sort(key=lambda x: (SEVERITY_ORDER[x["severity"]], KIND_ORDER.get(x["kind"], 9), x["due_date"] or "9999"))
    return out


def acknowledge(db: Session, principal, key: str, note: str | None) -> dict:
    principal.require_any("decision.read")
    keys = {i["key"]: i for i in items(db, principal)}
    if key not in keys:
        raise DomainError("NOT_FOUND", "Élément inconnu ou déjà résolu", 404)
    db.add(DecisionAcknowledgement(organization_id=principal.org_id, item_key=key, user_id=principal.user_id, note=note))
    db.flush()
    principal.audit("decision.acknowledged", "decision_item", key, details={"note": note})
    return {"key": key, "acknowledged": True, "resolved": False,
            "note": "Accusé de réception enregistré — la cause reste à traiter dans son module d'origine."}
