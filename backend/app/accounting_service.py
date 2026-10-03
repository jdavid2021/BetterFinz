from __future__ import annotations

import hashlib

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    AccountingEntity,
    CategorizationRule,
    FinancialAccount,
    Household,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    Transaction,
)

CENT = Decimal("0.01")
ASSET_KINDS = {"checking", "savings", "money_market", "cash_management", "investment"}
WORKSPACE_TYPES = {"individual", "home", "home_business", "small_business", "enterprise"}

# code, name, type, parent code, posting
STANDARD_CHART = (
    ("1000", "Assets", "asset", None, False),
    ("1100", "Transfer", "asset", "1000", True),
    ("1110", "Credit Card Payment", "asset", "1000", True),
    ("1120", "Loan Payment", "asset", "1000", True),
    ("1130", "Mortgage Payment", "asset", "1000", True),
    ("2000", "Liabilities", "liability", None, False),
    ("3000", "Equity", "equity", None, False),
    ("3100", "Opening Balance Equity", "equity", "3000", True),
    ("3200", "Uncategorized", "equity", "3000", True),
    ("4000", "Income", "income", None, False),
    ("4100", "Income", "income", "4000", True),
    ("4200", "Business Income", "income", "4000", True),
    ("4300", "Other Income", "income", "4000", True),
    ("5000", "Expenses", "expense", None, False),
    ("5100", "Bill", "expense", "5000", True),
    ("5110", "Utilities", "expense", "5000", True),
    ("5111", "Electricity & Gas", "expense", "5110", True),
    ("5112", "Water & Sewer", "expense", "5110", True),
    ("5113", "Waste & Recycling", "expense", "5110", True),
    ("5114", "Phone & Internet", "expense", "5110", True),
    ("5200", "Food & Dining", "expense", "5000", False),
    ("5210", "Groceries", "expense", "5200", True),
    ("5220", "Dining", "expense", "5200", True),
    ("5300", "Transportation", "expense", "5000", True),
    ("5400", "Healthcare", "expense", "5000", True),
    ("5500", "Shopping", "expense", "5000", True),
    ("5600", "Professional Services", "expense", "5000", True),
    ("5700", "Software & Subscriptions", "expense", "5000", True),
    ("5800", "Taxes & Licenses", "expense", "5000", True),
    ("5900", "Other Expense", "expense", "5000", True),
)
LEGACY_CATEGORY_CODES = {
    "Uncategorized": "3200",
    "Income": "4100",
    "Mortgage Payment": "1130",
    "Loan Payment": "1120",
    "Credit Card Payment": "1110",
    "Bill": "5100",
    "Utilities": "5110",
    "Electricity & Gas": "5111",
    "Water & Sewer": "5112",
    "Waste & Recycling": "5113",
    "Phone & Internet": "5114",
    "Software & Subscriptions": "5700",
    "Transfer": "1100",
    "Groceries": "5210",
    "Transportation": "5300",
    "Healthcare": "5400",
    "Dining": "5220",
    "Shopping": "5500",
}


class AccountingError(ValueError):
    pass


def money(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def normal_balance(account_type: str) -> str:
    return "debit" if account_type in {"asset", "expense"} else "credit"


def ensure_household_accounting(db: Session, hid: str) -> None:
    if db.get_bind().dialect.name == "postgresql":
        lock_key = int.from_bytes(hashlib.sha256(hid.encode()).digest()[:8], "big", signed=True)
        db.execute(select(func.pg_advisory_xact_lock(lock_key)))
    chart = {
        row.code: row
        for row in db.scalars(
            select(LedgerAccount).where(
                LedgerAccount.household_id == hid,
                LedgerAccount.entity_id.is_(None),
            )
        )
    }
    for code, name, account_type, parent_code, posting in STANDARD_CHART:
        if code in chart:
            continue
        row = LedgerAccount(
            household_id=hid,
            entity_id=None,
            parent_id=chart[parent_code].id if parent_code else None,
            code=code,
            name=name,
            account_type=account_type,
            normal_balance=normal_balance(account_type),
            is_system=True,
            allow_posting=posting,
            data_source="accounting_template",
        )
        db.add(row)
        db.flush()
        chart[code] = row

    accounts = list(
        db.scalars(select(FinancialAccount).where(FinancialAccount.household_id == hid))
    )
    for account in accounts:
        if not account.ledger_account_id:
            account_type = "asset" if account.kind in ASSET_KINDS else "liability"
            root = chart["1000" if account_type == "asset" else "2000"]
            ledger = LedgerAccount(
                household_id=hid,
                entity_id=None,
                parent_id=root.id,
                code=f"FA-{account.id[:12]}",
                name=account.name,
                account_type=account_type,
                normal_balance=normal_balance(account_type),
                is_system=True,
                allow_posting=True,
                data_source="financial_account",
            )
            db.add(ledger)
            db.flush()
            account.ledger_account_id = ledger.id

    for transaction in db.scalars(
        select(Transaction).where(Transaction.household_id == hid)
    ):
        if not transaction.category_id:
            transaction.category_id = chart[
                LEGACY_CATEGORY_CODES.get(transaction.category, "3200")
            ].id

    category_by_name = {
        row.name: row
        for row in chart.values()
        if row.allow_posting
    }
    for rule in db.scalars(
        select(CategorizationRule).where(CategorizationRule.household_id == hid)
    ):
        if not rule.category_id:
            category = category_by_name.get(rule.category)
            if category:
                rule.category_id = category.id

    db.flush()
    sync_unposted_transactions(db, hid)
    initialize_opening_balances(db, hid)
    return None


def public_entity(row: AccountingEntity) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "is_active": row.is_active,
    }


def list_entities(db: Session, hid: str) -> list[dict]:
    ensure_household_accounting(db, hid)
    result = [
        public_entity(row)
        for row in db.scalars(
            select(AccountingEntity)
            .where(AccountingEntity.household_id == hid, AccountingEntity.is_active.is_(True))
            .order_by(AccountingEntity.name)
        )
    ]
    db.commit()
    return result


def create_entity(db: Session, hid: str, name: str) -> dict:
    ensure_household_accounting(db, hid)
    clean = name.strip()
    if db.scalar(
        select(AccountingEntity.id).where(
            AccountingEntity.household_id == hid,
            func.lower(AccountingEntity.name) == clean.lower(),
        )
    ):
        raise AccountingError("A segment with this name already exists.")
    row = AccountingEntity(
        household_id=hid,
        name=clean,
        entity_type="segment",
        data_source="manual",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return public_entity(row)


def update_entity(db: Session, hid: str, segment_id: str, name: str | None, is_active: bool | None) -> dict:
    row = db.scalar(select(AccountingEntity).where(AccountingEntity.id == segment_id, AccountingEntity.household_id == hid))
    if not row:
        raise AccountingError("Segment not found.")
    if name is not None:
        clean = name.strip()
        duplicate = db.scalar(select(AccountingEntity.id).where(AccountingEntity.household_id == hid, func.lower(AccountingEntity.name) == clean.lower(), AccountingEntity.id != row.id))
        if duplicate:
            raise AccountingError("A segment with this name already exists.")
        row.name = clean
    if is_active is not None:
        row.is_active = is_active
    db.commit()
    return public_entity(row)


def segment_settings(db: Session, hid: str) -> dict:
    household = db.get(Household, hid)
    if not household:
        raise AccountingError("Household not found.")
    return {"label": household.segment_label}


def update_segment_settings(db: Session, hid: str, label: str) -> dict:
    household = db.get(Household, hid)
    if not household:
        raise AccountingError("Household not found.")
    household.segment_label = label.strip()
    db.commit()
    return {"label": household.segment_label}


def update_transaction_segments(db: Session, hid: str, transaction_ids: list[str], segment_id: str | None) -> dict:
    if segment_id and not db.scalar(select(AccountingEntity.id).where(AccountingEntity.id == segment_id, AccountingEntity.household_id == hid, AccountingEntity.is_active.is_(True))):
        raise AccountingError("Segment not found.")
    rows = list(db.scalars(select(Transaction).where(Transaction.household_id == hid, Transaction.id.in_(transaction_ids))))
    if len(rows) != len(set(transaction_ids)):
        raise AccountingError("One or more transactions were not found.")
    for row in rows:
        row.entity_id = segment_id
        entry = db.scalar(select(JournalEntry).where(JournalEntry.transaction_id == row.id))
        if entry:
            entry.entity_id = segment_id
    db.commit()
    return {"updated": len(rows), "segment_id": segment_id}


def update_workspace(db: Session, hid: str, workspace_type: str) -> dict:
    if workspace_type not in WORKSPACE_TYPES:
        raise AccountingError("Choose a supported workspace type.")
    household = db.get(Household, hid)
    if not household:
        raise AccountingError("Household not found.")
    household.workspace_type = workspace_type
    household.dml_flag = "U"
    ensure_household_accounting(db, hid)
    db.commit()
    return {"workspace_type": workspace_type}


def workspace(db: Session, hid: str) -> dict:
    household = db.get(Household, hid)
    ensure_household_accounting(db, hid)
    db.commit()
    return {"workspace_type": household.workspace_type if household else "individual"}


def _depth(accounts: dict[str, LedgerAccount], row: LedgerAccount) -> int:
    depth = 1
    parent_id = row.parent_id
    seen = {row.id}
    while parent_id:
        if parent_id in seen:
            raise AccountingError("The category tree contains a cycle.")
        seen.add(parent_id)
        parent = accounts.get(parent_id)
        if not parent:
            break
        depth += 1
        parent_id = parent.parent_id
    return depth


def category_rows(db: Session, hid: str, include_inactive: bool = False) -> list[LedgerAccount]:
    ensure_household_accounting(db, hid)
    stmt = select(LedgerAccount).where(
        LedgerAccount.household_id == hid,
        LedgerAccount.entity_id.is_(None),
    )
    if not include_inactive:
        stmt = stmt.where(LedgerAccount.is_active.is_(True))
    return list(db.scalars(stmt.order_by(LedgerAccount.code, LedgerAccount.name)))


def public_categories(db: Session, hid: str, include_inactive: bool = False) -> list[dict]:
    rows = category_rows(db, hid, include_inactive)
    by_id = {row.id: row for row in rows}
    result = []
    for row in rows:
        path = [row.name]
        parent = by_id.get(row.parent_id or "")
        while parent:
            path.insert(0, parent.name)
            parent = by_id.get(parent.parent_id or "")
        result.append(
            {
                "id": row.id,
                "parent_id": row.parent_id,
                "code": row.code,
                "name": row.name,
                "path": " › ".join(path),
                "depth": len(path),
                "account_type": row.account_type,
                "normal_balance": row.normal_balance,
                "is_system": row.is_system,
                "is_active": row.is_active,
                "allow_posting": row.allow_posting,
            }
        )
    db.commit()
    return result


def create_category(
    db: Session, hid: str, name: str, parent_id: str, account_type: str | None = None
) -> dict:
    clean = name.strip()
    if not clean:
        raise AccountingError("Enter a category name.")
    rows = category_rows(db, hid, True)
    by_id = {row.id: row for row in rows}
    parent = by_id.get(parent_id)
    if not parent or not parent.is_active:
        raise AccountingError("Choose an active parent category.")
    if _depth(by_id, parent) >= 3:
        raise AccountingError("Categories can have no more than three levels.")
    inherited_type = parent.account_type
    if account_type and account_type != inherited_type:
        raise AccountingError("A child category must use its parent category type.")
    if any(
        row.parent_id == parent.id
        and row.name.lower() == clean.lower()
        and row.is_active
        for row in rows
    ):
        raise AccountingError("That category already exists under this parent.")
    sequence = max(
        [int(row.code[-3:]) for row in rows if row.code.startswith("U") and row.code[-3:].isdigit()]
        or [0]
    ) + 1
    row = LedgerAccount(
        household_id=hid,
        parent_id=parent.id,
        code=f"U{sequence:03d}",
        name=clean,
        account_type=inherited_type,
        normal_balance=normal_balance(inherited_type),
        is_system=False,
        allow_posting=True,
        data_source="manual",
    )
    db.add(row)
    db.commit()
    return next(item for item in public_categories(db, hid, True) if item["id"] == row.id)


def update_category(
    db: Session,
    hid: str,
    category_id: str,
    name: str | None = None,
    parent_id: str | None = None,
    is_active: bool | None = None,
) -> dict:
    rows = category_rows(db, hid, True)
    by_id = {row.id: row for row in rows}
    row = by_id.get(category_id)
    if not row:
        raise AccountingError("Category not found.")
    if row.parent_id is None:
        raise AccountingError("Top-level accounting groups are fixed.")
    if name is not None:
        clean = name.strip()
        if not clean:
            raise AccountingError("Enter a category name.")
        row.name = clean
    if parent_id is not None and parent_id != row.parent_id:
        parent = by_id.get(parent_id)
        if not parent or not parent.is_active:
            raise AccountingError("Choose an active parent category.")
        if parent.id == row.id:
            raise AccountingError("A category cannot be its own parent.")
        if parent.account_type != row.account_type:
            raise AccountingError("Categories cannot move between accounting groups.")
        if _depth(by_id, parent) >= 3:
            raise AccountingError("Categories can have no more than three levels.")
        row.parent_id = parent.id
        if any(child.parent_id == row.id for child in rows):
            raise AccountingError("Move this category's children before moving it to level three.")
    if is_active is not None:
        if row.is_system and not is_active:
            raise AccountingError("Built-in accounting categories cannot be archived.")
        row.is_active = is_active
    row.dml_flag = "U"
    # Preserve readable legacy strings while references use immutable IDs.
    for transaction in db.scalars(
        select(Transaction).where(
            Transaction.household_id == hid,
            Transaction.category_id == row.id,
        )
    ):
        transaction.category = row.name
    for rule in db.scalars(
        select(CategorizationRule).where(
            CategorizationRule.household_id == hid,
            CategorizationRule.category_id == row.id,
        )
    ):
        rule.category = row.name
    db.commit()
    return next(item for item in public_categories(db, hid, True) if item["id"] == row.id)


def category_for(db: Session, hid: str, category_id: str) -> LedgerAccount:
    row = db.scalar(
        select(LedgerAccount).where(
            LedgerAccount.id == category_id,
            LedgerAccount.household_id == hid,
            LedgerAccount.entity_id.is_(None),
            LedgerAccount.is_active.is_(True),
            LedgerAccount.allow_posting.is_(True),
        )
    )
    if not row:
        raise AccountingError("Choose an active posting category.")
    return row


def _replace_journal_lines(
    db: Session, entry: JournalEntry, source_account_id: str, category_id: str, amount: Decimal, direction: str
) -> None:
    db.execute(delete(JournalLine).where(JournalLine.journal_entry_id == entry.id))
    if direction == "credit":
        sides = ((source_account_id, amount, Decimal("0")), (category_id, Decimal("0"), amount))
    elif direction == "debit":
        sides = ((category_id, amount, Decimal("0")), (source_account_id, Decimal("0"), amount))
    else:
        return
    for ledger_id, debit, credit in sides:
        db.add(
            JournalLine(
                household_id=entry.household_id,
                journal_entry_id=entry.id,
                ledger_account_id=ledger_id,
                debit=money(debit),
                credit=money(credit),
                data_source="automatic_posting",
            )
        )


def sync_transaction_journal(db: Session, transaction: Transaction) -> None:
    entry = db.scalar(
        select(JournalEntry).where(JournalEntry.transaction_id == transaction.id)
    )
    if transaction.pending or transaction.direction not in {"credit", "debit"} or money(transaction.amount) == 0:
        if entry:
            db.delete(entry)
        return
    account = db.get(FinancialAccount, transaction.account_id)
    if not account or not account.ledger_account_id or not transaction.category_id:
        return
    if not entry:
        entry = JournalEntry(
            household_id=transaction.household_id,
            entity_id=transaction.entity_id,
            transaction_id=transaction.id,
            entry_date=transaction.posted_date,
            description=transaction.original_description,
            source_type="transaction",
            data_source="automatic_posting",
        )
        db.add(entry)
        db.flush()
    else:
        entry.entity_id = transaction.entity_id
        entry.entry_date = transaction.posted_date
        entry.description = transaction.original_description
    _replace_journal_lines(
        db,
        entry,
        account.ledger_account_id,
        transaction.category_id,
        money(transaction.amount),
        transaction.direction,
    )


def sync_unposted_transactions(db: Session, hid: str) -> int:
    rows = list(
        db.scalars(
            select(Transaction)
            .outerjoin(JournalEntry, JournalEntry.transaction_id == Transaction.id)
            .where(
                Transaction.household_id == hid,
                Transaction.pending.is_(False),
                JournalEntry.id.is_(None),
            )
        )
    )
    for row in rows:
        sync_transaction_journal(db, row)
    db.flush()
    return len(rows)


def initialize_opening_balances(db: Session, hid: str) -> None:
    opening_equity = db.scalar(
        select(LedgerAccount).where(
            LedgerAccount.household_id == hid,
            LedgerAccount.entity_id.is_(None),
            LedgerAccount.code == "3100",
        )
    )
    if not opening_equity:
        return
    accounts = list(
        db.scalars(
            select(FinancialAccount).where(
                FinancialAccount.household_id == hid,
                FinancialAccount.accounting_initialized.is_(False),
                FinancialAccount.ledger_account_id.is_not(None),
            )
        )
    )
    for account in accounts:
        current_net = db.scalar(
            select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .where(
                JournalEntry.household_id == hid,
                JournalEntry.source_type == "transaction",
                JournalLine.ledger_account_id == account.ledger_account_id,
                JournalEntry.entry_date <= (account.balance_as_of_date or date.today()),
            )
        )
        desired = money(account.balance if account.kind in ASSET_KINDS else -account.balance)
        delta = money(desired - Decimal(current_net or 0))
        if delta:
            earliest = db.scalar(
                select(func.min(Transaction.posted_date)).where(
                    Transaction.household_id == hid,
                    Transaction.account_id == account.id,
                )
            )
            entry = JournalEntry(
                household_id=hid,
                entity_id=None,
                transaction_id=None,
                entry_date=(earliest - timedelta(days=1)) if earliest else (account.balance_as_of_date or date.today()),
                description=f"Opening balance · {account.name}",
                source_type="opening_balance",
                data_source="accounting_setup",
            )
            db.add(entry)
            db.flush()
            first = (account.ledger_account_id, delta, Decimal("0")) if delta > 0 else (account.ledger_account_id, Decimal("0"), -delta)
            second = (opening_equity.id, Decimal("0"), delta) if delta > 0 else (opening_equity.id, -delta, Decimal("0"))
            for ledger_id, debit, credit in (first, second):
                db.add(JournalLine(
                    household_id=hid,
                    journal_entry_id=entry.id,
                    ledger_account_id=ledger_id,
                    debit=money(debit),
                    credit=money(credit),
                    data_source="accounting_setup",
                ))
        account.accounting_initialized = True
    db.flush()


def rebuild_opening_balances(db: Session, hid: str, account_ids: list[str]) -> None:
    accounts = list(
        db.scalars(
            select(FinancialAccount).where(
                FinancialAccount.household_id == hid,
                FinancialAccount.id.in_(account_ids),
            )
        )
    )
    for account in accounts:
        if account.ledger_account_id:
            entry_ids = list(
                db.scalars(
                    select(JournalEntry.id)
                    .join(JournalLine, JournalLine.journal_entry_id == JournalEntry.id)
                    .where(
                        JournalEntry.household_id == hid,
                        JournalEntry.source_type == "opening_balance",
                        JournalLine.ledger_account_id == account.ledger_account_id,
                    )
                )
            )
            if entry_ids:
                db.execute(delete(JournalEntry).where(JournalEntry.id.in_(entry_ids)))
        account.accounting_initialized = False
    db.flush()
    ensure_household_accounting(db, hid)


def update_transaction_categories(
    db: Session, hid: str, transaction_ids: list[str], category_id: str
) -> dict:
    category = category_for(db, hid, category_id)
    rows = list(
        db.scalars(
            select(Transaction).where(
                Transaction.household_id == hid,
                Transaction.id.in_(transaction_ids),
            )
        )
    )
    if len(rows) != len(set(transaction_ids)):
        raise AccountingError("One or more transactions were not found.")
    from app.categorization_service import learn_from_transaction

    for row in rows:
        row.category_id = category.id
        row.category = category.name
        row.classification_source = "manual"
        row.classification_confidence = Decimal("1")
        learn_from_transaction(
            db, hid, row.original_description, category.name, category.id
        )
        sync_transaction_journal(db, row)
    db.commit()
    return {"updated": len(rows), "category": category.name, "category_id": category.id}


def _report_balances(
    db: Session,
    hid: str,
    entity_id: str | None,
    start: date | None,
    end: date,
) -> list[tuple[LedgerAccount, Decimal, Decimal]]:
    stmt = (
        select(
            LedgerAccount,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalLine, JournalLine.ledger_account_id == LedgerAccount.id)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(
            JournalEntry.household_id == hid,
            JournalEntry.status == "posted",
            JournalEntry.entry_date <= end,
        )
    )
    if start:
        stmt = stmt.where(JournalEntry.entry_date >= start)
    if entity_id:
        stmt = stmt.where(JournalEntry.entity_id == entity_id)
    stmt = stmt.group_by(LedgerAccount.id).order_by(LedgerAccount.code, LedgerAccount.name)
    return [(account, money(debit), money(credit)) for account, debit, credit in db.execute(stmt)]


def _validate_entity(db: Session, hid: str, entity_id: str | None) -> None:
    if entity_id and not db.scalar(
        select(AccountingEntity.id).where(
            AccountingEntity.id == entity_id,
            AccountingEntity.household_id == hid,
            AccountingEntity.is_active.is_(True),
        )
    ):
        raise AccountingError("Entity not found.")


def profit_and_loss(db: Session, hid: str, start: date, end: date, entity_id: str | None) -> dict:
    if end < start:
        raise AccountingError("End date must be on or after start date.")
    ensure_household_accounting(db, hid)
    _validate_entity(db, hid, entity_id)
    income, expenses = [], []
    for account, debit, credit in _report_balances(db, hid, entity_id, start, end):
        if account.account_type == "income":
            amount = money(credit - debit)
            if amount:
                income.append({"id": account.id, "name": account.name, "amount": str(amount)})
        elif account.account_type == "expense":
            amount = money(debit - credit)
            if amount:
                expenses.append({"id": account.id, "name": account.name, "amount": str(amount)})
    total_income = money(sum((Decimal(row["amount"]) for row in income), Decimal("0")))
    total_expenses = money(sum((Decimal(row["amount"]) for row in expenses), Decimal("0")))
    db.commit()
    return {
        "report": "profit_loss",
        "segment_id": entity_id,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "income": income,
        "expenses": expenses,
        "total_income": str(total_income),
        "total_expenses": str(total_expenses),
        "net_income": str(money(total_income - total_expenses)),
    }


def trial_balance(db: Session, hid: str, as_of: date, entity_id: str | None) -> dict:
    ensure_household_accounting(db, hid)
    _validate_entity(db, hid, entity_id)
    rows = []
    total_debit = total_credit = Decimal("0")
    for account, debit, credit in _report_balances(db, hid, entity_id, None, as_of):
        balance = money(debit - credit)
        if not balance:
            continue
        debit_balance = balance if balance > 0 else Decimal("0")
        credit_balance = -balance if balance < 0 else Decimal("0")
        total_debit += debit_balance
        total_credit += credit_balance
        rows.append({
            "id": account.id,
            "code": account.code,
            "name": account.name,
            "account_type": account.account_type,
            "debit": str(money(debit_balance)),
            "credit": str(money(credit_balance)),
        })
    db.commit()
    return {
        "report": "trial_balance",
        "entity_id": entity_id,
        "as_of": as_of.isoformat(),
        "rows": rows,
        "total_debit": str(money(total_debit)),
        "total_credit": str(money(total_credit)),
        "balanced": money(total_debit - total_credit) == 0,
    }


def balance_sheet(db: Session, hid: str, as_of: date, entity_id: str | None) -> dict:
    ensure_household_accounting(db, hid)
    _validate_entity(db, hid, entity_id)
    assets, liabilities, equity = [], [], []
    retained = Decimal("0")
    for account, debit, credit in _report_balances(db, hid, entity_id, None, as_of):
        if account.account_type == "asset":
            amount = money(debit - credit)
            if amount:
                assets.append({"id": account.id, "name": account.name, "amount": str(amount)})
        elif account.account_type == "liability":
            amount = money(credit - debit)
            if amount:
                liabilities.append({"id": account.id, "name": account.name, "amount": str(amount)})
        elif account.account_type == "equity":
            amount = money(credit - debit)
            if amount:
                equity.append({"id": account.id, "name": account.name, "amount": str(amount)})
        elif account.account_type == "income":
            retained += credit - debit
        elif account.account_type == "expense":
            retained -= debit - credit
    retained = money(retained)
    if retained:
        equity.append({"id": "current-earnings", "name": "Current earnings", "amount": str(retained)})
    total_assets = money(sum((Decimal(row["amount"]) for row in assets), Decimal("0")))
    total_liabilities = money(sum((Decimal(row["amount"]) for row in liabilities), Decimal("0")))
    total_equity = money(sum((Decimal(row["amount"]) for row in equity), Decimal("0")))
    db.commit()
    return {
        "report": "balance_sheet",
        "entity_id": entity_id,
        "as_of": as_of.isoformat(),
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "total_assets": str(total_assets),
        "total_liabilities": str(total_liabilities),
        "total_equity": str(total_equity),
        "difference": str(money(total_assets - total_liabilities - total_equity)),
        "balanced": money(total_assets - total_liabilities - total_equity) == 0,
    }
