from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, or_, select

from app.models import Transaction


@dataclass(frozen=True)
class TransactionQuery:
    q: str = ""
    account_id: str = ""
    category: str = ""
    category_id: str = ""
    segment_id: str = ""
    amount: Decimal | None = None
    selected_date: date | None = None
    date_from: date | None = None
    date_to: date | None = None
    sort_by: str = "date"
    sort_dir: str = "desc"


class TransactionQueryError(ValueError):
    pass


def transaction_statement(household_id: str, query: TransactionQuery):
    if query.date_from and query.date_to and query.date_from > query.date_to:
        raise TransactionQueryError("From date must be on or before To date.")
    if query.sort_by not in {"transaction", "date", "category", "amount"}:
        raise TransactionQueryError("Unsupported transaction sort field.")
    if query.sort_dir not in {"asc", "desc"}:
        raise TransactionQueryError("Sort direction must be asc or desc.")

    stmt = select(Transaction).where(Transaction.household_id == household_id)
    if query.q:
        stmt = stmt.where(
            or_(
                Transaction.original_description.ilike(f"%{query.q}%"),
                Transaction.merchant.ilike(f"%{query.q}%"),
            )
        )
    if query.account_id:
        stmt = stmt.where(Transaction.account_id == query.account_id)
    if query.category:
        stmt = stmt.where(Transaction.category == query.category)
    if query.category_id:
        stmt = stmt.where(Transaction.category_id == query.category_id)
    if query.segment_id:
        stmt = stmt.where(Transaction.entity_id == query.segment_id)
    if query.amount is not None:
        stmt = stmt.where(Transaction.amount == abs(query.amount))
    if query.selected_date:
        stmt = stmt.where(Transaction.posted_date == query.selected_date)
    else:
        if query.date_from:
            stmt = stmt.where(Transaction.posted_date >= query.date_from)
        if query.date_to:
            stmt = stmt.where(Transaction.posted_date <= query.date_to)

    signed_amount = case(
        (Transaction.direction == "credit", Transaction.amount),
        else_=-Transaction.amount,
    )
    sort_columns = {
        "transaction": func.lower(Transaction.merchant),
        "date": Transaction.posted_date,
        "category": func.lower(Transaction.category),
        "amount": signed_amount,
    }
    sort_column = sort_columns[query.sort_by]
    ordering = sort_column.asc() if query.sort_dir == "asc" else sort_column.desc()
    return stmt.order_by(ordering, Transaction.id.asc())
