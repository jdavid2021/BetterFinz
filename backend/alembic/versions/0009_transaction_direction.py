"""preserve transaction debit or credit direction

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

revision="0009";down_revision="0008";branch_labels=None;depends_on=None

def upgrade()->None:
    op.add_column("transactions",sa.Column("direction",sa.String(10),nullable=False,server_default="unknown"))
    op.execute("UPDATE transactions SET direction='credit' WHERE category='Income'")
    op.execute("UPDATE transactions SET direction='debit' WHERE category IN ('Mortgage Payment','Loan Payment','Credit Card Payment','Bill','Groceries','Transportation','Healthcare','Dining','Shopping')")

def downgrade()->None:
    op.drop_column("transactions","direction")
