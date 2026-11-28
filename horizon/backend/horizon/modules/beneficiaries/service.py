"""Bénéficiaires versionnés.

* Création → version 1 « en revue » ; un approbateur distinct du créateur la valide.
* Modification matérielle (nom, IBAN, BIC, pays) → nouvelle version en revue,
  bénéficiaire repassé « en revue », et invalidation des approbations des lots
  qui référencent l'ancienne version (retour « À vérifier »).
* Modification mineure (adresse, courriel, catégorie) → nouvelle version qui
  hérite de l'approbation.
* Suspension → aucun paiement ne peut être exécuté vers ce bénéficiaire.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.errors import Conflict, DomainError, Forbidden, NotFound
from horizon.core.iban import check_format, normalize
from horizon.modules.beneficiaries.models import MATERIAL_FIELDS, Beneficiary, BeneficiaryVersion
from horizon.modules.identity.models import User

EDITABLE = ("name", "iban", "bic", "country_code", "address", "email", "category")


def _verification(iban: str, bic: str) -> dict:
    v = check_format(iban)
    return {
        "iban_format": v,
        "bic_format_valid": bool(bic) and len(bic) in (8, 11) and bic[:4].isalpha(),
        "name_match": {"status": "NOT_PERFORMED",
                       "note": "Aucun service de vérification du nom du bénéficiaire n'est intégré (simulation)."},
        "checked_at": clock.now().isoformat(),
    }


def get(db: Session, principal, bene_id: uuid.UUID, perm: str = "beneficiary.read") -> Beneficiary:
    b = db.get(Beneficiary, bene_id)
    if b is None or b.organization_id != principal.org_id:
        raise NotFound("Bénéficiaire", bene_id)
    if not principal.authz.can_see_entity(perm, b.entity_id):
        principal.denied(perm, entity_id=b.entity_id)
        raise Forbidden(f"Permission « {perm} » requise", {"permission": perm})
    return b


def create(db: Session, principal, data: dict) -> Beneficiary:
    entity_id = data["entity_id"]
    principal.require("beneficiary.write", entity_id)
    iban = normalize(data["iban"])
    ver = _verification(iban, data.get("bic", ""))
    if not ver["iban_format"]["format_valid"]:
        raise DomainError("IBAN_FORMAT_INVALID", "IBAN au format invalide", 422, ver["iban_format"])
    b = Beneficiary(organization_id=principal.org_id, entity_id=entity_id, status="PENDING_REVIEW",
                    created_by=principal.user_id)
    db.add(b)
    db.flush()
    v = BeneficiaryVersion(
        beneficiary_id=b.id, version_no=1, name=data["name"].strip(), iban=iban, bic=(data.get("bic") or "").upper(),
        country_code=data["country_code"].upper(), address=data.get("address", ""), email=data.get("email", ""),
        category=data.get("category", "Fournisseur"), created_by=principal.user_id, change_kind="CREATION",
        changed_fields=list(EDITABLE), review_status="PENDING", verification=ver,
    )
    db.add(v)
    db.flush()
    b.current_version_id = v.id
    db.flush()
    principal.audit("beneficiary.created", "beneficiary", b.id, entity_id=entity_id,
                    details={"name": v.name, "iban": iban, "version": 1})
    return b


def update(db: Session, principal, bene_id: uuid.UUID, changes: dict) -> Beneficiary:
    from horizon.modules.payments import service as payments

    b = db.get(Beneficiary, bene_id, with_for_update=True)
    if b is None or b.organization_id != principal.org_id:
        raise NotFound("Bénéficiaire", bene_id)
    principal.require("beneficiary.write", b.entity_id)
    if b.status == "REJECTED":
        raise Conflict("BENEFICIARY_REJECTED", "Bénéficiaire rejeté : créez-en un nouveau")
    cur = db.get(BeneficiaryVersion, b.current_version_id)
    new_vals = {f: getattr(cur, f) for f in EDITABLE}
    for k, v in changes.items():
        if k in EDITABLE and v is not None:
            new_vals[k] = normalize(v) if k == "iban" else (v.upper() if k in ("bic", "country_code") else v)
    changed = [f for f in EDITABLE if new_vals[f] != getattr(cur, f)]
    if not changed:
        return b
    material = [f for f in changed if f in MATERIAL_FIELDS]
    ver = _verification(new_vals["iban"], new_vals["bic"])
    if "iban" in material and not ver["iban_format"]["format_valid"]:
        raise DomainError("IBAN_FORMAT_INVALID", "IBAN au format invalide", 422, ver["iban_format"])
    no = (db.scalar(select(func.max(BeneficiaryVersion.version_no)).where(BeneficiaryVersion.beneficiary_id == b.id)) or 0) + 1
    v = BeneficiaryVersion(
        beneficiary_id=b.id, version_no=no, created_by=principal.user_id,
        change_kind="MATERIAL" if material else "MINOR", changed_fields=changed,
        review_status="PENDING" if material or b.approved_version_id is None else "INHERITED",
        verification=ver, **new_vals,
    )
    db.add(v)
    db.flush()
    b.current_version_id = v.id
    invalidated = []
    if material:
        if b.status != "SUSPENDED":
            b.status = "PENDING_REVIEW"
        invalidated = payments.on_beneficiary_material_change(db, principal, b, reason=(
            f"Modification matérielle du bénéficiaire ({', '.join(material)}) : nouvelle revue requise"))
    elif v.review_status == "INHERITED":
        b.approved_version_id = v.id
        # Les paiements en préparation sont repointés vers la version mineure (non matérielle).
        payments.repin_minor_version(db, b, v)
    db.flush()
    principal.audit("beneficiary.updated", "beneficiary", b.id, entity_id=b.entity_id,
                    details={"version": no, "changed_fields": changed, "material": bool(material),
                             "invalidated_batches": invalidated})
    return b


def review(db: Session, principal, bene_id: uuid.UUID, approve: bool, comment: str | None) -> Beneficiary:
    from horizon.modules.payments import service as payments

    b = db.get(Beneficiary, bene_id, with_for_update=True)
    if b is None or b.organization_id != principal.org_id:
        raise NotFound("Bénéficiaire", bene_id)
    principal.require("beneficiary.approve", b.entity_id)
    principal.require_step_up()
    v = db.get(BeneficiaryVersion, b.current_version_id)
    if v.review_status != "PENDING":
        raise Conflict("NOTHING_TO_REVIEW", "Aucune version en attente de revue")
    if v.created_by == principal.user_id:
        principal.denied("beneficiary.approve", entity_id=b.entity_id, action="beneficiary.review_denied",
                         details={"reason": "four_eyes"})
        raise Forbidden("Séparation des tâches : l'auteur d'une version ne peut pas la valider",
                        code="SEGREGATION_OF_DUTIES")
    v.review_status = "APPROVED" if approve else "REJECTED"
    v.reviewed_by = principal.user_id
    v.reviewed_at = clock.now()
    v.review_comment = comment
    if approve:
        b.approved_version_id = v.id
        if b.status != "SUSPENDED":
            b.status = "ACTIVE"
    else:
        b.status = "REJECTED" if b.approved_version_id is None else b.status
    db.flush()
    if approve:
        payments.repin_after_beneficiary_approval(db, b, v)
    principal.audit("beneficiary.approved" if approve else "beneficiary.review_rejected", "beneficiary", b.id,
                    entity_id=b.entity_id, details={"version": v.version_no, "comment": comment})
    return b


def set_suspension(db: Session, principal, bene_id: uuid.UUID, suspend: bool, reason: str) -> Beneficiary:
    from horizon.modules.payments import service as payments

    b = db.get(Beneficiary, bene_id, with_for_update=True)
    if b is None or b.organization_id != principal.org_id:
        raise NotFound("Bénéficiaire", bene_id)
    principal.require("beneficiary.approve", b.entity_id)
    principal.require_step_up()
    if suspend:
        b.status = "SUSPENDED"
        b.suspended_reason = reason
        invalidated = payments.on_beneficiary_material_change(db, principal, b, reason=f"Bénéficiaire suspendu : {reason}")
    else:
        if b.status != "SUSPENDED":
            raise Conflict("NOT_SUSPENDED", "Bénéficiaire non suspendu")
        v = db.get(BeneficiaryVersion, b.current_version_id)
        b.status = "ACTIVE" if v.review_status in ("APPROVED", "INHERITED") else "PENDING_REVIEW"
        b.suspended_reason = None
        invalidated = []
    db.flush()
    principal.audit("beneficiary.suspended" if suspend else "beneficiary.reactivated", "beneficiary", b.id,
                    entity_id=b.entity_id, details={"reason": reason, "invalidated_batches": invalidated})
    return b


STATUS_LABELS = {"PENDING_REVIEW": "En revue", "ACTIVE": "Actif", "SUSPENDED": "Suspendu", "REJECTED": "Rejeté"}


def serialize_version(db: Session, v: BeneficiaryVersion) -> dict:
    def uname(uid):
        u = db.get(User, uid) if uid else None
        return u.full_name if u else None

    return {
        "id": str(v.id), "version_no": v.version_no, "name": v.name, "iban": v.iban, "bic": v.bic,
        "country_code": v.country_code, "address": v.address, "email": v.email, "category": v.category,
        "change_kind": v.change_kind, "changed_fields": v.changed_fields, "review_status": v.review_status,
        "created_by": uname(v.created_by), "created_at": v.created_at.isoformat(),
        "reviewed_by": uname(v.reviewed_by), "reviewed_at": v.reviewed_at.isoformat() if v.reviewed_at else None,
        "review_comment": v.review_comment, "verification": v.verification,
    }


def serialize(db: Session, b: Beneficiary, with_history: bool = False) -> dict:
    from horizon.modules.organizations.models import LegalEntity

    cur = db.get(BeneficiaryVersion, b.current_version_id)
    ent = db.get(LegalEntity, b.entity_id)
    out = {
        "id": str(b.id), "entity": {"id": str(ent.id), "name": ent.name}, "status": b.status,
        "status_label": STATUS_LABELS[b.status], "suspended_reason": b.suspended_reason,
        "current_version": serialize_version(db, cur),
        "approved_version_id": str(b.approved_version_id) if b.approved_version_id else None,
        "pending_review": cur.review_status == "PENDING",
        "created_at": b.created_at.isoformat(),
    }
    if with_history:
        vs = db.scalars(select(BeneficiaryVersion).where(BeneficiaryVersion.beneficiary_id == b.id)
                        .order_by(BeneficiaryVersion.version_no.desc())).all()
        out["versions"] = [serialize_version(db, v) for v in vs]
    return out
