from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import urllib.request
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.db import Base
from app.models import AuditEvent, FinancialAccount, FinancialConnection, Household, JournalLine, LedgerAccount, LiabilityStatement, ScheduledPayment, Transaction
from app.account_merge_service import merge_accounts
from app.accounting_service import ensure_household_accounting
from app.simplefin_service import SimpleFinBusy, classify_core_cash_sweeps, connection_sync_lock, core_sweep_direction, cross_source_descriptions_similar, fetch, infer_kind, is_fidelity_core_sweep, preview, public_account, reconcile_existing_duplicates, request, status, sync, sync_health
from app.reconciliation_service import merge_duplicate
from app.main import accounts as account_rows


def db_session():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def local_account(household_id):
    return FinancialAccount(household_id=household_id,name="Primary Checking",kind="checking",mask="1234",balance=Decimal("100"),available_balance=Decimal("90"),investment_balance=Decimal("0"),original_balance=None,reserve=Decimal("25"),institution_name="Example Bank",bank_login_url=None)


def setup():
    db=db_session();household=Household(name="Household");db.add(household);db.flush();local=local_account(household.id);connection=FinancialConnection(household_id=household.id,provider="simplefin",encrypted_access_url="encrypted");db.add_all([local,connection]);db.commit();return db,household,local,connection


def test_preview_suggests_exact_mask_and_kind_match():
    db,household,local,connection=setup()
    payload={"connections":[{"conn_id":"c1","name":"Example Bank"}],"accounts":[{"id":"remote-1","conn_id":"c1","name":"Checking","account-number":"1234","currency":"USD","balance":"101","transactions":[]}]}
    result=preview(db,household.id,connection,payload)
    assert result["accounts"][0]["suggested_existing_account_id"]==local.id
    assert result["accounts"][0]["institution_name"]=="Example Bank"


def test_sync_reconciles_existing_transaction_and_preserves_reserve():
    db,household,local,connection=setup();local.connection_id=connection.id;local.provider_account_id="remote-1"
    existing=Transaction(household_id=household.id,account_id=local.id,provider_id=None,original_description="Coffee Shop 123",merchant="Coffee Shop",amount=Decimal("12.34"),direction="debit",posted_date=datetime(2026,8,1,tzinfo=timezone.utc).date(),category="Dining",classification_source="rules",classification_confidence=Decimal("1"),fingerprint="existing-fingerprint",data_source="statement")
    db.add(existing);db.commit()
    payload={"accounts":[{"id":"remote-1","balance":"87.66","balance-date":1785542400,"transactions":[{"id":"tx-1","posted":1785542400,"amount":"-12.34","description":"Coffee Shop 123"}]}]}
    result=sync(db,household.id,connection,payload);db.refresh(existing);db.refresh(local)
    assert result=={"added":0,"duplicates":0,"matched_existing":1}
    assert existing.provider_id is not None
    assert db.scalar(select(func.count(Transaction.id)))==1
    assert local.balance==Decimal("87.66")
    assert local.available_balance==Decimal("87.66")
    assert local.reserve==Decimal("25.00")
    assert connection.status=="active"
    assert connection.next_sync_at is not None
    assert connection.consecutive_failures==0
    assert sync_health(connection)=="healthy"


def test_sync_does_not_treat_credit_card_balance_as_available_cash():
    db,household,local,connection=setup();local.kind="credit_card";local.available_balance=Decimal("2500");local.connection_id=connection.id;local.provider_account_id="remote-1";db.commit()
    payload={"accounts":[{"id":"remote-1","balance":"593.95","balance-date":1787702400,"transactions":[]}]}
    sync(db,household.id,connection,payload);db.refresh(local)
    assert local.balance==Decimal("593.95")
    assert local.available_balance==Decimal("2500.00")


def test_status_reports_stale_and_scheduled_sync_metadata():
    db,household,_,connection=setup()
    connection.status="active"
    connection.last_successful_sync_at=datetime.now(timezone.utc)-timedelta(days=2)
    connection.next_sync_at=datetime.now(timezone.utc)-timedelta(hours=1)
    db.commit()
    result=status(db,household.id)[0]
    assert result["sync_health"]=="stale"
    assert result["automatic_sync_enabled"] is True
    assert result["next_sync_at"] is not None


def test_connection_lock_rejects_concurrent_sync(monkeypatch):
    class LockedRedis:
        def set(self,*_args,**_kwargs):return False
    monkeypatch.setattr("app.simplefin_service.Redis.from_url",lambda *_args,**_kwargs:LockedRedis())
    with __import__("pytest").raises(SimpleFinBusy):
        with connection_sync_lock("connection-id"):
            raise AssertionError("lock should not be acquired")


def test_infer_kind_recognizes_product_names_without_generic_type_words():
    assert infer_kind("Quicksilver (1806)")=="credit_card"
    assert infer_kind("Secured loan (0992)")=="loan"


def test_requests_identify_finleash(monkeypatch):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,_size):return b"ok"
    class Opener:
        def open(self,req,timeout):
            assert req.get_header("User-agent")=="FinLeash/1.0";assert timeout==20;return Response()
    monkeypatch.setattr(urllib.request,"build_opener",lambda *_:Opener())
    assert request(urllib.request.Request("https://bridge.simplefin.org/test"))==b"ok"


def test_fetch_defaults_to_transaction_history_window(monkeypatch):
    seen={}
    def fake_request(req,stage="access"):
        seen["url"]=req.full_url;return b"{\"accounts\":[]}"
    monkeypatch.setattr("app.simplefin_service.request",fake_request)
    fetch("https://user:secret@bridge.simplefin.org/simplefin")
    assert "start-date=" in seen["url"]
    assert "user" not in seen["url"] and "secret" not in seen["url"]


def test_public_account_uses_strict_name_suffix_when_account_number_is_missing():
    account=public_account({"id":"remote-1","name":"Spend (9051)"})
    assert account["mask"]=="9051"
    assert account["mask_source"]=="name_suffix"
    assert public_account({"id":"remote-2","name":"Spend 9051"})["mask"]=="0000"


def test_preview_resolves_duplicate_remote_masks_with_unique_name_match():
    db,household,local,connection=setup();local.name="PNC Spend account";local.mask="9051";local.institution_name="PNC Bank";db.commit()
    payload={"connections":[{"conn_id":"c1","name":"PNC Bank"}],"accounts":[
        {"id":"spend","conn_id":"c1","name":"Spend (9051)","currency":"USD","balance":"100","transactions":[]},
        {"id":"generic","conn_id":"c1","name":"Account (9051)","currency":"USD","balance":"100","transactions":[]},
    ]}
    result=preview(db,household.id,connection,payload)
    assert result["accounts"][0]["suggested_existing_account_id"]==local.id
    assert result["accounts"][0]["suggestion_confidence"]=="possible"
    assert result["accounts"][1]["suggested_existing_account_id"] is None


def test_preview_does_not_guess_when_duplicate_remote_names_are_tied():
    db,household,local,connection=setup();local.name="PNC account";local.mask="9051";local.institution_name="PNC Bank";db.commit()
    payload={"connections":[{"conn_id":"c1","name":"PNC Bank"}],"accounts":[
        {"id":"one","conn_id":"c1","name":"Account (9051)","transactions":[]},
        {"id":"two","conn_id":"c1","name":"Checking (9051)","transactions":[]},
    ]}
    result=preview(db,household.id,connection,payload)
    assert all(account["suggested_existing_account_id"] is None for account in result["accounts"])


def test_cross_source_payment_descriptions_match_only_the_same_payee():
    assert cross_source_descriptions_similar("Payment to Mercury Cards","MERCURY CARD FBT PAYMENT ACH WEB")
    assert not cross_source_descriptions_similar("Payment to Mercury Cards","CHASE CARD PAYMENT ACH WEB")


def test_sync_reconciles_statement_transaction_that_already_has_provider_id():
    db,household,local,connection=setup();local.connection_id=connection.id;local.provider_account_id="remote-1"
    existing=Transaction(household_id=household.id,account_id=local.id,provider_id="statement-external",original_description="MERCURY CARD FBT PAYMENT ACH WEB",merchant="Mercury Card",amount=Decimal("321.00"),direction="debit",posted_date=datetime(2026,8,6,tzinfo=timezone.utc).date(),category="Credit Card Payment",classification_source="manual",classification_confidence=Decimal("1"),fingerprint="mercury-statement",data_source="statement")
    db.add(existing);db.commit()
    payload={"accounts":[{"id":"remote-1","balance":"100","balance-date":1785974400,"transactions":[{"id":"mercury-simplefin","posted":1785974400,"amount":"-321.00","description":"Payment to Mercury Cards"}]}]}
    result=sync(db,household.id,connection,payload);db.refresh(existing)
    assert result=={"added":0,"duplicates":0,"matched_existing":1}
    assert existing.provider_id!="statement-external"
    assert existing.category=="Credit Card Payment"
    assert db.scalar(select(func.count(Transaction.id)))==1


def test_existing_duplicate_cleanup_is_dry_run_then_preserves_statement_row():
    db,household,local,connection=setup();local.connection_id=connection.id;local.provider_account_id="remote-1"
    statement=Transaction(household_id=household.id,account_id=local.id,provider_id="statement-external",original_description="MERCURY CARD FBT PAYMENT ACH WEB",merchant="Mercury Card",amount=Decimal("321.00"),direction="debit",posted_date=datetime(2026,8,6,tzinfo=timezone.utc).date(),category="Credit Card Payment",classification_source="manual",classification_confidence=Decimal("1"),fingerprint="cleanup-statement",data_source="statement")
    imported=Transaction(household_id=household.id,account_id=local.id,provider_id="simplefin-external",original_description="Payment to Mercury Cards",merchant="Payment To Mercury Cards",amount=Decimal("321.00"),direction="debit",posted_date=datetime(2026,8,6,tzinfo=timezone.utc).date(),category="Uncategorized",classification_source="unclassified",classification_confidence=Decimal("0"),data_source="simplefin")
    db.add_all([statement,imported]);db.commit();imported_id=imported.id
    assert reconcile_existing_duplicates(db,household.id,connection)=={"matched":1,"conflicts":0}
    assert db.scalar(select(func.count(Transaction.id)))==2
    assert reconcile_existing_duplicates(db,household.id,connection,dry_run=False)=={"matched":1,"conflicts":0}
    db.refresh(statement)
    assert db.get(Transaction,imported_id) is None
    assert statement.provider_id=="simplefin-external"
    assert statement.category=="Credit Card Payment"

def test_account_merge_preserves_manual_history_and_moves_live_connection():
    db=db_session();household=Household(name="Household");db.add(household);db.flush()
    connection=FinancialConnection(household_id=household.id,provider="simplefin",encrypted_access_url="encrypted",status="active")
    db.add(connection);db.flush()
    survivor=FinancialAccount(household_id=household.id,name="Best Egg Personal Loan",kind="loan",mask="0992",balance=Decimal("17887.34"),balance_as_of_date=date(2026,7,21),available_balance=Decimal("0"),investment_balance=Decimal("0"),original_balance=Decimal("20000"),reserve=Decimal("0"),institution_name="Best Egg")
    source=FinancialAccount(household_id=household.id,name="Secured loan (0992)",kind="loan",mask="0992",balance=Decimal("17552.39"),balance_as_of_date=date(2026,9,5),available_balance=Decimal("17552.39"),investment_balance=Decimal("0"),original_balance=None,reserve=Decimal("0"),institution_name="Best Egg",connection_id=connection.id,provider_account_id="remote-best-egg",connection_mode="automatic",data_source="simplefin")
    db.add_all([survivor,source]);db.commit();ensure_household_accounting(db,household.id);db.commit();source_ledger_id=source.ledger_account_id
    transaction=Transaction(household_id=household.id,account_id=source.id,original_description="Processed",merchant="Processed",amount=Decimal("255.09"),direction="credit",posted_date=date(2026,5,30),category="Uncategorized",classification_source="unclassified",classification_confidence=Decimal("0"))
    statement=LiabilityStatement(household_id=household.id,account_id=survivor.id,opening_balance=Decimal("18000"),new_balance=Decimal("17887.34"),new_payments=Decimal("255.09"),due_date=date(2026,9,18),minimum_payment=Decimal("510.17"),interest_rate=Decimal("6.5"),interest_paid=Decimal("69.46"),statement_date=date(2026,7,21))
    payment=ScheduledPayment(household_id=household.id,account_id=None,obligation_account_id=source.id,payee="Best Egg",amount=Decimal("510.17"),minimum_amount=Decimal("510.17"),scheduled_date=date(2026,9,18),earliest_withdrawal_date=date(2026,9,18),latest_withdrawal_date=date(2026,9,18),due_date=date(2026,9,18))
    db.add_all([transaction,statement,payment]);db.commit()
    result=merge_accounts(db,household.id,survivor.id,source.id)
    db.refresh(survivor);db.refresh(source);db.refresh(transaction);db.refresh(statement);db.refresh(payment)
    assert result["moved"]["transactions"]==1
    assert survivor.connection_id==connection.id and survivor.provider_account_id=="remote-best-egg"
    assert survivor.balance==Decimal("17552.39") and survivor.original_balance==Decimal("20000.00")
    assert source.is_active is False and source.connection_id is None
    assert transaction.account_id==survivor.id
    assert statement.account_id==survivor.id
    assert payment.obligation_account_id==survivor.id
    assert db.scalar(select(func.count(JournalLine.id)).where(JournalLine.ledger_account_id==source_ledger_id))==0
    source_ledger=db.get(LedgerAccount,source_ledger_id)
    assert source_ledger.is_active is False and source_ledger.allow_posting is False
    assert db.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.action=="accounts_merged"))==1


def test_fidelity_core_sweep_is_an_internal_transfer():
    db,household,local,connection=setup();local.connection_id=connection.id;local.provider_account_id="remote-1";db.commit()
    description="PURCHASE INTO CORE ACCOUNT FDIC INSURED DEPOSIT AT CITIZENS BANK (QZENQ) (Cash)"
    payload={"accounts":[{"id":"remote-1","balance":"1082.96","balance-date":1788566400,"transactions":[{"id":"core-sweep","posted":1788393600,"amount":"982.96","description":description}]}]}
    assert is_fidelity_core_sweep(description)
    assert sync(db,household.id,connection,payload)=={"added":1,"duplicates":0,"matched_existing":0}
    row=db.scalar(select(Transaction).where(Transaction.account_id==local.id));category=db.get(LedgerAccount,row.category_id)
    assert row.is_transfer is True and row.category=="Transfer"
    assert category.code=="1100" and category.account_type=="asset"
    assert row.direction=="debit"

def test_core_sweep_redemption_posts_as_a_credit_despite_the_provider_sign():
    db,household,local,connection=setup();local.connection_id=connection.id;local.provider_account_id="remote-1";db.commit()
    description="REDEMPTION FROM CORE ACCOUNT FDIC INSURED DEPOSIT AT CITIZENS BANK (QZENQ) (Cash)"
    assert core_sweep_direction(description)=="credit" and core_sweep_direction("DIRECT DEPOSIT SCH DISTRICTPAYROLL") is None
    payload={"accounts":[{"id":"remote-1","balance":"100.00","balance-date":1788566400,"transactions":[{"id":"core-redemption","posted":1788393600,"amount":"-982.96","description":description}]}]}
    assert sync(db,household.id,connection,payload)["added"]==1
    row=db.scalar(select(Transaction).where(Transaction.account_id==local.id))
    assert row.direction=="credit" and row.is_transfer is True

def test_classify_core_cash_sweeps_corrects_previously_imported_directions():
    db,household,local,connection=setup();local.connection_id=connection.id;local.provider_account_id="remote-1";db.commit()
    stale=Transaction(household_id=household.id,account_id=local.id,original_description="PURCHASE INTO CORE ACCOUNT FDIC INSURED DEPOSIT AT CITIZENS BANK (QZENQ) (Cash)",merchant="Core Sweep",amount=Decimal("982.96"),direction="credit",posted_date=date(2026,9,17),pending=False,is_transfer=False,data_source="simplefin")
    db.add(stale);db.commit()
    assert classify_core_cash_sweeps(db,household.id)["updated"]==1
    db.refresh(stale)
    assert stale.direction=="debit" and stale.is_transfer is True and stale.category=="Transfer"

def test_confirmed_simplefin_duplicate_does_not_return_on_next_sync():
    db,household,local,connection=setup();local.connection_id=connection.id;local.provider_account_id="remote-1";db.commit()
    payload={"accounts":[{"id":"remote-1","balance":"94.17","balance-date":1788566400,"transactions":[{"id":"gerber-a","posted":1785974400,"amount":"-5.83","description":"DIRECT DEBIT GERBER LIFE INSURANCE"},{"id":"gerber-b","posted":1785974400,"amount":"-5.83","description":"DIRECT DEBIT GERBER LIFE INSURANCE"}]}]}
    assert sync(db,household.id,connection,payload)["added"]==2
    rows=list(db.scalars(select(Transaction).where(Transaction.account_id==local.id).order_by(Transaction.id)))
    merge_duplicate(db,household.id,rows[0].id,rows[1].id)
    result=sync(db,household.id,connection,payload)
    assert result["duplicates"]==2 and db.scalar(select(func.count(Transaction.id)))==1


def test_accounts_include_connection_sync_metadata():
    db,household,local,connection=setup()
    synced_at=datetime.now(timezone.utc)
    local.connection_id=connection.id
    local.provider_account_id="remote-1"
    local.connection_mode="automatic"
    local.data_source="simplefin"
    connection.status="active"
    connection.last_sync_at=synced_at
    connection.last_successful_sync_at=synced_at
    connection.next_sync_at=synced_at+timedelta(hours=6)
    db.commit()
    result=account_rows(hid=household.id,db=db)[0]
    assert result["connection_provider"]=="simplefin"
    assert result["connection_status"]=="active"
    assert result["sync_health"]=="healthy"
    assert datetime.fromisoformat(result["last_successful_sync_at"]).replace(tzinfo=None)==synced_at.replace(tzinfo=None)
    assert datetime.fromisoformat(result["next_sync_at"]).replace(tzinfo=None)==(synced_at+timedelta(hours=6)).replace(tzinfo=None)
