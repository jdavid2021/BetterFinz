from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.balance_service import available_balance_view
from app.db import Base
from app.models import FinancialAccount, FinancialConnection, Household, Transaction


def setup(reported: str = "0"):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    household = Household(name="Household")
    db.add(household)
    db.flush()
    connection = FinancialConnection(household_id=household.id, provider="simplefin", encrypted_access_url="encrypted")
    db.add(connection)
    db.flush()
    account = FinancialAccount(household_id=household.id, name="Spend", kind="checking", mask="9051", balance=Decimal(reported), available_balance=Decimal(reported), investment_balance=Decimal("0"), reserve=Decimal("0"), connection_id=connection.id, connection_mode="automatic", data_source="simplefin")
    db.add(account)
    db.flush()
    return db, household, account


def transaction(household_id: str, account_id: str, amount: str, direction: str, category: str, days_ago: int):
    return Transaction(household_id=household_id, account_id=account_id, original_description=category, merchant=category, amount=Decimal(amount), direction=direction, posted_date=date.today() - timedelta(days=days_ago), pending=False, category=category, classification_source="rules", classification_confidence=Decimal("1"), data_source="simplefin")


def test_zero_provider_balance_uses_recent_posted_activity_estimate():
    db, household, account = setup()
    db.add_all([
        transaction(household.id, account.id, "1000", "credit", "Income", 7),
        transaction(household.id, account.id, "250", "debit", "Bill", 3),
    ])
    db.commit()

    view = available_balance_view(db, household.id, account)

    assert view.amount == Decimal("750")
    assert view.reported_amount == Decimal("0")
    assert view.source == "calculated_activity"
    assert view.anchor_date == date.today() - timedelta(days=7)


def test_nonzero_provider_balance_remains_authoritative():
    db, household, account = setup("400")
    db.add(transaction(household.id, account.id, "1000", "credit", "Income", 7))
    db.commit()

    view = available_balance_view(db, household.id, account)

    assert view.amount == Decimal("400")
    assert view.source == "provider"
