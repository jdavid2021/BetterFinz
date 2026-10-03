"""income recurrence: frequency and series id

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa

revision="0019"
down_revision="0018"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("income_events",sa.Column("frequency",sa.String(20),nullable=False,server_default="one_time"))
    op.add_column("income_events",sa.Column("series_id",sa.String(36)))
    op.create_index("ix_income_events_series_id","income_events",["series_id"])

def downgrade():
    op.drop_index("ix_income_events_series_id",table_name="income_events")
    op.drop_column("income_events","series_id")
    op.drop_column("income_events","frequency")
