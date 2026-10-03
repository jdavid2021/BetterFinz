"""initial financial vertical slice"""
from alembic import op
import sqlalchemy as sa
revision="0001";down_revision=None;branch_labels=None;depends_on=None
def upgrade():
    # Models are the migration source of truth for this initial greenfield schema.
    from app.db import Base
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=op.get_bind())
def downgrade():
    from app.db import Base
    from app import models  # noqa: F401
    Base.metadata.drop_all(bind=op.get_bind())
