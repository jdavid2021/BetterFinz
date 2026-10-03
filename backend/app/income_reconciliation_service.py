from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.categorization_service import normalize_description


@dataclass
class ResolvedIncome:
    id: str
    name: str
    household_id: str
    account_id: str
    expected_date: date
    amount: Decimal
    reliability: str
    status: str
    include_in_forecast: bool
    actual_date: date | None = None


def _same_source(income_name: str, transaction) -> bool:
    expected = normalize_description(income_name)
    candidates = {
        normalize_description(transaction.original_description),
        normalize_description(transaction.merchant),
    }
    return any(
        candidate
        and len(candidate) >= 4
        and (candidate in expected or expected in candidate)
        for candidate in candidates
    )


def resolve_income(income, transactions, balance_as_of: date | None, as_of: date) -> ResolvedIncome:
    if income.expected_date > as_of:
        return ResolvedIncome(
            income.id, income.name, income.household_id, income.account_id,
            income.expected_date, Decimal(income.amount), income.reliability,
            "estimated", True,
        )

    window_start = income.expected_date - timedelta(days=3)
    matches = [
        transaction
        for transaction in transactions
        if transaction.household_id == income.household_id
        and transaction.account_id == income.account_id
        and transaction.direction == "credit"
        and not transaction.pending
        and window_start <= transaction.posted_date <= as_of
        and _same_source(income.name, transaction)
    ]
    if matches:
        match = min(matches, key=lambda transaction: abs((transaction.posted_date - income.expected_date).days))
        already_in_balance = balance_as_of is None or balance_as_of >= match.posted_date
        return ResolvedIncome(
            income.id, income.name, income.household_id, income.account_id,
            match.posted_date, Decimal(match.amount), income.reliability,
            "received", not already_in_balance, actual_date=match.posted_date,
        )

    status = "missing" if as_of > income.expected_date + timedelta(days=7) else "not_confirmed"
    return ResolvedIncome(
        income.id, income.name, income.household_id, income.account_id,
        income.expected_date, Decimal(income.amount), income.reliability,
        status, False,
    )
