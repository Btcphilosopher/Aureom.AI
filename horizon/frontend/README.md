# HORIZON — interface (Next.js)

Interface de démonstration du poste de travail de trésorerie HORIZON.
**ENVIRONNEMENT DE DÉMONSTRATION** — concept indépendant, données synthétiques, aucun service bancaire réel.
Aucune marque d'établissement bancaire n'est reproduite : le logotype « HORIZON » et l'illustration parisienne sont originaux.

## Pile

| Élément | Version (épinglée) |
|---|---|
| Next.js (App Router, Turbopack) | 16.4.6 |
| React / React DOM | 19.3.1 |
| TypeScript | 5.9.3 (Next 16 exige ≥ 5.1) |
| @playwright/test | 1.63.0 (identique au Chromium préinstallé) |

Aucune bibliothèque d'interface ni de graphique : composants et graphique SVG écrits à la main.
Points Next 16 pris en compte : pas de `middleware`/`proxy`, pas de `next lint`, paramètres de route lus côté client
avec `useParams()` (les `params` serveur sont asynchrones), pas de `useSearchParams` sans frontière Suspense.

## Accès à l'API

Le navigateur n'appelle que la même origine : `/api/v1/*` est réécrit vers `${BACKEND_URL}/v1/*`
(`next.config.ts`, défaut `http://localhost:8000`). `BACKEND_URL` est lu au **build** et au démarrage :
définissez-le avant `npm run build` (ex. `BACKEND_URL=http://api:8000` dans Docker).

* Session : cookie `HttpOnly`, `SameSite=Strict` posé par `/v1/auth/mfa` ;
* toute requête non-GET porte `X-Horizon-CSRF: 1` (`src/lib/api.ts`) ;
* `STEP_UP_REQUIRED` → fenêtre de réauthentification MFA puis rejeu de la requête (`src/components/StepUp.tsx`).

## Lancer

```bash
npm ci
```

```bash
npm run dev            # http://localhost:3000 (API attendue sur :8000)
```

```bash
npm run build && npm start
```

Connexion : page `/login`, utilisateurs fictifs listés (démonstration uniquement) avec leur code TOTP courant ;
mot de passe commun `Horizon-Demo-2026!`.

## Tests navigateur (Playwright)

Préparer la base en « état maquette » puis lancer l'API (depuis `../backend`, environnement virtuel actif) :

```bash
./scripts/reset_demo_db.sh --mockup-state
```

```bash
uvicorn horizon.main:app --port 8000
```

Puis, dans `frontend/` (interface servie par `npm run build && npm start`) :

```bash
npx playwright test --trace off
```

Les tests modifient l'état (approbations, exécution) : réinitialisez la base avant chaque exécution.
Ils produisent aussi `../docs/screenshots/dashboard.png` (1672×941, facteur 2) et `lot-approbation.png`.

Couverture : connexion MFA ; indicateurs calculés (24,80 M€, 12 paiements / 1,24 M€, 3,60 M€) et ouverture de la
justification de chaque indicateur ; centre de décisions ; navigation dans les 9 sections ; refus pour l'administrateur
technique et pour la préparatrice ; double approbation avec réauthentification (Sophie Bernard puis Marc Lefèvre),
refus d'une seconde approbation par la même personne ; exécution simulée (« Traitement terminé », étapes réception
technique / acceptation / exécution) ; liquidités mises à jour (24,32 M€) ; vérification de la chaîne d'audit et export.

## Structure

```
src/app/login/                     connexion + MFA
src/app/(app)/                     pages authentifiées (Shell : navigation, en-tête, réauthentification)
  page.tsx                         Vue d'ensemble (maquette)
  comptes/, comptes/[id]/          soldes, consolidation, écritures, historique
  paiements/                       lots, nouveau paiement, import CSV, bénéficiaires
  paiements/lots/[id]/             détail, approbations, versions, historique
  paiements/[id]/                  statut détaillé, traitement des rejets
  paiements/beneficiaires/[id]/    versions, vérification, revue, suspension
  tresorerie/, tresorerie/rapprochement/
  financement/, change/, commerce-international/(+[id]), documents/, administration/
src/components/                    Shell, StepUp, ForecastChart, KpiExplain, ui, icônes, illustration
src/lib/                           client API, formats fr-FR, hooks
e2e/                               tests Playwright
```
