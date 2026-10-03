"""statement upload history

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "statement_uploads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id"), nullable=False),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("financial_accounts.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_format", sa.String(12), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="completed"),
        sa.Column("statement_start_date", sa.Date(), nullable=True),
        sa.Column("statement_end_date", sa.Date(), nullable=True),
        sa.Column("transactions_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicates_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_source", sa.String(32), nullable=False, server_default="statement"),
        sa.Column("dml_flag", sa.String(1), nullable=False, server_default="I"),
    )
    op.create_index("ix_statement_uploads_household_id", "statement_uploads", ["household_id"])
    op.create_index("ix_statement_uploads_account_id", "statement_uploads", ["account_id"])
    op.create_index("ix_statement_uploads_file_hash", "statement_uploads", ["file_hash"])
    op.create_index("ix_statement_uploads_statement_end_date", "statement_uploads", ["statement_end_date"])
    op.create_index("ix_statement_upload_household_account", "statement_uploads", ["household_id", "account_id"])


def downgrade() -> None:
    op.drop_table("statement_uploads")
