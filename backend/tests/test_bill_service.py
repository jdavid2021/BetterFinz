from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.biller_directory import match_biller, search_billers
from app.bill_service import bill_candidates, create_bill, match_open_bill_payments, update_bill
from app.db import Base
from app.models import FinancialAccount, Household, ScheduledPayment, Transaction
from app.schemas import BillCreate


def setup_household(db: Session):
    household = Household(name="Test")
    db.add(household)
    db.flush()
    checking = FinancialAccount(household_id=household.id,name="Checking",kind="checking",mask="1234",balance=Decimal("1000"),available_balance=Decimal("1000"),reserve=Decimal("0"),is_active=True,connection_mode="manual")
    db.add(checking)
    db.flush()
    return household, checking


def test_recurring_debits_become_confirmable_bill_candidates():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
    with Session(engine) as db:
        household,checking=setup_household(db)
        for posted,amount in ((date(2026,5,18),Decimal("181")),(date(2026,6,18),Decimal("195")),(date(2026,7,17),Decimal("189"))):
            db.add(Transaction(household_id=household.id,account_id=checking.id,original_description="DUKE ENERGY AUTOPAY",merchant="Duke Energy",amount=amount,direction="debit",posted_date=posted,category="Bill",pending=False,is_transfer=False))
        db.commit();candidates=bill_candidates(db,household.id,date(2026,8,5))
    assert len(candidates)==1
    assert candidates[0]["name"]=="Duke Energy"
    assert candidates[0]["frequency"]=="monthly"
    assert candidates[0]["confidence"]=="high"
    assert candidates[0]["next_date"]=="2026-08-17"


def test_missed_recurring_due_date_is_returned_as_overdue_not_skipped():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
    with Session(engine) as db:
        household,checking=setup_household(db)
        for posted in (date(2026,5,2),date(2026,6,2),date(2026,7,2)):
            db.add(Transaction(household_id=household.id,account_id=checking.id,original_description="BILL PAYMENT ARON LOPEZ",merchant="Aron Lopez",amount=Decimal("140"),direction="debit",posted_date=posted,category="Bill",pending=False,is_transfer=False))
        db.commit();candidate=bill_candidates(db,household.id,date(2026,8,5))[0]
    assert candidate["next_date"]=="2026-08-02"


def test_bank_description_aliases_with_identical_history_are_one_suggestion():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
    with Session(engine) as db:
        household,checking=setup_household(db)
        for posted,amount in ((date(2026,5,9),Decimal("300")),(date(2026,6,9),Decimal("305")),(date(2026,7,9),Decimal("310"))):
            for description in ("RECURRING CARD ESURANCE CAR","ESURANCE CAR INSURANCE"):
                db.add(Transaction(household_id=household.id,account_id=checking.id,original_description=description,merchant=description.title(),amount=amount,direction="debit",posted_date=posted,category="Bill",pending=False,is_transfer=False))
        db.commit();candidates=bill_candidates(db,household.id,date(2026,8,5))
    assert len(candidates)==1


def test_confirmed_bill_creates_a_year_of_monthly_payment_occurrences():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
    with Session(engine) as db:
        household,checking=setup_household(db)
        body=BillCreate(name="Water",merchant_pattern="CITY WATER AUTOPAY",category="Utilities",bill_type="recurring",amount_type="variable",typical_amount=Decimal("85"),frequency="monthly",due_date=date(2026,8,6),default_account_id=checking.id)
        bill=create_bill(db,household.id,body)
        payments=list(db.scalars(select(ScheduledPayment).where(ScheduledPayment.bill_id==bill.id).order_by(ScheduledPayment.due_date)))
    assert len(payments)==12
    assert payments[0].due_date==date(2026,8,6)
    assert payments[-1].due_date==date(2027,7,6)
    assert all(payment.status=="not_planned" for payment in payments)


def test_matching_imported_debit_marks_the_bill_occurrence_paid():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
    with Session(engine) as db:
        household,checking=setup_household(db)
        body=BillCreate(name="Internet",merchant_pattern="SPECTRUM INTERNET",category="Phone & Internet",bill_type="recurring",amount_type="fixed",typical_amount=Decimal("120"),frequency="monthly",due_date=date(2026,8,6),default_account_id=checking.id)
        bill=create_bill(db,household.id,body)
        db.add(Transaction(household_id=household.id,account_id=checking.id,original_description="SPECTRUM INTERNET PAYMENT",merchant="Spectrum",amount=Decimal("120"),direction="debit",posted_date=date(2026,8,5),category="Bill",pending=False,is_transfer=False));db.commit()
        assert match_open_bill_payments(db,household.id)==1
        payment=db.scalar(select(ScheduledPayment).where(ScheduledPayment.bill_id==bill.id,ScheduledPayment.due_date==date(2026,8,6)))
        assert payment.status=="paid"
        assert payment.paid_date==date(2026,8,5)


def test_biller_directory_matches_transaction_descriptions_and_searches_names():
    biller, confidence = match_biller("FRONTIER COMMU AUTOPAY")
    assert biller is not None
    assert biller.id == "frontier"
    assert confidence == "high"
    matches = search_billers("Pasco utilities")
    assert matches[0]["id"] == "pasco-utilities"
    assert matches[0]["domains"] == ("pascocountyfl.net",)
    esurance = search_billers("Esurance car insurance")[0]
    assert esurance["website_url"] == "https://www.esurance.com/customer-login"
    assert esurance["customer_service_phone"] == "1-800-378-7262"


def test_confirmed_directory_biller_uses_trusted_url_instead_of_typed_url():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        household, checking = setup_household(db)
        body = BillCreate(
            name="Frontier Internet",
            merchant_pattern="FRONTIER COMMU AUTOPAY",
            category="Phone & Internet",
            bill_type="recurring",
            amount_type="fixed",
            typical_amount=Decimal("80"),
            frequency="monthly",
            due_date=date(2026, 8, 20),
            default_account_id=checking.id,
            website_url="https://example.com/not-frontier",
            biller_id="frontier",
        )
        bill = create_bill(db, household.id, body)
    assert bill.website_url == "https://frontier.com/resources/pay-bill-online"
    assert bill.biller_directory_id == "frontier"


def test_edit_bill_preserves_paid_history_and_rebuilds_future_occurrences():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
    with Session(engine) as db:
        household,checking=setup_household(db)
        original=BillCreate(name="Internet",merchant_pattern="FRONTIER",category="Phone & Internet",bill_type="recurring",amount_type="fixed",typical_amount=Decimal("80"),frequency="monthly",due_date=date(2026,8,6),default_account_id=checking.id,biller_id="frontier")
        bill=create_bill(db,household.id,original)
        first=db.scalar(select(ScheduledPayment).where(ScheduledPayment.bill_id==bill.id).order_by(ScheduledPayment.due_date));first.status="paid";db.commit()
        revised=BillCreate(name="Frontier Fiber",merchant_pattern="FRONTIER",category="Phone & Internet",bill_type="recurring",amount_type="fixed",typical_amount=Decimal("92"),frequency="monthly",due_date=date(2026,8,12),default_account_id=checking.id,biller_id="frontier",payment_method="bank_bill_pay")
        update_bill(db,household.id,bill.id,revised)
        rows=list(db.scalars(select(ScheduledPayment).where(ScheduledPayment.bill_id==bill.id).order_by(ScheduledPayment.due_date)))
    assert first in rows and first.status=="paid" and first.amount==Decimal("80")
    assert any(row.due_date==date(2026,8,12) and row.amount==Decimal("92") for row in rows)
    assert all(row.method=="bank_bill_pay" for row in rows if row.status=="not_planned")
