"""track bill payment method

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa

revision="0016"
down_revision="0015"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("bill_profiles",sa.Column("payment_method",sa.String(30),nullable=False,server_default="manual_online"))

def downgrade():
    op.drop_column("bill_profiles","payment_method")
