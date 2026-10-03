"""add original account balance for mortgages"""
from alembic import op
import sqlalchemy as sa
revision="0003";down_revision="0002";branch_labels=None;depends_on=None
def upgrade():
    op.add_column("financial_accounts", sa.Column("original_balance", sa.Numeric(14,2), nullable=True))
def downgrade():
    op.drop_column("financial_accounts", "original_balance")
