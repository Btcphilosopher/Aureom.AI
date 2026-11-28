"""Permissions côté serveur, isolation des organisations, authentification, CSRF,
documents protégés, journaux expurgés."""
import logging
import time

from sqlalchemy import select

from horizon.core.crypto import totp_now
from horizon.core.redaction import RedactingFilter, mask_iban, redact
from horizon.modules.audit.models import AuditEvent
from horizon.seed import demo_totp_secret
from tests.conftest import FR_LINES


def test_organization_isolation(api):
    lum = api.accounts("claire")
    atlas = api.accounts("lucas")
    assert set(atlas) == {"Atlas SAS — Compte courant"}
    fr = next(a for n, a in lum.items() if n.startswith("Lumière France — Compte principal"))
    assert api.get("lucas", f"/v1/accounts/{fr['id']}").status_code == 404
    b = api.batch(FR_LINES)
    assert api.get("lucas", f"/v1/payment-batches/{b['id']}").status_code == 404
    assert api.get("lucas", "/v1/payment-batches").json()["data"] == []
    assert api.get("lucas", "/v1/beneficiaries").json()["data"] == []
    ov = api.get("lucas", "/v1/overview").json()
    assert ov["kpis"][0]["value"]["amount"] == "1000000.00"
    # un préparateur d'une autre organisation ne peut pas utiliser un bénéficiaire Lumière
    bene = api.beneficiaries()["Acier Rhône SAS"]
    acc = next(iter(atlas.values()))
    r = api.post("lucas", "/v1/payment-batches", json={"debtor_account_id": acc["id"], "payments": [
        {"beneficiary_id": bene["id"], "amount": "1.00"}]})
    assert r.status_code == 404


def test_entity_scoped_visibility(api):
    marc = api.accounts("marc")
    assert all(a["entity"]["name"] == "Lumière France" for a in marc.values())
    de = api.account("Lumière Deutschland")
    r = api.get("marc", f"/v1/accounts/{de['id']}")
    assert r.status_code == 403
    with_denials = api.get("ines", "/v1/audit-events", params={"action": "access.denied"}).json()["data"]
    assert any(e["actor"] == "Marc Lefèvre" and e["outcome"] == "DENIED" for e in with_denials)


def test_least_privilege_roles(api):
    # Audit : lecture et audit, aucune écriture
    ents = {e["name"]: e["id"] for e in api.get("ines", "/v1/me").json()["entities"]}
    assert api.get("ines", "/v1/audit-events").status_code == 200
    r = api.post("ines", "/v1/beneficiaries", json={"entity_id": ents["Lumière France"], "name": "Test SA", "iban": "FR7630006000011234567890189",
                                                    "country_code": "FR"})
    assert r.status_code == 403
    # Administration : gestion des utilisateurs, aucune donnée de compte ni paiement
    assert api.get("julien", "/v1/admin/users").status_code == 200
    assert api.get("julien", "/v1/accounts").status_code == 403
    assert api.get("julien", "/v1/payment-batches").status_code == 403
    # Consultation/préparation : pas d'accès à l'audit ni à l'administration
    assert api.get("claire", "/v1/audit-events").status_code == 403
    assert api.get("claire", "/v1/admin/users").status_code == 403
    # Approbateur : ne prépare pas
    acc = api.account("Lumière France — Compte principal", "sophie")
    bene = api.beneficiaries("sophie")["Acier Rhône SAS"]
    r = api.post("sophie", "/v1/payment-batches", json={"debtor_account_id": acc["id"], "payments": [
        {"beneficiary_id": bene["id"], "amount": "1.00"}]})
    assert r.status_code == 403


def test_admin_cannot_grant_itself_and_needs_step_up(api):
    me = api.get("julien", "/v1/me").json()
    r = api.post("julien", "/v1/admin/role-assignments", json={"user_id": me["user"]["id"], "role": "APPROVER",
                                                                "approval_limit": "1.00"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "STEP_UP_REQUIRED"
    api.step_up("julien")
    r = api.post("julien", "/v1/admin/role-assignments", json={"user_id": me["user"]["id"], "role": "APPROVER",
                                                                "approval_limit": "1.00"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "SELF_GRANT_FORBIDDEN"


def test_authentication_flow(api):
    assert api.c.get("/v1/accounts").status_code == 401
    r = api.c.post("/v1/auth/login", json={"email": "claire.martin@lumiere.example", "password": "mauvais"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    r = api.c.post("/v1/auth/login", json={"email": "claire.martin@lumiere.example", "password": "Horizon-Demo-2026!"})
    ch = r.json()["challenge_id"]
    r = api.c.post("/v1/auth/mfa", json={"challenge_id": ch, "code": "000000"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "MFA_INVALID"
    r = api.c.post("/v1/auth/mfa", json={"challenge_id": ch, "code": totp_now(demo_totp_secret("claire.martin@lumiere.example"))})
    assert r.status_code == 200
    token = r.json()["token"]
    # le défi ne peut pas être rejoué
    r = api.c.post("/v1/auth/mfa", json={"challenge_id": ch, "code": totp_now(demo_totp_secret("claire.martin@lumiere.example"))})
    assert r.status_code == 401
    assert api.c.post("/v1/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert api.c.get("/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_cookie_session_requires_csrf_header(api):
    r = api.c.post("/v1/auth/login", json={"email": "claire.martin@lumiere.example", "password": "Horizon-Demo-2026!"})
    r = api.c.post("/v1/auth/mfa", json={"challenge_id": r.json()["challenge_id"],
                                          "code": totp_now(demo_totp_secret("claire.martin@lumiere.example"))})
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=strict" in r.headers["set-cookie"].lower()
    assert api.c.get("/v1/me").status_code == 200  # lecture via cookie
    r = api.c.post("/v1/forecasts", json={"scenario_id": "00000000-0000-0000-0000-000000000000", "horizon_days": 7})
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_HEADER_MISSING"
    r = api.c.post("/v1/forecasts", json={"scenario_id": "00000000-0000-0000-0000-000000000000", "horizon_days": 7},
                   headers={"X-Horizon-CSRF": "1"})
    assert r.status_code == 404
    api.c.cookies.clear()


def test_documents_temporary_links(api, monkeypatch):
    docs = api.get("claire", "/v1/documents").json()["data"]
    contract = next(d for d in docs if d["category"] == "Contrat de financement")
    link = api.post("claire", f"/v1/documents/{contract['id']}/links").json()
    r = api.c.get(link["url"])
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and r.headers["cache-control"] == "no-store"
    # lien altéré
    assert api.c.get(link["url"][:-2] + "00").status_code == 403
    # lien expiré
    from horizon.modules.documents import service as dsvc

    real = time.time
    monkeypatch.setattr(dsvc.time, "time", lambda: real() + 3600)
    r = api.c.get(link["url"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "LINK_EXPIRED"
    monkeypatch.setattr(dsvc.time, "time", real)
    # l'utilisateur d'une autre organisation ne peut même pas générer un lien
    assert api.post("lucas", f"/v1/documents/{contract['id']}/links").status_code == 404
    # Marc (France) ne voit pas un document de l'entité allemande
    assert api.post("marc", f"/v1/documents/{contract['id']}/links").status_code == 403


def test_document_upload_validation(api):
    ents = {e["name"]: e["id"] for e in api.get("claire", "/v1/me").json()["entities"]}
    r = api.post("claire", "/v1/documents", files={"file": ("x.pdf", b"not a pdf", "application/pdf")},
                 data={"entity_id": ents["Lumière France"], "title": "Faux PDF"})
    assert r.status_code == 415 and r.json()["error"]["code"] == "CONTENT_MISMATCH"
    r = api.post("claire", "/v1/documents", files={"file": ("x.exe", b"MZ...", "application/x-msdownload")},
                 data={"entity_id": ents["Lumière France"], "title": "Exécutable"})
    assert r.status_code == 415
    r = api.post("claire", "/v1/documents", files={"file": ("note.txt", b"bonjour", "text/plain")},
                 data={"entity_id": ents["Lumière France"], "title": "Note"})
    assert r.status_code == 201 and len(r.json()["sha256"]) == 64


def test_objects_are_encrypted_at_rest(api):
    import os

    from horizon.core.config import get_settings

    root = get_settings().storage_path
    files = [os.path.join(root, f) for f in os.listdir(root)]
    assert files
    for f in files:
        with open(f, "rb") as fh:
            assert not fh.read().startswith(b"%PDF")


def test_logs_and_audit_details_are_redacted(caplog, db):
    assert mask_iban("FR7630006000011234567890189").startswith("FR76") and "*" in mask_iban("FR7630006000011234567890189")
    red = redact({"password": "s3cret", "iban": "FR7630006000011234567890189", "nested": {"token": "abc"}})
    assert red["password"] == "[expurgé]" and red["nested"]["token"] == "[expurgé]" and "*" in red["iban"]
    logger = logging.getLogger("horizon.test")
    logger.addFilter(RedactingFilter())
    with caplog.at_level(logging.INFO):
        logger.info("Paiement vers FR7630006000011234567890189 émis")
    assert "FR7630006000011234567890189" not in caplog.text
    created = db.scalars(select(AuditEvent).where(AuditEvent.action == "beneficiary.created")).first()
    assert "*" in created.details["iban"]
