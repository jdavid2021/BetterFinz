"""add legal acceptance and privacy workflows

Revision ID: 0025
Revises: 0024
"""

from alembic import op
import sqlalchemy as sa


revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "legal_acceptances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document", sa.String(20), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("document_digest", sa.String(64), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "document", "version", name="uq_legal_user_document_version"),
    )
    op.create_index("ix_legal_acceptances_user_id", "legal_acceptances", ["user_id"])

    op.create_table(
        "account_deletion_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("execute_after", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", name="uq_deletion_request_user"),
    )
    op.create_index(
        "ix_account_deletion_requests_due",
        "account_deletion_requests",
        ["status", "execute_after"],
    )

    op.create_table(
        "deletion_tombstones",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("subject_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
    )


def downgrade():
    op.drop_table("deletion_tombstones")
    op.drop_index("ix_account_deletion_requests_due", table_name="account_deletion_requests")
    op.drop_table("account_deletion_requests")
    op.drop_index("ix_legal_acceptances_user_id", table_name="legal_acceptances")
    op.drop_table("legal_acceptances")
