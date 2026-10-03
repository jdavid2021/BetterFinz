from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BillProfile,
    FinancialAccount,
    Household,
    IncomeEvent,
    ScheduledPayment,
)


def onboarding_status(db: Session, household_id: str) -> dict:
    household = db.get(Household, household_id)
    if household is None:
        raise LookupError("Household not found.")
    account_complete = bool(
        db.scalar(
            select(func.count(FinancialAccount.id)).where(
                FinancialAccount.household_id == household_id,
                FinancialAccount.is_active,
                FinancialAccount.data_source != "seed",
            )
        )
    )
    income_complete = bool(
        db.scalar(
            select(func.count(IncomeEvent.id)).where(
                IncomeEvent.household_id == household_id,
                IncomeEvent.data_source != "seed",
            )
        )
    )
    bill_count = db.scalar(
        select(func.count(BillProfile.id)).where(
            BillProfile.household_id == household_id,
            BillProfile.is_active,
            BillProfile.data_source != "seed",
        )
    )
    payment_count = db.scalar(
        select(func.count(ScheduledPayment.id)).where(
            ScheduledPayment.household_id == household_id,
            ScheduledPayment.data_source != "seed",
        )
    )
    plan_complete = bool(bill_count or payment_count)
    steps = [
        {"id": "account", "complete": account_complete},
        {"id": "income", "complete": income_complete},
        {"id": "plan", "complete": plan_complete},
    ]
    complete = all(step["complete"] for step in steps)
    next_step = next((step["id"] for step in steps if not step["complete"]), None)
    return {
        "account_complete": account_complete,
        "income_complete": income_complete,
        "plan_complete": plan_complete,
        "complete": complete,
        "dismissed": household.onboarding_dismissed_at is not None,
        "dismissed_at": household.onboarding_dismissed_at.isoformat()
        if household.onboarding_dismissed_at
        else None,
        "next_step": next_step,
        "steps": steps,
    }


def dismiss_onboarding(db: Session, household_id: str) -> dict:
    household = db.get(Household, household_id)
    if household is None:
        raise LookupError("Household not found.")
    if household.onboarding_dismissed_at is None:
        household.onboarding_dismissed_at = datetime.now(timezone.utc)
        household.dml_flag = "U"
        db.commit()
    return onboarding_status(db, household_id)
