"""Garde-fous d'intégrité au niveau base de données.

* Écritures comptabilisées immuables (journal_entries, journal_lines).
* Équilibre débit = crédit par devise vérifié en fin de transaction
  (trigger de contrainte différé).
* Journal d'audit en ajout seul.
* Versions de bénéficiaire : coordonnées immuables (seuls les champs de revue
  peuvent évoluer).

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION horizon_forbid_change() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'HORIZON: % sur % interdit (enregistrement immuable)', TG_OP, TG_TABLE_NAME
            USING ERRCODE = 'check_violation';
        END; $$ LANGUAGE plpgsql;

        CREATE TRIGGER journal_entries_immutable BEFORE UPDATE OR DELETE ON journal_entries
          FOR EACH ROW EXECUTE FUNCTION horizon_forbid_change();
        CREATE TRIGGER journal_lines_immutable BEFORE UPDATE OR DELETE ON journal_lines
          FOR EACH ROW EXECUTE FUNCTION horizon_forbid_change();
        CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events
          FOR EACH ROW EXECUTE FUNCTION horizon_forbid_change();

        CREATE FUNCTION horizon_check_entry_balanced() RETURNS trigger AS $$
        DECLARE
          unbalanced record;
          line_count integer;
        BEGIN
          SELECT count(*) INTO line_count FROM journal_lines WHERE entry_id = NEW.entry_id;
          IF line_count < 2 THEN
            RAISE EXCEPTION 'HORIZON: écriture % avec moins de deux lignes', NEW.entry_id
              USING ERRCODE = 'check_violation';
          END IF;
          SELECT currency, sum(debit_minor) AS d, sum(credit_minor) AS c INTO unbalanced
            FROM journal_lines WHERE entry_id = NEW.entry_id
            GROUP BY currency HAVING sum(debit_minor) <> sum(credit_minor) LIMIT 1;
          IF FOUND THEN
            RAISE EXCEPTION 'HORIZON: écriture % déséquilibrée en % (débit %, crédit %)',
              NEW.entry_id, unbalanced.currency, unbalanced.d, unbalanced.c
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NULL;
        END; $$ LANGUAGE plpgsql;

        CREATE CONSTRAINT TRIGGER journal_lines_balanced AFTER INSERT ON journal_lines
          DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
          EXECUTE FUNCTION horizon_check_entry_balanced();

        CREATE FUNCTION horizon_beneficiary_version_guard() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'HORIZON: suppression de version de bénéficiaire interdite'
              USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.name IS DISTINCT FROM OLD.name OR NEW.iban IS DISTINCT FROM OLD.iban
             OR NEW.bic IS DISTINCT FROM OLD.bic OR NEW.country_code IS DISTINCT FROM OLD.country_code
             OR NEW.version_no IS DISTINCT FROM OLD.version_no
             OR NEW.beneficiary_id IS DISTINCT FROM OLD.beneficiary_id THEN
            RAISE EXCEPTION 'HORIZON: coordonnées de bénéficiaire immuables, créer une nouvelle version'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;

        CREATE TRIGGER beneficiary_versions_guard BEFORE UPDATE OR DELETE ON beneficiary_versions
          FOR EACH ROW EXECUTE FUNCTION horizon_beneficiary_version_guard();

        CREATE SEQUENCE IF NOT EXISTS journal_entry_number_seq;
        CREATE SEQUENCE IF NOT EXISTS payment_batch_reference_seq;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS beneficiary_versions_guard ON beneficiary_versions;
        DROP FUNCTION IF EXISTS horizon_beneficiary_version_guard();
        DROP TRIGGER IF EXISTS journal_lines_balanced ON journal_lines;
        DROP FUNCTION IF EXISTS horizon_check_entry_balanced();
        DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events;
        DROP TRIGGER IF EXISTS journal_lines_immutable ON journal_lines;
        DROP TRIGGER IF EXISTS journal_entries_immutable ON journal_entries;
        DROP FUNCTION IF EXISTS horizon_forbid_change();
        DROP SEQUENCE IF EXISTS journal_entry_number_seq;
        DROP SEQUENCE IF EXISTS payment_batch_reference_seq;
        """
    )
