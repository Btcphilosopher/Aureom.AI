"""Registre en partie double : équilibre, immuabilité, contrepassations, idempotence, change."""
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from horizon.core.errors import Conflict, DomainError
from horizon.core.money import convert_minor, fmt, to_minor
from horizon.modules.accounts.models import BankAccount
from horizon.modules.ledger import service as ledger
from horizon.modules.ledger.models import JournalEntry, JournalLine
from horizon.modules.organizations.models import Organization


def _fr(db):
    acc = db.scalar(select(BankAccount).where(BankAccount.name == "Lumière France — Compte principal"))
    return acc, db.get(Organization, acc.organization_id)


def test_seed_balances_are_derived_from_balanced_entries(db):
    expected = {"Lumière France — Compte principal": 12_400_000_00, "Lumière Deutschland — Geschäftskonto": 7_800_000_00,
                "Lumière Italia — Conto principale": 4_600_000_00}
    for name, minor in expected.items():
        acc = db.scalar(select(BankAccount).where(BankAccount.name == name))
        assert ledger.booked_balance(db, acc.id) == minor
    org_id = acc.organization_id
    for row in db.execute(select(JournalLine.currency, func.sum(JournalLine.debit_minor), func.sum(JournalLine.credit_minor))
                          .join(JournalEntry).where(JournalEntry.organization_id == org_id).group_by(JournalLine.currency)):
        assert row[1] == row[2], f"balance déséquilibrée en {row[0]}"


def test_every_entry_is_balanced_per_currency(db):
    bad = db.execute(text("""SELECT entry_id, currency FROM journal_lines GROUP BY entry_id, currency
                             HAVING sum(debit_minor) <> sum(credit_minor)""")).all()
    assert bad == []


def test_service_rejects_unbalanced_entry(db):
    acc, org = _fr(db)
    gl = ledger.bank_gl(db, acc.id)
    cp = ledger.purpose_gl(db, org.id, acc.entity_id, "COUNTERPARTY_OUT", "EUR")
    with pytest.raises(DomainError) as e:
        ledger.post_entry(db, org_id=org.id, entity_id=acc.entity_id, journal="COR", description="x",
                          lines=[ledger.Line(gl.id, "EUR", debit=100), ledger.Line(cp.id, "EUR", credit=99)],
                          idempotency_key="t:unbalanced")
    assert e.value.code == "ENTRY_UNBALANCED"


def test_database_trigger_rejects_unbalanced_lines_even_bypassing_service(db):
    acc, org = _fr(db)
    gl = ledger.bank_gl(db, acc.id)
    e = JournalEntry(organization_id=org.id, entity_id=acc.entity_id, entry_number=999999, journal="COR",
                     booking_date=acc.created_at.date(), value_date=acc.created_at.date(), description="direct",
                     idempotency_key="t:direct")
    db.add(e)
    db.flush()
    db.add(JournalLine(entry_id=e.id, line_no=1, gl_account_id=gl.id, currency="EUR", debit_minor=500, credit_minor=0,
                       value_date=e.value_date))
    db.add(JournalLine(entry_id=e.id, line_no=2, gl_account_id=gl.id, currency="EUR", debit_minor=0, credit_minor=400,
                       value_date=e.value_date))
    with pytest.raises(DBAPIError, match="déséquilibrée"):
        db.commit()


def test_one_sided_line_constraint(db):
    acc, org = _fr(db)
    gl = ledger.bank_gl(db, acc.id)
    with pytest.raises(DomainError):
        ledger.post_entry(db, org_id=org.id, entity_id=acc.entity_id, journal="COR", description="x",
                          lines=[ledger.Line(gl.id, "EUR", debit=100, credit=100), ledger.Line(gl.id, "EUR", credit=0)],
                          idempotency_key="t:onesided")


def test_posted_entries_are_immutable(db):
    entry = db.scalars(select(JournalEntry).limit(1)).first()
    with pytest.raises(DBAPIError, match="immuable"):
        db.execute(text("UPDATE journal_entries SET description = 'altéré' WHERE id = :i"), {"i": entry.id})
    db.rollback()
    with pytest.raises(DBAPIError, match="immuable"):
        db.execute(text("DELETE FROM journal_lines WHERE entry_id = :i"), {"i": entry.id})
    db.rollback()


def test_reversal_is_linked_and_nets_to_zero(db):
    acc, org = _fr(db)
    gl = ledger.bank_gl(db, acc.id)
    fees = ledger.purpose_gl(db, org.id, acc.entity_id, "BANK_FEES", "EUR")
    before = ledger.booked_balance(db, acc.id)
    entry, created = ledger.post_entry(db, org_id=org.id, entity_id=acc.entity_id, journal="FRA", description="Frais",
                                       lines=[ledger.Line(fees.id, "EUR", debit=12_345), ledger.Line(gl.id, "EUR", credit=12_345)],
                                       idempotency_key="t:fee")
    assert created
    assert ledger.booked_balance(db, acc.id) == before - 12_345
    rev = ledger.reverse_entry(db, entry.id, "Saisie erronée", None)
    assert rev.reverses_entry_id == entry.id and rev.journal == "COR"
    assert ledger.booked_balance(db, acc.id) == before
    with pytest.raises(Conflict) as e:
        ledger.reverse_entry(db, entry.id, "encore", None)
    assert e.value.code == "ALREADY_REVERSED"
    with pytest.raises(Conflict):
        ledger.reverse_entry(db, rev.id, "contrepasser la contrepassation", None)
    db.commit()


def test_posting_is_idempotent(db):
    acc, org = _fr(db)
    gl = ledger.bank_gl(db, acc.id)
    cp = ledger.purpose_gl(db, org.id, acc.entity_id, "COUNTERPARTY_IN", "EUR")
    lines = [ledger.Line(gl.id, "EUR", debit=1000), ledger.Line(cp.id, "EUR", credit=1000)]
    e1, c1 = ledger.post_entry(db, org_id=org.id, entity_id=acc.entity_id, journal="ENC", description="a", lines=lines,
                               idempotency_key="t:idem")
    e2, c2 = ledger.post_entry(db, org_id=org.id, entity_id=acc.entity_id, journal="ENC", description="a", lines=lines,
                               idempotency_key="t:idem")
    assert c1 and not c2 and e1.id == e2.id


def test_fx_entry_must_balance_in_each_currency(db):
    acc, org = _fr(db)
    usd = db.scalar(select(BankAccount).where(BankAccount.name == "Lumière France — Compte USD"))
    eur_gl, usd_gl = ledger.bank_gl(db, acc.id), ledger.bank_gl(db, usd.id)
    pos_eur = ledger.purpose_gl(db, org.id, acc.entity_id, "FX_POSITION", "EUR")
    pos_usd = ledger.purpose_gl(db, org.id, acc.entity_id, "FX_POSITION", "USD")
    # Mêmes nombres, devises différentes : déséquilibré devise par devise → refusé
    with pytest.raises(DomainError) as e:
        ledger.post_entry(db, org_id=org.id, entity_id=acc.entity_id, journal="CHG", description="naïf",
                          lines=[ledger.Line(usd_gl.id, "USD", debit=100_000), ledger.Line(eur_gl.id, "EUR", credit=100_000)],
                          idempotency_key="t:fx-naive")
    assert e.value.code == "ENTRY_UNBALANCED"
    entry, _ = ledger.post_entry(db, org_id=org.id, entity_id=acc.entity_id, journal="CHG", description="conversion",
                                 lines=[ledger.Line(pos_eur.id, "EUR", debit=100_000), ledger.Line(eur_gl.id, "EUR", credit=100_000),
                                        ledger.Line(usd_gl.id, "USD", debit=108_400), ledger.Line(pos_usd.id, "USD", credit=108_400)],
                                 idempotency_key="t:fx-ok")
    db.commit()
    assert ledger.booked_balance(db, usd.id) == 108_400


def test_gl_currency_must_match_line_currency(db):
    acc, org = _fr(db)
    gl = ledger.bank_gl(db, acc.id)
    cp = ledger.purpose_gl(db, org.id, acc.entity_id, "COUNTERPARTY_IN", "USD")
    with pytest.raises(DomainError) as e:
        ledger.post_entry(db, org_id=org.id, entity_id=acc.entity_id, journal="ENC", description="x",
                          lines=[ledger.Line(gl.id, "USD", debit=10), ledger.Line(cp.id, "USD", credit=10)],
                          idempotency_key="t:ccy")
    assert e.value.code == "CURRENCY_MISMATCH"


def test_money_precision_and_conversion():
    assert to_minor("480000.00", "EUR") == 48_000_000
    assert to_minor("1000", "JPY") == 1000
    with pytest.raises(DomainError):
        to_minor("10.001", "EUR")
    with pytest.raises(DomainError):
        to_minor("1.5", "JPY")
    with pytest.raises(DomainError):
        to_minor("abc", "EUR")
    assert fmt(12_345, "EUR") == "123.45"
    # arrondi bancaire (demi au pair)
    assert convert_minor(1, "EUR", "EUR", Decimal("0.5")) == 0
    assert convert_minor(3, "EUR", "EUR", Decimal("0.5")) == 2
