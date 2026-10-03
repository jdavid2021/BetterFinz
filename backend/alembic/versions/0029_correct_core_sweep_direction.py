"""Record Fidelity core cash sweeps on the correct side of the cash account.

Revision ID: 0029
Revises: 0028
"""

from alembic import op


revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

PURCHASE = (
    "lower(original_description) LIKE '%purchase into core account%' "
    "AND lower(original_description) LIKE '%fdic insured deposit%'"
)
REDEMPTION = (
    "lower(original_description) LIKE '%redemption from core account%' "
    "AND lower(original_description) LIKE '%fdic insured deposit%'"
)


CORRECTED = (
    "SELECT id FROM transactions WHERE data_source = 'simplefin' "
    f"AND ((direction = 'credit' AND {PURCHASE}) OR (direction = 'debit' AND {REDEMPTION}))"
)


def upgrade() -> None:
    # Drop the wrong-sided postings first; ensure_household_accounting reposts them on the next sync.
    op.execute(
        "DELETE FROM journal_lines WHERE journal_entry_id IN "
        f"(SELECT id FROM journal_entries WHERE transaction_id IN ({CORRECTED}))"
    )
    op.execute(f"DELETE FROM journal_entries WHERE transaction_id IN ({CORRECTED})")
    op.execute(
        "UPDATE financial_accounts SET accounting_initialized = false WHERE id IN "
        f"(SELECT account_id FROM transactions WHERE id IN ({CORRECTED}))"
    )
    op.execute(
        "UPDATE transactions SET direction = 'debit' "
        f"WHERE data_source = 'simplefin' AND direction = 'credit' AND {PURCHASE}"
    )
    op.execute(
        "UPDATE transactions SET direction = 'credit' "
        f"WHERE data_source = 'simplefin' AND direction = 'debit' AND {REDEMPTION}"
    )


def downgrade() -> None:
    pass
