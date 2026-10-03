from datetime import date
from decimal import Decimal
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

class LoginRequest(BaseModel): email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"); password: str = Field(min_length=8)
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    accept_terms: bool
    accept_privacy: bool
    terms_version: str = Field(min_length=1, max_length=40)
    privacy_version: str = Field(min_length=1, max_length=40)
class EmailRequest(BaseModel): email: EmailStr
class TokenRequest(BaseModel): token: str = Field(min_length=32, max_length=256)
class PasswordResetRequest(TokenRequest):
    password: str = Field(min_length=12, max_length=128)

class LegalAcceptanceRequest(BaseModel):
    accept_terms: bool
    accept_privacy: bool
    terms_version: str = Field(min_length=1, max_length=40)
    privacy_version: str = Field(min_length=1, max_length=40)

class ReauthenticationRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)

class DeletionRequestRequest(BaseModel):
    password: str | None = Field(default=None, max_length=128)

class DeletionConfirmationRequest(TokenRequest):
    pass
class PaymentCreate(BaseModel):
    payee: str = Field(min_length=1, max_length=120); account_id: str | None
    amount: Decimal = Field(gt=0, decimal_places=2); scheduled_date: date; expected_withdrawal_date: date
    due_date: date; method: str = "manual_external_payment"; confirmation_number: str | None = None
class PaymentUpdate(BaseModel):
    amount: Decimal | None = Field(None, gt=0); expected_withdrawal_date: date | None = None
    account_id: str | None = None; status: str | None = None; confirmation_number: str | None = None
class MonthlyPlanPaymentUpdate(BaseModel):
    payment_id: str | None = None
    obligation_account_id: str | None = None
    checking_account_id: str
    due_date: date
    scheduled_date: date
    amount: Decimal = Field(gt=0, decimal_places=2)
    status: str = "scheduled"
    paid_date: date | None = None
    confirmation_number: str | None = Field(default=None,max_length=80)

    @field_validator("status")

    def validate_status(cls,value:str)->str:
        if value not in {"not_planned","scheduled","paid"}:raise ValueError("Choose NP, Scheduled, or Paid.")
        return value

    @model_validator(mode="after")
    def validate_paid_date(self):
        if self.status=="paid" and self.paid_date is None:raise ValueError("Paid date is required when status is Paid.")
        return self

class ReconcileRequest(BaseModel):
    transaction_id: str
    confirm_account_change: bool = False
class RecurringChargeDecision(BaseModel):
    account_id: str = Field(min_length=36,max_length=36)
    merchant_pattern: str = Field(min_length=1,max_length=180)
    decision: str

    @field_validator("decision")
    @classmethod
    def validate_decision(cls,value:str)->str:
        if value not in {"subscription","recurring_bill","dismissed"}:raise ValueError("Choose subscription, recurring bill, or dismissed.")
        return value
class TransactionMatchContextRequest(BaseModel): transaction_ids: list[str] = Field(min_length=1,max_length=100)
class NotificationPreferencesUpdate(BaseModel):
    low_balance: bool = True
    upcoming_payments: bool = True
    missing_income: bool = True
    upcoming_days: int = Field(default=7,ge=1,le=30)
class AccountReconciliationRequest(BaseModel):
    account_id: str
    period_start: date
    period_end: date
    opening_balance: Decimal = Field(decimal_places=2)
    closing_balance: Decimal = Field(decimal_places=2)
    notes: str = Field(default="",max_length=500)

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end<self.period_start:raise ValueError("Period end must be on or after period start.")
        if (self.period_end-self.period_start).days>400:raise ValueError("Reconciliation periods cannot exceed 400 days.")
        return self

class ReconciliationTransactionCreate(BaseModel):
    account_id: str
    posted_date: date
    description: str = Field(min_length=1,max_length=255)
    amount: Decimal = Field(gt=0,decimal_places=2)
    direction: str

    @field_validator("direction")
    @classmethod
    def validate_direction(cls,value:str)->str:
        if value not in {"credit","debit"}:raise ValueError("Choose credit or debit.")
        return value

class TransactionMergeRequest(BaseModel):
    keep_transaction_id: str
    duplicate_transaction_id: str
class WhatIfRequest(BaseModel): payment_id: str; expected_withdrawal_date: date | None = None; amount: Decimal | None = None; include_uncertain_income: bool = False
class ApiModel(BaseModel): model_config = ConfigDict(from_attributes=True)


class AccountConnectionUpdate(BaseModel):
    institution_name: str = Field(min_length=1, max_length=120)
    bank_login_url: str = Field(max_length=500)
    connection_mode: str = "manual"

    @field_validator("bank_login_url")
    @classmethod
    def validate_bank_url(cls, value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Enter a public HTTPS bank URL without embedded credentials.")
        return value.strip()

    @field_validator("connection_mode")
    @classmethod
    def validate_connection_mode(cls, value: str) -> str:
        if value != "manual": raise ValueError("Automatic bank connections are not available yet.")
        return value

class ManualAccountCreate(AccountConnectionUpdate):
    name: str = Field(min_length=1, max_length=100)
    kind: str = "checking"
    mask: str = Field(pattern=r"^[A-Za-z0-9]{2,4}$")
    balance: Decimal = Field(ge=0, decimal_places=2)
    available_balance: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    original_balance: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    reserve: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        allowed = {"checking", "savings", "credit_card", "money_market", "cash_management", "mortgage", "auto_loan", "buy_now_pay_later", "loan", "investment", "other"}
        if value not in allowed: raise ValueError("Choose a supported account type.")
        return value

    @model_validator(mode="after")
    def validate_mortgage_balances(self):
        if self.kind == "mortgage" and self.original_balance is None:
            raise ValueError("Original mortgage amount is required for mortgage accounts.")
        return self

class AccountMergeRequest(BaseModel):
    survivor_account_id: str = Field(min_length=36, max_length=36)
    duplicate_account_id: str = Field(min_length=36, max_length=36)


class IncomeCreate(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    account_id: str
    amount: Decimal = Field(gt=0,decimal_places=2)
    expected_date: date
    reliability: str = "high_confidence"
    frequency: str = "one_time"

    @field_validator("reliability")
    @classmethod
    def validate_reliability(cls,value:str)->str:
        if value not in {"guaranteed","high_confidence","uncertain"}:raise ValueError("Choose guaranteed, high confidence, or uncertain.")
        return value

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls,value:str)->str:
        if value not in {"one_time","weekly","biweekly","semi_monthly","monthly"}:raise ValueError("Choose one-time, weekly, biweekly, semi-monthly, or monthly.")
        return value


class BillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    merchant_pattern: str = Field(min_length=1, max_length=180)
    category: str = Field(default="Bill", min_length=1, max_length=80)
    bill_type: str = "recurring"
    amount_type: str = "variable"
    typical_amount: Decimal = Field(gt=0, decimal_places=2)
    frequency: str = "monthly"
    due_date: date
    default_account_id: str | None = None
    website_url: str | None = Field(default=None, max_length=500)
    biller_id: str | None = Field(default=None,max_length=80)
    payment_method: str = "manual_online"
    remaining_balance: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    installments_remaining: int | None = Field(default=None, ge=1, le=600)

    @field_validator("bill_type")
    @classmethod
    def validate_bill_type(cls, value: str) -> str:
        if value not in {"recurring", "statement_balance", "installment", "one_time"}:
            raise ValueError("Choose recurring, statement balance, installment, or one-time.")
        return value

    @field_validator("amount_type")
    @classmethod
    def validate_amount_type(cls, value: str) -> str:
        if value not in {"fixed", "variable"}: raise ValueError("Choose fixed or variable.")
        return value

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, value: str) -> str:
        if value not in {"monthly", "quarterly", "annual", "one_time"}: raise ValueError("Choose a supported frequency.")
        return value

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls,value:str)->str:
        if value not in {"manual_online","company_autopay","bank_bill_pay","paper_check"}:raise ValueError("Choose a supported bill payment method.")
        return value

    @model_validator(mode="after")
    def validate_bill_funding(self):
        if self.payment_method in {"company_autopay","bank_bill_pay","paper_check"} and not self.default_account_id:raise ValueError("Choose the checking account used for this payment method.")
        return self

    @field_validator("website_url")
    @classmethod
    def validate_website_url(cls, value: str | None) -> str | None:
        if not value: return None
        parsed=urlparse(value.strip())
        if parsed.scheme!="https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Enter a public HTTPS biller URL without embedded credentials.")
        return value.strip()


class BillCandidateIgnore(BaseModel):
    merchant_pattern: str = Field(min_length=1, max_length=180)

class LiabilityStatementCreate(BaseModel):
    account_id: str
    opening_balance: Decimal = Field(ge=0)
    new_balance: Decimal = Field(ge=0)
    new_payments: Decimal = Field(default=Decimal("0"), ge=0)
    statement_date: date
    due_date: date
    minimum_payment: Decimal = Field(gt=0)
    interest_rate: Decimal | None = Field(default=None, ge=0, le=100)
    interest_paid: Decimal = Field(default=Decimal("0"), ge=0)

class LiabilityScheduleRequest(BaseModel):
    checking_account_id: str
    amount: Decimal = Field(gt=0)
    scheduled_date: date

class TransactionCategoryUpdate(BaseModel):
    transaction_ids: list[str] = Field(min_length=1, max_length=100)
    category_id: str | None = None
    category: str | None = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str | None) -> str | None:
        if value is None: return value
        allowed = {"Income", "Mortgage Payment", "Loan Payment", "Credit Card Payment", "Bill", "Transfer", "Groceries", "Transportation", "Healthcare", "Dining", "Shopping", "Uncategorized"}
        if value not in allowed: raise ValueError("Choose a supported transaction category.")
        return value

class CategorizationRuleUpdate(BaseModel):
    category_id: str | None = None
    category: str | None = None
    is_active: bool | None = None

    @field_validator("category")
    @classmethod
    def validate_optional_category(cls, value: str | None) -> str | None:
        if value is None:return value
        allowed={"Income","Mortgage Payment","Loan Payment","Credit Card Payment","Bill","Transfer","Groceries","Transportation","Healthcare","Dining","Shopping","Uncategorized"}
        if value not in allowed:raise ValueError("Choose a supported transaction category.")
        return value

class AccountingWorkspaceUpdate(BaseModel):
    workspace_type: str

class AccountingSegmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

class AccountingSegmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None

class SegmentSettingsUpdate(BaseModel):
    label: str = Field(min_length=1, max_length=30)

class TransactionSegmentUpdate(BaseModel):
    transaction_ids: list[str] = Field(min_length=1)
    segment_id: str | None = None

class LedgerCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: str
    account_type: str | None = None

class LedgerCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    parent_id: str | None = None
    is_active: bool | None = None
