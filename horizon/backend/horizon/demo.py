"""Démonstration reproductible HORIZON — 12 étapes exécutées via l'API HTTP.

Usage :
    python -m horizon.demo                      # en processus (TestClient), base déjà initialisée
    python -m horizon.demo --until 3            # s'arrête à l'état de la maquette (lot en attente)
    python -m horizon.demo --base-url http://localhost:8000 --report demo.md

Chaque étape affiche des preuves (statuts, soldes, écritures) et lève une
erreur si une vérification échoue : la démonstration sert aussi de test de bout en bout.
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import time
import uuid
import zipfile
from decimal import Decimal

from horizon.core.crypto import totp_now
from horizon.seed import DEMO_PASSWORD, demo_totp_secret

logging.getLogger("httpx").setLevel(logging.WARNING)

USERS = {
    "claire": "claire.martin@lumiere.example",
    "sophie": "sophie.bernard@lumiere.example",
    "marc": "marc.lefevre@lumiere.example",
    "katrin": "katrin.weber@lumiere.example",
    "julien": "julien.moreau@lumiere.example",
    "ines": "ines.garnier@lumiere.example",
}


class DemoFailure(AssertionError):
    pass


def check(cond, message):
    if not cond:
        raise DemoFailure(message)


class Api:
    def __init__(self, base_url: str | None):
        if base_url:
            import httpx

            self.http = httpx.Client(base_url=base_url, timeout=30)
        else:
            from fastapi.testclient import TestClient

            from horizon.main import app

            self.http = TestClient(app)
        self.tokens: dict[str, str] = {}

    def login(self, who: str) -> None:
        email = USERS[who]
        r = self.http.post("/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD})
        r.raise_for_status()
        r = self.http.post("/v1/auth/mfa", json={"challenge_id": r.json()["challenge_id"],
                                                  "code": totp_now(demo_totp_secret(email))})
        r.raise_for_status()
        self.tokens[who] = r.json()["token"]
        self.http.cookies.clear()

    def step_up(self, who: str) -> None:
        self.call(who, "POST", "/v1/auth/step-up", json={"code": totp_now(demo_totp_secret(USERS[who]))})

    def call(self, who: str, method: str, path: str, expect: int | tuple = (200, 201), **kw):
        if who not in self.tokens:
            self.login(who)
        headers = {"Authorization": f"Bearer {self.tokens[who]}", **kw.pop("headers", {})}
        r = self.http.request(method, path, headers=headers, **kw)
        exp = (expect,) if isinstance(expect, int) else expect
        if r.status_code not in exp:
            raise DemoFailure(f"{method} {path} → {r.status_code} (attendu {exp}) : {r.text[:400]}")
        ctype = r.headers.get("content-type", "")
        return r.json() if ctype.startswith("application/json") else r


class Report:
    def __init__(self):
        self.lines: list[str] = ["# Démonstration HORIZON — journal d'exécution", "",
                                 "ENVIRONNEMENT DE DÉMONSTRATION · données synthétiques · aucun service bancaire réel", ""]

    def step(self, n: int, title: str):
        print(f"\n=== Étape {n} — {title}")
        self.lines += ["", f"## Étape {n} — {title}", ""]

    def ok(self, msg: str):
        print(f"  ✔ {msg}")
        self.lines.append(f"- ✔ {msg}")


def eur(m: dict) -> Decimal:
    return Decimal(m["amount"])


def account_by_name(accounts, prefix):
    return next(a for a in accounts if a["name"].startswith(prefix))


def run(base_url: str | None = None, until: int = 12, report_path: str | None = None) -> Report:
    api = Api(base_url)
    rep = Report()
    C = lambda *a, **k: api.call("claire", *a, **k)  # noqa: E731

    # 1 ------------------------------------------------------------------------
    rep.step(1, "Consultation des comptes")
    accounts = C("GET", "/v1/accounts")["data"]
    fr = account_by_name(accounts, "Lumière France — Compte principal")
    de = account_by_name(accounts, "Lumière Deutschland")
    it = account_by_name(accounts, "Lumière Italia")
    for a in (fr, de, it):
        rep.ok(f"{a['entity']['name']} : disponible {a['balance']['available']['amount']} {a['currency']} "
               f"(comptabilisé {a['balance']['booked']['amount']}, réservé {a['balance']['reserved']['amount']})")
    ov = C("GET", "/v1/overview")
    liq = ov["kpis"][0]
    rep.ok(f"Liquidités disponibles (calculées) : {liq['value']['amount']} EUR — formule : {liq['explain']['formula']}")
    ext = [a for a in accounts if a["kind"] == "EXTERNAL_READONLY"][0]
    rep.ok(f"Compte externe en lecture seule présenté à part : {ext['name']} — fraîcheur "
           f"{ext['balance']['freshness']['label']} ({ext['balance']['freshness']['age_hours']} h)")
    if until < 2:
        return _finish(rep, report_path)

    # 2 ------------------------------------------------------------------------
    rep.step(2, "Création d'un bénéficiaire")
    ent_fr = fr["entity"]["id"]
    from horizon.core.iban import make_iban

    new_iban = make_iban("FR", "99999000040000012345601")
    iban_check = C("POST", "/v1/beneficiaries/validate-iban", json={"iban": new_iban})
    bad = C("POST", "/v1/beneficiaries/validate-iban", json={"iban": new_iban[:-1] + "9"})
    rep.ok(f"Contrôle IBAN {new_iban} : format_valid={iban_check['format_valid']} (variante altérée : "
           f"{bad['format_valid']}, {bad['issues'][0]}) — « {iban_check['scope']} »")

    bene = C("POST", "/v1/beneficiaries", json={"entity_id": ent_fr, "name": "Fonderie Loire SAS",
                                               "iban": new_iban, "bic": "HZDMFRP4XXX",
                                               "country_code": "FR", "address": "Nantes (fictif)"})
    check(bene["status"] == "PENDING_REVIEW", "le bénéficiaire doit être en revue")
    rep.ok(f"Bénéficiaire créé par Claire Martin : {bene['current_version']['name']} — statut {bene['status_label']}")
    api.step_up("claire")
    r = api.call("claire", "POST", f"/v1/beneficiaries/{bene['id']}/review", expect=403, json={"decision": "APPROVE"})
    rep.ok(f"Claire ne peut pas valider sa propre création : {r['error']['code']}")
    api.step_up("sophie")
    bene = api.call("sophie", "POST", f"/v1/beneficiaries/{bene['id']}/review",
                    json={"decision": "APPROVE", "comment": "Contrôle documentaire fictif OK"})
    check(bene["status"] == "ACTIVE", "bénéficiaire actif attendu")
    rep.ok("Sophie Bernard (approbatrice, réauthentifiée) valide la version 1 → statut Actif")
    if until < 3:
        return _finish(rep, report_path)

    # 3 ------------------------------------------------------------------------
    rep.step(3, "Préparation d'un lot fournisseurs de 480 000 €")
    benes = {b["current_version"]["name"]: b["id"] for b in C("GET", "/v1/beneficiaries", params={"limit": 200})["data"]}
    lines = [("Acier Rhône SAS", "120000.00", "FAC AR-2026-1102"), ("Logistique Seine SARL", "64000.00", "FAC LS-88231"),
             ("Emballages Garonne SA", "48500.00", "FAC EG-4410"), ("Électricité Pyrénées SAS", "37500.00", "FAC EP-11-2026"),
             ("Imprimerie Vasseur SARL", "22000.00", "FAC IV-2026-77"), ("Cabinet Delorme Conseil", "93000.00", "HON-2026-Q4"),
             ("Fonderie Loire SAS", "95000.00", "FAC FL-0001")]
    total = sum(Decimal(x[1]) for x in lines)
    check(total == Decimal("480000.00"), "total du lot")
    payload = {"debtor_account_id": fr["id"], "label": "Règlement fournisseurs – Déc.", "kind": "SUPPLIER_BATCH",
               "payments": [{"beneficiary_id": benes[n], "amount": a, "remittance_info": ref} for n, a, ref in lines]}
    key = f"demo-lot-fournisseurs-{uuid.uuid4()}"
    batch = C("POST", "/v1/payment-batches", json=payload, headers={"Idempotency-Key": key}, expect=201)
    replay = api.http.post("/v1/payment-batches", json=payload,
                           headers={"Idempotency-Key": key, "Authorization": f"Bearer {api.tokens['claire']}"})
    check(replay.status_code == 200 and replay.json()["id"] == batch["id"], "rejeu idempotent")
    rep.ok(f"Lot {batch['reference']} créé : {batch['payment_count']} paiements, {batch['total']['amount']} EUR ; "
           f"rejeu avec la même Idempotency-Key → même lot (HTTP 200, Idempotent-Replayed)")
    batch = C("POST", f"/v1/payment-batches/{batch['id']}/submit-for-approval", json={"expected_version": batch["version"]})
    check(batch["status"] == "PENDING_APPROVAL" and batch["required_approvals"] == 2, "lot en attente de 2 approbations")
    rep.ok(f"Soumis pour approbation : {batch['status_label']} — {batch['required_approvals']} approbations distinctes "
           f"requises ; éligibles : {', '.join(e['name'] for e in batch['eligible_approvers'])}")
    ov = C("GET", "/v1/overview")
    rep.ok(f"Tableau de bord : {ov['kpis'][1]['value']['count']} paiements à approuver pour "
           f"{ov['kpis'][1]['value']['total']['amount']} EUR ; alertes : {ov['kpis'][3]['value']['count']}")
    if until < 4:
        return _finish(rep, report_path)

    # 4 ------------------------------------------------------------------------
    rep.step(4, "Approbation par deux utilisateurs distincts")
    bid, ver = batch["id"], batch["version"]
    sc = {s["code"]: s["id"] for s in C("GET", "/v1/cashflow-scenarios")["data"]}
    r = api.call("claire", "POST", f"/v1/payment-batches/{bid}/approvals", expect=403, json={"decision": "APPROVE", "version": ver})
    rep.ok(f"Préparatrice (Claire) → refus : {r['error']['code']}")
    r = api.call("julien", "POST", f"/v1/payment-batches/{bid}/approvals", expect=403, json={"decision": "APPROVE", "version": ver})
    rep.ok(f"Administrateur technique (Julien) → refus : {r['error']['code']} (l'administration n'inclut pas l'approbation)")
    api.login("sophie")  # nouvelle session sans réauthentification
    r = api.call("sophie", "POST", f"/v1/payment-batches/{bid}/approvals", expect=401, json={"decision": "APPROVE", "version": ver})
    rep.ok(f"Sophie sans réauthentification → {r['error']['code']}")
    api.step_up("sophie")
    r = api.call("sophie", "POST", f"/v1/payment-batches/{bid}/approvals", expect=409,
                 json={"decision": "APPROVE", "version": ver + 7})
    rep.ok(f"Approbation d'une version obsolète → {r['error']['code']}")
    r = api.call("sophie", "POST", f"/v1/payment-batches/{bid}/approvals", json={"decision": "APPROVE", "version": ver,
                                                                                  "comment": "Factures contrôlées"})
    rep.ok(f"Sophie Bernard approuve la version {ver} → {r['result']['approvals']}/{r['result']['required']}")
    r = api.call("sophie", "POST", f"/v1/payment-batches/{bid}/approvals", expect=409, json={"decision": "APPROVE", "version": ver})
    rep.ok(f"Seconde approbation par la même personne → {r['error']['code']}")
    before = C("GET", f"/v1/accounts/{fr['id']}")["balance"]
    forecast_before = C("POST", "/v1/forecasts", json={"scenario_id": sc["CENTRAL"], "horizon_days": 30})
    api.step_up("marc")
    r = api.call("marc", "POST", f"/v1/payment-batches/{bid}/approvals", json={"decision": "APPROVE", "version": ver})
    check(r["batch"]["status"] == "APPROVED", "lot approuvé")
    after = C("GET", f"/v1/accounts/{fr['id']}")["balance"]
    check(eur(after["reserved"]) - eur(before["reserved"]) == Decimal("480000.00"), "réservation de 480 000")
    check(eur(after["booked"]) == eur(before["booked"]), "comptabilisé inchangé avant exécution")
    rep.ok(f"Marc Lefèvre approuve → quorum 2/2, lot {r['batch']['status_label']} ; réservé {after['reserved']['amount']} EUR, "
           f"disponible {after['available']['amount']} EUR, comptabilisé inchangé {after['booked']['amount']} EUR")
    if until < 5:
        return _finish(rep, report_path)

    # 5 ------------------------------------------------------------------------
    rep.step(5, "Exécution simulée")
    n = C("POST", "/v1/demo/run-jobs")["processed"]
    b = C("GET", f"/v1/payment-batches/{bid}")
    check(b["status"] == "COMPLETED" and all(p["status"] == "EXECUTED" for p in b["payments"]), "lot exécuté")
    p0 = C("GET", f"/v1/payments/{b['payments'][0]['id']}")
    rep.ok(f"{n} tâches traitées ; lot {b['status_label']} — {b['status_counts']}")
    trail = " → ".join(f"{e['to_label']}" for e in p0["events"])
    rep.ok(f"Parcours ligne 1 : {trail}")
    rep.ok(f"Réception technique {p0['technical_ack_at'][11:19]} · acceptation {p0['accepted_at'][11:19]} · "
           f"exécution (règlement confirmé) {p0['executed_at'][11:19]} — référence {p0['bank_reference']}")
    bal = C("GET", f"/v1/accounts/{fr['id']}")["balance"]
    check(eur(bal["booked"]) == eur(before["booked"]) - Decimal("480000.00"), "débit de 480 000")
    check(eur(bal["reserved"]) == eur(before["reserved"]), "réservations consommées")
    rep.ok(f"Compte France : comptabilisé {bal['booked']['amount']} EUR (−480 000), réservations consommées")
    tb = C("GET", "/v1/ledger/trial-balance")
    check(all(v["balanced"] for v in tb["totals_by_currency"].values()), "balance équilibrée")
    rep.ok("Balance générale équilibrée dans chaque devise")

    # 6 ------------------------------------------------------------------------
    rep.step(6, "Réception d'un événement dupliqué sans double débit")
    evs = C("GET", "/v1/demo/simulator/events")["data"]
    settled = next(e for e in evs if e["type"] == "PAYMENT_SETTLED" and e["submission_key"] == p0["submission_key"])
    r = C("POST", "/v1/demo/simulator/redeliver", json={"event_id": settled["event_id"]})
    check(r["outcome"] == "DUPLICATE_IGNORED", "doublon ignoré")
    bal2 = C("GET", f"/v1/accounts/{fr['id']}")["balance"]
    check(bal2["booked"] == bal["booked"], "solde inchangé")
    tx = C("GET", f"/v1/accounts/{fr['id']}/transactions", params={"limit": 200})["data"]
    check(sum(1 for t in tx if t["reference_id"] == p0["id"]) == 1, "une seule écriture")
    rep.ok(f"Événement {settled['event_id'][:20]}… redélivré → {r['outcome']} (livraisons en double : "
           f"{r['duplicate_deliveries']}) ; solde inchangé {bal2['booked']['amount']} EUR ; une seule écriture pour le paiement")

    # 7 ------------------------------------------------------------------------
    rep.step(7, "Traitement d'un paiement rejeté")
    rej = C("POST", "/v1/payment-batches", json={"debtor_account_id": de["id"], "label": "Acompte projet industriel",
                                                  "kind": "SINGLE", "payments": [{"beneficiary_id": benes["Maschinenbau Ostwald GmbH"],
                                                                                  "amount": "300000.00",
                                                                                  "remittance_info": "Anzahlung Projekt 2027"}]})
    rej = C("POST", f"/v1/payment-batches/{rej['id']}/submit-for-approval", json={"expected_version": rej["version"]})
    for who in ("katrin", "sophie"):
        api.step_up(who)
        api.call(who, "POST", f"/v1/payment-batches/{rej['id']}/approvals", json={"decision": "APPROVE", "version": rej["version"]})
    de_before = C("GET", f"/v1/accounts/{de['id']}")["balance"]
    C("POST", "/v1/demo/run-jobs")
    rb = C("GET", f"/v1/payment-batches/{rej['id']}")
    rp = rb["payments"][0]
    check(rp["status"] == "REJECTED" and rp["rejection_code"] == "AC04", "rejet AC04")
    de_after = C("GET", f"/v1/accounts/{de['id']}")["balance"]
    check(de_after["booked"] == de_before["booked"] and eur(de_after["reserved"]) == eur(de_before["reserved"]) - Decimal("300000"),
          "réservation libérée, aucun débit")
    rep.ok(f"Lot {rb['reference']} approuvé (Katrin Weber + Sophie Bernard) puis {rp['status_label']} par le destinataire : "
           f"{rp['rejection_code']} — {rp['rejection_label']} ; réservation libérée, aucun débit")
    dec = C("GET", "/v1/decisions")["data"]
    item = next(i for i in dec if i["kind"] == "PAYMENT_REJECTED")
    C("POST", "/v1/decisions/acknowledge", json={"key": item["key"], "note": "Vu, je contacte le fournisseur"})
    still = any(i["key"] == item["key"] for i in C("GET", "/v1/decisions")["data"])
    check(still, "l'accusé de réception ne résout pas")
    rep.ok("Accusé de réception enregistré : l'alerte reste présente (la cause n'est pas résolue)")
    C("POST", f"/v1/payments/{rp['id']}/rejection-resolution",
      json={"resolution": "Compte clôturé confirmé ; nouvelles coordonnées demandées au fournisseur"})
    gone = not any(i["key"] == item["key"] for i in C("GET", "/v1/decisions")["data"])
    check(gone, "rejet traité")
    rep.ok("Rejet traité avec justification → l'élément quitte le centre de décisions")

    # 8 ------------------------------------------------------------------------
    rep.step(8, "Gestion d'un résultat inconnu")
    outcomes = []
    for kind, ref in (("TIMEOUT_AFTER_RECORD", "FAC EP-12-2026"), ("TIMEOUT_BEFORE_RECORD", "FAC LS-88990")):
        C("POST", "/v1/demo/simulator/faults", json={"kind": kind, "match_remittance": ref})
        name = "Électricité Pyrénées SAS" if "EP" in ref else "Logistique Seine SARL"
        ub = C("POST", "/v1/payment-batches", json={"debtor_account_id": fr["id"], "label": f"Facture {ref}", "kind": "SINGLE",
                                                     "payments": [{"beneficiary_id": benes[name], "amount": "18400.00",
                                                                   "remittance_info": ref}]})
        ub = C("POST", f"/v1/payment-batches/{ub['id']}/submit-for-approval", json={"expected_version": ub["version"]})
        api.step_up("marc")
        api.call("marc", "POST", f"/v1/payment-batches/{ub['id']}/approvals", json={"decision": "APPROVE", "version": ub["version"]})
        # exécution jusqu'à la soumission seulement : on observe l'état intermédiaire
        from horizon.modules.jobs import queue

        if base_url is None:
            queue.run_one()  # execute_batch
            queue.run_one()  # submit_payment → délai dépassé
            mid_batch = C("GET", f"/v1/payment-batches/{ub['id']}")
            mid = C("GET", f"/v1/payments/{mid_batch['payments'][0]['id']}")
            check(mid["status"] == "UNKNOWN", "résultat inconnu attendu")
            rep.ok(f"{kind} : paiement {mid['end_to_end_id']} → {mid['status_label']} ; cas de rapprochement ouvert")
        C("POST", "/v1/demo/run-jobs")
        pay = C("GET", f"/v1/payment-batches/{ub['id']}")["payments"][0]
        pay = C("GET", f"/v1/payments/{pay['id']}")
        check(pay["status"] == "EXECUTED", "exécuté après recherche")
        reasons = [e["reason"] for e in pay["events"] if e["reason"] and "Recherche" in e["reason"]]
        outcomes.append((kind, pay))
        rep.ok(f"{kind} : {reasons[0] if reasons else ''} → {pay['status_label']} ; tentatives de soumission : "
               f"{pay['submission_attempts']} (même clé {pay['submission_key'][:16]}…)")
    from horizon.core.db import SessionLocal
    from horizon.modules.integrations.models import SimBankOrder
    from sqlalchemy import func, select

    if base_url is None:
        with SessionLocal() as s:
            for _, pay in outcomes:
                n = s.scalar(select(func.count()).select_from(SimBankOrder).where(SimBankOrder.submission_key == pay["submission_key"]))
                check(n == 1, "un seul ordre chez le destinataire")
        rep.ok("Chez le destinataire : exactement un ordre par clé d'idempotence (aucune double exécution)")

    # 9 ------------------------------------------------------------------------
    rep.step(9, "Mise à jour de la prévision sans double comptage")
    fa = C("POST", "/v1/forecasts", json={"scenario_id": sc["CENTRAL"], "horizon_days": 30})
    # Différences attendues : uniquement les opérations postérieures (rejet DE libérant 300 000, 2 paiements de 18 400).
    sb = {s["date"]: Decimal(s["closing"]["amount"]) for s in forecast_before["series"]}
    sa = {s["date"]: Decimal(s["closing"]["amount"]) for s in fa["series"]}
    later_delta = Decimal("-36800.00")  # seuls effets postérieurs : 2 × 18 400 exécutés à l'étape 8
    d1 = sorted(sa)[1]
    check(all(sa[d] - sb[d] == later_delta for d in sorted(sa)[1:]),
          f"écart J+1..J+30 = effets ultérieurs uniquement ({sa[d1] - sb[d1]})")
    rep.ok(f"Point de départ : {forecast_before['inputs']['starting_balance']['amount']} → {fa['inputs']['starting_balance']['amount']} EUR "
           f"(le lot exécuté est passé du « prévu » au « comptabilisé »)")
    rep.ok(f"Prévision J+1 avant/après : {sb[d1]} / {sa[d1]} — écart {sa[d1] - sb[d1]} sur tout l'horizon = uniquement les "
           f"2 × 18 400 de l'étape 8 ; le lot de 480 000 n'est compté ni deux fois ni zéro fois (le rejet de 300 000, créé "
           f"après le premier calcul, n'y figure jamais)")
    exp = C("GET", "/v1/expected-receipts")["data"]
    hsc = next(e for e in exp if e["counterparty"].startswith("Hôtellerie Saint-Clair"))
    f1 = C("POST", "/v1/forecasts", json={"scenario_id": sc["CENTRAL"], "horizon_days": 30})
    C("POST", "/v1/demo/simulator/incoming", json={"expected_receipt_id": hsc["id"]})
    f2 = C("POST", "/v1/forecasts", json={"scenario_id": sc["CENTRAL"], "horizon_days": 30})
    e1 = Decimal(f1["series"][-1]["closing"]["amount"])
    e2 = Decimal(f2["series"][-1]["closing"]["amount"])
    check(e1 == e2, "fin d'horizon inchangée après encaissement")
    rep.ok(f"Encaissement attendu « {hsc['counterparty']} » (1 200 000) reçu : comptabilisé +1 200 000, sorti des encaissements "
           f"attendus ; solde prévu à J+30 inchangé ({e2} EUR)")
    run = C("POST", "/v1/reconciliation/runs", json={"account_id": fr["id"]})
    cases = C("GET", "/v1/reconciliation-cases", params={"status": "OPEN"})["data"]
    fee = next(c for c in cases if c["kind"] == "MISSING_IN_LEDGER")
    rep.ok(f"Rapprochement : {run['statement_lines']} lignes, {run['matched']} rapprochées, écart détecté : {fee['description']}")
    api.step_up("claire")
    C("POST", f"/v1/reconciliation-cases/{fee['id']}/resolve",
      json={"action": "POST_ADJUSTMENT", "note": "Frais de tenue de compte confirmés par la grille tarifaire (fictive)"})
    rep.ok("Écart résolu par écriture de régularisation liée (journal FRA)")

    # 10 -----------------------------------------------------------------------
    rep.step(10, "Consultation d'une échéance de financement")
    insts = C("GET", "/v1/financing/installments")["data"]
    nxt = next(i for i in insts if i["status"] == "TO_PREPARE")
    det = C("GET", f"/v1/financing/installments/{nxt['id']}")
    rep.ok(f"{det['facility']} ({det['facility_reference']}) : échéance du {nxt['due_date']} — principal "
           f"{nxt['principal']['amount']}, intérêts {nxt['interest']['amount']}, total {nxt['total']['amount']} EUR — "
           f"{nxt['status_label']}, responsable {nxt['owner']}")
    rep.ok(f"Contrat : engagé {det['facility_detail']['committed']['amount']} EUR, utilisé {det['facility_detail']['drawn']['amount']} EUR "
           f"— {det['facility_detail']['status_label']}")
    prep = api.call("katrin", "POST", f"/v1/financing/installments/{nxt['id']}/prepare")
    fb = api.call("katrin", "GET", f"/v1/payment-batches/{prep['batch_id']}")
    api.call("katrin", "POST", f"/v1/payment-batches/{fb['id']}/submit-for-approval", json={"expected_version": fb["version"]})
    fc = C("POST", "/v1/forecasts", json={"scenario_id": sc["CENTRAL"], "horizon_days": 30})
    counted = [ln for ln in fc["lines"] if ln["source_id"] == nxt["id"]]
    excl = [x for x in fc["excluded"] if x.get("source_id") == nxt["id"]]
    check(not counted and excl, "échéance comptée via son paiement uniquement")
    rep.ok(f"Katrin Weber prépare et soumet le paiement ({prep['batch_reference']}) ; la prévision compte le paiement et exclut "
           f"l'échéance : « {excl[0]['reason']} »")

    # 11 -----------------------------------------------------------------------
    rep.step(11, "Simulation d'un devis de change")
    ind = C("POST", "/v1/fx-quotes", json={"entity_id": ent_fr, "base": "EUR", "quote": "USD", "side": "SELL",
                                           "amount": "250000.00", "amount_currency": "EUR", "kind": "INDICATIVE"})
    rep.ok(f"Taux indicatif {ind['pair']} : vente {ind['sell']['amount']} EUR → {ind['buy']['amount']} USD au taux client "
           f"{ind['client_rate']} (médian {ind['mid_rate']}, marge {ind['fee_bps']} pb = {ind['fee']['amount']} EUR) — "
           f"source « {ind['source']} » — {ind['kind_label']}")
    usd = account_by_name(accounts, "Lumière France — Compte USD")
    exe = C("POST", "/v1/fx-quotes", json={"entity_id": ent_fr, "base": "EUR", "quote": "USD", "side": "SELL",
                                           "amount": "250000.00", "amount_currency": "EUR", "kind": "EXECUTABLE_SIMULATED",
                                           "sell_account_id": fr["id"], "buy_account_id": usd["id"]})
    r = api.call("sophie", "POST", f"/v1/fx-quotes/{ind['id']}/accept", expect=409)
    rep.ok(f"Acceptation d'un taux indicatif → {r['error']['code']}")
    api.step_up("sophie")
    acc_q = api.call("sophie", "POST", f"/v1/fx-quotes/{exe['id']}/accept")
    rep.ok(f"Offre exécutable SIMULÉE (expire à {exe['expires_at'][11:19]}) acceptée par Sophie Bernard → "
           f"{acc_q['status']} ; écriture CHG équilibrée par devise via les positions de change ; aucun ordre réel")
    tb = C("GET", "/v1/ledger/trial-balance")
    check(all(v["balanced"] for v in tb["totals_by_currency"].values()), "équilibre multidevise")
    rep.ok("Balance : " + ", ".join(f"{c} équilibrée" for c in tb["totals_by_currency"]))

    # 12 -----------------------------------------------------------------------
    rep.step(12, "Export d'un rapport et de sa piste d'audit")
    resp = api.call("ines", "POST", "/v1/reports/treasury-export")
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    manifest = json.loads(z.read("manifeste.json"))
    import hashlib

    for name, sha in manifest["files"].items():
        check(hashlib.sha256(z.read(name)).hexdigest() == sha, f"empreinte {name}")
    check(manifest["audit_chain"]["valid"], "chaîne d'audit valide")
    rep.ok(f"Archive {resp.headers['content-disposition'].split('filename=')[1]} (SHA-256 {resp.headers['x-report-sha256'][:16]}…) : "
           f"{', '.join(z.namelist())}")
    rep.ok(f"Manifeste : {manifest['audit_events']} événements d'audit, chaîne vérifiée = {manifest['audit_chain']['valid']}")
    v = api.call("ines", "GET", "/v1/audit-events/verify")
    rep.ok(f"Vérification indépendante de la chaîne : valide={v['valid']} sur {v['checked']} événements")
    denied = api.call("ines", "GET", "/v1/audit-events", params={"action": "access.denied", "limit": 200})["data"]
    check(denied, "refus tracés")
    rep.ok(f"Refus d'accès tracés (access.denied) : {len(denied)} — ex. {denied[-1]['actor']} sur « {denied[-1]['object_id']} » "
           f"({denied[-1]['outcome']})")
    return _finish(rep, report_path)


def _finish(rep: Report, path: str | None) -> Report:
    print("\nDémonstration terminée avec succès.")
    rep.lines += ["", "Démonstration terminée avec succès."]
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(rep.lines) + "\n")
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url")
    ap.add_argument("--until", type=int, default=12)
    ap.add_argument("--report")
    a = ap.parse_args()
    t = time.time()
    run(a.base_url, a.until, a.report)
    print(f"Durée : {time.time() - t:.1f} s")
