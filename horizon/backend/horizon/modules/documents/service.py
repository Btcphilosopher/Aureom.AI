"""Documents : téléversement contrôlé, empreinte SHA-256, liens temporaires signés."""
from __future__ import annotations

import hashlib
import time
import uuid

from sqlalchemy.orm import Session

from horizon.core.config import get_settings
from horizon.core.crypto import sign, verify_signature
from horizon.core.errors import DomainError, Forbidden, NotFound
from horizon.modules.documents.models import Document
from horizon.modules.documents.storage import storage
from horizon.modules.identity.models import User

ALLOWED_TYPES = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg", "text/csv": ".csv",
                 "text/plain": ".txt", "application/xml": ".xml"}
MAX_BYTES = 10 * 1024 * 1024
SIGNATURES = {"application/pdf": b"%PDF", "image/png": b"\x89PNG", "image/jpeg": b"\xff\xd8"}


def store(db: Session, *, org_id, entity_id, title, category, filename, content_type, data: bytes, uploaded_by=None,
          trade_file_id=None, facility_id=None, source="UPLOAD") -> Document:
    if content_type not in ALLOWED_TYPES:
        raise DomainError("UNSUPPORTED_TYPE", f"Type non autorisé : {content_type}", 415)
    if len(data) == 0 or len(data) > MAX_BYTES:
        raise DomainError("INVALID_SIZE", "Fichier vide ou supérieur à 10 Mo", 413)
    magic = SIGNATURES.get(content_type)
    if magic and not data.startswith(magic):
        raise DomainError("CONTENT_MISMATCH", "Le contenu ne correspond pas au type déclaré", 415)
    doc_id = uuid.uuid4()
    key = f"{org_id}/{doc_id}"
    storage().put(key, data)
    d = Document(id=doc_id, organization_id=org_id, entity_id=entity_id, trade_file_id=trade_file_id,
                 facility_id=facility_id, title=title, category=category, filename=filename[:300],
                 content_type=content_type, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                 storage_key=key, source=source, uploaded_by=uploaded_by)
    db.add(d)
    db.flush()
    return d


def get_visible(db: Session, principal, doc_id) -> Document:
    d = db.get(Document, doc_id)
    if d is None or d.organization_id != principal.org_id:
        raise NotFound("Document", doc_id)
    if not principal.authz.can_see_entity("document.read", d.entity_id):
        principal.denied("document.read", entity_id=d.entity_id, details={"document_id": str(doc_id)})
        raise Forbidden("Accès au document refusé", {"permission": "document.read"})
    return d


def make_link(db: Session, principal, doc_id) -> dict:
    d = get_visible(db, principal, doc_id)
    exp = int(time.time()) + get_settings().document_link_ttl_seconds
    msg = f"{d.id}:{principal.user_id}:{exp}"
    token = f"{d.id}.{principal.user_id}.{exp}.{sign('document-link', msg)}"
    principal.audit("document.link_created", "document", d.id, entity_id=d.entity_id, details={"expires": exp})
    return {"url": f"/v1/documents/content?token={token}", "expires_at_epoch": exp,
            "ttl_seconds": get_settings().document_link_ttl_seconds}


def resolve_link(db: Session, token: str) -> tuple[Document, User]:
    try:
        doc_id, user_id, exp, sig = token.split(".")
        exp_i = int(exp)
    except ValueError as exc:
        raise DomainError("INVALID_LINK", "Lien invalide", 403) from exc
    if not verify_signature("document-link", f"{doc_id}:{user_id}:{exp}", sig):
        raise DomainError("INVALID_LINK", "Lien invalide", 403)
    if exp_i < time.time():
        raise DomainError("LINK_EXPIRED", "Lien expiré", 403)
    d = db.get(Document, uuid.UUID(doc_id))
    u = db.get(User, uuid.UUID(user_id))
    if d is None or u is None or u.organization_id != d.organization_id or not u.is_active:
        raise DomainError("INVALID_LINK", "Lien invalide", 403)
    # Les droits sont revérifiés au moment du téléchargement.
    from horizon.modules.organizations.permissions import Authz

    if not Authz.load(db, u.id, u.organization_id).can_see_entity("document.read", d.entity_id):
        raise Forbidden("Droits retirés depuis la création du lien")
    return d, u


def read(d: Document) -> bytes:
    data = storage().get(d.storage_key)
    if hashlib.sha256(data).hexdigest() != d.sha256:
        raise DomainError("INTEGRITY_ERROR", "Empreinte du document incohérente", 500)
    return data


def serialize(db, d: Document) -> dict:
    u = db.get(User, d.uploaded_by) if d.uploaded_by else None
    return {"id": str(d.id), "title": d.title, "category": d.category, "filename": d.filename,
            "content_type": d.content_type, "size_bytes": d.size_bytes, "sha256": d.sha256, "source": d.source,
            "entity_id": str(d.entity_id), "trade_file_id": str(d.trade_file_id) if d.trade_file_id else None,
            "facility_id": str(d.facility_id) if d.facility_id else None,
            "uploaded_by": u.full_name if u else "Données de démonstration", "uploaded_at": d.created_at.isoformat()}
