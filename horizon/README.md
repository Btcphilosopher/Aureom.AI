# HORIZON — Banque d'entreprise et trésorerie

> **ENVIRONNEMENT DE DÉMONSTRATION** · Concept indépendant · Données synthétiques · Aucun service bancaire réel
>
> HORIZON est un prototype inspiré d'une maquette de poste de trésorerie. Ce n'est **pas** un produit officiel de
> BNP Paribas ni d'aucun établissement : il n'utilise ni leur nom ni leur logo, n'accède à aucun système bancaire
> et ne déplace aucun fonds. Toutes les entreprises, personnes, comptes, IBAN, taux et opérations sont fictifs.
> Ne saisissez jamais de véritables identifiants bancaires.

![Tableau de bord](docs/screenshots/dashboard.png)

Des soldes explicables, des paiements contrôlés, des prévisions transparentes et une responsabilité identifiable à
chaque étape : chaque indicateur du tableau de bord est **calculé** depuis le registre et ouvre sa justification
(formule, composantes, taux datés, exclusions).

## Démarrage rapide (Docker Compose)

```bash
cp .env.example .env
```

```bash
docker compose up --build
```

* Interface : <http://localhost:3000> · API : <http://localhost:8000/docs>
* Le conteneur `migrate` applique les migrations, crée le Groupe Lumière, puis rejoue les étapes 1 à 3 de la
  démonstration : l'interface s'ouvre dans l'**état de la maquette** (24,80 M€ ; 12 paiements à approuver pour
  1,24 M€ ; 3,60 M€ attendus sur 7 jours ; 3 alertes ; lot fournisseurs de 480 000 € en attente).
* Le travailleur (`worker`) exécute les paiements approuvés contre le simulateur bancaire.
* Ports d'hôte modifiables : `HORIZON_API_PORT`, `HORIZON_WEB_PORT`. Sauvegarde : `docker compose --profile ops run --rm backup`.

### Utilisateurs fictifs (mot de passe `Horizon-Demo-2026!`)

L'écran de connexion affiche le code TOTP courant de chaque utilisateur fictif (démonstration uniquement).

| Utilisateur | Fonction | Rôles |
|---|---|---|
| Claire Martin | Trésorerie groupe | Consultation + Préparation (groupe) |
| Sophie Bernard | Directrice financière groupe | Consultation + Approbation (groupe, plafond 5 M€) |
| Marc Lefèvre | Responsable trésorerie France | Consultation France + Approbation **limitée au compte principal France** (1 M€) |
| Katrin Weber | Leiterin Finanzen Deutschland | Consultation, Préparation, Approbation (Allemagne, 1 M€) |
| Giulia Romano | Responsabile tesoreria Italia | Consultation, Préparation, Approbation (Italie, 500 k€) |
| Julien Moreau | Administrateur technique | Administration (**aucun droit d'approbation**) |
| Inès Garnier | Auditrice interne | Audit |
| Lucas Petit | Autre organisation (« Groupe Atlas ») | Sert à démontrer l'isolation |

Parcours conseillé : Sophie Bernard → centre de décisions → « Examiner » → approuver (code MFA demandé) ;
Marc Lefèvre → approuver → le travailleur exécute → « Traitement terminé ».

## Démonstration reproductible (12 étapes)

```bash
cd backend && ./scripts/reset_demo_db.sh && python -m horizon.demo --report ../docs/DEMO_EXECUTION.md
```

Consultation des comptes · création d'un bénéficiaire · lot fournisseurs de 480 000 € · approbation par deux
personnes distinctes · exécution simulée · événement dupliqué sans double débit · paiement rejeté · résultat
inconnu · prévision sans double comptage · échéance de financement · devis de change · export du rapport et de sa
piste d'audit. Chaque étape vérifie ses résultats ; journal : [`docs/DEMO_EXECUTION.md`](docs/DEMO_EXECUTION.md).

## Développement local

Prérequis : Python 3.13, PostgreSQL 16, Node 22.

```bash
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
```

```bash
export HORIZON_DATABASE_URL=postgresql+psycopg://horizon:horizon@localhost:5433/horizon
```

```bash
./scripts/reset_demo_db.sh --mockup-state
```

```bash
uvicorn horizon.main:app --port 8000
```

```bash
python -m horizon.worker
```

```bash
cd frontend && npm ci && npm run build && npm start
```

Sans travailleur, le panneau « Démonstration » de l'administration (ou `POST /v1/demo/run-jobs`) traite la file.

## Tests

```bash
cd backend && python -m pytest
```

Base PostgreSQL réelle (`HORIZON_TEST_DATABASE_URL`, défaut `…/horizon_test`) ; une base modèle migrée et peuplée
est clonée pour chaque test.

```bash
cd frontend && npx playwright test --trace off
```

Résultats réels : [`docs/RESULTATS_TESTS.md`](docs/RESULTATS_TESTS.md) — **83 tests backend réussis**, **8 tests
navigateur réussis** contre la pile Docker Compose, démonstration 12/12.

## Documentation

| Document | Contenu |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Monolithe modulaire, adaptateurs, base, versions des dépendances |
| [PAIEMENTS.md](docs/PAIEMENTS.md) | Cycle de vie et transitions, approbations, exécution, doublons, résultat inconnu |
| [REGISTRE_ET_SOLDES.md](docs/REGISTRE_ET_SOLDES.md) | Partie double, règles du solde disponible, change, consolidation |
| [PREVISIONS.md](docs/PREVISIONS.md) | Méthode déterministe, scénarios, fourchette, absence de double comptage |
| [SECURITE_ET_EXPLOITATION.md](docs/SECURITE_ET_EXPLOITATION.md) | MFA, permissions, isolation, secrets, audit, sauvegardes, prérequis réglementaires |
| [API.md](docs/API.md) · [openapi.json](docs/openapi.json) | Conventions et points d'entrée |
| [STATUT_DES_FONCTIONS.md](docs/STATUT_DES_FONCTIONS.md) | Opérationnel / simulé / intégré / reporté |
| [RESULTATS_TESTS.md](docs/RESULTATS_TESTS.md) | Sorties réelles des tests |

## Avant toute utilisation réelle

Identifier le rôle réglementaire visé, les marchés et les intégrations envisagées, puis rechercher les exigences
applicables auprès des sources officielles actuelles. Voir
[SECURITE_ET_EXPLOITATION.md §9](docs/SECURITE_ET_EXPLOITATION.md#9-avant-toute-utilisation-réelle).
