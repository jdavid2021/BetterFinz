from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine,func,select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.db import Base
from app.models import FinancialAccount,Household,Transaction,TransactionMerge
from app.reconciliation_service import ReconciliationError,add_missing_transaction,complete_reconciliation,merge_duplicate,preview_reconciliation,reconciliation_history,review_duplicates

def setup(kind="checking"):
 engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);db=Session(engine)
 household=Household(name="Home");db.add(household);db.flush();account=FinancialAccount(household_id=household.id,name="Primary",kind=kind,mask="1234",balance=Decimal("0"),available_balance=Decimal("0"),investment_balance=Decimal("0"),reserve=Decimal("0"),connection_mode="manual",data_source="manual");db.add(account);db.commit();return db,household,account

def body(account,opening,closing):
 return SimpleNamespace(account_id=account.id,period_start=date(2026,8,1),period_end=date(2026,8,31),opening_balance=Decimal(opening),closing_balance=Decimal(closing),notes="Checked against statement")

def transaction(household,account,description,amount,direction,source="statement",pending=False,provider_id=None,fingerprint=None,category="Uncategorized"):
 return Transaction(household_id=household.id,account_id=account.id,provider_id=provider_id,original_description=description,merchant=description.title(),amount=Decimal(amount),direction=direction,posted_date=date(2026,8,6),pending=pending,category=category,classification_source="manual",classification_confidence=Decimal("1"),fingerprint=fingerprint,data_source=source)

def test_asset_reconciliation_excludes_pending_transactions():
 db,household,account=setup();db.add_all([transaction(household,account,"Payroll","500","credit"),transaction(household,account,"Rent","300","debit"),transaction(household,account,"Pending dinner","20","debit",pending=True)]);db.commit()
 result=preview_reconciliation(db,household.id,body(account,"1000","1200"))
 assert result["calculated_closing_balance"]=="1200.00"
 assert result["balanced"] is True
 assert result["transaction_count"]==2 and result["pending_count"]==1

def test_liability_reconciliation_uses_charges_minus_payments():
 db,household,account=setup("credit_card");db.add_all([transaction(household,account,"Store","200","debit"),transaction(household,account,"Payment","150","credit")]);db.commit()
 result=preview_reconciliation(db,household.id,body(account,"1000","1050"))
 assert result["formula"]=="Opening + debits - credits"
 assert result["calculated_closing_balance"]=="1050.00" and result["balanced"] is True

def test_completion_requires_zero_difference_and_saves_history():
 db,household,account=setup()
 with pytest.raises(ReconciliationError,match="difference must be"):
  complete_reconciliation(db,household.id,body(account,"100","99"))
 saved=complete_reconciliation(db,household.id,body(account,"100","100"))
 assert saved["difference"]=="0.00"
 assert reconciliation_history(db,household.id,account.id)[0]["id"]==saved["id"]
 with pytest.raises(ReconciliationError,match="already been reconciled"):
  complete_reconciliation(db,household.id,body(account,"100","100"))

def test_preview_flags_the_reported_mercury_duplicate_pair():
 db,household,account=setup();db.add_all([transaction(household,account,"MERCURY CARD FBT PAYMENT ACH WEB","321","debit","statement",provider_id="statement-id",fingerprint="statement-fp"),transaction(household,account,"Payment to Mercury Cards","321","debit","simplefin",provider_id="simplefin-id")]);db.commit()
 result=preview_reconciliation(db,household.id,body(account,"1000","358"))
 assert len(result["duplicate_candidates"])==1
 assert len(result["duplicate_candidates"][0]["transactions"])==2

def test_merge_is_audited_and_preserves_simplefin_identity_and_category():
 db,household,account=setup();statement=transaction(household,account,"MERCURY CARD FBT PAYMENT ACH WEB","321","debit","statement",provider_id="statement-id",fingerprint="statement-fp",category="Credit Card Payment");imported=transaction(household,account,"Payment to Mercury Cards","321","debit","simplefin",provider_id="simplefin-id");db.add_all([statement,imported]);db.commit();imported_id=imported.id
 result=merge_duplicate(db,household.id,statement.id,imported.id);db.refresh(statement)
 assert result["removed_transaction_id"]==imported_id
 assert statement.provider_id=="simplefin-id" and statement.category=="Credit Card Payment"
 assert db.scalar(select(func.count(Transaction.id)))==1
 audit=db.scalar(select(TransactionMerge));assert audit.removed_transaction_id==imported_id and "Payment to Mercury Cards" in audit.removed_snapshot

def test_merge_rejects_transactions_from_different_amounts():
 db,household,account=setup();left=transaction(household,account,"A","10","debit");right=transaction(household,account,"A","11","debit","simplefin",provider_id="sf");db.add_all([left,right]);db.commit()
 with pytest.raises(ReconciliationError,match="same account, date, amount"):
  merge_duplicate(db,household.id,left.id,right.id)


def test_missing_transaction_is_explicit_and_auditable():
 db,household,account=setup();request=SimpleNamespace(account_id=account.id,posted_date=date(2026,8,12),description="Monthly bank fee",amount=Decimal("12.00"),direction="debit")
 result=add_missing_transaction(db,household.id,request);row=db.get(Transaction,result["id"])
 assert row.data_source=="reconciliation"
 assert row.notes=="Added explicitly during account reconciliation."
 assert row.amount==Decimal("12.00") and row.direction=="debit"

def test_completed_periods_cannot_overlap():
 db,household,account=setup();complete_reconciliation(db,household.id,body(account,"100","100"));overlap=body(account,"100","100");overlap.period_start=date(2026,8,15);overlap.period_end=date(2026,9,15)
 with pytest.raises(ReconciliationError,match="overlaps"):
  complete_reconciliation(db,household.id,overlap)


def test_duplicate_review_is_household_scoped_and_excludes_transfers():
 db,household,account=setup();left=transaction(household,account,"GERBER LIFE INSURANCE","5.83","debit","simplefin",provider_id="sf-a");right=transaction(household,account,"GERBER LIFE INSURANCE","5.83","debit","simplefin",provider_id="sf-b");sweep=transaction(household,account,"PURCHASE INTO CORE ACCOUNT FDIC INSURED DEPOSIT","5.83","debit","simplefin",provider_id="sf-c");sweep.is_transfer=True;db.add_all([left,right,sweep]);db.commit()
 result=review_duplicates(db,household.id,account.id)
 assert result["count"]==1 and len(result["groups"][0]["transactions"])==2
 merge_duplicate(db,household.id,left.id,right.id)
 audit=db.scalar(select(TransactionMerge));assert "sf-b" in audit.removed_snapshot
