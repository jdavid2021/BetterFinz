"""recurring bill profiles

Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bill_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("merchant_pattern", sa.String(180), nullable=False),
        sa.Column("category", sa.String(80), nullable=False, server_default="Bill"),
        sa.Column("bill_type", sa.String(30), nullable=False, server_default="recurring"),
        sa.Column("amount_type", sa.String(20), nullable=False, server_default="variable"),
        sa.Column("typical_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False, server_default="monthly"),
        sa.Column("due_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("default_account_id", sa.String(36), sa.ForeignKey("financial_accounts.id"), nullable=True),
        sa.Column("website_url", sa.String(500), nullable=True),
        sa.Column("remaining_balance", sa.Numeric(14, 2), nullable=True),
        sa.Column("installments_remaining", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("dml_flag", sa.String(1), nullable=False, server_default="I"),
        sa.UniqueConstraint("household_id", "merchant_pattern", name="uq_bill_household_pattern"),
    )
    op.create_index("ix_bill_profiles_household_id", "bill_profiles", ["household_id"])
    op.create_index("ix_bill_profiles_default_account_id", "bill_profiles", ["default_account_id"])
    op.add_column("scheduled_payments", sa.Column("bill_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_scheduled_payment_bill", "scheduled_payments", "bill_profiles", ["bill_id"], ["id"])
    op.create_index("ix_scheduled_payments_bill_id", "scheduled_payments", ["bill_id"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_payments_bill_id", table_name="scheduled_payments")
    op.drop_constraint("fk_scheduled_payment_bill", "scheduled_payments", type_="foreignkey")
    op.drop_column("scheduled_payments", "bill_id")
    op.drop_table("bill_profiles")
