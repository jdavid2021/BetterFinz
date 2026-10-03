"""Correct clearly inferred SimpleFIN liability account kinds.

Revision ID: 0027
Revises: 0026
"""

from alembic import op


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE financial_accounts SET kind = 'credit_card' "
        "WHERE data_source = 'simplefin' AND kind = 'checking' "
        "AND lower(name) LIKE '%quicksilver%'"
    )
    op.execute(
        "UPDATE financial_accounts SET kind = 'mortgage' "
        "WHERE data_source = 'simplefin' AND kind = 'checking' "
        "AND lower(name) LIKE '%mortgage%'"
    )
    op.execute(
        "UPDATE financial_accounts SET kind = 'auto_loan' "
        "WHERE data_source = 'simplefin' AND kind = 'checking' "
        "AND lower(name) LIKE '%auto loan%'"
    )
    op.execute(
        "UPDATE financial_accounts SET kind = 'loan' "
        "WHERE data_source = 'simplefin' AND kind = 'checking' "
        "AND lower(name) LIKE '%loan%'"
    )


def downgrade() -> None:
    pass
