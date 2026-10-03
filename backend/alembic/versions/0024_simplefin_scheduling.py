"""add scheduled SimpleFIN synchronization state

Revision ID: 0024
Revises: 0023
"""

from alembic import op
import sqlalchemy as sa


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "financial_connections",
        sa.Column("sync_started_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "financial_connections",
        sa.Column("next_sync_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "financial_connections",
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        "ix_financial_connections_next_sync_at",
        "financial_connections",
        ["next_sync_at"],
    )
    op.execute(
        """
        UPDATE financial_connections
        SET next_sync_at = COALESCE(last_successful_sync_at, CURRENT_TIMESTAMP)
        WHERE provider = 'simplefin' AND status <> 'pending'
        """
    )


def downgrade():
    op.drop_index(
        "ix_financial_connections_next_sync_at",
        table_name="financial_connections",
    )
    op.drop_column("financial_connections", "consecutive_failures")
    op.drop_column("financial_connections", "next_sync_at")
    op.drop_column("financial_connections", "sync_started_at")
