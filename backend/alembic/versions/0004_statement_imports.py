"""statement imports classifications and liabilities"""
from alembic import op
import sqlalchemy as sa
revision="0004";down_revision="0003";branch_labels=None;depends_on=None
def upgrade():
    op.add_column("transactions",sa.Column("classification_source",sa.String(30),nullable=False,server_default="rules"))
    op.add_column("transactions",sa.Column("classification_confidence",sa.Numeric(5,4),nullable=False,server_default="0"))
    op.add_column("transactions",sa.Column("fingerprint",sa.String(64),nullable=True))
    op.create_unique_constraint("uq_transactions_fingerprint","transactions",["fingerprint"])
    op.create_table("liability_statements",sa.Column("id",sa.String(36),primary_key=True),sa.Column("household_id",sa.String(36),sa.ForeignKey("households.id"),nullable=False),sa.Column("account_id",sa.String(36),sa.ForeignKey("financial_accounts.id"),nullable=False),sa.Column("opening_balance",sa.Numeric(14,2),nullable=False),sa.Column("new_balance",sa.Numeric(14,2),nullable=False),sa.Column("new_payments",sa.Numeric(14,2),nullable=False,server_default="0"),sa.Column("due_date",sa.Date(),nullable=False),sa.Column("minimum_payment",sa.Numeric(14,2),nullable=False),sa.Column("interest_rate",sa.Numeric(7,4),nullable=True),sa.Column("interest_paid",sa.Numeric(14,2),nullable=False,server_default="0"),sa.Column("statement_date",sa.Date(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.Column("data_source",sa.String(32),nullable=False,server_default="statement"),sa.Column("dml_flag",sa.String(1),nullable=False,server_default="I"))
    op.create_index("ix_liability_statement_household","liability_statements",["household_id"])
def downgrade():
    op.drop_table("liability_statements")
    op.drop_constraint("uq_transactions_fingerprint","transactions",type_="unique")
    op.drop_column("transactions","fingerprint")
    op.drop_column("transactions","classification_confidence")
    op.drop_column("transactions","classification_source")
