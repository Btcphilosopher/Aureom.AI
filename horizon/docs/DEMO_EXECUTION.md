# Démonstration HORIZON — journal d'exécution

ENVIRONNEMENT DE DÉMONSTRATION · données synthétiques · aucun service bancaire réel


## Étape 1 — Consultation des comptes

- ✔ Lumière France : disponible 12400000.00 EUR (comptabilisé 12400000.00, réservé 0.00)
- ✔ Lumière Deutschland : disponible 7800000.00 EUR (comptabilisé 7800000.00, réservé 0.00)
- ✔ Lumière Italia : disponible 4600000.00 EUR (comptabilisé 4600000.00, réservé 0.00)
- ✔ Liquidités disponibles (calculées) : 24800000.00 EUR — formule : Σ (solde comptabilisé − réservations actives) des comptes SIMULÉS, chaque solde converti en EUR au dernier taux daté
- ✔ Compte externe en lecture seule présenté à part : Lumière France — Compte GBP (autre établissement) — fraîcheur Données périmées (44.9 h)

## Étape 2 — Création d'un bénéficiaire

- ✔ Contrôle IBAN FR8499999000040000012345601 : format_valid=True (variante altérée : False, Clé de contrôle (modulo 97) incorrecte) — « Contrôle de format uniquement : ne prouve ni l'existence du compte ni l'identité du titulaire. »
- ✔ Bénéficiaire créé par Claire Martin : Fonderie Loire SAS — statut En revue
- ✔ Claire ne peut pas valider sa propre création : FORBIDDEN
- ✔ Sophie Bernard (approbatrice, réauthentifiée) valide la version 1 → statut Actif

## Étape 3 — Préparation d'un lot fournisseurs de 480 000 €

- ✔ Lot LOT-2026-00004 créé : 7 paiements, 480000.00 EUR ; rejeu avec la même Idempotency-Key → même lot (HTTP 200, Idempotent-Replayed)
- ✔ Soumis pour approbation : En attente d'approbation — 2 approbations distinctes requises ; éligibles : Sophie Bernard, Marc Lefèvre
- ✔ Tableau de bord : 12 paiements à approuver pour 1240000.00 EUR ; alertes : 3

## Étape 4 — Approbation par deux utilisateurs distincts

- ✔ Préparatrice (Claire) → refus : FORBIDDEN
- ✔ Administrateur technique (Julien) → refus : FORBIDDEN (l'administration n'inclut pas l'approbation)
- ✔ Sophie sans réauthentification → STEP_UP_REQUIRED
- ✔ Approbation d'une version obsolète → VERSION_MISMATCH
- ✔ Sophie Bernard approuve la version 1 → 1/2
- ✔ Seconde approbation par la même personne → ALREADY_DECIDED
- ✔ Marc Lefèvre approuve → quorum 2/2, lot Approuvé ; réservé 480000.00 EUR, disponible 11920000.00 EUR, comptabilisé inchangé 12400000.00 EUR

## Étape 5 — Exécution simulée

- ✔ 15 tâches traitées ; lot Traitement terminé — {'EXECUTED': 7}
- ✔ Parcours ligne 1 : En attente d'approbation → Approuvé → Soumis → Réception technique → Accepté par le système destinataire → Exécuté selon confirmation
- ✔ Réception technique 14:54:43 · acceptation 14:54:43 · exécution (règlement confirmé) 14:54:43 — référence SIMREF-CE69D880DA22
- ✔ Compte France : comptabilisé 11920000.00 EUR (−480 000), réservations consommées
- ✔ Balance générale équilibrée dans chaque devise

## Étape 6 — Réception d'un événement dupliqué sans double débit

- ✔ Événement sim-evt-ce83fa65-146… redélivré → DUPLICATE_IGNORED (livraisons en double : 1) ; solde inchangé 11920000.00 EUR ; une seule écriture pour le paiement

## Étape 7 — Traitement d'un paiement rejeté

- ✔ Lot LOT-2026-00005 approuvé (Katrin Weber + Sophie Bernard) puis Rejeté par le destinataire : AC04 — Compte du bénéficiaire clôturé ; réservation libérée, aucun débit
- ✔ Accusé de réception enregistré : l'alerte reste présente (la cause n'est pas résolue)
- ✔ Rejet traité avec justification → l'élément quitte le centre de décisions

## Étape 8 — Gestion d'un résultat inconnu

- ✔ TIMEOUT_AFTER_RECORD : paiement HZN2026000060001 → Résultat inconnu ; cas de rapprochement ouvert
- ✔ TIMEOUT_AFTER_RECORD : Recherche effectuée : ordre retrouvé chez le destinataire (état RECEIVED) — aucune nouvelle soumission → Exécuté selon confirmation ; tentatives de soumission : 1 (même clé hzn-8630d4c3-a5b…)
- ✔ TIMEOUT_BEFORE_RECORD : paiement HZN2026000070001 → Résultat inconnu ; cas de rapprochement ouvert
- ✔ TIMEOUT_BEFORE_RECORD : Recherche effectuée : ordre introuvable chez le destinataire → nouvelle soumission avec la même clé d'idempotence → Exécuté selon confirmation ; tentatives de soumission : 2 (même clé hzn-5dfc9e18-9b4…)
- ✔ Chez le destinataire : exactement un ordre par clé d'idempotence (aucune double exécution)

## Étape 9 — Mise à jour de la prévision sans double comptage

- ✔ Point de départ : 24800000.00 → 24283200.00 EUR (le lot exécuté est passé du « prévu » au « comptabilisé »)
- ✔ Prévision J+1 avant/après : 24320000.00 / 24283200.00 — écart -36800.00 sur tout l'horizon = uniquement les 2 × 18 400 de l'étape 8 ; le lot de 480 000 n'est compté ni deux fois ni zéro fois (le rejet de 300 000, créé après le premier calcul, n'y figure jamais)
- ✔ Encaissement attendu « Hôtellerie Saint-Clair SA » (1 200 000) reçu : comptabilisé +1 200 000, sorti des encaissements attendus ; solde prévu à J+30 inchangé (25642075.00 EUR)
- ✔ Rapprochement : 11 lignes, 10 rapprochées, écart détecté : Frais de tenue de compte — novembre (2026-11-28) présent au relevé, absent du registre
- ✔ Écart résolu par écriture de régularisation liée (journal FRA)

## Étape 10 — Consultation d'une échéance de financement

- ✔ Prêt amortissable équipement (TL-LUM-DE-2024-02) : échéance du 2026-12-12 — principal 500000.00, intérêts 46125.00, total 546125.00 EUR — À préparer, responsable Katrin Weber
- ✔ Contrat : engagé 6000000.00 EUR, utilisé 6000000.00 EUR — Contrat accepté (fictif)
- ✔ Katrin Weber prépare et soumet le paiement (LOT-2026-00008) ; la prévision compte le paiement et exclut l'échéance : « Échéance préparée : comptée via son paiement »

## Étape 11 — Simulation d'un devis de change

- ✔ Taux indicatif EUR/USD : vente 250000.00 EUR → 269728.50 USD au taux client 1.078914 (médian 1.0805350000, marge 15 pb = 375.05 EUR) — source « Simulateur de taux HORIZON (synthétique, non contractuel) » — Taux indicatif — non exécutable
- ✔ Acceptation d'un taux indicatif → QUOTE_INDICATIVE
- ✔ Offre exécutable SIMULÉE (expire à 14:55:15) acceptée par Sophie Bernard → ACCEPTED_SIMULATED ; écriture CHG équilibrée par devise via les positions de change ; aucun ordre réel
- ✔ Balance : EUR équilibrée, USD équilibrée

## Étape 12 — Export d'un rapport et de sa piste d'audit

- ✔ Archive "horizon-rapport-20261128-145445.zip" (SHA-256 b1e06982251fa1b3…) : rapport.csv, piste_audit.csv, manifeste.json
- ✔ Manifeste : 100 événements d'audit, chaîne vérifiée = True
- ✔ Vérification indépendante de la chaîne : valide=True sur 101 événements
- ✔ Refus d'accès tracés (access.denied) : 3 — ex. Claire Martin sur « beneficiary.approve » (DENIED)

Démonstration terminée avec succès.
