from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.accounting_service import (
    AccountingError,
    balance_sheet,
    create_category,
    ensure_household_accounting,
    profit_and_loss,
    public_categories,
    trial_balance,
    update_transaction_categories,
    update_transaction_segments,
)
from app.db import Base
from app.models import (
    AccountingEntity,
    FinancialAccount,
    Household,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    Transaction,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def household_account(db: Session, balance: Decimal = Decimal("70")):
    household = Household(name="Test household")
    db.add(household)
    db.flush()
    account = FinancialAccount(
        household_id=household.id,
        name="Checking",
        kind="checking",
        mask="1234",
        balance=balance,
        balance_as_of_date=date(2026, 8, 17),
        available_balance=balance,
        investment_balance=Decimal("0"),
        original_balance=None,
        reserve=Decimal("0"),
        connection_mode="manual",
    )
    db.add(account)
    db.flush()
    return household, account


def test_settled_transactions_create_balanced_journals_and_reports(db):
    household, account = household_account(db)
    db.add_all(
        [
            Transaction(
                household_id=household.id,
                account_id=account.id,
                original_description="Client payment",
                merchant="Client",
                amount=Decimal("100"),
                direction="credit",
                posted_date=date(2026, 8, 10),
                category="Income",
            ),
            Transaction(
                household_id=household.id,
                account_id=account.id,
                original_description="Grocery store",
                merchant="Grocery Store",
                amount=Decimal("30"),
                direction="debit",
                posted_date=date(2026, 8, 11),
                category="Groceries",
            ),
        ]
    )
    ensure_household_accounting(db, household.id)
    db.commit()

    entries = list(
        db.scalars(
            select(JournalEntry).where(JournalEntry.source_type == "transaction")
        )
    )
    assert len(entries) == 2
    for entry in entries:
        debit, credit = db.execute(
            select(func.sum(JournalLine.debit), func.sum(JournalLine.credit)).where(
                JournalLine.journal_entry_id == entry.id
            )
        ).one()
        assert debit == credit

    pnl = profit_and_loss(
        db, household.id, date(2026, 1, 1), date(2026, 8, 17), None
    )
    assert pnl["total_income"] == "100.00"
    assert pnl["total_expenses"] == "30.00"
    assert pnl["net_income"] == "70.00"

    tb = trial_balance(db, household.id, date(2026, 8, 17), None)
    assert tb["balanced"] is True
    assert tb["total_debit"] == tb["total_credit"]

    sheet = balance_sheet(db, household.id, date(2026, 8, 17), None)
    assert sheet["balanced"] is True
    assert sheet["total_assets"] == "70.00"
    assert sheet["total_equity"] == "70.00"


def test_zero_amount_transaction_is_not_posted(db):
    household, account = household_account(db, Decimal("0"))
    transaction = Transaction(household_id=household.id, account_id=account.id, original_description="Zero", merchant="Zero", amount=Decimal("0"), direction="credit", posted_date=date(2026, 8, 17), category="Income")
    db.add(transaction)
    ensure_household_accounting(db, household.id)
    db.commit()
    assert db.scalar(select(JournalEntry).where(JournalEntry.transaction_id == transaction.id)) is None


def test_pending_transaction_is_not_posted(db):
    household, account = household_account(db, Decimal("0"))
    transaction = Transaction(
        household_id=household.id,
        account_id=account.id,
        original_description="Pending",
        merchant="Pending",
        amount=Decimal("20"),
        direction="debit",
        posted_date=date(2026, 8, 17),
        pending=True,
        category="Shopping",
    )
    db.add(transaction)
    ensure_household_accounting(db, household.id)
    db.commit()
    assert db.scalar(
        select(JournalEntry).where(JournalEntry.transaction_id == transaction.id)
    ) is None


def test_reclassification_replaces_counter_line(db):
    household, account = household_account(db, Decimal("-30"))
    transaction = Transaction(
        household_id=household.id,
        account_id=account.id,
        original_description="Cafe",
        merchant="Cafe",
        amount=Decimal("30"),
        direction="debit",
        posted_date=date(2026, 8, 17),
        category="Dining",
    )
    db.add(transaction)
    ensure_household_accounting(db, household.id)
    categories = public_categories(db, household.id)
    groceries = next(row for row in categories if row["name"] == "Groceries")
    update_transaction_categories(db, household.id, [transaction.id], groceries["id"])

    db.refresh(transaction)
    assert transaction.category == "Groceries"
    entry = db.scalar(
        select(JournalEntry).where(JournalEntry.transaction_id == transaction.id)
    )
    line_accounts = set(
        db.scalars(
            select(JournalLine.ledger_account_id).where(
                JournalLine.journal_entry_id == entry.id
            )
        )
    )
    assert groceries["id"] in line_accounts


def test_category_tree_is_limited_to_three_levels(db):
    household, _ = household_account(db, Decimal("0"))
    ensure_household_accounting(db, household.id)
    categories = public_categories(db, household.id)
    expenses = next(row for row in categories if row["code"] == "5000")
    level_two = create_category(db, household.id, "Operations", expenses["id"])
    level_three = create_category(db, household.id, "Hosting", level_two["id"])
    with pytest.raises(AccountingError, match="three levels"):
        create_category(db, household.id, "Cloud", level_three["id"])

def test_segments_classify_transactions_without_splitting_the_books(db):
    household, account = household_account(db, Decimal("50"))
    segment = AccountingEntity(household_id=household.id, name="Retail", entity_type="segment")
    transaction = Transaction(
        household_id=household.id, account_id=account.id, original_description="Retail sale",
        merchant="Customer", amount=Decimal("50"), direction="credit",
        posted_date=date(2026, 8, 17), category="Income",
    )
    db.add_all([segment, transaction])
    ensure_household_accounting(db, household.id)
    db.commit()

    update_transaction_segments(db, household.id, [transaction.id], segment.id)

    segmented = profit_and_loss(db, household.id, date(2026, 1, 1), date(2026, 8, 17), segment.id)
    combined = profit_and_loss(db, household.id, date(2026, 1, 1), date(2026, 8, 17), None)
    sheet = balance_sheet(db, household.id, date(2026, 8, 17), None)
    assert segmented["net_income"] == "50.00"
    assert combined["net_income"] == "50.00"
    assert sheet["balanced"] is True
    assert account.entity_id is None
    db.refresh(transaction)
    assert transaction.entity_id == segment.id

def test_utility_charge_posts_to_specific_expense_account(db):
    household, account = household_account(db, Decimal("915"))
    transaction = Transaction(
        household_id=household.id, account_id=account.id,
        original_description="CITY WATER AUTOPAY", merchant="City Water",
        amount=Decimal("85"), direction="debit", posted_date=date(2026, 8, 17),
        category="Water & Sewer", classification_source="rules",
        classification_confidence=Decimal("0.95"),
    )
    db.add(transaction)
    ensure_household_accounting(db, household.id)
    db.commit()
    category = db.get(LedgerAccount, transaction.category_id)
    pnl = profit_and_loss(db, household.id, date(2026, 8, 1), date(2026, 8, 31), None)
    assert category is not None and category.name == "Water & Sewer"
    assert pnl["total_expenses"] == "85.00"
    assert pnl["net_income"] == "-85.00"
