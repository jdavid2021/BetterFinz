import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

def uid() -> str: return str(uuid.uuid4())
def now() -> datetime: return datetime.now(timezone.utc)

class AuditMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    data_source: Mapped[str] = mapped_column(String(32), default="manual")
    dml_flag: Mapped[str] = mapped_column(String(1), default="I")

class User(Base, AuditMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auth_version: Mapped[int] = mapped_column(default=0)
    memberships: Mapped[list["HouseholdMember"]] = relationship(back_populates="user")

class SocialAccount(Base, AuditMixin):
    __tablename__ = "social_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(320))
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_social_provider_subject"),)

class LoginToken(Base, AuditMixin):
    __tablename__ = "login_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(320), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(32), default="magic_login", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class LegalAcceptance(Base):
    __tablename__ = "legal_acceptances"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document: Mapped[str] = mapped_column(String(20))
    version: Mapped[str] = mapped_column(String(40))
    document_digest: Mapped[str] = mapped_column(String(64))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint(
            "user_id", "document", "version", name="uq_legal_user_document_version"
        ),
    )

class AccountDeletionRequest(Base):
    __tablename__ = "account_deletion_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="awaiting_confirmation")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execute_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_account_deletion_requests_due", "status", "execute_after"),
    )

class DeletionTombstone(Base):
    __tablename__ = "deletion_tombstones"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    subject_hash: Mapped[str] = mapped_column(String(64), unique=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reason: Mapped[str] = mapped_column(String(40), default="user_requested")

class WebAuthnCredential(Base, AuditMixin):
    __tablename__ = "webauthn_credentials"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    credential_id: Mapped[str] = mapped_column(String(1024), unique=True)
    public_key: Mapped[str] = mapped_column(Text)
    sign_count: Mapped[int] = mapped_column(default=0)
    transports: Mapped[str] = mapped_column(String(120), default="")
    label: Mapped[str] = mapped_column(String(80), default="Passkey")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class Household(Base, AuditMixin):
    __tablename__ = "households"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))
    workspace_type: Mapped[str] = mapped_column(String(30), default="individual")
    segment_label: Mapped[str] = mapped_column(String(30), default="Business")
    onboarding_dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class HouseholdMember(Base):
    __tablename__ = "household_members"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    role: Mapped[str] = mapped_column(String(24), default="owner")
    user: Mapped[User] = relationship(back_populates="memberships")
    __table_args__ = (UniqueConstraint("user_id", "household_id"),)

class FinancialAccount(Base, AuditMixin):
    __tablename__ = "financial_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(30))
    mask: Mapped[str] = mapped_column(String(4))
    balance: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    balance_as_of_date: Mapped[date | None] = mapped_column(Date)
    available_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    investment_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    original_balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    reserve: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    connection_mode: Mapped[str] = mapped_column(String(20), default="manual")
    institution_name: Mapped[str | None] = mapped_column(String(120))
    bank_login_url: Mapped[str | None] = mapped_column(String(500))
    connection_id: Mapped[str | None] = mapped_column(ForeignKey("financial_connections.id"), index=True)
    provider_account_id: Mapped[str | None] = mapped_column(String(255))
    # Deprecated storage retained for migration compatibility; accounts no longer own segments.
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("accounting_entities.id"), index=True)
    ledger_account_id: Mapped[str | None] = mapped_column(ForeignKey("ledger_accounts.id"), index=True)
    accounting_initialized: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("connection_id", "provider_account_id", name="uq_account_connection_provider"),)

class FinancialConnection(Base, AuditMixin):
    __tablename__ = "financial_connections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    provider: Mapped[str] = mapped_column(String(30), index=True)
    encrypted_access_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str] = mapped_column(String(255), default="")
    __table_args__ = (Index("ix_connection_household_provider", "household_id", "provider"),)

class IncomeEvent(Base, AuditMixin):
    __tablename__ = "income_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("financial_accounts.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    expected_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    reliability: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="expected")
    frequency: Mapped[str] = mapped_column(String(20), default="one_time")
    series_id: Mapped[str | None] = mapped_column(String(36), index=True)

class ScheduledPayment(Base, AuditMixin):
    __tablename__ = "scheduled_payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("financial_accounts.id"), index=True)
    obligation_account_id: Mapped[str | None] = mapped_column(ForeignKey("financial_accounts.id"), index=True)
    bill_id: Mapped[str | None] = mapped_column(ForeignKey("bill_profiles.id"), index=True)
    payee: Mapped[str] = mapped_column(String(120), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    minimum_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    scheduled_date: Mapped[date] = mapped_column(Date)
    earliest_withdrawal_date: Mapped[date] = mapped_column(Date, index=True)
    latest_withdrawal_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(String(40), default="manual_external_payment")
    status: Mapped[str] = mapped_column(String(40), default="planned")
    paid_date: Mapped[date | None] = mapped_column(Date)
    status_source: Mapped[str] = mapped_column(String(30), default="user")
    confirmation_number: Mapped[str | None] = mapped_column(String(80))
    optional: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (Index("ix_payment_household_withdrawal", "household_id", "earliest_withdrawal_date"),)


class BillProfile(Base, AuditMixin):
    __tablename__ = "bill_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    merchant_pattern: Mapped[str] = mapped_column(String(180))
    category: Mapped[str] = mapped_column(String(80), default="Bill")
    bill_type: Mapped[str] = mapped_column(String(30), default="recurring")
    amount_type: Mapped[str] = mapped_column(String(20), default="variable")
    typical_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    frequency: Mapped[str] = mapped_column(String(20), default="monthly")
    due_day: Mapped[int] = mapped_column(default=1)
    default_account_id: Mapped[str | None] = mapped_column(ForeignKey("financial_accounts.id"), index=True)
    website_url: Mapped[str | None] = mapped_column(String(500))
    biller_directory_id: Mapped[str | None] = mapped_column(String(80), index=True)
    payment_method: Mapped[str] = mapped_column(String(30), default="manual_online")
    remaining_balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    installments_remaining: Mapped[int | None] = mapped_column()
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("household_id", "merchant_pattern", name="uq_bill_household_pattern"),)


class IgnoredBillPattern(Base, AuditMixin):
    __tablename__ = "ignored_bill_patterns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    merchant_pattern: Mapped[str] = mapped_column(String(180))
    __table_args__ = (UniqueConstraint("household_id", "merchant_pattern", name="uq_ignored_bill_household_pattern"),)

class RecurringChargeSeries(Base, AuditMixin):
    __tablename__ = "recurring_charge_series"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("financial_accounts.id", ondelete="CASCADE"), index=True)
    merchant_pattern: Mapped[str] = mapped_column(String(180))
    name: Mapped[str] = mapped_column(String(120))
    series_type: Mapped[str] = mapped_column(String(30), default="subscription")
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    typical_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    frequency: Mapped[str] = mapped_column(String(20))
    last_charge_date: Mapped[date] = mapped_column(Date)
    next_expected_date: Mapped[date] = mapped_column(Date, index=True)
    confidence: Mapped[str] = mapped_column(String(20), default="medium")
    occurrence_count: Mapped[int] = mapped_column(default=2)
    amount_variation: Mapped[Decimal] = mapped_column(Numeric(7, 4), default=Decimal("0"))
    __table_args__ = (
        UniqueConstraint("household_id", "account_id", "merchant_pattern", name="uq_recurring_household_account_pattern"),
        CheckConstraint("series_type in ('subscription','recurring_bill')", name="ck_recurring_series_type"),
        CheckConstraint("status in ('confirmed','dismissed')", name="ck_recurring_status"),
    )

class AccountingEntity(Base, AuditMixin):
    __tablename__ = "accounting_entities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    entity_type: Mapped[str] = mapped_column(String(30), default="personal")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("household_id", "name", name="uq_entity_household_name"),)

class LedgerAccount(Base, AuditMixin):
    __tablename__ = "ledger_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("accounting_entities.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("ledger_accounts.id"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    account_type: Mapped[str] = mapped_column(String(20))
    normal_balance: Mapped[str] = mapped_column(String(6))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_posting: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        UniqueConstraint("household_id", "entity_id", "code", name="uq_ledger_household_entity_code"),
        CheckConstraint("account_type in (\x27asset\x27,\x27liability\x27,\x27equity\x27,\x27income\x27,\x27expense\x27)", name="ck_ledger_account_type"),
        CheckConstraint("normal_balance in (\x27debit\x27,\x27credit\x27)", name="ck_ledger_normal_balance"),
    )

class Transaction(Base, AuditMixin):
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("financial_accounts.id"), index=True)
    provider_id: Mapped[str | None] = mapped_column(String(150), unique=True)
    original_description: Mapped[str] = mapped_column(String(255))
    merchant: Mapped[str] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    direction: Mapped[str] = mapped_column(String(10), default="unknown")
    posted_date: Mapped[date] = mapped_column(Date, index=True)
    pending: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str] = mapped_column(String(80), default="Uncategorized")
    classification_source: Mapped[str] = mapped_column(String(30), default="rules")
    classification_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"))
    fingerprint: Mapped[str | None] = mapped_column(String(64), unique=True)
    is_transfer: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("accounting_entities.id"), index=True)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("ledger_accounts.id"), index=True)

class JournalEntry(Base, AuditMixin):
    __tablename__ = "journal_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    # Legacy column name retained for a non-destructive migration. It now stores an
    # optional reporting segment, not a separate set of books.
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("accounting_entities.id"), index=True)
    transaction_id: Mapped[str | None] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), unique=True, index=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(30), default="transaction")
    status: Mapped[str] = mapped_column(String(20), default="posted")

class JournalLine(Base, AuditMixin):
    __tablename__ = "journal_lines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    journal_entry_id: Mapped[str] = mapped_column(ForeignKey("journal_entries.id", ondelete="CASCADE"), index=True)
    ledger_account_id: Mapped[str] = mapped_column(ForeignKey("ledger_accounts.id"), index=True)
    debit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    credit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    memo: Mapped[str] = mapped_column(String(255), default="")
    __table_args__ = (CheckConstraint("debit >= 0 and credit >= 0 and ((debit = 0) <> (credit = 0))", name="ck_journal_line_one_side"),)

class LiabilityStatement(Base, AuditMixin):
    __tablename__ = "liability_statements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("financial_accounts.id"), index=True)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    new_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    new_payments: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    due_date: Mapped[date] = mapped_column(Date, index=True)
    minimum_payment: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    interest_paid: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    statement_date: Mapped[date] = mapped_column(Date, index=True)

class StatementUpload(Base, AuditMixin):
    __tablename__ = "statement_uploads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("financial_accounts.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_format: Mapped[str] = mapped_column(String(12))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(30), default="completed")
    statement_start_date: Mapped[date | None] = mapped_column(Date)
    statement_end_date: Mapped[date | None] = mapped_column(Date, index=True)
    transactions_added: Mapped[int] = mapped_column(default=0)
    duplicates_skipped: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (Index("ix_statement_upload_household_account", "household_id", "account_id"),)

class AccountReconciliation(Base, AuditMixin):
    __tablename__ = "account_reconciliations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("financial_accounts.id"), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    closing_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    credits_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    debits_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    calculated_closing_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    difference: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    transaction_count: Mapped[int] = mapped_column(default=0)
    pending_count: Mapped[int] = mapped_column(default=0)
    reconciled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    notes: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("account_id", "period_start", "period_end", name="uq_reconciliation_account_period"),)

class TransactionMerge(Base, AuditMixin):
    __tablename__ = "transaction_merges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("financial_accounts.id"), index=True)
    survivor_transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    removed_transaction_id: Mapped[str] = mapped_column(String(36), unique=True)
    removed_snapshot: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(60), default="user_confirmed_duplicate")

class DebtStrategySnapshot(Base, AuditMixin):
    __tablename__ = "debt_strategy_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    payload: Mapped[str] = mapped_column(Text)


class PaymentMatch(Base, AuditMixin):
    __tablename__ = "payment_matches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("scheduled_payments.id"), unique=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), unique=True)
    match_type: Mapped[str] = mapped_column(String(30), default="exact")

class CategorizationRule(Base, AuditMixin):
    __tablename__ = "categorization_rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    pattern: Mapped[str] = mapped_column(String(180))
    sample_description: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(80))
    category_id: Mapped[str | None] = mapped_column(ForeignKey("ledger_accounts.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    match_count: Mapped[int] = mapped_column(default=0)
    last_matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("household_id", "pattern", name="uq_rule_household_pattern"), Index("ix_rule_household_active", "household_id", "is_active"))

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str | None] = mapped_column(String(36), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(100))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    detail: Mapped[str] = mapped_column(Text, default="")

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info")
    title: Mapped[str] = mapped_column(String(140))
    message: Mapped[str] = mapped_column(String(500))
    href: Mapped[str] = mapped_column(String(255))
    dedupe_key: Mapped[str] = mapped_column(String(180), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    low_balance: Mapped[bool] = mapped_column(Boolean, default=True)
    upcoming_payments: Mapped[bool] = mapped_column(Boolean, default=True)
    missing_income: Mapped[bool] = mapped_column(Boolean, default=True)
    upcoming_days: Mapped[int] = mapped_column(default=7)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class ImportRun(Base, AuditMixin):
    __tablename__ = "import_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    sheet_name: Mapped[str] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="previewed")
    report: Mapped[str] = mapped_column(Text, default="")
