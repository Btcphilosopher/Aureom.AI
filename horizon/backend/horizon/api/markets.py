from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from horizon.api.schemas import FinancingRequestIn, FinancingSimIn, FxQuoteIn
from horizon.core import clock
from horizon.core.context import Principal, get_principal
from horizon.core.errors import NotFound
from horizon.core.pagination import PageParams, paginate_list
from horizon.modules.financing import service as financing
from horizon.modules.financing.models import FinancingFacility, FinancingInstallment, FinancingRequest
from horizon.modules.fx import service as fx
from horizon.modules.fx.models import FxQuote, FxRate

router = APIRouter(prefix="/v1", tags=["Change et financement"])


@router.get("/fx/rates", tags=["Change"])
def rates(p: Principal = Depends(get_principal)):
    p.require_any("fx.read")
    fx.ensure_rates(p.db, clock.today())
    latest = p.db.scalars(select(FxRate).where(FxRate.as_of_date == clock.today())).all()
    return {"data": [fx.serialize_rate(r) for r in latest],
            "notice": "Taux synthétiques produits par un simulateur — non contractuels, sans lien avec le marché."}


@router.post("/fx-quotes", status_code=201, tags=["Change"])
def create_quote(body: FxQuoteIn, p: Principal = Depends(get_principal)):
    q = fx.create_quote(p.db, p, **body.model_dump())
    return fx.serialize_quote(q)


@router.get("/fx-quotes/{quote_id}", tags=["Change"])
def get_quote(quote_id: uuid.UUID, p: Principal = Depends(get_principal)):
    q = p.db.get(FxQuote, quote_id)
    if q is None or q.organization_id != p.org_id or not p.authz.can_see_entity("fx.read", q.entity_id):
        raise NotFound("Devis", quote_id)
    return fx.serialize_quote(q)


@router.post("/fx-quotes/{quote_id}/accept", tags=["Change"], summary="Accepter une offre exécutable SIMULÉE (aucun ordre réel)")
def accept_quote(quote_id: uuid.UUID, p: Principal = Depends(get_principal)):
    return fx.serialize_quote(fx.accept_quote(p.db, p, quote_id))


@router.get("/financing/facilities", tags=["Financement"])
def facilities(p: Principal = Depends(get_principal)):
    p.require_any("financing.read")
    rows = [f for f in p.db.scalars(select(FinancingFacility).where(FinancingFacility.organization_id == p.org_id))
            if p.authz.can_see_entity("financing.read", f.entity_id)]
    return {"data": [financing.serialize_facility(p.db, f) for f in rows]}


@router.get("/financing/facilities/{facility_id}", tags=["Financement"])
def facility(facility_id: uuid.UUID, p: Principal = Depends(get_principal)):
    f = p.db.get(FinancingFacility, facility_id)
    if f is None or f.organization_id != p.org_id or not p.authz.can_see_entity("financing.read", f.entity_id):
        raise NotFound("Contrat", facility_id)
    return financing.serialize_facility(p.db, f, detail=True)


@router.get("/financing/installments", tags=["Financement"])
def installments(page: PageParams = Depends(), p: Principal = Depends(get_principal)):
    p.require_any("financing.read")
    rows = p.db.scalars(select(FinancingInstallment).where(FinancingInstallment.organization_id == p.org_id)
                        .order_by(FinancingInstallment.due_date)).all()
    rows = [i for i in rows if p.authz.can_see_entity("financing.read", p.db.get(FinancingFacility, i.facility_id).entity_id)]
    return paginate_list([financing.serialize_installment(p.db, i) for i in rows], page)


@router.get("/financing/installments/{inst_id}", tags=["Financement"])
def installment(inst_id: uuid.UUID, p: Principal = Depends(get_principal)):
    i = p.db.get(FinancingInstallment, inst_id)
    if i is None or i.organization_id != p.org_id:
        raise NotFound("Échéance", inst_id)
    fac = p.db.get(FinancingFacility, i.facility_id)
    if not p.authz.can_see_entity("financing.read", fac.entity_id):
        raise NotFound("Échéance", inst_id)
    return {**financing.serialize_installment(p.db, i), "facility_detail": financing.serialize_facility(p.db, fac)}


@router.post("/financing/installments/{inst_id}/prepare", tags=["Financement"],
             summary="Préparer le paiement de l'échéance (circuit d'approbation normal)")
def prepare(inst_id: uuid.UUID, p: Principal = Depends(get_principal)):
    return financing.prepare_installment(p.db, p, inst_id)


@router.post("/financing/simulations", status_code=201, tags=["Financement"])
def simulate(body: FinancingSimIn, p: Principal = Depends(get_principal)):
    s = financing.simulate(p.db, p, body.model_dump())
    return {"id": str(s.id), "params": s.params, "result": s.result, "kind": "SIMULATION"}


@router.post("/financing/requests", status_code=201, tags=["Financement"])
def create_request(body: FinancingRequestIn, p: Principal = Depends(get_principal)):
    return financing.serialize_request(p.db, financing.create_request(p.db, p, body.model_dump()))


@router.get("/financing/requests", tags=["Financement"])
def list_requests(p: Principal = Depends(get_principal)):
    p.require_any("financing.read")
    rows = p.db.scalars(select(FinancingRequest).where(FinancingRequest.organization_id == p.org_id)).all()
    return {"data": [financing.serialize_request(p.db, r) for r in rows if p.authz.can_see_entity("financing.read", r.entity_id)]}
