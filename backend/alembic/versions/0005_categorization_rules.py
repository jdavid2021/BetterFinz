"""household categorization learning rules"""
from alembic import op
import sqlalchemy as sa
revision="0005";down_revision="0004";branch_labels=None;depends_on=None

def upgrade():
    op.create_table("categorization_rules",sa.Column("id",sa.String(36),primary_key=True),sa.Column("household_id",sa.String(36),sa.ForeignKey("households.id"),nullable=False),sa.Column("pattern",sa.String(180),nullable=False),sa.Column("sample_description",sa.String(255),nullable=False),sa.Column("category",sa.String(80),nullable=False),sa.Column("is_active",sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column("match_count",sa.Integer(),nullable=False,server_default="0"),sa.Column("last_matched_at",sa.DateTime(timezone=True),nullable=True),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.Column("data_source",sa.String(32),nullable=False,server_default="manual_learning"),sa.Column("dml_flag",sa.String(1),nullable=False,server_default="I"),sa.UniqueConstraint("household_id","pattern",name="uq_rule_household_pattern"))
    op.create_index("ix_rule_household_active","categorization_rules",["household_id","is_active"])

def downgrade():
    op.drop_table("categorization_rules")
