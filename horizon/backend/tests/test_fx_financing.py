"""Change (simulation) et financement : distinctions indicatif/exécutable, expiration,
équilibre par devise, aucun octroi automatique."""
from datetime import timedelta
from decimal import Decimal

from horizon.core import clock


def ent(api, name="Lumière France"):
    return {e["name"]: e["id"] for e in api.get("claire", "/v1/me").json()["entities"]}[name]


def test_rates_are_identified_and_dated(api):
    r = api.get("claire", "/v1/fx/rates").json()
    assert r["data"] and all(x["source"] and x["as_of"] and x["id"] for x in r["data"])
    assert "synthétiques" in r["notice"]


def test_consolidation_uses_dated_rates_and_separates_external(api):
    c = api.get("claire", "/v1/consolidation").json()
    assert c["simulated_available"]["amount"] == "24800000.00"
    ext = c["external_components"][0]
    assert ext["currency"] == "GBP" and ext["rate"]["rate_id"] and ext["rate"]["as_of"] and ext["rate"]["inverted"]
    expected = (Decimal("850000.00") * Decimal(ext["rate"]["rate"])).quantize(Decimal("0.01"))
    assert Decimal(ext["observed_in_base"]["amount"]) == expected
    assert Decimal(c["consolidated_estimate"]["amount"]) == Decimal("24800000.00") + expected
    assert c["warnings"] and "périmées" in c["warnings"][0]
    usd = next(x for x in c["simulated_components"] if x["currency"] == "USD")
    assert usd["rate"]["rate_id"] is not None  # même un solde nul passe par un taux identifié


def quote(api, kind, **kw):
    body = {"entity_id": ent(api), "base": "EUR", "quote": "USD", "side": "SELL", "amount": "100000.00",
            "amount_currency": "EUR", "kind": kind, **kw}
    r = api.post("claire", "/v1/fx-quotes", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_indicative_quote_is_never_executable(api):
    q = quote(api, "INDICATIVE")
    assert Decimal(q["client_rate"]) < Decimal(q["mid_rate"])  # le client vend EUR : marge défavorable
    assert q["fee"]["currency"] == "EUR" and Decimal(q["fee"]["amount"]) > 0
    api.step_up("sophie")
    r = api.post("sophie", f"/v1/fx-quotes/{q['id']}/accept")
    assert r.status_code == 409 and r.json()["error"]["code"] == "QUOTE_INDICATIVE"


def test_executable_quote_expires(api):
    accs = api.accounts()
    q = quote(api, "EXECUTABLE_SIMULATED", sell_account_id=accs["Lumière France — Compte principal"]["id"],
              buy_account_id=accs["Lumière France — Compte USD"]["id"])
    assert q["seconds_remaining"] <= 30
    clock.advance(timedelta(seconds=31))
    api.step_up("sophie")
    r = api.post("sophie", f"/v1/fx-quotes/{q['id']}/accept")
    assert r.status_code == 409 and r.json()["error"]["code"] == "QUOTE_EXPIRED"


def test_accepted_simulated_conversion_books_per_currency(api):
    accs = api.accounts()
    q = quote(api, "EXECUTABLE_SIMULATED", sell_account_id=accs["Lumière France — Compte principal"]["id"],
              buy_account_id=accs["Lumière France — Compte USD"]["id"])
    r = api.post("claire", f"/v1/fx-quotes/{q['id']}/accept")
    assert r.status_code == 403  # la préparatrice ne peut pas exécuter
    api.step_up("sophie")
    r = api.post("sophie", f"/v1/fx-quotes/{q['id']}/accept")
    assert r.status_code == 200 and r.json()["status"] == "ACCEPTED_SIMULATED"
    accs = api.accounts()
    assert accs["Lumière France — Compte USD"]["balance"]["booked"]["amount"] == q["buy"]["amount"]
    assert accs["Lumière France — Compte principal"]["balance"]["booked"]["amount"] == "12300000.00"
    tb = api.get("claire", "/v1/ledger/trial-balance").json()["totals_by_currency"]
    assert tb["EUR"]["balanced"] and tb["USD"]["balanced"]
    r = api.post("sophie", f"/v1/fx-quotes/{q['id']}/accept")
    assert r.status_code == 409  # pas de double acceptation


def test_financing_contract_installments_and_no_automatic_grant(api):
    fac = api.get("katrin", "/v1/financing/facilities").json()["data"]
    tl = next(f for f in fac if f["kind"] == "TERM_LOAN")
    assert tl["status_label"].startswith("Contrat accepté")
    insts = api.get("katrin", "/v1/financing/installments").json()["data"]
    nxt = insts[0]
    assert nxt["status"] == "TO_PREPARE" and nxt["days_until_due"] == 14
    r = api.post("katrin", f"/v1/financing/installments/{nxt['id']}/prepare")
    assert r.status_code == 200
    assert api.post("katrin", f"/v1/financing/installments/{nxt['id']}/prepare").status_code == 409
    b = api.get_batch(r.json()["batch_id"], who="katrin")
    assert b["kind"] == "FINANCING" and b["total"]["amount"] == nxt["total"]["amount"]
    sim = api.post("claire", "/v1/financing/simulations", json={"amount": "1000000.00", "months": 24, "annual_rate_pct": 4.5})
    assert sim.status_code == 201 and "Ne constitue ni une offre" in sim.json()["result"]["disclaimer"]
    req = api.post("claire", "/v1/financing/requests", json={"entity_id": ent(api), "kind": "RCF", "amount": "5000000.00",
                                                             "purpose": "Financement du besoin en fonds de roulement"})
    assert req.status_code == 201
    assert req.json()["status"] == "SUBMITTED_FOR_REVIEW" and "aucun octroi automatique" in req.json()["status_label"]
    facs_after = api.get("claire", "/v1/financing/facilities").json()["data"]
    assert len(facs_after) == len(api.get("sophie", "/v1/financing/facilities").json()["data"])  # aucun contrat créé
