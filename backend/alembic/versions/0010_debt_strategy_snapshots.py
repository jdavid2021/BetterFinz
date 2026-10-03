"""save generated debt strategies

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision="0010";down_revision="0009";branch_labels=None;depends_on=None

def upgrade()->None:
    op.create_table(
        "debt_strategy_snapshots",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("household_id",sa.String(36),sa.ForeignKey("households.id"),nullable=False),
        sa.Column("payload",sa.Text(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("data_source",sa.String(32),nullable=False),
        sa.Column("dml_flag",sa.String(1),nullable=False),
    )
    op.create_index("ix_debt_strategy_snapshots_household_id","debt_strategy_snapshots",["household_id"])

def downgrade()->None:
    op.drop_index("ix_debt_strategy_snapshots_household_id",table_name="debt_strategy_snapshots")
    op.drop_table("debt_strategy_snapshots")
