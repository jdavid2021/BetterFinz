"""Store user-reviewed recurring charges separately from bank transactions.

Revision ID: 0028
Revises: 0027
"""

from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recurring_charge_series",
        sa.Column("id",sa.String(length=36),primary_key=True),
        sa.Column("household_id",sa.String(length=36),sa.ForeignKey("households.id",ondelete="CASCADE"),nullable=False),
        sa.Column("account_id",sa.String(length=36),sa.ForeignKey("financial_accounts.id",ondelete="CASCADE"),nullable=False),
        sa.Column("merchant_pattern",sa.String(length=180),nullable=False),
        sa.Column("name",sa.String(length=120),nullable=False),
        sa.Column("series_type",sa.String(length=30),nullable=False,server_default="subscription"),
        sa.Column("status",sa.String(length=20),nullable=False,server_default="confirmed"),
        sa.Column("typical_amount",sa.Numeric(14,2),nullable=False),
        sa.Column("frequency",sa.String(length=20),nullable=False),
        sa.Column("last_charge_date",sa.Date(),nullable=False),
        sa.Column("next_expected_date",sa.Date(),nullable=False),
        sa.Column("confidence",sa.String(length=20),nullable=False,server_default="medium"),
        sa.Column("occurrence_count",sa.Integer(),nullable=False,server_default="2"),
        sa.Column("amount_variation",sa.Numeric(7,4),nullable=False,server_default="0"),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("data_source",sa.String(length=32),nullable=False,server_default="manual"),
        sa.Column("dml_flag",sa.String(length=1),nullable=False,server_default="I"),
        sa.UniqueConstraint("household_id","account_id","merchant_pattern",name="uq_recurring_household_account_pattern"),
        sa.CheckConstraint("series_type in ('subscription','recurring_bill')",name="ck_recurring_series_type"),
        sa.CheckConstraint("status in ('confirmed','dismissed')",name="ck_recurring_status"),
    )
    op.create_index("ix_recurring_charge_series_household_id","recurring_charge_series",["household_id"])
    op.create_index("ix_recurring_charge_series_account_id","recurring_charge_series",["account_id"])
    op.create_index("ix_recurring_charge_series_next_expected_date","recurring_charge_series",["next_expected_date"])


def downgrade() -> None:
    op.drop_table("recurring_charge_series")
