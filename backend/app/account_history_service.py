from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import FinancialAccount, LiabilityStatement, ScheduledPayment, StatementUpload


def money(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def account_history(db: Session, household_id: str, account_id: str, months: int = 12):
    account = db.scalar(select(FinancialAccount).where(FinancialAccount.id == account_id, FinancialAccount.household_id == household_id))
    if not account:
        return None
    months = min(max(months, 1), 24)
    today = date.today()
    first_month = date(today.year, today.month, 1)
    cutoff = first_month - timedelta(days=31 * (months - 1))
    cutoff = date(cutoff.year, cutoff.month, 1)
    statements = list(db.scalars(select(LiabilityStatement).where(
        LiabilityStatement.household_id == household_id,
        LiabilityStatement.account_id == account_id,
        LiabilityStatement.statement_date >= cutoff,
    ).order_by(LiabilityStatement.statement_date.desc())))
    payments = list(db.scalars(select(ScheduledPayment).where(
        ScheduledPayment.household_id == household_id,
        ScheduledPayment.obligation_account_id == account_id,
        or_(ScheduledPayment.due_date >= cutoff, ScheduledPayment.scheduled_date >= cutoff),
    ).order_by(ScheduledPayment.scheduled_date.desc())))
    uploads = list(db.scalars(select(StatementUpload).where(
        StatementUpload.household_id == household_id,
        StatementUpload.account_id == account_id,
        StatementUpload.created_at >= cutoff,
    ).order_by(StatementUpload.created_at.desc())))
    return {
        "account": {"id": account.id, "name": account.name, "kind": account.kind, "mask": account.mask, "institution_name": account.institution_name},
        "period_start": cutoff.isoformat(), "period_end": today.isoformat(),
        "statements": [{
            "id": row.id, "statement_date": row.statement_date.isoformat(), "due_date": row.due_date.isoformat(),
            "opening_balance": money(row.opening_balance), "new_balance": money(row.new_balance),
            "payments_and_credits": money(row.new_payments), "minimum_payment": money(row.minimum_payment),
            "interest_rate": money(row.interest_rate), "interest_paid": money(row.interest_paid),
        } for row in statements],
        "payments": [{
            "id": row.id, "amount": money(row.amount), "minimum_amount": money(row.minimum_amount),
            "due_date": row.due_date.isoformat(), "scheduled_date": row.scheduled_date.isoformat(),
            "paid_date": row.paid_date.isoformat() if row.paid_date else None, "status": row.status,
            "confirmation_number": row.confirmation_number,
        } for row in payments],
        "uploads": [{
            "id": row.id, "filename": row.filename, "file_format": row.file_format, "file_size": row.file_size,
            "status": row.status, "uploaded_at": row.created_at.isoformat(),
            "statement_start_date": row.statement_start_date.isoformat() if row.statement_start_date else None,
            "statement_end_date": row.statement_end_date.isoformat() if row.statement_end_date else None,
            "transactions_added": row.transactions_added, "duplicates_skipped": row.duplicates_skipped,
            "error_message": row.error_message,
        } for row in uploads],
    }
