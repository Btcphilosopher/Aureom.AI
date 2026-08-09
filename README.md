# Aardvark Escrow

A production-grade escrow platform: it holds funds between two or more
parties and releases, refunds, or arbitrates them according to strict,
auditable business rules. Built for marketplaces, procurement systems,
freelance platforms, and logistics companies that need a REST API they
can integrate against, not a spreadsheet with extra steps.

**Status:** feature-complete against the original specification. 210
tests, 96.5% coverage, every endpoint live and documented.

~7,100 lines of hand-written Python (55% application code, 40% tests) —
see [Project stats](#project-stats) below.

## What it does

- **Escrows** move through a ten-state lifecycle — created, funded,
  in progress, awaiting approval, released, disputed, refunded,
  cancelled, closed — enforced by a single state machine that's the only
  code path allowed to change an escrow's status. Every transition is
  audited.
- **Wallets** use an authorization-hold model, the same mental model as
  a card pre-authorization: funding an escrow locks money without moving
  it; funds only actually transfer on release. A full, append-only
  ledger backs every balance.
- **Disputes** can be resolved three ways — release the full amount,
  refund it, or split it between both parties — always by an admin,
  never unilaterally by either side.
- **Money movement is row-locked, idempotent, and deadlock-safe** under
  genuine concurrency — not just in theory; verified with tests that
  fire real concurrent requests (`asyncio.gather` in-process, and
  separately, real parallel `curl` processes) and check the numbers land
  exactly right.
- **Everything is audited.** An immutable, admin-queryable trail of
  every security- and money-relevant action, plus downloadable PDF/CSV
  reports: escrow history, wallet statements, audit exports, operator
  activity, and a platform-wide financial summary.
- **Background workers** handle notification delivery, automatic
  cancellation of unfunded escrows past their deadline, daily wallet
  reconciliation against the ledger, and platform statistics — all real
  Celery tasks, verified against a real worker consuming from Redis.

## API surface

| Area | Endpoints |
|---|---|
| **Auth** | `POST /auth/register`, `/login`, `/refresh`, `/logout` |
| **Users** | `GET /users/me`, `PATCH /users/me` |
| **Wallet** | `GET /wallet`, `POST /wallet/deposit`, `/withdraw` |
| **Escrows** | `POST /escrows`, `GET /escrows`, `GET /escrows/{id}`, `POST .../cancel`, `/fund`, `/approve`, `/release`, `/refund`, `/dispute` |
| **Disputes** | `POST /disputes/{id}/evidence`, `/resolve` |
| **Audit** | `GET /audit` (admin) |
| **Notifications** | `GET /notifications` |
| **Reports** | `GET /reports/escrows/{id}`, `/wallet/statement`, `/audit`, `/operator-activity`, `/financial-summary` |
| **Health** | `GET /health`, `/health/live`, `/health/ready` |

Every protected endpoint accepts either a bearer JWT
(`Authorization: Bearer <token>`) or an API key (`X-API-Key: <key>`)
interchangeably. Full interactive docs at `/api/v1/docs` (Swagger) and
`/api/v1/redoc`; a static schema export lives at
[`docs/openapi.json`](docs/openapi.json).

## Stack

FastAPI · SQLAlchemy 2.x (async) · Alembic · PostgreSQL · Redis · Celery ·
Pydantic v2 · PyJWT · Passlib (Argon2) · Structlog · Prometheus ·
OpenTelemetry · ReportLab · Pytest · Docker

## Quickstart

```bash
cp .env.example .env
docker compose up --build
```

The API comes up on `http://localhost:8000`, docs at
`http://localhost:8000/api/v1/docs`.

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/health/ready   # verifies DB connectivity
```

`docker-compose.yml` runs five services: `postgres`, `redis`, `api`,
`worker` (background tasks), and `beat` (their schedule). See
[docs/deployment-guide.md](docs/deployment-guide.md) for the full
environment variable reference and a first-deploy checklist.

**Bootstrapping your first admin** — there is no self-serve way to
become one, by design:

```bash
python scripts/create_admin.py you@example.com --create --name "Your Name"
```

See [docs/administration-guide.md](docs/administration-guide.md).

## Local development without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # then point DATABASE_URL/REDIS_URL at local services
python main.py
```

Background workers run as separate processes, pointed at the same `.env`:

```bash
celery -A app.workers.celery_app worker --loglevel=info   # runs tasks
celery -A app.workers.celery_app beat --loglevel=info     # triggers them on schedule
```

## Testing

```bash
pytest --cov=app
```

This is a real integration suite — it runs against Postgres and Redis
rather than mocking them (an escrow platform's entire value is
transactional correctness, so that's what needs testing, and it's what
caught every real bug documented in
[docs/architecture.md](docs/architecture.md)). Before running it:
`docker compose up -d postgres redis`, apply migrations
(`alembic upgrade head`), and set `ENVIRONMENT=test` in `.env` — this
disables rate limiting so the suite's rapid successive requests don't
trip it.

Tests are marked by category, matching the spec's own test taxonomy:

```bash
pytest -m unit                              # pure logic, no DB — fast (~2s)
pytest -m "integration and not database"    # everything except the slower DB-focused suite
pytest -m security                          # IDOR, rate limiting, RBAC, injection resistance, ...
pytest -m escrow                            # state machine, transaction engine, disputes
pytest -m database                          # migrations + constraint tests
```

## Project layout

```
app/
  main.py            FastAPI application factory
  core/               settings, logging, exception hierarchy, redis client
  database/           async engine, session factory, declarative base, UnitOfWork
  domain/
    entities/          SQLAlchemy models — 12 tables (see docs/er-diagram.md)
    repositories/       persistence interfaces + SQLAlchemy implementations
    services/           AuthService, UserService, WalletService,
                        EscrowStateMachine, EscrowService,
                        EscrowTransactionEngine, DisputeService
  security/            JWT, Argon2 hashing, refresh tokens, API keys,
                       get_current_user / require_role
  schemas/             Pydantic request/response models
  middleware/          request context, rate limiting, security headers
  api/v1/              versioned REST endpoints (see API surface above)
  audit/               report generation — PDF (ReportLab) + CSV
  workers/             Celery app, Beat schedule, and task implementations
migrations/           Alembic environment + versions
tests/                 pytest suite — unit + integration against real Postgres/Redis
docs/                  architecture, ER diagram, guides, OpenAPI export
docker/                per-service Dockerfiles
scripts/               entrypoint.sh (Docker) + create_admin.py
```

## Documentation

- **[docs/architecture.md](docs/architecture.md)** — why the system is
  built the way it is: clean architecture layering, the escrow state
  machine, financial integrity model, dispute resolution, security
  model, background workers, reporting, testing strategy. Includes a
  running history of real bugs caught along the way and how they were
  fixed — concurrency races, an async-ORM staleness bug, a ledger
  semantics/documentation mismatch, an Alembic URL-override bug.
- **[docs/er-diagram.md](docs/er-diagram.md)** — the full schema as a
  Mermaid ER diagram, plus notes on the non-obvious relationships.
- **[docs/developer-guide.md](docs/developer-guide.md)** — practical,
  task-oriented: how to add an endpoint end-to-end, conventions actually
  enforced, and a catalogue of pitfalls this codebase has already hit
  once so nobody rediscovers them.
- **[docs/deployment-guide.md](docs/deployment-guide.md)** — services,
  every environment variable, a first-deploy checklist, scaling notes.
- **[docs/security-guide.md](docs/security-guide.md)** — operating the
  security controls: secrets, session/API-key revocation, what to watch
  in the audit trail, and the threat-model reasoning behind what was and
  wasn't built (CSRF, SQLi, IDOR, mass-assignment).
- **[docs/administration-guide.md](docs/administration-guide.md)** —
  bootstrapping the first admin, resolving disputes, running
  reconciliation on demand.
- **[docs/openapi.json](docs/openapi.json)** — static export of the full
  OpenAPI schema.

## Project stats

| | |
|---|---|
| Application code (`app/`) | 3,902 lines, 80 files |
| Tests (`tests/`) | 2,829 lines, 21 files |
| Migrations, scripts, entrypoint | 433 lines |
| **Python total** | **7,121 lines**, 105 files |
| Documentation | 1,203 lines across 7 Markdown files |
| Test coverage | 96.5% (210 tests) |

Counted with [`cloc`](https://github.com/AlDanial/cloc) (code only —
excludes blank lines and comments; comments add roughly another 1,385
lines on top, mostly the "explain why, not just what" docstrings
demonstrated throughout `app/domain/services/`).
