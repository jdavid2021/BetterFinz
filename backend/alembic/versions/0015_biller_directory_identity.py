"""biller directory identity

Revision ID: 0015
Revises: 0014
"""
import sqlalchemy as sa
from alembic import op

revision="0015";down_revision="0014";branch_labels=None;depends_on=None

def upgrade()->None:
    op.add_column("bill_profiles",sa.Column("biller_directory_id",sa.String(80),nullable=True))
    op.create_index("ix_bill_profiles_biller_directory_id","bill_profiles",["biller_directory_id"])

def downgrade()->None:
    op.drop_index("ix_bill_profiles_biller_directory_id",table_name="bill_profiles")
    op.drop_column("bill_profiles","biller_directory_id")
