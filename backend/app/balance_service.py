from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import FinancialAccount, Transaction


CASH_KINDS = {"checking", "savings", "money_market"}


@dataclass(frozen=True)
class BalanceView:
    amount: Decimal
    reported_amount: Decimal
    as_of_date: date | None
    reported_as_of_date: date | None
    source: str
    anchor_date: date | None = None


def available_balance_view(db: Session, household_id: str, account: FinancialAccount) -> BalanceView:
    reported = Decimal(account.available_balance)
    default_source = "provider" if account.connection_id else account.data_source or "manual"
    default = BalanceView(reported, reported, account.balance_as_of_date, account.balance_as_of_date, default_source)
    if account.kind not in CASH_KINDS or not account.connection_id or reported != 0:
        return default

    cutoff = date.today() - timedelta(days=45)
    anchor = db.scalar(
        select(func.max(Transaction.posted_date)).where(
            Transaction.household_id == household_id,
            Transaction.account_id == account.id,
            Transaction.direction == "credit",
            Transaction.pending.is_(False),
            Transaction.category == "Income",
            Transaction.posted_date >= cutoff,
        )
    )
    if not anchor:
        return default

    signed_amount = case(
        (Transaction.direction == "credit", Transaction.amount),
        else_=-Transaction.amount,
    )
    calculated = Decimal(
        db.scalar(
            select(func.coalesce(func.sum(signed_amount), 0)).where(
                Transaction.household_id == household_id,
                Transaction.account_id == account.id,
                Transaction.pending.is_(False),
                Transaction.posted_date >= anchor,
            )
        )
        or 0
    )
    if calculated <= 0:
        return default
    activity_date = db.scalar(
        select(func.max(Transaction.posted_date)).where(
            Transaction.household_id == household_id,
            Transaction.account_id == account.id,
            Transaction.pending.is_(False),
            Transaction.posted_date >= anchor,
        )
    )
    return BalanceView(
        calculated,
        reported,
        activity_date,
        account.balance_as_of_date,
        "calculated_activity",
        anchor,
    )
