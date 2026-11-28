"""Données synthétiques du Groupe Lumière (fictif).

Les soldes initiaux NE sont PAS saisis directement : ils résultent d'écritures
équilibrées (ouverture il y a 90 jours + 90 jours de flux synthétiques), de
sorte que le registre explique chaque euro.

Usage : python -m horizon.seed  (base vide, migrations appliquées)
"""
from __future__ import annotations

import base64
import hashlib
import random
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from horizon.core import clock
from horizon.core.crypto import encrypt, hash_password
from horizon.core.db import session_scope
from horizon.core.iban import make_iban
from horizon.core.money import to_minor
from horizon.core.pdf import text_pdf
from horizon.core.system import principal_for
from horizon.modules.accounts.models import BankAccount, ExternalBalanceSnapshot
from horizon.modules.audit import service as audit
from horizon.modules.beneficiaries import service as benes
from horizon.modules.documents import service as docs
from horizon.modules.financing.models import FinancingDrawdown, FinancingFacility, FinancingInstallment
from horizon.modules.forecasting.models import CashflowScenario, ExpectedReceipt, RecurringAssumption
from horizon.modules.fx import service as fx
from horizon.modules.identity.models import User
from horizon.modules.integrations.bank_simulator import bank
from horizon.modules.ledger import service as ledger
from horizon.modules.ledger.models import GlAccount
from horizon.modules.organizations.models import ApprovalPolicyRule, LegalEntity, Organization, RoleAssignment
from horizon.modules.payments import service as payments
from horizon.modules.trade.models import TradeDeadline, TradeFile, TradeParty, TradeRequest, TradeTask

DEMO_PASSWORD = "Horizon-Demo-2026!"
TARGETS = {"FR": "12400000.00", "DE": "7800000.00", "IT": "4600000.00"}


def demo_totp_secret(email: str) -> str:
    """Secret TOTP déterministe pour les utilisateurs FICTIFS (démo reproductible)."""
    return base64.b32encode(hashlib.sha256(f"horizon-demo|{email}".encode()).digest()[:20]).decode().rstrip("=")


def _user(db, org, email, name, title):
    u = User(organization_id=org.id, email=email, full_name=name, title=title, password_hash=hash_password(DEMO_PASSWORD),
             totp_secret_enc=encrypt(demo_totp_secret(email)), is_demo=True)
    db.add(u)
    db.flush()
    return u


def _role(db, org, user, role, entity=None, account=None, limit=None, ref=""):
    db.add(RoleAssignment(organization_id=org.id, user_id=user.id, role=role, entity_id=entity.id if entity else None,
                          account_id=account.id if account else None,
                          approval_limit_minor=to_minor(limit, "EUR") if limit else None, mandate_reference=ref,
                          valid_from=clock.today() - timedelta(days=330)))


def _bank_account(db, org, ent, name, iban, bic, ccy, kind="SIMULATED", provider="Simulateur bancaire HORIZON (fictif)"):
    acc = BankAccount(organization_id=org.id, entity_id=ent.id, name=name, iban=iban, bic=bic, currency=ccy, kind=kind,
                      provider=provider)
    db.add(acc)
    db.flush()
    if kind == "SIMULATED":
        n = len(db.scalars(select(GlAccount.id).where(GlAccount.organization_id == org.id)).all()) + 1
        db.add(GlAccount(organization_id=org.id, entity_id=ent.id, code=f"512{n:04d}-{ccy}", name=f"Banque — {name}",
                         type="ASSET", purpose="BANK", currency=ccy, bank_account_id=acc.id))
        db.flush()
    return acc


def _history(db, org, ent, acc, target_minor: int, days: int, rng: random.Random):
    """Ouverture + flux quotidiens synthétiques aboutissant exactement au solde cible."""
    today = clock.today()
    start = today - timedelta(days=days)
    flows = []
    level = target_minor
    for i in range(1, days + 1):
        d = start + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        scale = target_minor // 100
        rec = rng.randint(int(scale * 0.6), int(scale * 2.2))
        pay = rng.randint(int(scale * 0.6), int(scale * 2.2))
        # légère vague pour un historique lisible
        if (i // 9) % 2 == 0:
            rec = int(rec * 1.15)
        else:
            pay = int(pay * 1.15)
        rec -= rec % 100
        pay -= pay % 100
        flows.append((d, rec, pay))
    net = sum(r - p for _, r, p in flows)
    opening = level - net
    bank_gl = ledger.bank_gl(db, acc.id)
    eq = ledger.purpose_gl(db, org.id, ent.id, "OPENING_EQUITY", acc.currency)
    cin = ledger.purpose_gl(db, org.id, ent.id, "COUNTERPARTY_IN", acc.currency)
    cout = ledger.purpose_gl(db, org.id, ent.id, "COUNTERPARTY_OUT", acc.currency)
    ledger.post_entry(db, org_id=org.id, entity_id=ent.id, journal="OUV", description=f"Solde d'ouverture — {acc.name}",
                      lines=[ledger.Line(bank_gl.id, acc.currency, debit=opening), ledger.Line(eq.id, acc.currency, credit=opening)],
                      idempotency_key=f"seed:opening:{acc.id}", value_date=start, booking_date=start,
                      reference_type="seed_history", reference_id=str(acc.id))
    for k, (d, rec, pay) in enumerate(flows):
        ledger.post_entry(db, org_id=org.id, entity_id=ent.id, journal="ENC", description="Encaissements clients (historique synthétique)",
                          lines=[ledger.Line(bank_gl.id, acc.currency, debit=rec), ledger.Line(cin.id, acc.currency, credit=rec)],
                          idempotency_key=f"seed:rec:{acc.id}:{k}", value_date=d, booking_date=d, reference_type="seed_history")
        ledger.post_entry(db, org_id=org.id, entity_id=ent.id, journal="PAI", description="Règlements fournisseurs (historique synthétique)",
                          lines=[ledger.Line(cout.id, acc.currency, debit=pay), ledger.Line(bank_gl.id, acc.currency, credit=pay)],
                          idempotency_key=f"seed:pay:{acc.id}:{k}", value_date=d, booking_date=d, reference_type="seed_history")


def _bene(db, prep_p, rev_p, ent, name, country, bban, bic, category="Fournisseur", address=""):
    b = benes.create(db, prep_p, {"entity_id": ent.id, "name": name, "iban": make_iban(country, bban), "bic": bic,
                                  "country_code": country, "address": address, "category": category})
    benes.review(db, rev_p, b.id, True, "Vérification documentaire (fictive) effectuée")
    return b


def seed() -> dict:
    rng = random.Random(20261128)
    today = clock.today()
    with session_scope() as db:
        if db.scalar(select(Organization).where(Organization.name == "Groupe Lumière")):
            print("Données déjà présentes — rien à faire.")
            return {}
        for k in range(0, 100):
            fx.ensure_rates(db, today - timedelta(days=k))
        org = Organization(name="Groupe Lumière", base_currency="EUR", is_demo=True)
        db.add(org)
        db.flush()
        fr = LegalEntity(organization_id=org.id, name="Lumière France", country_code="FR", country_name="France",
                         registration_number="RCS fictif 000 000 001", lei="HZNDEMO0000000000FR1")
        de = LegalEntity(organization_id=org.id, name="Lumière Deutschland", country_code="DE", country_name="Allemagne",
                         registration_number="HRB fiktiv 00001", lei="HZNDEMO0000000000DE1")
        it = LegalEntity(organization_id=org.id, name="Lumière Italia", country_code="IT", country_name="Italie",
                         registration_number="REA fittizio 000001", lei="HZNDEMO0000000000IT1")
        db.add_all([fr, de, it])
        db.flush()
        audit.record(db, organization_id=org.id, actor_user_id=None, actor_label="Initialisation des données de démonstration",
                     action="seed.organization_created", object_type="organization", object_id=org.id)

        claire = _user(db, org, "claire.martin@lumiere.example", "Claire Martin", "Trésorerie groupe")
        sophie = _user(db, org, "sophie.bernard@lumiere.example", "Sophie Bernard", "Directrice financière groupe")
        marc = _user(db, org, "marc.lefevre@lumiere.example", "Marc Lefèvre", "Responsable trésorerie France")
        katrin = _user(db, org, "katrin.weber@lumiere.example", "Katrin Weber", "Leiterin Finanzen Deutschland")
        giulia = _user(db, org, "giulia.romano@lumiere.example", "Giulia Romano", "Responsabile tesoreria Italia")
        julien = _user(db, org, "julien.moreau@lumiere.example", "Julien Moreau", "Administrateur technique")
        ines = _user(db, org, "ines.garnier@lumiere.example", "Inès Garnier", "Auditrice interne")

        acc_fr = _bank_account(db, org, fr, "Lumière France — Compte principal", make_iban("FR", "99999000010001234567891"),
                               "HZDMFRP1XXX", "EUR")
        acc_de = _bank_account(db, org, de, "Lumière Deutschland — Geschäftskonto", make_iban("DE", "999990000002345678"),
                               "HZDMDEF1XXX", "EUR")
        acc_it = _bank_account(db, org, it, "Lumière Italia — Conto principale", make_iban("IT", "X9999900001000003456789"),
                               "HZDMITM1XXX", "EUR")
        acc_usd = _bank_account(db, org, fr, "Lumière France — Compte USD", make_iban("FR", "99999000010007654321012"),
                                "HZDMFRP1XXX", "USD")
        acc_ext = _bank_account(db, org, fr, "Lumière France — Compte GBP (autre établissement)",
                                make_iban("GB", "HZXT99999912345678"), "HZXTGB21XXX", "GBP", kind="EXTERNAL_READONLY",
                                provider="Relevé externe simulé (lecture seule)")
        observed = datetime.combine(today - timedelta(days=2), time(18, 0), tzinfo=timezone.utc)
        db.add(ExternalBalanceSnapshot(organization_id=org.id, account_id=acc_ext.id, booked_minor=to_minor("850000.00", "GBP"),
                                       available_minor=to_minor("850000.00", "GBP"), currency="GBP",
                                       source="Relevé externe simulé — fin de journée", statement_reference="EXT-STMT-0042",
                                       observed_at=observed, received_at=observed + timedelta(minutes=40)))

        ref = "Délégation de pouvoirs fictive du 02/01/2026"
        _role(db, org, claire, "VIEWER")
        _role(db, org, claire, "PREPARER")
        _role(db, org, sophie, "VIEWER")
        _role(db, org, sophie, "APPROVER", limit="5000000.00", ref=ref)
        _role(db, org, marc, "VIEWER", fr)
        _role(db, org, marc, "APPROVER", fr, acc_fr, limit="1000000.00", ref=ref + " — limitée au compte principal")
        for u, e, lim in ((katrin, de, "1000000.00"), (giulia, it, "500000.00")):
            _role(db, org, u, "VIEWER", e)
            _role(db, org, u, "PREPARER", e)
            _role(db, org, u, "APPROVER", e, limit=lim, ref=ref)
        _role(db, org, julien, "ADMIN")
        _role(db, org, ines, "AUDITOR")
        db.add_all([
            ApprovalPolicyRule(organization_id=org.id, name="Groupe — paiement courant", min_amount_minor=0, required_approvals=1),
            ApprovalPolicyRule(organization_id=org.id, name="Groupe — à partir de 50 000 €", min_amount_minor=to_minor("50000", "EUR"),
                               required_approvals=2),
            ApprovalPolicyRule(organization_id=org.id, name="Compte principal France — courant", account_id=acc_fr.id,
                               min_amount_minor=0, required_approvals=1),
            ApprovalPolicyRule(organization_id=org.id, name="Compte principal France — à partir de 50 000 €", account_id=acc_fr.id,
                               min_amount_minor=to_minor("50000", "EUR"), required_approvals=2),
            ApprovalPolicyRule(organization_id=org.id, name="Compte principal France — à partir de 2 M€", account_id=acc_fr.id,
                               min_amount_minor=to_minor("2000000", "EUR"), required_approvals=3),
        ])
        db.flush()

        for acc, key in ((acc_fr, "FR"), (acc_de, "DE"), (acc_it, "IT")):
            _history(db, org, db.get(LegalEntity, acc.entity_id), acc, to_minor(TARGETS[key], "EUR"), 90, rng)

        P = {u.email: principal_for(db, u) for u in (claire, sophie, marc, katrin, giulia, julien, ines)}
        pc, ps = P[claire.email], P[sophie.email]
        B = {}
        B["acier"] = _bene(db, pc, ps, fr, "Acier Rhône SAS", "FR", "99999000020000011122201", "HZDMFRP2XXX", address="Lyon (fictif)")
        B["logistique"] = _bene(db, pc, ps, fr, "Logistique Seine SARL", "FR", "99999000020000022233301", "HZDMFRP2XXX")
        B["emballages"] = _bene(db, pc, ps, fr, "Emballages Garonne SA", "FR", "99999000020000033344401", "HZDMFRP2XXX")
        B["electricite"] = _bene(db, pc, ps, fr, "Électricité Pyrénées SAS", "FR", "99999000020000044455501", "HZDMFRP2XXX")
        B["imprimerie"] = _bene(db, pc, ps, fr, "Imprimerie Vasseur SARL", "FR", "99999000020000055566601", "HZDMFRP2XXX")
        B["delorme"] = _bene(db, pc, ps, fr, "Cabinet Delorme Conseil", "FR", "99999000020000066677701", "HZDMFRP2XXX",
                             category="Prestataire")
        B["garnier"] = _bene(db, pc, ps, fr, "Transports Garnier SAS", "FR", "99999000020000077788801", "HZDMFRP2XXX")
        B["ostwald"] = _bene(db, pc, ps, de, "Maschinenbau Ostwald GmbH", "DE", "999990000099990404", "HZDMDEF2XXX")
        B["rheinpark"] = _bene(db, pc, ps, de, "Immobilien Rheinpark GmbH", "DE", "999990000011112222", "HZDMDEF2XXX",
                               category="Bailleur")
        B["stadtwerke"] = _bene(db, pc, ps, de, "Stadtwerke Nordheim", "DE", "999990000033334444", "HZDMDEF2XXX")
        B["kreditbank"] = _bene(db, pc, ps, de, "Demo-Kreditbank AG (fiktiv)", "DE", "999990000055556666", "HZDMDEF3XXX",
                                category="Prêteur")
        B["adriatico"] = _bene(db, pc, ps, it, "Servizi Adriatico Srl", "IT", "X9999900002000000111222", "HZDMITM2XXX",
                               category="Prestataire")
        B["brera"] = _bene(db, pc, ps, it, "Consulenze Brera SpA", "IT", "X9999900002000000333444", "HZDMITM2XXX")
        # Bénéficiaire modifié après approbation → nouvelle revue requise (centre de décisions)
        benes.update(db, pc, B["garnier"].id, {"iban": make_iban("FR", "99999000030000099988801"),
                                               "bic": "HZDMFRP3XXX"})

        # Lots en attente d'approbation (préparés par Claire Martin)
        def pending(acc, label, lines, key):
            batch, _ = payments.create_batch(db, pc, {"debtor_account_id": str(acc.id), "label": label,
                                                      "kind": "SINGLE" if len(lines) == 1 else "SUPPLIER_BATCH",
                                                      "execution_date": (today + timedelta(days=2)).isoformat(),
                                                      "payments": lines}, f"seed:{key}")
            payments.submit_for_approval(db, pc, batch.id, batch.version)
            return batch

        pending(acc_it, "Prestations de services – Q4",
                [{"beneficiary_id": str(B["adriatico"].id), "amount": "125000.00", "remittance_info": "Fattura 2026-Q4-118"}], "it-q4")
        pending(acc_de, "Loyers et charges – Déc.",
                [{"beneficiary_id": str(B["rheinpark"].id), "amount": "210000.00", "remittance_info": "Miete Dezember 2026"},
                 {"beneficiary_id": str(B["stadtwerke"].id), "amount": "78000.00", "remittance_info": "Energie Nov 2026"},
                 {"beneficiary_id": str(B["rheinpark"].id), "amount": "47000.00", "remittance_info": "Nebenkosten Q4"}], "de-loyers")
        pending(acc_fr, "Honoraires et licences – Déc.",
                [{"beneficiary_id": str(B["delorme"].id), "amount": "300000.00", "remittance_info": "Honoraires mission 2026"}], "fr-hon")

        # Encaissements attendus (4 dans les 7 jours = 3,6 M€) + horizon plus long
        receipts = [
            (acc_fr, "Hôtellerie Saint-Clair SA", "FAC-2026-1182", "1200000.00", 2, "HIGH"),
            (acc_de, "Kaufhaus Nord AG", "RE-2026-0931", "1000000.00", 3, "HIGH"),
            (acc_fr, "Distribution Rhône SAS", "FAC-2026-1190", "900000.00", 5, "HIGH"),
            (acc_it, "Gruppo Vela SpA", "FT-2026-0544", "500000.00", 6, "MEDIUM"),
            (acc_fr, "Résidences Côte d'Opale", "FAC-2026-1214", "1450000.00", 16, "HIGH"),
            (acc_de, "Bahnhof Logistik GmbH", "RE-2026-0977", "820000.00", 21, "MEDIUM"),
            (acc_it, "Cantieri Lario Srl", "FT-2026-0571", "690000.00", 27, "MEDIUM"),
            (acc_fr, "Groupe Hôtelier Atlantique", "FAC-2027-0012", "2100000.00", 38, "LOW"),
            (acc_de, "Messe Süd GmbH", "RE-2027-0044", "1300000.00", 52, "LOW"),
            (acc_fr, "Collectivité fictive de Val-Clair", "FAC-2027-0051", "1750000.00", 66, "MEDIUM"),
            (acc_it, "Porto Ligure SpA", "FT-2027-0090", "980000.00", 75, "LOW"),
        ]
        for acc, cp, refn, amt, days, conf in receipts:
            db.add(ExpectedReceipt(organization_id=org.id, entity_id=acc.entity_id, account_id=acc.id, counterparty=cp,
                                   reference=refn, amount_minor=to_minor(amt, "EUR"), currency="EUR",
                                   expected_date=today + timedelta(days=days), confidence=conf))
        start = today - timedelta(days=60)
        for acc, label, cat, direction, amt, dom in (
            (acc_fr, "Salaires France", "Salaires", "OUT", "1650000.00", 28),
            (acc_de, "Gehälter Deutschland", "Salaires", "OUT", "980000.00", 27),
            (acc_it, "Stipendi Italia", "Salaires", "OUT", "560000.00", 27),
            (acc_fr, "TVA à décaisser", "Fiscalité", "OUT", "420000.00", 19),
            (acc_fr, "Loyer siège Paris", "Loyers", "OUT", "185000.00", 1),
            (acc_fr, "Achats fournisseurs récurrents (France)", "Achats", "OUT", "1100000.00", 5),
            (acc_de, "Wiederkehrende Lieferantenzahlungen", "Achats", "OUT", "600000.00", 8),
            (acc_it, "Pagamenti fornitori ricorrenti", "Achats", "OUT", "350000.00", 10),
            (acc_fr, "Encaissements clients récurrents (France)", "Encaissements", "IN", "600000.00", 12),
            (acc_fr, "Encaissements clients récurrents (France) — 2e quinzaine", "Encaissements", "IN", "550000.00", 26),
            (acc_de, "Wiederkehrende Kundenzahlungen", "Encaissements", "IN", "500000.00", 15),
            (acc_it, "Incassi ricorrenti clienti", "Encaissements", "IN", "300000.00", 20),
        ):
            db.add(RecurringAssumption(organization_id=org.id, entity_id=acc.entity_id, account_id=acc.id, label=label,
                                       category=cat, direction=direction, amount_minor=to_minor(amt, "EUR"), currency="EUR",
                                       day_of_month=dom, start_date=start))
        db.add_all([
            CashflowScenario(organization_id=org.id, code="CENTRAL", name="Scénario central", is_baseline=True,
                             description="Encaissements à confiance haute et moyenne à leur date ; paiements en attente "
                                         "d'approbation inclus ; hypothèses récurrentes sans majoration.",
                             include_low_confidence=False, include_pending_approval=True),
            CashflowScenario(organization_id=org.id, code="PRUDENT", name="Scénario prudent",
                             description="Encaissements décotés de 10 % et retardés de 5 jours ; décaissements récurrents "
                                         "majorés de 5 % ; confiance faible exclue.",
                             receipts_haircut_pct=10, receipts_delay_days=5, disbursements_uplift_pct=5,
                             include_low_confidence=False, include_pending_approval=True),
            CashflowScenario(organization_id=org.id, code="FAVORABLE", name="Scénario favorable",
                             description="Tous les encaissements attendus (y compris confiance faible) à leur date ; "
                                         "paiements en attente d'approbation exclus.",
                             include_low_confidence=True, include_pending_approval=False),
        ])

        # Financement
        rcf = FinancingFacility(organization_id=org.id, entity_id=fr.id, reference="RCF-LUM-2025-01", kind="RCF",
                                label="Crédit renouvelable syndiqué 2025-2030", lender="Pool bancaire fictif (démonstration)",
                                committed_minor=to_minor("20000000", "EUR"), currency="EUR", signed_date=date(2025, 6, 30),
                                maturity_date=date(2030, 6, 30), interest_rate_bps=385,
                                rate_description="Taux de référence fictif + marge 0,85 %", repayment_account_id=acc_fr.id)
        tl = FinancingFacility(organization_id=org.id, entity_id=de.id, reference="TL-LUM-DE-2024-02", kind="TERM_LOAN",
                               label="Prêt amortissable équipement", lender="Demo-Kreditbank AG (fiktiv)",
                               committed_minor=to_minor("6000000", "EUR"), currency="EUR", signed_date=date(2024, 12, 12),
                               maturity_date=date(2029, 12, 12), interest_rate_bps=410,
                               rate_description="Taux fixe fictif 4,10 %", repayment_beneficiary_id=B["kreditbank"].id,
                               repayment_account_id=acc_de.id)
        db.add_all([rcf, tl])
        db.flush()
        db.add(FinancingDrawdown(facility_id=rcf.id, amount_minor=to_minor("8000000", "EUR"), currency="EUR",
                                 drawdown_date=date(2026, 3, 16)))
        db.add(FinancingDrawdown(facility_id=tl.id, amount_minor=to_minor("6000000", "EUR"), currency="EUR",
                                 drawdown_date=date(2024, 12, 12)))
        outstanding = to_minor("4500000", "EUR")
        for q in range(0, 6):
            due = today + timedelta(days=14) + timedelta(days=91 * q)
            interest = outstanding * 410 // 10000 // 4
            db.add(FinancingInstallment(organization_id=org.id, facility_id=tl.id, due_date=due,
                                        principal_minor=to_minor("500000", "EUR"), interest_minor=interest - interest % 100,
                                        currency="EUR", owner_user_id=katrin.id))
            outstanding -= to_minor("500000", "EUR")
        contract = docs.store(db, org_id=org.id, entity_id=de.id, title="Contrat de prêt TL-LUM-DE-2024-02 (fictif)",
                              category="Contrat de financement", filename="contrat-TL-LUM-DE-2024-02.pdf",
                              content_type="application/pdf", facility_id=tl.id, source="SEED",
                              data=text_pdf("Contrat de pret amortissable (FICTIF)",
                                            ["Emprunteur : Lumiere Deutschland (fictive)", "Preteur : Demo-Kreditbank AG (fictive)",
                                             "Montant : 6 000 000 EUR - Taux fixe fictif 4,10 %",
                                             "Echeances trimestrielles de 500 000 EUR de principal",
                                             "Document genere pour la demonstration, sans valeur juridique."]))
        tl.document_ids = [str(contract.id)]

        # Commerce international — dossier documentaire
        tf = TradeFile(organization_id=org.id, entity_id=fr.id, reference="IMP-2026-014",
                       title="Importation de centres d'usinage (Japon)", direction="IMPORT",
                       instrument_considered="Crédit documentaire envisagé — non émis (hors périmètre)",
                       amount_minor=to_minor("2350000", "USD"), currency="USD", owner_user_id=claire.id)
        db.add(tf)
        db.flush()
        db.add_all([
            TradeParty(trade_file_id=tf.id, role="Importateur", name="Lumière France", country_code="FR"),
            TradeParty(trade_file_id=tf.id, role="Exportateur", name="Kōgyō Seiki K.K. (fictif)", country_code="JP"),
            TradeParty(trade_file_id=tf.id, role="Transitaire", name="Transitaire Atlantique SAS (fictif)", country_code="FR"),
            TradeDeadline(trade_file_id=tf.id, label="Date limite d'expédition", due_date=today + timedelta(days=45)),
            TradeDeadline(trade_file_id=tf.id, label="Présentation des documents", due_date=today + timedelta(days=60)),
            TradeTask(trade_file_id=tf.id, label="Obtenir le certificat d'origine", assignee_user_id=claire.id,
                      due_date=today + timedelta(days=20)),
            TradeTask(trade_file_id=tf.id, label="Valider l'assurance transport", assignee_user_id=claire.id,
                      due_date=today + timedelta(days=10), status="IN_PROGRESS"),
            TradeRequest(trade_file_id=tf.id, kind="Demande d'information", created_by=claire.id, status="DRAFT",
                         body="Demande d'informations sur les pièces requises pour un éventuel crédit documentaire. "
                              "Aucun engagement n'est demandé ni émis dans cette démonstration."),
        ])
        for title, fname, lines in (
            ("Facture pro forma PF-88412 (fictive)", "proforma-PF-88412.pdf", ["Vendeur : Kogyo Seiki K.K. (fictif)",
                                                                              "Acheteur : Lumiere France", "2 centres d'usinage - 2 350 000 USD"]),
            ("Projet de connaissement (fictif)", "connaissement-projet.pdf", ["Port de chargement : Yokohama",
                                                                              "Port de dechargement : Le Havre", "Projet non contractuel"]),
        ):
            docs.store(db, org_id=org.id, entity_id=fr.id, title=title, category="Commerce international", filename=fname,
                       content_type="application/pdf", data=text_pdf(title, lines), trade_file_id=tf.id, source="SEED")

        # Écart volontaire au relevé du simulateur : frais non comptabilisés (révélé au rapprochement)
        bank.add_fee_line(acc_fr.iban, to_minor("35.00", "EUR"), "EUR", "Frais de tenue de compte — novembre",
                          f"FEE-{acc_fr.id}-{today.strftime('%Y%m')}")

        # Locataire distinct pour démontrer l'isolation des organisations
        atlas = Organization(name="Groupe Atlas (locataire d'isolation)", base_currency="EUR", is_demo=True)
        db.add(atlas)
        db.flush()
        atlas_ent = LegalEntity(organization_id=atlas.id, name="Atlas SAS", country_code="FR", country_name="France")
        db.add(atlas_ent)
        db.flush()
        lucas = _user(db, atlas, "lucas.petit@atlas.example", "Lucas Petit", "Trésorier (autre organisation)")
        _role(db, atlas, lucas, "VIEWER")
        _role(db, atlas, lucas, "PREPARER")
        acc_atlas = _bank_account(db, atlas, atlas_ent, "Atlas SAS — Compte courant", make_iban("FR", "99999000090000000001234"),
                                  "HZDMFRP9XXX", "EUR")
        _history(db, atlas, atlas_ent, acc_atlas, to_minor("1000000", "EUR"), 10, rng)
        db.add(CashflowScenario(organization_id=atlas.id, code="CENTRAL", name="Scénario central", is_baseline=True))
        audit.record(db, organization_id=org.id, actor_user_id=None, actor_label="Initialisation des données de démonstration",
                     action="seed.completed", details={"anchor_date": today.isoformat()})
        return {"organization_id": str(org.id)}


if __name__ == "__main__":
    print(seed())
