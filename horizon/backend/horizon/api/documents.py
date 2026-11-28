from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from horizon.api.schemas import TradeDeadlineIn, TradeDecisionIn, TradeFileIn, TradePartyIn, TradeRequestIn, TradeTaskIn, TradeTaskPatch
from horizon.core import clock
from horizon.core.context import Principal, get_principal
from horizon.core.db import get_db
from horizon.core.errors import NotFound
from horizon.core.money import money, to_minor
from horizon.core.pagination import PageParams, paginate_list
from horizon.modules.audit import service as audit
from horizon.modules.audit.models import AuditEvent
from horizon.modules.documents import service as docs
from horizon.modules.documents.models import Document
from horizon.modules.identity.models import User
from horizon.modules.trade.models import TradeDeadline, TradeDecision, TradeFile, TradeParty, TradeRequest, TradeTask

router = APIRouter(prefix="/v1", tags=["Documents et commerce international"])

TRADE_DISCLAIMER = ("Espace de gestion documentaire. HORIZON n'émet aucune garantie bancaire, aucun crédit documentaire "
                    "et aucune confirmation juridique : ces opérations exigent un processus institutionnel et des "
                    "intégrations appropriées, hors du périmètre de cette démonstration.")


@router.get("/documents")
def list_documents(page: PageParams = Depends(), trade_file_id: uuid.UUID | None = None, p: Principal = Depends(get_principal)):
    p.require_any("document.read")
    stmt = select(Document).where(Document.organization_id == p.org_id).order_by(Document.created_at.desc())
    if trade_file_id:
        stmt = stmt.where(Document.trade_file_id == trade_file_id)
    rows = [d for d in p.db.scalars(stmt) if p.authz.can_see_entity("document.read", d.entity_id)]
    return paginate_list([docs.serialize(p.db, d) for d in rows], page)


@router.post("/documents", status_code=201)
async def upload(file: UploadFile = File(...), entity_id: uuid.UUID = Form(...), title: str = Form(...),
                 category: str = Form("Divers"), trade_file_id: uuid.UUID | None = Form(None),
                 p: Principal = Depends(get_principal)):
    p.require("document.write", entity_id)
    data = await file.read()
    d = docs.store(p.db, org_id=p.org_id, entity_id=entity_id, title=title[:300], category=category[:100],
                   filename=file.filename or "document", content_type=file.content_type or "", data=data,
                   uploaded_by=p.user_id, trade_file_id=trade_file_id)
    p.audit("document.uploaded", "document", d.id, entity_id=entity_id, details={"sha256": d.sha256, "size": d.size_bytes})
    return docs.serialize(p.db, d)


@router.post("/documents/{doc_id}/links", summary="Lien de téléchargement temporaire signé")
def link(doc_id: uuid.UUID, p: Principal = Depends(get_principal)):
    return docs.make_link(p.db, p, doc_id)


@router.get("/documents/content", summary="Téléchargement via lien temporaire (droits revérifiés)")
def content(token: str = Query(..., max_length=500), db: Session = Depends(get_db)):
    d, u = docs.resolve_link(db, token)
    data = docs.read(d)
    audit.record(db, organization_id=d.organization_id, actor_user_id=u.id, actor_label=u.full_name,
                 action="document.downloaded", object_type="document", object_id=d.id, entity_id=d.entity_id)
    return Response(content=data, media_type=d.content_type,
                    headers={"Content-Disposition": f'attachment; filename="{d.filename}"', "Cache-Control": "no-store",
                             "X-Content-Type-Options": "nosniff"})


# ---------------------------------------------------------------- commerce international

def _file(p: Principal, file_id: uuid.UUID, perm="trade.read") -> TradeFile:
    f = p.db.get(TradeFile, file_id)
    if f is None or f.organization_id != p.org_id or not p.authz.can_see_entity("trade.read", f.entity_id):
        raise NotFound("Dossier", file_id)
    if perm != "trade.read":
        p.require(perm, f.entity_id)
    return f


def _uname(db, uid):
    u = db.get(User, uid) if uid else None
    return u.full_name if u else None


def _ser_file(p: Principal, f: TradeFile, detail=False) -> dict:
    db = p.db
    out = {"id": str(f.id), "reference": f.reference, "title": f.title, "direction": f.direction,
           "instrument_considered": f.instrument_considered, "status": f.status, "entity_id": str(f.entity_id),
           "amount": money(f.amount_minor, f.currency) if f.amount_minor is not None else None,
           "owner": _uname(db, f.owner_user_id), "created_at": f.created_at.isoformat(), "disclaimer": TRADE_DISCLAIMER}
    if detail:
        q = lambda M: db.scalars(select(M).where(M.trade_file_id == f.id).order_by(M.created_at)).all()  # noqa: E731
        out["parties"] = [{"id": str(x.id), "role": x.role, "name": x.name, "country_code": x.country_code} for x in q(TradeParty)]
        out["deadlines"] = [{"id": str(x.id), "label": x.label, "due_date": x.due_date.isoformat(), "status": x.status,
                             "days_left": (x.due_date - clock.today()).days} for x in q(TradeDeadline)]
        out["requests"] = [{"id": str(x.id), "kind": x.kind, "body": x.body, "status": x.status,
                            "status_label": {"DRAFT": "Brouillon", "SENT_SIMULATED": "Transmise (simulation) — aucun engagement"}.get(x.status, x.status),
                            "created_by": _uname(db, x.created_by), "sent_at": x.sent_at.isoformat() if x.sent_at else None} for x in q(TradeRequest)]
        out["tasks"] = [{"id": str(x.id), "label": x.label, "status": x.status, "assignee": _uname(db, x.assignee_user_id),
                         "due_date": x.due_date.isoformat() if x.due_date else None} for x in q(TradeTask)]
        out["decisions"] = [{"id": str(x.id), "label": x.label, "rationale": x.rationale, "decided_by": _uname(db, x.decided_by),
                             "at": x.created_at.isoformat()} for x in q(TradeDecision)]
        out["documents"] = [docs.serialize(db, d) for d in db.scalars(select(Document).where(Document.trade_file_id == f.id))]
        ids = [str(f.id)] + [x["id"] for k in ("requests", "tasks", "decisions", "documents", "deadlines", "parties") for x in out[k]]
        evs = db.scalars(select(AuditEvent).where(AuditEvent.organization_id == p.org_id, AuditEvent.object_id.in_(ids))
                         .order_by(AuditEvent.id.desc()).limit(50)).all()
        out["history"] = [{"at": e.at.isoformat(), "actor": e.actor_label, "action": e.action, "object_type": e.object_type}
                          for e in evs]
    return out


@router.get("/trade-files")
def list_files(p: Principal = Depends(get_principal)):
    p.require_any("trade.read")
    rows = [f for f in p.db.scalars(select(TradeFile).where(TradeFile.organization_id == p.org_id).order_by(TradeFile.created_at))
            if p.authz.can_see_entity("trade.read", f.entity_id)]
    return {"data": [_ser_file(p, f) for f in rows], "disclaimer": TRADE_DISCLAIMER}


@router.post("/trade-files", status_code=201)
def create_file(body: TradeFileIn, p: Principal = Depends(get_principal)):
    p.require("trade.write", body.entity_id)
    n = len(p.db.scalars(select(TradeFile.id).where(TradeFile.organization_id == p.org_id)).all()) + 1
    f = TradeFile(organization_id=p.org_id, entity_id=body.entity_id, reference=f"{body.direction[:3]}-{clock.today().year}-{n:03d}",
                  title=body.title, direction=body.direction, instrument_considered=body.instrument_considered,
                  amount_minor=to_minor(body.amount, body.currency) if body.amount and body.currency else None,
                  currency=body.currency, owner_user_id=p.user_id)
    p.db.add(f)
    p.db.flush()
    p.audit("trade.file_created", "trade_file", f.id, entity_id=f.entity_id, details={"title": f.title})
    return _ser_file(p, f, True)


@router.get("/trade-files/{file_id}")
def get_file(file_id: uuid.UUID, p: Principal = Depends(get_principal)):
    return _ser_file(p, _file(p, file_id), True)


def _add(p, file_id, obj, action):
    f = _file(p, file_id, "trade.write")
    obj.trade_file_id = f.id
    p.db.add(obj)
    p.db.flush()
    p.audit(action, obj.__tablename__[:-1], obj.id, entity_id=f.entity_id)
    return _ser_file(p, f, True)


@router.post("/trade-files/{file_id}/tasks")
def add_task(file_id: uuid.UUID, body: TradeTaskIn, p: Principal = Depends(get_principal)):
    return _add(p, file_id, TradeTask(**body.model_dump()), "trade.task_added")


@router.patch("/trade-files/{file_id}/tasks/{task_id}")
def patch_task(file_id: uuid.UUID, task_id: uuid.UUID, body: TradeTaskPatch, p: Principal = Depends(get_principal)):
    f = _file(p, file_id, "trade.write")
    t = p.db.get(TradeTask, task_id)
    if t is None or t.trade_file_id != f.id:
        raise NotFound("Tâche", task_id)
    t.status = body.status
    p.audit("trade.task_updated", "trade_task", t.id, entity_id=f.entity_id, details={"status": body.status})
    return _ser_file(p, f, True)


@router.post("/trade-files/{file_id}/requests")
def add_request(file_id: uuid.UUID, body: TradeRequestIn, p: Principal = Depends(get_principal)):
    return _add(p, file_id, TradeRequest(kind=body.kind, body=body.body, created_by=p.user_id, status="SENT_SIMULATED",
                                         sent_at=clock.now()), "trade.request_sent_simulated")


@router.post("/trade-files/{file_id}/decisions")
def add_decision(file_id: uuid.UUID, body: TradeDecisionIn, p: Principal = Depends(get_principal)):
    return _add(p, file_id, TradeDecision(**body.model_dump(), decided_by=p.user_id), "trade.decision_recorded")


@router.post("/trade-files/{file_id}/deadlines")
def add_deadline(file_id: uuid.UUID, body: TradeDeadlineIn, p: Principal = Depends(get_principal)):
    return _add(p, file_id, TradeDeadline(**body.model_dump()), "trade.deadline_added")


@router.post("/trade-files/{file_id}/parties")
def add_party(file_id: uuid.UUID, body: TradePartyIn, p: Principal = Depends(get_principal)):
    return _add(p, file_id, TradeParty(**body.model_dump()), "trade.party_added")
