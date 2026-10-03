"""Income series management: recurrence generation, edits, and deletion."""
import calendar
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FinancialAccount, IncomeEvent, uid

INCOME_FREQUENCIES = {"one_time", "weekly", "biweekly", "semi_monthly", "monthly"}
DEPOSIT_ACCOUNT_KINDS = {"checking", "savings", "money_market", "cash_management"}
HORIZON_DAYS = 365
MAX_OCCURRENCES = 60


def _clamp_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def next_income_date(current: date, frequency: str, anchor_day: int) -> date:
    if frequency == "weekly":
        return current + timedelta(days=7)
    if frequency == "biweekly":
        return current + timedelta(days=14)
    if frequency == "semi_monthly":
        # Two deposits a month, e.g. the 1st/16th or 15th/30th, anchored on the first date chosen.
        if current.day < 16:
            return _clamp_day(current.year, current.month, current.day + 15)
        year, month = _next_month(current.year, current.month)
        return _clamp_day(year, month, current.day - 15)
    if frequency == "monthly":
        year, month = _next_month(current.year, current.month)
        return _clamp_day(year, month, anchor_day)
    raise ValueError("Unsupported income frequency.")


def occurrence_dates(start: date, frequency: str) -> list[date]:
    if frequency == "one_time":
        return [start]
    dates, current, horizon = [start], start, start + timedelta(days=HORIZON_DAYS)
    while len(dates) < MAX_OCCURRENCES:
        current = next_income_date(current, frequency, start.day)
        if current > horizon:
            break
        dates.append(current)
    return dates


def _deposit_account(db: Session, household_id: str, account_id: str) -> FinancialAccount:
    account = db.scalar(select(FinancialAccount).where(
        FinancialAccount.id == account_id,
        FinancialAccount.household_id == household_id,
        FinancialAccount.is_active,
    ))
    if not account:
        raise LookupError("Destination account was not found.")
    if account.kind not in DEPOSIT_ACCOUNT_KINDS:
        raise ValueError("Choose a deposit or cash-management account for income.")
    return account


def _build_events(household_id: str, body, series_id: str | None) -> list[IncomeEvent]:
    return [
        IncomeEvent(
            household_id=household_id,
            account_id=body.account_id,
            name=body.name.strip(),
            expected_date=occurrence,
            amount=body.amount,
            reliability=body.reliability,
            status="expected",
            frequency=body.frequency,
            series_id=series_id,
            data_source="manual",
        )
        for occurrence in occurrence_dates(body.expected_date, body.frequency)
    ]


def create_income(db: Session, household_id: str, body) -> list[IncomeEvent]:
    _deposit_account(db, household_id, body.account_id)
    series_id = uid() if body.frequency != "one_time" else None
    events = _build_events(household_id, body, series_id)
    db.add_all(events)
    db.commit()
    for event in events:
        db.refresh(event)
    return events


def _household_event(db: Session, household_id: str, income_id: str) -> IncomeEvent:
    event = db.scalar(select(IncomeEvent).where(
        IncomeEvent.id == income_id, IncomeEvent.household_id == household_id,
    ))
    if not event:
        raise LookupError("Income was not found.")
    return event


def update_income(db: Session, household_id: str, income_id: str, body, today: date) -> list[IncomeEvent]:
    """Replace the edited occurrence and everything after it with a regenerated series.

    Past occurrences stay untouched so already-received deposits keep reconciling.
    """
    event = _household_event(db, household_id, income_id)
    _deposit_account(db, household_id, body.account_id)
    if event.series_id:
        cutoff = min(today, body.expected_date, event.expected_date)
        stale = db.scalars(select(IncomeEvent).where(
            IncomeEvent.household_id == household_id,
            IncomeEvent.series_id == event.series_id,
            IncomeEvent.expected_date >= cutoff,
        )).all()
        for item in stale:
            db.delete(item)
    else:
        db.delete(event)
    db.flush()
    series_id = uid() if body.frequency != "one_time" else None
    events = _build_events(household_id, body, series_id)
    db.add_all(events)
    db.commit()
    for item in events:
        db.refresh(item)
    return events


def delete_income(db: Session, household_id: str, income_id: str, scope: str) -> int:
    event = _household_event(db, household_id, income_id)
    if scope == "all" and event.series_id:
        items = db.scalars(select(IncomeEvent).where(
            IncomeEvent.household_id == household_id,
            IncomeEvent.series_id == event.series_id,
        )).all()
    else:
        items = [event]
    for item in items:
        db.delete(item)
    db.commit()
    return len(items)
