# Prévisions de trésorerie — méthode déterministe `deterministe-v1`

Horizons : 7, 30 et 90 jours. Devise de présentation : EUR (conversion au taux daté, référence fournie).

## 1. Point de départ

**Solde comptabilisé** des comptes simulés visibles à la date d'arrêté — et non le disponible : les montants
réservés correspondent à des paiements prévus, comptés comme décaissements au point 2. Utiliser le disponible
les soustrairait deux fois (test `test_forecast_starts_from_booked_not_available`).

## 2. Flux, chacun avec sa source

| Catégorie | Inclus | Sort de la prévision quand… |
|---|---|---|
| Paiements | `APPROVED`, `SCHEDULED`, `SUBMITTED`, `ACCEPTED`, `UNKNOWN` (par prudence) et, selon le scénario, `PENDING_APPROVAL` | il est **exécuté** (il est alors dans le solde comptabilisé) ou rejeté/annulé |
| Encaissements attendus | état `EXPECTED` (confiance faible selon le scénario) | il est **rapproché** d'un crédit réel (`RECEIVED`) |
| Échéances de financement | non payées | un paiement de remboursement **compté** les couvre (sinon l'échéance reste comptée, avec une note) |
| Hypothèses récurrentes | occurrences futures | l'occurrence est **réalisée**, ou un paiement compté la référence (`forecast_ref = recurring:<id>:<date>`) |

Un flux échu non réalisé (date ≤ arrêté) est placé à J+1 et signalé `overdue`. Les comptes externes en lecture
seule sont exclus (données non contrôlées) et listés dans `excluded`, avec chaque exclusion motivée.

## 3. Scénarios (seed)

| Code | Encaissements | Décaissements récurrents | Confiance faible | En attente d'approbation |
|---|---|---|---|---|
| `CENTRAL` | à date | sans majoration | exclus | inclus |
| `PRUDENT` | −10 %, +5 jours | +5 % | exclus | inclus |
| `FAVORABLE` | à date | sans majoration | inclus | exclus |

`POST /v1/cashflow-scenarios` permet d'en créer d'autres (décote, retard, majoration, inclusions).

## 4. Fourchette

La zone affichée autour de la prévision est l'**enveloppe quotidienne (min/max) des scénarios Prudent, Central
et Favorable**. Ce n'est **pas** un intervalle de confiance statistique ; l'API le dit (`band_method`) et le
graphique le légende. Aucune méthode statistique n'est revendiquée dans cette version.

## 5. Historique et frontière

L'historique observé provient des soldes comptabilisés quotidiens du registre (date de valeur). La série
observée se termine exactement à la date d'arrêté, qui est aussi le premier point de la série prévue
(`boundary_date`) : la frontière historique/prévision est nette.

## 6. Traçabilité

`POST /v1/forecasts` fige un calcul (`ForecastRun`) : entrées (soldes de départ par compte, taux utilisés),
série quotidienne, lignes détaillées (source, identifiant, montant d'origine, note) et exclusions motivées.
`GET /v1/forecasts/{id}` le restitue à l'identique.

## 7. Absence de double comptage — preuves

* `test_execution_moves_amount_from_planned_to_observed_without_double_count` : J+1…J+30 identiques avant et après
  exécution d'un lot.
* `test_received_expected_receipt_leaves_forecast` : solde de fin d'horizon inchangé après encaissement.
* `test_recurring_occurrence_covered_by_payment_is_not_counted_twice`.
* Démonstration, étapes 9 et 10.
