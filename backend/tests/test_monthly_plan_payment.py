from datetime import date
from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.schemas import MonthlyPlanPaymentUpdate

def payload(**changes):
    values={"obligation_account_id":"debt-1","checking_account_id":"checking-1","due_date":date(2026,8,24),"scheduled_date":date(2026,8,20),"amount":Decimal("45.00"),"status":"scheduled"}
    values.update(changes);return values

def test_scheduled_payment_does_not_require_paid_date():
    row=MonthlyPlanPaymentUpdate(**payload())
    assert row.status=="scheduled" and row.paid_date is None

def test_paid_status_requires_actual_paid_date():
    with pytest.raises(ValidationError,match="Paid date is required"):
        MonthlyPlanPaymentUpdate(**payload(status="paid"))

def test_paid_status_accepts_actual_paid_date():
    row=MonthlyPlanPaymentUpdate(**payload(status="paid",paid_date=date(2026,8,20)))
    assert row.paid_date==date(2026,8,20)

def test_unknown_payment_status_is_rejected():
    with pytest.raises(ValidationError,match="Choose NP"):
        MonthlyPlanPaymentUpdate(**payload(status="completed_maybe"))

def test_existing_standalone_bill_can_be_updated_without_obligation_account():
    row=MonthlyPlanPaymentUpdate(**payload(payment_id="payment-1",obligation_account_id=None))
    assert row.payment_id=="payment-1" and row.obligation_account_id is None
