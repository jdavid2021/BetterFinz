"""ignored bill suggestions

Revision ID: 0014
Revises: 0013
"""
import sqlalchemy as sa
from alembic import op

revision="0014";down_revision="0013";branch_labels=None;depends_on=None


def upgrade()->None:
    op.create_table("ignored_bill_patterns",sa.Column("id",sa.String(36),primary_key=True),sa.Column("household_id",sa.String(36),sa.ForeignKey("households.id"),nullable=False),sa.Column("merchant_pattern",sa.String(180),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.Column("data_source",sa.String(32),nullable=False,server_default="manual"),sa.Column("dml_flag",sa.String(1),nullable=False,server_default="I"),sa.UniqueConstraint("household_id","merchant_pattern",name="uq_ignored_bill_household_pattern"))
    op.create_index("ix_ignored_bill_patterns_household_id","ignored_bill_patterns",["household_id"])


def downgrade()->None:
    op.drop_table("ignored_bill_patterns")
