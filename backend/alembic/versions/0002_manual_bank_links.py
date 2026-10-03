"""add manual bank connection metadata"""
from alembic import op
import sqlalchemy as sa
revision="0002";down_revision="0001";branch_labels=None;depends_on=None
def upgrade():
    op.add_column("financial_accounts", sa.Column("connection_mode", sa.String(20), nullable=False, server_default="manual"))
    op.add_column("financial_accounts", sa.Column("institution_name", sa.String(120), nullable=True))
    op.add_column("financial_accounts", sa.Column("bank_login_url", sa.String(500), nullable=True))
def downgrade():
    op.drop_column("financial_accounts", "bank_login_url")
    op.drop_column("financial_accounts", "institution_name")
    op.drop_column("financial_accounts", "connection_mode")
