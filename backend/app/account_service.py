from datetime import date
from decimal import Decimal
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import FinancialAccount, ScheduledPayment
from app.schemas import AccountConnectionUpdate, ManualAccountCreate


def _available_balance(body: ManualAccountCreate):
    return Decimal("0") if body.kind in {"mortgage", "auto_loan", "buy_now_pay_later", "loan", "other"} else body.available_balance


def _reserve(body: ManualAccountCreate):
    return Decimal("0") if body.kind in {"credit_card", "mortgage", "auto_loan", "buy_now_pay_later", "loan", "other"} else body.reserve

def update_manual_connection(db: Session, household_id: str, account_id: str, body: AccountConnectionUpdate) -> FinancialAccount | None:
    account = db.scalar(select(FinancialAccount).where(FinancialAccount.id == account_id, FinancialAccount.household_id == household_id, FinancialAccount.is_active))
    if not account: return None
    account.connection_mode = body.connection_mode
    account.institution_name = body.institution_name
    account.bank_login_url = body.bank_login_url
    db.commit(); db.refresh(account); return account


def create_manual_account(db: Session, household_id: str, body: ManualAccountCreate) -> FinancialAccount:
    account = FinancialAccount(household_id=household_id, name=body.name, kind=body.kind, mask=body.mask, balance=body.balance, balance_as_of_date=date.today(), available_balance=_available_balance(body), investment_balance=max(body.balance-body.available_balance,Decimal("0")) if body.kind=="cash_management" else Decimal("0"), original_balance=body.original_balance, reserve=_reserve(body), connection_mode="manual", institution_name=body.institution_name, bank_login_url=body.bank_login_url, data_source="manual")
    db.add(account); db.commit(); db.refresh(account); return account


def update_manual_account(db: Session, household_id: str, account_id: str, body: ManualAccountCreate) -> FinancialAccount | None:
    account = db.scalar(select(FinancialAccount).where(FinancialAccount.id == account_id, FinancialAccount.household_id == household_id, FinancialAccount.is_active))
    if not account: return None
    account.name = body.name; account.kind = body.kind; account.mask = body.mask
    account.balance = body.balance; account.balance_as_of_date = date.today(); account.available_balance = _available_balance(body); account.investment_balance=max(body.balance-body.available_balance,Decimal("0")) if body.kind=="cash_management" else Decimal("0"); account.original_balance = body.original_balance; account.reserve = _reserve(body)
    account.connection_mode = "manual"; account.institution_name = body.institution_name; account.bank_login_url = body.bank_login_url
    account.dml_flag = "U"; db.commit(); db.refresh(account); return account


def archive_account(db: Session, household_id: str, account_id: str) -> FinancialAccount | None:
    account = db.scalar(select(FinancialAccount).where(FinancialAccount.id == account_id, FinancialAccount.household_id == household_id, FinancialAccount.is_active))
    if not account: return None
    db.execute(update(ScheduledPayment).where(ScheduledPayment.household_id == household_id, ScheduledPayment.account_id == account.id).values(account_id=None))
    account.is_active = False; account.dml_flag = "D"; db.commit(); return account
