from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import FinancialAccount,Household,Transaction
from app.recurring_charge_service import decide_recurring_charge,recurring_charge_overview


class Decision:
    account_id=""
    merchant_pattern="netflix"
    decision="subscription"


def test_detects_card_subscription_and_persists_user_decision():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
    with Session(engine) as db:
        household=Household(name="Test");db.add(household);db.flush()
        card=FinancialAccount(household_id=household.id,name="Rewards Card",kind="credit_card",mask="4242",balance=Decimal("0"),available_balance=Decimal("5000"),reserve=Decimal("0"),is_active=True,connection_mode="manual");db.add(card);db.flush()
        for posted in (date(2026,5,8),date(2026,6,8),date(2026,7,8)):
            db.add(Transaction(household_id=household.id,account_id=card.id,original_description="NETFLIX.COM RECURRING",merchant="Netflix",amount=Decimal("22.99"),direction="debit",posted_date=posted,category="Entertainment",pending=False,is_transfer=False))
        db.commit();overview=recurring_charge_overview(db,household.id,date(2026,7,10))
        assert overview["review_count"]==1
        assert overview["candidates"][0]["account_kind"]=="credit_card"
        assert overview["candidates"][0]["annual_cost"]=="275.88"
        Decision.account_id=card.id;decide_recurring_charge(db,household.id,Decision())
        overview=recurring_charge_overview(db,household.id,date(2026,7,10))
        assert overview["review_count"]==0
        assert overview["confirmed"][0]["series_type"]=="subscription"


def test_repeated_variable_everyday_spending_is_not_suggested():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
    with Session(engine) as db:
        household=Household(name="Test");db.add(household);db.flush()
        checking=FinancialAccount(household_id=household.id,name="Checking",kind="checking",mask="1111",balance=Decimal("1000"),available_balance=Decimal("1000"),reserve=Decimal("0"),is_active=True,connection_mode="manual");db.add(checking);db.flush()
        for posted,amount in ((date(2026,5,1),"40"),(date(2026,6,1),"120"),(date(2026,7,1),"63")):
            db.add(Transaction(household_id=household.id,account_id=checking.id,original_description="LOCAL GROCERY",merchant="Local Grocery",amount=Decimal(amount),direction="debit",posted_date=posted,category="Groceries",pending=False,is_transfer=False))
        db.commit();overview=recurring_charge_overview(db,household.id,date(2026,7,10))
        assert overview["candidates"]==[]
