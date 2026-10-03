from datetime import date,timedelta
from decimal import Decimal
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from app.bill_service import match_open_scheduled_payments,payment_match_candidates,transaction_payment_contexts
from app.db import Base
from app.models import FinancialAccount,Household,IncomeEvent,Notification,PaymentMatch,ScheduledPayment,Transaction,User
from app.notification_service import generate_notifications

def setup(db):
 household=Household(name="Home");user=User(email="person@example.com",password_hash="x",display_name="Person");db.add_all([household,user]);db.flush();account=FinancialAccount(household_id=household.id,name="Checking",kind="checking",mask="1234",balance=Decimal("50"),available_balance=Decimal("50"),reserve=Decimal("100"),is_active=True,connection_mode="manual");db.add(account);db.flush();return household,user,account

def test_notifications_are_household_scoped_and_idempotent():
 engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
 with Session(engine) as db:
  household,user,account=setup(db);today=date.today();db.add_all([ScheduledPayment(household_id=household.id,account_id=account.id,payee="Water",amount=Decimal("40"),scheduled_date=today,due_date=today+timedelta(days=2),earliest_withdrawal_date=today,latest_withdrawal_date=today,status="planned"),IncomeEvent(household_id=household.id,account_id=account.id,name="Paycheck",amount=Decimal("1000"),expected_date=today-timedelta(days=8),reliability="high_confidence",status="missing")]);db.commit();generate_notifications(db,household.id,user.id,today);generate_notifications(db,household.id,user.id,today);rows=list(db.scalars(select(Notification)))
  assert {row.kind for row in rows}=={"low_balance","upcoming_payment","missing_income"};assert all(row.household_id==household.id and row.user_id==user.id for row in rows)

def test_payment_candidates_include_other_accounts_but_rank_planned_account_first():
 engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
 with Session(engine) as db:
  household,_,account=setup(db);other=FinancialAccount(household_id=household.id,name="Other",kind="checking",mask="9999",balance=Decimal("500"),available_balance=Decimal("500"),reserve=Decimal("0"),is_active=True,connection_mode="manual");db.add(other);db.flush();due=date(2026,8,20);payment=ScheduledPayment(household_id=household.id,account_id=account.id,payee="Water",amount=Decimal("80"),scheduled_date=due,due_date=due,earliest_withdrawal_date=due,latest_withdrawal_date=due,status="planned");eligible=Transaction(household_id=household.id,account_id=account.id,original_description="CITY WATER",merchant="City Water",amount=Decimal("80"),direction="debit",posted_date=due,pending=False,is_transfer=False);pending=Transaction(household_id=household.id,account_id=account.id,original_description="PENDING",merchant="Pending",amount=Decimal("80"),direction="debit",posted_date=due,pending=True,is_transfer=False);wrong=Transaction(household_id=household.id,account_id=other.id,original_description="OTHER",merchant="Other",amount=Decimal("80"),direction="debit",posted_date=due,pending=False,is_transfer=False);db.add_all([payment,eligible,pending,wrong]);db.commit();rows=payment_match_candidates(db,household.id,payment.id)
 assert [row["id"] for row in rows]==[eligible.id,wrong.id];assert rows[0]["score"]==100;assert rows[0]["account_matches"] is True;assert rows[1]["account_matches"] is False;assert rows[1]["account_name"]=="Other"

def test_payment_candidates_rank_plausible_matches_and_hide_unrelated_debits():
 engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
 with Session(engine) as db:
  household,_,account=setup(db);due=date(2026,8,2)
  payment=ScheduledPayment(household_id=household.id,account_id=account.id,payee="Aron Lopez",amount=Decimal("140"),scheduled_date=due,due_date=due,earliest_withdrawal_date=due,latest_withdrawal_date=due,status="planned")
  description_match=Transaction(household_id=household.id,account_id=account.id,original_description="BILL PAYMENT ARON LOPEZ",merchant="Aron Lopez",amount=Decimal("145"),direction="debit",posted_date=due+timedelta(days=2),pending=False,is_transfer=False)
  exact_late_match=Transaction(household_id=household.id,account_id=account.id,original_description="CHECK 5039",merchant="Check 5039",amount=Decimal("140"),direction="debit",posted_date=due+timedelta(days=15),pending=False,is_transfer=False)
  unrelated=Transaction(household_id=household.id,account_id=account.id,original_description="GROCERY STORE",merchant="Grocery Store",amount=Decimal("62"),direction="debit",posted_date=due,pending=False,is_transfer=False);previous_check=Transaction(household_id=household.id,account_id=account.id,original_description="CHECK 5020",merchant="Check 5020",amount=Decimal("140"),direction="debit",posted_date=due-timedelta(days=20),pending=False,is_transfer=False)
  db.add_all([payment,description_match,exact_late_match,unrelated,previous_check]);db.commit()
  rows=payment_match_candidates(db,household.id,payment.id)
  expected_ids=[description_match.id,exact_late_match.id]
 assert [row["id"] for row in rows]==expected_ids
 assert rows[0]["confidence"]=="high"
 assert rows[1]["confidence"]=="medium"
 assert "Exact amount" in rows[1]["reason"]

def test_payment_candidates_are_capped_to_eight_results():
 engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
 with Session(engine) as db:
  household,_,account=setup(db);due=date(2026,8,20);payment=ScheduledPayment(household_id=household.id,account_id=account.id,payee="Water",amount=Decimal("80"),scheduled_date=due,due_date=due,earliest_withdrawal_date=due,latest_withdrawal_date=due,status="planned");db.add(payment);db.add_all([Transaction(household_id=household.id,account_id=account.id,original_description=f"CITY WATER {index}",merchant="City Water",amount=Decimal("80"),direction="debit",posted_date=due-timedelta(days=index),pending=False,is_transfer=False) for index in range(10)]);db.commit();rows=payment_match_candidates(db,household.id,payment.id)
 assert len(rows)==8



def test_sync_matching_is_conservative_and_same_account_only():
 engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
 with Session(engine) as db:
  household,_,account=setup(db);other=FinancialAccount(household_id=household.id,name="Other",kind="checking",mask="9999",balance=Decimal("500"),available_balance=Decimal("500"),reserve=Decimal("0"),is_active=True,connection_mode="manual");db.add(other);db.flush();due=date(2026,9,12)
  same=ScheduledPayment(household_id=household.id,account_id=account.id,payee="PayPal",amount=Decimal("100"),scheduled_date=due-timedelta(days=8),due_date=due,earliest_withdrawal_date=due,latest_withdrawal_date=due,status="scheduled")
  cross=ScheduledPayment(household_id=household.id,account_id=account.id,payee="Electric",amount=Decimal("200"),scheduled_date=due-timedelta(days=8),due_date=due,earliest_withdrawal_date=due,latest_withdrawal_date=due,status="scheduled")
  same_transaction=Transaction(household_id=household.id,account_id=account.id,original_description="PAYPAL PAYMENT",merchant="PayPal",amount=Decimal("100"),direction="debit",posted_date=due-timedelta(days=8),pending=False,is_transfer=False)
  cross_transaction=Transaction(household_id=household.id,account_id=other.id,original_description="ELECTRIC PAYMENT",merchant="Electric",amount=Decimal("200"),direction="debit",posted_date=due-timedelta(days=8),pending=False,is_transfer=False)
  db.add_all([same,cross,same_transaction,cross_transaction]);db.commit()
  assert match_open_scheduled_payments(db,household.id)==1
  assert same.status=="paid" and same.paid_date==same_transaction.posted_date
  assert cross.status=="scheduled"
  assert db.scalar(select(PaymentMatch).where(PaymentMatch.payment_id==same.id)).transaction_id==same_transaction.id

def test_sync_matching_leaves_ambiguous_exact_debits_for_review():
 engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
 with Session(engine) as db:
  household,_,account=setup(db);due=date(2026,9,12);payment=ScheduledPayment(household_id=household.id,account_id=account.id,payee="PayPal",amount=Decimal("100"),scheduled_date=due,due_date=due,earliest_withdrawal_date=due,latest_withdrawal_date=due,status="scheduled");db.add(payment);db.add_all([Transaction(household_id=household.id,account_id=account.id,original_description="PAYPAL PAYMENT",merchant="PayPal",amount=Decimal("100"),direction="debit",posted_date=due-timedelta(days=offset),pending=False,is_transfer=False) for offset in (1,2)]);db.commit()
  assert match_open_scheduled_payments(db,household.id)==0
  assert payment.status=="scheduled"


def test_transaction_match_context_suggests_and_then_shows_confirmed_obligation():
 engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
 with Session(engine) as db:
  household,_,account=setup(db);due=date(2026,8,20)
  payment=ScheduledPayment(household_id=household.id,account_id=account.id,payee="City Water",amount=Decimal("80"),scheduled_date=due,due_date=due,earliest_withdrawal_date=due,latest_withdrawal_date=due,status="planned")
  debit=Transaction(household_id=household.id,account_id=account.id,original_description="CITY WATER AUTOPAY",merchant="City Water",amount=Decimal("80"),direction="debit",posted_date=due,pending=False,is_transfer=False)
  credit=Transaction(household_id=household.id,account_id=account.id,original_description="CITY WATER REFUND",merchant="City Water",amount=Decimal("80"),direction="credit",posted_date=due,pending=False,is_transfer=False)
  unrelated=Transaction(household_id=household.id,account_id=account.id,original_description="ZEL TO TABITHA",merchant="Tabitha",amount=Decimal("82"),direction="debit",posted_date=due,pending=False,is_transfer=False)
  db.add_all([payment,debit,credit,unrelated]);db.commit()
  context=transaction_payment_contexts(db,household.id,[debit.id,credit.id,unrelated.id,"outside-household-id"])
  assert context[debit.id]["suggestions"][0]["payment_id"]==payment.id
  assert context[debit.id]["suggestions"][0]["confidence"]=="high"
  assert context[credit.id]["suggestions"]==[] and context[unrelated.id]["suggestions"]==[] and context[unrelated.id]["options"][0]["payment_id"]==payment.id and "outside-household-id" not in context
  match=PaymentMatch(household_id=household.id,payment_id=payment.id,transaction_id=debit.id,match_type="exact");payment.status="paid";db.add(match);db.commit()
  matched=transaction_payment_contexts(db,household.id,[debit.id])[debit.id]
  assert matched["matched"]["payee"]=="City Water" and matched["suggestions"]==[]
