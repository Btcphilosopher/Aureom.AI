# Registre en partie double, soldes et consolidation

## 1. Plan de comptes (par entité et par devise)

| Finalité (`purpose`) | Type | Préfixe | Usage |
|---|---|---|---|
| `BANK` | Actif | 512 | Miroir comptable d'un compte bancaire **simulé** (un par compte) |
| `OPENING_EQUITY` | Capitaux | 101 | Contrepartie des soldes d'ouverture |
| `COUNTERPARTY_OUT` | Passif | 401 | Tiers payés (paiements sortants, retours) |
| `COUNTERPARTY_IN` | Actif | 411 | Encaissements clients |
| `FX_POSITION` | Actif | 476 | Position de change — **une par devise** |
| `BANK_FEES` | Charge | 627 | Frais bancaires (régularisations de rapprochement) |
| `SUSPENSE` | Actif | 471 | Compte d'attente |

Journaux : `OUV` ouverture · `ENC` encaissements · `PAI` paiements · `RET` retours · `CHG` change ·
`FRA` frais · `COR` corrections et contrepassations.

## 2. Règles

1. **Montants entiers** en unités mineures (`BIGINT`), conversions en `Decimal` (arrondi bancaire). Aucun `float`.
   Une précision excédentaire est refusée (`INVALID_AMOUNT_PRECISION`).
2. **Équilibre par devise** : pour chaque écriture et chaque devise, Σ débits = Σ crédits.
   Vérifié deux fois : dans `ledger.post_entry` (erreur `ENTRY_UNBALANCED`) **et** par un trigger PostgreSQL
   de contrainte différé (`journal_lines_balanced`) qui refuse le `COMMIT` même si le service est contourné.
3. **Une ligne = un seul côté** (contrainte `CHECK`), montant positif, devise = devise du compte comptable.
4. **Immuabilité** : triggers `journal_entries_immutable` / `journal_lines_immutable` (UPDATE/DELETE interdits).
5. **Corrections liées** : contrepassation (`reverses_entry_id`, unique : une seule contrepassation par écriture,
   pas de contrepassation de contrepassation) et écriture de correction (`corrects_entry_id`).
6. **Idempotence** : `idempotency_key` unique (`payment-execution:<id>`, `payment-return:<event>`,
   `fx-quote:<id>`, `reco-adjust:<case>`…). Rejouer un traitement ne double jamais un effet.
7. **Référence aux opérations** : `reference_type` / `reference_id` (paiement, devis, ligne de relevé…).

## 3. Écritures types

| Opération | Débit | Crédit |
|---|---|---|
| Ouverture | 512 Banque | 101 Contrepartie d'ouverture |
| Encaissement | 512 Banque | 411 Tiers – encaissements |
| Paiement exécuté (sur confirmation) | 401 Tiers – paiements | 512 Banque |
| Retour de fonds | 512 Banque | 401 Tiers – paiements |
| Frais (régularisation) | 627 Frais | 512 Banque |
| **Change** EUR → USD | 476 Position EUR (EUR) · 512 Banque USD (USD) | 512 Banque EUR (EUR) · 476 Position USD (USD) |

Change : l'écriture comporte quatre lignes ; elle s'équilibre **dans chaque devise** séparément grâce aux comptes
de position. Une écriture « naïve » Dr USD 100 000 / Cr EUR 100 000 est refusée (test
`test_fx_entry_must_balance_in_each_currency`). La marge de change est incluse dans le taux client et affichée
séparément (en devise vendue) sur le devis.

## 4. Soldes d'un compte simulé

```
Solde comptabilisé = Σ débits − Σ crédits du compte 512 lié (date de valeur ≤ date)
Montants réservés  = Σ réservations ACTIVE du compte
Solde disponible   = Solde comptabilisé − Montants réservés
```

* Une réservation est créée à l'**approbation finale** d'un paiement (sous verrou du compte), consommée à son
  **exécution confirmée**, libérée en cas de rejet, d'annulation ou d'invalidation.
* « Opérations en attente » = paiements `SUBMITTED` / `ACCEPTED` / `UNKNOWN` : listées, mais **déjà couvertes**
  par leur réservation — jamais soustraites deux fois.
* Source : « Registre HORIZON en partie double (simulé) », fraîcheur : temps réel.

Le seed ne saisit aucun solde : 12 400 000 € / 7 800 000 € / 4 600 000 € résultent d'une écriture d'ouverture
il y a 90 jours puis de 90 jours de flux synthétiques équilibrés (test
`test_seed_balances_are_derived_from_balanced_entries`).

## 5. Comptes externes en lecture seule

`kind = EXTERNAL_READONLY` : aucun compte comptable, aucun paiement possible (`ACCOUNT_READ_ONLY`). Le solde
affiché est celui du dernier relevé (`ExternalBalanceSnapshot`) avec **source**, **heure d'observation**, heure de
réception et **fraîcheur** (périmé au-delà de 24 h, paramétrable). Exemple du seed : compte GBP chez un autre
établissement, relevé de J-2 à 18 h → « Données périmées » au centre de décisions.

## 6. Consolidation multidevise

`GET /v1/consolidation` et l'indicateur « Liquidités disponibles » :

* chaque solde est converti **individuellement** en EUR au dernier taux daté disponible ; la réponse inclut
  pour chaque composante l'identifiant du taux, sa date, sa source, et s'il a été inversé ;
* deux agrégats distincts : **disponible des comptes simulés** (indicateur principal) et **estimation consolidée**
  incluant les soldes externes observés ;
* jamais d'addition de montants de devises différentes ; avertissement si une composante est périmée.

Taux : `DeterministicRateProvider` (synthétique, reproductible, ±0,4 % autour d'une référence fixe) — non
contractuel et sans lien avec le marché.
