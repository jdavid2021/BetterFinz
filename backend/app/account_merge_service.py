from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.accounting_service import ensure_household_accounting, initialize_opening_balances, sync_transaction_journal
from app.audit_service import record_audit
from app.models import (
    AccountReconciliation,
    BillProfile,
    CategorizationRule,
    FinancialAccount,
    IncomeEvent,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    LiabilityStatement,
    ScheduledPayment,
    StatementUpload,
    Transaction,
    TransactionMerge,
)


class AccountMergeError(ValueError):
    pass


def _move_rows(db: Session, model, household_id: str, field: str, source_id: str, survivor_id: str) -> int:
    column = getattr(model, field)
    result = db.execute(
        update(model)
        .where(model.household_id == household_id, column == source_id)
        .values({field: survivor_id})
    )
    return int(result.rowcount or 0)


def _newer_balance(source: FinancialAccount, survivor: FinancialAccount) -> bool:
    if source.connection_id and not survivor.connection_id:
        return True
    if source.balance_as_of_date is None:
        return False
    return survivor.balance_as_of_date is None or source.balance_as_of_date > survivor.balance_as_of_date


def merge_accounts(
    db: Session,
    household_id: str,
    survivor_id: str,
    duplicate_id: str,
    user_id: str | None = None,
) -> dict:
    if survivor_id == duplicate_id:
        raise AccountMergeError("Choose two different accounts.")
    ensure_household_accounting(db, household_id)
    rows = list(
        db.scalars(
            select(FinancialAccount).where(
                FinancialAccount.household_id == household_id,
                FinancialAccount.id.in_([survivor_id, duplicate_id]),
                FinancialAccount.is_active.is_(True),
            )
        )
    )
    if len(rows) != 2:
        raise AccountMergeError("One or both accounts are unavailable.")
    by_id = {row.id: row for row in rows}
    survivor, source = by_id[survivor_id], by_id[duplicate_id]
    if survivor.kind != source.kind:
        raise AccountMergeError("Only accounts of the same type can be merged.")
    if survivor.connection_id and source.connection_id and (
        survivor.connection_id != source.connection_id
        or survivor.provider_account_id != source.provider_account_id
    ):
        raise AccountMergeError("Disconnect one provider account before merging two different live connections.")
    survivor_periods = set(db.execute(select(AccountReconciliation.period_start, AccountReconciliation.period_end).where(AccountReconciliation.household_id == household_id, AccountReconciliation.account_id == survivor.id)).all())
    source_periods = set(db.execute(select(AccountReconciliation.period_start, AccountReconciliation.period_end).where(AccountReconciliation.household_id == household_id, AccountReconciliation.account_id == source.id)).all())
    if survivor_periods & source_periods:
        raise AccountMergeError("The accounts contain overlapping reconciliations that require manual review.")

    source_ledger_id = source.ledger_account_id
    survivor_ledger_id = survivor.ledger_account_id
    if not source_ledger_id or not survivor_ledger_id:
        raise AccountMergeError("Accounting setup is incomplete for one of the accounts.")

    moved = {
        "transactions": _move_rows(db, Transaction, household_id, "account_id", source.id, survivor.id),
        "statements": _move_rows(db, LiabilityStatement, household_id, "account_id", source.id, survivor.id),
        "uploads": _move_rows(db, StatementUpload, household_id, "account_id", source.id, survivor.id),
        "reconciliations": _move_rows(db, AccountReconciliation, household_id, "account_id", source.id, survivor.id),
        "income_events": _move_rows(db, IncomeEvent, household_id, "account_id", source.id, survivor.id),
        "funding_payments": _move_rows(db, ScheduledPayment, household_id, "account_id", source.id, survivor.id),
        "obligation_payments": _move_rows(db, ScheduledPayment, household_id, "obligation_account_id", source.id, survivor.id),
        "bill_profiles": _move_rows(db, BillProfile, household_id, "default_account_id", source.id, survivor.id),
        "transaction_merges": _move_rows(db, TransactionMerge, household_id, "account_id", source.id, survivor.id),
    }

    affected_transactions = list(
        db.scalars(
            select(Transaction).where(
                Transaction.household_id == household_id,
                (Transaction.account_id == survivor.id) | (Transaction.category_id == source_ledger_id),
            )
        )
    )
    db.execute(
        update(Transaction)
        .where(Transaction.household_id == household_id, Transaction.category_id == source_ledger_id)
        .values(category_id=survivor_ledger_id, category=survivor.name)
    )
    db.execute(
        update(CategorizationRule)
        .where(CategorizationRule.household_id == household_id, CategorizationRule.category_id == source_ledger_id)
        .values(category_id=survivor_ledger_id, category=survivor.name)
    )

    opening_entry_ids = list(
        db.scalars(
            select(JournalEntry.id)
            .join(JournalLine, JournalLine.journal_entry_id == JournalEntry.id)
            .where(
                JournalEntry.household_id == household_id,
                JournalEntry.source_type == "opening_balance",
                JournalLine.ledger_account_id.in_([source_ledger_id, survivor_ledger_id]),
            )
        )
    )
    if opening_entry_ids:
        db.execute(delete(JournalLine).where(JournalLine.journal_entry_id.in_(opening_entry_ids)))
        db.execute(delete(JournalEntry).where(JournalEntry.id.in_(opening_entry_ids)))
    db.execute(
        update(JournalLine)
        .where(JournalLine.household_id == household_id, JournalLine.ledger_account_id == source_ledger_id)
        .values(ledger_account_id=survivor_ledger_id)
    )

    if _newer_balance(source, survivor):
        survivor.balance = source.balance
        survivor.balance_as_of_date = source.balance_as_of_date
        if survivor.kind in {"checking", "savings", "money_market", "cash_management", "investment", "credit_card"}:
            survivor.available_balance = source.available_balance
        survivor.investment_balance = source.investment_balance
    if survivor.original_balance is None:
        survivor.original_balance = source.original_balance
    survivor.institution_name = survivor.institution_name or source.institution_name
    survivor.bank_login_url = survivor.bank_login_url or source.bank_login_url
    source_connection_id = source.connection_id
    source_provider_account_id = source.provider_account_id
    source_data_source = source.data_source
    source.connection_id = None
    source.provider_account_id = None
    source.connection_mode = "manual"
    db.flush()
    if source_connection_id:
        survivor.connection_id = source_connection_id
        survivor.provider_account_id = source_provider_account_id
        survivor.connection_mode = "automatic"
        survivor.data_source = source_data_source
    source.is_active = False
    source.dml_flag = "D"
    source.accounting_initialized = True
    survivor.accounting_initialized = False
    source_ledger = db.get(LedgerAccount, source_ledger_id)
    if source_ledger:
        source_ledger.is_active = False
        source_ledger.allow_posting = False
        source_ledger.dml_flag = "D"
    db.flush()
    for transaction in affected_transactions:
        sync_transaction_journal(db, transaction)
    initialize_opening_balances(db, household_id)
    record_audit(db, household_id, user_id, "accounts_merged", label=survivor.name, source=source.name)
    db.commit()
    db.refresh(survivor)
    return {"account_id": survivor.id, "archived_account_id": source.id, "moved": moved}
