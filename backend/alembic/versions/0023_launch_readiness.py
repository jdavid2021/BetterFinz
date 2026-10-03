"""add verified auth and onboarding state

Revision ID: 0023
Revises: 0022
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True)))
    op.add_column(
        "users",
        sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "login_tokens",
        sa.Column(
            "purpose",
            sa.String(32),
            nullable=False,
            server_default="magic_login",
        ),
    )
    op.create_index("ix_login_tokens_purpose", "login_tokens", ["purpose"])
    op.add_column(
        "households",
        sa.Column("onboarding_dismissed_at", sa.DateTime(timezone=True)),
    )
    # Existing accounts already proved ownership through the previous auth flow.
    op.execute("UPDATE users SET email_verified_at = created_at")


def downgrade():
    op.drop_column("households", "onboarding_dismissed_at")
    op.drop_index("ix_login_tokens_purpose", table_name="login_tokens")
    op.drop_column("login_tokens", "purpose")
    op.drop_column("users", "auth_version")
    op.drop_column("users", "email_verified_at")
