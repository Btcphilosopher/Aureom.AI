"""Export d'un rapport de trésorerie accompagné de sa piste d'audit.

Archive ZIP : rapport.csv, piste_audit.csv, manifeste.json (empreintes SHA-256
de chaque fichier + état de vérification de la chaîne d'audit).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile

from sqlalchemy import select
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.money import fmt
from horizon.modules.accounts.service import consolidate, visible_accounts
from horizon.modules.audit import service as audit
from horizon.modules.audit.models import AuditEvent
from horizon.modules.payments.models import Payment, PaymentBatch
from horizon.modules.payments.state import PAYMENT_LABELS
from horizon.modules.reports.models import ReportExport


def _csv(rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8-sig")


def treasury_export(db: Session, principal) -> tuple[bytes, str, ReportExport]:
    principal.require_any("report.export")
    now = clock.now()
    cons = consolidate(db, principal, visible_accounts(db, principal))
    rows = [["HORIZON — ENVIRONNEMENT DE DÉMONSTRATION — données synthétiques"],
            [f"Généré le {now.isoformat()} par {principal.user.full_name}"], [],
            ["Section", "Compte", "Devise", "Comptabilisé", "Réservé", "Disponible", "Converti (EUR)", "Taux", "Date du taux", "Source du taux"]]
    for c in cons["simulated_components"]:
        rows.append(["Compte simulé", c["account"], c["currency"], c["booked"]["amount"], c["reserved"]["amount"],
                     c["available"]["amount"], c["available_in_base"]["amount"], c["rate"]["rate"], c["rate"]["as_of"], c["rate"]["source"]])
    for c in cons["external_components"]:
        if c.get("missing"):
            continue
        rows.append(["Compte externe (lecture seule)", c["account"], c["currency"], c["observed"]["amount"], "", "",
                     c["observed_in_base"]["amount"], c["rate"]["rate"], c["rate"]["as_of"], c["rate"]["source"]])
    rows += [[], ["Total disponible comptes simulés (EUR)", cons["simulated_available"]["amount"]],
             ["Estimation consolidée incluant externes (EUR)", cons["consolidated_estimate"]["amount"]], [],
             ["Lot", "Libellé", "Ligne", "Montant", "Devise", "Statut", "Référence bancaire", "Code rejet"]]
    for p in db.scalars(select(Payment).where(Payment.organization_id == principal.org_id).order_by(Payment.created_at)):
        if not principal.authz.has("payment.read", p.entity_id, p.debtor_account_id):
            continue
        b = db.get(PaymentBatch, p.batch_id)
        rows.append([b.reference, b.label, p.line_no, fmt(p.amount_minor, p.currency), p.currency, PAYMENT_LABELS[p.status],
                     p.bank_reference or "", p.rejection_code or ""])
    report = _csv(rows)
    evs = db.scalars(select(AuditEvent).where(AuditEvent.organization_id == principal.org_id).order_by(AuditEvent.id)).all()
    arows = [["id", "horodatage", "acteur", "action", "objet", "identifiant", "résultat", "détails", "hash_précédent", "hash"]]
    for e in evs:
        arows.append([e.id, e.at.isoformat(), e.actor_label, e.action, e.object_type or "", e.object_id or "", e.outcome,
                      json.dumps(e.details, ensure_ascii=False), e.prev_hash, e.hash])
    trail = _csv(arows)
    chain = audit.verify_chain(db, principal.org_id)
    manifest = {
        "generated_at": now.isoformat(), "generated_by": principal.user.full_name, "environment": "DÉMONSTRATION",
        "files": {"rapport.csv": hashlib.sha256(report).hexdigest(), "piste_audit.csv": hashlib.sha256(trail).hexdigest()},
        "audit_chain": chain, "audit_events": len(evs),
        "notice": "Concept indépendant — données synthétiques — aucun service bancaire réel.",
    }
    mbytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("rapport.csv", report)
        z.writestr("piste_audit.csv", trail)
        z.writestr("manifeste.json", mbytes)
    data = buf.getvalue()
    sha = hashlib.sha256(data).hexdigest()
    rec = ReportExport(organization_id=principal.org_id, kind="TREASURY_WITH_AUDIT", params={}, sha256=sha,
                       audit_event_count=len(evs), created_by=principal.user_id)
    db.add(rec)
    db.flush()
    principal.audit("report.exported", "report_export", rec.id, details={"sha256": sha, "audit_events": len(evs)})
    return data, f"horizon-rapport-{now.strftime('%Y%m%d-%H%M%S')}.zip", rec
