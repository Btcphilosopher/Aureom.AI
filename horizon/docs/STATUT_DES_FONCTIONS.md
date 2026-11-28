# Statut des fonctions

Légende :

* **Opérationnel** : implémenté, actif dans l'application et couvert par des tests automatisés.
* **Simulé** : fonctionne de bout en bout contre un simulateur déterministe ou des données synthétiques ; aucun
  système réel n'est appelé.
* **Intégré (adaptateur)** : interface d'intégration et implémentation présentes, testées hors production
  (émulateur) ou non activées par défaut.
* **Reporté** : volontairement hors périmètre de cette version ; l'emplacement est préparé ou documenté.

| Domaine | Fonction | Statut | Remarques |
|---|---|---|---|
| Interface | Tableau de bord fidèle à la maquette, 9 sections, indicateurs cliquables avec justification | Opérationnel | Pas de logo BNP Paribas : identité « HORIZON » originale |
| Interface | Panneau de démonstration (file, pannes, redélivrance, retours) | Simulé | Désactivable (`HORIZON_DEMO_CONTROLS=false`) |
| Identité | Connexion organisationnelle, MFA TOTP, réauthentification, sessions révocables | Opérationnel | Fournisseur local d'identifiants fictifs |
| Identité | Fournisseur d'identité d'entreprise (OIDC/SAML), WebAuthn, anti-rejeu TOTP | Reporté | Interface `IdentityProvider` prête |
| Organisations | Groupe, entités, utilisateurs, mandats, rôles, plafonds, délégations, politiques | Opérationnel | Administration via API et interface |
| Permissions | Contrôle serveur par entité et par compte, isolation des organisations | Opérationnel | 5 rôles ; l'administration n'approuve jamais |
| Comptes | Solde comptabilisé, réservé, disponible, opérations en attente | Opérationnel | Sur comptes simulés |
| Comptes | Comptes externes en lecture seule, fraîcheur, données périmées | Simulé | Relevé synthétique ; pas de connexion à une autre banque |
| Comptes | Consolidation multidevise à taux datés | Opérationnel | Taux synthétiques |
| Registre | Partie double, équilibre par devise, immuabilité, contrepassations, réservations, change | Opérationnel | Garde-fous PostgreSQL |
| Bénéficiaires | Versions, revue à quatre yeux, suspension, invalidation des approbations | Opérationnel | |
| Bénéficiaires | Contrôle de format IBAN | Opérationnel | Ne prouve ni l'existence ni le titulaire |
| Bénéficiaires | Vérification du nom du bénéficiaire auprès d'un service tiers | Reporté | Affiché « non effectué » |
| Paiements | Virement unitaire, lot, planification, import CSV, annulation, statuts | Opérationnel | |
| Paiements | Soumission, acceptation, règlement, rejet, retour de fonds | Simulé | Simulateur bancaire déterministe (règles documentées) |
| Paiements | Résultat inconnu, recherche avant nouvelle soumission, reprise après interruption | Opérationnel (contre simulateur) | |
| Paiements | Rappel de fonds après transmission | Reporté | Annulation refusée après soumission |
| Paiements | Messages ISO 20022 (pain.001, pain.002, camt.053…) | Reporté | **Aucune compatibilité SEPA/SWIFT revendiquée** |
| Approbations | Séparation des tâches, seuils, quorum distinct, plafonds, restriction par compte, expiration, réauthentification, historique | Opérationnel | |
| Prévisions | 7/30/90 jours, scénarios, encaissements, échéances, hypothèses récurrentes, sans double comptage | Opérationnel | Méthode déterministe documentée |
| Prévisions | Fourchette | Opérationnel | Enveloppe de scénarios — pas un intervalle statistique |
| Prévisions | Méthodes statistiques | Reporté | |
| Financement | Contrats, utilisations, échéances, préparation du remboursement | Simulé | Contrats fictifs |
| Financement | Simulations et demandes | Opérationnel | Aucun octroi automatique ; revue humaine hors démo |
| Change | Taux indicatifs, devis (paire, sens, montants, taux, frais, source, expiration) | Simulé | |
| Change | Acceptation d'une offre exécutable | Simulé | Écriture entre comptes simulés ; **aucun ordre réel** |
| Commerce international | Dossiers : parties, documents, échéances, demandes, tâches, décisions, historique | Opérationnel | Gestion documentaire uniquement |
| Commerce international | Émission de garantie, crédit documentaire, confirmation | Reporté | Exige un processus institutionnel |
| Documents | Téléversement contrôlé, empreinte, chiffrement au repos, liens temporaires signés | Opérationnel | |
| Documents | Stockage S3 compatible | Intégré (adaptateur) | Testé contre l'émulateur `moto` ; Compose utilise le volume chiffré |
| Documents | Analyse antivirus, OCR, import depuis messagerie | Reporté | |
| Rapprochement | Relevé ↔ registre, cas avec responsable/échéance, accusé ≠ résolution, régularisation liée | Opérationnel (contre relevé simulé) | |
| Centre de décisions | Lots, bénéficiaires, échéances, rejets, écarts, résultats inconnus, données périmées | Opérationnel | |
| Intégrations | Comptes/relevés, paiements, notifications, taux, identité, import de documents | Intégré (adaptateur) | Simulateurs uniquement ; notifications journalisées, jamais envoyées |
| Intégrations | Connexion à une banque, un réseau de paiement ou un fournisseur de données réels | Reporté | Aucun accès ni partenariat revendiqué |
| API | `/v1`, pagination, validation, erreurs structurées, versionnement, idempotence, OpenAPI | Opérationnel | `docs/openapi.json` |
| Audit | Journal chaîné en ajout seul, refus tracés, export avec manifeste | Opérationnel | |
| Exploitation | File de tâches idempotente, travailleur, reprise | Opérationnel | |
| Exploitation | Sauvegarde/restauration | Opérationnel | Testées automatiquement |
| Exploitation | TLS de bout en bout, KMS/HSM, supervision, limitation de débit, PRA | Reporté | Voir `SECURITE_ET_EXPLOITATION.md` §9 |
