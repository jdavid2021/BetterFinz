"""add household notifications and preferences"""
from alembic import op
import sqlalchemy as sa
revision="0026";down_revision="0025";branch_labels=None;depends_on=None
def upgrade():
 op.create_table("notifications",sa.Column("id",sa.String(36),primary_key=True),sa.Column("household_id",sa.String(36),sa.ForeignKey("households.id",ondelete="CASCADE"),nullable=False),sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id",ondelete="CASCADE")),sa.Column("kind",sa.String(40),nullable=False),sa.Column("severity",sa.String(16),nullable=False),sa.Column("title",sa.String(140),nullable=False),sa.Column("message",sa.String(500),nullable=False),sa.Column("href",sa.String(255),nullable=False),sa.Column("dedupe_key",sa.String(180),nullable=False,unique=True),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("read_at",sa.DateTime(timezone=True)),sa.Column("dismissed_at",sa.DateTime(timezone=True)))
 for col in ("household_id","user_id","kind","created_at"):op.create_index(f"ix_notifications_{col}","notifications",[col])
 op.create_table("notification_preferences",sa.Column("id",sa.String(36),primary_key=True),sa.Column("household_id",sa.String(36),sa.ForeignKey("households.id",ondelete="CASCADE"),nullable=False),sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False,unique=True),sa.Column("low_balance",sa.Boolean(),nullable=False),sa.Column("upcoming_payments",sa.Boolean(),nullable=False),sa.Column("missing_income",sa.Boolean(),nullable=False),sa.Column("upcoming_days",sa.Integer(),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
 op.create_index("ix_notification_preferences_household_id","notification_preferences",["household_id"])
def downgrade():
 op.drop_table("notification_preferences");op.drop_table("notifications")
