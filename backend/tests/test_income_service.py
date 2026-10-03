from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.income_service import (
    create_income,
    delete_income,
    next_income_date,
    occurrence_dates,
    update_income,
)
from app.models import FinancialAccount, Household, IncomeEvent
from app.schemas import IncomeCreate


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
def household(db):
    home = Household(name="Test Household", data_source="manual")
    db.add(home)
    db.flush()
    account = FinancialAccount(
        household_id=home.id, name="Checking", kind="checking",
        institution_name="Test Bank", mask="1234", data_source="manual",
        balance=Decimal("100"), available_balance=Decimal("100"),
    )
    db.add(account)
    db.commit()
    return home, account


def payload(account_id, **overrides):
    base = dict(
        name="Employer paycheck", account_id=account_id, amount=Decimal("2500.00"),
        expected_date=date(2026, 8, 14), reliability="high_confidence", frequency="biweekly",
    )
    base.update(overrides)
    return IncomeCreate(**base)


def test_monthly_dates_clamp_to_short_months():
    assert next_income_date(date(2026, 1, 31), "monthly", 31) == date(2026, 2, 28)
    # Anchor day is restored once the month is long enough again.
    assert next_income_date(date(2026, 2, 28), "monthly", 31) == date(2026, 3, 31)


def test_semi_monthly_alternates_between_two_days():
    assert next_income_date(date(2026, 8, 1), "semi_monthly", 1) == date(2026, 8, 16)
    assert next_income_date(date(2026, 8, 16), "semi_monthly", 1) == date(2026, 9, 1)
    assert next_income_date(date(2026, 8, 15), "semi_monthly", 15) == date(2026, 8, 30)
    assert next_income_date(date(2026, 8, 30), "semi_monthly", 15) == date(2026, 9, 15)


def test_occurrences_cover_a_year_and_one_time_is_single():
    weekly = occurrence_dates(date(2026, 8, 14), "weekly")
    assert len(weekly) == 53
    assert all((later - earlier).days == 7 for earlier, later in zip(weekly, weekly[1:]))
    assert occurrence_dates(date(2026, 8, 14), "one_time") == [date(2026, 8, 14)]


def test_create_recurring_income_builds_series(db, household):
    home, account = household
    events = create_income(db, home.id, payload(account.id))
    assert len(events) == 27  # biweekly across 365 days
    assert len({event.series_id for event in events}) == 1
    assert events[0].series_id is not None
    assert all(event.frequency == "biweekly" for event in events)


def test_create_one_time_income_has_no_series(db, household):
    home, account = household
    events = create_income(db, home.id, payload(account.id, frequency="one_time"))
    assert len(events) == 1 and events[0].series_id is None


def test_create_income_rejects_credit_card_account(db, household):
    home, _ = household
    card = FinancialAccount(
        household_id=home.id, name="Card", kind="credit_card",
        institution_name="Bank", mask="9999", data_source="manual",
        balance=Decimal("0"), available_balance=Decimal("0"),
    )
    db.add(card)
    db.commit()
    with pytest.raises(ValueError, match="deposit"):
        create_income(db, home.id, payload(card.id))


def test_update_income_regenerates_future_and_keeps_past(db, household):
    home, account = household
    events = create_income(db, home.id, payload(account.id))
    past = [event for event in events if event.expected_date < date(2026, 9, 10)]
    target = next(event for event in events if event.expected_date >= date(2026, 9, 10))
    update_income(
        db, home.id, target.id,
        payload(account.id, amount=Decimal("3000.00"), expected_date=date(2026, 9, 15), frequency="monthly"),
        today=date(2026, 9, 10),
    )
    remaining = db.scalars(select(IncomeEvent).order_by(IncomeEvent.expected_date)).all()
    kept_past = [event for event in remaining if event.expected_date < date(2026, 9, 10)]
    assert {event.id for event in kept_past} == {event.id for event in past}
    future = [event for event in remaining if event.expected_date >= date(2026, 9, 10)]
    assert all(event.amount == Decimal("3000.00") and event.frequency == "monthly" for event in future)
    assert future[0].expected_date == date(2026, 9, 15)
    assert len({event.series_id for event in future}) == 1
    assert future[0].series_id != target.series_id


def test_update_income_household_scoped(db, household):
    home, account = household
    other = Household(name="Other", data_source="manual")
    db.add(other)
    db.commit()
    events = create_income(db, home.id, payload(account.id))
    with pytest.raises(LookupError):
        update_income(db, other.id, events[0].id, payload(account.id), today=date(2026, 8, 14))


def test_delete_scope_one_removes_single_occurrence(db, household):
    home, account = household
    events = create_income(db, home.id, payload(account.id))
    deleted = delete_income(db, home.id, events[3].id, "one")
    assert deleted == 1
    assert db.scalar(select(IncomeEvent).where(IncomeEvent.id == events[3].id)) is None
    assert len(db.scalars(select(IncomeEvent)).all()) == len(events) - 1


def test_delete_scope_all_removes_entire_series(db, household):
    home, account = household
    events = create_income(db, home.id, payload(account.id))
    keeper = create_income(db, home.id, payload(account.id, name="Side gig", frequency="one_time"))[0]
    deleted = delete_income(db, home.id, events[0].id, "all")
    assert deleted == len(events)
    left = db.scalars(select(IncomeEvent)).all()
    assert [event.id for event in left] == [keeper.id]
