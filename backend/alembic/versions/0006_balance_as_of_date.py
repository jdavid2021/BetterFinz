"""track account balance effective date

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("financial_accounts", sa.Column("balance_as_of_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("financial_accounts", "balance_as_of_date")
