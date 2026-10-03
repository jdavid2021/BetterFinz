"""social login, magic links, and passkeys

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa

revision="0017"
down_revision="0016"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("social_accounts",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False,index=True),
        sa.Column("provider",sa.String(20),nullable=False),
        sa.Column("subject",sa.String(255),nullable=False),
        sa.Column("email",sa.String(320),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("data_source",sa.String(32),nullable=False,server_default="manual"),
        sa.Column("dml_flag",sa.String(1),nullable=False,server_default="I"),
        sa.UniqueConstraint("provider","subject",name="uq_social_provider_subject"))
    op.create_table("login_tokens",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("email",sa.String(320),nullable=False,index=True),
        sa.Column("token_hash",sa.String(64),nullable=False,unique=True),
        sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("used_at",sa.DateTime(timezone=True)),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("data_source",sa.String(32),nullable=False,server_default="manual"),
        sa.Column("dml_flag",sa.String(1),nullable=False,server_default="I"))
    op.create_table("webauthn_credentials",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False,index=True),
        sa.Column("credential_id",sa.String(1024),nullable=False,unique=True),
        sa.Column("public_key",sa.Text,nullable=False),
        sa.Column("sign_count",sa.Integer,nullable=False,server_default="0"),
        sa.Column("transports",sa.String(120),nullable=False,server_default=""),
        sa.Column("label",sa.String(80),nullable=False,server_default="Passkey"),
        sa.Column("last_used_at",sa.DateTime(timezone=True)),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("data_source",sa.String(32),nullable=False,server_default="manual"),
        sa.Column("dml_flag",sa.String(1),nullable=False,server_default="I"))

def downgrade():
    op.drop_table("webauthn_credentials")
    op.drop_table("login_tokens")
    op.drop_table("social_accounts")
