"""Application FastAPI HORIZON — monolithe modulaire."""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from horizon.api import accounts, admin, auth, documents, markets, payments, treasury
from horizon.core.config import get_settings
from horizon.core.db import SessionLocal
from horizon.core.errors import DomainError
from horizon.core.redaction import configure_logging, redact

# Enregistre les gestionnaires de tâches.
import horizon.modules.payments.execution  # noqa: F401,E402

log = logging.getLogger("horizon.api")
SUPPORTED_VERSIONS = {"2026-11-01"}

DESCRIPTION = """
**HORIZON — Banque d'entreprise et trésorerie** · ENVIRONNEMENT DE DÉMONSTRATION

Concept indépendant. Données synthétiques. Aucun service bancaire réel, aucun accès à un système bancaire,
aucun déplacement de fonds. Ce prototype n'est pas un produit officiel d'un établissement bancaire.

* Versionnement : préfixe `/v1` + en-tête optionnel `Horizon-API-Version` (valeur prise en charge : `2026-11-01`).
* Erreurs structurées : `{"error": {"code", "message", "details", "request_id"}}`.
* Pagination : `limit` (1–200) et `cursor` opaque ; réponse `{"data": [...], "page": {...}}`.
* Idempotence : en-tête `Idempotency-Key` sur la création de lots.
* Authentification : session après MFA (TOTP) ; cookie `HttpOnly` + en-tête `X-Horizon-CSRF: 1`, ou jeton Bearer.
"""


def create_app() -> FastAPI:
    configure_logging()
    st = get_settings()
    app = FastAPI(title="HORIZON API", version=st.api_version, description=DESCRIPTION,
                  openapi_tags=[{"name": "Vue d'ensemble"}, {"name": "Identité"}, {"name": "Comptes et registre"},
                                {"name": "Bénéficiaires"}, {"name": "Paiements"}, {"name": "Trésorerie"},
                                {"name": "Rapprochement"}, {"name": "Centre de décisions"}, {"name": "Change"},
                                {"name": "Financement"}, {"name": "Documents et commerce international"},
                                {"name": "Administration et audit"}, {"name": "Intégrations"}, {"name": "Démonstration"}])

    @app.middleware("http")
    async def context_mw(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid[:64]
        ver = request.headers.get("horizon-api-version")
        if ver and ver not in SUPPORTED_VERSIONS:
            return JSONResponse(status_code=400, content={"error": {
                "code": "UNSUPPORTED_API_VERSION", "message": f"Version d'API non prise en charge : {ver}",
                "details": {"supported": sorted(SUPPORTED_VERSIONS)}, "request_id": rid}})
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Horizon-API-Version"] = st.api_version
        response.headers["X-Horizon-Environment"] = "demonstration"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    def _err(request: Request, status: int, code: str, message: str, details=None):
        return JSONResponse(status_code=status, content={"error": {
            "code": code, "message": message, "details": details,
            "request_id": getattr(request.state, "request_id", None)}})

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return _err(request, exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return _err(request, 422, "VALIDATION_ERROR", "Requête invalide", details)

    @app.exception_handler(DBAPIError)
    async def db_error(request: Request, exc: DBAPIError):
        msg = str(exc.orig) if exc.orig else str(exc)
        if "HORIZON:" in msg:
            return _err(request, 409, "INTEGRITY_GUARD", msg.split("HORIZON:")[1].split("\n")[0].strip())
        if "unique" in msg.lower() or "duplicate key" in msg.lower():
            return _err(request, 409, "CONFLICT", "Opération concurrente ou doublon détecté — réessayez")
        log.exception("Erreur base de données : %s", redact(msg))
        return _err(request, 500, "DATABASE_ERROR", "Erreur interne")

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("Erreur non gérée : %s", redact(str(exc)))
        return _err(request, 500, "INTERNAL_ERROR", "Erreur interne")

    for r in (auth.router, auth.me_router, accounts.router, payments.router, treasury.router, markets.router,
              documents.router, admin.router):
        app.include_router(r)

    @app.get("/health", tags=["Exploitation"])
    def health():
        return {"status": "ok", "environment": "DÉMONSTRATION"}

    @app.get("/ready", tags=["Exploitation"])
    def ready():
        with SessionLocal() as s:
            rev = s.execute(text("SELECT version_num FROM alembic_version")).scalar()
        return {"status": "ready", "schema_revision": rev}

    return app


app = create_app()
