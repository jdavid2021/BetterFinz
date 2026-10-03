"""account reconciliation periods and audited transaction merges

Revision ID: 0020
Revises: 0019
"""
from alembic import op
import sqlalchemy as sa

revision="0020"
down_revision="0019"
branch_labels=None
depends_on=None

def audit_columns():
 return [sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.Column("data_source",sa.String(32),nullable=False,server_default="reconciliation"),sa.Column("dml_flag",sa.String(1),nullable=False,server_default="I")]

def upgrade():
 op.create_table("account_reconciliations",sa.Column("id",sa.String(36),primary_key=True),sa.Column("household_id",sa.String(36),sa.ForeignKey("households.id"),nullable=False),sa.Column("account_id",sa.String(36),sa.ForeignKey("financial_accounts.id"),nullable=False),sa.Column("period_start",sa.Date(),nullable=False),sa.Column("period_end",sa.Date(),nullable=False),sa.Column("opening_balance",sa.Numeric(14,2),nullable=False),sa.Column("closing_balance",sa.Numeric(14,2),nullable=False),sa.Column("credits_total",sa.Numeric(14,2),nullable=False),sa.Column("debits_total",sa.Numeric(14,2),nullable=False),sa.Column("calculated_closing_balance",sa.Numeric(14,2),nullable=False),sa.Column("difference",sa.Numeric(14,2),nullable=False),sa.Column("transaction_count",sa.Integer(),nullable=False,server_default="0"),sa.Column("pending_count",sa.Integer(),nullable=False,server_default="0"),sa.Column("reconciled_at",sa.DateTime(timezone=True),nullable=False),sa.Column("notes",sa.Text(),nullable=False,server_default=""),*audit_columns(),sa.UniqueConstraint("account_id","period_start","period_end",name="uq_reconciliation_account_period"))
 op.create_index("ix_account_reconciliations_household_id","account_reconciliations",["household_id"]);op.create_index("ix_account_reconciliations_account_id","account_reconciliations",["account_id"])
 op.create_table("transaction_merges",sa.Column("id",sa.String(36),primary_key=True),sa.Column("household_id",sa.String(36),sa.ForeignKey("households.id"),nullable=False),sa.Column("account_id",sa.String(36),sa.ForeignKey("financial_accounts.id"),nullable=False),sa.Column("survivor_transaction_id",sa.String(36),sa.ForeignKey("transactions.id"),nullable=False),sa.Column("removed_transaction_id",sa.String(36),nullable=False,unique=True),sa.Column("removed_snapshot",sa.Text(),nullable=False),sa.Column("reason",sa.String(60),nullable=False,server_default="user_confirmed_duplicate"),*audit_columns())
 op.create_index("ix_transaction_merges_household_id","transaction_merges",["household_id"]);op.create_index("ix_transaction_merges_account_id","transaction_merges",["account_id"]);op.create_index("ix_transaction_merges_survivor_transaction_id","transaction_merges",["survivor_transaction_id"])

def downgrade():
 op.drop_table("transaction_merges");op.drop_table("account_reconciliations")
