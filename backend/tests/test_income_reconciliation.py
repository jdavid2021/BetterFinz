from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.income_reconciliation_service import resolve_income


def income(expected=date(2026, 8, 6)):
    return SimpleNamespace(
        id="income-1", household_id="household-1", account_id="account-1",
        name="Direct Deposit Sch Districtpayroll (Cash)", expected_date=expected,
        amount=Decimal("713.62"), reliability="guaranteed",
    )


def transaction(posted=date(2026, 8, 6), amount="702.14"):
    return SimpleNamespace(
        household_id="household-1", account_id="account-1", direction="credit",
        pending=False, posted_date=posted, amount=Decimal(amount),
        original_description="SCH DISTRICTPAYROLL", merchant="Sch Districtpayroll",
    )


def test_future_income_is_an_estimate_and_can_fund_forecast():
    resolved = resolve_income(income(date(2026, 8, 12)), [], date(2026, 8, 11), date(2026, 8, 11))
    assert (resolved.status, resolved.include_in_forecast) == ("estimated", True)


def test_due_income_without_matching_transaction_is_not_confirmed_or_funded():
    resolved = resolve_income(income(), [], date(2026, 8, 11), date(2026, 8, 11))
    assert (resolved.status, resolved.include_in_forecast) == ("not_confirmed", False)


def test_matching_deposit_uses_actual_amount_and_date():
    resolved = resolve_income(income(), [transaction(date(2026, 8, 7), "702.14")], date(2026, 8, 5), date(2026, 8, 11))
    assert (resolved.status, resolved.amount, resolved.expected_date) == ("received", Decimal("702.14"), date(2026, 8, 7))
    assert resolved.include_in_forecast is True


def test_received_income_already_in_current_balance_is_not_added_twice():
    resolved = resolve_income(income(), [transaction()], date(2026, 8, 11), date(2026, 8, 11))
    assert (resolved.status, resolved.include_in_forecast) == ("received", False)


def test_unmatched_income_becomes_missing_after_grace_period():
    resolved = resolve_income(income(), [], date(2026, 8, 20), date(2026, 8, 20))
    assert resolved.status == "missing"
