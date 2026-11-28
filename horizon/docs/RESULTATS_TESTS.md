# Résultats réels des tests

Exécutés le 28 novembre 2026 dans l'environnement de développement (Linux, Python 3.13.18, PostgreSQL 16, Node 22, Chromium Playwright 1.63). Sorties brutes reproduites ci-dessous, sans retouche autre que la suppression des pourcentages de progression.

| Suite | Commande | Résultat |
|---|---|---|
| Backend (pytest, PostgreSQL réel) | `cd backend && python -m pytest -vv` | **83 réussis, 0 échec, 0 ignoré** (38 s) |
| Backend dans le conteneur Compose | `docker compose run --rm -e HORIZON_TEST_DATABASE_URL=… api python -m pytest` | 80 réussis, 2 ignorés (pas de `pg_dump` ni de super-utilisateur dans le conteneur), image antérieure au test S3 |
| Navigateur (Playwright) contre `next start` + uvicorn | `npx playwright test --trace off` | **7 réussis** (+ test de délégation ajouté ensuite : 1 réussi) |
| Navigateur contre la pile **Docker Compose** complète (base neuve, vrai travailleur) | `E2E_BASE_URL=http://localhost:13000 npx playwright test --trace off` | **8 réussis, 0 échec** (19,5 s) |
| Démonstration en 12 étapes | `python -m horizon.demo --report ../docs/DEMO_EXECUTION.md` | **12/12 étapes, toutes les vérifications passées** (4,1 s) — voir [DEMO_EXECUTION.md](DEMO_EXECUTION.md) |
| Build de production frontend | `npm run build` | réussi, 0 erreur TypeScript |

## Couverture des exigences de test

| Exigence | Tests |
|---|---|
| Écritures équilibrées | `test_ledger.py` (service + trigger PostgreSQL contourné, une ligne = un côté, équilibre par devise pour le change) |
| Approbations concurrentes | `test_concurrent_approvals_finalize_exactly_once`, `test_concurrent_double_click_same_approver` |
| Versions | `test_approval_targets_precise_version`, `test_material_change_invalidates_prior_approvals`, `test_stale_edit_rejected`, `test_payment_keeps_pinned_beneficiary_version`, `test_versions_are_immutable_in_database` |
| Soldes réservés | `test_two_distinct_approvers_reach_quorum_and_reserve_funds`, `test_insufficient_funds_blocks_final_approval`, `test_forecast_starts_from_booked_not_available` |
| Doublons | `test_duplicate_event_does_not_double_debit` (même event_id ET autre event_id), `test_idempotency_key`, `test_enqueue_is_idempotent`, `test_posting_is_idempotent` |
| Résultats inconnus | `test_unknown_result_after_record_is_searched_not_resubmitted`, `test_unknown_result_before_record_resubmits_with_same_key`, `test_interrupted_submission_is_recovered` |
| Permissions | `test_security.py` (isolation, périmètre entité/compte, rôles minimaux, admin sans approbation), `test_preparer_cannot_approve_own_batch`, `test_account_restriction_on_mandate`, `test_delegation_is_capped_and_counts_as_distinct_approver`, `test_rights_revoked_before_execution_block_submission` |
| Consolidation | `test_consolidation_uses_dated_rates_and_separates_external`, `test_overview_kpis_are_computed_and_explained` |
| Restauration | `test_backup_and_restore_roundtrip` (base vierge, empreintes comparées, sauvegarde altérée refusée) |

## Sortie pytest

```
tests/test_approvals.py::test_two_distinct_approvers_reach_quorum_and_reserve_funds PASSED
tests/test_approvals.py::test_preparer_cannot_approve_own_batch PASSED  
tests/test_approvals.py::test_technical_admin_cannot_approve PASSED     
tests/test_approvals.py::test_step_up_is_required_and_expires PASSED    
tests/test_approvals.py::test_same_approver_counts_once PASSED          
tests/test_approvals.py::test_approval_targets_precise_version PASSED   
tests/test_approvals.py::test_material_change_invalidates_prior_approvals PASSED
tests/test_approvals.py::test_stale_edit_rejected PASSED                
tests/test_approvals.py::test_approval_limit_enforced PASSED            
tests/test_approvals.py::test_account_restriction_on_mandate PASSED     
tests/test_approvals.py::test_delegation_is_capped_and_counts_as_distinct_approver PASSED
tests/test_approvals.py::test_expired_approvals_do_not_count PASSED     
tests/test_approvals.py::test_insufficient_funds_blocks_final_approval PASSED
tests/test_approvals.py::test_concurrent_approvals_finalize_exactly_once PASSED
tests/test_approvals.py::test_concurrent_double_click_same_approver PASSED
tests/test_approvals.py::test_rights_revoked_before_execution_block_submission PASSED
tests/test_approvals.py::test_reject_decision_cancels_batch PASSED      
tests/test_backup_restore_demo.py::test_backup_and_restore_roundtrip PASSED
tests/test_backup_restore_demo.py::test_full_twelve_step_demo PASSED    
tests/test_beneficiaries.py::test_iban_format_check_is_not_proof_of_existence PASSED
tests/test_beneficiaries.py::test_four_eyes_review PASSED               
tests/test_beneficiaries.py::test_versions_are_immutable_in_database PASSED
tests/test_beneficiaries.py::test_suspension_blocks_payments PASSED     
tests/test_forecast.py::test_execution_moves_amount_from_planned_to_observed_without_double_count PASSED
tests/test_forecast.py::test_forecast_starts_from_booked_not_available PASSED
tests/test_forecast.py::test_received_expected_receipt_leaves_forecast PASSED
tests/test_forecast.py::test_recurring_occurrence_covered_by_payment_is_not_counted_twice PASSED
tests/test_forecast.py::test_band_is_envelope_of_documented_scenarios PASSED
tests/test_forecast.py::test_scenario_creation_and_horizon_validation PASSED
tests/test_forecast.py::test_external_accounts_excluded_and_stated PASSED
tests/test_fx_financing.py::test_rates_are_identified_and_dated PASSED  
tests/test_fx_financing.py::test_consolidation_uses_dated_rates_and_separates_external PASSED
tests/test_fx_financing.py::test_indicative_quote_is_never_executable PASSED
tests/test_fx_financing.py::test_executable_quote_expires PASSED        
tests/test_fx_financing.py::test_accepted_simulated_conversion_books_per_currency PASSED
tests/test_fx_financing.py::test_financing_contract_installments_and_no_automatic_grant PASSED
tests/test_ledger.py::test_seed_balances_are_derived_from_balanced_entries PASSED
tests/test_ledger.py::test_every_entry_is_balanced_per_currency PASSED  
tests/test_ledger.py::test_service_rejects_unbalanced_entry PASSED      
tests/test_ledger.py::test_database_trigger_rejects_unbalanced_lines_even_bypassing_service PASSED
tests/test_ledger.py::test_one_sided_line_constraint PASSED             
tests/test_ledger.py::test_posted_entries_are_immutable PASSED          
tests/test_ledger.py::test_reversal_is_linked_and_nets_to_zero PASSED   
tests/test_ledger.py::test_posting_is_idempotent PASSED                 
tests/test_ledger.py::test_fx_entry_must_balance_in_each_currency PASSED
tests/test_ledger.py::test_gl_currency_must_match_line_currency PASSED  
tests/test_ledger.py::test_money_precision_and_conversion PASSED        
tests/test_payments.py::test_full_lifecycle_distinguishes_receipt_acceptance_execution PASSED
tests/test_payments.py::test_duplicate_event_does_not_double_debit PASSED
tests/test_payments.py::test_invalid_webhook_signature_rejected PASSED  
tests/test_payments.py::test_partial_batch_keeps_individual_results PASSED
tests/test_payments.py::test_unknown_result_after_record_is_searched_not_resubmitted PASSED
tests/test_payments.py::test_unknown_result_before_record_resubmits_with_same_key PASSED
tests/test_payments.py::test_interrupted_submission_is_recovered PASSED 
tests/test_payments.py::test_expired_job_lease_is_reclaimed PASSED      
tests/test_payments.py::test_enqueue_is_idempotent PASSED               
tests/test_payments.py::test_cancellation_depends_on_state PASSED       
tests/test_payments.py::test_idempotency_key PASSED                     
tests/test_payments.py::test_external_read_only_account_cannot_be_debited PASSED
tests/test_payments.py::test_csv_import_all_or_nothing PASSED           
tests/test_payments.py::test_return_of_funds_restores_balance PASSED    
tests/test_payments.py::test_scheduled_payment_executes_on_date PASSED  
tests/test_payments.py::test_beneficiary_material_change_after_approval_invalidates PASSED
tests/test_payments.py::test_payment_keeps_pinned_beneficiary_version PASSED
tests/test_payments.py::test_state_machine_rejects_illegal_transitions PASSED
tests/test_reconciliation_audit.py::test_reconciliation_detects_fee_and_ack_does_not_resolve PASSED
tests/test_reconciliation_audit.py::test_decision_items_have_source_owner_due_state PASSED
tests/test_reconciliation_audit.py::test_overview_kpis_are_computed_and_explained PASSED
tests/test_reconciliation_audit.py::test_audit_chain_is_append_only_and_tamper_evident PASSED
tests/test_reconciliation_audit.py::test_export_contains_report_and_verifiable_audit_trail PASSED
tests/test_reconciliation_audit.py::test_structured_errors_pagination_and_versioning PASSED
tests/test_reconciliation_audit.py::test_openapi_exposes_required_endpoints PASSED
tests/test_security.py::test_organization_isolation PASSED              
tests/test_security.py::test_entity_scoped_visibility PASSED            
tests/test_security.py::test_least_privilege_roles PASSED               
tests/test_security.py::test_admin_cannot_grant_itself_and_needs_step_up PASSED
tests/test_security.py::test_authentication_flow PASSED                 
tests/test_security.py::test_cookie_session_requires_csrf_header PASSED 
tests/test_security.py::test_documents_temporary_links PASSED           
tests/test_security.py::test_document_upload_validation PASSED          
tests/test_security.py::test_objects_are_encrypted_at_rest PASSED       
tests/test_security.py::test_logs_and_audit_details_are_redacted PASSED 
tests/test_storage_s3.py::test_s3_storage_roundtrip_and_encryption PASSED
============================= 83 passed in 38.02s ==============================
```

## Sortie Playwright (pile Docker Compose)

```
Running 8 tests using 1 worker

  ✓  1 [chromium] › e2e/horizon.spec.ts:20:5 › connexion MFA et tableau de bord calculé (état maquette) (2.0s)
  ✓  2 [chromium] › e2e/horizon.spec.ts:53:5 › capture d'écran du tableau de bord (1672×941, ×2) (2.2s)
  ✓  3 [chromium] › e2e/horizon.spec.ts:65:5 › navigation dans les 9 sections sans erreur (2.0s)
  ✓  4 [chromium] › e2e/horizon.spec.ts:77:5 › l'administrateur technique ne peut pas approuver (2.2s)
  ✓  5 [chromium] › e2e/horizon.spec.ts:95:5 › la préparatrice ne peut pas approuver son propre lot (1.5s)
  ✓  6 [chromium] › e2e/horizon.spec.ts:104:5 › double approbation : Sophie Bernard puis Marc Lefèvre, avec réauthentification (4.2s)
  ✓  7 [chromium] › e2e/horizon.spec.ts:143:5 › après exécution : liquidités mises à jour et audit consultable (3.1s)
  ✓  8 [chromium] › e2e/horizon.spec.ts:160:5 › délégation d'approbation plafonnée, avec réauthentification (1.7s)

  8 passed (19.5s)
```

## Limites des tests

* Le stockage S3 est testé contre l'émulateur `moto`, pas contre un service S3 réel : l'image MinIO n'était pas téléchargeable depuis cet environnement ; la pile Compose utilise donc le stockage chiffré sur volume.
* Les tests navigateur modifient l'état : réinitialiser la base (`scripts/reset_demo_db.sh --mockup-state`) avant chaque exécution.
* Pas de tests de charge, de tests d'intrusion ni de tests multi-navigateurs (Chromium uniquement).
