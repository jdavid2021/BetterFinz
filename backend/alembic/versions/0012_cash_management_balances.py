"""cash management balance buckets

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op

revision="0012";down_revision="0011";branch_labels=None;depends_on=None

def upgrade()->None:
    op.add_column("financial_accounts",sa.Column("investment_balance",sa.Numeric(14,2),nullable=False,server_default="0"))

def downgrade()->None:
    op.drop_column("financial_accounts","investment_balance")
