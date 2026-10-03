from datetime import date
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base
from app.income_detection_service import income_candidates
from app.models import FinancialAccount, Household, Transaction

def test_recurring_checking_credits_become_confirmable_income_candidate():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
    with Session(engine) as db:
        household=Household(name="Test");db.add(household);db.flush()
        checking=FinancialAccount(household_id=household.id,name="Checking",kind="checking",mask="1234",balance=Decimal("1000"),available_balance=Decimal("1000"),reserve=Decimal("0"),is_active=True,connection_mode="manual")
        db.add(checking);db.flush()
        for index,posted in enumerate((date(2026,6,5),date(2026,6,19),date(2026,7,3))):
            db.add(Transaction(household_id=household.id,account_id=checking.id,original_description=f"ACME PAYROLL DIRECT DEP {index}",merchant="Acme Payroll",amount=Decimal("2500"),direction="credit",posted_date=posted,category="Income",classification_source="rules",classification_confidence=Decimal("0.99")))
        db.add(Transaction(household_id=household.id,account_id=checking.id,original_description="REFUND",merchant="Refund",amount=Decimal("50"),direction="credit",posted_date=date(2026,7,4),category="Shopping",classification_source="manual",classification_confidence=Decimal("1")))
        db.commit();candidates=income_candidates(db,household.id,date(2026,7,10))
    assert len(candidates)==1
    assert candidates[0]["amount"]=="2500.00"
    assert candidates[0]["frequency_days"]==14
    assert candidates[0]["next_date"]=="2026-07-17"
    assert candidates[0]["reliability"]=="guaranteed"

def test_debits_are_never_income_candidates_even_if_categorized_as_income():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
    with Session(engine) as db:
        household=Household(name="Test");db.add(household);db.flush()
        checking=FinancialAccount(household_id=household.id,name="Checking",kind="checking",mask="1234",balance=Decimal("0"),available_balance=Decimal("0"),reserve=Decimal("0"),is_active=True,connection_mode="manual")
        db.add(checking);db.flush();db.add(Transaction(household_id=household.id,account_id=checking.id,original_description="PAYROLL REVERSAL",merchant="Payroll",amount=Decimal("1000"),direction="debit",posted_date=date(2026,7,3),category="Income",classification_source="manual",classification_confidence=Decimal("1")));db.commit()
        assert income_candidates(db,household.id)==[]
