"""convert accounting entities into optional reporting segments

Revision ID: 0022
Revises: 0021
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("households", sa.Column("segment_label", sa.String(30), nullable=False, server_default="Business"))
    op.alter_column("journal_entries", "entity_id", existing_type=sa.String(36), nullable=True)
    # Accounts and their ledger nodes now belong to the shared books. Existing
    # transaction classifications remain attached as reporting segments.
    op.execute("UPDATE financial_accounts SET entity_id = NULL")
    op.execute("UPDATE ledger_accounts SET entity_id = NULL")


def downgrade():
    # Rows without a segment cannot satisfy the old separate-books constraint.
    op.execute("DELETE FROM journal_lines WHERE journal_entry_id IN (SELECT id FROM journal_entries WHERE entity_id IS NULL)")
    op.execute("DELETE FROM journal_entries WHERE entity_id IS NULL")
    op.alter_column("journal_entries", "entity_id", existing_type=sa.String(36), nullable=False)
    op.drop_column("households", "segment_label")
