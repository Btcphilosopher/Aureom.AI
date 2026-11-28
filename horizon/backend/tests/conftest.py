"""Infrastructure de test.

* Base PostgreSQL réelle (pas de SQLite : triggers, verrous et index partiels
  font partie de ce qui est testé).
* Une base modèle ``<nom>_template`` est migrée et peuplée une fois ; chaque
  test reçoit une copie fraîche (CREATE DATABASE ... TEMPLATE), ce qui isole
  totalement les tests en ~0,3 s.
"""
from __future__ import annotations

import os
import tempfile
import uuid

import pytest

TEST_DB_URL = os.environ.get("HORIZON_TEST_DATABASE_URL",
                             "postgresql+psycopg://horizon:horizon@localhost:5433/horizon_test")
os.environ["HORIZON_DATABASE_URL"] = TEST_DB_URL
os.environ["HORIZON_ENV"] = "test"
os.environ.setdefault("HORIZON_STORAGE_PATH", tempfile.mkdtemp(prefix="horizon-objects-"))

import psycopg  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from horizon.core import clock  # noqa: E402
from horizon.core.config import reset_settings  # noqa: E402
from horizon.core.db import reset_engine  # noqa: E402

URL = make_url(TEST_DB_URL)
DB_NAME = URL.database
TEMPLATE = f"{DB_NAME}_template"


def _admin_conn():
    return psycopg.connect(host=URL.host, port=URL.port, user=URL.username, password=URL.password, dbname="postgres",
                           autocommit=True)


def _recreate(name: str, template: str | None = None) -> None:
    with _admin_conn() as c:
        c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        c.execute(f'CREATE DATABASE "{name}"' + (f' TEMPLATE "{template}"' if template else ""))


@pytest.fixture(scope="session", autouse=True)
def template_db():
    """Migre (Alembic) et peuple la base modèle une seule fois par session."""
    from alembic import command
    from alembic.config import Config

    _recreate(TEMPLATE)
    os.environ["HORIZON_DATABASE_URL"] = TEST_DB_URL.rsplit("/", 1)[0] + f"/{TEMPLATE}"
    reset_settings()
    reset_engine()
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.upgrade(cfg, "head")
    from horizon.seed import seed

    seed()
    reset_engine()
    os.environ["HORIZON_DATABASE_URL"] = TEST_DB_URL
    reset_settings()
    yield


@pytest.fixture(autouse=True)
def fresh_db(template_db):
    reset_engine()
    _recreate(DB_NAME, TEMPLATE)
    clock.reset()
    yield
    clock.reset()
    reset_engine()


@pytest.fixture
def db():
    from horizon.core.db import SessionLocal

    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


class Api:
    """Client HTTP en processus avec connexion MFA et réauthentification."""

    USERS = {
        "claire": "claire.martin@lumiere.example", "sophie": "sophie.bernard@lumiere.example",
        "marc": "marc.lefevre@lumiere.example", "katrin": "katrin.weber@lumiere.example",
        "giulia": "giulia.romano@lumiere.example", "julien": "julien.moreau@lumiere.example",
        "ines": "ines.garnier@lumiere.example", "lucas": "lucas.petit@atlas.example",
    }

    def __init__(self):
        from fastapi.testclient import TestClient

        from horizon.main import app

        self.c = TestClient(app)
        self.tokens: dict[str, str] = {}

    def login(self, who):
        from horizon.core.crypto import totp_now
        from horizon.seed import DEMO_PASSWORD, demo_totp_secret

        email = self.USERS[who]
        r = self.c.post("/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD})
        assert r.status_code == 200, r.text
        r = self.c.post("/v1/auth/mfa", json={"challenge_id": r.json()["challenge_id"],
                                               "code": totp_now(demo_totp_secret(email))})
        assert r.status_code == 200, r.text
        self.tokens[who] = r.json()["token"]
        self.c.cookies.clear()
        return self.tokens[who]

    def h(self, who):
        if who not in self.tokens:
            self.login(who)
        return {"Authorization": f"Bearer {self.tokens[who]}"}

    def step_up(self, who):
        from horizon.core.crypto import totp_now
        from horizon.seed import demo_totp_secret

        r = self.c.post("/v1/auth/step-up", headers=self.h(who), json={"code": totp_now(demo_totp_secret(self.USERS[who]))})
        assert r.status_code == 200, r.text

    def get(self, who, path, **kw):
        return self.c.get(path, headers={**self.h(who), **kw.pop("headers", {})}, **kw)

    def post(self, who, path, **kw):
        return self.c.post(path, headers={**self.h(who), **kw.pop("headers", {})}, **kw)

    def patch(self, who, path, **kw):
        return self.c.patch(path, headers={**self.h(who), **kw.pop("headers", {})}, **kw)

    # --- raccourcis métier ---
    def accounts(self, who="claire"):
        return {a["name"]: a for a in self.get(who, "/v1/accounts", params={"limit": 200}).json()["data"]}

    def beneficiaries(self, who="claire"):
        return {b["current_version"]["name"]: b for b in
                self.get(who, "/v1/beneficiaries", params={"limit": 200}).json()["data"]}

    def account(self, prefix, who="claire"):
        return next(a for n, a in self.accounts(who).items() if n.startswith(prefix))

    def batch(self, lines, account="Lumière France — Compte principal", who="claire", label="Lot de test",
              execution_date=None, key=None, submit=True):
        acc = self.account(account, who)
        benes = self.beneficiaries(who)
        body = {"debtor_account_id": acc["id"], "label": label,
                "payments": [{"beneficiary_id": benes[n]["id"], "amount": a, "remittance_info": r} for n, a, r in lines]}
        if execution_date:
            body["execution_date"] = execution_date
        headers = {"Idempotency-Key": key} if key else {}
        r = self.post(who, "/v1/payment-batches", json=body, headers=headers)
        assert r.status_code == 201, r.text
        b = r.json()
        if submit:
            r = self.post(who, f"/v1/payment-batches/{b['id']}/submit-for-approval", json={"expected_version": b["version"]})
            assert r.status_code == 200, r.text
            b = r.json()
        return b

    def approve(self, who, batch, version=None, expect=200):
        self.step_up(who)
        r = self.post(who, f"/v1/payment-batches/{batch['id']}/approvals",
                      json={"decision": "APPROVE", "version": version or batch["version"]})
        assert r.status_code == expect, r.text
        return r.json()

    def run_jobs(self):
        from horizon.modules.jobs import queue

        return queue.drain()

    def get_batch(self, batch_id, who="claire"):
        return self.get(who, f"/v1/payment-batches/{batch_id}").json()


@pytest.fixture
def api():
    return Api()


FR_LINES = [("Acier Rhône SAS", "120000.00", "FAC 1"), ("Logistique Seine SARL", "60000.00", "FAC 2")]


def new_id():
    return str(uuid.uuid4())
