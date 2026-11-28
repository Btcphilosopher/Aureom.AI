"""Prévision de trésorerie déterministe et transparente.

Méthode (documentée, reproductible) :
1. Point de départ = solde COMPTABILISÉ des comptes simulés à la date d'arrêté
   (pas le disponible : les réservations correspondent à des paiements
   prévus, qui sont comptés comme décaissements — on évite ainsi le double
   comptage).
2. Flux ajoutés jour par jour, chacun avec sa source :
   * paiements approuvés / planifiés / soumis / acceptés / inconnus (non encore
     comptabilisés) et, selon le scénario, en attente d'approbation ;
   * encaissements attendus à l'état EXPECTED (un encaissement rapproché passe
     à RECEIVED et sort de la prévision) ;
   * échéances de financement non payées et non encore préparées en paiement
     (une échéance préparée est comptée via son paiement, pas deux fois) ;
   * occurrences d'hypothèses récurrentes non réalisées et non couvertes par
     un paiement référencé (forecast_ref).
3. Ajustements de scénario : décote et retard des encaissements, majoration
   des décaissements estimés (hypothèses récurrentes uniquement).
4. Fourchette = enveloppe (min/max quotidien) des scénarios PRUDENT et
   FAVORABLE. Ce n'est pas un intervalle statistique.
Les flux échus non réalisés (date ≤ arrêté) sont placés à J+1 et signalés.
Comptes externes en lecture seule : exclus de la projection (données non
contrôlées) et listés dans « excluded ».
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.config import get_settings
from horizon.core.errors import DomainError, NotFound
from horizon.core.money import money
from horizon.modules.accounts.models import BankAccount
from horizon.modules.accounts.service import visible_accounts
from horizon.modules.financing.models import FinancingFacility, FinancingInstallment
from horizon.modules.forecasting.models import (
    CashflowScenario,
    ExpectedReceipt,
    ForecastRun,
    RecurringAssumption,
    RecurringRealization,
)
from horizon.modules.fx import service as fx
from horizon.modules.ledger import service as ledger
from horizon.modules.payments.models import Payment, PaymentBatch

METHOD = "deterministe-v1"
PLANNED = ("APPROVED", "SCHEDULED", "SUBMITTED", "ACCEPTED", "UNKNOWN")
HORIZONS = (7, 30, 90)


def _occurrences(a: RecurringAssumption, start: date, end: date):
    d = date(start.year, start.month, 1)
    while d <= end:
        dom = min(a.day_of_month, calendar.monthrange(d.year, d.month)[1])
        occ = date(d.year, d.month, dom)
        if start <= occ <= end and occ >= a.start_date and (a.end_date is None or occ <= a.end_date):
            yield occ
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)


def compute(db: Session, principal, scenario: CashflowScenario, horizon_days: int, as_of: date | None = None) -> dict:
    if horizon_days not in HORIZONS:
        raise DomainError("INVALID_HORIZON", "Horizons pris en charge : 7, 30 ou 90 jours", 422)
    base = get_settings().base_currency
    as_of = as_of or clock.today()
    end = as_of + timedelta(days=horizon_days)
    accounts = visible_accounts(db, principal, "forecast.read")
    sims = [a for a in accounts if a.kind == "SIMULATED"]
    sim_ids = {a.id for a in sims}
    acc_by_id = {a.id: a for a in sims}
    rates_used: dict[str, dict] = {}

    def to_base(minor: int, ccy: str) -> int:
        v, ref = fx.convert(db, minor, ccy, base, as_of)
        rates_used[f"{ccy}/{base}"] = ref
        return v

    start_components = []
    start_total = 0
    for a in sims:
        booked = ledger.booked_balance(db, a.id, as_of)
        conv = to_base(booked, a.currency)
        start_total += conv
        start_components.append({"account_id": str(a.id), "account": a.name, "booked": money(booked, a.currency),
                                 "booked_in_base": money(conv, base)})

    lines: list[dict] = []
    excluded: list[dict] = []

    def add(d: date, amount_base: int, label: str, source_type: str, source_id: str, account: BankAccount, *, category: str,
            original: dict, note: str | None = None):
        overdue = d <= as_of
        lines.append({"date": (as_of + timedelta(days=1) if overdue else d).isoformat(), "original_date": d.isoformat(),
                      "amount": money(amount_base, base), "amount_minor": amount_base, "label": label,
                      "category": category, "source_type": source_type, "source_id": source_id,
                      "account": account.name, "original_amount": original, "overdue": overdue, "note": note})

    # 1. Paiements non comptabilisés
    statuses = PLANNED + (("PENDING_APPROVAL",) if scenario.include_pending_approval else ())
    payments = db.scalars(select(Payment).where(Payment.organization_id == principal.org_id,
                                                Payment.status.in_(statuses))).all()
    covered_refs = set()
    counted_batches = set()
    for p in payments:
        if p.debtor_account_id not in sim_ids:
            continue
        counted_batches.add(p.batch_id)
        if p.execution_date > end:
            continue
        batch = db.get(PaymentBatch, p.batch_id)
        for ref in (p.forecast_ref, batch.forecast_ref):
            if ref:
                covered_refs.add(ref)
        add(p.execution_date, -to_base(p.amount_minor, p.currency), f"{batch.reference} — {batch.label} (ligne {p.line_no})",
            "payment", str(p.id), acc_by_id[p.debtor_account_id], category="Paiements",
            original=money(p.amount_minor, p.currency),
            note="Résultat inconnu : compté par prudence" if p.status == "UNKNOWN" else
            ("En attente d'approbation" if p.status == "PENDING_APPROVAL" else None))
    if not scenario.include_pending_approval:
        n = sum(1 for p in db.scalars(select(Payment).where(Payment.organization_id == principal.org_id,
                                                             Payment.status == "PENDING_APPROVAL")))
        if n:
            excluded.append({"reason": "Paiements en attente d'approbation exclus par le scénario", "count": n})

    # 2. Encaissements attendus
    haircut = Decimal(str(scenario.receipts_haircut_pct or 0)) / Decimal(100)
    delay = int(scenario.receipts_delay_days or 0)
    receipts = db.scalars(select(ExpectedReceipt).where(ExpectedReceipt.organization_id == principal.org_id)).all()
    for r in receipts:
        if r.account_id not in sim_ids:
            continue
        if r.status != "EXPECTED":
            excluded.append({"reason": "Encaissement déjà réalisé (rapproché) : présent dans le solde observé",
                             "source_type": "expected_receipt", "source_id": str(r.id), "label": r.counterparty})
            continue
        if r.confidence == "LOW" and not scenario.include_low_confidence:
            excluded.append({"reason": "Confiance faible exclue par le scénario", "source_id": str(r.id), "label": r.counterparty})
            continue
        d = r.expected_date + timedelta(days=delay)
        if d > end:
            continue
        amt = int(Decimal(to_base(r.amount_minor, r.currency)) * (1 - haircut))
        add(d, amt, f"{r.counterparty} — {r.reference}", "expected_receipt", str(r.id), acc_by_id[r.account_id],
            category="Encaissements attendus", original=money(r.amount_minor, r.currency),
            note=(f"Décote {scenario.receipts_haircut_pct} %, retard {delay} j" if haircut or delay else None))

    # 3. Échéances de financement
    for inst in db.scalars(select(FinancingInstallment).where(FinancingInstallment.organization_id == principal.org_id,
                                                              FinancingInstallment.status != "PAID")):
        fac = db.get(FinancingFacility, inst.facility_id)
        acc = acc_by_id.get(fac.repayment_account_id)
        if acc is None or inst.due_date > end:
            continue
        if inst.payment_batch_id is not None and inst.payment_batch_id in counted_batches:
            excluded.append({"reason": "Échéance préparée : comptée via son paiement", "source_type": "financing_installment",
                             "source_id": str(inst.id), "label": fac.label})
            continue
        draft_note = ("Paiement préparé mais pas encore soumis : l'échéance reste comptée ici"
                      if inst.payment_batch_id is not None else None)
        total = inst.principal_minor + inst.interest_minor
        add(inst.due_date, -to_base(total, inst.currency), f"Échéance {fac.label}", "financing_installment", str(inst.id),
            acc, category="Financement", original=money(total, inst.currency), note=draft_note)

    # 4. Hypothèses récurrentes
    uplift = Decimal(str(scenario.disbursements_uplift_pct or 0)) / Decimal(100)
    for a in db.scalars(select(RecurringAssumption).where(RecurringAssumption.organization_id == principal.org_id,
                                                          RecurringAssumption.is_active.is_(True))):
        acc = acc_by_id.get(a.account_id)
        if acc is None:
            continue
        realized = {r.occurrence_date for r in db.scalars(select(RecurringRealization).where(
            RecurringRealization.assumption_id == a.id))}
        for occ in _occurrences(a, as_of + timedelta(days=1), end):
            ref = f"recurring:{a.id}:{occ.isoformat()}"
            if occ in realized:
                excluded.append({"reason": "Occurrence réalisée", "source_id": ref, "label": a.label})
                continue
            if ref in covered_refs:
                excluded.append({"reason": "Occurrence couverte par un paiement préparé", "source_id": ref, "label": a.label})
                continue
            amt = to_base(a.amount_minor, a.currency)
            if a.direction == "OUT":
                amt = -int(Decimal(amt) * (1 + uplift))
            else:
                amt = int(Decimal(amt) * (1 - haircut))
            add(occ, amt, a.label, "recurring_assumption", ref, acc, category=a.category,
                original=money(a.amount_minor, a.currency))

    for a in accounts:
        if a.kind != "SIMULATED":
            excluded.append({"reason": "Compte externe en lecture seule : exclu de la projection", "label": a.name,
                             "source_type": "account", "source_id": str(a.id)})

    by_day: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for ln in lines:
        v = ln["amount_minor"]
        by_day[ln["date"]][0 if v >= 0 else 1] += abs(v)
    series = [{"date": as_of.isoformat(), "inflows": "0.00", "outflows": "0.00", "closing": money(start_total, base),
               "closing_minor": start_total, "observed": True}]
    bal = start_total
    for i in range(1, horizon_days + 1):
        d = (as_of + timedelta(days=i)).isoformat()
        inf, outf = by_day.get(d, [0, 0])
        bal += inf - outf
        series.append({"date": d, "inflows": money(inf, base)["amount"], "outflows": money(outf, base)["amount"],
                       "closing": money(bal, base), "closing_minor": bal, "observed": False})
    lines.sort(key=lambda x: (x["date"], x["amount_minor"]))
    return {
        "scenario": serialize_scenario(scenario), "horizon_days": horizon_days, "as_of": as_of.isoformat(),
        "base_currency": base, "method": METHOD, "method_description": __doc__,
        "inputs": {"starting_balance": money(start_total, base), "starting_components": start_components,
                   "rates": list(rates_used.values())},
        "series": series, "lines": lines, "excluded": excluded,
        "totals": {"inflows": money(sum(x["amount_minor"] for x in lines if x["amount_minor"] > 0), base),
                   "outflows": money(-sum(x["amount_minor"] for x in lines if x["amount_minor"] < 0), base),
                   "ending": money(bal, base)},
    }


def run_and_store(db: Session, principal, scenario_id, horizon_days: int) -> ForecastRun:
    sc = get_scenario(db, principal, scenario_id)
    res = compute(db, principal, sc, horizon_days)
    fr = ForecastRun(organization_id=principal.org_id, scenario_id=sc.id, horizon_days=horizon_days,
                     as_of=date.fromisoformat(res["as_of"]), method=METHOD, inputs=res["inputs"], series=res["series"],
                     lines=res["lines"], excluded=res["excluded"], created_by=principal.user_id)
    db.add(fr)
    db.flush()
    principal.audit("forecast.run", "forecast", fr.id, details={"scenario": sc.code, "horizon": horizon_days})
    return fr


def get_scenario(db, principal, scenario_id) -> CashflowScenario:
    sc = db.get(CashflowScenario, scenario_id)
    if sc is None or sc.organization_id != principal.org_id:
        raise NotFound("Scénario", scenario_id)
    return sc


def scenario_by_code(db, org_id, code) -> CashflowScenario | None:
    return db.scalar(select(CashflowScenario).where(CashflowScenario.organization_id == org_id, CashflowScenario.code == code))


def chart(db: Session, principal, horizon_days: int) -> dict:
    """Historique observé + prévision centrale + fourchette (enveloppe des scénarios)."""
    base = get_settings().base_currency
    as_of = clock.today()
    central = scenario_by_code(db, principal.org_id, "CENTRAL")
    prudent = scenario_by_code(db, principal.org_id, "PRUDENT")
    favorable = scenario_by_code(db, principal.org_id, "FAVORABLE")
    c = compute(db, principal, central, horizon_days, as_of)
    p = compute(db, principal, prudent, horizon_days, as_of) if prudent else c
    f = compute(db, principal, favorable, horizon_days, as_of) if favorable else c
    hist_days = min(max(horizon_days, 14), 60)
    sims = [a for a in visible_accounts(db, principal, "forecast.read") if a.kind == "SIMULATED"]
    hist: dict[date, int] = defaultdict(int)
    for a in sims:
        for d, bal in ledger.daily_balances(db, a.id, as_of - timedelta(days=hist_days), as_of):
            hist[d] += fx.convert(db, bal, a.currency, base, d)[0]
    observed = [{"date": d.isoformat(), "value": money(v, base)["amount"]} for d, v in sorted(hist.items())]
    forecast = [{"date": s["date"], "value": s["closing"]["amount"]} for s in c["series"]]
    band = []
    for sc, sp, sf in zip(c["series"], p["series"], f["series"]):
        vals = [sc["closing_minor"], sp["closing_minor"], sf["closing_minor"]]
        band.append({"date": sc["date"], "low": money(min(vals), base)["amount"], "high": money(max(vals), base)["amount"]})
    return {"base_currency": base, "as_of": as_of.isoformat(), "horizon_days": horizon_days, "observed": observed,
            "forecast": forecast, "band": band,
            "band_method": "Fourchette = enveloppe quotidienne (min/max) des scénarios Prudent, Central et Favorable",
            "scenarios": {k: serialize_scenario(v) for k, v in (("central", central), ("prudent", prudent), ("favorable", favorable)) if v},
            "central_totals": c["totals"], "boundary_date": as_of.isoformat()}


def serialize_scenario(s: CashflowScenario) -> dict:
    return {"id": str(s.id), "code": s.code, "name": s.name, "description": s.description,
            "receipts_haircut_pct": str(s.receipts_haircut_pct), "receipts_delay_days": s.receipts_delay_days,
            "disbursements_uplift_pct": str(s.disbursements_uplift_pct),
            "include_pending_approval": s.include_pending_approval, "include_low_confidence": s.include_low_confidence,
            "is_baseline": s.is_baseline}


def serialize_run(fr: ForecastRun, scenario: CashflowScenario) -> dict:
    return {"id": str(fr.id), "scenario": serialize_scenario(scenario), "horizon_days": fr.horizon_days,
            "as_of": fr.as_of.isoformat(), "method": fr.method, "created_at": fr.created_at.isoformat(),
            "inputs": fr.inputs, "series": fr.series, "lines": fr.lines, "excluded": fr.excluded}
