from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from horizon.api.schemas import AckIn, ForecastIn, ReconAckIn, ReconResolveIn, ReconRunIn, ScenarioIn
from horizon.core import clock
from horizon.core.context import Principal, get_principal
from horizon.core.errors import Conflict, NotFound
from horizon.core.money import money
from horizon.core.pagination import PageParams, paginate_list
from horizon.modules.accounts.models import BankAccount
from horizon.modules.decisions import service as decisions
from horizon.modules.forecasting import service as forecasting
from horizon.modules.forecasting.models import CashflowScenario, ExpectedReceipt, ForecastRun, RecurringAssumption
from horizon.modules.reconciliation import service as reco
from horizon.modules.reconciliation.models import ReconciliationCase

router = APIRouter(prefix="/v1", tags=["Trésorerie"])


@router.get("/cashflow-scenarios")
def list_scenarios(p: Principal = Depends(get_principal)):
    p.require_any("forecast.read")
    rows = p.db.scalars(select(CashflowScenario).where(CashflowScenario.organization_id == p.org_id)
                        .order_by(CashflowScenario.created_at)).all()
    return {"data": [forecasting.serialize_scenario(s) for s in rows]}


@router.post("/cashflow-scenarios", status_code=201)
def create_scenario(body: ScenarioIn, p: Principal = Depends(get_principal)):
    p.require_any("forecast.write")
    if forecasting.scenario_by_code(p.db, p.org_id, body.code):
        raise Conflict("SCENARIO_EXISTS", "Code de scénario déjà utilisé")
    s = CashflowScenario(organization_id=p.org_id, created_by=p.user_id, **body.model_dump())
    p.db.add(s)
    p.db.flush()
    p.audit("forecast.scenario_created", "cashflow_scenario", s.id, details=body.model_dump())
    return forecasting.serialize_scenario(s)


@router.post("/forecasts", status_code=201, summary="Calculer et figer une prévision explicable")
def run_forecast(body: ForecastIn, p: Principal = Depends(get_principal)):
    p.require_any("forecast.read")
    fr = forecasting.run_and_store(p.db, p, body.scenario_id, body.horizon_days)
    return forecasting.serialize_run(fr, p.db.get(CashflowScenario, fr.scenario_id))


@router.get("/forecasts/chart", summary="Historique observé, prévision centrale et fourchette de scénarios")
def forecast_chart(horizon_days: int = Query(90), p: Principal = Depends(get_principal)):
    p.require_any("forecast.read")
    return forecasting.chart(p.db, p, horizon_days)


@router.get("/forecasts/{forecast_id}")
def get_forecast(forecast_id: uuid.UUID, p: Principal = Depends(get_principal)):
    p.require_any("forecast.read")
    fr = p.db.get(ForecastRun, forecast_id)
    if fr is None or fr.organization_id != p.org_id:
        raise NotFound("Prévision", forecast_id)
    return forecasting.serialize_run(fr, p.db.get(CashflowScenario, fr.scenario_id))


@router.get("/expected-receipts")
def expected_receipts(page: PageParams = Depends(), p: Principal = Depends(get_principal)):
    p.require_any("forecast.read")
    rows = p.db.scalars(select(ExpectedReceipt).where(ExpectedReceipt.organization_id == p.org_id)
                        .order_by(ExpectedReceipt.expected_date)).all()
    data = []
    for r in rows:
        acc = p.db.get(BankAccount, r.account_id)
        if not p.authz.can_see_account("forecast.read", acc.entity_id, acc.id):
            continue
        data.append({"id": str(r.id), "counterparty": r.counterparty, "reference": r.reference,
                     "amount": money(r.amount_minor, r.currency), "expected_date": r.expected_date.isoformat(),
                     "confidence": r.confidence, "status": r.status, "account": acc.name,
                     "matched_entry_id": str(r.matched_entry_id) if r.matched_entry_id else None})
    return paginate_list(data, page)


@router.get("/recurring-assumptions")
def recurring(p: Principal = Depends(get_principal)):
    p.require_any("forecast.read")
    rows = p.db.scalars(select(RecurringAssumption).where(RecurringAssumption.organization_id == p.org_id)).all()
    return {"data": [{"id": str(a.id), "label": a.label, "category": a.category, "direction": a.direction,
                      "amount": money(a.amount_minor, a.currency), "day_of_month": a.day_of_month,
                      "account": p.db.get(BankAccount, a.account_id).name, "active": a.is_active} for a in rows]}


# ---------------------------------------------------------------- rapprochement

@router.get("/reconciliation-cases", tags=["Rapprochement"])
def list_cases(page: PageParams = Depends(), status: str | None = None, p: Principal = Depends(get_principal)):
    p.require_any("reconciliation.read")
    rows = p.db.scalars(select(ReconciliationCase).where(ReconciliationCase.organization_id == p.org_id)
                        .order_by(ReconciliationCase.created_at.desc())).all()
    rows = [c for c in rows if p.authz.has("reconciliation.read", c.entity_id, c.account_id)
            and (status is None or c.status == status)]
    return paginate_list([reco.serialize(p.db, c) for c in rows], page)


@router.post("/reconciliation/runs", tags=["Rapprochement"], summary="Rapprocher le relevé du simulateur avec le registre")
def run_reco(body: ReconRunIn, p: Principal = Depends(get_principal)):
    acc = p.db.get(BankAccount, body.account_id)
    if acc is None or acc.organization_id != p.org_id:
        raise NotFound("Compte", body.account_id)
    p.require("reconciliation.resolve", acc.entity_id, acc.id)
    r = reco.run(p.db, acc, clock.today() - timedelta(days=30), owner_user_id=p.user_id)
    p.audit("reconciliation.run", "bank_account", acc.id, entity_id=acc.entity_id,
            details={"lines": r.statement_lines, "matched": r.matched, "opened": r.cases_opened})
    return {"id": str(r.id), "statement_lines": r.statement_lines, "matched": r.matched, "cases_opened": r.cases_opened,
            "source": r.source}


@router.post("/reconciliation-cases/{case_id}/acknowledge", tags=["Rapprochement"])
def ack_case(case_id: uuid.UUID, body: ReconAckIn, p: Principal = Depends(get_principal)):
    return reco.serialize(p.db, reco.acknowledge(p.db, p, case_id, body.note))


@router.post("/reconciliation-cases/{case_id}/resolve", tags=["Rapprochement"])
def resolve_case(case_id: uuid.UUID, body: ReconResolveIn, p: Principal = Depends(get_principal)):
    return reco.serialize(p.db, reco.resolve(p.db, p, case_id, body.action, body.note))


# ------------------------------------------------------------ centre de décisions

@router.get("/decisions", tags=["Centre de décisions"])
def list_decisions(p: Principal = Depends(get_principal)):
    p.require_any("decision.read")
    return {"data": decisions.items(p.db, p)}


@router.post("/decisions/acknowledge", tags=["Centre de décisions"], summary="Accuser réception (ne résout pas la cause)")
def ack_decision(body: AckIn, p: Principal = Depends(get_principal)):
    return decisions.acknowledge(p.db, p, body.key, body.note)
