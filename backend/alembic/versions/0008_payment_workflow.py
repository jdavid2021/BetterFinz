"""add obligation payment workflow fields

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa
revision="0008";down_revision="0007";branch_labels=None;depends_on=None

def upgrade()->None:
    op.add_column("scheduled_payments",sa.Column("obligation_account_id",sa.String(36),nullable=True))
    op.add_column("scheduled_payments",sa.Column("paid_date",sa.Date(),nullable=True))
    op.add_column("scheduled_payments",sa.Column("status_source",sa.String(30),nullable=False,server_default="user"))
    op.create_foreign_key("fk_payment_obligation_account","scheduled_payments","financial_accounts",["obligation_account_id"],["id"])
    op.create_index("ix_scheduled_payments_obligation_account_id","scheduled_payments",["obligation_account_id"])

def downgrade()->None:
    op.drop_index("ix_scheduled_payments_obligation_account_id",table_name="scheduled_payments")
    op.drop_constraint("fk_payment_obligation_account","scheduled_payments",type_="foreignkey")
    op.drop_column("scheduled_payments","status_source");op.drop_column("scheduled_payments","paid_date");op.drop_column("scheduled_payments","obligation_account_id")
