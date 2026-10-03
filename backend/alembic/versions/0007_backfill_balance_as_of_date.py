"""backfill balance dates from imported statement transactions

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE financial_accounts AS account
        SET balance_as_of_date = imported.latest_transaction_date
        FROM (
            SELECT account_id, MAX(posted_date) AS latest_transaction_date
            FROM transactions
            WHERE data_source = 'statement'
            GROUP BY account_id
        ) AS imported
        WHERE account.id = imported.account_id
          AND account.balance_as_of_date IS NULL
        """
    )


def downgrade() -> None:
    # Existing balance dates cannot be distinguished safely from backfilled dates.
    pass
