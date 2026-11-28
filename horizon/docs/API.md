# API HORIZON `/v1`

Documentation interactive : `http://localhost:8000/docs` (Swagger) et `/redoc` ; spécification figée :
[`openapi.json`](openapi.json) (83 chemins).

## Conventions

| Sujet | Règle |
|---|---|
| Version | Préfixe `/v1` ; en-tête optionnel `Horizon-API-Version: 2026-11-01` (toute autre valeur → `400 UNSUPPORTED_API_VERSION`) ; la réponse rappelle la version. |
| Authentification | `Authorization: Bearer <jeton>` (obtenu après MFA) ou cookie `horizon_session` + `X-Horizon-CSRF: 1` sur les écritures. |
| Réauthentification | `POST /v1/auth/step-up` avant une action sensible ; sinon `401 STEP_UP_REQUIRED`. |
| Montants | Chaînes décimales (`"480000.00"`) + devise ; réponses : `{"amount","currency","minor_units"}`. |
| Erreurs | `{"error": {"code", "message", "details", "request_id"}}` ; `request_id` = en-tête `X-Request-ID`. |
| Validation | Pydantic, champs inconnus refusés → `422 VALIDATION_ERROR` avec le détail par champ. |
| Pagination | `?limit=1..200&cursor=<opaque>` → `{"data": [...], "page": {"limit", "total", "next_cursor"}}`. |
| Idempotence | `Idempotency-Key` sur `POST /v1/payment-batches` (rejeu → 200 + `Idempotent-Replayed: true`). |
| Concurrence | `expected_version` (modification, soumission) et `version` (approbation) → `409 VERSION_MISMATCH`. |

Codes fréquents : `FORBIDDEN`, `SEGREGATION_OF_DUTIES`, `APPROVAL_LIMIT_EXCEEDED`, `ALREADY_DECIDED`,
`INSUFFICIENT_FUNDS`, `INVALID_TRANSITION`, `NOT_CANCELLABLE`, `ACCOUNT_READ_ONLY`, `IBAN_FORMAT_INVALID`,
`QUOTE_EXPIRED`, `QUOTE_INDICATIVE`, `INTEGRITY_GUARD`.

## Points d'entrée demandés

| Méthode | Chemin | Description |
|---|---|---|
| GET | `/v1/overview` | Indicateurs calculés + justification, comptes, centre de décisions, paiements récents |
| GET | `/v1/accounts` | Comptes visibles avec soldes expliqués |
| GET | `/v1/accounts/{account_id}/transactions` | Écritures affectant le compte (paginé) |
| POST | `/v1/beneficiaries` | Création (version 1 en revue) |
| POST | `/v1/payment-batches` | Virement unitaire ou lot |
| POST | `/v1/payment-batches/{batch_id}/submit-for-approval` | Contrôles + règle d'approbation |
| POST | `/v1/payment-batches/{batch_id}/approvals` | Décision sur une version précise |
| GET | `/v1/payments/{payment_id}` | Détail, historique, retours |
| POST | `/v1/cashflow-scenarios` | Nouveau scénario |
| GET | `/v1/forecasts/{forecast_id}` | Prévision figée (entrées, série, lignes, exclusions) |
| POST | `/v1/fx-quotes` | Devis indicatif ou exécutable simulé |
| GET | `/v1/reconciliation-cases` | Cas de rapprochement |
| GET | `/v1/audit-events` | Journal d'audit (rôles Audit/Administration) |

Autres : authentification (`/v1/auth/*`, `/v1/me`, `/v1/directory`), consolidation, registre (journal, balance,
contrepassation), bénéficiaires (revue, suspension, versions), import CSV, annulation, traitement des rejets,
cycle de vie (`/v1/payment-lifecycle`), prévisions (`POST /v1/forecasts`, graphique), encaissements attendus,
hypothèses, rapprochement (exécution, accusé, résolution), centre de décisions, change (taux, acceptation),
financement (contrats, échéances, préparation, simulations, demandes), documents (téléversement, liens),
commerce international, administration (utilisateurs, mandats, politiques, délégations), vérification de la
chaîne d'audit, export, webhook du simulateur, contrôles de démonstration (`/v1/demo/*`).

## Exemple (curl)

```bash
API=http://localhost:8000
CH=$(curl -s -X POST $API/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"claire.martin@lumiere.example","password":"Horizon-Demo-2026!"}' | jq -r .challenge_id)
CODE=$(curl -s $API/v1/auth/demo-users | jq -r '.users[] | select(.email=="claire.martin@lumiere.example") | .current_totp')
TOKEN=$(curl -s -X POST $API/v1/auth/mfa -H 'Content-Type: application/json' \
  -d "{\"challenge_id\":\"$CH\",\"code\":\"$CODE\"}" | jq -r .token)
curl -s $API/v1/overview -H "Authorization: Bearer $TOKEN" | jq '.kpis[] | {label, value}'
```

`/v1/auth/demo-users` (codes TOTP des utilisateurs fictifs) n'existe qu'en démonstration
(`HORIZON_DEMO_SHOW_TOTP=true`, refusé hors `HORIZON_ENV=demo|test`).
